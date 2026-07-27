# Live pilot evidence — Gemma 4 12B and local BRF corpus (2026-07-22)

## Verdict

**NOT READY.** The endpoint, runtime identity, network boundary, full synthetic golden evaluation,
live browser answer/refusal/citation-highlight journey, upload/ingestion, and tenant switching all
passed. The mandatory real-corpus readiness gate did not: the live model refused `q03`
(`cell_value`) even though the source-bearing chunks were present at retrieval ranks 1, 2, 4, and
6. A prose control (`q01`) also produced a non-verbatim quote that the grounding verifier correctly
rejected.

This report therefore does not claim that the live BRF pilot passed. It contains no real filenames,
source passages, personal data, credentials, cookies, or private network addresses. The companion
machine-readable packet is `docs/evidence/pilot-live-gemma4-12b-2026-07-22.json`.

## Repository baseline

- Backend repository: `feat/pilot-e2e-acceptance` at `e822211` before this evidence commit.
- Canonical frontend repository: `feat/model-identity-indicator` at `2067523`, clean.
- The previous deterministic acceptance work was not rebuilt or redesigned.
- Two unrelated untracked planning/research files in the backend repository were preserved and
  excluded.

## Runtime and tunnel identity

The local forward was owned by an `ssh` process, had the expected local-forward shape, and targeted
the intended configured host alias. The forwarded OpenAI-compatible `/models` endpoint advertised
one model, matching Gemma 4 12B. No advertised model identifier or remote address is stored here.

`GET /api/health` reported:

| field | value |
|---|---|
| status | `ok` |
| mode | `pilot` |
| provider | `selfhosted` |
| model | `gemma4:e12b` |
| runtime label | `agenntserver` |
| ready | `true` |
| warning | `null` |

The live answer responses independently reported `provider=selfhosted` and `model=gemma4:e12b`.
The audited processes connected only to the loopback SSH forward. No connection to a fake, disabled,
hosted, or ambient local 4B provider was observed.

## Corpus scope

The protected local folder contained nine PDFs: two born-digital and seven scanned, totalling
19,914,078 bytes. The aggregate SHA-256 over the sorted per-file hashes was
`2764b79feed939bbdcd23e8d07acec6912ea047a6e74760ef7251fd67e6ae7d4`.

Only counts and the aggregate fingerprint are recorded. Individual filenames, hashes, extracted
text, answers, and citations remain in gitignored local artifacts or temporary storage.

The live readiness harness ingested:

- 2 born-digital documents into the temporary Q&A tenant;
- 7 scanned documents into isolated ingestion-smoke tenants;
- 63 scanned pages, 9,572 retained words, and 74 scanned chunks.

## Real-corpus live readiness

Production-parity command:

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
  --out out/pilot-live-2026-07-22/model2vec-live
```

Result: exit `1`, `VERDICT: NOT READY`, provider `selfhosted`.

| qid | class | result | verified citations | rejected |
|---|---|---:|---:|---|
| `q09` | org-number fragment | answered | 1 | 0 |
| `q08` | party-name fragment | answered | 1 | 0 |
| `q03` | cell-value fragment | refused: `insufficient_data` | 0 | 0 |
| `q01` | prose control | refused: `grounding_failed` | 0 | 1 `quote_not_found` |
| `q02` | prose control | answered | 1 | 0 |
| `q11` | unsupported control | safely refused | 0 | 0 |

Network audit: one connection to the loopback tunnel, zero external connections.

The hashed-embedder diagnostic produced the same question outcomes. This rules out an embedder swap
as a remedy.

## Failure isolation

The committed deterministic harness was rerun on the same current corpus:

```bash
cd backend
uv run python -m scripts.model_readiness \
  --selftest \
  --out out/pilot-live-2026-07-22/harness-selftest
