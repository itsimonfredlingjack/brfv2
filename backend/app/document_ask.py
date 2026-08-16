"""Document-level scoring and packing for the third ask() path."""

from __future__ import annotations

from dataclasses import dataclass

from .schemas import RetrievalHit


@dataclass(frozen=True)
class DocumentScore:
    document_id: str
    document_name: str
    max_score: float
    n_matching_chunks: int


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
