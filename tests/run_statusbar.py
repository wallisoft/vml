"""StatusBar: panels, the clock panels, Text from a script, staying along the foot, the designer's placing, the web."""
import json, os, re, subprocess, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("VML_PREFS", os.path.join(tempfile.mkdtemp(prefix="vml-prefs-"), "prefs.json"))
from PySide6.QtWidgets import QApplication
from vml.engine import Engine
from vml.statusbar import fill
import datetime

ok = []
def check(label, got, want):
    passed = got == want
    ok.append(passed)
    print(f"{'PASS' if passed else 'FAIL'}  {label}: {got!r}" + ("" if passed else f" (wanted {want!r})"))

FORM = """@Window SbTest
Width=420
Height=200

@Canvas c
Parent=SbTest

@StatusBar sb
Parent=c
Canvas.Left=0
Canvas.Top=174
Width=420
Height=26
Anchor=Bottom,Left,Right
Panels=Ready|{date}|{time}
"""
d = tempfile.mkdtemp(prefix="vml-sb-")
form = os.path.join(d, "sb.vml")
open(form, "w").write(FORM)
app = QApplication.instance() or QApplication([])

now = datetime.datetime(2026, 10, 17, 9, 5)
check("{time} and {date} are filled in", fill("{date} at {time}", now), "17 Oct 2026 at 09:05")
check("plain words are left alone", fill("Ready", now), "Ready")

eng = Engine()
eng.load(form)
for _ in range(5): app.processEvents()
check("the first panel shows its words", eng.cmd_GetProperty("sb", "Text"), "Ready")
eng.cmd_SetProperty("sb", "Text", "Saving...")
check("Text from a script changes the first panel", eng.cmd_GetProperty("sb", "Text"), "Saving...")
check("and leaves the others", eng.find("sb").widget.shown()[1:], [fill("{date}"), fill("{time}")])
w = eng.windows[0].widget
w.resize(640, 300)
for _ in range(10): app.processEvents()
h = eng.find("sb").host
check("it stays along the foot, full width, when the form grows", (h.x(), h.y() + h.height(), h.width()), (0, eng.find("c").widget.height(), eng.find("c").widget.width()))

# the designer puts a new one along the bottom of the form, full width
des = Engine()
des.load(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "designer", "designer.vml"))
for _ in range(5): app.processEvents()
groups = {t["name"]: t["group"] for t in json.loads(des.cmd_GetControlTypes())}
check("it's in the Add menu's Bars group", groups.get("StatusBar"), "Bars")
name = des.cmd_AddDesignControl("StatusBar", 100, 100)
form_w = des.find("Surface").widget.form
sbn = des.find(name)
check("added along the foot of the form, full width",
      (sbn.props.get("Canvas.Left"), int(sbn.props.get("Canvas.Top")) + int(sbn.props.get("Height")), sbn.props.get("Width")),
      ("0", form_w.height(), str(form_w.width())))
check("anchored to stay there", sbn.props.get("Anchor"), "Bottom,Left,Right")
check("with Ready, the date and the time", sbn.props.get("Panels"), "Ready|{date}|{time}")

# the web page
out = os.path.join(d, "sb.html")
subprocess.run([sys.executable, "-m", "vml", "html", form, out], capture_output=True, env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
               cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
page = open(out).read() if os.path.exists(out) else ""
check("on the web: a bar with its three panels", len(re.findall(r'<span data-tpl="[^"]*">', page.split('class="sbar"', 1)[-1].split("</div>")[0])), 3)
check("pinned to the foot", "bottom:0px" in page.split('class="sbar"', 1)[-1][:200], True)

print(f"{sum(ok)}/{len(ok)} passed")
sys.exit(0 if all(ok) else 1)
