# BRF Grounded Q&A Vertical Slice — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement
> this plan task-by-task (inline execution chosen — tasks share one schema and one session;
> user authorized autonomous push-through). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the mock BRF app real: upload → extract(words+boxes) → chunk → hybrid index →
ask (Swedish) → grounded LLM answer → verified citations → correct PDF highlights → refusals;
then eval harness, failure-mode hardening, wired settings, multi-doc, demo polish, OCR rig.

**Architecture:** FastAPI backend (`backend/`, Python 3.12 via uv) with PyMuPDF extraction,
word-range-provenance chunks, BM25⊕embedding hybrid, pluggable LLM (Anthropic SDK →
`claude -p` CLI fallback), strict quote verification & box resolution. Existing React/Vite
frontend wired to it with a pdf.js viewer + highlight overlays.

**Tech Stack:** Python 3.12 (uv), FastAPI, PyMuPDF (fitz), pytest, httpx; anthropic SDK
(model `claude-opus-4-8`); optional `model2vec` embeddings with pure-Python hashed TF-IDF
fallback; React 19 + Vite 8, pdfjs-dist; oxlint.

## Global Constraints

- Never commit `DONT_PUSH_brf_stuff/`, `wetransfer_hej_2026-07-14_1729*`, `backend/data/`,
  model caches — .gitignore them in Task 0.
- All citation rects: PDF points, **top-left origin** (fitz convention), 1-based page numbers.
- Chunks never cross page boundaries. LLM quotes must come from a single chunk.
- Every §2 failure mode in SPEC.md gets a test that proves detection (not just absence of crash).
- LLM default model `claude-opus-4-8`; adaptive thinking; structured JSON contract identical for
  both providers. Tests use `FakeLLM` — never the network.
- The floor (Tasks 0–13) must be proven with a real run before ceiling work (Tasks 14–19).
- Frontend keeps the existing visual language (glass panels, Swedish copy).
- Commits: small, per task, with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

## Interfaces (source of truth)

```python
# schemas.py (pydantic v2)
Word     = {text: str, x0: float, y0: float, x1: float, y1: float, block: int, line: int}
PageData = {number: int (1-based), width: float, height: float, rotation: int, words: list[Word]}
DocumentMeta = {id: str, name: str, pages: int, chunks: int, words: int, uploaded_at: str}
Chunk    = {id: str, document_id: str, page: int, word_start: int, word_end: int,  # inclusive range into PageData.words
            text: str}
RetrievalHit = {chunk_id: str, score: float, bm25: float, dense: float, document_id: str, page: int, text: str}
CitationOut  = {document_id: str, document_name: str, page: int, quote: str, chunk_id: str,
                rects: list[list[float]], score: float}
RejectedCitation = {chunk_id: str, quote: str, reason: str}  # reasons: quote_not_found | provenance_mismatch | bbox_out_of_bounds | unknown_chunk
AskResponse  = {answer: str, refusal: bool, refusal_reason: str|None,  # low_relevance | insufficient_data | grounding_failed
                warning: str|None, citations: list[CitationOut], rejected_citations: list[RejectedCitation],
                retrieval: list[RetrievalHit], provider: str, model: str}
```

```python
# normalize.py
normalize_token(s: str) -> str            # NFKC, ligatures, soft-hyphen strip, quote/dash fold, casefold, strip punct edges
tokenize_quote(q: str) -> list[str]       # normalize + split; drops empty tokens
match_tokens(words: list[str], quote_tokens: list[str]) -> list[tuple[int, int]]
# returns ALL (start, end_inclusive) word-index spans in `words` matching quote_tokens,
# consuming hyphen-split word pairs ("för-", "valtning") as one token, and matching a
# quote hyphen-pair against a joined source word. Pure, total, tested to death.

# citations.py
resolve_citation(store, chunk_id, quote) -> Resolved | Rejection
# 1. chunk lookup (unknown_chunk) 2. match within chunk word range (all occurrences in chunk ok →
# take first; 0 in chunk: search whole page+doc → provenance_mismatch if found elsewhere,
# quote_not_found otherwise) 3. words → per-(block,line) union rects 4. clamp/validate vs page rect
# (reject bbox_out_of_bounds if center off-page or degenerate)
```

```python
# llm.py — provider contract
class LLMProvider: def complete(self, system: str, user: str, max_tokens: int, model: str) -> str
parse_llm_json(raw) -> {"answer": str, "citations": [{"chunk_id","quote"}], "insufficient_data": bool}
# tolerant: strips code fences, finds first {...} block, validates shape
pick_provider() -> AnthropicProvider if ANTHROPIC_API_KEY else ClaudeCLIProvider
```

Prompt contract (answer.py): system = grounding contract (always) + user-configurable prefix.
Rules: svara på svenska; använd ENDAST utdragen; varje påstående backas av citations;
`quote` = ordagrant sammanhängande utdrag ur ETT chunk, max 40 ord, inga «…»; om utdragen inte
räcker → `insufficient_data: true`. Chunks rendered as `[chunk_id] (Dokument, sida N)\ntext`.

