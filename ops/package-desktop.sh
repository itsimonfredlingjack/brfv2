#!/usr/bin/env bash
# Build the Fedora distribution artifact (RPM) for BRF Dokument-AI.
#
#   ops/package-desktop.sh             build only
#   ops/package-desktop.sh --install   build, then install with dnf (needs sudo)
#
# Packaging is done with Fedora's own rpmbuild rather than Tauri's RPM bundler.
# The bundler produced a correct staging tree but did not finish packing this
# payload in 27 minutes of CPU in two separate attempts (default gzip and
# configured zstd), while compressing the same bytes with the system compressor
# takes seconds — the cost is not the compression. rpmbuild packs the identical
# tree in under a minute, is the native tool on the target distribution, and
# lets the payload compressor be chosen explicitly. Tauri still produces the
# binary and owns the window/asset side; only the packing step is ours.
#
# The artifact is a function of the commit and nothing else. Two clean
# checkouts of the same commit, at different paths, produce RPM files with the
# same SHA-256. What that costs, and why each piece is here:
#
#   clean tree required   an artifact nobody can check out is an artifact
#                         nobody can reproduce
#   SOURCE_DATE_EPOCH     the commit's own timestamp is the only clock the
#                         build reads
#   --remap-path-prefix   the checkout path never reaches the compiled shell
#   stamped buildroot     no wall-clock mtimes in the payload
#   fixed build host      the builder's hostname is not part of the product
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
# shellcheck source=ops/lib/repro.sh
source "$ROOT/ops/lib/repro.sh"

APPNAME="BRF Dokument-AI"
BINNAME="brfv2-desktop"
PKGNAME="brf-dokument-ai"

# Stand-ins for the two values rpm would otherwise take from the machine.
# `%{_buildhost}` lands in the package header verbatim; the remapped source
# root shows up in any path the Rust compiler records.
BUILD_HOST="reproducible.brfdokumentai.se"
SOURCE_PREFIX="/builddir/brfv2"

INSTALL=0
[ "${1:-}" = "--install" ] && INSTALL=1

green() { printf '\033[32m%s\033[0m\n' "$*"; }
step() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
fail() { printf '\033[31mFEL: %s\033[0m\n' "$*" >&2; exit 1; }

command -v rpmbuild >/dev/null 2>&1 || fail "rpmbuild saknas — kör 'sudo dnf install rpm-build'."
[ -d src-tauri/runtime/python ] || fail "src-tauri/runtime saknas — kör 'make desktop-runtime' först."
[ -f src-tauri/runtime/BUNDLE.json ] || fail "src-tauri/runtime/BUNDLE.json saknas — kör om 'make desktop-runtime'."
[ -d brfv2-mockup/node_modules ] || fail "brfv2-mockup/node_modules saknas — kör 'make setup' först."

repro_require_clean_tree
COMMIT="$(repro_commit)"
EPOCH="$(repro_epoch)"
DELIVERY_TREE="$(repro_delivery_tree)"
export SOURCE_DATE_EPOCH="$EPOCH"

# The staged runtime is an input to this build, so it has to belong to the same
# sources. Otherwise the package would carry a Python tree from one revision
# and a shell from another, and its provenance record would be fiction.
BUNDLE_TREE="$(python3 -c "import json;print(json.load(open('src-tauri/runtime/BUNDLE.json')).get('deliveryTree') or '')")"
[ -n "$BUNDLE_TREE" ] || fail \
  "den stegade körmiljön saknar härkomst (byggd från en smutsig checkout) — kör om 'make desktop-runtime'."
[ "$BUNDLE_TREE" = "$DELIVERY_TREE" ] || fail \
  "den stegade körmiljön är byggd från andra källor än den här checkouten
  bundle:   $BUNDLE_TREE
  checkout: $DELIVERY_TREE
  Kör om 'make desktop-runtime'."

VERSION="$(python3 -c "import json;print(json.load(open('src-tauri/tauri.conf.json'))['version'])")"

step "Kanoniskt UI"
(cd brfv2-mockup && npm run build)
[ -f brfv2-mockup/dist/index.html ] || fail "frontendbygget producerade ingen dist/index.html"

