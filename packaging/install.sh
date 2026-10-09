#!/usr/bin/env bash
#
# Visualised installer for Linux (Ubuntu 22.04+ and similar).
#   curl -fsSL https://github.com/wallisoft/vml-releases/releases/latest/download/install.sh | bash
# Installs into your home folder: the designer in your app menu, `vml` in ~/.local/bin, and .vml files
# opening in VML. Asks for your password only to add one small system library. Re-run to update.

set -euo pipefail

URL="${VML_URL:-https://github.com/wallisoft/vml-releases/releases/latest/download/vml-linux-x86_64.tar.gz}"
DEST="$HOME/.local/opt/vml"

if [ "$(id -u)" -eq 0 ]; then
    echo "Please run this as your normal user, not root. It asks for sudo only when it needs it." >&2
    exit 1
fi

echo "==> Installing Visualised into $DEST"
if command -v apt-get >/dev/null 2>&1; then
    if ! dpkg-query -W -f='${Status}' libxcb-cursor0 2>/dev/null | grep -q "install ok installed"; then
        echo "==> Need sudo now: installing libxcb-cursor0 (Qt needs it)"
        sudo apt-get install -y libxcb-cursor0 || echo "    (apt reported errors; carrying on)"
    fi
fi

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
echo "==> Downloading the latest Visualised"
curl -fsSL "$URL" -o "$tmp/vml.tar.gz"
rm -rf "$DEST"
mkdir -p "$DEST"
tar xzf "$tmp/vml.tar.gz" -C "$DEST" --strip-components=1
chmod +x "$DEST/vml"

mkdir -p "$HOME/.local/bin" "$HOME/.local/share/applications" "$HOME/.local/share/mime/packages"
ln -sf "$DEST/vml" "$HOME/.local/bin/vml"

cat > "$HOME/.local/share/mime/packages/vml.xml" << MIME
<?xml version="1.0" encoding="UTF-8"?>
<mime-info xmlns="http://www.freedesktop.org/standards/shared-mime-info">
  <mime-type type="application/x-vml">
    <comment>VML form</comment>
    <glob pattern="*.vml"/>
    <glob pattern="*.vmlproj"/>
  </mime-type>
</mime-info>
MIME
command -v update-mime-database >/dev/null && update-mime-database "$HOME/.local/share/mime" >/dev/null 2>&1 || true

rm -f "$HOME/.local/share/applications/vml.desktop"
cat > "$HOME/.local/share/applications/visualised.desktop" << DESKTOP
[Desktop Entry]
Type=Application
Name=Visualised
Comment=Design desktop and web apps in VML
Exec=$DEST/vml %f
Icon=$DEST/vml.png
Terminal=false
Categories=Development;IDE;
MimeType=application/x-vml;
StartupNotify=false
DESKTOP
command -v update-desktop-database >/dev/null && update-desktop-database "$HOME/.local/share/applications" >/dev/null 2>&1 || true
command -v xdg-mime >/dev/null && xdg-mime default visualised.desktop application/x-vml >/dev/null 2>&1 || true

echo
echo "Done. Visualised is in your app menu; .vml files open in VML; and 'vml' works in a terminal"
case ":$PATH:" in *":$HOME/.local/bin:"*) ;; *) echo "(open a new terminal first, so ~/.local/bin is on your PATH)";; esac
