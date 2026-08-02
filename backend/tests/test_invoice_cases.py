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


def case_for(env, snapshot) -> object:
    """The projected case a snapshot belongs to.

    Goes through the deterministic id rather than through a lookup, because
    that id *is* the identity — a case exists conceptually as soon as its
    invoice does, whether or not anybody has written it to disk yet.
    """
    return case_ops.project_one(
        env.store, case_ops.case_id_for(env.store.tenant_id, case_key_for(snapshot)[0])
    )


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
        case = case_for(env, stored)
        assert case.primary_invoice_id == stored.id
        assert [o.kind for o in case.observations] == ["accounting_snapshot"]
        assert len(case_ops.project(env.store)) == 1

    def test_reading_the_same_invoice_again_changes_nothing(self, integration_env):
        env = integration_env
        first = env.integrations.upsert_invoice(snapshot())
        case = case_for(env, first)
        opened = len(case.timeline)

        # A second read mints a new adapter-side id; the store keeps the
        # identity, so nothing downstream is orphaned.
        second = env.integrations.upsert_invoice(snapshot())
        assert second.id == first.id
        again = case_for(env, second)

        assert again.id == case.id
        assert len(again.timeline) == opened
        assert len(case_ops.project(env.store)) == 1
        assert len(env.integrations.list_invoices()) == 1

    def test_a_second_source_becomes_a_second_observation_not_a_second_case(
        self, integration_env
    ):
        env = integration_env
        env.integrations.upsert_invoice(
            snapshot(adapter="fixture-accounting", external_ref="SI-2026-131", number="2026-131")
        )
        fortnox_read = env.integrations.upsert_invoice(
            snapshot(
                adapter="fortnox",
                external_ref="4711",
                number="2026-131",
                source_status={"Booked": "True", "Cancelled": "False"},
            )
        )
        case = case_for(env, fortnox_read)

        assert len(case_ops.project(env.store)) == 1
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
        case = case_for(env, stored)
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
        rows = case_ops.project(env.store)
        assert len(rows) == 2
        # And the projection left nothing behind to be picked up twice.
        assert env.integrations.list_invoice_cases() == []
        assert len(case_ops.project(env.store)) == 2


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
    env.case = case_ops.analyse_case(env.store, case_for(env, stored).id)
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
        again = case_ops.analyse_case(worked.store, worked.case.id)
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
        case_ops.analyse_case(worked.store, worked.case.id)
        after = worked.integrations.get_finding(decided.id)
        assert after is not None and after.status == "approved"
        assert after.decision_note == "kollad"


