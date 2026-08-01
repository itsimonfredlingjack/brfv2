"""The integration block's security boundary and its honesty about doubt.

Two things are asserted here that are easy to state and easy to lose:

* one tenant cannot see another's source events, invoices, findings or the
  documents that arrived with them;
* a finding never says more than what verified verbatim.

Nothing in this file needs a credential, a network endpoint or a running model.
That is itself part of what is being asserted — a test suite that needed one
would mean the code path did too.
"""

from __future__ import annotations

import inspect
import json
import typing
from decimal import Decimal
from pathlib import Path

import pytest

from app.integrations import protocols
from app.integrations.accounting_fixture import FixtureAccountingAdapter, FixtureError
from app.integrations.eml import (
    ACCEPTED_ATTACHMENT_TYPES,
    MAX_ATTACHMENTS,
    EmlRejected,
    accepted_format,
    parse_eml,
)
from app.integrations.intake import DuplicateSourceEvent, import_eml
from app.integrations.models import VERDICT_LABELS, SourceEvent
from app.integrations.protocols import (
    FORBIDDEN_METHOD_STEMS,
    ReadOnlyAdapterError,
    assert_read_only,
)
from app.integrations.review import (
    amount_unit,
    incoming_document_ids,
    review_invoice,
    scan_amounts,
    scan_iso_periods,
)
from app.integrations.store import IntegrationError, IntegrationStore

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
MAIL = FIXTURES / "mail"

INVOICE_MATCHING = "SI-2026-114"
INVOICE_DEVIATING = "SI-2026-131"
INVOICE_NO_CONTRACT = "SI-2026-207"
# Inside the seeded agreement's open-ended period.
INVOICE_IN_CONTRACT_PERIOD = "SI-2026-402"
# Same supplier, written without "Entreprenad" and with no organisation number:
# the case where the anchor is weak and wants a human to confirm an alias.
INVOICE_SHORT_NAME = "SI-2027-018"


# ---------------------------------------------------------------------------
# Adapter boundaries
# ---------------------------------------------------------------------------


class TestAdaptersCannotWrite:
    def test_every_protocol_in_the_module_is_checked(self):
        """The enforcement has exactly one hole — a protocol nobody passed to
        assert_read_only. This closes it."""
        declared = [
            obj
            for name, obj in vars(protocols).items()
            if isinstance(obj, type)
            and issubclass(obj, typing.Protocol)  # type: ignore[arg-type]
            and obj is not typing.Protocol
            and obj.__module__ == protocols.__name__
        ]
        assert declared, "inga protokoll hittades — testet skyddar ingenting"
        for protocol in declared:
            # Re-running the check is the assertion: it raised at import time if
            # it was going to, so this proves the check *applies* to each one.
            assert assert_read_only(protocol) is protocol

    @pytest.mark.parametrize("verb", ["send", "archive", "update", "approve", "attest", "pay", "post", "book"])
    def test_a_writing_verb_is_refused(self, verb):
        namespace = {"__module__": "test", "__qualname__": "Sneaky"}
        namespace[f"{verb}_something"] = lambda self: None
        sneaky = type("Sneaky", (typing.Protocol,), namespace)
        with pytest.raises(ReadOnlyAdapterError) as exc:
            assert_read_only(sneaky)
        assert verb in str(exc.value)

    def test_the_forbidden_list_covers_the_verbs_the_brief_names(self):
        for verb in ("send", "archive", "update", "approve", "attest", "post", "book", "pay"):
            assert verb in FORBIDDEN_METHOD_STEMS

    def test_reading_verbs_are_allowed(self):
        namespace = {"__module__": "test", "__qualname__": "Fine"}
        for name in ("list_invoices", "get_invoice", "parse_message", "fetch_page", "read_all"):
            namespace[name] = lambda self: None
        fine = type("Fine", (typing.Protocol,), namespace)
        assert assert_read_only(fine) is fine

    def test_the_shipped_adapters_satisfy_their_protocols(self):
        from app.integrations.eml import EmlFileAdapter

        assert isinstance(EmlFileAdapter(), protocols.MailImportAdapter)
        assert isinstance(FixtureAccountingAdapter(), protocols.AccountingReadAdapter)

    def test_no_adapter_source_opens_a_network_connection(self):
        """Names are a tripwire; this is the check on behaviour.

        The read-only *protocol* check matches on method names, which a method
        called `fetch` that POSTs would pass. Neither shipped adapter imports a
        client library or references a URL scheme at all, so there is nothing
        for such a method to call.
        """
        import app.integrations.accounting_fixture as fixture_mod
        import app.integrations.eml as eml_mod

        for module in (fixture_mod, eml_mod):
            source = inspect.getsource(module)
            for forbidden in ("httpx", "requests", "urllib.request", "socket.", "http://", "https://"):
                assert forbidden not in source, f"{module.__name__} nämner {forbidden}"


