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

import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel

from ..store import Store
from .accounting_fixture import FixtureAccountingAdapter, FixtureError
from .connections import ConnectionManager, NotConnected, PROVIDER_FORTNOX, PROVIDER_GRAPH
from .credentials import ConnectionError_
from .egress import EgressRefused, RemoteError
from .eml import EmlRejected, accepted_format
from .fortnox import FortnoxConfig, FortnoxConfigError
from .graph_mail import GraphConfig, GraphConfigError, WELL_KNOWN_FOLDERS
from .intake import (
    AdoptionError,
    DuplicateSourceEvent,
    adopt_attachment,
    import_eml,
    withdraw_attachment,
)
from .models import FindingStatus, ReviewStatus, SupplierAlias, utc_now_iso
from .oauth import OAuthError, PendingLogins
from .review import review_invoice
from .supplier import normalize as normalize_supplier

logger = logging.getLogger("brf.integrations.routes")

# Ceiling for an uploaded .eml at the HTTP layer. The parser has its own, lower
# limit; this one exists so an oversized body is refused before it is buffered
# and hashed.
MAX_EML_BYTES = 26 * 1024 * 1024

# Where an invoice may be read from. "fixture" is the synthetic dataset the
# block shipped with and keeps working with no credential at all; "fortnox" is
# a live, connected company. Named in the request rather than inferred from
# what happens to be connected, so a demo and a live read cannot be confused
# for one another in a screenshot.
INVOICE_SOURCES = ("fixture", "fortnox")


class DecisionRequest(BaseModel):
    status: str
    note: str | None = None
    linked_document_ids: list[str] | None = None


class ImportInvoiceRequest(BaseModel):
    external_ref: str
    source: str = "fixture"


class GraphConfigRequest(BaseModel):
    client_id: str
    authority: str = "consumers"
    mailbox: str = ""
    folder: str = "inbox"


class FortnoxConfigRequest(BaseModel):
    client_id: str
    client_secret: str = ""
    redirect_uri: str
    read_supplier_register: bool = False


class CompleteLoginRequest(BaseModel):
    code: str = ""
    state: str = ""


class AliasRequest(BaseModel):
    invoice_name: str
    document_name: str
    note: str | None = None


class ArchiveRequest(BaseModel):
    note: str


