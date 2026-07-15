"""Chunking strategies over extracted pages.

Invariants: every chunk is a contiguous, inclusive word range within a single
page; chunk.text is exactly the join of those words; chunks never cross page
boundaries (SPEC §2.4 rests on this).
"""

from __future__ import annotations

from .schemas import Chunk, PageData, Word

_ABBREVIATIONS = {"t.ex.", "bl.a.", "s.k.", "m.m.", "m.fl.", "dvs.", "osv.", "ca.", "nr.", "kap.", "st."}
_SENTENCE_END = (".", "!", "?")


def chunk_pages(document_id: str, pages: list[PageData], *, strategy: str, size: int, overlap: int) -> list[Chunk]:
    chunks: list[Chunk] = []
    for page in pages:
        for start, end in _page_ranges(page.words, strategy=strategy, size=size, overlap=overlap):
            text = " ".join(w.text for w in page.words[start : end + 1])
            chunks.append(
                Chunk(
                    id=f"{document_id}:p{page.number}:{start}-{end}",
                    document_id=document_id,
                    page=page.number,
                    word_start=start,
                    word_end=end,
                    text=text,
                )
            )
    return chunks


def _page_ranges(words: list[Word], *, strategy: str, size: int, overlap: int) -> list[tuple[int, int]]:
    n = len(words)
    if n == 0:
        return []
    if strategy == "fixed":
        ranges = _fixed_ranges(0, n - 1, size, overlap)
    elif strategy == "sentence":
        ranges = _pack_units(_sentence_units(words, 0, n - 1), size)
    elif strategy == "recursive":
        units: list[tuple[int, int]] = []
        for lo, hi in _recursive_units(words):
            if hi - lo + 1 > size:
                units.extend(_sentence_units(words, lo, hi))  # sentence-first split
            else:
                units.append((lo, hi))
        ranges = _pack_units(units, size)
    else:
        raise ValueError(f"Okänd chunk-strategi: {strategy}")
    return _apply_overlap(ranges, overlap) if strategy != "fixed" else ranges


def _fixed_ranges(lo: int, hi: int, size: int, overlap: int) -> list[tuple[int, int]]:
    step = max(1, size - overlap)
    ranges = []
    s = lo
    while True:
        e = min(s + size - 1, hi)
        ranges.append((s, e))
        if e >= hi:
            return ranges
        s += step


def _sentence_units(words: list[Word], lo: int, hi: int) -> list[tuple[int, int]]:
    """Split words[lo..hi] into sentence ranges."""
    units = []
    start = lo
    for i in range(lo, hi + 1):
        t = words[i].text
        if t.endswith(_SENTENCE_END) and t.casefold() not in _ABBREVIATIONS:
            nxt = words[i + 1].text if i < hi else None
            if nxt is None or nxt[0].isupper() or nxt[0].isdigit() or nxt[0] in "§ÅÄÖ":
                units.append((start, i))
                start = i + 1
    if start <= hi:
        units.append((start, hi))
    return units


def _recursive_units(words: list[Word]) -> list[tuple[int, int]]:
    """Block (paragraph) ranges; blocks themselves stay whole here and are
    split further during packing if oversized."""
    units: list[tuple[int, int]] = []
    start = 0
    for i in range(1, len(words)):
        if words[i].block != words[start].block:
            units.append((start, i - 1))
            start = i
    units.append((start, len(words) - 1))
    return units


def _pack_units(units: list[tuple[int, int]], size: int) -> list[tuple[int, int]]:
    """Greedily pack adjacent units into ranges of at most `size` words.
    A single unit larger than `size` is split (sentence-first, then fixed)."""
    ranges: list[tuple[int, int]] = []
    cur: tuple[int, int] | None = None
    for lo, hi in units:
        unit_len = hi - lo + 1
        if unit_len > size:
            if cur is not None:
                ranges.append(cur)
                cur = None
            ranges.extend(_split_oversized(lo, hi, size))
            continue
        if cur is None:
            cur = (lo, hi)
        elif (hi - cur[0] + 1) <= size:
            cur = (cur[0], hi)
        else:
            ranges.append(cur)
            cur = (lo, hi)
    if cur is not None:
        ranges.append(cur)
    return ranges


def _split_oversized(lo: int, hi: int, size: int) -> list[tuple[int, int]]:
    return _fixed_ranges(lo, hi, size, 0)


def _apply_overlap(ranges: list[tuple[int, int]], overlap: int) -> list[tuple[int, int]]:
    """Extend each non-first range backwards by up to `overlap` words, keeping
    ranges contiguous slices and guaranteeing forward progress."""
    if overlap <= 0 or len(ranges) <= 1:
        return ranges
    out = [ranges[0]]
    for prev, (s, e) in zip(ranges, ranges[1:]):
        new_s = max(0, s - overlap, prev[0] + 1)
        out.append((min(new_s, s), e))
    return out
