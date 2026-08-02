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
from typing import Iterable

from pydantic import ValidationError

from .models import Task

logger = logging.getLogger("brf.tasks")

SCHEMA_VERSION = 1

META_FILE = "meta.json"
TASKS_FILE = "tasks.json"


class TaskStoreError(RuntimeError):
    """Refusing to operate on this tenant's task data."""


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

    def update_task(self, task: Task) -> Task:
        """Replace a task with a new version of itself.

        The caller is responsible for having appended the activity events that
        explain the change — the store does not infer them, because a store
        that guessed what happened would produce a history nobody wrote.
        """
        with self.lock:
            rows = self._read()
            record = task.model_copy(update={"tenant_id": self.tenant_id})
            for i, existing in enumerate(rows):
                if existing.id == record.id:
                    if len(record.activity) < len(existing.activity):
                        raise TaskStoreError(
                            f"Uppgiften {record.id} skulle skrivas med kortare historik "
                            "än den redan har. Historiken är append-only."
                        )
                    rows[i] = record
                    break
            else:
                raise TaskStoreError(f"Okänd uppgift: {record.id}")
            self._write(rows)
        return record


__all__ = ["SCHEMA_VERSION", "TaskStore", "TaskStoreError"]
