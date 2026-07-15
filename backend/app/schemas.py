"""Pydantic models shared across the backend. Coordinates are PDF points,
top-left origin (PyMuPDF convention); pages are 1-based."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Word(BaseModel):
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    block: int
    line: int


class PageData(BaseModel):
    number: int  # 1-based
    width: float
    height: float
    rotation: int = 0
    words: list[Word]


class Chunk(BaseModel):
    id: str
    document_id: str
    page: int  # 1-based
    word_start: int  # inclusive index into PageData.words
    word_end: int  # inclusive
    text: str


class DocumentMeta(BaseModel):
    id: str
    name: str
    pages: int
    words: int
    chunks: int
    uploaded_at: str


class RetrievalHit(BaseModel):
    chunk_id: str
    score: float  # fused, min-max normalized over the candidate pool (ranking)
    confidence: float  # absolute 0..1 (IDF-weighted query coverage ⊕ cosine) — refusal gate
    bm25: float
    dense: float
    document_id: str
    document_name: str
    page: int
    text: str


class CitationOut(BaseModel):
    document_id: str
    document_name: str
    page: int
    quote: str
    chunk_id: str
    rects: list[list[float]]  # [[x0, y0, x1, y1], ...] one per text line
    score: float


RejectReason = Literal[
    "quote_not_found",
    "provenance_mismatch",
    "bbox_out_of_bounds",
    "unknown_chunk",
]


class RejectedCitation(BaseModel):
    chunk_id: str
    quote: str
    reason: RejectReason


RefusalReason = Literal[
    "no_documents",
    "low_relevance",
    "insufficient_data",
    "grounding_failed",
]


class AskRequest(BaseModel):
    question: str


class AskResponse(BaseModel):
    answer: str
    refusal: bool = False
    refusal_reason: RefusalReason | None = None
    warning: str | None = None
    citations: list[CitationOut] = Field(default_factory=list)
    rejected_citations: list[RejectedCitation] = Field(default_factory=list)
    retrieval: list[RetrievalHit] = Field(default_factory=list)
    provider: str = ""
    model: str = ""


class Settings(BaseModel):
    # Chunking
    chunkStrategy: Literal["recursive", "fixed", "sentence"] = "recursive"
    chunkSize: int = Field(default=220, ge=20, le=2000)  # words per chunk
    chunkOverlap: int = Field(default=40, ge=0, le=500)  # words
    # Retrieval
    searchWeighting: int = Field(default=50, ge=0, le=100)  # 0=BM25 only, 100=dense only
    candidateCount: int = Field(default=100, ge=1, le=1000)
    topK: int = Field(default=6, ge=1, le=50)
    minRelevance: float = Field(default=0.18, ge=0.0, le=1.0)
    # Generation
    aiModel: str = "claude-opus-4-8"
    systemPrompt: str = ""
    maxResponseLength: int = Field(default=1200, ge=100, le=8000)  # LLM max_tokens
    requireSources: bool = True
    insufficientDataBehavior: Literal["refuse", "warn"] = "refuse"

    def chunking_signature(self) -> tuple:
        """Knobs whose change requires re-chunk + re-index."""
        return (self.chunkStrategy, self.chunkSize, self.chunkOverlap)
