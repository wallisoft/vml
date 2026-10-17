"""The new designer, driven like a user: right-click add, select, drag, resize, edit in the grid, save, reopen, preview."""
import json, os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("VML_PREFS", os.path.join(__import__("tempfile").mkdtemp(prefix="vml-prefs-"), "prefs.json"))   # never the real settings
from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QCheckBox, QLineEdit
from vml.engine import Engine

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
eng = Engine()
for _d in ("cmd_InfoDialog", "cmd_ErrorDialog"):
    setattr(eng, _d, lambda msg, title="", _n=_d: print(f"[dialog] {msg}"))
eng.load(os.path.join(HERE, "designer", "designer.vml"))
app, ok = QApplication.instance(), []

def check(label, got, want):
    passed = got == want
    ok.append(passed)
    print(f"{'PASS' if passed else 'FAIL'}  {label}: {got!r}" + ("" if passed else f" (wanted {want!r})"))

def settle():
    for _ in range(6):
        app.processEvents()

def steps():
    surf = eng.find("Surface")
    view, ov = surf.widget, surf.widget.overlay
    origin = view.form.pos()
    groups = [a.text() for a in eng.find("CtxAdd").menu.actions() if not a.isSeparator()]
    check("Add menu: the controls in groups, as a toolbox has them", groups[:3], ["Text", "Buttons and choices", "Pickers"])
    add_items = [a.text() for g in eng.find("CtxAdd").menu.actions() if g.menu() for a in g.menu().actions()]
    check("every control is in one of them, StackPanel and Border too", "StackPanel" in add_items and "Border" in add_items and "Button" in add_items, True)
    check("the Text group starts with TextBlock", [a.text() for a in eng.find("CtxAdd").menu.actions()[0].menu().actions()][:2], ["TextBlock", "TextBox"])
    check("grid starts on the form itself", eng.find("Props").widget.target, "Surface")

    # right-click at (40, 40) on the form, then Add > Button
    QTest.mouseClick(ov, Qt.RightButton, Qt.NoModifier, origin + QPoint(40, 40))
    eng.find("SurfaceMenu").menu.close()
    eng.find("Add_Button").action.trigger(); settle()
    check("button added where right-clicked", (eng.cmd_GetControlX("Button1"), eng.cmd_GetControlY("Button1")), (40, 40))
    check("new button selected", view.selected, "Button1")
    check("property grid follows selection", eng.find("Props").widget.target, "Button1")
    check("title shows unsaved", eng.find("Designer").widget.windowTitle(), "Visualised - Untitled *")

    # drag it by (+46, +22): 86,62 snaps to the 8px grid -> (88, 64)
    start = origin + QPoint(60, 50)
    QTest.mousePress(ov, Qt.LeftButton, Qt.NoModifier, start)
    QTest.mouseMove(ov, start + QPoint(30, 15)); QTest.mouseMove(ov, start + QPoint(46, 22))
    QTest.mouseRelease(ov, Qt.LeftButton, Qt.NoModifier, start + QPoint(46, 22)); settle()
    check("dragged and snapped to grid", (eng.cmd_GetControlX("Button1"), eng.cmd_GetControlY("Button1")), (88, 64))
    grid = eng.find("Props").widget
    check("grid shows the new position live", grid.editors["Canvas.Left"].text(), "88")

    # resize from the bottom-right handle by (+37, +11) -> 136 x 40
    br = view.overlay.handles(view.overlay.rect_of(eng.find("Button1")))["BottomRight"].center()
    QTest.mousePress(ov, Qt.LeftButton, Qt.NoModifier, br)
    QTest.mouseMove(ov, br + QPoint(37, 11))
    QTest.mouseRelease(ov, Qt.LeftButton, Qt.NoModifier, br + QPoint(37, 11)); settle()
    check("resized with the handle, snapped", (eng.cmd_GetControlWidth("Button1"), eng.cmd_GetControlHeight("Button1")), (136, 40))

    # edit Content in the property grid, as a user would
    ed = grid.editors["Content"]
    ed.setText("Go!"); ed.editingFinished.emit(); settle()
    check("grid edit reaches the control", eng.find("Button1").widget.text(), "Go!")
    ed = grid.editors["OnClick"]
    ed.setText("GoClicked"); ed.editingFinished.emit()
    check("event handler set from the grid", eng.find("Button1").props.get("OnClick"), "GoClicked")

    # add a TextBox and a CheckBox, arrow-nudge, rename through the grid
    eng.store.set_setting("click_x", 40); eng.store.set_setting("click_y", 120)
    eng.handle("AddControl(TextBox)", eng.find("Add_TextBox"))
    QTest.keyClick(ov, Qt.Key_Right); QTest.keyClick(ov, Qt.Key_Down, Qt.ShiftModifier); settle()
    check("arrow keys nudge (1px, Shift = 8px)", (eng.cmd_GetControlX("TextBox1"), eng.cmd_GetControlY("TextBox1")), (41, 128))
    eng.store.set_setting("click_x", 40); eng.store.set_setting("click_y", 180)
    eng.handle("AddControl(CheckBox)", eng.find("Add_CheckBox"))
    name_ed = eng.find("Props").widget.findChildren(QLineEdit)[0]
    name_ed.setText("chkRemember"); name_ed.editingFinished.emit(); settle()
    check("renamed through the grid", eng.find("chkRemember") is not None and view.selected, "chkRemember")

    # select nothing: grid edits the form
    QTest.mouseClick(ov, Qt.LeftButton, Qt.NoModifier, origin + QPoint(500, 400)); settle()
    check("clicking empty form edits the form", eng.find("Props").widget.target, "Surface")
    g = eng.find("Props").widget
    g.editors["FormName"].setText("LoginForm"); g.editors["FormName"].editingFinished.emit()
    g.editors["FormTitle"].setText("Please log in"); g.editors["FormTitle"].editingFinished.emit()
    eng.windows[0].widget.grab().save(os.path.join(HERE, "tests", "designer-new.png"))

    # save, clear, reopen
    path = os.path.join(tempfile.gettempdir(), "LoginForm.vml")
    eng.cmd_ExportVml("Surface", path)
    saved = open(path).read()
    check("saved VML has the button with its handler", "@Button Button1" in saved and "OnClick=GoClicked" in saved, True)
    eng.cmd_ClearDesign("Surface")
    check("cleared", len(surf.children), 0)
    eng.cmd_ImportVml(path, "Surface"); settle()
    check("reopened: three controls back", [k.name for k in surf.children], ["Button1", "TextBox1", "chkRemember"])
    check("reopened: position, size and text intact",
          (eng.cmd_GetControlX("Button1"), eng.cmd_GetControlWidth("Button1"), eng.find("Button1").widget.text()), (88, 136, "Go!"))
    check("reopened: form properties", eng.cmd_GetProperty("Surface", "FormTitle"), "Please log in")

    # script editor: double-click Button1 -> editor opens on OnClick; write Lua; save
    def drive_editor():
        ed = [w for w in eng.windows if "script-editor" in w.scope]
        check("double-click opened the script editor", len(ed), 1)
        if not ed:
            return
        sc = ed[0].scope
        find = lambda n: eng.scopes[sc][n]
        check("editor opened on OnClick", find("cboEvent").widget.currentText(), "OnClick")
        check("events listed for a Button", find("cboEvent").widget.count() >= 4, True)
        check("language choices", [find("cboLang").widget.itemText(i) for i in range(2)], ["Lua", "Shell (Bash)"])
        find("txtCode").widget.setPlainText('-- say hello\nif true then\n    Vml("SetProperty", "Button1", "Content", "Clicked!")\nend\n')
        ed[0].widget.grab().save(os.path.join(HERE, "tests", "script-editor.png"))
        find("btnSave").widget.click()
    QTimer.singleShot(700, drive_editor)
    btn_centre = view.overlay.rect_of(eng.find("Button1")).center()
    QTest.mouseDClick(ov, Qt.LeftButton, Qt.NoModifier, btn_centre); settle()
    check("handler name kept (the grid named it earlier)", eng.find("Button1").props.get("OnClick"), "GoClicked")
    check("property grid shows it", eng.find("Props").widget.target == "Button1" and eng.find("Props").widget.editors["OnClick"].text(), "GoClicked")
    eng.cmd_ExportVml("Surface", path)
    saved = open(path).read()
    check("script saved into the form", "@Script GoClicked" in saved and "    Vml(\"SetProperty\"" in saved, True)
    eng.cmd_ClearDesign("Surface"); eng.cmd_ImportVml(path, "Surface"); settle()
    check("script comes back on reopen, indentation intact",
          json.loads(eng.cmd_GetDesignScript("Button1", "OnClick"))["code"].split("\n")[2], '    Vml("SetProperty", "Button1", "Content", "Clicked!")')

    # preview: the saved form running for real
    eng.cmd_PreviewDesign("Surface"); settle()
    prev = [w for w in eng.windows if "vml-preview" in w.scope]
    check("preview window opened", len(prev) == 1 and prev[0].widget.windowTitle(), "Please log in")
    if prev:
        prev[0].widget.grab().save(os.path.join(HERE, "tests", "preview.png"))
        live = next(n for n in eng.scopes[prev[0].scope].values() if n.name == "Button1")
        check("preview controls are live, not inert", live.host.testAttribute(Qt.WA_TransparentForMouseEvents), False)
        live.widget.click(); settle()
        check("clicking in preview runs the script", live.widget.text(), "Clicked!")
    print(f"\n{sum(ok)}/{len(ok)} passed")
    app.quit()

QTimer.singleShot(500, steps)
eng.run()
