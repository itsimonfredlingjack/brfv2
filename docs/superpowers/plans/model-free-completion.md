# Plan — model-free completion (branch `feat/model-free-completion`)

Goal: complete and prove everything that does NOT depend on a live model, so the only thing
left to plug in later is the model itself. The generation model does exactly one thing: read
context and emit `quotes[]`. Everything else is deterministic code proven against fixed
citation payloads via the existing scripted provider `FakeLLM` (`backend/app/llm.py:269`).

## Global Constraints (binding for every task)

1. **Zero live-model dependencies.** No code, test, or script added this phase may call a live
   LLM. All new tests/scripts use `FakeLLM` or fixed payloads. `BRF_LLM=fake` and explicit
   `provider=FakeLLM([...])` are the only generation providers exercised.
2. **Real-data discipline.** The real corpus lives in gitignored `DONT_PUSH_brf_stuff/`
   (8 PDFs: 1 born-digital 13pp, 7 scans 63pp). Never commit real documents or content derived
   from them — no names, org numbers, verbatim passages, or real filenames in committed files,
   test fixtures, evidence docs, commit messages, or subagent reports. Committed evidence is
   metrics-only; raw artifacts go to gitignored `backend/out/`. Every run touching real
   documents installs `install_network_audit` (`backend/scripts/eval.py:37`) and must record
   **0 connections** (no LLM at all this phase; use `BRF_EMBEDDER=hashed`).
3. **The verification invariant is untouchable.** A citation reaches the user only if EVERY
   span independently verbatim-verifies at a chunk-local location
   (`citations.resolve_citation`, all-or-nothing; `Resolved` only inside
   `isinstance(res, Resolved)`). No change may weaken, skip, or special-case verification —
   including for OCR text: no fuzzy matching, no confidence-weighted acceptance.
4. **Keep every suite green.** Baseline at branch point 55c8aaa, verified this session:
   `cd backend && uv run pytest -q` → **197 passed, 1 skipped**;
   `uv run pytest -q tests/test_isolation.py tests/test_lifecycle.py tests/test_auth.py`
   → **47 passed**. Retrieval gate: `make eval-fast` (no LLM). Run the relevant suites after
   your change; the full offline + isolation suites must pass before any commit is final.
5. **Compatibility.** Existing `backend/data/tenants/*/documents.json` and
   `extract/*.json` must keep loading — new schema fields need defaults. Old API consumers
   must not break (additive fields only on response models).
6. **Style.** User-facing strings in Swedish matching existing tone; code, comments, and test
   names in English matching existing conventions. No new runtime dependencies for the backend
   beyond what OCR strictly needs (tesseract is invoked as a subprocess, pattern in
   `backend/scripts/ocr_spike.py:65`; PyMuPDF `fitz` is already a dependency).
7. **Git.** Commit on `feat/model-free-completion`; never push; never commit anything under
   `backend/out/`, `backend/data/`, `DONT_PUSH_brf_stuff/`, `wetransfer_*`.

## Task 1 — Envelope-truncation fix (punch-list #5) + regression test

**Problem (measured, `docs/evidence/reality-report.md:163-165`):** `Settings.maxResponseLength`
(`backend/app/schemas.py:124`, default 1200, "LLM max_tokens") is passed straight through as
the provider `max_tokens` (`backend/app/answer.py:115`). The model must emit the WHOLE JSON
envelope — `answer` text plus all `citations[].quote/quotes` JSON — inside that budget, so
quote-dense answers (the q03/q05 class on real documents) truncate: the provider raises the
truncation `LLMError` (`backend/app/llm.py:112-116` Anthropic, `llm.py:192-204` OpenAI-compat),
`ask()` breaks out of its loop (`answer.py:123-125`, no retry for non-format errors) and
returns a generic `provider_error` refusal. The user setting is semantically the ANSWER length,
but it silently caps citations too.

