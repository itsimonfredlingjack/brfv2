"""What a real accounting export contains and a friendly fixture does not.

The fixture dataset the demo runs on is a small readable story: five invoices,
every field filled in, one deliberate weak supplier name. That is the right
shape for a demo and the wrong shape for a test suite, because the ways a real
source breaks an adapter are all *absences* — a row list that is empty, a row
with nothing in it, a field that is ``null`` rather than missing, an amount that
is negative, a supplier the export barely identifies.

So the edge cases live in their own fixture directory
(``backend/fixtures/accounting-edge-cases``) which the shipped adapter never
reads, and the Fortnox ones are driven through the same stub transport as the
rest of the live-integration suite — the real URLs, the real mapping table, the
real refusals, an answer nobody had to be online to get.

The list is the one a first live connection actually runs into:

============================  ==========================================
pagination                    the read is bounded, and says so rather
                              than implying it saw everything
missing attachment            neither adapter reads attachments, and a
                              case with no file offers none to open
empty rows                    ``InvoiceRows: []`` is an invoice, not a
                              crash and not a dropped record
contentless rows              a row with no values is skipped, not
                              carried as an empty line
null values                   ``null`` is not ``""`` and not ``0``
cancelled invoice             read, shown as the source's own state,
                              never acted on
credit invoice                a negative amount survives as an exact
                              ``Decimal`` and is offered as a credit
duplicate sources             two readings of one invoice converge on
                              one case with two observations
incomplete supplier identity  a nameless supplier anchors on nothing and
                              the review refuses rather than guesses
============================  ==========================================

Two of these have no fixture-adapter half and it is worth saying why rather
than quietly testing one side: the fixture source carries no bookkeeping state
at all (there is nothing there to call "cancelled", and inventing one would be
this product asserting something about a system it never asked), and it has no
pagination because it reads a directory rather than a paged API.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from app.integrations import fortnox as fortnox_mod
from app.integrations.accounting_fixture import FixtureAccountingAdapter, FixtureError
from app.invoices import cases
from app.invoices.identity import case_key_for

# The stub transport and the connected-manager helper are the live suite's, on
# purpose: a second stub would be a second definition of what a Fortnox request
# looks like, and the two would drift.
from tests.test_integrations_live import StubTransport, fortnox_connected

EDGE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "accounting-edge-cases"

EMPTY_ROWS = "KF-TOMMA-RADER"
EMPTY_ROWS_SECOND_SOURCE = "KF-TOMMA-RADER-KOPIA"
CONTENTLESS_ROWS = "KF-INNEHALLSLOSA-RADER"
NULL_FIELDS = "KF-NULL-FALT"
UNKNOWN_SUPPLIER = "KF-OKAND-LEVERANTOR"
CREDIT = "KF-KREDIT"


@pytest.fixture
def edge_adapter() -> FixtureAccountingAdapter:
    return FixtureAccountingAdapter(EDGE_DIR)


# ---------------------------------------------------------------------------
# The fixture adapter
# ---------------------------------------------------------------------------


class TestFixtureAdapterEdgeCases:
    def test_the_edge_cases_are_not_in_the_dataset_the_product_ships_with(self):
        """The demo story stays a story. Somebody reading these opted in."""
        shipped = FixtureAccountingAdapter().list_invoices("gjutformen-12")
        refs = {row["external_ref"] for row in shipped}
        assert refs.isdisjoint({EMPTY_ROWS, NULL_FIELDS, UNKNOWN_SUPPLIER, CREDIT})

    def test_every_dataset_in_the_directory_is_listed(self, edge_adapter):
        """No page boundary, and no silent truncation at a file boundary either."""
        rows = edge_adapter.list_invoices("gjutformen-12")
        assert {row["external_ref"] for row in rows} == {
            EMPTY_ROWS, EMPTY_ROWS_SECOND_SOURCE, CONTENTLESS_ROWS,
            NULL_FIELDS, UNKNOWN_SUPPLIER, CREDIT,
        }
        assert {row["dataset"] for row in rows} == {
            "kantfall-2026.json", "kantfall-2026-andra-kallan.json"
        }

    def test_another_associations_row_in_the_same_file_is_not_listed(self, edge_adapter):
        rows = edge_adapter.list_invoices("gjutformen-12")
        assert "KF-ANNAN-FORENING" not in {row["external_ref"] for row in rows}
        with pytest.raises(LookupError):
            edge_adapter.get_invoice("gjutformen-12", "KF-ANNAN-FORENING")

    def test_an_empty_row_list_is_an_invoice_not_a_failure(self, edge_adapter):
        snapshot = edge_adapter.get_invoice("gjutformen-12", EMPTY_ROWS)
        assert snapshot.lines == []
        assert snapshot.total_amount == Decimal("6250.00")

    def test_a_row_with_nothing_in_it_is_still_a_row(self, edge_adapter):
        """The fixture adapter keeps every row it is given, empty or not.

        Worth pinning rather than assuming: the Fortnox adapter *drops*
        contentless rows and this one does not, and a reader comparing two
        cases read from two sources should be able to find out why here
        instead of by experiment.
        """
        snapshot = edge_adapter.get_invoice("gjutformen-12", CONTENTLESS_ROWS)
        assert len(snapshot.lines) == 3
        assert [line.description for line in snapshot.lines] == [
            "", "", "Maskinell snöröjning med traktor"
        ]
        assert snapshot.lines[0].amount is None
        assert snapshot.lines[2].amount == Decimal("5000.00")

    def test_null_is_carried_as_absent_and_never_as_zero(self, edge_adapter):
        snapshot = edge_adapter.get_invoice("gjutformen-12", NULL_FIELDS)
        assert snapshot.total_amount is None
        assert snapshot.vat_amount is None
        assert snapshot.invoice_number is None
        assert snapshot.invoice_date is None
        assert snapshot.due_date is None
        assert snapshot.period_start is None and snapshot.period_end is None
        assert snapshot.lines == []
        # A missing currency falls back to the one this product's associations
        # actually invoice in — a fallback, not a reading.
        assert snapshot.currency == "SEK"

    def test_a_null_amount_is_listed_as_missing_rather_than_as_a_number(self, edge_adapter):
        row = next(
            r for r in edge_adapter.list_invoices("gjutformen-12")
            if r["external_ref"] == NULL_FIELDS
        )
        assert row["total_amount"] == ""
        assert row["invoice_number"] is None

    def test_a_negative_total_survives_as_an_exact_decimal(self, edge_adapter):
        snapshot = edge_adapter.get_invoice("gjutformen-12", CREDIT)
        assert snapshot.total_amount == Decimal("-6250.00")
        assert snapshot.vat_amount == Decimal("-1250.00")
        assert snapshot.lines[0].quantity == Decimal("-4")
        # A string through JSON, never a float: -6250.00 must not become
        # -6249.999999999999 on the way to a comparison that tests equality.
        payload = snapshot.model_dump(mode="json")
        assert payload["total_amount"] == "-6250.00"
        assert isinstance(payload["total_amount"], str)

    def test_a_supplier_the_export_never_names_gets_a_case_of_its_own(self, edge_adapter):
        """No name, no merging. The key falls back to the source's reference."""
        snapshot = edge_adapter.get_invoice("gjutformen-12", UNKNOWN_SUPPLIER)
        assert snapshot.supplier_name == ""
        assert snapshot.supplier_ref is None
        key, basis = case_key_for(snapshot)
        assert key == f"fixture-accounting:{UNKNOWN_SUPPLIER}"
        assert "slås inte ihop med något annat" in basis

    def test_two_readings_of_one_invoice_share_a_case_key(self, edge_adapter):
        """Same supplier, same number, two datasets, two document references."""
        first = edge_adapter.get_invoice("gjutformen-12", EMPTY_ROWS)
        second = edge_adapter.get_invoice("gjutformen-12", EMPTY_ROWS_SECOND_SOURCE)
        assert first.source_dataset != second.source_dataset
        assert first.external_ref != second.external_ref
        assert case_key_for(first)[0] == case_key_for(second)[0]

    def test_a_dataset_that_is_not_this_schema_is_refused_rather_than_read_loosely(self, tmp_path):
        (tmp_path / "framtida.json").write_text(
            json.dumps({"Schema": "brfv2-accounting-fixture/v2", "SupplierInvoices": []}),
            encoding="utf-8",
        )
        with pytest.raises(FixtureError, match="Schema"):
            FixtureAccountingAdapter(tmp_path).list_invoices("gjutformen-12")


