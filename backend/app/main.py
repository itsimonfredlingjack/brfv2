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

# Rasterized page widths the mobile client may request. A CLOSED allowlist,
# not a range: an open `w` is an unauthenticated-shaped rasterization DoS
# (every distinct width is a fresh MuPDF render). These three cover 1x/2x/3x
# of a phone viewport and nothing else needs to exist.
PAGE_IMAGE_WIDTHS = (720, 1080, 1440)


class LoginRequest(BaseModel):
    email: str
    password: str


def _default_data_root() -> Path:
    return Path(os.environ.get("BRF_DATA_ROOT") or (Path(__file__).resolve().parent.parent / "data"))


def create_app(
    registry: TenantRegistry | None = None,
    auth: AuthStore | None = None,
    data_root: str | Path | None = None,
    session_cookie_name: str = SESSION_COOKIE,
    session_cookie_path: str = "/",
    integration_transport=None,
) -> FastAPI:
    """Build the product app.

    ``integration_transport`` replaces the outbound HTTP transport the live
    integrations use (:mod:`app.integrations.egress`). It exists so the test
    suite can exercise the real Graph and Fortnox code paths — the same URLs,
    the same headers, the same refusals — without a credential, a network or a
    recording. Left ``None`` in every shipped configuration, which is what
    makes "the tests need no network" a property of the product rather than of
    the tests.
    """
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

    app = FastAPI(title="Träff")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            # xs_mobilapp's dev server. In production it is served from /m by
            # this same app, so it is same-origin and needs no entry here;
            # this exists only so `npm run dev` works without the proxy.
            "http://localhost:5174",
            "http://127.0.0.1:5174",
        ],
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
        """The session token, from the httpOnly cookie and nowhere else.

        There is deliberately no Authorization/Bearer path: /api/auth/login
        does not hand out a token, so accepting one would only widen the auth
        surface for a credential no legitimate client can obtain.

        The cookie *name* is a parameter because the installed desktop product
        gives each installation its own; the transport rule is not.
        """
        return request.cookies.get(session_cookie_name, "")

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
        from .model_display import display_name_for

        provider = pick_provider()
        # The same attribute answer.py reads to report per-response
        # provenance (getattr(provider, "model", "")) — never the
        # aiModel setting fallback, since that's a per-tenant default the
        # self-hosted provider ignores at generation time.
        raw_model = getattr(provider, "model", "") or ""
        return {
            "status": "ok",
            "mode": mode,
            "llm_provider": provider.name,
            "embedding_provider": get_embedder().name,
            "tenants": len(auth.list_tenants()),
            "llm": {
                "provider": provider.name,
                "model": raw_model,
                "display_name": display_name_for(raw_model),
                "runtime_label": os.environ.get("BRF_LLM_RUNTIME_LABEL", ""),
                # A configured, real generation path — never claims a model
                # is active for the "none"/"fake" providers. This reflects
                # configuration, not live reachability: a self-hosted
                # endpoint whose tunnel just dropped still reads ready=true
                # here (the actual generation call is what surfaces that
                # failure, per-request).
                "ready": provider.name not in ("none", "fake"),
            },
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
            session_cookie_name,
            token,
            httponly=True,
            samesite="lax",
            max_age=14 * 24 * 3600,
            path=session_cookie_path,
        )
        # The session token is returned ONLY as the httpOnly cookie set above.
        # It used to be echoed here as `token` for programmatic clients, which
        # put a long-lived credential into a JSON body that any script on the
        # page — or any logging proxy in between — could read, defeating the
        # point of making the cookie httpOnly. Nothing outside the test
        # fixtures consumed it.
        return {"user": user, "memberships": auth.memberships_for(user_id)}

    @app.post("/api/auth/logout")
    def logout(request: Request, response: Response) -> dict:
        token = _token_from(request)
        if token:
            auth.delete_session(token)
        response.delete_cookie(session_cookie_name, path=session_cookie_path)
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

    @app.get("/api/brf/{brf_id}/documents/{doc_id}/page/{page}")
    def get_page_image(
        doc_id: str,
        page: int,
        w: int = 1080,
        access: tuple[Store, str] = Depends(tenant_store),
    ) -> RawResponse:
        """Rasterize one page for the mobile client.

        The mobile app draws citation rects as plain boxes over this image
        instead of running pdf.js: `scale = w / page_width_pt`, and the rects
        are ALREADY top-left-origin PDF points, so there is no y-flip and no
        viewport matrix on the client. `page.rect` and `get_text("words")`
        (app/extract.py) share one coordinate space with `get_pixmap`, so a
        rotated page stays aligned without client-side rotation handling.

        Rendered on demand, never cached to disk: a render is ~5 ms, and a
        raster cache would be a second place tenant content lives — one that
        registry.delete()/delete_document() would have to remember to sweep.
        The client keeps its own tenant-namespaced copy, which logout wipes.
        """
        store, _ = access
        if w not in PAGE_IMAGE_WIDTHS:
            raise HTTPException(
                status_code=400,
                detail=f"Ogiltig bredd. Tillåtna: {', '.join(str(x) for x in PAGE_IMAGE_WIDTHS)}.",
            )
        pdf = store.get_pdf_bytes(doc_id)
        if pdf is None:
            raise HTTPException(status_code=404, detail="Okänt dokument.")

        import fitz

        doc = fitz.open(stream=pdf, filetype="pdf")
        try:
            if page < 1 or page > doc.page_count:
                raise HTTPException(status_code=404, detail="Sidan finns inte.")
            pdf_page = doc[page - 1]
            width_pt = float(pdf_page.rect.width)
            height_pt = float(pdf_page.rect.height)
            zoom = w / width_pt
            pixmap = pdf_page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
            # PNG, not JPEG/WebP: PyMuPDF cannot emit WebP at all, and on these
            # text pages PNG measured smaller than jpg_quality=85 at 1440px
            # while staying lossless — JPEG ringing around glyphs is the last
            # thing a document you are holding up as proof should have.
            body = pixmap.tobytes("png")
        finally:
            doc.close()

        return RawResponse(
            content=body,
            media_type="image/png",
            headers={
                # NO-STORE, deliberately, even though the bytes are immutable.
                # This is tenant document content. The browser's HTTP cache is
                # not something logout can clear, so an entry there would be a
                # second copy of another user's pages surviving on a shared
                # device — outside the tenant-namespaced client store that the
                # wipe guarantee is built on. The client caches these itself
                # (state/localStore.ts), so nothing is re-fetched twice.
                "Cache-Control": "private, no-store",
                "X-Page-Width-Pt": f"{width_pt:.2f}",
                "X-Page-Height-Pt": f"{height_pt:.2f}",
            },
        )

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
        """Hard-delete the whole BRF: files, index, settings, memberships.

        Integration records go with it without being mentioned here: they live
        inside the tenant's own directory (Store.integrations), so the tree
        removal that deletes documents deletes them too. A domain that needed a
        line in this function would be a domain that had put tenant data
        somewhere else.
        """
        registry.delete(brf_id)
        return {"deleted": brf_id}

    # ---------- integrations (source events, invoices, findings) ----------
    #
    # Mounted with the SAME dependencies as everything above: a membership
    # resolves to exactly one Store, and that Store is the only place its
    # integration records exist. Nothing here has its own authorisation path.

    from .integrations.routes import build_router as _build_integration_router

    app.include_router(
        _build_integration_router(
            tenant_store=tenant_store,
            require_admin=require_admin,
            current_user=current_user,
            transport=integration_transport,
        )
    )

    # ---------- invoices (one invoice as one case, on top of the same reads) ----------
    #
    # A separate router rather than more routes on the integrations one,
    # because it is a different product area: the integrations block is about
    # material arriving, and this is about an invoice being worked. It shares
    # the store, the adapters and the review engine, and adds no second way to
    # reach any of them.

    from .invoices.routes import build_router as _build_invoice_router

    app.include_router(
        _build_invoice_router(
            tenant_store=tenant_store,
            require_admin=require_admin,
            current_user=current_user,
            transport=integration_transport,
        )
    )

    # ---------- watches (dated obligations out of the tenant's own documents) ----------

    from .watches.routes import build_router as _build_watch_router

    app.include_router(
        _build_watch_router(
            tenant_store=tenant_store,
            require_admin=require_admin,
            current_user=current_user,
        )
    )

    # ---------- tasks (what the board decided to do about any of it) ----------

    from .tasks.routes import build_router as _build_task_router

    app.include_router(
        _build_task_router(
            tenant_store=tenant_store,
            require_admin=require_admin,
            current_user=current_user,
        )
    )

    # ---------- website (the association's own public pages) ----------
    #
    # Same dependencies again. `trusted_names_for` is the one addition: the
    # grounding gate that guards what a model writes onto a public page needs
    # the tenant's registered name for exactly the reason api_ask does — "Brf
    # Gjutformen 12" is an identifier, not a claim about the number twelve — and
    # it comes from the trusted tenant record, never from the request.

    from .website.routes import build_router as _build_website_router

    app.include_router(
        _build_website_router(
            tenant_store=tenant_store,
            require_admin=require_admin,
            current_user=current_user,
            trusted_names_for=lambda brf_id: (
                (auth.get_tenant(brf_id) or {}).get("name", ""),
            ),
        )
    )

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

    # ---------- mobile app (xs_mobilapp) ----------

    mobile_dist = Path(__file__).resolve().parent.parent.parent / "xs_mobilapp" / "dist"

    # The mobile client is same-origin by design and talks to nothing else.
    # Stating that as policy makes it enforceable rather than aspirational:
    # a stray third-party script, pixel or beacon fails closed instead of
    # quietly shipping document text off the device.
    #   img-src blob:  — page rasters are rendered from IndexedDB blobs
    #   style-src 'unsafe-inline' — React style={{...}} attributes
    MOBILE_SECURITY_HEADERS = {
        "Content-Security-Policy": "; ".join(
            [
                "default-src 'self'",
                "script-src 'self'",
                "style-src 'self' 'unsafe-inline'",
                "img-src 'self' blob: data:",
                "font-src 'self'",
                "connect-src 'self'",
                "manifest-src 'self'",
                "worker-src 'self'",
                "object-src 'none'",
                "base-uri 'none'",
                "form-action 'self'",
                "frame-ancestors 'none'",
            ]
        ),
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
        "X-Frame-Options": "DENY",
    }

    @app.get("/m")
    def mobile_root() -> RawResponse:
        return RawResponse(status_code=307, headers={"Location": "/m/"})

    @app.get("/m/{path:path}")
    def mobile_app(path: str) -> RawResponse:
        """Serve the built mobile client from the SAME ORIGIN as the API.

        That is what lets it reuse the httpOnly session cookie with no CORS
        entry and no token in JavaScript. Unknown paths fall back to
        index.html because the client routes /svar/:id and /dokument/:id
        itself — a deep link must open the app, not 404.
        """
        import mimetypes

        if not mobile_dist.is_dir():
            raise HTTPException(
                status_code=404,
                detail="Mobilappen är inte byggd. Kör `npm run build` i xs_mobilapp/.",
            )

        index = mobile_dist / "index.html"
        candidate = (mobile_dist / path).resolve() if path else index

        # Path traversal guard: a resolved path must stay inside dist.
        inside = mobile_dist.resolve() in candidate.parents or candidate == mobile_dist.resolve()
        target = candidate if (inside and candidate.is_file()) else index

        if not target.is_file():
            raise HTTPException(status_code=404, detail="Mobilappen saknar index.html.")

        media_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        # Vite fingerprints asset filenames; index.html and the service worker
        # must never be pinned or a deploy cannot land.
        cache = (
            "public, max-age=31536000, immutable"
            if target.parent.name == "assets"
            else "no-cache"
        )
        return RawResponse(
            content=target.read_bytes(),
            media_type=media_type,
            headers={"Cache-Control": cache, **MOBILE_SECURITY_HEADERS},
        )

    return app


# Run with: uv run uvicorn app.main:create_app --factory --port 8787
