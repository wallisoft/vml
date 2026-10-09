"""The Splitter: a bar between docked panes, dragged to resize the pane before it. The designer has one between the
project tree and the properties."""
import json, os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("VML_PREFS", os.path.join(tempfile.mkdtemp(prefix="vml-prefs-"), "prefs.json"))
from PySide6.QtCore import QEvent, QPoint, QPointF, QTimer, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication
from vml.engine import Engine

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = tempfile.mkdtemp(prefix="vml-split-")
ok = []

def check(label, got, want=True):
    passed = got == want
    ok.append(passed)
    print(f"{'PASS' if passed else 'FAIL'}  {label}" + ("" if passed else f": got {got!r}, wanted {want!r}"))

eng = Engine()
app = QApplication.instance()
app.setQuitOnLastWindowClosed(False)

def settle(n=10):
    for _ in range(n):
        app.processEvents()

def drag(bar, dx, dy):
    g = bar.mapToGlobal(QPoint(2, 2))
    def send(kind, x, y):
        button = Qt.NoButton if kind == QEvent.MouseMove else Qt.LeftButton
        app.sendEvent(bar, QMouseEvent(kind, QPointF(2 + x, 2 + y), QPointF(g.x() + x, g.y() + y), button, Qt.LeftButton, Qt.NoModifier))
    send(QEvent.MouseButtonPress, 0, 0); send(QEvent.MouseMove, dx, dy); send(QEvent.MouseButtonRelease, dx, dy)
    settle()

FORM = """@Window Panes
Title=Panes
Width=600
Height=400

@DockPanel Root
Parent=Panes

@Border Top
Parent=Root
DockPanel.Dock=Top
Height=100
Background=#fee

@Splitter Bar
Parent=Root
DockPanel.Dock=Top
OnMoved=Moved

@Border Side
Parent=Root
DockPanel.Dock=Right
Width=150
Background=#eef

@Splitter SideBar
Parent=Root
DockPanel.Dock=Right
Thickness=8
MinSize=100

@Border Rest
Parent=Root
Background=#efe

@Script Moved
Interpreter=lua
<<LUA
Vml("SetSetting", "moved", Vml("GetProperty", "Top", "Height"))
LUA
"""

def steps():
    path = os.path.join(WORK, "panes.vml")
    with open(path, "w") as f:
        f.write(FORM)
    eng.load(path); settle()
    w = lambda name: eng.find(name).widget
    check("a splitter docked Top is a thin bar across, one docked Right a thin bar down", ((w("Bar").height(), w("Bar").width()), (w("SideBar").width(), w("SideBar").height() > 100)), ((5, 600), (8, True)))
    drag(w("Bar"), 0, 60)
    check("dragging it down makes the pane before it taller, and the rest gives way", (w("Top").height(), eng.find("Top").props["Height"], w("Rest").height()), (160, "160", 400 - 160 - 5))
    check("OnMoved runs when the drag ends", eng.store.get_setting("moved"), "160")
    drag(w("Bar"), 0, -1000)
    check("it stops at a smallest size (60 unless MinSize says otherwise)", w("Top").height(), 60)
    drag(w("Bar"), 0, 5000)
    check("and leaves that much for the other side", w("Top").height(), 340)
    drag(w("SideBar"), -70, 0)
    check("one docked Right resizes the width of the pane to its right", (w("Side").width(), w("Rest").width()), (220, 600 - 220 - 8))
    drag(w("SideBar"), 1000, 0)
    check("MinSize is kept to", w("Side").width(), 100)
    check("it isn't offered on the design surface, which is a canvas", "Splitter" in [t["name"] for t in json.loads(eng.cmd_GetControlTypes())], False)

    # in the designer
    proj = os.path.join(WORK, "T.vmlproj")
    with open(proj, "w") as f:
        f.write("# Visualised project\nName=T\nStartup=a.vml\nForm=a.vml\n")
    with open(os.path.join(WORK, "a.vml"), "w") as f:
        f.write("@Window a\nTitle=a\n")
    eng.load(os.path.join(HERE, "designer", "designer.vml")); settle()
    bar, pane = eng.find("ProjSplit").widget, eng.find("ProjectPane").widget
    check("designer: with no project open there is no bar", bar.isVisible(), False)
    eng.run_script("ProjectLoad", proj); settle()
    before = pane.height()
    drag(bar, 0, 90)
    check("designer: the bar under the project tree is dragged to give the tree more room", (bar.isVisible(), before, pane.height(), eng.find("ProjTree").widget.height() > 250), (True, 200, 290, True))
    print(f"\n{sum(ok)}/{len(ok)} passed")
    app.quit()

QTimer.singleShot(200, steps)
app.exec()
sys.exit(0 if all(ok) else 1)
