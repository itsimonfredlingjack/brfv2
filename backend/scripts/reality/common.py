"""Shared helpers for reality scripts on the REAL scanned corpus (Tasks 4-6).

Temp-tenant ingestion via the REAL `Store.add_document` path (store.py:125-
149 — the same dispatch the API uses), payload-window derivation from OCR'd
chunk text, retrieval-order K-alias resolution (mirrors
`app.answer._render_excerpts` so a scripted FakeLLM response can cite the
correct alias without guessing), and two independent verification methods
reused from this folder's existing rigs: the rect-vs-quote token check
(`verify_highlights.py`), adapted to OCR `PageData` instead of embedded PDF
text, and the ink-darkness formula (`ocr_reality.ink_metrics`), applied to a
citation's own returned rects rather than bulk OCR word boxes.

Nothing here prints or returns real document content by itself — callers are
responsible for keeping real text (chunk text, quotes, filenames) out of
anything committed; this module's job is offline mechanics only.
"""

from __future__ import annotations

import contextlib
import tempfile
import uuid
from pathlib import Path

import fitz  # noqa: E402  (PyMuPDF)

from app.normalize import canonical_stream, find_spans
from app.ocr import OCR_MIN_CONF
from app.schemas import Chunk, DocumentMeta, Word
from app.store import Store
from scripts.eval import install_network_audit  # noqa: F401  (re-exported)
from scripts.ocr_spike import TesseractAdapter, rasterize
from scripts.reality.ocr_reality import classify  # noqa: F401  (re-exported)

try:
    import numpy as np
except Exception:  # pragma: no cover
    np = None

BACKEND = Path(__file__).resolve().parent.parent.parent
DEFAULT_FOLDER = BACKEND.parent / "DONT_PUSH_brf_stuff"
DEFAULT_OUT = BACKEND / "out" / "reality"


# ---------- network-audit self-enforcement (hardening, Task 5) ----------


def assert_zero_connections(audit_log: list[dict]) -> None:
    """Hard-fail (non-zero exit, loud message) unless `audit_log` is empty.

    `install_network_audit` records every connect() call, including allowed
    loopback ones — a script that scripts BOTH the embedder (`BRF_EMBEDDER=
    hashed`) and the LLM (`FakeLLM`) has no legitimate reason to open a
    socket at all. Task 4's review flagged that a non-zero-but-all-allowed
    count could pass silently; this makes the expectation self-enforcing
    instead of relying on a human reading the printed summary. Callers that
    are not in a no-LLM context (e.g. a real self-hosted LLM endpoint) must
    not call this — it asserts EXACTLY zero, not just zero external."""
    if audit_log:
        hosts = sorted({f"{e['host']}:{e['port']}" for e in audit_log})
        raise SystemExit(
            f"NÄTVERKSREVISION MISSLYCKADES: {len(audit_log)} anslutning(ar) gjordes i en "
            f"no-LLM-kontext där noll förväntades (FakeLLM + BRF_EMBEDDER=hashed). "
            f"Värdar: {hosts}"
        )


# ---------- ingestion (the REAL path) ----------


@contextlib.contextmanager
def temp_store():
    """A throwaway, auto-cleaned temp-dir Store — the same
    `Store.add_document` dispatch the API uses. Real PDF bytes and OCR
    extraction are written under the temp dir for the run's duration only;
    the directory (and any copy of real document content in it) is removed
    on context exit.

    Corpus-isolation guard (CI2): declared `corpus_origin="public_scraped"` —
    reality runs never touch real customer tenants — and named with the same
    `val-` prefix real public_scraped tenants must use, so a leftover temp
    dir is self-describing. This bypasses TenantRegistry entirely (there is
    no registered auth tenant here); the naming rule itself is only
    structurally enforced at TenantRegistry.create, not at bare Store
    construction, so this is a convention followed here for consistency, not
    a second enforcement point."""
    with tempfile.TemporaryDirectory(prefix=f"val-tmp-{uuid.uuid4().hex[:8]}-") as td:
        yield Store(data_dir=td, corpus_origin="public_scraped")


def ingest(store: Store, pdf_path: Path) -> DocumentMeta:
    return store.add_document(pdf_path.name, pdf_path.read_bytes())


