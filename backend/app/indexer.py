"""Hybrid retrieval: BM25 (lexical) ⊕ embedding cosine (dense).

Ranking uses min-max-normalized weighted fusion over the candidate pool.
The refusal gate uses `confidence` — an absolute 0..1 blend of IDF-weighted
query-term coverage and cosine similarity — because normalized fusion scores
are relative and say nothing about whether the corpus can answer at all.
"""

from __future__ import annotations

import math

from .embeddings import Embedder
from .normalize import canonical_stream
from .schemas import Chunk, RetrievalHit


def tokenize(text: str) -> list[str]:
    return [t.rstrip("-") for t, _ in canonical_stream(text.split())]


class BM25:
    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self.doc_tokens: list[list[str]] = []
        self.doc_freq: dict[str, int] = {}
        self.avg_len = 0.0

    def fit(self, docs: list[list[str]]) -> None:
        self.doc_tokens = docs
        self.doc_freq = {}
        for toks in docs:
            for t in set(toks):
                self.doc_freq[t] = self.doc_freq.get(t, 0) + 1
        self.avg_len = (sum(len(d) for d in docs) / len(docs)) if docs else 0.0

    def idf(self, term: str) -> float:
        n = len(self.doc_tokens)
        df = self.doc_freq.get(term, 0)
        return math.log(1.0 + (n - df + 0.5) / (df + 0.5))

    def scores(self, query_tokens: list[str]) -> list[float]:
        out = []
        for toks in self.doc_tokens:
            tf: dict[str, int] = {}
            for t in toks:
                tf[t] = tf.get(t, 0) + 1
            s = 0.0
            dl = len(toks) or 1
            for q in query_tokens:
                f = tf.get(q, 0)
                if not f:
                    continue
                s += self.idf(q) * (f * (self.k1 + 1)) / (f + self.k1 * (1 - self.b + self.b * dl / self.avg_len))
            out.append(s)
        return out


def _cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))  # vectors are L2-normalized


def _trigrams(t: str) -> frozenset[str]:
    return frozenset(t[i : i + 3] for i in range(len(t) - 2)) if len(t) >= 3 else frozenset()


def _minmax(values: dict[int, float]) -> dict[int, float]:
    if not values:
        return {}
    lo, hi = min(values.values()), max(values.values())
    if hi - lo < 1e-12:
        return {k: (1.0 if hi > 0 else 0.0) for k in values}
    return {k: (v - lo) / (hi - lo) for k, v in values.items()}