## Tasks

### Floor

- [x] **Task 0 — Housekeeping & baseline.** Extend `.gitignore` (secrets/data/scratch); commit
  the pre-existing WIP UI as a baseline commit; commit SPEC.md + this plan.
- [x] **Task 1 — Backend scaffold.** `backend/pyproject.toml` (uv, py3.12; deps: fastapi,
  uvicorn, pymupdf, pydantic, anthropic, httpx, python-multipart; dev: pytest). `app/main.py`
  with `GET /api/health` → `{status:"ok", llm_provider, embedding_provider}`. CORS for :5173.
  Test: `tests/test_api.py::test_health` (httpx ASGI). Run pytest → green. Commit.
- [x] **Task 2 — normalize.py (TDD).** Tests first: NFKC/ligature (`ﬁn`→`fin`), NBSP/thin-space,
  soft hyphen removal, typographic quotes/dashes fold, casefold, edge punctuation strip,
  `match_tokens` exact, hyphen-merge (`["för-","valtning"]` matches quote `förvaltning`),
  reverse hyphen (source `förvaltning`, quote tokens `för-`+`valtning` — via normalization both
  reduce to same), multiple occurrences returned, no-match → []. Implement minimal. Commit.
- [x] **Task 3 — extract.py (TDD).** Fixture builder `tests/pdf_fixtures.py::build_pdf(pages:
  list[list[tuple[text, x, y]]])` using fitz `insert_text`. Tests: word count, bbox sanity
  (within page, y increases down), block/line ids present, page dims/rotation, Swedish chars
  (åäö) intact. `extract_pdf(bytes) -> list[PageData]`. Commit.
- [x] **Task 4 — chunker.py (TDD).** `chunk_pages(pages, strategy, size, overlap) -> list[Chunk]`
  word-budget based; `fixed` = sliding window w/ overlap; `sentence` = sentence packing
  (split on `[.!?]\s+[A-ZÅÄÖ§]`); `recursive` = block(paragraph)-first packing, splits big
  blocks by sentence. Invariants tested: no chunk crosses pages; word ranges valid + text ==
  join of words; overlap honored; different size ⇒ different chunk count. Commit.
- [x] **Task 5 — embeddings.py + indexer.py (TDD).** `HashedTfidfEmbedder` (char 3–5-gram
  hashing → 512-dim L2-normed, pure python+math, deterministic); optional `Model2VecEmbedder`
  (import-guarded; provider name reported). BM25 with Swedish-aware tokenizer (reuse
  normalize_token). `HybridIndex.search(q, weight, candidates, top_k, min_score)` → min-max
  normalize each retriever over candidates, fuse `w*dense+(1-w)*bm25`. Tests: exact-term query
  ranks right chunk #1 at weight=0; weighting 0 vs 100 changes ranking on crafted corpus;
  min_score filters; candidateCount respected. Commit.
- [x] **Task 6 — citations.py (TDD — the core).** Tests per SPEC §2 using crafted fixture PDFs:
  2.1 fabricated quote → `quote_not_found`; 2.2 quote spanning 2 lines → 2 rects, each within
  its line's y-band; 2.3 across blocks → still matches; 2.5 hyphenated linebreak (`för-`/
  `valtning`) → match incl. both fragments' boxes; 2.6 identical footer on pages 1+2, citation
  cites page-2 chunk → rects on page 2; quote NOT in cited chunk but present on other page →
  `provenance_mismatch`; 2.7 synthetic word with bbox outside page (hand-built store) →
  `bbox_out_of_bounds`; 2.8 quote with NBSP+typographic quotes still matches. Commit.
- [x] **Task 7 — llm.py.** `parse_llm_json` TDD (clean JSON, fenced, prose-wrapped, invalid →
  LLMFormatError). `AnthropicProvider` per claude-api skill (messages.create, adaptive
  thinking, max_tokens from settings). `ClaudeCLIProvider`: `claude -p <prompt> --output-format
  json --model <model>` with timeout, parse `.result`. `FakeLLM(scripted)` for tests.
  Integration smoke test marked `@pytest.mark.llm` (skipped in CI runs). Commit.
- [x] **Task 8 — answer.py + /api/ask (TDD w/ FakeLLM).** Gates: empty index → refusal
  `no_documents`; top score < minRelevance → `low_relevance` (LLM not called — assert);
  FakeLLM insufficient_data → refusal `insufficient_data`; FakeLLM good quote → verified
  citation w/ rects; FakeLLM fabricated quote + requireSources → `grounding_failed` +
  rejected_citations populated; insufficientDataBehavior=warn → answer + warning instead of
  refusal. Commit.
- [x] **Task 9 — store.py + remaining API.** Disk layout `backend/data/{documents.json,
  settings.json, docs/<id>.pdf, extract/<id>.json}`; in-memory index rebuilt on boot &
  re-chunk on settings change (chunk/index knobs). Endpoints: upload (multipart, pdf-only),
  list, pdf, extraction, delete, settings GET/PUT (re-index on relevant change), reset.
  API tests for each incl. settings roundtrip + re-chunk effect visible via extraction. Commit.
