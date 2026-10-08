"""Step 2 on the real designer.vml: menus, composites via AddControlScript, reflection -> RefreshProperties, modal forms."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("VML_PREFS", os.path.join(__import__("tempfile").mkdtemp(prefix="vml-prefs-"), "prefs.json"))   # never the real settings
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from vml.engine import Engine

DESIGNER = os.path.expanduser("~/.vml/designer/vml/designer.vml")
eng = Engine()
for _d in ("cmd_InfoDialog", "cmd_ErrorDialog"):
    setattr(eng, _d, lambda msg, title="", _n=_d: print(f"[dialog {_n[4:]}] {msg}"))
eng.load(DESIGNER)
app, ok = QApplication.instance(), []

def check(label, got, want):
    passed = got == want
    ok.append(passed)
    print(f"{'PASS' if passed else 'FAIL'}  {label}: {got!r}" + ("" if passed else f" (wanted {want!r})"))

def steps():
    bar = eng.find("MainMenu").widget
    check("menu bar titles", [a.text() for a in bar.actions()], ["File", "Edit", "Tools", "Help", "▶ Preview"])
    file_menu = eng.find("File").menu
    check("File menu has items", len([a for a in file_menu.actions() if not a.isSeparator()]) >= 5, True)
    undo = eng.find("EditUndo").action
    check("shortcut wired", undo.shortcut().toString(), "Ctrl+Z")
    ctx = eng.find("CanvasContextMenu").menu
    check("context menu built", [a.text() for a in ctx.actions()][:1], ["Add New Control"])

    # a composite, through the designer's own AddControlScript, as the context menu would
    eng.store.set_setting("click_x", "120"); eng.store.set_setting("click_y", "80")
    eng.handle("AddControlScript(DummyButton)", eng.find("AddButton"))
    btn = eng.find("Button1")
    check("AddControlScript created Button1 on the canvas", btn is not None and btn.parent.name, "DesignCanvas")
    check("it's the DummyButton composite", eng.cmd_GetControlType("Button1"), "DummyButton")
    eng.cmd_SetProperty("Button1", "Content", "Hello")
    check("mapped property reaches the inner label", eng.find("Button1_Label").widget.text(), "Hello")
    props = json.loads(eng.cmd_GetControlPropertiesJson("Button1"))
    check("reflection lists the mapped property first", props[0]["name"], "Content")
    check("control is where it was dropped", (eng.cmd_GetControlX("Button1"), eng.cmd_GetControlY("Button1")), (120, 80))
    check("GetControlAt finds it", eng.cmd_GetControlAt(130, 90), "Button1")

    # the designer's own RefreshProperties, fed by reflection
    eng.cmd_SetCurrentControl("Button1")
    eng.run_script("RefreshProperties")
    rows = [k.name for k in eng.find("propertiesStack").children]
    check("RefreshProperties built property rows", len(rows) > 10, True)
    check("reflection reports the live mapped value", json.loads(eng.cmd_GetControlPropertiesJson("Button1"))[0]["value"], "Hello")
    check("Button1 sized as AddControlScript asked", (eng.find("Button1").host.width(), eng.find("Button1").host.height()), (100, 30))
    for _ in range(5):
        app.processEvents()
    eng.windows[0].widget.grab().save("/tmp/vmlengine/tests/designer2.png")

    # a modal form from a menu command (FormOpenModal about_dialog.vml); close it shortly after
    def close_dialog():
        dlg = [w for w in eng.windows if "about" in w.scope]
        check("modal about dialog opened", len(dlg), 1)
        if dlg:
            dlg[0].widget.grab().save("/tmp/vmlengine/tests/about.png")
            dlg[0].widget.close()
    QTimer.singleShot(600, close_dialog)
    eng.handle("FormOpenModal about_dialog.vml", eng.find("Help"))
    check("dialog's scope cleaned up afterwards", any("about" in s for s in eng.scopes), False)
    check("designer controls untouched", eng.find("propertiesStack") is not None, True)
    print(f"\n{sum(ok)}/{len(ok)} passed")
    app.quit()

QTimer.singleShot(400, steps)
eng.run()
