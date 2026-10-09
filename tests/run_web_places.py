"""Where a Bluetooth device was left, the air pressure, and the Clever Clogs app that uses them. The phone
is a stand-in here: it answers as the Visualised app would."""
import json, os, sys, tempfile, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("VML_PREFS", os.path.join(tempfile.mkdtemp(prefix="vml-prefs-"), "prefs.json"))
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("playwright isn't installed: skipping\n0/0 passed")
    raise SystemExit(0)
from vml.html import export_html

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FORM = os.path.join(HERE, "apps", "CleverClogs.vml")
WORK = tempfile.mkdtemp(prefix="vml-places-")
ok = []

def check(label, got, want=True):
    passed = got == want
    ok.append(passed)
    print(f"{'PASS' if passed else 'FAIL'}  {label}" + ("" if passed else f": got {got!r}, wanted {want!r}"))

page = export_html(FORM, os.path.join(WORK, "car.html"))
APP = """window.asked = []; window.LOG = "[]"; window.P = "1013.20";
window.VisualisedDevice = { info: () => '{"platform":"android-app","app":true}',
  bluetoothDevices: () => setTimeout(() => window.vmlFromPhone("bluetooth", JSON.stringify([
      {name: "Ford Sync", address: "AA:BB:CC:00:00:01", watched: false}, {name: "Headphones, left", address: "AA:BB:CC:00:00:02", watched: false}]), ""), 0),
  bluetoothWatch: (a, on) => { asked.push(["watch", a, on]); setTimeout(() => window.vmlFromPhone("watching", on ? "watching" : "stopped", ""), 0); },
  bluetoothLog: () => window.LOG, pressure: () => window.P,
  open: u => { asked.push(["open", u]); }, share: (t, title) => { asked.push(["share", t, title]); } };"""