# ---------------------------------------------------------------------------
# The accepted .eml format, and refusal of everything else
# ---------------------------------------------------------------------------


class TestEmlFormat:
    def test_the_served_format_matches_the_code(self):
        fmt = accepted_format()
        assert fmt["attachmentTypes"] == list(ACCEPTED_ATTACHMENT_TYPES)
        assert fmt["maxAttachments"] == MAX_ATTACHMENTS
        codes = {row["code"] for row in fmt["rejections"]}
        assert {"too_large", "unsupported_attachment", "missing_header", "not_a_pdf"} <= codes

    def test_the_ordinary_fixture_parses(self):
        message = parse_eml((MAIL / "faktura-snosvangen-2026-02.eml").read_bytes())
        assert message.sender == "faktura@snosvangen.example"
        assert message.subject.startswith("Faktura 2026-114")
        assert message.sent_at == "2026-02-03T08:14:00+01:00"
        assert [a.filename for a in message.attachments] == ["faktura-2026-114.pdf"]
        assert message.attachments[0].data.startswith(b"%PDF-")

    def test_a_message_with_no_attachment_is_accepted(self):
        message = parse_eml((MAIL / "fraga-fran-medlem.eml").read_bytes())
        assert message.attachments == []
        assert "jouren" in message.body_text

    def test_a_non_pdf_attachment_refuses_the_whole_message(self):
        with pytest.raises(EmlRejected) as exc:
            parse_eml((MAIL / "underlag-i-kalkylblad.eml").read_bytes())
        assert exc.value.code == "unsupported_attachment"

    @pytest.mark.parametrize(
        "raw,code",
        [
            (b"", "empty"),
            (b"inte ett mejl alls", "missing_header"),
            (b"From: a@b.example\r\n\r\nkropp\r\n", "missing_header"),
        ],
    )
    def test_malformed_input_is_refused_with_a_stable_code(self, raw, code):
        with pytest.raises(EmlRejected) as exc:
            parse_eml(raw)
        assert exc.value.code == code

    def test_an_oversized_message_is_refused_before_parsing(self):
        with pytest.raises(EmlRejected) as exc:
            parse_eml(b"x" * (25 * 1024 * 1024 + 1))
        assert exc.value.code == "too_large"

    def test_an_attachment_that_lies_about_being_a_pdf_is_refused(self):
        from email.message import EmailMessage

        msg = EmailMessage()
        msg["From"] = "a@b.example"
        msg["Subject"] = "Falsk PDF"
        msg.set_content("kropp")
        msg.add_attachment(b"MZ\x90\x00 inte en pdf", maintype="application", subtype="pdf", filename="x.pdf")
        with pytest.raises(EmlRejected) as exc:
            parse_eml(msg.as_bytes())
        assert exc.value.code == "not_a_pdf"

    def test_html_only_body_is_reduced_to_text(self):
        from email.message import EmailMessage

        msg = EmailMessage()
        msg["From"] = "a@b.example"
        msg["Subject"] = "HTML"
        msg.set_content(
            "<html><style>p{color:red}</style><body><p>Rad ett</p><p>Rad tv&aring;</p>"
            "<script>alert(1)</script></body></html>",
            subtype="html",
        )
        message = parse_eml(msg.as_bytes())
        assert "Rad ett" in message.body_text
        assert "Rad två" in message.body_text
        assert "alert" not in message.body_text
        assert "<p>" not in message.body_text


