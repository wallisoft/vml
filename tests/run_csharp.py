"""C# scripting (needs .NET and the built host): State, Vml calls, C# -> Lua -> C#, errors, and the designer."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("VML_PREFS", os.path.join(__import__("tempfile").mkdtemp(prefix="vml-prefs-"), "prefs.json"))   # never the real settings
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from vml import csharp
from vml.engine import Engine

if not csharp.available():
    print("C# isn't set up here (./vml.py setup-csharp): skipping\n0/0 passed")
    raise SystemExit(0)
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
eng = Engine().load(os.path.join(HERE, "tests", "csharp.vml"))
app, ok = QApplication.instance(), []

def check(label, got, want):
    passed = got == want
    ok.append(passed)
    print(f"{'PASS' if passed else 'FAIL'}  {label}: {got!r}" + ("" if passed else f" (wanted {want!r})"))

def settle():
    for _ in range(6):
        app.processEvents()

def steps():
    out = lambda: eng.find("lblOut").widget.text()
    eng.find("btnHello").widget.click(); settle()
    check("C# reads and writes the form", out(), "Hello Steve from C# (1)")
    eng.find("txtName").widget.setText("Ada"); eng.find("btnHello").widget.click(); settle()
    check("State persists between C# runs", out(), "Hello Ada from C# (2)")
    eng.find("btnRound").widget.click(); settle()
    check("C# -> Lua -> C# and back", out(), "lua saw x and C# said 'Y'")
    eng.find("btnBroken").widget.click(); settle()
    check("a compile error is reported, nothing breaks", (out(), eng.find("CsForm").widget.isVisible()), ("lua saw x and C# said 'Y'", True))

    eng.load(os.path.join(HERE, "designer", "designer.vml")); settle()
    check("the designer offers C#", json.loads(eng.cmd_GetLanguages())[-1], "C#")
    b = eng.cmd_AddDesignControl("Button", 24, 24)
    eng.cmd_SetDesignScript(b, "OnClick", "C#", 'Vml("SetProperty", "%s", "Content", $"{6 * 7}");' % b)
    check("design script stored as C#", json.loads(eng.cmd_GetDesignScript(b, "OnClick"))["language"], "C#")
    path = "/tmp/cs-design.vml"
    eng.cmd_ExportVml("Surface", path)
    check("saved with Interpreter=csharp", "Interpreter=csharp" in open(path).read(), True)
    eng.cmd_PreviewDesign("Surface"); settle()
    prev = [w for w in eng.windows if "vml-preview" in w.scope][-1]
    eng.scopes[prev.scope][b].widget.click(); settle()
    check("preview runs the C# script", eng.scopes[prev.scope][b].widget.text(), "42")
    print(f"\n{sum(ok)}/{len(ok)} passed")
    app.quit()

QTimer.singleShot(400, steps)
eng.run()