class TestAnalysisAudit:
    """A re-analysis may replace the engine's own findings, but not silently.

    "Open" means nobody had formally decided on it — not that nobody was
    working from it. Somebody may well have rung the supplier because of an
    open finding, so a run that replaces one has to leave behind: that it
    happened, when, which reading it was built on, which rules produced it,
    what differed, and the replaced version itself. The old version stops being
    a card on the screen; it does not stop existing.
    """

    def _changed_reading(self, env, *, amount: str = "9999.00") -> None:
        """The same invoice, read again out of a source that now says something else."""
        current = env.integrations.get_invoice(env.case.primary_invoice_id)
        env.integrations.upsert_invoice(
            current.model_copy(
                update={
                    "total_amount": Decimal(amount),
                    "content_sha256": "a" * 64,
                    "retrieved_at": utc_now_iso(),
                }
            )
        )

    def test_the_first_run_records_what_it_read_and_which_rules_read_it(self, worked):
        from app.invoices.models import ANALYSIS_ENGINE_VERSION, ENGINE

        runs = worked.integrations.list_analysis_runs(worked.case.primary_invoice_id)
        assert len(runs) == 1
        run = runs[0]
        snapshot = worked.integrations.get_invoice(worked.case.primary_invoice_id)
        assert run.sequence == 1 and run.supersedes == ""
        assert run.engine == ENGINE and run.engine_version == ANALYSIS_ENGINE_VERSION
        assert run.source.content_sha256 == snapshot.content_sha256
        assert run.source.adapter == snapshot.adapter
        assert run.source.external_ref == snapshot.external_ref
        assert run.ran_at
        # It replaced nothing, so it changed nothing. Listing every finding it
        # produced as "new" would be the findings on the screen repeated.
        assert run.replaced == [] and run.changes == []
        assert run.finding_count == len(
            case_ops.findings_for_invoice(worked.store, worked.case.primary_invoice_id)
        )
        # And its note does not describe something that did not happen.
        assert "ersatts" not in run.note

    def test_the_case_points_at_the_run_its_findings_came_from(self, worked):
        from app.invoices.models import ANALYSIS_ENGINE_VERSION

        run = worked.integrations.list_analysis_runs(worked.case.primary_invoice_id)[-1]
        assert worked.case.analysis_run_id == run.id
        assert worked.case.analysis_sequence == 1
        assert worked.case.analysis_engine_version == ANALYSIS_ENGINE_VERSION
        assert worked.case.public(TODAY)["analysis_outdated"] is False

    def test_findings_produced_under_older_rules_are_visibly_old(self, worked, monkeypatch):
        import app.invoices.models as models

        monkeypatch.setattr(models, "ANALYSIS_ENGINE_VERSION", "9999.01")
        assert worked.case.public(TODAY)["analysis_outdated"] is True

    def test_a_run_that_changes_nothing_is_not_a_second_version(self, worked):
        before = len(worked.case.timeline)
        again = case_ops.analyse_case(worked.store, worked.case.id)
        runs = worked.integrations.list_analysis_runs(worked.case.primary_invoice_id)
        assert len(runs) == 1, "en omkörning som inte ändrade något blev en version"
        assert len(again.timeline) == before
        assert again.analysis_at == worked.case.analysis_at

    def test_a_changed_reading_records_a_new_version_that_names_the_old_one(self, worked):
        first = worked.integrations.list_analysis_runs(worked.case.primary_invoice_id)[0]
        self._changed_reading(worked)
        case_ops.analyse_case(worked.store, worked.case.id)

        runs = worked.integrations.list_analysis_runs(worked.case.primary_invoice_id)
        assert [r.sequence for r in runs] == [1, 2]
        second = runs[1]
        assert second.supersedes == first.id
        assert second.supersedes_sequence == 1
        assert second.source_changed is True
        assert second.source.content_sha256 == "a" * 64
        assert second.id != first.id

    def test_the_replaced_findings_are_kept_whole_by_the_run_that_replaced_them(self, worked):
        was = {
            f.id: f.suggestion
            for f in case_ops.findings_for_invoice(
                worked.store, worked.case.primary_invoice_id
            )
        }
        assert was
        self._changed_reading(worked)
        case_ops.analyse_case(worked.store, worked.case.id)

        run = worked.integrations.list_analysis_runs(worked.case.primary_invoice_id)[-1]
        replaced = {f.id: f.suggestion for f in run.replaced}
        assert replaced == was, "det som ersattes finns inte kvar ordagrant i revisionsspåret"
        # And it is emphatically not a live card any more.
        live = {
            f.id
            for f in case_ops.findings_for_invoice(
                worked.store, worked.case.primary_invoice_id
            )
        }
        assert live.isdisjoint(replaced)

    def test_the_difference_is_written_out_with_both_values(self, worked):
        self._changed_reading(worked)
        case_ops.analyse_case(worked.store, worked.case.id)
        run = worked.integrations.list_analysis_runs(worked.case.primary_invoice_id)[-1]

        assert run.changes, "en ny version utan en enda beskriven skillnad"
        changed = [c for c in run.changes if c.kind == "changed"]
        assert changed, "ingen ändring beskrevs som en ändring"
        for change in changed:
            assert change.from_text and change.to_text
            assert change.summary
            assert change.finding_type_label and change.finding_type_label != change.finding_type
            assert change.from_text != change.to_text or change.fact_changes, (
                "ett fynd rapporterades som ändrat utan att något gick att peka på"
            )
        spoken = " ".join(
            [c.to_text for c in changed]
            + [f"{f.label} {f.from_value} {f.to_value}" for c in changed for f in c.fact_changes]
        )
        assert "9 999,00" in spoken, (
            "det nya beloppet står inte i beskrivningen av vad som ändrades"
        )
        # The old value has to be there too — "det står 9 999 nu" without "det
        # stod 12 500 då" is not a change description, it is a reading.
        assert any(f.from_value for c in changed for f in c.fact_changes)

    def test_the_timeline_says_that_a_new_analysis_replaced_the_old(self, worked):
        self._changed_reading(worked)
        case = case_ops.analyse_case(worked.store, worked.case.id)
        run = worked.integrations.list_analysis_runs(case.primary_invoice_id)[-1]

        entries = [e for e in case.timeline if e.kind == "analysis_run"]
        assert len(entries) == 2, "den nya granskningen syns inte som en egen händelse"
        latest = entries[-1]
        assert "version 2" in latest.summary
        assert latest.ref_id == run.id
        assert "Ersatte" in latest.note
        assert "a" * 16 in latest.note, "källversionen står inte i händelsen"
        assert run.engine_version in latest.note, "regelversionen står inte i händelsen"

    def test_a_recorded_run_is_never_edited(self, worked):
        run = worked.integrations.list_analysis_runs(worked.case.primary_invoice_id)[0]
        again = worked.integrations.append_analysis_run(
            run.model_copy(update={"summary": "omskriven"})
        )
        assert again.summary == run.summary, "en inspelad körning gick att skriva om"
        assert len(worked.integrations.list_analysis_runs()) == 1
        for verb in ("update_analysis_run", "delete_analysis_run", "upsert_analysis_run"):
            assert not hasattr(worked.integrations, verb)

    def test_a_decided_finding_is_never_in_the_replaced_set(self, worked):
        findings = case_ops.findings_for_invoice(worked.store, worked.case.primary_invoice_id)
        decided = worked.integrations.update_finding(
            findings[0].model_copy(update={"status": "approved", "decision_note": "kollad"})
        )
        self._changed_reading(worked)
        case_ops.analyse_case(worked.store, worked.case.id)

        run = worked.integrations.list_analysis_runs(worked.case.primary_invoice_id)[-1]
        assert decided.id not in {f.id for f in run.replaced}
        assert run.kept_count >= 1
        still = worked.integrations.get_finding(decided.id)
        assert still is not None and still.status == "approved"

    def test_something_a_person_dismissed_does_not_come_back_as_a_second_card(self, worked):
        findings = case_ops.findings_for_invoice(worked.store, worked.case.primary_invoice_id)
        target = findings[0]
        worked.integrations.update_finding(
            target.model_copy(update={"status": "dismissed", "decided_by": "anna"})
        )
        case_ops.analyse_case(worked.store, worked.case.id)

        after = case_ops.findings_for_invoice(worked.store, worked.case.primary_invoice_id)
        same = [f for f in after if f.suggestion == target.suggestion]
        assert len(same) == 1 and same[0].status == "dismissed", (
            "motorn skrev ett andra öppet kort bredvid ett beslut om samma sak"
        )

    def test_the_engine_still_saying_it_is_counted_on_the_next_recorded_run(
        self, integration_env
    ):
        """Suppressing a repeat must not read as the engine having stopped saying it."""
        env = integration_env
        first = env.integrations.upsert_invoice(
            snapshot(external_ref="AUD-1", supplier="Ödemarksbolaget AB", number="A-1")
        )
        case = case_for(env, first)
        case_ops.analyse_case(env.store, case.id)

        findings = case_ops.findings_for_invoice(env.store, first.id)
        # Whatever the document review made of it — the point is that it is not
        # the history comparison, so the second invoice below leaves it alone.
        against_documents = next(
            f for f in findings if f.finding_type != "invoice_previous_comparison"
        )
        env.integrations.update_finding(
            against_documents.model_copy(update={"status": "dismissed", "decided_by": "anna"})
        )

        # An earlier invoice from the same supplier arrives: the history
        # comparison changes, the contract finding does not.
        env.integrations.upsert_invoice(
            snapshot(
                external_ref="AUD-0",
                supplier="Ödemarksbolaget AB",
                number="A-0",
                invoice_date="2026-04-01",
                total="5000.00",
            )
        )
        case_ops.analyse_case(env.store, case.id)

        run = env.integrations.list_analysis_runs(first.id)[-1]
        assert run.sequence == 2
        assert run.already_decided_count >= 1, (
            "att motorn fortfarande säger det som avfärdats är inte inspelat någonstans"
        )
        assert run.kept_count >= 1
        assert any(c.finding_type == "invoice_previous_comparison" for c in run.changes)

    def test_confirming_a_supplier_name_is_recorded_as_what_it_changed(self, integration_env):
        """The one way an operator can change the analysis without the source moving.

        Confirming that "Snösvängen AB" and "Snösvängen Entreprenad AB" are the
        same company turns a weak anchor into a confirmed one, which is exactly
        the sort of change that used to happen silently: the finding's caveat
        disappeared and nothing said why.
        """
        import uuid as _uuid

        from app.integrations.models import SupplierAlias
        from app.integrations.supplier import normalize

        env = integration_env
        invoice = env.import_invoice("SI-2027-018")
        case = case_for(env, invoice)
        case_ops.analyse_case(env.store, case.id)

        weak = next(
            f
            for f in case_ops.findings_for_invoice(env.store, invoice.id)
            if f.alias_proposal is not None
        )
        proposal = weak.alias_proposal
        env.integrations.add_supplier_alias(
            SupplierAlias(
                id=_uuid.uuid4().hex[:12],
                tenant_id=env.store.tenant_id,
                invoice_name=proposal.invoice_name,
                document_name=proposal.document_name,
                normalized_key=normalize(proposal.invoice_name),
                created_by="anna",
                created_at=utc_now_iso(),
                note=None,
            )
        )
        case_ops.analyse_case(env.store, case.id)

        runs = env.integrations.list_analysis_runs(invoice.id)
        assert [r.sequence for r in runs] == [1, 2]
        latest = runs[-1]
        assert latest.source_changed is False, "källan rörde sig inte — reglerna gjorde det"
        anchors = [
            fact
            for change in latest.changes
            for fact in change.fact_changes
            if fact.label == "Koppling till leverantören"
        ]
        assert anchors, "att kopplingen bekräftades syns inte som en beskriven skillnad"
        assert anchors[0].from_value == "delvis namnlikhet"
        assert anchors[0].to_value == "ett namn någon här har bekräftat"
        # And the version that rested on the weak link is still readable, with
        # the weakness still on it — that is what makes it checkable later.
        assert any(f.anchor_strength == "partial" for f in latest.replaced)

    def test_the_audit_trail_belongs_to_the_tenant_like_everything_else(self, worked):
        run = worked.integrations.list_analysis_runs()[0]
        assert run.tenant_id == worked.store.tenant_id
        for finding in run.replaced:
            assert finding.tenant_id == worked.store.tenant_id