# ---------------------------------------------------------------------------
# Import: atomic, deduplicated, provenance-preserving
# ---------------------------------------------------------------------------


class TestImport:
    def test_import_preserves_hash_provenance_and_ingests_the_attachment(self, integration_env):
        env = integration_env
        raw = (MAIL / "faktura-snosvangen-2026-02.eml").read_bytes()
        event = import_eml(
            store=env.store,
            integrations=env.integrations,
            raw=raw,
            filename="faktura-snosvangen-2026-02.eml",
            imported_by="operator-1",
        )

        import hashlib

        assert event.content_sha256 == hashlib.sha256(raw).hexdigest()
        assert event.tenant_id == env.brf_id
        assert event.provenance.origin_filename == "faktura-snosvangen-2026-02.eml"
        assert event.provenance.origin_bytes == len(raw)
        assert event.provenance.imported_by == "operator-1"
        assert event.external_ref == "<snosvangen114@fixture.invalid>"
        assert event.occurred_at == "2026-02-03T08:14:00+01:00"
        assert event.import_status == "imported"
        assert event.review_status == "open"

        (attachment,) = event.attachments
        assert attachment.ingested and attachment.document_id
        # The attachment is a document of this tenant's, through the ordinary
        # ingestion path — not a second copy in a second place.
        assert attachment.document_id in env.store.documents
        assert env.store.get_pdf_bytes(attachment.document_id) is not None

    def test_the_same_bytes_twice_is_one_event_and_one_document(self, integration_env):
        env = integration_env
        raw = (MAIL / "faktura-snosvangen-2026-02.eml").read_bytes()
        first = import_eml(
            store=env.store, integrations=env.integrations, raw=raw,
            filename="a.eml", imported_by="u",
        )
        documents_after_first = set(env.store.documents)

        with pytest.raises(DuplicateSourceEvent) as exc:
            import_eml(
                store=env.store, integrations=env.integrations, raw=raw,
                filename="kopia.eml", imported_by="u",
            )
        assert exc.value.existing.id == first.id
        assert set(env.store.documents) == documents_after_first
        assert len(env.integrations.list_source_events()) == 1

    def test_a_refused_message_leaves_no_residue(self, integration_env):
        env = integration_env
        before_documents = set(env.store.documents)
        with pytest.raises(EmlRejected):
            import_eml(
                store=env.store,
                integrations=env.integrations,
                raw=(MAIL / "underlag-i-kalkylblad.eml").read_bytes(),
                filename="underlag-i-kalkylblad.eml",
                imported_by="u",
            )
        assert set(env.store.documents) == before_documents
        assert env.integrations.list_source_events() == []

    def test_a_failing_attachment_rolls_back_every_document_already_added(
        self, integration_env, monkeypatch
    ):
        """The half-import this whole module is arranged to prevent."""
        env = integration_env
        from email.message import EmailMessage

        first_pdf = parse_eml((MAIL / "faktura-snosvangen-2026-02.eml").read_bytes()).attachments[0].data
        # A DIFFERENT second PDF: identical bytes would be deduplicated to the
        # first document and never reach add_document a second time, so the
        # rollback would not be exercised at all.
        second_pdf = parse_eml(
            (MAIL / "faktura-snosvangen-2026-03-hojd-taxa.eml").read_bytes()
        ).attachments[0].data
        assert first_pdf != second_pdf

        msg = EmailMessage()
        msg["From"] = "a@b.example"
        msg["Subject"] = "Två bilagor"
        msg.set_content("kropp")
        msg.add_attachment(first_pdf, maintype="application", subtype="pdf", filename="ett.pdf")
        msg.add_attachment(second_pdf, maintype="application", subtype="pdf", filename="tva.pdf")

        real_add = env.store.add_document
        calls = {"n": 0}

        def explode(name, data):
            calls["n"] += 1
            if calls["n"] == 2:
                raise ValueError("andra bilagan går inte att läsa")
            return real_add(name, data)

        monkeypatch.setattr(env.store, "add_document", explode)
        before = set(env.store.documents)
        with pytest.raises(EmlRejected):
            import_eml(
                store=env.store, integrations=env.integrations, raw=msg.as_bytes(),
                filename="tva-bilagor.eml", imported_by="u",
            )
        assert calls["n"] == 2
        # The first attachment WAS ingested and then removed again.
        assert set(env.store.documents) == before
        assert env.integrations.list_source_events() == []

    def test_documents_are_suggested_not_linked(self, integration_env):
        env = integration_env
        event = import_eml(
            store=env.store,
            integrations=env.integrations,
            raw=(MAIL / "faktura-snosvangen-2026-02.eml").read_bytes(),
            filename="f.eml",
            imported_by="u",
        )
        assert event.linked_document_ids == []
        assert event.suggested_document_ids
        names = {env.store.documents[d].name for d in event.suggested_document_ids}
        assert "Snöröjningsavtal 2026.pdf" in names


