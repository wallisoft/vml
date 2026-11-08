#!/usr/bin/env bash
#
# One-time setup for tools/desk-watch.sh (away from desk, by Bluetooth):
#   1. which paired phone is the key (pair it first: Settings, Bluetooth)
#   2. lets l2ping ask it without sudo (one sudo, once)
#   3. on the Windows PC, a task that unlocks its screen again when you're back
#   4. runs the watcher as a service of yours: starts with your desktop, restarts if it stops
#   tools/desk-setup.sh          (again any time to change the phone or the PC)
#   tools/desk-setup.sh off      stop it

set -euo pipefail
cd "$(dirname "$0")/.."
UNIT="$HOME/.config/systemd/user/bob-desk.service"
if [ "${1:-}" = off ]; then
    systemctl --user disable --now bob-desk.service 2>/dev/null || true
    echo "Away from desk is off."; exit 0
fi

echo "==> Your phone"
mapfile -t devs < <({ bluetoothctl devices Paired 2>/dev/null || bluetoothctl paired-devices; } | sed -n 's/^Device //p')
[ ${#devs[@]} -gt 0 ] || { echo "Nothing is paired with this computer: pair your phone in Settings, Bluetooth, then run this again."; exit 1; }
for i in "${!devs[@]}"; do echo "   $((i + 1))) ${devs[$i]}"; done
read -rp "    Which one is your phone? " n
PHONE=$(echo "${devs[$((n - 1))]}" | cut -d' ' -f1)
read -rp "    The Windows PC to lock and unlock too [a8]: " HOST; HOST=${HOST:-a8}

echo "==> Letting l2ping ask the phone without sudo (once)"
command -v l2ping > /dev/null || sudo apt-get install -y bluez
sudo setcap cap_net_raw+ep "$(readlink -f "$(command -v l2ping)")"
l2ping -c 1 -t 5 "$PHONE" > /dev/null 2>&1 && echo "    the phone answers" || echo "    the phone didn't answer: is its Bluetooth on, and is it near? (carrying on)"

mkdir -p "$HOME/.config/bob"
printf 'PHONE=%s\nHOST=%s\nMISSES=3\nUNLOCK=yes\n' "$PHONE" "$HOST" > "$HOME/.config/bob/desk"

echo "==> On $HOST: a task to unlock its screen when you're back"
PS=$(cat <<'PSEOF'
$d = "C:\ProgramData\bob"; New-Item -ItemType Directory -Force $d | Out-Null
Set-Content "$d\unlock.ps1" '$id = (Get-Process explorer -ErrorAction SilentlyContinue | Select-Object -First 1).SessionId; if ($id) { tscon $id /dest:console }'
$a = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File $d\unlock.ps1"
Register-ScheduledTask -TaskName "BobUnlock" -Action $a -User "SYSTEM" -RunLevel Highest -Force | Out-Null
"    BobUnlock is ready"
PSEOF
)
ssh -o BatchMode=yes -o ConnectTimeout=6 "$HOST" "powershell -NoProfile -EncodedCommand $(printf %s "$PS" | iconv -f UTF-8 -t UTF-16LE | base64 -w0)" \
    || echo "    couldn't reach $HOST: it'll only be locked, not unlocked, till this is run again with it awake"

echo "==> Running it as a service of yours"
mkdir -p "$(dirname "$UNIT")"
cat > "$UNIT" <<UNITEOF
[Unit]
Description=Bob: away from desk, by Bluetooth
After=graphical-session.target

[Service]
ExecStart=$PWD/tools/desk-watch.sh
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
UNITEOF
chmod +x tools/desk-watch.sh
systemctl --user daemon-reload
systemctl --user enable --now bob-desk.service
systemctl --user restart bob-desk.service
sleep 2
journalctl --user -u bob-desk.service -n 3 --no-pager -o cat
echo "==> Done: walk away with your phone and both screens lock; come back and they unlock. (tools/desk-setup.sh off to stop)"
