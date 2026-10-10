"""Link: a desktop app, a web page and a phone app talking to each other through a relay that cannot read a word.
The relay here is a stand-in on this machine; where PHP is installed the real one (server/link/link.php) is put
through the same exchange."""
import base64, json, os, shutil, subprocess, sys, tempfile, time, urllib.request
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("VML_PREFS", os.path.join(tempfile.mkdtemp(prefix="vml-prefs-"), "prefs.json"))
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("playwright isn't installed: skipping\n0/0 passed")
    raise SystemExit(0)
try:
    import cryptography  # noqa: F401
except ImportError:
    print("the cryptography package isn't installed (pip install cryptography): skipping\n0/0 passed")
    raise SystemExit(0)
from link_relay import Relay
from vml import link
from vml.html import export_html

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = tempfile.mkdtemp(prefix="vml-link-")
ok = []

def check(label, got, want=True):
    passed = got == want
    ok.append(passed)
    print(f"{'PASS' if passed else 'FAIL'}  {label}" + ("" if passed else f": got {got!r}, wanted {want!r}"))

def events(end, want, secs=6):
    """What has arrived at a desktop end, waiting until there are `want` of them (or time runs out)."""
    out, until = [], time.time() + secs
    while len(out) < want and time.time() < until:
        try:
            out.append(end.events.get(timeout=0.1))
        except Exception:
            pass
    return out

open(os.path.join(WORK, "talk.vml"), "w").write("""@Window Talk
Title=Talk
Width=320
Height=240

@Canvas c
Parent=Talk

@TextBlock lblGot
Parent=c
Canvas.Left=8
Canvas.Top=8
Width=300
Height=200
TextWrapping=Wrap
Text=

@Script Got
Interpreter=lua
<<LUA
local what, text = ...
Heard = (Heard or "") .. what .. ":" .. text .. "|"
Vml("SetProperty", "lblGot", "Text", Heard)
if what == "message" and text == "ping" then Vml("LinkSend", "pong") end
LUA
""")
page = export_html(os.path.join(WORK, "talk.vml"), os.path.join(WORK, "talk.html"))
relay = Relay()
os.environ["VML_LINK_URL"] = relay.url

