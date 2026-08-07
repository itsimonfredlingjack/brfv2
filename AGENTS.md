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

## Branch topology (if a file seems missing)

Product lines were not always merged in lockstep. **Which branch you are on determines which features exist.** Full story: [`docs/POST-BP6-PRODUKTBAS.md`](docs/POST-BP6-PRODUKTBAS.md). Tracked branch table for strangers: README § “Grenar”.

| Branch | Role |
| --- | --- |
| **`feat/produktbas`** | Where current work happens (this guide assumes it). Ahead of `main` with invoices-as-cases, concurrency/state integrity, desktop/invoice/intake acceptance, website builder work. Renamed from `feat/kalla-mobile-pwa` (2026-08-03)—the old name is misleading. |
| **`main`** | Product base: backend, web, PWA, Android, Tauri, Fortnox, Graph, watches, tasks. May lack files that only exist on `feat/produktbas` (e.g. `backend/app/invoices/rules.py`, `backend/app/history.py`, concurrency tests, intake acceptance scripts). |
| **`bp6/fedora-pilot-closeout`** (`v0.2.0-fedora-pilot`) | Frozen pilot evidence. No further development. |

If `src-tauri/`, `backend/app/integrations/`, or invoice packages seem missing, the checkout is on an older line—not that the feature never existed.

---

## Repository layout

One repo, no submodules. `make setup` from a clean clone is the full setup.

| Path | Role |
| --- | --- |
| `backend/` | Shared FastAPI app: RAG (`extract` → `chunker` → `indexer` → `answer` → `citations`), auth, `TenantRegistry` / `Store`, `history`, `desktop`, packages for integrations, invoices, watches, tasks, website |
| `brfv2-mockup/` | **Canonical web + desktop UI** (React/Vite). Real HTTP contract. |
| `xs_mobilapp/` | Mobile PWA: ask → grounded answer → source highlight |
| `kalla-native/` | Native Android (Expo Router + RN). See nested [`kalla-native/AGENTS.md`](kalla-native/AGENTS.md) before coding there. |
| `src-tauri/` | Tauri 2 shell + Fedora RPM packaging. Window/sidecar only; product adapter in `backend/app/desktop.py` |
| `docs/` | Architecture, runbooks, evidence |
| `ops/` | Desktop runtime build, payload inspect, forbidden-provider rules, demo scripts |
| `conductor/` | Project context for agents (product, stack, workflow, tracks) |

### `backend/app/integrations/` is two things

1. **Vendor adapters** (smaller): Fortnox, Graph mail, OAuth, credentials, egress, connections.
2. **Inkommande post** (larger): review queue—not an inbox—intake, mailbox, threads, triage, preserve, resolve, review. See `docs/INKOMMANDE-POST.md`.

Other domains: `watches/` (Bevakningar), `invoices/` (Fakturor as cases), `tasks/` (Uppgifter—human-created only), `website/` (Hemsidan—block commands, no model-driven publish).

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
6. **Read-only integrations by default** — Fortnox and Microsoft Graph are intelligence layers; adapters have no write verbs for association systems of record. See integrations below.
7. **Sovereign inference (product claim)** — association content is not disclosed to external model/OCR/embedding/reranking/transcription/analytics/telemetry/error-reporting services for processing. Authorised read-only intake from the association’s existing systems of record is permitted. See inference status below.

---

## Inference and AI: dual status (read carefully)

### Already structurally self-hosted

These are **not** broken leak incidents to “fix first”:

- **`BRF_MODE=pilot`** refuses to start unless `provider.name == "selfhosted"` (`backend/app/main.py`).
- **Desktop** pins `BRF_LLM=selfhosted`, applies `model_endpoint.py` on configured base URLs, scrubs hostile env keys in the shell.
- **Fedora RPM payload** excludes `app.llm_hosted` and the Anthropic package; `ops/forbidden_providers.json` + inspect/artifact tests enforce the payload.
- Endpoint policy for the **installed product** is default-deny: **loopback** and **private-network HTTPS** (`backend/app/model_endpoint.py`).

### Still present in source / web / dev / eval (scheduled for removal)

