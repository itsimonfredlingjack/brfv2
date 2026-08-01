"""An uppgift: what somebody is actually going to do, and where it came from.

The product proposes. A finding says an invoice may not match its contract; a
watch says a notice period runs out on a date. Neither of those is work. This
is the record of a human deciding that something *will* be done, by whom, by
when — and it is deliberately the one domain in this product that the engine
cannot create.

That asymmetry is the design. Findings and watches arrive as proposals because
a rule engine can read a document; nobody's obligations follow from that until
a person takes them on. So there is no ``proposed`` task and no scan that
produces one: creating a task **is** the decision, and it is recorded as one.

Three properties make a task worth more than a line in a notebook:

1. **Its evidence travels with it.** A task made from a finding or a watch
   carries that origin's citations, so the passage behind the work opens at the
   right page months later. A task with no traceable origin is a to-do item;
   this product's whole claim is the difference between those two.
2. **Its history is append-only.** Every change writes a
   :class:`TaskEvent` with who did it and when. Nothing is edited silently,
   because "who moved the deadline and when" is exactly the question that gets
   asked afterwards.
3. **It is never deleted.** A task that existed is a record of what the board
   decided to do. Work that turned out to be unnecessary is *cancelled*, with a
   stated reason, and stays visible.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from ..schemas import CitationOut
from ..terms import parse_iso

# Where the work came from. "manual" is a first-class member, not a fallback:
# plenty of board work starts in a meeting rather than in a document, and a
# vocabulary that forced everything to claim a source would produce false
# provenance rather than honest absence.
TaskOriginKind = Literal["finding", "watch", "source_event", "manual"]

ORIGIN_LABELS: dict[str, str] = {
    "finding": "Fakturagranskning",
    "watch": "Bevakning",
    "source_event": "Inkommande post",
    "manual": "Skapad för hand",
}

# Five states, each of which a board does something different about. "blocked"
# earns its place by being the one that needs someone else — a state that looks
# like "open" on a list is how a stalled task stays invisible for a month.
TaskStatus = Literal["open", "in_progress", "blocked", "done", "cancelled"]

TASK_STATUS_LABELS: dict[str, str] = {
    "open": "att göra",
    "in_progress": "pågår",
    "blocked": "blockerad",
    "done": "klar",
    "cancelled": "avbruten",
}

ACTIVE_STATUSES: tuple[str, ...] = ("open", "in_progress", "blocked")
# Ending a task one of these two ways requires a stated reason. Marking work
# done does not: the note would be ceremony, and the activity trail already
# says who closed it and when. Cancelling or blocking is where the missing
# sentence is the one somebody later wishes had been written.
REASON_REQUIRED: tuple[str, ...] = ("blocked", "cancelled")

TaskEventKind = Literal[
    "created",
    "status_changed",
    "assigned",
    "due_changed",
    "noted",
    "edited",
]

EVENT_LABELS: dict[str, str] = {
    "created": "skapad",
    "status_changed": "status ändrad",
    "assigned": "ansvarig ändrad",
    "due_changed": "datum ändrat",
    "noted": "kommentar",
    "edited": "text ändrad",
}


class TaskOrigin(BaseModel):
    """What this work came out of, in enough detail to go back to it."""

    kind: TaskOriginKind = "manual"
    # The finding, watch or source event this was created from. Empty for
    # manual work — and the pair (kind, ref_id) is what the UI uses to show
    # "there is already a task for this" instead of quietly making a second.
    ref_id: str = ""
    # What that thing said at the time. Kept as a copy on purpose: a finding
    # can be re-run and a watch re-dated, and the task should still say what it
    # was created about rather than silently re-describing itself.
    label: str = ""

    def public(self) -> dict:
        return {**self.model_dump(mode="json"), "kind_label": ORIGIN_LABELS[self.kind]}


class TaskEvent(BaseModel):
    """One thing that happened to a task. Written once, never edited."""

    id: str
    at: str
    by: str
    kind: TaskEventKind
    # The change in plain values, so the trail is readable without diffing two
    # snapshots. Both empty for a plain comment.
    from_value: str = ""
    to_value: str = ""
    note: str = ""

    def public(self) -> dict:
        return {**self.model_dump(mode="json"), "kind_label": EVENT_LABELS[self.kind]}


class Task(BaseModel):
    """Work the association has taken on."""

    id: str
    tenant_id: str

    title: str
    description: str = ""
    status: TaskStatus = "open"
    # Empty means nobody is named yet, and every view says "ej utsedd" rather
    # than leaving a blank that reads as though somebody has it.
    responsible: str = ""
    due_date: str | None = None

    origin: TaskOrigin = Field(default_factory=TaskOrigin)
    # Carried from the origin at creation. The evidence is the point: a task
    # about a contract term should open that term, not a document name.
    citations: list[CitationOut] = Field(default_factory=list)
    source_document_id: str = ""
    source_document_name: str = ""

    created_by: str
    created_at: str
    # Append-only. The list is the audit trail and the UI's activity feed at
    # once; there is no separate log to keep in step with it.
    activity: list[TaskEvent] = Field(default_factory=list)

    @property
    def active(self) -> bool:
        return self.status in ACTIVE_STATUSES

    def days_left(self, today: date) -> int | None:
        due = parse_iso(self.due_date or "")
        return (due - today).days if due else None

    def overdue(self, today: date) -> bool:
        """Past its date and still open.

        A finished task is never overdue, however late it was — the question a
        board asks of a closed task is whether it was done, not whether the
        date held.
        """
        left = self.days_left(today)
        return bool(self.active and left is not None and left < 0)

    def last_activity_at(self) -> str:
        return self.activity[-1].at if self.activity else self.created_at

    def public(self, today: date) -> dict:
        return {
            **self.model_dump(mode="json"),
            "status_label": TASK_STATUS_LABELS[self.status],
            "origin": self.origin.public(),
            "activity": [event.public() for event in self.activity],
            "active": self.active,
            "overdue": self.overdue(today),
            "days_left": self.days_left(today),
            "last_activity_at": self.last_activity_at(),
        }


__all__ = [
    "ACTIVE_STATUSES",
    "EVENT_LABELS",
    "ORIGIN_LABELS",
    "REASON_REQUIRED",
    "TASK_STATUS_LABELS",
    "Task",
    "TaskEvent",
    "TaskEventKind",
    "TaskOrigin",
    "TaskOriginKind",
    "TaskStatus",
]
