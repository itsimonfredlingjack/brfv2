# Runbook — self-hosted Gemma 4 for the pilot (EU GPU host)

What Simon stands up so the app's only generation path is a model on infrastructure
we control. The app already talks to any OpenAI-compatible endpoint via three env vars;
nothing in the app changes when the endpoint moves from a laptop to an EU server.

> **Verification tiers** (per the pilot brief). **Verified** = official primary source, accessed
> 2026-07-16. **Public-unverified** = secondary source only. **Spike-item** = confirm on the box.
> Ground-truth any figure with `ollama show gemma4:e4b` / `vllm --version` on the actual host —
> "Gemma 4" search results are polluted by look-alike domains; only ai.google.dev, ollama.com,
> and docs.vllm.ai were trusted here.

## What the app needs from the endpoint

Set these where the backend runs (see `.env.example`):

```
BRF_MODE=pilot                              # refuses to boot unless the LLM is self-hosted
BRF_LLM=selfhosted                          # or leave BRF_LLM=auto; base_url alone selects it
BRF_LLM_BASE_URL=https://llm.internal.eu/v1 # the OpenAI-compatible endpoint
BRF_LLM_MODEL=gemma4:e4b                     # exact served model id
BRF_LLM_API_KEY=<token>                     # if the server enforces one (vLLM --api-key)
BRF_LLM_TIMEOUT_S=300
```

The provider posts to `POST {BRF_LLM_BASE_URL}/chat/completions` with
`response_format={"type":"json_object"}` and `temperature=0`. If the server rejects
`response_format` it retries once without it (the grounding contract already demands JSON, and
`parse_llm_json` tolerates prose-wrapped JSON), so JSON mode is a bonus, not a hard dependency.

## The model

- **Gemma 4**, open weights, **Apache-2.0** license — commercial use permitted. *(Verified:
  ai.google.dev/gemma/apache_2; huggingface.co/google/gemma-4-E4B-it.)* One caveat worth a
  lawyer's five minutes: a separate legacy "Gemma Terms of Use" page still exists; press coverage
  says Gemma 4 moved to plain Apache-2.0, but confirm which text governs the weights before
  production. *(Public-unverified.)*
- **Variant for the pilot: `gemma4:e4b`** ("Effective 4B", ~8B with embeddings), 128K context.
  *(Verified: ai.google.dev/gemma/docs/core/model_card_4.)* This is what the demo eval ran on
  (local Ollama, Apple M4). It answers the Swedish grounding contract correctly. E4B is the
  quality/VRAM sweet spot for a single-BRF pilot; **26B A4B or 31B** are the upgrade path if
  Swedish answer quality proves insufficient — same endpoint, change `BRF_LLM_MODEL`.
- **Swedish support: Spike-item.** The model card claims "35+ languages out of the box" and
  "140+ pre-trained" but does not name Swedish. The demo answers were fluent and correctly
  grounded, but judge Swedish quality on the real corpus before committing. The eval harness
  (`make eval-selfhosted`) is exactly that judgment tool — it runs the golden set through this
  endpoint. (Plain `make eval` uses the standard hosted provider and is the dev/eval default.)
- **VRAM (weights only, excludes KV-cache):** E4B ≈ 17.9 GB BF16 / 8.9 GB 8-bit / 4.5 GB Q4.
  *(Verified: ai.google.dev/gemma/docs/core; the card notes figures vary by inference tool.)*

## Option A — Ollama (simplest; what the demo used)

*(Verified: docs.ollama.com unless noted.)*

```bash
# On the GPU host:
curl -fsSL https://ollama.com/install.sh | sh
ollama pull gemma4:e4b                      # confirm size with `ollama list`

# Serve on the network (default bind is 127.0.0.1 only):
sudo systemctl edit ollama.service
#   [Service]
#   Environment="OLLAMA_HOST=0.0.0.0:11434"
sudo systemctl restart ollama
```

- OpenAI-compatible endpoint: `http://<host>:11434/v1` → `BRF_LLM_BASE_URL`. JSON mode supported.
- **Ollama has no built-in auth** *(Verified: docs.ollama.com/faq — it warns against exposing
  11434 publicly).* Do NOT expose 11434 to the internet. Put it behind one of: a private
  network/VPN (WireGuard) with the app; or a reverse proxy (Caddy/nginx) terminating TLS and
  requiring a bearer token that you also set as `BRF_LLM_API_KEY`. The app sends the token; the
  proxy enforces it. Ollama itself ignores the token.

## Option B — vLLM (higher throughput, native API-key auth)

*(Verified: docs.vllm.ai/projects/recipes/.../Gemma4; the recipe currently recommends a nightly
build — confirm the stable version with `pip index versions vllm` on the host: Spike-item.)*

```bash
uv pip install -U vllm --pre --extra-index-url https://wheels.vllm.ai/nightly/cu129   # per recipe
vllm serve google/gemma-4-E4B-it \
  --dtype auto \
  --max-model-len 131072 \
  --api-key "$BRF_LLM_API_KEY"                # native bearer-token enforcement
```

- Endpoint `http://<host>:8000/v1` → `BRF_LLM_BASE_URL`; set the same token as `BRF_LLM_API_KEY`.
- Structured output: current docs use `response_format={"type":"json_schema",...}`; plain
  `json_object` mode is **Spike-item** (test it — the app degrades gracefully if unsupported).

## Host sizing

- Single 24 GB GPU (e.g. one L4/A10-class card) comfortably serves E4B. *(VRAM figures Verified;
  the "24 GB is comfortable for E4B" framing is Public-unverified — the vLLM recipe's guidance.)*
- **EU location** is the point: Hetzner (DE/FI) GPU servers or an EU OVH/Scaleway GPU instance.
  The research report recommends Hetzner for low-cost EU self-host. Keep the LLM host and the app
  in the same EU network so document text never crosses a border or a third party.

## Proving zero external LLM calls

`make eval-selfhosted` runs with `--network-audit`: it instruments every TCP connect from the eval
process and hard-fails if anything connects outside loopback + `BRF_LLM_BASE_URL`. It writes
`backend/eval/network_audit.json` (total connections, distinct endpoints, any external). A clean
run is the evidence that document text reached only the self-hosted endpoint. For the app process
itself in production, pair this with a host firewall egress-deny (below) — belt and braces.

## Deploy-step notes (not built this phase, per brief)

- **Full-disk encryption**: enable LUKS on the data volume that holds `backend/data/` (PDFs,
  extraction JSON, `auth.db`) at provisioning time. The app stores documents as plain files;
  encryption at rest is an infrastructure responsibility. Back up the LUKS key out-of-band.
- **Egress firewall**: on the app host, default-deny outbound; allow only the LLM host:port and
  OS updates. This makes "no external LLM call" a network invariant, not just an app behavior.
- **TLS**: terminate HTTPS at a reverse proxy in front of both the app and the LLM endpoint.
- **Session cookie**: set `Secure` on the session cookie once served over HTTPS (the app sets
  HttpOnly + SameSite=Lax today; add Secure via the proxy or a one-line change when TLS is on).
