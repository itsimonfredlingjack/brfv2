# Shared provenance and reproducibility helpers for the desktop packaging.
#
# Sourced by ops/build-runtime.sh and ops/package-desktop.sh. Not executable on
# its own.
#
# The rule these encode: the distributable artifact is a function of the
# delivery sources and nothing else. Not of where the checkout happens to live,
# not of when it was built, and not of what else the build machine had lying
# around.

# The tracked paths the artifact is actually built from. Everything else in the
# repository — documentation, evidence, evaluation scripts, the legacy root
# frontend — can change without changing a single byte of the package, and
# `repro_delivery_tree` is what makes that checkable rather than asserted.
#
# It is also what lets the acceptance evidence live in the same commit as the
# delivery it describes: evidence is not on this list, so committing it cannot
# move the artifact.
REPRO_DELIVERY_PATHS=(
  backend/app
  backend/pyproject.toml
  backend/uv.lock
  backend/.python-version
  brfv2-mockup/src
  brfv2-mockup/public
  brfv2-mockup/index.html
  brfv2-mockup/package.json
  brfv2-mockup/package-lock.json
  brfv2-mockup/vite.config.js
  src-tauri
  ops/pins.json
  ops/fetch_pinned.py
  ops/lib
  ops/build-runtime.sh
  ops/package-desktop.sh
  ops/brf-dokument-ai.spec
)

# One fixed, tracked build clock. Declared in ops/pins.json instead of read
# from the commit date, so that the artifact does not change when the commit
# does — see REPRO_DELIVERY_PATHS.
repro_epoch() {
  python3 -c "import json;print(json.load(open('$ROOT/ops/pins.json'))['build']['epoch'])"
}

repro_commit() {
  git -C "$ROOT" rev-parse HEAD
}

repro_dirty() {
  [ -n "$(git -C "$ROOT" status --porcelain)" ] && echo true || echo false
}

# A content hash over exactly the committed sources the artifact is built from.
# Two checkouts that print the same value must produce the same RPM; if they do
# not, the difference came from the environment and is a bug in this build.
repro_delivery_tree() {
  git -C "$ROOT" ls-tree -r HEAD -- "${REPRO_DELIVERY_PATHS[@]}" | sha256sum | cut -d' ' -f1
}

# A distributable artifact has to be attributable to a commit somebody can
# check out. Packaging a dirty tree produces bytes no one can reproduce and
# evidence no one can verify, so it is refused rather than warned about.
repro_require_clean_tree() {
  if [ "$(repro_dirty)" = "true" ]; then
    printf '\033[31mFEL: arbetskatalogen är inte ren.\033[0m\n' >&2
    printf 'Distributionsartefakten identifieras av sin commit; en smutsig checkout\n' >&2
    printf 'går inte att reproducera och kan inte granskas. Committa eller stasha först:\n\n' >&2
    git -C "$ROOT" status --short >&2
    exit 1
  fi
}

# Every timestamp inside the artifact becomes the fixed build epoch. Without
# this the payload carries whatever wall clock the builder had, and two correct
# builds differ for no reason anyone cares about.
repro_stamp_tree() {
  local tree="$1" epoch="$2"
  find "$tree" -exec touch -h -d "@$epoch" {} +
}
