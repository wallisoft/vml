"""The designer's Undo, Redo, Cut, Copy and Paste, and selecting several (a box drawn round them, Ctrl+click):
driven from its own menus and the mouse, as a user would."""
import os, sys, time, json, tempfile
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
os.environ.setdefault("VML_PREFS", os.path.join(tempfile.mkdtemp(prefix="vml-prefs-"), "prefs.json"))   # never the real settings
from PySide6.QtWidgets import QApplication
from vml.engine import Engine
eng = Engine(); eng.load(os.path.join(HERE, "designer", "designer.vml")); app = QApplication.instance()
def settle(t=0.4):
    t0 = time.time()
    while time.time() - t0 < t: app.processEvents()
settle()
ok = []
def check(label, got, want):
    ok.append(got == want); print(("PASS " if got == want else "FAIL ") + label, got, "" if got == want else f"(wanted {want})")
run = lambda h: eng.find(h).action.trigger() or settle(0.2)
names = lambda: sorted(k.name for k in eng._surface("Surface").children)
check("nothing to undo at first", eng.cmd_CanUndo(), "false")
eng.find("ToolsAdd_Button").action.trigger(); settle(0.2)
eng.find("ToolsAdd_TextBox").action.trigger(); settle(0.2)
check("two added", names(), ["Button1", "TextBox1"])
eng.cmd_SetProperty("Props", "Target", "Button1")
run("EditUndo"); check("undo takes the TextBox away", names(), ["Button1"])
run("EditUndo"); check("and the Button", names(), [])
check("nothing more to undo", eng.cmd_CanUndo(), "false")
run("EditRedo"); run("EditRedo"); check("redo brings both back", names(), ["Button1", "TextBox1"])
eng.cmd_SetProperty("Button1", "Content", "Go")
eng._surface("Surface").widget.emit("OnChanged", {"selected_control": "Button1"}); settle(0.2)
run("EditUndo"); check("a property change undoes", eng.find("Button1").props.get("Content"), "Button1")
run("EditRedo"); check("and redoes", eng.find("Button1").props.get("Content"), "Go")
eng.cmd_SetDesignScript("Button1", "OnClick", "lua", "print('hi')")
eng._surface("Surface").widget.select("Button1", user=True)
eng.cmd_SetProperty("Surface", "Selected", "Button1")
run("EditCopy"); run("EditPaste")
check("paste makes Button2", names(), ["Button1", "Button2", "TextBox1"])
b2 = eng.find("Button2")
check("with its properties, script, and a step down", (b2.props.get("Content"), int(float(b2.props["Canvas.Top"])) - int(float(eng.find("Button1").props["Canvas.Top"])), list(getattr(b2, "design_scripts", {}).keys())), ("Go", 16, ["OnClick"]))
check("the clipboard has it as text", eng.cmd_ClipboardGet().startswith("VML-CONTROLS:"), True)
eng.cmd_SetProperty("Surface", "Selected", "TextBox1"); eng._surface("Surface").widget.select("TextBox1", user=True)
run("EditCut"); check("cut takes it off", names(), ["Button1", "Button2"])
run("EditPaste"); check("and paste puts it back", names(), ["Button1", "Button2", "TextBox1"])
run("EditUndo"); run("EditUndo"); check("undo the paste and the cut", names(), ["Button1", "Button2", "TextBox1"])
# a frame with something inside
eng.cmd_AddDesignControl("Frame", 300, 200); settle(0.2)
eng.cmd_CreateControl("CheckBox", "Inner", "Frame1"); settle(0.1)
eng.cmd_CopyControl("Frame1"); n = eng.cmd_PasteControl(); settle(0.2)
check("a frame pastes with what's inside", [k.type.name for k in eng.find(n).children], ["CheckBox"])
eng.cmd_ClearDesign("Surface"); check("New starts the list again", (eng.cmd_CanUndo(), eng.cmd_CanRedo()), ("false", "false"))

# ---- a group: a box drawn round some, Ctrl+click, then copy, paste, move and delete them together
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
surf = eng._surface("Surface"); view = surf.widget; ov = view.overlay
for c in ("Button", "TextBox", "CheckBox"):
    eng.find("ToolsAdd_" + c).action.trigger(); settle(0.15)
