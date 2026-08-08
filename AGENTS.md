# Träff — agent guide

Tracked operational instructions for coding agents. **Conductor** is the source of truth for product principles, tech stack, and workflow; this file is the brownfield map and day-to-day constraints.

| Topic | Authoritative doc |
| --- | --- |
| Product vision, problem, non-goals | [`conductor/product.md`](conductor/product.md) |
| Voice, design principles, errors | [`conductor/product-guidelines.md`](conductor/product-guidelines.md) |
| Languages, clients, persistence | [`conductor/tech-stack.md`](conductor/tech-stack.md) |
| TDD, commits, review, checkpoints | [`conductor/workflow.md`](conductor/workflow.md) |
| Active work units | [`conductor/tracks.md`](conductor/tracks.md) |
| Human-facing product overview (Swedish) | [`README.md`](README.md) |

Most product docs under `docs/` and the root README are Swedish. Code, many newer technical docs, and this file are English. Both are normal.

---

## Product identity

**Träff** is grounded document Q&A and structured work for Swedish housing associations (*bostadsrättsföreningar*). Every approved answer opens the cited PDF at the exact page with the passage highlighted. Unsupported questions are **refused**, never guessed.

Träff turns fragmented board work (mail, invoices, contracts, questions, deadlines) into **source-backed, human-controlled** actions. Association content stays in Träff-controlled infrastructure (Sweden preferred, else EU/EES). See Conductor product docs for full wording.

Historical names you may still see: BRF Dokument-AI, Källa (mobile/native era). **Träff** is the current product identity. `brfv2-mockup/` is a historical directory name for the **canonical** web frontend—not a mock-only UI.

---

## Branch note

Product lines were not always merged in lockstep. **Which branch you are on determines which features exist.** Current work happens on **`feat/produktbas`** (this guide assumes it). If `src-tauri/`, `backend/app/integrations/`, invoice packages, or similar seem missing, the checkout is on an older line—not that the feature never existed. Branch table and history: README § “Grenar”, [`docs/POST-BP6-PRODUKTBAS.md`](docs/POST-BP6-PRODUKTBAS.md).

---

## Repository layout

One repo, no submodules. `make setup` from a clean clone is the full setup.

| Path | Role |
| --- | --- |
| `backend/` | Shared FastAPI app: RAG, auth, `TenantRegistry` / `Store`, domain packages (integrations, invoices, watches, tasks, website, desktop) |
| `brfv2-mockup/` | **Canonical web + desktop UI** (React/Vite). Real HTTP contract. |
| `xs_mobilapp/` | Mobile PWA: ask → grounded answer → source highlight |
| `kalla-native/` | Native Android (Expo Router + RN). See nested [`kalla-native/AGENTS.md`](kalla-native/AGENTS.md) before coding there. |
| `src-tauri/` | Tauri 2 shell + Fedora RPM packaging. Window/sidecar only; product adapter in `backend/app/desktop.py` |
| `docs/` | Architecture, runbooks, evidence, domain docs |
| `ops/` | Desktop runtime build, payload inspect, forbidden-provider rules, demo scripts |
| `conductor/` | Project context for agents (product, stack, workflow, tracks) |

### `backend/app/integrations/` is two things

1. **Vendor adapters** (smaller): Fortnox, Graph mail, OAuth, credentials, egress, connections.
2. **Inkommande post** (larger): review queue—not an inbox—intake, mailbox, threads, triage, preserve, resolve, review. See `docs/INKOMMANDE-POST.md`.

Other domains: `watches/` (Bevakningar), `invoices/` (Fakturor as cases), `tasks/` (Uppgifter—human-created only), `website/` (Hemsidan—block commands, no model-driven publish). Domain runbooks live under `docs/` (e.g. `FAKTUROR.md`, `HEMSIDA.md`, `INTEGRATIONSDOMAN.md`).

---

## Client parity (deliberate gaps)

A phone is not where a board reviews post or invoices. Do not “add X to mobile” without checking this table.

| Capability | Web/desktop (`brfv2-mockup`) | PWA | Android |
| --- | --- | --- | --- |
| Ask → grounded answer → citation | ✅ | ✅ | ✅ |
| Documents / library | ✅ | ✅ | ✅ |
| Granskning · Bevakningar · Uppgifter | ✅ | ✅ | — |
| Inkommande post · Fakturor · Hemsidan · Connections / desktop settings | ✅ | — | — |

Backend contract is shared: route changes are checked against every client that can call them, not only the screen that exists today.

---

## Core product invariants

