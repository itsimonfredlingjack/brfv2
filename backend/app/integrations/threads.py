"""Grouping incoming post into the conversations a board actually reads.

A queue that lists every reply as an unrelated row is a queue that shows the
same matter four times and lets a person resolve one copy of it. So messages
are grouped — and the whole difficulty of this module is that grouping mail is
a *reading* of the material, never a fact about it.

Two signals, in that order of trust:

1. **The reply chain.** ``Message-ID``, ``In-Reply-To`` and ``References`` are
   what mail clients actually use, and when they are present they are right far
   more often than any heuristic. They are still sender-controlled text: a
   forged ``In-Reply-To`` joins two conversations, and plenty of real mail
   carries none at all.
2. **The subject, stripped of its reply prefixes, plus the people involved.**
   The fallback for the very common case of a reply typed into a fresh message.
   Bounded by participants so that two associations' separate "Offert" threads
   with different suppliers do not merge into one.

What is deliberately *not* here: no similarity scoring, no clustering, no
"probably the same matter" beyond those two rules. A thread is a presentation
of records that each stand on their own, and every card shows the individual
messages it is made of — so a grouping that got it wrong is visible and
harmless, rather than a silent merge a reviewer has to unpick.

Threads are **derived, never stored**. The tenant's source events are the
records; this reads them. That is not tidiness — a stored thread table would be
the first collection in this package that is not simply "the tenant's own file",
and it would need its own tenant check, its own migration and its own
reconciliation every time an event is deleted.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from datetime import date, datetime
from zoneinfo import ZoneInfo

from .models import SourceEvent, TRIAGE_CATEGORY_LABELS
from ..terms import STOCKHOLM_TZ, calendar_date_in

# Reply and forward prefixes, Swedish and English, as a mail client writes
# them: "Re:", "SV:", "Sv:", "VB:", "Fwd:", "Ang:", and the numbered forms
# Outlook produces on a long thread ("Re[2]:").
_PREFIX = re.compile(
    r"^\s*(?:(?:re|sv|svar|vb|vs|fwd|fw|vidarebefordrat|ang|aw|antw)\s*(?:\[\d+\])?\s*:\s*)+",
    re.IGNORECASE,
)
_WHITESPACE = re.compile(r"\s+")


def strip_reply_prefixes(subject: str) -> str:
    """"SV: Re: Offert takomläggning" → "Offert takomläggning".

    Applied repeatedly by the pattern itself, because a message that has been
    round a board twice carries several prefixes and stripping one leaves the
    thread split in two.
    """
    previous = subject or ""
    for _ in range(8):  # a bound, not an expectation
        stripped = _PREFIX.sub("", previous).strip()
        if stripped == previous:
            break
        previous = stripped
    return previous.strip()


def normalize_subject(subject: str) -> str:
    """A subject reduced to what two messages in one conversation share."""
    text = strip_reply_prefixes(subject or "")
    text = unicodedata.normalize("NFKC", text).casefold()
    return _WHITESPACE.sub(" ", text).strip()


def participants(event: SourceEvent) -> frozenset[str]:
    """Everyone on the message, lowercased.

    Used only to keep two same-named conversations apart, never to identify
    anybody: the addresses are already in the record and this adds no claim.
    """
    people = {(event.origin or "").lower()}
    people |= {r.lower() for r in event.recipients}
    return frozenset(p for p in people if p)


def subject_key(event: SourceEvent) -> str:
    """The fallback grouping key: normalised subject + the domains involved.

    Domains rather than full addresses, because a supplier replying from
    ``anna@`` after ``info@`` wrote first is one conversation, and requiring the
    exact address set to match would split it. A domain set is the coarsest
    thing that still refuses to merge two different counterparties.
    """
    subject = normalize_subject(event.subject)
    domains = sorted({p.rsplit("@", 1)[-1] for p in participants(event) if "@" in p})
    if not subject:
        # No subject to group on: the message stands alone rather than joining
        # every other subjectless message in the mailbox.
        return f"event:{event.id}"
    return "subject:" + subject + "|" + ",".join(domains)


class _Union:
    """Union-find over message identifiers. Small, and local on purpose."""

    def __init__(self) -> None:
        self._parent: dict[str, str] = {}

    def find(self, key: str) -> str:
        self._parent.setdefault(key, key)
        root = key
        while self._parent[root] != root:
            root = self._parent[root]
        while self._parent[key] != root:  # path compression
            self._parent[key], key = root, self._parent[key]
        return root

    def union(self, left: str, right: str) -> None:
        a, b = self.find(left), self.find(right)
        if a != b:
            # Deterministic: the smaller string wins, so the same input always
            # produces the same roots regardless of iteration order.
            self._parent[max(a, b)] = min(a, b)


def thread_key_for(event: SourceEvent, existing: list[SourceEvent]) -> tuple[str, str]:
    """The thread key and display subject for one event, given what is stored.

    Computed at import so a card cannot regroup itself under a reader later. It
    joins an existing thread when the reply chain says so, and otherwise falls
    back to the subject key — which is stable, so two messages that arrive
    hours apart still land together.
    """
    chain = {ref for ref in ([event.external_ref] if event.external_ref else [])}
    chain |= {event.in_reply_to} if event.in_reply_to else set()
    chain |= set(event.references)
    if chain:
        for other in existing:
            other_chain = {other.external_ref} if other.external_ref else set()
            other_chain |= {other.in_reply_to} if other.in_reply_to else set()
            other_chain |= set(other.references)
            if chain & other_chain and other.thread_key:
                return other.thread_key, other.thread_subject or strip_reply_prefixes(event.subject)
    key = subject_key(event)
    for other in existing:
        if other.thread_key == key:
            return key, other.thread_subject or strip_reply_prefixes(event.subject)
    return key, strip_reply_prefixes(event.subject) or "(utan ämne)"


@dataclass
class Thread:
    """One conversation, as the queue presents it."""

    key: str
    subject: str
    events: list[SourceEvent] = field(default_factory=list)

    # ---- the facts a card is built from ----

    @property
    def message_count(self) -> int:
        return len(self.events)

    @property
    def attachment_count(self) -> int:
        return sum(len(e.attachments) for e in self.events)

    @property
    def first(self) -> SourceEvent:
        return self.events[0]

    @property
    def latest(self) -> SourceEvent:
        return self.events[-1]

    def _at(self, event: SourceEvent) -> str:
        """When the message happened, preferring the source's own time."""
        return event.occurred_at or event.received_at

    @property
    def first_at(self) -> str:
        return self._at(self.first)

    @property
    def latest_at(self) -> str:
        return self._at(self.latest)

    @property
    def open_count(self) -> int:
        return sum(1 for e in self.events if e.resolution is None)

    @property
    def awaiting_reply(self) -> bool:
        """Does this thread look like it is waiting for someone here to answer?

        Deliberately conservative, and deliberately phrased as *looks like* in
        every string the UI shows. The product reads one folder of incoming
        post: it cannot see the board's sent mail, so it cannot know whether
        somebody already replied. What it can see is that the newest message in
        the thread asked something and nobody here has resolved it — which is
        exactly the state worth surfacing, and is honest about being a
        suggestion rather than a fact.
        """
        latest = self.latest
        if latest.resolution is not None:
            return False
        triage = latest.triage
        return bool(triage and triage.awaiting_reply)

    @property
    def category(self) -> str:
        """The thread's category: the newest message that has one.

        The newest rather than the first, because a thread that started as a
        quote and ended with an approval is now about the approval — and that
        is the thing a board must not miss.
        """
        for event in reversed(self.events):
            if event.triage_confirmation is not None:
                return event.triage_confirmation.category
            if event.triage is not None and event.triage.category != "unclear":
                return event.triage.category
        return "unclear"

    @property
    def confirmed(self) -> bool:
        return any(e.triage_confirmation is not None for e in self.events)

    def public(self) -> dict:
        """Everything a thread card needs, with no second read of the store."""
        latest = self.latest
        triage = latest.triage
        return {
            "key": self.key,
            "subject": self.subject or "(utan ämne)",
            "category": self.category,
            "category_label": TRIAGE_CATEGORY_LABELS.get(self.category, self.category),
            "category_confirmed": self.confirmed,
            "latest_sender": latest.origin,
            "latest_sender_display": latest.origin_display or "",
            "first_at": self.first_at,
            "latest_at": self.latest_at,
            "message_count": self.message_count,
            "attachment_count": self.attachment_count,
            "awaiting_reply": self.awaiting_reply,
            "open_count": self.open_count,
            "resolved": self.open_count == 0,
            # The newest message's reading is what the card headline shows;
            # every message's own triage travels with it in `events`.
            "headline": (triage.headline if triage else ""),
            "why_it_matters": (triage.why_it_matters if triage else ""),
            "action_hint": (triage.action_hint if triage else ""),
            "supplier_name": (triage.supplier_name if triage else ""),
            "suggested_by": (triage.suggested_by if triage else ""),
            "uncertainty": (triage.uncertainty if triage else ""),
            "signals": [s.model_dump(mode="json") for s in (triage.signals if triage else [])],
            "related": [r.model_dump(mode="json") for r in (triage.related if triage else [])],
            "events": [e.model_dump(mode="json") for e in self.events],
        }


