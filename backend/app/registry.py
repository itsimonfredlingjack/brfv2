"""TenantRegistry — one fully isolated Store per BRF.

Isolation model (SPEC-PILOT §2): object-graph + filesystem separation, not
query filtering. Each tenant's PDFs, extraction JSON, settings, chunks,
embeddings and hybrid index live in their own Store under
data_root/tenants/<brf_id>/. There is no shared collection to filter and no
retrieval path that spans tenants — a request first resolves an
authenticated membership to a brf_id, and only then reaches that tenant's
Store. The auth database is the source of truth for which tenants exist.
"""

from __future__ import annotations

import logging
import shutil
import threading
from datetime import datetime, timezone
from pathlib import Path

from .auth import BRF_ID_RE, AuthStore
from .store import Store

logger = logging.getLogger("brf.registry")


class TenantRegistry:
    def __init__(self, data_root: str | Path, auth: AuthStore) -> None:
        self.data_root = Path(data_root)
        self.tenants_dir = self.data_root / "tenants"
        self.tenants_dir.mkdir(parents=True, exist_ok=True)
        self.auth = auth
        self._stores: dict[str, Store] = {}
        self._lock = threading.Lock()

    def _tenant_dir(self, brf_id: str) -> Path:
        # brf_id is validated against BRF_ID_RE before any path use — no
        # separators, no dots — so it cannot traverse out of tenants_dir.
        return self.tenants_dir / brf_id

    def get(self, brf_id: str) -> Store | None:
        """The tenant's Store, or None for unknown/invalid ids."""
        if not BRF_ID_RE.match(brf_id or ""):
            return None
        with self._lock:
            store = self._stores.get(brf_id)
            if store is not None:
                return store
            if self.auth.get_tenant(brf_id) is None:
                return None
            store = Store(data_dir=self._tenant_dir(brf_id))
            self._stores[brf_id] = store
            return store

    def create(self, name: str, brf_id: str | None = None) -> str:
        brf_id = self.auth.create_tenant(name, brf_id)
        self.get(brf_id)  # eager init so the directory exists immediately
        return brf_id

    def delete(self, brf_id: str) -> bool:
        """Hard-delete a tenant: in-memory store, every file on disk, and the
        auth rows (memberships cascade). Irreversible."""
        if not BRF_ID_RE.match(brf_id or ""):
            return False
        existed = self.auth.get_tenant(brf_id) is not None
        with self._lock:
            self._stores.pop(brf_id, None)
        shutil.rmtree(self._tenant_dir(brf_id), ignore_errors=True)
        self.auth.delete_tenant(brf_id)
        if existed:
            logger.info("Tenant %s hårdraderad (filer + index + medlemskap)", brf_id)
        return existed

    def list(self) -> list[dict]:
        return self.auth.list_tenants()

    def purge_expired_all(self, now: datetime | None = None) -> dict[str, list[str]]:
        """Apply each tenant's retention window. Returns {brf_id: [doc_ids]}."""
        now = now or datetime.now(timezone.utc)
        purged: dict[str, list[str]] = {}
        for t in self.auth.list_tenants():
            store = self.get(t["brf_id"])
            if store is None:
                continue
            doomed = store.purge_expired(now)
            if doomed:
                purged[t["brf_id"]] = doomed
        return purged
