# Evidence — scanned-ingestion end-to-end proof (2026-07-17)

Proves the scanned-ingestion pipeline (OCR → `Store.add_document` → chunk → index → cite) end
to end on the REAL scanned corpus, not just synthetic fixtures. **Redaction policy:** the corpus
contains personal data, so this report is metrics and anonymized slugs only — no names, org
numbers, verbatim passages, or real filenames. Raw artifacts (chunk text, quoted spans, per-page
detail) live in gitignored `backend/out/reality/scanned_ingestion.json` for local review only.

## Method

All 7 real scans in the corpus (63 pages total; the 1 born-digital PDF is skipped by the same
`classify` heuristic `ocr_reality.py` uses). Each scan is ingested into its own throwaway
temp-tenant `Store` through the REAL production path (`Store.add_document` → `app.ocr.ocr_pdf` at
250dpi/swe, conf-gated at 60, chunked, indexed — no bypass). Per document, up to 10 chunks are
sampled (evenly spaced) and a FIXED citation payload is derived directly from that chunk's own
OCR'd text: a single contiguous 6–16-word window, or (alternating) two shorter disjoint windows
from the same chunk. The payload text becomes both the question (guaranteeing its own chunk
ranks in retrieval) and the scripted `FakeLLM` citation — the FULL pipeline
(retrieve → generate → verify → resolve) runs for real, with no live model ever called. Two
independent checks re-derive whether each returned highlight is honest: (a) rect-covered OCR
words match the cited span token-for-token through `app.normalize` (`verify_highlights.py`'s
method, applied to the stored OCR `PageData`); (b) an ink check that the returned rects sit on
dark pixels (`ocr_reality.ink_metrics`'s darkness formula, applied to the citation's own rects).
A final probe corrupts one character of a verified multi-span citation's second span and asserts
the WHOLE citation rejects and the answer refuses.

**Offline discipline:** `BRF_EMBEDDER=hashed`, `BRF_LLM=fake` (explicit `FakeLLM` provider passed
to every `ask()` call — no code path can reach a live model), `scripts.eval.install_network_audit`
active for the whole run. **Measured: 0 connections total, 0 external.**

## Per-document results (all 7 real scans)

| doc (anonymized) | pages | words kept | chunks | blank pages | raw OCR words | conf-gate drop | payloads verified | rect-ink boxes on-ink |
|---|---|---|---|---|---|---|---|---|
| scan-A | 14 | 2 133 | 18 | 0 | 2 254 | 5.4% | 10/10 (5 single/5 multi) | 44/44 |
| scan-B | 3 | 628 | 5 | 0 | 648 | 3.1% | 5/5 (3s/2m) | 11/11 |
| scan-C (30pp, duplex blanks + drawings) | 30 | 3 212 | 27 | **11** | 3 453 | 7.0% | 10/10 (5s/5m) | 27/34 |
| scan-D | 3 | 542 | 5 | 0 | 582 | 6.9% | 5/5 (3s/2m) | 14/14 |
| scan-E | 7 | 1 310 | 8 | 0 | 1 391 | 5.8% | 8/8 (4s/4m) | 35/36 |
| scan-F | 3 | 597 | 4 | 0 | 616 | 3.1% | 4/4 (2s/2m) | 13/13 |
| scan-G | 3 | 1 150 | 7 | 0 | 1 186 | 3.0% | 7/7 (4s/3m) | 24/24 |
| **total** | **63** | **9 572** | **74** | **11** | **10 130** | **5.5%** | **49/49** | **168/176** |

"Conf-gate drop": fraction of raw tesseract word detections at 250dpi dropped by the production
`OCR_MIN_CONF=60` gate (`app/ocr.py`) — a second, independent (ungated) tesseract pass per
document via `TesseractAdapter`, separate from the real ingestion pass. "Blank pages": pages that
survived the gate with zero words (duplex backsides / drawing-only pages) — `Store.add_document`
ingested all of them without failure or exception.

## Condition-2 proof: the 30-page duplex-blank document

