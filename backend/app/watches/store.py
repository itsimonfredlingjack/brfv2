"""Per-tenant persistence for watches. Same shape, same isolation, as everything else.

JSON files in the tenant's own directory, written atomically at ``0600``.
``registry.delete()`` sweeps them with the rest, and there is no shared
collection anywhere that a missing ``WHERE`` could leak across — see
:mod:`app.integrations.store` for the argument, which applies here unchanged.
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

from .models import UnresolvedObligation, Watch

logger = logging.getLogger("brf.watches")

# 2 adds two watch kinds that no document scan produces — "stated_deadline"
# and "expected_reply", both created from reviewed incoming post. Additive, and
# the version still goes up: a version-1 build reading one of these would fail
# validation on the unknown kind, and the loud refusal in _check_schema is a
# far better failure than a store that will not open with a pydantic
# traceback.
SCHEMA_VERSION = 2

META_FILE = "meta.json"
WATCHES_FILE = "watches.json"
UNRESOLVED_FILE = "unresolved.json"

T = TypeVar("T", bound=BaseModel)


class WatchError(RuntimeError):
    """Refusing to operate on this tenant's watch data."""


class WatchNotFound(WatchError):
    """No watch with that id here — its own type so a route can answer 404
    for that and not for every other refusal this store makes."""


def _atomic_write_json(path: Path, payload) -> None:
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


