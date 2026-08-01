"""Source-driven watches: what becomes a date, what refuses to, and who owns it.

The feature's whole value is that a board can trust the calendar it produces,
so the tests are mostly about what the engine declines to do:

* a notice period with no anchor date does not become a deadline;
* a month without a day is not a date;
* a clause that will not verify verbatim produces no watch at all;
* nothing the engine proposes is an obligation until a person approves it.

Nothing here needs a credential, a network endpoint or a running model.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from app import terms
from app.watches.derive import scan_documents
from app.watches.models import Watch


def words(text: str) -> list[str]:
    return text.split()


def build_document(store, name: str, lines: list[str]) -> str:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from scripts.make_integration_fixtures import _invoice_pdf

    return store.add_document(name, _invoice_pdf(lines)).id


# ---------------------------------------------------------------------------
# Date arithmetic
# ---------------------------------------------------------------------------


class TestDateArithmetic:
    def test_three_months_before_the_last_of_december(self):
        """The example the feature exists for."""
        assert terms.shift_months(date(2026, 12, 31), -3) == date(2026, 9, 30)

    def test_a_day_that_does_not_exist_clamps_down_never_up(self):
        # 31 mars minus en månad is the last day of February, not 3 March.
        assert terms.shift_months(date(2026, 3, 31), -1) == date(2026, 2, 28)
        assert terms.shift_months(date(2028, 3, 31), -1) == date(2028, 2, 29)
        assert terms.shift_months(date(2026, 1, 31), 1) == date(2026, 2, 28)

    def test_a_year_is_twelve_months_including_over_a_boundary(self):
        assert terms.shift(date(2026, 11, 1), 1, "year") == date(2027, 11, 1)
        assert terms.shift(date(2026, 2, 29 if False else 28), -1, "year") == date(2025, 2, 28)

    def test_weeks_and_days_are_plain(self):
        assert terms.shift(date(2026, 5, 31), 2, "week") == date(2026, 6, 14)
        assert terms.shift(date(2026, 5, 31), 1, "day") == date(2026, 6, 1)


class TestRelativeDeadlines:
    def test_a_notice_before_a_written_date_resolves(self):
        (deadline,) = terms.scan_relative_deadlines(
            words(
                "Avtalet förlängs automatiskt om det inte sägs upp senast tre månader "
                "före den 31 december 2026."
            )
        )
        assert deadline.before is True
        assert deadline.anchor_iso == "2026-12-31"
        assert deadline.resolve() == "2026-09-30"

    def test_a_duration_after_a_written_date_resolves_forward(self):
        (deadline,) = terms.scan_relative_deadlines(
            words("Garantitiden är fem år från slutbesiktningen den 12 maj 2024.")
        )
        assert deadline.before is False
        assert deadline.resolve() == "2029-05-12"

    def test_a_notice_period_with_no_anchor_date_resolves_to_nothing(self):
        """The seeded snow contract's clause, and the reason for the whole rule."""
        assert (
            terms.scan_relative_deadlines(
                words("Uppsägning skall ske skriftligen senast tre månader före avtalstidens utgång.")
            )
            == []
        )

    def test_a_duration_with_no_direction_is_not_a_deadline(self):
        assert terms.scan_relative_deadlines(words("Avtalstiden är tolv månader.")) == []

    def test_a_date_in_the_previous_sentence_is_not_the_anchor(self):
        """The bug this guard exists for, in the seeded snow contract's own words.

        Counting "tre månader före" from the agreement's *start* date produced
        a deadline of 2026-08-01 — verifiable, confident and wrong, because the
        clause counts from a date the document never states.
        """
        assert (
            terms.scan_relative_deadlines(
                words(
                    "Avtalet gäller från den 1 november 2026 och tills vidare. "
                    "Uppsägning skall ske skriftligen senast tre månader före "
                    "avtalstidens utgång."
                )
            )
            == []
        )

    def test_a_date_before_the_duration_is_not_the_anchor(self):
        assert (
            terms.scan_relative_deadlines(
                words("Enligt beslutet den 12 mars 2026 gäller tre månader före utgången")
            )
            == []
        )


