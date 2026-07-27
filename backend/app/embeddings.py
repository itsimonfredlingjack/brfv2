"""Pluggable embedding providers.

Default preference: model2vec multilingual static embeddings (real semantic
vectors, small and fast) when the package + model are available; otherwise a
deterministic, offline, pure-Python hashed character-n-gram embedder that
still provides a useful second retrieval signal for morphology-rich Swedish.
Force a provider with BRF_EMBEDDER=hashed|model2vec.
"""

from __future__ import annotations

import logging
import math
import os
import zlib
from functools import lru_cache
from typing import Protocol

from .normalize import normalize_text

logger = logging.getLogger("brf.embeddings")


class Embedder(Protocol):
    name: str

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class HashedNgramEmbedder:
    """Hashing-trick char-3..5-gram vectors, L2-normalized. Deterministic,
    dependency-free, offline."""

    name = "hashed-char-ngram"
    dim = 512

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._one(t) for t in texts]

    def _one(self, text: str) -> list[float]:
        v = [0.0] * self.dim
        s = " " + " ".join(normalize_text(text).split()) + " "
        counts: dict[str, int] = {}
        for n in (3, 4, 5):
            for i in range(len(s) - n + 1):
                g = s[i : i + n]
                counts[g] = counts.get(g, 0) + 1
        for g, c in counts.items():
            h = zlib.crc32(g.encode("utf-8"))
            sign = 1.0 if (h >> 31) & 1 else -1.0
            v[h % self.dim] += sign * (1.0 + math.log(c))
        norm = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / norm for x in v]


class Model2VecEmbedder:
    """Multilingual static embeddings via model2vec (downloads once from HF)."""

    MODEL_ID = "minishlab/potion-multilingual-128M"

    def __init__(self) -> None:
        from model2vec import StaticModel  # import-guarded

        self.model = StaticModel.from_pretrained(self.MODEL_ID)
        self.name = f"model2vec:{self.MODEL_ID.split('/')[-1]}"

    def embed(self, texts: list[str]) -> list[list[float]]:
        import numpy as np

        vecs = self.model.encode(texts)
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return (vecs / norms).tolist()


@lru_cache(maxsize=None)
def _build_embedder(choice: str) -> Embedder:
    if choice == "hashed":
        return HashedNgramEmbedder()
    if choice in ("auto", "model2vec"):
        try:
            emb = Model2VecEmbedder()
            logger.info("Embedding provider: %s", emb.name)
            return emb
        except Exception as exc:
            if choice == "model2vec":
                raise
            logger.warning("model2vec unavailable (%s); falling back to hashed n-grams", exc)
    return HashedNgramEmbedder()


def get_embedder() -> Embedder:
    """Shared, cached provider instance.

    Caching is not an optimisation here, it is a correctness requirement:
    Model2VecEmbedder loads ~1.5 GB of weights per instance, and this function
    is called per Store (so once per tenant) AND inside the /api/health
    handler. Uncached, every health check allocated another 1.5 GB — enough
    for readiness polling alone to OOM the process. The models are read-only
    and stateless, so one instance is safely shared.

    Keyed on the env value rather than a bare maxsize=1 so that flipping
    BRF_EMBEDDER between providers still takes effect.
    """
    return _build_embedder(os.environ.get("BRF_EMBEDDER", "auto"))
