#!/usr/bin/env bash
#
# No-Stick installer for Linux (Ubuntu, Mint, Debian and similar).
#   curl -fsSL https://github.com/wallisoft/no-stick-releases/releases/latest/download/install.sh | bash
# Installs into your home folder: No-Stick in your app menu and `no-stick` in ~/.local/bin.
# No-Stick is a Visualised app, so this fetches the Visualised runtime first if you don't have it.
# Nothing here touches your boot menu: that only happens when you ask No-Stick to. Re-run to update.

set -euo pipefail

main() {
    local REL="https://github.com/wallisoft/no-stick-releases/releases/latest/download"
    local URL="${NOSTICK_URL:-$REL/no-stick.tar.gz}"
    local VML_INSTALLER="https://github.com/wallisoft/vml-releases/releases/latest/download/install.sh"
    local VML_BIN="$HOME/.local/opt/vml/vml"
    local DEST="$HOME/.vml/apps/no-stick"

    if [ "$(id -u)" -eq 0 ]; then
        echo "Please run this as your normal user, not root." >&2
        exit 1
    fi

    if [ ! -x "$VML_BIN" ]; then
        echo "==> No-Stick runs on Visualised: installing that first"
        curl -fsSL "$VML_INSTALLER" | bash
    fi
    if [ ! -x "$VML_BIN" ]; then
        echo "Visualised didn't install, so No-Stick can't run. See the messages above." >&2
        exit 1
    fi

    tmp="$(mktemp -d)"                       # not local: the exit trap below still needs it
    trap 'rm -rf "$tmp"' EXIT
    echo "==> Downloading the latest No-Stick"
    curl -fsSL "$URL" -o "$tmp/no-stick.tar.gz"
    rm -rf "$DEST"
    rm -rf "$HOME/.local/opt/no-stick"       # where No-Stick 0.2 and earlier lived
    mkdir -p "$DEST"
    tar xzf "$tmp/no-stick.tar.gz" -C "$DEST" --strip-components=1
    echo "==> Installed No-Stick $(cat "$DEST/VERSION" 2>/dev/null || echo "") into $DEST"

    mkdir -p "$HOME/.local/bin" "$HOME/.local/share/applications"
    cat > "$HOME/.local/bin/no-stick" << LAUNCH
#!/bin/sh
exec "$VML_BIN" "$DEST/no-stick.vml" "\$@"
LAUNCH
    chmod +x "$HOME/.local/bin/no-stick"

    cat > "$HOME/.local/share/applications/no-stick.desktop" << DESKTOP
[Desktop Entry]
Type=Application
Name=No-Stick
Comment=Boot ISOs and virtual disks on real hardware, with no USB stick
Exec="$VML_BIN" "$DEST/no-stick.vml"
Icon=$DEST/no-stick.png
Terminal=false
Categories=System;Utility;
StartupNotify=false
DESKTOP
    command -v update-desktop-database >/dev/null && update-desktop-database "$HOME/.local/share/applications" >/dev/null 2>&1 || true

    # say plainly what No-Stick will need when it is used; none of this stops the install
    local missing=""
    for c in losetup blkid findmnt grub-reboot pkexec; do
        command -v "$c" >/dev/null 2>&1 || [ -x "/usr/sbin/$c" ] || [ -x "/sbin/$c" ] || missing="$missing $c"
    done
    echo
    echo "Done. No-Stick is in your app menu, and 'no-stick' works in a terminal"
    case ":$PATH:" in *":$HOME/.local/bin:"*) ;; *) echo "(open a new terminal first, so ~/.local/bin is on your PATH)";; esac
    if [ ! -d /boot/grub ]; then
        echo "Note: No-Stick adds its entry to the GRUB boot menu, and this PC doesn't appear to use GRUB (/boot/grub is missing)."
    fi
    if [ -n "$missing" ]; then
        echo "Note: these tools weren't found and No-Stick uses them:$missing"
    fi
}

main "$@"
