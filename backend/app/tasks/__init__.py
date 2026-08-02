"""Uppgifter och ansvar: what the board is going to do about what it found.

The rest of the product reads and proposes. This is where a human turns a
finding, a watch or a piece of incoming post into work with a name on it, a
date, a status and a history — carrying the original evidence along so the
passage behind the work still opens months later.

It is the one domain here that no engine can create. That is the point: a rule
engine can read a document, but nobody's obligations follow from that until a
person takes them on, and creating a task *is* that decision.
"""

from .models import (
    ACTIVE_STATUSES,
    ORIGIN_LABELS,
    TASK_STATUS_LABELS,
    Task,
    TaskEvent,
    TaskOrigin,
    TaskStatus,
)
from .store import SCHEMA_VERSION, TaskStore, TaskStoreError

__all__ = [
    "ACTIVE_STATUSES",
    "ORIGIN_LABELS",
    "SCHEMA_VERSION",
    "TASK_STATUS_LABELS",
    "Task",
    "TaskEvent",
    "TaskOrigin",
    "TaskStatus",
    "TaskStore",
    "TaskStoreError",
]