class WatchStore:
    """Watches and unresolved obligations for exactly one tenant."""

    def __init__(self, data_dir: str | Path, tenant_id: str) -> None:
        if not tenant_id:
            raise WatchError("WatchStore kräver ett tenant-id.")
        self.tenant_id = tenant_id
        self.dir = Path(data_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.dir, 0o700)
        except OSError:  # pragma: no cover
            logger.debug("Kunde inte sätta 0700 på %s", self.dir)
        self.lock = threading.RLock()
        self._check_schema()

    def _check_schema(self) -> None:
        path = self.dir / META_FILE
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            _atomic_write_json(path, {"schemaVersion": SCHEMA_VERSION})
            return
        except (OSError, json.JSONDecodeError) as exc:
            raise WatchError(
                f"{path} går inte att läsa ({exc}) — vägrar öppna bevakningsdata för "
                f"'{self.tenant_id}'."
            ) from exc
        version = raw.get("schemaVersion") if isinstance(raw, dict) else None
        if version == SCHEMA_VERSION:
            return
        if isinstance(version, int) and version < SCHEMA_VERSION:  # pragma: no cover
            _atomic_write_json(path, {"schemaVersion": SCHEMA_VERSION})
            return
        raise WatchError(
            f"Bevakningsdata för '{self.tenant_id}' har schemaVersion {version!r}; den här "
            f"versionen förstår {SCHEMA_VERSION}. En nyare datakatalog får inte öppnas av en "
            "äldre installation — då skrivs fält bort."
        )

    # ---------- generic io ----------

    def _read(self, filename: str, model: type[T]) -> list[T]:
        path = self.dir / filename
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return []
        except (OSError, json.JSONDecodeError) as exc:
            raise WatchError(f"{path} går inte att läsa: {exc}") from exc
        if not isinstance(raw, list):
            raise WatchError(f"{path} innehåller inte en lista.")
        rows: list[T] = []
        for entry in raw:
            try:
                record = model.model_validate(entry)
            except ValidationError as exc:
                raise WatchError(f"Ogiltig post i {path}: {exc}") from exc
            if getattr(record, "tenant_id", self.tenant_id) != self.tenant_id:
                raise WatchError(
                    f"{path} innehåller en post för tenant "
                    f"{getattr(record, 'tenant_id')!r} i {self.tenant_id!r}s katalog."
                )
            rows.append(record)
        return rows

    def _write(self, filename: str, rows: Iterable[BaseModel]) -> None:
        _atomic_write_json(self.dir / filename, [row.model_dump(mode="json") for row in rows])

    def _stamp(self, record: T) -> T:
        return record.model_copy(update={"tenant_id": self.tenant_id})

    # ---------- watches ----------

    def list_watches(self) -> list[Watch]:
        with self.lock:
            rows = self._read(WATCHES_FILE, Watch)
        return sorted(rows, key=lambda w: (w.due_date, w.title))

    def get_watch(self, watch_id: str) -> Watch | None:
        return next((w for w in self.list_watches() if w.id == watch_id), None)

    def add_watch(self, watch: Watch) -> Watch:
        """Add a watch. An id already on disk is returned rather than doubled.

        Idempotent on ``id`` because the two callers that matter now derive
        theirs rather than minting it: the recurring successor
        (:meth:`decide_watch`) and a watch created out of reviewed incoming post
        (:func:`app.integrations.resolve.derived_output_id`). A second arrival
        under the same id is the same obligation being recorded twice — a retry,
        a double submit — and appending it would put the same date on the board
        twice with nothing to say which one the board should act on.
        """
        with self.lock:
            rows = self._read(WATCHES_FILE, Watch)
            existing = next((w for w in rows if w.id == watch.id), None)
            if existing is not None:
                return existing
            record = self._stamp(watch)
            rows.append(record)
            self._write(WATCHES_FILE, rows)
        return record

    def mutate_watch(self, watch_id: str, apply: Callable[[Watch], Watch]) -> Watch:
        """Change one watch across a single locked read-modify-write.

        Same repair, same reason as :meth:`app.tasks.store.TaskStore.mutate_task`:
        the version ``apply`` decides against is the one on disk at that moment,
        not one the route read before it queued for the lock.
        """
        with self.lock:
            rows = self._read(WATCHES_FILE, Watch)
            for i, existing in enumerate(rows):
                if existing.id != watch_id:
                    continue
                record = self._stamp(apply(existing))
                if record.id != existing.id:
                    raise WatchError(
                        f"En ändring av {watch_id} får inte byta id till {record.id}."
                    )
                rows[i] = record
                self._write(WATCHES_FILE, rows)
                return record
        raise WatchNotFound(f"Okänd bevakning: {watch_id}")

    def decide_watch(
        self,
        watch_id: str,
        apply: Callable[[Watch], Watch],
        successor: Callable[[Watch], Watch | None] | None = None,
    ) -> tuple[Watch, Watch | None]:
        """Record a decision and, for a completed recurring obligation, its next turn.

        One lock, one write, and **at most one successor** — which is the whole
        point. Completing a yearly obligation used to be four separate store
        calls from the route (read, update, add successor, update again), and
        eight people pressing "avklarad" at the same moment produced eight
        successors: eight identical besiktningar on next year's board, seven of
        which nobody could account for.

        Two things make one the ceiling. The decision and the successor are
        written together under this lock, so no second caller can observe the
        half-done state; and ``succeeded_by`` is checked *inside* it, so a watch
        that already has a successor never grows another — including on a
        retry, minutes later, from an operator who never saw the first response.
        The successor's id is derived by the caller from the predecessor and the
        new date, so even a store that somehow saw two attempts converges on one
        row rather than two.
        """
        with self.lock:
            rows = self._read(WATCHES_FILE, Watch)
            index = next((i for i, w in enumerate(rows) if w.id == watch_id), None)
            if index is None:
                raise WatchNotFound(f"Okänd bevakning: {watch_id}")

            decided = self._stamp(apply(rows[index]))
            if decided.id != watch_id:
                raise WatchError(f"En ändring av {watch_id} får inte byta id.")
            rows[index] = decided

            made: Watch | None = None
            if successor is not None and not decided.succeeded_by:
                candidate = successor(decided)
                if candidate is not None:
                    made = next((w for w in rows if w.id == candidate.id), None)
                    if made is None:
                        made = self._stamp(candidate)
                        rows.append(made)
                    rows[index] = decided = decided.model_copy(
                        update={"succeeded_by": made.id}
                    )
            elif decided.succeeded_by:
                # Already succeeded — a retry, or two people pressing at once.
                # The existing successor is returned so the caller reports what
                # is really there instead of nothing.
                made = next((w for w in rows if w.id == decided.succeeded_by), None)

            self._write(WATCHES_FILE, rows)
            return decided, made

    def update_watch(self, watch: Watch) -> Watch:
        """Replace a watch with a version the caller already holds.

        Narrower than it reads: prefer :meth:`mutate_watch`, which cannot be
        handed a version that went stale while the request waited for the lock.
        """
        return self.mutate_watch(watch.id, lambda _existing: watch)

    def delete_watch(self, watch_id: str) -> bool:
        with self.lock:
            rows = self._read(WATCHES_FILE, Watch)
            remaining = [w for w in rows if w.id != watch_id]
            if len(remaining) == len(rows):
                return False
            self._write(WATCHES_FILE, remaining)
        return True

    def replace_proposals(
        self, proposals: Iterable[Watch], unresolved: Iterable[UnresolvedObligation]
    ) -> tuple[list[Watch], list[UnresolvedObligation]]:
        """A re-scan supersedes untouched proposals and nothing else.

        Watches a human has approved, dismissed or completed are records of a
        decision and survive every later scan. A fresh proposal that duplicates
        one of them — same document, same kind, same derived date — is dropped
        rather than offered again, because "we already decided that" is not a
        new suggestion, and re-proposing a dismissed obligation every week is
        how a queue teaches people to ignore it.
        """
        with self.lock:
            rows = self._read(WATCHES_FILE, Watch)
            decided = [w for w in rows if w.status != "proposed"]
            known = {(w.source_document_id, w.kind, w.derived_due_date) for w in decided}
            fresh = [
                self._stamp(p)
                for p in proposals
                if (p.source_document_id, p.kind, p.derived_due_date) not in known
            ]
            self._write(WATCHES_FILE, decided + fresh)
            open_rows = [self._stamp(u) for u in unresolved]
            self._write(UNRESOLVED_FILE, open_rows)
        return fresh, open_rows

    # ---------- unresolved ----------

    def list_unresolved(self) -> list[UnresolvedObligation]:
        with self.lock:
            rows = self._read(UNRESOLVED_FILE, UnresolvedObligation)
        return sorted(rows, key=lambda u: (u.source_document_name, u.what))


__all__ = ["SCHEMA_VERSION", "WatchError", "WatchNotFound", "WatchStore"]
