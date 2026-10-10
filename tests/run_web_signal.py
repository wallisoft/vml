"""Signalling with light, and hearing speech: Listen, Flash and WatchLight, and the Morse Torch app that uses
all three. The phone and its camera are stand-ins here: a made-up light is fed to the reader at a camera's pace."""
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

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FORM = os.path.join(HERE, "apps", "MorseTorch.vml")
WORK = tempfile.mkdtemp(prefix="vml-signal-")
ok = []

def check(label, got, want=True):
    passed = got == want
    ok.append(passed)
    print(f"{'PASS' if passed else 'FAIL'}  {label}" + ("" if passed else f": got {got!r}, wanted {want!r}"))

page = export_html(FORM, os.path.join(WORK, "morse.html"))
made = open(page, encoding="utf-8").read()
check("an app's version and icon travel inside the page, where a phone looks for them",
      ('<meta name="app-version" content="1.5">' in made, '<link rel="icon" href="data:image/png;base64,' in made), (True, True))
APP = """window.asked = [];
window.VisualisedDevice = { info: () => '{"platform":"android-app","app":true}',
  flash: p => { asked.push(["flash", p]); }, listen: p => { asked.push(["listen", p]); }, speak: t => { asked.push(["speak", t]); },
  torch: on => { asked.push(["torch", on]); }, brightness: n => { asked.push(["brightness", n]); }, keepAwake: () => {}, log: t => { window.kept = (window.kept || []).concat([t]); } };
navigator.mediaDevices.getUserMedia = () => new Promise(() => {});      // a camera that never shows a picture"""
# A made-up light, seen the way a camera would see it: a reading every 33 ms, a little noise, and the Tick
# script run every 100 ms as the form's Timer would. unit: how fast the sender is sending.
SEE = """([pattern, dark, bright]) => { const V = window.vml.Vml, steps = pattern.split(",").map(Number);
  const reader = new window.vml.LightReader((state, ms) => V("RunScript", "Light", state, String(Math.round(ms)), ""));
  const total = steps.reduce((a, b) => a + b, 0) + 5000; let nextTick = 100, seed = 7;
  const noise = () => { seed = (seed * 1103515245 + 12345) % 2147483648; return (seed / 2147483648 - 0.5) * 10; };
  for (let t = -1500; t < total; t += 33) {
    let on = false, at = 0;
    if (t >= 0) for (let i = 0; i < steps.length; i++) { if (t < at + steps[i]) { on = i % 2 === 0; break; } at += steps[i]; }
    reader.feed((on ? bright : dark) + noise(), t);
    while (t >= nextTick) { V("RunScript", "Tick"); nextTick += 100; }
  }
  return document.querySelector("#v_lblGot").innerText; }"""
