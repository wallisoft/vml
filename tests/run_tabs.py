"""TabStrip, TabPage and Toolbar: on a form, from scripts, in the designer (pages, clicking tabs, adding into a page,
saving and opening again), and on the web."""
import json, os, re, subprocess, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("VML_PREFS", os.path.join(tempfile.mkdtemp(prefix="vml-prefs-"), "prefs.json"))
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication, QToolButton
from vml.engine import Engine
from vml.tabs import toolbar_items

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ok = []
def check(label, got, want):
    passed = got == want
    ok.append(passed)
    print(f"{'PASS' if passed else 'FAIL'}  {label}: {got!r}" + ("" if passed else f" (wanted {want!r})"))

FORM = """@Window T
Width=480
Height=320

@Canvas c
Parent=T

@Toolbar tb
Parent=c
Canvas.Left=0
Canvas.Top=0
Width=480
Height=34
Anchor=Top,Left,Right
Items=New=DoNew, Open, |, Save
OnClick=Tool

@TabStrip tabs
Parent=c
Canvas.Left=12
Canvas.Top=46
Width=456
Height=220
SelectedIndex=1
SelectionChanged=Changed

@TabPage pOne
Parent=tabs
Header=One

@TextBlock lbl
Parent=pOne
Canvas.Left=16
Canvas.Top=16
Text=on page one

@TabPage pTwo
Parent=tabs
Header=Two

@TextBlock out
Parent=c
Canvas.Left=12
Canvas.Top=280
Text=

@Script DoNew
Interpreter=lua
<<LUA
Vml("SetProperty", "out", "Text", "new")
LUA

@Script Tool
Interpreter=lua
<<LUA
Vml("SetProperty", "out", "Text", Vml("GetProperty", "out", "Text") .. "+" .. Vml("GetSetting", "toolbar_index"))
LUA

@Script Changed
Interpreter=lua
<<LUA
Vml("SetProperty", "out", "Text", "tab " .. Vml("GetProperty", "tabs", "SelectedIndex"))
LUA
"""
d = tempfile.mkdtemp(prefix="vml-tabs-")
form = os.path.join(d, "t.vml")
open(form, "w").write(FORM)
app = QApplication.instance() or QApplication([])
settle = lambda: [app.processEvents() for _ in range(6)]

check("Items: words, handlers and dividers", toolbar_items("New=DoNew, Open, |, Save"), [("New", "DoNew"), ("Open", ""), ("|", ""), ("Save", "")])

eng = Engine()
eng.load(form)
settle()
t = eng.find("tabs").widget
check("the strip holds its two pages, in order", [p.name for p in t.pages()], ["pOne", "pTwo"])
check("SelectedIndex=1 shows the second", [p.host.isVisible() for p in t.pages()], [False, True])
r = t.rects[0].center()
t.mousePressEvent(QMouseEvent(QEvent.MouseButtonPress, QPointF(r), QPointF(r), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier))
settle()
check("clicking a tab shows its page and runs SelectionChanged", ([p.host.isVisible() for p in t.pages()], eng.cmd_GetProperty("out", "Text")), ([True, False], "tab 0"))
eng.cmd_SetProperty("tabs", "SelectedIndex", "1")
settle()
check("a script picks a tab", eng.cmd_GetProperty("tabs", "SelectedIndex"), "1")
buttons = eng.find("tb").widget.findChildren(QToolButton)
check("the toolbar's buttons", [b.text() for b in buttons], ["New", "Open", "Save"])
buttons[0].click(); settle()
check("a button with a handler runs it, then OnClick", eng.cmd_GetProperty("out", "Text"), "new+0")
buttons[2].click(); settle()
check("OnClick knows which (dividers don't count)", eng.cmd_GetProperty("out", "Text"), "new+0+2")
eng.windows[0].widget.resize(640, 380); settle()
check("the toolbar stays full width as the form grows", eng.find("tb").host.width(), eng.find("c").widget.width())