scan-C (30 pages, 11 of them blank duplex backsides per the reality report) ingested through
`Store.add_document` without any failure: `DocumentMeta.source == "scanned"`, 27 chunks built
from the 19 non-blank pages, 3 212 words kept. This is the real-data condition-2 proof the
scanned-ingestion MVP was built against.

## Payload verification (acceptance bar: ≥ 0.9)

- **49/49 payloads attempted, considered, and verified — rate 1.0.** 0 chunks skipped as
  too-short, **0 retrieval misses** (every payload's own chunk ranked in the top-K for its own
  text, as designed).
- 26 single-span payloads, 23 multi-span payloads (2 disjoint fragments each) across the corpus.
- **Bar: PASS** (1.0 ≥ 0.9).

## Independent verification (acceptance bar: rects-on-ink ≥ 0.9)

**(a) Rect-vs-quote token check** (independent of `citations.resolve_citation`, re-derived from
the stored OCR `PageData`): 49/49 verdicts land — **48 `exact`, 1 `superset(edge-spill)`, 0
invariant violations, 0 mismatches.** Independent-check rate **1.0**.

**(b) Ink check** (darkness formula applied to each citation's own returned rects): **168/176
rect-boxes on-ink, rate 0.9545 overall — bar PASS** (0.9545 ≥ 0.9). Per-document breakdown is
uneven: 6 of 7 docs are at or near 1.0, but **scan-C (the drawing-heavy 30pp doc) measures
0.7941 (27/34), below the 0.9 bar on its own.** Reported honestly, not smoothed into the
aggregate: this check operates on citation-level line-union rects (may span whitespace between
merged words), a stricter/different sample than the original reality report's per-word-box ink
metric (which measured 0.932 boxes-on-ink for this same document over the full corpus of raw OCR
word boxes, not just cited spans). The gap is plausibly the line-union rect covering more
inter-word gap on a layout with embedded drawings, not a mislocation — no invariant violation was
found on this document (all its citations verified `exact`).

## Approximate flag

**All 49 verified citations have `CitationOut.approximate == True`** (source `"scanned"`) — the
UI-facing marker is set correctly on every scanned-source highlight.

## Corruption probe: the all-or-nothing invariant on real OCR text

18 verified multi-span citations, one per probe, had their second span corrupted by a single
alphabetic-character edit and were re-submitted through the full pipeline (question and alias
unchanged, only the cited quote corrupted). **18/18 (100%) rejected the WHOLE citation and the
answer refused with `grounding_failed`, 0 citations shown** — the all-or-nothing verification
invariant holds on real OCR'd text, not just synthetic fixtures.

## Acceptance bars — summary

| bar | measured | verdict |
|---|---|---|
| payload verification rate ≥ 0.9 | 1.0 (49/49) | **PASS** |
| rects-on-ink ≥ 0.9 (aggregate) | 0.9545 (168/176) | **PASS** |
| blank-page tolerance on the real 30pp doc | 11/11 blank pages ingested, 0 failures | **PASS** |
| conf-gate drop fraction reported per doc | 3.0%–7.0% per doc, 5.5% aggregate | **reported** |
| corruption invariant (all-or-nothing) | 18/18 whole-citation reject + refuse | **PASS** |
| network audit | 0 connections, 0 external | **PASS** |

One sub-finding did NOT clear its own bar in isolation: scan-C's per-document rects-on-ink rate
(0.7941) is below 0.9, masked by the aggregate. See above — reported, not tuned away.

## Suite status after Tasks 1–4

`cd backend && uv run pytest -q` → **238 passed, 1 skipped**
`uv run pytest -q tests/test_isolation.py tests/test_lifecycle.py tests/test_auth.py` → **47 passed**

## Reproduce

`backend/scripts/reality/` (committed, content-free): `scanned_ingestion.py` (this run),
`common.py` (shared helpers: temp-tenant ingestion, payload derivation, alias resolution,
independent checks — reused by Tasks 5–6). Reads the local gitignored corpus folder, writes only
to gitignored `backend/out/reality/`.

    cd backend && BRF_EMBEDDER=hashed uv run python -m scripts.reality.scanned_ingestion

(`--limit N` caps the number of scanned PDFs for fast iteration; the run above covers the full
corpus, no `--limit`.)