with sync_playwright() as p:
    b = p.chromium.launch()

    def open_page():
        ctx = b.new_context()
        ctx.add_init_script(f"window.VML_LINK_URL = {json.dumps(relay.url)};")
        pg = ctx.new_page()
        pg.goto("file://" + str(page))
        pg.wait_for_selector("#vml_status[data-ready='1']", state="attached", timeout=20000)
        return pg
    V = lambda pg, *a: pg.evaluate("a => window.vml.Vml(...a)", list(a))
    heard = lambda pg: pg.inner_text("#v_lblGot")
    def until(pg, text, secs=8):
        try:
            pg.wait_for_function("t => document.querySelector('#v_lblGot').innerText.includes(t)", arg=text, timeout=secs * 1000)
        except Exception:
            pass
        return heard(pg)

    one = open_page()
    code = V(one, "Link", "Got")
    check("a page starts a link and is given a code to show the other app", (code[:3], len(code), V(one, "LinkCode") == code), ("VL1", 46, True))
    one.wait_for_timeout(600)

    desk = link.Link(code)
    check("a desktop app joins with the code, and each end is told the other is there", (events(desk, 1), "joined:|" in until(one, "joined:|")), ([("joined", "")], True))
    desk.send("hello from the desk é•你")
    V(one, "LinkSend", "and from the page")
    check("a message each way arrives as it was sent, accents and all", (until(one, "你").endswith("message:hello from the desk é•你|"), events(desk, 1)), (True, [("message", "and from the page")]))
    desk.send("ping")
    check("an app's own script can answer a message", events(desk, 1), [("message", "pong")])
    long = "x" * 15000
    desk.send(long)
    check("a long message goes through whole", until(one, long[:50]).endswith("message:" + long + "|"), True)

    two = open_page()
    V(two, "Link", "Got", code)
    check("a third app can join the same link, and all are told", (events(desk, 1), "joined:|" in until(two, "joined:|"), heard(one).count("joined:|")), ([("joined", "")], True, 2))
    V(two, "LinkSend", "to you both")
    check("what one sends, every other end gets", (events(desk, 1), until(one, "to you both").endswith("message:to you both|"), "to you both" in heard(two)), ([("message", "to you both")], True, False))

    sent = json.dumps(relay.messages)
    check("the relay was handed nothing it could read: not the words, not the code",
          (any(w in sent for w in ("hello from the desk", "and from the page", "to you both", "ping", "pong", "xxxxxxxx")), code in sent, code[3:] in sent, desk.channel in code),
          (False, False, False, False))
    check("each message is sealed afresh: the same text never looks the same twice",
          len({m["b"] for m in relay.messages}) == len(relay.messages), True)

    # someone who can see the relay plays an old message back
    old = next(m for m in relay.messages if m["s"] == desk.sender)
    before = heard(one)
    req = urllib.request.Request(relay.url + "?c=" + desk.channel, data=json.dumps({"s": old["s"], "b": old["b"]}).encode(), headers={"Content-Type": "text/plain"})
    urllib.request.urlopen(req).read()
    forged = base64.b64encode(os.urandom(60)).decode()
    urllib.request.urlopen(urllib.request.Request(relay.url + "?c=" + desk.channel, data=json.dumps({"s": "00" * 8, "b": forged}).encode())).read()
    desk.send("after the replay")
    check("an old message played back, and one made up by a stranger, are not delivered",
          until(one, "after the replay")[len(before):], "message:after the replay|")

    other = link.Link()
    other.send("nobody is listening")
    check("a link with a different code hears nothing of this one", (other.channel != desk.channel, events(other, 1, 1.5)), (True, []))
    other.close()

    relay.down = True
    check("when the relay can't be reached, sending says so", (V(two, "LinkSend", "into the void"), "error:" in until(two, "error:")), ("true", True))
    try:
        desk.send("into the void")
        told = ""
    except link.LinkError as exc:
        told = str(exc)
    check("on the desktop too", told.startswith("The relay "), True)
    relay.down = False
    one.wait_for_timeout(2500)
    desk.send("back again")
    check("and when it comes back, the link carries on", until(one, "back again", 12).endswith("message:back again|"), True)

    V(two, "LinkClose")
    check("closing tells the others", (events(desk, 1, 8), "left:|" in until(one, "left:|")), ([("left", "")], True))
    check("a code that isn't one is refused, in words", ("error:That isn't a link code.|" in (V(two, "Link", "Got", "VL1nonsense"), until(two, "isn't a link code"))[1]), True)
    try:
        link.Link("hello")
        told = ""
    except link.LinkError as exc:
        told = str(exc)
    check("on the desktop too", told, "That isn't a link code.")
    desk.close()

    # Link Chat, the app that shows it off: one starts, the other joins with the code, and they talk
    chat = export_html(os.path.join(HERE, "apps", "LinkChat.vml"), os.path.join(WORK, "chat.html"))
    def open_chat():
        ctx = b.new_context(viewport={"width": 360, "height": 640})
        ctx.add_init_script(f"window.VML_LINK_URL = {json.dumps(relay.url)};")
        pg = ctx.new_page()
        pg.goto("file://" + str(chat))
        pg.wait_for_selector("#vml_status[data-ready='1']", state="attached", timeout=20000)
        return pg
    ann, bob = open_chat(), open_chat()
    ann.click("#v_btnStart")
    shown = ann.input_value("#v_txtCode")
    check("Link Chat: starting shows the code as text and as a QR picture", (shown[:3], len(shown), ann.get_attribute("#v_imgCode", "src")[:22], ann.is_visible("#v_imgCode")), ("VL1", 46, "data:image/png;base64,", True))
    same = ann.evaluate("code => JSON.stringify(window.vml.qrMatrix(code))", shown) == json.dumps([[bool(c) for c in row] for row in __import__("vml.qr", fromlist=["matrix"]).matrix(shown)], separators=(",", ":"))
    check("the QR code a page draws is dot for dot the one the desktop draws", same, True)
    bob.once("dialog", lambda d: d.accept(shown))            # (no camera here that reads codes: it asks for it to be pasted)
    bob.click("#v_btnJoin")
    ann.wait_for_function("document.querySelector('#v_lblState').innerText.startsWith('Linked')", timeout=8000)
    bob.wait_for_function("document.querySelector('#v_lblState').innerText.startsWith('Linked')", timeout=8000)
    check("Link Chat: the other joins with the code, and both say they are linked, the code put away", (ann.inner_text("#v_lblState"), ann.is_visible("#v_imgCode")), ("Linked. Nobody in between can read this.", False))
    ann.fill("#v_txtSay", "tea?"); ann.click("#v_btnSend")
    bob.wait_for_function("document.querySelector('#v_lblLog').innerText.includes('tea?')", timeout=8000)
    bob.fill("#v_txtSay", "two sugars"); bob.click("#v_btnSend")
    ann.wait_for_function("document.querySelector('#v_lblLog').innerText.includes('two sugars')", timeout=8000)
    check("Link Chat: what each says, the other sees", (ann.inner_text("#v_lblLog").split(), bob.inner_text("#v_lblLog").split()), (["You:", "tea?", "Them:", "two", "sugars"], ["Them:", "tea?", "You:", "two", "sugars"]))
    bob.once("dialog", lambda d: d.dismiss())
    carl = open_chat(); carl.once("dialog", lambda d: d.dismiss()); carl.click("#v_btnJoin")
    carl.wait_for_function("document.querySelector('#v_lblState').innerText === 'Nothing was given.'", timeout=5000)
    check("Link Chat: joining with nothing says so, and sending with nobody there says so", (carl.fill("#v_txtSay", "hello?"), carl.click("#v_btnSend"), carl.inner_text("#v_lblState"))[2], "There is nobody on the link yet.")
    b.close()

