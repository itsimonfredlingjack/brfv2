from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from .answer import ask
from .schemas import AskRequest, AskResponse, Settings
from .store import Store

logger = logging.getLogger("brf")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


def create_app(store: Store | None = None) -> FastAPI:
    app = FastAPI(title="BRF Dokument-AI")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    st = store if store is not None else Store()
    app.state.store = st

    @app.get("/api/health")
    def health() -> dict:
        from .llm import pick_provider

        return {
            "status": "ok",
            "llm_provider": pick_provider().name,
            "embedding_provider": st.index.embedder.name,
            "documents": len(st.documents),
        }

    @app.get("/api/settings")
    def get_settings() -> Settings:
        return st.settings

    @app.put("/api/settings")
    def put_settings(settings: Settings) -> Settings:
        st.update_settings(settings)
        return st.settings

    @app.get("/api/documents")
    def list_documents() -> list:
        return st.list_documents()

    MAX_UPLOAD_BYTES = 50 * 1024 * 1024

    @app.post("/api/documents")
    async def upload_document(file: UploadFile) -> dict:
        if not (file.filename or "").lower().endswith(".pdf"):
            raise HTTPException(status_code=400, detail="Endast PDF-filer stöds.")
        data = await file.read()
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="Filen är större än 50 MB.")
        try:
            meta = st.add_document(file.filename or "namnlös.pdf", data)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return meta.model_dump()

    @app.get("/api/documents/{doc_id}/pdf")
    def get_pdf(doc_id: str) -> Response:
        pdf = st.get_pdf_bytes(doc_id)
        if pdf is None:
            raise HTTPException(status_code=404, detail="Okänt dokument.")
        return Response(content=pdf, media_type="application/pdf")

    @app.get("/api/documents/{doc_id}/extraction")
    def get_extraction(doc_id: str) -> dict:
        data = st.get_extraction_summary(doc_id)
        if data is None:
            raise HTTPException(status_code=404, detail="Okänt dokument.")
        return data

    @app.delete("/api/documents/{doc_id}")
    def delete_document(doc_id: str) -> dict:
        if not st.delete_document(doc_id):
            raise HTTPException(status_code=404, detail="Okänt dokument.")
        return {"deleted": doc_id}

    @app.post("/api/ask")
    def api_ask(req: AskRequest) -> AskResponse:
        question = req.question.strip()
        if not question:
            raise HTTPException(status_code=400, detail="Tom fråga.")
        return ask(st, question)

    @app.post("/api/reset")
    def reset() -> dict:
        """Wipe all documents and reseed the demo corpus."""
        from scripts.seed import seed_store

        st.wipe()
        seeded = seed_store(st)
        return {"status": "reseeded", "documents": seeded}

    return app


# Run with: uv run uvicorn app.main:create_app --factory --port 8787
