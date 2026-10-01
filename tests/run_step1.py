"""Drive the step-1 form like a user would, and check every result."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from vml.engine import Engine

eng = Engine().load(os.path.join(os.path.dirname(__file__), "step1.vml"))
app, ok = QApplication.instance(), []

def text(n):
    return eng.cmd_GetProperty(n, "Text")

def check(label, got, want):
    passed = got == want
    ok.append(passed)
    print(f"{'PASS' if passed else 'FAIL'}  {label}: {got!r}" + ("" if passed else f" (wanted {want!r})"))

def steps():
    n = eng.nodes
    check("OnOpened made dynamic chips", eng.cmd_GetChildControls("Dynamic"), '["chip1", "chip2", "chip3"]')
    n["btnClick"].widget.click(); n["btnClick"].widget.click()
    check("two clicks via settings + RunScript args", text("lblCount"), "Clicked 2 times")
    n["txtName"].widget.setText("Steve")
    check("TextChanged event", text("lblHello"), "Hello, Steve")
    n["chkShout"].widget.click()
    check("checkbox + shared script", text("lblHello"), "HELLO, STEVE!")
    n["cboColour"].widget.setCurrentIndex(2)
    check("dropdown changed title colour", eng.cmd_GetProperty("lblTitle", "Foreground"), "#991b1b")
    n["btnBash"].widget.click()
    s = text("lblShell")
    check("Shell + VML_DB_PATH + vml-parse on PATH", s.startswith("Linux / db: vml-") and s.endswith("parser: yes"), True)
    eng.cmd_SetProperty("lblHello", "Text", "set by script")
    check("script-set Text doesn't fire user events", text("lblHello"), "set by script")
    props = json.loads(eng.cmd_GetControlPropertiesJson("cboColour"))
    names = {p["name"]: p for p in props}
    check("reflection: dropdown property has options", names["FontWeight"]["type"], "dropdown")
    check("reflection: live SelectedItem", names["SelectedItem"]["value"], "Red")
    check("reflection: groups present", sorted({p["group"] for p in props}), ["Appearance", "Behaviour", "Common", "Layout", "Placement", "Text"])
    db = eng.store.db.execute("SELECT property_value FROM ui_properties p JOIN ui_tree t ON t.id=p.ui_tree_id "
                              "WHERE t.name='lblTitle' AND p.property_name='Foreground'").fetchone()[0]
    check("write-through to SQLite", db, "#991b1b")
    eng.windows[0].widget.grab().save("/tmp/vmlengine/tests/step1.png")
    print(f"\n{sum(ok)}/{len(ok)} passed")
    app.quit()

QTimer.singleShot(300, steps)
eng.run()
