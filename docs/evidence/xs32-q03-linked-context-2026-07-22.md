# XS-32 evidence — q03 linked table context (2026-07-22)

## Verdict

**READY.** The unchanged live readiness gate now exits 0 with the intended
`selfhosted` / `gemma4:e12b` runtime. q03 is answered with two independently
verified, resolvable citations; q11 still refuses safely; the network audit
records zero external connections.

No private filename, document text, answer text, party name, document id,
tenant data, credential, cookie, or private network address is stored here.
Exact prompts and model output remain only in gitignored
`backend/out/xs32/` artifacts.

## Instrumented baseline

Command:

```bash
cd backend
BRF_MODE=pilot \
BRF_LLM=selfhosted \
BRF_LLM_BASE_URL=http://127.0.0.1:8000/v1 \
BRF_LLM_MODEL=gemma4:e12b \
BRF_LLM_RUNTIME_LABEL=agenntserver \
BRF_EMBEDDER=model2vec \
uv run python -m scripts.trace_q03 \
  --network-audit \
  --out out/xs32/q03-baseline
```

Observed stage chain:

| Stage | Baseline result |
|---|---|
| Runtime | pilot, selfhosted, Gemma 4 12B, intended runtime label |
| Chat template | system role supported; template fingerprint captured; 8192-token context |
| Retrieval | q03 task rows at production ranks 1 and 4 |
| Context assembly | task row present; same-document responsibility legend absent |
| Diagnostic census | legend at rank 8, outside unchanged `topK=6` |
| Model raw output | non-empty JSON object, one citation supplied |
| Structured parse | successful; model set `insufficient_data=true` |
| Citation verification | not reached because the refuse behavior accepts the model's insufficiency decision first |
| Numeric grounding | not reached because the response was already a refusal |
| Final selection | `insufficient_data` |
| Network audit | 2 loopback connections, 0 external |

The private raw output explicitly distinguished the row from its missing
legend: the model found the annual-report task and cited it, but correctly
declined to identify a responsible party without the code definition. This
rules out the chat template, JSON parser, citation resolver, numeric grounding,
and final refusal selector as the first failing stage.

## Root cause

The document represents responsibility as a join across two real source
locations:

1. a coded task row; and
2. an earlier same-document legend defining the responsibility codes.

Query-based top-K retrieval surfaced the task row but not the legend because
the legend has little lexical overlap with the question. Raising `topK`,
lowering `minRelevance`, changing weights, or weakening refusal would be broad
and would obscure the actual document structure.

## Fix

`app.linked_context.append_linked_table_legends` performs deterministic
document-structure closure after the normal relevance gate:

- it recognizes only a responsibility-shaped legend with at least two quoted
  single-letter codes;
- it requires a retrieved leaf table row to use one of those exact codes;
- it links only a legend from the same tenant snapshot and same document;
- it appends at most one legend per source document;
- it leaves the original hit order, scores, `topK`, `minRelevance`, retrieval
  weights, reranker setting, prompt contract, citation verifier, numeric
  grounding, and refusal behavior unchanged;
- the legend remains an ordinary source chunk, so the model must cite it and
  the citation must resolve verbatim to its own PDF page.

## Instrumented result after the fix

The same trace command, writing to `out/xs32/q03-linked-context`, produced:

| Stage | Result after fix |
|---|---|
| Production retrieval | unchanged: six ranked hits, target rows at ranks 1 and 4 |
| Linked context | same-document legend appended after the six ranked hits |
| Prompt | task row present and responsibility legend present |
| Model raw output | valid JSON, `insufficient_data=false`, two citations |
| Citation verification | 2 verified, 0 rejected, two distinct source pages |
| Highlight resolution | 5 non-empty rectangles across the two citations |
| Numeric grounding | reached and passed |
| Provider identity | `selfhosted`, `gemma4:e12b` |
| Network audit | 2 loopback connections, 0 external |

## Unchanged live readiness gate

```bash
cd backend
BRF_MODE=pilot \
BRF_LLM=selfhosted \
BRF_LLM_BASE_URL=http://127.0.0.1:8000/v1 \
BRF_LLM_MODEL=gemma4:e12b \
BRF_LLM_RUNTIME_LABEL=agenntserver \
BRF_EMBEDDER=model2vec \
uv run python -m scripts.model_readiness \
  --network-audit \
  --out out/xs32/readiness-after
```

Result: exit 0, `VERDICT: READY`, provider `selfhosted`.

| qid | result | verified citations | rejected |
|---|---|---:|---|
| q09 | answered | 1 | 0 |
| q08 | answered | 1 | 0 |
| q03 | answered | 2 | 0 |
| q01 | safely blocked: `grounding_failed` | 0 | 1 `quote_not_found` |
| q02 | answered | 1 | 0 |
| q11 | safely refused: `insufficient_data` | 0 | 0 |

Network audit: one loopback connection, zero external connections.

q01 remains a known, non-gating prose-control limitation; its non-verbatim
quote is still rejected. The fix did not convert that unsafe output into a
success.

## Regression verification

- focused answer/LLM/citation/readiness tests: 135 passed, 1 skipped;
- full backend: 532 passed, 1 skipped;
- auth/isolation/lifecycle: 48 passed;
- deterministic retrieval: recall@6 1.000 (46/46);
- canonical frontend: 14 passed, lint exit 0, build exit 0;
- Playwright: 11 passed;
- readiness self-test: READY, zero connections;
- fabricated self-test: expected NOT READY, exit 1, zero connections.

Private trace files remain gitignored:

- `backend/out/xs32/q03-baseline/private-trace.json`
- `backend/out/xs32/q03-linked-context/private-trace.json`
- `backend/out/xs32/readiness-after/model_readiness.json`
