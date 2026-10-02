"""The Menu Editor, driven like a user; the menu on the design surface; saved, reopened, and run in preview."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from vml.engine import Engine

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
eng = Engine()
eng.load(os.path.join(HERE, "designer", "designer.vml"))
app, ok = QApplication.instance(), []

def check(label, got, want):
    passed = got == want
    ok.append(passed)
    print(f"{'PASS' if passed else 'FAIL'}  {label}: {got!r}" + ("" if passed else f" (wanted {want!r})"))

def settle():
    for _ in range(8):
        app.processEvents()

def steps():
    view = eng.find("Surface").widget

    def drive_editor():
        ed = [w for w in eng.windows if "menu-editor" in w.scope]
        check("Menu Editor opened", len(ed), 1)
        if not ed:
            return
        sc = ed[0].scope
        f = lambda n: eng.scopes[sc][n].widget
        def typ(text):
            f("txtCaption").setText(text); settle()
        typ("&File");                         check("name made from the caption", f("txtName").text(), "mnuFile")
        f("btnNext").click(); typ("&New"); f("btnIndent").click()
        f("txtShortcut").setText("Ctrl+N"); settle()
        f("btnNext").click(); typ("-")
        f("btnNext").click(); typ("E&xit")
        f("btnNext").click(); typ("&Help"); f("btnOutdent").click()
        f("btnNext").click(); typ("&About"); f("btnIndent").click()
        check("list shows the structure", [f("lstMenu").item(i).text() for i in range(f("lstMenu").count())],
              ["&File", "....&New   [Ctrl+N]", "....-----", "....E&xit", "&Help", "....&About"])
        ed[0].widget.grab().save(os.path.join(HERE, "tests", "menu-editor.png"))
        f("btnMeOK").click()

    QTimer.singleShot(700, drive_editor)
    eng.handle("OpenMenuEditor", eng.find("EditMenus"))
    settle()
    items = json.loads(eng.cmd_GetDesignMenu("Surface"))
    check("menu kept after OK", [(i["name"], i["level"]) for i in items],
          [("mnuFile", 0), ("mnuNew", 1), ("mnuSep3", 1), ("mnuExit", 1), ("mnuHelp", 0), ("mnuAbout", 1)])
    check("design surface shows the menu bar", [a.text() for a in view.menubar.actions()], ["&File", "&Help"])
    check("form moved down to make room", view.form.y() > view.menubar.y(), True)

    # a script for File > Exit's sibling New, via the script editor's menu target
    eng.cmd_SetDesignScript("menu:mnuNew", "OnClick", "Lua", 'Vml("SetSetting", "menu_test", "new clicked")')
    btn = eng.cmd_AddDesignControl("Button", 24, 24)
    path = "/tmp/menus-test.vml"
    eng.cmd_ExportVml("Surface", path)
    text = open(path).read()
    check("saved: menu bar above a filling canvas", "@TinyMenu Form1Menu\nParent=Form1Root\nDockPanel.Dock=Top" in text, True)
    check("saved: submenu item under its parent", "@MenuItem mnuNew\nParent=mnuFile\nText=&New\nShortcut=Ctrl+N\nOnClick=mnuNew_Click" in text, True)
    check("saved: its script", "@Script mnuNew_Click" in text, True)
    eng.cmd_ClearDesign("Surface")
    check("cleared, menu too", view.menubar.isVisible(), False)
    eng.cmd_ImportVml(path, "Surface"); settle()
    check("reopened: menu back", [(i["name"], i["level"]) for i in json.loads(eng.cmd_GetDesignMenu("Surface"))][:2],
          [("mnuFile", 0), ("mnuNew", 1)])
    check("reopened: form height unchanged", eng.cmd_GetProperty("Surface", "FormHeight"), 480)
    check("reopened: menu script back", json.loads(eng.cmd_GetDesignScript("menu:mnuNew", "OnClick"))["code"].startswith("Vml("), True)
    eng.windows[0].widget.grab().save(os.path.join(HERE, "tests", "menus-designer.png"))

    # Cancel closes only the Menu Editor, never the designer
    def cancel_editor():
        ed = [w for w in eng.windows if "menu-editor" in w.scope]
        if ed:
            eng.scopes[ed[0].scope]["btnMeCancel"].widget.click()
    QTimer.singleShot(600, cancel_editor)
    eng.handle("OpenMenuEditor", eng.find("EditMenus")); settle()
    check("Cancel closed the editor, not the designer", eng.find("Designer").widget.isVisible(), True)
    check("menu unchanged by Cancel", [a.text() for a in view.menubar.actions()], ["&File", "&Help"])

    # menus as controls: click a caption on the design surface, edit it in the grid
    ov = view.overlay
    file_act = view.menubar.actions()[0]
    centre = view.menubar.actionGeometry(file_act).center() + view.menubar.pos()
    QTest.mouseClick(ov, Qt.LeftButton, Qt.NoModifier, centre); settle()
    file_act.menu().close()
    check("clicking a caption selects the menu item", view.selected, "menu:mnuFile")
    grid = eng.find("Props").widget
    check("property grid edits it", grid.target, "menu:mnuFile")
    grid.editors["Text"].setText("&Project"); grid.editors["Text"].editingFinished.emit(); settle()
    check("caption changed on the design surface", view.menubar.actions()[0].text(), "&Project")
    new = eng.cmd_MenuAddItem("menu:mnuFile", "after")
    check("Add Item After: new top-level menu after File's submenu", [a.text() for a in view.menubar.actions()],
          ["&Project", "Item1", "&Help"])
    check("and it's selected", view.selected, new)
    child = eng.cmd_MenuAddItem(new, "child")
    check("Add Submenu Item: it now has a dropdown", view.menubar.actions()[1].menu().actions()[0].text(), "Item2")
    eng.handle("DeleteSelected", eng.find("MiDelete"))
    check("Delete removes the selected item", [a.text() for a in view.menubar.actions()[1].menu().actions()], [])
    eng.cmd_MenuDeleteItem(new)
    check("deleting a menu removes it and its submenu", [a.text() for a in view.menubar.actions()], ["&Project", "&Help"])

    eng.cmd_PreviewDesign("Surface"); settle()
    prev = [w for w in eng.windows if "vml-preview" in w.scope][-1]
    sc = prev.scope
    bar = next(n for n in eng.scopes[sc].values() if n.type.name == "TinyMenu").widget
    check("preview: real menu bar", [a.text() for a in bar.actions()], ["&Project", "&Help"])
    eng.scopes[sc]["mnuNew"].action.trigger(); settle()
    check("preview: menu item runs its script", eng.store.get_setting("menu_test"), "new clicked")
    check("preview: canvas below the menu, controls in place",
          eng.scopes[sc][btn].host.mapTo(prev.widget, QPoint(0, 0)).y() >= bar.height() + 24, True)
    prev.widget.grab().save(os.path.join(HERE, "tests", "menus-preview.png"))
    print(f"\n{sum(ok)}/{len(ok)} passed")
    app.quit()

QTimer.singleShot(500, steps)
eng.run()
