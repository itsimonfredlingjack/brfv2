"""The invoice workspace: one case, honest statuses, and a history that holds.

Five promises are asserted here, and each is one the workspace makes to the
person reading it:

* **One invoice is one case.** Reading the same invoice twice, or reading it
  from two sources, converges on a single case with a single identity and
  several observations — never two competing records. Where identity cannot be
  established, nothing is merged.
* **Refresh is idempotent.** Pressing "läs om och granska" a second time
  produces no second case, no second observation, no second timeline entry and
  no second finding.
* **A comparison says what changed and what explains it.** The difference
  against the previous invoice is decomposed into the part the invoice explains
  itself (quantity) and the part it does not (unit price).
* **Fortnox is not touched, and its status is not ours.** The accounting
  system's own state is read and shown beside a local review status that is
  never called an approval.
* **A re-analysis cannot overwrite a human.** Review statuses, comments and
  decided findings survive every re-run.

Nothing in this file needs a credential, a network or a model.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.integrations.models import InvoiceLine, InvoiceSnapshot, utc_now_iso
from app.invoices import cases as case_ops
from app.invoices import compare
from app.invoices.identity import case_key_for, email_basis, number_key

TODAY = date(2026, 8, 2)


# ---------------------------------------------------------------------------
# Building blocks
# ---------------------------------------------------------------------------


def snapshot(
    *,
    tenant_id: str = "gjutformen-12",
    adapter: str = "fixture-accounting",
    external_ref: str = "SI-TEST-1",
    supplier: str = "Snösvängen Entreprenad AB",
    supplier_ref: str | None = "556812-3344",
    number: str | None = "TEST-1",
    invoice_date: str | None = "2026-05-01",
    due_date: str | None = "2026-05-31",
    total: str | None = "6250.00",
    vat: str | None = "1250.00",
    lines: list[InvoiceLine] | None = None,
    source_status: dict | None = None,
    source_event_id: str | None = None,
) -> InvoiceSnapshot:
    """One synthetic reading. Built rather than fixtured so a test can say
    exactly which field it is about."""
    return InvoiceSnapshot(
        id=uuid.uuid4().hex[:12],
        tenant_id=tenant_id,
        adapter=adapter,
        external_ref=external_ref,
        supplier_name=supplier,
        supplier_ref=supplier_ref,
        invoice_number=number,
        invoice_date=invoice_date,
        due_date=due_date,
        total_amount=Decimal(total) if total is not None else None,
        currency="SEK",
        vat_amount=Decimal(vat) if vat is not None else None,
        lines=lines or [],
        retrieved_at=utc_now_iso(),
        source_dataset="test",
        content_sha256="0" * 64,
        source_status=source_status or {},
        source_event_id=source_event_id,
    )


def line(description: str, quantity: str, unit_price: str, amount: str) -> InvoiceLine:
    return InvoiceLine(
        description=description,
        quantity=Decimal(quantity),
        unit_price=Decimal(unit_price),
        amount=Decimal(amount),
    )


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------


class TestIdentity:
    def test_supplier_and_number_are_the_key(self):
        key, basis = case_key_for(snapshot(number="2026-131"))
        assert key.endswith("#2026131")
        assert "fakturanummer" in basis

    def test_separators_in_a_number_do_not_make_a_second_case(self):
        assert number_key("2026-131") == number_key("2026/131") == number_key("2026 131")

    def test_without_a_number_the_key_is_the_source_reference_and_merges_with_nothing(self):
        key, basis = case_key_for(snapshot(number=None, external_ref="SI-9"))
        assert key == "fixture-accounting:SI-9"
        assert "slås inte ihop" in basis

    def test_two_sources_reading_the_same_invoice_get_the_same_key(self):
        fixture_read = snapshot(adapter="fixture-accounting", external_ref="SI-2026-131", number="2026-131")
        fortnox_read = snapshot(adapter="fortnox", external_ref="4711", number="2026-131")
        assert case_key_for(fixture_read)[0] == case_key_for(fortnox_read)[0]

    def test_a_different_number_from_the_same_supplier_is_a_different_case(self):
        assert case_key_for(snapshot(number="2026-131"))[0] != case_key_for(snapshot(number="2026-114"))[0]


class TestEmailIdentity:
    """An email is attacker-controlled text, so attaching one is stricter."""

    def test_the_message_the_invoice_was_read_out_of_always_counts(self, integration_env):
        env = integration_env
        event = _import_mail(env, "faktura-snosvangen-2026-02.eml")
        basis = email_basis(event, snapshot(source_event_id=event.id, number="ZZZ-999"))
        assert basis == "Fakturan lästes in ur det här meddelandet."

    def test_a_message_quoting_the_number_and_naming_the_supplier_counts(self, integration_env):
        env = integration_env
        event = _import_mail(env, "faktura-snosvangen-2026-02.eml")
        # The fixture mail is about invoice 2026-114 from Snösvängen.
        assert email_basis(event, snapshot(number="2026-114")) is not None

    def test_a_message_from_the_same_supplier_about_something_else_is_not_attached(
        self, integration_env
    ):
        env = integration_env
        event = _import_mail(env, "faktura-snosvangen-2026-02.eml")
        assert email_basis(event, snapshot(number="9999-001")) is None

    def test_a_number_alone_is_not_enough_without_the_supplier(self, integration_env):
        env = integration_env
        event = _import_mail(env, "faktura-snosvangen-2026-02.eml")
        assert email_basis(event, snapshot(supplier="Nordisk Hissteknik AB", number="2026-114")) is None


def _import_mail(env, filename: str):
    from pathlib import Path

    from app.integrations.intake import import_eml

    raw = (Path(__file__).resolve().parent.parent / "fixtures" / "mail" / filename).read_bytes()
    return import_eml(
        store=env.store,
        integrations=env.integrations,
        raw=raw,
        filename=filename,
        imported_by="admin",
    )


# ---------------------------------------------------------------------------
# Convergence and idempotency
# ---------------------------------------------------------------------------


class TestConvergence:
    def test_reading_an_invoice_opens_exactly_one_case(self, integration_env):
        env = integration_env
        stored = env.integrations.upsert_invoice(snapshot())
        case = case_ops.case_for_snapshot(env.store, stored)
        assert case.primary_invoice_id == stored.id
        assert [o.kind for o in case.observations] == ["accounting_snapshot"]
        assert len(env.integrations.list_invoice_cases()) == 1

    def test_reading_the_same_invoice_again_changes_nothing(self, integration_env):
        env = integration_env
        first = env.integrations.upsert_invoice(snapshot())
        case = case_ops.case_for_snapshot(env.store, first)
        opened = len(case.timeline)

        # A second read mints a new adapter-side id; the store keeps the
        # identity, so nothing downstream is orphaned.
        second = env.integrations.upsert_invoice(snapshot())
        assert second.id == first.id
        again = case_ops.case_for_snapshot(env.store, second)

        assert again.id == case.id
        assert len(again.timeline) == opened
        assert len(env.integrations.list_invoice_cases()) == 1
        assert len(env.integrations.list_invoices()) == 1

    def test_a_second_source_becomes_a_second_observation_not_a_second_case(
        self, integration_env
    ):
        env = integration_env
        fixture_read = env.integrations.upsert_invoice(
            snapshot(adapter="fixture-accounting", external_ref="SI-2026-131", number="2026-131")
        )
        case_ops.case_for_snapshot(env.store, fixture_read)
        fortnox_read = env.integrations.upsert_invoice(
            snapshot(
                adapter="fortnox",
                external_ref="4711",
                number="2026-131",
                source_status={"Booked": "True", "Cancelled": "False"},
            )
        )
        case = case_ops.case_for_snapshot(env.store, fortnox_read)

        assert len(env.integrations.list_invoice_cases()) == 1
        snapshots = [o for o in case.observations if o.kind == "accounting_snapshot"]
        assert {o.adapter for o in snapshots} == {"fixture-accounting", "fortnox"}
        # Every observation says why it was attached.
        assert all(o.basis for o in case.observations)

    def test_the_mail_and_its_attachment_join_the_case(self, integration_env):
        env = integration_env
        event = _import_mail(env, "faktura-snosvangen-2026-02.eml")
        stored = env.integrations.upsert_invoice(
            snapshot(number="2026-114", source_event_id=event.id)
        )
        case = case_ops.case_for_snapshot(env.store, stored)
        kinds = [o.kind for o in case.observations]
        assert "email" in kinds and "document" in kinds
        documents = case_ops.documents_for(env.store, case)
        assert documents and documents[0]["role"] == "Originalfil ur meddelandet"

    def test_the_projection_picks_up_invoices_read_before_the_workspace_existed(
        self, integration_env
    ):
        env = integration_env
        env.import_invoice("SI-2026-114")
        env.import_invoice("SI-2026-207")
        assert env.integrations.list_invoice_cases() == []
        rows = case_ops.ensure_cases(env.store)
        assert len(rows) == 2
        # Running it again is a no-op, not a second set.
        assert len(case_ops.ensure_cases(env.store)) == 2


# ---------------------------------------------------------------------------
# Change against the previous invoice
# ---------------------------------------------------------------------------


class TestPreviousComparison:
    def test_the_first_invoice_from_a_supplier_says_so_rather_than_inventing_a_baseline(self):
        current = snapshot()
        finding = compare.previous_comparison(current, [current])
        assert finding.verdict == "cannot_be_verified"
        assert "ingen tidigare inläst faktura" in finding.suggestion.lower()

    def test_an_unchanged_amount_is_reported_as_unchanged(self):
        old = snapshot(external_ref="A", number="1", invoice_date="2026-01-01")
        new = snapshot(external_ref="B", number="2", invoice_date="2026-02-01")
        finding = compare.previous_comparison(new, [old, new])
        assert finding.verdict == "matches"
        assert "oförändrat" in finding.suggestion

    def test_a_rise_is_split_into_what_the_invoice_explains_and_what_it_does_not(self):
        old = snapshot(
            external_ref="A",
            number="2026-114",
            invoice_date="2026-02-03",
            total="6250.00",
            vat="1250.00",
            lines=[line("Maskinell snöröjning med traktor", "4", "1250.00", "5000.00")],
        )
        new = snapshot(
            external_ref="B",
            number="2026-131",
            invoice_date="2026-03-03",
            total="10875.00",
            vat="2175.00",
            lines=[line("Maskinell snöröjning med traktor", "6", "1450.00", "8700.00")],
        )
        finding = compare.previous_comparison(new, [old, new])

        assert finding.verdict == "possible_deviation"
        assert "4 625,00 SEK" in finding.suggestion
        assert "+74,0 %" in finding.suggestion
        # The quantity effect is explained by the invoice; the price effect is not.
        assert "Fakturan förklarar själv en del av det" in finding.suggestion
        assert "antalet" in finding.suggestion
        assert "Det här förklarar den inte" in finding.suggestion
        assert "à-priset" in finding.suggestion
        # 6 × (1450 − 1250) = 1 200 of the difference is the price rise.
        assert "1 200,00 SEK av skillnaden" in finding.suggestion
        # 1250 × (6 − 4) = 2 500 is the quantity rise.
        assert "2 500,00 SEK av skillnaden" in finding.suggestion

    def test_it_never_claims_the_rise_is_wrong(self):
        old = snapshot(external_ref="A", number="1", invoice_date="2026-01-01", total="1000.00")
        new = snapshot(external_ref="B", number="2", invoice_date="2026-02-01", total="2000.00")
        finding = compare.previous_comparison(new, [old, new])
        assert finding.verdict != "matches"
        assert finding.verdict_label == "möjlig avvikelse"
        assert "kan vara helt avtalsenlig" in (finding.uncertainty or "")

    def test_the_baseline_is_the_previous_invoice_not_the_newest_one(self):
        first = snapshot(external_ref="A", number="1", invoice_date="2026-01-01", total="1000.00")
        second = snapshot(external_ref="B", number="2", invoice_date="2026-02-01", total="1500.00")
        third = snapshot(external_ref="C", number="3", invoice_date="2026-03-01", total="2000.00")
        assert compare.previous_snapshot(third, [first, second, third]).external_ref == "B"
        assert compare.previous_snapshot(second, [first, second, third]).external_ref == "A"


class TestDuplicatesAndCredits:
    def _keys(self, rows):
        return {row.id: case_key_for(row)[0] for row in rows}

    def test_the_same_amount_days_apart_is_flagged_as_a_possible_duplicate(self):
        a = snapshot(external_ref="A", number="1001", invoice_date="2026-05-02")
        b = snapshot(external_ref="B", number="1002", invoice_date="2026-05-06")
        keys = self._keys([a, b])
        findings = compare.duplicate_findings(
            b, [a, b], case_key=keys[b.id], key_of=lambda r: keys[r.id]
        )
        assert [f.finding_type for f in findings] == ["invoice_possible_duplicate"]
        assert "4 dagar isär" in findings[0].suggestion
        assert "flagga, inte ett fel" in (findings[0].uncertainty or "")

    def test_the_same_amount_months_apart_is_not(self):
        a = snapshot(external_ref="A", number="1001", invoice_date="2026-01-02")
        b = snapshot(external_ref="B", number="1002", invoice_date="2026-05-06")
        keys = self._keys([a, b])
        assert (
            compare.duplicate_findings(b, [a, b], case_key=keys[b.id], key_of=lambda r: keys[r.id])
            == []
        )

    def test_the_same_number_under_two_spellings_of_the_supplier_is_caught(self):
        a = snapshot(supplier="Snösvängen Entreprenad AB", external_ref="A", number="2026-131")
        b = snapshot(supplier="Snösvängen AB", external_ref="B", number="2026-131")
        keys = self._keys([a, b])
        findings = compare.duplicate_findings(
            b, [a, b], case_key=keys[b.id], key_of=lambda r: keys[r.id]
        )
        types = [f.finding_type for f in findings]
        assert "invoice_possible_duplicate" in types
        duplicate = next(f for f in findings if f.finding_type == "invoice_possible_duplicate")
        assert "särskiljande ordet" in duplicate.suggestion

    def test_an_exactly_opposite_amount_is_offered_as_a_possible_credit(self):
        a = snapshot(external_ref="A", number="1001", invoice_date="2026-05-02", total="6250.00")
        b = snapshot(external_ref="B", number="1002", invoice_date="2026-05-20", total="-6250.00")
        keys = self._keys([a, b])
        findings = compare.duplicate_findings(
            b, [a, b], case_key=keys[b.id], key_of=lambda r: keys[r.id]
        )
        credit = next(f for f in findings if f.finding_type == "invoice_credit_relation")
        assert "kan vara krediteringen" in credit.suggestion
        assert "betyder inte" in (credit.uncertainty or "")


class TestNewLines:
    def test_a_line_never_seen_from_this_supplier_becomes_a_question(self):
        old = snapshot(
            external_ref="A",
            number="1",
            invoice_date="2026-01-01",
            lines=[line("Maskinell snöröjning med traktor", "4", "1250.00", "5000.00")],
        )
        new = snapshot(
            external_ref="B",
            number="2",
            invoice_date="2026-02-01",
            lines=[
                line("Maskinell snöröjning med traktor", "4", "1250.00", "5000.00"),
                line("Miljöavgift", "1", "450.00", "450.00"),
            ],
        )
        finding = compare.new_line_finding(new, [old, new])
        assert finding is not None
        assert finding.verdict == "cannot_be_verified"
        assert "Miljöavgift" in finding.suggestion
        assert "Maskinell" not in finding.suggestion

    def test_with_no_history_nothing_is_new(self):
        only = snapshot(lines=[line("Miljöavgift", "1", "450.00", "450.00")])
        assert compare.new_line_finding(only, [only]) is None


# ---------------------------------------------------------------------------
# The case as something people work on
# ---------------------------------------------------------------------------


@pytest.fixture()
def worked(integration_env):
    """One real fixture invoice, converged and analysed against the seeded corpus."""
    env = integration_env
    stored = env.integrations.upsert_invoice(env.adapter.get_invoice(env.brf_id, "SI-2026-131"))
    case = case_ops.case_for_snapshot(env.store, stored)
    env.case = case_ops.analyse_case(env.store, case)
    return env


class TestAnalysis:
    def test_it_produces_both_a_contract_finding_and_a_history_finding(self, worked):
        findings = case_ops.findings_for_invoice(worked.store, worked.case.primary_invoice_id)
        types = {f.finding_type for f in findings}
        assert types & {
            "invoice_contract_amount",
            "invoice_contract_period",
            "invoice_without_contract",
            "contract_term_not_comparable",
        }
        assert "invoice_previous_comparison" in types

    def test_running_it_again_adds_no_second_history(self, worked):
        before = len(worked.case.timeline)
        findings_before = len(
            case_ops.findings_for_invoice(worked.store, worked.case.primary_invoice_id)
        )
        again = case_ops.analyse_case(worked.store, worked.case)
        assert len(again.timeline) == before
        assert (
            len(case_ops.findings_for_invoice(worked.store, again.primary_invoice_id))
            == findings_before
        )

    def test_signals_carry_the_finding_they_came_from(self, worked):
        for signal in worked.case.signals:
            if signal.kind in ("open_question", "no_deviation_found"):
                continue
            assert signal.finding_id, f"{signal.kind} saknar fynd att peka på"

    def test_a_dismissed_finding_stops_driving_a_signal(self, worked):
        findings = case_ops.findings_for_invoice(worked.store, worked.case.primary_invoice_id)
        for finding in findings:
            worked.integrations.update_finding(finding.model_copy(update={"status": "dismissed"}))
        assert case_ops.signals_for(
            case_ops.findings_for_invoice(worked.store, worked.case.primary_invoice_id)
        ) == []

    def test_a_decided_finding_survives_a_re_run(self, worked):
        findings = case_ops.findings_for_invoice(worked.store, worked.case.primary_invoice_id)
        decided = worked.integrations.update_finding(
            findings[0].model_copy(update={"status": "approved", "decision_note": "kollad"})
        )
        case_ops.analyse_case(worked.store, worked.case)
        after = worked.integrations.get_finding(decided.id)
        assert after is not None and after.status == "approved"
        assert after.decision_note == "kollad"


class TestHumanWork:
    def test_a_local_status_is_never_called_an_approval(self, worked):
        from app.invoices.models import REVIEW_STATUS_CAVEATS, REVIEW_STATUS_LABELS

        joined = " ".join(REVIEW_STATUS_LABELS.values()).lower()
        assert "godkänn" not in joined and "attest" not in joined
        assert "inte ett godkännande" in REVIEW_STATUS_CAVEATS["reviewed_no_objection"]

    def test_setting_a_status_writes_who_and_when(self, worked):
        case = case_ops.set_review_status(
            worked.store,
            worked.case,
            status="reviewed_no_objection",
            note="",
            user_id="anna",
        )
        assert case.review_status == "reviewed_no_objection"
        assert case.review_status_by == "anna"
        latest = case.timeline[-1]
        assert latest.kind == "status_changed" and latest.by == "anna" and latest.human

    def test_the_statuses_that_hide_a_missing_sentence_demand_one(self, worked):
        for status in ("needs_investigation", "awaiting_documentation", "question_sent"):
            with pytest.raises(case_ops.CaseError):
                case_ops.set_review_status(
                    worked.store, worked.case, status=status, note="  ", user_id="anna"
                )

    def test_a_comment_is_kept_apart_from_the_engine(self, worked):
        case = case_ops.comment(
            worked.store, worked.case, text="Ringde leverantören.", user_id="anna"
        )
        assert [c.note for c in case.comments()] == ["Ringde leverantören."]
        assert case.comments()[0].human is True
        assert all(not e.human for e in case.timeline if e.kind == "finding_recorded")

    def test_two_identical_comments_are_two_comments(self, worked):
        case = case_ops.comment(worked.store, worked.case, text="Påminde", user_id="anna")
        case = case_ops.comment(worked.store, case, text="Påminde", user_id="anna")
        assert len(case.comments()) == 2

    def test_a_re_analysis_leaves_the_human_record_alone(self, worked):
        case = case_ops.set_review_status(
            worked.store,
            worked.case,
            status="needs_investigation",
            note="Fråga om taxan",
            user_id="anna",
        )
        case = case_ops.comment(worked.store, case, text="Avtalet mailat", user_id="bo")
        case = case_ops.assign(worked.store, case, responsible="Bo", user_id="anna")

        after = case_ops.analyse_case(worked.store, case)
        assert after.review_status == "needs_investigation"
        assert after.review_status_note == "Fråga om taxan"
        assert after.responsible == "Bo"
        assert [c.note for c in after.comments()] == ["Avtalet mailat"]

    def test_the_history_can_only_grow(self, worked):
        from app.integrations.store import IntegrationError

        truncated = worked.case.model_copy(update={"timeline": worked.case.timeline[:1]})
        with pytest.raises(IntegrationError):
            worked.integrations.upsert_invoice_case(truncated)


class TestSourceStatusIsNotOurs:
    def test_the_accounting_systems_state_is_read_and_labelled_as_theirs(self, integration_env):
        env = integration_env
        stored = env.integrations.upsert_invoice(
            snapshot(adapter="fortnox", source_status={"Booked": "True", "Cancelled": "False"})
        )
        case = case_ops.case_for_snapshot(env.store, stored)
        assert case.source_status is not None
        assert case.source_status.booked is True
        assert case.source_status.label() == "Bokförd i ekonomisystemet"
        # And it is nowhere near the local one.
        assert case.review_status == "not_reviewed"

    def test_a_source_with_no_such_notion_gets_no_invented_status(self, integration_env):
        env = integration_env
        stored = env.integrations.upsert_invoice(snapshot())
        case = case_ops.case_for_snapshot(env.store, stored)
        assert case.source_status is None


class TestQueue:
    def test_an_overdue_case_is_only_overdue_while_it_is_open(self, integration_env):
        env = integration_env
        stored = env.integrations.upsert_invoice(snapshot(due_date="2026-01-01"))
        case = case_ops.case_for_snapshot(env.store, stored)
        assert case.overdue(TODAY) is True
        closed = case_ops.set_review_status(
            env.store, case, status="closed", note="", user_id="anna"
        )
        assert closed.overdue(TODAY) is False

    def test_date_signals_are_computed_not_stored(self, integration_env):
        env = integration_env
        stored = env.integrations.upsert_invoice(snapshot(due_date="2026-08-05"))
        case = case_ops.case_for_snapshot(env.store, stored)
        assert [s.kind for s in case.signals] == []
        assert "due_soon" in [s.kind for s in case.all_signals(TODAY)]

    def test_counts_are_computed_on_the_server(self, integration_env):
        env = integration_env
        env.import_invoice("SI-2026-114")
        rows = case_ops.ensure_cases(env.store)
        counts = case_ops.totals(rows, TODAY)
        assert counts["total"] == 1 and counts["open"] == 1 and counts["unassigned"] == 1


class TestSupplierMemory:
    def test_it_is_assembled_from_records_that_already_exist(self, integration_env):
        env = integration_env
        env.import_invoice("SI-2026-114")
        env.import_invoice("SI-2026-131")
        rows = case_ops.ensure_cases(env.store)
        newest = max(rows, key=lambda c: c.invoice_date or "")
        context = case_ops.supplier_context(env.store, newest, TODAY)
        assert context["invoice_count"] == 2
        assert context["previous"] and context["previous"][0]["invoice_number"] == "2026-114"
        assert context["amount_low"] == "6250.00"
        assert context["org_numbers"] == ["556812-3344"]
