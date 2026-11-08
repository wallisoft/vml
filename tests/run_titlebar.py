"""A window's own title bar (TitleBar=Own): drawn in the edge's colour, the form keeps its designed size under it,
min/max/close, grips to resize by, none of it when maximised or not resizable; and the designer keeps it."""
import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("VML_PREFS", os.path.join(tempfile.mkdtemp(prefix="vml-prefs-"), "prefs.json"))
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from vml.engine import Engine
from vml.registry import TITLE_BAR_H, host_radius

ok = []
def check(label, got, want):
    passed = got == want
    ok.append(passed)
    print(f"{'PASS' if passed else 'FAIL'}  {label}: {got!r}" + ("" if passed else f" (wanted {want!r})"))

FORM = """@Window TbTest
Title=Title bar test
Width=420
Height=300
BorderBrush=#127A68
BorderThickness=2
TitleBar=Own

@Canvas c
Parent=TbTest
Background=#FFFFFF

@Button b
Parent=c
Canvas.Left=10
Canvas.Top=10
Width=100
Height=30
Content=Hello
"""
d = tempfile.mkdtemp(prefix="vml-tb-")
form = os.path.join(d, "tb.vml")
open(form, "w").write(FORM)
app = QApplication.instance() or QApplication([])
eng = Engine()
eng.load(form)
for _ in range(10): app.processEvents()
w = eng.windows[0].widget
check("no frame from the desktop", bool(w.windowFlags() & Qt.FramelessWindowHint), True)
check("the bar is shown, along the top", (w.bar.isVisible(), w.bar.y(), w.bar.height(), w.bar.width()), (True, 0, TITLE_BAR_H, w.width()))
from vml.registry import host_title_bar
check("in the desktop's own title bar colour", w.bar.colour.name(), host_title_bar()[0].lower())
check("with whichever words read on it", w.bar.ink.name(), "#111827" if w.bar.colour.lightness() > 140 else "#ffffff")
check("the edge in BorderBrush, round it all", (w.edge.colour.name(), w.edge.isVisible()), ("#127a68", True))
check("its title is the window's", w.bar.title.text(), "Title bar test")
from vml.registry import host_title_bar
check("centred or to the left, as the desktop puts it", w.bar.align, host_title_bar()[1])
eng.cmd_SetProperty("TbTest", "Title", "Changed")
check("and follows it", w.bar.title.text(), "Changed")
check("the form keeps its designed height under the bar", (eng.find("c").widget.height(), w.height()), (300, 300 + TITLE_BAR_H))
check("Height reads as the form's", eng.cmd_GetProperty("TbTest", "Height"), 300)
eng.cmd_SetProperty("TbTest", "Height", "320")
for _ in range(5): app.processEvents()
check("and sets the form's", eng.find("c").widget.height(), 320)
check("eight grips to resize by", sum(g.isVisible() for g in w.grips), 8)
check("min, max and close", [k for k, b in w.bar.buttons.items() if b.isVisible()], ["min", "max", "close"])
w.showMaximized()
for _ in range(5): app.processEvents()
check("maximised: square, a thin edge all round, no grips", (w.edge.radius, w.edge.width_px, w.edge.isVisible(), sum(g.isVisible() for g in w.grips)), ((0, 0), 1, True, 0))
w.showNormal()
for _ in range(5): app.processEvents()
check("back again: rounded as the desktop rounds, its own edge, and grips", (w.edge.radius, w.edge.width_px, sum(g.isVisible() for g in w.grips)), (host_radius(), 2, 8))
eng.cmd_SetProperty("TbTest", "CornerRadius", "4")
check("CornerRadius says otherwise, all four", w.radius(), (4, 4))
eng.cmd_SetProperty("TbTest", "TitleBackground", "#F3F4F6")
eng.cmd_SetProperty("TbTest", "Version", "1.0")
check("its Version beside the title", ("Changed" in w.bar.title.text(), "1.0" in w.bar.title.text()), (True, True))
check("TitleBackground colours it, with dark words on a light bar", (w.bar.colour.name(), w.bar.ink.name()), ("#f3f4f6", "#111827"))
eng.cmd_SetProperty("TbTest", "TitleBar", "System")
for _ in range(5): app.processEvents()
check("System: the desktop's own again, same form size", (bool(w.windowFlags() & Qt.FramelessWindowHint), w.bar.isVisible(), eng.find("c").widget.height()), (False, False, 320))

fixed = os.path.join(d, "fixed.vml")
open(fixed, "w").write(FORM.replace("TbTest", "Fixed").replace("TitleBar=Own", "TitleBar=Own\nResizable=false"))
e2 = Engine(); e2.load(fixed)
for _ in range(10): app.processEvents()
w2 = e2.windows[0].widget
plain = os.path.join(d, "plain.vml")
open(plain, "w").write(FORM.replace("TbTest", "Plain").replace("BorderBrush=#127A68\nBorderThickness=2\n", ""))
e3 = Engine(); e3.load(plain)
for _ in range(10): app.processEvents()
check("no edge: still the desktop's own title bar colour", e3.windows[0].widget.bar.colour.name(), host_title_bar()[0].lower())
check("not resizable: no maximise, no grips", (w2.bar.buttons["max"].isVisible(), sum(g.isVisible() for g in w2.grips)), (False, 0))

# the designer keeps it, both ways
des = Engine()
des.load(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "designer", "designer.vml"))
for _ in range(5): app.processEvents()
des.cmd_ImportVml(form)
check("the designer reads it", (des.cmd_GetProperty("Surface", "FormTitleBar"), des.cmd_GetProperty("Surface", "FormBorderThickness")), ("Own", "2"))
out = os.path.join(d, "out.vml")
des.cmd_ExportVml("Surface", out)
text = open(out).read()
check("and writes it back", ("BorderThickness=2" in text, text.startswith("#!/usr/bin/env vml\n")), (True, True))
check("Own is the default, so not written", "TitleBar=" in text, False)
des.cmd_SetProperty("Surface", "FormTitleBar", "System")
des.cmd_ExportVml("Surface", out)
check("System is written when asked for", "TitleBar=System" in open(out).read(), True)
old = os.path.join(d, "old.vml")
open(old, "w").write(FORM.replace("TitleBar=Own\n", ""))
des.cmd_ClearDesign("Surface")
check("a new form wears its own title bar", des.cmd_GetProperty("Surface", "FormTitleBar"), "Own")
des.cmd_ImportVml(old)
check("a form that doesn't say gets ours", des.cmd_GetProperty("Surface", "FormTitleBar"), "Own")
plain = Engine()
plain.load(old)
for _ in range(5): app.processEvents()
pw = plain.windows[0].widget
check("and runs with it, the edge round it all", (pw.bar_mode, pw.bar is not None and pw.bar.isVisible()), ("Own", True))

print(f"{sum(ok)}/{len(ok)} passed")
sys.exit(0 if all(ok) else 1)
