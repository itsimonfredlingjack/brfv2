"""Data lifecycle: hard delete leaves nothing behind; retention purges."""

from datetime import datetime, timedelta, timezone

import pytest

from app.auth import AuthStore
from app.registry import TenantRegistry
from app.schemas import Settings
from app.store import Store
from tests.pdf_fixtures import build_pdf


def _residue(root, brf_id: str) -> list[str]:
    """Every file left under a tenant's directory."""
    d = root / "tenants" / brf_id
    return [str(p.relative_to(root)) for p in d.rglob("*") if p.is_file()] if d.exists() else []


class TestDocumentHardDelete:
    def test_delete_removes_all_traces(self, tmp_path):
        auth = AuthStore(tmp_path / "auth.db")
        registry = TenantRegistry(tmp_path, auth)
        registry.create("Brf A", "synthetic", "brf-a")
        store = registry.get("brf-a")
        meta = store.add_document("Doc.pdf", build_pdf([[("Text att radera.", 72, 100)]]))
        pdf_path = tmp_path / "tenants" / "brf-a" / "docs" / f"{meta.id}.pdf"
        extract_path = tmp_path / "tenants" / "brf-a" / "extract" / f"{meta.id}.json"
        assert pdf_path.exists() and extract_path.exists()
        assert any(c.document_id == meta.id for c in store.chunks.values())

        assert store.delete_document(meta.id)
        assert not pdf_path.exists() and not extract_path.exists()
        assert not any(c.document_id == meta.id for c in store.chunks.values())
        assert meta.id not in store.documents
        # Reload from disk: still gone.
        reloaded = Store(data_dir=tmp_path / "tenants" / "brf-a")
        assert meta.id not in reloaded.documents
        assert all(c.document_id != meta.id for c in reloaded.chunks.values())


class TestTenantHardDelete:
    def test_delete_tenant_removes_files_index_and_memberships(self, tmp_path):
        auth = AuthStore(tmp_path / "auth.db")
        registry = TenantRegistry(tmp_path, auth)
        registry.create("Brf A", "synthetic", "brf-a")
        registry.create("Brf B", "synthetic", "brf-b")
        uid = auth.create_user("u@a.se", "lösenord-1", "U")
        auth.add_membership(uid, "brf-a", "admin")
        auth.add_membership(uid, "brf-b", "member")
        sa = registry.get("brf-a")
        sb = registry.get("brf-b")
        sa.add_document("A.pdf", build_pdf([[("Alfadata ALFA-1.", 72, 100)]]))
        sb.add_document("B.pdf", build_pdf([[("Betadata BETA-2.", 72, 100)]]))

        assert registry.delete("brf-a")

        # A: directory gone, membership gone, tenant row gone.
        assert _residue(tmp_path, "brf-a") == []
        assert not (tmp_path / "tenants" / "brf-a").exists()
        assert auth.get_tenant("brf-a") is None
        assert auth.role_for(uid, "brf-a") is None
        # B: completely untouched.
        assert auth.get_tenant("brf-b") is not None
        assert auth.role_for(uid, "brf-b") == "member"
        assert _residue(tmp_path, "brf-b")
        reloaded_b = Store(data_dir=tmp_path / "tenants" / "brf-b")
        assert len(reloaded_b.documents) == 1

    def test_deleted_tenant_not_recreated_by_registry_get(self, tmp_path):
        auth = AuthStore(tmp_path / "auth.db")
        registry = TenantRegistry(tmp_path, auth)
        registry.create("Brf A", "synthetic", "brf-a")
        registry.delete("brf-a")
        assert registry.get("brf-a") is None
        assert not (tmp_path / "tenants" / "brf-a").exists()


class TestRetention:
    def test_purge_expired_deletes_only_old_documents(self, tmp_path):
        store = Store(data_dir=tmp_path)
        store.update_settings(Settings(retentionDays=30))
        old = store.add_document("Old.pdf", build_pdf([[("Gammalt dokument.", 72, 100)]]))
        new = store.add_document("New.pdf", build_pdf([[("Nytt dokument.", 72, 100)]]))
        # Backdate 'old' past the window.
        store.documents[old.id].uploaded_at = (
            datetime.now(timezone.utc) - timedelta(days=40)
        ).isoformat(timespec="seconds")

        purged = store.purge_expired()
        assert purged == [old.id]
        assert old.id not in store.documents and new.id in store.documents
        assert not (tmp_path / "docs" / f"{old.id}.pdf").exists()

    def test_retention_zero_keeps_everything(self, tmp_path):
        store = Store(data_dir=tmp_path)
        store.update_settings(Settings(retentionDays=0))
        m = store.add_document("Keep.pdf", build_pdf([[("Behåll.", 72, 100)]]))
        store.documents[m.id].uploaded_at = (
            datetime.now(timezone.utc) - timedelta(days=9999)
        ).isoformat(timespec="seconds")
        assert store.purge_expired() == []
        assert m.id in store.documents

    def test_registry_purge_is_per_tenant(self, tmp_path):
        auth = AuthStore(tmp_path / "auth.db")
        registry = TenantRegistry(tmp_path, auth)
        registry.create("Brf A", "synthetic", "brf-a")
        registry.create("Brf B", "synthetic", "brf-b")
        sa, sb = registry.get("brf-a"), registry.get("brf-b")
        sa.update_settings(Settings(retentionDays=30))  # B keeps default 0
        ma = sa.add_document("A.pdf", build_pdf([[("A gammalt.", 72, 100)]]))
        mb = sb.add_document("B.pdf", build_pdf([[("B gammalt.", 72, 100)]]))
        for s, m in ((sa, ma), (sb, mb)):
            s.documents[m.id].uploaded_at = (
                datetime.now(timezone.utc) - timedelta(days=90)
            ).isoformat(timespec="seconds")

        purged = registry.purge_expired_all()
        assert purged == {"brf-a": [ma.id]}  # only A has a retention window
        assert mb.id in sb.documents
