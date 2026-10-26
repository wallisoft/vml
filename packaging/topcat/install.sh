#!/usr/bin/env bash
#
# TopCat installer for Linux (Ubuntu 22.04+ and similar).
#   curl -fsSL https://github.com/wallisoft/vml/releases/download/topcat-v0.2/install.sh | bash
# Installs into your home folder: TopCat in your app menu and `topcat` in ~/.local/bin.
# Asks for your password only to add one small system library. Re-run to update.

set -euo pipefail

URL="${TOPCAT_URL:-https://github.com/wallisoft/vml/releases/download/topcat-v0.2/topcat-linux-x86_64.tar.gz}"
DEST="$HOME/.local/opt/topcat"

if [ "$(id -u)" -eq 0 ]; then
    echo "Please run this as your normal user, not root. It asks for sudo only when it needs it." >&2
    exit 1
fi

echo "==> Installing TopCat into $DEST"
if command -v apt-get >/dev/null 2>&1; then
    if ! dpkg-query -W -f='${Status}' libxcb-cursor0 2>/dev/null | grep -q "install ok installed"; then
        echo "==> Need sudo now: installing libxcb-cursor0 (Qt needs it)"
        sudo apt-get install -y libxcb-cursor0 || echo "    (apt reported errors; carrying on)"
    fi
fi

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
echo "==> Downloading the latest TopCat"
curl -fsSL "$URL" -o "$tmp/topcat.tar.gz"
rm -rf "$DEST"
mkdir -p "$DEST"
tar xzf "$tmp/topcat.tar.gz" -C "$DEST" --strip-components=1
chmod +x "$DEST/TopCat"

mkdir -p "$HOME/.local/bin" "$HOME/.local/share/applications"
ln -sf "$DEST/TopCat" "$HOME/.local/bin/topcat"

cat > "$HOME/.local/share/applications/topcat.desktop" << DESKTOP
[Desktop Entry]
Type=Application
Name=TopCat
Comment=Ask your machines' tools from anywhere, even via Claude
Exec=$DEST/TopCat
Icon=$DEST/topcat/topcat.png
Terminal=false
Categories=Utility;
StartupNotify=false
DESKTOP
command -v update-desktop-database >/dev/null && update-desktop-database "$HOME/.local/share/applications" >/dev/null 2>&1 || true

echo
echo "Done. TopCat is in your app menu, and 'topcat' works in a terminal."
case ":$PATH:" in *":$HOME/.local/bin:"*) ;; *) echo "(open a new terminal first, so ~/.local/bin is on your PATH)";; esac
