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
    invoice-cases.json     [InvoiceCase, ...]
    analysis-runs.json     [AnalysisRun, ...]      append-only

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

from ..invoices.models import AnalysisRun, InvoiceCase
from .models import (
    InvoiceSnapshot,
    MailboxCheckpoint,
    ReviewFinding,
    SourceEvent,
    SupplierAlias,
    finding_content_key,
)

logger = logging.getLogger("brf.integrations")

# 2 adds three things a version-1 build does not know about: an attachment's
# adoption into the archive, a finding's anchor strength, and the supplier
# alias file. All three are additive and load fine here — but a version-1
# build that opened this directory would read a source event, drop
# `archived`/`archived_by`/`archived_at` as unknown fields, and write it back
# without them. An adopted document would silently stop being evidence and
# nobody would see it happen. That is precisely what the version refusal is
# for, so the number goes up.
#
# 3 is the intake queue: a source event now carries its thread key, its triage
# suggestion, the human's confirmation of it, how it was resolved, and the
# document its text was preserved as. The same argument applies with more
# force — a version-2 build that read one of these events and wrote it back
# would drop `resolution` and `preserved_document_id`, which would turn a
# settled queue item back into an open one and orphan a document in the
# archive with nothing pointing at it.
#
# 4 is the invoice workspace: a new file of :class:`~app.invoices.models.InvoiceCase`
# records, and a ``source_status`` on the invoice snapshot carrying what the
# accounting system said about its own record. The argument is the same and the
# stakes are higher than they look — an invoice case holds the association's own
# review status, its comments and its timeline, and a version-3 build that read
# one back would drop every one of them. It cannot read the file at all, which
# is the point of refusing a newer directory outright.
#
# 5 is the analysis audit trail: a new append-only file of
# :class:`~app.invoices.models.AnalysisRun` records, and three fields on the
# invoice case naming which run the current findings came out of. The argument
# for the bump is the sharpest one yet — a version-4 build would read a case,
# drop `analysis_run_id`, and write it back, severing the only link between
# what is on screen and the record of what it replaced. An audit trail that a
# downgrade can quietly detach is not one.
SCHEMA_VERSION = 5