class TestAnalysisDiff:
    """The comparison itself, without a store in the way."""

    def _finding(self, finding_type: str, verdict: str, text: str):
        from app.integrations.models import ReviewFinding

        return ReviewFinding(
            id=uuid.uuid4().hex[:12],
            tenant_id="t",
            finding_type=finding_type,
            created_at=utc_now_iso(),
            invoice_id="i",
            verdict=verdict,
            suggestion=text,
        )

    def test_identical_findings_are_no_difference_at_all(self):
        from app.invoices import audit

        a = self._finding("invoice_new_line", "cannot_be_verified", "samma text")
        b = self._finding("invoice_new_line", "cannot_be_verified", "samma text")
        assert audit.diff_findings([a], [b]) == []

    def test_one_of_a_type_on_each_side_is_a_change_not_a_swap(self):
        from app.invoices import audit

        old = self._finding("invoice_previous_comparison", "matches", "oförändrat")
        new = self._finding("invoice_previous_comparison", "possible_deviation", "höjt")
        [change] = audit.diff_findings([old], [new])
        assert change.kind == "changed"
        assert change.from_verdict == "matches" and change.to_verdict == "possible_deviation"
        assert change.from_text == "oförändrat" and change.to_text == "höjt"
        assert change.replaced_finding_id == old.id and change.finding_id == new.id

    def test_several_of_one_type_are_not_paired_by_guesswork(self):
        from app.invoices import audit

        old = [
            self._finding("invoice_possible_duplicate", "possible_deviation", "A"),
            self._finding("invoice_possible_duplicate", "possible_deviation", "B"),
        ]
        new = [self._finding("invoice_possible_duplicate", "possible_deviation", "C")]
        kinds = sorted(c.kind for c in audit.diff_findings(old, new))
        assert kinds == ["added", "removed", "removed"], (
            "två borttagna och en ny parades ihop till en påhittad ändring"
        )

    def test_a_disappearance_is_not_reported_as_a_dismissal(self):
        from app.invoices import audit

        old = self._finding("invoice_new_line", "cannot_be_verified", "ny rad")
        [change] = audit.diff_findings([old], [])
        assert change.kind == "removed"
        assert "inte att det är avfärdat" in change.summary


