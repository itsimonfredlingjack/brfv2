# Evidence — reality check on real BRF documents (2026-07-16)

First contact between the system and real BRF documents. Everything before this ran on
synthetic, born-digital fixtures; this phase fed the pipeline a real corpus and measured what
broke. **Redaction policy:** the corpus contains personal data, so this report contains metrics
and generic descriptors only — no names, no organisation numbers, no verbatim passages, no real
filenames. Raw artifacts (per-question JSON, highlight renders, OCR overlays) live in gitignored
local folders (`backend/out/reality/`, session scratch) for local review only.

## Corpus and method

Eight real PDFs from a local, gitignored folder: **1 born-digital** (a 13-page financial-
management contract with letterhead, prose sections, and appendix task-code tables) and
**7 scans with no text layer** (63 pages: service/management contracts, a parking lease, a
30-page mobility-measure contract with site drawings, a print-shop output). All A4, no page
rotation. This is a contracts corpus — not the protokoll/årsredovisning/stadgar mix the brief
described; findings about table-heavy annual reports remain to be validated when such documents
arrive.

**Offline discipline (every run that touched a real document):** local Ollama `gemma4:e4b` as
the only LLM, embeddings from local cache (`HF_HUB_OFFLINE=1`), and the eval harness's
socket-level network audit active. Measured across the three LLM runs: **1 TCP connection each,
0 external** (a single kept-alive connection to `127.0.0.1:11434`). The OCR rig makes no network
calls at all. Additionally, no raw page images from the corpus were sent through any hosted
model during analysis — all verification below is computational (rects vs embedded text, ink
statistics), reproducible via `backend/scripts/reality/`.

## 1. Born-digital verdict: the pipeline works on real documents — after one real bug

Real board-style questions (10 answerable + 1 unanswerable control) against the born-digital
contract, full pipeline (ingest → retrieve → answer → verify → highlight):

| outcome | count | detail |
|---|---|---|
| Answered, citations verified | **8/10** | incl. 3 citations on appendix table pages |
| Honest refusal (`insufficient_data`) | 2/10 | facts that exist only as table-cell/letterhead fragments (below) |
| Unanswerable control | refused ✅ | `insufficient_data`, no guess |
| False answers | **0** | |
| Rejected citations accepted | 0 | one `quote_not_found` rejection → refusal, correct direction |

**Highlight placement: 6/6 citations land exactly.** Verified computationally: the embedded-text
words covered by the returned rects equal the cited quote token-for-token (through the app's own
canonicalization) — including two multi-line highlights (11 and 7 rects) on a fragment-heavy
appendix table page. Retrieval was never the bottleneck: the correct pages were retrieved on
every question, including the ones that failed downstream.

### The real bug: hidden "thinking" channel ate the whole answer

Initially **4 of 10** answerable questions failed as `provider_error` with the provider's
truncation message ("höj Maximal svarslängd"). That diagnosis was wrong: re-running at
`maxResponseLength` 2400 and 3600 failed identically. Direct probing of the serving stack showed
`finish_reason=length` after ~104 completion tokens with **zero visible content** and a hidden
`reasoning` field — the model (gemma4:e4b, Ollama 0.32.0, capabilities include `thinking`)
entered its reasoning mode on table-heavy excerpts and burned the entire budget invisibly. The
synthetic corpus never triggered thinking, which is why every prior eval was green.

**Fix (applied, tested):** `OpenAICompatProvider` now sends `reasoning_effort: "none"`
(Verified working on Ollama 0.32.0 this session: all four failing questions now answer or refuse
honestly), with a sticky degrade-on-400 for servers that reject the parameter (vLLM behavior:
Spike-item — confirm on the pilot host). The misleading truncation error is replaced by one that
names the reasoning channel when content is empty. Tests: 2 new provider tests; full suite
**181 passed**, isolation **47 passed**, retrieval eval recall@6 1.000.

### The structural finding: fragment facts are unquotable

The two remaining refusals share one cause. Real contracts put key facts in **layout fragments**
— party/letterhead blocks and table columns — where no contiguous 6+-word sentence containing
the fact exists. Measured: 68% of the contract's text lines are ≤2-word fragments; the appendix
table pages yield **zero** quotable 6–16-word sentences; in one refusal the model stitched a
grammatically natural quote whose every word exists in the document but **no contiguous span
does** — the verifier correctly rejected it (`quote_not_found`) and the system refused rather
than fabricate. Safe, but real board questions ("what is the org number", "who is responsible
for X" when X is a table row) become unanswerable under the strict contiguous-quote contract.
This is punch-list #1 for product usefulness on real documents.

## 2. OCR go/no-go on real scans: **conditional GO**

Measured with the tesseract rig (`swe`, 250 dpi primary) over all 7 scans, plus a real-layout
calibration using the born-digital contract (rasterized and OCR'd, embedded text as ground
truth — the previous calibration number came from a clean synthetic fixture and was not reused).

### Per-scan measurements (250 dpi)

| doc (anonymized) | pages | OCR words | conf mean / p10 | boxes on ink | text stability* |
|---|---|---|---|---|---|
| scan A (service contract) | 14 | 2 254 | 91.2 / 90.0 | 0.989 | 0.909 (70/77) |
| scan B (service contract) | 3 | 648 | 92.5 / 90.7 | 0.995 | 1.000 (24/24) |
| scan C (30-p contract w/ drawings) | 30 | 3 453 | 89.7 / 87.8 | 0.932 | 0.974 (114/117) |
| scan D (service contract) | 3 | 582 | 89.8 / 80.4 | 0.985 | 1.000 (20/20) |
| scan E (7-p contract) | 7 | 1 391 | 90.2 / 88.9 | 0.988 | 0.980 (48/49) |
| scan F (parking lease) | 3 | 616 | 93.3 / 92.0 | 0.998 | 0.957 (22/23) |
| scan G (print-shop output) | 3 | 1 186 | 92.5 / 90.2 | 0.996 | 0.977 (43/44) |

\* dual-DPI self-consistency: high-confidence 8-word windows from the 250 dpi read located in the
150 dpi read via the app's own `find_spans` — a correctness proxy (biased toward easy regions;
no human-typed ground truth was taken from scan images, per the data-handling constraint).
"Boxes on ink": fraction of word boxes whose interior is dark against the page background — an
offset/misscaled box fails this.

