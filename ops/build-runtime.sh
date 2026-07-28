#!/usr/bin/env bash
# Stage the self-contained Python runtime the installed desktop application
# ships with: src-tauri/runtime/.
#
# Approach (decision recorded in docs/adr/0001-desktop-python-runtime.md):
# a relocated copy of the SAME uv-managed CPython the test suite runs on, with
# the SAME hash-locked wheels resolved from backend/uv.lock. What ships is what
# was verified — no second dependency resolver and no re-derived module graph
# between `pytest` and the RPM.
#
# Idempotent: safe to re-run. Needs no sudo and touches nothing outside the
# checkout and the user's own caches.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

RUNTIME="$ROOT/src-tauri/runtime"
PY_TAG="python3.12"
MODEL_ID="minishlab/potion-multilingual-128M"
MODEL_DIR_NAME="potion-multilingual-128M"

# Packages resolved by the lock that the desktop delivery deliberately does not
# ship. Removing them is defence in depth, not an optimisation: `anthropic` is
# the only other network LLM client in the dependency tree, and the desktop
# product must have no code path to a third-party model at all. `hf_xet` and
# `pip` only exist to download things at runtime, which a packaged, offline
# application must never do.
EXCLUDED_PACKAGES=(anthropic hf_xet hf_xet-* pip pip-* pkg_resources setuptools setuptools-*)

green() { printf '\033[32m%s\033[0m\n' "$*"; }
yellow() { printf '\033[33m%s\033[0m\n' "$*"; }
step() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
fail() { printf '\033[31mFEL: %s\033[0m\n' "$*" >&2; exit 1; }

command -v uv >/dev/null 2>&1 || fail "uv saknas — kör 'make setup' först."
[ -x "backend/.venv/bin/python" ] || fail "backend/.venv saknas — kör 'make setup' först."

# ---------------------------------------------------------------------------
step "Interpreter"
# ---------------------------------------------------------------------------
# pyvenv.cfg's `home` points at the exact uv-managed CPython the backend venv
# was built from, so the bundle can never drift to a different patch release
# than the one the tests ran on.
PY_HOME="$(awk -F' = ' '/^home/ {print $2}' backend/.venv/pyvenv.cfg)"
# readlink -f, not `cd ..`: uv keeps a `cpython-3.12-...` symlink beside the
# real `cpython-3.12.13-...` directory. Staging the symlink instead of the tree
# produces a bundle that only works on the build machine.
PY_ROOT="$(readlink -f "$PY_HOME/..")"
PY_VERSION="$(backend/.venv/bin/python -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')"
[ -x "$PY_ROOT/bin/python3" ] || fail "hittade ingen fristående CPython under $PY_ROOT"
green "CPython $PY_VERSION från $PY_ROOT"

rm -rf "$RUNTIME"
mkdir -p "$RUNTIME/python"
# Copy the CONTENTS so the destination is a real directory; internal relative
# symlinks (bin/python3 -> python3.12, the libpython soname chain) are kept as
# links because they stay valid wherever the tree is installed.
cp -a "$PY_ROOT/." "$RUNTIME/python/"
chmod -R u+w "$RUNTIME/python"

# Nothing here can run in a packaged application: build headers, the CPython
# test suite, Tk (no display toolkit is used), and the static library.
rm -rf \
  "$RUNTIME/python/BUILD" \
  "$RUNTIME/python/share" \
  "$RUNTIME/python/include" \
  "$RUNTIME/python/lib/$PY_TAG/test" \
  "$RUNTIME/python/lib/$PY_TAG/idlelib" \
  "$RUNTIME/python/lib/$PY_TAG/lib2to3" \
  "$RUNTIME/python/lib/$PY_TAG/ensurepip" \
  "$RUNTIME/python/lib/$PY_TAG/pydoc_data" \
  "$RUNTIME/python/lib/$PY_TAG/tkinter" \
  "$RUNTIME/python/lib/$PY_TAG/turtledemo" \
  "$RUNTIME/python/lib/$PY_TAG/site-packages" \
  "$RUNTIME/python/lib/$PY_TAG/lib-dynload/_tkinter"*.so \
  "$RUNTIME/python/lib/"{tcl,tk,itcl,thread}* \
  "$RUNTIME/python/lib/libtcl"* \
  "$RUNTIME/python/lib/libpython"*.a \
  "$RUNTIME/python/bin/"{2to3,idle3,pydoc3}* \
  "$RUNTIME/python/bin/pip"*
mkdir -p "$RUNTIME/python/lib/$PY_TAG/site-packages"

# ---------------------------------------------------------------------------
step "Låsta beroenden"
# ---------------------------------------------------------------------------
REQUIREMENTS="$RUNTIME/requirements.lock.txt"
(cd backend && uv export --frozen --no-dev --no-emit-project --format requirements.txt) > "$REQUIREMENTS"
uv pip install \
  --quiet \
  --python "$RUNTIME/python/bin/python3" \
  --target "$RUNTIME/python/lib/$PY_TAG/site-packages" \
  --requirements "$REQUIREMENTS"
# `--target` drops console scripts next to the packages; the shell only ever
# runs `python -m app.desktop`, so they are dead weight.
rm -rf "$RUNTIME/python/lib/$PY_TAG/site-packages/bin"

for pattern in "${EXCLUDED_PACKAGES[@]}"; do
  rm -rf "$RUNTIME/python/lib/$PY_TAG/site-packages/$pattern"
done
green "beroenden installerade ($(du -sh "$RUNTIME/python/lib/$PY_TAG/site-packages" | cut -f1))"

