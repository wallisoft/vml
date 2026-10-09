"""A form as a web page on a phone: scaled to the screen when it is wider than the screen, left alone when it
fits, and reachable from a phone on the same network from the designer."""
import json, os, sys, tempfile, urllib.request
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("VML_PREFS", os.path.join(tempfile.mkdtemp(prefix="vml-prefs-"), "prefs.json"))
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("playwright isn't installed: skipping\n0/0 passed")
    raise SystemExit(0)
from vml.html import export_html

WORK = tempfile.mkdtemp(prefix="vml-phone-")
ok = []

def check(label, got, want=True):
    passed = got == want
    ok.append(passed)
    print(f"{'PASS' if passed else 'FAIL'}  {label}" + ("" if passed else f": got {got!r}, wanted {want!r}"))

def form(name, width, height, extra=""):
    path = os.path.join(WORK, name + ".vml")
    with open(path, "w") as f:
        f.write(f"""@Window {name}
Title={name}
Width={width}
Height={height}
{extra}
@MenuTheme theme
Parent={name}
Background=#1E3A8A

@Canvas c
Parent={name}
Background=#FFFFFF

@Button btnTap
Parent=c
Canvas.Left=20
Canvas.Top=20
Width=120
Height=40
Content=Tap
OnClick=Tapped

@TextBlock lblOut
Parent=c
Canvas.Left=20
Canvas.Top=80
Text=-

@Button btnRight
Parent=c
Canvas.Left={width - 140}
Canvas.Top=20
Width=120
Height=40
Content=Right
Anchor=Top,Right

@Button btnBottom
Parent=c
Canvas.Left=20
Canvas.Top={height - 60}
Width={width - 40}
Height=40
Content=Bottom
Anchor=Bottom,Left,Right

@Rectangle pad
Parent=c
Canvas.Left=20
Canvas.Top=120
Width=200
Height=100
Fill=#BFDBFE
OnPointerPressed=Pressed

@Script Tapped
Interpreter=lua
<<LUA
Vml("SetProperty", "lblOut", "Text", "tapped")
LUA

@Script Pressed
Interpreter=lua
<<LUA
Vml("SetProperty", "lblOut", "Text", Vml("GetSetting", "event_x") .. "," .. Vml("GetSetting", "event_y"))
LUA
""")
    return path

wide = export_html(form("Desk", 720, 480), os.path.join(WORK, "desk.html"))
phone = export_html(form("Pocket", 360, 740), os.path.join(WORK, "pocket.html"))
asis = export_html(form("AsIs", 720, 480, "PhoneFit=None\n"), os.path.join(WORK, "asis.html"))

box = lambda pg, sel: {k: round(v) for k, v in pg.eval_on_selector(sel, "e => { const r = e.getBoundingClientRect(); return {x: r.x, y: r.y, w: r.width, h: r.height, r: r.right, b: r.bottom}; }").items()}
with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={"width": 360, "height": 740}, device_scale_factor=3, is_mobile=True, has_touch=True)
    pg = ctx.new_page()
    errors = []
    pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    pg.goto("file://" + str(wide))
    pg.wait_for_selector("#vml_status[data-ready='1']", state="attached", timeout=20000)
    check("phone: the page says it is an app", pg.get_attribute('meta[name="mobile-web-app-capable"]', "content"), "yes")
    check("phone: the theme colour is the menu bar's", pg.get_attribute('meta[name="theme-color"]', "content").lower(), "#1e3a8a")
    check("phone: a form drawn 720 wide is scaled to a 360 screen: nothing hangs off the side", (box(pg, "#v_btnRight")["r"], pg.evaluate("document.documentElement.scrollWidth")), (350, 360))
    check("phone: and a button is half its drawn size", (box(pg, "#v_btnTap")["w"], box(pg, "#v_btnTap")["h"]), (60, 20))
    check("phone: what is anchored to the bottom reaches the bottom of the screen", box(pg, "#v_btnBottom")["b"], 730)
    pg.tap("#v_btnTap")
    check("phone: a tap is a click", pg.inner_text("#v_lblOut"), "tapped")
    r = box(pg, "#v_pad")
    pg.mouse.click(r["x"] + 50, r["y"] + 25)
    check("phone: where a press landed is told in the form's own pixels, not the screen's", pg.inner_text("#v_lblOut"), "100,50")
    pg.set_viewport_size({"width": 740, "height": 360}); pg.wait_for_timeout(150)
    check("phone: turned on its side, wide enough now, the form is its own size again", (box(pg, "#v_btnTap")["w"], box(pg, "#v_btnRight")["r"]), (120, 720))
    pg.set_viewport_size({"width": 360, "height": 740}); pg.wait_for_timeout(150)
    check("phone: and upright again it is scaled again", box(pg, "#v_btnTap")["w"], 60)

    pg.goto("file://" + str(phone))
    pg.wait_for_selector("#v_btnTap")
    pg.wait_for_selector("#vml_status[data-ready='1']", state="attached", timeout=20000)
    check("phone: a form drawn phone-sized is shown as drawn, full size", (box(pg, "#v_btnTap")["w"], box(pg, "#v_btnTap")["h"], box(pg, "#v_btnRight")["r"], box(pg, "#v_btnBottom")["b"]), (120, 40, 340, 720))
    pg.set_viewport_size({"width": 412, "height": 915}); pg.wait_for_timeout(150)
    check("phone: on a bigger phone its anchors stretch it, as on a desktop", (box(pg, "#v_btnTap")["w"], box(pg, "#v_btnRight")["r"], box(pg, "#v_btnBottom")["r"], box(pg, "#v_btnBottom")["b"]), (120, 392, 392, 895))
    pg.set_viewport_size({"width": 360, "height": 740})

    pg.goto("file://" + str(asis))
    pg.wait_for_selector("#vml_status[data-ready='1']", state="attached", timeout=20000)
    check("phone: PhoneFit=None leaves a wide form alone", box(pg, "#v_btnTap")["w"], 120)
    check("phone: nothing went wrong in the pages", errors, [])
    ctx.close()

    desk = b.new_page(viewport={"width": 1000, "height": 700})
    desk.goto("file://" + str(wide))
    desk.wait_for_selector("#vml_status[data-ready='1']", state="attached", timeout=20000)
    check("desktop: a browser wider than the form is untouched", (box(desk, "#v_btnTap")["w"], box(desk, "#v_btnRight")["r"]), (120, 980))
    b.close()

