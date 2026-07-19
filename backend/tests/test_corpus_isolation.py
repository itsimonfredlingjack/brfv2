"""Structural guard (CI2 corpus-isolation): a document's corpus_origin can
only ever be its tenant's. `Store.add_document` takes no caller-supplied
origin parameter — there is no argument to abuse — and stamps every
ingested document with the tenant's own `Store.corpus_origin`. A defensive
check inside `add_document` guards any future refactor that might construct
a mismatched `DocumentMeta` some other way.
"""

from __future__ import annotations

import pytest

from app.schemas import DocumentMeta
from app.store import Store
from tests.pdf_fixtures import build_pdf


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