step "Skal (release)"
# Two separate leaks have to be closed here, and each needs its own mechanism.
#
# rustc records source paths for panic locations and debug info:
#   --remap-path-prefix rewrites them to a fixed stand-in.
#
# `tauri::generate_context!` bakes CARGO_MANIFEST_DIR into the binary as a
# string at macro-expansion time. --remap-path-prefix cannot reach that — it
# rewrites paths the compiler emits, not values a macro read from the
# environment. So the crate is compiled through a canonical symlink instead,
# and CARGO_MANIFEST_DIR becomes the same path from every checkout. This is the
# same trick a distribution build does by always building in /builddir; the
# target directory stays inside the checkout, so nothing is shared but the name.
CANONICAL_SHELL="${BRFV2_SHELL_BUILD_LINK:-/var/tmp/brfv2-desktop-shell}"
if [ -e "$CANONICAL_SHELL" ] && [ ! -L "$CANONICAL_SHELL" ]; then
  fail "$CANONICAL_SHELL finns och är inte en symlänk — ta bort den eller sätt BRFV2_SHELL_BUILD_LINK."
fi
ln -sfn "$ROOT/src-tauri" "$CANONICAL_SHELL"
[ "$(readlink "$CANONICAL_SHELL")" = "$ROOT/src-tauri" ] || fail "kunde inte peka om $CANONICAL_SHELL."

# The dependency sources are just as much a build location as the checkout is:
# every crate rustc compiles records where it was read from, and left alone
# that puts ~/.cargo and ~/.rustup — and therefore the builder's user name —
# into the shipped executable.
CARGO_HOME_DIR="${CARGO_HOME:-$HOME/.cargo}"
RUSTUP_HOME_DIR="${RUSTUP_HOME:-$HOME/.rustup}"
RUSTFLAGS="--remap-path-prefix=$ROOT=$SOURCE_PREFIX \
--remap-path-prefix=$CARGO_HOME_DIR=/builddir/cargo \
--remap-path-prefix=$RUSTUP_HOME_DIR=/builddir/rustup ${RUSTFLAGS:-}" \
CARGO_INCREMENTAL=0 \
  cargo build --release --locked --manifest-path "$CANONICAL_SHELL/Cargo.toml"
rm -f "$CANONICAL_SHELL"
[ -x "src-tauri/target/release/$BINNAME" ] || fail "release-binären saknas"

# Note the shape: `grep -c` reads its input to the end. With `grep -q` the
# pipeline's left side dies of SIGPIPE the moment a match is found, and under
# `set -o pipefail` that non-zero status makes the `if` look like "no match" —
# a guard that silently never fires. This one fires.
for leak in "$ROOT" "$HOME"; do
  found="$(strings -a "src-tauri/target/release/$BINNAME" | { grep -cF -- "$leak" || true; })"
  [ "$found" -eq 0 ] || fail \
    "release-binären innehåller $found förekomst(er) av $leak — bygget är inte platsoberoende."
done

# ---------------------------------------------------------------------------
step "Buildroot"
# ---------------------------------------------------------------------------
# The layout is not free-form: tauri-utils resolves resources to
# /usr/lib/<productName> at runtime, so that exact path — spaces and all — is
# what the application will look in.
BUILD="$ROOT/src-tauri/target/rpm"
BUILDROOT="$BUILD/buildroot"
rm -rf "$BUILD"
mkdir -p \
  "$BUILDROOT/usr/bin" \
  "$BUILDROOT/usr/lib/$APPNAME" \
  "$BUILDROOT/usr/share/applications" \
  "$BUILDROOT/usr/share/icons/hicolor/32x32/apps" \
  "$BUILDROOT/usr/share/icons/hicolor/128x128/apps" \
  "$BUILDROOT/usr/share/icons/hicolor/256x256/apps" \
  "$BUILD/rpmbuild"/{BUILD,RPMS,SOURCES,SPECS,SRPMS}

install -m 0755 "src-tauri/target/release/$BINNAME" "$BUILDROOT/usr/bin/$BINNAME"
cp -a src-tauri/runtime "$BUILDROOT/usr/lib/$APPNAME/runtime"
cp -a brfv2-mockup/dist "$BUILDROOT/usr/lib/$APPNAME/ui"
# Build-only artifacts that should not ship.
rm -f "$BUILDROOT/usr/lib/$APPNAME/runtime/requirements.lock.txt"

install -m 0644 src-tauri/icons/32x32.png "$BUILDROOT/usr/share/icons/hicolor/32x32/apps/$BINNAME.png"
install -m 0644 src-tauri/icons/128x128.png "$BUILDROOT/usr/share/icons/hicolor/128x128/apps/$BINNAME.png"
install -m 0644 "src-tauri/icons/128x128@2x.png" "$BUILDROOT/usr/share/icons/hicolor/256x256/apps/$BINNAME.png"

cat > "$BUILDROOT/usr/share/applications/$APPNAME.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=$APPNAME
GenericName=Dokument-Q&A för bostadsrättsföreningar
Comment=Grundade svar ur föreningens egna dokument, med exakt källhänvisning
Exec=$BINNAME
Icon=$BINNAME
Terminal=false
Categories=Office;Viewer;
Keywords=BRF;bostadsrätt;dokument;PDF;stadgar;AI;
StartupWMClass=$BINNAME
StartupNotify=true
EOF
chmod 0644 "$BUILDROOT/usr/share/applications/$APPNAME.desktop"

