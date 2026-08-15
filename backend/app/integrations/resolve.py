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

**One button, four domains, and what happens when it fails halfway.** This is
the only place in the product where a single human act writes into documents,
tasks, watches *and* the queue. There is no transaction across four JSON files
and this deliberately does not invent one. What it has instead is three
properties that together make a partial failure safe to retry:

1. **One writer at a time.** The tenant's integration lock is held across the
   whole resolution, so no *second resolution* can interleave with this one.
   (Ordering, as everywhere: ``integrations.lock`` before ``Store.lock``,
   ``tasks.lock`` and ``watches.lock``.)

   It does **not** make the five writes one commit. The four files are written
   one after another, each atomically on its own, and a reader looking at a
   different domain — ``GET /tasks`` while this is running — takes that
   domain's lock and not this one. Such a reader can therefore see the task
   before the card that produced it says so. What the lock rules out is a
   *concurrent writer* observing or extending the half-done state, which is a
   different and smaller claim than atomicity. The honest description of the
   guarantee is the one below: retry-safe, idempotent convergence — not an
   atomic cross-file commit.
2. **Derived identity for everything created.** The task's id and the watch's
   id are functions of *which decision they came out of*
   (:func:`derived_output_id`; preservation is idempotent on the event). So the
   act is idempotent by construction: repeating it converges on the same rows
   instead of a second set.
3. **An idempotency key on the record.** :func:`resolution_key` digests the
   request, and a replay of the identical request against an event that already
   carries that key returns what it produced rather than doing it again. A
   *different* request against a settled item is refused
   (:class:`ResolutionConflict`) rather than allowed to overwrite the decision
   that is there — changing a settlement is what :func:`reopen_source_event`
   is for, and it files the old one instead of dropping it.

Together those answer the failure that used to be real: a fault after the task
was created but before the event was updated left the task committed and the
message unresolved, and the operator's retry — the only thing they could
reasonably do — made a second identical task. Now the retry recomputes the same
task id, gets the task that already exists, finishes the write, and the
association ends with one task and one settled card.

What is *not* claimed: this holds within one process. Two processes writing the
same tenant would still be two writers over one file, and the derived ids are
what would keep that from duplicating rather than the lock. See
:mod:`app.integrations.store`.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import date

from ..schemas import CitationOut
from ..store import Store
from ..tasks.models import Task, TaskEvent, TaskOrigin
from ..terms import RelativeHit, Span, anchor_relative, parse_iso
from ..watches.models import DEFAULT_REMIND_LEAD_DAYS, Watch
from .intake import AdoptionError, adopt_attachment
from .models import (
    EXCLUSIVE_RESOLUTIONS,
    RESOLUTION_LABELS,
    DecisionRecord,
    Resolution,
    ResolutionOutcome,
    SourceEvent,
    utc_now_iso,
)
from .store import SourceEventNotFound
from .preserve import PreservationError, citation_for, preserve_message

logger = logging.getLogger("brf.integrations.resolve")

# How many of the triage's quotes are turned into citations on a created task
# or watch. Enough to carry the reason the work exists; not so many that the
# work item becomes a copy of the message.
MAX_CARRIED_CITATIONS = 3


class ResolutionError(ValueError):
    """The resolution cannot be recorded as asked, and the message says why."""


class ResolutionConflict(ResolutionError):
    """This item is already settled, and this is a *different* settlement.

    Its own type so the route can answer **409** rather than 422: nothing about
    the request is malformed, and rephrasing it will not help. The item simply
    already carries a decision, and replacing it silently is the thing this
    refuses to do. Reopen first — that files the old decision — and then settle
    it again.
    """


def _digest(*parts: str) -> str:
    return hashlib.sha256("\x00".join(parts).encode("utf-8")).hexdigest()


def _normalized(spec: dict | None) -> dict:
    """One creation payload reduced to what it actually asks for.

    Strings are stripped and empty fields dropped, so ``{"title": "Utred "}``,
    ``{"title": "Utred"}`` and ``{"title": "Utred", "responsible": ""}`` are one
    command rather than three. This is what makes the key canonical over the
    *normalized* request instead of over its exact bytes — and since every
    output's identity is derived from the key, it is also what stops a retyped
    trailing space from producing a second task.
    """
    out: dict = {}
    for name, value in (spec or {}).items():
        if isinstance(value, str):
            value = value.strip()
        if value is None or value == "":
            continue
        out[name] = value
    return out


