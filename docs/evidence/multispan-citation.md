# Evidence — multi-span citation contract (2026-07-16)

Extends what a *citation* can be — from one contiguous verbatim quote to a SET of short spans —
so fragment-facts (org number, party name, amounts that live in table cells and letterheads with
no contiguous sentence to quote) can be assembled from individually-verified fragments instead of
refused. **The verification invariant is unchanged and was not weakened:** a citation is shown
only if EVERY span is independently verbatim-verified in its cited chunk; if any span fails, the
whole citation is rejected exactly as a fabricated single quote is. No paraphrased, fabricated, or
unverified fragment can reach the user.

**Redaction:** the validation corpus contains personal data. This report is metrics-only — no
names, org numbers, or verbatim passages. Real-document artifacts stay in gitignored local folders.

## The contract

- Model emits, per citation, either `"quote"` (one contiguous span — the common case, unchanged)
  or `"quotes": [...]` (2–`MAX_SPANS` short spans, for a fragment-fact). Both normalize to a span
  list in `parse_llm_json`.
- `citations.resolve_citation(chunk, spans, pages)` runs **every** span through the existing
  `resolve_quote` (same normalization, same wrong-occurrence guard, same bbox validation) and
  returns `Resolved` only if all spans verify; the first failure returns `Rejected(reason,
  failed_span=...)`. Rects are the union of the spans' line boxes (deduplicated, reading order).
- `CitationOut` gains `quotes` (the verified spans); `quote` becomes a display string joining
  fragments with `" […] "` — a marker that signals discontinuity rather than implying one
  seamless sentence.

## The invariant is provably intact

- **Tests (offline suite 197 passed, 1 skipped; was 181):** new `test_citations.py` cases prove
  union-rects on success, single-span equivalence to `resolve_quote`, `too_many_spans`,
  blank/empty span rejection, cross-chunk `provenance_mismatch`, and — the core —
  `test_invariant_one_unverified_span_rejects_the_whole_citation`. New `test_answer.py` cases
  prove end-to-end that one bad span → `grounding_failed` with nothing shown, and that a good
  single citation survives alongside a rejected multi-span (warn path).
- **Fresh-context adversary** (a verifier subagent given only the source, no design context, tasked
  to make an unverified span reach the user): **no violation** across 10 attack classes — blank/
  zero-width/whitespace spans, casefold and NFKC and hyphen-free forgeries, a fabricated
  fragment on another page, the `MAX_SPANS` boundary with a fabricated last span, `requireSources`
  off, and warn + insufficient-data. It confirmed the whole surface reduces to one gate: a
  citation is emitted only inside `if isinstance(res, Resolved)`, and `Resolved` provably requires
  every span to be normalized-verbatim at a chunk-local location. Confidence: high.
- **Residual risks it flagged (by-design, documented, not code bugs):**
  1. *Assembly reading.* Two individually-verified fragments joined for display could imply a
     combined claim not contiguous in the source. Mitigated by the `" […] "` marker and by
     `quotes[]` exposing fragments separately; a frontend must not render them as one seamless
     sentence (current chip shows the marked display string).
  2. *The free-text `answer` is still not verified* — only that ≥1 citation verifies. Unchanged by
     this work; it is the boundary of what "verified" covers (pre-existing).
  3. `chunk.word_start/word_end` from the ingest chunker are trusted (not reachable from LLM
     output, outside the threat model).

## Real-data validation — offline, network audit 0 external on every LLM run

Re-ran the reality-report board questions on the real born-digital contract with the mandated
offline model (`gemma4:e4b`).

**No regression, zero false answers.** All previously-passing questions still answer; an
independent checker (rect-covered words re-derived and matched to each cited span through the
app's own normalizer) found **12/12 citations land `exact`, 0 invariant violations, 0 false
answers**. Network audit: 1 connection, 0 external, on every run.

**The mechanism resolves the real fragment-fact.** For the org-number question (previously refused
because the model stitched a non-contiguous quote that verified nowhere), the correct fragments —
the BRF name and the org number — each verify individually on the retrieved page, and
`resolve_citation([name, number])` on that real retrieved chunk returns **Resolved with 2
highlight rects**. The same two fragments cited against the *other* retrieved chunks are correctly
`provenance_mismatch` — the invariant holding on real data.

**But the local model will not emit the multi-span form.** `gemma4:e4b` produced **zero** `quotes`
citations across: the production default budget; a raised budget (3000); pointed fragment-fact
questions; and three prompt variants including one with a worked example. It instead stitches
fragments into a single non-contiguous quote, which is correctly rejected — so the org-number
question still refuses end-to-end. This is a capability limit of a 4B model, not a prompt problem
and not a mechanism problem.

**A capable model uses verified fragments** (synthetic data only, hosted provider — no personal
data): given a table-layout page, `claude-cli` answered every fragment-fact with verified,
highlighted citations, choosing a single contiguous quote where the layout allowed one and
leaving multi-span as the fallback. The contract behaves correctly under a model that can follow
it.

## Verdict and the decision this surfaces

The multi-span citation contract is **implemented and provably safe**, resolves the real
fragment-fact when the citation is correctly formed, and does not regress or weaken verification.
The definition-of-done criterion "previously-refused fragment questions now answer" is met at the
mechanism level and on the real fact via `resolve_citation`, but **not end-to-end on real
documents with `gemma4:e4b`, because that model will not emit multi-span citations.**

**Design fork (Simon's call — infra/model, the one input only he can provide):** realizing
fragment-fact answers on real documents needs a more capable generation model on the offline/
EU-resident path (a larger Gemma or comparable instruct model that follows the `quotes[]`
contract). The alternative — inferring spans in code that the model did not assert (layout-block
assembly) — would violate the invariant and is deliberately **not** built.

## Reproduce

- Unit/e2e: `cd backend && uv run pytest -q tests/test_citations.py tests/test_answer.py tests/test_llm.py`
- Real-data (offline): `uv run python -m scripts.reality.digital_reality` then
  `uv run python -m scripts.reality.verify_highlights` (metrics only; reads the local gitignored
  corpus, writes to gitignored `out/reality/`). The gemma emission probes and the capable-model
  synthetic demo are throwaway scripts (scratch only; synthetic demo uses no real documents).
