# SPEC — BRF Dokument-AI: Grounded Q&A Vertical Slice

> **Provenance note:** The original SPEC.md was not found on disk at build time (2026-07-16).
> This document is a faithful reconstruction from the build prompt (which quotes §2 and §5),
> `deep-research-report.md` (architecture research), and the canonical frontend.
> Section numbering matches the
> build prompt's references: §2 = failure modes, §5 = OCR spike.

## §0. Product context

Swedish housing co-op (BRF) boards drown in PDFs — stadgar, protokoll, avtal, årsredovisningar.
The product lets a board member upload documents and ask questions in Swedish. Every answer is
**grounded**: it cites exact verbatim passages, each citation is **verified against the source
text**, and the passage is **highlighted at the correct position in the rendered PDF**. If the
documents cannot answer, the system **refuses** instead of guessing.

Single-tenant, local, demo-grade deployment. Multi-tenant, auth, EU hosting hardening, GraphRAG,
and agentic loops are explicitly a later phase.

## §1. The vertical slice (the floor)

End-to-end path, all real (no mocks):

1. **Upload** a digital PDF via the UI → backend extracts per-word text + bounding boxes
   (page, x0, y0, x1, y1 in PDF points, top-left origin) with PyMuPDF.
2. **Chunk** the text (configurable strategy/size/overlap); every chunk records its exact
   word range `(document_id, page, word_start..word_end)` — provenance is word-level.
3. **Index** chunks: hybrid lexical (BM25) + semantic (embedding provider), weighted fusion.
4. **Ask** a Swedish question in the chat UI → top-K retrieval → LLM answers **only** from
   retrieved excerpts and returns structured citations `{chunk_id, quote}` where `quote` is a
   verbatim contiguous excerpt.
5. **Verify** each quote: it must be found (after canonical normalization) inside the cited
   chunk's word range. Failures are rejected, never rendered.
6. **Resolve** verified quotes to bounding boxes: matched word span → one rect per text line →
   rects clamped/validated against the page rect.
7. **Highlight**: the frontend renders the actual PDF page (pdf.js) with overlay rectangles at
   the cited passage; clicking a citation navigates to the right document + page.
8. **Refuse** when retrieval confidence is below threshold or the LLM signals insufficient
   data, per the `insufficientDataBehavior` setting.

**Definition of done (floor):** a real run — seeded documents, a question asked through the UI,
a grounded answer with a highlight that lands on the true passage, and a refusal on an
unanswerable question — captured as evidence (screenshots + API transcripts).

## §2. Failure modes — every one must be detected, with a test proving detection

