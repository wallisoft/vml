"""Opening a panel-laid-out form in the designer converts it to a canvas form that looks the same."""
import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("VML_PREFS", os.path.join(__import__("tempfile").mkdtemp(prefix="vml-prefs-"), "prefs.json"))   # never the real settings
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication
from vml.engine import Engine

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "apps", "no-stick", "no-stick.vml")
GROW = (int(sys.argv[2]), int(sys.argv[3])) if len(sys.argv) > 3 else (0, 0)
OUT = os.path.join(tempfile.gettempdir(), "import-layout-out.vml")
eng = Engine()
eng.load(os.path.join(HERE, "designer", "designer.vml"))
app, ok = QApplication.instance(), []

def check(label, passed, detail=""):
    ok.append(bool(passed))
    print(f"{'PASS' if passed else 'FAIL'}  {label}" + (f": {detail}" if detail else ""))

def settle():
    for _ in range(10):
        app.processEvents()

def render(path, png, grow=(0, 0)):
    """Build a form off screen without running its OnOpened script; return {name: rect} and save a picture."""
    import shutil
    copy = os.path.join(os.path.dirname(os.path.abspath(path)), ".render-" + os.path.basename(path))
    shutil.copyfile(path, copy)                          # a copy, so a form that is already running isn't disturbed
    path = copy
    try:
        eng.load(path, show=False)
    finally:
        os.remove(copy)
    scope = os.path.realpath(path)
    win = next(n for n in eng.scopes[scope].values() if n.type.name == "Window")
    w = win.widget
    w.setAttribute(Qt.WA_DontShowOnScreen, True)
    w.resize(w.size().expandedTo(w.minimumSizeHint())); w.show(); settle()
    w.resize(w.size().expandedTo(w.minimumSizeHint())); settle()
    if grow != (0, 0):
        w.setMinimumSize(0, 0); w.setMaximumSize(16777215, 16777215)
        w.resize(w.width() + grow[0], w.height() + grow[1]); settle()
    from PySide6.QtCore import QPoint
    rects = {}
    for n in eng.scopes[scope].values():
        if n is not win and n.host.isVisibleTo(w):
            p = n.widget.mapTo(w, QPoint(0, 0))
            rects[n.name] = (p.x(), p.y(), n.widget.width(), n.widget.height())
    w.grab().save(png)
    size = (w.width(), w.height())
    w.hide()
    for n in [n for n in list(eng.scopes[scope].values()) if n.parent is None]:
        eng.delete(n.name, scope)
    eng.scopes.pop(scope, None)
    return rects, size

def steps():
    before, size0 = render(SRC, os.path.join(HERE, "tests", "import-layout-before.png"))
    check("opened and converted", eng.cmd_ImportVml(SRC, "Surface") is True)
    check("flagged as a conversion", eng.store.get_setting("import_converted") == "true")
    print("     " + eng.store.get_setting("import_notes"))
    settle()
    eng.windows[0].widget.grab().save(os.path.join(HERE, "tests", "import-layout-designer.png"))
    check("saved as a canvas form", eng.cmd_ExportVml("Surface", OUT) is True)
    text = open(OUT).read()
    check("no layout panels left", not any(l.startswith(("@StackPanel ", "@Grid ", "@Border ", "@ScrollViewer "))
                                           for l in text.split("\n")))
    after, size1 = render(OUT, os.path.join(HERE, "tests", "import-layout-after.png"))
    check("same window size", size0 == size1, f"{size0} -> {size1}")
    both = [n for n in before if n in after]
    off = {n: (before[n], after[n]) for n in both if max(abs(x - y) for x, y in zip(before[n], after[n])) > 2}
    check(f"{len(both)} controls in the same place (within 2px)", not off, "; ".join(f"{n} {a}->{b}" for n, (a, b) in list(off.items())[:8]))
    if GROW != (0, 0):                                   # resized, the canvas form should follow the layout form
        b2, _ = render(SRC, os.path.join(HERE, "tests", "import-layout-before-big.png"), GROW)
        a2, _ = render(OUT, os.path.join(HERE, "tests", "import-layout-after-big.png"), GROW)
        off = {n: (b2[n], a2[n]) for n in b2 if n in a2 and max(abs(x - y) for x, y in zip(b2[n], a2[n])) > 2}
        check(f"resized by {GROW}, {len([n for n in b2 if n in a2])} controls still match", not off,
              "; ".join(f"{n} {a}->{b}" for n, (a, b) in list(off.items())[:8]))
    check("it opens again as an ordinary canvas form", eng.cmd_ImportVml(OUT, "Surface") is True
          and eng.store.get_setting("import_converted") == "false")
    print(f"\n{sum(ok)}/{len(ok)} passed")
    app.quit()

QTimer.singleShot(500, steps)
eng.run()