1. **Refuse over fabricate** — no answer without a verifiable citation in the tenant’s own documents.
2. **Tenant isolation is structural** — each `brf_id` has its own store/index via `TenantRegistry`. Not a forgettable `WHERE` filter. **404, not 403**, for another tenant’s resources.
3. **Human decides, system prepares** — findings and queues, not autonomous external approvals.
4. **A write is a command** — mutate paths use locked read–validate–write (`apply` into mutate_* / cases.mutate). Lock order: domain store before `Store.lock`. Creatable-twice entities get derived ids, never ad-hoc `uuid4` for identity. Limits (single-process): `docs/INTEGRATIONSDOMAN.md` §2b.
5. **Money is `Decimal`** (JSON string), never `float`, for invoice comparisons.
6. **Read-only integrations by default** — Fortnox and Microsoft Graph are intelligence layers; adapters have no write verbs for association systems of record.
7. **Sovereign inference (product claim)** — association content is not disclosed to external model/OCR/embedding/reranking/transcription/analytics/telemetry/error-reporting services for processing. Authorised read-only intake from the association’s existing systems of record is permitted.

---

## Inference boundary

**Dual status (not a leak incident to “fix first”):** installed product paths are structurally self-hosted (pilot refuses non-`selfhosted`, desktop pins self-hosted + `model_endpoint.py`, Fedora RPM excludes hosted providers). The source tree still contains hosted Anthropic / Claude CLI support for web/dev/eval (`backend/app/llm_hosted.py`) and does not yet apply endpoint policy on every non-desktop path.

- **Track:** [`conductor/tracks/sovereign-inference-boundary/`](conductor/tracks/sovereign-inference-boundary/) — **do not implement unless the session’s task says so.** Do not reintroduce hosted product providers when doing other work.
- **Mechanisms / ADR:** `docs/adr/0002-model-endpoint-boundary.md`, `docs/DEPLOY-SELFHOSTED-LLM.md`, track spec.
- **Test providers:** offline `BRF_LLM=fake` (`backend/tests/conftest.py`); deterministic acceptance `BRF_LLM=scripted`; live pilot/demo generation uses self-hosted (e.g. tunnel + `BRF_LLM_BASE_URL`), not a silent smaller local fallback.
- External coding agents (IDE, research) may run **outside** the product runtime. They must not become product providers and must not receive association content through Träff.

---

## Integrations (adapters)

Read-only intelligence layer—not an accounting system or mail client. Domain model: `docs/INTEGRATIONSDOMAN.md`.

- **Fortnox** — supplier invoices, company info; no write verbs; egress denies non-GET (except token POST). `docs/INTEGRATION-FORTNOX.md`.
- **Microsoft Graph / Outlook** — human-selected message into the review queue; scopes `Mail.Read` etc., never send/write. `docs/INTEGRATION-OUTLOOK.md`.

---

## Commands (repo root)

```bash
make setup              # uv, backend venv, embedder weights, node_modules, Playwright chromium
make backend            # API :8787 (dev mode — see inference boundary)
make frontend           # brfv2-mockup :5173
make mobile             # xs_mobilapp :5174 (needs backend)
make test               # backend offline tests
make test-isolation     # isolation + lifecycle + auth
make eval-fast          # retrieval only, no LLM
make mobile-test        # PWA unit + lint/typecheck + e2e/a11y
```

Frontend unit: `cd brfv2-mockup && npm test` / `cd xs_mobilapp && npm test` (no `test:unit` script name). E2E: `cd brfv2-mockup && npm run test:e2e`.

Desktop, demo, and acceptance targets (`desktop-*`, `demo`, `invoice-acceptance`, `intake-acceptance`, vocabulary/rules locks): see `Makefile` and domain docs under `docs/`. Invoice/intake and much of website acceptance are **deterministic (no model)**; generated-answer desktop acceptance needs self-hosted runtime. Evidence under `docs/evidence/<RUN_LABEL>-…` — do not overwrite committed evidence casually.

---

## Platform and tooling gotchas

- **Python 3.12** required; distro Python often wrong (e.g. Fedora 3.14). **`uv` is required.**
- **Playwright** `install-deps` is apt-oriented; fails on Fedora with missing `apt-get`. Browser download is portable; use distro packages for missing system libs.
- **Rerank** optional (`uv sync --extra rerank`) — large torch/CUDA pull; off by default.
- **Ruff** not in backend venv: `uvx ruff@0.15.0 check --config ruff.toml <file>`. Report-only under `backend/app` (desktop delivery hash); auto-fix only under tests/scripts via hooks if present.
- **Scratch pytest** must live under `backend/tests/` so `app` imports resolve. Fixtures: `integration_env`, intake `queue`, etc.
- Do not put ruff into `backend/pyproject.toml` casually — that file is on desktop delivery hash paths.

---

## Working-tree safety

- Prefer surgical edits; do not `git add .` when unrelated dirty files exist.
- Do not revert, overwrite, or commit unrelated WIP (website, DEMO, research, etc.) unless asked.
- Commits: Conventional Commits; atomic; only when the human requests a commit.
- Critical changes need independent review against the **actual diff**, tests, and evidence (`conductor/workflow.md`).

---

## Nested agent guides

- [`kalla-native/AGENTS.md`](kalla-native/AGENTS.md) — Expo **versioned** docs requirement only; do not duplicate this whole file there.
