"""Per-tenant persistence for tasks. Same shape and isolation as everything else.

One JSON file in the tenant's own directory, written atomically at ``0600``.
``registry.delete()`` sweeps it with the rest, and there is no shared
collection anywhere that a missing ``WHERE`` could leak across — see
:mod:`app.integrations.store` for the argument, unchanged here.

There is deliberately no ``delete``. A task that existed is a record of what
the board decided to do; work that turned out to be unnecessary is cancelled
with a stated reason and stays visible.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from pathlib import Path
from typing import Callable, Iterable

from pydantic import ValidationError

from ..history import AppendOnlyViolation, check_append_only
from .models import Task

logger = logging.getLogger("brf.tasks")

SCHEMA_VERSION = 1

META_FILE = "meta.json"
TASKS_FILE = "tasks.json"


class TaskStoreError(RuntimeError):
    """Refusing to operate on this tenant's task data."""


class TaskNotFound(TaskStoreError):
    """No task with that id in this tenant's directory.

    Its own type so a route can answer 404 for "there is no such task" without
    also answering 404 for "that write would have destroyed history" — two
    different failures that were previously one exception and would have been
    reported to the operator as the same thing.
    """


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


class TaskStore:
    """Tasks for exactly one tenant."""

    def __init__(self, data_dir: str | Path, tenant_id: str) -> None:
        if not tenant_id:
            raise TaskStoreError("TaskStore kräver ett tenant-id.")
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
            raise TaskStoreError(
                f"{path} går inte att läsa ({exc}) — vägrar öppna uppgiftsdata för "
                f"'{self.tenant_id}'."
            ) from exc
        version = raw.get("schemaVersion") if isinstance(raw, dict) else None
        if version == SCHEMA_VERSION:
            return
        if isinstance(version, int) and version < SCHEMA_VERSION:  # pragma: no cover
            _atomic_write_json(path, {"schemaVersion": SCHEMA_VERSION})
            return
        raise TaskStoreError(
            f"Uppgiftsdata för '{self.tenant_id}' har schemaVersion {version!r}; den här "
            f"versionen förstår {SCHEMA_VERSION}. En nyare datakatalog får inte öppnas av "
            "en äldre installation — då skrivs fält bort."
        )

    # ---------- io ----------

    def _read(self) -> list[Task]:
        path = self.dir / TASKS_FILE
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return []
        except (OSError, json.JSONDecodeError) as exc:
            raise TaskStoreError(f"{path} går inte att läsa: {exc}") from exc
        if not isinstance(raw, list):
            raise TaskStoreError(f"{path} innehåller inte en lista.")
        rows: list[Task] = []
        for entry in raw:
            try:
                record = Task.model_validate(entry)
            except ValidationError as exc:
                raise TaskStoreError(f"Ogiltig post i {path}: {exc}") from exc
            if record.tenant_id != self.tenant_id:
                raise TaskStoreError(
                    f"{path} innehåller en uppgift för tenant {record.tenant_id!r} i "
                    f"{self.tenant_id!r}s katalog."
                )
            rows.append(record)
        return rows

    def _write(self, rows: Iterable[Task]) -> None:
        _atomic_write_json(self.dir / TASKS_FILE, [row.model_dump(mode="json") for row in rows])

    # ---------- reads ----------

    def list_tasks(self) -> list[Task]:
        """Newest activity first: a board reads what moved, not what was filed."""
        with self.lock:
            rows = self._read()
        return sorted(rows, key=lambda t: t.last_activity_at(), reverse=True)

    def get_task(self, task_id: str) -> Task | None:
        return next((t for t in self.list_tasks() if t.id == task_id), None)

    def tasks_for_origin(self, kind: str, ref_id: str) -> list[Task]:
        """Existing work for a finding, watch or source event.

        Used to show "there is already a task for this" rather than letting two
        people create the same one a week apart — the failure a shared queue is
        supposed to prevent, not cause.
        """
        if not ref_id:
            return []
        return [t for t in self.list_tasks() if t.origin.kind == kind and t.origin.ref_id == ref_id]

    # ---------- writes ----------

    def add_task(self, task: Task) -> Task:
        with self.lock:
            rows = self._read()
            record = task.model_copy(update={"tenant_id": self.tenant_id})
            if any(r.id == record.id for r in rows):
                raise TaskStoreError(f"Uppgiften {record.id} finns redan.")
            rows.append(record)
            self._write(rows)
        return record

    def ensure_task(self, task: Task) -> tuple[Task, bool]:
        """Add this task unless its id is already here. Returns ``(task, created)``.

        The difference from :meth:`add_task` is who the duplicate is. ``add_task``
        refuses one, because two callers minting the same random id means
        something is badly wrong. Here the id is **derived** from the decision
        the task came out of (see
        :func:`app.integrations.resolve.derived_output_id`), so a
        second arrival under the same id is the same intent arriving twice — an
        operator pressing "spara" again after a timeout, or a retry after a
        fault killed the request halfway through. Returning what already exists
        is the correct answer to that, and it is what keeps a retry from leaving
        the association with two identical tasks nobody can tell apart.
        """
        with self.lock:
            rows = self._read()
            existing = next((r for r in rows if r.id == task.id), None)
            if existing is not None:
                return existing, False
            record = task.model_copy(update={"tenant_id": self.tenant_id})
            rows.append(record)
            self._write(rows)
        return record, True

    def mutate_task(self, task_id: str, apply: Callable[[Task], Task]) -> Task:
        """Change one task, safely against every other request.

        The lock is held across the whole read-modify-write and the version
        handed to ``apply`` is read from disk *inside* it, so a caller that read
        the task a second ago cannot write back a version that has since been
        commented on. That is the whole repair: eight concurrent comments used
        to leave two, because each request built a complete replacement object
        from a task it had read before taking the lock, and the last writer won.

        Same shape as :func:`app.invoices.cases.mutate`, deliberately — the two
        domains have the same problem and should not have two different answers
        to it.
        """
        with self.lock:
            rows = self._read()
            for i, existing in enumerate(rows):
                if existing.id != task_id:
                    continue
                record = apply(existing).model_copy(update={"tenant_id": self.tenant_id})
                if record.id != existing.id:
                    raise TaskStoreError(
                        f"En ändring av {task_id} får inte byta id till {record.id}."
                    )
                try:
                    check_append_only(existing.activity, record.activity, what="Uppgiften")
                except AppendOnlyViolation as exc:
                    raise TaskStoreError(str(exc)) from exc
                rows[i] = record
                self._write(rows)
                return record
        raise TaskNotFound(f"Okänd uppgift: {task_id}")

    def update_task(self, task: Task) -> Task:
        """Replace a task with a new version of itself.

        Kept for callers that genuinely hold the current version — and narrower
        than it looks: :func:`app.history.check_append_only` requires the stored
        activity to still be a *prefix* of what is being written, so a stale
        complete object is refused rather than silently overwriting a comment
        somebody else added in the meantime. New code should use
        :meth:`mutate_task`, which cannot be stale in the first place.

        The caller is responsible for having appended the activity events that
        explain the change — the store does not infer them, because a store
        that guessed what happened would produce a history nobody wrote.
        """
        return self.mutate_task(task.id, lambda _existing: task)


__all__ = ["SCHEMA_VERSION", "TaskNotFound", "TaskStore", "TaskStoreError"]