# from the designer
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from vml.engine import Engine
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
eng = Engine()
app = QApplication.instance()
app.setQuitOnLastWindowClosed(False)
said = []
eng.cmd_InfoDialog = lambda msg, title="": said.append(str(msg))
eng.cmd_ChoiceDialog = lambda msg, title="", buttons="": "Don't Save"

def steps():
    eng.load(os.path.join(HERE, "designer", "designer.vml"))
    for _ in range(10): app.processEvents()
    eng.find("FileNewPhone").action.trigger()
    for _ in range(10): app.processEvents()
    check("designer: New Phone Form is a form the size of a phone held upright", (str(eng.vml("GetProperty", "Surface", "FormWidth")), str(eng.vml("GetProperty", "Surface", "FormHeight"))), ("360", "740"))
    eng.vml("AddDesignControl", "Button", 20, 20)
    url = eng.cmd_PreviewOnPhone("Surface")
    if not url:
        print("SKIP  designer: this computer has no network address, so Preview on Phone can't be tried")
    else:
        local = "http://127.0.0.1:" + url.split(":")[2]
        page = urllib.request.urlopen(local, timeout=5)
        text = page.read().decode()
        check("designer: Preview on Phone serves the form at this computer's network address, with no file name to type",
              (url.startswith("http://") and not url.startswith("http://127."), url.endswith("/") and url.count("/") == 3, page.headers.get("Cache-Control"), "Button1" in text, 'name="theme-color"' in text), (True, True, "no-store", True, True))
        try:
            urllib.request.urlopen(local + "../../etc/passwd", timeout=5); leaked = True
        except Exception:
            leaked = False
        check("designer: and nothing outside its own folder", leaked, False)
        shown = []
        eng.cmd_InfoDialog = lambda msg, title="", picture="": shown.append((str(msg), str(picture)))
        eng.find("ViewPhone").action.trigger()
        for _ in range(10): app.processEvents()
        check("designer: the menu item shows the address, with a QR code of it, and puts it on the clipboard",
              (url in shown[-1][0], shown[-1][1].startswith("data:image/png;base64,"), eng.vml("ClipboardGet") == url), (True, True, True))
    # the QR code itself
    from vml import qr, dialogs
    m = qr.matrix("http://192.168.1.23:54321/")
    finder = [[m[y][x] for x in range(7)] for y in range(7)]
    check("QR: a code is square, with the corner squares a scanner looks for", (len(m), all(len(r) == len(m) for r in m), finder[0], finder[1], finder[3]),
          (25, True, [True] * 7, [True, False, False, False, False, False, True], [True, False, True, True, True, False, True]))
    check("QR: longer text makes a bigger code, and too much is refused", (len(qr.matrix("x" * 100)) > 25, eng.cmd_QrCode("x" * 300)), (True, ""))
    try:
        import cv2, numpy as np
        read = lambda t: cv2.QRCodeDetector().detectAndDecode(cv2.imdecode(np.frombuffer(qr.png(t, 8), np.uint8), cv2.IMREAD_GRAYSCALE))[0]
        texts = ["http://192.168.1.23:54321/", "https://visualised.io", "Visualised: draw it, script it, run it. " * 3, "é ü ✓ and a longer line of ordinary words to fill it"]
        check("QR: a reader reads back exactly what was put in, at several sizes", [read(t) == t for t in texts], [True] * 4)
    except ImportError:
        print("SKIP  QR: no QR reader (opencv) here to read the codes back")
    box = dialogs.Box(None, "t", "words", picture=eng.cmd_QrCode("http://192.168.1.23:54321/", 5))
    check("a message box can show a picture above its words", (box.picture is not None, box.picture.pixmap().width()), (True, (25 + 8) * 5))
    box.deleteLater()
    print(f"\n{sum(ok)}/{len(ok)} passed")
    app.quit()

QTimer.singleShot(200, steps)
app.exec()
sys.exit(0 if all(ok) else 1)
