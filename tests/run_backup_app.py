"""The Backup app: it says what bkup says, plainly, and its buttons run what they claim. bkup itself is stood
in for by a small script, so the test needs no server."""
import os, stat, sys, tempfile, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("VML_PREFS", os.path.join(tempfile.mkdtemp(prefix="vml-prefs-"), "prefs.json"))
WORK = tempfile.mkdtemp(prefix="vml-backup-")
fake = os.path.join(WORK, "bkup")
open(fake, "w").write(f'''#!/bin/bash
state=$(cat {WORK}/state 2>/dev/null || echo good)
echo "$1" >> {WORK}/asked
when=$(date -d "${{AGO:-1 hour ago}}" "+%F %T")
case "$1" in
status)
  [ "$state" = down ] && {{ echo "ssh: connect to host len1 port 22: No route to host"; exit 255; }}
  if [ "$state" = bad ]; then ok=false; n=1; r=problem; d="/mnt/len1-d2 is not mounted"; else ok=true; n=0; r=ok; d="up to date, 256M"; fi
  [ "$state" = old ] && when=$(date -d "40 hours ago" "+%F %T")
  cat <<J
{{ "name": "hetz1", "started": "$when", "finished": "$when", "ok": $ok, "problems": $n, "snapshot": "f9da54e9", "store": "/x", "store_size": "255M",
  "steps": [ {{ "step": "pull", "result": "ok", "detail": "1.9G pulled from bkup-source:" }},
             {{ "step": "databases", "result": "ok", "detail": "prepared 1 hour(s) ago, no problems" }},
             {{ "step": "copy on /mnt/len1-d2", "result": "$r", "detail": "$d" }} ] }}
J
  ;;
snapshots) echo "49fdb96b  2026-10-10 16:19:19  hetz1  bkup"; echo "f9da54e9  2026-10-11 03:30:42  hetz1  bkup" ;;
check) echo "check snapshots, trees and blobs"; sleep 0.5; echo "no errors were found"; [ "$state" = bad ] && exit 1; exit 0 ;;
"") echo "---- bkup of hetz1"; sleep 0.4; echo "pull ok"; echo "backup ok" ;;
esac
''')
os.chmod(fake, os.stat(fake).st_mode | stat.S_IEXEC)
os.environ["BKUP_CMD"] = fake
os.environ["BKUP_STICK_LOG"] = os.path.join(WORK, "stick.log")
open(os.environ["BKUP_STICK_LOG"], "w").write("2026-10-11 06:49:15 VMLBACKUP2 up to date: 256M, 2 nights, 2 keys\n")

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from vml.engine import Engine
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
eng = Engine().load(os.path.join(HERE, "apps", "Backup.vml"))
app, ok = QApplication.instance(), []

def check(label, got, want=True):
    passed = got == want
    ok.append(passed)
    print(f"{'PASS' if passed else 'FAIL'}  {label}" + ("" if passed else f": got {got!r}, wanted {want!r}"))

def settle(ms=300):
    end = time.time() + ms / 1000
    while time.time() < end:
        app.processEvents(); time.sleep(0.01)

P = lambda name, prop: eng.cmd_GetProperty(name, prop)
state = lambda s: open(os.path.join(WORK, "state"), "w").write(s)
asked = lambda: open(os.path.join(WORK, "asked")).read().splitlines()

def steps():
    settle()
    check("it asks as it opens, and a good night is green", (P("lblHead", "Text"), P("lblLight", "Foreground").lower()), ("The last backup worked", "#16a34a"))
    out = P("txtOut", "Text")
    check("each step is listed with what happened", ("✓  pull" in out, "1.9G pulled" in out, "prepared 1 hour(s) ago, no problems" in out), (True, True, True))
    check("when, how big, and which night", ("store 255M" in P("lblWhen", "Text"), "f9da54e9" in P("lblWhen", "Text")), (True, True))
    check("the stick's last word is shown", "VMLBACKUP2 up to date: 256M, 2 nights, 2 keys" in P("lblStick", "Text"))

    state("bad"); eng.find("btnRefresh").widget.click(); settle()
    check("a problem is red, and counted", (P("lblHead", "Text"), P("lblLight", "Foreground").lower()), ("1 problem in the last backup", "#dc2626"))
    check("the step that failed is marked, with why", "✗  copy on /mnt/len1-d2\n     /mnt/len1-d2 is not mounted" in P("txtOut", "Text"))

    state("old"); eng.find("btnRefresh").widget.click(); settle()
    check("a missed night is amber, though the last run was fine", (P("lblHead", "Text"), P("lblLight", "Foreground").lower()), ("No backup for 40 hours", "#d97706"))

    state("down"); eng.find("btnRefresh").widget.click(); settle()
    check("a machine that doesn't answer is grey, not green", (P("lblHead", "Text"), P("lblLight", "Foreground").lower()), ("Couldn't ask the backup machine", "#9ca3af"))
    check("and what came back is shown", "No route to host" in P("txtOut", "Text"))

    open(os.environ["BKUP_STICK_LOG"], "a").write("2026-10-11 07:20:01 VMLBACKUP2 FAILED: Permission denied (13)\n")
    state("good"); eng.find("btnRefresh").widget.click(); settle()
    check("a stick that failed is in red", ("FAILED" in P("lblStick", "Text"), P("lblStick", "Foreground").lower()), (True, "#dc2626"))

    eng.find("btnNights").widget.click(); settle(900)
    check("the nights kept are listed", ("49fdb96b" in P("txtOut", "Text"), "f9da54e9" in P("txtOut", "Text")), (True, True))
    eng.find("btnCheck").widget.click()
    settle(150); check("the buttons wait while a job runs", P("btnNow", "IsEnabled") in ("false", "False", False))
    settle(900)
    check("the check reports that the store is sound", (P("lblHead", "Text"), "no errors were found" in P("txtOut", "Text")), ("The store reads back sound", True))
    check("and the buttons are back", P("btnNow", "IsEnabled") in ("true", "True", True, "", None))

    asks = []
    eng.cmd_ConfirmDialog = lambda msg, title="": (asks.append(title), False)[1]
    n = len(asked()); eng.find("btnNow").widget.click(); settle(500)
    check("Back up now asks first, and No runs nothing", (asks, len(asked())), (["Back up now"], n))
    eng.cmd_ConfirmDialog = lambda msg, title="": True
    eng.find("btnNow").widget.click(); settle(150)
    check("Yes starts one, and says so", P("lblHead", "Text"), "Backing up now…")
    settle(1500)
    check("its output was shown as it ran, then the new result", (asked()[n:], P("lblHead", "Text")), (["", "status"], "The last backup worked"))
    print(f"\n{sum(ok)}/{len(ok)} passed")
    app.quit()

QTimer.singleShot(400, steps)
eng.run()
