"""Clever Clogs 2: where you left your Bluetooth things, and the time you spent with them. The phone is a
stand-in here: it answers as the Visualised app would (paired devices, the Bluetooth log, location, pressure)."""
import calendar, json, os, sys, tempfile, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("VML_PREFS", os.path.join(tempfile.mkdtemp(prefix="vml-prefs-"), "prefs.json"))
os.environ["TZ"] = "UTC"
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("playwright isn't installed: skipping\n0/0 passed")
    raise SystemExit(0)
from vml.html import export_html

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FORM = os.path.join(HERE, "apps", "CleverClogs.vml")
WORK = tempfile.mkdtemp(prefix="vml-places-")
SHOTS = os.environ.get("CC_SHOTS", "")
ok = []

def check(label, got, want=True):
    passed = got == want
    ok.append(passed)
    print(f"{'PASS' if passed else 'FAIL'}  {label}" + ("" if passed else f": got {got!r}, wanted {want!r}"))

CAR, DESK, BUDS = "AA:BB:CC:00:00:01", "AA:BB:CC:00:00:02", "AA:BB:CC:00:00:03"
page = export_html(FORM, os.path.join(WORK, "clogs.html"))
APP = """window.asked = []; window.LOG = "[]"; window.P = "1013.20"; window.SAVED = null; window.SURE = true;
window.confirm = () => window.SURE;
window.VisualisedDevice = { info: () => '{"platform":"android-app","app":true}',
  bluetoothDevices: () => setTimeout(() => window.vmlFromPhone("bluetooth", JSON.stringify([
      {name: "Ford Sync", address: "%s", watched: false}, {name: "Keychron K2", address: "%s", watched: false},
      {name: "Galaxy Buds, Steve", address: "%s", watched: false}]), ""), 0),
  bluetoothWatch: (a, on) => { asked.push(["watch", a, on]); setTimeout(() => window.vmlFromPhone("watching", on ? "watching" : "stopped", ""), 0); },
  bluetoothLog: () => window.LOG, pressure: () => window.P,
  saveFile: (name, text) => { window.SAVED = [name, text]; return "Downloads/" + name; },
  open: u => { asked.push(["open", u]); }, share: (t, title) => { asked.push(["share", t, title]); } };""" % (CAR, DESK, BUDS)

now = int(time.time())
today = calendar.timegm(time.gmtime(now)[:3] + (0, 0, 0))
yday = today - 86400
at = lambda day, hh, mm: day + hh * 3600 + mm * 60
def ev(device, name, what, t, **where):
    return dict(device=device, name=name, what=what, time=t, **where)

