"""Cross-encoder reranking stage.

Diagnosed: true financial-table answer rows rank 4-37 among 40-54 hybrid
(BM25 ⊕ dense) candidates — only the top-6 ever reaches the prompt. Fix:
retrieve wide, cross-encode (query, chunk_text) pairs with a multilingual
jina reranker, then cut to the prompt's usual top_k. Prompt size is
unchanged; only WHICH chunks fill it changes.

Lifted from rag-project-backend's services/reranking_service.py, adapted to
brfv2's conventions: SYNC (no asyncio — brfv2's endpoints are sync FastAPI
handlers), no service framework, module-level lazy singleton like llm.py's
`_provider` pattern. The CUDA-OOM fallback dance in the source project is
dropped — MPS/CPU is our only topology, no GPU contention with a co-resident
LLM to dance around.
"""

from __future__ import annotations

import logging
import os

from .schemas import RetrievalHit

logger = logging.getLogger("brf.rerank")

# Default cross-encoder. Overridable via BRF_RERANK_MODEL — used by the licensing
# eval to swap in a commercially-licensed model (e.g. a clean Apache-2.0
# cross-encoder) without code change. Read at CALL time so a test/measurement can
# select the model via the environment; the lazy singleton still loads only once.
DEFAULT_MODEL_NAME = "jinaai/jina-reranker-v2-base-multilingual"
DEFAULT_MAX_LENGTH = 1024


def model_name() -> str:
    return os.environ.get("BRF_RERANK_MODEL", DEFAULT_MODEL_NAME)


def max_length() -> int:
    """Tokenizer truncation length. Overridable via BRF_RERANK_MAX_LENGTH because
    it is model-bound: jina supports 1024, but XLM-R-based cross-encoders
    (e.g. cross-encoder/mmarco-mMiniLMv2) cap at 512 positions and overflow
    above that. Set per model when swapping via BRF_RERANK_MODEL."""
    return int(os.environ.get("BRF_RERANK_MAX_LENGTH", str(DEFAULT_MAX_LENGTH)))

# Lazy singleton, like llm.py's `_provider` — loaded once, on first use.
_model = None


def _resolve_device() -> str:
    import torch

    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


def _load_model():
    global _model
    if _model is not None:
        return _model
    from sentence_transformers import CrossEncoder

    device = _resolve_device()
    name = model_name()
    logger.info("Laddar cross-encoder-omrankare %s på %s", name, device)
    _model = CrossEncoder(name, max_length=max_length(), trust_remote_code=True, device=device)
    return _model


def _default_predict(pairs: list[tuple[str, str]]) -> list[float]:
    """Score (query, chunk_text) pairs. Jina returns pre-normalized 0-1
    scores — no sigmoid needed. torch.no_grad() only; no CUDA-OOM retry dance
    (not our topology, see module docstring)."""
    import torch

    model = _load_model()
    with torch.no_grad():
        scores = model.predict(pairs)
    return [float(s) for s in scores]


# Scoring seam for tests: monkeypatch this module attribute to inject a fake
# scorer without loading the real model. rerank_chunks() below reads the
# name at call time (module-global lookup), so reassignment takes effect
# even though rerank_chunks doesn't take the scorer as a parameter.
_predict_fn = _default_predict


def reranker_available() -> bool:
    """Cheap availability probe: can the deps import, and are the model
    weights already cached? Deliberately does NOT construct a CrossEncoder
    (that loads weights into memory/VRAM — too slow and heavy for a mere
    availability check called on every ask())."""
    try:
        import sentence_transformers  # noqa: F401
        import torch  # noqa: F401
    except ImportError:
        return False
    try:
        from huggingface_hub import try_to_load_from_cache

        cached = try_to_load_from_cache(model_name(), "config.json")
        return isinstance(cached, str)
    except Exception:
        # Any cache-probe surprise (corrupt cache, hub API changes, ...)
        # means "not confidently available" — caller treats this as
        # unavailable and raises loudly, never silently skips reranking.
        return False


def rerank_chunks(query: str, hits: list[RetrievalHit], top_k: int) -> list[RetrievalHit]:
    """Score each hit's chunk text against the query, sort descending, break
    ties deterministically by original rank (earlier-ranked hit wins), and
    cut to top_k. Every other hit field is preserved untouched; only
    `rerank_score` is populated on the returned copies — `score`/`confidence`
    stay exactly as retrieval produced them (see answer.py's relevance-gate
    comment for why that separation matters)."""
    if not hits:
        return []
    pairs = [(query, h.text) for h in hits]
    scores = _predict_fn(pairs)
    ranked = sorted(
        zip(hits, scores, range(len(hits))),
        key=lambda triple: (-triple[1], triple[2]),
    )
    return [hit.model_copy(update={"rerank_score": float(score)}) for hit, score, _ in ranked[:top_k]]
