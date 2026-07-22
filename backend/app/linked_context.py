"""Deterministic document-structure context closure.

Hybrid retrieval ranks chunks by the user's words. Some PDF tables encode the
actual answer with a short code in a task row while defining that code in a
legend on another page. The legend is semantically required but often has no
query-term overlap, so raising ``topK`` globally is neither precise nor safe.

This module appends a same-document legend only when a retrieved chunk contains
a coded leaf table row that uses one of the legend's explicitly defined codes.
It does not alter ranking, relevance scores, thresholds, or the original top-K
survivors. The appended chunk is ordinary citable source material and must pass
the same verbatim citation resolver as every other excerpt.
"""

from __future__ import annotations

import re

from .schemas import Chunk, DocumentMeta, RetrievalHit

_LEAF_ROW_CODE_RE = re.compile(r"\b[A-ZÅÄÖ]\d+(?:\.\d+){2,}\b")
_QUOTED_CODE_RE = re.compile(r"[\"“”]([A-ZÅÄÖ])[\"“”]")
_STANDALONE_CODE_RE = re.compile(r"\b([A-ZÅÄÖ])\b")

# Shape/relationship words, not customer names or a fixed A/B meaning. A
# quoted-letter paragraph must look like a column legend and name at least one
# responsibility role before it can be linked into the prompt.
_LEGEND_SHAPE_TERMS = ("kolumn", "marker")
_RESPONSIBILITY_TERMS = (
    "ansvar",
    "beställar",
    "leverantör",
    "uppdragsgiv",
    "uppdragstag",
    "utförs av",
    "utföres av",
)


def responsibility_legend_codes(text: str) -> frozenset[str]:
    """Return codes only for a paragraph shaped like a responsibility legend."""
    folded = text.casefold()
    if not all(term in folded for term in _LEGEND_SHAPE_TERMS):
        return frozenset()
    if not any(term in folded for term in _RESPONSIBILITY_TERMS):
        return frozenset()
    codes = frozenset(_QUOTED_CODE_RE.findall(text))
    # One quoted letter is too weak: require a real choice/mapping legend.
    return codes if len(codes) >= 2 else frozenset()


def coded_row_uses(text: str, codes: frozenset[str]) -> bool:
    """True only for a leaf table row whose text uses a legend-defined code."""
    if not codes or not _LEAF_ROW_CODE_RE.search(text):
        return False
    return bool(codes & frozenset(_STANDALONE_CODE_RE.findall(text)))


def append_linked_table_legends(
    hits: list[RetrievalHit],
    chunks: dict[str, Chunk],
    documents: dict[str, DocumentMeta],
) -> list[RetrievalHit]:
    """Append at most one required responsibility legend per source document.

    Original hits retain their order and score semantics. Linked context gets
    zero ranking/confidence fields because it did not win retrieval; those
    values are never used for the pre-LLM relevance gate (which is evaluated
    before this function is called). Its provenance is still the real chunk,
    document and page, so citations resolve normally.
    """
    if not hits:
        return hits

    existing_ids = {hit.chunk_id for hit in hits}
    hits_by_document: dict[str, list[RetrievalHit]] = {}
    for hit in hits:
        hits_by_document.setdefault(hit.document_id, []).append(hit)

    additions: list[RetrievalHit] = []
    for document_id, document_hits in hits_by_document.items():
        legends = [
            (chunk, codes)
            for chunk in chunks.values()
            if chunk.document_id == document_id
            and chunk.id not in existing_ids
            and (codes := responsibility_legend_codes(chunk.text))
        ]
        legends.sort(key=lambda item: (item[0].page, item[0].word_start, item[0].id))

        for legend, codes in legends:
            if not any(coded_row_uses(hit.text, codes) for hit in document_hits):
                continue
            doc_meta = documents.get(document_id)
            additions.append(
                RetrievalHit(
                    chunk_id=legend.id,
                    score=0.0,
                    confidence=0.0,
                    bm25=0.0,
                    dense=0.0,
                    document_id=document_id,
                    document_name=doc_meta.name if doc_meta is not None else document_id,
                    page=legend.page,
                    text=legend.text,
                )
            )
            existing_ids.add(legend.id)
            break

    return [*hits, *additions]
