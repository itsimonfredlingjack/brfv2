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
from app.store import Store


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

    def test_fresh_empty_directory_with_no_documents_still_defaults_quietly(self, tmp_path):
        """Regression lock: the common ad hoc test/script shape (a brand new,
        empty tmp_path, no documents.json at all, no explicit corpus_origin)
        must keep defaulting to 'synthetic' without raising — this is NOT the
        'already migrated but meta vanished' anomaly (see
        TestAlreadyMigratedTenantMetaMissingFailsClosed), it's simply nothing
        recorded yet."""
        assert not (tmp_path / "documents.json").exists()
        store = Store(data_dir=tmp_path)
        assert store.corpus_origin == "synthetic"
        assert json.loads((tmp_path / "tenant_meta.json").read_text("utf-8"))["corpus_origin"] == "synthetic"


class TestTenantMetaFailsClosed:
    """Finding (CI2 review, closed in CI3): a tenant_meta.json that EXISTS
    but is malformed or holds an invalid value must refuse to open the
    tenant (loud Swedish RuntimeError) — never silently downgrade to
    'synthetic'. The migration default is reserved for a file that is
    entirely ABSENT (see TestMigrationOnLoad and
    TestAlreadyMigratedTenantMetaMissingFailsClosed)."""

    def test_malformed_json_tenant_meta_fails_closed(self, tmp_path):
        (tmp_path / "tenant_meta.json").write_text("{not valid json", "utf-8")
        with pytest.raises(RuntimeError, match="tenant_meta.json"):
            Store(data_dir=tmp_path)

    def test_invalid_origin_value_in_tenant_meta_fails_closed(self, tmp_path):
        (tmp_path / "tenant_meta.json").write_text(json.dumps({"corpus_origin": "bogus"}), "utf-8")
        with pytest.raises(RuntimeError, match="tenant_meta.json"):
            Store(data_dir=tmp_path)

    def test_tenant_meta_missing_the_key_entirely_fails_closed(self, tmp_path):
        (tmp_path / "tenant_meta.json").write_text(json.dumps({"some_other_key": "x"}), "utf-8")
        with pytest.raises(RuntimeError, match="tenant_meta.json"):
            Store(data_dir=tmp_path)

    def test_valid_tenant_meta_still_opens_normally(self, tmp_path):
        # Regression, the other direction: a well-formed file must NOT raise.
        (tmp_path / "tenant_meta.json").write_text(json.dumps({"corpus_origin": "customer"}), "utf-8")
        store = Store(data_dir=tmp_path)
        assert store.corpus_origin == "customer"


class TestAlreadyMigratedTenantMetaMissingFailsClosed:
    """The other half of the same finding: documents.json that already shows
    EVERY entry stamped with a corpus_origin, but tenant_meta.json is
    missing, is not a legacy tenant — it's a tenant that already migrated
    once and then lost its tenant_meta.json some other way. That must fail
    loud, not quietly re-default to 'synthetic' (which could mask a real
    customer/public_scraped tenant's true origin)."""

    def test_fully_stamped_documents_without_tenant_meta_fails_closed(self, tmp_path):
        assert not (tmp_path / "tenant_meta.json").exists()
        (tmp_path / "documents.json").write_text(
            json.dumps(
                {
                    "abc123": {
                        "id": "abc123",
                        "name": "A.pdf",
                        "pages": 1,
                        "words": 3,
                        "chunks": 1,
                        "uploaded_at": "2026-01-01T00:00:00+00:00",
                        "source": "digital",
                        "corpus_origin": "customer",
                    }
                }
            ),
            "utf-8",
        )
        with pytest.raises(RuntimeError, match="tenant_meta.json"):
            Store(data_dir=tmp_path)

    def test_explicit_corpus_origin_bypasses_the_anomaly_check(self, tmp_path):
        # An explicit corpus_origin (the TenantRegistry.create path) is a
        # fresh, explicit declaration, not a migration — it's accepted even
        # if documents.json happens to already look fully-stamped.
        (tmp_path / "documents.json").write_text(
            json.dumps(
                {
                    "abc123": {
                        "id": "abc123",
                        "name": "A.pdf",
                        "pages": 1,
                        "words": 3,
                        "chunks": 1,
                        "uploaded_at": "2026-01-01T00:00:00+00:00",
                        "source": "digital",
                        "corpus_origin": "customer",
                    }
                }
            ),
            "utf-8",
        )
        store = Store(data_dir=tmp_path, corpus_origin="customer")
        assert store.corpus_origin == "customer"


class TestOriginValidationAtDepth:
    """Finding: Store.__init__ and TenantRegistry.get validate corpus_origin
    against CORPUS_ORIGINS whenever it's provided as an argument — an
    invalid value raises immediately, rather than being silently accepted
    and persisted."""

    def test_store_rejects_invalid_corpus_origin_argument(self, tmp_path):
        with pytest.raises(ValueError):
            Store(data_dir=tmp_path, corpus_origin="not-a-real-origin")
        # Nothing persisted for the rejected value.
        assert not (tmp_path / "tenant_meta.json").exists()

    def test_registry_get_rejects_invalid_corpus_origin_argument(self, tmp_path):
        registry = _registry(tmp_path)
        registry.create("Test", "customer", "brf-a")
        with pytest.raises(ValueError):
            registry.get("brf-a", corpus_origin="not-a-real-origin")


