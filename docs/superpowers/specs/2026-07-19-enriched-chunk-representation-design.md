# Design — enriched chunk representation for annual-report retrieval

**Branch:** `feat/enriched-chunk-representation` (off `main` @ 1727977)
**Date:** 2026-07-19
**Status:** design, pending user review

## Problem

The 13 substantive refusals on the real annual-report corpus are all **retrieval
misses at topK=6** (`docs/evidence/refusal-diagnosis.md`): the true answer-bearing
table row sits in a chunk ranked 4–37 of ~40–54 under `hashed` embedding + BM25, so
it never reaches the prompt. Two alternatives are closed by measurement:

- **No rerank-score threshold separates cleanly** (score-gate insufficient).
- **The jina reranker is CC-BY-NC-4.0** — unusable in a product we intend to sell.

The remaining lever is **chunk representation**. This design embeds an *enriched*
representation of each chunk while keeping the frozen chunk text exactly as-is for
citation resolution.

**Honest framing.** Whether year + section-heading enrichment actually lifts the true
rows into topK on the `hashed` embedder is an **open empirical question** — the query
terms ("räntekostnader", "soliditet") do not lexically overlap the section headings
("Resultaträkning", "Flerårsöversikt"), so BM25 may see little gain and the dense
signal only a modest shift. The deliverable is the **measured number**, positive or
null. A null result is a valid, reportable outcome per the task brief ("If enrichment
doesn't move the number, say so plainly").

## The invariant (must not break)

Search against the ENRICHED string; verify quotes against the FROZEN string. The span
map, word indices, bounding boxes, and the entire citation-verification chain must be
untouched. Enrichment text must never be quotable back as document text.

**How the design guarantees this structurally:**

1. `citations.resolve_quote` verifies quotes against `PageData.words` (the extracted
   PDF words) — it never reads `chunk.text` or any enriched string. Untouched.
2. `RetrievalHit.text` stays `chunk.text` (frozen). `answer.py:_render_excerpts` shows
   the model `h.text` — **the model never sees the enrichment**, so it cannot copy it
   into a quote. This is a stronger guarantee than "enrichment happens to not verify":
   the enrichment is not even present in the model's input.
3. The cross-encoder reranker also scores frozen `h.text`.
4. Enrichment feeds BM25 fit + embedding **only**, inside `HybridIndex.build()`.

## Mechanism

### `app/enrich.py` (new, pure)

```
search_text(chunk, page, *, year: str | None, section_heading: str | None) -> str
```

Returns `"{year} {section_heading}\n{chunk.text}"` with whichever of `year` /
`section_heading` were confidently found, else **exactly `chunk.text`** (graceful
degradation — enrichment can only add a prefix, never alter or drop the frozen text).

- **Document year** (per document): the most frequent `20\d{2}` token on the first 3
  pages, requiring count ≥ 2 (filters stray amounts/postcodes like the observed
  `2072.` count-1). Grounded: grantorp→2025 (count 4), perrongen→2024 (count 4).
- **Section heading** (per chunk): the nearest heading-like line at or before the
  chunk's first word, carried forward in document reading order (a note chunk deep in
  "Noter" inherits the last section heading seen). A **heading-like line** is a
  `(block, line)` group that is short (≤ 6 words), digit-free, with median word height
  > 1.12× the page median word height (font-size proxy). Grounded: this detector
  surfaced *Förvaltningsberättelse, Flerårsöversikt, Resultaträkning, Balansräkning,
  Eget kapital* on the correct pages. Note-level headings ("Not 8 …") carry digits and
  are intentionally out of scope (that is the deferred "table context" tier).

Scope is **year + section heading** only (per decision). "+ table/note context" is a
deferred escalation if minimal enrichment under-recovers.

### `schemas.Chunk`

Add index-only field `search_text: str | None = None`. Chunks are rebuilt in memory
each boot from `extract/<id>.json` (store.py) — they are **not** persisted — so this is
no disk-format change and needs no migration. When `None`, consumers fall back to
`text`.

### `indexer.HybridIndex.build()`

Fit BM25 and embed `c.search_text or c.text` instead of `c.text`. `RetrievalHit.text`
stays `c.text`. Signature unchanged (reads the field off the chunk), so existing
callers/tests (`idx.build(chunks, doc_names)`) keep working — a chunk with
`search_text=None` behaves exactly as today.

### `store.Store._rebuild()`

After chunking, compute per-document year and per-chunk section heading (walking pages
in reading order), set `chunk.search_text`, then build the index. `_rebuild` already
holds `self.pages` and `self.documents`, so no new data flow is needed.

## Tests (TDD)

- `test_enrich.py`: year derivation (frequency + threshold, stray-token rejection);
  heading detection (height threshold, digit-free, carry-forward across pages);
  graceful degradation → identity when nothing found.
- **Invariant proof** (`test_citations.py` or `test_enrich.py`): build an enriched
  chunk whose `search_text` contains a year+heading phrase absent from `PageData.words`;
  assert (a) the index retrieves it via an enrichment-only query term, (b) its
  `RetrievalHit.text == chunk.text` (no leak), and (c) feeding the enrichment-only
  phrase as a citation quote yields `Rejected` from `resolve_citation`.
- `test_indexer.py`: `search_text` drives ranking while `hit.text` stays frozen.
- All existing suites stay green (backend 390, isolation 48, frontend 63, lint, build).

## Measurement

Embedder pinned to `hashed` for **both arms** — isolates enrichment from the
embedder-swap lever the task explicitly declined. (A `model2vec` cross-read may be
reported as secondary, clearly labelled as a second variable.)

1. **Primary — deterministic retrieval-recovery (offline, no model).** For each of the
   13 refusal cases, reuse the *authoritative* locator
   (`refusal_buckets.label_row_occurrences` + `chunk_contains_occurrence`) to ask: does
   a retrieved chunk now contain the true answer-bearing row, and at what rank?
   Report **baseline vs enriched vs enriched+rerank**. This is the exact bucket-1
   (retrieval_miss) count the diagnosis used — reproducible, no external dependency, no
   model. A crude label+value heuristic is **not** acceptable (it false-positives on
   prose digits — observed).
2. **Secondary — live end-to-end** via `scripts/reality/annual_reports.py`, network-
   audited, self-hosted **12B pilot** (agenntserver, SSH tunnel to `:8000`). Report
   recoveries with **verified citations landing on the correct cell**
   (`row_landing_verdict`) plus any **wrong-row** answers, enrichment with and without
   the reranker. The tunnel/server must be brought up; if the remote is not serving,
   report the deterministic number and flag the live pass as blocked on infra.

**Guards / tracked cases:**
- Full re-index required; report ingest cost (wall-clock + chunk counts).
- Synthetic golden eval (`make eval` recall ≥ 0.85, currently 1.000) + contracts corpus
  stay green.
- `rb-lycksaligheten q_fund` (the one genuine wrong-row / transposed-table fragment
  case) stays tracked: report whether enrichment fixes, worsens, or leaves it.

## Out of scope

Reranker licensing, multi-span emission, temporal layer, Docling, new features, table/
note-level "context" enrichment (deferred), embedder swap as the primary lever.

## Done when

Enrichment implemented with the citation invariant proven intact by test; recovery
count out of 13 measured with and without the reranker; no regressions; ingest cost
reported; evidence in `docs/evidence/`. If enrichment doesn't move the number, that is
reported plainly. Then stop.