class TestNoticePeriods:
    def test_the_renewal_length_is_not_the_notice_period(self):
        """Both numbers are in the sentence, and only one is the notice period."""
        found = terms.scan_notice_periods(
            words(
                "Om avtalet inte sägs upp förlängs det med tolv månader i taget. "
                "Avtalet får sägas upp skriftligen senast sex månader före avtalstidens utgång."
            )
        )
        assert [(n.count, n.unit) for n in found] == [(6, "month")]

    def test_a_number_in_the_previous_sentence_is_not_the_notice_period(self):
        found = terms.scan_notice_periods(
            words("Avgiften höjs med tre procent. Uppsägning sker senast sex månader i förväg.")
        )
        assert [(n.count, n.unit) for n in found] == [(6, "month")]

    def test_the_common_inflections_are_all_read(self):
        for phrasing in (
            "Uppsägningstiden är tre månader.",
            "Avtalet får sägas upp med tre månaders varsel.",
            "Avtalet sägs upp tre månader i förväg.",
        ):
            found = terms.scan_notice_periods(words(phrasing))
            assert found and found[0].count == 3, phrasing


class TestRecurrence:
    def test_the_written_cycle_is_read(self):
        assert [r.every for r in terms.scan_recurrence(words("Kontrollen sker vart tredje år."))] == [
            "triennial"
        ]
        assert [r.every for r in terms.scan_recurrence(words("Avläsning sker kvartalsvis."))] == [
            "quarterly"
        ]
        assert [r.every for r in terms.scan_recurrence(words("Rapport lämnas årligen."))] == ["yearly"]

    def test_prose_without_a_cycle_has_none(self):
        assert terms.scan_recurrence(words("Ersättning utgår med 12 500 kronor per månad.")) == []


# ---------------------------------------------------------------------------
# The engine, against real documents
# ---------------------------------------------------------------------------


