"""Size-gated full-corpus ask: tokenizer, n_ctx, fit gate, hit order.

llama.cpp chat lives at BRF_LLM_BASE_URL (…/v1). Context size and the
generator tokenizer do not: GET {origin}/props and POST {origin}/tokenize.
See docs/superpowers/specs/2026-08-16-full-corpus-ask-design.md.
"""

from __future__ import annotations

import hashlib
import logging
import os
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from .schemas import Chunk, DocumentMeta, RetrievalHit

logger = logging.getLogger("brf.full_corpus")

QUESTION_RESERVE_TOKENS = 512
ARCHIVE_PROBE = "stadgar styrelse förening kallelse årsredovisning ekonomi"
_UNSET = object()

Bound = Literal["fits", "threshold", "n_ctx", "n_ctx_missing", "tokenizer_error"]


@dataclass(frozen=True)
class FitDecision:
    use_full_corpus: bool
    bound: Bound
    chunk_token_sum: int
    prefix_tokens: int
    n_ctx: int | None
    threshold: int | None
    effective_cap: int | None


def decide_fit(
    *,
    chunk_token_sum: int,
    prefix_tokens: int,
    n_ctx: int | None,
    threshold: int | None,
    question_reserve: int = QUESTION_RESERVE_TOKENS,
    response_budget: int,
) -> FitDecision:
    """Window cap is n_ctx minus reserves. Optional threshold is an extra ceiling."""
    window_cap = (n_ctx - question_reserve - response_budget) if n_ctx is not None else None
    extra = threshold if threshold is not None and threshold > 0 else None
    if window_cap is None:
        effective_cap = extra
    elif extra is None:
        effective_cap = window_cap
    else:
        effective_cap = min(window_cap, extra)

    if threshold == 0:
        bound: Bound = "threshold"
        use = False
    elif n_ctx is None:
        bound = "n_ctx_missing"
        use = False
    elif effective_cap is not None and prefix_tokens > effective_cap:
        if extra is not None and window_cap is not None and extra < window_cap and prefix_tokens > extra:
            bound = "threshold"
            use = False
        else:
            bound = "n_ctx"
            use = False
    else:
        bound = "fits"
        use = True

    logger.info(
        "full_corpus bound=%s use=%s chunk_tokens=%s prefix_tokens=%s n_ctx=%s threshold=%s",
        bound,
        use,
        chunk_token_sum,
        prefix_tokens,
        n_ctx,
        threshold,
    )
    if bound == "n_ctx_missing":
        logger.warning(
            "n_ctx saknas — helarkivvägen kan inte övervägas, retrievalvägen används"
        )
    return FitDecision(
        use_full_corpus=use,
        bound=bound,
        chunk_token_sum=chunk_token_sum,
        prefix_tokens=prefix_tokens,
        n_ctx=n_ctx,
        threshold=threshold,
        effective_cap=effective_cap,
    )


class CorpusRuntime(Protocol):
    def n_ctx(self) -> int | None: ...
    def count(self, text: str) -> int: ...


def user_prompt(question: str, excerpts: str, *, full_corpus: bool) -> str:
    """Retrieval keeps FRÅGA first; full-corpus puts it last so the prefix is stable."""
    if full_corpus:
        return f"UTDRAG:\n{excerpts}\n\nFRÅGA: {question}"
    return f"FRÅGA: {question}\n\nUTDRAG:\n{excerpts}"


def edge_order(ranked_high_to_low: list[str]) -> list[str]:
    """U-shape: best first and last, worst toward the middle."""
    left: list[str] = []
    right: list[str] = []
    for i, item in enumerate(ranked_high_to_low):
        if i % 2 == 0:
            left.append(item)
        else:
            right.append(item)
    return left + list(reversed(right))


def ranked_document_ids(scores, documents: dict[str, DocumentMeta]) -> list[str]:
    scored = [row.document_id for row in scores if row.document_id in documents]
    seen = set(scored)
    rest = sorted(
        (doc_id for doc_id in documents if doc_id not in seen),
        key=lambda doc_id: (documents[doc_id].name, doc_id),
    )
    return edge_order(scored + rest)


def document_ids_for_probe(index, settings, documents: dict[str, DocumentMeta], chunks: dict) -> list[str]:
    """Query-independent ranking: frozen probe, then U-shape. Stable across questions."""
    return _document_ids_from_query(index, settings, documents, chunks, ARCHIVE_PROBE)


def document_ids_for_question(
    index,
    settings,
    documents: dict[str, DocumentMeta],
    chunks: dict,
    question: str,
) -> list[str]:
    """Query-dependent ranking. Prefix changes with the question — kills KV cache."""
    return _document_ids_from_query(index, settings, documents, chunks, question)


