# Evidence — enriched chunk representation for annual-report retrieval (2026-07-19)

Branch `feat/enriched-chunk-representation` (off `main` @ 1727977). **Redaction:** metrics
only — no document-specific names, amounts, or org numbers; the accounting terms used below
(`räntekostnader`, `Resultaträkning`, …) are generic Swedish vocabulary already present in the
committed test fixtures and question set.

## Question

Fix annual-report retrieval through *representation*, not ranking — two alternatives were
closed by prior measurement (no rerank-score threshold separates cleanly; the jina reranker is
CC-BY-NC, unusable in a product we sell). **Primary question: how many of the 13 known refusals
recover with enrichment (document year + section heading) and NO reranker?** Then, separately,
enrichment + reranker.

## Headline

**Enrichment recovers 0.** This is a null result. The representation lever, as scoped (document
year + section heading), does not move annual-report retrieval — it adds no signal that
discriminates the true table row from the prose that competes for the same query vocabulary.
The citation invariant is implemented and proven intact; the lever is simply inert for this
class of query on this corpus.

## The design and the invariant (implemented, proven)

Each chunk gets an enriched **search string** = `"{document year} {section heading}\n{frozen
chunk text}"`, used **only** for BM25 fit + embedding inside `HybridIndex.build`. The frozen
`chunk.text` is untouched; `RetrievalHit.text` stays frozen; `answer.py:_render_excerpts` shows
the model `h.text`, so **the model never sees the enrichment**; verification (`resolve_quote`)
reads `PageData.words`. Enrichment is default-on, toggled by `BRF_ENRICH`, and degrades to the
frozen text when no year/heading is confidently found.

**Invariant proven by test** (`backend/tests/test_enrich_invariant.py`): the enrichment-only
phrase `"2025 Resultaträkning"` — real search text, but non-contiguous in the document's words —
is `Rejected` by `resolve_citation`; the control (the frozen row text) verifies; and through the
full `ask()` path a model citing the enrichment prefix yields **0 citations**. Adversarial
review empirically disproved vacuity: with `BRF_ENRICH=0` both invariant tests fail loudly
(`search_text` is `None`), so they cannot pass unless enrichment genuinely fired.

## Deterministic retrieval-recovery (primary evidence — offline, reproducible, no model)

For each `(document, financial question)`, does the true **answer-bearing** table row reach
`topK=6`? The row is located by the **authoritative** word-index locator
(`refusal_buckets.label_row_occurrences` + `chunk_contains_occurrence`) reused verbatim — never
a crude label+value string heuristic (which false-positives on prose digits, per
`refusal-diagnosis.md`). 17 gradeable cases (of 20 financial `doc×q` pairs; 3 have no
answer-bearing row for those labels in that document). Embedder **pinned `hashed`** — the arm
the original 13 refusals were measured on — to isolate enrichment from an embedder swap; a
`model2vec` cross-read is reported as a clearly-labelled second variable.

| arm | embedder | true row in topK=6 | Δ vs its baseline |
|---|---|---|---|
| baseline | hashed | **10 / 17** | — |
| **enriched** | hashed | **10 / 17** | **0** (ranks byte-identical) |
| baseline + rerank | hashed | 16 / 17 | +6 (rerank alone) |
| enriched + rerank | hashed | 16 / 17 | **+0 over rerank** |
| baseline | model2vec | 10 / 17 | — |
| **enriched** | model2vec | **9 / 17** | **−1 (slightly worse)** |