# ---------------------------------------------------------------------------
# Read-only accounting adapter
# ---------------------------------------------------------------------------


class TestAccountingAdapter:
    def test_it_lists_and_maps_without_a_credential(self, integration_env):
        adapter = FixtureAccountingAdapter()
        rows = adapter.list_invoices(integration_env.brf_id)
        assert {r["external_ref"] for r in rows} >= {
            INVOICE_MATCHING, INVOICE_DEVIATING, INVOICE_NO_CONTRACT
        }
        snapshot = adapter.get_invoice(integration_env.brf_id, INVOICE_MATCHING)
        assert snapshot.supplier_name == "Snösvängen Entreprenad AB"
        assert snapshot.total_amount == Decimal("6250.00")
        assert snapshot.vat_amount == Decimal("1250.00")
        assert snapshot.lines[0].unit_price == Decimal("1250.00")
        assert snapshot.period_start == "2026-01-01"
        assert snapshot.content_sha256

    def test_amounts_survive_as_decimals_through_json(self, integration_env):
        adapter = FixtureAccountingAdapter()
        snapshot = adapter.get_invoice(integration_env.brf_id, INVOICE_MATCHING)
        payload = snapshot.model_dump(mode="json")
        # A string, not a float: 6250.00 must not become 6249.999999999999.
        assert payload["total_amount"] == "6250.00"
        assert isinstance(payload["total_amount"], str)

    def test_another_tenants_reference_is_not_found(self, integration_env):
        adapter = FixtureAccountingAdapter()
        with pytest.raises(LookupError):
            adapter.get_invoice("nagon-annan-forening", INVOICE_MATCHING)

    def test_a_fixture_without_the_schema_marker_is_refused(self, tmp_path):
        (tmp_path / "x.json").write_text(json.dumps({"SupplierInvoices": []}), encoding="utf-8")
        with pytest.raises(FixtureError):
            FixtureAccountingAdapter(tmp_path).list_invoices("x")

    def test_the_core_domain_names_no_vendor(self):
        """A vendor may exist in an adapter or in the wiring. Not in the domain.

        The line moved when the live integrations arrived, and it is worth
        saying where it now runs. ``egress.py`` has to name the hosts it will
        talk to, ``credentials.py`` the providers it stores tokens for, and
        ``routes.py`` the adapters it wires — naming them is what those modules
        are *for*, and a policy that could not say "api.fortnox.se" would not
        be a policy.

        What must stay vendor-free is the part that decides things: the record
        types, their persistence, the adapter contract, the importer and the
        review engine. A verdict must never depend on who supplied the invoice.
        """
        package = Path(__file__).resolve().parent.parent / "app" / "integrations"
        domain = [
            "models.py",
            "store.py",
            "protocols.py",
            "review.py",
            "intake.py",
            "terms.py",
            "supplier.py",
        ]
        for name in domain:
            text = (package / name).read_text(encoding="utf-8").lower()
            for vendor in ("fortnox", "outlook", "graph.microsoft", "msgraph"):
                assert vendor not in text, f"{name} nämner {vendor}"

    def test_no_domain_record_has_a_field_named_after_a_vendor(self):
        """The stronger version of the same rule, over the types themselves."""
        from app.integrations.credentials import Connection
        from app.integrations.models import (
            InvoiceSnapshot,
            ReviewFinding,
            SourceEvent,
            SupplierAlias,
        )

        for model in (SourceEvent, InvoiceSnapshot, ReviewFinding, SupplierAlias, Connection):
            for field in model.model_fields:
                lowered = field.lower()
                for vendor in ("fortnox", "outlook", "graph", "microsoft", "msgraph"):
                    assert vendor not in lowered, f"{model.__name__}.{field}"


