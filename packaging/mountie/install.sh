#!/bin/bash
# Mountie for Linux: into your home folder, onto your app menu. No root needed (except for the two system
# packages it asks for, if they're missing).
#   curl -fsSL https://github.com/wallisoft/mountie-releases/releases/latest/download/install.sh | bash
set -euo pipefail
URL="https://github.com/wallisoft/mountie-releases/releases/latest/download/mountie-linux-x86_64.tar.gz"
DEST="$HOME/.local/share/mountie"
need=()
command -v fusermount3 >/dev/null || need+=(fuse3)
command -v sshfs >/dev/null || need+=(sshfs)
command -v avahi-browse >/dev/null || need+=(avahi-utils)      # finds phones sharing themselves (the Phone tab)
if [ ${#need[@]} -gt 0 ]; then
  echo "Mountie uses ${need[*]} for drives in Files, and to find phones on your Wi-Fi."
  if command -v apt-get >/dev/null; then sudo apt-get install -y "${need[@]}" || echo "(carrying on without: install ${need[*]} later)"
  elif command -v dnf >/dev/null; then sudo dnf install -y "${need[@]/avahi-utils/avahi-tools}" || true
  else echo "Please install: ${need[*]}"; fi
fi
pkill -x Mountie 2>/dev/null || true
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
echo "Downloading Mountie..."
curl -fsSL "$URL" | tar xz -C "$tmp"
rm -rf "$DEST"; mkdir -p "$(dirname "$DEST")"; mv "$tmp/mountie" "$DEST"
mkdir -p "$HOME/.local/bin" "$HOME/.local/share/applications" "$HOME/.local/share/icons/hicolor/256x256/apps"
ln -sf "$DEST/Mountie" "$HOME/.local/bin/mountie"
cp "$DEST/mountie/mountie.png" "$HOME/.local/share/icons/hicolor/256x256/apps/mountie.png"
cat > "$HOME/.local/share/applications/mountie.desktop" <<DESK
[Desktop Entry]
Type=Application
Name=Mountie
Comment=Servers, disk images, folders and RAM, as drives
Exec=$DEST/Mountie
Icon=mountie
Categories=Utility;System;FileTools;
StartupWMClass=Mountie
DESK
update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true
echo "Mountie $(cat "$DEST/VERSION") is installed: it's on your app menu, or type: mountie"
