"""Enriched chunk representation for retrieval (search-only, never cited).

Builds a per-chunk SEARCH string = "{document year} {section heading}\\n{frozen
chunk text}" used ONLY for BM25 fit + embedding in HybridIndex.build. The frozen
chunk text is never altered; RetrievalHit.text stays the frozen text and the
model never sees the enrichment (app/answer.py renders h.text). Verification
reads PageData.words and is wholly untouched. When no year/heading is confidently
found, the search string is exactly the frozen text (graceful degradation).

Scope (2026-07-19): document year + section heading. Note-level "table context"
is intentionally deferred (see docs/superpowers/specs/2026-07-19-...).
"""

from __future__ import annotations

import os
import re
import statistics

from .schemas import Chunk, PageData, Word

# Whole-token 20XX (optional trailing punctuation): matches "2025" / "2025." but
# not "2024-2025", "769600-2025", or a date embedded in a longer token.
_YEAR_RE = re.compile(r"^(20\d{2})[.,:;)]?$")


def document_year(pages: list[PageData], *, scan_pages: int = 3, min_count: int = 2) -> str | None:
    """Most frequent standalone 20XX token in the first `scan_pages` pages,
    requiring count >= min_count (filters stray amounts / postcodes)."""
    counts: dict[str, int] = {}
    for page in pages[:scan_pages]:
        for w in page.words:
            for tok in w.text.split():
                m = _YEAR_RE.match(tok.strip())
                if m:
                    counts[m.group(1)] = counts.get(m.group(1), 0) + 1
    if not counts:
        return None
    year, count = max(counts.items(), key=lambda kv: (kv[1], kv[0]))
    return year if count >= min_count else None


def _median_height(words: list[Word]) -> float:
    hs = [w.y1 - w.y0 for w in words]
    return statistics.median(hs) if hs else 0.0


def is_heading_line(words: list[Word], page_median_h: float, *, max_words: int = 6, ratio: float = 1.12) -> bool:
    """A (block, line) group that reads like a section heading: short, digit-free,
    and taller than the page's body text (font-size proxy)."""
    if not words or len(words) > max_words or page_median_h <= 0:
        return False
    if any(any(ch.isdigit() for ch in w.text) for w in words):
        return False
    return _median_height(words) > page_median_h * ratio


def document_headings(pages: list[PageData]) -> list[tuple[int, int, str]]:
    """(page_number, first_word_index, heading_text) for every heading-like line,
    sorted in document reading order."""
    out: list[tuple[int, int, str]] = []
    for page in pages:
        page_median = _median_height(page.words)
        groups: dict[tuple[int, int], list[tuple[int, Word]]] = {}
        for idx, w in enumerate(page.words):
            groups.setdefault((w.block, w.line), []).append((idx, w))
        for entries in groups.values():
            words = [w for _i, w in entries]
            if is_heading_line(words, page_median):
                first_idx = min(i for i, _w in entries)
                ordered = sorted(entries, key=lambda e: e[1].x0)
                text = " ".join(w.text for _i, w in ordered)
                out.append((page.number, first_idx, text))
    out.sort(key=lambda t: (t[0], t[1]))
    return out


def heading_for(headings: list[tuple[int, int, str]], page: int, word_start: int) -> str | None:
    """The last heading at or before (page, word_start) in reading order."""
    chosen: str | None = None
    for pn, idx, text in headings:
        if (pn, idx) <= (page, word_start):
            chosen = text
        else:
            break
    return chosen