eng.cmd_AddDesignControl("Label" if "Label" in __import__("vml.registry", fromlist=["x"]).REGISTRY else "TextBlock", 400, 300); settle(0.2)
far = [k.name for k in surf.children if k.name not in ("Button1", "TextBox1", "CheckBox1")][0]
f = view.form.geometry()
start, end = f.topLeft() + QPoint(4, 4), f.topLeft() + QPoint(300, 150)
QTest.mousePress(ov, Qt.LeftButton, Qt.NoModifier, start)
QTest.mouseMove(ov, start + QPoint(40, 40)); QTest.mouseMove(ov, end)
QTest.mouseRelease(ov, Qt.LeftButton, Qt.NoModifier, end); settle(0.2)
check("a box round three selects all three, not the one outside it", sorted(eng.cmd_GetProperty("Surface", "SelectedAll").split(",")), ["Button1", "CheckBox1", "TextBox1"])
farpt = ov.rect_of(eng.find(far)).center()
QTest.mouseClick(ov, Qt.LeftButton, Qt.ControlModifier, farpt); settle(0.1)
check("Ctrl+click adds one", len(eng.cmd_GetProperty("Surface", "SelectedAll").split(",")), 4)
QTest.mouseClick(ov, Qt.LeftButton, Qt.ControlModifier, farpt); settle(0.1)
check("and takes it out again", far in eng.cmd_GetProperty("Surface", "SelectedAll").split(","), False)
tops = {n: int(float(eng.find(n).props["Canvas.Top"])) for n in ("Button1", "TextBox1", "CheckBox1")}
grab = ov.rect_of(eng.find("TextBox1")).center()
QTest.mousePress(ov, Qt.LeftButton, Qt.NoModifier, grab)
QTest.mouseMove(ov, grab + QPoint(10, 20)); QTest.mouseMove(ov, grab + QPoint(40, 80))
QTest.mouseRelease(ov, Qt.LeftButton, Qt.NoModifier, grab + QPoint(40, 80)); settle(0.2)
moved = {n: int(float(eng.find(n).props["Canvas.Top"])) - tops[n] for n in tops}
check("dragging one moves the group together", len(set(moved.values())) == 1 and list(moved.values())[0] > 0, True)
run("EditUndo")
check("and one Undo puts the whole group back", {n: int(float(eng.find(n).props["Canvas.Top"])) for n in tops}, tops)
box = ov.group_box()
check("a group has its box round it all", box is not None and all(box.contains(ov.rect_of(eng.find(n))) for n in tops), True)
QTest.mouseClick(ov, Qt.RightButton, Qt.NoModifier, ov.rect_of(eng.find("Button1")).center()); settle(0.2)
for m in QApplication.topLevelWidgets():
    if m.isVisible() and m.inherits("QMenu"): m.close()
check("right-click on one keeps the group", sorted(eng.cmd_GetProperty("Surface", "SelectedAll").split(",")), ["Button1", "CheckBox1", "TextBox1"])
inbox = QPoint(box.right() - 3, box.bottom() - 3)
QTest.mousePress(ov, Qt.LeftButton, Qt.NoModifier, inbox)
QTest.mouseMove(ov, inbox + QPoint(8, 8)); QTest.mouseMove(ov, inbox + QPoint(16, 16))
QTest.mouseRelease(ov, Qt.LeftButton, Qt.NoModifier, inbox + QPoint(16, 16)); settle(0.2)
check("dragging inside the box moves the group", all(int(float(eng.find(n).props["Canvas.Top"])) == tops[n] + 16 for n in tops), True)
run("EditUndo")
eng.cmd_SetProperty("Surface", "SelectedAll", "Button1,TextBox1,CheckBox1")
run("EditCopy"); run("EditPaste")
check("the group pastes as a group, selected", sorted(eng.cmd_GetProperty("Surface", "SelectedAll").split(",")), ["Button2", "CheckBox2", "TextBox2"])
check("pasted, the box is back round them", ov.group_box() is not None, True)
QTest.mouseClick(ov, Qt.LeftButton, Qt.NoModifier, view.form.geometry().bottomRight() - QPoint(20, 20)); settle(0.6)
check("a click on the form clears it", (ov.group_box(), eng.cmd_GetProperty("Surface", "SelectedAll")), (None, ""))
eng.cmd_SetProperty("Surface", "SelectedAll", "Button2,TextBox2,CheckBox2")
run("EditDelete")
check("Delete takes the whole group", [n for n in ("Button2", "CheckBox2", "TextBox2") if eng.find(n) is not None], [])
run("EditUndo")
check("and Undo brings it all back", [n for n in ("Button2", "CheckBox2", "TextBox2") if eng.find(n) is not None], ["Button2", "CheckBox2", "TextBox2"])

# ---- the form's own events, and the Script Editor on the Tools menu
check("the form's events", [e["name"] for e in json.loads(eng.cmd_GetControlEvents("Surface"))],
      ["OnOpened", "OnClosing", "OnResized", "OnActivated", "OnKeyDown", "OnKeyUp"])
check("Tools has the Script Editor", "Script Editor..." in [a.text() for a in eng.find("Tools").action.menu().actions()], True)
eng.cmd_SetDesignScript("Surface", "OnResized", "lua", "Vml('SetSetting', 'resized', tostring(width) .. 'x' .. tostring(height))")
out = os.path.join(tempfile.mkdtemp(), "ev.vml")
eng.cmd_ExportVml("Surface", out)
text = open(out).read()
check("OnResized is saved with the form", "OnResized=" in text, True)
run_eng = Engine(); run_eng.load(out); settle(0.5)
w = run_eng.windows[-1].widget
w.resize(w.width() + 60, w.height() + 30); settle(0.5)
check("and fires when the running form is resized", (run_eng.store.get_setting("resized") or "").count("x"), 1)

print(f"{sum(ok)}/{len(ok)} passed")
sys.exit(0 if all(ok) else 1)