def resolution_key(
    *,
    event_id: str,
    kinds: list[str],
    note: str,
    attachment_ids: list[str],
    task: dict | None,
    watch: dict | None,
) -> str:
    """The idempotency key of one resolution request.

    Everything the request would *do* goes into the digest and nothing that
    merely describes when it arrived. Two clicks on one button produce the same
    key; changing the task's title, or who is responsible, or the date produces
    a different one, because that is genuinely a different decision.

    ``sort_keys`` on the two open dictionaries matters: the task and watch specs
    arrive as JSON objects whose key order a client is free to vary, and a key
    that changed with it would recognise nothing.
    """
    payload = json.dumps(
        {
            "event": event_id,
            "kinds": sorted(set(kinds)),
            "note": note,
            "attachments": sorted(set(attachment_ids)),
            "task": _normalized(task),
            "watch": _normalized(watch),
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return _digest("resolution", payload)[:16]


def derived_output_id(kind: str, tenant_id: str, key: str) -> str:
    """The id of a task or a watch created by one resolution, derived not minted.

    Keyed on the **whole normalized decision** (:func:`resolution_key`) and on
    which output of it this is. A retry of the identical request recomputes the
    same id and converges on the row that already exists; a decision that
    differs anywhere that matters gets its own row.

    It used to be keyed on the message and the task's title alone, and that was
    too narrow to be safe. Settling a message into "Utred" for Anna by 1
    September, reopening it, and settling it into "Utred" for Bo by 1 October
    produced *one* task — Anna's — and the second settlement pointed at it. The
    board had recorded a decision the system had quietly declined to carry out,
    and nothing anywhere said so. Everything a reviewer actually chose is now
    part of the identity, so a different choice cannot land on an incompatible
    row.

    The trade-off, stated rather than hidden: the key covers the whole request,
    so changing only the watch's date also gives the task a new id, and a
    reviewer who reopens and adjusts one field gets a second task next to the
    first. That is the safe direction to err in — two visible rows the board can
    reconcile, rather than one row that silently disagrees with the decision
    that produced it — and reopening is a deliberate act, not something that
    happens by accident.
    """
    return _digest("resolution-output", kind, tenant_id, key)[:12]


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
    key: str,
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
    task_id = derived_output_id("create_task", store.tenant_id, key)
    task = Task(
        id=task_id,
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
                    # Derived alongside the task, so a retry that reaches
                    # ``ensure_task`` and finds the task already there does not
                    # differ from it in a way nobody would ever see.
                    id=_digest("task-created", task_id)[:12],
                    at=now,
                    by=user_id,
                    kind="created",
                    to_value=task.title,
                    note=task.origin.label,
                )
            ]
        }
    )
    # ``ensure_task`` rather than ``add_task``: the id is derived from the whole
    # decision, so a second arrival under it is this same decision arriving
    # twice — a retry after a fault, a double submit — and the honest answer is
    # the task that already exists. A different decision derives a different id
    # and cannot land here at all.
    stored, created = store.tasks.ensure_task(task)
    if not created:
        logger.info(
            "Uppgiften %s fanns redan för källhändelse %s — återanvänds i stället för "
            "att dubbleras.",
            stored.id,
            event.id,
        )
    return ResolutionOutcome(
        kind="create_task",
        label=RESOLUTION_LABELS["create_task"],
        ref_id=stored.id,
        ref_label=f"{stored.title} ({stored.public(today)['status_label']})",
    )


def _due_date_from_spec(event: SourceEvent, spec: dict) -> str:
    """The watch's due date: typed, or computed from a human-supplied anchor.

    ``anchor_date`` is Feature 2: the missing start of an unanchored frist.
    The arithmetic is :func:`app.terms.anchor_relative`, the same function
    Feature 1 uses for day-counts. A received-date never enters here.
    """
    anchor_text = _text(spec, "anchor_date")
    if anchor_text:
        return _due_from_human_anchor(event, spec, anchor_text)
    due = _text(spec, "due_date")
    if parse_iso(due) is None:
        raise ResolutionError("Bevakningen behöver ett datum, skrivet ÅÅÅÅ-MM-DD.")
    return due


