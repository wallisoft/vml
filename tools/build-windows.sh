#!/usr/bin/env bash
#
# Build Visualised for Windows on a Windows PC over SSH, from here, and bring the results back:
#   tools/build-windows.sh          the PC called a8 in ~/.ssh/config
#   tools/build-windows.sh HOST     another one
# Sends this folder as it is (uncommitted changes too, not what .gitignore leaves out), runs tools/build-windows.ps1
# there (Nuitka, the release job's smoke tests, Inno Setup, the zip, and the Store package when the PC has
# makeappx), and copies Visualised-Setup.exe, vml-windows-x64.zip (and Visualised.msix) to ~/.cache/vml-build-windows.
# The PC needs OpenSSH Server and this machine's key; it installs Python 3.12 and Inno Setup itself the first time.

set -euo pipefail
cd "$(dirname "$0")/.."
HOST="${1:-a8}"
VERSION=$(grep -m1 '__version__' vml/__init__.py | cut -d'"' -f2)
OUT="$HOME/.cache/vml-build-windows"           # (not under vml-build: build-local.sh clears that)
START=$(date +%s)
SSH=(ssh -o ConnectTimeout=10 -o ServerAliveInterval=30 -o ServerAliveCountMax=6)
echo "==> Visualised $VERSION: Windows build on $HOST"

"${SSH[@]}" "$HOST" "echo ok" > /dev/null 2>&1 || { echo "Can't reach $HOST over SSH: is it on, and awake?"; exit 1; }

echo "==> Sending the source"
STAGE=$(mktemp -d); trap 'rm -rf "$STAGE"' EXIT
mkdir "$STAGE/vml-build"
git ls-files -z --cached --others --exclude-standard | python3 -c '
import sys, zipfile, os
names = [n for n in sys.stdin.buffer.read().decode().split("\0") if n and os.path.isfile(n)]
with zipfile.ZipFile(sys.argv[1], "w", zipfile.ZIP_DEFLATED) as z:
    for n in names:
        z.write(n)
print(f"    {len(names)} files")' "$STAGE/vml-build/src.zip"
cp tools/build-windows.ps1 "$STAGE/vml-build/"

# the Store package's names, as the release job has them (GitHub variables), if gh can read them
if command -v gh > /dev/null && ID=$(gh variable get MSIX_IDENTITY_NAME -R wallisoft/vml 2>/dev/null) && [ -n "$ID" ]; then
    ID="$ID" PUB="$(gh variable get MSIX_PUBLISHER -R wallisoft/vml)" \
    PUBDISP="$(gh variable get MSIX_PUBLISHER_DISPLAY -R wallisoft/vml)" \
    NAME="$(gh variable get MSIX_DISPLAY_NAME -R wallisoft/vml 2>/dev/null || echo Visualised)" \
    python3 -c 'import json, os; print(json.dumps({"id": os.environ["ID"], "publisher": os.environ["PUB"],
        "publisher_display": os.environ["PUBDISP"], "name": os.environ["NAME"] or "Visualised"}))' > "$STAGE/vml-build/msix.json"
fi
scp -q -r "$STAGE/vml-build" "$HOST:"

"${SSH[@]}" "$HOST" "powershell -NoProfile -ExecutionPolicy Bypass -File vml-build\\build-windows.ps1 -Version $VERSION"

echo "==> Bringing the results back"
rm -rf "$OUT" && mkdir -p "$OUT"
scp -q "$HOST:vml-build/out/*" "$OUT/"
chmod -R u+rw,go+r "$OUT"                       # (files from Windows can arrive without the read bit)
ls -lh "$OUT" | tail -n +2 | awk '{print "    " $5 "  " $NF}'
echo "==> Visualised $VERSION for Windows in $(( ($(date +%s) - START) / 60 ))m $(( ($(date +%s) - START) % 60 ))s: $OUT"
