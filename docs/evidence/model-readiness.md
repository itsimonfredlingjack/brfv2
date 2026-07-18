# Evidence — one-command model-readiness harness (2026-07-18)

Adds a single command that will validate a candidate generation model against the real corpus
the moment one is available — closing Task 6's "only the model is missing" gap identified in
`docs/evidence/multispan-citation.md` and `docs/evidence/fragment-fact-model-boundary.md`.
**Redaction policy:** the corpus contains personal and business data, so this report is
metrics-only — no names, org numbers, verbatim passages, or real filenames. Raw artifacts (per-
question detail, derived spans) live in gitignored `backend/out/reality/model_readiness.json` for
local review only.

## What the command does

`backend/scripts/model_readiness.py` (`make model-readiness`):

1. Ingests the real corpus through the REAL `Store.add_document` path (`scripts/reality/
   common.py`): the born-digital contract into one temp tenant — the exact configuration Task 5's
   `fragment_facts.py` measured retrievability against — and, separately, the scanned documents
   too when a working tesseract install is detected, each into its OWN throwaway temp tenant as an
   ingestion-only health check (kept out of the Q&A tenant so it cannot dilute retrieval for the
   questions below).
2. Asks a committed, content-free question set through whichever LLM provider the ambient
   environment picks — exactly `scripts/eval.py`'s own default (`BRF_LLM`/`BRF_LLM_BASE_URL`/
   `BRF_LLM_MODEL`, `pick_provider()`): three fragment-fact board questions (org-number/party/
   cell-value classes, Task 5's measured qid mapping), two prose-answerable controls, and one
   unanswerable control — all reused from `scripts/reality/digital_reality.py`'s already-committed
   generic Swedish questions, not duplicated.
3. Reports, per question: answered/refused (+ reason), verified citations emitted, single- vs
   multi-span (`len(c.quotes) > 1`), rejected citations with reasons, and the `approximate` flag.
   The verdict here is purely STRUCTURAL — anything counted in `resp.citations` has already passed
   `citations.resolve_citation` (all-or-nothing); the harness does not re-verify.
4. Prints a per-question table and a READY/NOT READY verdict with exit code (0/1), and writes
   `backend/out/reality/model_readiness.json`. **READY iff every fragment-fact question is
   answered with ≥1 verified citation AND the unanswerable control refuses** — computed by a pure,
   unit-tested function (`compute_verdict`) independent of any real corpus or LLM.
5. `--network-audit`, wired exactly like `scripts/eval.py`'s own flag (auto-sets
   `HF_HUB_OFFLINE=1`, installs the same connect()-auditing hook, reports total/external
   connection counts); a non-empty external count fails the verdict.
6. `--selftest` / `--selftest-negative`: score the harness itself with a scripted `FakeLLM` — no
   live model is ever called by this repo's own tests or CI this phase. Both install the network
   audit unconditionally and hard-fail (`common.assert_zero_connections`) if the log is non-empty
   at all.

## Schema unblock: ANSWER_SCHEMA now accepts multi-span citations

`ANSWER_SCHEMA` (`backend/app/llm.py`) previously modeled only single-`quote` citations with
`additionalProperties: False`, so a capable model on the Anthropic structured-output path could
not have emitted `quotes[]` even if it tried. The citation item schema is now additive-only:
`chunk_id` remains the only unconditionally required field; `quote: string` (unchanged) or
`quotes: array[string]` (2–4 items, matching `citations.MAX_SPANS`) are both accepted via a
two-branch `oneOf`, so a citation carries exactly one of the two forms — matching the model-facing
contract (`GROUNDING_CONTRACT`, `app/answer.py`) and `parse_llm_json`'s existing leniency
(`llm.py:81-85`). `AnthropicProvider` is the only consumer of this schema.
13 new unit tests (`tests/test_llm.py::TestAnswerSchemaCitationItem`) pin the schema's structure
directly and validate fixed single-span and multi-span payloads against it — `jsonschema` is not a
project dependency (confirmed not importable), so validation uses a small hand-rolled structural
checker scoped to exactly this schema fragment's keywords, per the task's fallback instruction,
rather than adding a dependency. `ClaudeCLIProvider`'s no-truncation-detection gap remains
documented, unchanged (Task 1).

## Self-test results (this session — no live model)

Both self-tests ran against the full real corpus (1 born-digital document ingested into the Q&A
tenant; all 7 real scans ingested successfully into their own throwaway tenants as the smoke
check) with `BRF_EMBEDDER=hashed` and an explicit scripted `FakeLLM` — zero live-model calls.

**`--selftest` (correct, real-chunk-derived multi-span payloads for all three fragment classes):**

