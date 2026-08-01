"""Per-tenant persistence for the integration domain.

Deliberately the same shape as :class:`app.store.Store`: JSON files inside the
tenant's own directory, written atomically, loaded on construction. That is not
imitation for its own sake — it is what makes tenant isolation inherited rather
than re-argued.

The isolation model in this backend is object-graph and filesystem separation,
not query filtering (see :mod:`app.registry`). A SQLite table of source events
keyed by ``tenant_id`` would have introduced the first shared collection in the
product, and with it the first place a missing ``WHERE`` clause could leak one
association's supplier invoices into another's queue. There is no such
collection here: a ``brf_id`` resolves to one directory, and that directory is
the only place its records exist. ``registry.delete()`` removes it with
everything else in it.

Layout, under ``tenants/<brf_id>/integrations/``::

    meta.json              {"schemaVersion": N}
    source-events.json     [SourceEvent, ...]
    invoices.json          [InvoiceSnapshot, ...]
    findings.json          [ReviewFinding, ...]

Migration is by explicit version number rather than by hoping every field has a
tolerant default. ``schemaVersion`` higher than this build understands is a
loud refusal, because opening a newer store read-write and writing it back is
how a downgrade silently deletes fields.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from pathlib import Path
from typing import Iterable, TypeVar

from pydantic import BaseModel, ValidationError

from .models import InvoiceSnapshot, ReviewFinding, SourceEvent

logger = logging.getLogger("brf.integrations")

SCHEMA_VERSION = 1

META_FILE = "meta.json"
SOURCE_EVENTS_FILE = "source-events.json"
INVOICES_FILE = "invoices.json"
FINDINGS_FILE = "findings.json"

T = TypeVar("T", bound=BaseModel)


class IntegrationError(RuntimeError):
    """Refusing to operate on this tenant's integration data."""