# ---------------------------------------------------------------------------
# The edge cases, all the way to a case
# ---------------------------------------------------------------------------


class TestTheEdgeCasesReachACase:
    """The adapter is only half of it. These land in the store and get reviewed."""

    def _read(self, env, external_ref: str):
        adapter = FixtureAccountingAdapter(EDGE_DIR)
        return env.integrations.upsert_invoice(adapter.get_invoice(env.brf_id, external_ref))

    def test_two_sources_of_one_invoice_are_one_case_with_two_observations(self, integration_env):
        self._read(integration_env, EMPTY_ROWS)
        self._read(integration_env, EMPTY_ROWS_SECOND_SOURCE)
        built = cases.project(integration_env.store)
        assert len(built) == 1
        assert len(built[0].observations) == 2
        assert {o.external_ref for o in built[0].observations} == {
            EMPTY_ROWS, EMPTY_ROWS_SECOND_SOURCE
        }

    def test_an_invoice_with_no_amount_is_reviewed_without_inventing_one(self, integration_env):
        self._read(integration_env, NULL_FIELDS)
        case = cases.project(integration_env.store)[0]
        worked = cases.analyse_case(integration_env.store, case.id)
        assert worked.total_amount is None
        comparison = next(
            f for f in cases.findings_for_invoice(integration_env.store, worked.primary_invoice_id)
            if f.finding_type == "invoice_previous_comparison"
        )
        assert comparison.verdict == "cannot_be_verified"

    def test_a_nameless_supplier_is_refused_rather_than_matched_to_a_contract(
        self, integration_env
    ):
        """The seeded archive has a snow-clearing contract. It must not attach here."""
        self._read(integration_env, UNKNOWN_SUPPLIER)
        case = cases.project(integration_env.store)[0]
        worked = cases.analyse_case(integration_env.store, case.id)
        findings = cases.findings_for_invoice(integration_env.store, worked.primary_invoice_id)
        assert any(f.finding_type == "invoice_without_contract" for f in findings)
        assert not any(f.citations for f in findings)
        assert {s.kind for s in worked.signals} >= {"missing_contract"}

    def test_a_case_with_no_attachment_offers_no_document_to_open(self, integration_env):
        """An accounting read carries no file, and none is invented for it.

        The observation is the reading, and it is honest about being one: there
        is no original to open, so the case offers nothing to open. A rendered
        stand-in here would be the product citing itself.
        """
        self._read(integration_env, EMPTY_ROWS)
        case = cases.project(integration_env.store)[0]
        assert cases.documents_for(integration_env.store, case) == []
        assert {o.kind for o in case.observations} == {"accounting_snapshot"}
        assert all(not o.document_id for o in case.observations)

    def test_a_credit_note_is_offered_as_the_credit_of_the_invoice_it_cancels(
        self, integration_env
    ):
        self._read(integration_env, EMPTY_ROWS)
        credit = self._read(integration_env, CREDIT)
        case = next(
            c for c in cases.project(integration_env.store) if c.primary_invoice_id == credit.id
        )
        worked = cases.analyse_case(integration_env.store, case.id)
        findings = [
            f for f in cases.findings_for_invoice(integration_env.store, credit.id)
            if f.finding_type == "invoice_credit_relation"
        ]
        assert len(findings) == 1
        assert "Den här posten är negativ" in findings[0].suggestion
        assert "2026-901" in findings[0].suggestion
        assert "betyder inte" in (findings[0].uncertainty or "")
        assert "credit_relation" in {s.kind for s in worked.signals}

    def test_the_credit_note_never_reads_as_settling_anything(self, integration_env):
        """A credit is an observation about two amounts. Not a resolution."""
        self._read(integration_env, EMPTY_ROWS)
        credit = self._read(integration_env, CREDIT)
        case = next(
            c for c in cases.project(integration_env.store) if c.primary_invoice_id == credit.id
        )
        worked = cases.analyse_case(integration_env.store, case.id)
        assert worked.review_status == "not_reviewed"
        assert worked.source_status is None
        signal = next(s for s in worked.signals if s.kind == "credit_relation")
        assert signal.severity() == "info"


