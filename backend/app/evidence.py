"""Request-scoped evidence accounting for a planned, multi-search answer.

An EvidencePack is the audit trail of ONE ask: what was asked, what the
planner proposed, what actually ran, what came back, and which chunks
survived deduplication to reach the prompt. It is built per request and
thrown away with it — BRF-2 rules out persistent chat memory, and nothing
here is written to disk.

Two invariants this module exists to hold:

1. **Citable identity is never synthesised.** Every chunk that reaches the
   prompt is a real `Chunk` with its real id, so `citations.resolve_citation`
   verifies it against `PageData.words` exactly as it always has. Context
   expansion adds NEIGHBOURING REAL CHUNKS, it does not splice text into an
   existing hit — a spliced hit would let the model quote words outside the
   chunk's own word range, and verification would (correctly) reject it.
2. **Deduplication is recorded, not silent.** The same chunk found by two
   subqueries is kept once, and the pack remembers that it was a repeat and
   which queries found it.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from .schemas import Chunk, RetrievalHit

# How many page-local neighbours may be pulled in around each seed chunk
# (one before, one after). Small on purpose: expansion exists to repair a
# fact split across a chunk boundary, not to widen retrieval by stealth.
CONTEXT_NEIGHBOURS = 1


class ExecutedQuery(BaseModel):
    """One search that actually ran, and what it returned."""

    query: str
    # Which planned subquery this came from (index into the plan), or -1 for
    # a query the application issued itself.
    plan_index: int = -1
    hit_ids: list[str] = Field(default_factory=list)
    # Chunk ids this query returned that were ALREADY in the pack.
    duplicate_ids: list[str] = Field(default_factory=list)


class EvidencePack(BaseModel):
    """Everything one question gathered, in the order it gathered it."""

    question: str
    planned_subqueries: list[str] = Field(default_factory=list)
    executed: list[ExecutedQuery] = Field(default_factory=list)
    # Deduplicated, in first-seen order. These are the citable excerpts.
    hits: list[RetrievalHit] = Field(default_factory=list)
    # Chunk ids added by context expansion rather than by a search.
    expanded_ids: list[str] = Field(default_factory=list)

    # ---------- accounting ----------

    @property
    def chunk_ids(self) -> list[str]:
        return [h.chunk_id for h in self.hits]

    @property
    def document_ids(self) -> list[str]:
        """Distinct source documents, first-seen order — the "cross-document"
        in cross-document intelligence is observable here."""
        seen: list[str] = []
        for h in self.hits:
            if h.document_id not in seen:
                seen.append(h.document_id)
        return seen

    @property
    def document_names(self) -> list[str]:
        seen: dict[str, str] = {}
        for h in self.hits:
            seen.setdefault(h.document_id, h.document_name)
        return list(seen.values())

    @property
    def duplicate_count(self) -> int:
        return sum(len(e.duplicate_ids) for e in self.executed)

    def add_query(self, query: str, hits: list[RetrievalHit], *, plan_index: int = -1) -> ExecutedQuery:
        """Record one executed search, keeping only chunks not already held.

        Ranking within a query is preserved; across queries, first seen wins.
        The duplicate is not discarded quietly — it is named in the record,
        because "both searches independently found this" is evidence.
        """
        known = {h.chunk_id for h in self.hits}
        record = ExecutedQuery(query=query, plan_index=plan_index)
        for h in hits:
            record.hit_ids.append(h.chunk_id)
            if h.chunk_id in known:
                record.duplicate_ids.append(h.chunk_id)
                continue
            known.add(h.chunk_id)
            self.hits.append(h)
        self.executed.append(record)
        return record

    def note_expansion(self, hit: RetrievalHit) -> bool:
        """Add a context-expansion chunk if it is genuinely new."""
        if any(h.chunk_id == hit.chunk_id for h in self.hits):
            return False
        self.hits.append(hit)
        self.expanded_ids.append(hit.chunk_id)
        return True


def _neighbours(seed: Chunk, by_doc_page: dict[tuple[str, int], list[Chunk]]) -> list[Chunk]:
    """Page-local adjacent chunks: same document, same page, nearest word
    ranges either side. Never crosses a page boundary — a citation carries a
    page number, and a "neighbour" on another page is a different location in
    the document, not more of the same passage."""
    siblings = by_doc_page.get((seed.document_id, seed.page), [])
    if len(siblings) < 2:
        return []
    ordered = sorted(siblings, key=lambda c: (c.word_start, c.word_end))
    try:
        pos = next(i for i, c in enumerate(ordered) if c.id == seed.id)
    except StopIteration:
        return []
    lo = max(0, pos - CONTEXT_NEIGHBOURS)
    hi = min(len(ordered), pos + CONTEXT_NEIGHBOURS + 1)
    return [c for c in ordered[lo:hi] if c.id != seed.id]


def expand_context(
    pack: EvidencePack,
    chunks: dict[str, Chunk],
    documents: dict,
    *,
    max_added: int = 4,
) -> int:
    """Pull page-local neighbours of the pack's hits in as first-class hits.

    Each added hit keeps the NEIGHBOUR's own real chunk id, page and document
    — so it is citable and verifiable through the unchanged citation path. It
    carries score/confidence 0.0 because it did not earn a retrieval score;
    that also keeps it out of the relevance gate's `max(confidence)`, which
    must stay a statement about what RETRIEVAL found.

    Returns the number of chunks added. Bounded by `max_added` so a densely
    chunked page cannot flood the prompt.
    """
    by_doc_page: dict[tuple[str, int], list[Chunk]] = {}
    for c in chunks.values():
        by_doc_page.setdefault((c.document_id, c.page), []).append(c)

    added = 0
    # Snapshot the seeds: expansion must not cascade off its own additions.
    seeds = [h.chunk_id for h in pack.hits]
    for chunk_id in seeds:
        if added >= max_added:
            break
        seed = chunks.get(chunk_id)
        if seed is None:
            continue
        for neighbour in _neighbours(seed, by_doc_page):
            if added >= max_added:
                break
            doc_meta = documents.get(neighbour.document_id)
            hit = RetrievalHit(
                chunk_id=neighbour.id,
                score=0.0,
                confidence=0.0,
                bm25=0.0,
                dense=0.0,
                document_id=neighbour.document_id,
                document_name=doc_meta.name if doc_meta is not None else neighbour.document_id,
                page=neighbour.page,
                text=neighbour.text,
            )
            if pack.note_expansion(hit):
                added += 1
    return added