The source tree still contains and deliberately supports **hosted Anthropic API** and **Claude CLI** providers (`backend/app/llm_hosted.py`), Makefile-documented defaults, tests that assert hosted selection, and `OpenAICompatProvider` construction that does **not** yet apply `model_endpoint.py` on every non-desktop path.

**Track:** [`conductor/tracks/sovereign-inference-boundary/`](conductor/tracks/sovereign-inference-boundary/) — architecture consolidation so source, policy, docs, and artefacts match. Decisions 1–7 are locked in the track spec. **Do not implement that track unless the session’s task says so.** Do not reintroduce hosted product providers when doing other work.

### Test providers

- Offline tests: `BRF_LLM=fake` (see `backend/tests/conftest.py`).
- Deterministic acceptance: `BRF_LLM=scripted`.
- Live generation for pilot/demo: self-hosted (e.g. tunnel to controlled host + `BRF_LLM_BASE_URL`), not a smaller silent local fallback.

External coding agents (IDE, research) may run **outside** the product runtime. They must not become product providers and must not receive association content through Träff.

---

## Integrations (adapters)

Read-only intelligence layer—not an accounting system or mail client. Domain model: `docs/INTEGRATIONSDOMAN.md`.

- **Fortnox** — supplier invoices, company info; no write verbs; egress denies non-GET (except token POST). `docs/INTEGRATION-FORTNOX.md`.
- **Microsoft Graph / Outlook** — human-selected message into the review queue; scopes `Mail.Read` etc., never send/write. `docs/INTEGRATION-OUTLOOK.md`.

---

## Commands (repo root)

```bash
make setup              # uv, backend venv, embedder weights, node_modules, Playwright chromium
make backend            # API :8787 (dev mode — see inference dual status)
make frontend           # brfv2-mockup :5173
make mobile             # xs_mobilapp :5174 (needs backend)
make test               # backend offline tests
make test-isolation     # isolation + lifecycle + auth
make eval-fast          # retrieval only, no LLM
make mobile-test        # PWA unit + lint/typecheck + e2e/a11y
```

Frontend unit: `cd brfv2-mockup && npm test` / `cd xs_mobilapp && npm test` (no `test:unit` script name). E2E: `cd brfv2-mockup && npm run test:e2e`.

Desktop: `desktop-build`, `desktop-run`, `desktop-check`, `desktop-package`, `desktop-acceptance`, … — see `Makefile`.

`make invoice-acceptance` / `intake-acceptance` / much of website acceptance: **no model** (deterministic). `desktop-acceptance` that checks a **generated** answer needs self-hosted runtime (SSH tunnel + pilot path). Evidence under `docs/evidence/<RUN_LABEL>-…` — do not overwrite committed evidence casually.

Vocabulary / rules locks: `make website-vocabulary-lock` / `website-vocabulary-check`, `make invoice-rules-lock` after deliberate version bumps.

Pilot sketch (self-hosted model on controlled infra):

```bash
ssh -N -L 8000:127.0.0.1:8000 agenntserver
make demo   # preflight + pilot backend + canonical frontend
```

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

## Docs map (deeper reading)

- MVP / demo: `docs/MVP-STATUS.md`, `DEMO-QUICKSTART.md`, `DEMO-RUNBOOK.md`
- Self-hosted LLM: `docs/DEPLOY-SELFHOSTED-LLM.md`
- Desktop Fedora: `docs/DESKTOP-FEDORA.md`
- Domains: `INTEGRATIONSDOMAN.md`, `INKOMMANDE-POST.md`, `FAKTUROR.md`, `BEVAKNINGAR.md`, `UPPGIFTER.md`, `HEMSIDA.md`
- Specs: `SPEC.md`, `SPEC-PILOT.md` (historical dual-path notes may be superseded by the sovereign track—prefer Conductor + track for current intent)
- Evidence: `docs/evidence/`
- Model endpoint ADR: `docs/adr/0002-model-endpoint-boundary.md`

---

## Nested agent guides

- [`kalla-native/AGENTS.md`](kalla-native/AGENTS.md) — Expo **versioned** docs requirement only; do not duplicate this whole file there.
