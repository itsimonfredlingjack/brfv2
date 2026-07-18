# Evidence — fragment-fact path to the model boundary (2026-07-18)

Proves the multi-span citation mechanism (`docs/evidence/multispan-citation.md`) end to end on
THREE distinct real fragment-fact classes from the real born-digital contract — not just the one
org-number case shown earlier by a throwaway scratch script. **Redaction policy:** the corpus
contains personal and business data, so this report is metrics-only — no names, org numbers,
verbatim passages, or real filenames. Raw artifacts (chunk text, derived spans, per-case detail)
live in gitignored `backend/out/reality/fragment_facts.json` for local review only.

## Method

The one born-digital PDF in the corpus (13pp; classified the same way `ocr_reality.classify`
distinguishes it from the 7 real scans), ingested into a throwaway temp-tenant `Store` through the
REAL `Store.add_document` path — no bypass. Three fragment-fact classes, each located by a
deterministic, regex/proximity heuristic over the chunk's own word stream (no fuzzy matching, no
model help, pinned by 17 new unit tests on synthetic fixtures):

- **org-number** — a `\d{6}-\d{4}`-shaped token, paired with the contiguous run of capitalized,
  non-label tokens immediately before it (skipping one intervening "org"-shaped label token, e.g.
  "Org.nr", if present), capped at 4 words so an unrelated caption is never pulled in. The regex
  is anchored (`^...$`) so an 8-digit Swedish personnummer substring — which shares the `NNNNNN-
  NNNN` shape at the tail — cannot be mistaken for an organisation number.
- **party/counterparty name** — a colon-terminated role/label token matched against a small
  generic allowlist of Swedish contract party-role words (company/counterparty/client/etc.),
  paired with the contiguous run of words up to the next label token.
- **cell-value** — a leaf-level appendix-table row code (an uppercase-letter+digit code with at
  least two dotted segments, e.g. distinguishing a leaf row from a section header), paired with
  the descriptive text up to the first short ALL-CAPS table-cell value token.

For each case, the located chunk's real retrievability was independently confirmed (via
`common.alias_for_chunk`, the same retrieval call `ask()` makes) against an already-committed,
content-free generic board question (`digital_reality.QUESTIONS`, the q03/q09-class set) — chosen
per case by measured top-K retrieval on this document, not by construction. The FULL pipeline
(retrieve → generate → verify → resolve) then ran through a scripted `FakeLLM` citing the two
verified spans as `"quotes"` on the correctly retrieved alias — no live model is ever called.