def _document_ids_from_query(index, settings, documents, chunks, query: str) -> list[str]:
    from .document_ask import score_documents

    n_chunks = max(len(chunks), 1)
    wide = index.search(
        query,
        weight=settings.searchWeighting / 100.0,
        candidates=max(settings.candidateCount, n_chunks),
        top_k=n_chunks,
        min_confidence=0.0,
    )
    return ranked_document_ids(score_documents(wide), documents)


def hits_for_full_corpus(
    chunks: dict[str, Chunk],
    documents: dict[str, DocumentMeta],
    *,
    document_ids: list[str] | None = None,
) -> list[RetrievalHit]:
    """Every chunk as a hit, in a total order. Scores are not retrieval scores."""
    if document_ids is None:
        ordered = sorted(
            chunks.values(),
            key=lambda c: (
                documents[c.document_id].name if c.document_id in documents else "",
                c.document_id,
                c.page,
                c.word_start,
                c.id,
            ),
        )
    else:
        rank = {doc_id: i for i, doc_id in enumerate(document_ids)}
        ordered = sorted(
            chunks.values(),
            key=lambda c: (
                rank.get(c.document_id, len(rank)),
                c.page,
                c.word_start,
                c.id,
            ),
        )
    hits: list[RetrievalHit] = []
    for chunk in ordered:
        meta = documents.get(chunk.document_id)
        hits.append(
            RetrievalHit(
                chunk_id=chunk.id,
                score=0.0,
                confidence=0.0,
                bm25=0.0,
                dense=0.0,
                document_id=chunk.document_id,
                document_name=meta.name if meta is not None else chunk.document_id,
                page=chunk.page,
                text=chunk.text,
                rerank_score=None,
            )
        )
    return hits


def prefix_fingerprint(system: str, excerpts: str) -> str:
    """Stable hash of the cacheable prefix (system + rendered excerpts, not the question)."""
    return hashlib.sha256((system + excerpts).encode("utf-8")).hexdigest()


def measure_tokens(
    runtime: CorpusRuntime,
    chunks: dict[str, Chunk],
    *,
    system: str,
    excerpts: str,
) -> tuple[int, int]:
    """chunk_token_sum (overlap counted twice) and prefix_tokens of the rendered prompt."""
    chunk_token_sum = sum(runtime.count(chunk.text) for chunk in chunks.values())
    prefix_tokens = runtime.count(system + "\n\nUTDRAG:\n" + excerpts)
    return chunk_token_sum, prefix_tokens


def server_origin(base_url: str) -> str:
    """Strip a trailing /v1 so /props and /tokenize hit the server origin."""
    url = base_url.rstrip("/")
    if url.endswith("/v1"):
        url = url[: -len("/v1")]
    return url.rstrip("/")


class LlamaCppRuntime:
    """Loopback llama.cpp origin: n_ctx from /props, tokens from /tokenize."""

    def __init__(self, base_url: str, transport: Any = None) -> None:
        import httpx

        origin = server_origin(base_url)
        timeout_s = float(os.environ.get("BRF_LLM_TIMEOUT_S", "300"))
        self._client = httpx.Client(base_url=origin, timeout=timeout_s, transport=transport)
        self._n_ctx: int | None | object = _UNSET

    def n_ctx(self) -> int | None:
        if self._n_ctx is not _UNSET:
            return self._n_ctx  # type: ignore[return-value]
        value = self._n_ctx_from_props()
        if value is None:
            value = self._n_ctx_from_slots()
        if value is None:
            logger.warning(
                "n_ctx saknas på llama.cpp /props och /slots — helarkivvägen kan inte övervägas"
            )
        self._n_ctx = value
        return value

    def count(self, text: str) -> int:
        resp = self._client.post("/tokenize", json={"content": text})
        resp.raise_for_status()
        tokens = resp.json().get("tokens")
        if not isinstance(tokens, list):
            raise ValueError("llama.cpp /tokenize svarade utan tokens-lista")
        return len(tokens)

    def _n_ctx_from_props(self) -> int | None:
        try:
            resp = self._client.get("/props")
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            return None
        settings = data.get("default_generation_settings") if isinstance(data, dict) else None
        if not isinstance(settings, dict):
            return None
        raw = settings.get("n_ctx")
        return raw if isinstance(raw, int) and raw > 0 else None

    def _n_ctx_from_slots(self) -> int | None:
        try:
            resp = self._client.get("/slots")
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            return None
        if not isinstance(data, list) or not data:
            return None
        raw = data[0].get("n_ctx") if isinstance(data[0], dict) else None
        return raw if isinstance(raw, int) and raw > 0 else None


def live_corpus_runtime() -> LlamaCppRuntime | None:
    """Injected at API/script boundaries. Tests keep BRF_LLM=fake → None → retrieval."""
    kind = os.environ.get("BRF_LLM", "").strip().lower()
    if kind in ("fake", "scripted", "none"):
        return None
    base = os.environ.get("BRF_LLM_BASE_URL", "").strip()
    if not base:
        return None
    return LlamaCppRuntime(base)