class TestHumanWork:
    def test_a_local_status_is_never_called_an_approval(self, worked):
        from app.invoices.models import REVIEW_STATUS_CAVEATS, REVIEW_STATUS_LABELS

        joined = " ".join(REVIEW_STATUS_LABELS.values()).lower()
        assert "godkänn" not in joined and "attest" not in joined
        assert "inte ett godkännande" in REVIEW_STATUS_CAVEATS["reviewed_no_objection"]

    def test_setting_a_status_writes_who_and_when(self, worked):
        case = case_ops.set_review_status(
            worked.store,
            worked.case.id,
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
                    worked.store, worked.case.id, status=status, note="  ", user_id="anna"
                )

    def test_a_comment_is_kept_apart_from_the_engine(self, worked):
        case = case_ops.comment(
            worked.store, worked.case.id, text="Ringde leverantören.", user_id="anna"
        )
        assert [c.note for c in case.comments()] == ["Ringde leverantören."]
        assert case.comments()[0].human is True
        assert all(not e.human for e in case.timeline if e.kind == "finding_recorded")

    def test_two_identical_comments_are_two_comments(self, worked):
        case_ops.comment(worked.store, worked.case.id, text="Påminde", user_id="anna")
        case = case_ops.comment(worked.store, worked.case.id, text="Påminde", user_id="anna")
        assert len(case.comments()) == 2

    def test_a_re_analysis_leaves_the_human_record_alone(self, worked):
        case = case_ops.set_review_status(
            worked.store,
            worked.case.id,
            status="needs_investigation",
            note="Fråga om taxan",
            user_id="anna",
        )
        case_ops.comment(worked.store, case.id, text="Avtalet mailat", user_id="bo")
        case_ops.assign(worked.store, case.id, responsible="Bo", user_id="anna")

        after = case_ops.analyse_case(worked.store, case.id)
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
        case = case_for(env, stored)
        assert case.source_status is not None
        assert case.source_status.booked is True
        assert case.source_status.label() == "Bokförd i ekonomisystemet"
        # And it is nowhere near the local one.
        assert case.review_status == "not_reviewed"

    def test_a_source_with_no_such_notion_gets_no_invented_status(self, integration_env):
        env = integration_env
        stored = env.integrations.upsert_invoice(snapshot())
        case = case_for(env, stored)
        assert case.source_status is None


