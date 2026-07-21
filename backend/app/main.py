from __future__ import annotations

import logging
import os
import threading
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response as RawResponse
from pydantic import BaseModel

from .answer import ask
from .auth import AuthError, AuthStore
from .registry import TenantRegistry
from .schemas import AskRequest, AskResponse, Settings
from .store import Store

logger = logging.getLogger("brf")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

SESSION_COOKIE = "brf_session"
MAX_UPLOAD_BYTES = 50 * 1024 * 1024
RETENTION_SWEEP_S = 24 * 3600


class LoginRequest(BaseModel):
    email: str
    password: str


def _default_data_root() -> Path:
    return Path(os.environ.get("BRF_DATA_ROOT") or (Path(__file__).resolve().parent.parent / "data"))


def create_app(
    registry: TenantRegistry | None = None,
    auth: AuthStore | None = None,
    data_root: str | Path | None = None,
) -> FastAPI:
    mode = os.environ.get("BRF_MODE", "dev")
    root = Path(data_root) if data_root is not None else _default_data_root()
    auth = auth if auth is not None else AuthStore(root / "auth.db")
    registry = registry if registry is not None else TenantRegistry(root, auth)

    if mode == "pilot":
        from .llm import pick_provider

        provider = pick_provider()
        if provider.name != "selfhosted":
            raise RuntimeError(
                "BRF_MODE=pilot kräver självhostad LLM — sätt BRF_LLM_BASE_URL "
                f"(aktiv leverantör: {provider.name})."
            )

    app = FastAPI(title="BRF Dokument-AI")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.registry = registry
    app.state.auth = auth
    app.state.mode = mode

    # Retention sweep: at boot and daily. Tests call purge_expired directly.
    registry.purge_expired_all()
    stop_event = threading.Event()
    app.state.retention_stop = stop_event

    def _retention_loop() -> None:
        while not stop_event.wait(RETENTION_SWEEP_S):
            try:
                registry.purge_expired_all()
                auth.delete_expired_sessions()
            except Exception:  # never let the sweep kill the thread
                logger.exception("Retention-svepet misslyckades")

    threading.Thread(target=_retention_loop, name="brf-retention", daemon=True).start()

    # ---------- auth glue ----------

    def _token_from(request: Request) -> str:
        header = request.headers.get("authorization", "")
        if header.lower().startswith("bearer "):
            return header[7:].strip()
        return request.cookies.get(SESSION_COOKIE, "")

    def current_user(request: Request) -> dict:
        user = auth.resolve_session(_token_from(request))
        if user is None:
            raise HTTPException(status_code=401, detail="Inloggning krävs.")
        return user

    def tenant_store(brf_id: str, user: dict = Depends(current_user)) -> tuple[Store, str]:
        """Resolve (store, role) for an authenticated member. Non-members get
        404 — never 403 — so tenant ids cannot be probed for existence."""
        role = auth.role_for(user["id"], brf_id)
        store = registry.get(brf_id) if role else None
        if role is None or store is None:
            raise HTTPException(status_code=404, detail="Okänd förening.")
        return store, role

    def require_admin(access: tuple[Store, str] = Depends(tenant_store)) -> Store:
        store, role = access
        if role != "admin":
            raise HTTPException(status_code=403, detail="Kräver administratörsroll.")
        return store

    # ---------- public ----------

    @app.get("/api/health")
    def health() -> dict:
        from .embeddings import get_embedder
        from .llm import pick_provider

        return {
            "status": "ok",
            "mode": mode,
            "llm_provider": pick_provider().name,
            "embedding_provider": get_embedder().name,
            "tenants": len(auth.list_tenants()),
        }

    @app.post("/api/auth/login")
    def login(req: LoginRequest, response: Response) -> dict:
        try:
            user_id = auth.verify_login(req.email, req.password)
        except AuthError as exc:  # throttled
            raise HTTPException(status_code=429, detail=str(exc)) from exc
        if user_id is None:
            raise HTTPException(status_code=401, detail="Fel e-post eller lösenord.")
        token = auth.create_session(user_id)
        user = auth.get_user(user_id)
        response.set_cookie(
            SESSION_COOKIE,
            token,
            httponly=True,
            samesite="lax",
            max_age=14 * 24 * 3600,
            path="/",
        )
        return {
            "user": user,
            "memberships": auth.memberships_for(user_id),
            "token": token,  # for programmatic clients (eval, tests); UI uses the cookie
        }

    @app.post("/api/auth/logout")
    def logout(request: Request, response: Response) -> dict:
        token = _token_from(request)
        if token:
            auth.delete_session(token)
        response.delete_cookie(SESSION_COOKIE, path="/")
        return {"status": "utloggad"}

    @app.get("/api/auth/me")
    def me(user: dict = Depends(current_user)) -> dict:
        return {"user": user, "memberships": auth.memberships_for(user["id"])}

    # ---------- tenant-scoped ----------

    @app.get("/api/brf/{brf_id}/documents")
    def list_documents(access: tuple[Store, str] = Depends(tenant_store)) -> list:
        store, _ = access
        return store.list_documents()

    @app.post("/api/brf/{brf_id}/documents")
    async def upload_document(brf_id: str, file: UploadFile, store: Store = Depends(require_admin)) -> dict:
        if not (file.filename or "").lower().endswith(".pdf"):
            raise HTTPException(status_code=400, detail="Endast PDF-filer stöds.")
        data = await file.read()
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="Filen är större än 50 MB.")
        try:
            meta = store.add_document(file.filename or "namnlös.pdf", data)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return meta.model_dump()

    @app.get("/api/brf/{brf_id}/documents/{doc_id}/pdf")
    def get_pdf(doc_id: str, access: tuple[Store, str] = Depends(tenant_store)) -> RawResponse:
        store, _ = access
        pdf = store.get_pdf_bytes(doc_id)
        if pdf is None:
            raise HTTPException(status_code=404, detail="Okänt dokument.")
        return RawResponse(content=pdf, media_type="application/pdf")

    @app.get("/api/brf/{brf_id}/documents/{doc_id}/extraction")
    def get_extraction(doc_id: str, access: tuple[Store, str] = Depends(tenant_store)) -> dict:
        store, _ = access
        data = store.get_extraction_summary(doc_id)
        if data is None:
            raise HTTPException(status_code=404, detail="Okänt dokument.")
        return data

    @app.delete("/api/brf/{brf_id}/documents/{doc_id}")
    def delete_document(doc_id: str, store: Store = Depends(require_admin)) -> dict:
        if not store.delete_document(doc_id):
            raise HTTPException(status_code=404, detail="Okänt dokument.")
        return {"deleted": doc_id}

    @app.get("/api/brf/{brf_id}/settings")
    def get_settings(access: tuple[Store, str] = Depends(tenant_store)) -> Settings:
        store, _ = access
        return store.settings

    @app.put("/api/brf/{brf_id}/settings")
    def put_settings(settings: Settings, store: Store = Depends(require_admin)) -> Settings:
        store.update_settings(settings)
        return store.settings

    @app.post("/api/brf/{brf_id}/ask")
    def api_ask(req: AskRequest, brf_id: str, access: tuple[Store, str] = Depends(tenant_store)) -> AskResponse:
        store, _ = access
        question = req.question.strip()
        if not question:
            raise HTTPException(status_code=400, detail="Tom fråga.")
        # Numeric grounding gate (SPEC §2.10 follow-up): the tenant's own
        # registered name may legitimately contain a digit (e.g. "Brf
        # Gjutformen 12") — that digit is an identifier, not a factual claim,
        # and must not trigger a false numeric_grounding_failed refusal. The
        # trusted tenant record — never anything client-supplied — is the
        # only source for this.
        tenant = auth.get_tenant(brf_id)
        trusted_names = [tenant["name"]] if tenant else []
        return ask(store, question, trusted_names=trusted_names)

    @app.delete("/api/brf/{brf_id}")
    def delete_tenant(brf_id: str, store: Store = Depends(require_admin)) -> dict:
        """Hard-delete the whole BRF: files, index, settings, memberships."""
        registry.delete(brf_id)
        return {"deleted": brf_id}

    # ---------- dev only ----------

    @app.post("/api/reset")
    def reset(user: dict = Depends(current_user)) -> dict:
        """Wipe every tenant and reseed the demo corpus. Dev mode only, and
        authenticated — this is a destructive global op, never anonymous."""
        if mode != "dev":
            raise HTTPException(status_code=403, detail="Endast tillgängligt i dev-läge.")
        import sys

        backend_root = str(Path(__file__).resolve().parent.parent)
        if backend_root not in sys.path:  # robust under any server cwd
            sys.path.insert(0, backend_root)
        from scripts.seed import seed_demo

        for t in registry.list():
            registry.delete(t["brf_id"])
        seeded = seed_demo(registry, auth)
        return {"status": "reseeded", **seeded}

    return app


# Run with: uv run uvicorn app.main:create_app --factory --port 8787
