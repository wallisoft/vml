"""The streaming command runner: output appears live, the exit script fires, Cancel works."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("VML_PREFS", os.path.join(__import__("tempfile").mkdtemp(prefix="vml-prefs-"), "prefs.json"))   # never the real settings
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from vml.engine import Engine

VML = '''
@Window W
Title=Process test
Width=400
Height=300

@StackPanel S
Parent=W
Margin=10

@ListBox log
Parent=S
Height=200

@TextBlock status
Parent=S
Text=idle

@Script Done
Interpreter=lua
<<L
Vml("SetProperty", "status", "Text", "finished, exit " .. Vml("GetSetting", "exit_code"))
L
'''
open("/tmp/proc.vml", "w").write(VML)
eng = Engine().load("/tmp/proc.vml")
app, ok = QApplication.instance(), []

def check(label, got, want):
    passed = got == want
    ok.append(passed)
    print(f"{'PASS' if passed else 'FAIL'}  {label}: {got!r}" + ("" if passed else f" (wanted {want!r})"))

def settle(ms=1500):
    import time
    end = time.time() + ms / 1000
    while time.time() < end:
        app.processEvents()
        time.sleep(0.01)

def steps():
    # a job that prints 5 lines, one every 0.1s, then exits 0
    pid = eng.cmd_RunProcess('for i in 1 2 3 4 5; do echo "line $i"; sleep 0.1; done', "log", "Done")
    check("got a job id", pid.startswith("proc"), True)
    check("running at first", eng.cmd_ProcessRunning(pid), True)
    settle(1200)
    lst = eng.find("log").widget
    check("all five lines streamed into the list", [lst.item(i).text() for i in range(lst.count())],
          ["line 1", "line 2", "line 3", "line 4", "line 5"])
    check("not running after it finished", eng.cmd_ProcessRunning(pid), False)
    check("exit code captured", eng.cmd_ProcessExitCode(pid), "0")
    check("the on-exit script ran", eng.find("status").widget.text(), "finished, exit 0")

    # a failing job
    pid2 = eng.cmd_RunProcess('echo oops; exit 3', "log", "Done")
    settle(600)
    check("failure exit code", eng.cmd_ProcessExitCode(pid2), "3")

    # cancel a long one
    pid3 = eng.cmd_RunProcess('sleep 30', "log", "Done")
    check("long job running", eng.cmd_ProcessRunning(pid3), True)
    check("cancel returns true", eng.cmd_CancelProcess(pid3), True)
    settle(500)
    check("cancelled job stops", eng.cmd_ProcessRunning(pid3), False)

    print(f"\n{sum(ok)}/{len(ok)} passed")
    app.quit()

QTimer.singleShot(300, steps)
eng.run()
