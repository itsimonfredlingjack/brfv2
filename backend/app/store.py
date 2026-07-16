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
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .chunker import chunk_pages
from .embeddings import get_embedder
from .extract import extract_pdf
from .indexer import HybridIndex
from .schemas import Chunk, DocumentMeta, PageData, Settings

logger = logging.getLogger("brf.store")

MAX_DOCUMENT_PAGES = 400  # resource guard: reject absurd page counts up front


class Store:
    def __init__(self, data_dir: str | Path | None = None) -> None:
        # Guards every mutation; FastAPI runs sync endpoints concurrently in a
        # threadpool. Rebuilds rebind fresh objects (never mutate in place),
        # so readers that snapshot references under the lock stay consistent.
        self.lock = threading.RLock()
        default = Path(__file__).resolve().parent.parent / "data"
        self.data_dir = Path(data_dir or os.environ.get("BRF_DATA_DIR") or default)
        (self.data_dir / "docs").mkdir(parents=True, exist_ok=True)
        (self.data_dir / "extract").mkdir(parents=True, exist_ok=True)

        self.settings = self._load_settings()
        self.documents: dict[str, DocumentMeta] = self._load_documents()
        self.pages: dict[str, list[PageData]] = {}
        dropped: list[str] = []
        for doc_id in list(self.documents):
            pages = self._load_extraction(doc_id)
            if pages is None:
                logger.warning("Extraction saknas för %s — tar bort dokumentet", doc_id)
                self.documents.pop(doc_id)
                dropped.append(doc_id)
            else:
                self.pages[doc_id] = pages
        if dropped:  # keep disk consistent with the drop, don't leave orphans
            for doc_id in dropped:
                (self.data_dir / "docs" / f"{doc_id}.pdf").unlink(missing_ok=True)
            self._save_documents()
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
        """Rebuild chunks + index into FRESH objects, then publish by
        reference swap — concurrent readers keep a consistent (old) view."""
        with self.lock:
            s = self.settings
            new_chunks: dict[str, Chunk] = {}
            for doc_id, pages in self.pages.items():
                for c in chunk_pages(doc_id, pages, strategy=s.chunkStrategy, size=s.chunkSize, overlap=s.chunkOverlap):
                    new_chunks[c.id] = c
                if doc_id in self.documents:
                    self.documents[doc_id].chunks = sum(1 for c in new_chunks.values() if c.document_id == doc_id)
            new_index = HybridIndex(self.index.embedder)
            new_index.build(list(new_chunks.values()), {d.id: d.name for d in self.documents.values()})
            self.chunks = new_chunks
            self.index = new_index

    def snapshot(self) -> tuple[HybridIndex, dict, dict, dict]:
        """Consistent (index, chunks, pages, documents) view for one request."""
        with self.lock:
            return self.index, self.chunks, dict(self.pages), dict(self.documents)

    # ---------- public API ----------

    def add_document(self, name: str, pdf_bytes: bytes) -> DocumentMeta:
        pages = extract_pdf(pdf_bytes)
        total_words = sum(len(p.words) for p in pages)
        if total_words == 0:
            raise ValueError(
                "Dokumentet saknar textlager (troligen en skannad PDF). "
                "OCR ingår inte i denna version — se OCR-spikriggen."
            )
        if len(pages) > MAX_DOCUMENT_PAGES:
            raise ValueError(
                f"Dokumentet har {len(pages)} sidor — max {MAX_DOCUMENT_PAGES}. Dela upp filen."
            )
        doc_id = uuid.uuid4().hex[:12]
        with self.lock:
            try:
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
                self.pages = {**self.pages, doc_id: pages}
                self._rebuild()
                self._save_documents()
                return self.documents[doc_id]
            except Exception:
                # Roll back: no orphaned files, no half-registered document.
                self.documents.pop(doc_id, None)
                self.pages = {k: v for k, v in self.pages.items() if k != doc_id}
                (self.data_dir / "docs" / f"{doc_id}.pdf").unlink(missing_ok=True)
                (self.data_dir / "extract" / f"{doc_id}.json").unlink(missing_ok=True)
                raise

    def delete_document(self, doc_id: str) -> bool:
        with self.lock:
            if doc_id not in self.documents:
                return False
            self.documents.pop(doc_id)
            self.pages = {k: v for k, v in self.pages.items() if k != doc_id}
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
        with self.lock:
            meta = self.documents.get(doc_id)
            pages = self.pages.get(doc_id)
            chunks = self.chunks
        if meta is None or pages is None:
            return None
        return {
            "document": meta.model_dump(),
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
                for c in chunks.values()
                if c.document_id == doc_id
            ],
        }

    def update_settings(self, new: Settings) -> None:
        with self.lock:
            old = self.settings
            rechunk = new.chunking_signature() != old.chunking_signature()
            self.settings = new
            if rechunk:
                logger.info("Chunk-inställningar ändrade — chunkar om och bygger nytt index")
                try:
                    self._rebuild()
                except Exception:
                    # _rebuild publishes only at the end, so the old chunks and
                    # index are still live — revert settings to match reality.
                    self.settings = old
                    raise
            self._save_settings()

    def purge_expired(self, now: datetime | None = None) -> list[str]:
        """Hard-delete documents older than settings.retentionDays (0 = off).
        Returns the deleted document ids."""
        with self.lock:
            days = self.settings.retentionDays
            if not days:
                return []
            cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=days)
            doomed = [
                doc_id
                for doc_id, meta in self.documents.items()
                if datetime.fromisoformat(meta.uploaded_at) < cutoff
            ]
            for doc_id in doomed:
                self.delete_document(doc_id)
            if doomed:
                logger.info("Retention: raderade %d dokument äldre än %d dagar", len(doomed), days)
            return doomed

    def wipe(self) -> None:
        with self.lock:
            for doc_id in list(self.documents):
                (self.data_dir / "docs" / f"{doc_id}.pdf").unlink(missing_ok=True)
                (self.data_dir / "extract" / f"{doc_id}.json").unlink(missing_ok=True)
            self.documents = {}
            self.pages = {}
            self._rebuild()  # once, not once per document
            self._save_documents()
