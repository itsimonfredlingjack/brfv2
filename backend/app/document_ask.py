"""Document-level selection and packing for the third ask() path.

Product selection is the local model over cached regulatory descriptions
(1–3 documents). Max fused score is not a scorer here — it measures 1/11 on
BRF-1 document pick and must not steer packing. `score_documents` remains for
measurement-only U-shape / probe ordering.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from .document_describe import described_documents, ensure_descriptions
from .full_corpus import QUESTION_RESERVE_TOKENS, hits_for_full_corpus
from .llm import extract_json_object
from .schemas import Chunk, DocumentMeta, RetrievalHit

logger = logging.getLogger("brf.document_ask")

MAX_FULL_DOCUMENTS = 3


@dataclass(frozen=True)
class DocumentScore:
    document_id: str
    document_name: str
    max_score: float
    n_matching_chunks: int


@dataclass(frozen=True)
class PackDecision:
    use_documents: bool
    bound: str
    document_ids: list[str]
    scores: list[DocumentScore]
    prefix_tokens: int | None


def score_documents(hits: list[RetrievalHit]) -> list[DocumentScore]:
    grouped: dict[str, DocumentScore] = {}
    for hit in hits:
        existing = grouped.get(hit.document_id)
        if existing is None:
            grouped[hit.document_id] = DocumentScore(
                document_id=hit.document_id,
                document_name=hit.document_name,
                max_score=hit.score,
                n_matching_chunks=1,
            )
            continue
        grouped[hit.document_id] = DocumentScore(
            document_id=existing.document_id,
            document_name=existing.document_name,
            max_score=max(existing.max_score, hit.score),
            n_matching_chunks=existing.n_matching_chunks + 1,
        )
    return sorted(
        grouped.values(),
        key=lambda r: (-r.max_score, r.document_name, r.document_id),
    )


def hits_for_document_ids(
    chunks: dict[str, Chunk],
    documents: dict[str, DocumentMeta],
    document_ids: list[str],
) -> list[RetrievalHit]:
    allowed = set(document_ids)
    subset = {cid: chunk for cid, chunk in chunks.items() if chunk.document_id in allowed}
    return hits_for_full_corpus(subset, documents)


def _index_letter(i: int) -> str:
    if i < 26:
        return chr(ord("A") + i)
    return _index_letter(i // 26 - 1) + chr(ord("A") + (i % 26))


def catalog_entries(documents: dict[str, DocumentMeta]) -> list[tuple[str, DocumentMeta]]:
    return [(_index_letter(i), meta) for i, meta in enumerate(described_documents(documents))]


def selection_prompt(entries: list[tuple[str, DocumentMeta]], question: str) -> tuple[str, str]:
    system = (
        "Du väljer vilka handlingar som kan besvara frågan. "
        "Välj 1–3 handlingar. Du svarar inte på frågan. Du citerar inte. "
        'Svara med JSON {"documents": ["X", ...]} där varje X är en bokstav '
        "ur listan. Välj minst en och högst tre."
    )
    lines = ["HANDLINGAR:"]
    for letter, meta in entries:
        lines.append(f"{letter}. {meta.description}")
    lines.append("")
    lines.append(f"FRÅGA: {question}")
    return system, "\n".join(lines)


def parse_selected_letters(raw: str, valid: set[str]) -> list[str]:
    try:
        obj = extract_json_object(raw)
    except Exception:
        obj = {}
    docs = obj.get("documents") if isinstance(obj, dict) else None
    if isinstance(docs, str):
        docs = [docs]
    out: list[str] = []
    if isinstance(docs, list):
        for item in docs:
            if not isinstance(item, str):
                continue
            letter = item.strip().upper()
            if letter in valid and letter not in out:
                out.append(letter)
            if len(out) >= MAX_FULL_DOCUMENTS:
                break
        if out:
            return out
    for letter in re.findall(r"\b([A-Z]{1,2})\b", raw.upper()):
        if letter in valid and letter not in out:
            out.append(letter)
        if len(out) >= MAX_FULL_DOCUMENTS:
            break
    return out


def select_documents_by_description(
    *,
    question: str,
    documents: dict[str, DocumentMeta],
    provider,
    model: str,
) -> list[str]:
    """Return document ids, 1–3, in the model's order. Empty = cannot select."""
    entries = catalog_entries(documents)
    if not entries:
        return []
    system, user = selection_prompt(entries, question)
    try:
        raw = provider.complete(system, user, max_tokens=96, model=model)
    except Exception:
        logger.exception("beskrivningsurval misslyckades")
        return []
    valid = {letter for letter, _meta in entries}
    letters = parse_selected_letters(raw, valid)
    by_letter = {letter: meta.id for letter, meta in entries}
    return [by_letter[letter] for letter in letters if letter in by_letter]


