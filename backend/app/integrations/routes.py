"""HTTP surface for the integration domain.

Registered onto the product app by :func:`app.main.create_app`, using the same
``tenant_store`` / ``require_admin`` dependencies as every other tenant-scoped
route. That is deliberate and load-bearing: these routes get tenant isolation
from the dependency that already resolves an authenticated membership to one
``Store``, so there is no second authorisation path to keep correct, and a
non-member gets the same 404 — never 403 — that keeps tenant ids unprobeable.

Read routes need a membership. Anything that changes state — importing a
message, reading an invoice into the tenant, running a review, recording a
human decision — needs ``admin``, because all four are acts the association is
answerable for.

There is no route here that writes to an external system, because there is no
adapter method that could.
"""

from __future__ import annotations

import logging
from typing import Callable

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel

from ..store import Store
from .accounting_fixture import FixtureAccountingAdapter, FixtureError
from .eml import EmlRejected, accepted_format
from .intake import DuplicateSourceEvent, import_eml
from .models import FindingStatus, ReviewStatus
from .review import review_invoice

logger = logging.getLogger("brf.integrations.routes")

# Ceiling for an uploaded .eml at the HTTP layer. The parser has its own, lower
# limit; this one exists so an oversized body is refused before it is buffered
# and hashed.
MAX_EML_BYTES = 26 * 1024 * 1024


class DecisionRequest(BaseModel):
    status: str
    note: str | None = None
    linked_document_ids: list[str] | None = None


class ImportInvoiceRequest(BaseModel):
    external_ref: str


