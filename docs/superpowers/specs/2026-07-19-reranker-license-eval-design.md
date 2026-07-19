# Design — licensable-reranker recovery eval

**Branch:** `feat/reranker-license-eval` (off `main` @ 92c621a)
**Date:** 2026-07-19
**Status:** design approved, pending spec review

## Problem

The cross-encoder reranker is the only measured lever that recovers annual-report
table rows (`rerank-recovery.md`: 11/13 offline, 9/13 live; my harness: 16/17). But the
shipped model `jinaai/jina-reranker-v2-base-multilingual` is **CC-BY-NC-4.0** — unusable
in a product we sell — and the enrichment detour that tried to avoid it produced a null
(`enriched-representation.md`). So the direct question returns: **is there a
commercially-licensed, self-hostable reranker that recovers comparably?**

Prior licensing research (`backend/out/reality/rerank_measure/licensing/research.md`) already
mapped the field under the project's **standing exclusion policy** (exclude Chinese-origin
org OR Chinese-origin base model, even under Apache-2.0). Under that policy the only
off-the-shelf clean candidate is `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1`, but its
Swedish is zero-shot (not in its mMARCO fine-tune languages). The user chose to **test both
lanes and compare** — measure the clean candidate AND a best-in-class Chinese-base Apache
candidate, so we learn both whether the clean option works and the quality ceiling the
policy forgoes.

## What this eval is (and is not)

- **Is:** a recovery comparison across rerankers on the deterministic, offline harness built
  in the enrichment phase (`scripts/reality/enrichment_recovery.py --rerank`). It answers
  "does a licensable reranker put the true row into topK as well as jina?"
- **Is not:** a wrong-row / relevance-quality measurement. The reranker's known 0→4 wrong-row
  regression (`rerank-recovery.md`) is a live-model, **reranker-agnostic** problem (needs a
  score-gate + the Gemma-12B tunnel, currently down). It is flagged as the next phase on
  whichever reranker wins — not solved here.

## Mechanism

### `app/rerank.py` — make the model configurable

`MODEL_NAME = os.environ.get("BRF_RERANK_MODEL", "jinaai/jina-reranker-v2-base-multilingual")`.
Default unchanged → the existing rerank-marked test and cached jina weights keep working
byte-identically. Both `_load_model()` and `reranker_available()`'s cache-probe read the same
configurable name, so an availability check matches the model actually loaded.

**Invariant:** reranking only reorders *which* chunks reach the prompt. `RetrievalHit.text`
stays frozen; `citations.py`/`normalize.py`/verification are untouched. Swapping the reranker
model changes ranking only — never what can be cited. No new citation surface.

### Candidates (both load via `sentence_transformers.CrossEncoder`, weights self-hosted, no cloud API)

| model | license | org / base | provenance lane | Swedish |
|---|---|---|---|---|
| `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1` | Apache-2.0 | Nils Reimers / XLM-R-Large (Meta) | **clean** (non-Chinese) | zero-shot (CC-100 pretrain only) |
| `BAAI/bge-reranker-v2-m3` | Apache-2.0 | BAAI (Beijing) / XLM-R-large | Chinese-org (excluded by policy) | multilingual incl. sv |
| `jinaai/jina-reranker-v2-base-multilingual` | CC-BY-NC-4.0 | Jina (Berlin) | baseline reference (unlicensable) | MKQA-evaluated |

`bge-reranker-v2-m3` is the Chinese-base ceiling representative (loads cleanly via
CrossEncoder; chosen over `mxbai-rerank-v2`, which needs a bespoke loader).

### Measurement

Weights download **once**, un-audited (network), like jina's original ~1.1 GB — then all
measurement runs are offline (`HF_HUB_OFFLINE=1`, harness enforces `assert_zero_connections`).

Reuse `scripts/reality/enrichment_recovery.py --rerank`, setting `BRF_RERANK_MODEL` per run.
Compare true-row-into-topK=6 over the 17 gradeable cases:

- no-rerank baseline (already: 10/17)
- jina (already: 16/17)
- **mmarco-mMiniLMv2** (clean) — the decision variable
- **bge-reranker-v2-m3** (Chinese-base ceiling)

Embedder pinned `hashed` (isolate the reranker variable, as before). Enrichment is irrelevant
here (proven inert) — run with `BRF_ENRICH=0` so the comparison is reranker-only.

## Interpretation / done when

- **If mmarco recovers comparably to jina** (≈16/17): the licensing blocker dissolves — a
  clean, Apache-2.0, self-hostable reranker works. Ship-path unblocked (pending the separate
  wrong-row/score-gate phase).
- **If mmarco underperforms** (zero-shot Swedish gap) but bge is strong: the policy is costing
  real quality — the honest fork is fine-tuning `microsoft/mdeberta-v3-base` (MIT) into a
  Swedish cross-encoder, or revisiting the policy. Report the gap plainly.
- **If neither helps:** the reranker path itself is weaker than believed — report and stop.

Recovery comparison measured across the 3 rerankers, provenance tradeoff quantified, evidence
in `docs/evidence/reranker-license-eval.md` (metrics-only), suites green (rerank test still
passes on the default jina model), no regressions.

## Guards

- Full re-index NOT required (reranking is a query-time stage; no re-chunk/re-embed).
- Existing suites green; the rerank-marked real-model test still passes on the default model.
- Data discipline: metrics-only committed evidence; raw artifacts gitignored under
  `backend/out/reality/`.

## Out of scope

Wrong-row / score-gate fix (next phase, live model), mdeberta fine-tune (a build project, only
if the eval says so), reranker enabled-by-default (stays `rerankEnabled=False`), licensing
negotiation with Elastic/Jina.
