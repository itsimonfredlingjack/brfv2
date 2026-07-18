# Evidence — refusal diagnosis: why 13 financial questions refused (2026-07-18)

Diagnoses the 13 substantive refusals from the annual-report validation
(`annual-reports.md`). Method: three independent analysis layers with every disagreement
adjudicated by fresh re-derivation — the corrections are part of the record below.
**Redaction:** metrics only; raw detail in gitignored `backend/out/reality/refusal_buckets/`.

## Bucket distribution (adjudicated)

Buckets per the diagnosis protocol: (1) retrieval miss — answer-bearing text absent from
the six retrieved chunks; (2) extraction garble — retrieved but label/value scrambled in
the chunk string; (3) citation emission — retrieved, readable, model refused anyway.

| analysis layer | b1 miss | b2 garble | b3 emission |
|---|---|---|---|
| script (`refusal_buckets.py`, word-index containment) | 10 | 1 | 2 |
| adversarial synthesis (page-rank based) | 12 | 0 | 1 |
| **reconciliation (per-case re-derivation — authoritative)** | **13** | **0** | **0** |

Both initial layers were wrong in identifiable, documented ways. The script's
false-positive taxonomy (now a checklist for future table diagnostics): prose digits
(years, rate deltas) near a label word counted as "values"; a ratio-definition sentence's
formula constant counted as a value; the fee label matched only in singular while the real
table header is plural; a fund *movement* (flow) row conflated with the *balance* (stock)
row. The synthesis conflated page-level retrieval rank with chunk-level containment once.
Retrieval itself is deterministic — all layers reproduced identical retrieved sets.

**At the default topK=6, every substantive refusal was a retrieval miss — the refusals
were CORRECT behavior.** Zero rejected citations: the model never fabricated. Genuine
answer-row chunks ranked 4–37 of 38–54 chunks (median ≈ 14) under hashed-embedding +
BM25 retrieval; financial-table rows lose to prose mentioning the same vocabulary.

## Retrieval-widening experiment (topK=12, controlled diagnosis — not a tuning change)

Rank census over all 13: 6 cases had a candidate chunk at rank ≤ 12. Re-asked those 6 with
`topK=12` (runtime setting; live Gemma 12B; audit 1 connection/0 external; prompt
≈ 4.7–5.2k tokens, envelope headroom held, 0 truncation/empty-content events):

| case (best rank) | outcome at topK=12 |
|---|---|
| hsb-perrongen q_interest (10) | **answered** — cites the true note-table row, exact, on-row |
| hsb-taltrasten q_interest (11) | **answered** — 3 citations, all true rows, exact |
| brf-grantorp q_fund (7) | **answered** — cites the TRUE balance row, bypassing an adjacent flow-note near-miss |
| hsb-taltrasten q_fund (4) | refused — in-context chunk is the flow/movement note; true balance rows rank 15/38: **correct refusal, wrong-type evidence** |
| rb-lycksaligheten q_interest (11) | refused — in-context chunk is the accrual line (not the year's expense; that row ranks 30): **correct refusal, wrong-type evidence** |
| rb-lycksaligheten q_fund (8) | refused — **the corpus's one genuine fragment-fact**: a transposed table where the true value is IN the shown chunk but 56 word-indices from its label across table lines; answering requires a multi-span citation; the model refused rather than stitch |
| control: hsb-perrongen q_solidity (answered at topK=6) | still answered, exact — widening does not regress the working path |

**Evidence-discrimination finding:** 0/4 answered citations were near-misses (verified
geometrically against the reconciliation's true-row locations), and 2/3 persistent
refusals correctly declined adjacent-but-wrong-TYPE evidence (flow vs balance, accrual vs
expense). The model's answer/refuse boundary tracked evidence quality precisely in every
adjudicated case.

## Multi-span verdict

- **Mechanism (fixed-payload method, FakeLLM, zero connections): WORKS on real
  annual-report chunks.** Hand-constructed label+value fragment pairs resolved with
  2 rects, on-row, independent-exact; a corrupted span rejected the whole citation
  (`grounding_failed`). Note: 2 of the 3 probe substrates were later reclassified as
  false bucket-3 cases — the probes remain valid as mechanism tests (real chunks, real
  fragments) but were not probing genuinely held-and-refused evidence.
- **Natural emission: 0 fired in 31 live answers across both runs — and exactly ONE
  natural case existed that required it** (the transposed table above). On it the model
  refused instead of emitting `quotes[]` — the SAFE failure (contrast the 4B, which
  stitched fabrications into rejection). Standard row-major tables never need multi-span
  because rows are contiguous; prompt-variant probes were not run — with a single natural
  case there is no meaningful emission experiment to run on this corpus.

## Prioritized fixes (by refusals recovered, of 13)

1. **Retrieval ranking for financial-table rows — recovers up to 13.** The only
   first-wall fix. Measured levers: rank ≤ 12 alone recovers 3 answers (topK widening held
   within the context budget), but median true-row rank ≈ 14 and worst 37 — a ranking
   improvement is needed, not just a wider window: semantic embedder on the pilot path
   (hashed n-grams are the floor), financial-vocabulary query expansion
   (label-synonym mapping: soliditet/räntekostnader/underhållsfond families), or
   table-row-aware chunk scoring. Next-phase decision.
2. **Transposed-table fragment citation — recovers 1** (and unlocks the class): the
   multi-span mechanism is built and proven; emission would need contract/prompt work.
   With 1/13 natural frequency, strictly second priority.
3. **No fix needed:** extraction (0 garbled cases — row-major PyMuPDF order is clean on
   these templates), the citation contract (0 violations anywhere), the model's evidence
   discrimination (already correct).

## Reproduce

Bucketing + probes (no LLM): `cd backend && uv run python -m scripts.reality.refusal_buckets [--multispan-probe]`
(hard-fails on ANY network connection). Rank census + topK experiment: scratch scripts
preserved under gitignored `backend/out/reality/refusal_buckets/{reconcile,topk_experiment}/`.
