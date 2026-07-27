# Live pilot evidence — real-corpus gate on the XS-36 hygiene commit (2026-07-27)

## Verdict

**READY.** The unchanged BP3 real-corpus gate, re-run after XS-36's handover-hygiene
changes. Its purpose is twofold: confirm that correcting the OCR message and adding
artifact metadata did not disturb gate behavior, and produce an artifact that quotes
cleanly — the XS-35 review could not tie the previous artifact to its commit except
through prose and the file's mtime.

No gate code, threshold, question, refusal rule or network-audit semantic was changed.

## Commit and environment

Unlike earlier runs, the commit pin is **inside the artifact** rather than asserted
around it:

```json
{
  "configured_model": "gemma4:e12b",
  "configured_runtime_label": "agenntserver",
  "configured_llm": "selfhosted",
  "embedder": "model2vec",
  "timestamp_utc": "2026-07-27T20:56:26Z",
  "commit": "710cf1c77149a3004c4bbe7f71a00516a87a2824",
  "dirty": false,
  "branch": "feat/pilot-e2e-acceptance"
}
```

`dirty: false` is part of the claim: the run is pinned to that commit because the
worktree was clean when it executed.

`configured_*` is deliberate wording. These are the values the client was configured
with, not values the server proved. The runtime is never asked to attest its own
identity — that is [XS-37](https://linear.app/ai-sprints/issue/XS-37), parked
post-pilot. `BRF_LLM_BASE_URL` is intentionally excluded from the artifact: it can
carry tunnel topology, and the network audit already records which endpoints were
reached.

- Host: Fedora 44 (`7.1.5-200.fc44.x86_64`).
- Model service: Gemma 4 12B via llama.cpp on `agenntserver`, reached through
  `ssh -N -L 8000:127.0.0.1:8000 agenntserver`. The forwarded `/v1/models` endpoint
  advertised a single model matching the Gemma 4 12B GGUF weights before the run.

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
  --out out/xs36-hygiene-rerun
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

Identical to the `a1960b7` run recorded in
[pilot-live-gemma4-12b-2026-07-27.md](pilot-live-gemma4-12b-2026-07-27.md) and to the
independent XS-35 re-run. `q01`'s known non-verbatim-quote limitation is still
correctly rejected by the grounding verifier rather than silently passed.

## Ingestion

- 2 born-digital documents ingested into the temporary Q&A tenant.
- 7 scanned documents skipped for the ingestion-smoke check. The artifact records the
  reason verbatim as:

  ```text
  tesseract-binären saknas (Fedora: sudo dnf install tesseract tesseract-langpack-swe)
  ```

  This is the corrected message. The previous artifact carried a malformed word and
  macOS-only `brew` guidance on a Fedora host; see the note in the `a1960b7` evidence.

## Network audit

Network audit: 1 connection, 0 external. The only recorded endpoint was the loopback
SSH forward (`127.0.0.1:8000`).

## Reproducibility boundary

This gate cannot be run from a clean checkout. It reads the association's real PDFs
from the gitignored `DONT_PUSH_brf_stuff/` and requires a reachable `gemma4:e12b`
runtime on `agenntserver`. That is an accepted, documented limit rather than hidden
state — the corpus is customer material that may contain personal data and does not
belong in the repository. The consequence, stated plainly: only someone with both
corpus and runtime access can re-verify this particular result. Everything else in the
project's local verification runs from a clean checkout after `make setup` alone.

## Scope note

The raw `model_readiness.json` and per-question diagnostic detail remain in the
gitignored `backend/out/xs36-hygiene-rerun/` directory and are not reproduced here,
consistent with the redaction practice in the earlier evidence.
