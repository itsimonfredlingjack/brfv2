"""What one piece of incoming post appears to be, and what it says so with.

The queue's job is to let a board answer five questions quickly: what arrived,
why it matters, what it connects to, whether anyone has to act, and what should
be kept. This module answers them as *suggestions*, and the whole design is
about keeping them suggestions.

Three rules, and each of them is the same rule the review engine and the watch
engine already live by:

1. **Nothing is asserted that was not read.** Every field on a
   :class:`~app.integrations.models.TriageSuggestion` is built from a
   :class:`~app.integrations.models.TriageSignal` that carries the words it was
   read from. A category with no evidence behind it is ``unclear``, which is a
   real answer and displayed as one — not a guess dressed as a reading.

2. **The floor is deterministic.** The category, the dates, the amounts, the
   supplier and the links are produced by rules over the text, using the
   scanners this product already has (:mod:`app.terms`,
   :func:`app.integrations.review.scan_amounts`) — the same code that reads the
   association's contracts. Those rules run with no model, no network and no
   credential, which is why the whole queue works on an installation that has
   never configured generation.

3. **A model may only refine what the rules read, and only if it can be
   checked.** When a real provider is configured, it is asked for two things a
   rule engine writes badly — a headline and a sentence on why the message
   matters — and one thing it may reasonably disagree about: the category. Its
   answer is accepted only if the category is in the closed vocabulary and its
   stated evidence is found *verbatim* in the message. Anything else is
   discarded and the deterministic reading stands. ``suggested_by`` then names
   the model, because "regelmotor" and "regelmotor + språkmodell" are different
   assurances and a reader is entitled to know which one they are looking at.

The attachments are read too, and through the ordinary door: an attachment that
arrived in the queue is already an ingested document, so its extracted page
words are right there in the tenant's store. Reading them here adds no second
extraction path and no second copy of anything.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from ..store import Store
from ..terms import (
    STOCKHOLM_TZ,
    anchor_relative,
    calendar_date_in,
    scan_dates,
    scan_day_deadlines,
    scan_notice_periods,
    scan_recurrence,
    scan_relative_deadlines,
    scan_unanchored_deadlines,
    svenskt_datum,
)
from .models import (
    TRIAGE_CATEGORY_LABELS,
    AnchorQuestion,
    RelatedRecord,
    SourceEvent,
    TriageSignal,
    TriageSuggestion,
    utc_now_iso,
)
from .supplier import core_tokens, normalize as normalize_supplier

logger = logging.getLogger("brf.integrations.triage")

# How much of an attachment is read for triage. A queue card is a summary, and
# the first page or two of an invoice or a quote carries the parties, the
# amount and the dates; the rest is terms that belong in the document view.
# Bounded so that a 200-page appendix cannot make importing mail slow.
ATTACHMENT_WORD_BUDGET = 1200

# Longest quote a signal may carry. Long enough for a full Swedish sentence,
# short enough that a card is not a transcript.
MAX_QUOTE_WORDS = 32

_SENTENCE_END = re.compile(r"[.!?]$")
_WORD = re.compile(r"\S+")


# ---------------------------------------------------------------------------
# Vocabularies
# ---------------------------------------------------------------------------
#
# Each set is what a Swedish board actually receives, and each is deliberately
# small: a keyword that fires on half the mailbox stops being a signal. They
# are matched against *cleaned, casefolded* tokens, so "Fakturan," matches
# "fakturan".

INVOICE_WORDS = frozenset(
    {
        "faktura", "fakturan", "fakturor", "fakturanummer", "fakturadatum",
        "delfaktura", "kreditfaktura", "slutfaktura", "betalningspåminnelse",
        "ocr", "bankgiro", "plusgiro", "förfallodatum", "förfaller",
        "betalningsvillkor", "momsbelopp", "invoice",
    }
)

CONTRACT_WORDS = frozenset(
    {
        "avtal", "avtalet", "avtalsförslag", "ramavtal", "offert", "offerten",
        "offertförslag", "anbud", "kontrakt", "prisförslag", "uppdragsbekräftelse",
        "entreprenadkontrakt", "quotation",
    }
)

AUTHORITY_WORDS = frozenset(
    {
        "kommunen", "kommunstyrelsen", "länsstyrelsen", "stadsbyggnadskontoret",
        "miljöförvaltningen", "räddningstjänsten", "skatteverket", "lantmäteriet",
        "bolagsverket", "boverket", "myndighet", "myndigheten", "tillsyn",
        "tillsynsbesök", "föreläggande", "remiss", "bygglov", "diarienummer",
        "förvaltaren", "förvaltningen", "fastighetsförvaltaren",
    }
)

# Somebody committing the association, or being told it is committed. These
# are *acts*, which is why they get to override the topic scoring below.
DECISION_ACT_WORDS = frozenset(
    {
        "godkänner", "godkänt", "godkänd", "godkännande", "beslutat", "beslutar",
        "beslut", "bekräftar", "accepterar", "accepterat", "antagit",
    }
)

# The wider set, including the words that merely *accompany* a decision. "Tack
# för din beställning" is in half the commercial mail a board receives and must
# not on its own relabel a message as a board decision, so these only score.
DECISION_WORDS = DECISION_ACT_WORDS | frozenset(
    {"bekräftelse", "beställer", "beställt", "beställning", "avrop", "orderbekräftelse"}
)

# Two different ways a Swedish sentence asks for something back, and both are
# needed: the first version of this had only the second, and read "När på året
# gäller jouren för snöröjning?" as a message asking nothing at all.
INTERROGATIVES = frozenset(
    {
        "när", "vad", "vem", "vems", "vilken", "vilket", "vilka", "hur", "varför",
        "var", "vart", "kan", "får", "ska", "skulle", "vore", "finns", "går",
        "behöver", "stämmer",
    }
)

REQUEST_WORDS = frozenset(
    {
        "återkom", "återkoppla", "återkoppling", "besked", "svar", "svara",
        "bekräfta", "meddela", "undrar", "önskar", "hör",
    }
)

QUESTION_WORDS = INTERROGATIVES | REQUEST_WORDS

RENEWAL_WORDS = frozenset(
    {
        "förlängs", "förlängning", "automatiskt", "förnyas", "uppsägning",
        "uppsägningstid", "säga", "upp",
    }
)

# The order that breaks a tie between equally-evidenced categories. It is a
# statement about consequence, not about likelihood: the two things a board
# loses money to are a decision nobody recorded and a question nobody answered,
# so those outrank a category that merely files the message.
CATEGORY_PRIORITY: tuple[str, ...] = (
    "decision_or_approval",
    "invoice",
    "contract_or_quote",
    "authority_or_manager",
    "question_awaiting_reply",
    "information",
    "unclear",
)


def _clean(token: str) -> str:
    return token.strip().strip(" \t()[]{}.,;:!?\"'§•·«»–—")


def _fold(token: str) -> str:
    return _clean(token).casefold()


@dataclass(frozen=True)
class _TextSource:
    """One body of text to read, and where a quote from it came from."""

    words: list[str]
    source: str  # "subject" | "body" | "attachment"
    ref: str = ""

    def quote(self, start: int, end: int) -> str:
        """A readable verbatim quote around a span.

        Widened to sentence boundaries where they are close, because a bare
        "2026-09-30" tells a reviewer nothing about what happens on that date,
        and the sentence around it is the whole value of showing a quote at
        all. Bounded on both sides so a card cannot become a page.
        """
        lo = max(0, start)
        hi = min(len(self.words) - 1, end)
        # Walk back to the start of the sentence, then forward to its end.
        while lo > start - MAX_QUOTE_WORDS // 2 and lo > 0:
            if _SENTENCE_END.search(self.words[lo - 1]) and not _looks_abbreviated(self.words[lo - 1]):
                break
            lo -= 1
        while hi < end + MAX_QUOTE_WORDS // 2 and hi < len(self.words) - 1:
            if _SENTENCE_END.search(self.words[hi]) and not _looks_abbreviated(self.words[hi]):
                break
            hi += 1
        if hi - lo + 1 > MAX_QUOTE_WORDS:
            hi = lo + MAX_QUOTE_WORDS - 1
        return " ".join(self.words[lo : hi + 1]).strip()


def _looks_abbreviated(word: str) -> bool:
    return _fold(word) in {"t.ex", "bl.a", "dvs", "resp", "ca", "nr", "s.k", "m.m"}


def text_sources(store: Store, event: SourceEvent) -> list[_TextSource]:
    """Everything about this message that can be read, subject first.

    Attachment text comes out of the tenant's own extraction — the same
    ``PageData`` the index and the citation resolver use — so there is no
    second parser here and nothing is re-extracted.
    """
    sources = [
        _TextSource(words=_WORD.findall(event.subject or ""), source="subject"),
        _TextSource(words=_WORD.findall(event.body_text or ""), source="body"),
    ]
    for attachment in event.attachments:
        if not attachment.document_id:
            continue
        pages = store.pages.get(attachment.document_id)
        if not pages:
            continue
        words: list[str] = []
        for page in pages:
            words.extend(w.text for w in page.words)
            if len(words) >= ATTACHMENT_WORD_BUDGET:
                break
        if words:
            sources.append(
                _TextSource(
                    words=words[:ATTACHMENT_WORD_BUDGET],
                    source="attachment",
                    ref=attachment.id,
                )
            )
    return sources


# ---------------------------------------------------------------------------
# Category
# ---------------------------------------------------------------------------


def _keyword_hits(source: _TextSource, vocabulary: frozenset[str]) -> list[tuple[int, str]]:
    """Positions of the distinct vocabulary words present in this source."""
    seen: dict[str, int] = {}
    for i, word in enumerate(source.words):
        folded = _fold(word)
        if folded in vocabulary and folded not in seen:
            seen[folded] = i
    return [(index, word) for word, index in seen.items()]


def _category_evidence(sources: list[_TextSource]) -> dict[str, list[TriageSignal]]:
    """What speaks for each category, with the words that speak for it."""
    vocabularies: dict[str, frozenset[str]] = {
        "invoice": INVOICE_WORDS,
        "contract_or_quote": CONTRACT_WORDS,
        "authority_or_manager": AUTHORITY_WORDS,
        "decision_or_approval": DECISION_WORDS,
    }
    evidence: dict[str, list[TriageSignal]] = {key: [] for key in vocabularies}
    for source in sources:
        for category, vocabulary in vocabularies.items():
            for index, word in _keyword_hits(source, vocabulary):
                evidence[category].append(
                    TriageSignal(
                        kind="reference",
                        label="Ord som pekar hit",
                        value=word,
                        quote=source.quote(index, index),
                        source=source.source,
                        source_ref=source.ref,
                    )
                )
    return evidence


def _score(signals: list[TriageSignal]) -> int:
    """How strongly the evidence speaks, weighting where it was read.

    The subject line is what the sender chose to call the message and is worth
    more than the same word buried in a signature block; an attachment is worth
    more than the covering sentence, because "here is the invoice" and an
    actual invoice are different amounts of evidence.
    """
    weight = {"subject": 3, "attachment": 2, "body": 1}
    return sum(weight.get(signal.source, 1) for signal in signals)


def classify(sources: list[_TextSource], *, asks_something: bool) -> tuple[str, list[TriageSignal]]:
    """Pick a category, and return the evidence that picked it.

    ``information`` is what a message that was read but matched no vocabulary
    becomes, and ``unclear`` is reserved for one that could not be read at all.
    Keeping those apart matters: the first is a filing decision, the second is
    the product saying it does not know, and merging them would hide the second
    inside the first.
    """
    evidence = _category_evidence(sources)

    # An act outranks a topic. "SV: Offert takomläggning" carrying "vi
    # godkänner offerten" scores three times over for *avtal eller offert* —
    # the subject names the quote twice and the body once — and reads as a
    # decision to every human who opens it. The subject says what the thread is
    # about; the body says what this message *did*, and "did anyone approve the
    # quote" is precisely the question a board cannot answer from its inbox.
    #
    # So a first-person commitment written in the message body decides the
    # category outright. Deliberately not the subject (a subject line is a
    # topic, not an act) and deliberately not an attachment (a contract
    # template contains the word "godkännande" and approves nothing).
    for source in sources:
        if source.source != "body":
            continue
        acts = _keyword_hits(source, DECISION_ACT_WORDS)
        if acts:
            return "decision_or_approval", evidence.get("decision_or_approval", [])

    scored = {key: _score(signals) for key, signals in evidence.items() if signals}

    if asks_something:
        # A question is scored from its own signal rather than a vocabulary
        # hit, and deliberately low: almost every message asks something, and a
        # question inside an invoice mail does not make it stop being an
        # invoice.
        scored["question_awaiting_reply"] = max(scored.get("question_awaiting_reply", 0), 2)

    if not scored:
        readable = any(source.words for source in sources)
        return ("information" if readable else "unclear"), []

    best = max(scored.values())
    winners = [key for key, value in scored.items() if value == best]
    category = min(winners, key=lambda key: CATEGORY_PRIORITY.index(key))
    return category, evidence.get(category, [])


# ---------------------------------------------------------------------------
# Structured signals
# ---------------------------------------------------------------------------


def _date_signals(source: _TextSource, *, reference_date: date | None = None) -> list[TriageSignal]:
    """Dates, deadlines and rhythms — read by the same scanners as contracts.

    Reusing :mod:`app.terms` is the point. A notice period stated in an email
    is the same Swedish sentence as one stated in a contract, and a second
    reader written for mail would drift from the one the watch engine uses,
    which is exactly how a product ends up disagreeing with itself about a
    date.

    Day-counts with no date of their own ("inom tio dagar") are the one
    extra the mail path does: they are resolved against the message's
    received date, never against a contract's signing date, and never by
    changing the scanners the watch engine calls.

    Month/week/year frists with no date ("inom tre månader") are *not*
    resolved here. That is Feature 2, and it lives in
    :func:`_unanchored_questions` so a received-date cannot leak onto them.
    """
    words = source.words
    signals: list[TriageSignal] = []

    for deadline in scan_relative_deadlines(words):
        signals.append(
            TriageSignal(
                kind="deadline",
                label="Beräknat datum",
                value=deadline.resolve(),
                quote=source.quote(deadline.span.start, deadline.span.end),
                source=source.source,
                source_ref=source.ref,
            )
        )

    if reference_date is not None:
        hits = scan_day_deadlines(words)
        for hit, anchored in zip(
            hits, anchor_relative(hits, reference_date=reference_date), strict=True
        ):
            if hit.anchor_iso:
                label = f"Beräknat från {svenskt_datum(anchored.anchor_iso)}"
            else:
                label = f"Beräknat från mottaget {svenskt_datum(anchored.anchor_iso)}"
            signals.append(
                TriageSignal(
                    kind="deadline",
                    label=label,
                    value=anchored.resolve(),
                    quote=source.quote(anchored.span.start, anchored.span.end),
                    source=source.source,
                    source_ref=source.ref,
                )
            )

    covered = {(s.value) for s in signals}
    for hit in scan_dates(words):
        if hit.iso in covered:
            continue
        covered.add(hit.iso)
        signals.append(
            TriageSignal(
                kind="date",
                label="Datum i texten",
                value=hit.iso,
                quote=source.quote(hit.span.start, hit.span.end),
                source=source.source,
                source_ref=source.ref,
            )
        )

    for notice in scan_notice_periods(words):
        signals.append(
            TriageSignal(
                kind="renewal",
                label="Uppsägningstid",
                value=notice.human(),
                quote=source.quote(notice.span.start, notice.span.end),
                source=source.source,
                source_ref=source.ref,
            )
        )

    for recurrence in scan_recurrence(words):
        signals.append(
            TriageSignal(
                kind="renewal",
                label="Återkommer",
                value=recurrence.human(),
                quote=source.quote(recurrence.span.start, recurrence.span.end),
                source=source.source,
                source_ref=source.ref,
            )
        )
    return signals


def _unanchored_questions(source: _TextSource) -> list[AnchorQuestion]:
    """Frists whose start is not a date and must not be guessed from receipt.

    Explicitly a different path from :func:`_date_signals`. This function
    takes no ``reference_date`` so "inom tre månader" cannot be counted from
    when Graph delivered the copy.

    Deferred (do not do in a terms.py fingerprint bump unless that is the
    task): the particle walk is cloned from ``scan_day_deadlines``;
    ``terms.py`` / this file / IntakeQueue.jsx+css have crossed 1k lines;
    the mail-only scanner still lives in fingerprinted ``terms.py``;
    the card has a second submit beside Bevaka; answering one question
    still settles the event (remaining questions drop); resolve builds a
    dummy ``RelativeHit``; ``open_anchor_summaries`` is an untyped dict
    and the strip ignores ``event_id``.
    """
    questions: list[AnchorQuestion] = []
    for hit in scan_unanchored_deadlines(source.words):
        questions.append(
            AnchorQuestion(
                quote=source.quote(hit.span.start, hit.span.end),
                count=hit.count,
                unit=hit.unit,
                before=hit.before,
                source=source.source,
                source_ref=source.ref,
            )
        )
    return questions


def _amount_signals(source: _TextSource) -> list[TriageSignal]:
    from .review import amount_unit, scan_amounts

    unit_labels = {"rate": "styckpris eller timpris", "periodic": "periodiskt belopp", "plain": "belopp"}
    signals: list[TriageSignal] = []
    for start, end, value in scan_amounts(source.words):
        unit = amount_unit(source.words, end)
        signals.append(
            TriageSignal(
                kind="amount",
                label=unit_labels[unit].capitalize(),
                value=_money(value),
                quote=source.quote(start, end),
                source=source.source,
                source_ref=source.ref,
            )
        )
    return signals


def _money(value: Decimal) -> str:
    """A Swedish amount as text. Never a float — see models.py."""
    quantized = value.quantize(Decimal("0.01")) if value == value.to_integral_value() else value
    return f"{quantized} kr".replace(".", ",")


def _asks_something(event: SourceEvent) -> tuple[bool, TriageSignal | None]:
    """Does this message appear to be waiting for an answer from here?

    A question mark alone is too weak — signatures and marketing carry them —
    so a question word has to be present as well, and the sentence carrying
    both is what the signal quotes. Stated everywhere in the UI as *appears
    to*: this product reads incoming post and cannot see whether somebody here
    already replied.
    """
    body = _TextSource(words=_WORD.findall(f"{event.subject} {event.body_text}"), source="body")
    for i, word in enumerate(body.words):
        if "?" not in word:
            continue
        window = {_fold(w) for w in body.words[max(0, i - 14) : i + 1]}
        if window & QUESTION_WORDS:
            return True, TriageSignal(
                kind="question",
                label="Ser ut att vänta svar",
                value="fråga i meddelandet",
                quote=body.quote(i, i),
                source="body",
            )
    return False, None


def _decision_signal(sources: list[_TextSource]) -> TriageSignal | None:
    """A sentence that reads like somebody approved or ordered something.

    The unambiguous commitments are looked for first, so the quote a card shows
    is "Vi godkänner offerten…" rather than "Tack för din beställning" when the
    message happens to contain both. Both still count — an order confirmation
    is a fact worth preserving — but the stronger sentence is the one worth
    showing.
    """
    for vocabulary in (DECISION_ACT_WORDS, DECISION_WORDS):
        for source in sources:
            for index, word in _keyword_hits(source, vocabulary):
                return TriageSignal(
                    kind="decision",
                    label="Kan innehålla ett beslut",
                    value=word,
                    quote=source.quote(index, index),
                    source=source.source,
                    source_ref=source.ref,
                )
    return None


# ---------------------------------------------------------------------------
# Who it is from, and what it connects to
# ---------------------------------------------------------------------------


def guess_supplier(event: SourceEvent, sources: list[_TextSource]) -> tuple[str, TriageSignal | None]:
    """The organisation this appears to be from.

    The display name on the address first, because a sender who writes
    "Snösvängen Entreprenad AB <faktura@snosvangen.se>" has told us the name;
    the domain's own label second, title-cased, which is a guess and is
    labelled as one. Never invented from the body text: a name picked out of
    prose would be the kind of confident nonsense this product exists not to
    produce.
    """
    display = (event.origin_display or "").strip()
    if display and "@" not in display and len(display) > 2:
        return display, TriageSignal(
            kind="supplier",
            label="Avsändarens namn",
            value=display,
            quote=f"{display} <{event.origin}>",
            source="body",
        )
    domain = event.origin.rsplit("@", 1)[-1] if "@" in event.origin else ""
    label = domain.split(".")[0] if domain else ""
    if not label:
        return "", None
    return label.capitalize(), TriageSignal(
        kind="supplier",
        label="Gissad ur avsändarens domän",
        value=label.capitalize(),
        quote=event.origin,
        source="body",
    )


def find_related(
    store: Store, event: SourceEvent, supplier_name: str
) -> list[RelatedRecord]:
    """Records already here that this message appears to concern.

    Four kinds, each with a stated basis a reviewer can check:

    * **documents** — the suggestion the queue already computes with the
      product's own retrieval (:func:`app.integrations.intake.suggest_documents`),
      reused rather than re-derived;
    * **invoices** — an invoice snapshot whose supplier normalises to the same
      key as the sender's name;
    * **earlier correspondence** — a source event from the same address;
    * **work already taken on** — a task or watch already created from this
      event, so that a second person does not create a duplicate.

    All proposals. Nothing here links anything; a link is what a human does on
    the card.
    """
    related: list[RelatedRecord] = []

    for doc_id in event.suggested_document_ids:
        meta = store.documents.get(doc_id)
        if meta is None:
            continue
        related.append(
            RelatedRecord(
                kind="document",
                ref_id=doc_id,
                label=meta.name,
                basis="föreslaget av sökningen på ämne och avsändare",
            )
        )

    key = normalize_supplier(supplier_name) if supplier_name else ""
    if key:
        distinctive = set(core_tokens(supplier_name))
        try:
            invoices = store.integrations.list_invoices()
        except Exception as exc:  # a queue card must not fail on a broken file
            logger.warning("Kunde inte läsa fakturor för koppling: %s", exc)
            invoices = []
        for invoice in invoices:
            invoice_key = normalize_supplier(invoice.supplier_name)
            shared = distinctive & set(core_tokens(invoice.supplier_name))
            if invoice_key != key and not shared:
                continue
            related.append(
                RelatedRecord(
                    kind="invoice",
                    ref_id=invoice.id,
                    label=f"{invoice.supplier_name} {invoice.invoice_number or invoice.external_ref}",
                    basis=(
                        "samma leverantörsnamn"
                        if invoice_key == key
                        else f"delar namndelen {', '.join(sorted(shared))}"
                    ),
                )
            )

    try:
        events = store.integrations.list_source_events()
    except Exception as exc:
        logger.warning("Kunde inte läsa köns tidigare post: %s", exc)
        events = []
    for earlier in events:
        if earlier.id == event.id or earlier.origin != event.origin:
            continue
        related.append(
            RelatedRecord(
                kind="source_event",
                ref_id=earlier.id,
                label=f"{earlier.subject or '(utan ämne)'} — {earlier.received_at[:10]}",
                basis="tidigare post från samma avsändare",
            )
        )
        if sum(1 for r in related if r.kind == "source_event") >= 3:
            break

    try:
        for task in store.tasks.tasks_for_origin("source_event", event.id):
            related.append(
                RelatedRecord(
                    kind="task",
                    ref_id=task.id,
                    label=task.title,
                    basis="uppgift som redan skapats ur den här posten",
                )
            )
    except Exception as exc:
        logger.warning("Kunde inte läsa uppgifter för koppling: %s", exc)

    return related[:12]


# ---------------------------------------------------------------------------
# The suggestion
# ---------------------------------------------------------------------------


def _headline(category: str, event: SourceEvent, supplier: str) -> str:
    subject = (event.subject or "").strip() or "(utan ämne)"
    who = supplier or event.origin
    prefix = {
        "invoice": "Ser ut att gälla en faktura",
        "contract_or_quote": "Ser ut att gälla ett avtal eller en offert",
        "authority_or_manager": "Ser ut att komma från en myndighet eller förvaltare",
        "decision_or_approval": "Kan innehålla ett beslut eller godkännande",
        "question_awaiting_reply": "Ser ut att vänta på ett svar",
        "information": "Information",
        "unclear": "Går inte att avgöra vad det gäller",
    }[category]
    return f"{prefix} — {subject} (från {who})"


_WHY_BY_CATEGORY: dict[str, str] = {
    "decision_or_approval": "Ett godkännande som bara finns i en inkorg är svårt att belägga senare",
    "invoice": "En faktura bör stämmas av mot föreningens eget underlag",
    "contract_or_quote": "Avtal och offerter binder föreningen och bör kunna sökas fram",
    "authority_or_manager": "Post från myndighet eller förvaltare har oftast en tidsgräns",
    "question_awaiting_reply": "En obesvarad fråga är den vanligaste sortens tappad tråd",
}


def _why_it_matters(category: str, signals: list[TriageSignal]) -> str:
    """One sentence, written only from what was read.

    The clause about the category is a general truth about that kind of post;
    everything after it names something actually found in this message. Nothing
    is asserted here that is not in ``signals``.
    """
    lead = _WHY_BY_CATEGORY.get(category, "")
    found: list[str] = []
    amounts = [s for s in signals if s.kind == "amount"]
    dates = sorted({s.value for s in signals if s.kind in ("date", "deadline")})
    if amounts:
        found.append(f"belopp nämns ({amounts[0].value})")
    if dates:
        found.append(f"datum nämns ({', '.join(dates[:3])})")
    if not lead and not found:
        return ""
    if not found:
        return f"{lead}."
    if not lead:
        return f"{found[0][0].upper()}{found[0][1:]}" + (f", {found[1]}" if len(found) > 1 else "") + "."
    return f"{lead}. {', '.join(found)}."


def _action_hint(category: str, awaiting: bool, dates: list[TriageSignal]) -> str:
    if awaiting:
        return "Någon behöver troligen svara."
    if category == "invoice":
        return "Läs in fakturan och granska den mot avtalet."
    if category == "decision_or_approval":
        return "Bevara meddelandet så att beslutet går att belägga."
    if dates:
        return "Överväg en bevakning på datumet."
    return ""


def analyze(store: Store, event: SourceEvent) -> TriageSuggestion:
    """Read one queue item. Deterministic, offline, and always a suggestion.

    Never raises: a card that cannot be produced must not be able to fail an
    import or blank the queue. A failure downgrades to ``unclear`` with the
    reason in ``uncertainty``, which is the honest form of "we could not read
    this" and is exactly what the operator needs to see.
    """
    try:
        sources = text_sources(store, event)
        awaiting, question_signal = _asks_something(event)
        category, category_signals = classify(sources, asks_something=awaiting)

        signals: list[TriageSignal] = []
        anchor_questions: list[AnchorQuestion] = []
        reference_date = calendar_date_in(event.received_at, zone=STOCKHOLM_TZ)
        for source in sources:
            signals.extend(_date_signals(source, reference_date=reference_date))
            signals.extend(_amount_signals(source))
            anchor_questions.extend(_unanchored_questions(source))
        if question_signal is not None:
            signals.append(question_signal)
        decision_signal = _decision_signal(sources)
        if decision_signal is not None:
            signals.append(decision_signal)

        supplier, supplier_signal = guess_supplier(event, sources)
        if supplier_signal is not None:
            signals.append(supplier_signal)
        signals.extend(category_signals[:4])

        dates = [s for s in signals if s.kind in ("date", "deadline")]
        uncertainty = ""
        if category == "unclear":
            uncertainty = (
                "Meddelandet innehåller ingen text som den här läsningen känner igen. "
                "Sätt kategori för hand."
            )
        elif not signals:
            uncertainty = "Inget datum, belopp eller namn kunde läsas ur meddelandet."
        elif any(s.source == "attachment" for s in signals) is False and event.attachments:
            uncertainty = "Bilagornas text kunde inte läsas — bedömningen bygger bara på mejltexten."

        return TriageSuggestion(
            category=category,
            category_label=TRIAGE_CATEGORY_LABELS[category],
            headline=_headline(category, event, supplier),
            why_it_matters=_why_it_matters(category, signals),
            action_hint=_action_hint(category, awaiting, dates),
            awaiting_reply=awaiting,
            contains_decision=decision_signal is not None,
            supplier_name=supplier,
            signals=_dedupe(signals),
            related=find_related(store, event, supplier),
            anchor_questions=anchor_questions,
            suggested_by="regelmotor",
            uncertainty=uncertainty,
            created_at=utc_now_iso(),
        )
    except Exception as exc:  # pragma: no cover - defensive; the queue must survive
        logger.exception("Triage misslyckades för %s", event.id)
        return TriageSuggestion(
            category="unclear",
            category_label=TRIAGE_CATEGORY_LABELS["unclear"],
            headline=event.subject or "(utan ämne)",
            uncertainty=f"Analysen kunde inte köras: {exc.__class__.__name__}.",
            suggested_by="regelmotor",
        )


# ---------------------------------------------------------------------------
# Optional model refinement
# ---------------------------------------------------------------------------

_TRIAGE_SYSTEM = """Du sorterar inkommande post till en svensk bostadsrättsförening.

