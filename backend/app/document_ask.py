"""Document-level scoring and packing for the third ask() path."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from .full_corpus import QUESTION_RESERVE_TOKENS, hits_for_full_corpus
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


def pack_documents(
    *,
    scores: list[DocumentScore],
    chunks: dict[str, Chunk],
    documents: dict[str, DocumentMeta],
    runtime,
    system: str,
    n_ctx: int | None,
    response_budget: int,
    threshold: int,
) -> PackDecision:
    if threshold == 0:
        return PackDecision(False, "threshold", [], scores, None)
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
