#!/usr/bin/env bash
#
# Build Visualised for Linux here, test it, and install it over ~/.local/opt/vml (where install.sh puts it).
#   tools/build-local.sh            build, smoke test, install
#   tools/build-local.sh --no-install
# For patch releases (x.y.z, z > 0): GitHub only builds major and minor tags (vX.Y.0), see .github/workflows/release.yml.
# Same Nuitka command and smoke tests as the Linux job there, so a green local build means the same thing.

set -euo pipefail
cd "$(dirname "$0")/.."
INSTALL=1; [ "${1:-}" = "--no-install" ] && INSTALL=0
VERSION=$(grep -m1 '__version__' vml/__init__.py | cut -d'"' -f2)
VENV="$HOME/.cache/vml-build-venv"
OUT="$HOME/.cache/vml-build"
START=$(date +%s)
echo "==> Visualised $VERSION: local Linux build"

need=()
for p in patchelf python3-venv python3-dev build-essential libxcb-cursor0; do
    dpkg-query -W -f='${Status}' "$p" 2>/dev/null | grep -q "install ok installed" || need+=("$p")
done
[ ${#need[@]} -eq 0 ] || { echo "==> sudo: installing ${need[*]}"; sudo apt-get install -y "${need[@]}"; }

if [ ! -x "$VENV/bin/python" ]; then
    echo "==> Making the build venv (first time only)"
    python3 -m venv "$VENV"
fi
"$VENV/bin/python" -m pip install -q --upgrade pip
"$VENV/bin/python" -m pip install -q -r packaging/build-requirements.txt paramiko mfusepy python-xlib

echo "==> Compiling with Nuitka (the cache makes the second build much quicker)"
rm -rf "$OUT" && mkdir -p "$OUT"
"$VENV/bin/python" -m nuitka --standalone --assume-yes-for-downloads --enable-plugin=pyside6 \
    --include-package=vml --include-package=lupa \
    --include-package=paramiko --include-module=mfusepy --include-package=Xlib \
    --include-data-dir=designer=designer --include-data-dir=vml/lua=lua --include-data-dir=vml/web=web \
    --include-data-dir=csharp=csharp \
    --output-filename=vml --output-dir="$OUT" vml.py

D="$OUT/dist-vml"
mv "$OUT/vml.dist" "$D"
"$VENV/bin/python" packaging/make_icon.py "$D/vml.png"
cp packaging/THIRD-PARTY-NOTICES.txt "$D/"; cp LICENSE "$D/LICENSE.txt"; cp LICENSE-EXCEPTION.md "$D/"

echo "==> Smoke tests"
T="$OUT/smoke"; mkdir -p "$T"
export QT_QPA_PLATFORM=offscreen
fail() { echo "FAILED: $1"; [ -f "${2:-}" ] && cat "$2"; exit 1; }
"$D/vml" parse tests/step1.vml | grep -q "INSERT INTO ui_tree" || fail "parse"
timeout 60 "$D/vml" tests/step1.vml --shot "$T/shot.png" 2> "$T/form.log" || true
test -s "$T/shot.png" || fail "opening a form" "$T/form.log"
timeout 90 "$D/vml" --shot "$T/designer.png" 2> "$T/designer.log" || true
test -s "$T/designer.png" || fail "opening the designer" "$T/designer.log"
timeout 90 "$D/vml" "$D/designer/databases.vml" --shot "$T/script.png" 2> "$T/script.log" || true
test -s "$T/script.png" || fail "a form that runs a script" "$T/script.log"
cp -r "$D" "$T/app" && mv "$T/app/vml" "$T/app/SmokeApp" && cp tests/step1.vml "$T/app/SmokeApp.vml"
VML_DEBUG=1 timeout 60 "$T/app/SmokeApp" --shot "$T/app.png" 2> "$T/app.log" || true
grep -q "SmokeApp.vml: Parsed" "$T/app.log" || fail "an exported app running its own form" "$T/app.log"
timeout 60 "$D/vml" tests/project/Demo.vmlproj --shot "$T/proj.png" 2> "$T/proj.log" || true
test -s "$T/proj.png" && ! grep -q "module helpers.lua" "$T/proj.log" || fail "running a project" "$T/proj.log"
test -f "$D/csharp/VmlCSharpHost/VmlCSharpHost.csproj" || fail "the C# host source is missing"
for f in winforms.vml vb6.vml lib/importkit.lua; do test -f "$D/designer/importers/$f" || fail "importer missing: $f"; done
for f in Designer.vmlproj designer.vml databases.vml modules/files.lua modules/project.lua modules/app.lua; do
    test -f "$D/designer/$f" || fail "designer part missing: $f"
done
test -f "$D/web/android-template.apk" || fail "the Android template is missing"
unset QT_QPA_PLATFORM
echo "    all passed"

tar czf "$OUT/vml-linux-x86_64.tar.gz" -C "$OUT" --transform 's,^dist-vml,vml,' dist-vml

# Also make a .deb (Debian/Ubuntu/Mint) and a no-FUSE AppImage (any distro) — the same packager Bob uses for apps.
echo "==> Linux packages (.deb + AppImage)"
if bash tools/bob/linux-package.sh --bundle "$D" --name visualised --app "Visualised" \
        --version "$VERSION" --exe vml --icon "$D/vml.png" --out "$OUT" \
        --categories "Development;" --depends "libxcb-cursor0" \
        --desc "Visualised - design and build cross-platform apps with VML, no coding required"; then
    ls "$OUT"/*.deb "$OUT"/*.AppImage 2>/dev/null | sed 's,^,    ,'
else
    echo "    (couldn't build .deb/AppImage - the tar.gz is still here)"
fi

if [ $INSTALL -eq 1 ]; then
    echo "==> Installing over ~/.local/opt/vml"
    rm -rf "$HOME/.local/opt/vml" && mkdir -p "$HOME/.local/opt/vml"
    tar xzf "$OUT/vml-linux-x86_64.tar.gz" -C "$HOME/.local/opt/vml" --strip-components=1
    mkdir -p "$HOME/.local/bin" && ln -sf "$HOME/.local/opt/vml/vml" "$HOME/.local/bin/vml"
fi
echo "==> Visualised $VERSION built in $(( ($(date +%s) - START) / 60 ))m $(( ($(date +%s) - START) % 60 ))s: $OUT/vml-linux-x86_64.tar.gz"
