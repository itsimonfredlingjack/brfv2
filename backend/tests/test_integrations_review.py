"""What the review engine reads, what it refuses to read, and what it will not claim.

Three capabilities are asserted here, and each of them exists because the first
version of the engine got the case wrong in a way that looked right:

* **Supplier identity.** "Snösvängen AB" and "Snösvängen Entreprenad AB" are one
  company that two documents spell differently; "Svenska Hiss AB" and "Svenska
  Städ AB" are two companies that share a word. The engine must join the first
  pair and never the second, and must say how sure it is either way.
* **Terms that are not numbers.** An index-regulated price, an open-ended
  agreement, a duration counted from a signing date. Reading these is the
  difference between *kan inte verifieras* meaning "the contract is silent" and
  meaning "we could not read what it said".
* **What counts as evidence.** Material in the queue is what is being reviewed.
  It becomes evidence when a named person adopts it into the archive, and not
  before — and an invoice never corroborates itself even then.

Nothing here needs a credential, a network endpoint or a running model.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from app import terms
from app.integrations import supplier
from app.integrations.intake import AdoptionError, adopt_attachment, import_eml, withdraw_attachment
from app.integrations.models import SupplierAlias
from app.integrations.review import (
    evidence_excluded_document_ids,
    review_invoice,
    unadopted_incoming_document_ids,
)

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
MAIL = FIXTURES / "mail"

INVOICE_MATCHING = "SI-2026-114"
INVOICE_IN_CONTRACT_PERIOD = "SI-2026-402"
INVOICE_SHORT_NAME = "SI-2027-018"


def words(text: str) -> list[str]:
    return text.split()


# ---------------------------------------------------------------------------
# Supplier names
# ---------------------------------------------------------------------------


class TestSupplierNames:
    def test_a_legal_form_is_stripped_from_the_end_only(self):
        assert supplier.core_tokens("Snösvängen Entreprenad AB") == ["snösvängen", "entreprenad"]
        assert supplier.core_tokens("Bygg & Co Handelsbolag") == ["bygg", "&", "co"]
        # A name that *begins* with AB is using it as a name.
        assert supplier.core_tokens("AB Svenska Bostäder") == ["ab", "svenska", "bostäder"]

    def test_swedish_letters_survive_normalisation(self):
        assert supplier.normalize("Snösvängen AB") == "snösvängen"
        # …while an accent that is decoration does not.
        assert supplier.normalize("Café Sundberg AB") == "cafe sundberg"

    def test_an_organisation_number_is_one_number_however_it_is_written(self):
        assert supplier.normalize_org_number("556812-3344") == "5568123344"
        assert supplier.normalize_org_number("5568123344") == "5568123344"
        assert supplier.normalize_org_number("16556812-3344") == "5568123344"
        assert supplier.normalize_org_number("12345") == ""

    def test_the_needle_list_is_ordered_strongest_first(self):
        needles = supplier.needles_for(
            "Snösvängen Entreprenad AB",
            org_number="556812-3344",
            aliases=[("Snösvängen", "u-1")],
        )
        strengths = [n.strength for n in needles]
        assert strengths[0] == "org_number"
        assert "exact" in strengths and "alias" in strengths
        assert supplier.strength_rank("org_number") < supplier.strength_rank("partial")

    def test_a_generic_first_token_cannot_carry_a_partial_match_alone(self):
        """"Svenska Hiss AB" must not anchor on "Svenska"."""
        partials = [
            n for n in supplier.needles_for("Svenska Hiss AB") if n.strength == "partial"
        ]
        assert all(len(n.tokens) >= 2 for n in partials), [n.tokens for n in partials]

    def test_a_distinctive_first_token_may_carry_one(self):
        partials = [
            n for n in supplier.needles_for("Snösvängen Entreprenad AB")
            if n.strength == "partial"
        ]
        assert ("snösvängen",) in {n.tokens for n in partials}

    def test_a_name_does_not_continue_past_its_own_sentence(self):
        """"…Snösvängen AB. Entreprenören ska…" is a name, then a new sentence."""
        from app.integrations.review import _full_name_at

        written, is_prefix = _full_name_at(
            "avtal med Snösvängen AB. Entreprenören ska utföra".split(), 2, 1
        )
        assert written == "Snösvängen AB"
        assert is_prefix is False

    def test_a_longer_name_in_the_document_is_seen_as_longer(self):
        from app.integrations.review import _full_name_at

        written, is_prefix = _full_name_at(
            "och Snösvängen Entreprenad AB, org.nr 556812-3344,".split(), 1, 1
        )
        assert written == "Snösvängen Entreprenad AB"
        assert is_prefix is True

    def test_names_differ_is_about_the_company_not_the_spelling(self):
        assert not supplier.names_differ("Snösvängen AB", "Snösvängen")
        assert supplier.names_differ("Snösvängen AB", "Snösvängen Entreprenad AB")


# ---------------------------------------------------------------------------
# Terms
# ---------------------------------------------------------------------------


class TestSwedishDates:
    def test_a_long_form_date_is_read(self):
        hits = terms.scan_dates(words("Avtalet gäller från den 1 november 2026 och tills vidare."))
        assert [h.iso for h in hits] == ["2026-11-01"]

    def test_a_date_without_a_year_is_not_guessed(self):
        """The snow contract's "från den 15 november till den 15 april" has no year."""
        assert terms.scan_dates(words("Jourperioden löper från den 15 november till den 15 april")) == []

    def test_an_impossible_date_is_not_a_date(self):
        assert terms.scan_dates(words("den 31 februari 2026")) == []

    def test_iso_and_swedish_are_both_read(self):
        hits = terms.scan_dates(words("perioden 2026-01-01 till den 31 mars 2026"))
        assert [h.iso for h in hits] == ["2026-01-01", "2026-03-31"]