def build_threads(events: list[SourceEvent]) -> list[Thread]:
    """Group stored source events into conversations, newest thread first.

    The reply chain is applied first and transitively — A references B and B
    references C puts all three together even when A never mentions C — and the
    stored ``thread_key`` carries the subject fallback that was computed at
    import. An event from a build that predates threading has an empty key and
    is grouped by subject here, so an existing queue reads correctly without a
    migration that rewrites everybody's records.
    """
    union = _Union()
    by_message_id: dict[str, str] = {}

    for event in events:
        key = event.thread_key or subject_key(event)
        union.find(key)
        if event.external_ref:
            by_message_id[event.external_ref] = key

    for event in events:
        key = event.thread_key or subject_key(event)
        for ref in ([event.in_reply_to] if event.in_reply_to else []) + event.references:
            other = by_message_id.get(ref)
            if other is not None:
                union.union(key, other)

    grouped: dict[str, Thread] = {}
    for event in events:
        key = union.find(event.thread_key or subject_key(event))
        thread = grouped.get(key)
        if thread is None:
            thread = Thread(key=key, subject=event.thread_subject or strip_reply_prefixes(event.subject))
            grouped[key] = thread
        elif not thread.subject:
            thread.subject = event.thread_subject or strip_reply_prefixes(event.subject)
        thread.events.append(event)

    threads = list(grouped.values())
    for thread in threads:
        # Oldest first inside a thread: that is how a conversation is read, and
        # `latest` has to mean the newest message for every card property.
        thread.events.sort(key=lambda e: (e.occurred_at or e.received_at, e.received_at, e.id))
    threads.sort(key=lambda t: (t.latest_at, t.key), reverse=True)
    return threads


