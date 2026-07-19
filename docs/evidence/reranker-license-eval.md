# Evidence — licensable-reranker recovery eval (2026-07-19)

Branch `feat/reranker-license-eval` (off `main` @ 92c621a). **Redaction:** metrics only.
Follows `enriched-representation.md` (enrichment recovered 0) and `rerank-recovery.md` (the
CC-BY-NC jina reranker recovers, but introduced a wrong-row failure class).

## Question

The cross-encoder reranker is the only measured lever that lifts annual-report table rows into
topK — but the shipped model is CC-BY-NC-4.0 (unusable in a product we sell). **Is there a
commercially-licensed, self-hostable reranker that recovers comparably?** Per the user's call,
test both provenance lanes: a clean (non-Chinese at every layer) Apache-2.0 model, and a
best-in-class Chinese-origin Apache-2.0 model, against the jina baseline.

## Method

`app/rerank.py` made model-configurable (`BRF_RERANK_MODEL`, default jina unchanged) plus a
`BRF_RERANK_MAX_LENGTH` (XLM-R-based models cap at 512 positions where jina supports 1024).
The invariant is untouched: reranking only reorders *which* chunks reach the prompt;
`RetrievalHit.text` stays frozen and `citations.py`/verification are byte-identical — swapping
the reranker changes ranking only, never what can be cited.

Measurement reuses the deterministic recovery harness from the enrichment phase
(`scripts/reality/enrichment_recovery.py --rerank`, authoritative word-index row locator, no
LLM): does the true answer-bearing row reach topK=6? Embedder pinned `hashed`, enrichment off
(reranker-only variable), audit 0 external connections. Model weights downloaded once
(un-audited); all recovery runs offline.

## Result — a licensable reranker recovers the rows

| reranker | license | org / base | provenance | true row in topK=6 |
|---|---|---|---|---|
| none (hybrid only) | — | — | — | 10 / 17 |
| **cross-encoder/mmarco-mMiniLMv2-L12-H384-v1** | **Apache-2.0** | Nils Reimers / **XLM-R-Large (Meta)** | **clean (non-Chinese)** | **14 / 17** |
| jinaai/jina-reranker-v2-base-multilingual | CC-BY-NC-4.0 | Jina (Berlin) | baseline (unlicensable) | 16 / 17 |
| BAAI/bge-reranker-v2-m3 | Apache-2.0 | **BAAI (Beijing)** / XLM-R-large | Chinese-org (excluded by policy) | **17 / 17** |

**The licensing blocker can be dissolved.** Both Apache-2.0 candidates recover the rows; the
choice is a provenance tradeoff:

- **Holding the "no Chinese-origin base/org" policy → mmarco recovers 14/17** — a fully clean,
  Apache-2.0, self-hostable cross-encoder recovers +4 over the no-rerank baseline and most of
  what the unlicensable jina does, on Swedish it was never fine-tuned on (zero-shot via XLM-R's
  CC-100 pretrain).
- **Relaxing the policy → bge-reranker-v2-m3 recovers 17/17** — perfect, and *better* than jina,
  also Apache-2.0. The policy costs ~3 cases (14 vs 17).

## Where mmarco loses to jina (per-case), and why

mmarco's 3 misses vs jina are all large-chunk interest/solidity cases:

| case | no-rerank | jina | mmarco |
|---|---|---|---|
| brf-grantorp / q_interest | 14 | 3 | **16** |
| hsb-taltrasten / q_interest | 11 | 3 | **12** |
| rb-lycksaligheten / q_solidity | 37 | 4 | **11** |

These regress toward their un-reranked ranks — consistent with **XLM-R's 512-token cap**
truncating the answer row out of a large note/table chunk before the cross-encoder scores it
(jina reads 1024 tokens; mmarco was run at 512 because XLM-R overflows above 514 positions —
a real, structural limitation of the clean candidate, not a tuning choice). mmarco still
*recovers* 4 cases the baseline missed (grantorp q_fund, grantorp/taltrasten q_solidity, rb
q_fund). So the clean-model gap is partly a context-length artifact, plausibly narrowable by
chunk-size tuning for the reranker or by fine-tuning a longer-context clean base.

## Important: recovery is not the whole bar — wrong-row is unmeasured here

This eval measures **recovery only** (true row into topK). It does **not** measure the
reranker's known **wrong-row** failure class (`rerank-recovery.md`: jina turned honest refusals
into confident verbatim citations on the *wrong* row, 0→4 on the annual-report set). That
failure is a **live-model, reranker-agnostic** property — the verification invariant bounds
fabrication, not relevance — and it applies to *any* reranker, including mmarco and bge. It
requires the Gemma-12B tunnel (currently down) plus a score-gate, and is the **next phase** on
whichever reranker is chosen. A better recovery number here does not by itself clear the
product's zero-wrong-answer bar.

## Guards

- No re-index (reranking is a query-time stage). Default model unchanged → existing behavior
  byte-identical; `rerankEnabled` stays default-off.
- Suites green: backend **418 passed / 1 skipped** (+3 config tests) on the default jina model;
  the rerank-marked real-model test still passes on the default.
- Data discipline: metrics-only here; raw per-case JSON in gitignored
  `backend/out/reality/reranker_eval/`.

## Conclusion and fork

The enrichment detour was chasing a way around the reranker's license; this eval shows the
direct path works. **A commercially-licensed reranker recovers the annual-report rows** — the
only open question is provenance:

1. **Clean provenance (policy held):** ship `mmarco-mMiniLMv2` (Apache-2.0, Meta base) at
   14/17, and either accept the 512-token gap or invest in a longer-context clean cross-encoder
   (e.g. fine-tune `microsoft/mdeberta-v3-base`, MIT) to close it.
2. **Best recovery (policy relaxed for self-hosted weights):** `bge-reranker-v2-m3` (Apache-2.0)
   at 17/17.

Either way the **next phase is the wrong-row/score-gate work** (live 12B), which gates whether
*any* reranker can ship under the zero-wrong-answer bar — recovery alone does not.

## Reproduce

```bash
cd backend
# one-time weight download (network): CrossEncoder("cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"), CrossEncoder("BAAI/bge-reranker-v2-m3")
BRF_ENRICH=0 BRF_RERANK_MODEL=cross-encoder/mmarco-mMiniLMv2-L12-H384-v1 BRF_RERANK_MAX_LENGTH=512 \
  uv run python -m scripts.reality.enrichment_recovery --rerank --out out/reality/reranker_eval/mmarco.json
BRF_ENRICH=0 BRF_RERANK_MODEL=BAAI/bge-reranker-v2-m3 \
  uv run python -m scripts.reality.enrichment_recovery --rerank --out out/reality/reranker_eval/bge.json
# jina baseline + no-rerank already in out/reality/enrichment/rec_baseline_rerank.json (16/17) and rec_baseline.json (10/17)
```
(Requires the public corpus at `~/brf-corpus-public/brf-annual-reports-2026-07-18/sample-ars`.)