class TestPeriods:
    def test_an_open_ended_period_has_a_start_and_no_end(self):
        (period,) = terms.scan_periods(
            words("Avtalet gäller från den 1 november 2026 och tills vidare.")
        )
        assert period.start_iso == "2026-11-01"
        assert period.end_iso is None and period.open_ended
        assert period.covers("2026-12-01", "2026-12-31")
        assert not period.covers("2026-01-01", "2026-01-31")
        assert period.human() == "2026-11-01 och tills vidare"

    def test_a_closed_period_is_bounded_at_both_ends(self):
        (period,) = terms.scan_periods(words("Avtalet gäller från 2026-01-01 – 2026-12-31."))
        assert (period.start_iso, period.end_iso) == ("2026-01-01", "2026-12-31")
        assert not period.open_ended
        assert period.covers("2026-03-01", "2026-03-31")
        assert not period.covers("2026-12-01", "2027-01-31")

    def test_two_dates_in_an_invoice_header_are_not_a_period(self):
        """The rule that stopped the engine inventing "2026-02-03 – 2026-03-05"."""
        assert terms.scan_periods(words("Fakturadatum: 2026-02-03 Förfallodatum: 2026-03-05")) == []


class TestDurationsAndNotice:
    def test_a_duration_written_twice_is_one_duration(self):
        (duration,) = terms.scan_durations(
            words("Avtalstiden är tolv (12) månader från undertecknande.")
        )
        assert (duration.count, duration.unit, duration.anchor) == (12, "month", "undertecknande")
        assert duration.human() == "12 månader från undertecknande"

    def test_a_notice_period_is_read_from_either_side_of_the_word(self):
        found = terms.scan_notice_periods(words("Uppsägningstiden är tre månader."))
        assert (found[0].count, found[0].unit) == (3, "month")
        found = terms.scan_notice_periods(
            words("Uppsägning skall ske skriftligen senast tre månader före avtalstidens utgång")
        )
        assert found and found[0].count == 3


