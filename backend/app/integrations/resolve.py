"""What happens when a human settles a queue item.

Every route out of this queue leads to a domain this product already has. That
is the whole design and it is worth stating as a prohibition: **there is no
email archive here.** A preserved message is a document, work is an uppgift, a
date is a bevakning, an invoice is read through the invoice path. A second
archive keyed on mail would give the association two answers to "what does our
contract say about the notice period", and the second one would be the one
nobody maintains.

Five outcomes, and the combinations that make sense:

``take_in``           preserve the message text as a document and/or adopt the
                      attachments the reviewer chose. Combines with everything.
``create_task``       :mod:`app.tasks` — with the origin ``source_event`` that
                      domain already knows about.
``monitor``           :mod:`app.watches` — a dated obligation or an awaited
                      answer, created **approved** rather than proposed,
                      because a person just decided it.
``already_handled``   it mattered and nothing further is needed.
``not_relevant``      out of the queue. Nothing is touched in the mailbox.

The last two are exclusive: a record that says both "not relevant" and "here is
the task I made from it" is a record nobody can act on, so the route refuses
the combination rather than storing it.

**Evidence travels.** When the message is preserved in the same act, the task
and the watch created alongside it get *verified citations into that document*
— resolved through :func:`app.citations.resolve_citation` like any other, so
the sentence behind the work opens at the right line months later. When it is
not preserved, they carry no citations at all rather than a reference to
something unopenable. That asymmetry is deliberate and is what makes the
citation mean something.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date

from ..schemas import CitationOut
from ..store import Store
from ..tasks.models import Task, TaskEvent, TaskOrigin
from ..terms import parse_iso
from ..watches.models import DEFAULT_REMIND_LEAD_DAYS, Watch
from .intake import AdoptionError, adopt_attachment
from .models import (
    EXCLUSIVE_RESOLUTIONS,
    RESOLUTION_LABELS,
    Resolution,
    ResolutionOutcome,
    SourceEvent,
    utc_now_iso,
)
from .preserve import PreservationError, citation_for, preserve_message

logger = logging.getLogger("brf.integrations.resolve")

# How many of the triage's quotes are turned into citations on a created task
# or watch. Enough to carry the reason the work exists; not so many that the
# work item becomes a copy of the message.
MAX_CARRIED_CITATIONS = 3


class ResolutionError(ValueError):
    """The resolution cannot be recorded as asked, and the message says why."""


def _text(spec: dict, key: str) -> str:
    """One free-form field, read defensively.

    ``task`` and ``watch`` arrive as open dictionaries on the route, which is
    the right shape — they are two different domains' creation payloads and
    modelling them twice would be modelling them badly. The cost is that a
    client can put a number where a string belongs, and this is where that
    becomes a 422 with a sentence rather than a 500 with a traceback.
    """
    value = spec.get(key)
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ResolutionError(f"Fältet '{key}' ska vara text.")
    return value.strip()


def _lead_days(spec: dict) -> int:
    value = spec.get("remind_lead_days")
    if value is None or value == "":
        return DEFAULT_REMIND_LEAD_DAYS
    try:
        days = int(value)
    except (TypeError, ValueError) as exc:
        raise ResolutionError("Påminnelsen ska anges som ett antal dagar.") from exc
    if not 0 <= days <= 365:
        raise ResolutionError("Påminnelse ska ligga 0–365 dagar före.")
    return days


def _validate(kinds: list[str]) -> list[str]:
    """The requested outcomes, deduplicated, or a refusal explaining itself."""
    unknown = [k for k in kinds if k not in RESOLUTION_LABELS]
    if unknown:
        raise ResolutionError(
            f"Okänt utfall: {', '.join(unknown)}. Tillåtna: {', '.join(RESOLUTION_LABELS)}."
        )
    ordered = list(dict.fromkeys(kinds))
    if not ordered:
        raise ResolutionError("Ange minst ett utfall.")
    exclusive = [k for k in ordered if k in EXCLUSIVE_RESOLUTIONS]
    if exclusive and len(ordered) > 1:
        raise ResolutionError(
            f"'{RESOLUTION_LABELS[exclusive[0]]}' kan inte kombineras med något annat utfall — "
            "posten är antingen färdigbehandlad eller något ni gör något av."
        )
    return ordered


def _carried_citations(store: Store, event: SourceEvent) -> list[CitationOut]:
    """Verified citations into the preserved message, best-effort.

    Only quotes the triage actually read are offered, and only ones that verify
    verbatim survive. A quote that will not resolve is dropped silently here
    for the same reason the answer path drops one: a citation that cannot be
    opened is worse than no citation, because it looks like proof.
    """
    document_id = event.preserved_document_id
    if not document_id or event.triage is None:
        return []
    out: list[CitationOut] = []
    seen: set[str] = set()
    for signal in event.triage.signals:
        quote = (signal.quote or "").strip()
        if not quote or quote in seen or signal.source == "attachment":
            continue
        seen.add(quote)
        citation = citation_for(store, document_id, quote)
        if citation is not None:
            out.append(citation)
        if len(out) >= MAX_CARRIED_CITATIONS:
            break
    return out


def _preserve(
    store: Store, event: SourceEvent, user_id: str, note: str, attachment_ids: list[str]
) -> tuple[SourceEvent, list[ResolutionOutcome]]:
    """Keep the message text and the attachments the reviewer chose.

    The text and the attachments are separate decisions on purpose. A mail
    carrying a contract and an invoice adopts the contract and leaves the
    invoice where it is — the rule adoption has had since it shipped — and
    preserving the covering message is a third, independent choice.
    """
    outcomes: list[ResolutionOutcome] = []
    body = (event.body_text or "").strip()
    if body:
        try:
            event = preserve_message(
                store=store,
                integrations=store.integrations,
                event_id=event.id,
                user_id=user_id,
                note=note,
            )
            outcomes.append(
                ResolutionOutcome(
                    kind="take_in",
                    label="Meddelandets text bevarad som dokument",
                    ref_id=event.preserved_document_id or "",
                    ref_label=store.documents[event.preserved_document_id].name
                    if event.preserved_document_id in store.documents
                    else "",
                )
            )
        except PreservationError as exc:
            raise ResolutionError(str(exc)) from exc

    for attachment_id in attachment_ids:
        try:
            event = adopt_attachment(
                store=store,
                integrations=store.integrations,
                event_id=event.id,
                attachment_id=attachment_id,
                user_id=user_id,
                note=note,
            )
        except AdoptionError as exc:
            raise ResolutionError(str(exc)) from exc
        chosen = next((a for a in event.attachments if a.id == attachment_id), None)
        outcomes.append(
            ResolutionOutcome(
                kind="take_in",
                label="Bilaga lagd i föreningens arkiv",
                ref_id=(chosen.document_id or "") if chosen else "",
                ref_label=chosen.filename if chosen else attachment_id,
            )
        )

    if not outcomes:
        raise ResolutionError(
            "Det finns varken text eller vald bilaga att ta in. Välj en bilaga, eller "
            "markera posten som hanterad i stället."
        )
    return event, outcomes


def _create_task(
    store: Store,
    event: SourceEvent,
    user_id: str,
    spec: dict,
    citations: list[CitationOut],
    today: date,
) -> ResolutionOutcome:
    """Take work on, through the tasks domain's own model.

    The task is built here rather than by calling the tasks route, because a
    route is an HTTP surface and this is not an HTTP client. What is *not*
    duplicated is the meaning: the origin kind ``source_event`` already exists
    in :mod:`app.tasks.models`, the activity trail is written the same way, and
    the store enforces the same append-only history.
    """
    title = _text(spec, "title") or (event.subject or "").strip()
    if not title:
        raise ResolutionError("Uppgiften behöver en rubrik.")
    due = _text(spec, "due_date") or None
    if due is not None and parse_iso(due) is None:
        raise ResolutionError("Datum ska skrivas ÅÅÅÅ-MM-DD.")

    document_id = ""
    document_name = ""
    if citations:
        document_id = citations[0].document_id
        document_name = citations[0].document_name

    now = utc_now_iso()
    task = Task(
        id=uuid.uuid4().hex[:12],
        tenant_id=store.tenant_id,
        title=title[:200],
        description=_text(spec, "description"),
        responsible=_text(spec, "responsible"),
        due_date=due,
        origin=TaskOrigin(
            kind="source_event",
            ref_id=event.id,
            label=f"{event.subject or '(utan ämne)'} — från {event.origin}",
        ),
        citations=citations,
        source_document_id=document_id,
        source_document_name=document_name,
        created_by=user_id,
        created_at=now,
    )
    task = task.model_copy(
        update={
            "activity": [
                TaskEvent(
                    id=uuid.uuid4().hex[:12],
                    at=now,
                    by=user_id,
                    kind="created",
                    to_value=task.title,
                    note=task.origin.label,
                )
            ]
        }
    )
    stored = store.tasks.add_task(task)
    return ResolutionOutcome(
        kind="create_task",
        label=RESOLUTION_LABELS["create_task"],
        ref_id=stored.id,
        ref_label=f"{stored.title} ({stored.public(today)['status_label']})",
    )


def _create_watch(
    store: Store,
    event: SourceEvent,
    user_id: str,
    spec: dict,
    citations: list[CitationOut],
    today: date,
) -> ResolutionOutcome:
    """Put a date, or an awaited answer, on the board.

    Created ``approved`` rather than ``proposed``. Everything the watch engine
    derives arrives as a proposal because a rule engine read it; this arrives
    because a person read a message and decided — and asking them to approve
    their own decision would be a ceremony that teaches people to click through
    approvals.

    ``derived_due_date`` and ``derivation`` are still filled in honestly: the
    date came from a human reading incoming post, and the record says exactly
    that rather than implying an arithmetic nobody performed.
    """
    due = _text(spec, "due_date")
    if parse_iso(due) is None:
        raise ResolutionError("Bevakningen behöver ett datum, skrivet ÅÅÅÅ-MM-DD.")
    kind = _text(spec, "kind") or ("expected_reply" if _awaits_reply(event) else "stated_deadline")
    if kind not in ("stated_deadline", "expected_reply"):
        raise ResolutionError(
            "En bevakning ur inkommande post är antingen ett utsatt datum eller ett väntat svar."
        )
    title = _text(spec, "title")
    if not title:
        title = (
            f"Väntar svar om {event.subject or 'inkommande post'} senast {due}"
            if kind == "expected_reply"
            else f"{event.subject or 'Inkommande post'} — senast {due}"
        )

    remind = _lead_days(spec)

    watch = Watch(
        id=uuid.uuid4().hex[:12],
        tenant_id=store.tenant_id,
        kind=kind,
        status="approved",
        title=title[:200],
        due_date=due,
        derived_due_date=due,
        derivation=(
            f"Datum ur inkommande post: {event.subject or '(utan ämne)'} från {event.origin}, "
            f"{(event.occurred_at or event.received_at)[:10]}. Satt av en människa vid granskningen."
        ),
        recurrence="none",
        responsible=_text(spec, "responsible"),
        remind_lead_days=remind,
        citations=citations,
        source_document_id=citations[0].document_id if citations else "",
        source_document_name=citations[0].document_name if citations else "",
        created_at=utc_now_iso(),
        decided_by=user_id,
        decided_at=utc_now_iso(),
        decision_note=_text(spec, "note") or None,
    )
    stored = store.watches.add_watch(watch)
    return ResolutionOutcome(
        kind="monitor",
        label=RESOLUTION_LABELS["monitor"],
        ref_id=stored.id,
        ref_label=f"{stored.title} ({stored.public(today)['bucket']})",
    )


def _awaits_reply(event: SourceEvent) -> bool:
    return bool(event.triage and event.triage.awaiting_reply)


def resolve_source_event(
    *,
    store: Store,
    event_id: str,
    user_id: str,
    kinds: list[str],
    note: str = "",
    attachment_ids: list[str] | None = None,
    task: dict | None = None,
    watch: dict | None = None,
    today: date | None = None,
) -> SourceEvent:
    """Settle one queue item, and route it into the domains that own the result.

    The order matters and is fixed: preserve first, because that is what
    produces the document a task's and a watch's citations point into. A task
    created before the message was preserved would carry no evidence, and the
    reviewer pressed one button expecting both.

    Nothing here writes to the mailbox, and nothing deletes the queue entry: a
    resolved item keeps its provenance, its triage and its outcome, because
    "what did we decide about this, and when" is the question the whole record
    exists to answer.
    """
    integrations = store.integrations
    event = integrations.get_source_event(event_id)
    if event is None:
        raise ResolutionError("Okänd källhändelse.")

    ordered = _validate(kinds)
    reason = (note or "").strip()
    outcomes: list[ResolutionOutcome] = []
    when = today or date.today()

    if "take_in" in ordered:
        if not reason:
            raise ResolutionError(
                "Ange varför posten ska bevaras. Ett dokument som blir en del av föreningens "
                "underlag utan att någon säger varför är inte ett arkiv."
            )
        event, preserved = _preserve(store, event, user_id, reason, attachment_ids or [])
        outcomes.extend(preserved)

    citations = _carried_citations(store, event)

    if "create_task" in ordered:
        outcomes.append(_create_task(store, event, user_id, task or {}, citations, when))
    if "monitor" in ordered:
        outcomes.append(_create_watch(store, event, user_id, watch or {}, citations, when))
    for kind in ("already_handled", "not_relevant"):
        if kind in ordered:
            outcomes.append(ResolutionOutcome(kind=kind, label=RESOLUTION_LABELS[kind]))

    # The coarse status the rest of the product already reads stays in step
    # with the richer record, so a client that only knows `review_status`
    # (and the mobile app is one) is never shown a settled item as open.
    review_status = "dismissed" if "not_relevant" in ordered else "approved"

    settled = event.model_copy(
        update={
            "resolution": Resolution(
                outcomes=outcomes,
                decided_by=user_id,
                decided_at=utc_now_iso(),
                note=reason,
            ),
            "review_status": review_status,
            "decided_by": user_id,
            "decided_at": utc_now_iso(),
            "decision_note": reason or None,
        }
    )
    return integrations.update_source_event(settled)


def reopen_source_event(*, store: Store, event_id: str) -> SourceEvent:
    """Put a settled item back in the queue.

    The outcome record is cleared; what it produced is not. A task made from
    this message stays a task, a preserved document stays in the archive, and a
    watch stays on the board — those are records of decisions, and reopening a
    queue card is not a decision about any of them. The card says what it
    produced, so a reviewer can go and cancel the task themselves if that is
    what they meant.
    """
    integrations = store.integrations
    event = integrations.get_source_event(event_id)
    if event is None:
        raise ResolutionError("Okänd källhändelse.")
    return integrations.update_source_event(
        event.model_copy(
            update={
                "resolution": None,
                "review_status": "open",
                "decided_by": None,
                "decided_at": None,
            }
        )
    )


__all__ = [
    "MAX_CARRIED_CITATIONS",
    "ResolutionError",
    "reopen_source_event",
    "resolve_source_event",
]