**Fix (in `backend/app/answer.py`, provider-agnostic):**
- Introduce a module constant `_CITATION_HEADROOM_TOKENS` sized for the citation envelope:
  `maxCitations`-like usage is bounded by retrieval `k` (≤6 excerpt aliases) and
  `MAX_SPANS = 4` spans of ≤16 words each (`backend/app/citations.py:25`); ~600 tokens is a
  defensible bound — document the arithmetic in a comment.
- Compute `envelope_budget = s.maxResponseLength + _CITATION_HEADROOM_TOKENS` once and pass it
  as `max_tokens` to `provider.complete(...)`. `maxResponseLength` keeps its user-facing
  meaning (answer budget); the envelope gets headroom for citations.
- Update the truncation `LLMError` messages in `backend/app/llm.py` so they no longer blame the
  user's "Maximal svarslängd" knob incorrectly — the message should state the envelope budget
  that was exceeded (keep Swedish, keep the reasoning-channel special case at `llm.py:197-201`
  intact).
- Update the `Settings.maxResponseLength` field description (`schemas.py:124`) to say it is the
  answer budget and that citation JSON gets separate headroom.

**Regression test (the case that previously truncated), in `backend/tests/test_llm.py` /
`test_answer.py` following the existing monkeypatched-httpx pattern (`test_llm.py:138-159`):**
- Build a fixed envelope payload: a long `answer` plus a multi-quote citation set whose total
  serialized size needs MORE than `maxResponseLength` worth of tokens but LESS than
  `maxResponseLength + _CITATION_HEADROOM_TOKENS`. Use a fake OpenAI-compat handler that
  simulates a server cap: if the request's `max_tokens` < tokens needed → return truncated
  content with `finish_reason: "length"`; else return the full envelope with `finish_reason:
  "stop"`. (Token need computed deterministically inside the handler, e.g. `len(text)//4`.)
- Assert: with the OLD budget semantics (i.e. `max_tokens == maxResponseLength`) this payload
  truncates — encode this as an assertion that the handler WOULD truncate at
  `s.maxResponseLength` (proving the case is the previously-failing one), and that through
  `ask()` with the fix the request carries `max_tokens == s.maxResponseLength +
  _CITATION_HEADROOM_TOKENS`, the envelope parses, citations verify, and the answer is
  returned (no refusal).
- Also assert the truncation path still refuses honestly when even the new budget is exceeded.

**Out of scope:** `ClaudeCLIProvider` cannot detect truncation (no finish_reason surfaces,
`llm.py:259-262`) — do not attempt to fix; leave a one-line comment noting the gap.

## Task 2 — Scanned-ingestion pipeline (OCR → same chain), deterministic and unit-tested

**Problem:** scanned PDFs (no text layer) die at `Store.add_document`
(`backend/app/store.py:127-131`): `extract_pdf` returns zero words → `ValueError` → HTTP 422
(`backend/app/main.py:179-180`). The OCR rig exists only as measurement scripts
(`backend/scripts/ocr_spike.py`), produces `OCRWord` without `block`/`line`, and never touches
the app. Reality report §2 gave OCR a **conditional GO** with measured conditions.