class TestQueue:
    def test_an_overdue_case_is_only_overdue_while_it_is_open(self, integration_env):
        env = integration_env
        stored = env.integrations.upsert_invoice(snapshot(due_date="2026-01-01"))
        case = case_for(env, stored)
        assert case.overdue(TODAY) is True
        closed = case_ops.set_review_status(
            env.store, case.id, status="closed", note="", user_id="anna"
        )
        assert closed.overdue(TODAY) is False

    def test_date_signals_are_computed_not_stored(self, integration_env):
        env = integration_env
        stored = env.integrations.upsert_invoice(snapshot(due_date="2026-08-05"))
        case = case_for(env, stored)
        assert [s.kind for s in case.signals] == []
        assert "due_soon" in [s.kind for s in case.all_signals(TODAY)]

    def test_counts_are_computed_on_the_server(self, integration_env):
        env = integration_env
        env.import_invoice("SI-2026-114")
        rows = case_ops.project(env.store)
        counts = case_ops.totals(rows, TODAY)
        assert counts["total"] == 1 and counts["open"] == 1 and counts["unassigned"] == 1


class TestConcurrency:
    """What happens when two requests arrive at once.

    This class exists because an earlier version of the workspace projected
    cases *by writing them* on every read, with a ``uuid4`` id. Eight
    concurrent reads of four invoices produced **thirty-one** cases: the
    find-then-write was not atomic, and a random id meant the store's upsert
    could not collapse the duplicates afterwards. Both halves are asserted
    here, because either one alone would let it come back.
    """

    def _threads(self, work, count: int = 8) -> list[Exception]:
        import threading

        errors: list[Exception] = []

        def run() -> None:
            try:
                work()
            except Exception as exc:  # noqa: BLE001 - the point is to collect them
                errors.append(exc)

        threads = [threading.Thread(target=run) for _ in range(count)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        return errors

    def test_a_read_writes_nothing_at_all(self, integration_env):
        env = integration_env
        env.import_invoice("SI-2026-114")
        env.import_invoice("SI-2026-131")

        assert case_ops.project(env.store)  # there is something to see
        assert env.integrations.list_invoice_cases() == [], (
            "projicering är en läsning och ska inte skriva någonting"
        )

    def test_the_projection_is_the_same_answer_every_time(self, integration_env):
        env = integration_env
        env.import_invoice("SI-2026-114")
        first = [c.model_dump(mode="json") for c in case_ops.project(env.store)]
        second = [c.model_dump(mode="json") for c in case_ops.project(env.store)]
        # Ids, timestamps and machine timeline entries are all derived, so two
        # reads are byte-identical. An id or a clock read in here would make a
        # React key change under the reader on every refresh.
        assert first == second

    def test_concurrent_reads_create_no_cases(self, integration_env):
        env = integration_env
        for ref in ("SI-2026-114", "SI-2026-131", "SI-2026-207", "SI-2026-402"):
            env.import_invoice(ref)

        errors = self._threads(lambda: case_ops.project(env.store))
        assert errors == []
        assert env.integrations.list_invoice_cases() == []

    def test_concurrent_writes_converge_on_one_case(self, integration_env):
        env = integration_env
        env.import_invoice("SI-2026-114")
        case_id = case_ops.project(env.store)[0].id

        errors = self._threads(
            lambda: case_ops.comment(
                env.store, case_id, text="Ringde leverantören.", user_id="anna"
            )
        )
        assert errors == []
        rows = env.integrations.list_invoice_cases()
        assert len(rows) == 1, f"åtta samtidiga kommentarer gav {len(rows)} ärenden"
        assert rows[0].id == case_id
        # And not one of the eight was lost to a read-modify-write race.
        assert len(rows[0].comments()) == 8

    def test_the_id_is_derived_from_identity_not_minted(self, integration_env):
        env = integration_env
        env.import_invoice("SI-2026-114")
        case = case_ops.project(env.store)[0]
        assert case.id == case_ops.case_id_for(env.store.tenant_id, case.case_key)
        # Two associations that share a supplier and a number still get
        # different ids, so a lookup that forgot its tenant cannot cross over.
        assert case_ops.case_id_for("annan-brf", case.case_key) != case.id

    def test_a_case_is_written_the_first_time_somebody_acts(self, integration_env):
        env = integration_env
        env.import_invoice("SI-2026-114")
        case_id = case_ops.project(env.store)[0].id
        assert env.integrations.list_invoice_cases() == []

        case_ops.set_review_status(
            env.store, case_id, status="reviewed_no_objection", note="", user_id="anna"
        )
        stored = env.integrations.list_invoice_cases()
        assert [c.id for c in stored] == [case_id]
        # And the projection keeps reporting the human record it now carries.
        assert case_ops.project_one(env.store, case_id).review_status == "reviewed_no_objection"

    def test_a_changed_identity_does_not_orphan_the_review_notes(self, integration_env):
        """An invoice that gains a number changes its key — and its derived id.

        That is the one case the deterministic id makes awkward, so it is
        asserted rather than hoped for: the human record has to travel to the
        new identity, or a re-read would quietly strand somebody's
        investigation on a row nothing points at.
        """
        env = integration_env
        first = env.integrations.upsert_invoice(snapshot(number=None, external_ref="SI-9"))
        case = case_for(env, first)
        case_ops.set_review_status(
            env.store,
            case.id,
            status="needs_investigation",
            note="Saknar fakturanummer — fråga leverantören.",
            user_id="anna",
        )

        # The number turns up on a re-read. Same invoice, new identity.
        again = env.integrations.upsert_invoice(snapshot(number="2026-500", external_ref="SI-9"))
        assert again.id == first.id
        moved = case_for(env, again)
        assert moved is not None
        assert moved.id != case.id
        assert moved.review_status == "needs_investigation"
        assert moved.review_status_note == "Saknar fakturanummer — fråga leverantören."
        # And there is still exactly one case on screen, not the old one beside it.
        assert len(case_ops.project(env.store)) == 1

    def test_a_mutation_reads_the_version_on_disk_not_the_callers_copy(self, integration_env):
        env = integration_env
        env.import_invoice("SI-2026-114")
        case_id = case_ops.project(env.store)[0].id

        # A caller holds a stale copy from before somebody else commented…
        stale = case_ops.project_one(env.store, case_id)
        case_ops.comment(env.store, case_id, text="Först", user_id="bo")
        assert len(stale.comments()) == 0

        # …and writing through it must not drop what happened in between.
        case_ops.comment(env.store, case_id, text="Sedan", user_id="anna")
        notes = [c.note for c in case_ops.project_one(env.store, case_id).comments()]
        assert notes == ["Först", "Sedan"]


class TestSupplierMemory:
    def test_it_is_assembled_from_records_that_already_exist(self, integration_env):
        env = integration_env
        env.import_invoice("SI-2026-114")
        env.import_invoice("SI-2026-131")
        rows = case_ops.project(env.store)
        newest = max(rows, key=lambda c: c.invoice_date or "")
        context = case_ops.supplier_context(env.store, newest, TODAY)
        assert context["invoice_count"] == 2
        assert context["previous"] and context["previous"][0]["invoice_number"] == "2026-114"
        assert context["amount_low"] == "6250.00"
        assert context["org_numbers"] == ["556812-3344"]
