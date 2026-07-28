#!/usr/bin/env bash
# Stage the self-contained Python runtime the installed desktop application
# ships with: src-tauri/runtime/.
#
# Approach (decision recorded in docs/adr/0001-desktop-python-runtime.md):
# the exact CPython build pinned in ops/pins.json — the same
# python-build-standalone release uv resolves for the interpreter the test
# suite runs on — with the SAME hash-locked wheels resolved from
# backend/uv.lock. What ships is what was verified: no second dependency
# resolver and no re-derived module graph between `pytest` and the RPM.
#
# Every third-party input is fetched by ops/fetch_pinned.py and checked against
# its SHA-256 before it is used. A local cache may hold the bytes; it never
# decides what they are. Nothing here reads a mutable Hugging Face cache, an
# ambient `uv` from PATH, or "whichever interpreter the venv happens to point
# at" — those were the three ways the build could quietly change identity.
#
# The staged tree is deterministic: same commit in, same bytes out, from any
# checkout path. See ops/lib/repro.sh.
#
# Idempotent: safe to re-run. Needs no sudo and touches nothing outside the
# checkout and the build cache.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
# shellcheck source=ops/lib/repro.sh
source "$ROOT/ops/lib/repro.sh"

RUNTIME="$ROOT/src-tauri/runtime"
PY_TAG="python3.12"
APPNAME="BRF Dokument-AI"
# Where the bundle lands once the RPM is installed. Baked into the compiled
# bytecode so a traceback from the installed application names the file the
# operator can actually open.
INSTALL_PREFIX="/usr/lib/$APPNAME/runtime"
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

[ -x "backend/.venv/bin/python" ] || fail "backend/.venv saknas — kör 'make setup' först."

# Any interpreter this script starts — including the ones uv runs to query the
# target environment — must not drop bytecode into the staged tree as a side
# effect. Such a .pyc records the absolute path it was compiled at, which is
# exactly the build-location leak this build has to be free of. The bytecode
# that ships is written deliberately, once, further down.
export PYTHONDONTWRITEBYTECODE=1

EPOCH="$(repro_epoch)"
COMMIT="$(repro_commit)"
DIRTY="$(repro_dirty)"
export SOURCE_DATE_EPOCH="$EPOCH"
# A dirty checkout has no committed tree to hash, so the bundle records that it
# has no verifiable provenance rather than inventing one. Packaging refuses
# such a bundle outright.
if [ "$DIRTY" = "true" ]; then
  DELIVERY_TREE=""
  yellow "checkouten är smutsig — bundlen märks utan härkomst och kan inte paketeras."
else
  DELIVERY_TREE="$(repro_delivery_tree)"
fi

PINNED_PY_VERSION="$(python3 -c "import json;print(json.load(open('ops/pins.json'))['python']['version'])")"
PINNED_PY_BUILD="$(python3 -c "import json;print(json.load(open('ops/pins.json'))['python']['build'])")"

# ---------------------------------------------------------------------------
step "Pinnad verktygskedja"
# ---------------------------------------------------------------------------
UV="$(ops/fetch_pinned.py uv)"
green "uv: $UV"

# ---------------------------------------------------------------------------
step "Interpreter (CPython $PINNED_PY_VERSION+$PINNED_PY_BUILD)"
# ---------------------------------------------------------------------------
PY_ARCHIVE="$(ops/fetch_pinned.py python)"

rm -rf "$RUNTIME"
mkdir -p "$RUNTIME"
# The archive contains a single top-level `python/` directory, which becomes
# $RUNTIME/python. tar preserves the archive's own timestamps, so extraction is
# already deterministic.
tar -xzf "$PY_ARCHIVE" -C "$RUNTIME"
[ -x "$RUNTIME/python/bin/python3" ] || fail "arkivet innehöll ingen körbar python3"
chmod -R u+w "$RUNTIME/python"

