"""Disk-backed single-tenant document store + in-memory hybrid index.

Layout under BRF_DATA_DIR (default backend/data/):
  documents.json      {doc_id: DocumentMeta}
  settings.json       Settings
  docs/<id>.pdf       original uploads
  extract/<id>.json   list[PageData]
The index is rebuilt in memory on boot and on chunking-knob changes.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .chunker import chunk_pages
from .embeddings import get_embedder
from .extract import extract_pdf
from .indexer import HybridIndex
from .schemas import Chunk, DocumentMeta, PageData, Settings

logger = logging.getLogger("brf.store")


class Store:
    def __init__(self, data_dir: str | Path | None = None) -> None:
        default = Path(__file__).resolve().parent.parent / "data"
        self.data_dir = Path(data_dir or os.environ.get("BRF_DATA_DIR") or default)
        (self.data_dir / "docs").mkdir(parents=True, exist_ok=True)
        (self.data_dir / "extract").mkdir(parents=True, exist_ok=True)

        self.settings = self._load_settings()
        self.documents: dict[str, DocumentMeta] = self._load_documents()
        self.pages: dict[str, list[PageData]] = {}
        for doc_id in list(self.documents):
            pages = self._load_extraction(doc_id)
            if pages is None:
                logger.warning("Extraction saknas för %s — tar bort dokumentet", doc_id)
                self.documents.pop(doc_id)
            else:
                self.pages[doc_id] = pages
        self.chunks: dict[str, Chunk] = {}
        self.index = HybridIndex(get_embedder())
        self._rebuild()

    # ---------- persistence helpers ----------

    def _load_settings(self) -> Settings:
        p = self.data_dir / "settings.json"
        if p.exists():
            try:
                return Settings.model_validate_json(p.read_text("utf-8"))
            except Exception as exc:
                logger.warning("settings.json ogiltig (%s) — använder standard", exc)
        return Settings()

    def _save_settings(self) -> None:
        (self.data_dir / "settings.json").write_text(self.settings.model_dump_json(indent=2), "utf-8")

    def _load_documents(self) -> dict[str, DocumentMeta]:
        p = self.data_dir / "documents.json"
        if not p.exists():
            return {}
        raw = json.loads(p.read_text("utf-8"))
        return {k: DocumentMeta.model_validate(v) for k, v in raw.items()}

    def _save_documents(self) -> None:
        payload = {k: v.model_dump() for k, v in self.documents.items()}
        (self.data_dir / "documents.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), "utf-8")

    def _load_extraction(self, doc_id: str) -> list[PageData] | None:
        p = self.data_dir / "extract" / f"{doc_id}.json"
        if not p.exists():
            return None
        raw = json.loads(p.read_text("utf-8"))
        return [PageData.model_validate(x) for x in raw]

    def _save_extraction(self, doc_id: str, pages: list[PageData]) -> None:
        payload = [p.model_dump() for p in pages]
        (self.data_dir / "extract" / f"{doc_id}.json").write_text(json.dumps(payload, ensure_ascii=False), "utf-8")

    # ---------- index ----------

    def _rebuild(self) -> None:
        s = self.settings
        self.chunks = {}
        for doc_id, pages in self.pages.items():
            for c in chunk_pages(doc_id, pages, strategy=s.chunkStrategy, size=s.chunkSize, overlap=s.chunkOverlap):
                self.chunks[c.id] = c
            if doc_id in self.documents:
                self.documents[doc_id].chunks = sum(1 for c in self.chunks.values() if c.document_id == doc_id)
        self.index.build(list(self.chunks.values()), {d.id: d.name for d in self.documents.values()})

    # ---------- public API ----------

    def add_document(self, name: str, pdf_bytes: bytes) -> DocumentMeta:
        pages = extract_pdf(pdf_bytes)
        total_words = sum(len(p.words) for p in pages)
        if total_words == 0:
            raise ValueError(
                "Dokumentet saknar textlager (troligen en skannad PDF). "
                "OCR ingår inte i denna version — se OCR-spikriggen."
            )
        doc_id = uuid.uuid4().hex[:12]
        (self.data_dir / "docs" / f"{doc_id}.pdf").write_bytes(pdf_bytes)
        self._save_extraction(doc_id, pages)
        meta = DocumentMeta(
            id=doc_id,
            name=name,
            pages=len(pages),
            words=total_words,
            chunks=0,
            uploaded_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )
        self.documents[doc_id] = meta
        self.pages[doc_id] = pages
        self._rebuild()
        self._save_documents()
        return self.documents[doc_id]

    def delete_document(self, doc_id: str) -> bool:
        if doc_id not in self.documents:
            return False
        self.documents.pop(doc_id)
        self.pages.pop(doc_id, None)
        (self.data_dir / "docs" / f"{doc_id}.pdf").unlink(missing_ok=True)
        (self.data_dir / "extract" / f"{doc_id}.json").unlink(missing_ok=True)
        self._rebuild()
        self._save_documents()
        return True

    def list_documents(self) -> list[dict]:
        return [m.model_dump() for m in sorted(self.documents.values(), key=lambda d: d.name)]

    def get_pdf_bytes(self, doc_id: str) -> bytes | None:
        p = self.data_dir / "docs" / f"{doc_id}.pdf"
        return p.read_bytes() if doc_id in self.documents and p.exists() else None

    def get_extraction_summary(self, doc_id: str) -> dict | None:
        if doc_id not in self.documents:
            return None
        pages = self.pages[doc_id]
        return {
            "document": self.documents[doc_id].model_dump(),
            "pages": [
                {"number": p.number, "width": p.width, "height": p.height, "words": len(p.words)} for p in pages
            ],
            "chunks": [
                {
                    "id": c.id,
                    "page": c.page,
                    "word_start": c.word_start,
                    "word_end": c.word_end,
                    "preview": c.text[:160],
                    "words": c.word_end - c.word_start + 1,
                }
                for c in self.chunks.values()
                if c.document_id == doc_id
            ],
        }

    def update_settings(self, new: Settings) -> None:
        rechunk = new.chunking_signature() != self.settings.chunking_signature()
        self.settings = new
        self._save_settings()
        if rechunk:
            logger.info("Chunk-inställningar ändrade — chunkar om och bygger nytt index")
            self._rebuild()

    def wipe(self) -> None:
        for doc_id in list(self.documents):
            self.delete_document(doc_id)
