"""Anchors: in the designer (dragging the form grip) and at runtime (resizing the preview window)."""
import os, sys
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

def geom(n, scope=None):
    node = eng.find(n, scope)
    g = node.host.geometry()
    return (g.x(), g.y(), node.widget.width(), node.widget.height())

def add(ctype, x, y, anchor, **props):
    eng.store.set_setting("click_x", x); eng.store.set_setting("click_y", y)
    name = eng.cmd_AddDesignControl(ctype, x, y)
    for k, v in props.items():
        eng.cmd_SetProperty(name, k, v)
    grid = eng.find("Props").widget
    combo = grid.editors["Anchor"]                       # set it through the property grid, as a user would
    combo.setCurrentText(anchor)
    return name

def steps():
    view = eng.find("Surface").widget
    ok_btn = add("Button", 520, 432, "Bottom,Right")
    name_box = add("TextBox", 24, 24, "Top,Left,Right", Width="592")
    lst = add("ListBox", 24, 64, "Top,Bottom,Left,Right", Width="592", Height="352")
    fixed = add("Button", 24, 432, "Top,Left")
    settle()
    check("anchor stored on the control", eng.cmd_GetProperty(ok_btn, "Anchor"), "Bottom,Right")
    before = {n: geom(n) for n in (ok_btn, name_box, lst, fixed)}

    # drag the form's corner grip by (+80, +40): 640x480 -> 720x520
    grip = view.overlay.form_grip().center()
    QTest.mousePress(view.overlay, Qt.LeftButton, Qt.NoModifier, grip)
    QTest.mouseMove(view.overlay, grip + QPoint(40, 20)); QTest.mouseMove(view.overlay, grip + QPoint(80, 40))
    QTest.mouseRelease(view.overlay, Qt.LeftButton, Qt.NoModifier, grip + QPoint(80, 40)); settle()
    check("form resized", (eng.cmd_GetProperty("Surface", "FormWidth"), eng.cmd_GetProperty("Surface", "FormHeight")), (720, 520))
    b, a = before[ok_btn], geom(ok_btn)
    check("Bottom,Right button moved with the corner", (a[0] - b[0], a[1] - b[1], a[2], a[3]), (80, 40, b[2], b[3]))
    check("Top,Left,Right text box stretched across", geom(name_box)[2], before[name_box][2] + 80)
    check("filling list stretched both ways", geom(lst)[2:], (before[lst][2] + 80, before[lst][3] + 40))
    check("Top,Left button stayed put", geom(fixed), before[fixed])
    check("new position committed to the property", eng.cmd_GetProperty(ok_btn, "Canvas.Left"), str(b[0] + 80))

    # runtime: preview, then resize the window by (+100, +60)
    eng.cmd_PreviewDesign("Surface"); settle()
    prev = [w for w in eng.windows if "vml-preview" in w.scope][-1]
    sc = prev.scope
    p0 = {n: geom(n, sc) for n in (ok_btn, name_box, lst, fixed)}
    prev.widget.resize(prev.widget.width() + 100, prev.widget.height() + 60); settle()
    b, a = p0[ok_btn], geom(ok_btn, sc)
    check("runtime: button follows the corner", (a[0] - b[0], a[1] - b[1]), (100, 60))
    check("runtime: text box stretches", geom(name_box, sc)[2] - p0[name_box][2], 100)
    check("runtime: list fills both ways", (geom(lst, sc)[2] - p0[lst][2], geom(lst, sc)[3] - p0[lst][3]), (100, 60))
    check("runtime: unanchored button unmoved", geom(fixed, sc)[:2], p0[fixed][:2])
    prev.widget.grab().save(os.path.join(HERE, "tests", "anchors-preview.png"))
    eng.find("Surface").widget.select(ok_btn, user=True); settle()
    eng.windows[0].widget.grab().save(os.path.join(HERE, "tests", "anchors-designer.png"))
    print(f"\n{sum(ok)}/{len(ok)} passed")
    app.quit()

QTimer.singleShot(500, steps)
eng.run()
