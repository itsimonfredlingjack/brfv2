# Conductor — Träff

Navigation hub for project context.

## Quick Links

### Core Documents

| Document | Description | Status |
| --- | --- | --- |
| [Product Vision](./product.md) | Product overview and goals | Complete |
| [Product Guidelines](./product-guidelines.md) | Voice, tone, principles | Complete |
| [Tech Stack](./tech-stack.md) | Technology decisions | Complete |
| [Workflow](./workflow.md) | Development process | Complete |
| [Tracks](./tracks.md) | Development track registry | Ready |

### Style Guides

| Guide | Language / domain |
| --- | --- |
| [General](./code_styleguides/general.md) | Universal principles + Rust (Tauri) notes |
| [Python](./code_styleguides/python.md) | Backend standards (see also root `ruff.toml`) |
| [JavaScript](./code_styleguides/javascript.md) | Web UI conventions |
| [TypeScript](./code_styleguides/typescript.md) | PWA / native conventions |
| [HTML/CSS](./code_styleguides/html-css.md) | Web markup and styling |

## Active Tracks

| Track | Status | Priority | Spec | Plan |
| --- | --- | --- | --- | --- |
| [Enforce sovereign inference boundary](./tracks/sovereign-inference-boundary/) | Phase 0 done · impl pending | Critical | [spec](./tracks/sovereign-inference-boundary/spec.md) | [plan](./tracks/sovereign-inference-boundary/plan.md) |

## Getting Started

1. Review [Product Vision](./product.md) for product context and non-goals
2. Check [Tech Stack](./tech-stack.md) and root `README.md` / `AGENTS.md` for layout
3. Read [Workflow](./workflow.md) for TDD, commits, review, and checkpoints
4. Run `/conductor:new-track` to create the first feature track

## Common Commands

```bash
make setup              # one-time: uv, backend, embedder, node_modules, Playwright
make backend            # API on :8787
make frontend           # canonical UI on :5173
make test               # backend tests (offline, deterministic)
make mobile             # mobile PWA on :5174 (needs backend)
```

See root `Makefile` for desktop, invoice, intake, and website acceptance targets.

## Related product docs (outside conductor/)

- [MVP status](../docs/MVP-STATUS.md)
- [Integrations domain](../docs/INTEGRATIONSDOMAN.md)
- [Post-BP6 product base / branches](../docs/POST-BP6-PRODUKTBAS.md)
- [SPEC](../SPEC.md) · [Pilot contract](../SPEC-PILOT.md)

---

**Setup completed:** 2026-08-05  
**Project type:** brownfield  
**Product name:** Träff