def build_router(
    *,
    tenant_store: Callable,
    require_admin: Callable,
    current_user: Callable,
    accounting_adapter: FixtureAccountingAdapter | None = None,
) -> APIRouter:
    router = APIRouter()
    adapter = accounting_adapter or FixtureAccountingAdapter()

    # ---------- what this version accepts ----------

    @router.get("/api/brf/{brf_id}/integrations/format")
    def get_format(access: tuple[Store, str] = Depends(tenant_store)) -> dict:
        """The accepted import format, straight from the parser's own constants.

        Served rather than duplicated in the UI so the dialog that tells an
        operator what may be imported cannot drift from the code that decides.
        """
        return {"mail": accepted_format(), "accountingAdapter": adapter.name}

    # ---------- source events ----------

    @router.get("/api/brf/{brf_id}/integrations/source-events")
    def list_source_events(access: tuple[Store, str] = Depends(tenant_store)) -> list[dict]:
        store, _ = access
        return [e.model_dump(mode="json") for e in store.integrations.list_source_events()]

    @router.get("/api/brf/{brf_id}/integrations/source-events/{event_id}")
    def get_source_event(
        event_id: str, access: tuple[Store, str] = Depends(tenant_store)
    ) -> dict:
        store, _ = access
        event = store.integrations.get_source_event(event_id)
        if event is None:
            raise HTTPException(status_code=404, detail="Okänd källhändelse.")
        return event.model_dump(mode="json")

    @router.post("/api/brf/{brf_id}/integrations/source-events")
    async def import_source_event(
        file: UploadFile,
        store: Store = Depends(require_admin),
        user: dict = Depends(current_user),
    ) -> dict:
        filename = file.filename or "meddelande.eml"
        if not filename.lower().endswith(".eml"):
            raise HTTPException(
                status_code=400,
                detail="Endast .eml-filer tas emot. Exportera meddelandet ur din e-postklient.",
            )
        data = await file.read()
        if len(data) > MAX_EML_BYTES:
            raise HTTPException(status_code=413, detail="Filen är större än 26 MB.")
        try:
            event = import_eml(
                store=store,
                integrations=store.integrations,
                raw=data,
                filename=filename,
                imported_by=user["id"],
            )
        except DuplicateSourceEvent as exc:
            # 409, not 200-with-a-note: the caller asked to create something and
            # nothing was created. The existing id is returned so the UI can
            # take the operator to what they already have.
            raise HTTPException(
                status_code=409,
                detail=str(exc),
                headers={"X-Existing-Source-Event": exc.existing.id},
            ) from exc
        except EmlRejected as exc:
            raise HTTPException(
                status_code=422,
                detail=exc.message,
                headers={"X-Import-Rejection": exc.code},
            ) from exc
        return event.model_dump(mode="json")

    @router.post("/api/brf/{brf_id}/integrations/source-events/{event_id}/decision")
    def decide_source_event(
        event_id: str,
        req: DecisionRequest,
        store: Store = Depends(require_admin),
        user: dict = Depends(current_user),
    ) -> dict:
        from .models import utc_now_iso

        allowed = ("open", "approved", "dismissed", "corrected")
        if req.status not in allowed:
            raise HTTPException(
                status_code=422, detail=f"Ogiltig status. Tillåtna: {', '.join(allowed)}."
            )
        integrations = store.integrations
        event = integrations.get_source_event(event_id)
        if event is None:
            raise HTTPException(status_code=404, detail="Okänd källhändelse.")

        links = event.linked_document_ids
        if req.linked_document_ids is not None:
            unknown = [d for d in req.linked_document_ids if d not in store.documents]
            if unknown:
                raise HTTPException(
                    status_code=422,
                    detail=f"Okända dokument: {', '.join(unknown)}.",
                )
            links = req.linked_document_ids

        updated = event.model_copy(
            update={
                "review_status": req.status,
                "linked_document_ids": links,
                "decided_by": user["id"] if req.status != "open" else None,
                "decided_at": utc_now_iso() if req.status != "open" else None,
                "decision_note": req.note,
            }
        )
        return integrations.update_source_event(updated).model_dump(mode="json")

    @router.delete("/api/brf/{brf_id}/integrations/source-events/{event_id}")
    def delete_source_event(event_id: str, store: Store = Depends(require_admin)) -> dict:
        """Remove a queue entry. Ingested documents stay.

        Deliberately not a cascade: an attachment that went through ingestion is
        a document of the association's now, cited in answers and possibly
        linked elsewhere. Deleting the envelope must not silently take the
        contents with it — the documents view is where a document is deleted.
        """
        if not store.integrations.delete_source_event(event_id):
            raise HTTPException(status_code=404, detail="Okänd källhändelse.")
        return {"deleted": event_id}

    # ---------- invoices ----------

    @router.get("/api/brf/{brf_id}/integrations/available-invoices")
    def list_available_invoices(
        brf_id: str, access: tuple[Store, str] = Depends(tenant_store)
    ) -> dict:
        """What the read-only adapter can offer. Nothing is stored by looking."""
        try:
            rows = adapter.list_invoices(brf_id)
        except FixtureError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return {"adapter": adapter.name, "invoices": rows}

    @router.get("/api/brf/{brf_id}/integrations/invoices")
    def list_invoices(access: tuple[Store, str] = Depends(tenant_store)) -> list[dict]:
        store, _ = access
        return [i.model_dump(mode="json") for i in store.integrations.list_invoices()]

    @router.post("/api/brf/{brf_id}/integrations/invoices")
    def import_invoice(
        brf_id: str, req: ImportInvoiceRequest, store: Store = Depends(require_admin)
    ) -> dict:
        """Read one invoice into this tenant. A read there, a write only here."""
        try:
            snapshot = adapter.get_invoice(brf_id, req.external_ref.strip())
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except FixtureError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return store.integrations.upsert_invoice(snapshot).model_dump(mode="json")

    @router.post("/api/brf/{brf_id}/integrations/invoices/{invoice_id}/review")
    def run_review(invoice_id: str, store: Store = Depends(require_admin)) -> dict:
        integrations = store.integrations
        invoice = integrations.get_invoice(invoice_id)
        if invoice is None:
            raise HTTPException(status_code=404, detail="Okänd faktura.")
        findings = review_invoice(store, invoice)
        stored = integrations.replace_findings_for_invoice(invoice_id, findings)
        return {
            "invoice": invoice.model_dump(mode="json"),
            "findings": [f.model_dump(mode="json") for f in stored],
        }

    # ---------- findings ----------

    @router.get("/api/brf/{brf_id}/integrations/findings")
    def list_findings(access: tuple[Store, str] = Depends(tenant_store)) -> list[dict]:
        store, _ = access
        return [f.model_dump(mode="json") for f in store.integrations.list_findings()]

    @router.post("/api/brf/{brf_id}/integrations/findings/{finding_id}/decision")
    def decide_finding(
        finding_id: str,
        req: DecisionRequest,
        store: Store = Depends(require_admin),
        user: dict = Depends(current_user),
    ) -> dict:
        from .models import utc_now_iso

        allowed = ("open", "approved", "dismissed", "corrected")
        if req.status not in allowed:
            raise HTTPException(
                status_code=422, detail=f"Ogiltig status. Tillåtna: {', '.join(allowed)}."
            )
        integrations = store.integrations
        finding = integrations.get_finding(finding_id)
        if finding is None:
            raise HTTPException(status_code=404, detail="Okänt fynd.")
        if req.status == "corrected" and not (req.note or "").strip():
            # A correction without a note records that someone disagreed and
            # nothing about what is actually true. That is worse than an open
            # finding, because it looks handled.
            raise HTTPException(
                status_code=422,
                detail="En korrigering måste beskrivas — ange vad som gäller i stället.",
            )
        updated = finding.model_copy(
            update={
                "status": req.status,
                "decided_by": user["id"] if req.status != "open" else None,
                "decided_at": utc_now_iso() if req.status != "open" else None,
                "decision_note": req.note,
            }
        )
        return integrations.update_finding(updated).model_dump(mode="json")

    return router


__all__ = ["build_router", "DecisionRequest", "ImportInvoiceRequest", "MAX_EML_BYTES"]
