# Evidence — the original eval is green per-tenant (2026-07-16)

The pilot's definition of done requires that the original eval is green **per tenant** and that
generation runs through the provider interface. Dev and eval use only synthetic, fictional BRF data
(Gjutformen 12, Sjöutsikten 7) — no personal data — so the dev/eval **default** is the standard
hosted provider; the self-hosted, EU-resident path is forced only in `BRF_MODE=pilot` with real
data. Both providers are exercised below against the same `pick_provider()` interface — a one-line
endpoint swap apart.

## Default provider (hosted) — the dev/eval default

`make eval` → the standard hosted provider (logged-in `claude` CLI, or the Anthropic SDK when
`ANTHROPIC_API_KEY` is set). No env to set; no data-residency constraint (synthetic data).

### Tenant A — Brf Gjutformen 12 (`golden.json`, 46 answerable + 10 unanswerable)

| metric | value | gate | status |
|---|---|---|---|
| recall@6 | 1.000 (46/46) | ≥ 0.85 | ✅ |
| answer_rate (answerable) | 1.000 | — | — |
| citation_verification_rate | 1.000 | ≥ 0.90 | ✅ |
| highlight_correctness | 0.978 | ≥ 0.90 | ✅ |
| citation_doc_accuracy | 1.000 | — | — |
| false_answer_rate | 0.000 | ≤ 0.00 | ✅ |

Wall-clock 216 s. One highlight miss (`g14`) — the same item misses on the local model too, so it
is a highlight-resolution quirk in that passage, not a provider difference. Zero false answers.
(Per the confirming-run scope, tenant B was not separately re-run on the hosted default this pass;
its per-tenant greenness is proven on the egress-proof provider below.)

## Egress-proof provider (local Gemma via Ollama) — proves zero external calls

`make eval-selfhosted` / `make eval-b-selfhosted` → `gemma4:e4b` served by local Ollama at
`http://127.0.0.1:11434/v1`, through the same `OpenAICompatProvider` a production EU host would use.
`--network-audit` instruments `socket.connect` and hard-fails on any non-loopback connection, so
"no document text left the machine" is a passing tripwire, not an assertion. Running the golden set
on **both** tenants here covers "green per-tenant" end to end.

### Tenant A — Brf Gjutformen 12

| metric | value | gate | status |
|---|---|---|---|
| recall@6 | 1.000 (46/46) | ≥ 0.85 | ✅ |
| citation_verification_rate | 0.981 | ≥ 0.90 | ✅ |
| highlight_correctness | 0.978 | ≥ 0.90 | ✅ |
| false_answer_rate | 0.000 | ≤ 0.00 | ✅ |

Network audit: 3 connections, **0 external** (all to `127.0.0.1:11434`). One false refusal (`g24`,
the model rejected its own quote so the orchestrator refused rather than answer ungrounded) and one
highlight miss (`g14`) — both inside the gates. Wall-clock ≈ 55 min (the local 4B model serializes
≈ 40–70 s/answer).

### Tenant B — Brf Sjöutsikten 7 (`golden_b.json`, 28 answerable + 7 unanswerable)

Corpus B is deliberately disjoint from A (different org.nr, loans, bank, vendors) so any bleed would
be visible.

| metric | value | gate | status |
|---|---|---|---|
| recall@6 | 1.000 (28/28) | ≥ 0.85 | ✅ |
| answer_rate (answerable) | 0.964 | — | — |
| citation_verification_rate | 1.000 | ≥ 0.90 | ✅ |
| highlight_correctness | 0.963 | ≥ 0.90 | ✅ |
| false_answer_rate | 0.000 | ≤ 0.00 | ✅ |

Network audit: 3 connections, **0 external** (all to `127.0.0.1:11434`). One false refusal (`g07`,
gated out at the low-relevance step) and one highlight miss (`g15`) — both inside the gates. Zero
false answers. Wall-clock ≈ 38 min.

## Reproduce

```
make eval               # tenant A, hosted default (dev/eval)
make eval-b             # tenant B, hosted default
make eval-selfhosted    # tenant A, local Gemma + network audit (egress proof)
make eval-b-selfhosted  # tenant B, local Gemma + network audit (egress proof)
```

`eval/last_run.json` (metrics) and `eval/network_audit.json` (egress proof) are git-ignored run
artifacts, so their numbers are transcribed here.