- **Enrichment alone recovers 0** on the hashed embedder (every rank unchanged), and is **−1 on
  model2vec** (the non-discriminating prefix slightly dilutes the true chunk's vector).
- **The reranker recovers 6** (10→16); **enrichment adds nothing on top of it** (enriched+rerank
  == baseline+rerank == 16/17). The reranker does all the work — the exact lever ruled out on
  licensing grounds.

Raw per-case ranks in gitignored `backend/out/reality/enrichment/rec_*.json`.
(Caveat, documented in the harness: the `--rerank` arm reranks a `WIDE_TOP_K=60` pool, wider
than production's default `rerankCandidates=40`, so its recovery is an *upper bound* — the
production-faithful reranker numbers are the prior phase's live run, `rerank-recovery.md`.)

## Why enrichment is inert (mechanism — verified, not assumed)

Enrichment **is** applied: 40/40 chunks in a sample document carry a distinct `search_text`; the
true `räntekostnader` chunk carries the prefix `"2025 Resultaträkning"`; section headings are
detected correctly per section (`Förvaltningsberättelse`, `Flerårsöversikt`, `Resultaträkning`,
`Eget kapital`, …). Fusion **scores shift at the 3rd–4th decimal**, but the **ranking order is
unchanged**, for two structural reasons:

1. **The document year is constant across every chunk** in a report → it adds identical signal
   to all candidates and cannot re-order them.
2. **The section heading is orthogonal to the query vocabulary** — the query `räntekostnader`
   does not lexically match `Resultaträkning`, so BM25 gives the prefix no weight; and the
   heading is shared across all chunks in a section, so on the dense side it cannot separate the
   true row from the prose chunks in the same section that mention the same term. This is exactly
   the competition `refusal-diagnosis.md` identified: *financial-table rows lose to prose sharing
   their vocabulary* — and year+heading does not change that vocabulary overlap.

## Live end-to-end (12B pilot): not run — logically determined by the above

Because enrichment provably does **not** change the retrieved top-6 (identical ranking) and the
model is shown only the frozen `RetrievalHit.text`, the baseline and enriched prompts are
**byte-identical** → identical answers → **0 end-to-end recovery by construction**. A live 12B
pass would confirm a foregone conclusion. (The reranker's live end-to-end behaviour is already
on record: `rerank-recovery.md` — 9/13 recovered but wrong-row answers went 0→4, so
`rerankEnabled` stays OFF.) Decision to skip the redundant live pass taken with the user.

## Tracked case: rb-lycksaligheten q_fund (the one genuine wrong-row)

Rank **8 → 8, unchanged** under enrichment — neither fixed nor worsened. It is the
transposed-table fragment case that needs a multi-span citation (the model declines to stitch);
that is orthogonal to this representation lever.

## Guards (all green)

- **Full re-index** required and measured: 4 docs / 95 pages / 171 chunks / **0.82 s**
  (~9 ms/page, hashed). Enriched == baseline (0.82 s) → **enrichment adds no measurable ingest
  overhead** (a 3-page year scan + a height-based heading pass is negligible vs extraction +
  embedding).
- **Synthetic golden**: recall **1.000 in every arm** (tenant A 46/46, tenant B 28/28, enriched
  and baseline) → no regression on what already worked.
- **Suites**: backend **414 passed / 1 skipped** (+24 new tests over the 390 baseline),
  isolation trio **48**, frontend **63**, `oxlint` (5 pre-existing warnings, unchanged —
  backend-only change), `vite build` OK.

## Conclusion

The mechanism is sound and safe: an invariant-preserving, cleanly-toggled enriched search
representation that provably cannot leak into citations and adds ~zero ingest cost. But as
scoped (document year + section heading) it is **inert** for annual-report retrieval — it moves
the recovery number by **0** (slightly negative on a semantic embedder), because its tokens are
non-discriminating for these queries. **The licensing blocker is not resolved by enrichment.**

Reported plainly per the brief: this finding — that year+heading representation does not move the
number — matters more than a fix that looks good. The only measured lever that recovers these
rows remains the cross-encoder reranker (16/17), which stays unlicensable (CC-BY-NC) and
wrong-row-prone. The honest next levers (out of scope here) are query-side financial-label
expansion so the query reaches the sparse row, a table-row-aware dense unit, or a *licensable*
reranker — not year+heading enrichment.

## Reproduce

```bash
cd backend
# deterministic recovery (no model; hard-fails on any network connection)
BRF_ENRICH=0 uv run python -m scripts.reality.enrichment_recovery --out out/reality/enrichment/rec_baseline.json
BRF_ENRICH=1 uv run python -m scripts.reality.enrichment_recovery --out out/reality/enrichment/rec_enriched.json
BRF_ENRICH=1 uv run python -m scripts.reality.enrichment_recovery --rerank --out out/reality/enrichment/rec_enriched_rerank.json
BRF_EMBEDDER=model2vec BRF_ENRICH=1 uv run python -m scripts.reality.enrichment_recovery --out out/reality/enrichment/rec_m2v_enriched.json
# invariant proof + regression
uv run pytest tests/test_enrich_invariant.py tests/test_enrich.py tests/test_store_enrichment.py -v
uv run python -m scripts.eval --retrieval-only            # enriched
BRF_ENRICH=0 uv run python -m scripts.eval --retrieval-only   # baseline
```
(Requires the public corpus at `~/brf-corpus-public/brf-annual-reports-2026-07-18/sample-ars`.)
