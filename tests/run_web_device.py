"""What an app can ask of a phone: buzz, share, notify, where it is, a photo. In the Visualised app these go
through it; in a browser through what the browser offers; on a computer they do the nearest sensible thing."""
import json, os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("VML_PREFS", os.path.join(tempfile.mkdtemp(prefix="vml-prefs-"), "prefs.json"))
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("playwright isn't installed: skipping\n0/0 passed")
    raise SystemExit(0)
from vml.html import export_html

WORK = tempfile.mkdtemp(prefix="vml-device-")
ok = []

def check(label, got, want=True):
    passed = got == want
    ok.append(passed)
    print(f"{'PASS' if passed else 'FAIL'}  {label}" + ("" if passed else f": got {got!r}, wanted {want!r}"))

BUTTONS = ["Info", "Buzz", "Share", "Note", "Awake", "Where", "Snap"]
FORM = os.path.join(WORK, "Pocket.vml")
with open(FORM, "w") as f:
    f.write("@Window Pocket\nTitle=Pocket\nWidth=360\nHeight=740\n\n@Canvas c\nParent=Pocket\n\n")
    for i, name in enumerate(BUTTONS):
        f.write(f"@Button btn{name}\nParent=c\nCanvas.Left=20\nCanvas.Top={20 + i * 50}\nWidth=120\nHeight=40\nContent={name}\nOnClick=Do{name}\n\n")
    f.write("""@TextBlock lblOut
Parent=c
Canvas.Left=160
Canvas.Top=20
Text=-

@Image imgShot
Parent=c
Canvas.Left=160
Canvas.Top=80
Width=160
Height=120

@Script DoInfo
Interpreter=lua
<<LUA
Vml("SetProperty", "lblOut", "Text", Vml("DeviceInfo"))
LUA

@Script DoBuzz
Interpreter=lua
<<LUA
Vml("Vibrate", 150)
LUA

@Script DoShare
Interpreter=lua
<<LUA
Vml("Share", "Meet at the pier", "Plans")
LUA

@Script DoNote
Interpreter=lua
<<LUA
Vml("Notify", "Tea", "It's brewed")
LUA

@Script DoAwake
Interpreter=lua
<<LUA
Vml("KeepAwake", "true")
LUA

@Script DoWhere
Interpreter=lua
<<LUA
Vml("GetLocation", "Found")
LUA

@Script Found
Interpreter=lua
<<LUA
local lat, lon, within, problem = ...
Vml("SetProperty", "lblOut", "Text", lat .. "|" .. lon .. "|" .. within .. "|" .. problem)
LUA

@Script DoSnap
Interpreter=lua
<<LUA
Vml("TakePhoto", "imgShot", "Snapped")
LUA

@Script Snapped
Interpreter=lua
<<LUA
local image = ...
Vml("SetProperty", "lblOut", "Text", "photo in " .. image)
LUA
""")
page = export_html(FORM, os.path.join(WORK, "pocket.html"))

# a stand-in for the phone app: it writes down what the page asked of it
APP = """window.asked = [];
window.VisualisedDevice = {
  info: () => JSON.stringify({platform: "android-app", app: true, version: "0.1.0"}),
  vibrate: ms => { asked.push(["vibrate", ms]); }, share: (t, title) => { asked.push(["share", t, title]); },
  notify: (title, t) => { asked.push(["notify", title, t]); }, background: on => { asked.push(["background", on]); },
  torch: on => { asked.push(["torch", on]); }, speak: t => { asked.push(["speak", t]); }, open: u => { asked.push(["open", u]); },
  saveFile: (n, t) => { asked.push(["saveFile", n, t]); return n; }, keepAwake: on => { asked.push(["keepAwake", on]); }, toast: t => {} };"""
