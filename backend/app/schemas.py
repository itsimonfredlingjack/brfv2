"""Pydantic models shared across the backend. Coordinates are PDF points,
top-left origin (PyMuPDF convention); pages are 1-based."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


# Corpus-isolation guard (CI2): the three document collections that must
# never blend. Origin is a TENANT property (declared once, at creation,
# never inferred from path/filename) — every document inherits its tenant's
# origin at ingestion. See app.registry / app.store for enforcement.
CorpusOrigin = Literal["customer", "public_scraped", "synthetic"]
CORPUS_ORIGINS: tuple[CorpusOrigin, ...] = ("customer", "public_scraped", "synthetic")


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
    # Index-only ENRICHED representation used for BM25 fit + embedding
    # (app/enrich.py, set in Store._rebuild). NEVER shown to the model and
    # NEVER cited: RetrievalHit.text stays `text` (frozen), and verification
    # reads PageData.words. Chunks are rebuilt in memory each boot (not
    # persisted), so this is no disk-format change. None => use `text`.
    search_text: str | None = None


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
    # True when the document still carries less than MIN_WORDS_PER_PAGE words
    # per page after ingestion — it is searchable in name only. Ingested, not
    # rejected, but never silently: the archive list marks it. Documents that
    # predate the field load as False.
    thin: bool = False
    # Pages individually under that threshold. Catches the case the
    # document-level dispatch cannot: a mostly-digital PDF with a handful of
    # scanned pages averages above the threshold and never reaches OCR, so
    # this is the only place those pages show up at all.
    thin_pages: int = 0
    # Corpus-isolation guard (CI2): stamped from the tenant's corpus_origin at
    # ingestion (Store.add_document) — never caller-supplied, never inferred
    # from path/filename. Deliberately NO pydantic default: Store loads raw
    # JSON itself and injects a migrated value for pre-CI2 documents.json
    # entries missing this key (see Store._load_documents) before this model
    # ever validates them, so a bare model load never silently mis-defaults a
    # real tenant's documents to the wrong corpus.
    corpus_origin: CorpusOrigin
    # What the document regulates (parties, amounts, questions it can answer),
    # generated at ingestion / re-OCR by the local model. Not a summary of the
    # text. None on documents that predate the field or when generation was
    # skipped. description_fp is a hash of the extracted page text; a mismatch
    # regenerates the description.
    description: str | None = None
    description_fp: str | None = None


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
    # Cross-encoder relevance score (0..1, pre-normalized by the jina
    # reranker), populated only when Settings.rerankEnabled and this hit
    # survived rerank.rerank_chunks(); None otherwise. Additive — never used
    # to redefine `score`/`confidence` semantics (see answer.py's
    # relevance-gate comment). Lets measurement scripts see both signals.
    rerank_score: float | None = None


class CitationOut(BaseModel):
    document_id: str
    document_name: str
    page: int
    quote: str  # display string; for multi-span citations the joined fragments
    quotes: list[str] = Field(default_factory=list)  # the verified spans (1..MAX_SPANS)
    chunk_id: str
    rects: list[list[float]]  # [[x0, y0, x1, y1], ...] one per text line, union over spans
    # Retrieval path: fused hit score. Full-corpus path: JSON null — 0.0 would
    # read as weak evidence, and the field is required (no default) so a
    # builder cannot forget it.
    score: float | None
    # True when the cited document's DocumentMeta.source == "scanned": rects
    # come from OCR word boxes, which clip ~9-27% of the time vs. exact on
    # born-digital PDFs (never misplaced — see reality-check evidence). The
    # UI marks the highlight as approximate; verification is unaffected.
    approximate: bool = False
    # The cited document's tenant's corpus_origin (additive; CI2 evidence
    # surface) — None only if the citation's document meta was somehow
    # unresolvable (defensive, should not happen in practice).
    corpus_origin: CorpusOrigin | None = None


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
    # A citation quote verified verbatim, but the model's own free-text
    # answer asserted a different number alongside it (SPEC §2.10) — distinct
    # from grounding_failed (no citation verified at all) because here the
    # citation itself is real; only the prose claim is unsupported.
    "numeric_grounding_failed",
]


class AskRequest(BaseModel):
    question: str
    # Opt in to the planned cross-document path (BRF-1, app/multihop.py).
    # Default False = the single-search path, byte-for-byte as before. The
    # field alone is not enough: the server must also have BRF_PLANNED_ASK
    # set, so a client cannot switch on an unreleased path by itself.
    planned: bool = False


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
    # BORTTAGET 2026-08-13: `clarification`, som bar planerarens motfråga.
    # Läget `clarify` finns inte längre (se app/query_plan.py), så fältet hade
    # varit null på varje svar produkten kan ge — ett löfte i wire-kontraktet
    # om något systemet aldrig gör. Ingen konsument läste det: varken
    # brfv2-mockup eller mobilklienten nämner `clarification`.


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
    # Optional extra ceiling on full-corpus prefix_tokens. 0 forces retrieval
    # (before/after on the same commit). None / a positive N are used only when
    # the full-corpus path is opted in (`Store._prefer_full_corpus`); the
    # product default is description-selected document packing. A persisted
    # 32000 (the old default) is migrated to None on load — see Store._load_settings.
    fullCorpusTokenThreshold: int | None = Field(default=None, ge=0)
    # Cross-encoder rerank stage (fix/rerank-financial-tables): retrieve a
    # wide candidate pool, cross-encode each against the query, and pass only
    # the top topK onward — fixes true financial-table answer rows ranking
    # 4-37 among 40-54 hybrid candidates where only the top-6 reaches the
    # prompt. Default OFF: behavior is unchanged everywhere until a
    # deployment opts in (see app/rerank.py).
    rerankEnabled: bool = False
    rerankCandidates: int = Field(default=40, ge=10, le=100)
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
