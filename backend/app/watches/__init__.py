"""Source-driven watches: dated obligations read out of the association's own documents.

The invoice review answers "is this bill right". This answers the question a
board actually loses money and buildings to: "what were we supposed to do by
when, and did anyone do it".

It is built on the same three rules as the rest of the product, because they
are what make the answer worth anything:

* **Nothing is claimed that was not read.** Every watch carries the passage its
  date came from, verified verbatim, opening at the right page.
* **A proposal is not a decision.** The engine proposes; a named person
  approves, adjusts, assigns and is recorded doing it.
* **An undated obligation stays undated.** A time limit the engine cannot
  compute becomes an :class:`~app.watches.models.UnresolvedObligation` that says
  what is missing — never a calendar entry built on a guess, which would look
  exactly like a correct one.

There is no calendar integration here and that is the point of the sequencing:
a stable internal obligation domain first, an adapter to somebody else's
calendar later, exactly as the accounting adapter followed the fixture one.
"""

from .models import (
    BUCKET_LABELS,
    RECURRENCE_STEPS,
    WATCH_KIND_LABELS,
    WATCH_STATUS_LABELS,
    Recurrence,
    UnresolvedObligation,
    Watch,
    WatchKind,
    WatchStatus,
)
from .store import SCHEMA_VERSION, WatchError, WatchStore

__all__ = [
    "BUCKET_LABELS",
    "RECURRENCE_STEPS",
    "SCHEMA_VERSION",
    "UnresolvedObligation",
    "WATCH_KIND_LABELS",
    "WATCH_STATUS_LABELS",
    "Watch",
    "WatchError",
    "WatchKind",
    "WatchStatus",
    "WatchStore",
    "Recurrence",
]