**Offline discipline:** `BRF_EMBEDDER=hashed`, `BRF_LLM=fake` (explicit `FakeLLM` passed to every
`ask()` call), `scripts.eval.install_network_audit` active for the whole run. **Hardening (this
task, addressing Task 4's review):** `scripts/reality/common.assert_zero_connections` now
hard-fails the process (non-zero exit, loud message) if the audit log is non-empty at all — even
an "allowed" loopback connection — since a script whose embedder AND LLM are both fully scripted
has no legitimate reason to open any socket. Wired into `fragment_facts.py`'s own run; a reusable
helper is available for `scanned_ingestion.py` to adopt later (that script itself was not modified
this task, per the task's scope). **Measured: 0 connections total, 0 external.**

## Case results

| case | doc-order candidates located | retrieved alias | citation rects | independent rect-token verdict |
|---|---|---|---|---|
| org-number | 4 | found (top-K) | 2 | exact |
| party/counterparty name | 2 | found (top-K) | 2 | exact |
| appendix cell-value | 96 | found (top-K) | 2 | exact |

**3/3 cases resolved** through the full `ask()` path: answer returned (no refusal), a single
verified citation with `len(quotes) == 2` matching the derived spans exactly, and `len(rects) == 2`
in every case (one line-rect per span — the "multi-rect" bar of ≥2 met exactly, not just cleared).
The independent rect-tokens-vs-span-tokens check (re-derived outside
`citations.resolve_citation`, `verify_highlights.py`'s method) returns **`exact` for all 3/3** —
no invariant violations, no mismatches. 0 cases were `not_locatable` or a `retrieval_miss`.

"Candidates located" is the count of ALL occurrences the heuristic found across the whole document
before checking retrievability — the first candidate whose owning chunk was actually retrieved in
top-K for the case's question was used for the full-pipeline proof; heuristic location and
retrieval confirmation are deliberately measured as separate steps (an occurrence can be real and
correctly paired yet still be a genuine retrieval miss for a given generic question — that would
have been reported as `retrieval_miss`, distinct from `not_locatable`, had it occurred).

## Invariant probes (per case, on the real fragment-fact text)

**Corruption probe** (one span's last alphabetic character flipped, question unchanged): **3/3**
whole-citation rejections — `quote_not_found` in all 3 cases — with the answer refusing
`grounding_failed` and **0 citations shown**, every time.

**Cross-chunk provenance probe** (the SAME two valid, uncorrupted spans cited against a
DIFFERENT chunk from the same real retrieval — one that does not contain them): **3/3**
`provenance_mismatch` rejections, answer refuses `grounding_failed`, **0 citations shown**, every
time.

Both probes hold the all-or-nothing verification invariant and the wrong-occurrence guard on real
fragment-fact text across all three classes, not just the previously-shown org-number case.

## Acceptance bars — summary

| bar | measured | verdict |
|---|---|---|
| cases resolved | 3/3 | **PASS** |
| multi-rect (`len(rects) >= 2`) on every resolved case | 3/3 (2 rects each) | **PASS** |
| `quotes` carries both derived spans exactly | 3/3 | **PASS** |
| independent rect-token verdict == `exact` | 3/3 | **PASS** |
| corruption probe → whole-citation reject + `grounding_failed` + 0 shown | 3/3 | **PASS** |
| cross-chunk probe → `provenance_mismatch` + `grounding_failed` + 0 shown | 3/3 | **PASS** |
| network audit | 0 connections, 0 external | **PASS** |
| audit self-enforcement (non-zero exit on any connection) | wired, not triggered this run | **PASS** |

## What remains model-only

This task closes the mechanism side of the fragment-fact gap: for all three real fact classes
(org-number, party name, appendix cell-value), a correctly-formed `quotes[]` citation resolves,
highlights with 2 independently-verified rects, and survives both an all-or-nothing corruption
probe and a wrong-occurrence cross-chunk probe — end to end through the real retrieval and
verification pipeline, on real chunks, not synthetic fixtures. **What this task does not and
cannot prove is whether a live generation model will spontaneously emit that `quotes[]` payload
for these facts unprompted.** That question was already measured in
`docs/evidence/multispan-citation.md`'s real-data section: the mandated offline model
(`gemma4:e4b`) produced zero `quotes` citations across multiple prompts and budgets for the
org-number fact and instead stitched a single non-contiguous quote (correctly rejected), while a
more capable hosted model used the fragment form correctly on synthetic data. This task does not
re-run that model-emission probe (zero live-model calls, per the phase's global constraint) — it
extends the FIXED-payload proof to two more real fact classes so the emission gap is now known to
be the *only* remaining gap across all three, not just one.

## Suite status after this task

`cd backend && uv run pytest -q` → **259 passed, 1 skipped** (was 238 passed, 1 skipped before
this task; +21 new tests: 17 for the span-derivation heuristics on synthetic fixtures, 4 for
the network-audit hardening helper).
`uv run pytest -q tests/test_isolation.py tests/test_lifecycle.py tests/test_auth.py` →
**47 passed** (unchanged).

## Reproduce

`backend/scripts/reality/fragment_facts.py` (committed, content-free), reusing
`scripts/reality/common.py` (temp-tenant ingestion, alias resolution, independent rect check, and
the new `assert_zero_connections` hardening helper). Reads the local gitignored corpus folder,
writes only to gitignored `backend/out/reality/fragment_facts.json`.

    cd backend && uv run python -m scripts.reality.fragment_facts

Unit tests for the deterministic locator heuristics (synthetic fixtures, no real corpus):

    cd backend && uv run pytest -q tests/test_reality_fragment_facts.py tests/test_reality_common.py