# ---------------------------------------------------------------------------
# The Fortnox adapter
# ---------------------------------------------------------------------------


def _fortnox_invoice(**overrides) -> dict:
    base = {
        "GivenNumber": "301",
        "InvoiceNumber": "2026-301",
        "SupplierName": "Snösvängen Entreprenad AB",
        "SupplierNumber": "S042",
        "InvoiceDate": "2026-04-01",
        "DueDate": "2026-05-01",
        "Currency": "SEK",
        "Total": "6250.00",
        "VAT": "1250.00",
        "Booked": False,
        "Cancelled": False,
        "SupplierInvoiceRows": [
            {
                "Description": "Maskinell snöröjning med traktor",
                "Quantity": "4",
                "Price": "1250.00",
                "Debit": "5000.00",
            }
        ],
    }
    base.update(overrides)
    return base


def _register_opted_in(tmp_path, transport):
    """A connected adapter that may also read the supplier register.

    Built from scratch rather than reconfigured, because reconfiguring a live
    connection drops its credential — which is the right behaviour and the
    reason this cannot be one line on top of ``fortnox_connected``.
    """
    import time

    from app.integrations.connections import ConnectionManager
    from app.integrations.credentials import CredentialStore, Secrets
    from app.integrations.oauth import PendingLogins

    credentials = CredentialStore(tmp_path, tenant_id="gjutformen-12")
    manager = ConnectionManager(credentials, pending=PendingLogins(), transport=transport)
    manager.configure_fortnox(
        fortnox_mod.FortnoxConfig(
            client_id="c", redirect_uri="https://x.example/cb", read_supplier_register=True
        ),
        client_secret="s",
        user_id="admin",
    )
    credentials.write_secrets(
        fortnox_mod.PROVIDER,
        Secrets(
            access_token="fx-access",
            refresh_token="fx-refresh",
            client_secret="s",
            access_expires_epoch=time.time() + 3600,
        ),
    )
    return manager.fortnox_adapter()