| qid | class | status | citations | multi-span | rejected |
|---|---|---|---|---|---|
| q09 (org_number) | fragment | answered | 1 | 1 | — |
| q08 (party_name) | fragment | answered | 1 | 1 | — |
| q03 (cell_value) | fragment | answered | 1 | 1 | — |
| q01 | prose | answered | 1 | 0 | — |
| q02 | prose | answered | 1 | 0 | — |
| q11 | unanswerable | refused (insufficient_data) | 0 | 0 | — |

**VERDICT: READY — exit code 0.** Network audit: 0 connections, 0 external.

**`--selftest-negative` (one span of each fragment-fact citation corrupted by a single-character
edit — Task 5's `common.corrupt_span` corruption-probe technique, chosen over a literal
quote-stitch fabrication because whether two real fragments sit textually adjacent in the source
varies per occurrence, so a stitch is not a reliably-breaking negative signal on every real case):**

| qid | class | status | citations | rejected |
|---|---|---|---|---|
| q09 (org_number) | fragment | refused (grounding_failed) | 0 | quote_not_found |
| q08 (party_name) | fragment | refused (grounding_failed) | 0 | quote_not_found |
| q03 (cell_value) | fragment | refused (grounding_failed) | 0 | quote_not_found |
| q01 | prose | answered | 1 | — |
| q02 | prose | answered | 1 | — |
| q11 | unanswerable | refused (insufficient_data) | 0 | — |

**VERDICT: NOT READY — exit code 1**, with the three fragment questions listed as the reasons
(prose controls, unaffected by the corruption, still pass — confirming the verdict logic isolates
the fragment-fact gate correctly rather than failing wholesale). Network audit: 0 connections, 0
external.

Both runs are reproducible via `make model-readiness-selftest` / `make model-readiness-selftest-
negative`, and are the harness's own proof this phase — plumbing verified end to end (real
ingestion → real retrieval → scripted generation → real verification → real verdict computation),
without depending on any live model.

## What remains: the deferred next gate

This harness makes the eventual model swap a one-command validation, but **running it against a
live candidate model is deliberately out of scope this phase** (global constraint: zero
live-model dependencies — every test/script this phase uses `FakeLLM` or fixed payloads). The two
self-tests prove the harness's own mechanics are correct; they do not and cannot show whether any
particular candidate model will emit verified fragment-fact citations on the real documents.
`docs/evidence/multispan-citation.md` already measured this for one model (`gemma4:e4b`: zero
`quotes` citations across multiple prompts/budgets, stitches instead — correctly rejected). The
next gate is: point `BRF_LLM_BASE_URL`/`BRF_LLM_MODEL` (or another provider) at a candidate model
and run `make model-readiness` — one command, real corpus, the same READY/NOT READY criterion —
to get a go/no-go the moment a stronger offline-capable model is available to evaluate.

One more knob a future live-model run should reconsider alongside the LLM swap: this harness
defaults `BRF_EMBEDDER=hashed` (deterministic, offline, no HF network dependency) for its own
retrieval side, chosen for this phase's zero-network-dependency discipline, not for maximum
retrieval quality. A production-parity readiness run should also evaluate the default
`model2vec` embedder (or whichever embedder production will actually run), not swap only the
generation model and leave retrieval on the offline fallback.

## Suite status after this task

`cd backend && uv run pytest -q` → **282 passed, 1 skipped** (was 259 passed, 1 skipped before
this task; +23 new tests: 13 for the `ANSWER_SCHEMA` multi-span citation-item shape, 10 for
`compute_verdict`'s readiness logic on fixed synthetic rows, including the fragment-less/empty-
input fix below).
`uv run pytest -q tests/test_isolation.py tests/test_lifecycle.py tests/test_auth.py` →
**47 passed** (unchanged).

## Reproduce

`backend/scripts/model_readiness.py` (committed, content-free), reusing `scripts/reality/
common.py` (temp-tenant ingestion, alias resolution, `assert_zero_connections`) and the committed
question set / fragment-fact locators from `digital_reality.py` and `fragment_facts.py`. Reads the
local gitignored corpus folder, writes only to gitignored `backend/out/reality/
model_readiness.json`.

    make model-readiness-selftest             # this session's READY evidence, exit 0
    make model-readiness-selftest-negative     # this session's NOT READY evidence, exit 1
    make model-readiness                       # the deferred live-model gate (NOT run this phase)

Unit tests (no real corpus, no LLM):

    cd backend && uv run pytest -q tests/test_llm.py::TestAnswerSchemaCitationItem tests/test_model_readiness.py