Du får ett mejls ämne, avsändare och text. Svara med ETT JSON-objekt:

{"category": "<en av kategorierna>",
 "headline": "<en rad: vad meddelandet gäller>",
 "why_it_matters": "<en mening: varför styrelsen bör bry sig>",
 "evidence": "<en ordagrann mening ur meddelandet som stöder kategorin>"}

Kategorier: invoice, contract_or_quote, authority_or_manager,
decision_or_approval, question_awaiting_reply, information, unclear.

Regler:
- "evidence" MÅSTE vara kopierad ordagrant ur meddelandets text. Hittar du
  ingen sådan mening, svara med kategorin "unclear" och tom evidence.
- Påstå ingenting som inte står i meddelandet. Gissa inte belopp eller datum.
- Skriv på svenska. Inga andra fält, ingen text utanför JSON-objektet."""

# What a refinement may cost. A queue card is not an answer, and a model that
# needs more than this to write one line is producing something the card cannot
# show anyway.
TRIAGE_MAX_TOKENS = 400


def model_available() -> bool:
    """Is there a real generation path configured on this installation?

    ``fake`` and ``none`` are not. That is what keeps the whole queue —
    including its tests, its acceptance run and any offline installation —
    deterministic without a flag anybody has to remember to set.
    """
    try:
        from ..llm import pick_provider

        return pick_provider().name not in ("none", "fake")
    except Exception:  # pragma: no cover - provider construction is defensive already
        return False


def refine_with_model(event: SourceEvent, suggestion: TriageSuggestion) -> TriageSuggestion:
    """Let a configured model improve the words, never the facts.

    What the model may change: the category, the headline, the sentence on why
    it matters. What it may not touch: the signals, the related records, the
    dates and the amounts — those were read by the scanners and a model that
    could overwrite them would be a model that can invent a deadline.

    Its category is accepted only if the vocabulary contains it **and** the
    sentence it offers as evidence is found in the message. The check is the
    same idea as :mod:`app.citations`, at the resolution a queue card needs:
    the words have to be in the text. A model that cannot point at the message
    does not get to relabel it.

    Never raises. A provider that is down, slow or nonsensical leaves the
    deterministic reading exactly as it was — which is the reading the product
    would have shipped anyway.
    """
    import json

    from ..llm import pick_provider

    haystack = _normalized(f"{event.subject}\n{event.body_text}")
    if not haystack:
        return suggestion

    provider = pick_provider()
    user = (
        f"ÄMNE: {event.subject}\n"
        f"AVSÄNDARE: {event.origin_display or ''} <{event.origin}>\n"
        f"MOTTAGET: {event.occurred_at or event.received_at}\n\n"
        f"TEXT:\n{(event.body_text or '')[:6000]}"
    )
    # One broad except, deliberately: an unreachable endpoint, a truncated
    # answer and a response that is not JSON at all are the same event here —
    # the refinement did not happen — and every one of them must leave the
    # deterministic card intact rather than surface as a failed import.
    try:
        raw = provider.complete(
            _TRIAGE_SYSTEM,
            user,
            max_tokens=TRIAGE_MAX_TOKENS,
            model=getattr(provider, "model", "") or "",
        )
        start, end = raw.find("{"), raw.rfind("}")
        obj = json.loads(raw[start : end + 1]) if start != -1 and end > start else {}
    except Exception as exc:
        logger.info("Språkmodellen förfinade inte triagen för %s: %s", event.id, exc)
        return suggestion
    if not isinstance(obj, dict):
        return suggestion

    category = obj.get("category")
    evidence = obj.get("evidence") or ""
    headline = (obj.get("headline") or "").strip()
    why = (obj.get("why_it_matters") or "").strip()

    model_name = getattr(provider, "model", "") or provider.name
    grounded = isinstance(evidence, str) and _normalized(evidence) and _normalized(evidence) in haystack

    if not grounded:
        # The model said something about a message it could not point at. The
        # deterministic reading stands, and the card says a check was tried and
        # did not hold — silence here would be the product hiding a
        # disagreement about its own material.
        return suggestion.model_copy(
            update={
                "uncertainty": (
                    suggestion.uncertainty
                    + (" " if suggestion.uncertainty else "")
                    + "Språkmodellens förslag kunde inte beläggas i meddelandets text och användes inte."
                ).strip()
            }
        )

    update: dict = {
        "suggested_by": f"regelmotor + språkmodell ({model_name})",
        "signals": [
            *suggestion.signals,
            TriageSignal(
                kind="reference",
                label="Språkmodellens belägg",
                value="citat ur meddelandet",
                quote=evidence.strip()[:400],
                source="body",
            ),
        ][:16],
    }
    if category in TRIAGE_CATEGORY_LABELS:
        update["category"] = category
        update["category_label"] = TRIAGE_CATEGORY_LABELS[category]
    if headline:
        update["headline"] = headline[:300]
    if why:
        update["why_it_matters"] = why[:400]
    return suggestion.model_copy(update=update)


def _normalized(text: str) -> str:
    """Whitespace-folded, casefolded text for the verbatim check.

    Folding whitespace and case is the whole tolerance. A model that quotes the
    sentence with a different line break still passes; one that paraphrases
    does not, which is the distinction that matters.
    """
    return " ".join((text or "").split()).casefold()


def analyze_and_refine(store: Store, event: SourceEvent) -> TriageSuggestion:
    """The deterministic reading, refined by a model when one is configured."""
    suggestion = analyze(store, event)
    if not model_available():
        return suggestion
    return refine_with_model(event, suggestion)


def _dedupe(signals: list[TriageSignal]) -> list[TriageSignal]:
    """One row per (kind, value, source) — the same date read twice is one date."""
    seen: set[tuple[str, str, str]] = set()
    out: list[TriageSignal] = []
    for signal in signals:
        key = (signal.kind, signal.value, signal.source)
        if key in seen:
            continue
        seen.add(key)
        out.append(signal)
    return out[:16]


__all__ = [
    "ATTACHMENT_WORD_BUDGET",
    "CATEGORY_PRIORITY",
    "analyze",
    "classify",
    "find_related",
    "guess_supplier",
    "text_sources",
]
