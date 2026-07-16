"""Pydantic models shared across the backend. Coordinates are PDF points,
top-left origin (PyMuPDF convention); pages are 1-based."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


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
    # "scanned" = ingested via OCR (no text layer found). Existing
    # documents.json entries predate this field and load as "digital" via
    # the default.
    source: Literal["digital", "scanned"] = "digital"


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
    quote: str  # display string; for multi-span citations the joined fragments
    quotes: list[str] = Field(default_factory=list)  # the verified spans (1..MAX_SPANS)
    chunk_id: str
    rects: list[list[float]]  # [[x0, y0, x1, y1], ...] one per text line, union over spans
    score: float
    # True when the cited document's DocumentMeta.source == "scanned": rects
    # come from OCR word boxes, which clip ~9-27% of the time vs. exact on
    # born-digital PDFs (never misplaced — see reality-check evidence). The
    # UI marks the highlight as approximate; verification is unaffected.
    approximate: bool = False


RejectReason = Literal[
    "quote_not_found",
    "provenance_mismatch",
    "bbox_out_of_bounds",
    "unknown_chunk",
    "too_many_spans",
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
    "provider_error",
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
    # Generation — model ids must be plain identifiers (no leading dash:
    # the value is passed as a CLI argument by one provider)
    aiModel: str = Field(default="claude-opus-4-8", pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$")
    systemPrompt: str = ""
    # Answer budget (tokens). The provider's actual max_tokens is larger:
    # citation JSON gets separate headroom on top (see answer.py
    # _CITATION_HEADROOM_TOKENS) so quote-dense answers don't truncate.
    maxResponseLength: int = Field(default=1200, ge=100, le=8000)
    requireSources: bool = True
    insufficientDataBehavior: Literal["refuse", "warn"] = "refuse"
    # Data lifecycle: documents older than this are hard-deleted (0 = keep forever)
    retentionDays: int = Field(default=0, ge=0, le=3650)

    @model_validator(mode="after")
    def _overlap_below_size(self) -> "Settings":
        if self.chunkOverlap >= self.chunkSize:
            raise ValueError("chunkOverlap måste vara mindre än chunkSize")
        return self

    def chunking_signature(self) -> tuple:
        """Knobs whose change requires re-chunk + re-index."""
        return (self.chunkStrategy, self.chunkSize, self.chunkOverlap)