```

Result: exit `0`, `VERDICT: READY`, all three fragment facts cited, unsupported control refused,
zero network connections. This proves that current ingestion, retrieval, citation resolution, and
verdict computation can represent and verify the missing `q03` fact.

A redacted retrieval diagnostic placed `q03`'s target chunks at ranks 1, 2, 4, and 6. The model still
refused when `topK` was separately constrained to 1, 3, and 6. A source-agnostic instruction to
inspect table label/value fragments before refusing did not change the result. This is evidence of
a live model compliance/capability limitation, not evidence for a reranker or broad retrieval change.

No application code or assertion was changed in response.

## Full live-provider golden evaluation

```bash
BRF_MODE=pilot \
BRF_EMBEDDER=model2vec \
BRF_LLM_BASE_URL=http://127.0.0.1:8000/v1 \
BRF_LLM_MODEL=gemma4:e12b \
BRF_LLM_RUNTIME_LABEL=agenntserver \
make eval-selfhosted
```

Result: exit `0` in 255.6 seconds.

| metric | result | gate |
|---|---:|---:|
| recall@6 | 1.000 (46/46) | >= 0.85 |
| answer rate | 1.000 | informational |
| citation verification | 1.000 | >= 0.90 |
| highlight correctness | 0.978 | >= 0.90 |
| citation document accuracy | 1.000 | informational |
| false-answer rate | 0.000 | <= 0.00 |

There was one known synthetic highlight miss, `g14`, inside the configured gate. The audit recorded
three loopback-tunnel connections and zero external connections. It regenerated the intended raw,
gitignored artifacts:

- `backend/eval/last_run.json`
- `backend/eval/network_audit.json`

The full golden set is synthetic. Its green result complements but does not override the failed
real-corpus readiness verdict.

## Live browser smoke

The browser smoke used Chromium through the Playwright CLI, a temporary backend store, the canonical
frontend, `BRF_MODE=pilot`, the live 12B endpoint, and the production `model2vec` embedder. The two
born-digital corpus documents were copied to a private temporary directory under generic filenames
and uploaded through the real browser file input. The temporary environment was cleaned afterward.

Observed results:

- login and active-association selection passed;
- the UI displayed `Gemma 4 12B` and `Self-hosted · agenntserver`;
- both uploads returned HTTP 200 with positive page, word, and chunk counts;
- the temporary Q&A tenant was restricted to those two uploaded documents before asking;
- an answerable question returned HTTP 200, `selfhosted`, `gemma4:e12b`, one verified and resolvable
  citation, zero rejected citations, and page 3;
- clicking the citation opened the generically named PDF on page 3;
- two citation overlays were visible and both the first overlay's width and height were positive;
- the unsupported question safely refused with `insufficient_data`, zero citations, and the visible
  `Otillräckligt underlag` message;
- switching association removed all prior corpus filenames, citations, and pending response state.

No source text, answer text, real filename, cookie, or private address was copied into this packet.

## Tenant isolation regression check

```bash
make test-isolation
```

Result: `48 passed, 6 warnings in 4.81s`, exit `0`. The warnings are the existing PyMuPDF/SWIG and
Starlette/httpx deprecations.

## Network-audit outcome

The same `socket.connect` auditor used by the existing evaluation tooling was active during the live
real-corpus readiness and full golden runs. It permits only loopback and the explicitly configured
self-hosted endpoint and raises on any other TCP connection.

| run | total connections | external connections |
|---|---:|---:|
| real-corpus readiness | 1 | 0 |
| deterministic harness self-test | 0 | 0 |
| full live-provider golden eval | 3 | 0 |

`backend/eval/network_audit.json` contains only the loopback base URL and loopback endpoint. The
companion tracked JSON records the endpoint class as `loopback_ssh_tunnel` rather than retaining any
remote address.

## Genuine limitations and next prerequisite

The service is reachable, correctly identified, and able to complete the core browser journey, so
there is no missing tunnel command to report. The remaining blocker is model behavior: the intended
Gemma 4 12B runtime must answer the mandatory `q03` fragment-fact question with at least one verified
citation while preserving the safe refusal on `q11`.

After changing or reconfiguring the model service, rerun exactly:

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
  --out out/pilot-live-2026-07-22/model2vec-live-rerun
```

Do not report the live pilot as passed unless that command exits 0 with `VERDICT: READY`. A future
investigation may inspect the server's Gemma chat-template/structured-output behavior, but this run
does not justify weakening citation verification, enabling fallback, or changing retrieval/reranking.
