#!/usr/bin/env bash
# One-command bootstrap for a clean checkout. Idempotent: safe to re-run.
#
# Deliberately installs nothing system-wide and needs no sudo. Everything
# lands in the checkout (.venv, node_modules) or the user's own caches
# (~/.local/bin for uv, ~/.cache for model weights and browsers).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

green() { printf '\033[32m%s\033[0m\n' "$*"; }
yellow() { printf '\033[33m%s\033[0m\n' "$*"; }
step() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }

# --- uv -----------------------------------------------------------------
# The backend pins Python >=3.12,<3.13. Distros ship whatever they ship
# (Fedora 44 is on 3.14), so uv — which fetches its own interpreter — is the
# only portable way to get a matching runtime without touching the system.
step "Python-verktygskedja (uv)"
if command -v uv >/dev/null 2>&1; then
  green "uv finns redan: $(uv --version)"
else
  yellow "uv saknas — installerar i ~/.local/bin (inget sudo, inget systempaket)."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
  green "uv installerad: $(uv --version)"
  yellow "Lägg till ~/.local/bin i din PATH permanent om det inte redan är gjort."
fi
command -v uv >/dev/null 2>&1 || { echo "uv gick inte att hitta ens efter installation — avbryter."; exit 1; }

# --- backend ------------------------------------------------------------
# Base install only. The `rerank` extra pulls torch + ~3.8 GB of CUDA wheels
# and is NOT needed for a green test run or for the pilot loop — reranking is
# off by default (Settings.rerankEnabled = False). Opt in explicitly with
# `uv sync --extra rerank` in backend/ if you are actually evaluating it.
step "Backend-beroenden"
(cd backend && uv sync)
green "backend/.venv klar ($(du -sh backend/.venv | cut -f1))"

# --- embedder weights ---------------------------------------------------
# Fetched lazily on first ask() otherwise, which makes the first backend
# start exceed `make demo`'s health timeout on a cold cache. ~100 MB.
step "Embedder-vikter (model2vec)"
(cd backend && uv run python -c "
from app.embeddings import Model2VecEmbedder
from model2vec import StaticModel
StaticModel.from_pretrained(Model2VecEmbedder.MODEL_ID)
print('cachad:', Model2VecEmbedder.MODEL_ID)
")
green "embedder cachad"

# --- frontend -----------------------------------------------------------
# node_modules must be built on THIS platform: a tree copied from another OS
# carries the wrong native bindings (rolldown/lightningcss/oxlint ship
# per-platform binaries) and fails at build time, not install time.
step "Kanonisk frontend (brfv2-mockup)"
(cd brfv2-mockup && npm install)
green "brfv2-mockup/node_modules klar"

step "Äldre rotfrontend (regressionsskydd)"
npm install
green "node_modules klar"

# --- browsers -----------------------------------------------------------
# `npx playwright install-deps` only works on apt-based distros; on Fedora it
# fails with "spawn apt-get ENOENT". The browser download itself is portable
# and the Ubuntu fallback build runs fine on Fedora.
step "Playwright-browser (chromium)"
(cd brfv2-mockup && npx playwright install chromium)
green "chromium klar"

cat <<'EOF'

────────────────────────────────────────────────────────────
Klart. Nästa steg:

  make test              backend-tester (offline, deterministiska)
  make demo-reset        seeda de två demoföreningarna
  make demo              hela pilotstacken (kräver SSH-tunnel, se README)

Frontend + backend var för sig:
  make backend           :8787 i dev-läge
  make frontend          :5173 kanoniskt UI

Skrivbordsapplikationen (Fedora):
  make desktop-run       kör skalet mot den här checkouten
  make desktop-package   bygger RPM:en (kräver `sudo dnf install rpm-build`)
────────────────────────────────────────────────────────────
EOF