class TestFortnoxEdgeCases:
    def test_the_list_read_is_bounded_and_asks_for_one_page(self, tmp_path):
        """One page, a stated size, newest first — and no second request.

        Fortnox answers a list read with ``MetaInformation`` describing how many
        pages exist. This adapter reads one page on purpose: the list is a
        chooser a person picks one invoice out of, not a sync. What matters is
        that it cannot *quietly* become a sync — a page walk would multiply
        every read against somebody's live company by the number of pages.
        """
        payload = {
            "SupplierInvoices": [_fortnox_invoice(GivenNumber=str(n)) for n in range(1, 26)],
            "MetaInformation": {
                "@TotalResources": 412, "@TotalPages": 17, "@CurrentPage": 1
            },
        }
        transport = StubTransport().route("GET", "/3/supplierinvoices", payload)
        adapter = fortnox_connected(tmp_path, transport).fortnox_adapter()

        rows = adapter.list_invoices("gjutformen-12")
        assert len(rows) == 25
        assert len(transport.requests) == 1, "en sidvandring har smugit in i listläsningen"
        query = transport.requests[0]["query"]
        assert query["limit"] == [str(fortnox_mod.DEFAULT_PAGE_SIZE)]
        assert query["sortby"] == ["givennumber"] and query["sortorder"] == ["descending"]
        assert "page" not in query

    @pytest.mark.parametrize(
        "asked, sent",
        [(1, 1), (10, 10), (0, 1), (-5, 1), (1000, fortnox_mod.MAX_PAGE_SIZE)],
    )
    def test_the_page_size_is_clamped_to_something_a_provider_will_accept(
        self, tmp_path, asked, sent
    ):
        transport = StubTransport().route("GET", "/3/supplierinvoices", {"SupplierInvoices": []})
        adapter = fortnox_connected(tmp_path, transport).fortnox_adapter()
        adapter.list_invoices("gjutformen-12", limit=asked)
        assert transport.requests[-1]["query"]["limit"] == [str(sent)]

    def test_a_page_of_junk_entries_yields_the_rows_that_are_rows(self, tmp_path):
        payload = {"SupplierInvoices": [_fortnox_invoice(), "inte ett objekt", None, 17]}
        transport = StubTransport().route("GET", "/3/supplierinvoices", payload)
        adapter = fortnox_connected(tmp_path, transport).fortnox_adapter()
        rows = adapter.list_invoices("gjutformen-12")
        assert [row["external_ref"] for row in rows] == ["301"]

    def test_an_answer_with_no_invoices_at_all_is_an_empty_list(self, tmp_path):
        for payload in ({}, {"SupplierInvoices": None}, {"SupplierInvoices": []}):
            transport = StubTransport().route("GET", "/3/supplierinvoices", payload)
            adapter = fortnox_connected(tmp_path, transport).fortnox_adapter()
            assert adapter.list_invoices("gjutformen-12") == []

    def test_an_invoice_with_no_rows_maps_without_inventing_a_line(self, tmp_path):
        transport = StubTransport().route(
            "GET", "/3/supplierinvoices/301",
            {"SupplierInvoice": _fortnox_invoice(SupplierInvoiceRows=[])},
        )
        adapter = fortnox_connected(tmp_path, transport).fortnox_adapter()
        snapshot = adapter.get_invoice("gjutformen-12", "301")
        assert snapshot.lines == []
        assert snapshot.total_amount == Decimal("6250.00")

    def test_rows_with_nothing_in_them_are_dropped_rather_than_carried(self, tmp_path):
        transport = StubTransport().route(
            "GET", "/3/supplierinvoices/301",
            {
                "SupplierInvoice": _fortnox_invoice(
                    SupplierInvoiceRows=[
                        {},
                        {"Description": "", "Quantity": None, "Price": None, "Total": None},
                        "inte ett objekt",
                        {"Description": "Utryckning", "Quantity": "1", "Price": "980.00"},
                    ]
                )
            },
        )
        adapter = fortnox_connected(tmp_path, transport).fortnox_adapter()
        snapshot = adapter.get_invoice("gjutformen-12", "301")
        assert [line.description for line in snapshot.lines] == ["Utryckning"]

    def test_null_fields_become_absent_never_empty_strings_or_zero(self, tmp_path):
        transport = StubTransport().route(
            "GET", "/3/supplierinvoices/301",
            {
                "SupplierInvoice": _fortnox_invoice(
                    InvoiceNumber=None, InvoiceDate=None, DueDate=None,
                    Total=None, VAT=None, Currency=None, SupplierNumber=None,
                    SupplierInvoiceRows=None,
                )
            },
        )
        adapter = fortnox_connected(tmp_path, transport).fortnox_adapter()
        snapshot = adapter.get_invoice("gjutformen-12", "301")
        assert snapshot.invoice_number is None
        assert snapshot.invoice_date is None and snapshot.due_date is None
        assert snapshot.total_amount is None and snapshot.vat_amount is None
        assert snapshot.supplier_ref is None
        assert snapshot.lines == []
        assert snapshot.currency == "SEK"

    def test_an_invoice_number_can_come_from_the_external_field_instead(self, tmp_path):
        """The mapping table's second source, exercised rather than assumed."""
        transport = StubTransport().route(
            "GET", "/3/supplierinvoices/301",
            {
                "SupplierInvoice": _fortnox_invoice(
                    InvoiceNumber=None, ExternalInvoiceNumber="EXT-2026-301"
                )
            },
        )
        adapter = fortnox_connected(tmp_path, transport).fortnox_adapter()
        assert adapter.get_invoice("gjutformen-12", "301").invoice_number == "EXT-2026-301"
        preview = adapter.mapping_preview("gjutformen-12", "301")
        row = next(f for f in preview["fields"] if f["target"] == "invoice_number")
        assert row["sourceField"] == "ExternalInvoiceNumber"

    def test_a_cancelled_invoice_is_read_shown_and_left_alone(self, tmp_path):
        transport = StubTransport().route(
            "GET", "/3/supplierinvoices/301",
            {"SupplierInvoice": _fortnox_invoice(Cancelled=True, Booked=True, Balance="0")},
        )
        adapter = fortnox_connected(tmp_path, transport).fortnox_adapter()
        snapshot = adapter.get_invoice("gjutformen-12", "301")
        assert snapshot.source_status["Cancelled"] == "True"
        assert snapshot.source_status["Booked"] == "True"
        assert transport.methods == {"GET"}

    def test_the_cancelled_state_reaches_the_case_as_the_sources_own(
        self, tmp_path, integration_env
    ):
        """Their status, labelled as theirs, beside this product's own."""
        transport = StubTransport().route(
            "GET", "/3/supplierinvoices/301",
            {"SupplierInvoice": _fortnox_invoice(Cancelled=True, Booked=True)},
        )
        adapter = fortnox_connected(tmp_path, transport).fortnox_adapter()
        integration_env.integrations.upsert_invoice(
            adapter.get_invoice(integration_env.brf_id, "301")
        )
        case = cases.project(integration_env.store)[0]
        assert case.source_status is not None
        assert case.source_status.cancelled is True
        assert case.source_status.adapter == "fortnox"
        # The association's own position is untouched by the accounting
        # system's: a cancelled invoice is not a reviewed one.
        assert case.review_status == "not_reviewed"

    def test_a_cancelled_invoice_in_the_list_is_flagged_without_being_hidden(self, tmp_path):
        transport = StubTransport().route(
            "GET", "/3/supplierinvoices",
            {"SupplierInvoices": [_fortnox_invoice(Cancelled=True)]},
        )
        adapter = fortnox_connected(tmp_path, transport).fortnox_adapter()
        row = adapter.list_invoices("gjutformen-12")[0]
        assert row["cancelled"] is True and row["booked"] is False

    def test_a_credit_invoice_keeps_its_sign_and_its_precision(self, tmp_path):
        transport = StubTransport().route(
            "GET", "/3/supplierinvoices/302",
            {
                "SupplierInvoice": _fortnox_invoice(
                    GivenNumber="302", InvoiceNumber="2026-302",
                    Total="-6250.00", VAT="-1250.00",
                    SupplierInvoiceRows=[
                        {"Description": "Maskinell snöröjning med traktor",
                         "Quantity": "-4", "Price": "1250.00", "Debit": "-5000.00"}
                    ],
                )
            },
        )
        adapter = fortnox_connected(tmp_path, transport).fortnox_adapter()
        snapshot = adapter.get_invoice("gjutformen-12", "302")
        assert snapshot.total_amount == Decimal("-6250.00")
        assert snapshot.lines[0].amount == Decimal("-5000.00")
        assert snapshot.model_dump(mode="json")["total_amount"] == "-6250.00"

    def test_a_swedish_decimal_comma_is_read_as_a_decimal_point(self, tmp_path):
        """An export written for humans, parsed without going through float."""
        transport = StubTransport().route(
            "GET", "/3/supplierinvoices/301",
            {"SupplierInvoice": _fortnox_invoice(Total="6 250,50", VAT="1 250,10")},
        )
        adapter = fortnox_connected(tmp_path, transport).fortnox_adapter()
        snapshot = adapter.get_invoice("gjutformen-12", "301")
        assert snapshot.total_amount == Decimal("6250.50")
        assert snapshot.vat_amount == Decimal("1250.10")

    def test_an_unparsable_amount_is_absent_rather_than_guessed(self, tmp_path):
        transport = StubTransport().route(
            "GET", "/3/supplierinvoices/301",
            {"SupplierInvoice": _fortnox_invoice(Total="se bilaga")},
        )
        adapter = fortnox_connected(tmp_path, transport).fortnox_adapter()
        assert adapter.get_invoice("gjutformen-12", "301").total_amount is None

    def test_a_supplier_the_export_barely_identifies_still_maps(self, tmp_path):
        transport = StubTransport().route(
            "GET", "/3/supplierinvoices/301",
            {"SupplierInvoice": _fortnox_invoice(SupplierName="", SupplierNumber="")},
        )
        adapter = fortnox_connected(tmp_path, transport).fortnox_adapter()
        snapshot = adapter.get_invoice("gjutformen-12", "301")
        assert snapshot.supplier_name == ""
        assert snapshot.supplier_ref is None
        # No supplier number means no register lookup to make, opted in or not.
        assert not any(r["path"].startswith("/3/suppliers") for r in transport.requests)

    def test_an_unreadable_supplier_register_never_fails_the_invoice(self, tmp_path):
        """A weaker anchor is a worse review. A failed read is no review at all."""
        transport = StubTransport().route(
            "GET", "/3/supplierinvoices/301", {"SupplierInvoice": _fortnox_invoice()}
        ).route("GET", "/3/suppliers/S042", {"Error": "forbidden"}, status=403)
        snapshot = _register_opted_in(tmp_path, transport).get_invoice("gjutformen-12", "301")
        assert snapshot.supplier_ref == "S042"
        assert snapshot.supplier_name == "Snösvängen Entreprenad AB"

    def test_neither_adapter_reads_an_attachment(self, tmp_path):
        """Not "there was none" — there is no code that would fetch one.

        Fortnox keeps invoice files behind its own archive endpoints. Reading
        them would put a supplier's PDF into the association's archive without
        anybody choosing it, and the product has one way in for a document: a
        person puts it there.
        """
        transport = StubTransport().route(
            "GET", "/3/supplierinvoices/301",
            {
                "SupplierInvoice": _fortnox_invoice(
                    AttachmentInformation={"@NumberOfAttachments": 2, "Attachments": ["a", "b"]}
                )
            },
        )
        adapter = fortnox_connected(tmp_path, transport).fortnox_adapter()
        adapter.get_invoice("gjutformen-12", "301")
        assert [r["path"] for r in transport.requests] == ["/3/supplierinvoices/301"]
        source = Path(fortnox_mod.__file__).read_text("utf-8").lower()
        for endpoint in ("inbox", "fileconnection", "archive"):
            assert endpoint not in source, f"fortnox.py nämner {endpoint} — läser den filer nu?"

    def test_the_same_invoice_read_from_fortnox_and_the_fixture_is_one_case(
        self, tmp_path, integration_env
    ):
        """The identity is the supplier and the number, not the source.

        This is the shape a live connection actually arrives in: an association
        has been reading a fixture export, connects Fortnox, and the same
        invoice comes back under a different document reference. Two cases here
        would be two review histories for one invoice.
        """
        transport = StubTransport().route(
            "GET", "/3/supplierinvoices/901",
            {
                "SupplierInvoice": _fortnox_invoice(
                    GivenNumber="901", InvoiceNumber="2026-901", Booked=True
                )
            },
        )
        fixture = FixtureAccountingAdapter(EDGE_DIR)
        # When each reading happened is stated rather than left to the clock:
        # both would otherwise land in the same second, and which one describes
        # the case would then be decided by a tie-break on a random id.
        integration_env.integrations.upsert_invoice(
            fixture.get_invoice(integration_env.brf_id, EMPTY_ROWS).model_copy(
                update={"retrieved_at": "2026-04-01T09:00:00+00:00"}
            )
        )
        integration_env.integrations.upsert_invoice(
            fortnox_connected(tmp_path, transport)
            .fortnox_adapter()
            .get_invoice(integration_env.brf_id, "901")
            .model_copy(update={"retrieved_at": "2026-04-02T09:00:00+00:00"})
        )
        built = cases.project(integration_env.store)
        assert len(built) == 1
        assert {o.adapter for o in built[0].observations} == {"fixture-accounting", "fortnox"}
        # The case describes itself by the most recent reading, and that
        # reading is the one carrying the accounting system's own state.
        assert built[0].source_status is not None
        assert built[0].source_status.adapter == "fortnox"
        assert built[0].source_status.booked is True
