"""The designer's themes: chosen from Settings, they recolour its bar, its edge and its boxes, and are remembered."""
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
    check("six themes on offer", [n for n in ("Classic", "Slate", "Forest", "Plum", "Charcoal", "Paper") if "SetTheme" + n in eng.scopes[sc]],
          ["Classic", "Slate", "Forest", "Plum", "Charcoal", "Paper"])
    check("starts on Classic", item("Classic").action.text().startswith("✓"), True)
    check("Classic edge", win.widget.edge_name(), "#1e3a8a")
    item("Forest").action.trigger(); settle()
    check("Forest is ticked", (item("Forest").action.text().startswith("✓"), item("Classic").action.text().startswith("✓")), (True, False))
    check("the bar is green", "#14532d" in bar.styleSheet().lower(), True)
    check("the window's edge follows", win.widget.edge_name(), "#14532d")
    check("boxes will follow", eng._edge() if eng._parent_window() is win.widget else win.widget.edge_name(), "#14532d")
    check("its menus follow", "#14532d" in eng.scopes[sc]["Settings"].menu.styleSheet().lower(), True)
    check("remembered", licences.load_prefs().get("theme"), "Forest")
    item("Paper").action.trigger(); settle()
    check("a light bar gets dark text", "color: #111827" in bar.styleSheet().lower(), True)
    licences.save_prefs({**licences.load_prefs(), "theme": "Nonsense"})
    eng.cmd_RunScript("ApplyTheme"); settle()
    check("an unknown theme falls back to Classic", win.widget.edge_name(), "#1e3a8a")
    print(f"\n{sum(ok)}/{len(ok)} passed")
    app.quit()

QTimer.singleShot(500, steps)
eng.run()
