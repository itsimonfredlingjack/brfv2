# Technology Stack

Brownfield stack as confirmed in Conductor setup (2026-08-05). Source of truth for versions remains the manifests (`backend/pyproject.toml`, client `package.json` files, `src-tauri/Cargo.toml`).

## Languages

| Language | Role | Notes |
| --- | --- | --- |
| **Python 3.12** | Backend, scripts, acceptance | `requires-python = ">=3.12,<3.13"`; uv manages the venv |
| **JavaScript / JSX** | Canonical web UI | `brfv2-mockup` |
| **TypeScript** | Mobile PWA + native | `xs_mobilapp`, `kalla-native` |
| **Rust** | Tauri 2 desktop shell & packaging | Maintained project code; not product business logic |

## Frontend

### Frameworks

| Client | Stack | Path |
| --- | --- | --- |
| Canonical web / desktop UI | React + Vite | `brfv2-mockup/` |
| Mobile PWA | React + TypeScript + Vite | `xs_mobilapp/` |
| Native Android | Expo Router + React Native + Reanimated | `kalla-native/` |
| Desktop shell | Tauri 2 wraps the canonical web UI | `src-tauri/` |

**Rationale:** One product identity (Träff) with deliberate client parity: phone is for grounded ask + library loops; full post/invoice/website work lives on web/desktop.

### Notable frontend libraries

| Library | Purpose | Where |
| --- | --- | --- |
| pdfjs-dist | PDF viewing / citation UI | web |
| @puckeditor/core | Website block editor | web |
| lucide-react | Icons | web |
| Playwright / Vitest | E2E and unit tests | web, PWA |
| Expo modules | native device capabilities | kalla-native |

### Styling

Client-specific CSS / theme tokens (e.g. `theme.css`, native theme modules). No root Prettier policy unless the project later adopts one.

## Backend

### Language & framework

- **Python 3.12** + **FastAPI** + **Pydantic v2** + **uvicorn**
- Single shared backend for all clients: RAG pipeline, auth, integrations, invoices, watches, tasks, website builder

**Rationale:** One HTTP contract; frontends must not fork domain rules.

### RAG / documents (high level)

`extract` → `chunker` → `indexer` → `answer` → `citations`, with grounding helpers (`numeric_grounding`, terms, etc.). Embeddings via model2vec; optional rerank extra pulls heavier torch stack only when needed.

### LLM

- Pilot/self-hosted inference on Träff-controlled infrastructure (e.g. Gemma on controlled host via tunnel in demo ops)
- **No external model APIs for association content processing** (product invariant)

### Persistence

| Store | Purpose |
| --- | --- |
| **SQLite** | Auth: users, tenants, memberships, sessions |
| **Per-tenant filesystem** | JSON meta, extracts, settings, local indexes via `TenantRegistry` / `Store` |

There is **no** shared multi-tenant Postgres product database for document content. Tenant isolation is structural (separate object graphs), not a single filtered table.

### Money / integrations

- Money as `Decimal`, JSON string — never `float` for invoice comparisons
- **Fortnox** and **Microsoft Graph** adapters: read-only intelligence layer
- Incoming-post feature lives under `backend/app/integrations/` as product logic, not only connectors

### Additional backend libraries (from `pyproject.toml`)

| Library | Purpose |
| --- | --- |
| pymupdf | PDF extract |
| httpx | HTTP client |
| anthropic | Present as dependency; product policy still forbids external model use for association content — treat host/model config as operational, not a green light for SaaS leakage |
| model2vec | Embeddings |
| pytest | Tests |

## Desktop packaging

- **Tauri 2** + Rust (`src-tauri/`)
- Fedora **RPM** packaging under `ops/`
- Desktop Python runtime packaging is delivery-sensitive: changes under delivery paths affect artifact identity hashes — see `ruff.toml` comments and `docs/DESKTOP-FEDORA.md`

## Infrastructure & operations

- **Self-hosted** on Träff-controlled infrastructure, preferably Sweden, else EU/EES
- Local development via **Make** targets from repo root (`make setup`, `make backend`, `make frontend`, `make test`, desktop/acceptance targets)
- Evidence for acceptance runs under `docs/evidence/` (never overwrite committed evidence carelessly)

## Development tools

| Concern | Tool / config |
| --- | --- |
| Python packages | **uv** |
| Python lint | **ruff** via `uvx ruff@0.15.0` + root `ruff.toml` (not in backend pyproject — artifact hash) |
| Web/PWA lint | **oxlint** (`npm run lint` in brfv2-mockup, xs_mobilapp) |
| Native lint | **ESLint** (`kalla-native/eslint.config.js`) |
| Backend tests | `make test` / pytest |
| UI unit | Vitest |
| UI E2E / acceptance | Playwright; desktop/invoice/intake acceptance via Make + Tauri |

## Decision log (setup snapshot)

### Single shared FastAPI backend

**Status:** Accepted (existing)  
**Context:** Multiple clients must share auth, grounding, and domain routes.  
**Decision:** One backend contract; clients differ only in surface area.  
**Consequences:** Route changes checked against every client, not only the one with the screen.

### Per-tenant file stores + SQLite auth

**Status:** Accepted (existing)  
**Context:** Isolation must be structural; document corpora must not mix.  
**Decision:** SQLite for auth/tenancy metadata; per-tenant files/indexes for content.  
**Consequences:** No shared multi-tenant SQL product DB for documents; ops are filesystem-aware.

### Controlled inference, no external model APIs for content

**Status:** Product invariant  
**Context:** Privacy, residency, verifiability for BRF boards.  
**Decision:** Inference on Träff-controlled SE/EU infrastructure; content never leaves the operating environment.  
**Consequences:** Demo/pilot requires self-hosted model path; egress audits matter.

### Read-only Fortnox / Graph

**Status:** Accepted (existing)  
**Context:** Intelligence layer, not accounting or mail client.  
**Decision:** Adapters have no write verbs; tests enforce GET-only where specified.  
**Consequences:** Human decisions stay in Träff; external systems of record unchanged by Träff.

## Version compatibility (indicative)

| Component | Constraint | Notes |
| --- | --- | --- |
| Python | 3.12.x | Distro Python often wrong; uv fetches |
| Tauri | 2.x (pinned in Cargo.toml) | Desktop shell |
| React | per client package.json | Keep clients independent unless deliberately aligned |
