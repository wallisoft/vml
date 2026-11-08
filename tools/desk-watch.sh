#!/usr/bin/env bash
#
# Away from desk, by Bluetooth: when your phone goes out of range of this computer, lock this computer's screen and
# the Windows PC's; when it comes back, unlock both, and log how long you were away. Nothing to press.
#
# Runs in the background as a service of yours (tools/desk-setup.sh puts it there and does the one-time setup).
# It asks the phone over Bluetooth every few seconds (l2ping: the phone only has to be paired with this computer
# and have Bluetooth on; no app on it). A few missed answers in a row is "gone", so a dropped ping doesn't lock you.
#
#   ~/.config/bob/desk          PHONE=AA:BB:CC:DD:EE:FF   HOST=a8   MISSES=3   UNLOCK=yes
#   ~/.local/share/bob/away.csv date,away,back,minutes   (Bob shows today's total along its foot)
#
# The phone is the key: while it's near, both screens unlock themselves. UNLOCK=no to only lock.
# While you're away, anyone touching this computer's keyboard or mouse sets off an alarm (sound and a spoken
# warning), and you're told when you're back. ALARM=no for none. (It gives your phone a few seconds to be seen
# first, so you coming back doesn't set it off.)

set -u
CONF="$HOME/.config/bob/desk"
LOG="$HOME/.local/share/bob/away.csv"
PHONE="" HOST="a8" MISSES=3 UNLOCK=yes ALARM=yes
[ -f "$CONF" ] && . "$CONF"
[ -n "$PHONE" ] || { echo "no PHONE= in $CONF: run tools/desk-setup.sh"; exit 1; }
SSH=(ssh -o BatchMode=yes -o ConnectTimeout=4)

session() {   # this user's desktop session, to lock and unlock (a service isn't in it, so it has to ask)
    loginctl show-user "${USER:-$(id -un)}" -p Display --value 2>/dev/null
}

lock_all() {
    "${SSH[@]}" "$HOST" "tsdiscon console" > /dev/null 2>&1 &         # the Windows PC: back to its lock screen
    loginctl lock-session "$(session)"
}

unlock_all() {
    loginctl unlock-session "$(session)"
    [ "$HOST" ] && "${SSH[@]}" "$HOST" "schtasks /run /tn BobUnlock" > /dev/null 2>&1 &
}

idle_ms() {   # how long since anyone touched this computer's keyboard or mouse (GNOME; lock screen included)
    gdbus call --session --dest org.gnome.Mutter.IdleMonitor --object-path /org/gnome/Mutter/IdleMonitor/Core \
        --method org.gnome.Mutter.IdleMonitor.GetIdletime 2>/dev/null | sed -n 's/.*uint64 \([0-9]*\).*/\1/p'
}

alarm() {
    pactl set-sink-mute @DEFAULT_SINK@ 0 > /dev/null 2>&1          # (heard even if it was muted)
    for _ in 1 2 3; do
        paplay /usr/share/sounds/freedesktop/stereo/alarm-clock-elapsed.oga 2>/dev/null \
            || canberra-gtk-play -i alarm-clock-elapsed 2>/dev/null || printf '\a'
    done
    spd-say -w "Hands off, please. This computer is locked." > /dev/null 2>&1
}

here=1 miss=0 since=0 first=0 touched="" stirred=0 rang=0
echo "watching $PHONE: away after $MISSES missed answers; locking this computer and $HOST"
while true; do
    if l2ping -c 1 -t 3 "$PHONE" > /dev/null 2>&1; then
        miss=0
        if [ $here -eq 0 ]; then                                       # back
            here=1
            [ "$UNLOCK" = yes ] && unlock_all
            mins=$(( ($(date +%s) - since + 30) / 60 ))
            mkdir -p "$(dirname "$LOG")"
            [ -s "$LOG" ] || echo "date,away,back,minutes" > "$LOG"
            echo "$(date -d "@$since" +%F),$(date -d "@$since" +%H:%M),$(date +%H:%M),$mins" >> "$LOG"
            notify-send -a Bob ${touched:+-u critical} "Welcome back" "Away ${mins}m, $(date -d "@$since" +%H:%M) to $(date +%H:%M)${touched:+
Someone used the keyboard or mouse while you were away, at$touched}" > /dev/null 2>&1
            echo "$(date +%H:%M) back after ${mins}m${touched:+ (touched at$touched)}"
            touched="" stirred=0
        fi
    else
        miss=$((miss + 1))
        [ $miss -eq 1 ] && first=$(date +%s)                         # (away from the first missed answer)
        if [ $here -eq 1 ] && [ $miss -ge "$MISSES" ]; then          # gone
            here=0
            since=$first
            lock_all
            echo "$(date +%H:%M) away: locked"
        fi
    fi
    # away, and someone's at the keyboard? Give the phone a few seconds to turn up first: it may just be you
    if [ $here -eq 0 ] && [ "$ALARM" = yes ] && [ $(( $(date +%s) - since )) -gt 20 ]; then
        idle=$(idle_ms)
        if [ -n "$idle" ] && [ "$idle" -lt 3000 ]; then
            [ $stirred -eq 0 ] && stirred=$(date +%s)
        fi
        if [ $stirred -gt 0 ] && [ $(( $(date +%s) - stirred )) -ge 8 ]; then
            if [ $(( $(date +%s) - rang )) -ge 30 ]; then              # (not every two seconds)
                touched="$touched $(date -d "@$stirred" +%H:%M)"
                echo "$(date +%H:%M) someone's at the keyboard: alarm"
                alarm &
                rang=$(date +%s)
            fi
            stirred=0
        fi
    fi
    sleep 2
done