# ---------------------------------------------------------------------------
step "Produktkod"
# ---------------------------------------------------------------------------
# `backend/app` only. `backend/scripts` — which contains the demo seeder — is
# deliberately absent from the bundle, so the shipped application structurally
# cannot seed demo associations or demo credentials.
mkdir -p "$RUNTIME/backend"
cp -a backend/app "$RUNTIME/backend/app"
find "$RUNTIME/backend" -name '__pycache__' -type d -prune -exec rm -rf {} +

# ---------------------------------------------------------------------------
step "Embedder-vikter ($MODEL_ID)"
# ---------------------------------------------------------------------------
# Bundled rather than downloaded on first run: a packaged application must work
# offline, and a silent first-run fetch from huggingface.co would be exactly
# the hidden egress this product promises not to do.
SNAPSHOT="$(backend/.venv/bin/python - "$MODEL_ID" <<'PY'
import sys
from huggingface_hub import snapshot_download
print(snapshot_download(sys.argv[1], allow_patterns=[
    "config.json", "model.safetensors", "modules.json",
    "tokenizer.json", "tokenizer_config.json",
    "special_tokens_map.json", "vocab.txt",
]))
PY
)"
mkdir -p "$RUNTIME/models/$MODEL_DIR_NAME"
# -L: the HF cache stores snapshots as symlinks into blobs/, and the bundle has
# to carry real files.
cp -Lr "$SNAPSHOT"/. "$RUNTIME/models/$MODEL_DIR_NAME/"
rm -rf "$RUNTIME/models/$MODEL_DIR_NAME/onnx" "$RUNTIME/models/$MODEL_DIR_NAME/.eval_results"
green "vikter kopierade ($(du -sh "$RUNTIME/models/$MODEL_DIR_NAME" | cut -f1))"

# ---------------------------------------------------------------------------
step "Relokerbarhet"
# ---------------------------------------------------------------------------
# Everything in the bundle is installed under a different prefix than it was
# built at, so any symlink that is absolute or points outside the tree would be
# dangling on the target machine — the exact failure that only shows up after
# the RPM is installed somewhere else.
ESCAPED=0
while IFS= read -r link; do
  target="$(readlink "$link")"
  case "$target" in
    /*) yellow "absolut symlink: $link -> $target"; ESCAPED=1; continue ;;
  esac
  resolved="$(readlink -f "$link" || true)"
  case "$resolved" in
    "$RUNTIME"/*) ;;
    *) yellow "symlink pekar utanför bundlen: $link -> $target"; ESCAPED=1 ;;
  esac
done < <(find "$RUNTIME" -type l)
[ "$ESCAPED" -eq 0 ] || fail "körmiljön är inte relokerbar (se varningarna ovan)."
green "inga absoluta eller utåtpekande symlänkar"

# ---------------------------------------------------------------------------
step "Bytekod och smoketest"
# ---------------------------------------------------------------------------
# The application is installed read-only under /usr/lib and runs with -B, so
# every .pyc it will ever use has to exist before packaging.
"$RUNTIME/python/bin/python3" -m compileall -q \
  "$RUNTIME/backend/app" "$RUNTIME/python/lib/$PY_TAG/site-packages" >/dev/null 2>&1 || true

(cd "$RUNTIME/backend" && BRF_MODEL2VEC_PATH="$RUNTIME/models/$MODEL_DIR_NAME" HF_HUB_OFFLINE=1 \
  "$RUNTIME/python/bin/python3" -E -s -B - <<'PY'
import os, sys
import app.desktop, app.main, app.store, app.ocr, app.answer  # noqa: F401
from app.embeddings import Model2VecEmbedder
try:
    import anthropic  # noqa: F401
except ImportError:
    pass
else:
    sys.exit("anthropic ligger kvar i bundlen — den självhostade gränsen är inte strukturell.")
embedder = Model2VecEmbedder()
vector = embedder.embed(["Styrelsen har sitt säte i Göteborgs kommun."])[0]
assert len(vector) == 256, len(vector)
print(f"OK  python={sys.version.split()[0]}  embedder={embedder.name}  dim={len(vector)}")
PY
)

# ---------------------------------------------------------------------------
step "Härkomst"
# ---------------------------------------------------------------------------
backend/.venv/bin/python - "$RUNTIME" "$PY_VERSION" "$PY_ROOT" "$MODEL_ID" <<'PY'
import hashlib, json, os, subprocess, sys
from pathlib import Path

runtime, py_version, py_root, model_id = Path(sys.argv[1]), sys.argv[2], sys.argv[3], sys.argv[4]
requirements = (runtime / "requirements.lock.txt").read_bytes()


def tree_bytes(path: Path) -> int:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return ""


(runtime / "BUNDLE.json").write_text(
    json.dumps(
        {
            "schema": "brfv2-desktop-bundle/v1",
            "python": {"version": py_version, "source": os.path.basename(py_root)},
            "requirements": {
                "source": "backend/uv.lock (uv export --frozen --no-dev)",
                "sha256": hashlib.sha256(requirements).hexdigest(),
            },
            "excludedPackages": ["anthropic", "hf_xet", "pip", "setuptools"],
            "embedder": {"modelId": model_id, "bundled": True},
            "commit": git("rev-parse", "HEAD"),
            "dirty": bool(git("status", "--porcelain")),
            "sizes": {
                "pythonBytes": tree_bytes(runtime / "python"),
                "backendBytes": tree_bytes(runtime / "backend"),
                "modelsBytes": tree_bytes(runtime / "models"),
            },
        },
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    + "\n",
    encoding="utf-8",
)
print(json.dumps(json.loads((runtime / "BUNDLE.json").read_text()), indent=2, sort_keys=True))
PY

green "Körmiljö klar: $RUNTIME ($(du -sh "$RUNTIME" | cut -f1))"