# ---- the same commands on the desktop, through the engine
from PySide6.QtWidgets import QApplication
from vml.engine import Engine
eng = Engine()
app = QApplication.instance()
got = []
eng.run_script = lambda name, *args, origin=None: got.append((name,) + tuple(args))
def spin(want, secs=8):
    until_ = time.time() + secs
    while len(got) < want and time.time() < until_:
        app.processEvents(); time.sleep(0.02)
    out = list(got); got.clear()
    return out
code = eng.vml("Link", "Got")
far = link.Link(code)
check("desktop: Link gives a code, and the handler is told when the other end joins", (code[:3], eng.vml("LinkCode") == code, spin(1)), ("VL1", True, [("Got", "joined", "")]))
far.send("to the engine")
check("desktop: a message runs the handler", spin(1), [("Got", "message", "to the engine")])
check("desktop: LinkSend reaches the other end", (eng.vml("LinkSend", "from the engine"), events(far, 2)), ("true", [("joined", ""), ("message", "from the engine")]))
eng.vml("LinkClose")
check("desktop: LinkClose tells the other end, and there is no link after", (events(far, 1, 8), eng.vml("LinkCode"), eng.vml("LinkSend", "x")), ([("left", "")], "", ""))
far.close()
relay.close()

# ---- the real relay, where PHP is to hand
if shutil.which("php"):
    import socket
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    env = dict(os.environ, LINK_DB=os.path.join(WORK, "link.db"))
    php = subprocess.Popen(["php", "-S", f"127.0.0.1:{port}", "-t", os.path.join(HERE, "server", "link")], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        url = f"http://127.0.0.1:{port}/link.php"
        for _ in range(50):
            try:
                urllib.request.urlopen(url + "?c=" + "0" * 32).read(); break
            except Exception:
                time.sleep(0.1)
        a = link.Link(relay=url); time.sleep(0.6); z = link.Link(a.code, relay=url)
        check("the real relay: two ends find each other", (events(a, 1), events(z, 1)), ([("joined", "")], [("joined", "")]))
        a.send("through php"); z.send("and back")
        check("the real relay: messages go both ways", (events(z, 1), events(a, 1)), ([("message", "through php")], [("message", "and back")]))
        def ask(query, body=None):
            try:
                with urllib.request.urlopen(urllib.request.Request(url + query, data=body)) as r:
                    return r.status, json.loads(r.read())
            except urllib.error.HTTPError as exc:
                return exc.code, json.loads(exc.read())
        check("the real relay: refuses what isn't a channel, a sender or a message",
              (ask("?c=short")[0], ask("?c=" + "a" * 32, b'{"s":"me","b":"aGk="}')[0], ask("?c=" + "a" * 32, b'{"s":"0123456789abcdef","b":"<b>"}')[0],
               ask("?c=" + "a" * 32, json.dumps({"s": "0123456789abcdef", "b": "A" * 24001}).encode())[0]), (400, 400, 400, 400))
        for i in range(205):
            ask("?c=" + "b" * 32, json.dumps({"s": "0123456789abcdef", "b": "QUJD"}).encode())
        kept = ask("?c=" + "b" * 32 + "&since=0")
        check("the real relay: keeps only the newest 200 of a channel, and slows a flood", (len(kept[1]["m"]) <= 100, kept[1]["m"][0]["q"] > 1 if kept[1]["m"] else True,
              ask("?c=" + "b" * 32, json.dumps({"s": "0123456789abcdef", "b": "QUJD"}).encode())[0]), (True, True, 429))
        import sqlite3
        rows = sqlite3.connect(os.path.join(WORK, "link.db")).execute("select count(*), group_concat(body) from messages where channel = ?", (a.channel,)).fetchone()
        check("the real relay: what it keeps on disk is unreadable", (rows[0] >= 4, "through php" in (rows[1] or "")), (True, False))
        a.close(); z.close()
    finally:
        php.terminate()
else:
    print("      (php isn't installed here, so the real relay was not tried)")

print(f"\n{sum(ok)}/{len(ok)} passed")
sys.exit(0 if all(ok) else 1)
