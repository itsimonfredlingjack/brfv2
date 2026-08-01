"""HTTP surface for watches.

Mounted with the same ``tenant_store`` / ``require_admin`` dependencies as
everything else, so tenant isolation is inherited rather than re-argued.
Reading needs a membership; scanning and every decision needs ``admin``,
because approving a watch is the association taking on an obligation and
dismissing one is the association deciding not to.

The board endpoint computes the buckets server-side. That is deliberate: the
desktop view and the phone must not be able to disagree about what "snart"
means, and "snart" is a function of each watch's own reminder lead time rather
than a fixed window.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Callable

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..store import Store
from .derive import scan_documents
from .models import (
    BUCKET_LABELS,
    MAX_REMIND_LEAD_DAYS,
    WATCH_KIND_LABELS,
    WATCH_STATUS_LABELS,
    Watch,
)
from ..terms import parse_iso

logger = logging.getLogger("brf.watches.routes")

DECISIONS = ("proposed", "approved", "dismissed", "done")


class WatchDecision(BaseModel):
    """What a human does to a proposal.

    Every field except ``status`` is optional and only applied when present, so
    "approve this as it stands" and "approve it but the date is the 30th" are
    the same call with one extra field rather than two endpoints.
    """

    status: str
    due_date: str | None = None
    responsible: str | None = None
    remind_lead_days: int | None = None
    note: str | None = None


def build_router(
    *,
    tenant_store: Callable,
    require_admin: Callable,
    current_user: Callable,
    today: Callable[[], date] = date.today,
) -> APIRouter:
    router = APIRouter()

    def _now_iso() -> str:
        from ..integrations.models import utc_now_iso

        return utc_now_iso()

    @router.get("/api/brf/{brf_id}/watches")
    def list_watches(access: tuple[Store, str] = Depends(tenant_store)) -> dict:
        """Everything, grouped the way a board reads it.

        Proposals are kept apart from the buckets rather than mixed in. A
        suggestion nobody has looked at is not an obligation the association
        has, and a view that blends the two is a view that quietly commits
        people to things a rule engine invented.
        """
        store, _ = access
        now = today()
        rows = store.watches.list_watches()
        buckets: dict[str, list[dict]] = {key: [] for key in BUCKET_LABELS}
        proposed: list[dict] = []
        settled: list[dict] = []
        for watch in rows:
            public = watch.public(now)
            if watch.status == "proposed":
                proposed.append(public)
            elif watch.status == "approved":
                buckets[public["bucket"]].append(public)
            else:
                settled.append(public)
        return {
            "today": now.isoformat(),
            "proposed": proposed,
            "buckets": buckets,
            "bucketLabels": BUCKET_LABELS,
            "kindLabels": WATCH_KIND_LABELS,
            "statusLabels": WATCH_STATUS_LABELS,
            "settled": settled,
            "unresolved": [u.model_dump(mode="json") for u in store.watches.list_unresolved()],
        }

    @router.post("/api/brf/{brf_id}/watches/scan")
    def scan(store: Store = Depends(require_admin)) -> dict:
        """Re-read the archive and propose what can be dated.

        Never touches a watch a human has decided on — see
        :meth:`app.watches.store.WatchStore.replace_proposals`.
        """
        result = scan_documents(store, now_iso=_now_iso())
        fresh, unresolved = store.watches.replace_proposals(result.watches, result.unresolved)
        now = today()
        return {
            "documentsRead": result.documents_read,
            "proposed": [w.public(now) for w in fresh],
            "unresolved": [u.model_dump(mode="json") for u in unresolved],
        }

    @router.post("/api/brf/{brf_id}/watches/{watch_id}/decision")
    def decide(
        watch_id: str,
        req: WatchDecision,
        store: Store = Depends(require_admin),
        user: dict = Depends(current_user),
    ) -> dict:
        if req.status not in DECISIONS:
            raise HTTPException(
                status_code=422, detail=f"Ogiltig status. Tillåtna: {', '.join(DECISIONS)}."
            )
        watch = store.watches.get_watch(watch_id)
        if watch is None:
            raise HTTPException(status_code=404, detail="Okänd bevakning.")

        update: dict = {"status": req.status}
        if req.due_date is not None:
            if parse_iso(req.due_date) is None:
                raise HTTPException(status_code=422, detail="Datum ska vara ÅÅÅÅ-MM-DD.")
            update["due_date"] = req.due_date
        if req.responsible is not None:
            update["responsible"] = req.responsible.strip()
        if req.remind_lead_days is not None:
            if not 0 <= req.remind_lead_days <= MAX_REMIND_LEAD_DAYS:
                raise HTTPException(
                    status_code=422,
                    detail=f"Påminnelse ska ligga 0–{MAX_REMIND_LEAD_DAYS} dagar före.",
                )
            update["remind_lead_days"] = req.remind_lead_days

        note = (req.note or "").strip()
        if req.status == "dismissed" and not note:
            # Same rule as a corrected finding: dismissing an obligation the
            # engine read out of the association's own contract is a decision
            # that somebody may have to defend later, and "nobody said why" is
            # not a defence.
            raise HTTPException(
                status_code=422,
                detail="Ange varför bevakningen avfärdas — vad gäller i stället?",
            )
        if req.status != "proposed":
            update["decided_by"] = user["id"]
            update["decided_at"] = _now_iso()
        else:
            update["decided_by"] = None
            update["decided_at"] = None
        update["decision_note"] = note or None

        updated = store.watches.update_watch(watch.model_copy(update=update))
        now = today()

        # Completing a recurring obligation creates the next turn rather than
        # editing this one, so the history of what was actually done survives.
        successor = None
        if req.status == "done" and updated.recurrence != "none":
            next_due = updated.next_due_after()
            if next_due:
                import uuid

                successor = store.watches.add_watch(
                    updated.model_copy(
                        update={
                            "id": uuid.uuid4().hex[:12],
                            "status": "approved",
                            "due_date": next_due,
                            "derived_due_date": next_due,
                            "derivation": f"{updated.due_date} plus ett intervall ({updated.recurrence})",
                            "title": updated.title.replace(updated.due_date, next_due),
                            "created_at": _now_iso(),
                            "decided_by": None,
                            "decided_at": None,
                            "decision_note": None,
                            "succeeded_by": None,
                        }
                    )
                )
                updated = store.watches.update_watch(
                    updated.model_copy(update={"succeeded_by": successor.id})
                )

        return {
            "watch": updated.public(now),
            "successor": successor.public(now) if successor else None,
        }

    @router.delete("/api/brf/{brf_id}/watches/{watch_id}")
    def delete_watch(watch_id: str, store: Store = Depends(require_admin)) -> dict:
        """Remove a proposal outright. A decided watch is a record and stays."""
        watch = store.watches.get_watch(watch_id)
        if watch is None:
            raise HTTPException(status_code=404, detail="Okänd bevakning.")
        if watch.status != "proposed":
            raise HTTPException(
                status_code=409,
                detail="En bevakning som någon tagit ställning till raderas inte. "
                "Markera den som avklarad eller avfärdad i stället.",
            )
        store.watches.delete_watch(watch_id)
        return {"deleted": watch_id}

    return router


__all__ = ["WatchDecision", "build_router"]
