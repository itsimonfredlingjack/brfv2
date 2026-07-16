"""Quote verification and bounding-box resolution (SPEC §2).

A quote is only rendered if it is verbatim-findable (canonical normalization,
hyphenation-aware) *at the cited chunk's location*. Every rejection carries a
reason so failures are observable, never silent.
"""

from __future__ import annotations

from dataclasses import dataclass

from .normalize import find_spans
from .schemas import Chunk, PageData

# Tolerated overflow beyond the page rect before a box is declared invalid.
_EDGE_EPSILON_PT = 3.0


@dataclass
class Resolved:
    page: int
    rects: list[list[float]]  # [[x0, y0, x1, y1], ...] one per text line
    span: tuple[int, int]  # inclusive word indices on the page


@dataclass
class Rejected:
    reason: str  # RejectReason value


def resolve_quote(chunk: Chunk, quote: str, pages_by_doc: dict[str, list[PageData]]) -> Resolved | Rejected:
    pages = pages_by_doc.get(chunk.document_id)
    if not pages or not (1 <= chunk.page <= len(pages)):
        return Rejected(reason="unknown_chunk")
    page = pages[chunk.page - 1]
    words = [w.text for w in page.words]

    spans = find_spans(words, quote)
    chosen = _pick_span(spans, chunk)
    if chosen is None:
        if spans or _found_elsewhere(quote, chunk, pages_by_doc):
            # Verbatim text exists in the corpus — but not where the citation
            # claims (duplicated boilerplate / wrong-occurrence hazard).
            return Rejected(reason="provenance_mismatch")
        return Rejected(reason="quote_not_found")

    rects = _rects_for_span(page, chosen)
    if rects is None:
        return Rejected(reason="bbox_out_of_bounds")
    return Resolved(page=page.number, rects=rects, span=chosen)


def _pick_span(spans: list[tuple[int, int]], chunk: Chunk) -> tuple[int, int] | None:
    """Prefer spans fully inside the chunk's word range. A span straddling the
    chunk boundary is accepted only if at least half of it lies inside the
    range (chunk-boundary quotes); spans mostly or entirely elsewhere on the
    page are rejected (§2.6 wrong-occurrence guard)."""
    contained = [s for s in spans if s[0] >= chunk.word_start and s[1] <= chunk.word_end]
    if contained:
        return contained[0]
    for s in spans:
        overlap = min(s[1], chunk.word_end) - max(s[0], chunk.word_start) + 1
        if overlap > 0 and 2 * overlap >= (s[1] - s[0] + 1):
            return s
    return None


def _found_elsewhere(quote: str, chunk: Chunk, pages_by_doc: dict[str, list[PageData]]) -> bool:
    for pages in pages_by_doc.values():
        for page in pages:
            if find_spans([w.text for w in page.words], quote):
                return True
    return False


def _rects_for_span(page: PageData, span: tuple[int, int]) -> list[list[float]] | None:
    """Union word boxes per (block, line) → one rect per visual text line.
    Returns None if any resulting rect is degenerate or off-page."""
    groups: dict[tuple[int, int], list[float]] = {}
    for w in page.words[span[0] : span[1] + 1]:
        key = (w.block, w.line)
        if key not in groups:
            groups[key] = [w.x0, w.y0, w.x1, w.y1]
        else:
            g = groups[key]
            g[0] = min(g[0], w.x0)
            g[1] = min(g[1], w.y0)
            g[2] = max(g[2], w.x1)
            g[3] = max(g[3], w.y1)

    rects: list[list[float]] = []
    for g in groups.values():
        x0, y0, x1, y1 = g
        if x1 <= x0 or y1 <= y0:
            return None
        if x0 < -_EDGE_EPSILON_PT or y0 < -_EDGE_EPSILON_PT:
            return None
        if x1 > page.width + _EDGE_EPSILON_PT or y1 > page.height + _EDGE_EPSILON_PT:
            return None
        rects.append(
            [
                round(max(0.0, x0), 2),
                round(max(0.0, y0), 2),
                round(min(page.width, x1), 2),
                round(min(page.height, y1), 2),
            ]
        )
    rects.sort(key=lambda r: (r[1], r[0]))
    return rects