# ---------------------------------------------------------------------------
# Value extraction
# ---------------------------------------------------------------------------


class TestValueExtraction:
    def test_swedish_thousands_grouping_is_reassembled(self):
        words = "Ersättning uppgår till 12 500 kronor per månad".split()
        found = scan_amounts(words)
        assert [value for *_, value in found] == [Decimal("12500")]
        start, end, _ = found[0]
        assert amount_unit(words, end) == "periodic"

    def test_an_hourly_rate_is_a_rate(self):
        words = "traktor 1 250 kronor per timme, manuell".split()
        (start, end, value), = scan_amounts(words)
        assert value == Decimal("1250")
        assert amount_unit(words, end) == "rate"

    def test_a_year_is_not_an_amount(self):
        """The maintenance plan's 'År 2030' sits right after '850 000 kronor.'"""
        words = "kostnad av 850 000 kronor. År 2030 utförs omputsning".split()
        assert [value for *_, value in scan_amounts(words)] == [Decimal("850000")]

    def test_a_plain_number_without_a_currency_is_not_an_amount(self):
        assert scan_amounts("max 400 sidor per dokument".split()) == []

    def test_a_period_needs_a_period_word(self):
        assert scan_iso_periods("Fakturadatum: 2026-02-03 Förfallodatum: 2026-03-05".split()) == []
        found = scan_iso_periods("Avtalet gäller perioden 2026-01-01 – 2026-12-31 och".split())
        assert [(a, b) for *_, a, b in found] == [("2026-01-01", "2026-12-31")]


# ---------------------------------------------------------------------------
# The review itself
# ---------------------------------------------------------------------------


