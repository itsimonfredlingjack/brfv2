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
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

APPNAME="BRF Dokument-AI"
BINNAME="brfv2-desktop"
PKGNAME="brf-dokument-ai"

INSTALL=0
[ "${1:-}" = "--install" ] && INSTALL=1

green() { printf '\033[32m%s\033[0m\n' "$*"; }
step() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
fail() { printf '\033[31mFEL: %s\033[0m\n' "$*" >&2; exit 1; }

command -v rpmbuild >/dev/null 2>&1 || fail "rpmbuild saknas — kör 'sudo dnf install rpm-build'."
[ -d src-tauri/runtime/python ] || fail "src-tauri/runtime saknas — kör 'make desktop-runtime' först."
[ -f src-tauri/runtime/BUNDLE.json ] || fail "src-tauri/runtime/BUNDLE.json saknas — kör om 'make desktop-runtime'."
[ -d brfv2-mockup/node_modules ] || fail "brfv2-mockup/node_modules saknas — kör 'make setup' först."

VERSION="$(python3 -c "import json;print(json.load(open('src-tauri/tauri.conf.json'))['version'])")"

step "Kanoniskt UI"
(cd brfv2-mockup && npm run build)
[ -f brfv2-mockup/dist/index.html ] || fail "frontendbygget producerade ingen dist/index.html"

step "Skal (release)"
cargo build --release --locked --manifest-path src-tauri/Cargo.toml
[ -x "src-tauri/target/release/$BINNAME" ] || fail "release-binären saknas"

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
green "buildroot klar ($(du -sh --apparent-size "$BUILDROOT" | cut -f1))"

# ---------------------------------------------------------------------------
step "RPM"
# ---------------------------------------------------------------------------
cp ops/"$PKGNAME".spec "$BUILD/rpmbuild/SPECS/"
rpmbuild -bb "$BUILD/rpmbuild/SPECS/$PKGNAME.spec" \
  --define "_topdir $BUILD/rpmbuild" \
  --define "stagedroot $BUILDROOT" \
  --define "brfversion $VERSION" \
  --noclean 2>&1 | sed 's/^/  /'

RPM="$(find "$BUILD/rpmbuild/RPMS" -name "$PKGNAME-*.rpm" | sort | tail -1)"
[ -n "$RPM" ] || fail "hittade ingen byggd RPM under $BUILD/rpmbuild/RPMS"
mkdir -p dist
cp -f "$RPM" dist/
RPM="dist/$(basename "$RPM")"
green "Artefakt: $RPM ($(du -h "$RPM" | cut -f1))"

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