class TestDerivation:
    def test_an_auto_renewal_clause_becomes_a_dated_watch(self, integration_env):
        env = integration_env
        build_document(
            env.store,
            "Serviceavtal hiss 2026.pdf",
            [
                "Serviceavtal hiss 2026",
                "Mellan Bostadsrattsforeningen Gjutformen 12 och Nordisk Hissteknik AB.",
                "Avtalet forlangs automatiskt med tolv manader om det inte sags upp",
                "senast tre manader fore den 31 december 2026.",
            ],
        )
        result = scan_documents(env.store, now_iso="2026-08-01T00:00:00+00:00")
        notice = [w for w in result.watches if w.kind == "notice_deadline"]
        assert len(notice) == 1
        watch = notice[0]
        assert watch.due_date == "2026-09-30"
        assert watch.derived_due_date == "2026-09-30"
        assert "2026-12-31 minus 3 månader" == watch.derivation
        assert "Säg upp eller ompröva avtalet senast 2026-09-30" == watch.title
        assert watch.status == "proposed"
        assert watch.responsible == ""
        # The evidence opens where the date was read.
        assert watch.citations and watch.citations[0].document_name == "Serviceavtal hiss 2026.pdf"
        assert "tre manader fore" in watch.citations[0].quote

    def test_the_seeded_notice_clause_is_unresolved_not_invented(self, integration_env):
        """"tre månader före avtalstidens utgång" has no date. It stays undated."""
        env = integration_env
        result = scan_documents(env.store, now_iso="2026-08-01T00:00:00+00:00")
        snow = [
            u for u in result.unresolved if u.source_document_name == "Snöröjningsavtal 2026.pdf"
        ]
        assert snow, "uppsägningstiden utan datum rapporterades inte alls"
        assert "Uppsägningstid" in snow[0].what
        assert "inte vilket datum" in snow[0].why
        assert snow[0].citations
        # …and nothing in the archive invented a deadline for it.
        assert not [
            w
            for w in result.watches
            if w.source_document_name == "Snöröjningsavtal 2026.pdf"
            and w.kind == "notice_deadline"
        ]

    def test_a_notice_clause_pointing_at_a_cited_term_resolves(self, integration_env):
        """The commonest Swedish shape: the end date is stated, one sentence up.

        `scan_relative_deadlines` will not touch this and is right not to — its
        anchor must be a date the clause points at directly. The period rule
        resolves "avtalstidens utgång" instead, and writes down that it did.
        """
        env = integration_env
        build_document(
            env.store,
            "Stadavtal 2026.pdf",
            [
                "Stadavtal",
                "Avtalet galler fran och med den 1 februari 2026 till och med den 31 januari 2028.",
                "Om avtalet inte sags upp forlangs det med tolv manader i taget.",
                "Avtalet far sagas upp skriftligen senast sex manader fore avtalstidens utgang.",
            ],
        )
        result = scan_documents(env.store, now_iso="2026-08-01T00:00:00+00:00")
        mine = [w for w in result.watches if w.source_document_name == "Stadavtal 2026.pdf"]
        notice = next(w for w in mine if w.kind == "notice_deadline")
        assert notice.due_date == "2027-07-31"
        assert notice.derivation == (
            "avtalstidens utgång 2028-01-31 enligt citerad avtalstid "
            "2026-02-01 – 2028-01-31, minus 6 månader"
        )
        # The expiry is not offered beside it: one obligation, one entry.
        assert not [w for w in mine if w.kind == "expiry"]

    def test_the_same_clause_without_an_end_date_stays_unresolved(self, integration_env):
        """Remove the period and the identical notice sentence resolves to nothing."""
        env = integration_env
        build_document(
            env.store,
            "Avtal utan avtalstid.pdf",
            [
                "Avtal",
                "Avtalet galler tills vidare.",
                "Avtalet far sagas upp skriftligen senast sex manader fore avtalstidens utgang.",
            ],
        )
        result = scan_documents(env.store, now_iso="2026-08-01T00:00:00+00:00")
        assert not [
            w for w in result.watches if w.source_document_name == "Avtal utan avtalstid.pdf"
        ]
        assert [
            u for u in result.unresolved if u.source_document_name == "Avtal utan avtalstid.pdf"
        ]

    def test_a_dated_inspection_with_a_cycle_becomes_a_recurring_watch(self, integration_env):
        """The seeded protocol: OVK senast den 31 maj 2026, vart tredje år."""
        env = integration_env
        result = scan_documents(env.store, now_iso="2026-08-01T00:00:00+00:00")
        inspections = [w for w in result.watches if w.kind == "inspection"]
        assert inspections, "ingen besiktningsbevakning ur protokollet"
        watch = next(w for w in inspections if w.recurrence == "triennial")
        assert watch.due_date == "2029-05-31"
        assert watch.derivation == "2026-05-31 plus ett intervall (triennial)"

    def test_a_month_without_a_day_is_not_a_date(self, integration_env):
        """"genomföras i maj 2026" must not become the 1st, or the 31st, of May."""
        env = integration_env
        result = scan_documents(env.store, now_iso="2026-08-01T00:00:00+00:00")
        assert not [w for w in result.watches if w.due_date.startswith("2026-05-01")]

    def test_a_warranty_runs_from_the_date_the_document_gives(self, integration_env):
        env = integration_env
        build_document(
            env.store,
            "Entreprenadkontrakt tak.pdf",
            [
                "Entreprenadkontrakt tak",
                "Garantitiden ar fem ar fran slutbesiktningen den 12 maj 2024.",
            ],
        )
        result = scan_documents(env.store, now_iso="2026-08-01T00:00:00+00:00")
        warranty = next(w for w in result.watches if w.kind == "warranty")
        assert warranty.due_date == "2029-05-12"
        assert "Garantitiden går ut 2029-05-12" == warranty.title

    def test_a_queued_attachment_is_not_scanned_until_it_is_adopted(self, integration_env):
        """Same evidence rule as the invoice review, for the same reason."""
        from app.integrations.intake import adopt_attachment, import_eml

        env = integration_env
        MAIL = Path(__file__).resolve().parent.parent / "fixtures" / "mail"
        event = import_eml(
            store=env.store,
            integrations=env.integrations,
            raw=(MAIL / "faktura-snosvangen-2026-02.eml").read_bytes(),
            filename="f.eml",
            imported_by="u",
        )
        document_id = event.attachments[0].document_id
        from app.watches.derive import reviewable_document_ids

        assert document_id not in reviewable_document_ids(env.store)

        adopt_attachment(
            store=env.store,
            integrations=env.integrations,
            event_id=event.id,
            attachment_id=event.attachments[0].id,
            user_id="ordforande",
            note="Föreningens exemplar.",
        )
        assert document_id in reviewable_document_ids(env.store)

    def test_the_same_clause_read_twice_is_one_watch(self, integration_env):
        env = integration_env
        build_document(
            env.store,
            "Avtal med upprepad klausul.pdf",
            [
                "Avtal",
                "Avtalet sags upp senast tre manader fore den 31 december 2026.",
                "Sammanfattning: uppsagning sker senast tre manader fore den 31 december 2026.",
            ],
        )
        result = scan_documents(env.store, now_iso="2026-08-01T00:00:00+00:00")
        mine = [
            w for w in result.watches if w.source_document_name == "Avtal med upprepad klausul.pdf"
        ]
        assert len(mine) == 1


