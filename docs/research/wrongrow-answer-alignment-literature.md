# Research — killing confident wrong-row answers (literature review, 2026-07-20)

Feeds **XS-31** (post-pilot: semantic label matching for financial-table citations). Not
implementation — a literature scan to ground XS-31's design before that phase starts.

**Method:** automated web research — 5 search angles, 23 primary sources fetched, 102 claims
extracted, adversarial 3-vote verification attempted on the top 25. **13 claims were
independently confirmed (3-0)**; 2 were refuted and dropped; **10 more come from a real fetched
primary source but only got a single extraction pass — the second/third verification vote hit a
session limit before completing.** Those 10 are listed separately and should be treated as
"sourced but not adversarially checked," not as verified fact. Full run log:
`backend/out/reality/` is not it — this run's raw journal is session-local; treat this document
as the durable record.

## Confirmed (3-0 adversarially verified)

**Answerability / calibrated abstention:**
- "Sufficient context" (Joren et al., ICLR 2025, [2411.06037](https://arxiv.org/abs/2411.06037)):
  a classifier can label whether retrieved context contains enough information to answer a
  query — **without needing a ground-truth answer**. Large models answer well when context is
  sufficient but **confidently answer wrong instead of abstaining when it isn't** — this is
  exactly our failure mode. Small models (paper tests Gemma 2, Mistral) hallucinate or abstain
  even when context IS sufficient — i.e. **a small local LLM like our Gemma 12B cannot be
  trusted to self-judge sufficiency**; the check needs to live outside the generator.
- SQuAD 2.0 ([1806.03822](https://arxiv.org/abs/1806.03822)): established that a QA system must
  detect "no supported answer in this text" and abstain, not just extract the nearest-sounding
  span — and that unanswerable questions were deliberately written to *look* like answerable
  ones, which is structurally our `q_fee` problem (a plausible neighbor row, not a garbled one).
- SURE-RAG ([OpenReview](https://openreview.net/forum?id=Jjr2Odj8DJ)): reframes the RAG answer
  step as **evidence-sufficiency classification** (supports / refutes / insufficient) — answer
  only if classified "Supported" AND a confidence score clears a threshold, else abstain.
  Important: it explicitly argues **sufficiency is a set-level property of the whole retrieved
  context, not a per-passage score** — directly explaining why our per-chunk cross-encoder score
  floor failed (it's the wrong granularity, not just the wrong threshold). Its verifier is a
  self-hostable base-scale NLI cross-encoder (DeBERTa-v3-base) — no cloud API — but the
  aggregator on top **is a small trained classifier**, i.e. this approach needs a light fine-tune.
- CalibRAG ([2411.08891](https://arxiv.org/abs/2411.08891)): names the general version of our
  finding — standard RAG retrieval optimizes for query-relevance only and "does not ensure the
  resulting decision is well-calibrated." Relevance ≠ correctness is the literature's framing of
  exactly what our score-gate experiment measured.
- A counterfactual-prompting approach ([ACL 2024 findings](https://aclanthology.org/2024.findings-emnlp.133/))
  gets a RAG system to self-assess uncertainty by perturbing retrieval quality and observing the
  answer's sensitivity — **no fine-tuning required**, prompt-only.
- FT-RAG ([2605.01495](https://arxiv.org/abs/2605.01495)): decomposes tables into entry-level
  semantic units in a structured graph so label↔value association survives into retrieval — one
  concrete table-serialization technique (confirmed only at the "it does this" level; its
  reported accuracy gains are in the unverified list below).

## Sourced but NOT independently verified (session limit — treat as leads, not facts)

These came from a single real fetch of a real paper (not fabricated), but only one extraction
pass ran before the adversarial re-check hit the session limit. Worth reading before relying on
the number:

- **FinGround** ([2604.23588](https://arxiv.org/pdf/2604.23588)) — reportedly aligns each atomic
  claim to evidence via a cross-encoder fine-tuned on ~8,400 financial NLI examples (TAT-QA +
  FinQA), claimed 87.2% alignment F1; and separately reports that **generic NLI fails on
  ratio/margin claims even when the correct row IS retrieved** — i.e. the failure is reasoning,
  not retrieval, for that claim class. If true, this is the closest match to "semantic
  answer-alignment" as asked for — but it implies a **fine-tune is required** (not off-the-shelf).
- **TAT-QA / TAGOP** ([ACL 2021](https://aclanthology.org/2021.acl-long.254.pdf)) — reportedly
  grounds answers by sequence-tagging the supporting cells against explicit row/column headers,
  then applies an operator classifier — a structure-aware grounding pattern, not free-text
  matching.
- **RAGChecker** ([2510.24402](https://arxiv.org/pdf/2510.24402)) — reportedly decomposes both
  the reference answer and the model's response into atomic "claims" and checks entailment
  between them, separating retrieval failures (low claim recall) from generation failures (low
  faithfulness) — a diagnostic framework, not a runtime gate, but useful for re-measuring XS-31.
- **Cell-level retriever** ([2206.08506](https://arxiv.org/pdf/2206.08506)) — reportedly
  retrieving individual gold cells instead of whole rows reduces contamination from
  similar/unrelated cells in the same row feeding a numerical-reasoning generator — directly
  targets our exact failure shape (a real row, wrong cell/line).
- **A direct contradiction that needs resolving, not just citing**: one source
  ([2506.12071](https://arxiv.org/html/2506.12071v1)) reportedly found a cross-encoder reranker
  *underperforms* simpler hybrid BM25 on mixed text+table financial documents, while another
  ([2510.11394](https://arxiv.org/html/2510.11394v1)) reportedly found adding a reranker
  (Cohere rerank-v3.5) *raised* faithfulness and roughly halved hallucination. Both are
  unverified. This tension mirrors our own result (reranking recovers rows but adds wrong-row
  answers) — worth reading both papers directly before citing either.

## What this means for XS-31 (not decided here — input to that phase's design)

Three converging directions, roughly in order of "closest to what we already have":

1. **Sufficiency/abstention as a set-level, non-generator check** (SURE-RAG's framing) — the
   confirmed literature agrees a per-passage score floor is the wrong tool (matches our own
   measurement exactly); the check needs to look at the *whole* answer-plus-evidence set, and
   the small model itself cannot be trusted to self-judge sufficiency.
2. **Label/row structural alignment before citation is accepted** — TAT-QA/TAGOP-style: verify
   the cited row's header/label against the question's target metric using structure, not just
   whether the quote is verbatim-real. This is closest to what XS-31 already asks for
   ("semantic label matching"), but the two sourced techniques that do this precisely (FinGround,
   cell-level retriever) both imply a small fine-tune, conflicting with the "no new training"
   preference — worth deciding in XS-31 whether that tradeoff is acceptable.
3. **A lightweight self-hostable NLI cross-encoder as a claim-vs-evidence check**, confirmed
   feasible (SURE-RAG uses DeBERTa-v3-base, EU-hostable, no cloud API) — but note this checks
   *entailment of the answer text*, not *does this row's label match the question* — it's a
   faithfulness gate, not automatically an answer-alignment gate. Don't conflate the two.

## Honest limits of this research pass

Only 25 of 102 extracted claims got a verification attempt; only 13 completed adversarial
verification before the session limit. Synthesis (semantic dedup across all 102) did not run.
This is a first pass to ground XS-31, not a literature review to build directly from — read the
primary sources above before committing to an implementation.