# How many unanswered-anchor cards the queue shows at once. More than this
# and the rest collapse to a count — alert fatigue is a documented failure
# mode, not a display preference.
OPEN_ANCHOR_SHOWN = 3


def open_anchor_summaries(
    threads: list[Thread],
    *,
    today: date | None = None,
    cap: int = OPEN_ANCHOR_SHOWN,
) -> dict:
    """Unanswered "från vilket datum?" questions, oldest first, capped.

    An unanswered question that sits in a long list is the same silent drop
    Feature 2 exists to close. The queue therefore counts them, ages them,
    and refuses to render more than ``cap`` cards at once.

    Each question is a row — two frists in one message are two questions, not
    one card that hid the second. Age is calendar days in Europe/Stockholm,
    the same zone :func:`calendar_date_in` uses for the received date.
    """
    now = today if today is not None else datetime.now(ZoneInfo(STOCKHOLM_TZ)).date()
    items: list[dict] = []
    for thread in threads:
        if thread.open_count == 0:
            continue
        for event in thread.events:
            if event.resolution is not None:
                continue
            questions = event.triage.anchor_questions if event.triage else []
            asked_date = calendar_date_in(event.received_at)
            age_days = (now - asked_date).days if asked_date is not None else 0
            for question in questions:
                items.append(
                    {
                        "thread_key": thread.key,
                        "event_id": event.id,
                        "subject": thread.subject,
                        "quote": question.quote,
                        "label": question.label,
                        "asked_at": event.received_at,
                        "age_days": max(0, age_days),
                    }
                )
    items.sort(key=lambda row: (row["asked_at"], row["event_id"], row["quote"]))
    shown = items[:cap]
    return {
        "total": len(items),
        "cap": cap,
        "shown": shown,
        "hidden": max(0, len(items) - len(shown)),
    }


__all__ = [
    "OPEN_ANCHOR_SHOWN",
    "Thread",
    "build_threads",
    "normalize_subject",
    "open_anchor_summaries",
    "participants",
    "strip_reply_prefixes",
    "subject_key",
    "thread_key_for",
]