class TestReview:
    def test_a_matching_rate_is_reported_as_matching_with_an_exact_citation(self, integration_env):
        env = integration_env
        invoice = env.import_invoice(INVOICE_MATCHING)
        findings = review_invoice(env.store, invoice)
        amount = next(f for f in findings if f.finding_type == "invoice_contract_amount")

        assert amount.verdict == "matches"
        assert amount.verdict_label == VERDICT_LABELS["matches"] == "överensstämmer"
        assert amount.suggested_by == "regelmotor"

        cited = [c for c in amount.citations if "1 250" in c.quote]
        assert cited, "beloppet måste citeras ordagrant"
        citation = cited[0]
        assert citation.document_name == "Snöröjningsavtal 2026.pdf"
        assert citation.page == 2
        assert citation.rects, "ett citat utan rektanglar går inte att peka på"

        # The quote is verbatim in the document it claims to be in.
        page_words = [w.text for w in env.store.pages[citation.document_id][citation.page - 1].words]
        assert citation.quote in " ".join(page_words)

        # Verified fact vs. suggestion stay apart.
        assert any(f.source == "document" for f in amount.verified_facts)
        assert any(f.source == "invoice" for f in amount.verified_facts)
        assert amount.uncertainty, "även en match ska säga vad den inte täcker"

    def test_a_different_rate_is_a_possible_deviation_never_an_accusation(self, integration_env):
        env = integration_env
        invoice = env.import_invoice(INVOICE_DEVIATING)
        amount = next(
            f for f in review_invoice(env.store, invoice)
            if f.finding_type == "invoice_contract_amount"
        )
        assert amount.verdict == "possible_deviation"
        assert amount.verdict_label == "möjlig avvikelse"
        assert "1 250" in " ".join(c.quote for c in amount.citations)
        assert "inte ett konstaterat avtalsbrott" in (amount.uncertainty or "")
        # The nearest comparable rate is the tractor rate, not the shovelling one.
        assert "200,00" in amount.suggestion

    def test_a_supplier_with_no_document_cannot_be_verified(self, integration_env):
        env = integration_env
        invoice = env.import_invoice(INVOICE_NO_CONTRACT)
        findings = review_invoice(env.store, invoice)
        assert len(findings) == 1
        finding = findings[0]
        assert finding.finding_type == "invoice_without_contract"
        assert finding.verdict == "cannot_be_verified"
        assert finding.verdict_label == "kan inte verifieras"
        assert finding.citations == []
        assert "Nordisk Hissteknik AB" in finding.suggestion

    def test_an_open_ended_period_is_read_and_bounds_the_invoice(self, integration_env):
        """The snow contract says 'från den 1 november 2026 och tills vidare'.

        The first version of this engine read ISO dates only, could not see
        that sentence at all, and answered *kan inte verifieras*. It now reads
        the Swedish date and the open end — and the January 2026 invoice turns
        out to fall *before* the agreement it is being checked against, which
        is a real finding about real data and exactly what a reviewer should be
        shown.
        """
        env = integration_env
        invoice = env.import_invoice(INVOICE_MATCHING)
        period = next(
            f for f in review_invoice(env.store, invoice)
            if f.finding_type == "invoice_contract_period"
        )
        assert period.verdict == "possible_deviation"
        assert period.uncertainty
        # The cited term, in the document's own words.
        cited = [f.value for f in period.verified_facts if f.label.startswith("Avtalstid")]
        assert cited == ["2026-11-01 och tills vidare"]

    def test_an_invoice_inside_an_open_ended_period_matches(self, integration_env):
        """The same clause, an invoice from the season it actually covers."""
        env = integration_env
        invoice = env.import_invoice(INVOICE_IN_CONTRACT_PERIOD)
        period = next(
            f for f in review_invoice(env.store, invoice)
            if f.finding_type == "invoice_contract_period"
        )
        assert period.verdict == "matches"
        # An open end is not a closed one, and the finding says so rather than
        # implying the agreement is known to still be running.
        assert "tills vidare" in period.suggestion
        assert "uppsagt" in period.suggestion

    def test_an_imported_attachment_is_never_cited_as_its_own_evidence(self, integration_env):
        """The invoice PDF agreeing with the invoice is not a finding."""
        env = integration_env
        event = import_eml(
            store=env.store,
            integrations=env.integrations,
            raw=(MAIL / "faktura-snosvangen-2026-02.eml").read_bytes(),
            filename="f.eml",
            imported_by="u",
        )
        attachment_doc = event.attachments[0].document_id
        assert attachment_doc in incoming_document_ids(env.store)

        invoice = env.import_invoice(INVOICE_MATCHING)
        for finding in review_invoice(env.store, invoice):
            for citation in finding.citations:
                assert citation.document_id != attachment_doc, (
                    "granskningen citerade fakturan som bevis för sig själv"
                )

    def test_every_citation_in_every_finding_verifies_verbatim(self, integration_env):
        """The property the whole block rests on, asserted over all fixtures."""
        env = integration_env
        for ref in (INVOICE_MATCHING, INVOICE_DEVIATING, INVOICE_NO_CONTRACT):
            invoice = env.import_invoice(ref)
            for finding in review_invoice(env.store, invoice):
                for citation in finding.citations:
                    pages = env.store.pages[citation.document_id]
                    words = [w.text for w in pages[citation.page - 1].words]
                    assert citation.quote in " ".join(words), (
                        f"{ref}: citat som inte står ordagrant på s. {citation.page}"
                    )
                if finding.verdict != "matches":
                    assert finding.uncertainty, f"{ref}: {finding.verdict} utan osäkerhet"

    def test_rerunning_a_review_keeps_decided_findings(self, integration_env):
        env = integration_env
        invoice = env.import_invoice(INVOICE_DEVIATING)
        first = env.integrations.replace_findings_for_invoice(
            invoice.id, review_invoice(env.store, invoice)
        )
        decided = first[0].model_copy(update={"status": "dismissed", "decided_by": "u"})
        env.integrations.update_finding(decided)

        env.integrations.replace_findings_for_invoice(
            invoice.id, review_invoice(env.store, invoice)
        )
        stored = env.integrations.list_findings()
        assert any(f.id == decided.id and f.status == "dismissed" for f in stored), (
            "en omkörning raderade ett mänskligt beslut"
        )