STAGED_VERSION="$("$RUNTIME/python/bin/python3" -c 'import sys; print(sys.version)')"
VENV_VERSION="$(backend/.venv/bin/python -c 'import sys; print(sys.version)')"
# The parity that makes "what ships is what was verified" a fact rather than an
# intention: the packaged interpreter and the one pytest ran on are the same
# build, down to the compiler and build date in sys.version.
[ "$STAGED_VERSION" = "$VENV_VERSION" ] || fail \
  "den pinnade tolken är inte den testsviten kör på.
  paketerad: $STAGED_VERSION
  backend/.venv: $VENV_VERSION
  Uppdatera ops/pins.json (och kör om testerna) eller synka om backend/.venv."
green "CPython $STAGED_VERSION — identisk med backend/.venv"

# Nothing here can run in a packaged application: build headers, the CPython
# test suite, Tk (no display toolkit is used), the static library, and the
# tools that only exist to install more software at runtime.
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
  "$RUNTIME/python/lib/libtk"* \
  "$RUNTIME/python/lib/libpython"*.a \
  "$RUNTIME/python/bin/"{2to3,idle3,pydoc3}* \
  "$RUNTIME/python/bin/pip"*
mkdir -p "$RUNTIME/python/lib/$PY_TAG/site-packages"

# ---------------------------------------------------------------------------
step "Låsta beroenden"
# ---------------------------------------------------------------------------
REQUIREMENTS="$RUNTIME/requirements.lock.txt"
(cd backend && "$UV" export --frozen --no-dev --no-emit-project --format requirements.txt) > "$REQUIREMENTS"
grep -q -- "--hash=sha256:" "$REQUIREMENTS" || fail \
  "det exporterade kravfilen saknar hashar — vägrar installera overifierade hjul."
# --require-hashes: every wheel that lands in the bundle is checked against
# backend/uv.lock, so a compromised or substituted artifact fails the build
# instead of shipping.
"$UV" pip install \
  --quiet \
  --require-hashes \
  --python "$RUNTIME/python/bin/python3" \
  --target "$RUNTIME/python/lib/$PY_TAG/site-packages" \
  --requirements "$REQUIREMENTS"
# `--target` drops console scripts next to the packages; the shell only ever
# runs `python -m app.desktop`, so they are dead weight. They are also the one
# thing uv writes with a build-time absolute path baked in (the shebang), so
# they have to go — and each package's RECORD has to stop claiming them, or the
# metadata still carries the length of a path from this machine.
python3 - "$RUNTIME/python/lib/$PY_TAG/site-packages" <<'PY'
import shutil, sys
from pathlib import Path

site = Path(sys.argv[1])
shutil.rmtree(site / "bin", ignore_errors=True)
for record in site.glob("*.dist-info/RECORD"):
    lines = record.read_text(encoding="utf-8").splitlines(keepends=True)
    kept = [line for line in lines if not line.startswith("bin/")]
    if len(kept) != len(lines):
        record.write_text("".join(kept), encoding="utf-8")
PY

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
step "Embedder-vikter (pinnad revision)"
# ---------------------------------------------------------------------------
# Bundled rather than downloaded on first run: a packaged application must work
# offline, and a silent first-run fetch from huggingface.co would be exactly
# the hidden egress this product promises not to do. Pinned to one commit with
# an explicit file list, so the bundle cannot inherit whatever revision was
# lying in a cache on the build machine.
ops/fetch_pinned.py embedder "$RUNTIME/models/$MODEL_DIR_NAME" >/dev/null
green "vikter verifierade ($(du -sh "$RUNTIME/models/$MODEL_DIR_NAME" | cut -f1))"

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
#
# The whole tree is recompiled, standard library included, rather than only the
# parts installed here. The interpreter archive ships its own .pyc compiled at
# the distributor's build path, and anything that imports during staging can
# overwrite one of them with a copy compiled at *this* checkout's path. One
# deterministic pass over everything removes both variants of that problem.
#
# Two flags are what make the result reproducible instead of a record of this
# machine:
#   -s/-p            rewrite the source path recorded in each .pyc from this
#                    checkout to the path the file will have once installed,
#                    so the bytes do not depend on where the build ran — and a
#                    traceback names a file the operator can actually open.
#   unchecked-hash   drop the source mtime from the .pyc header entirely. The
#                    installed tree is read-only, so there is nothing to
#                    invalidate against, and an embedded build clock is pure
#                    variance.
find "$RUNTIME" -name '__pycache__' -type d -prune -exec rm -rf {} +
"$RUNTIME/python/bin/python3" -E -s -B -m compileall -q -f \
  --invalidation-mode unchecked-hash \
  -s "$RUNTIME" -p "$INSTALL_PREFIX" \
  "$RUNTIME/backend/app" "$RUNTIME/python/lib/$PY_TAG" >/dev/null 2>&1 || true

