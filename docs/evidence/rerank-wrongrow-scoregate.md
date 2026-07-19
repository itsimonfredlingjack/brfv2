# Evidence — reranker wrong-row (live) + score-gate: the gate doesn't hold (2026-07-19)

Branch `diag/rerank-wrongrow` (off `main` @ f560db5). **Redaction:** metrics only.
Closes the thread opened by `reranker-license-eval.md` (a licensable reranker *recovers* the
rows) and `rerank-recovery.md` (jina introduced a wrong-row failure class). Live model: the
self-hosted **Gemma 4 12B** on the LAN Ubuntu box (llama.cpp,
GGUF Q4_K_XL), network-audited. Embedder `hashed`, enrichment off.

## Question

Recovery is not the ship bar. Can a *licensable* reranker be safely enabled — i.e. does it
recover the rows **without** turning honest refusals into confident wrong-row answers, and if
not, can a cross-encoder **score floor** gate the misfires out?

## Live wrong-row (of 24 questions/doc-pairs; 4 are unanswerable controls)

| reranker | license/provenance | answered | citations (all verbatim-verified) | on correct row | **pure wrong-row answers** | mixed (correct + noise cite) | controls refused |
|---|---|---|---|---|---|---|---|
| mmarco-mMiniLMv2 | Apache-2.0, clean | 13 | 18 (18/18) | 13/18 | **2** (q_fee ×2) | 3 (q_loans, q_fee) | 4/4 |
| BAAI/bge-reranker-v2-m3 | Apache-2.0, Chinese-org | 20 | 30 (30/30) | 23/30 | **3** (q_fee ×3) | 4 (q_loans, q_fee) | 4/4 |
| jina-reranker-v2 (prior, `rerank-recovery.md`) | CC-BY-NC | ~13 | 30 (30/30) | — | ~3 (q_fee) | 4 (q_loans) | 4/4 |

**Nothing fabricated in any run** — every citation is verbatim-verified, 0 independent-check
violations. The failure is *relevance*, not fabrication: verification bounds one, not the other.

**The wrong-row failure is reranker-agnostic and concentrated in `q_fee`** (årsavgift per m²).
Three of the four docs do not report fee-per-m² as a value-bearing labeled row at all (it is
"not answer-bearing" under the authoritative locator), so *any* reranker that surfaces a
plausible fee-adjacent row lets the 12B answer on the wrong row instead of refusing. bge, which
recovers best (17/17 offline) and answers most aggressively (20/24), therefore produces the
*most* wrong-row answers (3 pure). More recovery bought more wrong answers.

## Score-gate: measured, and it does NOT separate the misfires

Prior hypothesis (`rerank-recovery.md` next-phase #1): misfire chunks may score measurably
*below* true rows, so a floor "drop reranked chunks below score T from the excerpts" could turn
wrong-row answers into safe refusals. Measured offline (no LLM) — the reranked top-6 chunks
tagged answer-bearing (true row present) vs distractor:

| reranker | answer-bearing scores (top-6) | distractor scores (top-6) |
|---|---|---|
| mmarco (logits) | n=25, med −2.29, max **1.06** | n=95, med −2.65, max **2.74** |
| bge (0–1) | n=44, med **0.172**, max 0.97 | n=76, med **0.160**, max 0.93 |

**The distributions overlap; distractors routinely outscore true rows.** And every `q_fee`
misfire has a *high-scoring* distractor with **no** true row in the pool (mmarco best distractor
1.08 / 1.11 / 2.19; bge 0.69 / 0.77 / 0.93). A floor set high enough to drop those distractors
also drops most true rows (bge answer-bearing median 0.17); a floor low enough to keep true rows
keeps the misfire distractors. **No floor separates them — the hypothesis is refuted on both
the clean and the ceiling reranker.** The cross-encoder's own score is not a reliable
"is-this-the-right-row" signal on this corpus.

## Verdict

- **Recovery is solved and licensable** (`reranker-license-eval.md`): mmarco 14/17 clean, bge
  17/17.
- **But the reranker cannot be safely enabled.** It introduces reranker-agnostic wrong-row
  answers (2–3 pure, plus noise citations), and the assumed fix — a cross-encoder score floor —
  provably does not gate them out. Under the product's zero-wrong-answer bar, that is
  disqualifying. **`rerankEnabled` stays default-off.**
- **The product's safe default is vindicated:** without the reranker the pipeline *refuses* the
  hard financial-table questions rather than answering them wrong. For a BRF board acting on
  liability/economy figures, an honest refusal beats a confident wrong row.

## What the real fix would need (not a score floor; separate design)

The dominant misfire (`q_fee`) is a **grounding/answerability** problem the reranker amplifies:
the value the question asks for is not present as a labeled row, yet the model answers from a
plausible-looking neighbor. Candidate directions, each a real project:
1. **Answer-alignment guard** — accept a citation only if the cited row's *label* matches the
   question's target term (the `row_landing_verdict` logic exists as a measurement; making it a
   runtime gate needs the question→label mapping, an NLU step).
2. **Generation-side "value-not-present" refusal** — prompt/contract work so the model refuses
   when the specific asked-for figure isn't in a clearly-labeled row, not just when retrieval is
   empty.
3. **Ship reranker-off** — keep the zero-wrong-answer property, accept the recall ceiling
   (refuses the ~7–13 hard rows), and treat reranking as a future opt-in behind (1) or (2).

## Guards / provenance

- Live runs network-audited: **1 connection each to the self-hosted 12B endpoint, 0 external**;
  controls 4/4 refused; all citations verbatim-verified, 0 violations.
- No code change this phase (measurement only, on the merged `BRF_RERANK_MODEL` config).
- Data discipline: metrics-only; raw run JSON + score dumps in gitignored
  `backend/out/reality/reranker_eval/`.

## Reproduce

```bash
cd backend
MODEL=<served gguf id from GET :8000/v1/models>
# live wrong-row (self-hosted 12B on the LAN; runner hard-fails on any external connection)
BRF_EMBEDDER=hashed HF_HUB_OFFLINE=1 BRF_LLM=selfhosted \
  BRF_LLM_BASE_URL=http://<self-hosted-12b-host>:8000/v1 BRF_LLM_MODEL="$MODEL" \
  BRF_RERANK_MODEL=cross-encoder/mmarco-mMiniLMv2-L12-H384-v1 BRF_RERANK_MAX_LENGTH=512 \
  uv run python -m scripts.reality.annual_reports --rerank --out out/reality/reranker_eval/live_mmarco
# score-gate analysis (offline, no LLM): scratch script tags reranked top-6 answer-bearing vs distractor
```
