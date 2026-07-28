#!/usr/bin/env bash
# Prove that the RPM is a function of the sources and not of where they live.
#
#   ops/verify-reproducible.sh <checkout-a> <checkout-b> [commit]
#
# Clones this repository into two directories with deliberately different
# absolute paths, builds the distribution artifact in each, and compares the
# two files byte for byte. Anything that leaks the build location — a source
# path compiled into the shell or into a .pyc, a wall-clock timestamp, the
# builder's hostname — shows up here as two different SHA-256 values.
#
# Writes a machine-readable result to <checkout-a>/../reproducibility.json.
# Takes roughly ten minutes: each checkout downloads nothing it can verify from
# cache, but does compile the Rust shell and stage a 770 MB Python runtime.
set -euo pipefail

SOURCE_REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

A="${1:?ange sökväg för checkout A}"
B="${2:?ange sökväg för checkout B}"
COMMIT="${3:-$(git -C "$SOURCE_REPO" rev-parse HEAD)}"

green() { printf '\033[32m%s\033[0m\n' "$*"; }
step() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
fail() { printf '\033[31mFEL: %s\033[0m\n' "$*" >&2; exit 1; }

[ "$A" != "$B" ] || fail "de två checkouterna måste ligga på olika sökvägar."

prepare() {
  local target="$1"
  rm -rf "$target"
  git clone --quiet --no-local "$SOURCE_REPO" "$target"
  git -C "$target" checkout --quiet --detach "$COMMIT"
  [ -z "$(git -C "$target" status --porcelain)" ] || fail "$target är inte ren efter klon."
  # The two dependency trees the build needs. Both are lock-driven, so this
  # installs the same versions in both checkouts.
  (cd "$target/backend" && uv sync --quiet)
  (cd "$target/brfv2-mockup" && npm ci --silent >/dev/null)
}

build() {
  local target="$1"
  (cd "$target" && ops/build-runtime.sh >/dev/null)
  (cd "$target" && ops/package-desktop.sh >/dev/null)
  find "$target/dist" -name '*.rpm' | sort | tail -1
}

step "Förbereder två checkouter av $COMMIT"
prepare "$A"
prepare "$B"
green "A: $A"
green "B: $B"

step "Bygger i A"
RPM_A="$(build "$A")"
step "Bygger i B"
RPM_B="$(build "$B")"

SHA_A="$(sha256sum "$RPM_A" | cut -d' ' -f1)"
SHA_B="$(sha256sum "$RPM_B" | cut -d' ' -f1)"

step "Jämförelse"
printf '  A  %s  %s\n' "$SHA_A" "$RPM_A"
printf '  B  %s  %s\n' "$SHA_B" "$RPM_B"

RESULT="$(dirname "$A")/reproducibility.json"
IDENTICAL=false
if cmp -s "$RPM_A" "$RPM_B"; then IDENTICAL=true; fi

python3 - "$A" "$B" "$COMMIT" "$RPM_A" "$SHA_A" "$RPM_B" "$SHA_B" "$IDENTICAL" > "$RESULT" <<'PY'
import json, os, sys

a, b, commit, rpm_a, sha_a, rpm_b, sha_b, identical = sys.argv[1:9]
print(json.dumps(
    {
        "schema": "brfv2-desktop-reproducibility/v1",
        "commit": commit,
        "checkouts": [
            {"path": a, "artifact": os.path.basename(rpm_a), "sha256": sha_a,
             "bytes": os.path.getsize(rpm_a)},
            {"path": b, "artifact": os.path.basename(rpm_b), "sha256": sha_b,
             "bytes": os.path.getsize(rpm_b)},
        ],
        "identical": identical == "true",
        "comparedBy": "cmp -s (byte för byte) + sha256sum",
    },
    ensure_ascii=False, indent=2, sort_keys=True,
))
PY

if [ "$IDENTICAL" = "true" ]; then
  green "IDENTISKA — samma bytes från två olika sökvägar. Resultat: $RESULT"
else
  printf '\033[31mOLIKA — artefakten beror fortfarande på byggplatsen.\033[0m\n' >&2
  printf 'Jämför innehållet, till exempel:\n' >&2
  printf '  rpm2cpio %s | cpio -idmv -D /tmp/a\n' "$RPM_A" >&2
  printf '  rpm2cpio %s | cpio -idmv -D /tmp/b\n' "$RPM_B" >&2
  printf '  diff -rq /tmp/a /tmp/b\n' >&2
  exit 1
fi