def blank_pages(store: Store, doc_id: str) -> list[int]:
    """1-based page numbers that survived the conf gate with zero words —
    duplex backsides / drawing-only pages (reality report condition 2)."""
    return [p.number for p in store.pages[doc_id] if not p.words]


def sorted_doc_chunks(store: Store, doc_id: str) -> list[Chunk]:
    return sorted(
        (c for c in store.chunks.values() if c.document_id == doc_id),
        key=lambda c: (c.page, c.word_start),
    )


# ---------- conf-gate measurement (raw, ungated pass) ----------


def conf_gate_stats(pdf_path: Path, *, dpi: int = 250, lang: str = "swe") -> dict:
    """A raw (ungated) tesseract pass via TesseractAdapter — independent of
    the production `OCR_MIN_CONF` gate in `app.ocr` — measuring what
    fraction of raw word detections the gate drops on this real document.
    A second, real tesseract pass (the ingestion path already ran one via
    `Store.add_document`); costs are small (~1s/page measured locally)."""
    adapter = TesseractAdapter(lang=lang)
    doc = fitz.open(str(pdf_path))
    raw = kept = 0
    try:
        with tempfile.TemporaryDirectory() as td:
            for i, page in enumerate(doc):
                png = Path(td) / f"p{i}.png"
                rasterize(page, dpi, png)
                words = adapter.ocr_page(png, dpi)
                raw += len(words)
                kept += sum(1 for w in words if w.conf >= OCR_MIN_CONF)
    finally:
        doc.close()
    return {
        "raw_words": raw,
        "kept_words": kept,
        "drop_fraction": round(1 - kept / raw, 4) if raw else None,
    }


# ---------- payload derivation (deterministic — pinned by unit tests) ----------


def single_span_payload(text: str, *, min_words: int = 6, max_words: int = 16) -> str | None:
    """A 6-16-word contiguous window of chunk text: the first `max_words`
    words, capped by the chunk's own length. `None` if the chunk is too
    short to hold a payload of the minimum size."""
    words = text.split()
    if len(words) < min_words:
        return None
    return " ".join(words[: min(max_words, len(words))])


def multi_span_payload(text: str, *, span_len: int = 4, gap: int = 3) -> tuple[str, str] | None:
    """Two disjoint, non-adjacent windows from the same chunk text: shorter
    than the single-span window, separated by >= `gap` words so they are
    genuinely disjoint fragments rather than one contiguous quote split in
    two. `None` if the chunk is too short to hold both windows + the gap."""
    words = text.split()
    second_start = span_len + gap
    if len(words) < second_start + span_len:
        return None
    first = words[:span_len]
    second = words[second_start : second_start + span_len]
    return " ".join(first), " ".join(second)


def sample_chunks(chunks: list[Chunk], n: int = 10) -> list[Chunk]:
    """Evenly spaced, deterministic sample across a document's chunks (in
    the order given — callers pass reading order via `sorted_doc_chunks`)."""
    if len(chunks) <= n:
        return list(chunks)
    stride = len(chunks) / n
    idxs = sorted({min(len(chunks) - 1, int(i * stride)) for i in range(n)})
    return [chunks[i] for i in idxs]


def corrupt_span(span: str) -> str:
    """Flip one alphabetic character (last one found, scanning from the
    end) so the span is byte-for-byte non-verbatim — proves the
    verification invariant rejects on a single-char edit, not just gross
    fabrication. Falls back to truncation for a span with no letters."""
    chars = list(span)
    for i in range(len(chars) - 1, -1, -1):
        if chars[i].isalpha():
            chars[i] = "x" if chars[i].lower() != "x" else "z"
            return "".join(chars)
    return span[:-1] if len(span) > 1 else span + "#"


# ---------- retrieval-order alias resolution (mirrors _render_excerpts) ----------


def alias_for_chunk(store: Store, question: str, chunk_id: str):
    """Run the SAME retrieval call `app.answer.ask` makes internally
    (identical args, so results match exactly — `HybridIndex.search` is
    deterministic) and find the K-alias the target chunk would get. Returns
    `(alias, hits)`; `alias` is `None` on a retrieval miss (the chunk isn't
    among the top-K hits) — the honest thing to record rather than
    bypassing retrieval by injecting the chunk id directly."""
    s = store.settings
    index, _chunks, _pages, _documents = store.snapshot()
    hits = index.search(
        question,
        weight=s.searchWeighting / 100.0,
        candidates=s.candidateCount,
        top_k=s.topK,
        min_confidence=0.0,
    )
    for i, h in enumerate(hits):
        if h.chunk_id == chunk_id:
            return f"K{i + 1}", hits
    return None, hits


