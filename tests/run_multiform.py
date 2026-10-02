"""Multi-form: modal child talking to its parent, dialog results, per-form Lua, named instances, open-form commands."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from vml.engine import Engine

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FORMS = os.path.join(HERE, "tests", "multiform")
eng = Engine().load(os.path.join(FORMS, "main.vml"))
app, ok = QApplication.instance(), []

def check(label, got, want):
    passed = got == want
    ok.append(passed)
    print(f"{'PASS' if passed else 'FAIL'}  {label}: {got!r}" + ("" if passed else f" (wanted {want!r})"))

def settle():
    for _ in range(8):
        app.processEvents()

def steps():
    main_scope = eng.find("Main").scope
    def in_child():
        child = [w for w in eng.windows if w.name == "Child"]
        check("child opened modally", len(child) == 1 and child[0].widget.isModal(), True)
        sc = child[0].scope
        check("child reads the parent by Form.Control", eng.scopes[sc]["lblGreeting"].widget.text(),
              "Hello Steve / main's secret seen here: nil")
        check("same control name, each form its own", eng.scopes[sc]["btnOK"].widget.text(), "OK")
        eng.scopes[sc]["btnOK"].widget.click()
    QTimer.singleShot(500, in_child)
    eng.find("btnAsk").widget.click(); settle()
    check("child wrote into the parent", eng.find("lblResult").widget.text(), "answer: 42")
    check("FormOpenModal returned the dialog result", eng.find("lblStatus").widget.text(), "dialog returned: ok")
    check("main's globals are still its own", eng.lua_state(main_scope).globals().secret, "main's own")
    check("child's Lua state dropped when it closed", any("child.vml" in k for k in eng.luas), False)

    # named instance: a script in main and one in child share the "lobby" state
    eng.load(os.path.join(FORMS, "child.vml"))           # non-modal this time
    eng.run_script("SharedWrite"); eng.run_script("SharedWrite")
    eng.run_script("SharedRead")
    check("named instance shared across forms", eng.store.get_setting("visitors_seen"), "2")
    check("FormOpen on an open form brings it forward, no duplicate",
          (eng.cmd_FormOpen(os.path.join(FORMS, "child.vml")), sum(1 for w in eng.windows if w.name == "Child")), ("Child", 1))
    check("HideForm", (eng.cmd_HideForm("Child"), eng._form_window("Child").widget.isVisible()), (True, False))
    check("ShowForm", (eng.cmd_ShowForm("Child"), eng._form_window("Child").widget.isVisible()), (True, True))
    check("CloseForm", (eng.cmd_CloseForm("Child"), eng._form_window("Child").widget.isVisible()), (True, False))

    # the designer: a saved form whose button opens a sibling form, previewed
    eng.load(os.path.join(HERE, "designer", "designer.vml")); settle()
    eng.store.set_setting("current_file", os.path.join(FORMS, "designed.vml"))
    b = eng.cmd_AddDesignControl("Button", 24, 24)
    eng.cmd_SetDesignScript(b, "OnClick", "Lua", 'Vml("FormOpen", "child.vml")')
    eng.cmd_PreviewDesign("Surface"); settle()
    prev = [w for w in eng.windows if "vml-preview" in w.scope][-1]
    eng.scopes[prev.scope][b].widget.click(); settle()
    check("preview opens a child form next to the saved file", eng._form_window("Child").widget.isVisible(), True)
    print(f"\n{sum(ok)}/{len(ok)} passed")
    app.quit()

QTimer.singleShot(400, steps)
eng.run()