class TestIndexClauses:
    def test_a_named_index_is_recorded(self):
        (clause,) = terms.scan_index_clauses(
            words("Priserna indexregleras årligen enligt SCB:s entreprenadindex E84.")
        )
        assert clause.basis == "entreprenadindex"
        assert "indexreglerat pris" in clause.human()

    def test_kpi_is_recognised_by_either_name(self):
        assert terms.scan_index_clauses(words("Ersättningen justeras enligt KPI."))[0].basis == "KPI"
        assert (
            terms.scan_index_clauses(words("Ersättningen följer konsumentprisindex."))[0].basis
            == "KPI"
        )

    def test_an_ordinary_price_paragraph_has_no_index_clause(self):
        assert terms.scan_index_clauses(words("Ersättning utgår med 12 500 kronor per månad.")) == []


# ---------------------------------------------------------------------------
# The engine, against the seeded corpus
# ---------------------------------------------------------------------------


class TestAnchoring:
    def test_the_organisation_number_is_the_strongest_anchor(self, integration_env):
        """The seeded contract carries "org.nr 556812-3344", and so does the invoice."""
        env = integration_env
        invoice = env.import_invoice(INVOICE_MATCHING)
        findings = review_invoice(env.store, invoice)
        assert {f.anchor_strength for f in findings} == {"org_number"}
        assert all("entydigt" in (f.anchor_note or "") for f in findings)
        assert all(f.alias_proposal is None for f in findings)

    def test_a_shorter_supplier_name_still_anchors_but_weakly_and_asks(self, integration_env):
        """"Snösvängen AB" against a contract that says "Snösvängen Entreprenad AB"."""
        env = integration_env
        invoice = env.import_invoice(INVOICE_SHORT_NAME)
        findings = review_invoice(env.store, invoice)
        assert findings, "en svag koppling ska ge ett fynd, inte tystnad"
        weak = findings[0]
        assert weak.anchor_strength == "partial"
        assert weak.alias_proposal is not None
        assert weak.alias_proposal.invoice_name == "Snösvängen AB"
        assert "Snösvängen" in weak.alias_proposal.document_name
        # And every finding it produced admits the names are not identical.
        assert all("inte bekräftad" in (f.uncertainty or "") for f in findings)

    def test_a_confirmed_alias_makes_the_same_anchor_strong(self, integration_env):
        env = integration_env
        invoice = env.import_invoice(INVOICE_SHORT_NAME)
        proposal = review_invoice(env.store, invoice)[0].alias_proposal
        env.store.integrations.add_supplier_alias(
            SupplierAlias(
                id="a1",
                tenant_id=env.brf_id,
                invoice_name=proposal.invoice_name,
                document_name=proposal.document_name,
                normalized_key=supplier.normalize(proposal.invoice_name),
                created_by="ordforande",
                note="Samma bolag, namnbyte 2026.",
            )
        )
        again = review_invoice(env.store, invoice)
        assert {f.anchor_strength for f in again} == {"alias"}
        assert all("bekräftat" in (f.anchor_note or "") for f in again)
        assert all("inte bekräftad" not in (f.uncertainty or "") for f in again)

    def test_an_alias_belongs_to_one_supplier_and_one_tenant(self, integration_env):
        env = integration_env
        env.store.integrations.add_supplier_alias(
            SupplierAlias(
                id="a1",
                tenant_id=env.brf_id,
                invoice_name="Snösvängen AB",
                document_name="Snösvängen Entreprenad AB",
                normalized_key=supplier.normalize("Snösvängen AB"),
                created_by="u",
            )
        )
        assert env.store.integrations.aliases_for("Snösvängen AB")
        assert env.store.integrations.aliases_for("Nordisk Hissteknik AB") == []
        other = env.registry.get("sjoutsikten-7")
        assert other is not None
        assert other.integrations.list_supplier_aliases() == []

    def test_the_same_alias_twice_is_one_alias(self, integration_env):
        env = integration_env

        def add(alias_id: str):
            return env.store.integrations.add_supplier_alias(
                SupplierAlias(
                    id=alias_id,
                    tenant_id=env.brf_id,
                    invoice_name="Snösvängen AB",
                    document_name="Snösvängen Entreprenad AB",
                    normalized_key=supplier.normalize("Snösvängen AB"),
                    created_by="u",
                )
            )

        first = add("a1")
        assert add("a2").id == first.id
        assert len(env.store.integrations.list_supplier_aliases()) == 1