def _due_from_human_anchor(event: SourceEvent, spec: dict, anchor_text: str) -> str:
    anchor = parse_iso(anchor_text)
    if anchor is None:
        raise ResolutionError("Ankaret behöver ett datum, skrivet ÅÅÅÅ-MM-DD.")
    questions = list(event.triage.anchor_questions) if event.triage else []
    if not questions:
        raise ResolutionError("Det finns ingen öppen frist att ankra.")
    quote = _text(spec, "quote")
    question = next((q for q in questions if q.quote == quote), questions[0]) if quote else questions[0]
    hit = RelativeHit(
        span=Span(0, 0),
        count=question.count,
        unit=question.unit,
        before=question.before,
        anchor_iso="",
    )
    (anchored,) = anchor_relative([hit], reference_date=anchor)
    return anchored.resolve()


def _create_watch(
    store: Store,
    event: SourceEvent,
    user_id: str,
    spec: dict,
    citations: list[CitationOut],
    today: date,
    key: str,
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

    Feature 2: when the spec carries ``anchor_date`` and the card has an
    unanswered :class:`~app.integrations.models.AnchorQuestion`, the due date
    is computed here through :func:`app.terms.anchor_relative` — the same
    function Feature 1 uses. The human types the missing start; they do not
    type the deadline.
    """
    due = _due_date_from_spec(event, spec)
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
        # Derived from the decision this came out of — see
        # ``derived_output_id``. A retry puts the same obligation on the board
        # once; the random id it replaced put it there twice. Keying it on the
        # kind and the date alone was not enough either: two settlements that
        # agreed on those and disagreed on the title, who is responsible or the
        # reminder produced one row carrying the *first* one's fields.
        id=derived_output_id("monitor", store.tenant_id, key),
        tenant_id=store.tenant_id,
        kind=kind,
        status="approved",
        title=title[:200],
        due_date=due,
        derived_due_date=due,
        derivation=_watch_derivation(event, spec, due),
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


def _watch_derivation(event: SourceEvent, spec: dict, due: str) -> str:
    anchor_text = _text(spec, "anchor_date")
    if anchor_text:
        quote = ""
        if event.triage and event.triage.anchor_questions:
            quote = event.triage.anchor_questions[0].quote
        return (
            f"Fristen «{quote}» räknad från {anchor_text} till {due}, "
            f"angivet av en människa vid granskningen."
        )
    return (
        f"Datum ur inkommande post: {event.subject or '(utan ämne)'} från {event.origin}, "
        f"{(event.occurred_at or event.received_at)[:10]}. Satt av en människa vid granskningen."
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

    An item that is **already settled** accepts only the identical request,
    which returns what that request already did. A different one raises
    :class:`ResolutionConflict` and nothing is written — because the alternative
    is overwriting a named person's decision with no trace that it existed.
    :func:`reopen_source_event` is the operation for changing one's mind, and it
    keeps the old decision.
    """
    integrations = store.integrations
    ordered = _validate(kinds)
    reason = (note or "").strip()
    when = today or date.today()
    key = resolution_key(
        event_id=event_id,
        kinds=kinds,
        note=reason,
        attachment_ids=list(attachment_ids or []),
        task=task,
        watch=watch,
    )

    # One writer at a time across the whole act. Preserving, adopting, creating
    # a task, creating a watch and settling the card are five writes into four
    # different files. The lock serialises *resolutions* against each other; it
    # is not a transaction over the four files and does not pretend to be one —
    # a concurrent ``GET /tasks`` takes the task store's lock, not this one, and
    # can see the task before the card says it made it. What makes that
    # survivable is not the lock but the two properties below it: every id is
    # derived, so the act converges when repeated, and the card carries the key
    # of the request that produced it. See the module docstring.
    with integrations.lock:
        event = integrations.get_source_event(event_id)
        if event is None:
            raise ResolutionError("Okänd källhändelse.")

        if event.resolution is not None:
            if event.resolution.key == key:
                # This exact request already ran. Not an error and not a second
                # resolution: the operator's client retried, or somebody
                # double-clicked, and what they asked for is already true.
                logger.info(
                    "Källhändelse %s är redan avslutad med samma begäran (%s) — svarar med "
                    "det som redan skedde.",
                    event_id,
                    key,
                )
                return event
            # A *different* settlement of an item that already carries one. This
            # used to be allowed, and it overwrote the decision that was there:
            # who had settled it, why, and what it produced were replaced with
            # no record that they had ever existed — the same erasure `reopen`
            # was repaired for, reachable through the ordinary settle button.
            #
            # Changing a settlement is a real thing a board does, and it has an
            # operation: reopen, which *files* the old decision, and then settle
            # again. So this refuses and says which act is missing, rather than
            # guessing that the newer request was meant to win.
            logger.info(
                "Källhändelse %s är redan avslutad (%s) och begäran är en annan (%s) — "
                "vägrar skriva över beslutet.",
                event_id,
                event.resolution.key or "utan nyckel",
                key,
            )
            raise ResolutionConflict(
                "Posten är redan avgjord, och det här är ett annat beslut än det som står "
                "på den. Öppna posten igen först — då sparas det tidigare beslutet i "
                "postens historik — och avgör den sedan på nytt."
            )

        outcomes: list[ResolutionOutcome] = []

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
            outcomes.append(_create_task(store, event, user_id, task or {}, citations, when, key))
        if "monitor" in ordered:
            outcomes.append(_create_watch(store, event, user_id, watch or {}, citations, when, key))
        for kind in ("already_handled", "not_relevant"):
            if kind in ordered:
                outcomes.append(ResolutionOutcome(kind=kind, label=RESOLUTION_LABELS[kind]))

        # The coarse status the rest of the product already reads stays in step
        # with the richer record, so a client that only knows `review_status`
        # (and the mobile app is one) is never shown a settled item as open.
        review_status = "dismissed" if "not_relevant" in ordered else "approved"
        decided_at = utc_now_iso()

        def settle(current: SourceEvent) -> SourceEvent:
            """Record the settlement on the version under the lock.

            ``_preserve`` and the two creators have each written to the event or
            to another domain since it was read, so the update is applied to
            ``current`` rather than to the copy this function started with —
            otherwise settling would silently undo the preservation it had just
            performed.
            """
            return current.model_copy(
                update={
                    "resolution": Resolution(
                        outcomes=outcomes,
                        decided_by=user_id,
                        decided_at=decided_at,
                        note=reason,
                        key=key,
                    ),
                    "review_status": review_status,
                    "decided_by": user_id,
                    "decided_at": decided_at,
                    "decision_note": reason or None,
                }
            )

        return integrations.mutate_source_event(event_id, settle)


def reopen_source_event(
    *, store: Store, event_id: str, user_id: str = "", note: str = ""
) -> SourceEvent:
    """Put a settled item back in the queue.

    What the settlement produced is not touched. A task made from this message
    stays a task, a preserved document stays in the archive, and a watch stays
    on the board — those are records of decisions, and reopening a queue card is
    not a decision about any of them. A reviewer can go and cancel the task
    themselves if that is what they meant.

    **And the settlement itself is not touched either — it is filed.** This used
    to set ``resolution`` to ``None`` and null the decider and the date, which
    read as "put the card back" and was in fact an erasure: after a reopen there
    was nothing anywhere saying the association had ever settled the item, who
    settled it, why, or what it created. The tasks it made were still in
    Uppgifter, with an origin pointing back at a card that now denied making
    them — and "the card says what it produced", the sentence this function's
    own docstring used to rest on, was false the moment it was called.

    So the settlement moves into ``decision_history``
    (:class:`~app.integrations.models.DecisionRecord`) and ``resolution``
    becomes ``None`` as before. The queue reads exactly as it did; the record
    survives. It goes on the source event rather than into a new store for the
    reason this module opens with: there is no email archive here, and a second
    place to look for what was decided about a message would be one.
    """
    integrations = store.integrations

    def apply(event: SourceEvent) -> SourceEvent:
        update: dict = {
            "resolution": None,
            "review_status": "open",
            "decided_by": None,
            "decided_at": None,
        }
        if event.resolution is not None:
            update["decision_history"] = [
                *event.decision_history,
                DecisionRecord(
                    resolution=event.resolution,
                    review_status=event.review_status,
                    superseded_at=utc_now_iso(),
                    superseded_by=user_id,
                    note=(note or "").strip(),
                ),
            ]
        return event.model_copy(update=update)

    try:
        return integrations.mutate_source_event(event_id, apply)
    except SourceEventNotFound as exc:
        raise ResolutionError("Okänd källhändelse.") from exc


__all__ = [
    "MAX_CARRIED_CITATIONS",
    "ResolutionConflict",
    "ResolutionError",
    "derived_output_id",
    "reopen_source_event",
    "resolution_key",
    "resolve_source_event",
]
