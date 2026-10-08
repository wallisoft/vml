"""The form's own scripts: OnOpened and helpers survive open, save and preview; double-click the form to edit OnOpened."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("VML_PREFS", os.path.join(__import__("tempfile").mkdtemp(prefix="vml-prefs-"), "prefs.json"))   # never the real settings
from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
import vml.engine as E
from vml.engine import Engine

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
errors, _log = [], E.log
E.log = lambda m: (errors.append(m) if "script error" in m else None, _log(m))
eng = Engine().load(os.path.join(HERE, "designer", "designer.vml"))
app, ok = QApplication.instance(), []

def check(label, got, want):
    passed = got == want
    ok.append(passed)
    print(f"{'PASS' if passed else 'FAIL'}  {label}: {got!r}" + ("" if passed else f" (wanted {want!r})"))

def settle():
    for _ in range(8):
        app.processEvents()

def steps():
    eng.cmd_ImportVml(os.path.join(HERE, "tests", "web", "demo.vml"), "Surface"); settle()
    surf = eng.find("Surface")
    check("the form's OnOpened is kept", surf.props.get("OnOpened"), "DemoOpened")
    eng.cmd_SetProperty("Surface", "FormResizable", "false")
    eng.cmd_SetProperty("Surface", "FormModal", "true")
    eng.cmd_ExportVml("Surface", "/tmp/formscripts.vml")
    text = open("/tmp/formscripts.vml").read()
    window_lines = text.split("@Window ", 1)[1].split("\n\n", 1)[0]
    check("form-level lines sit with the window, even with a menu",
          all(x in window_lines for x in ("OnOpened=DemoOpened", "Resizable=false", "Modal=true")), True)
    check("and the menu bar didn't get them", "OnOpened" not in text.split("@TinyMenu", 1)[1].split("\n\n", 1)[0], True)
    check("OnOpened's script saved", "@Script DemoOpened" in text, True)
    eng.cmd_SetProperty("Surface", "FormModal", "false")
    eng.cmd_PreviewDesign("Surface"); settle()
    prev = [w for w in eng.windows if "vml-preview" in w.scope][-1]
    eng.scopes[prev.scope]["btnGo"].widget.click(); settle()
    check("preview runs OnOpened first, so scripts work", (errors, eng.scopes[prev.scope]["lstLog"].widget.count()), ([], 2))
    prev.widget.close()

    # a helper script nothing triggers directly (only called by other scripts) is kept too
    with open("/tmp/helper.vml", "w") as f:
        f.write("@Window H\nWidth=300\nHeight=200\n\n@Canvas HC\nParent=H\n\n@Button b1\nParent=HC\nOnClick=Click\n\n"
                "@Script Click\nInterpreter=lua\n<<L\nVml(\"RunScript\", \"Helper\")\nL\n\n"
                "@Script Helper\nInterpreter=lua\n<<L\nVml(\"SetSetting\", \"helped\", \"yes\")\nL\n")
    eng.cmd_ImportVml("/tmp/helper.vml", "Surface")
    check("a helper script is kept", sorted(surf.form_scripts), ["Helper"])
    eng.cmd_ExportVml("Surface", "/tmp/helper2.vml")
    check("and saved again", "@Script Helper" in open("/tmp/helper2.vml").read(), True)

    def in_editor():
        ed = [w for w in eng.windows if "script-editor" in w.scope]
        check("double-click the empty form: editor on the form's OnOpened",
              ed and (eng.scopes[ed[0].scope]["lblControl"].widget.text(), eng.scopes[ed[0].scope]["cboEvent"].widget.currentText()),
              ("Form  (the window itself)", "OnOpened"))
        if ed:
            ed[0].widget.close()
    QTimer.singleShot(600, in_editor)
    view = surf.widget
    QTest.mouseDClick(view.overlay, Qt.LeftButton, Qt.NoModifier, view.form.pos() + QPoint(250, 150)); settle()
    print(f"\n{sum(ok)}/{len(ok)} passed")
    app.quit()

QTimer.singleShot(400, steps)
eng.run()