with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={"width": 360, "height": 640}, is_mobile=True, has_touch=True)
    ctx.add_init_script(APP)
    pg = ctx.new_page()
    errors = []
    pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    said = []
    pg.on("console", lambda m: said.append(m.text) if m.type == "log" else None)
    pg.goto("file://" + str(page))
    pg.wait_for_selector("#vml_status[data-ready='1']", state="attached", timeout=20000)
    status = lambda: pg.inner_text("#v_lblStatus")
    V = lambda *a: pg.evaluate("a => window.vml.Vml(...a)", list(a))

    # the torch page: what the app opens on
    shown = lambda name: pg.is_visible("#v_" + name)
    check("it opens on the torch, with the Morse out of the way", (shown("btnBig"), shown("btnSend"), shown("sldOn"), shown("rcWhite")), (True, False, False, False))
    pg.evaluate("asked.length = 0"); pg.tap("#v_btnBig")
    check("app: one tap and the torch is on, and the button says so", (pg.evaluate("asked")[-1], pg.inner_text("#v_btnBig"), pg.inner_text("#v_lblHome")), (["torch", True], "ON", "Torch on."))
    pg.evaluate("asked.length = 0"); pg.tap("#v_btnFlashT")
    check("app: Flashing is a second on and a second off", pg.evaluate("asked")[-1], ["flash", "1000,1000"])
    pg.evaluate("asked.length = 0; window.vmlFromPhone('flash')")
    check("app: and it goes round again until it is switched off", pg.evaluate("asked"), [["flash", "1000,1000"]])
    pg.tap("#v_btnSettings")
    pg.evaluate("""() => { for (const [id, v] of [["v_sldOn", 3], ["v_sldOff", 20]]) { const e = document.getElementById(id); e.value = v; e.dispatchEvent(new Event("input", { bubbles: true })); } }""")
    check("the sliders in Settings set how long it is on and off, and say so",
          (pg.inner_text("#v_lblOn"), pg.inner_text("#v_lblOff"), V("GetSetting", "on"), V("GetSetting", "off")),
          ("Flashing: on for 0.3 seconds", "Flashing: off for 2.0 seconds", "3", "20"))
    pg.tap("#v_btnBackS")
    pg.evaluate("asked.length = 0; window.vmlFromPhone('flash')")
    check("app: the next flash keeps the new time", pg.evaluate("asked"), [["flash", "300,2000"]])
    pg.evaluate("asked.length = 0"); pg.tap("#v_btnBig")
    check("app: the big button again and it is off, and stays off", (pg.evaluate("asked"), pg.inner_text("#v_btnBig"), pg.evaluate("window.vmlFromPhone('flash'), asked.length")),
          ([["flash", ""], ["torch", False]], "Torch", 2))
    pg.evaluate("asked.length = 0"); pg.tap("#v_btnScreen")
    check("app: Screen light turns the whole screen white and the screen up", (shown("rcWhite"), shown("btnBig"), pg.evaluate("asked")[-1]), (True, False, ["brightness", 100]))
    pg.evaluate("""() => { const e = document.getElementById("v_sldDim"); e.value = 30; e.dispatchEvent(new Event("input", { bubbles: true })); }""")
    check("app: its slider dims it", pg.evaluate("asked")[-1], ["brightness", 30])
    pg.dispatch_event("#v_rcWhite", "mousedown")
    check("app: a tap on the light goes back, and the screen is the phone's own again", (shown("rcWhite"), shown("btnBig"), pg.evaluate("asked")[-1]), (False, True, ["brightness", -1]))
    pg.tap("#v_btnTell")
    check("app: Tell it asks the phone to listen", pg.evaluate("asked")[-1][0], "listen")
    pg.evaluate("asked.length = 0; window.vmlFromPhone('listen', 'torch on please', '')")
    check("app: 'torch on' turns it on", pg.evaluate("asked")[-1], ["torch", True])
    pg.tap("#v_btnTell"); pg.evaluate("asked.length = 0; window.vmlFromPhone('listen', 'turn it off', '')")
    check("app: 'off' turns it off", pg.evaluate("asked")[-1], ["torch", False])
    pg.tap("#v_btnTell"); pg.evaluate("asked.length = 0; window.vmlFromPhone('listen', 'send hi', '')")
    check("app: 'send' and a message goes to the Morse page and flashes it, showing the dots and dashes",
          (shown("btnSend"), shown("btnBig"), pg.evaluate("asked")[-1], pg.inner_text("#v_lblOut")),
          (True, False, ["flash", "200,200,200,200,200,200,200,600,200,200,200"], "\u2022 \u2022 \u2022 \u2022 \u2003\u2022 \u2022"))
    pg.evaluate("for (let i = 0; i < 13; i++) window.vml.Vml('RunScript', 'SendTick')")
    check("and a bar under them shows how far the torch has got", V("GetProperty", "pbSend", "Value"), "50")
    pg.evaluate("window.vmlFromPhone('flash')")
    check("app: full when it is sent", (V("GetProperty", "pbSend", "Value"), status()), ("100", "Sent."))
    pg.tap("#v_btnBackM")
    pg.tap("#v_btnTell"); pg.evaluate("window.vmlFromPhone('listen', 'make me a sandwich', '')")
    check("app: anything else is told what it can say", status(), "Heard 'make me a sandwich'. Try: torch on, flash, screen, off, or send and a message.")
    pg.tap("#v_btnMorse")
    V("SetProperty", "txtSay", "Text", "SOS")

    pg.evaluate("asked.length = 0"); pg.tap("#v_btnSend")
    check("app: SOS goes to the torch as dots and dashes with the right gaps",
          (pg.evaluate("asked"), status()), ([["flash", "200,200,200,200,200,600,600,200,600,200,600,600,200,200,200,200,200"]], "Sending..."))
    pg.evaluate("window.vmlFromPhone('flash')")
    check("app: and the form is told when the torch has finished", status(), "Sent.")
    pg.tap("#v_btnSpeed")
    V("SetProperty", "txtSay", "Text", "a b")
    pg.evaluate("asked.length = 0"); pg.tap("#v_btnSend")
    check("app: Quick is a shorter dot, and a space is seven of them", pg.evaluate("asked")[0][1], "120,120,360,840,360,120,120,120,120,120,120")
    pg.tap("#v_btnBackM"); pg.tap("#v_btnSettings")
    pg.evaluate("""() => { const e = document.getElementById("v_sldWait"); e.value = 3; e.dispatchEvent(new Event("input", { bubbles: true })); }""")
    check("Settings can make Send wait, for someone testing with a phone in each hand", (pg.inner_text("#v_lblWait"), V("GetSetting", "wait")), ("Morse: wait 3 seconds after Send (time to put the phone down)", "3"))
    pg.tap("#v_btnBackS"); pg.tap("#v_btnMorse")
    V("SetProperty", "txtSay", "Text", "e"); pg.evaluate("asked.length = 0"); pg.tap("#v_btnSend")
    first = (pg.evaluate("asked.filter(a => a[0] === 'flash' && a[1])"), status())
    V("RunScript", "WaitTick"); V("RunScript", "WaitTick")
    second = (pg.evaluate("asked.filter(a => a[0] === 'flash' && a[1])"), status())
    V("RunScript", "WaitTick")
    check("app: then Send counts down before the torch starts", (first, second, pg.evaluate("asked.filter(a => a[0] === 'flash' && a[1])"), status()),
          (([], "Sending in 3..."), ([], "Sending in 1..."), [["flash", "120"]], "Sending..."))
    pg.evaluate("window.vmlFromPhone('flash')")
    check("app: what an app logs is handed to the phone app to keep, for its maker to read there", pg.evaluate("window.kept[window.kept.length - 1]"), "MorseTorch sent (unit 120): 120")
    V("RunScript", "DoPace")
    pg.evaluate("""() => { const e = document.getElementById("v_sldWait"); e.value = 0; e.dispatchEvent(new Event("input", { bubbles: true })); }""")
    V("SetProperty", "txtSay", "Text", "a b")
    pg.tap("#v_btnSpeed"); pg.tap("#v_btnSpeed")
    check("the speed button goes Steady, Quick, Slow and round again", (pg.inner_text("#v_btnSpeed"), status()), ("Steady", "Steady: about 6 words a minute."))

    pg.tap("#v_btnSay")
    check("app: Say it asks the phone to listen", pg.evaluate("asked")[-1], ["listen", "Say your message"])
    pg.evaluate("window.vmlFromPhone('listen', 'meet at the pier', '')")
    check("app: what was heard lands in the message box", (V("GetProperty", "txtSay", "Text"), status()), ("meet at the pier", "Heard. Press Send to flash it."))
    pg.tap("#v_btnSay"); pg.evaluate("window.vmlFromPhone('listen', '', 'Nothing was heard.')")
    check("app: and hearing nothing says so", status(), "Nothing was heard.")

    # reading it back
    pg.evaluate("asked.length = 0"); pg.tap("#v_btnSend")
    pier = pg.evaluate("asked")[0][1]
    pg.evaluate("window.vmlFromPhone('flash')")
    pg.tap("#v_btnWatch")
    check("app: Watch for light starts the camera over the dark box", (pg.inner_text("#v_btnWatch"), pg.evaluate("!!document.querySelector('video')")), ("Stop watching", True))
    pg.evaluate("asked.length = 0")
    got = pg.evaluate(SEE, [pier, 40, 230])
    check("a message flashed at a camera is read back, letter for letter", got.strip(), "MEET AT THE PIER")
    check("with the dots and dashes it arrived as on show (the newest, when there are too many to fit)",
          pg.inner_text("#v_lblIn").endswith("\u2022 \u2014 \u2014 \u2022 \u2003\u2022 \u2022 \u2003\u2022 \u2003\u2022 \u2014 \u2022"), True)
    logged = [m for m in said if m.startswith("[log] MorseTorch")]
    check("what was sent, what was seen flash by flash, and how the camera behaved are logged for the app's maker",
          (any("sent (unit 200): 200,200,200,200,200,600" in m for m in logged), any("read 'MEET AT THE PIER' (the light went quiet; " in m and "dot taken as" in m and "on " in m and "off " in m for m in logged), "camera: pictures" in logged[-1]), (True, True, True))
    check("and spoken when the light has been quiet a while", (pg.evaluate("asked"), status()), ([["speak", "MEET AT THE PIER"]], "Message received."))
    quick = ",".join(str(int(int(n) * 0.6)) for n in pier.split(","))
    pg.tap("#v_btnClear")
    check("a sender going faster than this phone is set to is followed", pg.evaluate(SEE, [quick, 40, 230]).strip(), "MEET AT THE PIER")
    pg.tap("#v_btnClear")
    check("a faint light against a bright room still reads", pg.evaluate(SEE, [pier, 150, 190]).strip(), "MEET AT THE PIER")
    pg.tap("#v_btnClear")
    sos = "200,200,200,200,200,600,600,200,600,200,600,600,200,200,200,200,200"
    pg.evaluate(SEE, [sos, 40, 230])
    check("a second message follows the first", pg.evaluate(SEE, [sos, 40, 230]).strip(), "SOS / SOS")
    pg.evaluate("window.vmlAway()")
    check("app: leaving the screen lets go of the camera, and the form is told", (pg.inner_text("#v_btnWatch"), pg.evaluate("!!document.querySelector('video')"), status()), ("Watch for light", False, "Watching stopped while the app was away."))
    pg.tap("#v_btnWatch")
    pg.tap("#v_btnWatch")
    check("app: Stop watching lets go of the camera", (pg.inner_text("#v_btnWatch"), pg.evaluate("!!document.querySelector('video')")), ("Watch for light", False))
    # the whole picture: a street lamp that never changes, a far torch two dots across that does, and a shaking hand
    pg.tap("#v_btnClear"); pg.tap("#v_btnWatch")
    seen = pg.evaluate("""([pattern]) => { const V = window.vml.Vml, steps = pattern.split(",").map(Number), W = 320, H = 240;
      const watcher = new window.vml.LightWatcher(W, H, (state, ms) => V("RunScript", "Light", state, String(Math.round(ms)), "")), finder = watcher.finder, lum = new Uint8Array(W * H);
      const total = steps.reduce((a, b) => a + b, 0) + 5000; let nextTick = 100, seed = 11, spots = [];
      const rnd = () => { seed = (seed * 1103515245 + 12345) % 2147483648; return seed / 2147483648; };
      for (let t = -3000; t < total; t += 33) {
        let on = false, at = 0;
        if (t >= 0) for (let i = 0; i < steps.length; i++) { if (t < at + steps[i]) { on = i % 2 === 0; break; } at += steps[i]; }
        const dx = Math.round((rnd() - 0.5) * 6), dy = Math.round((rnd() - 0.5) * 6);
        for (let i = 0; i < lum.length; i++) lum[i] = 50 + rnd() * 12;
        for (let y = 30; y < 50; y++) for (let x = 40; x < 60; x++) lum[(y + dy) * W + x + dx] = 255;       // the lamp
        if (on) for (let y = 180; y < 182; y++) for (let x = 250; x < 252; x++) lum[(y + dy) * W + x + dx] = 240;     // the torch
        watcher.feed(lum, t);
        if (t > 3000 && finder.spot) spots.push(finder.spot);
        while (t >= nextTick) { V("RunScript", "Tick"); nextTick += 100; }
      }
      const near = spots.filter(s => Math.abs(s.x * W - 250) < 14 && Math.abs(s.y * H - 181) < 14).length / Math.max(1, spots.length);
      return [document.querySelector("#v_lblGot").innerText.trim(), near > 0.95]; }""", [pier])
    check("a far torch is found wherever it is in the picture, past a brighter lamp and a shaking hand, and read", seen, ["MEET AT THE PIER", True])
    still = pg.evaluate("""() => { const W = 320, H = 240, f = new window.vml.BlinkFinder(W, H), lum = new Uint8Array(W * H); let seed = 3, found = 0;
      const rnd = () => { seed = (seed * 1103515245 + 12345) % 2147483648; return seed / 2147483648; };
      for (let t = 0; t < 20000; t += 33) { const dx = Math.round((rnd() - 0.5) * 6);
        for (let i = 0; i < lum.length; i++) lum[i] = 50 + rnd() * 12;
        for (let y = 30; y < 50; y++) for (let x = 40; x < 60; x++) lum[y * W + x + dx] = 255;
        f.feed(lum, t); if (t > 5000 && f.spot) found++; }
      return found; }""")
    check("a lamp and a shaking hand with nothing flashing is not taken for a signal", still, 0)
    # the real thing: what a phone's camera saw of another phone's torch, hand held in a bright room, played back
    import gzip, json
    tape = json.load(gzip.open(os.path.join(HERE, "tests", "data", "light-hello-claude.json.gz"), "rt"))
    pg.tap("#v_btnClear")
    real = pg.evaluate("""tape => { const V = window.vml.Vml, raw = atob(tape.squares), n = tape.cols * tape.rows;
      const watcher = new window.vml.LightWatcher(tape.cols * 8, tape.rows * 8, (state, ms) => V("RunScript", "Light", state, String(Math.round(ms)), "")), finder = watcher.finder;
      let nextTick = tape.times[0] + 100, on = 0, frames = 0;
      tape.times.forEach((t, f) => {
        for (let i = 0; i < n; i++) finder.now[i] = raw.charCodeAt(f * n + i);
        watcher.squares(t);
        if (finder.spot) { frames++; if (Math.abs(finder.spot.x * tape.cols - 22) < 5 && Math.abs(finder.spot.y * tape.rows - 14) < 5) on++; }
        while (t >= nextTick) { V("RunScript", "Tick"); nextTick += 100; }
      });
      for (let k = 0; k < 40; k++) V("RunScript", "Tick");
      return [document.querySelector("#v_lblGot").innerText, on / frames > 0.8]; }""", tape)
    check("a recording of a real phone's torch, hand held in a bright room, is read", ("HELLO CLAUDE," in real[0], real[1]), (True, True))
    print("      (read as: " + " ".join(real[0].split()) + ")")
    pg.tap("#v_btnWatch")
    steady = pg.evaluate("""() => { let n = 0; const r = new window.vml.LightReader(() => n++);
        for (let t = 0; t < 20000; t += 33) r.feed(200 + (t % 99 < 50 ? 4 : -4), t); return n; }""")
    check("a steady scene, however bright, is never a signal", steady, 0)
    check("app: nothing went wrong on the page", errors, [])
    ctx.close()

    # sending and watching at once, where the camera can work its own light; and taking turns where it can't
    for can in (True, False):
        ctx = b.new_context(viewport={"width": 360, "height": 640}, is_mobile=True, has_touch=True)
        ctx.add_init_script(APP + """
navigator.mediaDevices.getUserMedia = async () => { const s = document.createElement("canvas").captureStream(10), t = s.getVideoTracks()[0];
  window.lamp = []; t.getCapabilities = () => ({ torch: %s }); t.applyConstraints = c => { lamp.push(c.advanced[0].torch); return Promise.resolve(); }; return s; };""" % ("true" if can else "false"))
        pg = ctx.new_page()
        pg.goto("file://" + str(page))
        pg.wait_for_selector("#vml_status[data-ready='1']", state="attached", timeout=20000)
        pg.evaluate('window.vml.Vml("SetProperty", "txtSay", "Text", "e e")'); pg.tap("#v_btnMorse"); pg.tap("#v_btnSpeed")
        pg.tap("#v_btnWatch"); pg.wait_for_timeout(300)
        pg.tap("#v_btnSend")
        if can:
            pg.wait_for_function("document.querySelector('#v_lblStatus').innerText === 'Sent.'", timeout=5000)
            check("mirror: a camera that can work its own light signals with it while still watching",
                  (pg.evaluate("lamp"), [a for a in pg.evaluate("asked") if a[0] == "flash" and a[1]], pg.evaluate("!!document.querySelector('video')"), pg.inner_text("#v_btnWatch")),
                  ([True, False, True, False], [], True, "Stop watching"))
        else:
            pg.wait_for_timeout(600)
            during = (pg.evaluate("asked.filter(a => a[0] === 'flash')"), pg.evaluate("!!document.querySelector('video')"))
            pg.evaluate("window.vmlFromPhone('flash')"); pg.wait_for_timeout(300)
            check("turns: one that can't lets go of the camera for the torch, then goes back to watching",
                  (during, pg.evaluate("!!document.querySelector('video')"), pg.inner_text("#v_btnWatch"), pg.inner_text("#v_lblStatus")),
                  (([["flash", "120,840,120"]], False), True, "Stop watching", "Sent."))
        ctx.close()

    # in a browser the whole screen is the light
    ctx = b.new_context(viewport={"width": 360, "height": 640})
    pg = ctx.new_page()
    pg.goto("file://" + str(page))
    pg.wait_for_selector("#vml_status[data-ready='1']", state="attached", timeout=20000)
    pg.evaluate('window.vml.Vml("SetProperty", "txtSay", "Text", "e e")'); pg.click("#v_btnMorse"); pg.click("#v_btnSpeed"); pg.click("#v_btnSend")
    lit = pg.evaluate("getComputedStyle(document.querySelector('#vml_flash')).backgroundColor")
    pg.wait_for_function("document.querySelector('#v_lblStatus').innerText === 'Sent.'", timeout=5000)
    check("browser: Flash lights the whole screen, then clears it and says it is done", (lit, pg.query_selector("#vml_flash") is None), ("rgb(255, 255, 255)", True))
    pg.click("#v_btnWatch")
    pg.wait_for_function("/couldn't|needs|allowed/.test(document.querySelector('#v_lblStatus').innerText)", timeout=5000)
    check("browser: with no camera to be had, watching says why and stops", (pg.inner_text("#v_btnWatch"), "camera" in pg.inner_text("#v_lblStatus")), ("Watch for light", True))
    b.close()