def evaluate_document_path(
    *,
    question: str,
    index,
    chunks: dict[str, Chunk],
    documents: dict[str, DocumentMeta],
    runtime,
    settings,
    provider,
    store=None,
) -> PackDecision:
    # `index` is unused: fused retrieval must not rank documents (BRF-1 1/11).
    _ = index
    if store is not None:
        ensure_descriptions(store, provider)
        documents = dict(store.documents)

    if not catalog_entries(documents):
        return PackDecision(False, "no_descriptions", [], [], None)

    model = getattr(provider, "model", "") or settings.aiModel
    picked_ids = select_documents_by_description(
        question=question,
        documents=documents,
        provider=provider,
        model=model,
    )
    if not picked_ids:
        return PackDecision(False, "no_selection", [], [], None)

    scores = [
        DocumentScore(
            document_id=doc_id,
            document_name=documents[doc_id].name if doc_id in documents else doc_id,
            max_score=1.0 - i * 0.01,
            n_matching_chunks=1,
        )
        for i, doc_id in enumerate(picked_ids)
        if doc_id in documents
    ]
    from .answer import _CITATION_HEADROOM_TOKENS, _system_prompt

    return pack_documents(
        scores=scores,
        chunks=chunks,
        documents=documents,
        runtime=runtime,
        system=_system_prompt(settings),
        n_ctx=runtime.n_ctx(),
        response_budget=settings.maxResponseLength + _CITATION_HEADROOM_TOKENS,
        threshold=None,
    )


def pack_documents(
    *,
    scores: list[DocumentScore],
    chunks: dict[str, Chunk],
    documents: dict[str, DocumentMeta],
    runtime,
    system: str,
    n_ctx: int | None,
    response_budget: int,
    threshold: int | None,
) -> PackDecision:
    _ = threshold
    if n_ctx is None:
        return PackDecision(False, "n_ctx_missing", [], scores, None)
    if not scores:
        return PackDecision(False, "no_hits", [], scores, None)

    packed: list[str] = []
    prefix_tokens: int | None = None
    for i, row in enumerate(scores):
        if len(packed) >= MAX_FULL_DOCUMENTS:
            break
        candidate = packed + [row.document_id]
        prefix_tokens = _prefix_tokens(candidate, chunks, documents, runtime, system)
        fits = prefix_tokens + QUESTION_RESERVE_TOKENS + response_budget <= n_ctx
        if i == 0 and not fits:
            logger.info(
                "document_ask bound=top_document_n_ctx n_docs=0 prefix_tokens=%s top_max=%s top_n_chunks=%s",
                prefix_tokens,
                row.max_score,
                row.n_matching_chunks,
            )
            return PackDecision(False, "top_document_n_ctx", [], scores, prefix_tokens)
        if fits:
            packed = candidate

    logger.info(
        "document_ask bound=fits n_docs=%s prefix_tokens=%s top_max=%s top_n_chunks=%s",
        len(packed),
        prefix_tokens,
        scores[0].max_score,
        scores[0].n_matching_chunks,
    )
    return PackDecision(True, "fits", packed, scores, prefix_tokens)


def _prefix_tokens(
    document_ids: list[str],
    chunks: dict[str, Chunk],
    documents: dict[str, DocumentMeta],
    runtime,
    system: str,
) -> int:
    from .answer import _render_excerpts

    hits = hits_for_document_ids(chunks, documents, document_ids)
    excerpts, _alias = _render_excerpts(hits)
    return runtime.count(system + "\n\nUTDRAG:\n" + excerpts)
