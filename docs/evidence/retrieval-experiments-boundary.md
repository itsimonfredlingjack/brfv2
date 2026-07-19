# Boundary note — retrieval experiments are bounded negative findings (2026-07-19)

Two retrieval levers were measured this phase to lift annual-report financial-table rows past
the top-K refusal ceiling. Both closed negatively. **This note states the scope of those
conclusions so they are not over-read as universal.**

## What was found

- **Enrichment** (embed document year + section heading; `enriched-representation.md`):
  recovers **0/13** — the added tokens are non-discriminating (year constant per document,
  heading orthogonal to query vocabulary). The citation invariant was proven intact by test.
- **Reranker** (`reranker-license-eval.md`, `rerank-wrongrow-scoregate.md`): a *licensable*
  cross-encoder **does** recover the rows (mmarco 14/17 clean/Apache, bge 17/17), so the
  licensing worry is answered — but every reranker reintroduces **wrong-row answers** (verbatim-
  real citations on the wrong row, concentrated in `q_fee`), and the assumed mitigation (a
  cross-encoder score floor) is **refuted by measurement** (answer-bearing vs distractor scores
  overlap; misfire distractors score high). `rerankEnabled` stays default-off.

## These findings are bounded — exhausted for, and only for:

- **This architecture:** hybrid BM25 ⊕ static/hashed-embedding retrieval + a single-vector
  reranking stage, with citation = verbatim-verified span. A different retrieval architecture
  (e.g. late-interaction/ColBERT-style, table-structure-aware indexing, or a learned
  answer-alignment gate) was not tried and is not ruled out.
- **This corpus:** 4 born-digital Swedish annual reports (95 pages), where several asked
  figures (notably fee-per-m²) are **not present as labeled value rows at all** — a data
  property, not purely a retrieval failure.
- **This evaluation set:** 17 gradeable `(doc, financial-question)` pairs via the deterministic
  word-index locator; 24 live questions. A larger/broader eval could shift the numbers.
- **This pilot deadline:** off-the-shelf, no-new-training, no-architecture-change options only.
  Fine-tuning a longer-context clean cross-encoder (`mdeberta-v3-base`, MIT) or building an
  answer-alignment gate were explicitly deferred, not disproven.

**Not claimed:** that enrichment or reranking cannot help annual-report retrieval in general,
that no licensable reranker is good enough, or that the recall ceiling is permanent. Only that,
**within the constraints above, neither lever is a pilot-ready win**, and the product's
safe-refuse behavior is the correct default for the pilot.

## What would change the conclusion (post-pilot)

The dominant remaining failure (`q_fee` wrong-row) is a **grounding/answer-alignment** problem,
not a ranking one: the model answers from a plausible neighbor when the asked-for figure is not
a clearly-labeled row. The tracked post-pilot item (see Linear) is to verify **semantic
agreement between the user's requested metric and the cited row's label** before a citation is
accepted — the lever that could let a (now-known-licensable) reranker be enabled safely. Until
that exists, further retrieval tuning is out of scope for the pilot.
