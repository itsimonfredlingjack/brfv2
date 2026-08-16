# agenntserver thin checkout — implementation plan

> Operational setup, not a product feature. Execute on this host; do not
> install frontend/Android/Tauri.

**Goal:** Backend-only Träff checkout on agenntserver, synced via GitHub.

**Architecture:** `uv sync` + gitignored `backend/.env` pointing at local
Gemma; docs that tell agents not to run full `make setup` here.

**Tech Stack:** git, uv, Python 3.12, Gemma 4 12B on `:8000`.

## Global Constraints

- Python `>=3.12,<3.13` via uv; do not use distro Python for the venv.
- Do not `uv sync --extra rerank` unless evaluating rerank.
- Do not commit `backend/.env`.
- Do not force-push. Push `main` only.

---

### Task 1: Backend venv + embedder

- [x] `cd backend && uv sync`
- [x] Cache model2vec weights (same snippet as `ops/setup.sh`)
- [x] Copy `backend/.env.example` → `backend/.env` (already loopback Gemma)
- [x] `curl -sS http://127.0.0.1:8000/v1/models` returns a model
- [x] `make test` from repo root (offline backend tests)
- [x] Install `tesseract-ocr` + `tesseract-ocr-swe` (required after OCR-on-thin-text)

### Task 2: Agent map + publish

- [x] Short “two machines” note in `AGENTS.md`
- [ ] Commit docs (`docs:` conventional commit)
- [ ] `git push origin main` (includes the five laptop commits already on this branch)