def build_router(
    *,
    tenant_store: Callable,
    require_admin: Callable,
    current_user: Callable,
    accounting_adapter: FixtureAccountingAdapter | None = None,
    pending_logins: PendingLogins | None = None,
    transport=None,
) -> APIRouter:
    router = APIRouter()
    adapter = accounting_adapter or FixtureAccountingAdapter()
    # One per application, not one per request: a device-code sign-in spans
    # several HTTP calls and has to be findable in between. Per tenant inside,
    # so two associations on one installation cannot see each other's.
    logins = pending_logins or PendingLogins()

    def manager(store: Store) -> ConnectionManager:
        return ConnectionManager(
            store.integrations.credentials, pending=logins, transport=transport
        )

    def _live(store: Store, provider: str):
        """Run a live call, turning every failure into an operator-readable 4xx.

        Everything that can go wrong here is about the *other* system or the
        connection to it, and none of it is a bug in this request — so none of
        it should read as a 500. The connection also records what happened, so
        the UI can show "återkallad" instead of an error that looks transient.
        """

        def run(fn):
            try:
                return fn()
            except NotConnected as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            except OAuthError as exc:
                raise HTTPException(status_code=409, detail=exc.message) from exc
            except EgressRefused as exc:
                # A refused URL is a bug in *this* product, and it is louder
                # than a 4xx would suggest — so it is logged with its code and
                # returned as a plain refusal rather than dressed up.
                logger.error("Utgående anrop vägrades (%s): %s", exc.code, exc.message)
                raise HTTPException(status_code=502, detail=exc.message) from exc
            except RemoteError as exc:
                manager(store).note_failure(provider, exc)
                raise HTTPException(
                    status_code=502, detail=f"{provider}: {exc.detail}"
                ) from exc

        return run

    # ---------- what this version accepts ----------

    @router.get("/api/brf/{brf_id}/integrations/format")
    def get_format(access: tuple[Store, str] = Depends(tenant_store)) -> dict:
        """The accepted import format, straight from the parser's own constants.

        Served rather than duplicated in the UI so the dialog that tells an
        operator what may be imported cannot drift from the code that decides.
        """
        return {
            "mail": accepted_format(),
            "accountingAdapter": adapter.name,
            "invoiceSources": list(INVOICE_SOURCES),
            "mailFolders": list(WELL_KNOWN_FOLDERS),
        }

    # ---------- live connections ----------
    #
    # Configuration and sign-in are separate acts (see credentials.py), and
    # both are admin: pointing an installation at a mailbox and signing in to
    # it are things the association is answerable for.

    @router.get("/api/brf/{brf_id}/integrations/connections")
    def get_connections(access: tuple[Store, str] = Depends(tenant_store)) -> dict:
        """Connection status. Contains no secret — see credentials.Connection."""
        store, _ = access
        return manager(store).status()

    @router.put("/api/brf/{brf_id}/integrations/connections/microsoft-graph")
    def configure_graph(
        req: GraphConfigRequest,
        store: Store = Depends(require_admin),
        user: dict = Depends(current_user),
    ) -> dict:
        try:
            connection = manager(store).configure_graph(
                GraphConfig(
                    client_id=req.client_id,
                    authority=req.authority,
                    mailbox=req.mailbox,
                    folder=req.folder,
                ),
                user_id=user["id"],
            )
        except (GraphConfigError, ConnectionError_) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return connection.public()

    @router.put("/api/brf/{brf_id}/integrations/connections/fortnox")
    def configure_fortnox(
        req: FortnoxConfigRequest,
        store: Store = Depends(require_admin),
        user: dict = Depends(current_user),
    ) -> dict:
        try:
            connection = manager(store).configure_fortnox(
                FortnoxConfig(
                    client_id=req.client_id,
                    redirect_uri=req.redirect_uri,
                    read_supplier_register=req.read_supplier_register,
                ),
                client_secret=req.client_secret,
                user_id=user["id"],
            )
        except (FortnoxConfigError, ConnectionError_) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return connection.public()

    @router.post("/api/brf/{brf_id}/integrations/connections/{provider}/login")
    def begin_login(provider: str, store: Store = Depends(require_admin)) -> dict:
        """Start a sign-in. Returns what the operator has to do next."""
        return _live(store, provider)(lambda: manager(store).begin_login(provider).public())

    @router.post("/api/brf/{brf_id}/integrations/connections/{provider}/login/poll")
    def poll_login(
        provider: str,
        store: Store = Depends(require_admin),
        user: dict = Depends(current_user),
    ) -> dict:
        """One poll of a device-code sign-in. "pending" while the operator types."""
        connection = _live(store, provider)(
            lambda: manager(store).finish_device_login(provider, user_id=user["id"])
        )
        if connection is None:
            return {"status": "pending"}
        return {"status": "connected", "connection": connection.public()}

    @router.post("/api/brf/{brf_id}/integrations/connections/{provider}/login/complete")
    def complete_login(
        provider: str,
        req: CompleteLoginRequest,
        store: Store = Depends(require_admin),
        user: dict = Depends(current_user),
    ) -> dict:
        code = req.code.strip()
        if not code:
            raise HTTPException(status_code=422, detail="Ingen kod angiven.")
        # An operator pastes the whole redirect address as often as the bare
        # code, and telling them off for it would be pedantry: pull the two
        # parameters out and use them.
        state = req.state.strip()
        if "code=" in code:
            from urllib.parse import parse_qs, urlsplit

            query = parse_qs(urlsplit(code).query)
            state = state or (query.get("state") or [""])[0]
            code = (query.get("code") or [code])[0]
        connection = _live(store, provider)(
            lambda: manager(store).complete_code_login(
                provider, code=code, state=state, user_id=user["id"]
            )
        )
        return {"status": "connected", "connection": connection.public()}

    @router.delete("/api/brf/{brf_id}/integrations/connections/{provider}")
    def disconnect(provider: str, store: Store = Depends(require_admin)) -> dict:
        """Forget the credentials. Everything already imported stays."""
        try:
            removed = manager(store).disconnect(provider)
        except NotConnected as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"disconnected": provider, "hadCredentials": removed}

    # ---------- connected mailbox ----------

    @router.get("/api/brf/{brf_id}/integrations/mailbox/messages")
    def list_mailbox(
        limit: int = 25,
        onlyWithAttachments: bool = True,
        store: Store = Depends(require_admin),
    ) -> dict:
        """List the connected mailbox. Headers only; no body is fetched here."""
        rows = _live(store, PROVIDER_GRAPH)(
            lambda: manager(store)
            .graph_adapter()
            .list_messages(limit=limit, only_with_attachments=onlyWithAttachments)
        )
        return {"provider": PROVIDER_GRAPH, "messages": [m.public() for m in rows]}

    @router.post("/api/brf/{brf_id}/integrations/mailbox/messages/{message_id}/import")
    def import_from_mailbox(
        message_id: str,
        store: Store = Depends(require_admin),
        user: dict = Depends(current_user),
    ) -> dict:
        """Import one chosen message through the ordinary `.eml` path.

        The bytes are Graph's ``/$value`` — the message as it stands — so the
        format ceiling, the attachment rule, the hash, the duplicate check and
        the atomic rollback are the same code the manual import runs. Nothing
        in the mailbox is marked, moved or deleted by this.
        """
        raw = _live(store, PROVIDER_GRAPH)(
            lambda: manager(store).graph_adapter().get_message_mime(message_id)
        )
        try:
            event = import_eml(
                store=store,
                integrations=store.integrations,
                raw=raw,
                filename=f"{message_id[:40]}.eml",
                imported_by=user["id"],
                method="graph-mailbox-import",
                adapter_name=PROVIDER_GRAPH,
                external_hint=message_id,
            )
        except DuplicateSourceEvent as exc:
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

    # ---------- adopting an attachment into the archive ----------

    @router.post(
        "/api/brf/{brf_id}/integrations/source-events/{event_id}"
        "/attachments/{attachment_id}/archive"
    )
    def archive_attachment(
        event_id: str,
        attachment_id: str,
        req: ArchiveRequest,
        store: Store = Depends(require_admin),
        user: dict = Depends(current_user),
    ) -> dict:
        """Make this attachment part of the association's own archive.

        "Archive" here means *our* archive — the opposite direction from the
        outward ``archive`` verb that :mod:`app.integrations.protocols` refuses
        on an adapter. Nothing is archived in the mail system; a document the
        association already holds stops being merely incoming material and
        starts being evidence the review may cite.
        """
        try:
            event = adopt_attachment(
                store=store,
                integrations=store.integrations,
                event_id=event_id,
                attachment_id=attachment_id,
                user_id=user["id"],
                note=req.note,
            )
        except AdoptionError as exc:
            status = 404 if str(exc).startswith("Okänd") else 422
            raise HTTPException(status_code=status, detail=str(exc)) from exc
        return event.model_dump(mode="json")

    @router.delete(
        "/api/brf/{brf_id}/integrations/source-events/{event_id}"
        "/attachments/{attachment_id}/archive"
    )
    def unarchive_attachment(
        event_id: str, attachment_id: str, store: Store = Depends(require_admin)
    ) -> dict:
        """Undo the adoption. The document stays; it stops counting as evidence."""
        try:
            event = withdraw_attachment(
                integrations=store.integrations,
                event_id=event_id,
                attachment_id=attachment_id,
            )
        except AdoptionError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return event.model_dump(mode="json")

    # ---------- supplier aliases ----------

    @router.get("/api/brf/{brf_id}/integrations/supplier-aliases")
    def list_aliases(access: tuple[Store, str] = Depends(tenant_store)) -> list[dict]:
        store, _ = access
        return [a.model_dump(mode="json") for a in store.integrations.list_supplier_aliases()]

    @router.post("/api/brf/{brf_id}/integrations/supplier-aliases")
    def add_alias(
        req: AliasRequest,
        store: Store = Depends(require_admin),
        user: dict = Depends(current_user),
    ) -> dict:
        """Record that two supplier names are the same supplier.

        This is the human half of the weak-anchor loop: the engine may notice
        that "Snösvängen AB" and "Snösvängen Entreprenad AB" share a
        distinctive head, but only a person here can say they are the same
        company. Once said, it is recorded with their id and is strong
        evidence from then on.
        """
        invoice_name = req.invoice_name.strip()
        document_name = req.document_name.strip()
        if not invoice_name or not document_name:
            raise HTTPException(
                status_code=422, detail="Både fakturans och dokumentets namn krävs."
            )
        key = normalize_supplier(invoice_name)
        if not key:
            raise HTTPException(
                status_code=422,
                detail="Fakturans leverantörsnamn innehåller inget att matcha på.",
            )
        alias = store.integrations.add_supplier_alias(
            SupplierAlias(
                id=uuid.uuid4().hex[:12],
                tenant_id=store.tenant_id,
                invoice_name=invoice_name,
                document_name=document_name,
                normalized_key=key,
                created_by=user["id"],
                created_at=utc_now_iso(),
                note=(req.note or "").strip() or None,
            )
        )
        return alias.model_dump(mode="json")

    @router.delete("/api/brf/{brf_id}/integrations/supplier-aliases/{alias_id}")
    def delete_alias(alias_id: str, store: Store = Depends(require_admin)) -> dict:
        if not store.integrations.delete_supplier_alias(alias_id):
            raise HTTPException(status_code=404, detail="Okänd alias-post.")
        return {"deleted": alias_id}

    # ---------- invoices ----------

    def _accounting_source(store: Store, source: str):
        """Resolve a named source to something with the read adapter's shape.

        Two sources, never guessed between. ``fixture`` reads synthetic files
        and needs nothing; ``fortnox`` reads a live, connected company. An
        installation with Fortnox connected can still read the fixture set —
        which is what keeps the demo and the tests honest on a machine where a
        real integration exists.
        """
        if source not in INVOICE_SOURCES:
            raise HTTPException(
                status_code=422,
                detail=f"Okänd fakturakälla. Tillåtna: {', '.join(INVOICE_SOURCES)}.",
            )
        if source == "fixture":
            return adapter
        return manager(store).fortnox_adapter()

    @router.get("/api/brf/{brf_id}/integrations/available-invoices")
    def list_available_invoices(
        brf_id: str,
        source: str = "fixture",
        access: tuple[Store, str] = Depends(tenant_store),
    ) -> dict:
        """What the read-only adapter can offer. Nothing is stored by looking."""
        store, _ = access
        if source == "fixture":
            try:
                rows = adapter.list_invoices(brf_id)
            except FixtureError as exc:
                raise HTTPException(status_code=500, detail=str(exc)) from exc
            return {"adapter": adapter.name, "source": source, "invoices": rows}
        live = _live(store, PROVIDER_FORTNOX)
        rows = live(lambda: _accounting_source(store, source).list_invoices(brf_id))
        return {"adapter": PROVIDER_FORTNOX, "source": source, "invoices": rows}

    @router.get("/api/brf/{brf_id}/integrations/invoices/mapping-preview")
    def invoice_mapping_preview(
        brf_id: str, external_ref: str, store: Store = Depends(require_admin)
    ) -> dict:
        """Which Fortnox field became which of ours, with both values.

        The first live connection is the only moment the mapping can actually
        be checked against the source system, and "the amounts looked right" is
        not checking. A person compares this table against the invoice in
        Fortnox once; after that the mapping is a verified fact rather than a
        confident assumption in a source file.
        """
        return _live(store, PROVIDER_FORTNOX)(
            lambda: manager(store)
            .fortnox_adapter()
            .mapping_preview(brf_id, external_ref.strip())
        )

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
            if req.source == "fixture":
                snapshot = _accounting_source(store, req.source).get_invoice(
                    brf_id, req.external_ref.strip()
                )
            else:
                # Resolving the source is itself a live act — it may find that
                # nobody has connected anything — so it happens inside the
                # wrapper that turns that into a 409 rather than a 500.
                snapshot = _live(store, PROVIDER_FORTNOX)(
                    lambda: _accounting_source(store, req.source).get_invoice(
                        brf_id, req.external_ref.strip()
                    )
                )
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
