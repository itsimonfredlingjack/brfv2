# Enriched Chunk Representation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Lift true annual-report table rows into topK by embedding an *enriched* representation (document year + section heading prepended) of each chunk, while keeping the frozen chunk text exactly as-is for citation resolution.

**Architecture:** A new pure module `app/enrich.py` derives a per-chunk *search string*. `Chunk` gains an index-only `search_text` field. `HybridIndex.build()` fits BM25 and embeds `c.search_text or c.text`, but `RetrievalHit.text` stays `c.text` (frozen). `Store._rebuild()` computes enrichment (it holds pages + documents) and sets `search_text`. The model never sees the enrichment (`answer.py:_render_excerpts` shows `h.text`), so it can never quote it. An env toggle `BRF_ENRICH` (default on) lets the measurement harness produce a clean baseline arm.

**Tech Stack:** Python 3.12, pydantic v2, `uv`, pytest. Backend under `backend/`, run tests with `cd backend && uv run pytest`.

## Global Constraints

- **The citation invariant is inviolable.** `citations.resolve_quote` verifies against `PageData.words` only; `RetrievalHit.text` MUST stay `chunk.text`; enrichment feeds BM25-fit + embedding ONLY, inside `HybridIndex.build()`. Enrichment text must never be quotable back as document text — proven by test.
- **Graceful degradation:** when no year/heading is confidently found, `search_text` is exactly `chunk.text`. Enrichment can only add a prefix, never alter or drop frozen text.
- **Enrichment default ON** (`BRF_ENRICH` unset ⇒ enabled) — all existing tests run *with* enrichment and must stay green.
- **Measurement embedder pinned to `hashed`** for both arms (isolate enrichment from an embedder swap).
- **Data discipline:** never write real corpus text (chunk text, quotes, filenames) to committed files. Real content goes only to gitignored `backend/out/...`. Committed evidence is metrics-only.
- All suites green before push: backend 390, isolation 48, frontend 63, lint, build. Don't push until green.
- Commit messages end with: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`

---

### Task 1: `Chunk.search_text` field + indexer uses it

**Files:**
- Modify: `backend/app/schemas.py` (Chunk model, ~line 37-43)
- Modify: `backend/app/indexer.py` (`HybridIndex.build`, ~line 87-96)
- Test: `backend/tests/test_indexer.py`

**Interfaces:**
- Produces: `Chunk.search_text: str | None = None` (index-only, not persisted). `HybridIndex.build()` fits/embeds `c.search_text or c.text`; `RetrievalHit.text` stays `c.text`.

- [ ] **Step 1: Write the failing test** — append to `backend/tests/test_indexer.py`:

```python
class TestSearchTextDrivesRankingButNotDisplay:
    def test_search_text_used_for_ranking_display_text_frozen(self):
        # A chunk whose FROZEN text is a bare row, but whose search_text carries
        # a distinctive enrichment term. A query for that term must retrieve it,
        # yet the returned hit.text must be the frozen text (no enrichment leak).
        frozen = "1 234 567"
        chunks = [
            Chunk(id="d1:p1:c0", document_id="d1", page=1, word_start=0, word_end=2,
                  text=frozen, search_text="Zorblecksynized 2099 " + frozen),
            Chunk(id="d1:p1:c1", document_id="d1", page=1, word_start=3, word_end=8,
                  text="föreningen har ett fint hus här", search_text=None),
        ]
        idx = HybridIndex(HashedNgramEmbedder())
        idx.build(chunks, {"d1": "Doc"})
        hits = idx.search("Zorbleckynized", weight=0.5, candidates=10, top_k=1, min_confidence=0.0)
        assert hits[0].chunk_id == "d1:p1:c0"
        assert hits[0].text == frozen  # frozen text returned, NOT the search_text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_indexer.py::TestSearchTextDrivesRankingButNotDisplay -v`
Expected: FAIL — `Chunk` has no `search_text` (pydantic validation error / unexpected keyword).

- [ ] **Step 3: Add the field** — in `backend/app/schemas.py`, inside `class Chunk`, after `text: str`:

```python
    text: str
    # Index-only ENRICHED representation used for BM25 fit + embedding
    # (app/enrich.py, set in Store._rebuild). NEVER shown to the model and
    # NEVER cited: RetrievalHit.text stays `text` (frozen), and verification
    # reads PageData.words. Chunks are rebuilt in memory each boot (not
    # persisted), so this is no disk-format change. None => use `text`.
    search_text: str | None = None
```

- [ ] **Step 4: Use it in the index** — in `backend/app/indexer.py` `HybridIndex.build`, change the two lines that read `c.text`:

```python
    def build(self, chunks: list[Chunk], doc_names: dict[str, str]) -> None:
        self.chunks = list(chunks)
        self.doc_names = dict(doc_names)
        docs = [tokenize(c.search_text or c.text) for c in self.chunks]
        self.bm25.fit(docs)
        self._token_sets = [set(d) for d in docs]
        self._vocab_trigrams = {
            t: _trigrams(t) for t in self.bm25.doc_freq if len(t) >= 5
        }
        self.vectors = self.embedder.embed([c.search_text or c.text for c in self.chunks]) if self.chunks else []
```