class HybridIndex:
    def __init__(self, embedder: Embedder) -> None:
        self.embedder = embedder
        self.chunks: list[Chunk] = []
        self.doc_names: dict[str, str] = {}
        self.bm25 = BM25()
        self.vectors: list[list[float]] = []
        self._token_sets: list[set[str]] = []
        self._vocab_trigrams: dict[str, frozenset[str]] = {}

    def build(self, chunks: list[Chunk], doc_names: dict[str, str]) -> None:
        self.chunks = list(chunks)
        self.doc_names = dict(doc_names)
        docs = [tokenize(c.search_text or c.text) for c in self.chunks]
        self.bm25.fit(docs)
        self._token_sets = [set(d) for d in docs]
        self._vocab_trigrams = {
            t: _trigrams(t) for t in self.bm25.doc_freq if len(t) >= 5
        }
        self.vectors = self.embedder.embed([c.search_text or c.text for c in self.chunks]) if self.chunks else []

    def __len__(self) -> int:
        return len(self.chunks)

    def _expand_query(self, q_tokens: list[str]) -> dict[str, tuple[set[str], set[str]]]:
        """Map each query token to (strong, fuzzy) corpus-vocabulary matches.

        Strong = exact or substring containment — Swedish is compound-heavy
        ("snöröjningsjouren" ⊃ "snöröjning", "lägenheter" ⊂
        "bostadslägenheter"); safe enough to feed the BM25 ranking query.
        Fuzzy = trigram overlap ≥ 0.5 — catches inflection with vowel elision
        ("fönstren" ↔ "fönsterbyte"); used only by the confidence gate, at
        reduced weight, because it is too noisy for ranking.
        """
        vocab = self.bm25.doc_freq
        out: dict[str, tuple[set[str], set[str]]] = {}
        for q in set(q_tokens):
            strong: set[str] = set()
            fuzzy: set[str] = set()
            if q in vocab:
                strong.add(q)
            if len(q) >= 5:
                q_tri = _trigrams(q)
                for t in vocab:
                    if t == q or min(len(t), len(q)) < 5 or max(len(t), len(q)) < 6:
                        continue
                    if abs(len(t) - len(q)) <= 12 and (q in t or t in q):
                        strong.add(t)
                        continue
                    tri = self._vocab_trigrams.get(t)
                    if tri and q_tri and len(q_tri & tri) / len(q_tri) >= 0.5:
                        fuzzy.add(t)
            out[q] = (strong, fuzzy)
        return out

    def _coverage(self, expanded: dict[str, tuple[set[str], set[str]]], idx: int) -> float:
        total = 0.0
        matched = 0.0
        for q, (strong, fuzzy) in expanded.items():
            all_matches = strong | fuzzy
            if q in self.bm25.doc_freq:
                w = self.bm25.idf(q)
            elif all_matches:
                w = min(self.bm25.idf(m) for m in all_matches)  # most common variant
            else:
                w = self.bm25.idf(q)  # unseen term: max idf, drags coverage down
            total += w
            if any(m in self._token_sets[idx] for m in strong):
                matched += w
            elif any(m in self._token_sets[idx] for m in fuzzy):
                matched += 0.6 * w  # fuzzy hit: partial credit
        return matched / total if total > 0 else 0.0

    def search(
        self,
        query: str,
        *,
        weight: float,
        candidates: int,
        top_k: int,
        min_confidence: float,
    ) -> list[RetrievalHit]:
        """weight: 0.0 = pure BM25 … 1.0 = pure dense."""
        if not self.chunks:
            return []
        q_tokens = tokenize(query)
        expanded = self._expand_query(q_tokens)
        # BM25 sees the original tokens plus their STRONG expansions only —
        # fuzzy matches are gate-only (too noisy for ranking).
        bm25_query = list(q_tokens) + sorted(
            {m for strong, _ in expanded.values() for m in strong if m not in q_tokens}
        )
        bm25_all = self.bm25.scores(bm25_query)
        q_vec = self.embedder.embed([query])[0]
        dense_all = [_cosine(q_vec, v) for v in self.vectors]

        n = len(self.chunks)
        k = min(candidates, n)
        pool: set[int] = set()
        pool.update(sorted(range(n), key=lambda i: bm25_all[i], reverse=True)[:k])
        pool.update(sorted(range(n), key=lambda i: dense_all[i], reverse=True)[:k])

        bm25_n = _minmax({i: bm25_all[i] for i in pool})
        dense_n = _minmax({i: dense_all[i] for i in pool})

        scored = []
        for i in pool:
            fused = weight * dense_n[i] + (1 - weight) * bm25_n[i]
            cos01 = max(0.0, min(1.0, dense_all[i]))
            conf = 0.5 * self._coverage(expanded, i) + 0.5 * cos01
            scored.append((fused, conf, i))
        scored.sort(key=lambda t: (-t[0], t[2]))

        hits: list[RetrievalHit] = []
        for fused, conf, i in scored:
            if conf < min_confidence:
                continue
            c = self.chunks[i]
            hits.append(
                RetrievalHit(
                    chunk_id=c.id,
                    score=round(fused, 4),
                    confidence=round(conf, 4),
                    bm25=round(bm25_all[i], 4),
                    dense=round(dense_all[i], 4),
                    document_id=c.document_id,
                    document_name=self.doc_names.get(c.document_id, c.document_id),
                    page=c.page,
                    text=c.text,
                )
            )
            if len(hits) >= top_k:
                break
        return hits
