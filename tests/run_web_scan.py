"""ScanCode in the Visualised app: the page hands the camera's picture to the app, which reads the code.
The app is stood in for here; that its reader reads our own codes is checked where the app is built."""
import base64, os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("playwright isn't installed: skipping\n0/0 passed")
    raise SystemExit(0)
from vml.html import export_html

WORK = tempfile.mkdtemp(prefix="vml-scan-")
ok = []

def check(label, got, want=True):
    passed = got == want
    ok.append(passed)
    print(f"{'PASS' if passed else 'FAIL'}  {label}" + ("" if passed else f": got {got!r}, wanted {want!r}"))

with open(os.path.join(WORK, "scan.vml"), "w") as f:
    f.write("""@Window Scan
Title=Scan
Width=300
Height=200

@Canvas c
Parent=Scan

@TextBlock lblGot
Parent=c
Canvas.Left=8
Canvas.Top=8
Width=280
Height=100
Text=

@Script Got
Interpreter=lua
<<LUA
local text, problem = ...
Vml("SetProperty", "lblGot", "Text", "[" .. text .. "][" .. problem .. "]")
LUA
""")
page = export_html(os.path.join(WORK, "scan.vml"), os.path.join(WORK, "scan.html"))
APP = """window.__calls = [];
window.VisualisedDevice = { readCode(grey, w, h) { window.__calls.push([grey.length, w, h, atob(grey).length]);
    return window.__calls.length < 3 ? "" : "VL1-what-the-code-says"; }, log() {} };"""

with sync_playwright() as p:
    b = p.chromium.launch(args=["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"])
    ctx = b.new_context()
    ctx.add_init_script(APP + " delete window.BarcodeDetector;")
    pg = ctx.new_page()
    pg.goto("file://" + str(page))
    pg.wait_for_selector("#vml_status[data-ready='1']", state="attached", timeout=20000)
    pg.evaluate("window.vml.Vml('ScanCode', 'Got', 'Point it')")
    check("the camera opens though the page has no reader of its own", pg.wait_for_selector("#vml_scan video", timeout=5000) is not None)
    pg.wait_for_function("/VL1/.test(document.body.innerText)", timeout=15000)
    calls = pg.evaluate("window.__calls")
    check("the app was asked until it could read it", len(calls), 3)
    n, w, h, raw = calls[-1]
    check("one byte for each dot of the picture", raw, w * h)
    check("a picture small enough to hand over", max(w, h) <= 720 and min(w, h) >= 100)
    check("the handler has what the code says", "[VL1-what-the-code-says][]" in pg.inner_text("body"))
    check("the camera is put away", pg.query_selector("#vml_scan") is None)
    b.close()

print(f"\n{sum(ok)}/{len(ok)} passed")
