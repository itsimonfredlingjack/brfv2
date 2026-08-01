"""A watch: a dated obligation the board has to act on, and where it comes from.

The product already reads what a contract says about time. This is what makes
that worth something — the difference between "the system can find the notice
period" and "the board does not miss it".

Three rules shape the type, and each is the same rule the review engine lives
by, applied to a different question:

1. **A proposal is not a watch.** Everything the engine derives arrives as
   ``proposed``. A person approves it, adjusts the date, names who is
   responsible and decides when to be reminded. Until then it is a suggestion
   with a citation, and it is displayed as one.
2. **A date that was not read is not a date.** ``due_date`` is only ever
   derived from a passage that verified verbatim, with the arithmetic written
   down in ``derivation`` so a reader can check it without trusting it. A term
   whose date cannot be computed does not become a watch at all — it becomes
   an :class:`UnresolvedObligation`, which says what was found and why it could
   not be dated.
3. **The evidence travels with the obligation.** ``citations`` is the same
   ``CitationOut`` an answer carries, so a watch opens the contract at the page
   the deadline was read from. A deadline whose source cannot be opened is a
   claim, not a watch.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Literal

from pydantic import BaseModel, Field

from ..schemas import CitationOut
from ..terms import parse_iso, shift

# What kind of obligation this is. Kept small and concrete: each member is a
# thing a board actually has a routine for, and a kind nobody can act on
# differently from another kind should not be its own member.
WatchKind = Literal[
    # Say something before a date, or the agreement renews itself.
    "notice_deadline",
    # The agreement simply ends.
    "expiry",
    # A guarantee period runs out.
    "warranty",
    # A statutory or contractual inspection falls due.
    "inspection",
    # Something that comes back on a cycle.
    "recurring_obligation",
]

WATCH_KIND_LABELS: dict[str, str] = {
    "notice_deadline": "Uppsägning",
    "expiry": "Avtalet upphör",
    "warranty": "Garanti",
    "inspection": "Besiktning eller kontroll",
    "recurring_obligation": "Återkommande skyldighet",
}

# Same four words as a finding's status, for the same reason: a reviewer does
# the same four things to both, and two vocabularies for one gesture is how a
# UI starts disagreeing with its backend. "done" replaces "corrected" here
# because a watch is an obligation, and the thing you do to an obligation that
# a correction would not cover is to complete it.
WatchStatus = Literal["proposed", "approved", "dismissed", "done"]

WATCH_STATUS_LABELS: dict[str, str] = {
    "proposed": "väntar på godkännande",
    "approved": "bevakas",
    "dismissed": "avfärdad",
    "done": "avklarad",
}

Recurrence = Literal["none", "monthly", "quarterly", "yearly", "biennial", "triennial"]

RECURRENCE_STEPS: dict[str, tuple[int, str]] = {
    "monthly": (1, "month"),
    "quarterly": (3, "month"),
    "yearly": (1, "year"),
    "biennial": (2, "year"),
    "triennial": (3, "year"),
}

# Where a watch sits relative to today. Computed server-side so the desktop
# view and the phone cannot disagree about what "snart" means.
Bucket = Literal["overdue", "soon", "later", "recurring"]

BUCKET_LABELS: dict[str, str] = {
    "overdue": "Försenat",
    "soon": "Snart",
    "later": "Senare",
    "recurring": "Återkommande",
}

DEFAULT_REMIND_LEAD_DAYS = 30
MAX_REMIND_LEAD_DAYS = 365


class Watch(BaseModel):
    """One dated obligation, proposed by the engine and owned by a human."""

    id: str
    tenant_id: str
    kind: WatchKind
    status: WatchStatus = "proposed"

    # Written as an instruction, not as a label: "Säg upp eller ompröva avtalet
    # senast 2026-09-30" is something a person can act on; "Uppsägningstid" is
    # a category.
    title: str
    due_date: str

    # What the engine derived, kept even after a human moves the date. The two
    # together are the audit trail: somebody decided the deadline was not what
    # the contract's arithmetic said, and that decision is visible.
    derived_due_date: str
    derivation: str

    recurrence: Recurrence = "none"
    # Empty means nobody is named yet, and the view says "ej utsedd" rather
    # than quietly implying the board has it covered.
    responsible: str = ""
    remind_lead_days: int = DEFAULT_REMIND_LEAD_DAYS

    # The passage the date was read from — same type, same verbatim
    # verification and same rects as an answer's citation.
    citations: list[CitationOut] = Field(default_factory=list)
    source_document_id: str = ""
    source_document_name: str = ""

    created_at: str
    decided_by: str | None = None
    decided_at: str | None = None
    decision_note: str | None = None
    # Set when a recurring watch is completed and the next turn is created, so
    # the history stays readable instead of one row being edited forever.
    succeeded_by: str | None = None

    # ---- derived, never stored ----

    def remind_at(self) -> str:
        due = parse_iso(self.due_date)
        if due is None:  # pragma: no cover - due_date is validated on the way in
            return self.due_date
        return (due - timedelta(days=self.remind_lead_days)).isoformat()

    def next_due_after(self) -> str | None:
        """When this comes round again, for a recurring obligation."""
        if self.recurrence == "none":
            return None
        due = parse_iso(self.due_date)
        if due is None:  # pragma: no cover
            return None
        count, unit = RECURRENCE_STEPS[self.recurrence]
        return shift(due, count, unit).isoformat()

    def bucket(self, today: date) -> Bucket:
        """Where this belongs on the board.

        ``recurring`` wins over the date buckets on purpose: a yearly
        obligation is a different kind of thing to plan around than a one-off
        deadline, and mixing them into "senare" is how a year wheel stops being
        a year wheel. An overdue recurring one still reads as overdue, because
        a missed obligation is not a rhythm.
        """
        due = parse_iso(self.due_date)
        if due is None:  # pragma: no cover
            return "later"
        if due < today:
            return "overdue"
        if self.recurrence != "none":
            return "recurring"
        return "soon" if parse_iso(self.remind_at()) <= today else "later"

    def public(self, today: date) -> dict:
        return {
            **self.model_dump(mode="json"),
            "kind_label": WATCH_KIND_LABELS[self.kind],
            "status_label": WATCH_STATUS_LABELS[self.status],
            "remind_at": self.remind_at(),
            "bucket": self.bucket(today),
            "days_left": (parse_iso(self.due_date) - today).days
            if parse_iso(self.due_date)
            else None,
            "next_due_after": self.next_due_after(),
        }


class UnresolvedObligation(BaseModel):
    """A time limit that was read but could not be dated.

    This exists so that "we found nothing" and "we found something we could not
    turn into a date" stop looking identical. The second is a real answer, and
    it is the one a board can act on by supplying the missing fact — a signing
    date, a handover date — which no amount of scanning will produce.

    It is deliberately not a :class:`Watch`. Giving it a date would mean
    inventing one, and a calendar full of invented dates is worse than an empty
    one.
    """

    id: str
    tenant_id: str
    what: str
    why: str
    citations: list[CitationOut] = Field(default_factory=list)
    source_document_id: str = ""
    source_document_name: str = ""
    created_at: str


__all__ = [
    "BUCKET_LABELS",
    "Bucket",
    "DEFAULT_REMIND_LEAD_DAYS",
    "MAX_REMIND_LEAD_DAYS",
    "RECURRENCE_STEPS",
    "Recurrence",
    "UnresolvedObligation",
    "WATCH_KIND_LABELS",
    "WATCH_STATUS_LABELS",
    "Watch",
    "WatchKind",
    "WatchStatus",
]