# ---------------------------------------------------------------------------
# Buckets and the year wheel
# ---------------------------------------------------------------------------


def _watch(**overrides) -> Watch:
    base = dict(
        id="w1",
        tenant_id="t",
        kind="notice_deadline",
        status="approved",
        title="Säg upp senast",
        due_date="2026-09-30",
        derived_due_date="2026-09-30",
        derivation="x",
        created_at="2026-08-01T00:00:00+00:00",
    )
    return Watch(**{**base, **overrides})


class TestBuckets:
    def test_a_past_date_is_overdue_even_when_it_recurs(self):
        """A missed obligation is not a rhythm."""
        assert _watch(due_date="2026-01-01").bucket(date(2026, 8, 1)) == "overdue"
        assert (
            _watch(due_date="2026-01-01", recurrence="yearly").bucket(date(2026, 8, 1)) == "overdue"
        )

    def test_the_reminder_lead_decides_soon_not_a_fixed_window(self):
        watch = _watch(due_date="2026-09-30", remind_lead_days=30)
        assert watch.remind_at() == "2026-08-31"
        assert watch.bucket(date(2026, 8, 15)) == "later"
        assert watch.bucket(date(2026, 9, 1)) == "soon"
        # The same date with a longer lead is already "soon".
        assert _watch(due_date="2026-09-30", remind_lead_days=90).bucket(date(2026, 8, 15)) == "soon"

    def test_a_future_recurring_obligation_lives_in_the_year_wheel(self):
        assert _watch(due_date="2029-05-31", recurrence="triennial").bucket(
            date(2026, 8, 1)
        ) == "recurring"

    def test_the_next_turn_is_computed_from_the_cycle(self):
        assert _watch(due_date="2026-05-31", recurrence="triennial").next_due_after() == "2029-05-31"
        assert _watch(due_date="2026-05-31", recurrence="quarterly").next_due_after() == "2026-08-31"
        assert _watch().next_due_after() is None

    def test_the_public_shape_carries_labels_and_days_left(self):
        public = _watch(due_date="2026-09-30").public(date(2026, 8, 1))
        assert public["kind_label"] == "Uppsägning"
        assert public["status_label"] == "bevakas"
        assert public["days_left"] == 60
        assert public["bucket"] == "later"
        assert public["remind_at"] == "2026-08-31"
