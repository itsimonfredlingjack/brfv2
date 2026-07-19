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
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .auth import BRF_ID_RE, AuthStore
from .schemas import CORPUS_ORIGINS, CorpusOrigin
from .store import Store

logger = logging.getLogger("brf.registry")

_VAL_PREFIX = "val-"


def _check_naming(brf_id: str, corpus_origin: CorpusOrigin) -> None:
    """Naming rule (CI2): a tenant's id namespace must match its declared
    corpus, so the two are never accidentally out of sync. `synthetic` has no
    naming constraint (the two pre-existing demo tenants are grandfathered by
    virtue of that — there is nothing to grandfather, since synthetic origin
    was never naming-constrained)."""
    is_val = brf_id.startswith(_VAL_PREFIX)
    if corpus_origin == "public_scraped" and not is_val:
        raise ValueError(
            f"corpus_origin 'public_scraped' kräver ett brf_id som börjar med "
            f"'{_VAL_PREFIX}' (fick {brf_id!r})."
        )
    if corpus_origin == "customer" and is_val:
        raise ValueError(
            f"corpus_origin 'customer' får inte ha ett brf_id som börjar med "
            f"'{_VAL_PREFIX}' (fick {brf_id!r})."
        )


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

    def get(self, brf_id: str, *, corpus_origin: CorpusOrigin | None = None) -> Store | None:
        """The tenant's Store, or None for unknown/invalid ids.

        `corpus_origin` only matters the first time a given tenant's Store is
        constructed after this directory came into existence (i.e. right
        after `create()`) — once tenant_meta.json exists on disk it is
        authoritative and this argument is ignored (see
        Store._load_or_init_corpus_origin)."""
        if not BRF_ID_RE.match(brf_id or ""):
            return None
        with self._lock:
            store = self._stores.get(brf_id)
            if store is not None:
                return store
            if self.auth.get_tenant(brf_id) is None:
                return None
            store = Store(data_dir=self._tenant_dir(brf_id), corpus_origin=corpus_origin)
            self._stores[brf_id] = store
            return store

    def create(self, name: str, corpus_origin: CorpusOrigin, brf_id: str | None = None) -> str:
        """Create a new tenant. `corpus_origin` is REQUIRED — no default —
        every tenant must declare which of the three corpora (customer,
        public_scraped, synthetic) it is, up front, and the naming rule below
        keeps the id namespace honest about it."""
        if corpus_origin not in CORPUS_ORIGINS:
            raise ValueError(f"Ogiltigt corpus_origin: {corpus_origin!r} (tillåtna: {CORPUS_ORIGINS}).")
        brf_id = brf_id or uuid.uuid4().hex[:12]
        _check_naming(brf_id, corpus_origin)
        brf_id = self.auth.create_tenant(name, brf_id)
        self.get(brf_id, corpus_origin=corpus_origin)  # eager init so the directory exists immediately
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
