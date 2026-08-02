"""HTTP surface for the invoice workspace.

Same ``tenant_store`` / ``require_admin`` dependencies as every other
tenant-scoped route, so isolation is inherited rather than re-argued and a
non-member gets 404 — never 403 — exactly as everywhere else.

Reading needs a membership. Everything that changes state needs ``admin``:
reading an invoice into the association, running the analysis, setting the
local review status, naming somebody responsible, writing a comment. All five
are acts the association is answerable for.

**Nothing here writes to Fortnox, and nothing here could.** The only outbound
call any of these routes can make is the same read-only GET the integrations
block already owns (:mod:`app.integrations.sources`), and the adapter behind it
has no write verb for :mod:`app.integrations.protocols` to allow.

Two reads serve the whole screen — the queue and one case — because the
alternative renders in stages and can show a row whose badge disagrees with its
buttons. A third exists for one thing only: opening a superseded analysis,
which nobody reads until they ask for it and which would otherwise be carried,
whole, on every case read.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Callable

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..integrations.accounting_fixture import FixtureAccountingAdapter, FixtureError
from ..integrations.connections import ConnectionManager, PROVIDER_FORTNOX
from ..integrations.models import FINDING_TYPE_LABELS, VERDICT_LABELS
from ..integrations.oauth import PendingLogins
from ..integrations.sources import INVOICE_SOURCES, accounting_source, live_runner
from ..store import Store
from . import cases as case_ops
from .identity import case_key_for
from .models import (
    ANALYSIS_ENGINE_VERSION,
    CHANGE_LABELS,
    ENGINE,
    REVIEW_STATUS_CAVEATS,
    REVIEW_STATUS_LABELS,
    SIGNAL_LABELS,
    SIGNAL_SEVERITY,
    InvoiceCase,
)

logger = logging.getLogger("brf.invoices.routes")

# Which adapter a case came out of, mapped back to the source name a refresh
# has to ask for. Kept explicit: guessing "it must be Fortnox because Fortnox is
# connected" is how a demo installation silently starts making live calls.
ADAPTER_SOURCES: dict[str, str] = {
    "fixture-accounting": "fixture",
    "fortnox": "fortnox",
}


class ImportRequest(BaseModel):
    external_ref: str
    source: str = "fixture"


class CaseUpdateRequest(BaseModel):
    """A change to a case. Only what is sent changes."""

    review_status: str | None = None
    responsible: str | None = None
    note: str = ""


class CommentRequest(BaseModel):
    note: str


def build_router(
    *,
    tenant_store: Callable,
    require_admin: Callable,
    current_user: Callable,
    accounting_adapter: FixtureAccountingAdapter | None = None,
    pending_logins: PendingLogins | None = None,
    transport=None,
    today: Callable[[], date] = date.today,
) -> APIRouter:
    router = APIRouter()
    fixture = accounting_adapter or FixtureAccountingAdapter()
    logins = pending_logins or PendingLogins()

    def manager(store: Store) -> ConnectionManager:
        return ConnectionManager(
            store.integrations.credentials, pending=logins, transport=transport
        )

    def _case(store: Store, case_id: str) -> InvoiceCase:
        """The projected case, whether or not it has ever been written to disk."""
        case = case_ops.project_one(store, case_id)
        if case is None:
            raise HTTPException(status_code=404, detail="Okänt fakturaärende.")
        return case

    def _labels() -> dict:
        return {
            "reviewStatus": REVIEW_STATUS_LABELS,
            "reviewStatusCaveats": REVIEW_STATUS_CAVEATS,
            "signals": SIGNAL_LABELS,
            "signalSeverity": SIGNAL_SEVERITY,
            "verdicts": VERDICT_LABELS,
            "findingTypes": FINDING_TYPE_LABELS,
            "changes": CHANGE_LABELS,
            # The rules the *code* runs now. A client compares it against the
            # version stamped on the case to tell a fresh conclusion from one
            # nobody has re-run since the rules changed.
            "engineVersion": ANALYSIS_ENGINE_VERSION,
            "engine": ENGINE,
        }

    def _read_snapshot(store: Store, source: str, external_ref: str):
        """Read one invoice out of a named source. A read there, a write only here."""
        try:
            if source == "fixture":
                return accounting_source(
                    store, source, fixture=fixture, manager=manager(store)
                ).get_invoice(store.tenant_id, external_ref.strip())
            # Resolving the source is itself a live act — it may find that
            # nobody has connected anything — so it happens inside the wrapper
            # that turns that into a 409 rather than a 500.
            live = live_runner(store, PROVIDER_FORTNOX, manager(store))
            return live(
                lambda: accounting_source(
                    store, source, fixture=fixture, manager=manager(store)
                ).get_invoice(store.tenant_id, external_ref.strip())
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except FixtureError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    # ---------- the queue ----------

    @router.get("/api/brf/{brf_id}/invoices")
    def workspace(access: tuple[Store, str] = Depends(tenant_store)) -> dict:
        """Every invoice case, with what it is, where it stands and what it needs.

        A **read**, in the ordinary sense: :func:`app.invoices.cases.project`
        computes the cases the tenant's records imply and writes nothing. An
        invoice read before this workspace existed — or through the incoming
        pane — therefore appears here with no migration step and without a GET
        quietly creating records. A case is written to disk the first time
        somebody acts on it, and not before.
        """
        store, _ = access
        now = today()
        rows = case_ops.project(store)
        return {
            "today": now.isoformat(),
            "cases": [c.public(now) for c in rows],
            "counts": case_ops.totals(rows, now),
            "labels": _labels(),
            "sources": list(INVOICE_SOURCES),
            "suppliers": sorted({c.supplier_name for c in rows if c.supplier_name}),
            "responsibles": sorted({c.responsible for c in rows if c.responsible}),
        }

    # ---------- one case ----------

    @router.get("/api/brf/{brf_id}/invoices/cases/{case_id}")
    def read_case(case_id: str, access: tuple[Store, str] = Depends(tenant_store)) -> dict:
        """One case with everything a reviewer needs, in one read."""
        store, _ = access
        now = today()
        case = _case(store, case_id)
        snapshot = store.integrations.get_invoice(case.primary_invoice_id)
        findings = case_ops.findings_for_invoice(store, case.primary_invoice_id)

        tasks = [t.public(now) for t in store.tasks.tasks_for_origin("invoice_case", case.id)]
        finding_ids = {f.id for f in findings}
        for finding_id in finding_ids:
            tasks.extend(
                t.public(now) for t in store.tasks.tasks_for_origin("finding", finding_id)
            )

        source_event = None
        for observation in case.observations:
            if observation.kind == "email":
                event = store.integrations.get_source_event(observation.ref_id)
                if event is not None:
                    source_event = event.model_dump(mode="json")
                    break

        return {
            "today": now.isoformat(),
            "case": case.public(now),
            "invoice": snapshot.model_dump(mode="json") if snapshot else None,
            "findings": [f.model_dump(mode="json") for f in findings],
            "documents": case_ops.documents_for(store, case),
            "sourceEvent": source_event,
            "supplier": case_ops.supplier_context(store, case, now),
            "tasks": tasks,
            # Every recorded analysis, newest first, *without* the superseded
            # findings themselves — those are one request away and nobody reads
            # them until they ask. What is here is enough to see that a run
            # replaced another, what it read, what changed and under which
            # rules.
            "analyses": [run.public() for run in case_ops.analysis_runs(store, case)],
            "labels": _labels(),
        }

    @router.get("/api/brf/{brf_id}/invoices/cases/{case_id}/analyses/{run_id}")
    def read_analysis(
        case_id: str, run_id: str, access: tuple[Store, str] = Depends(tenant_store)
    ) -> dict:
        """One recorded analysis, with the findings it replaced.

        The third read in this product area, and the exception is deliberate:
        carrying every superseded finding — citations, quotes and all — on every
        case read would grow the payload with records nobody has asked to see.
        A reader who *does* ask gets the version whole, exactly as it stood.

        Reading needs a membership only. An audit trail a reviewer cannot open
        without admin rights is one the board cannot check, and nothing here
        changes anything.
        """
        store, _ = access
        case = _case(store, case_id)
        run = store.integrations.get_analysis_run(run_id)
        # The case check is what keeps a run id from being a way around it: a
        # run belongs to one invoice, and asking for it under another case is a
        # 404 the same way another tenant's case is.
        if run is None or run.invoice_id != case.primary_invoice_id:
            raise HTTPException(status_code=404, detail="Okänd granskningskörning.")
        return {"case_id": case.id, "run": run.with_replaced(), "labels": _labels()}

    @router.post("/api/brf/{brf_id}/invoices/cases/{case_id}")
    def update_case(
        case_id: str,
        req: CaseUpdateRequest,
        store: Store = Depends(require_admin),
        user: dict = Depends(current_user),
    ) -> dict:
        """Set this association's own review status, or name who is looking.

        Neither is an approval in anyone else's system. The status labels say
        so and :data:`app.invoices.models.REVIEW_STATUS_CAVEATS` carries the
        sentence that spells it out, so a client cannot show the label without
        being able to show what it does not mean.
        """
        case = _case(store, case_id)
        changed = False
        try:
            if req.responsible is not None:
                case = case_ops.assign(
                    store, case.id, responsible=req.responsible, user_id=user["id"]
                )
                changed = True
            if req.review_status is not None:
                case = case_ops.set_review_status(
                    store, case.id, status=req.review_status, note=req.note, user_id=user["id"]
                )
                changed = True
        except case_ops.CaseError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if not changed:
            raise HTTPException(status_code=422, detail="Inget att ändra.")
        return case.public(today())

    @router.post("/api/brf/{brf_id}/invoices/cases/{case_id}/comment")
    def comment_case(
        case_id: str,
        req: CommentRequest,
        store: Store = Depends(require_admin),
        user: dict = Depends(current_user),
    ) -> dict:
        case = _case(store, case_id)
        try:
            case = case_ops.comment(store, case.id, text=req.note, user_id=user["id"])
        except case_ops.CaseError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return case.public(today())

    @router.post("/api/brf/{brf_id}/invoices/cases/{case_id}/refresh")
    def refresh_case(
        case_id: str,
        reread: bool = True,
        store: Store = Depends(require_admin),
    ) -> dict:
        """Read the invoice again and run the analysis again.

        Idempotent by construction. The snapshot keeps its identity across a
        re-read, converging on the same case; open findings are replaced while
        decided ones are kept; and every machine timeline entry carries a key
        derived from what it says, so a refresh that finds nothing new adds
        nothing to the history. Pressing this twice leaves exactly the same
        records as pressing it once.

        A refresh that *does* find something new is written down rather than
        applied silently: the superseded findings, the reading they were built
        on and the rules that produced them are kept as an
        :class:`~app.invoices.models.AnalysisRun`, readable under
        ``/analyses/{run_id}``.
        """
        case = _case(store, case_id)
        source_note = "Källan lästes inte om."
        if reread:
            observation = next(
                (o for o in case.observations if o.kind == "accounting_snapshot"), None
            )
            source = ADAPTER_SOURCES.get(observation.adapter if observation else "", "")
            if source and observation:
                try:
                    snapshot = _read_snapshot(store, source, observation.external_ref)
                except HTTPException as exc:
                    # The other system being unreachable, signed out, or no
                    # longer holding this invoice must not make the case
                    # unreviewable. The analysis still runs against what is
                    # already read in, and the reason the re-read failed is
                    # returned rather than swallowed — a refresh that quietly
                    # did half of what it said is worse than one that says so.
                    source_note = (
                        f"Fakturan kunde inte läsas om ur {source}: {exc.detail} "
                        "Granskningen kördes mot det som redan är inläst."
                    )
                else:
                    store.integrations.upsert_invoice(snapshot)
                    source_note = f"Fakturan lästes om ur {source}."
            else:
                source_note = (
                    "Ärendet har ingen känd fakturakälla att läsa om — granskningen kördes "
                    "mot det som redan är inläst."
                )
        try:
            case = case_ops.analyse_case(store, case.id)
        except case_ops.CaseError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {"case": case.public(today()), "source": source_note}

    # ---------- reading an invoice in ----------

    @router.post("/api/brf/{brf_id}/invoices/import")
    def import_invoice(
        req: ImportRequest,
        store: Store = Depends(require_admin),
    ) -> dict:
        """Read one invoice into this tenant, converge it and analyse it.

        One operator action, because it is one intention: nobody reads an
        invoice in order to leave it unexamined. Reading the same reference
        again lands on the same case and the same snapshot id rather than
        producing a second of either.
        """
        snapshot = _read_snapshot(store, req.source, req.external_ref)
        stored = store.integrations.upsert_invoice(snapshot)
        # The id is derived from the invoice's identity, so reading the same
        # reference again resolves to the same case rather than creating a
        # second one — including when two operators press the button at once.
        case_id = case_ops.case_id_for(store.tenant_id, case_key_for(stored)[0])
        try:
            case = case_ops.analyse_case(store, case_id)
        except case_ops.CaseError as exc:  # pragma: no cover - defensive
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return case.public(today())

    return router


__all__ = ["ADAPTER_SOURCES", "CaseUpdateRequest", "CommentRequest", "ImportRequest", "build_router"]