# on a computer
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from vml.engine import Engine
from vml import dialogs
eng = Engine()
app = QApplication.instance()
app.setQuitOnLastWindowClosed(False)
dialogs.prompt = lambda *a, **k: "put the kettle on"

def steps():
    eng.load(FORM)
    for _ in range(10): app.processEvents()
    text = lambda n: str(eng.vml("GetProperty", n, "Text"))
    eng.find("btnSay").widget.click()
    check("computer: Say it asks you to type instead", (text("txtSay"), text("lblStatus")), ("put the kettle on", "Heard. Press Send to flash it."))
    eng.vml("SetProperty", "txtSay", "Text", "e")
    eng.find("btnSend").widget.click()
    first = text("lblStatus")
    QTimer.singleShot(600, lambda: finish(first))

def finish(first):
    text = lambda n: str(eng.vml("GetProperty", n, "Text"))
    check("computer: Send waits as long as the flashes would take, then says Sent", (first, text("lblStatus")), ("Sending...", "Sent."))
    eng.find("btnWatch").widget.click()
    for _ in range(10): app.processEvents()
    check("computer: watching says a computer can't", (text("lblStatus"), str(eng.vml("GetProperty", "btnWatch", "Content"))), ("A computer has no camera to watch with.", "Watch for light"))
    print(f"\n{sum(ok)}/{len(ok)} passed")
    for w in list(eng.windows): w.widget.close()
    app.quit()

QTimer.singleShot(200, steps)
app.exec()
sys.exit(0 if all(ok) else 1)
