"""Disk-backed single-tenant document store + in-memory hybrid index.

Layout under BRF_DATA_DIR (default backend/data/):
  tenant_meta.json    {corpus_origin} — this tenant's corpus, CI2 guard
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
import subprocess
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .chunker import chunk_pages
from .embeddings import get_embedder
from .enrich import chunk_search_texts, enrichment_enabled
from .extract import extract_pdf
from .indexer import HybridIndex
from .ocr import ocr_pdf, tesseract_available
from .schemas import CORPUS_ORIGINS, Chunk, CorpusOrigin, DocumentMeta, PageData, Settings

logger = logging.getLogger("brf.store")

MAX_DOCUMENT_PAGES = 400  # resource guard: reject absurd page counts up front


def _atomic_write(path: Path, content: str) -> None:
    """Write `content` to `path` atomically: write to a temp file in the SAME
    directory, then `os.replace` (atomic on POSIX and Windows). A crash or
    failure mid-write can never leave a truncated/partial file at `path` —
    either the old content survives untouched, or the new content lands
    whole. NOTE: this guarantees atomicity (no torn reads), not durability —
    there is no fsync, so a hard power loss immediately after os.replace may
    still lose the newest write; acceptable for the local single-process
    pilot. Used for documents.json and tenant_meta.json (CI2/CI3 fail-closed
    hardening): these are the two files a corrupted write could turn into a
    silent corpus-origin mixup."""
    tmp = path.with_name(f"{path.name}.tmp-{uuid.uuid4().hex[:8]}")
    tmp.write_text(content, "utf-8")
    try:
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)  # no-op once os.replace has moved it away


class Store:
    def __init__(self, data_dir: str | Path | None = None, corpus_origin: CorpusOrigin | None = None) -> None:
        # Guards every mutation; FastAPI runs sync endpoints concurrently in a
        # threadpool. Rebuilds rebind fresh objects (never mutate in place),
        # so readers that snapshot references under the lock stay consistent.
        self.lock = threading.RLock()
        default = Path(__file__).resolve().parent.parent / "data"
        self.data_dir = Path(data_dir or os.environ.get("BRF_DATA_DIR") or default)
        (self.data_dir / "docs").mkdir(parents=True, exist_ok=True)
        (self.data_dir / "extract").mkdir(parents=True, exist_ok=True)

        # Corpus-isolation guard (CI2): the tenant's origin, persisted in
        # tenant_meta.json sibling to documents.json/settings.json. Must be
        # resolved BEFORE _load_documents() so pre-CI2 document records can
        # migrate to it.
        self.corpus_origin = self._load_or_init_corpus_origin(corpus_origin)
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

    def _load_or_init_corpus_origin(self, corpus_origin: CorpusOrigin | None) -> CorpusOrigin:
        """tenant_meta.json — a sibling record to documents.json/settings.json
        holding the one thing every document in this Store inherits: which of
        the three corpora (customer / public_scraped / synthetic) it belongs
        to.

        Fail-closed (CI3 hardening): if the file already exists on disk, disk
        wins (the durable record is authoritative — a caller-supplied
        `corpus_origin` is ignored once a tenant is established) — but a
        tenant_meta.json that exists and is malformed, or holds a value
        outside CORPUS_ORIGINS, means something went wrong and this refuses
        to open the tenant (loud error) rather than silently downgrading to
        "synthetic". A silent downgrade here could reboot a real customer
        tenant as synthetic without anyone noticing.

        If the file is missing entirely: an explicit `corpus_origin`
        (tenant creation, via TenantRegistry.create) is persisted as-is — no
        migration involved, this is a fresh, explicit declaration. Otherwise
        (no `corpus_origin` argument given) the "synthetic" migration default
        applies ONLY when it is safe to assume no origin was ever recorded
        for this tenant: no documents.json yet (a fresh/empty Store — the
        common ad hoc test/script shape), or a documents.json that shows a
        genuinely pre-CI2 legacy tenant (at least one entry missing
        corpus_origin). If documents.json exists and EVERY entry already
        carries a corpus_origin, this tenant was already migrated once —
        tenant_meta.json vanishing on top of that is an anomaly, not a
        legacy case, and must fail loud rather than paper over it."""
        if corpus_origin is not None and corpus_origin not in CORPUS_ORIGINS:
            raise ValueError(f"Ogiltigt corpus_origin: {corpus_origin!r} (tillåtna: {CORPUS_ORIGINS}).")

        p = self.data_dir / "tenant_meta.json"
        if p.exists():
            try:
                raw = json.loads(p.read_text("utf-8"))
            except Exception as exc:
                raise RuntimeError(
                    f"tenant_meta.json är trasig och kan inte tolkas som JSON ({exc}) för tenanten "
                    f"under {self.data_dir} (tenant-katalog '{self.data_dir.name}') — vägrar öppna "
                    "tenanten. Undersök och åtgärda filen manuellt; detta tystas aldrig ner."
                ) from exc
            origin = raw.get("corpus_origin") if isinstance(raw, dict) else None
            if origin not in CORPUS_ORIGINS:
                raise RuntimeError(
                    f"tenant_meta.json har ett ogiltigt corpus_origin ({origin!r}, tillåtna: "
                    f"{CORPUS_ORIGINS}) för tenanten under {self.data_dir} (tenant-katalog "
                    f"'{self.data_dir.name}') — vägrar öppna tenanten. Undersök och åtgärda filen "
                    "manuellt; detta tystas aldrig ner."
                )
            return origin

        if corpus_origin is not None:
            origin = corpus_origin
        else:
            if not self._documents_json_shows_already_migrated_tenant():
                origin = "synthetic"
                logger.info(
                    "Tenant-katalog %s saknar corpus_origin — migrerar till 'synthetic' och skriver tillbaka",
                    self.data_dir,
                )
            else:
                raise RuntimeError(
                    f"tenant_meta.json saknas under {self.data_dir} (tenant-katalog "
                    f"'{self.data_dir.name}'), men dokumenten där har redan corpus_origin stämplat "
                    "— tenanten verkar redan ha migrerats en gång men saknar nu sin tenant_meta.json. "
                    "Vägrar tyst falla tillbaka till 'synthetic'; undersök manuellt vad som tog bort filen."
                )
        _atomic_write(p, json.dumps({"corpus_origin": origin}, ensure_ascii=False, indent=2))
        return origin

    def _documents_json_shows_already_migrated_tenant(self) -> bool:
        """True only when documents.json exists, is non-empty, and EVERY
        entry already carries a corpus_origin — the signature of a tenant
        that already went through CI2 migration once. False for a missing/
        empty documents.json (nothing recorded yet — safe to default) and
        for a legacy documents.json with at least one entry missing
        corpus_origin (the genuine CI2 migration case)."""
        p = self.data_dir / "documents.json"
        if not p.exists():
            return False
        try:
            raw = json.loads(p.read_text("utf-8"))
        except Exception as exc:
            raise RuntimeError(
                f"documents.json är trasig och kan inte tolkas som JSON ({exc}) under {self.data_dir} "
                f"(tenant-katalog '{self.data_dir.name}'), och tenant_meta.json saknas — kan inte "
                "avgöra om tenanten är legacy. Vägrar öppna tenanten."
            ) from exc
        if not raw:
            return False
        return all("corpus_origin" in v for v in raw.values())

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
        try:
            raw = json.loads(p.read_text("utf-8"))
        except Exception as exc:
            # Fail-closed (CI3 hardening): a corrupt document register must
            # never crash __init__ with a bare traceback, and must never be
            # silently skipped — name the file and the tenant, loudly.
            raise RuntimeError(
                f"documents.json är trasig och kan inte tolkas som JSON ({exc}) för tenanten "
                f"under {self.data_dir} (tenant-katalog '{self.data_dir.name}') — vägrar starta "
                "med ett skadat dokumentregister. Återställ filen från backup eller undersök manuellt."
            ) from exc
        migrated_ids: list[str] = []
        docs: dict[str, DocumentMeta] = {}
        for k, v in raw.items():
            if "corpus_origin" not in v:
                v = {**v, "corpus_origin": self.corpus_origin}
                migrated_ids.append(k)
            docs[k] = DocumentMeta.model_validate(v)
        if migrated_ids:
            logger.info(
                "Migrerar %d dokument utan corpus_origin -> '%s' (tenant-ursprung) i %s",
                len(migrated_ids), self.corpus_origin, self.data_dir,
            )
            payload = {k: v.model_dump() for k, v in docs.items()}
            _atomic_write(p, json.dumps(payload, ensure_ascii=False, indent=2))
        return docs

    def _save_documents(self) -> None:
        payload = {k: v.model_dump() for k, v in self.documents.items()}
        _atomic_write(self.data_dir / "documents.json", json.dumps(payload, ensure_ascii=False, indent=2))

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
            if enrichment_enabled():
                # Enriched search string per chunk (app/enrich.py). Sets the
                # index-only search_text; frozen c.text and PageData.words are
                # untouched, so citation verification is wholly unaffected.
                search_map = chunk_search_texts(list(new_chunks.values()), self.pages)
                for cid, search_text in search_map.items():
                    new_chunks[cid].search_text = search_text
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
        # Resource guard runs BEFORE OCR dispatch: extract_pdf already walks
        # every page of the PDF (text or not), so the page count is known
        # up front — a 400+ page scanned PDF must be rejected here, not
        # after burning minutes of tesseract time on a document we're about
        # to refuse anyway.
        if len(pages) > MAX_DOCUMENT_PAGES:
            raise ValueError(
                f"Dokumentet har {len(pages)} sidor — max {MAX_DOCUMENT_PAGES}. Dela upp filen."
            )
        total_words = sum(len(p.words) for p in pages)
        source: str = "digital"
        if total_words == 0:
            # Document-level dispatch: a scanned PDF has zero digital words on
            # EVERY page, so "no text layer anywhere" is treated as "this is
            # the scanned case" and OCR replaces the whole document's
            # extraction. Mixed digital/scanned documents (e.g. one scanned
            # page inside an otherwise digital PDF) are out of scope — such a
            # document already has total_words > 0 and never reaches OCR.
            if not tesseract_available():
                raise ValueError(
                    "Dokumentet saknar textlager (troligen en skannad PDF). "
                    "OCR kräver tesseract med svenskt språkstöd, vilket inte "
                    "är tillgängligt på den här servern."
                )
            try:
                pages = ocr_pdf(pdf_bytes)
            except RuntimeError as exc:
                # tesseract exited non-zero (environment problem, not a
                # content problem) — surface as a user-facing Swedish 422
                # via main.py's existing ValueError -> HTTPException mapping.
                raise ValueError(
                    "OCR-motorn misslyckades — kontrollera tesseract-installationen."
                ) from exc
            except subprocess.TimeoutExpired as exc:
                raise ValueError(
                    "OCR-motorn tog för lång tid (timeout) — kontrollera tesseract-installationen."
                ) from exc
            total_words = sum(len(p.words) for p in pages)
            if total_words == 0:
                raise ValueError("OCR kunde inte hitta någon läsbar text i dokumentet.")
            source = "scanned"
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
                    source=source,
                    # Corpus-isolation guard (CI2): stamped from the tenant's
                    # own origin. add_document takes NO caller-supplied
                    # origin parameter — there is no argument to abuse, so a
                    # customer tenant cannot receive a public_scraped (or any
                    # other-origin) document through any ingestion API.
                    corpus_origin=self.corpus_origin,
                )
                if meta.corpus_origin != self.corpus_origin:
                    # Defense-in-depth: this can't happen via the construction
                    # above, but guards any future refactor that builds
                    # DocumentMeta elsewhere and hands it to add_document.
                    raise ValueError(
                        f"corpus_origin-avvikelse: dokumentet har '{meta.corpus_origin}' men "
                        f"tenanten har '{self.corpus_origin}' — ett dokument kan aldrig ha ett "
                        "annat ursprung än sin tenant."
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
