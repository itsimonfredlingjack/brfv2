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
from typing import Callable, Iterable, TypeVar

from pydantic import BaseModel, ValidationError

from ..history import AppendOnlyViolation, check_append_only
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
#
# 6 adds the decision history a reopen no longer throws away
# (:class:`~app.integrations.models.DecisionRecord`), the idempotency key on a
# resolution, and the mailbox checkpoint's retry floor. The version bump is
# load-bearing for the first of those in a way the others are not: a version-5
# build that read a reopened event and wrote it back would drop
# `decision_history` — which is to say it would finish the erasure this version
# exists to stop, and leave no trace that it had. The migration invents nothing;
# an event that was reopened under version 5 has a history that is genuinely
# gone, and a fabricated record of a decision nobody can now describe would be
# worse than an empty list.
SCHEMA_VERSION = 6

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


class SourceEventNotFound(IntegrationError):
    """No queue item with that id here. Its own type so a route can answer 404
    for that alone, and not for every other refusal this store makes."""


class FindingNotFound(IntegrationError):
    """No finding with that id here. Same argument as :class:`SourceEventNotFound`."""


class DuplicateContent(IntegrationError):
    """These exact bytes are already in this tenant's queue.

    Raised from inside :meth:`IntegrationStore.add_source_event`, under the
    lock, which is the only place the answer cannot go stale between being
    computed and being acted on. :func:`app.integrations.intake.import_eml`
    turns it into the ``DuplicateSourceEvent`` its callers already handle.
    """

    def __init__(self, existing: SourceEvent) -> None:
        super().__init__(
            f"Meddelandet är redan importerat ({existing.received_at}) som {existing.id}."
        )
        self.existing = existing


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

        5 → 6 is additive with the same discipline. An event migrated from 5
        gets an empty ``decision_history`` and a resolution with an empty
        ``key``. Both are honest: a settlement reopened under version 5 was
        deleted rather than filed, and there is nothing left to reconstruct it
        from; a resolution written under 5 has no idempotency key, so a replay
        of it cannot be recognised and is treated as a fresh act — which is the
        old behaviour, correctly preserved rather than guessed at. The mailbox
        checkpoints are rewritten so ``retry_from`` is present on disk rather
        than implied.
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
        if from_version < 6:
            for filename, model in (
                (SOURCE_EVENTS_FILE, SourceEvent),
                (MAILBOX_FILE, MailboxCheckpoint),
            ):
                if (self.dir / filename).exists():
                    self._write(filename, self._read(filename, model))

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
        """Write one event, refusing a second one for the same bytes.

        Two guards, and they answer different questions. The id guard catches a
        second write of the *same event*; the content-hash guard catches a
        second import of the *same message* under a different id. Both live
        inside the lock, which is the repair: the hash check used to sit in
        :func:`app.integrations.intake.import_eml` before this call, and eight
        concurrent imports of one MIME message all read "no duplicate" before
        any of them wrote, then appended seven or eight separate events with
        seven or eight random ids.

        The caller now also derives the id from the content hash, so the two
        guards agree even across processes, where a lock cannot reach.
        """
        with self.lock:
            rows = self._read(SOURCE_EVENTS_FILE, SourceEvent)
            record = self._stamp(event)
            if any(r.id == record.id for r in rows):
                raise IntegrationError(f"Källhändelsen {record.id} finns redan.")
            clash = next(
                (r for r in rows if record.content_sha256 and r.content_sha256 == record.content_sha256),
                None,
            )
            if clash is not None:
                raise DuplicateContent(clash)
            rows.append(record)
            self._write(SOURCE_EVENTS_FILE, rows)
        return record

    def mutate_source_event(
        self, event_id: str, apply: Callable[[SourceEvent], SourceEvent]
    ) -> SourceEvent:
        """Change one queue item across a single locked read-modify-write.

        The same repair as :meth:`app.tasks.store.TaskStore.mutate_task` and
        :func:`app.invoices.cases.mutate`, and the reason it is needed here is
        that a queue item is touched from more directions than anything else in
        the product: a decision, a triage refresh, a confirmation, an
        attachment adoption, a preservation, a resolution. Each of those used to
        read the event, build a complete replacement, and write it back — so a
        triage refresh landing between another request's read and write silently
        discarded the confirmation that request had just recorded.
        """
        with self.lock:
            rows = self._read(SOURCE_EVENTS_FILE, SourceEvent)
            for i, existing in enumerate(rows):
                if existing.id != event_id:
                    continue
                record = self._stamp(apply(existing))
                if record.id != existing.id:
                    raise IntegrationError(
                        f"En ändring av {event_id} får inte byta id till {record.id}."
                    )
                try:
                    check_append_only(
                        existing.decision_history,
                        record.decision_history,
                        what="Källhändelsen",
                    )
                except AppendOnlyViolation as exc:
                    raise IntegrationError(str(exc)) from exc
                rows[i] = record
                self._write(SOURCE_EVENTS_FILE, rows)
                return record
        raise SourceEventNotFound(f"Okänd källhändelse: {event_id}")

    def update_source_event(self, event: SourceEvent) -> SourceEvent:
        """Replace an event with a version the caller already holds.

        Prefer :meth:`mutate_source_event`. Kept because several callers already
        hold a version they built under this store's lock, and because the
        append-only check on ``decision_history`` now refuses the stale-object
        case this used to wave through.
        """
        return self.mutate_source_event(event.id, lambda _existing: event)

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
        """Record where a fetch got to. Merged under the lock, never replaced.

        Two fetches of the same folder can overlap — nothing stops an operator
        pressing "hämta nytt" twice, and the second request does not wait for
        the first. Whichever *finished* last used to win outright, so a slow
        fetch that started earlier and read less could push the mark back over
        material already dealt with, and the queue re-presented a fortnight of
        it. Merging fixes that without a second lock: the mark takes the later
        of the two.

        ``retry_from`` merges the other way, to the **earlier** of the two
        non-empty values, because it is a debt rather than a position. If either
        fetch could not read a message, that message is still owed, and the
        conservative answer is the one that re-reads more. It is only cleared by
        a caller that passes an empty value *and* has itself stalled on nothing
        — expressed here as: an empty incoming value clears it, because the
        fetch that wrote it saw the whole window it asked for.
        """
        with self.lock:
            rows = self._read(MAILBOX_FILE, MailboxCheckpoint)
            key = (checkpoint.provider, checkpoint.folder)
            existing = next((r for r in rows if (r.provider, r.folder) == key), None)
            merged = checkpoint
            if existing is not None:
                retry = checkpoint.retry_from
                if retry and existing.retry_from:
                    retry = min(retry, existing.retry_from)
                merged = checkpoint.model_copy(
                    update={
                        "high_water_mark": max(
                            existing.high_water_mark, checkpoint.high_water_mark
                        ),
                        "retry_from": retry,
                    }
                )
            rows = [r for r in rows if (r.provider, r.folder) != key]
            rows.append(merged)
            self._write(MAILBOX_FILE, rows)
        return merged

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
        should never grow the directory. Constructed under this store's lock,
        double-checked, for the same reason too — a check-then-set here would
        hand two concurrent callers two ``CredentialStore`` objects with two
        different locks over one ``connections.json``, and a token refresh
        racing a disconnect would be writing under neither.
        """
        current = getattr(self, "_credentials", None)
        if current is not None:
            return current
        with self.lock:
            if getattr(self, "_credentials", None) is None:
                from .credentials import CredentialStore

                self._credentials = CredentialStore(self.dir, tenant_id=self.tenant_id)
            return self._credentials

    def mutate_finding(
        self, finding_id: str, apply: Callable[[ReviewFinding], ReviewFinding]
    ) -> ReviewFinding:
        """Change one finding across a single locked read-modify-write.

        A finding is decided by one person at a time in practice, but "in
        practice" is not the guarantee: an analysis re-run
        (``replace_findings_for_invoice``) touches the same file, and a decision
        built from a finding read before that run could put a superseded
        statement back on the invoice under a fresh "approved".
        """
        with self.lock:
            rows = self._read(FINDINGS_FILE, ReviewFinding)
            for i, existing in enumerate(rows):
                if existing.id != finding_id:
                    continue
                record = self._stamp(apply(existing))
                if record.id != existing.id:
                    raise IntegrationError(
                        f"En ändring av {finding_id} får inte byta id till {record.id}."
                    )
                rows[i] = record
                self._write(FINDINGS_FILE, rows)
                return record
        raise FindingNotFound(f"Okänt fynd: {finding_id}")

    def update_finding(self, finding: ReviewFinding) -> ReviewFinding:
        """Replace a finding with a version the caller holds. Prefer
        :meth:`mutate_finding`, which cannot be handed a stale one."""
        return self.mutate_finding(finding.id, lambda _existing: finding)