class TestGetRequiresExistingDirectory:
    """Finding (CI2 review, closed in CI3): registry.get(brf_id) WITHOUT
    corpus_origin must only ever OPEN a tenant directory that already
    exists — never materialize one. Closes the crash-window where a
    customer tenant's auth-db row exists but its Store was never actually
    constructed (a crash between auth.create_tenant and create()'s eager
    get()) — under the old behavior, the next plain get() would silently
    create a fresh directory and default it to 'synthetic'."""

    def test_get_without_origin_raises_if_directory_never_materialized(self, tmp_path):
        auth = AuthStore(tmp_path / "auth.db")
        registry = TenantRegistry(tmp_path, auth)
        # Simulate the crash window directly: an auth-db row with NO
        # corresponding directory on disk (create() normally makes both in
        # the same call — this reproduces what a crash in between leaves).
        auth.create_tenant("Kund AB", "brf-crashed")
        assert not (tmp_path / "tenants" / "brf-crashed").exists()

        with pytest.raises(RuntimeError, match="brf-crashed"):
            registry.get("brf-crashed")

        # And it must not have side-effected a directory into existence.
        assert not (tmp_path / "tenants" / "brf-crashed").exists()

    def test_get_with_origin_still_materializes_a_new_directory(self, tmp_path):
        # The ONE legitimate case: create()'s own eager-init call, which
        # always passes corpus_origin explicitly.
        auth = AuthStore(tmp_path / "auth.db")
        registry = TenantRegistry(tmp_path, auth)
        auth.create_tenant("Kund AB", "brf-fresh")
        assert not (tmp_path / "tenants" / "brf-fresh").exists()

        store = registry.get("brf-fresh", corpus_origin="customer")
        assert store is not None
        assert store.corpus_origin == "customer"
        assert (tmp_path / "tenants" / "brf-fresh").exists()

    def test_get_without_origin_opens_an_existing_directory_normally(self, tmp_path):
        # Regression, the ordinary path: create() already materialized the
        # directory, so a later plain get() (every real caller) just opens it.
        registry = _registry(tmp_path)
        registry.create("Test", "customer", "brf-a")
        registry2 = _registry(tmp_path)  # fresh instance, no in-memory cache
        store = registry2.get("brf-a")
        assert store is not None
        assert store.corpus_origin == "customer"


class TestLoudLoadFailures:
    """Finding: a malformed documents.json must raise a clear, actionable
    Swedish error naming the file and the tenant — never an unhandled
    traceback mid-__init__, never a silent skip."""

    def test_truncated_documents_json_raises_with_explicit_origin(self, tmp_path):
        (tmp_path / "documents.json").write_text('{"abc": {"id": "abc"', "utf-8")  # truncated JSON
        with pytest.raises(RuntimeError, match="documents.json"):
            Store(data_dir=tmp_path, corpus_origin="synthetic")

    def test_truncated_documents_json_raises_without_explicit_origin(self, tmp_path):
        # No tenant_meta.json and no corpus_origin argument routes through
        # the "is this tenant already migrated" check first, which reads the
        # same file — must fail exactly as loudly, not silently continue.
        (tmp_path / "documents.json").write_text('{"abc": {"id": "abc"', "utf-8")
        with pytest.raises(RuntimeError, match="documents.json"):
            Store(data_dir=tmp_path)


class TestMigrationWriteIsAtomic:
    """Finding: all writes to documents.json/tenant_meta.json go
    temp-file + os.replace in the same directory — a failure mid-write can
    never leave a truncated file behind; the ORIGINAL content survives
    intact."""

    def test_os_replace_failure_leaves_original_documents_json_intact(self, tmp_path, monkeypatch):
        # tenant_meta.json already exists and is valid, so the ONLY write
        # this Store construction attempts is the documents.json migration
        # write-back (a legacy entry missing corpus_origin).
        (tmp_path / "tenant_meta.json").write_text(json.dumps({"corpus_origin": "synthetic"}), "utf-8")
        original = json.dumps(
            {
                "abc123": {
                    "id": "abc123",
                    "name": "Legacy.pdf",
                    "pages": 1,
                    "words": 3,
                    "chunks": 1,
                    "uploaded_at": "2026-01-01T00:00:00+00:00",
                    "source": "digital",
                    # no corpus_origin — triggers the migration write-back.
                }
            }
        )
        (tmp_path / "documents.json").write_text(original, "utf-8")

        def _boom(*args, **kwargs):
            raise OSError("simulated os.replace failure")

        monkeypatch.setattr("os.replace", _boom)

        with pytest.raises(OSError):
            Store(data_dir=tmp_path)

        # The original file is untouched — no truncation, no partial write.
        assert (tmp_path / "documents.json").read_text("utf-8") == original
        # No leftover temp file either.
        leftovers = [p for p in tmp_path.iterdir() if p.name.startswith("documents.json.tmp-")]
        assert leftovers == []