- [x] **Task 10 — seed corpus + golden set.** `scripts/seed_content.py`: 5 synthetic Swedish
  docs (Stadgar; Årsredovisning 2025; Styrelseprotokoll 2026-03; Snöröjningsavtal 2026;
  Underhållsplan 2026–2036) for **Brf Gjutformen 12**, multi-page, shared footer boilerplate
  every page. `scripts/seed.py --reset` builds PDFs via fitz (deterministic), uploads through
  the store pipeline, and emits `eval/golden.json`: ≥35 answerable Q→{doc, page, passage,
  golden_rects via `page.search_for`} + ≥8 unanswerable. Test: determinism (two runs → same
  doc ids/chunk counts), golden passages all resolvable. Commit.
- [x] **Task 11 — frontend wiring: api.js, upload, documents.** Vite proxy `/api`→8787.
  Upload modal: real file input → POST, processing overlay driven by real request, error state.
  Documents tab + overview cards read `GET /api/documents`. Commit.
- [x] **Task 12 — frontend: chat + PdfViewer highlights.** Chat calls `/api/ask`; renders
  answer, citation chips `Dokument (sida N)`, refusal style, rejected-citation notice.
  `PdfViewer.jsx`: pdfjs-dist canvas render; highlight overlay divs from rects via viewport
  transform (y-flip → convertToViewportRectangle); prev/next page; opened by citation click
  with that citation's rects. `npm run build` green. Commit.
- [x] **Task 13 — FLOOR PROOF.** Seed; run backend+frontend; through the browser (Chrome MCP or
  Playwright MCP): upload flow visible, ask "Vilken dag startar snöröjningsjouren?" → answer +
  citation → open viewer → screenshot highlight; verify overlay matches passage location
  (compare against `page.search_for` rects programmatically too); ask unanswerable ("Vad
  kostar en parkeringsplats i garaget?" — not in corpus) → refusal screenshot. curl transcript
  of /api/ask saved to `docs/evidence/`. **Report floor to user.** Commit.

### Ceiling (in order, each gated on the previous)

- [x] **Task 14 — Eval harness (item 1).** `scripts/eval.py`: loads golden.json, runs
  retrieval metrics (recall@k) directly against index; full mode drives `/api/ask` in-process
  (real provider) for citation_verification_rate, highlight_correctness (IoU≥0.3 vs golden
  rects), false_answer_rate; `--retrieval-only`; `--settings JSON` overrides; markdown report
  to stdout + `eval/last_run.json`. Gates per SPEC §6. Run full eval → report numbers. Commit.
- [x] **Task 15 — Failure-mode hardening (item 2).** Audit §2 ↔ tests matrix; add adversarial
  eval questions (quotes near duplicated boilerplate, hyphenated passages, multi-line);
  add `tests/test_failure_modes.py` covering any gap; refusal path exercised with all three
  reasons end-to-end. Commit.
- [x] **Task 16 — Settings wiring proof (item 3).** `scripts/eval.py --sweep`: runs eval
  (retrieval-only) across knob grid (weighting 0/50/100; topK 1/5/10; chunkSize 120/400;
  minRelevance 0/0.9) and prints the differing numbers; assert in test that at least
  weighting & topK sweeps produce different metric values. Commit.
- [x] **Task 17 — Multi-document proof (item 4).** Golden set already cross-doc; add eval
  breakdown per document + a `citation_doc_accuracy` metric (cited doc == golden doc);
  UI: verify citations open the right document. Commit.
- [x] **Task 18 — Demo polish (item 5).** `DEMO.md` (scripted flow, exact questions, reset
  instructions, troubleshooting), `Makefile` targets (`make backend`, `make seed`, `make eval`,
  `make demo-reset`), root README section. Runnable-by-Max standard. Commit.
- [x] **Task 19 — OCR spike rig (item 6).** `scripts/ocr_spike.py` per SPEC §5 with
  `TesseractAdapter` (guarded on binary presence) + adapter interface; calibration mode on a
  seeded digital PDF (rasterize→OCR→drift vs fitz truth); overlay PNGs; metrics.json;
  README-OCR notes. Test: adapter interface + calibration on synthetic page when tesseract
  present, else skipped with reason. Commit.
- [ ] **Task 20 — Final review & report.** Full pytest + eval + build; workflow-based
  adversarial code review of the diff; fix confirmed findings; final eval numbers; report.

## Verification commands

```bash
cd backend && uv run pytest -q                      # all unit/API tests
cd backend && uv run python scripts/seed.py --reset # deterministic corpus + golden
cd backend && uv run python scripts/eval.py         # full eval (LLM)
cd backend && uv run python scripts/eval.py --retrieval-only --sweep
cd backend && uv run uvicorn app.main:app --port 8787
npm run dev / npm run build                         # frontend
```
