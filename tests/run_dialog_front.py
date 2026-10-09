"""A question must never be left hidden behind the window it is about: that window answers to nothing while the
question waits, not even its close button."""
import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("VML_PREFS", os.path.join(tempfile.mkdtemp(prefix="vml-prefs-"), "prefs.json"))
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from vml.engine import Engine
from vml import dialogs, engine as engine_module

WORK = tempfile.mkdtemp(prefix="vml-front-")
ok = []

def check(label, got, want=True):
    passed = got == want
    ok.append(passed)
    print(f"{'PASS' if passed else 'FAIL'}  {label}" + ("" if passed else f": got {got!r}, wanted {want!r}"))

def form(name):
    path = os.path.join(WORK, name + ".vml")
    open(path, "w").write(f"@Window {name}\nTitle={name}\nWidth=300\nHeight=200\n\n@Canvas c\nParent={name}\n")
    return path

eng = Engine()
app = QApplication.instance()
app.setQuitOnLastWindowClosed(False)

def steps():
    eng.load(form("Main")); eng.load(form("Tool"))
    for _ in range(10): app.processEvents()
    main = next(w.widget for w in eng.windows if w.name == "Main")
    tool = next(w.widget for w in eng.windows if w.name == "Tool")
    using = [main]
    class Shim:                                                 # stands in for "which window is in use"
        def __getattr__(self, n): return getattr(QApplication, n)
        def activeWindow(self): return using[0]
    engine_module.QApplication = Shim()
    check("a question belongs to the window in use", eng._parent_window() is main)
    using[0] = None                                             # the moment after a dialog shuts: no window is 'in use'
    check("and the next one, asked straight after, to that same window, not whichever opened last", eng._parent_window() is main)
    box = dialogs.Box(main, "t", "words", ("OK",))
    using[0] = box
    check("a question asked from another question belongs to the window behind it", eng._parent_window() is main)
    using[0] = tool
    check("unless the user has moved to another window since", eng._parent_window() is tool)
    engine_module.QApplication = QApplication
    came = []
    box.front = lambda: came.append(1)
    QTimer.singleShot(50, lambda: QApplication.sendEvent(tool, __import__("PySide6.QtCore").QtCore.QEvent(__import__("PySide6.QtCore").QtCore.QEvent.WindowActivate)))
    QTimer.singleShot(200, box.reject)
    box.run()
    check("while a question waits, going to another window of the app brings the question to the front", len(came) >= 2)
    adrift = dialogs.Box(None, "t", "words", ("OK",))
    check("a question is never made without a window to stay in front of, when there is one", adrift.parentWidget() is not None or QApplication.activeWindow() is None)
    adrift.deleteLater()
    print(f"\n{sum(ok)}/{len(ok)} passed")
    for w in list(eng.windows): w.widget.close()
    app.quit()

QTimer.singleShot(200, steps)
app.exec()
sys.exit(0 if all(ok) else 1)