PNG = os.path.join(WORK, "shot.png")
with sync_playwright() as p:
    b = p.chromium.launch()
    # 1. in the app
    ctx = b.new_context(viewport={"width": 360, "height": 740}, is_mobile=True, has_touch=True, geolocation={"latitude": 50.7687, "longitude": 0.2845, "accuracy": 12}, permissions=["geolocation"])
    ctx.add_init_script(APP)
    pg = ctx.new_page()
    errors = []
    pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    pg.goto("file://" + str(page))
    pg.wait_for_selector("#vml_status[data-ready='1']", state="attached", timeout=20000)
    pg.screenshot(path=PNG)                                   # any picture will do for the camera to hand back
    text = lambda: pg.inner_text("#v_lblOut")
    pg.tap("#v_btnInfo")
    check("app: a script can tell it is running in the app on a phone", (json.loads(text()).get("platform"), json.loads(text()).get("app")), ("android-app", True))
    for name in ("Buzz", "Share", "Note", "Awake"):
        pg.tap("#v_btn" + name)
    check("app: buzz, share, notify and keep-awake go to the phone", pg.evaluate("asked"),
          [["vibrate", 150], ["share", "Meet at the pier", "Plans"], ["notify", "Tea", "It's brewed"], ["keepAwake", True]])
    more = pg.evaluate("""() => { asked.length = 0; const V = window.vml.Vml;
        V("RunInBackground", "true"); V("Torch", "true"); V("Speak", "Kettle's on"); V("OpenUrl", "tel:01323000000");
        return [V("SaveFile", "notes.txt", "two sugars"), asked, JSON.parse(V("DeviceInfo")).width]; }""")
    check("app: background, torch, speech, links and files go to the phone, and a script can ask the screen's size", more,
          ["notes.txt", [["background", True], ["torch", True], ["speak", "Kettle's on"], ["open", "tel:01323000000"], ["saveFile", "notes.txt", "two sugars"]], 360])
    pg.tap("#v_btnWhere")
    pg.wait_for_function("document.querySelector('#v_lblOut').innerText.includes('|')", timeout=10000)
    check("where the phone is comes back to the handler: latitude, longitude, metres, no problem", text(), "50.7687|0.2845|12|")
    with pg.expect_file_chooser() as chooser:
        pg.tap("#v_btnSnap")
    check("a photo is asked of the camera", (chooser.value.element.get_attribute("accept"), chooser.value.element.get_attribute("capture")), ("image/*", "environment"))
    chooser.value.set_files(PNG)
    pg.wait_for_function("document.querySelector('#v_lblOut').innerText.startsWith('photo')", timeout=10000)
    check("and lands in the Image, then the handler runs", (text(), pg.get_attribute("#v_imgShot", "src")[:23] if pg.get_attribute("#v_imgShot", "src") else None), ("photo in imgShot", "data:image/jpeg;base64,"))
    check("app: no offer to open in the app when already in it", pg.query_selector("#vml_offer") is None)
    check("app: nothing went wrong on the page", errors, [])
    ctx.close()

    # 2. in a phone's browser, previewed from the designer
    ctx = b.new_context(viewport={"width": 360, "height": 740}, is_mobile=True, has_touch=True, user_agent="Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 Chrome/126.0 Mobile Safari/537.36")
    ctx.add_init_script("window.VML_PREVIEW = true; window.buzzed = []; navigator.vibrate = ms => { buzzed.push(ms); return true; };"
                        "window.shared = []; navigator.share = d => { shared.push(d); return Promise.resolve(); };")
    pg = ctx.new_page()
    pg.goto("file://" + str(page))
    pg.wait_for_selector("#vml_status[data-ready='1']", state="attached", timeout=20000)
    pg.tap("#v_btnInfo")
    check("browser: a script can tell it is a web page on an Android phone", json.loads(pg.inner_text("#v_lblOut")), {"platform": "android-browser", "app": False, "online": True, "width": 360, "height": 740})
    pg.tap("#v_btnBuzz"); pg.tap("#v_btnShare")
    check("browser: buzz and share use what the browser has", (pg.evaluate("buzzed"), pg.evaluate("shared")), ([150], [{"text": "Meet at the pier", "title": "Plans"}]))
    with pg.expect_download() as got:
        pg.evaluate('window.vml.Vml("SaveFile", "notes.txt", "two sugars")')
    check("browser: SaveFile is a download", (got.value.suggested_filename, open(got.value.path()).read()), ("notes.txt", "two sugars"))
    pg.tap("#v_btnWhere")
    pg.wait_for_function("document.querySelector('#v_lblOut').innerText.includes('|')", timeout=25000)
    check("browser: location that isn't allowed tells the handler why", pg.inner_text("#v_lblOut"), "|||Location wasn't allowed.")
    offer = pg.query_selector("#vml_offer a")
    check("browser: a page previewed from the designer offers to open in the app", (offer is not None and offer.inner_text(), offer is not None and offer.get_attribute("href").startswith("visualised://")), ("Open in the Visualised app", True))
    ctx.close()

    # 3. the same page anywhere else makes no offer
    pg = b.new_page(viewport={"width": 360, "height": 740})
    pg.goto("file://" + str(page))
    pg.wait_for_selector("#vml_status[data-ready='1']", state="attached", timeout=20000)
    check("an exported app that isn't a preview makes no offer", pg.query_selector("#vml_offer") is None)
    b.close()

# on a computer
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from vml.engine import Engine
eng = Engine()
app = QApplication.instance()
app.setQuitOnLastWindowClosed(False)
said = []
from vml import dialogs
dialogs.message = lambda parent, title, message, *a, **k: said.append((title, message))

def steps():
    eng.load(FORM)
    for _ in range(10): app.processEvents()
    check("computer: DeviceInfo says desktop", (json.loads(eng.vml("DeviceInfo"))["platform"], json.loads(eng.vml("DeviceInfo"))["app"]), ("desktop", False))
    eng.vml("Vibrate", 100); eng.vml("KeepAwake", "true")
    eng.vml("Share", "Meet at the pier", "Plans")
    check("computer: Share puts the text on the clipboard", eng.vml("ClipboardGet"), "Meet at the pier")
    eng.vml("Notify", "Tea", "It's brewed")
    check("computer: Notify is a message box", said, [("Tea", "It's brewed")])
    eng.vml("GetLocation", "Found")
    for _ in range(10): app.processEvents()
    check("computer: GetLocation tells the handler a computer doesn't know", eng.vml("GetProperty", "lblOut", "Text"), "|||A computer doesn't know where it is.")
    print(f"\n{sum(ok)}/{len(ok)} passed")
    for w in list(eng.windows): w.widget.close()
    app.quit()

QTimer.singleShot(200, steps)
app.exec()
sys.exit(0 if all(ok) else 1)