(Leave `RetrievalHit(..., text=c.text, ...)` in `search()` exactly as-is — that is the frozen-display guarantee.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_indexer.py -v`
Expected: PASS (new test + all existing indexer tests, incl. `test_hits_carry_document_metadata` which asserts `hit.text == CORPUS[1].text`).

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas.py backend/app/indexer.py backend/tests/test_indexer.py
git commit -m "Add Chunk.search_text: enriched string drives ranking, frozen text stays the display/citation surface

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: `enrich.py` — document year derivation

**Files:**
- Create: `backend/app/enrich.py`
- Test: `backend/tests/test_enrich.py` (create)

**Interfaces:**
- Produces: `document_year(pages: list[PageData], *, scan_pages: int = 3, min_count: int = 2) -> str | None`

- [ ] **Step 1: Write the failing test** — create `backend/tests/test_enrich.py`:

```python
from app.enrich import document_year
from app.schemas import PageData, Word


def _w(text: str, y0: float = 100.0) -> Word:
    return Word(text=text, x0=72.0, y0=y0, x1=120.0, y1=y0 + 11.0, block=1, line=1)


def _page(n: int, tokens: list[str]) -> PageData:
    return PageData(number=n, width=595, height=842, words=[_w(t, 100 + 12 * i) for i, t in enumerate(tokens)])


class TestDocumentYear:
    def test_most_frequent_20xx_token_wins(self):
        pages = [_page(1, ["Årsredovisning", "2025", "för", "räkenskapsåret", "2025"])]
        assert document_year(pages) == "2025"

    def test_stray_single_occurrence_rejected(self):
        # "2072." appears once (a stray amount); real year "2024" appears twice.
        pages = [_page(1, ["2072.", "verksamhetsåret", "2024", "resultat", "2024"])]
        assert document_year(pages) == "2024"

    def test_no_year_returns_none(self):
        pages = [_page(1, ["Föreningen", "förvaltar", "fastigheten"])]
        assert document_year(pages) is None

    def test_only_scans_first_pages(self):
        pages = [_page(1, ["ingen", "siffra", "här"]), _page(2, ["2019", "2019"])]
        assert document_year(pages, scan_pages=1) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_enrich.py::TestDocumentYear -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.enrich'`.

- [ ] **Step 3: Create the module** — `backend/app/enrich.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_enrich.py::TestDocumentYear -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/enrich.py backend/tests/test_enrich.py
git commit -m "enrich: document-year derivation (most-frequent 20XX, count>=2)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: `enrich.py` — section heading detection + carry-forward

**Files:**
- Modify: `backend/app/enrich.py`
- Test: `backend/tests/test_enrich.py`

**Interfaces:**
- Consumes: `PageData`, `Word` from `app.schemas`.
- Produces:
  - `is_heading_line(words: list[Word], page_median_h: float, *, max_words: int = 6, ratio: float = 1.12) -> bool`
  - `document_headings(pages: list[PageData]) -> list[tuple[int, int, str]]` — `(page_number, first_word_index, heading_text)`, sorted reading order.
  - `heading_for(headings: list[tuple[int, int, str]], page: int, word_start: int) -> str | None` — last heading at or before `(page, word_start)`.

- [ ] **Step 1: Write the failing test** — append to `backend/tests/test_enrich.py`:

```python
from app.enrich import document_headings, heading_for, is_heading_line


def _line(text: str, *, y0: float, h: float, block: int, line: int, x0: float = 72.0) -> Word:
    return Word(text=text, x0=x0, y0=y0, x1=x0 + 40, y1=y0 + h, block=block, line=line)


class TestHeadingDetection:
    def test_tall_short_digitfree_line_is_heading(self):
        # median body height 10; a 16-high one-word line stands out.
        body = [_line("löpande", y0=200, h=10, block=2, line=1)]
        heading = [_line("Resultaträkning", y0=100, h=16, block=1, line=1)]
        page = PageData(number=1, width=595, height=842, words=heading + body)
        med = 10.0
        assert is_heading_line(heading, med) is True
        assert is_heading_line(body, med) is False

    def test_line_with_digits_is_not_heading(self):
        # "Not 8 Räntekostnader" carries a digit -> excluded (deferred tier).
        words = [_line("Not", y0=100, h=16, block=1, line=1),
                 _line("8", y0=100, h=16, block=1, line=1, x0=120)]
        assert is_heading_line(words, 10.0) is False

    def test_long_line_is_not_heading(self):
        words = [_line(f"ord{i}", y0=100, h=16, block=1, line=1, x0=72 + 30 * i) for i in range(8)]
        assert is_heading_line(words, 10.0) is False

    def test_headings_carry_forward_across_pages(self):
        p1 = PageData(number=1, width=595, height=842, words=[
            _line("Resultaträkning", y0=100, h=16, block=1, line=1),
            _line("intäkter", y0=200, h=10, block=2, line=1),
        ])
        p2 = PageData(number=2, width=595, height=842, words=[
            _line("kostnad", y0=100, h=10, block=1, line=1),  # no heading here
        ])
        headings = document_headings([p1, p2])
        assert [h[2] for h in headings] == ["Resultaträkning"]
        # a chunk starting on page 2 inherits the last heading seen
        assert heading_for(headings, page=2, word_start=0) == "Resultaträkning"
        # a chunk before the heading gets nothing
        assert heading_for(headings, page=1, word_start=0) == "Resultaträkning"

    def test_heading_words_joined_in_reading_order(self):
        p = PageData(number=1, width=595, height=842, words=[
            _line("Eget", y0=100, h=16, block=1, line=1, x0=72),
            _line("kapital", y0=100, h=16, block=1, line=1, x0=110),
        ])
        headings = document_headings([p])
        assert headings[0][2] == "Eget kapital"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_enrich.py::TestHeadingDetection -v`
Expected: FAIL — names not defined.

- [ ] **Step 3: Implement** — append to `backend/app/enrich.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_enrich.py -v`
Expected: PASS (year + heading suites).

- [ ] **Step 5: Commit**

```bash
git add backend/app/enrich.py backend/tests/test_enrich.py
git commit -m "enrich: section-heading detection (height proxy) + reading-order carry-forward

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: `enrich.py` — search-text builder, orchestration, toggle

**Files:**
- Modify: `backend/app/enrich.py`
- Test: `backend/tests/test_enrich.py`

**Interfaces:**
- Produces:
  - `enrichment_enabled() -> bool` — `os.environ.get("BRF_ENRICH", "1") != "0"`.
  - `build_search_text(chunk_text: str, *, year: str | None, section_heading: str | None) -> str`
  - `chunk_search_texts(chunks: list[Chunk], pages_by_doc: dict[str, list[PageData]]) -> dict[str, str]` — `{chunk_id: search_text}` for all chunks.

- [ ] **Step 1: Write the failing test** — append to `backend/tests/test_enrich.py`:

```python
from app.enrich import build_search_text, chunk_search_texts, enrichment_enabled
from app.schemas import Chunk


class TestBuildSearchText:
    def test_prepends_year_and_heading(self):
        assert build_search_text("1 234", year="2025", section_heading="Resultaträkning") == \
            "2025 Resultaträkning\n1 234"

    def test_degrades_to_identity_when_nothing_found(self):
        assert build_search_text("1 234", year=None, section_heading=None) == "1 234"

    def test_year_only(self):
        assert build_search_text("rad", year="2024", section_heading=None) == "2024\nrad"


class TestChunkSearchTexts:
    def test_each_chunk_gets_year_and_its_section(self):
        p1 = PageData(number=1, width=595, height=842, words=[
            _line("Resultaträkning", y0=100, h=16, block=1, line=1),
            _line("2025", y0=100, h=16, block=1, line=1, x0=200),
            _line("intäkt", y0=200, h=10, block=2, line=1),
        ])
        # year needs count>=2; add a second 2025 within scan window
        p1.words.append(_line("2025", y0=300, h=10, block=3, line=1))
        chunks = [Chunk(id="d1:p1:0", document_id="d1", page=1, word_start=2, word_end=3, text="intäkt 2025")]
        out = chunk_search_texts(chunks, {"d1": [p1]})
        assert out["d1:p1:0"].startswith("2025 Resultaträkning\n")
        assert out["d1:p1:0"].endswith("intäkt 2025")


class TestEnrichmentToggle:
    def test_default_enabled(self, monkeypatch):
        monkeypatch.delenv("BRF_ENRICH", raising=False)
        assert enrichment_enabled() is True

    def test_disabled_when_zero(self, monkeypatch):
        monkeypatch.setenv("BRF_ENRICH", "0")
        assert enrichment_enabled() is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_enrich.py::TestBuildSearchText tests/test_enrich.py::TestChunkSearchTexts tests/test_enrich.py::TestEnrichmentToggle -v`
Expected: FAIL — names not defined.

- [ ] **Step 3: Implement** — append to `backend/app/enrich.py`:

```python
def enrichment_enabled() -> bool:
    """Enrichment is ON by default. Set BRF_ENRICH=0 to disable — used by the
    measurement harness to produce a clean baseline arm and as a safety escape
    hatch. Not a user-facing Settings knob."""
    return os.environ.get("BRF_ENRICH", "1") != "0"


def build_search_text(chunk_text: str, *, year: str | None, section_heading: str | None) -> str:
    prefix = " ".join(p for p in (year, section_heading) if p)
    return f"{prefix}\n{chunk_text}" if prefix else chunk_text


def chunk_search_texts(
    chunks: list[Chunk], pages_by_doc: dict[str, list[PageData]]
) -> dict[str, str]:
    """Per-chunk enriched search string: document year + carried-forward section
    heading, prepended to the frozen chunk text. Degrades to the frozen text."""
    years = {d: document_year(p) for d, p in pages_by_doc.items()}
    headings = {d: document_headings(p) for d, p in pages_by_doc.items()}
    out: dict[str, str] = {}
    for c in chunks:
        heading = heading_for(headings.get(c.document_id, []), c.page, c.word_start)
        out[c.id] = build_search_text(c.text, year=years.get(c.document_id), section_heading=heading)
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_enrich.py -v`
Expected: PASS (all enrich suites).

- [ ] **Step 5: Commit**

```bash
git add backend/app/enrich.py backend/tests/test_enrich.py
git commit -m "enrich: search-text builder + per-chunk orchestration + BRF_ENRICH toggle

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Wire enrichment into `Store._rebuild()`

**Files:**
- Modify: `backend/app/store.py` (`_rebuild`, ~line 243-257; import at top)
- Test: `backend/tests/test_store_enrichment.py` (create)

**Interfaces:**
- Consumes: `chunk_search_texts`, `enrichment_enabled` from `app.enrich`.
- Produces: after `_rebuild`, every chunk in `store.chunks` has `search_text` set (to an enriched string or, on degradation, `None`/frozen text) when enrichment is enabled; index built from those.

**Fixture note (verified empirically):** `build_pdf` hardcodes `fontsize=11`, so height-based heading detection can't fire through the synthetic ingest path. Extend it with an optional 4th tuple element (fontsize). A `fontsize=18` heading extracts at ratio ~1.64× the body median (> the 1.12 threshold). Fixtures MUST order the heading FIRST (word index 0, so the single chunk inherits it via carry-forward) and the year line LAST (so `2025` is never adjacent to the heading — the invariant test in Task 6 depends on `"2025 Resultaträkning"` being non-contiguous in the extracted words).

- [ ] **Step 1: Extend `build_pdf` to support optional per-line font size** — in `backend/tests/pdf_fixtures.py`, replace the inner loop of `build_pdf`:

```python
def build_pdf(pages: list[list[tuple]], page_size=A4) -> bytes:
    """Build a PDF. Each page is a list of (text, x, y) or (text, x, y, fontsize)
    lines; y is the baseline in top-left-origin points, fontsize defaults to 11.
    Returns PDF bytes."""
    doc = fitz.open()
    for lines in pages:
        page = doc.new_page(width=page_size[0], height=page_size[1])
        for line in lines:
            text, x, y = line[0], line[1], line[2]
            fontsize = line[3] if len(line) > 3 else 11
            page.insert_text(fitz.Point(x, y), text, fontsize=fontsize, fontname="helv")
    data = doc.tobytes()
    doc.close()
    return data
```

Run: `cd backend && uv run pytest tests/test_ocr_ingestion.py tests/test_extract.py -q`
Expected: PASS — existing 3-tuple call sites are unaffected (backward compatible).

- [ ] **Step 2: Write the failing test** — create `backend/tests/test_store_enrichment.py`:

```python
"""Enrichment is applied at index-rebuild time (real Store path), and the frozen
display/citation surface is untouched. Synthetic table PDF only (data discipline)."""

from __future__ import annotations

from app.store import Store
from tests.pdf_fixtures import build_pdf


def _table_pdf() -> bytes:
    # Heading FIRST (block/word index 0 -> the single chunk inherits it), taller
    # (fontsize 18) so the height detector fires; year line LAST so "2025" is
    # never adjacent to the heading in the extracted word stream.
    return build_pdf([[
        ("Resultaträkning", 72, 100, 18),
        ("Räntekostnader 1 234 567", 72, 140),
        ("Årsredovisning 2025 räkenskapsåret 2025", 72, 180),
    ]])


class TestStoreEnrichment:
    def test_search_text_set_and_display_text_frozen(self, tmp_path):
        store = Store(data_dir=tmp_path)
        meta = store.add_document("ar.pdf", _table_pdf())
        row = next(c for c in store.chunks.values()
                   if c.document_id == meta.id and "Räntekostnader" in c.text)
        # enriched search string carries year + section heading...
        assert row.search_text is not None
        assert "2025" in row.search_text and "Resultaträkning" in row.search_text
        # ...but the frozen text is unchanged and is what retrieval returns.
        assert row.search_text.endswith(row.text)
        hits = store.index.search("Räntekostnader", weight=0.5, candidates=50,
                                  top_k=10, min_confidence=0.0)
        hit = next(h for h in hits if h.chunk_id == row.id)
        assert hit.text == row.text  # frozen, no enrichment leak

    def test_disabled_toggle_leaves_search_text_none(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BRF_ENRICH", "0")
        store = Store(data_dir=tmp_path)
        meta = store.add_document("ar.pdf", _table_pdf())
        row = next(c for c in store.chunks.values()
                   if c.document_id == meta.id and "Räntekostnader" in c.text)
        assert row.search_text is None
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_store_enrichment.py -v`
Expected: FAIL — `search_text` is `None` even when enabled (wiring absent).

- [ ] **Step 4: Implement** — in `backend/app/store.py`, add import near the other `from .` imports (top of file):

```python
from .enrich import chunk_search_texts, enrichment_enabled
```

Then in `_rebuild`, set `search_text` on the fresh chunks before building the index:

```python
    def _rebuild(self) -> None:
        """Rebuild chunks + index into FRESH objects, then publish by
        reference swap — concurrent readers keep a consistent (old) view."""
        with self.lock:
            s = self.settings
            new_chunks: dict[str, Chunk] = {}
            for doc_id, pages in self.pages.items():
                for c in chunk_pages(doc_id, pages, strategy=s.chunkStrategy, size=s.chunkSize, overlap=s.chunkOverlap):
                    new_chunks[c.id] = c
                if doc_id in self.documents:
                    self.documents[doc_id].chunks = sum(1 for c in new_chunks.values() if c.document_id == doc_id)
            if enrichment_enabled():
                # Enriched search string per chunk (app/enrich.py). Sets the
                # index-only search_text; frozen c.text and PageData.words are
                # untouched, so citation verification is wholly unaffected.
                search_map = chunk_search_texts(list(new_chunks.values()), self.pages)
                for cid, search_text in search_map.items():
                    new_chunks[cid].search_text = search_text
            new_index = HybridIndex(self.index.embedder)
            new_index.build(list(new_chunks.values()), {d.id: d.name for d in self.documents.values()})
            self.chunks = new_chunks
            self.index = new_index
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_store_enrichment.py -v`
Expected: PASS (2 tests).

- [ ] **Step 6: Commit**

```bash
git add backend/app/store.py backend/tests/test_store_enrichment.py backend/tests/pdf_fixtures.py
git commit -m "store: compute + attach enriched search_text at index rebuild (toggle-gated)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: Invariant proof — enrichment-only phrase is NOT citable

**Files:**
- Test: `backend/tests/test_enrich_invariant.py` (create)

**Interfaces:**
- Consumes: `Store`, `app.answer.ask`, `app.llm.FakeLLM`, `citations.resolve_citation`, `tests.pdf_fixtures.build_pdf`, `scripts.reality.common.alias_for_chunk`.

This is the design's load-bearing test: enrichment can move a chunk up in ranking, but a phrase that exists ONLY in the enrichment must fail citation verification, and the model's view is the frozen text.

- [ ] **Step 1: Write the failing test** — create `backend/tests/test_enrich_invariant.py`:

```python
"""The citation invariant under enrichment: enrichment can drive retrieval, but
enrichment text is never citable and the model never sees it. Synthetic only."""

from __future__ import annotations

from app.answer import ask
from app.citations import Rejected, resolve_citation
from app.llm import FakeLLM
from app.store import Store
from scripts.reality import common
from tests.pdf_fixtures import build_pdf


def _pdf() -> bytes:
    # Heading first + tall (detected + carried to the chunk); year line last, so
    # the enrichment prefix "2025 Resultaträkning" is NOT contiguous in the doc.
    return build_pdf([[
        ("Resultaträkning", 72, 100, 18),
        ("Räntekostnader 1 234 567", 72, 140),
        ("Årsredovisning 2025 räkenskapsåret 2025", 72, 180),
    ]])


def _row_chunk(store, doc_id):
    return next(c for c in store.chunks.values()
               if c.document_id == doc_id and "Räntekostnader" in c.text)


class TestEnrichmentNotCitable:
    def test_enrichment_prefix_fails_verification(self, tmp_path):
        store = Store(data_dir=tmp_path)
        meta = store.add_document("ar.pdf", _pdf())
        chunk = _row_chunk(store, meta.id)
        pages = store.pages[meta.id]

        # The enrichment prefix (everything before the frozen text) is a real
        # search string but is NOT contiguous document text.
        prefix = chunk.search_text[: chunk.search_text.rfind(chunk.text)].strip()
        assert prefix and prefix not in chunk.text  # e.g. "2025 Resultaträkning"

        res = resolve_citation(chunk, [prefix], pages)
        assert isinstance(res, Rejected)  # enrichment text cannot be cited

        # And the frozen row text CAN be cited (control) — proving the reject is
        # about provenance, not a broken verifier.
        ok = resolve_citation(chunk, ["Räntekostnader 1 234 567"], pages)
        assert not isinstance(ok, Rejected)

    def test_model_never_sees_enrichment_via_ask(self, tmp_path):
        store = Store(data_dir=tmp_path)
        store.update_settings(store.settings.model_copy(update={"minRelevance": 0.0}))
        meta = store.add_document("ar.pdf", _pdf())
        chunk = _row_chunk(store, meta.id)
        question = "Hur stora var föreningens räntekostnader under året?"
        alias, _hits = common.alias_for_chunk(store, question, chunk.id)
        assert alias is not None

        # Model tries to cite the enrichment prefix -> rejected, answer refused/stripped.
        prefix = chunk.search_text[: chunk.search_text.rfind(chunk.text)].strip()
        fake = FakeLLM([{"answer": "x", "citations": [{"chunk_id": alias, "quote": prefix}],
                         "insufficient_data": False}])
        resp = ask(store, question, provider=fake)
        assert len(resp.citations) == 0
        assert any(r.reason in ("quote_not_found", "provenance_mismatch") for r in resp.rejected_citations)
```

- [ ] **Step 2: Run test to verify it fails or passes**

Run: `cd backend && uv run pytest tests/test_enrich_invariant.py -v`
Expected: PASS immediately (the invariant is structural — Tasks 1 & 5 already guarantee it). If it FAILS, the enrichment leaked into `chunk.text` or `RetrievalHit.text` — STOP and fix the leak before proceeding; this test is the whole point.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_enrich_invariant.py
git commit -m "test: prove enrichment text is not citable and never reaches the model

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: Deterministic retrieval-recovery harness

**Files:**
- Create: `backend/scripts/reality/enrichment_recovery.py`
- Test: `backend/tests/test_enrichment_recovery.py` (create)

**Interfaces:**
- Consumes: `scripts.reality.common` (temp_store, ingest, install_network_audit, assert_zero_connections), `scripts.reality.annual_reports` (QUESTIONS, DEFAULT_DOCS, DEFAULT_FOLDER, doc_slug), `scripts.reality.refusal_buckets` (label_row_occurrences, chunk_contains_occurrence).
- Produces: `true_row_rank(store, doc_id, question, labels) -> int | None` — 1-based rank of the first retrieved chunk (wide search) that CONTAINS an answer-bearing label row; `None` if no answer-bearing occurrence exists at all. And a `main()` that runs all `DEFAULT_DOCS × answerable QUESTIONS`, comparing `topK` containment across arms.

The harness measures the exact lever — true answer row into the window — with NO model, reusing the *authoritative* word-index locator (never a crude label+value heuristic, which false-positives on prose digits).

- [ ] **Step 1: Write the failing test** — create `backend/tests/test_enrichment_recovery.py`:

```python
"""Pin the deterministic rank finder: it must report the rank of the retrieved
chunk that CONTAINS the answer-bearing row (word-index containment), not merely
a chunk on the right page. Synthetic table PDF only."""

from __future__ import annotations

from app.store import Store
from scripts.reality.enrichment_recovery import true_row_rank
from tests.pdf_fixtures import build_pdf


def _doc() -> bytes:
    # Two rows in one small table; only the räntekostnader row is answer-bearing
    # for the interest question.
    return build_pdf([[
        ("Resultaträkning", 72, 100),
        ("Räntekostnader 1 234 567", 72, 140),
        ("Driftskostnader 2 000 000", 72, 180),
    ]])


class TestTrueRowRank:
    def test_finds_rank_of_containing_chunk(self, tmp_path):
        store = Store(data_dir=tmp_path)
        store.update_settings(store.settings.model_copy(update={"minRelevance": 0.0}))
        meta = store.add_document("ar.pdf", _doc())
        rank = true_row_rank(store, meta.id,
                             "Hur stora var föreningens räntekostnader under året?",
                             ["räntekostnader"])
        assert rank == 1  # single chunk contains the answer-bearing row

    def test_none_when_no_answer_bearing_row(self, tmp_path):
        store = Store(data_dir=tmp_path)
        meta = store.add_document("ar.pdf", _doc())
        rank = true_row_rank(store, meta.id, "Vilken är soliditeten?", ["soliditet"])
        assert rank is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_enrichment_recovery.py -v`
Expected: FAIL — module/function missing.

- [ ] **Step 3: Implement** — create `backend/scripts/reality/enrichment_recovery.py`:

```python
"""Deterministic retrieval-recovery measurement for enriched chunk representation.

For every (document, financial question), does the true answer-bearing table row
get retrieved into topK — and at what rank — under baseline vs enriched vs
enriched+rerank? NO model of any kind: the answer-bearing row is located by the
AUTHORITATIVE word-index locator (refusal_buckets.label_row_occurrences +
chunk_contains_occurrence), reused, never a crude label+value string heuristic
(which false-positives on prose digits — see refusal-diagnosis.md).

Arms are selected by the caller's environment, not flags: run once with
BRF_ENRICH=0 (baseline) and once with BRF_ENRICH=1 (enriched); pass --rerank to
add the cross-encoder stage. This is a zero-LLM context — common.assert_zero_
connections enforces it (BRF_EMBEDDER=hashed, no ask()).

Data discipline: real chunk text/filenames only to the gitignored --out JSON;
stdout is metrics only (ranks, counts, page numbers).

Usage (from backend/):
    BRF_ENRICH=0 uv run python -m scripts.reality.enrichment_recovery --out out/reality/enrichment/baseline.json
    BRF_ENRICH=1 uv run python -m scripts.reality.enrichment_recovery --out out/reality/enrichment/enriched.json
    BRF_ENRICH=1 uv run python -m scripts.reality.enrichment_recovery --rerank --out out/reality/enrichment/enriched_rerank.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("BRF_EMBEDDER", "hashed")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("BRF_LLM", "fake")  # never a live model here

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.rerank import rerank_chunks  # noqa: E402
from scripts.reality import common  # noqa: E402
from scripts.reality.annual_reports import (  # noqa: E402
    DEFAULT_DOCS,
    DEFAULT_FOLDER,
    QUESTIONS,
    doc_slug,
)
from scripts.reality.refusal_buckets import (  # noqa: E402
    chunk_contains_occurrence,
    label_row_occurrences,
)

DEFAULT_OUT = Path(__file__).resolve().parent.parent.parent / "out" / "reality" / "enrichment" / "recovery.json"
WIDE_TOP_K = 60  # rank across (almost) all chunks so a miss still reports its rank


def _answer_bearing_occurrences(pages, labels):
    occ = []
    for label in labels:
        occ.extend(o for o in label_row_occurrences(pages, label) if o["answer_bearing"])
    return occ


def true_row_rank(store, doc_id, question, labels, *, rerank: bool = False) -> int | None:
    """1-based rank of the first retrieved chunk that CONTAINS an answer-bearing
    label row. None if the document has no answer-bearing occurrence for these
    labels (question not gradeable on this doc)."""
    s = store.settings
    index, chunks, pages_by_doc, _documents = store.snapshot()
    pages = pages_by_doc[doc_id]
    occ = _answer_bearing_occurrences(pages, labels)
    if not occ:
        return None
    hits = index.search(question, weight=s.searchWeighting / 100.0,
                        candidates=max(s.candidateCount, WIDE_TOP_K),
                        top_k=WIDE_TOP_K, min_confidence=0.0)
    if rerank:
        hits = rerank_chunks(question, hits, WIDE_TOP_K)
    for i, h in enumerate(hits):
        c = chunks[h.chunk_id]
        if any(chunk_contains_occurrence(c, o) for o in occ):
            return i + 1
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--folder", type=Path, default=DEFAULT_FOLDER)
    ap.add_argument("--docs", nargs="+", default=list(DEFAULT_DOCS))
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--top-k", type=int, default=6, help="the production window; a rank <= this is a recovery")
    ap.add_argument("--rerank", action="store_true")
    args = ap.parse_args()

    from app.enrich import enrichment_enabled

    audit_log, allowed = common.install_network_audit()
    print(f"Nätverksrevision aktiv — tillåtna: {sorted(allowed)}", flush=True)
    print(f"enrichment_enabled={enrichment_enabled()} rerank={args.rerank} top_k={args.top_k}", flush=True)

    answerable = [(qid, q, labels) for qid, q, labels in QUESTIONS if labels is not None]
    rows = []
    for rel_doc in args.docs:
        slug = doc_slug(rel_doc)
        with common.temp_store() as store:
            meta = common.ingest(store, args.folder / rel_doc)
            for qid, question, labels in answerable:
                rank = true_row_rank(store, meta.id, question, labels, rerank=args.rerank)
                gradeable = rank is not None
                recovered = gradeable and rank <= args.top_k
                rows.append({"doc": slug, "qid": qid, "rank": rank,
                             "gradeable": gradeable, "in_topk": recovered})
                print(f"  {slug}/{qid}: rank={rank} in_top{args.top_k}={recovered}", flush=True)

    gradeable = [r for r in rows if r["gradeable"]]
    in_topk = [r for r in gradeable if r["in_topk"]]
    summary = {
        "enrichment_enabled": enrichment_enabled(),
        "rerank": args.rerank,
        "top_k": args.top_k,
        "gradeable_cases": len(gradeable),
        "in_topk": len(in_topk),
        "missed": len(gradeable) - len(in_topk),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"rows": rows, "summary": summary}, ensure_ascii=False, indent=2), "utf-8")
    print(f"\nSUMMARY {json.dumps(summary, ensure_ascii=False)}", flush=True)
    print(f"DONE → {args.out}", flush=True)
    common.assert_zero_connections(audit_log)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_enrichment_recovery.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/reality/enrichment_recovery.py backend/tests/test_enrichment_recovery.py
git commit -m "measure: deterministic retrieval-recovery harness (authoritative row locator, no model)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: Regression gate + ingest cost

**Files:** none (verification task). Produces numbers for the evidence doc.

- [ ] **Step 1: Full backend suite (enrichment ON by default)**

Run: `cd backend && uv run pytest -q`
Expected: all pass (was 390 passed / 1 skipped; now higher with the new tests). If any pre-existing test regresses, STOP and fix — enrichment must not break a green suite.

- [ ] **Step 2: Isolation trio**

Run: `cd backend && uv run pytest -q tests/test_isolation.py tests/test_lifecycle.py tests/test_auth.py`
Expected: 48 passed.

- [ ] **Step 3: Synthetic golden — enriched vs baseline (must stay ≥ 0.85, currently 1.000)**

Run:
```bash
cd backend && uv run python -m scripts.eval --retrieval-only
BRF_ENRICH=0 uv run python -m scripts.eval --retrieval-only
```
Expected: both recall@k ≥ 0.85. Record both numbers. If enriched drops below baseline, that is a finding — investigate whether enrichment perturbs synthetic ranking (headings/years firing on seed docs) and tighten thresholds or note it.

- [ ] **Step 4: Tenant-B golden (contracts-style corpus)**

Run: `cd backend && uv run python -m scripts.eval --golden eval/golden_b.json --retrieval-only`
Expected: recall@k ≥ 0.85. Record.

- [ ] **Step 5: Ingest cost — full re-index wall-clock**

Run:
```bash
cd backend && HF_HUB_OFFLINE=1 BRF_EMBEDDER=hashed uv run python - <<'PY'
import time
from pathlib import Path
from scripts.reality import common
FOLDER = Path.home()/"brf-corpus-public"/"brf-annual-reports-2026-07-18"/"sample-ars"
DOCS = ["hsb-perrongen/2024_hsb.pdf","hsb-taltrasten/2025_hsb.pdf","rb-lycksaligheten/2025.pdf","brf-grantorp/2025.pdf"]
for d in DOCS:
    with common.temp_store() as s:
        t=time.perf_counter(); m=common.ingest(s, FOLDER/d); dt=time.perf_counter()-t
        print(f"{d}: pages={m.pages} chunks={m.chunks} ingest+index={dt:.2f}s")
PY
```
Expected: prints per-doc pages/chunks/seconds (ingest includes extract + chunk + enrich + build). Record the totals for the evidence doc — this is the ingest cost.

- [ ] **Step 6: Frontend + lint + build**

Run:
```bash
npm test
npm run lint
npm run build
```
Expected: frontend 63 passed; lint clean; build succeeds. (Frontend is unaffected by this change — it renders `citations`/`retrieval` from the API unchanged — so this is a no-regression check.)

- [ ] **Step 7: Commit any evidence scratch (gitignored) — no code commit needed here.** Proceed to Task 9.

---

### Task 9: Live measurement — 12B pilot (agenntserver)

**Files:** none (measurement). Requires the SSH tunnel to the self-hosted 12B.

This produces the headline end-to-end numbers. `annual_reports.py` is provider-agnostic and already supports `--rerank`; enrichment is on by default via `Store._rebuild`, and `BRF_ENRICH=0` gives the baseline arm.

- [ ] **Step 1: Bring up the tunnel and confirm the model serves**

Run:
```bash
ssh -f -N -L 8000:127.0.0.1:8000 agenntserver
curl -s http://127.0.0.1:8000/v1/models | head -c 400 ; echo
```
Expected: a JSON model list from the llama.cpp server. If the remote is not serving, STOP: report the deterministic Task 7 numbers and flag the live pass as blocked on infra (do not silently fall back to a different model — that muddies attribution).

- [ ] **Step 2: Baseline (enrichment OFF) — reproduce the refusals**

Run:
```bash
cd backend && HF_HUB_OFFLINE=1 BRF_EMBEDDER=hashed BRF_ENRICH=0 \
  BRF_LLM=selfhosted BRF_LLM_BASE_URL=http://127.0.0.1:8000/v1 BRF_LLM_MODEL=<serving-model-id> \
  uv run python -m scripts.reality.annual_reports --out out/reality/enrichment/live_baseline
```
Expected: `summary.questions_refused` reproduces ~13 substantive refusals + 4 controls; audit external=0. Record the refused (doc,qid) set — this is the "13".

- [ ] **Step 3: Enriched (enrichment ON) — NO reranker**

Run:
```bash
cd backend && HF_HUB_OFFLINE=1 BRF_EMBEDDER=hashed BRF_ENRICH=1 \
  BRF_LLM=selfhosted BRF_LLM_BASE_URL=http://127.0.0.1:8000/v1 BRF_LLM_MODEL=<serving-model-id> \
  uv run python -m scripts.reality.annual_reports --out out/reality/enrichment/live_enriched
```
Expected: for each of the 13 baseline refusals, record answered vs refused, and for answered ones `lands_on_label_row` (correct cell) + `independent_verdict`. Count wrong-row answers (`lands_on_label_row=false`). Audit external=0.

- [ ] **Step 4: Enriched + reranker**

Run:
```bash
cd backend && HF_HUB_OFFLINE=1 BRF_EMBEDDER=hashed BRF_ENRICH=1 \
  BRF_LLM=selfhosted BRF_LLM_BASE_URL=http://127.0.0.1:8000/v1 BRF_LLM_MODEL=<serving-model-id> \
  uv run python -m scripts.reality.annual_reports --rerank --out out/reality/enrichment/live_enriched_rerank
```
Expected: same metrics with the cross-encoder stage — this answers "does the reranker add anything worth licensing on top of enrichment?" Requires `uv sync --extra rerank` and cached weights; if unavailable, note it (do not skip silently).

- [ ] **Step 5: Track rb-lycksaligheten q_fund (the one genuine wrong-row / transposed-table case)**

From the three live JSONs, record whether `rb-lycksaligheten/q_fund` is fixed, worsened, or unchanged (it needs a multi-span citation the model declined — likely unchanged; report honestly).

- [ ] **Step 6: Deterministic recovery arms (no model, always runnable)**

Run:
```bash
cd backend
BRF_ENRICH=0 uv run python -m scripts.reality.enrichment_recovery --out out/reality/enrichment/rec_baseline.json
BRF_ENRICH=1 uv run python -m scripts.reality.enrichment_recovery --out out/reality/enrichment/rec_enriched.json
BRF_ENRICH=1 uv run python -m scripts.reality.enrichment_recovery --rerank --out out/reality/enrichment/rec_enriched_rerank.json
```
Expected: three summaries with `in_topk` / `missed` counts. This is the reproducible core, independent of the live model.

---

### Task 10: Evidence doc + memory + finish

**Files:**
- Create: `docs/evidence/enriched-representation.md` (metrics only — data discipline)
- Modify: `NOTES.md` (one-line phase entry, matching existing style)

- [ ] **Step 1: Write `docs/evidence/enriched-representation.md`** — metrics only, covering: the mechanism + invariant (with the proving test named), the deterministic retrieval-recovery table (baseline vs enriched vs enriched+rerank: in_topk of gradeable, per-doc ranks), the live end-to-end table (of the 13: recovered-with-verified-citation-on-correct-cell, wrong-row count, for enriched and enriched+rerank), the ingest cost, the synthetic/contracts regression numbers, and the rb-lycksaligheten verdict. If enrichment did NOT move the number, say so plainly and state the mechanism finding (query terms don't overlap section headings on the hashed embedder). Reproduce commands at the bottom.

- [ ] **Step 2: Commit evidence**

```bash
git add docs/evidence/enriched-representation.md NOTES.md
git commit -m "evidence: enriched-representation recovery measurement + ingest cost

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 3: Final full-suite green check before considering push**

Run: `cd backend && uv run pytest -q && cd .. && npm test && npm run lint && npm run build`
Expected: all green. Only then is the branch push-ready (per task brief; the user decides on push).

- [ ] **Step 4: Update memory** — write/update a project memory noting the enrichment phase outcome (branch, measured recovery number, invariant-intact test name, whether the reranker added anything), linking `[[brfv2-two-branch-state]]`.

---

## Self-Review

**Spec coverage:**
- Enrichment embeds enriched repr, frozen text for citation → Tasks 1, 4, 5 ✓
- Search vs verify separation → Tasks 1, 5; invariant proof → Task 6 ✓
- Enrichment-only phrase fails verification (explicit test) → Task 6 ✓
- Year + section heading scope → Tasks 2, 3, 4 ✓
- Recovery of 13 with/without reranker → Tasks 7 (deterministic), 9 (live) ✓
- Wrong-row answers reported → Task 9 Step 3 ✓
- Full re-index + ingest cost → Task 8 Step 5 ✓
- Synthetic golden + contracts stay green → Task 8 Steps 3-4 ✓
- rb-lycksaligheten tracked → Task 9 Step 5 ✓
- Embedder pinned hashed → harness defaults + Task 8/9 env ✓
- All suites green → Tasks 8, 10 ✓
- Evidence in docs/evidence → Task 10 ✓
- Null result reported plainly → Task 10 Step 1 ✓

**Placeholder scan:** `<serving-model-id>` in Task 9 is a genuine runtime value (the llama.cpp model id from Step 1's `/v1/models`), not a plan placeholder — acceptable. No TODO/TBD.

**Type consistency:** `search_text: str | None` used consistently (schemas, indexer `c.search_text or c.text`, store assignment, enrich returns `dict[str, str]`). `true_row_rank(...) -> int | None`, `chunk_search_texts(...) -> dict[str, str]`, `heading_for(...) -> str | None`, `document_year(...) -> str | None` consistent across tasks.