class TestPeriodReview:
    def test_an_invoice_inside_an_open_ended_agreement_matches(self, integration_env):
        env = integration_env
        invoice = env.import_invoice(INVOICE_IN_CONTRACT_PERIOD)
        period = next(
            f for f in review_invoice(env.store, invoice)
            if f.finding_type == "invoice_contract_period"
        )
        assert period.verdict == "matches"
        assert "tills vidare" in period.suggestion

    def test_an_invoice_before_the_agreement_is_a_possible_deviation(self, integration_env):
        env = integration_env
        invoice = env.import_invoice(INVOICE_MATCHING)
        period = next(
            f for f in review_invoice(env.store, invoice)
            if f.finding_type == "invoice_contract_period"
        )
        assert period.verdict == "possible_deviation"
        assert "2026-11-01" in period.suggestion


class TestIndexRegulatedPrices:
    """A contract that says the price follows an index cannot yield a deviation."""

    def _contract_with_index(self, env, lines: list[str]) -> str:
        import sys

        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from scripts.make_integration_fixtures import _invoice_pdf

        meta = env.store.add_document("Städavtal 2026.pdf", _invoice_pdf(lines))
        return meta.id

    def test_a_differing_base_amount_under_an_index_clause_is_not_a_deviation(
        self, integration_env
    ):
        env = integration_env
        self._contract_with_index(
            env,
            [
                "Städavtal 2026",
                "Mellan Bostadsrattsforeningen Gjutformen 12 och Stadbolaget Ren AB,",
                "org.nr 556900-1122, har traffats foljande avtal.",
                "Ersattning utgar med 9 000 kronor per manad.",
                "Priserna indexregleras arligen enligt SCB:s entreprenadindex E84.",
            ],
        )
        invoice = env.store.integrations.upsert_invoice(
            _snapshot(env.brf_id, "Stadbolaget Ren AB", Decimal("12500.00"), Decimal("2500.00"))
        )
        amount = next(
            f for f in review_invoice(env.store, invoice)
            if f.finding_type in ("invoice_contract_amount", "contract_term_not_comparable")
        )
        assert amount.verdict == "cannot_be_verified"
        assert amount.finding_type == "contract_term_not_comparable"
        assert "indexreglerat" in amount.suggestion
        # Both the amount and the index clause are cited, because a reviewer
        # has to be able to read the clause that disqualified the comparison.
        assert len(amount.citations) >= 3
        assert any(
            f.label == "Prisvillkoret är indexreglerat" for f in amount.verified_facts
        )

    def test_without_the_index_clause_the_same_numbers_are_a_possible_deviation(
        self, integration_env
    ):
        env = integration_env
        self._contract_with_index(
            env,
            [
                "Stadavtal 2026",
                "Mellan Bostadsrattsforeningen Gjutformen 12 och Stadbolaget Ren AB,",
                "org.nr 556900-1122, har traffats foljande avtal.",
                "Ersattning utgar med 9 000 kronor per manad.",
                "Fakturering sker manadsvis i efterskott.",
            ],
        )
        invoice = env.store.integrations.upsert_invoice(
            _snapshot(env.brf_id, "Stadbolaget Ren AB", Decimal("12500.00"), Decimal("2500.00"))
        )
        amount = next(
            f for f in review_invoice(env.store, invoice)
            if f.finding_type == "invoice_contract_amount"
        )
        assert amount.verdict == "possible_deviation"


def _snapshot(tenant_id: str, supplier_name: str, total, vat):
    from app.integrations.models import InvoiceSnapshot, utc_now_iso

    return InvoiceSnapshot(
        id="inv-test",
        tenant_id=tenant_id,
        adapter="fixture-accounting",
        external_ref="TEST-1",
        supplier_name=supplier_name,
        supplier_ref="556900-1122",
        invoice_date="2026-03-01",
        period_start="2026-02-01",
        period_end="2026-02-28",
        total_amount=total,
        vat_amount=vat,
        currency="SEK",
        retrieved_at=utc_now_iso(),
        source_dataset="test",
        content_sha256="0" * 64,
    )