with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={"width": 360, "height": 640}, is_mobile=True, has_touch=True, timezone_id="UTC",
                        geolocation={"latitude": 50.7687, "longitude": 0.2845, "accuracy": 12}, permissions=["geolocation"])
    ctx.add_init_script(APP)
    pg = ctx.new_page()
    errors = []
    pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto("file://" + str(page))
    pg.wait_for_selector("#vml_status[data-ready='1']", state="attached", timeout=20000)
    text = lambda n: pg.inner_text("#v_" + n)
    V = lambda *a: pg.evaluate("a => window.vml.Vml(...a)", list(a))
    opts = lambda n: pg.evaluate(f"[...document.querySelector('#v_{n}').options].map(o => o.text)")
    items = lambda n: pg.evaluate(f"[...document.querySelectorAll('#v_{n} option, #v_{n} li, #v_{n} .item')].map(o => o.textContent)")
    shot = lambda name: SHOTS and pg.screenshot(path=os.path.join(SHOTS, name))
    watches = lambda: [a for a in pg.evaluate("asked") if a[0] == "watch"]

    # ── as before: the car, saved by hand ──
    check("to begin with nothing is parked, and it says how to start", (text("lblWhen"), "I've parked here" in text("lblDetail")), ("Not parked yet", True))
    check("with nowhere saved, Take me there and Share are greyed out", (pg.is_disabled("#v_btnGo"), pg.is_disabled("#v_btnShare")), (True, True))
    V("RunScript", "DoGo")
    check("and there is nowhere to be taken", text("lblStatus"), "There's no place saved to go back to yet.")
    shot("1-start.png")
    pg.tap("#v_btnHere")
    pg.wait_for_function("document.querySelector('#v_lblWhen').innerText.startsWith('Parked')", timeout=10000)
    check("I've parked here saves the spot", (text("lblWhen"), "You saved it at" in text("lblDetail"), "within 12 m." in text("lblDetail"), "same level" in text("lblDetail")), ("Parked just now", True, True, True))
    check("and Take me there comes alive", pg.is_disabled("#v_btnGo"), False)
    pg.evaluate("window.P = '1012.48'"); V("RunScript", "Tick")
    check("two floors up the stairs, the barometer says so", "You are about 2 floors above it." in text("lblDetail"))
    pg.evaluate("window.P = '1013.55'"); V("RunScript", "Tick")
    check("and one floor down", "You are about 1 floor below it." in text("lblDetail"))
    pg.tap("#v_btnGo")
    check("Take me there opens walking directions to it", pg.evaluate("asked")[-1], ["open", "https://www.google.com/maps/dir/?api=1&travelmode=walking&destination=50.7687,0.2845"])
    V("SetProperty", "txtNote", "Text", "level 3, row C"); pg.focus("#v_txtNote"); pg.tap("#v_lblTitle")
    pg.tap("#v_btnShare")
    check("Share the spot hands on a map link, with the note", pg.evaluate("asked")[-1], ["share", "The car is here: https://maps.google.com/?q=50.7687,0.2845  (level 3, row C)", "Where the car is"])
    pg.evaluate("window.P = '1013.20'")

    # ── Things: anything Bluetooth ──
    pg.tap("#v_btnTabThings")
    check("the Things tab says what to do", "Press Find" in text("lblThings"))
    pg.tap("#v_btnFind")
    pg.wait_for_function("document.querySelector('#v_cmbAdd').options.length === 4", timeout=5000)
    check("Find lists what the phone is paired with, and adds none of them for you",
          (opts("cmbAdd"), watches(), text("lblStatus")), (["Add a device...", "Ford Sync", "Keychron K2", "Galaxy Buds Steve"], [], "Choose one from the list to add it."))
    pg.select_option("#v_cmbAdd", index=1)
    pg.wait_for_function("document.querySelector('#v_lblStatus').innerText.startsWith('Added')", timeout=5000)
    check("adding the car starts the phone watching it, guessed as a car", (watches(), text("lblStatus").startswith("Added Ford Sync as a car")), ([["watch", CAR, True]], True))
    pg.select_option("#v_cmbAdd", index=1)                    # (the car has gone from the list: the keyboard is first now)
    pg.wait_for_function("document.querySelector('#v_lblStatus').innerText.startsWith('Added Keychron')", timeout=5000)
    pg.select_option("#v_cmbAdd", index=1)
    pg.wait_for_function("document.querySelector('#v_lblStatus').innerText.startsWith('Added Galaxy')", timeout=5000)
    rows = items("lstThings")
    check("the keyboard is guessed as a desk, the buds as headphones",
          rows, ["🚗 Ford Sync  ·  not seen yet", "🖥 Keychron K2  ·  not seen yet", "🎧 Galaxy Buds Steve  ·  not seen yet"])
    check("and with nothing left to add, the list says so", opts("cmbAdd"), ["Nothing new to add"])
    V("SetProperty", "lstThings", "SelectedIndex", "2"); V("RunScript", "ThingPicked")
    pg.select_option("#v_cmbKind", index=3)
    pg.wait_for_function("document.querySelector('#v_lblStatus').innerText.includes('keys or a tag')", timeout=5000)
    check("a thing's kind can be changed", items("lstThings")[2].startswith("🔑 Galaxy Buds"))
    pg.select_option("#v_cmbKind", index=2)
    shot("2-things.png")

    # ── where each thing was left, from what the phone noted ──
    left = ev(CAR, "Ford Sync", "disconnected", now - 600, latitude=50.7701, longitude=0.2901, accuracy=8, pressure=1013.20)
    pg.evaluate("l => { window.LOG = JSON.stringify(l); }", [left]); V("RunScript", "Tick")
    check("the Things list says where each one is", items("lstThings")[0].endswith("left 10 minutes ago"))
    pg.tap("#v_btnTabWhere")
    check("Where offers every thing, and a place saved by hand",
          opts("cmbWhich"), ["🚗 Ford Sync", "🖥 Keychron K2", "🎧 Galaxy Buds Steve", "📌 A place saved by hand"])
    pg.select_option("#v_cmbWhich", index=0)
    check("the car: what the phone noted when it went out of range",
          (text("lblWhen"), "You left Ford Sync at" in text("lblDetail"), "within 8 m." in text("lblDetail")), ("Parked 10 minutes ago", True, True))
    shot("4-parked.png")
    pg.tap("#v_btnGo")
    check("and that is where it takes you", pg.evaluate("asked")[-1][1].endswith("destination=50.7701,0.2901"))
    pg.select_option("#v_cmbWhich", index=3)
    check("the place saved by hand is still there, with its note", (text("lblWhen"), V("GetProperty", "txtNote", "Text")), ("Parked just now", "level 3, row C"))
    pg.select_option("#v_cmbWhich", index=2)
    check("headphones never left anywhere say so, in their own words", (text("lblWhen"), V("GetProperty", "btnHere", "Content")), ("Not left anywhere yet", "I've left them here"))

    # ── a day at the desk, yesterday, and today so far ──
    log = [
        ev(DESK, "Keychron K2", "connected", now - 120),
        ev(CAR, "Ford Sync", "disconnected", now - 600, latitude=50.7701, longitude=0.2901, accuracy=8, pressure=1013.20),
        ev(DESK, "Keychron K2", "disconnected", at(yday, 17, 30)),
        ev(DESK, "Keychron K2", "connected", at(yday, 13, 5)),
        ev(CAR, "Ford Sync", "disconnected", at(yday, 12, 40), latitude=50.77, longitude=0.29, accuracy=10),
        ev(CAR, "Ford Sync", "connected", at(yday, 12, 15)),
        ev(DESK, "Keychron K2", "disconnected", at(yday, 12, 10)),
        ev(DESK, "Keychron K2", "connected", at(yday, 10, 33)),        # a three-minute cuppa
        ev(DESK, "Keychron K2", "disconnected", at(yday, 10, 30)),
        ev(DESK, "Keychron K2", "connected", at(yday, 8, 50)),
        ev(BUDS, "Galaxy Buds, Steve", "connected", at(yday - 80 * 86400, 9, 0)),   # too old to keep
    ]
    pg.evaluate("l => { window.LOG = JSON.stringify(l); }", log); V("RunScript", "Tick")
    pg.select_option("#v_cmbWhich", index=1)
    check("the desk keyboard in range: you're at your desk, and for how long", (text("lblWhen"), "since" in text("lblDetail"), "2m so far." in text("lblDetail")),
          ("At your desk", True, True))
    shot("5-desk.png")
    pg.tap("#v_btnTabTime")
    check("Time today: the desk so far", (text("lblDay"), items("lstDay")[-1].endswith("🖥 Keychron K2   2m"), "–now" in items("lstDay")[-1]), ("Today", True, True))
    check("and the next day button is greyed out on today", pg.is_disabled("#v_btnNext"), True)
    pg.tap("#v_btnPrev")
    check("yesterday's timeline: the cuppa doesn't count as leaving", items("lstDay"), [
        "08:50–12:10   🖥 Keychron K2   3h 20m", "12:15–12:40   🚗 Ford Sync   25m", "13:05–17:30   🖥 Keychron K2   4h 25m"])
    check("and the day's totals, biggest first", text("lblTotals"), "🖥 Keychron K2 7h 45m  ·  🚗 Ford Sync 25m")
    shot("3-time.png")
    pg.tap("#v_chkBreaks")
    pg.wait_for_timeout(200)
    check("untick the box and the cuppa splits the morning", (items("lstDay")[:2], text("lblTotals")),
          (["08:50–10:30   🖥 Keychron K2   1h 40m", "10:33–12:10   🖥 Keychron K2   1h 37m"], "🖥 Keychron K2 7h 42m  ·  🚗 Ford Sync 25m"))
    pg.tap("#v_chkBreaks")
    pg.wait_for_timeout(200)
    check("the week has its own totals, to the day shown", (text("lblWeek").split(":")[0] in ("This week, to yesterday", "That week, to yesterday"), "Keychron K2 7h 45m" in text("lblWeek")), (True, True))
    pg.tap("#v_btnShareDay")
    shared = pg.evaluate("asked")[-1]
    check("Share the day hands on the timeline", (shared[0], shared[1].startswith("Clever Clogs, Yesterday\n08:50–12:10"), shared[2]), ("share", True, "My day"))
    pg.tap("#v_btnCsv")
    saved = pg.evaluate("window.SAVED")
    lines = saved[1].strip().split("\n")
    check("Save as CSV: every stretch, for a timesheet", (saved[0], lines[0], lines[1], text("lblStatus")),
          ("clever-clogs-time.csv", "thing,kind,start,end,minutes", '"Keychron K2",Desk,' + time.strftime("%Y-%m-%d", time.gmtime(yday)) + " 08:50,"
           + time.strftime("%Y-%m-%d", time.gmtime(yday)) + " 12:10,200", "Saved 4 stretches to Downloads/clever-clogs-time.csv."))
    check("the open stretch has no end yet", lines[-1].split(",")[3], "")

    # ── remove one; the rest carries on ──
    pg.tap("#v_btnTabThings")
    V("SetProperty", "lstThings", "SelectedIndex", "2"); V("RunScript", "ThingPicked")
    pg.evaluate("window.SURE = false"); pg.tap("#v_btnRemove"); pg.wait_for_timeout(100)
    check("Remove asks first, and No leaves it be", len(items("lstThings")), 3)
    pg.evaluate("window.SURE = true"); pg.tap("#v_btnRemove"); pg.wait_for_timeout(200)
    check("Yes stops the phone watching it", (len(items("lstThings")), watches()[-1]), (2, ["watch", BUDS, False]))

    # ── shut and opened again: the phone forgot its log; the app didn't ──
    pg.evaluate("window.LOG = '[]'")
    pg.reload()
    pg.wait_for_selector("#vml_status[data-ready='1']", state="attached", timeout=20000)
    pg.tap("#v_btnTabTime"); pg.tap("#v_btnPrev")
    check("shut and opened again, yesterday is still there, though the phone kept no notes",
          items("lstDay"), ["08:50–12:10   🖥 Keychron K2   3h 20m", "12:15–12:40   🚗 Ford Sync   25m", "13:05–17:30   🖥 Keychron K2   4h 25m"])
    hist = json.loads(V("GetSetting", "history"))
    check("and nothing older than two months is kept", min(h["t"] for h in hist) >= now - 62 * 86400)

    # ── someone coming from Clever Clogs 1: their car, their spot and their note carry over ──
    for k, v in (("things", ""), ("spots", ""), ("history", "[]"), ("which", ""), ("note_" + CAR, ""),
                 ("cars", json.dumps([{"address": CAR, "name": "Ford Sync"}])), ("here_time", str(now - 7200)),
                 ("here_lat", "50.1"), ("here_lon", "0.2"), ("here_within", "9"), ("note", "level 2")):
        V("SetSetting", k, v)
    pg.reload()
    pg.wait_for_selector("#vml_status[data-ready='1']", state="attached", timeout=20000)
    check("version 1's car becomes a thing, with its spot and note",
          (opts("cmbWhich")[0], text("lblWhen"), V("GetProperty", "txtNote", "Text")), ("🚗 Ford Sync", "Parked 2 hours ago", "level 2"))
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
    eng.find("btnTabThings").widget.click()
    for _ in range(5): app.processEvents()
    eng.find("btnFind").widget.click()
    for _ in range(10): app.processEvents()
    check("computer: finding devices says it needs the phone app", text("lblStatus"), "Bluetooth devices need the Visualised app on a phone.")
    eng.find("btnTabWhere").widget.click()
    for _ in range(5): app.processEvents()
    eng.find("btnHere").widget.click()
    for _ in range(10): app.processEvents()
    check("computer: and so does saving the spot", text("lblStatus"), "A computer doesn't know where it is.")
    eng.find("btnTabTime").widget.click()
    for _ in range(5): app.processEvents()
    check("computer: the Time tab explains itself", text("lblTotals").startswith("Add your desk keyboard"))
    print(f"\n{sum(ok)}/{len(ok)} passed")
    for w in list(eng.windows): w.widget.close()
    app.quit()

QTimer.singleShot(200, steps)
app.exec()
sys.exit(0 if all(ok) else 1)