# Every file in the payload now carries the commit's timestamp instead of the
# moment this script happened to run.
repro_stamp_tree "$BUILDROOT" "$EPOCH"
green "buildroot klar ($(du -sh --apparent-size "$BUILDROOT" | cut -f1)), tidsstämplad @$EPOCH"

# ---------------------------------------------------------------------------
step "RPM"
# ---------------------------------------------------------------------------
cp ops/"$PKGNAME".spec "$BUILD/rpmbuild/SPECS/"
rpmbuild -bb "$BUILD/rpmbuild/SPECS/$PKGNAME.spec" \
  --define "_topdir $BUILD/rpmbuild" \
  --define "stagedroot $BUILDROOT" \
  --define "brfversion $VERSION" \
  --define "_buildhost $BUILD_HOST" \
  --define "use_source_date_epoch_as_buildtime 1" \
  --define "build_mtime_policy clamp_to_source_date_epoch" \
  --noclean 2>&1 | sed 's/^/  /'

RPM="$(find "$BUILD/rpmbuild/RPMS" -name "$PKGNAME-*.rpm" | sort | tail -1)"
[ -n "$RPM" ] || fail "hittade ingen byggd RPM under $BUILD/rpmbuild/RPMS"
mkdir -p dist
cp -f "$RPM" dist/
RPM="dist/$(basename "$RPM")"
SHA="$(sha256sum "$RPM" | cut -d' ' -f1)"
green "Artefakt:     $RPM ($(du -h "$RPM" | cut -f1))"
green "SHA-256:      $SHA"
green "Commit:       $COMMIT"
green "Delivery tree: $DELIVERY_TREE"

# A machine-readable receipt beside the artifact, so the acceptance evidence
# never has to be retyped from a terminal scrollback.
python3 - "$RPM" "$SHA" "$COMMIT" "$EPOCH" "$BUILD_HOST" "$SOURCE_PREFIX" "$DELIVERY_TREE" \
  > "dist/$(basename "$RPM").provenance.json" <<'PY'
import json, os, subprocess, sys

rpm, sha, commit, epoch, build_host, source_prefix, delivery_tree = sys.argv[1:8]
bundle = json.load(open("src-tauri/runtime/BUNDLE.json"))


def query(tag: str) -> str:
    # rpm exits 0 and prints "unknown tag" on stderr for a tag this rpm does
    # not have, so an unchecked query silently records an empty string.
    result = subprocess.run(
        ["rpm", "-qp", "--qf", "%%{%s}" % tag, rpm], capture_output=True, text=True, check=True
    )
    value = result.stdout.strip()
    if not value:
        raise SystemExit(f"FEL: rpm-taggen {tag} gav inget värde: {result.stderr.strip()}")
    return value


print(json.dumps(
    {
        "schema": "brfv2-desktop-artifact/v1",
        "artifact": os.path.basename(rpm),
        "sha256": sha,
        "bytes": os.path.getsize(rpm),
        "commit": commit,
        "dirty": False,
        "deliveryTree": delivery_tree,
        "sourceDateEpoch": int(epoch),
        "rpm": {
            "nevra": "%s-%s-%s.%s" % tuple(
                query(tag) for tag in ("NAME", "VERSION", "RELEASE", "ARCH")
            ),
            "buildTime": int(query("BUILDTIME")),
            "buildHost": query("BUILDHOST"),
            "headerSha256": query("SHA256HEADER"),
            "payloadCompressor": query("PAYLOADCOMPRESSOR"),
        },
        "reproducibility": {
            "sourcePrefix": source_prefix,
            "buildHost": build_host,
            "mtimePolicy": "clamp_to_source_date_epoch",
        },
        "bundle": bundle,
    },
    ensure_ascii=False, indent=2, sort_keys=True,
))
PY
green "Kvitto:   dist/$(basename "$RPM").provenance.json"

step "Paketets metadata"
rpm -qip "$RPM" | sed -n '1,14p'
echo "-- beroenden --"
rpm -qRp "$RPM" | sort -u | sed 's/^/  /'
echo "-- toppnivåinnehåll --"
rpm -qlp "$RPM" | awk -F/ 'NF<=5' | sort -u | head -20

if [ "$INSTALL" -eq 1 ]; then
  step "Installation"
  sudo dnf install -y "$RPM"
  green "Installerad. Starta från applikationsmenyn eller med: $BINNAME"
fi