# ---------------------------------------------------------------------------
# Adoption into the archive
# ---------------------------------------------------------------------------


class TestAdoption:
    def _event(self, env):
        return import_eml(
            store=env.store,
            integrations=env.integrations,
            raw=(MAIL / "faktura-snosvangen-2026-02.eml").read_bytes(),
            filename="f.eml",
            imported_by="u",
        )

    def test_an_attachment_is_not_evidence_until_someone_adopts_it(self, integration_env):
        env = integration_env
        event = self._event(env)
        document_id = event.attachments[0].document_id
        assert document_id in unadopted_incoming_document_ids(env.store)

        adopted = adopt_attachment(
            store=env.store,
            integrations=env.integrations,
            event_id=event.id,
            attachment_id=event.attachments[0].id,
            user_id="ordforande",
            note="Undertecknat avtal, samma som pärmen.",
        )
        attachment = adopted.attachments[0]
        assert attachment.archived is True
        assert attachment.archived_by == "ordforande"
        assert attachment.archived_at
        assert attachment.archive_note == "Undertecknat avtal, samma som pärmen."
        assert document_id not in unadopted_incoming_document_ids(env.store)

    def test_adoption_without_a_stated_reason_is_refused(self, integration_env):
        env = integration_env
        event = self._event(env)
        with pytest.raises(AdoptionError) as exc:
            adopt_attachment(
                store=env.store,
                integrations=env.integrations,
                event_id=event.id,
                attachment_id=event.attachments[0].id,
                user_id="u",
                note="   ",
            )
        assert "varför" in str(exc.value)

    def test_adoption_is_reversible_and_the_document_stays(self, integration_env):
        env = integration_env
        event = self._event(env)
        document_id = event.attachments[0].document_id
        adopt_attachment(
            store=env.store,
            integrations=env.integrations,
            event_id=event.id,
            attachment_id=event.attachments[0].id,
            user_id="u",
            note="skäl",
        )
        withdrawn = withdraw_attachment(
            integrations=env.integrations,
            event_id=event.id,
            attachment_id=event.attachments[0].id,
        )
        assert withdrawn.attachments[0].archived is False
        assert withdrawn.attachments[0].archived_by is None
        assert env.store.get_pdf_bytes(document_id) is not None

    def test_an_adopted_invoice_still_never_corroborates_itself(self, integration_env):
        """Adoption widens the archive. It does not let a paper prove itself."""
        env = integration_env
        event = self._event(env)
        adopt_attachment(
            store=env.store,
            integrations=env.integrations,
            event_id=event.id,
            attachment_id=event.attachments[0].id,
            user_id="u",
            note="arkiverad av misstag, men ändå",
        )
        document_id = event.attachments[0].document_id
        invoice = env.import_invoice(INVOICE_MATCHING)
        invoice = env.store.integrations.upsert_invoice(
            invoice.model_copy(update={"source_event_id": event.id})
        )
        assert document_id in evidence_excluded_document_ids(env.store, invoice)
        for finding in review_invoice(env.store, invoice):
            for citation in finding.citations:
                assert citation.document_id != document_id

    def test_an_adopted_contract_from_another_message_may_be_cited(self, integration_env):
        """The point of adoption: a contract that arrived by mail becomes usable."""
        env = integration_env
        event = self._event(env)
        document_id = event.attachments[0].document_id
        adopt_attachment(
            store=env.store,
            integrations=env.integrations,
            event_id=event.id,
            attachment_id=event.attachments[0].id,
            user_id="u",
            note="Föreningens exemplar.",
        )
        # A different invoice, with no source event of its own.
        invoice = env.import_invoice(INVOICE_MATCHING)
        assert document_id not in evidence_excluded_document_ids(env.store, invoice)

    def test_an_unknown_attachment_is_a_clean_refusal(self, integration_env):
        env = integration_env
        event = self._event(env)
        with pytest.raises(AdoptionError):
            adopt_attachment(
                store=env.store,
                integrations=env.integrations,
                event_id=event.id,
                attachment_id="finns-inte",
                user_id="u",
                note="skäl",
            )
