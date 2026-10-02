"""Frames, nesting, anchors inside frames, key events, live geometry, window options."""
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

def steps():
    view = eng.find("Surface").widget
    ov, form = view.overlay, view.form
    page = lambda x, y: form.pos() + QPoint(x, y)
    status = lambda: eng.find("statusText").widget.text()

    frame = eng.cmd_AddDesignControl("Frame", 40, 40)
    check("frame added with its caption", (frame, eng.find(frame).props.get("Text")), ("Frame1", "Frame1"))
    inner = eng.cmd_AddDesignControl("Button", 64, 80)          # a right-click inside the frame
    check("control added inside the frame", eng.find(inner).parent.name, "Frame1")
    check("its position is inside the frame", (eng.cmd_GetControlX(inner), eng.cmd_GetControlY(inner)), (24, 40))
    settle()
    check("status bar shows position and size", status(), f"{inner}  (Button)    X 24   Y 40    W 100   H 30")

    # click the frame's caption area to select the frame, then drag it: the button goes with it
    QTest.mouseClick(ov, Qt.LeftButton, Qt.NoModifier, page(200, 46)); settle()
    check("clicking the frame selects it", view.selected, "Frame1")
    before = ov.rect_of(eng.find(inner)).topLeft()
    QTest.mousePress(ov, Qt.LeftButton, Qt.NoModifier, page(200, 46))
    QTest.mouseMove(ov, page(220, 56))
    check("status updates live while dragging", status().startswith("Frame1  (Frame)    X 64"), True)
    QTest.mouseMove(ov, page(240, 62))
    QTest.mouseRelease(ov, Qt.LeftButton, Qt.NoModifier, page(240, 62)); settle()
    after = ov.rect_of(eng.find(inner)).topLeft()
    check("frame moved by (40, 16)", (eng.cmd_GetControlX(frame), eng.cmd_GetControlY(frame)), (80, 56))
    check("its button moved with it", (after - before).x(), 40)
    check("button still inside, same local place", (eng.find(inner).parent.name, eng.cmd_GetControlX(inner)), ("Frame1", 24))

    # drag a button from the form into the frame, then back out
    loose = eng.cmd_AddDesignControl("Button", 400, 300)
    QTest.mousePress(ov, Qt.LeftButton, Qt.NoModifier, page(420, 310))
    QTest.mouseMove(ov, page(300, 200)); QTest.mouseMove(ov, page(180, 180))
    QTest.mouseRelease(ov, Qt.LeftButton, Qt.NoModifier, page(180, 180)); settle()
    check("dragged onto the frame: now inside it", eng.find(loose).parent.name, "Frame1")
    QTest.mousePress(ov, Qt.LeftButton, Qt.NoModifier, ov.rect_of(eng.find(loose)).center())
    QTest.mouseMove(ov, page(500, 400)); QTest.mouseMove(ov, page(520, 420))
    QTest.mouseRelease(ov, Qt.LeftButton, Qt.NoModifier, page(520, 420)); settle()
    check("dragged off the frame: back on the form", eng.find(loose).parent.name, "Surface")
    eng.cmd_DeleteControl(loose)

    # stretchy: frame anchored all round, its button anchored bottom-right inside it
    eng.cmd_SetProperty(frame, "Anchor", "Top,Bottom,Left,Right")
    eng.cmd_SetProperty(inner, "Anchor", "Bottom,Right")
    fb, ib = (eng.cmd_GetControlWidth(frame), eng.cmd_GetControlHeight(frame)), (eng.cmd_GetControlX(inner), eng.cmd_GetControlY(inner))
    grip = ov.form_grip().center()
    QTest.mousePress(ov, Qt.LeftButton, Qt.NoModifier, grip)
    QTest.mouseMove(ov, grip + QPoint(40, 20)); QTest.mouseMove(ov, grip + QPoint(80, 40))
    QTest.mouseRelease(ov, Qt.LeftButton, Qt.NoModifier, grip + QPoint(80, 40)); settle()
    check("frame stretched with the form", (eng.cmd_GetControlWidth(frame) - fb[0], eng.cmd_GetControlHeight(frame) - fb[1]), (80, 40))
    check("button rode the frame's corner", (eng.cmd_GetControlX(inner) - ib[0], eng.cmd_GetControlY(inner) - ib[1]), (80, 40))
    check("kept after release (committed)", eng.cmd_GetProperty(inner, "Canvas.Left"), str(ib[0] + 80))

    # a text box with a key script, and window options
    box = eng.cmd_AddDesignControl("TextBox", 24, 24)
    lbl = eng.cmd_AddDesignControl("TextBlock", 24, 260)
    eng.cmd_SetDesignScript(box, "OnKeyDown", "Lua",
        'Vml("SetProperty", "%s", "Text", Vml("GetSetting", "event_modifiers") .. "|" .. Vml("GetSetting", "event_key"))' % lbl)
    eng.cmd_SetProperty("Surface", "FormResizable", "false")
    eng.cmd_SetProperty("Surface", "FormMinWidth", "500")
    path = "/tmp/frames-test.vml"
    eng.cmd_ExportVml("Surface", path)
    text = open(path).read()
    check("saved: button's parent is the frame", f"@Button {inner}\nParent=Frame1" in text, True)
    check("saved: window options with the window", "Resizable=false\nMinWidth=500\n\n@Canvas" in text, True)
    eng.cmd_ClearDesign("Surface"); eng.cmd_ImportVml(path, "Surface"); settle()
    check("reopened: nesting intact", eng.find(inner).parent.name, "Frame1")
    check("reopened: form options", eng.cmd_GetProperty("Surface", "FormResizable"), "false")
    n = eng.find(inner)
    check("reopened: button inside the frame isn't clipped", n.host.size().toTuple(), n.widget.size().toTuple())
    ov.update(); settle()
    eng.windows[0].widget.grab().save(os.path.join(HERE, "tests", "frames-designer.png"))

    eng.cmd_PreviewDesign("Surface"); settle()
    prev = [w for w in eng.windows if "vml-preview" in w.scope][-1]
    sc = prev.scope
    check("preview: not resizable", prev.widget.minimumSize() == prev.widget.maximumSize(), True)
    tb = eng.find(box, sc).widget
    tb.setFocus(); QTest.keyClick(tb, Qt.Key_S, Qt.ControlModifier); settle()
    check("preview: OnKeyDown with key and modifiers", eng.find(lbl, sc).widget.text(), "Ctrl|S")
    QTest.keyClick(tb, Qt.Key_Return); settle()
    check("preview: named keys", eng.find(lbl, sc).widget.text(), "|Enter")
    prev.widget.grab().save(os.path.join(HERE, "tests", "frames-preview.png"))
    print(f"\n{sum(ok)}/{len(ok)} passed")
    app.quit()

QTimer.singleShot(500, steps)
eng.run()
