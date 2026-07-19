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