### Real-layout calibration (born-digital contract, embedded truth)

| dpi | word match | drift p95 (max over pages) | quote findable | highlight lands |
|---|---|---|---|---|
| 250 | 0.885 | **0.236% of page height (~2 pt)** | 10/11 (0.909) | 8/11 (0.727) |
| 150 | 0.859 | 0.242% | 4/4 | 3/4 |

End-to-end fidelity means: a real passage is located in the OCR word stream via `find_spans`
(i.e. the citation verifier would verify it) and the OCR-derived line boxes are compared
geometrically against the embedded-truth boxes. **Every miss was under-coverage (highlight
clipped, precision 0.78–1.0), never misplacement.** The mean-drift statistic (0.5–0.6%) is
inflated by the calibration method itself (repeated common words matched to the wrong instance)
and the per-page p95 is the honest coordinate number.

### Verdict and thresholds

Bars were set against what usable highlighting on these documents requires: boxes on ink ≥0.9,
text stability ≥0.85, drift p95 under one line height (<1% page height), quote findability ≥0.8.
**All pass on all documents.** Recommendation: **GO** for building scanned ingestion, with
conditions that are now measured facts, not guesses:

1. **Confidence gate** (drop words < ~60 conf): at 250 dpi the rig OCRs letterhead graphics and
   table rules into a garbage tail (conf p10 = 11 on the digital render; clean at 150 dpi).
2. **Blank/sparse-page tolerance:** one doc has 11 of 30 pages with zero OCR words (duplex-scan
   backsides) plus site-drawing pages with 21–42 words. Ingestion must skip, not fail.
3. **Expectation setting:** highlight fidelity on scans will be roughly 73–91% (clipped-not-
   misplaced) versus 100% measured on born-digital — the UI should mark scanned-source
   highlights as approximate.
4. Quote verification itself (find + verify a verbatim passage in OCR text) held at 0.91–1.0
   across every measurement — the grounding contract survives OCR on this corpus.

## 3. Stress catalog (honest, tied to pipeline stage)

- **Fragment-table layout** (citation stage): 68% of lines ≤2 words; appendix pages have zero
  quotable sentences; facts in cells/letterheads unciteable → honest refusals. Biggest gap.
- **Hidden reasoning channel** (provider stage): fixed this session; see §1.
- **Blank duplex backsides / drawing pages** (future OCR ingestion): must skip gracefully.
- **Letterhead/graphic OCR garbage** (future OCR ingestion): conf-gate required.
- **Digit-dense content** (citation stage): 20% of words carry digits; digit facts cluster in
  fragments (see q09-class refusals). Table-cell citation would address this too.
- **Hyphenation across line breaks:** nearly absent in the real corpus (1 instance in 13 pages)
  — the synthetic corpus over-weighted this risk; existing merge logic suffices, deprioritize.
- **Multi-column/rotated pages:** none in this corpus (all A4 portrait, rotation 0) — untested,
  keep on the watch list for protokoll/årsredovisning corpora.
- **Reading order on table pages:** no column-scrambling observed — highlights on appendix
  table pages landed exactly; one fidelity passage on the densest table page was clipped
  (coverage 0.67), consistent with line-grouping imprecision, not extraction disorder.

## 4. Punch-list (prioritized)

1. **[DONE this session]** Disable hidden reasoning in the self-hosted provider
   (`reasoning_effort:"none"` + degrade + honest empty-content error). Confirm the parameter on
   the pilot host's serving stack (vLLM: Spike-item).
2. **Fragment-fact citation** — make table-cell/letterhead facts citable: e.g. allow up to N
   short quotes per citation, or a cell-level citation mode (bbox from layout block instead of
   contiguous word span). Unlocks the q03/q09 class of board questions. Design choice — Simon's
   call; touches the grounding contract.
3. **Scanned ingestion MVP** (now justified by the GO): tesseract word boxes → the existing
   `PageData.words`/boxes structures behind the same `add_document` path, with conf-gate,
   blank-page skip, and "approximate highlight" flag on scanned sources. The measured numbers
   above are the acceptance bar for its eval.
4. **Scan-quality gate at upload:** measure (conf distribution, words/page) at ingest; flag or
   reject below-bar scans instead of silently degrading.
5. **Answer-budget semantics:** `maxResponseLength` caps the whole JSON envelope (quotes
   included), so table-dense answers hit it earlier than prose — decouple answer budget from
   envelope budget, or size the default against real-content measurements.
6. **Real-corpus eval set:** build a golden set on real (or realistic) contracts once a
   redaction-safe workflow exists — the synthetic set missed both real failure modes found here.

## Reproduction

`backend/scripts/reality/` (committed, content-free): `digital_reality.py` (pipeline run + audit
+ highlight renders), `verify_highlights.py` (computational rect-vs-quote check),
`ocr_reality.py` (all OCR measurements; documents discovered by glob, anonymized slugs).
All read the local gitignored corpus folder and write only to gitignored/temp locations.