META_FILE = "meta.json"
SOURCE_EVENTS_FILE = "source-events.json"
INVOICES_FILE = "invoices.json"
FINDINGS_FILE = "findings.json"
SUPPLIER_ALIASES_FILE = "supplier-aliases.json"
MAILBOX_FILE = "mailbox-checkpoints.json"
INVOICE_CASES_FILE = "invoice-cases.json"
ANALYSIS_RUNS_FILE = "analysis-runs.json"

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
        self._credentials = None
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
        """Bring an older layout forward.

        1 → 2 is additive: every new field has a default that means "this never
        happened" — an attachment that was never adopted, a finding whose
        anchor was not recorded, an empty alias file. So the transformation is
        the identity and the work is re-writing each file through the current
        models, which is what makes the new fields present on disk rather than
        implied. Doing it eagerly matters: a half-migrated directory where some
        events have the field and some do not is the state that makes the next
        migration hard to reason about.

        2 → 3 is additive in the same way, with one thing worth stating: an
        event from an older build gets ``thread_key=""`` rather than a computed
        one. Computing it here would mean deciding a message's conversation
        from a migration, quietly, months after it arrived; instead
        :func:`app.integrations.threads.build_threads` groups an empty key by
        subject at read time, so an existing queue reads correctly and nothing
        was decided on anybody's behalf.

        3 → 4 is additive again, and needs no transformation at all: an invoice
        read by an older build simply has no ``source_status``, which is the
        correct record of a build that never asked for one, and there were no
        invoice cases before this version. Rewriting the files is still done
        eagerly for the reason above — a directory where some records have the
        field and some do not is the state that makes the next migration hard.

        4 → 5 adds the analysis audit trail, and the one thing worth stating is
        what is *not* invented: a case migrated from 4 has findings but no
        recorded run, and gets ``analysis_run_id=""`` rather than a fabricated
        run built from whatever is on disk. The next analysis records run 1 and
        carries the findings it replaced, saying in as many words that what
        came before them was never recorded. Back-dating a run here would put a
        row in an audit trail that describes a run nobody observed.
        """
        logger.info(
            "Migrerar integrationsdata för %s från schemaVersion %d till %d.",
            self.tenant_id,
            from_version,
            SCHEMA_VERSION,
        )
        if from_version < 4:
            for filename, model in (
                (SOURCE_EVENTS_FILE, SourceEvent),
                (INVOICES_FILE, InvoiceSnapshot),
                (FINDINGS_FILE, ReviewFinding),
            ):
                if (self.dir / filename).exists():
                    self._write(filename, self._read(filename, model))
        if from_version < 5 and (self.dir / INVOICE_CASES_FILE).exists():
            self._write(INVOICE_CASES_FILE, self._read(INVOICE_CASES_FILE, InvoiceCase))

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

    # ---------- mailbox checkpoints ----------

    def get_mailbox_checkpoint(self, provider: str, folder: str) -> MailboxCheckpoint:
        """Where the last fetch of this folder got to. Never ``None``.

        A tenant that has never fetched gets an empty checkpoint rather than
        nothing, because "we have not looked yet" and "we looked and found
        nothing" are different sentences on the screen and the caller should
        not have to invent the first one.

        Keyed by provider *and* folder: pointing an installation at ``archive``
        after reading ``inbox`` must not make it believe it has already seen
        everything in the new folder.
        """
        key = (provider, folder)
        with self.lock:
            rows = self._read(MAILBOX_FILE, MailboxCheckpoint)
        for row in rows:
            if (row.provider, row.folder) == key:
                return row
        return MailboxCheckpoint(provider=provider, folder=folder)

    def put_mailbox_checkpoint(self, checkpoint: MailboxCheckpoint) -> MailboxCheckpoint:
        with self.lock:
            rows = self._read(MAILBOX_FILE, MailboxCheckpoint)
            key = (checkpoint.provider, checkpoint.folder)
            rows = [r for r in rows if (r.provider, r.folder) != key]
            rows.append(checkpoint)
            self._write(MAILBOX_FILE, rows)
        return checkpoint

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

        The **identity is kept** across re-reads. An adapter mints a fresh
        ``id`` every time it maps a payload, so without this a second read of
        the same invoice would replace the row with one under a new id — and
        every finding, every case and every task that pointed at the old id
        would be left pointing at nothing. Re-reading an invoice is the most
        ordinary thing an operator does on this screen; it must not quietly
        orphan the review that was done on it.
        """
        with self.lock:
            rows = self._read(INVOICES_FILE, InvoiceSnapshot)
            record = self._stamp(invoice)
            key = (record.adapter, record.external_ref)
            existing = next((r for r in rows if (r.adapter, r.external_ref) == key), None)
            if existing is not None:
                record = record.model_copy(update={"id": existing.id})
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

        A produced finding that repeats, word for word, one of those decisions
        is **not** written beside it. Without this, dismissing a finding and
        pressing refresh left the invoice carrying the same sentence twice —
        once marked "avfärdad" and once "öppen" — and the reviewer had to work
        out that the second one was the first one coming back. A decision
        covers the statement it was made about; the engine still saying it is
        recorded on the analysis run
        (:attr:`~app.invoices.models.AnalysisRun.already_decided_count`) rather
        than as a second card.

        Returns what was actually written, which is what the audit trail
        records as this run's output.
        """
        with self.lock:
            rows = self._read(FINDINGS_FILE, ReviewFinding)
            kept = [
                f
                for f in rows
                if not (f.invoice_id == invoice_id and f.status == "open")
            ]
            decided = {
                finding_content_key(f)
                for f in kept
                if f.invoice_id == invoice_id and f.status != "open"
            }
            fresh = [
                self._stamp(f) for f in findings if finding_content_key(f) not in decided
            ]
            self._write(FINDINGS_FILE, kept + fresh)
        return fresh

    # ---------- invoice cases ----------
    #
    # The case is the *only* record in this store a human writes prose into —
    # a review status, a note, a comment. It lives here rather than in its own
    # directory for the same reason everything else does: one `brf_id` resolves
    # to one directory, and `registry.delete()` sweeps it without anyone having
    # to remember a second place.

    def list_invoice_cases(self) -> list[InvoiceCase]:
        """Newest activity first — a board reads what moved, not what was filed."""
        with self.lock:
            rows = self._read(INVOICE_CASES_FILE, InvoiceCase)
        return sorted(rows, key=lambda c: c.last_activity_at(), reverse=True)

    def get_invoice_case(self, case_id: str) -> InvoiceCase | None:
        return next((c for c in self.list_invoice_cases() if c.id == case_id), None)

    def find_invoice_case(self, case_key: str) -> InvoiceCase | None:
        """The case a new observation converges on, by its deterministic key."""
        if not case_key:
            return None
        return next((c for c in self.list_invoice_cases() if c.case_key == case_key), None)

    def upsert_invoice_case(self, case: InvoiceCase) -> InvoiceCase:
        """Write a case, replacing the row with the same id.

        Upsert on ``id`` and not on ``case_key``: two cases must never share a
        key, and if one day they somehow did, silently collapsing them here
        would destroy one association's review notes without anybody seeing it
        happen. :mod:`app.invoices.cases` is the only writer and resolves by key
        before it calls this.
        """
        with self.lock:
            rows = self._read(INVOICE_CASES_FILE, InvoiceCase)
            record = self._stamp(case)
            for i, existing in enumerate(rows):
                if existing.id == record.id:
                    if len(record.timeline) < len(existing.timeline):
                        # Same rule as the task store: the timeline is the audit
                        # trail, and a shorter one means somebody wrote over
                        # history rather than adding to it.
                        raise IntegrationError(
                            f"Fakturaärendet {record.id} skulle skrivas med kortare historik "
                            "än den redan har. Historiken är append-only."
                        )
                    rows[i] = record
                    break
            else:
                rows.append(record)
            self._write(INVOICE_CASES_FILE, rows)
        return record

    # ---------- analysis runs ----------
    #
    # The one collection in this store that is append-only in the strong sense:
    # no upsert, no update, no delete. A record of what an analysis replaced is
    # worth exactly as much as the guarantee that it was not edited afterwards,
    # and a method that could edit one is the guarantee gone. Removing the
    # tenant removes these with everything else, which is the only deletion
    # there is.

    def list_analysis_runs(self, invoice_id: str = "") -> list[AnalysisRun]:
        """Recorded runs, oldest first — this is a history, and it reads forwards."""
        with self.lock:
            rows = self._read(ANALYSIS_RUNS_FILE, AnalysisRun)
        if invoice_id:
            rows = [r for r in rows if r.invoice_id == invoice_id]
        return sorted(rows, key=lambda r: (r.sequence, r.ran_at))

    def get_analysis_run(self, run_id: str) -> AnalysisRun | None:
        return next((r for r in self.list_analysis_runs() if r.id == run_id), None)

    def latest_analysis_run(self, invoice_id: str) -> AnalysisRun | None:
        rows = self.list_analysis_runs(invoice_id)
        return rows[-1] if rows else None

    def append_analysis_run(self, run: AnalysisRun) -> AnalysisRun:
        """Write one run. Refuses to touch a run that is already recorded.

        The id is derived from what the run is — its rules, its reading, its
        result and the run it superseded (:func:`app.invoices.audit.run_id_for`)
        — so a second write under the same id is either a duplicate that should
        do nothing, or a rewrite of history. It cannot be both, and this returns
        the existing record rather than deciding: the caller writes under the
        lock it already holds, so the only way to arrive here twice with the
        same id is to have computed the identical run twice.
        """
        with self.lock:
            rows = self._read(ANALYSIS_RUNS_FILE, AnalysisRun)
            existing = next((r for r in rows if r.id == run.id), None)
            if existing is not None:
                return existing
            record = self._stamp(run)
            rows.append(record)
            self._write(ANALYSIS_RUNS_FILE, rows)
        return record

    # ---------- supplier aliases ----------

    def list_supplier_aliases(self) -> list[SupplierAlias]:
        with self.lock:
            rows = self._read(SUPPLIER_ALIASES_FILE, SupplierAlias)
        return sorted(rows, key=lambda a: (a.normalized_key, a.document_name))

    def aliases_for(self, invoice_supplier_name: str) -> list[SupplierAlias]:
        """Aliases a human recorded for this supplier, by normalised name.

        Matching on the normalised key rather than the literal string is what
        makes an alias survive the invoice being written "Snösvängen AB" one
        month and "Snösvängen  AB." the next.
        """
        from .supplier import normalize

        key = normalize(invoice_supplier_name)
        if not key:
            return []
        return [a for a in self.list_supplier_aliases() if a.normalized_key == key]

    def add_supplier_alias(self, alias: SupplierAlias) -> SupplierAlias:
        with self.lock:
            rows = self._read(SUPPLIER_ALIASES_FILE, SupplierAlias)
            record = self._stamp(alias)
            from .supplier import normalize

            duplicate = normalize(record.document_name)
            for existing in rows:
                if (
                    existing.normalized_key == record.normalized_key
                    and normalize(existing.document_name) == duplicate
                ):
                    return existing
            rows.append(record)
            self._write(SUPPLIER_ALIASES_FILE, rows)
        return record

    def delete_supplier_alias(self, alias_id: str) -> bool:
        with self.lock:
            rows = self._read(SUPPLIER_ALIASES_FILE, SupplierAlias)
            remaining = [a for a in rows if a.id != alias_id]
            if len(remaining) == len(rows):
                return False
            self._write(SUPPLIER_ALIASES_FILE, remaining)
        return True

    # ---------- credentials ----------

    @property
    def credentials(self):
        """Live-integration connections and secrets, in this tenant's directory.

        Lazy and cached for the same reason ``Store.integrations`` is: building
        it touches the filesystem, and a tenant that never connects anything
        should never grow the directory.
        """
        if getattr(self, "_credentials", None) is None:
            from .credentials import CredentialStore

            self._credentials = CredentialStore(self.dir, tenant_id=self.tenant_id)
        return self._credentials

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
