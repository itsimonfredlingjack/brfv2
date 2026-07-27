# Live pilot evidence — Gemma 4 12B real-corpus gate refresh after XS-33 (2026-07-27)

## Verdict

**READY.** This is a fresh, commit-pinned rerun of the unchanged BP3 real-corpus readiness
gate, requested by XS-34 to confirm the gate still passes against the live `gemma4:e12b`
runtime after the post-baseline retrieval/context-linking fix (XS-32) and the embedder
lifecycle change in `b939d50` (XS-33). No gate code, threshold, question, or refusal rule
was changed to obtain this result.

## Commit and environment

- Repository: `feat/pilot-e2e-acceptance` at `a1960b7` (working tree clean; resolved via
  `git rev-parse HEAD` immediately before the run, not assumed from the short SHA in prior
  handoffs).
- Host: Fedora 44 (`7.1.5-200.fc44.x86_64`), the same machine documented in
  [fedora-clean-checkout-2026-07-27.md](fedora-clean-checkout-2026-07-27.md).
- Model service: Gemma 4 12B via llama.cpp on `agenntserver`, reached through
  `ssh -N -L 8000:127.0.0.1:8000 agenntserver`. The forwarded `/v1/models` endpoint
  advertised exactly one model matching the Gemma 4 12B GGUF weights before the gate ran.
- This run supersedes the 2026-07-22 real-corpus result as the reference for BP5 criterion
  4; that result predates `b939d50` (shared embedder instance) and is preserved unmodified
  at [pilot-live-gemma4-12b-2026-07-22.md](pilot-live-gemma4-12b-2026-07-22.md) and its
  XS-32 correction at
  [xs32-q03-linked-context-2026-07-22.md](xs32-q03-linked-context-2026-07-22.md).

## Command (unchanged from the established gate)

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
  --out out/pilot-live-2026-07-27/model2vec-live
```

Result: exit `0`, `VERDICT: READY`, provider `selfhosted`.

## Question results

| qid | class | result | citations | rejected |
|---|---|---:|---:|---|
| `q09` | org-number fragment | answered | 1 | 0 |
| `q08` | party-name fragment | answered | 1 | 0 |
| `q03` | cell-value fragment | answered | 2 | 0 |
| `q01` | prose control | refused: `grounding_failed` | 0 | 1 `quote_not_found` |
| `q02` | prose control | answered | 1 | 0 |
| `q11` | unsupported control | safely refused: `insufficient_data` | 0 | 0 |

This matches the shape of the XS-32-corrected 2026-07-22 READY result: all three mandatory
fragment-fact questions answered with verified citations, the unsupported control still
safely refused, and `q01`'s known non-verbatim-quote limitation still correctly rejected by
the grounding verifier rather than silently passed. No threshold or refusal rule was
loosened to reach this outcome.

## Ingestion

- 2 born-digital documents ingested into the temporary Q&A tenant.
- 7 scanned documents skipped for the ingestion-smoke check. The preserved artifact
  records this reason verbatim:

  ```text
  tesseract-binärendon saknas (brew install tesseract tesseract-lang)
  ```

  This Fedora host has no `tesseract` installed, consistent with the documented,
  intentional OCR skip in
  [fedora-clean-checkout-2026-07-27.md](fedora-clean-checkout-2026-07-27.md) and
  [MVP-STATUS.md](../MVP-STATUS.md). OCR is not part of the pilot loop.

  The message itself was defective — a malformed word and macOS-only `brew`
  guidance on a Fedora host. XS-35 flagged it, and an earlier revision of this
  document quoted it in cleaned-up form, which is not how preserved evidence
  should be cited. The string above is exactly what the artifact contains. The
  product message was corrected in `710cf1c` (XS-36) and the gate re-run against
  the corrected code is recorded in
  [pilot-live-gemma4-12b-2026-07-27-xs36.md](pilot-live-gemma4-12b-2026-07-27-xs36.md).

## Network audit

Network audit: 1 connection, 0 external. The only recorded endpoint was the loopback SSH
forward (`127.0.0.1:8000`).

## Runtime identity

The forwarded `/v1/models` response, checked immediately before the gate ran, advertised a
single model matching the Gemma 4 12B weights family. The gate was invoked with
`BRF_LLM=selfhosted`, `BRF_LLM_MODEL=gemma4:e12b`, `BRF_LLM_RUNTIME_LABEL=agenntserver`,
matching the production-parity identity used throughout this pilot's evidence.

## Timestamp

Run completed 2026-07-27, commit `a1960b7`.

## Scope note

Per XS-34's autonomy instructions, this run only refreshes evidence for the unchanged gate.
No application, retrieval, or grounding code was touched to produce this result. The raw
`model_readiness.json` and per-question diagnostic detail remain in the gitignored
`backend/out/pilot-live-2026-07-27/` directory and are not reproduced here, consistent with
the redaction practice in the 2026-07-22 evidence.
