"""HTTP surface for tasks.

Same ``tenant_store`` / ``require_admin`` dependencies as everything else, so
tenant isolation is inherited rather than re-argued. Reading needs a
membership; creating and changing needs ``admin``, because a task is the
association taking work on and saying who owns it.

Every mutating route appends to the task's activity before it writes, and the
store refuses a write whose history is shorter than what is already on disk.
That pair is what makes "who moved the deadline, and when" answerable without
anyone having remembered to log it.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date
from typing import Callable

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..store import Store
from ..terms import parse_iso
from .store import TaskNotFound
from .models import (
    ACTIVE_STATUSES,
    ORIGIN_LABELS,
    REASON_REQUIRED,
    TASK_STATUS_LABELS,
    Task,
    TaskEvent,
    TaskOrigin,
)

logger = logging.getLogger("brf.tasks.routes")

STATUSES = tuple(TASK_STATUS_LABELS)
MAX_TITLE = 200


class CreateTaskRequest(BaseModel):
    title: str
    description: str = ""
    responsible: str = ""
    due_date: str | None = None
    origin_kind: str = "manual"
    origin_ref: str = ""


class UpdateTaskRequest(BaseModel):
    """A change to a task. Every field is optional; only what is sent changes."""

    title: str | None = None
    description: str | None = None
    status: str | None = None
    responsible: str | None = None
    due_date: str | None = None
    note: str = ""


class CommentRequest(BaseModel):
    note: str


def build_router(
    *,
    tenant_store: Callable,
    require_admin: Callable,
    current_user: Callable,
    today: Callable[[], date] = date.today,
) -> APIRouter:
    router = APIRouter()

    def _now() -> str:
        from ..integrations.models import utc_now_iso

        return utc_now_iso()

    def _event(user: dict, kind: str, **fields) -> TaskEvent:
        return TaskEvent(
            id=uuid.uuid4().hex[:12], at=_now(), by=user["id"], kind=kind, **fields
        )

    def _origin_evidence(store: Store, kind: str, ref_id: str) -> tuple[TaskOrigin, list, str, str]:
        """Resolve an origin and copy its evidence onto the task.

        The citations are copied rather than referenced on purpose: a finding
        can be re-run and a watch re-dated, and a task should keep saying what
        it was created about. A dangling reference that silently re-describes
        itself would be worse than no reference.
        """
        if kind == "manual":
            return TaskOrigin(kind="manual"), [], "", ""
        if not ref_id:
            raise HTTPException(status_code=422, detail="Ursprunget saknar referens.")
        if kind == "finding":
            finding = store.integrations.get_finding(ref_id)
            if finding is None:
                raise HTTPException(status_code=404, detail="Okänt fynd.")
            label = f"{finding.verdict_label}: {finding.suggestion[:160]}"
            citations = list(finding.citations)
            doc = citations[0].document_id if citations else ""
            name = citations[0].document_name if citations else ""
            return TaskOrigin(kind="finding", ref_id=ref_id, label=label), citations, doc, name
        if kind == "watch":
            watch = store.watches.get_watch(ref_id)
            if watch is None:
                raise HTTPException(status_code=404, detail="Okänd bevakning.")
            label = f"{watch.title} ({watch.due_date})"
            return (
                TaskOrigin(kind="watch", ref_id=ref_id, label=label),
                list(watch.citations),
                watch.source_document_id,
                watch.source_document_name,
            )
        if kind == "invoice_case":
            # Projected, not fetched from disk: a case only reaches storage once
            # somebody acts on it, and taking work on may well be the first act.
            from ..invoices.cases import findings_for_invoice, project_one

            case = project_one(store, ref_id)
            if case is None:
                raise HTTPException(status_code=404, detail="Okänt fakturaärende.")
            label = (
                f"{case.supplier_name} {case.invoice_number or ''}".strip()
                + (f" — {case.total_amount} {case.currency}" if case.total_amount is not None else "")
            )
            # The evidence travels here too: the first finding on the case that
            # has citations lends them to the task, so the passage behind the
            # work still opens after the invoice has been re-read.
            cited = next(
                (
                    f
                    for f in findings_for_invoice(store, case.primary_invoice_id)
                    if f.citations
                ),
                None,
            )
            citations = list(cited.citations) if cited else []
            doc = citations[0].document_id if citations else ""
            name = citations[0].document_name if citations else ""
            return (
                TaskOrigin(kind="invoice_case", ref_id=ref_id, label=label),
                citations,
                doc,
                name,
            )
        if kind == "source_event":
            event = store.integrations.get_source_event(ref_id)
            if event is None:
                raise HTTPException(status_code=404, detail="Okänd källhändelse.")
            label = f"{event.subject or '(utan ämne)'} — från {event.origin}"
            return TaskOrigin(kind="source_event", ref_id=ref_id, label=label), [], "", ""
        raise HTTPException(
            status_code=422, detail=f"Okänt ursprung. Tillåtna: {', '.join(ORIGIN_LABELS)}."
        )

    def _check_due(value: str | None) -> str | None:
        if value is None or value == "":
            return None
        if parse_iso(value) is None:
            raise HTTPException(status_code=422, detail="Datum ska skrivas ÅÅÅÅ-MM-DD.")
        return value

    # ---------- reads ----------

    @router.get("/api/brf/{brf_id}/tasks")
    def list_tasks(access: tuple[Store, str] = Depends(tenant_store)) -> dict:
        """Active work first, then what is closed.

        Grouped on the server for the same reason the watch board is: the
        desktop and the phone must not be able to disagree about what counts as
        overdue.
        """
        store, _ = access
        now = today()
        rows = [t.public(now) for t in store.tasks.list_tasks()]
        active = [t for t in rows if t["active"]]
        # Overdue first, then by date, then the undated — an undated task is
        # not urgent, it is unscheduled, and putting it above a dated one would
        # be a judgement nobody made.
        active.sort(key=lambda t: (not t["overdue"], t["due_date"] or "9999-12-31"))
        return {
            "today": now.isoformat(),
            "active": active,
            "done": [t for t in rows if t["status"] == "done"],
            "cancelled": [t for t in rows if t["status"] == "cancelled"],
            "statusLabels": TASK_STATUS_LABELS,
            "originLabels": ORIGIN_LABELS,
            "counts": {
                "active": len(active),
                "overdue": len([t for t in active if t["overdue"]]),
                "unassigned": len([t for t in active if not t["responsible"]]),
            },
        }

    @router.get("/api/brf/{brf_id}/tasks/for/{kind}/{ref_id}")
    def tasks_for_origin(
        kind: str, ref_id: str, access: tuple[Store, str] = Depends(tenant_store)
    ) -> list[dict]:
        """Work that already exists for a finding, watch or source event."""
        store, _ = access
        now = today()
        return [t.public(now) for t in store.tasks.tasks_for_origin(kind, ref_id)]

    # ---------- writes ----------

    @router.post("/api/brf/{brf_id}/tasks")
    def create_task(
        req: CreateTaskRequest,
        store: Store = Depends(require_admin),
        user: dict = Depends(current_user),
    ) -> dict:
        """Take work on. There is no engine that can do this.

        Findings and watches arrive as proposals because a rule engine can read
        a document. Nobody's obligations follow from that until a person takes
        them on, so creating a task *is* the decision and is recorded as one.
        """
        title = req.title.strip()
        if not title:
            raise HTTPException(status_code=422, detail="Uppgiften behöver en rubrik.")
        if len(title) > MAX_TITLE:
            raise HTTPException(
                status_code=422, detail=f"Rubriken får vara högst {MAX_TITLE} tecken."
            )
        origin, citations, document_id, document_name = _origin_evidence(
            store, req.origin_kind, req.origin_ref.strip()
        )
        now = today()
        task = Task(
            id=uuid.uuid4().hex[:12],
            tenant_id=store.tenant_id,
            title=title,
            description=req.description.strip(),
            responsible=req.responsible.strip(),
            due_date=_check_due(req.due_date),
            origin=origin,
            citations=citations,
            source_document_id=document_id,
            source_document_name=document_name,
            created_by=user["id"],
            created_at=_now(),
        )
        task = task.model_copy(
            update={
                "activity": [
                    _event(
                        user,
                        "created",
                        to_value=title,
                        note=origin.label,
                    )
                ]
            }
        )
        stored = store.tasks.add_task(task)
        if origin.kind == "invoice_case":
            # The case's timeline is the one place a reviewer looks for "what
            # has happened to this invoice", so work taken on from it belongs
            # there. The task itself is still the record; this is a pointer —
            # and writing it is what materialises a case nobody had touched yet.
            from ..invoices.cases import note_task

            try:
                note_task(store, origin.ref_id, task=stored, user_id=user["id"])
            except Exception as exc:
                # Deliberately broad, and the breadth is the point. The task is
                # already committed and is the record; the case entry is a
                # pointer to it. Letting anything thrown here become a 500 would
                # tell the operator their task was not created, and the only
                # thing they can reasonably do next — press the button again —
                # would give the association two identical tasks. Failing to
                # write a cross-reference is not a reason to lie about the write
                # that succeeded, so it is logged with the ids needed to repair
                # it and the created task is returned.
                logger.warning(
                    "Uppgiften %s skapades men kunde inte noteras på fakturaärendet %s: %s",
                    stored.id,
                    origin.ref_id,
                    exc,
                )
        return stored.public(now)

    @router.post("/api/brf/{brf_id}/tasks/{task_id}")
    def update_task(
        task_id: str,
        req: UpdateTaskRequest,
        store: Store = Depends(require_admin),
        user: dict = Depends(current_user),
    ) -> dict:
        note = req.note.strip()
        if req.status is not None and req.status not in STATUSES:
            raise HTTPException(
                status_code=422, detail=f"Ogiltig status. Tillåtna: {', '.join(STATUSES)}."
            )
        if req.due_date is not None:
            _check_due(req.due_date)  # a bad date is a 422 before any lock is taken

        def apply(task: Task) -> Task:
            """What this request changes, decided against the task on disk.

            Every ``!=`` below compares the request with the version read under
            the store's lock, not with one this route read a moment ago. That is
            what makes two people editing the same task at the same time produce
            two events rather than one — and what stops the second write from
            carrying a copy of the history the first one had already extended.
            """
            update: dict = {}
            events: list[TaskEvent] = []

            if req.status is not None and req.status != task.status:
                if req.status in REASON_REQUIRED and not note:
                    # Blocking and cancelling are where the missing sentence is
                    # the one somebody later wishes had been written. Marking
                    # work done needs no note — the trail already says who
                    # closed it and when.
                    raise HTTPException(
                        status_code=422,
                        detail="Ange varför uppgiften blockeras eller avbryts.",
                    )
                update["status"] = req.status
                events.append(
                    _event(
                        user, "status_changed", from_value=task.status, to_value=req.status, note=note
                    )
                )

            if req.responsible is not None and req.responsible.strip() != task.responsible:
                update["responsible"] = req.responsible.strip()
                events.append(
                    _event(
                        user,
                        "assigned",
                        from_value=task.responsible,
                        to_value=req.responsible.strip(),
                    )
                )

            if req.due_date is not None:
                checked = _check_due(req.due_date)
                if checked != task.due_date:
                    update["due_date"] = checked
                    events.append(
                        _event(
                            user, "due_changed", from_value=task.due_date or "", to_value=checked or ""
                        )
                    )

            text_changed = False
            if req.title is not None and req.title.strip() and req.title.strip() != task.title:
                update["title"] = req.title.strip()[:MAX_TITLE]
                text_changed = True
            if req.description is not None and req.description.strip() != task.description:
                update["description"] = req.description.strip()
                text_changed = True
            if text_changed:
                events.append(_event(user, "edited", to_value=update.get("title", task.title)))

            if not events:
                if note:
                    events.append(_event(user, "noted", note=note))
                else:
                    raise HTTPException(status_code=422, detail="Inget att ändra.")

            return task.model_copy(update={**update, "activity": [*task.activity, *events]})

        try:
            updated = store.tasks.mutate_task(task_id, apply)
        except TaskNotFound as exc:
            raise HTTPException(status_code=404, detail="Okänd uppgift.") from exc
        return updated.public(today())

    @router.post("/api/brf/{brf_id}/tasks/{task_id}/comment")
    def comment(
        task_id: str,
        req: CommentRequest,
        store: Store = Depends(require_admin),
        user: dict = Depends(current_user),
    ) -> dict:
        """Say something about the work without changing it.

        A comment is the purest case for :meth:`~app.tasks.store.TaskStore.mutate_task`:
        it needs nothing from the task except the history it is appended to, so
        reading that history anywhere but inside the lock is how eight comments
        became two.
        """
        note = req.note.strip()
        if not note:
            raise HTTPException(status_code=422, detail="Tom kommentar.")
        try:
            updated = store.tasks.mutate_task(
                task_id,
                lambda task: task.model_copy(
                    update={"activity": [*task.activity, _event(user, "noted", note=note)]}
                ),
            )
        except TaskNotFound as exc:
            raise HTTPException(status_code=404, detail="Okänd uppgift.") from exc
        return updated.public(today())

    return router


__all__ = ["CommentRequest", "CreateTaskRequest", "UpdateTaskRequest", "build_router"]
