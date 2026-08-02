"""The intake queue: what arrived, what it appears to be, and what was decided.

Four things are asserted here, and each of them is a promise the queue makes to
the person reading it:

* **A fetch shows what is new, not the mailbox again.** The checkpoint advances
  on success and only on success, and a message already in the queue is never
  offered twice.
* **A reading is never a claim.** Every triage signal carries the words it was
  read from; a message nothing could be read in is ``unclear`` rather than
  guessed at; and a model's suggestion is discarded unless it can point at the
  message.
* **Nothing enters the archive without a human.** Preservation and adoption are
  acts with a stated reason, and what they produce is an ordinary document —
  indexed, retrievable, and citable through the same verbatim machinery as
  every other page in this product.
* **The mailbox is untouched.** Every call this block makes is a GET.

Nothing in this file needs a credential, a network or a model. That is part of
what is being asserted: a queue that needed one would be a queue that could not
be reviewed offline.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from app.integrations.intake import import_eml
from app.integrations.mailbox import fetch_new, note_fetch_failure
from app.integrations.models import MailboxCheckpoint, SourceEvent
from app.integrations.preserve import (
    PreservationError,
    citation_for,
    preserve_message,
    render_pdf,
)
from app.integrations.resolve import (
    ResolutionError,
    reopen_source_event,
    resolve_source_event,
)
from app.integrations.threads import build_threads, strip_reply_prefixes, thread_key_for
from app.integrations.triage import analyze, refine_with_model

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
MAIL = FIXTURES / "mail"


# ---------------------------------------------------------------------------
# Building blocks
# ---------------------------------------------------------------------------


def message(
    *,
    subject: str,
    body: str,
    sender: str = "anna@snosvangen.example",
    display: str = "Anna Lind",
    message_id: str = "<m1@snosvangen.example>",
    date_header: str = "Tue, 03 Feb 2026 08:14:00 +0100",
    in_reply_to: str = "",
    references: str = "",
) -> bytes:
    """One minimal, real `.eml`. Built rather than stored so a test can say
    exactly which header it is about."""
    headers = [
        f"From: {display} <{sender}>",
        "To: Styrelsen <styrelsen@gjutformen12.example>",
        f"Subject: {subject}",
        f"Date: {date_header}",
        f"Message-ID: {message_id}",
    ]
    if in_reply_to:
        headers.append(f"In-Reply-To: {in_reply_to}")
    if references:
        headers.append(f"References: {references}")
    headers += [
        'Content-Type: text/plain; charset="utf-8"',
        "MIME-Version: 1.0",
        "",
        body,
    ]
    return "\r\n".join(headers).encode("utf-8")


@pytest.fixture()
def queue(integration_env):
    """A tenant with the seeded corpus, and a helper that imports one message."""

    def take_in(raw: bytes, **kwargs) -> SourceEvent:
        return import_eml(
            store=integration_env.store,
            integrations=integration_env.integrations,
            raw=raw,
            filename=kwargs.pop("filename", "meddelande.eml"),
            imported_by=kwargs.pop("imported_by", "admin-1"),
            **kwargs,
        )

    integration_env.take_in = take_in
    return integration_env


class StubMailbox:
    """A mailbox that answers from a list, and records what it was asked.

    Stands in for :class:`app.integrations.graph_mail.GraphMailAdapter` at the
    seam the fetch actually uses. The real adapter's own HTTP behaviour — the
    URL, the ``$filter``, the GET-only rule — is asserted in
    ``test_integrations_live.py`` against the transport stub, which is where
    that belongs.
    """

    def __init__(self, messages: list[dict]) -> None:
        self._messages = messages
        self.since_asked: list[str] = []
        self.fetched: list[str] = []

    def list_messages(self, *, limit, only_with_attachments, since=""):
        from app.integrations.graph_mail import MailboxMessage

        self.since_asked.append(since)
        rows = [
            MailboxMessage(
                id=m["id"],
                subject=m["subject"],
                from_address=m.get("from", "anna@snosvangen.example"),
                from_display=m.get("display", "Anna"),
                received_at=m["received_at"],
                has_attachments=False,
                internet_message_id=m.get("internet_message_id", ""),
                preview="",
            )
            for m in self._messages
            if not since or m["received_at"] >= since
        ]
        return rows[:limit]

    def get_message_mime(self, message_id: str) -> bytes:
        self.fetched.append(message_id)
        for m in self._messages:
            if m["id"] == message_id:
                return m["raw"]
        raise LookupError(message_id)


# ---------------------------------------------------------------------------
# Incremental fetching
# ---------------------------------------------------------------------------


class TestIncrementalFetch:
    def test_the_first_fetch_asks_for_everything(self, queue):
        mailbox = StubMailbox(
            [
                {
                    "id": "AAA",
                    "subject": "Offert takomläggning",
                    "received_at": "2026-02-03T08:14:00Z",
                    "internet_message_id": "<a@x.example>",
                    "raw": message(subject="Offert takomläggning", body="Vår offert bifogas.",
                                   message_id="<a@x.example>"),
                }
            ]
        )
        result = fetch_new(
            store=queue.store, adapter=mailbox, provider="microsoft-graph",
            folder="inbox", user_id="admin-1",
        )
        assert mailbox.since_asked == [""], "en första hämtning får inte filtrera bort något"
        assert result.seen == 1 and len(result.imported) == 1
        assert result.checkpoint.high_water_mark == "2026-02-03T08:14:00Z"
        assert result.checkpoint.last_new_count == 1

    def test_the_second_fetch_asks_only_for_what_is_newer(self, queue):
        first = {
            "id": "AAA",
            "subject": "Offert takomläggning",
            "received_at": "2026-02-03T08:14:00Z",
            "internet_message_id": "<a@x.example>",
            "raw": message(subject="Offert takomläggning", body="Vår offert bifogas.",
                           message_id="<a@x.example>"),
        }
        second = {
            "id": "BBB",
            "subject": "Sv: Offert takomläggning",
            "received_at": "2026-02-10T09:00:00Z",
            "internet_message_id": "<b@x.example>",
            "raw": message(subject="Sv: Offert takomläggning", body="Vi godkänner offerten.",
                           message_id="<b@x.example>", in_reply_to="<a@x.example>",
                           date_header="Tue, 10 Feb 2026 10:00:00 +0100"),
        }
        mailbox = StubMailbox([first])
        fetch_new(store=queue.store, adapter=mailbox, provider="microsoft-graph",
                  folder="inbox", user_id="admin-1")

        mailbox._messages.append(second)
        result = fetch_new(store=queue.store, adapter=mailbox, provider="microsoft-graph",
                           folder="inbox", user_id="admin-1")

        assert mailbox.since_asked[-1] == "2026-02-03T08:14:00Z"
        assert len(result.imported) == 1, "bara det nya meddelandet ska tas in"
        assert result.imported[0].subject == "Sv: Offert takomläggning"
        # The first message is inside the at-or-after window and was offered
        # again; it must be recognised, not re-imported.
        assert result.already_known == 1
        assert result.checkpoint.high_water_mark == "2026-02-10T09:00:00Z"

    def test_the_checkpoint_is_per_folder(self, queue):
        mailbox = StubMailbox([
            {"id": "AAA", "subject": "A", "received_at": "2026-02-03T08:14:00Z",
             "internet_message_id": "<a@x.example>",
             "raw": message(subject="A", body="text", message_id="<a@x.example>")},
        ])
        fetch_new(store=queue.store, adapter=mailbox, provider="microsoft-graph",
                  folder="inbox", user_id="admin-1")
        # Pointing the installation at another folder must not make it believe
        # it has already seen everything in it.
        other = queue.integrations.get_mailbox_checkpoint("microsoft-graph", "archive")
        assert other.high_water_mark == ""

    def test_a_refused_message_is_reported_and_not_half_imported(self, queue):
        """The `.eml` format refuses a whole message rather than dropping one
        attachment. A batch fetch must say so — silence would let an operator
        believe the queue is the mailbox."""
        raw = (MAIL / "underlag-i-kalkylblad.eml").read_bytes()
        mailbox = StubMailbox([
            {"id": "XLS", "subject": "Underlag", "received_at": "2026-02-03T08:14:00Z",
             "internet_message_id": "<xls@x.example>", "raw": raw},
        ])
        result = fetch_new(store=queue.store, adapter=mailbox, provider="microsoft-graph",
                           folder="inbox", user_id="admin-1")

        assert result.imported == []
        assert len(result.skipped) == 1
        assert result.skipped[0].code == "unsupported_attachment"
        assert "PDF" in result.skipped[0].reason or "pdf" in result.skipped[0].reason
        assert queue.integrations.list_source_events() == [], "ingenting halvimporterades"
        # The refusal travels on the checkpoint, so the screen can show it
        # without the operator having been watching when it happened.
        assert result.checkpoint.last_skipped[0].code == "unsupported_attachment"

    def test_an_unreadable_message_is_not_skipped_forever(self, queue):
        """A newer message must not move the checkpoint past an older one the
        fetch could not read — that would turn a transient failure into a
        permanent, silent one."""

        class Flaky(StubMailbox):
            def get_message_mime(self, message_id):
                if message_id == "OLD":
                    raise TimeoutError("brevlådan svarade inte")
                return super().get_message_mime(message_id)

        mailbox = Flaky([
            {"id": "OLD", "subject": "Äldre", "received_at": "2026-02-03T08:00:00Z",
             "internet_message_id": "<old@x.example>", "raw": b""},
            {"id": "NEW", "subject": "Nyare", "received_at": "2026-02-04T08:00:00Z",
             "internet_message_id": "<new@x.example>",
             "raw": message(subject="Nyare", body="text", message_id="<new@x.example>")},
        ])
        result = fetch_new(store=queue.store, adapter=mailbox, provider="microsoft-graph",
                           folder="inbox", user_id="admin-1")

        assert len(result.imported) == 1
        assert result.skipped[0].code == "unreadable"
        assert result.checkpoint.high_water_mark == "2026-02-03T08:00:00Z", (
            "checkpointen får inte passera det meddelande som inte gick att läsa"
        )

    def test_a_failed_fetch_does_not_move_the_checkpoint(self, queue):
        queue.integrations.put_mailbox_checkpoint(
            MailboxCheckpoint(
                provider="microsoft-graph", folder="inbox",
                high_water_mark="2026-02-03T08:14:00Z", last_fetched_at="2026-02-03T09:00:00Z",
            )
        )
        after = note_fetch_failure(
            store=queue.store, provider="microsoft-graph", folder="inbox",
            error="microsoft-graph: 503",
        )
        assert after.high_water_mark == "2026-02-03T08:14:00Z"
        assert after.last_error == "microsoft-graph: 503"

    def test_graph_timestamps_are_normalised_for_the_filter(self):
        from app.integrations.graph_mail import graph_timestamp

        # An offset stamp — which is what utc_now_iso produces — must become a
        # Z literal, or Graph answers 400 on a filter this product built.
        assert graph_timestamp("2026-02-03T09:14:00+01:00") == "2026-02-03T08:14:00Z"
        assert graph_timestamp("2026-02-03T08:14:00Z") == "2026-02-03T08:14:00Z"
        assert graph_timestamp("") == ""
        # Unparseable means no filter, never a filter built from nonsense: too
        # much material is a slow fetch, a bad filter is a silent empty one.
        assert graph_timestamp("i förrgår") == ""


# ---------------------------------------------------------------------------
# Conversations
# ---------------------------------------------------------------------------


class TestThreads:
    @pytest.mark.parametrize(
        "subject,expected",
        [
            ("SV: Re: Offert takomläggning", "Offert takomläggning"),
            ("Re[2]: Fråga om jourtid", "Fråga om jourtid"),
            ("VB: Fwd: Faktura 2026-114", "Faktura 2026-114"),
            ("Offert takomläggning", "Offert takomläggning"),
        ],
    )
    def test_reply_prefixes_are_stripped(self, subject, expected):
        assert strip_reply_prefixes(subject) == expected

    def test_a_reply_joins_its_thread_through_the_headers(self, queue):
        first = queue.take_in(
            message(subject="Offert takomläggning", body="Vår offert bifogas.",
                    message_id="<a@x.example>")
        )
        second = queue.take_in(
            message(subject="Ett helt annat ämne", body="Vi godkänner offerten.",
                    message_id="<b@x.example>", in_reply_to="<a@x.example>",
                    date_header="Tue, 10 Feb 2026 10:00:00 +0100")
        )
        threads = build_threads(queue.integrations.list_source_events())
        assert len(threads) == 1, "svaret ska hamna i samma tråd trots annat ämne"
        assert {e.id for e in threads[0].events} == {first.id, second.id}

    def test_a_reply_joins_its_thread_through_the_subject(self, queue):
        """The common case: a reply typed into a fresh message, no headers."""
        queue.take_in(message(subject="Offert takomläggning", body="Vår offert bifogas.",
                              message_id="<a@x.example>"))
        queue.take_in(message(subject="SV: Offert takomläggning", body="Vi godkänner.",
                              message_id="<b@x.example>",
                              date_header="Tue, 10 Feb 2026 10:00:00 +0100"))
        threads = build_threads(queue.integrations.list_source_events())
        assert len(threads) == 1
        assert threads[0].subject == "Offert takomläggning"

    def test_two_counterparties_with_one_subject_stay_apart(self, queue):
        queue.take_in(message(subject="Offert", body="Vår offert.", sender="a@ett.example",
                              message_id="<a@ett.example>"))
        queue.take_in(message(subject="Offert", body="Vår offert.", sender="b@tva.example",
                              message_id="<b@tva.example>"))
        threads = build_threads(queue.integrations.list_source_events())
        assert len(threads) == 2, "samma ämne från olika motparter är inte en tråd"

    def test_a_thread_card_carries_what_it_promises(self, queue):
        queue.take_in(message(subject="Offert takomläggning", body="Vår offert bifogas.",
                              message_id="<a@x.example>"))
        queue.take_in(message(subject="SV: Offert takomläggning",
                              body="Kan ni bekräfta att ni godkänner offerten?",
                              message_id="<b@x.example>", display="Bo Ek",
                              date_header="Tue, 10 Feb 2026 10:00:00 +0100"))
        card = build_threads(queue.integrations.list_source_events())[0].public()

        assert card["subject"] == "Offert takomläggning"
        assert card["message_count"] == 2
        assert card["attachment_count"] == 0
        assert card["latest_sender"] == "anna@snosvangen.example"
        assert card["latest_sender_display"] == "Bo Ek"
        assert card["first_at"] < card["latest_at"]
        assert card["open_count"] == 2 and card["resolved"] is False
        assert card["awaiting_reply"] is True, "sista meddelandet ställer en fråga"

    def test_an_event_from_an_older_build_still_groups(self, queue):
        """A queue written before threading has no stored key, and must read
        correctly without a migration that decides conversations for people."""
        event = queue.take_in(message(subject="Offert", body="Vår offert.",
                                      message_id="<a@x.example>"))
        queue.integrations.update_source_event(
            event.model_copy(update={"thread_key": "", "thread_subject": ""})
        )
        threads = build_threads(queue.integrations.list_source_events())
        assert len(threads) == 1 and threads[0].subject == "Offert"

    def test_thread_key_is_decided_once_at_import(self, queue):
        first = queue.take_in(message(subject="Offert", body="Vår offert.",
                                      message_id="<a@x.example>"))
        assert first.thread_key, "tråden avgörs vid import, inte vid läsning"
        key, subject = thread_key_for(first, [])
        assert subject == "Offert"


# ---------------------------------------------------------------------------
# Triage
# ---------------------------------------------------------------------------


class TestTriage:
    def test_an_invoice_mail_reads_as_an_invoice(self, queue):
        event = queue.take_in((MAIL / "faktura-snosvangen-2026-02.eml").read_bytes())
        assert event.triage is not None
        assert event.triage.category == "invoice"
        assert event.triage.suggested_by == "regelmotor"

    def test_an_approval_reads_as_a_decision_and_says_what_with(self, queue):
        event = queue.take_in(
            message(
                subject="SV: Offert takomläggning",
                body="Hej,\n\nVi godkänner offerten på 148 000 kr och sätter igång vecka 12.\n",
                message_id="<b@x.example>",
            )
        )
        triage = event.triage
        assert triage.category == "decision_or_approval"
        assert triage.contains_decision is True
        decisions = [s for s in triage.signals if s.kind == "decision"]
        assert decisions, "ett beslut måste komma med den mening det lästes ur"
        assert "godkänner" in decisions[0].quote

    def test_a_question_reads_as_awaiting_a_reply(self, queue):
        event = queue.take_in((MAIL / "fraga-fran-medlem.eml").read_bytes())
        assert event.triage.awaiting_reply is True
        assert [s for s in event.triage.signals if s.kind == "question"]

    def test_every_signal_carries_the_words_it_was_read_from(self, queue):
        event = queue.take_in(
            message(
                subject="Påminnelse: svar senast 2026-09-30",
                body="Vi behöver ert besked senast den 30 september 2026. Beloppet är 12 500 kr.",
                message_id="<c@x.example>",
            )
        )
        assert event.triage.signals
        haystack = f"{event.subject} {event.body_text}"
        for signal in event.triage.signals:
            assert signal.quote.strip(), f"{signal.kind} saknar citat"
            if signal.source in ("subject", "body") and signal.kind != "supplier":
                # Whitespace-folded rather than byte-identical: the quote is
                # rebuilt from words, which is what makes it findable in the
                # preserved document later.
                assert " ".join(signal.quote.split()) in " ".join(haystack.split())

    def test_dates_and_amounts_are_read_with_the_products_own_scanners(self, queue):
        event = queue.take_in(
            message(
                subject="Fakturaunderlag",
                body="Fakturan förfaller den 30 september 2026 och avser 12 500 kr.",
                message_id="<d@x.example>",
            )
        )
        values = {s.value for s in event.triage.signals}
        assert "2026-09-30" in values
        assert any("12 500" in v or "12500" in v for v in values)

    def test_a_message_with_nothing_readable_is_unclear_not_guessed(self, queue):
        event = queue.take_in(message(subject="...", body="...", message_id="<e@x.example>"))
        assert event.triage.category in ("unclear", "information")
        if event.triage.category == "unclear":
            assert event.triage.uncertainty, "oklart måste säga att det är oklart"

    def test_related_records_state_a_basis_a_human_can_check(self, queue):
        queue.take_in(message(subject="Faktura 2026-114", body="Bifogat faktura.",
                              message_id="<f1@x.example>"))
        event = queue.take_in(message(subject="Faktura 2026-115", body="Bifogat faktura.",
                                      message_id="<f2@x.example>",
                                      date_header="Tue, 10 Mar 2026 10:00:00 +0100"))
        earlier = [r for r in event.triage.related if r.kind == "source_event"]
        assert earlier, "tidigare post från samma avsändare ska föreslås"
        assert earlier[0].basis, "ett förslag utan angiven grund är inte kontrollerbart"

    def test_the_engine_never_calls_itself_ai(self, queue):
        event = queue.take_in(message(subject="Offert", body="Vår offert bifogas.",
                                      message_id="<g@x.example>"))
        assert event.triage.suggested_by == "regelmotor"

    def test_a_model_suggestion_that_cannot_be_grounded_is_discarded(self, queue, monkeypatch):
        """The rule that makes model refinement safe: a category the model
        cannot point at in the message does not get to relabel it."""
        event = queue.take_in(
            message(subject="Offert takomläggning", body="Vår offert bifogas.",
                    message_id="<h@x.example>")
        )
        baseline = event.triage

        class Ungrounded:
            name = "selfhosted"
            model = "gemma4:e12b"

            def complete(self, system, user, *, max_tokens, model):
                return (
                    '{"category": "invoice", "headline": "Faktura förfaller",'
                    ' "why_it_matters": "Den ska betalas",'
                    ' "evidence": "Fakturan förfaller den 1 mars 2026."}'
                )

        monkeypatch.setattr("app.llm.pick_provider", lambda: Ungrounded())
        refined = refine_with_model(event, baseline)

        assert refined.category == baseline.category, "obelagt förslag får inte byta kategori"
        assert refined.suggested_by == "regelmotor"
        assert "kunde inte beläggas" in refined.uncertainty

    def test_a_grounded_model_suggestion_is_used_and_named(self, queue, monkeypatch):
        event = queue.take_in(
            message(subject="Meddelande", body="Vi godkänner offerten på 148 000 kr.",
                    message_id="<i@x.example>")
        )

        class Grounded:
            name = "selfhosted"
            model = "gemma4:e12b"

            def complete(self, system, user, *, max_tokens, model):
                return (
                    '{"category": "decision_or_approval",'
                    ' "headline": "Offerten är godkänd",'
                    ' "why_it_matters": "Ett godkännande bör kunna beläggas.",'
                    ' "evidence": "Vi godkänner offerten på 148 000 kr."}'
                )

        monkeypatch.setattr("app.llm.pick_provider", lambda: Grounded())
        refined = refine_with_model(event, analyze(queue.store, event))

        assert refined.category == "decision_or_approval"
        assert refined.headline == "Offerten är godkänd"
        assert "språkmodell" in refined.suggested_by and "gemma4" in refined.suggested_by

    def test_a_broken_provider_leaves_the_deterministic_reading_intact(self, queue, monkeypatch):
        event = queue.take_in(message(subject="Offert", body="Vår offert bifogas.",
                                      message_id="<j@x.example>"))
        baseline = event.triage

        class Broken:
            name = "selfhosted"
            model = "gemma4:e12b"

            def complete(self, *a, **k):
                raise RuntimeError("tunneln är nere")

        monkeypatch.setattr("app.llm.pick_provider", lambda: Broken())
        assert refine_with_model(event, baseline).category == baseline.category

    def test_the_test_suite_never_reaches_a_model(self):
        """`fake` and `none` are not generation paths, so the whole queue —
        including this suite — runs deterministically without a flag."""
        from app.integrations.triage import model_available

        assert model_available() is False


# ---------------------------------------------------------------------------
# Preserving the message itself
# ---------------------------------------------------------------------------


class TestPreservation:
    def test_a_preserved_message_becomes_a_searchable_citable_document(self, queue):
        event = queue.take_in(
            message(
                subject="SV: Offert takomläggning",
                body=(
                    "Hej,\n\nVi godkänner offerten på 148 000 kr och sätter igång vecka 12.\n"
                    "Uppsägning skall ske skriftligen senast tre månader före avtalstidens utgång.\n"
                ),
                message_id="<k@x.example>",
            )
        )
        preserved = preserve_message(
            store=queue.store, integrations=queue.integrations, event_id=event.id,
            user_id="admin-1", note="Godkännandet måste gå att belägga.",
        )
        doc_id = preserved.preserved_document_id
        assert doc_id in queue.store.documents

        # Searchable through the ordinary index — no second retrieval path.
        hits = queue.store.index.search(
            "godkänner offerten takomläggning", weight=0.5, candidates=50, top_k=5,
            min_confidence=0.0,
        )
        assert doc_id in {h.document_id for h in hits}

        # Citable through the ordinary verbatim machinery, with real rects.
        citation = citation_for(
            queue.store, doc_id, "Vi godkänner offerten på 148 000 kr och sätter igång vecka 12."
        )
        assert citation is not None
        assert citation.page == 1 and citation.rects
        assert citation.document_id == doc_id

    def test_the_preserved_document_carries_its_provenance(self, queue):
        event = queue.take_in(message(subject="Beslut", body="Vi godkänner offerten.",
                                      message_id="<l@x.example>"))
        preserved = preserve_message(
            store=queue.store, integrations=queue.integrations, event_id=event.id,
            user_id="admin-1", note="Behövs som underlag.",
        )
        pages = queue.store.pages[preserved.preserved_document_id]
        text = " ".join(w.text for w in pages[0].words)
        assert event.content_sha256 in text, "hashen ska stå i dokumentet självt"
        assert "anna@snosvangen.example" in text
        assert "admin-1" in text

    def test_preservation_requires_a_stated_reason(self, queue):
        event = queue.take_in(message(subject="Beslut", body="Vi godkänner offerten.",
                                      message_id="<m@x.example>"))
        with pytest.raises(PreservationError) as exc:
            preserve_message(store=queue.store, integrations=queue.integrations,
                             event_id=event.id, user_id="admin-1", note="   ")
        assert "varför" in str(exc.value)

    def test_preserving_twice_does_not_make_a_second_copy(self, queue):
        event = queue.take_in(message(subject="Beslut", body="Vi godkänner offerten.",
                                      message_id="<n@x.example>"))
        first = preserve_message(store=queue.store, integrations=queue.integrations,
                                 event_id=event.id, user_id="admin-1", note="Underlag.")
        before = len(queue.store.documents)
        again = preserve_message(store=queue.store, integrations=queue.integrations,
                                 event_id=event.id, user_id="admin-1", note="Underlag igen.")
        assert again.preserved_document_id == first.preserved_document_id
        assert len(queue.store.documents) == before

    def test_a_message_with_no_text_cannot_be_preserved_as_text(self, queue):
        event = queue.take_in((MAIL / "faktura-snosvangen-2026-02.eml").read_bytes())
        stripped = queue.integrations.update_source_event(
            event.model_copy(update={"body_text": "   "})
        )
        with pytest.raises(PreservationError) as exc:
            preserve_message(store=queue.store, integrations=queue.integrations,
                             event_id=stripped.id, user_id="admin-1", note="Underlag.")
        assert "bilagan" in str(exc.value).lower()

    def test_a_preserved_message_may_not_corroborate_its_own_invoice(self, queue):
        """A preserved message is evidence — a named person kept it with a
        stated reason. It is still not evidence about the invoice that arrived
        in it: the covering mail says what the invoice says, and letting it
        verify verbatim against the sender's own sentence is exactly the
        self-corroboration the exclusion exists to prevent."""
        from app.integrations.review import evidence_excluded_document_ids

        event = queue.take_in((MAIL / "faktura-snosvangen-2026-02.eml").read_bytes())
        preserved = preserve_message(
            store=queue.store, integrations=queue.integrations, event_id=event.id,
            user_id="admin-1", note="Följebrevet hör till underlaget.",
        )
        invoice = queue.import_invoice("SI-2026-114")
        invoice = queue.integrations.upsert_invoice(
            invoice.model_copy(update={"source_event_id": event.id})
        )

        excluded = evidence_excluded_document_ids(queue.store, invoice)
        assert preserved.preserved_document_id in excluded
        # …and the attachments of that same event, adopted or not.
        assert {a.document_id for a in preserved.attachments} <= excluded

    def test_a_preserved_message_is_evidence_for_everything_else(self, queue):
        """The other half of the rule: preservation *is* the adoption bar, so a
        preserved message is not excluded the way an unadopted attachment is."""
        from app.integrations.review import unadopted_incoming_document_ids

        event = queue.take_in(
            message(subject="Uppsägningstid", body="Uppsägningstiden är tre månader.",
                    message_id="<x1@x.example>")
        )
        preserved = preserve_message(
            store=queue.store, integrations=queue.integrations, event_id=event.id,
            user_id="admin-1", note="Källa för uppsägningstiden.",
        )
        assert preserved.preserved_document_id not in unadopted_incoming_document_ids(queue.store)

    def test_a_rendered_message_is_a_readable_pdf(self, queue):
        event = queue.take_in(
            message(subject="Långt meddelande", body="Rad.\n" * 400, message_id="<o@x.example>")
        )
        pdf = render_pdf(event)
        assert pdf.startswith(b"%PDF-")


# ---------------------------------------------------------------------------
# Outcomes
# ---------------------------------------------------------------------------


class TestResolution:
    def _event(self, queue, **kwargs) -> SourceEvent:
        return queue.take_in(
            message(
                subject=kwargs.pop("subject", "SV: Offert takomläggning"),
                body=kwargs.pop(
                    "body",
                    "Vi godkänner offerten på 148 000 kr. Svar önskas senast den 30 september 2026.",
                ),
                message_id=kwargs.pop("message_id", "<p@x.example>"),
                **kwargs,
            )
        )

    def test_take_in_preserves_and_records_where_it_went(self, queue):
        event = self._event(queue)
        settled = resolve_source_event(
            store=queue.store, event_id=event.id, user_id="admin-1",
            kinds=["take_in"], note="Godkännandet ska gå att belägga.",
        )
        assert settled.preserved_document_id in queue.store.documents
        assert settled.review_status == "approved"
        assert settled.resolution.outcomes[0].kind == "take_in"
        assert settled.resolution.outcomes[0].ref_id == settled.preserved_document_id

    def test_take_in_and_create_task_is_one_act(self, queue):
        event = self._event(queue)
        settled = resolve_source_event(
            store=queue.store, event_id=event.id, user_id="admin-1",
            kinds=["take_in", "create_task"], note="Godkännandet ska gå att belägga.",
            task={"title": "Boka in takomläggning vecka 12", "responsible": "Bo"},
        )
        kinds = [o.kind for o in settled.resolution.outcomes]
        assert "take_in" in kinds and "create_task" in kinds

        task_id = next(o.ref_id for o in settled.resolution.outcomes if o.kind == "create_task")
        task = queue.store.tasks.get_task(task_id)
        assert task.origin.kind == "source_event" and task.origin.ref_id == event.id
        # The evidence travelled: the task opens the preserved message at the
        # line the work was decided from.
        assert task.citations, "en uppgift ur bevarad post ska bära sitt citat"
        assert task.citations[0].document_id == settled.preserved_document_id
        assert task.citations[0].rects

    def test_monitor_creates_an_approved_watch_not_a_proposal(self, queue):
        event = self._event(queue)
        settled = resolve_source_event(
            store=queue.store, event_id=event.id, user_id="admin-1",
            kinds=["monitor"], note="Vi väntar svar.",
            watch={"due_date": "2026-09-30", "kind": "expected_reply"},
            today=date(2026, 3, 1),
        )
        watch_id = next(o.ref_id for o in settled.resolution.outcomes if o.kind == "monitor")
        watch = queue.store.watches.get_watch(watch_id)
        assert watch.status == "approved", "en människa beslutade nyss — det är inget förslag"
        assert watch.kind == "expected_reply"
        assert watch.due_date == "2026-09-30"
        assert "inkommande post" in watch.derivation

    def test_a_malformed_task_or_watch_payload_is_a_refusal_not_a_crash(self, queue):
        """`task` and `watch` are open dictionaries on the route — the right
        shape for two different domains' payloads. The cost is that a client
        can put the wrong type in one, and that has to read as a refusal."""
        event = self._event(queue)
        with pytest.raises(ResolutionError) as exc:
            resolve_source_event(store=queue.store, event_id=event.id, user_id="admin-1",
                                 kinds=["create_task"], task={"title": 17})
        assert "text" in str(exc.value)

        with pytest.raises(ResolutionError) as exc:
            resolve_source_event(store=queue.store, event_id=event.id, user_id="admin-1",
                                 kinds=["monitor"],
                                 watch={"due_date": "2026-09-30", "remind_lead_days": "snart"})
        assert "antal dagar" in str(exc.value)

    def test_a_watch_needs_a_real_date(self, queue):
        event = self._event(queue)
        with pytest.raises(ResolutionError) as exc:
            resolve_source_event(store=queue.store, event_id=event.id, user_id="admin-1",
                                 kinds=["monitor"], watch={"due_date": "snart"})
        assert "ÅÅÅÅ-MM-DD" in str(exc.value)

    def test_already_handled_settles_without_touching_the_archive(self, queue):
        event = self._event(queue)
        before = len(queue.store.documents)
        settled = resolve_source_event(store=queue.store, event_id=event.id,
                                       user_id="admin-1", kinds=["already_handled"])
        assert settled.review_status == "approved"
        assert settled.preserved_document_id is None
        assert len(queue.store.documents) == before

    def test_not_relevant_removes_it_from_the_queue_only(self, queue):
        event = self._event(queue)
        settled = resolve_source_event(store=queue.store, event_id=event.id,
                                       user_id="admin-1", kinds=["not_relevant"])
        assert settled.review_status == "dismissed"
        # Still a record: the queue entry, its provenance and its reading stay.
        assert queue.integrations.get_source_event(event.id) is not None
        assert settled.content_sha256 == event.content_sha256

    def test_the_exclusive_outcomes_cannot_be_combined(self, queue):
        event = self._event(queue)
        with pytest.raises(ResolutionError) as exc:
            resolve_source_event(store=queue.store, event_id=event.id, user_id="admin-1",
                                 kinds=["not_relevant", "take_in"], note="Motsägelse.")
        assert "kan inte kombineras" in str(exc.value)

    def test_taking_in_requires_a_stated_reason(self, queue):
        event = self._event(queue)
        with pytest.raises(ResolutionError) as exc:
            resolve_source_event(store=queue.store, event_id=event.id,
                                 user_id="admin-1", kinds=["take_in"])
        assert "varför" in str(exc.value)

    def test_an_attachment_is_adopted_only_when_chosen(self, queue):
        event = queue.take_in((MAIL / "faktura-snosvangen-2026-02.eml").read_bytes())
        settled = resolve_source_event(
            store=queue.store, event_id=event.id, user_id="admin-1",
            kinds=["take_in"], note="Fakturaunderlag.",
        )
        assert all(not a.archived for a in settled.attachments), (
            "en bilaga blir inte arkiv bara för att mejlet bevarades"
        )

        chosen = settled.attachments[0].id
        again = resolve_source_event(
            store=queue.store, event_id=event.id, user_id="admin-1",
            kinds=["take_in"], note="Avtalet hör till underlaget.",
            attachment_ids=[chosen],
        )
        adopted = next(a for a in again.attachments if a.id == chosen)
        assert adopted.archived and adopted.archived_by == "admin-1"
        assert adopted.archive_note == "Avtalet hör till underlaget."

    def test_reopening_keeps_what_the_resolution_produced(self, queue):
        event = self._event(queue)
        settled = resolve_source_event(
            store=queue.store, event_id=event.id, user_id="admin-1",
            kinds=["take_in", "create_task"], note="Underlag.",
            task={"title": "Boka takomläggning"},
        )
        task_id = next(o.ref_id for o in settled.resolution.outcomes if o.kind == "create_task")
        document_id = settled.preserved_document_id

        reopened = reopen_source_event(store=queue.store, event_id=event.id)
        assert reopened.resolution is None and reopened.review_status == "open"
        # A task that existed is a record of a decision; reopening a card is
        # not a decision about it.
        assert queue.store.tasks.get_task(task_id) is not None
        assert document_id in queue.store.documents


# ---------------------------------------------------------------------------
# The HTTP surface, and the boundary it inherits
# ---------------------------------------------------------------------------


class TestQueueOverHttp:
    def _import(self, app, headers, raw: bytes, name="meddelande.eml"):
        return app.client.post(
            "/api/brf/brf-a/integrations/source-events",
            files={"file": (name, raw, "message/rfc822")},
            headers=headers,
        )

    def test_the_queue_reads_as_threads_with_counts(self, two_tenant_app):
        app = two_tenant_app
        self._import(app, app.admin_a_headers,
                     message(subject="Offert", body="Vår offert bifogas.",
                             message_id="<q1@x.example>"))
        self._import(app, app.admin_a_headers,
                     message(subject="SV: Offert", body="Kan ni bekräfta att ni godkänner?",
                             message_id="<q2@x.example>",
                             date_header="Tue, 10 Feb 2026 10:00:00 +0100"))

        reply = app.client.get("/api/brf/brf-a/integrations/intake", headers=app.admin_a_headers)
        assert reply.status_code == 200, reply.text
        body = reply.json()
        assert len(body["threads"]) == 1
        assert body["threads"][0]["message_count"] == 2
        assert body["counts"]["openThreads"] == 1
        assert body["counts"]["awaitingReply"] == 1
        # The labels are served, so no client has to keep its own copy of the
        # vocabulary and drift from the backend's.
        assert "invoice" in body["categoryLabels"]
        assert "take_in" in body["resolutionLabels"]
        assert body["mailbox"]["hasFetched"] is False

    def test_a_member_may_read_the_queue_and_not_resolve_it(self, two_tenant_app):
        app = two_tenant_app
        created = self._import(app, app.admin_a_headers,
                               message(subject="Offert", body="Vår offert.",
                                       message_id="<r@x.example>")).json()

        assert app.client.get("/api/brf/brf-a/integrations/intake",
                              headers=app.member_a_headers).status_code == 200
        refused = app.client.post(
            f"/api/brf/brf-a/integrations/source-events/{created['id']}/resolve",
            json={"outcomes": ["already_handled"]},
            headers=app.member_a_headers,
        )
        assert refused.status_code == 403

    def test_another_tenant_gets_404_not_403(self, two_tenant_app):
        """Same rule as everywhere else here: a 403 would confirm the id exists."""
        app = two_tenant_app
        created = self._import(app, app.admin_a_headers,
                               message(subject="Offert", body="Vår offert.",
                                       message_id="<s@x.example>")).json()

        for path, method, payload in (
            ("/api/brf/brf-a/integrations/intake", "get", None),
            (f"/api/brf/brf-a/integrations/source-events/{created['id']}/resolve", "post",
             {"outcomes": ["already_handled"]}),
            (f"/api/brf/brf-a/integrations/source-events/{created['id']}/triage", "post", None),
        ):
            call = getattr(app.client, method)
            reply = call(path, json=payload, headers=app.admin_b_headers) if payload else call(
                path, headers=app.admin_b_headers
            )
            assert reply.status_code == 404, (path, reply.status_code)

    def test_confirming_a_category_keeps_the_suggestion_beside_it(self, two_tenant_app):
        app = two_tenant_app
        created = self._import(app, app.admin_a_headers,
                               message(subject="Offert takomläggning", body="Vår offert bifogas.",
                                       message_id="<t@x.example>")).json()
        suggested = created["triage"]["category"]

        reply = app.client.post(
            f"/api/brf/brf-a/integrations/source-events/{created['id']}/triage/confirm",
            json={"category": "authority_or_manager", "note": "Det är förvaltaren som skrivit."},
            headers=app.admin_a_headers,
        )
        assert reply.status_code == 200, reply.text
        body = reply.json()
        assert body["triage_confirmation"]["category"] == "authority_or_manager"
        assert body["triage_confirmation"]["confirmed_by"]
        assert body["triage"]["category"] == suggested, (
            "förslaget ska stå kvar — paret är det enda spåret av var läsningen tog fel"
        )

    def test_an_unknown_category_is_refused(self, two_tenant_app):
        app = two_tenant_app
        created = self._import(app, app.admin_a_headers,
                               message(subject="Offert", body="Vår offert.",
                                       message_id="<u@x.example>")).json()
        reply = app.client.post(
            f"/api/brf/brf-a/integrations/source-events/{created['id']}/triage/confirm",
            json={"category": "brådskande"}, headers=app.admin_a_headers,
        )
        assert reply.status_code == 422

    def test_resolving_over_http_routes_into_the_other_domains(self, two_tenant_app):
        app = two_tenant_app
        created = self._import(
            app, app.admin_a_headers,
            message(subject="SV: Offert", body="Vi godkänner offerten på 148 000 kr.",
                    message_id="<v@x.example>"),
        ).json()

        reply = app.client.post(
            f"/api/brf/brf-a/integrations/source-events/{created['id']}/resolve",
            json={
                "outcomes": ["take_in", "create_task", "monitor"],
                "note": "Godkännandet ska gå att belägga.",
                "task": {"title": "Beställ takomläggning", "responsible": "Bo"},
                "watch": {"due_date": "2026-09-30", "kind": "stated_deadline"},
            },
            headers=app.admin_a_headers,
        )
        assert reply.status_code == 200, reply.text
        outcomes = {o["kind"]: o for o in reply.json()["resolution"]["outcomes"]}
        assert set(outcomes) == {"take_in", "create_task", "monitor"}

        tasks = app.client.get("/api/brf/brf-a/tasks", headers=app.admin_a_headers).json()
        assert any(t["id"] == outcomes["create_task"]["ref_id"] for t in tasks["active"])

        watches = app.client.get("/api/brf/brf-a/watches", headers=app.admin_a_headers).json()
        approved = [w for bucket in watches["buckets"].values() for w in bucket]
        assert any(w["id"] == outcomes["monitor"]["ref_id"] for w in approved)
        assert watches["proposed"] == [], "en människas beslut är inget förslag"

        documents = app.client.get("/api/brf/brf-a/documents", headers=app.admin_a_headers).json()
        assert any(d["id"] == outcomes["take_in"]["ref_id"] for d in documents)

    def test_an_approved_message_can_be_asked_about_with_a_citation_back_to_it(
        self, two_tenant_app
    ):
        """The end of the chain: preserved post is answerable, and the answer
        opens the original message at the line it came from."""
        app = two_tenant_app
        created = self._import(
            app, app.admin_a_headers,
            message(
                subject="Uppsägningstid för snöröjningsavtalet",
                body="Uppsägningstiden är tre månader enligt vad vi kom överens om.",
                message_id="<w@x.example>",
            ),
        ).json()
        app.client.post(
            f"/api/brf/brf-a/integrations/source-events/{created['id']}/resolve",
            json={"outcomes": ["take_in"], "note": "Källa för uppsägningstiden."},
            headers=app.admin_a_headers,
        )

        store = app.registry.get("brf-a")
        event = store.integrations.get_source_event(created["id"])
        hits = store.index.search("uppsägningstid snöröjningsavtal", weight=0.5, candidates=50,
                                  top_k=5, min_confidence=0.0)
        assert event.preserved_document_id in {h.document_id for h in hits}

        citation = citation_for(store, event.preserved_document_id,
                                "Uppsägningstiden är tre månader enligt vad vi kom överens om.")
        assert citation is not None and citation.rects

    def test_the_mailbox_is_never_written_to(self):
        """The whole block's boundary, restated at this block's own surface:
        no adapter here may carry an outward-writing verb."""
        from app.integrations import protocols

        assert_read_only = protocols.assert_read_only
        assert assert_read_only(protocols.MailboxReadAdapter) is protocols.MailboxReadAdapter
        declared = [
            name for name in vars(protocols.MailboxReadAdapter)
            if not name.startswith("_") and callable(getattr(protocols.MailboxReadAdapter, name, None))
        ]
        assert sorted(declared) == ["account_label", "get_message_mime", "list_messages"]

    def test_a_source_event_still_deserialises_from_a_pre_queue_record(self, tmp_path):
        """An event written before this block existed must load unchanged —
        every new field means "this never happened"."""
        legacy = {
            "id": "abc", "tenant_id": "brf-a", "source_type": "email",
            "received_at": "2026-02-03T08:14:00+00:00", "content_sha256": "a" * 64,
            "provenance": {
                "method": "manual-file-import", "adapter": "eml-file",
                "origin_filename": "m.eml", "origin_bytes": 10, "imported_by": "admin-1",
                "imported_at": "2026-02-03T08:14:00+00:00",
            },
            "origin": "anna@x.example", "subject": "Offert", "body_text": "text",
        }
        event = SourceEvent.model_validate(legacy)
        assert event.triage is None and event.resolution is None
        assert event.thread_key == "" and event.preserved_document_id is None
        assert event.category() == "unclear" and event.resolved() is False
