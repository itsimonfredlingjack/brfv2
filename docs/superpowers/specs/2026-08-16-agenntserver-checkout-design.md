# Dual-machine Träff checkout (agenntserver)

Date: 2026-08-16  
Approved approach: **1 — Git hub + thin server checkout**

## Problem

The Fedora/laptop checkout is the product worktree, but it freezes under
several concurrent agent sessions. Gemma 4 12B already runs on Ubuntu
`agenntserver` (RTX 4070, `127.0.0.1:8000`). Until now that host had no
Träff repo, so agents and research still piled onto the laptop.

## Goal

Same git project, two roles, so the laptop stays interactive:

- **Laptop** — UI, frontend, the running app, anything that needs a screen.
- **agenntserver** — SSH/Cursor agents, research, evals, backend work
  against local Gemma. Work here should be cheap to redo if a session dies.

## Non-goals

- Full `make setup` on the server (no `brfv2-mockup/node_modules`, no
  Android, no Tauri/`src-tauri/target`).
- rsync of the laptop tree (native bindings, 20+ GB artefacts).
- Running the Fedora desktop RPM on Ubuntu.
- Making this host the source of truth instead of GitHub.

## Approach (approved)

GitHub `origin` is the hub. This machine is a second worktree of `main`.
Install **backend only**: `uv sync` in `backend/` plus the model2vec
embedder cache, and host packages `tesseract-ocr` + `tesseract-ocr-swe`
(ingestion tests and scanned PDFs). Point pilot generation at loopback:

```
BRF_MODE=pilot
BRF_LLM=selfhosted
BRF_LLM_BASE_URL=http://127.0.0.1:8000/v1
BRF_LLM_MODEL=gemma4:e12b
BRF_LLM_RUNTIME_LABEL=agenntserver
```

No SSH tunnel on this host. Laptop tunnels only when the *app* there must
talk to Gemma.

Sync is `git pull` / `git push`. Remote `linuxtop` is a fallback when
commits exist on the laptop but are not on GitHub yet. Untracked screenshots
and design dumps stay local; research that should live is committed under
`docs/research/`.

Do not copy `.venv` or `node_modules` between machines. Do not edit the
same files on both hosts without pulling first.

## Layout

| Path | Role on agenntserver |
| --- | --- |
| `/home/simon/brfv2` | git worktree |
| `backend/.venv` | local, gitignored |
| `backend/.env` | local pilot LLM settings, gitignored |
| `docs/research/` | research that earns a commit |

## Success

- `git status` on both machines can reach the same `origin/main`.
- `make test` runs from this checkout without frontend install.
- A generation call from this host uses `http://127.0.0.1:8000/v1`.
- Agents opened here do not install UI/Android/Tauri unless the task is
  explicitly that surface.