# ---------------------------------------------------------------------------
# Persistence and schema
# ---------------------------------------------------------------------------


class TestIntegrationStore:
    def test_a_newer_schema_version_is_refused(self, tmp_path):
        (tmp_path / "meta.json").write_text(json.dumps({"schemaVersion": 99}), encoding="utf-8")
        with pytest.raises(IntegrationError) as exc:
            IntegrationStore(tmp_path, tenant_id="t")
        assert "99" in str(exc.value)

    def test_a_record_from_another_tenant_is_refused_on_read(self, tmp_path):
        store = IntegrationStore(tmp_path, tenant_id="rätt-tenant")
        (tmp_path / "source-events.json").write_text(
            json.dumps(
                [
                    {
                        "id": "x",
                        "tenant_id": "fel-tenant",
                        "source_type": "email",
                        "received_at": "2026-01-01T00:00:00+00:00",
                        "content_sha256": "0" * 64,
                        "provenance": {
                            "method": "m", "adapter": "a", "origin_filename": "f",
                            "origin_bytes": 1, "imported_by": "u",
                        },
                        "origin": "a@b.example",
                    }
                ]
            ),
            encoding="utf-8",
        )
        with pytest.raises(IntegrationError) as exc:
            store.list_source_events()
        assert "fel-tenant" in str(exc.value)

    def test_the_tenant_id_comes_from_the_store_not_the_caller(self, tmp_path):
        store = IntegrationStore(tmp_path, tenant_id="rätt-tenant")
        smuggled = SourceEvent(
            id="a",
            tenant_id="fel-tenant",
            source_type="email",
            received_at="2026-01-01T00:00:00+00:00",
            content_sha256="0" * 64,
            provenance={
                "method": "m", "adapter": "a", "origin_filename": "f",
                "origin_bytes": 1, "imported_by": "u",
            },
            origin="a@b.example",
        )
        assert store.add_source_event(smuggled).tenant_id == "rätt-tenant"

    def test_files_are_written_0600(self, tmp_path):
        store = IntegrationStore(tmp_path, tenant_id="t")
        store.add_source_event(
            SourceEvent(
                id="a", tenant_id="t", source_type="email",
                received_at="2026-01-01T00:00:00+00:00", content_sha256="0" * 64,
                provenance={
                    "method": "m", "adapter": "a", "origin_filename": "f",
                    "origin_bytes": 1, "imported_by": "u",
                },
                origin="a@b.example",
            )
        )
        mode = (tmp_path / "source-events.json").stat().st_mode & 0o777
        assert mode == 0o600, oct(mode)


# ---------------------------------------------------------------------------
# No real personal data or secrets in what ships
# ---------------------------------------------------------------------------


class TestFixtureHygiene:
    def test_fixtures_use_reserved_domains_only(self):
        import re

        pattern = re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+)")
        allowed_suffixes = (".example", ".invalid", ".test", ".localhost")
        for path in sorted(FIXTURES.rglob("*")):
            if not path.is_file():
                continue
            text = path.read_bytes().decode("utf-8", errors="ignore")
            for domain in pattern.findall(text):
                assert domain.lower().endswith(allowed_suffixes), f"{path.name}: {domain}"

    def test_fixtures_carry_no_secret_shaped_strings(self):
        import re

        pattern = re.compile(r"(sk-[A-Za-z0-9-]{8,}|ghp_[A-Za-z0-9]{20,}|BEGIN [A-Z ]*PRIVATE KEY)")
        for path in sorted(FIXTURES.rglob("*")):
            if path.is_file():
                text = path.read_bytes().decode("utf-8", errors="ignore")
                assert not pattern.search(text), f"{path.name} innehåller en hemlighetsliknande sträng"

    def test_the_mail_fixtures_are_the_ones_the_generator_produces(self):
        """A committed fixture that the generator no longer reproduces is a
        fixture nobody can regenerate."""
        import hashlib
        import sys

        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from scripts.make_integration_fixtures import build

        before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(MAIL.glob("*.eml"))}
        build()
        after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(MAIL.glob("*.eml"))}
        assert before == after
