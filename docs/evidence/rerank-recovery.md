# Evidence — cross-encoder reranking: recovery measured, and a new failure class (2026-07-19)

Fixes the retrieval ceiling diagnosed in `refusal-diagnosis.md` (13/13 refusals = true
financial-table rows ranking 4–37 under hashed+BM25, only top-6 reaching the model).
Approach per the phase brief: retrieve wide (40 candidates), rerank with the
`jinaai/jina-reranker-v2-base-multilingual` cross-encoder lifted from the donor RAG engine,
pass top-6 onward — prompt size unchanged. **Redaction:** metrics only; raw artifacts in
gitignored `backend/out/reality/rerank_measure/`.

## Implementation (commits 7b4c376, 7981e2b)

`backend/app/rerank.py` (sync CrossEncoder wrapper, lazy singleton, mps/cuda/cpu,
injectable scoring seam); `Settings.rerankEnabled` (default **off** — behavior byte-identical
until enabled) + `rerankCandidates=40`; wired at the retrieval call in `answer.py`; the
relevance gate deliberately keeps its original-retrieval-confidence semantics; enabled-but-
unavailable fails loudly in Swedish. `RetrievalHit.rerank_score` additive. `--rerank` flags on
the reality runners. Review-approved; verification invariant untouched (`citations.py`/
`normalize.py` byte-identical).

Dependency facts recorded honestly: the optional `rerank` extra forced a unified-lock
downgrade of `huggingface-hub` 1.23→0.36.2 and `tokenizers` 0.23.1→0.22.2 for the always-on
model2vec embedder. Measured equivalent (eval-fast recall@6 1.000/46 at both locks, model2vec
loads offline at both); re-pin proven structurally unsatisfiable (`transformers<5` requires
`hub<1.0`; `tokenizers>=0.23` capped by every transformers release). Residual risks: recall@6
is coarse (sub-threshold confidence drift invisible); cold-download path under hub 0.36
untested; no CI gate runs eval-fast on lock changes. **License flag: the reranker is
CC-BY-NC-4.0 (non-commercial) — a pilot/production licensing decision is required before this
ships beyond evaluation.**

## Offline rank census (no LLM; audit 0 connections)

**11/13 previously-refused true rows reach top-6 after reranking** (e.g. 29→2, 33→2, 37→4,
15→1). Misses: `hsb-taltrasten q_fee` (23→8), `rb-lycksaligheten q_interest` (30→12 — the
accrual-line and formula-constant distractors still outrank the true row). The known
wrong-type flow-note near-miss is correctly demoted below its true row. Synthetic golden
recall@6: **1.000 with rerank off AND on** (n=46). Retrieval-level warning that proved
prophetic: previously-answered `rb-lycksaligheten q_fee`'s cited chunk displaced 3→11.

## Live recovery (Gemma 4 12B via tunnel; audit 1 connection loopback:8000, 0 external)

Of the 13 previously-refused, with rerank on:

| outcome | count | cases |
|---|---|---|
| **Recovered** — answered, citation verified, lands on the TRUE row, independent exact | **9** | interest×4, solidity×3, fund×2 |
| **Misfire** — answered with a verbatim-exact citation on the WRONG row/page | **3** | q_fee on hsb-perrongen (right page wrong line), hsb-taltrasten, brf-grantorp (both cite p5-class rows; true fee rows are on p12-class pages that still miss top-6) |
| Honest refusal (matches census miss) | 1 | rb-lycksaligheten q_interest |

Previously-working surface: `rb-lycksaligheten q_fee` = **confirmed full regression**
(was correct; now answers from a wrong, non-label page — verbatim-exact, factually wrong row).
4 of the q_loans answers gained one extra wrong-row citation alongside correct ones
(citation-level noise). 2 previously-answered cases clean. Controls: 4/4 still refuse.
All 30 citations verbatim-verified, 0 independent-check violations — **nothing fabricated**.

Contracts corpus (11 board questions, rerank on): net +1 — 3 recoveries (incl. the historical
q03/q05 class), 2 SAFE regressions (previously-answered → honest refusal, no wrong answers),
5 unchanged, control refuses; `verify_highlights` 15/15 exact.

## The finding that matters: a new failure class

The reranker converts some honest refusals (and one correct answer) into **confident
wrong-row answers**: verbatim quotes from real rows that do not answer the question (a fee
definition row instead of the fee value row; a non-label page). Wrong-row count went **0 → 4**
on the annual-report set. The verification invariant bounds *fabrication*, not *relevance* —
a semantically-wrong row passes verbatim verification by construction. Under the product's
zero-false-answer bar, these 4 outweigh raw recovery: **net correct answers +8, but the
zero-wrong-answer property is broken while rerank is enabled.**

Verdict: the reranker demonstrably fixes the diagnosed ranking problem (11/13 offline, 9/13
live) at ~+4.7 s/question (MPS: model load 4.25 s once; per-query mean 3.95 s; ingest
untouched) — but it must NOT be enabled as-is. `rerankEnabled` stays default-off.

## Recommended next phase (not done here — measurement only this phase)

1. A principled floor on the cross-encoder's own score before a reranked chunk may enter the
   excerpt set (misfire chunks may score measurably lower than true rows — measure first,
   don't assume), and/or fee-vocabulary query expansion targeting the 2 census misses.
2. Re-measure this exact matrix (13 + answered-7 + controls + contracts) after any such
   change; the wrong-row count is the primary gate, recovery second.
3. Resolve the CC-BY-NC licensing question before any pilot use.

## Reproduce

Offline census: scratch runner under `backend/out/reality/rerank_measure/`. Live:
`uv run python -m scripts.reality.annual_reports --rerank [--docs <one>]` and
`uv run python -m scripts.reality.digital_reality --rerank` (tunnel + selfhosted env; runners
hard-fail on external connections). Suites at head: offline 339 passed/1 skipped, isolation
47, rerank-marked real-model test passes.