(cd "$RUNTIME/backend" && BRF_MODEL2VEC_PATH="$RUNTIME/models/$MODEL_DIR_NAME" HF_HUB_OFFLINE=1 \
  "$RUNTIME/python/bin/python3" -E -s -B - <<'PY'
import os, sys
import app.desktop, app.main, app.store, app.ocr, app.answer  # noqa: F401
from app.embeddings import Model2VecEmbedder
from app.model_endpoint import classify_endpoint
try:
    import anthropic  # noqa: F401
except ImportError:
    pass
else:
    sys.exit("anthropic ligger kvar i bundlen — den självhostade gränsen är inte strukturell.")
# The packaged code must carry the same endpoint policy the tests proved, not
# an older copy that happened to be in the checkout.
if classify_endpoint("https://api.openai.com/v1").allowed:
    sys.exit("bundlen accepterar en tredjepartsendpoint — modellgränsen är inte med i paketet.")
if not classify_endpoint("http://127.0.0.1:8000/v1").allowed:
    sys.exit("bundlen avvisar loopback — modellgränsen är felaktigt hårdare än policyn.")
embedder = Model2VecEmbedder()
vector = embedder.embed(["Styrelsen har sitt säte i Göteborgs kommun."])[0]
assert len(vector) == 256, len(vector)
print(f"OK  python={sys.version.split()[0]}  embedder={embedder.name}  dim={len(vector)}")
PY
)

# ---------------------------------------------------------------------------
step "Härkomst"
# ---------------------------------------------------------------------------
backend/.venv/bin/python - "$RUNTIME" "$DELIVERY_TREE" "$EPOCH" <<'PY'
import hashlib, json, subprocess, sys
from pathlib import Path

runtime, delivery_tree, epoch = Path(sys.argv[1]), sys.argv[2], int(sys.argv[3])
requirements = (runtime / "requirements.lock.txt").read_bytes()
pins = json.loads(
    subprocess.run(
        [sys.executable, str(Path.cwd() / "ops" / "fetch_pinned.py"), "manifest"],
        capture_output=True, text=True, check=True,
    ).stdout
)


def tree_bytes(path: Path) -> int:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


(runtime / "BUNDLE.json").write_text(
    json.dumps(
        {
            "schema": "brfv2-desktop-bundle/v2",
            # The identity of the sources this bundle was built from. Not the
            # commit: documentation and acceptance evidence live in the same
            # commit as the delivery and must not be able to move these bytes.
            # ops/lib/repro.sh REPRO_DELIVERY_PATHS is the exact path list.
            "deliveryTree": delivery_tree or None,
            "sourceDateEpoch": epoch,
            "pins": pins,
            "python": {
                "version": pins["python"]["version"],
                "source": f"{pins['python']['distribution']}@{pins['python']['build']}",
                "sha256": pins["python"]["sha256"],
            },
            "requirements": {
                "source": "backend/uv.lock (uv export --frozen --no-dev)",
                "sha256": hashlib.sha256(requirements).hexdigest(),
                "verifiedBy": "uv pip install --require-hashes",
            },
            "excludedPackages": ["anthropic", "hf_xet", "pip", "setuptools"],
            "embedder": {
                "modelId": pins["embedder"]["repoId"],
                "revision": pins["embedder"]["revision"],
                "bundled": True,
            },
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

# Last: one timestamp for the whole tree, taken from the commit. Everything
# above this line writes files whenever it happens to run.
repro_stamp_tree "$RUNTIME" "$EPOCH"

green "Körmiljö klar: $RUNTIME ($(du -sh "$RUNTIME" | cut -f1))"
