"""Tenant-level corpus_origin (CI2 corpus-isolation guard): declared
explicitly at creation, persisted in the tenant's own directory (sibling to
documents.json/settings.json — see Store._load_or_init_corpus_origin), and
enforced by a val- naming rule so a document's data provenance can never be
mixed across the three corpora (real customer docs, scraped public annual
reports, synthetic fixtures)."""

from __future__ import annotations

import json

import pytest

from app.auth import AuthStore
from app.registry import TenantRegistry


def _registry(tmp_path) -> TenantRegistry:
    auth = AuthStore(tmp_path / "auth.db")
    return TenantRegistry(tmp_path, auth)


class TestOriginPersistsAndReloads:
    @pytest.mark.parametrize(
        "corpus_origin,brf_id",
        [
            ("customer", "brf-a"),
            ("public_scraped", "val-scrape-1"),
            ("synthetic", "brf-synth-1"),
        ],
    )
    def test_origin_persists_across_reload(self, tmp_path, corpus_origin, brf_id):
        registry = _registry(tmp_path)
        registry.create("Test", corpus_origin, brf_id)
        store = registry.get(brf_id)
        assert store is not None
        assert store.corpus_origin == corpus_origin

        meta_path = tmp_path / "tenants" / brf_id / "tenant_meta.json"
        assert json.loads(meta_path.read_text("utf-8"))["corpus_origin"] == corpus_origin

        # Fresh registry against the same data root (simulates a process
        # restart) — must reload the SAME origin from disk, not re-derive it.
        registry2 = _registry(tmp_path)
        store2 = registry2.get(brf_id)
        assert store2 is not None
        assert store2.corpus_origin == corpus_origin

    def test_document_inherits_tenant_origin_on_ingestion(self, tmp_path):
        from tests.pdf_fixtures import build_pdf

        registry = _registry(tmp_path)
        registry.create("Test", "customer", "brf-a")
        store = registry.get("brf-a")
        meta = store.add_document("A.pdf", build_pdf([[("Text.", 72, 100)]]))
        assert meta.corpus_origin == "customer"


class TestMissingOriginFails:
    def test_creation_without_origin_raises(self, tmp_path):
        registry = _registry(tmp_path)
        with pytest.raises(TypeError):
            registry.create("Test", brf_id="brf-x")  # corpus_origin omitted entirely

    def test_creation_with_invalid_origin_raises(self, tmp_path):
        registry = _registry(tmp_path)
        with pytest.raises(ValueError):
            registry.create("Test", "not-a-real-origin", "brf-x")


class TestNamingRuleEnforcedBothDirections:
    def test_public_scraped_without_val_prefix_rejected(self, tmp_path):
        registry = _registry(tmp_path)
        with pytest.raises(ValueError):
            registry.create("Test", "public_scraped", "brf-not-val")

    def test_customer_with_val_prefix_rejected(self, tmp_path):
        registry = _registry(tmp_path)
        with pytest.raises(ValueError):
            registry.create("Test", "customer", "val-oops")

    def test_public_scraped_with_val_prefix_allowed(self, tmp_path):
        registry = _registry(tmp_path)
        brf_id = registry.create("Test", "public_scraped", "val-ok-1")
        assert brf_id == "val-ok-1"

    def test_customer_without_val_prefix_allowed(self, tmp_path):
        registry = _registry(tmp_path)
        brf_id = registry.create("Test", "customer", "brf-ok-1")
        assert brf_id == "brf-ok-1"

    def test_synthetic_has_no_naming_constraint(self, tmp_path):
        registry = _registry(tmp_path)
        # Neither a val- id nor a plain id is rejected for synthetic — no
        # exception raised for either of the following.
        registry.create("Test", "synthetic", "val-synth-1")
        registry.create("Test2", "synthetic", "brf-synth-2")

    def test_rejected_naming_never_registers_the_tenant(self, tmp_path):
        # The naming check runs BEFORE auth.create_tenant — a rejected
        # creation must leave no trace in the auth db or on disk.
        registry = _registry(tmp_path)
        with pytest.raises(ValueError):
            registry.create("Test", "public_scraped", "brf-not-val")
        assert registry.auth.get_tenant("brf-not-val") is None
        assert not (tmp_path / "tenants" / "brf-not-val").exists()


class TestMigrationOnLoad:
    """A tenant directory that predates CI2 — no tenant_meta.json, and
    documents.json entries without corpus_origin — must load as 'synthetic'
    and migrate (write the value back) rather than fail."""

    def test_legacy_tenant_directory_migrates_to_synthetic(self, tmp_path):
        from app.store import Store

        legacy_dir = tmp_path / "legacy-tenant"
        (legacy_dir / "docs").mkdir(parents=True)
        (legacy_dir / "extract").mkdir(parents=True)
        # A pre-CI2 documents.json entry — no corpus_origin key at all.
        (legacy_dir / "documents.json").write_text(
            json.dumps(
                {
                    "abc123": {
                        "id": "abc123",
                        "name": "Legacy.pdf",
                        "pages": 1,
                        "words": 10,
                        "chunks": 1,
                        "uploaded_at": "2026-01-01T00:00:00+00:00",
                        "source": "digital",
                    }
                }
            ),
            "utf-8",
        )
        (legacy_dir / "extract" / "abc123.json").write_text(
            json.dumps([{"number": 1, "width": 595.0, "height": 842.0, "rotation": 0, "words": []}]), "utf-8"
        )

        assert not (legacy_dir / "tenant_meta.json").exists()

        store = Store(data_dir=legacy_dir)

        assert store.corpus_origin == "synthetic"
        assert store.documents["abc123"].corpus_origin == "synthetic"

        # Migration persisted to disk.
        assert json.loads((legacy_dir / "tenant_meta.json").read_text("utf-8"))["corpus_origin"] == "synthetic"
        on_disk = json.loads((legacy_dir / "documents.json").read_text("utf-8"))
        assert on_disk["abc123"]["corpus_origin"] == "synthetic"

        # Reload: now explicit on disk, no further migration needed, same result.
        store2 = Store(data_dir=legacy_dir)
        assert store2.corpus_origin == "synthetic"
        assert store2.documents["abc123"].corpus_origin == "synthetic"
