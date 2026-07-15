from __future__ import annotations

import io
import logging

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from .answer import ask
from .schemas import AskRequest, AskResponse, Settings
from .store import Store

logger = logging.getLogger("brf")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

app = FastAPI(title="BRF Dokument-AI")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

store = Store()


@app.get("/api/health")
def health() -> dict:
    from .llm import pick_provider

    return {
        "status": "ok",
        "llm_provider": pick_provider().name,
        "embedding_provider": store.index.embedder.name,
        "documents": len(store.documents),
    }


@app.get("/api/settings")
def get_settings() -> Settings:
    return store.settings


@app.put("/api/settings")
def put_settings(settings: Settings) -> Settings:
    store.update_settings(settings)
    return store.settings


@app.get("/api/documents")
def list_documents() -> list:
    return store.list_documents()


@app.post("/api/documents")
async def upload_document(file: UploadFile) -> dict:
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Endast PDF-filer stöds.")
    data = await file.read()
    try:
        meta = store.add_document(file.filename, data)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return meta.model_dump()


@app.get("/api/documents/{doc_id}/pdf")
def get_pdf(doc_id: str) -> Response:
    pdf = store.get_pdf_bytes(doc_id)
    if pdf is None:
        raise HTTPException(status_code=404, detail="Okänt dokument.")
    return Response(content=pdf, media_type="application/pdf")


@app.get("/api/documents/{doc_id}/extraction")
def get_extraction(doc_id: str) -> dict:
    data = store.get_extraction_summary(doc_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Okänt dokument.")
    return data


@app.delete("/api/documents/{doc_id}")
def delete_document(doc_id: str) -> dict:
    if not store.delete_document(doc_id):
        raise HTTPException(status_code=404, detail="Okänt dokument.")
    return {"deleted": doc_id}


@app.post("/api/ask")
def api_ask(req: AskRequest) -> AskResponse:
    question = req.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Tom fråga.")
    return ask(store, question)


@app.post("/api/reset")
def reset() -> dict:
    """Wipe all documents and reseed the demo corpus."""
    from scripts.seed import seed_store

    store.wipe()
    seed_store(store)
    return {"status": "reseeded", "documents": len(store.documents)}