def _atomic_write_json(path: Path, payload) -> None:
    """Write JSON atomically, 0600.

    These files carry supplier names, amounts and message subjects — the same
    sensitivity class as the documents beside them, which is why the mode
    matches what ``desktop.py`` uses for its own configuration rather than the
    process umask.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp-{uuid.uuid4().hex[:8]}")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


class IntegrationStore:
    """Source events, invoice snapshots and findings for exactly one tenant."""

    def __init__(self, data_dir: str | Path, tenant_id: str) -> None:
        if not tenant_id:
            raise IntegrationError("IntegrationStore kräver ett tenant-id.")
        self.tenant_id = tenant_id
        self.dir = Path(data_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.dir, 0o700)
        except OSError:  # a filesystem that will not take the mode is not a reason to fail
            logger.debug("Kunde inte sätta 0700 på %s", self.dir)
        self.lock = threading.RLock()
        self._check_schema()

    # ---------- schema ----------

    def _check_schema(self) -> None:
        path = self.dir / META_FILE
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            _atomic_write_json(path, {"schemaVersion": SCHEMA_VERSION})
            return
        except (OSError, json.JSONDecodeError) as exc:
            raise IntegrationError(
                f"{path} går inte att läsa ({exc}) — vägrar öppna integrationsdata för "
                f"'{self.tenant_id}'. Undersök filen manuellt."
            ) from exc
        version = raw.get("schemaVersion") if isinstance(raw, dict) else None
        if version == SCHEMA_VERSION:
            return
        if isinstance(version, int) and version < SCHEMA_VERSION:
            self._migrate(version)
            _atomic_write_json(path, {"schemaVersion": SCHEMA_VERSION})
            return
        raise IntegrationError(
            f"Integrationsdata för '{self.tenant_id}' har schemaVersion {version!r}; "
            f"den här versionen förstår {SCHEMA_VERSION}. En nyare datakatalog får inte "
            "öppnas av en äldre installation — då skrivs fält bort."
        )

    def _migrate(self, from_version: int) -> None:
        """Bring an older layout forward. No older version exists yet.

        The branch is here rather than added later on purpose: the first
        migration is written when there is nothing at stake, and the shape it
        establishes — read all, transform, write all, then bump — is the shape
        the second one copies.
        """
        logger.info(
            "Migrerar integrationsdata för %s från schemaVersion %d till %d.",
            self.tenant_id,
            from_version,
            SCHEMA_VERSION,
        )

    # ---------- generic io ----------

    def _read(self, filename: str, model: type[T]) -> list[T]:
        path = self.dir / filename
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return []
        except (OSError, json.JSONDecodeError) as exc:
            raise IntegrationError(f"{path} går inte att läsa: {exc}") from exc
        if not isinstance(raw, list):
            raise IntegrationError(f"{path} innehåller inte en lista.")
        rows: list[T] = []
        for entry in raw:
            try:
                record = model.model_validate(entry)
            except ValidationError as exc:
                raise IntegrationError(f"Ogiltig post i {path}: {exc}") from exc
            # Belt and braces: a record whose tenant_id does not match the
            # directory it was loaded from means something copied data between
            # tenants. There is no code path that does that, which is exactly
            # why it must fail loudly if one ever appears.
            if getattr(record, "tenant_id", self.tenant_id) != self.tenant_id:
                raise IntegrationError(
                    f"{path} innehåller en post för tenant "
                    f"{getattr(record, 'tenant_id')!r} i {self.tenant_id!r}s katalog."
                )
            rows.append(record)
        return rows

    def _write(self, filename: str, rows: Iterable[BaseModel]) -> None:
        _atomic_write_json(
            self.dir / filename, [row.model_dump(mode="json") for row in rows]
        )

    def _stamp(self, record: T) -> T:
        """Force the tenant id from the directory, never from the caller.

        Same discipline as ``Store.add_document`` and ``corpus_origin``: there
        is no argument to abuse, because the value is not taken from an
        argument.
        """
        return record.model_copy(update={"tenant_id": self.tenant_id})

    # ---------- source events ----------

    def list_source_events(self) -> list[SourceEvent]:
        with self.lock:
            rows = self._read(SOURCE_EVENTS_FILE, SourceEvent)
        return sorted(rows, key=lambda e: e.received_at, reverse=True)

    def get_source_event(self, event_id: str) -> SourceEvent | None:
        return next((e for e in self.list_source_events() if e.id == event_id), None)

    def find_source_event_by_hash(self, content_sha256: str) -> SourceEvent | None:
        return next(
            (e for e in self.list_source_events() if e.content_sha256 == content_sha256),
            None,
        )

    def add_source_event(self, event: SourceEvent) -> SourceEvent:
        with self.lock:
            rows = self._read(SOURCE_EVENTS_FILE, SourceEvent)
            record = self._stamp(event)
            if any(r.id == record.id for r in rows):
                raise IntegrationError(f"Källhändelsen {record.id} finns redan.")
            rows.append(record)
            self._write(SOURCE_EVENTS_FILE, rows)
        return record

    def update_source_event(self, event: SourceEvent) -> SourceEvent:
        with self.lock:
            rows = self._read(SOURCE_EVENTS_FILE, SourceEvent)
            record = self._stamp(event)
            for i, existing in enumerate(rows):
                if existing.id == record.id:
                    rows[i] = record
                    break
            else:
                raise IntegrationError(f"Okänd källhändelse: {record.id}")
            self._write(SOURCE_EVENTS_FILE, rows)
        return record

    def delete_source_event(self, event_id: str) -> bool:
        with self.lock:
            rows = self._read(SOURCE_EVENTS_FILE, SourceEvent)
            remaining = [r for r in rows if r.id != event_id]
            if len(remaining) == len(rows):
                return False
            self._write(SOURCE_EVENTS_FILE, remaining)
        return True

    # ---------- invoices ----------

    def list_invoices(self) -> list[InvoiceSnapshot]:
        with self.lock:
            rows = self._read(INVOICES_FILE, InvoiceSnapshot)
        return sorted(rows, key=lambda i: (i.invoice_date or "", i.external_ref))

    def get_invoice(self, invoice_id: str) -> InvoiceSnapshot | None:
        return next((i for i in self.list_invoices() if i.id == invoice_id), None)

    def upsert_invoice(self, invoice: InvoiceSnapshot) -> InvoiceSnapshot:
        """Store a snapshot, replacing any earlier read of the same reference.

        Upsert rather than append because a snapshot is a *picture at a time*,
        not an event: reading the same invoice twice should leave one row that
        says what the source system currently says, not two rows that a reviewer
        has to reconcile.
        """
        with self.lock:
            rows = self._read(INVOICES_FILE, InvoiceSnapshot)
            record = self._stamp(invoice)
            key = (record.adapter, record.external_ref)
            rows = [r for r in rows if (r.adapter, r.external_ref) != key]
            rows.append(record)
            self._write(INVOICES_FILE, rows)
        return record

    # ---------- findings ----------

    def list_findings(self) -> list[ReviewFinding]:
        with self.lock:
            rows = self._read(FINDINGS_FILE, ReviewFinding)
        return sorted(rows, key=lambda f: f.created_at, reverse=True)

    def get_finding(self, finding_id: str) -> ReviewFinding | None:
        return next((f for f in self.list_findings() if f.id == finding_id), None)

    def replace_findings_for_invoice(
        self, invoice_id: str, findings: Iterable[ReviewFinding]
    ) -> list[ReviewFinding]:
        """Re-running a review supersedes its previous open findings.

        Findings a human has already acted on are kept: an approved or dismissed
        finding is a record of a decision, and a fresh run must not erase the
        decision it was made against. Only ``open`` ones — nobody's work — are
        replaced.
        """
        with self.lock:
            rows = self._read(FINDINGS_FILE, ReviewFinding)
            kept = [
                f
                for f in rows
                if not (f.invoice_id == invoice_id and f.status == "open")
            ]
            fresh = [self._stamp(f) for f in findings]
            self._write(FINDINGS_FILE, kept + fresh)
        return fresh

    def update_finding(self, finding: ReviewFinding) -> ReviewFinding:
        with self.lock:
            rows = self._read(FINDINGS_FILE, ReviewFinding)
            record = self._stamp(finding)
            for i, existing in enumerate(rows):
                if existing.id == record.id:
                    rows[i] = record
                    break
            else:
                raise IntegrationError(f"Okänt fynd: {record.id}")
            self._write(FINDINGS_FILE, rows)
        return record
