"""Structural guard (CI2 corpus-isolation): a document's corpus_origin can
only ever be its tenant's. `Store.add_document` takes no caller-supplied
origin parameter — there is no argument to abuse — and stamps every
ingested document with the tenant's own `Store.corpus_origin`. A defensive
check inside `add_document` guards any future refactor that might construct
a mismatched `DocumentMeta` some other way.

`TestCustomerCannotReceiveScrapedOrigin` (CI3) is the black-box counterpart:
a customer tenant is exercised through every public ingestion surface (the
direct Store API, the real HTTP upload route, including an adversarial
forged form field) and proven to only ever produce "customer" documents,
then the absence of an origin parameter is proven directly by introspecting
both signatures.
"""

from __future__ import annotations

import inspect

import pytest

from app.schemas import DocumentMeta
from app.store import Store
from tests.pdf_fixtures import build_pdf
from tests.tenant_fixtures import Harness


class TestAddDocumentStampsTenantOrigin:
    @pytest.mark.parametrize("corpus_origin", ["customer", "public_scraped", "synthetic"])
    def test_stamps_the_tenants_own_origin(self, tmp_path, corpus_origin):
        store = Store(data_dir=tmp_path, corpus_origin=corpus_origin)
        meta = store.add_document("A.pdf", build_pdf([[("Text.", 72, 100)]]))
        assert meta.corpus_origin == corpus_origin
        assert store.documents[meta.id].corpus_origin == corpus_origin

    def test_add_document_accepts_no_origin_parameter(self, tmp_path):
        # No argument to abuse: passing corpus_origin to add_document is a
        # TypeError, not a way to override the tenant's stamped origin.
        store = Store(data_dir=tmp_path, corpus_origin="customer")
        with pytest.raises(TypeError):
            store.add_document(
                "A.pdf", build_pdf([[("Text.", 72, 100)]]), corpus_origin="public_scraped"
            )

    def test_documents_listing_exposes_corpus_origin(self, tmp_path):
        store = Store(data_dir=tmp_path, corpus_origin="public_scraped")
        store.add_document("A.pdf", build_pdf([[("Text.", 72, 100)]]))
        listed = store.list_documents()
        assert len(listed) == 1
        assert listed[0]["corpus_origin"] == "public_scraped"


class TestMismatchDefenseRaises:
    def test_forced_mismatch_is_rejected(self, monkeypatch, tmp_path):
        """add_document's construction site always stamps self.corpus_origin,
        so a real mismatch can't arise through normal use — this proves the
        defensive check itself fires, by forcing a future-refactor-shaped
        mismatch: DocumentMeta construction returning a different origin than
        the one add_document asked for."""
        import app.store as store_mod

        class _ForcedMismatchMeta(DocumentMeta):
            def __init__(self, **data):
                data["corpus_origin"] = "public_scraped"
                super().__init__(**data)

        monkeypatch.setattr(store_mod, "DocumentMeta", _ForcedMismatchMeta)
        store = Store(data_dir=tmp_path, corpus_origin="customer")

        with pytest.raises(ValueError, match="corpus_origin-avvikelse"):
            store.add_document("A.pdf", build_pdf([[("Text.", 72, 100)]]))

        # The rejected ingestion left no residue: no orphaned pdf/extraction
        # file, no half-registered document.
        assert store.documents == {}
        assert not any((tmp_path / "docs").iterdir())
        assert not any((tmp_path / "extract").iterdir())


class TestCustomerCannotReceiveScrapedOrigin:
    """Black-box guard (CI3 phase brief): a customer-origin tenant's
    documents can ONLY ever carry corpus_origin "customer" — not because
    some check rejects a different value, but because neither public
    ingestion surface (the direct Store API, the HTTP upload route) has any
    parameter through which a caller could ask for one. Exercises both
    surfaces end to end, including an adversarial attempt to smuggle a
    different origin through the HTTP form, then proves the absence of the
    parameter itself by introspecting both signatures — so this starts
    failing the moment someone adds one, rather than staying silently true
    by accident."""

    def test_direct_add_document_only_ever_customer(self, tmp_path):
        store = Store(data_dir=tmp_path, corpus_origin="customer")
        for i in range(3):
            meta = store.add_document(f"doc{i}.pdf", build_pdf([[("Text.", 72, 100)]]))
            assert meta.corpus_origin == "customer"
        assert {d.corpus_origin for d in store.documents.values()} == {"customer"}

    def test_http_upload_route_only_ever_customer(self, tmp_path):
        h = Harness(tmp_path)
        h.make_tenant("Kund AB", "customer", "brf-cust-http")  # non-val name: customer origin
        h.make_user("admin@kund.se", memberships=[("brf-cust-http", "admin")])
        token = h.login("admin@kund.se")

        for i in range(2):
            r = h.client.post(
                "/api/brf/brf-cust-http/documents",
                files={"file": (f"doc{i}.pdf", build_pdf([[("Text.", 72, 100)]]), "application/pdf")},
                headers=h.bearer(token),
            )
            assert r.status_code == 200, r.text
            assert r.json()["corpus_origin"] == "customer"

        store = h.registry.get("brf-cust-http")
        assert {d.corpus_origin for d in store.documents.values()} == {"customer"}
        listed = h.client.get("/api/brf/brf-cust-http/documents", headers=h.bearer(token)).json()
        assert {d["corpus_origin"] for d in listed} == {"customer"}

    def test_http_upload_ignores_forged_origin_field(self, tmp_path):
        """Even a client that stuffs an extra 'corpus_origin' form field into
        the multipart request (attempting to smuggle a different origin in)
        gets nowhere: the upload route has no parameter bound to it — FastAPI
        silently drops unbound form fields — so the document still lands as
        'customer'."""
        h = Harness(tmp_path)
        h.make_tenant("Kund AB", "customer", "brf-cust-forge")
        h.make_user("admin@kund.se", memberships=[("brf-cust-forge", "admin")])
        token = h.login("admin@kund.se")

        r = h.client.post(
            "/api/brf/brf-cust-forge/documents",
            files={"file": ("A.pdf", build_pdf([[("Text.", 72, 100)]]), "application/pdf")},
            data={"corpus_origin": "public_scraped"},
            headers=h.bearer(token),
        )
        assert r.status_code == 200, r.text
        assert r.json()["corpus_origin"] == "customer"

    def test_add_document_signature_exposes_no_origin_parameter(self):
        """The whole guard rests on there being NO argument to abuse — this
        fails the instant Store.add_document grows an origin-shaped
        parameter, whatever it's named."""
        params = set(inspect.signature(Store.add_document).parameters) - {"self"}
        assert params == {"name", "pdf_bytes"}

    def test_upload_route_signature_exposes_no_origin_parameter(self, tmp_path):
        """Same guarantee at the HTTP boundary: introspects the ACTUAL
        registered FastAPI route (not a hand-copied assumption of its
        signature) for the document-upload endpoint."""
        h = Harness(tmp_path)
        route = next(
            r
            for r in h.app.routes
            if getattr(r, "path", None) == "/api/brf/{brf_id}/documents" and "POST" in getattr(r, "methods", set())
        )
        params = set(inspect.signature(route.endpoint).parameters)
        forbidden = {"corpus_origin", "origin", "source_origin"}
        assert not (forbidden & params), f"upload route gained an origin-shaped parameter: {params & forbidden}"
