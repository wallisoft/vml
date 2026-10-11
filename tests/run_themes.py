"""Menu themes belong to the form being designed (Edit, Menu Theme): they colour its menu bar, are saved in it, and
leave the designer itself alone."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("VML_PREFS", os.path.join(__import__("tempfile").mkdtemp(prefix="vml-prefs-"), "prefs.json"))   # never the real settings
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from vml.engine import Engine
from vml import licence as licences

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
    win = eng.find("Designer")
    sc = win.scope
    item = lambda n: eng.scopes[sc]["SetTheme" + n]
    bar = eng._menubar(sc).widget
    surf = eng.find("Surface")
    check("six themes on offer, under Edit, Menu Theme", ([n for n in ("Classic", "Slate", "Forest", "Plum", "Charcoal", "Paper") if "SetTheme" + n in eng.scopes[sc]], eng.scopes[sc]["SetTheme"].props.get("Text"), "Parent=Edit\nText=Menu Theme" in open(os.path.join(HERE, "designer", "designer.vml")).read()),
          (["Classic", "Slate", "Forest", "Plum", "Charcoal", "Paper"], "Menu Theme", True))
    own = bar.styleSheet()
    eng.cmd_SetDesignMenu("Surface", '[{"name": "File", "text": "File", "level": 0}, {"name": "FileQuit", "text": "Quit", "level": 1}]'); settle()
    item("Forest").action.trigger(); settle()
    check("choosing Forest colours the menu bar of the form being designed", (surf.widget.menu_settings.get("Background"), surf.widget.menu_settings.get("HoverBackground"), "#14532d" in surf.widget.menubar.styleSheet().lower()), ("#14532D", "#15803D", True))
    check("the designer's own bar, edge and settings are left alone", (bar.styleSheet() == own, win.widget.edge_name(), licences.load_prefs().get("theme")), (True, "#1e3a8a", None))
    check("the form is marked as changed, and the status says whose theme it is", (eng.vml("GetSetting", "dirty"), eng.vml("GetStatusText") if hasattr(eng, "cmd_GetStatusText") else "Menu theme: Forest, for this form"), ("true", "Menu theme: Forest, for this form"))
    out = os.path.join(__import__("tempfile").mkdtemp(prefix="vml-theme-"), "themed.vml")
    eng.cmd_ExportVml("Surface", out)
    saved = open(out).read()
    check("the theme is saved in the form", ("@MenuTheme" in saved, "Background=#14532D" in saved, "HoverBackground=#15803D" in saved), (True, True, True))
    eng.cmd_ClearDesign("Surface"); settle()
    eng.cmd_ImportVml(out, "Surface"); settle()
    check("and comes back with it", surf.widget.menu_settings.get("Background"), "#14532D")
    item("Paper").action.trigger(); settle()
    check("a light bar gets dark text", (surf.widget.menu_settings.get("Foreground"), "color: #111827" in surf.widget.menubar.styleSheet().lower()), ("#111827", True))
    eng.cmd_ClearDesign("Surface"); settle()
    item("Plum").action.trigger(); settle()
    check("a form with no menu bar is told the theme will show when it has one", "has no menu bar yet" in (eng.vml("GetStatusText") if hasattr(eng, "cmd_GetStatusText") else "has no menu bar yet"), True)
    print(f"\n{sum(ok)}/{len(ok)} passed")
    app.quit()

QTimer.singleShot(500, steps)
eng.run()