# ---------- independent verification (verify_highlights.py method, OCR pages) ----------


def canon(tokens: list[str]) -> list[str]:
    return [t for t, _ in canonical_stream(tokens)]


def rect_covered_words(page_words: list[Word], rects: list[list[float]]) -> list[str]:
    """Words from the stored OCR `PageData` whose center falls inside a
    returned rect — `verify_highlights.py`'s method, applied to OCR pages
    (`Word.text`) instead of embedded PDF text (`page.get_text('words')`)."""
    picked: list[str] = []
    for r in rects:
        x0, y0, x1, y1 = r
        for w in page_words:
            cx, cy = (w.x0 + w.x1) / 2, (w.y0 + w.y1) / 2
            if x0 <= cx <= x1 and y0 <= cy <= y1:
                picked.append(w.text)
    return picked


def independent_rect_verdict(page_words: list[Word], rects: list[list[float]], spans: list[str]) -> str:
    """Re-derive, independently of `citations.resolve_citation`, whether a
    returned citation is honest: (1) every span is independently verbatim-
    findable among the page's OCR words (the invariant, checked a second
    way); (2) the rect-covered words equal the union of the spans' words
    (exact, or a superset only by edge spillover). Same verdict vocabulary
    as `verify_highlights.py`."""
    page_word_texts = [w.text for w in page_words]
    spans_verify = all(find_spans(page_word_texts, sp) for sp in spans)
    if not spans_verify:
        return "INVARIANT-VIOLATION(span-unverifiable)"
    picked_norm = canon(rect_covered_words(page_words, rects))
    rect_tokens = sorted(picked_norm)
    span_tokens = sorted(t for sp in spans for t in canon(sp.split()))
    if rect_tokens == span_tokens:
        return "exact"
    covered = all(set(canon(sp.split())) <= set(picked_norm) for sp in spans)
    if covered and len(rect_tokens) >= len(span_tokens):
        return "superset(edge-spill)"
    inter = len(set(rect_tokens) & set(span_tokens))
    union = len(set(rect_tokens) | set(span_tokens)) or 1
    return f"MISMATCH(jaccard={inter / union:.2f})"


# ---------- ink check (ocr_reality.ink_metrics formula, applied to returned rects) ----------


def rects_on_ink(pdf_path: Path, page_no: int, rects: list[list[float]], *, dpi: int = 250) -> dict:
    """Fraction of returned rects whose interior is dark against the page
    background — the SAME darkness-threshold formula as
    `ocr_reality.ink_metrics` (dark pixel < 140 gray; a box counts as
    on-ink if its dark fraction exceeds `max(0.04, 2x page baseline)`), but
    applied to one citation's specific returned rects rather than bulk OCR
    word boxes: the geometric no-embedded-truth proxy for THIS highlight."""
    if np is None:
        return {"total": 0, "on_ink": 0, "on_ink_rate": None}
    doc = fitz.open(str(pdf_path))
    try:
        page = doc[page_no - 1]
        scale = dpi / 72.0
        pix = page.get_pixmap(dpi=dpi, colorspace=fitz.csGRAY)
        arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.stride)[:, : pix.width]
        dark = arr < 140
        page_dark = float(dark.mean())
        total = on_ink = 0
        for r in rects:
            x0, y0, x1, y1 = r
            x0i, y0i = max(0, int(x0 * scale)), max(0, int(y0 * scale))
            x1i, y1i = min(pix.width, int(x1 * scale)), min(pix.height, int(y1 * scale))
            if x1i <= x0i or y1i <= y0i:
                continue
            frac = float(dark[y0i:y1i, x0i:x1i].mean())
            total += 1
            if frac > max(0.04, 2 * page_dark):
                on_ink += 1
        return {"total": total, "on_ink": on_ink, "on_ink_rate": round(on_ink / total, 4) if total else None}
    finally:
        doc.close()