# the designer
des = Engine()
des.load(os.path.join(ROOT, "designer", "designer.vml"))
settle()
groups = {x["name"]: x["group"] for x in json.loads(des.cmd_GetControlTypes())}
check("in the Add menu", (groups.get("TabStrip"), groups.get("TabPage"), groups.get("Toolbar")), ("Containers", "Containers", "Bars"))
view = des.find("Surface").widget
strip = des.cmd_AddDesignControl("TabStrip", 40, 60)
settle()
sw = des.find(strip).widget
check("a new strip comes with two pages", [des.find(strip).widget.headers(), sw.current()], [["Tab 1", "Tab 2"], 0])
tool = des.cmd_AddDesignControl("Toolbar", 200, 200)
check("a new toolbar goes along the top, full width", (des.find(tool).props.get("Canvas.Top"), des.find(tool).props.get("Width")), ("0", str(view.form.width())))
# click the second tab on the design surface
tab2 = sw.rects[1].center()
page_pt = sw.mapTo(view.page, tab2)
view.overlay.mousePressEvent(QMouseEvent(QEvent.MouseButtonPress, QPointF(page_pt), QPointF(page_pt), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier))
view.overlay.mouseReleaseEvent(QMouseEvent(QEvent.MouseButtonRelease, QPointF(page_pt), QPointF(page_pt), Qt.LeftButton, Qt.NoButton, Qt.NoModifier))
settle()
second = sw.pages()[1]
check("clicking a tab in the designer shows that page, selected", (sw.current(), view.selected), (1, second.name))
# add a button inside the page showing
inside = second.widget.mapTo(view.page, QPoint(30, 30)) - view.form.pos()
btn = des.cmd_AddDesignControl("Button", inside.x(), inside.y())
check("a control added on the page goes into it", des.find(btn).parent.name, second.name)
newpage = des.cmd_AddDesignControl("TabPage", inside.x(), inside.y())
check("Add TabPage on the strip adds a third tab, and shows it", (sw.headers()[-1], sw.current()), ("Tab 3", 2))
saved = os.path.join(d, "designed.vml")
des.cmd_ExportVml("Surface", saved)
again = Engine()
again.load(saved)
settle()
sv = again.find(strip)
check("saved and opened again: the strip, its pages and the button in page two",
      ([p.name for p in sv.widget.pages()], again.find(btn).parent.name), ([p.name for p in sw.pages()], second.name))

# placement, border, and the Edit Tabs command
from vml.tabs import strip_geometry
check("tabs down the left: the page sits beside them", strip_geometry({"TabPlacement": "Left", "BorderThickness": "2"}, 400, 200)[3], (122, 2, 276, 196))
check("tabs along the bottom: the page above them", strip_geometry({"TabPlacement": "Bottom"}, 400, 200)[3], (0, 0, 400, 166))
eng.cmd_SetProperty("tabs", "TabPlacement", "Left"); settle()
pg = eng.find("pOne").host if t.current() == 0 else eng.find("pTwo").host
check("set to Left at run time, the page moves beside the tabs", pg.x(), 120)
eng.cmd_SetProperty("tabs", "TabPlacement", "Top"); settle()
check("a new strip in the designer has a 2px border", (des.find(strip).props.get("BorderThickness"), des.find(strip).props.get("BorderBrush")), ("2", "#CBD5E1"))
pages = sw.pages()
spec = [{"page": pages[2].name, "header": "Third, now first"}, {"page": pages[1].name, "header": "Two"}, {"page": "", "header": "Brand new"}]
des.cmd_SetTabs(strip, json.dumps(spec)); settle()
check("Edit Tabs: reordered, renamed, one added and one deleted", sw.headers(), ["Third, now first", "Two", "Brand new"])
check("the tab left out is gone", any(pg is pages[0] for pg in sw.pages()), False)
check("the page with the button kept it", des.find(btn).parent.name, pages[1].name)
des.cmd_ExportVml("Surface", saved)
again2 = Engine(); again2.load(saved); settle()
check("and it saves in the new order", again2.find(strip).widget.headers(), ["Third, now first", "Two", "Brand new"])

# the web
out = os.path.join(d, "t.html")
subprocess.run([sys.executable, "-m", "vml", "html", form, out], capture_output=True, cwd=ROOT,
               env={**os.environ, "QT_QPA_PLATFORM": "offscreen"})
page = open(out).read() if os.path.exists(out) else ""
check("on the web: two tabs, the second chosen", re.findall(r'<div class="vtabh"[^>]*>(.*?)</div>', page)[:1],
      ['<button type="button">One</button><button type="button" class=on>Two</button>'])
check("the first page hidden, the second shown", [("display:none" in m) for m in re.findall(r'class="vtabp" style="([^"]*)"', page)], [True, False])
check("the toolbar's three buttons and a divider", len(re.findall(r'data-run="[^"]*">', page)), 3)

print(f"{sum(ok)}/{len(ok)} passed")
sys.exit(0 if all(ok) else 1)
