"""The local API and `vml` command: bash calling back into its form, chains across languages, outside programs."""
import json, os, stat, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("VML_PREFS", os.path.join(__import__("tempfile").mkdtemp(prefix="vml-prefs-"), "prefs.json"))   # never the real settings
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from vml.engine import Engine

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
eng = Engine().load(os.path.join(HERE, "tests", "api", "main.vml"))
eng.load(os.path.join(HERE, "tests", "api", "other.vml"))          # opened second: has its own lblOut
app, ok = QApplication.instance(), []

def check(label, got, want):
    passed = got == want
    ok.append(passed)
    print(f"{'PASS' if passed else 'FAIL'}  {label}: {got!r}" + ("" if passed else f" (wanted {want!r})"))

def steps():
    main_scope = eng.find("ApiMain").scope
    lbl = lambda: eng.scopes[main_scope]["lblOut"].widget.text()
    eng.scopes[main_scope]["btnBash"].widget.click()
    check("bash read and wrote its own form", lbl(), "Hello, Steve, from bash")
    check("the other form's lblOut untouched", eng.find("ApiOther.lblOut").widget.text(), "untouched")
    check("vml setting from bash", eng.store.get_setting("from_bash"), "yes")
    check("an error gives a non-zero exit", eng.store.get_setting("error_seen"), "exit 1")
    eng.scopes[main_scope]["btnChain"].widget.click()
    check("bash -> Lua -> bash -> back", lbl(), "lua said 42 (bash echoed 21)")
    eng.scopes[main_scope]["btnSpeed"].widget.click()
    ms = int(eng.store.get_setting("speed_ms") or 999)
    print(f"      (each vml call from bash took about {ms} ms)")
    check("calls are quick (under 150 ms each)", ms < 150, True)

    out = eng.run_script("PyHello", "a", "b", origin=eng.find("btnPython"))
    check("Python reads and writes the form", lbl(), "Hello Steve from Python: mean 5.333333333333333")
    check("Python gets its arguments", eng.store.get_setting("py_args"), '["a", "b"]')
    check("Python -> Lua -> bash, printed back", out, "8 (bash echoed 4)")
    check("Python offered in the script editor", "Python" in json.loads(eng.cmd_GetLanguages()), True)

    disc = os.path.expanduser("~/.vml/api.json")
    check("discovery file readable only by you", oct(stat.S_IMODE(os.stat(disc).st_mode)), "0o600")
    env = {k: v for k, v in os.environ.items() if not k.startswith("VML_")}
    env["PYTHONPATH"] = HERE
    proc = subprocess.Popen([sys.executable, "-m", "vml.client", "set", "ApiMain.lblOut", "Text", "from outside"],
                            env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    while proc.poll() is None:                             # an idle engine, answering through its socket notifier
        app.processEvents(); time.sleep(0.005)
    check("an outside program drove the running form", lbl(), "from outside")
    out = subprocess.run([os.path.join(HERE, "vml.py"), "x", "y"], env=dict(env, VML_API="127.0.0.1:1", VML_TOKEN="x"),
                         capture_output=True, text=True)
    check("no engine there: clear error, exit 1", (out.returncode, out.stderr.startswith("vml:")), (1, True))
    print(f"\n{sum(ok)}/{len(ok)} passed")
    app.quit()

QTimer.singleShot(400, steps)
eng.run()