with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={"width": 360, "height": 640}, is_mobile=True, has_touch=True,
                        geolocation={"latitude": 50.7687, "longitude": 0.2845, "accuracy": 12}, permissions=["geolocation"])
    ctx.add_init_script(APP)
    pg = ctx.new_page()
    errors = []
    pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    pg.goto("file://" + str(page))
    pg.wait_for_selector("#vml_status[data-ready='1']", state="attached", timeout=20000)
    text = lambda n: pg.inner_text("#v_" + n)
    V = lambda *a: pg.evaluate("a => window.vml.Vml(...a)", list(a))
    check("to begin with nothing is parked, and it says how to start", (text("lblWhen"), "I've parked here" in text("lblDetail")), ("Not parked yet", True))
    pg.tap("#v_btnGo")
    check("and there is nowhere to be taken", text("lblStatus"), "There's no place saved to go back to yet.")

    pg.tap("#v_btnHere")
    pg.wait_for_function("document.querySelector('#v_lblWhen').innerText.startsWith('Parked')", timeout=10000)
    check("I've parked here saves the spot", (text("lblWhen"), "You saved it at" in text("lblDetail"), "within 12 m." in text("lblDetail"), "same level" in text("lblDetail")), ("Parked just now", True, True, True))
    pg.evaluate("window.P = '1012.48'"); V("RunScript", "Tick")
    check("two floors up the stairs, the barometer says so", "You are about 2 floors above it." in text("lblDetail"))
    pg.evaluate("window.P = '1013.55'"); V("RunScript", "Tick")
    check("and one floor down", "You are about 1 floor below it." in text("lblDetail"))
    pg.tap("#v_btnGo")
    check("Take me there opens walking directions to it", pg.evaluate("asked")[-1], ["open", "https://www.google.com/maps/dir/?api=1&travelmode=walking&destination=50.7687,0.2845"])
    V("SetProperty", "txtNote", "Text", "level 3, row C"); pg.focus("#v_txtNote"); pg.tap("#v_lblTitle")
    pg.tap("#v_btnShare")
    check("Share the spot hands on a map link, with the note", pg.evaluate("asked")[-1], ["share", "The car is here: https://maps.google.com/?q=50.7687,0.2845  (level 3, row C)", "Where the car is"])

    pg.tap("#v_btnFind")
    pg.wait_for_function("document.querySelector('#v_cmbCar').options.length === 3", timeout=5000)
    check("Find lists what the phone is paired with, and chooses none of them for you",
          (pg.evaluate("[...document.querySelector('#v_cmbCar').options].map(o => o.text)"), [a for a in pg.evaluate("asked") if a[0] == "watch"], text("lblStatus")),
          (["Choose a device", "Ford Sync", "Headphones left"], [], "Choose your car from the list."))
    pg.select_option("#v_cmbCar", index=1)
    pg.wait_for_function("document.querySelector('#v_lblStatus').innerText.startsWith('Done')", timeout=5000)
    check("choosing the car starts the phone noting where it is left", ([a for a in pg.evaluate("asked") if a[0] == "watch"], text("lblCar")),
          ([["watch", "AA:BB:CC:00:00:01", True]], "Noting where you leave Ford Sync."))
    pg.select_option("#v_cmbCar", index=2)
    pg.wait_for_function("document.querySelector('#v_lblCar').innerText.includes(' and ')", timeout=5000)
    check("a household with two cars chooses both", ([a for a in pg.evaluate("asked") if a[0] == "watch"][-1], text("lblCar")),
          (["watch", "AA:BB:CC:00:00:02", True], "Noting where you leave Ford Sync and Headphones, left."))
    pg.tap("#v_btnForget"); pg.wait_for_timeout(100)
    check("Forget stops watching them all", ([a for a in pg.evaluate("asked") if a[0] == "watch"][-2:], text("lblCar")),
          ([["watch", "AA:BB:CC:00:00:01", False], ["watch", "AA:BB:CC:00:00:02", False]], "Have it noted for you: choose your car's Bluetooth."))
    pg.select_option("#v_cmbCar", index=0); pg.select_option("#v_cmbCar", index=1)
    pg.wait_for_function("document.querySelector('#v_lblCar').innerText.endsWith('Ford Sync.')", timeout=5000)

    now = int(time.time())
    V("SetSetting", "here_time", str(now - 7200))
    left = {"device": "AA:BB:CC:00:00:01", "name": "Ford Sync", "what": "disconnected", "time": now - 600, "latitude": 50.7701, "longitude": 0.2901, "accuracy": 8, "pressure": 1013.55}
    other = {"device": "AA:BB:CC:00:00:02", "name": "Headphones", "what": "disconnected", "time": now - 30, "latitude": 1, "longitude": 2}
    pg.evaluate("l => { window.LOG = JSON.stringify(l); }", [other, left]); V("RunScript", "Tick")
    check("what the phone noted when the car went out of range is newer than the button, so it wins; other devices don't count",
          (text("lblWhen"), "You left Ford Sync at" in text("lblDetail"), "within 8 m." in text("lblDetail"), "same level" in text("lblDetail")), ("Parked 10 minutes ago", True, True, True))
    pg.tap("#v_btnGo")
    check("and that is where it takes you", pg.evaluate("asked")[-1][1].endswith("destination=50.7701,0.2901"))
    nowhere = dict(left, time=now - 300); nowhere.pop("latitude"); nowhere.pop("longitude"); nowhere.pop("accuracy")
    pg.evaluate("l => { window.LOG = JSON.stringify(l); }", [nowhere, left]); V("RunScript", "Tick")
    check("a time noted without a place says so", "but the phone couldn't tell where." in text("lblDetail"))
    back = {"device": "AA:BB:CC:00:00:01", "name": "Ford Sync", "what": "connected", "time": now - 60}
    pg.evaluate("l => { window.LOG = JSON.stringify(l); }", [back, left]); V("RunScript", "Tick")
    check("back in range of the car, it knows you're with it", (text("lblWhen"), "connected to Ford Sync since" in text("lblDetail")), ("You're with the car", True))

    pg.reload()                                               # (the stand-in phone starts again with nothing noted)
    pg.wait_for_selector("#vml_status[data-ready='1']", state="attached", timeout=20000)
    check("shut and opened again, it still knows: the spot, the note and which car",
          (text("lblWhen"), V("GetProperty", "txtNote", "Text"), text("lblCar")), ("Parked 2 hours ago", "level 3, row C", "Noting where you leave Ford Sync."))
    check("nothing went wrong on the page", errors, [])
    b.close()

# on a computer
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from vml.engine import Engine
eng = Engine()
app = QApplication.instance()
app.setQuitOnLastWindowClosed(False)

def steps():
    eng.load(FORM)
    for _ in range(10): app.processEvents()
    text = lambda n: str(eng.vml("GetProperty", n, "Text"))
    check("computer: the form opens and says nothing is parked", text("lblWhen"), "Not parked yet")
    eng.find("btnFind").widget.click()
    for _ in range(10): app.processEvents()
    check("computer: finding devices says it needs the phone app", text("lblStatus"), "Bluetooth devices need the Visualised app on a phone.")
    eng.find("btnHere").widget.click()
    for _ in range(10): app.processEvents()
    check("computer: and so does saving the spot", text("lblStatus"), "A computer doesn't know where it is.")
    print(f"\n{sum(ok)}/{len(ok)} passed")
    for w in list(eng.windows): w.widget.close()
    app.quit()

QTimer.singleShot(200, steps)
app.exec()
sys.exit(0 if all(ok) else 1)