**Build `backend/app/ocr.py`** (new module, deterministic, subprocess-based like
`ocr_spike.py:65` but reading tesseract's structure columns):
- `OCR_MIN_CONF = 60.0` (condition 1, reality report: garbage tail from letterhead graphics
  and table rules OCRs at very low conf; ~60 is the measured gate).
- `parse_tesseract_tsv(tsv: str, dpi: int, *, min_conf: float = OCR_MIN_CONF) -> list[Word]` —
  a PURE function (fully testable without tesseract): parse TSV, keep `level == "5"` word rows
  with non-blank text and `conf >= min_conf`, scale raster px → PDF pt via `72.0/dpi`, and map
  tesseract structure to the app's `Word` (`backend/app/schemas.py:11`): `block = block_num`;
  `line` must be unique per visual text line within a block (tesseract's `line_num` resets per
  paragraph — combine `par_num` and `line_num` deterministically so words on one visual line
  share `(block, line)` and different lines differ; `citations._rects_for_span` groups rects
  by exactly this key, `citations.py:122-135`).
- `ocr_pdf(data: bytes, *, dpi: int = 250, lang: str = "swe", min_conf: float = OCR_MIN_CONF)
  -> list[PageData]` — per page: rasterize via `fitz` `page.get_pixmap(dpi=...)` (pattern
  `ocr_spike.py:104`), invoke `tesseract <png> stdout -l swe --dpi <dpi> tsv` (subprocess, temp
  files in a `tempfile` dir), parse via `parse_tesseract_tsv`. `PageData.width/height` come
  from the PDF page rect (points), `number` 1-based, `rotation` from the page. A page with no
  (surviving) words yields `words=[]` — **never an exception** (condition 2: blank duplex
  backsides and drawing pages must skip, not fail).
- `tesseract_available() -> bool` — `shutil.which` + `swe` in `--list-langs` (pattern
  `ocr_spike.py:57`).

**Wire into `Store.add_document` (`store.py:124`):**
- After `extract_pdf`, if `total_words == 0`: if `tesseract_available()`, run `ocr_pdf` and use
  its pages (document-level dispatch — the no-text-layer case IS the scanned case; mixed
  digital/scanned documents stay out of scope, note in a comment); else raise the existing
  Swedish `ValueError`. If OCR also yields zero words total, raise a Swedish `ValueError`
  saying OCR found no readable text.
- Add `DocumentMeta.source: Literal["digital", "scanned"] = "digital"`
  (`schemas.py:38-44`); the OCR path sets `"scanned"`. Existing `documents.json` files load
  unchanged via the default. The persisted `extract/<id>.json` for a scanned doc is ordinary
  `PageData` — everything downstream (chunker, indexer, citations, highlights) runs the SAME
  code with zero branching.

**Tests (all deterministic, no tesseract binary needed except where marked):**
- `parse_tesseract_tsv`: fixed TSV fixture strings proving (a) conf gate drops low-conf rows,
  (b) blank page → `[]`, (c) px→pt scaling at 250 dpi, (d) `(block, line)` grouping puts
  same-visual-line words together and separates paragraphs with resetting `line_num`,
  (e) non-word rows (level != 5) ignored.
- Dispatch: monkeypatch `ocr_pdf` to return fixed `PageData` → `add_document` on a textless PDF
  (build with `tests/pdf_fixtures.py` helpers or a fitz-rendered image-only PDF) ingests,
  chunks, indexes; `DocumentMeta.source == "scanned"`; blank middle page (words=[]) produces no
  chunks and no failure (`chunker.py:36-37` already returns `[]` — prove it end-to-end).
- Unavailable: monkeypatch `tesseract_available` → False → the existing 422-path `ValueError`.
- Verification chain: with the monkeypatched OCR `PageData`, run `ask()` with
  `FakeLLM([...])` citing a verbatim quote from the OCR text → citation verifies with rects
  (proves OCR words flow through the SAME resolve/highlight chain); and a fabricated quote →
  rejected (invariant holds on OCR-shaped data).
- Real-tesseract integration (marked `@pytest.mark.ocr` + skipif, pattern
  `tests/test_ocr_spike.py`): render a small SYNTHETIC Swedish text to an image-only PDF via
  fitz, `add_document`, assert chunks exist and `source == "scanned"` and a verbatim quote from
  the synthetic text resolves to rects.

## Task 3 — "Approximate highlight" for scanned sources (API + UI), tested

**Reality report condition 3:** highlight fidelity on scans is ~73–91% (clipped, never
misplaced) vs 100% born-digital — the UI must mark scanned-source highlights as approximate.

**Backend:**
- `CitationOut.approximate: bool = False` (`schemas.py:59-67`). In the citation-assembly loop
  in `backend/app/answer.py` (~lines 142-190), set `approximate=True` when the cited document's
  `DocumentMeta.source == "scanned"` (document metadata is reachable from the store snapshot
  already used to resolve `document_name`).
- Tests in `test_answer.py` (FakeLLM): citation on a scanned-source doc (monkeypatched OCR
  pages per Task 2's pattern) → `approximate is True`; citation on a digital doc →
  `approximate is False`.

**Frontend (committed state; there are no frontend tests today — add minimal infra):**
- Citation chips (`src/App.jsx:1312-1326`): when `c.approximate`, render a small amber
  "Ungefärlig markering" affordance on the chip (reuse the `.chat-warning` amber family,
  `src/App.css:1863-1870`; extend `.citation-chip`, `App.css:1824`). Extract the chip into
  `src/components/CitationChip.jsx` so it is testable in isolation; keep markup/behavior
  otherwise identical (`openDocViewer` on click with `{page, rects, highlightPage}` —
  now also pass `approximate`).
- `src/components/PdfViewer.jsx`: accept an `approximate` prop; when true, render highlights
  with a visually distinct "approximate" variant (dashed border / reduced opacity — new CSS
  class in `PdfViewer.css`, e.g. `.pdfviewer-highlight--approximate`) and show a small amber
  note (reuse `.pdfviewer-jump` styling family) saying the marking is approximate because the
  document is scanned ("Inskannat dokument — markeringen är ungefärlig").
- **Test infra:** add `vitest` + `@testing-library/react` + `@testing-library/jest-dom` +
  `jsdom` as devDependencies and a `"test": "vitest run"` script (npm registry access for
  devDependencies is fine — the no-egress rule binds real-document/LLM runs, not tooling).
  Tests: `CitationChip` renders the approximate affordance iff `approximate`; clicking calls
  the handler with `approximate` included. For PdfViewer, extract the overlay-class decision
  into a pure helper (e.g. `highlightClassName(approximate)`) and unit-test it — do NOT try to
  render pdf.js in jsdom. `npm run build` and `npm run lint` must stay green.

## Task 4 — Prove scanned ingestion end-to-end on the REAL scanned corpus (fake provider)

**Deliverable:** a committed, content-free script `backend/scripts/reality/scanned_ingestion.py`
(argparse style/conventions of `digital_reality.py`; default `--folder` =
`DONT_PUSH_brf_stuff/`, default `--out` = `backend/out/reality/`), plus a metrics-only evidence
doc. Create shared helpers in `backend/scripts/reality/common.py` (temp-tenant ingestion,
payload derivation, network audit setup) — Tasks 5 and 6 will reuse them.

**Flow (offline; `install_network_audit` active; `BRF_EMBEDDER=hashed`; NO LLM — assert the
audit log shows 0 connections):**
1. For each scanned PDF in the corpus (skip the born-digital one — classify like
   `ocr_reality.classify`, `scripts/reality/ocr_reality.py:47`): ingest through the REAL path —
   a temp-dir `Store.add_document(name, pdf_bytes)` — recording: pages, pages with zero words
   after the conf gate (blank/drawing pages), words kept, chunks built,
   `DocumentMeta.source == "scanned"`. The 30-page doc with 11 blank duplex backsides must
   ingest without failure (condition-2 proof on real data).
2. Derive FIXED citation payloads from the OCR'd text itself: per document sample up to ~10
   chunks; single-span payloads = a 6–16-word contiguous window of `chunk.text`; multi-span
   payloads = two shorter disjoint windows from the same chunk. (Payloads exist verbatim by
   construction; they are real-document content and must appear ONLY in gitignored output.)
3. For each payload, run the FULL pipeline: `ask(store, question, provider=FakeLLM([...]))`
   where the question is the payload window itself (guarantees retrieval ranks its chunk) and
   the scripted response cites the correct `K`-alias with the quote(s). Record retrieval misses
   honestly (skip, count) rather than bypassing retrieval.
4. Verify and measure: citations returned (verified by construction of the pipeline),
   `approximate == True` on every scanned-source citation, rects non-empty; **independent
   checks**: (a) re-derive the words covered by the returned rects from the stored OCR
   `PageData` and assert they match the cited span token-for-token through
   `app.normalize` (the `verify_highlights.py` method applied to OCR pages); (b) ink check —
   fraction of returned rects whose interior is dark against the page background
   (`ocr_reality.ink_metrics` method) as the geometric no-embedded-truth proxy.
5. Invariant on OCR text: for a sample of multi-span payloads, corrupt one span (single-char
   edit) → the WHOLE citation must reject and the answer must refuse (`grounding_failed`),
   nothing shown.

**Acceptance bars (from the reality report's measured GO):** payload verification rate ≥ 0.9;
rects-on-ink ≥ 0.9; blank-page tolerance proven on the real 30pp doc; conf-gate drop fraction
reported per doc. If a bar fails on real data, REPORT THE NUMBER — do not tune thresholds to
pass.

**Output:** `backend/out/reality/scanned_ingestion.json` (gitignored, full detail) + committed
`docs/evidence/scanned-ingestion.md` (metrics only, redaction policy of
`docs/evidence/reality-report.md`), including the zero-connection audit line and the exact
reproduce command. Also add a `test-summary`-style line to the evidence doc for suite status
after Tasks 1–4.

## Task 5 — Prove the fragment-fact path to the model boundary (real chunks, fixed multi-span payloads)

**Context:** the multi-span mechanism is proven safe (`docs/evidence/multispan-citation.md`),
and the org-number case was shown to resolve once via a throwaway scratch script. Make the
proof committed, rerunnable, and covering the three fragment-fact classes — so the ONLY
remaining gap is "does the model emit these payloads".

**Deliverable:** committed, content-free `backend/scripts/reality/fragment_facts.py` (reuses
`scripts/reality/common.py`), offline, network-audited (0 connections), `BRF_EMBEDDER=hashed`.

**Flow:**
1. Ingest the real born-digital contract through the real path (temp tenant).
2. Three cases, payloads derived at runtime (never committed): **org-number** (locate via
   `\d{6}-\d{4}` regex in page text; spans = [entity-name fragment, org-number token]),
   **party/counterparty name** (letterhead/party-block fragment + a role/label fragment from
   the same chunk), **cell-value** (appendix table row: [row-label fragment, value fragment]).
   Each case: question text from the committed generic board-question set
   (`digital_reality.py:36-49` q03/q09 class); retrieve via the real index; script the
   `FakeLLM` with `{"chunk_id": "<alias of the retrieved chunk>", "quotes": [span1, span2]}`.
3. Assert per case, through full `ask()`: answer returned (no refusal), citation verified with
   `len(rects) >= 2` (multi-rect), `quotes` carries both spans, and the independent
   rect-tokens-vs-span-tokens check (as in Task 4) passes exactly.
4. Invariant: per case, a corrupted variant (one span altered) → whole citation rejected
   (`quote_not_found`/`provenance_mismatch`), answer refuses (`grounding_failed`), nothing
   shown. And a cross-chunk variant (valid spans cited against a DIFFERENT retrieved chunk) →
   `provenance_mismatch`.
5. If a case's fact genuinely cannot be located by the deterministic heuristics (e.g. no table
   row matches), report it as `not_locatable` with the reason — do not fake it.

**Output:** `backend/out/reality/fragment_facts.json` (gitignored) + committed
`docs/evidence/fragment-fact-model-boundary.md` (metrics only): cases resolved N/3, rect
counts, rejection proofs, audit line, and the explicit statement of what remains model-only.

## Task 6 — One-command model-readiness harness

**Deliverable:** `backend/scripts/model_readiness.py` + Makefile target `model-readiness`, so
the future model swap is a one-command validation. Reuses `scripts/reality/common.py`.

**Behavior (`make model-readiness`, default provider = ambient env exactly like
`scripts/eval.py` — `BRF_LLM`/`BRF_LLM_BASE_URL`/`BRF_LLM_MODEL`):**
1. Ingest the real corpus (born-digital always; scans too when tesseract available) into temp
   tenants via the real path.
2. Run a committed, content-free question set: the fragment-fact board questions (org-number,
   party, cell-value classes — reuse the generic Swedish questions from
   `digital_reality.py:36-49`), a couple of prose-answerable controls, and one unanswerable
   control.
3. Per question report: answered/refused, citations emitted, single- vs multi-span
   (`len(c.quotes) > 1`), rejected citations with reasons, `approximate` flags. The
   verification verdict is structural: anything in `citations[]` HAS passed the verifier.
4. Readiness verdict (exit code + table): READY iff every fragment-fact question is answered
   with ≥1 verified citation AND the unanswerable control refuses. Print per-question rows;
   write `backend/out/reality/model_readiness.json`.
5. `--network-audit` flag wired like eval's (auto-set `HF_HUB_OFFLINE=1`); when the provider is
   `selfhosted`, audit and report the connection count.
6. **Self-test proving the harness this phase (no live model):** `--selftest` derives correct
   multi-span payloads from the real chunks (Task 5's derivation) and runs the harness loop
   with `provider=FakeLLM(payloads)` → must print READY, exit 0. `--selftest-negative` scripts
   stitched/fabricated payloads → must print NOT READY, exit 1. Both run with the network
   audit asserting 0 connections. Unit tests cover the verdict logic with fixed inputs.

**Schema unblock (required for "only the model is missing"):** `ANSWER_SCHEMA`
(`backend/app/llm.py:21-38`) still models only single-`quote` citations with
`additionalProperties: False`, so a capable model on the Anthropic structured-output path
COULD NOT emit `quotes[]`. Extend the citation item schema to accept either `quote: str` or
`quotes: array[str] (2..4)` (oneOf or both-optional with a validation note matching
`parse_llm_json`'s leniency, `llm.py:81-85`). Add a unit test that validates fixed single-span
AND multi-span payloads against `ANSWER_SCHEMA` (jsonschema is available via pydantic's
ecosystem; if no validator dep exists, assert the schema dict's structure directly). Leave
`ClaudeCLIProvider`'s no-truncation-detection gap documented (Task 1 comment), nothing more.

**Docs:** short "Model readiness" section in `docs/evidence/model-readiness.md` (metrics only):
what the command does, the fake-provider self-test result from this session (READY plumbing
proven; NOT READY negative proven), and the statement that running it against a candidate
offline model is the deferred next gate.

## Task 7 — Final gate: whole-branch review, suites, evidence coherence, NOTES.md

1. Run and record: full offline suite, isolation suite, `make eval-fast`, frontend
   `npm run build` + `npm run lint` + `npm test` (with `HF_HUB_OFFLINE=1` where relevant).
   All must be green; offline count must be ≥ the 197 baseline plus this phase's new tests.
2. Verify no real-document content leaked into the committed tree
   (`git diff 55c8aaa..HEAD` scanned for org-number patterns, real filenames, corpus text) and
   that `git status` shows no stray artifacts; `backend/out/`, `backend/data/`, corpus folders
   still ignored.
3. Evidence coherence: `docs/evidence/scanned-ingestion.md`,
   `fragment-fact-model-boundary.md`, `model-readiness.md` exist, are metrics-only, name their
   reproduce commands, and their numbers match the actual gitignored run artifacts.
4. NOTES.md: add one entry per real lesson from this phase (envelope-vs-answer budget; OCR
   wiring through the unchanged verification chain; proving to the model boundary with a
   scripted provider), matching the existing entry style (bold dated title, why it mattered).
5. Final whole-branch code review (controller dispatches it — not this task's implementer).