| # | Failure mode | Required behavior |
|---|---|---|
| 2.1 | **Quote-not-found** — LLM paraphrased, invented, or altered the quote | Citation rejected. If all citations of an answer are rejected and `requireSources` is on, the answer degrades to the refusal path with reason `grounding_failed`. |
| 2.2 | **Span crosses lines** — quote wraps over ≥2 layout lines | Resolves to multiple rects, one per line; all must be returned and rendered. |
| 2.3 | **Span crosses blocks** — quote continues across paragraph/block boundary | Same as 2.2 — matching operates on the page word sequence, not on block-local text. |
| 2.4 | **Span crosses pages** | Chunks never cross page boundaries by construction, and the LLM may only quote from a single chunk; a quote that cannot be matched inside one page's chunk range is rejected. |
| 2.5 | **Hyphenation drift** — source has `för-⏎valtning`, quote has `förvaltning` (or vice versa) | Normalization + hyphen-merge matching must still find the span and include both fragment words' boxes. |
| 2.6 | **Duplicated boilerplate** — identical sentence appears on many pages (headers/footers, standard clauses) | The quote must match **inside the cited chunk's word range**. A quote found elsewhere in the corpus but not in the cited chunk is rejected as `provenance_mismatch` — never silently highlighted at the wrong occurrence. |
| 2.7 | **Out-of-bounds boxes** — resolved rect falls outside the page rect | Rect is invalid → citation rejected with `bbox_out_of_bounds` (defense-in-depth; should be unreachable via 2.1–2.6 checks). |
| 2.8 | **Unicode drift** — NBSP vs space, soft hyphens, typographic quotes/dashes, ligatures (ﬁ), case | Canonical normalization (NFKC + explicit table) applied identically to source words and quotes before matching. |
| 2.9 | **Unanswerable question** | With `insufficientDataBehavior=refuse`: no fabricated answer. Two gates: (a) retrieval gate — top hybrid score < `minRelevance` short-circuits before the LLM; (b) LLM gate — model returns `insufficient_data=true`. Eval measures false-answer rate on an unanswerable golden set; target 0. |
| 2.10 | **Numeric fabrication alongside a valid citation** — the citation quote verifies verbatim (2.1–2.8 all pass), but the model's own free-text `answer` asserts a *different* number than the quote it cites (paraphrase/transposition during generation) | `app/numeric_grounding.py`: every material number in `answer` must equal a number found in the ACCEPTED citations' verified quotes (normalized: NBSP/thin/narrow-NBSP space variants, decimal comma/point, thousands grouping (space- or period-grouped), percent sign or the word "procent"). One repair regeneration is attempted with the specific mismatch named; if still unsupported, refusal `numeric_grounding_failed` — never the unsupported answer. |
| 2.11 | **Numeric false positive from an entity identifier** — 2.10's gate treated a digit inside the tenant's own registered name (e.g. "Brf Gjutformen 12") as an unsupported claim, refusing a true answer solely because the name contains a number (confirmed live against Gemma 4 12B) | `app/numeric_grounding.mask_trusted_spans`: `app/answer.ask()` accepts `trusted_names` (main.py's `/ask` route sources it from `auth.get_tenant(brf_id)` — never client-supplied) plus, per response, the exact `document_name` of citations THAT response actually verified. Only a COMPLETE, exact-span, word-boundary match is masked before number extraction — never a bare digit, never a partial name, never anything from the question text or a rejected citation. A separate, unsupported number elsewhere in the same sentence is unaffected and still refuses. |

## §3. Architecture

```
PDF ──► extract (PyMuPDF: words+boxes) ──► chunk (word ranges) ──► index (BM25 ⊕ embeddings)
                                                                        │
question ──► hybrid retrieve (weight, topK, minRelevance) ──► LLM (structured JSON) ──►
verify quotes (normalize + match in chunk span) ──► resolve boxes (per-line rects) ──►
answer + citations {document_id, page, rects[], quote} ──► pdf.js viewer overlay
```

### Backend (Python 3.12, uv-managed, FastAPI, port 8787)

| Module | Responsibility |
|---|---|
| `app/schemas.py` | Pydantic models: Document, Page, Word, Chunk, Citation, AskRequest/Response, Settings |
| `app/normalize.py` | Canonical normalization + token-level matching primitives (incl. hyphen merge) |
| `app/extract.py` | PyMuPDF → pages, words (text + bbox + block/line ids), page dims/rotation |
| `app/chunker.py` | Strategies: `recursive` (paragraph→sentence packing), `fixed`, `sentence`; size/overlap in tokens(words); never crosses pages |
| `app/embeddings.py` | Pluggable providers: `model2vec` multilingual static embeddings if available, hashed char-n-gram TF-IDF fallback (offline, deterministic) |
| `app/indexer.py` | BM25 (Swedish-aware tokenizer) + dense cosine; min-max-normalized weighted fusion via `searchWeighting` |
| `app/llm.py` | Pluggable: Anthropic SDK (`claude-opus-4-8`, adaptive thinking, JSON contract) when `ANTHROPIC_API_KEY` set; `claude -p` CLI fallback otherwise; `FakeLLM` for tests |
| `app/citations.py` | Quote verification + box resolution + every §2 detection |
| `app/answer.py` | Orchestration incl. both refusal gates and settings application |
| `app/store.py` | Disk persistence under `backend/data/` (uploaded PDFs + extraction JSON + index) |
| `app/main.py` | FastAPI routes |

### API

| Route | Purpose |
|---|---|
| `GET /api/health` | liveness + active providers |
| `POST /api/documents` (multipart) | upload → extract → chunk → index; returns document summary |
| `GET /api/documents` | list |
| `GET /api/documents/{id}/pdf` | raw PDF for the viewer |
| `GET /api/documents/{id}/extraction` | pages, words-per-page counts, chunk map (QA view) |
| `DELETE /api/documents/{id}` | remove |
| `POST /api/ask` `{question}` | full RAG; returns `{answer, refusal, refusal_reason, citations[], retrieval[], rejected_citations[]}` |
| `GET/PUT /api/settings` | live settings (persisted to `backend/data/settings.json`) |
| `POST /api/reset` | wipe + reseed demo corpus |

Citation payload: `{document_id, document_name, page (1-based), quote, chunk_id, rects: [[x0,y0,x1,y1],…] in PDF points (top-left origin), score}`.

### Frontend (existing Vite/React app, made real)

- `brfv2-mockup/src/api.js` — API client; Vite dev proxy `/api` → `:8787`.
- Upload modal → real `POST /api/documents` with progress states.
- Documents tab → real list.
- AI chat → `POST /api/ask`; renders answer + citation chips; refusals rendered distinctly.
- `brfv2-mockup/src/components/PdfPane.jsx` — pdf.js canvas render of the real page + absolutely-positioned
  highlight overlays (fitz top-left rect × viewport scale, y-flip through pdf.js viewport so
  rotation is handled); citation click opens viewer at the right doc/page.

## §4. Settings contract — every knob is real

| Knob (SettingsView) | Backend effect |
|---|---|
| `chunkStrategy` (`recursive`/`fixed`/`sentence`) | chunker algorithm (re-chunk + re-index on change) |
| `chunkSize`, `chunkOverlap` | chunk word budget / overlap |
| `searchWeighting` (0–100) | dense weight in hybrid fusion (0 = pure BM25, 100 = pure semantic) |
| `candidateCount` | candidates fetched per retriever before fusion |
| `topK` | chunks passed to the LLM |
| `minRelevance` (0–1) | retrieval refusal gate threshold |
| `aiModel` | LLM model id passed to provider |
| `maxResponseLength` | LLM max tokens |
| `requireSources` | all-citations-rejected → refusal (2.1) |
| `insufficientDataBehavior` (`refuse`/`warn`) | refusal vs answer-with-warning on low confidence |
| `systemPrompt` | prepended operator guidance (grounding contract is non-negotiable and always appended) |

Changing chunk/index knobs triggers re-chunk/re-index of stored documents. The eval harness must
produce different numbers when knobs move (proof of wiring).

## §5. OCR spike — build the measurement rig, not the decision

Most real BRF PDFs are scans (verified: 7 of 8 sample PDFs have no text layer). The rig
(`backend/scripts/ocr_spike.py`) must, given a PDF:

1. Rasterize each page (PyMuPDF, 200–300 dpi).
2. Run candidate OCR adapters (pluggable): `tesseract` (via `pytesseract`, `swe` language) —
   plus a documented adapter interface where Mistral OCR / others slot in when keys exist.
3. Emit per-page **overlay PNGs** — extracted word boxes drawn on the rasterized page.
4. Compute metrics into `metrics.json`:
   - **Coordinate drift** (calibration mode, digital PDFs only): OCR word boxes vs PyMuPDF
     ground-truth boxes — mean/p95 center drift as % of page height, match rate.
   - **Quote-match rate**: given expected passages (`--passages file`), fraction findable in
     OCR text via the same §2 normalization pipeline.
5. **No go/no-go call.** That decision needs real BRF scans and Simon. The rig makes the spike
   a one-hour exercise when documents arrive.

## §6. Eval harness — one command, run after every significant change

`backend/eval/golden.json`: 30–50 Swedish question→passage pairs over the seeded corpus
(answerable, incl. cross-document + multi-line passages) plus ≥8 unanswerable questions.
Golden passage boxes are computed **independently** of the citation pipeline via
`fitz.Page.search_for` at seed time.

`uv run python scripts/eval.py [--retrieval-only] [--settings overrides.json]` reports:

| Metric | Definition | Gate |
|---|---|---|
| `recall@k` | golden passage's word range overlaps any top-k chunk | ≥ 0.85 @ k=topK |
| `citation_verification_rate` | LLM citations passing §2 verification | ≥ 0.90 |
| `highlight_correctness` | answered questions where a citation rect lands on the golden passage (same doc+page; IoU ≥ 0.30 **or** ≥ 60 % of the citation rect inside the golden rect — shorter-but-correct quotes count) | ≥ 0.90 |
| `false_answer_rate` | unanswerable questions answered instead of refused | = 0.00 |

`--retrieval-only` skips the LLM (fast loop); full mode exercises the LLM provider.

## §7. Seeded demo corpus & demo flow

`backend/scripts/seed.py` deterministically generates realistic **synthetic** Swedish BRF PDFs
(multi-page, real text layers, shared footer boilerplate on every page to exercise 2.6):
Stadgar, Årsredovisning 2025, Styrelseprotokoll mars 2026, Snöröjningsavtal 2026,
Underhållsplan 2026–2036 — for the fictional **Brf Gjutformen 12**. One command resets and
reseeds (`POST /api/reset` / `seed.py --reset`). `DEMO.md` scripts a runnable demo flow that
works without Simon in the room. Real customer PDFs under `DONT_PUSH_brf_stuff/` are never
committed and never part of the seeded corpus.

## §8. Non-goals (this phase)

Multi-tenant + auth, EU production hosting, OCR go/no-go, GraphRAG/multi-hop, agentic loops,
cross-encoder reranking, table-structure extraction. The retrieval/LLM provider seams exist so
the research-recommended EU stack (Qdrant, BGE-M3, Mistral) can replace local components later
without changing the citation contract.
