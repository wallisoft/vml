"""Link, paired by pressing together: two apps with nothing in common yet each press within a few seconds of the
other, are given each other's keys by the relay, and show three words to compare. The real relay
(server/link/link.php with pair.php) is used throughout, so PHP is needed."""
import base64, hashlib, json, os, re, shutil, socket, sqlite3, subprocess, sys, tempfile, threading, time, urllib.error, urllib.request
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("VML_PREFS", os.path.join(tempfile.mkdtemp(prefix="vml-prefs-"), "prefs.json"))
if not shutil.which("php"):
    print("php isn't installed: skipping\n0/0 passed")
    raise SystemExit(0)
try:
    import cryptography  # noqa: F401
    from playwright.sync_api import sync_playwright
except ImportError:
    print("playwright or the cryptography package isn't installed: skipping\n0/0 passed")
    raise SystemExit(0)
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from vml import link
from vml.html import export_html

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = tempfile.mkdtemp(prefix="vml-pair-")
ok = []

def check(label, got, want=True):
    passed = got == want
    ok.append(passed)
    print(f"{'PASS' if passed else 'FAIL'}  {label}" + ("" if passed else f": got {got!r}, wanted {want!r}"))

s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
DB = os.path.join(WORK, "link.db")
php = subprocess.Popen(["php", "-S", f"127.0.0.1:{port}", "-t", os.path.join(HERE, "server", "link")],
                       env=dict(os.environ, LINK_DB=DB, PHP_CLI_SERVER_WORKERS="4"), stdout=subprocess.DEVNULL, stderr=open(os.environ.get("PAIR_PHP_LOG", os.devnull), "w"))
URL = f"http://127.0.0.1:{port}/link.php"
os.environ["VML_LINK_URL"] = URL

def ask(query, body=None):
    try:
        with urllib.request.urlopen(urllib.request.Request(URL + query, data=None if body is None else json.dumps(body).encode())) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())

def one(end, secs=12):
    try:
        return end.events.get(timeout=secs)
    except Exception:
        return None

def settle():
    """Let the five seconds in which presses count as together go by, so the next test starts clean."""
    db_ = sqlite3.connect(DB)
    db_.execute("update pairs set at = at - 60000"); db_.execute("delete from counts where what like 'p:%' or what like 'h:p%'"); db_.commit()

def fresh_address():
    sqlite3.connect(DB).execute("delete from counts").connection.commit()

def key():
    private = ec.generate_private_key(ec.SECP256R1())
    raw = private.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return private, raw, hashlib.sha256(raw).hexdigest(), base64.urlsafe_b64encode(raw).decode().rstrip("=")

try:
    for _ in range(50):
        try:
            urllib.request.urlopen(URL + "?c=" + "0" * 32).read(); break
        except Exception:
            time.sleep(0.1)

    check("there are 256 words, none twice, and the page has the same ones in the same order",
          (len(link.WORDS), len(set(link.WORDS)),
           " ".join(re.search(r'const LINK_WORDS = \((.*?)\)\.split', open(os.path.join(HERE, "vml", "html.py")).read(), re.S).group(1).replace('" +', "").replace('"', "").split()) == " ".join(link.WORDS)),
          (256, 256, True))

    # ---- two desktop ends
    a, b = link.Pairing(), link.Pairing()
    ea, eb = one(a), one(b)
    check("two that press together are each given the same three words", (ea[0], eb[0], ea[1] == eb[1], len(ea[1].split()), all(w in link.WORDS for w in ea[1].split())), ("words", "words", True, 3, True))
    check("and have worked out the same code, which is a link code like any other", (a.code == b.code, a.code[:3], len(a.code)), (True, "VL1", 46))
    la, lb = link.Link(a.code), link.Link(b.code)
    check("the link they open with it joins them", (one(la), one(lb)), (("joined", ""), ("joined", "")))
    la.send("paired without a code"); lb.send("so we are")
    check("and carries messages both ways", (one(lb), one(la)), (("message", "paired without a code"), ("message", "so we are")))
    disk = " ".join(str(r) for t in ("pairs", "messages") for r in sqlite3.connect(DB).execute(f"select * from {t}"))
    check("the relay never held the code, the words or the messages", any(x in disk for x in (a.code, a.code[3:], ea[1], "paired without", "so we are")), False)
    la.close(); lb.close()
    settle()

    # ---- nobody, and a crowd
    t = time.time()
    lone = link.Pairing()
    e = one(lone, 40)
    check("a press nobody answers gives up in about 25 seconds and says so", (e[0], e[1].startswith("Nobody else pressed in time"), 20 < time.time() - t < 34), ("error", True, True))
    settle()
    crowd = [link.Pairing() for _ in range(3)]
    got = [one(c) for c in crowd]
    check("three pressing at once are all told to try again: no guessing who meant whom", [g[0] + ":" + g[1][:17] for g in got], ["error:Someone else was "] * 3)
    settle()

    # a, then b a second later, then c a second after that: b is as near to c as to a
    i1 = ask("?p=go", {"c": "1" * 64})[1]["id"]
    i2 = ask("?p=go", {"c": "2" * 64})[1]["id"]
    db = sqlite3.connect(DB)
    db.execute("update pairs set at = at - 4000 where id = ?", (i1,)); db.commit()
    i3 = ask("?p=go", {"c": "3" * 64})[1]["id"]
    db.execute("update pairs set at = at + 4000 where id = ?", (i3,)); db.commit()
    ask(f"?p=wait&id={i1}"); ask(f"?p=wait&id={i2}")
    check("a chain of three, each within five seconds of the next, pairs nobody", [ask(f"?p=wait&id={i}")[1]["state"] for i in (i1, i2, i3)], ["busy", "busy", "busy"])
    settle()
    i1 = ask("?p=go", {"c": "1" * 64})[1]["id"]
    db.execute("update pairs set at = at - 6000 where id = ?", (i1,)); db.commit()
    i2 = ask("?p=go", {"c": "2" * 64})[1]["id"]
    check("two presses six seconds apart are not together", [ask(f"?p=wait&id={i}")[1]["state"] for i in (i1, i2)], ["waiting", "waiting"])
    settle()

    # ---- what the relay will and won't do
    settle()
    p1, r1, c1, k1 = key(); p2, r2, c2, k2 = key()
    i1 = ask("?p=go", {"c": c1})[1]["id"]
    check("a key can't be handed over before there is a pairing", ask(f"?p=key&id={i1}", {"k": k1}), (409, {"ok": False, "error": "not paired yet"}))
    i2 = ask("?p=go", {"c": c2})[1]["id"]
    check("two are not paired the instant the second presses: a moment is left for a third to be seen", (ask(f"?p=wait&id={i1}")[1], ask(f"?p=wait&id={i2}")[1]), ({"ok": True, "state": "waiting"}, {"ok": True, "state": "waiting"}))
    time.sleep(1.6)
    check("each is told of the other's promise, and no key yet", (ask(f"?p=wait&id={i1}")[1], ask(f"?p=wait&id={i2}")[1]),
          ({"ok": True, "state": "paired", "c": c2, "k": ""}, {"ok": True, "state": "paired", "c": c1, "k": ""}))
    check("a key that isn't the one promised is refused", ask(f"?p=key&id={i1}", {"k": k2})[0], 400)
    check("the right key is taken, and then the other is given it", (ask(f"?p=key&id={i1}", {"k": k1})[0], ask(f"?p=wait&id={i2}")[1]["k"]), (200, k1))
    check("what isn't a pairing, a promise or a key is refused",
          (ask("?p=wait&id=nonsense")[0], ask("?p=wait&id=" + "0" * 32)[0], ask("?p=go", {"c": "short"})[0], ask(f"?p=key&id={i2}", {"k": "<b>"})[0], ask("?p=dance")[0]),
          (400, 404, 400, 400, 400))
    ids = [ask("?p=go", {"c": "4" * 64})[1].get("id", "") for _ in range(4)]
    check("a pairing's name is 32 random hex digits: nothing to count through", (all(re.fullmatch("[0-9a-f]{32}", i) for i in ids), len(set(ids))), (True, 4))
    settle(); fresh_address()
    codes = [ask("?p=go", {"c": "5" * 64})[0] for _ in range(14)]
    check("twelve presses a minute from one address, then a wait", (codes[:12], codes[12:]), ([200] * 12, [429, 429]))
    settle(); fresh_address()
    db.execute("update pairs set at = at - 200000"); db.commit()
    ask("?p=go", {"c": "6" * 64})
    check("pairings are forgotten after two minutes", db.execute("select count(*) from pairs").fetchone()[0], 1)
    settle()
    check("the relay still carries links as before", ask("?c=" + "a" * 32 + "&since=0"), (200, {"ok": True, "seq": 0, "m": []}))

    # ---- a relay that swaps the keys: it pairs with each side itself, to sit in the middle
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    class Middle(BaseHTTPRequestHandler):
        """Tells every app it is paired, with a key of its own in place of the other app's."""
        mine = key()
        def log_message(self, *a): pass
        def do_GET(self): self.reply({"ok": True, "state": "paired", "c": self.mine[2], "k": self.mine[3] if "shown" in self.path else ""})
        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", "0")))
            self.reply({"ok": True, "id": os.urandom(16).hex()})
        def reply(self, what):
            data = json.dumps(what).encode()
            self.send_response(200); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)
    class Shows(Middle):
        def do_GET(self): self.reply({"ok": True, "state": "paired", "c": self.mine[2], "k": self.mine[3]})
    class Lies(Middle):
        def do_GET(self): self.reply({"ok": True, "state": "paired", "c": self.mine[2], "k": key()[3]})
    def serve(handler):
        srv = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        return srv, f"http://127.0.0.1:{srv.server_port}/"
    srv, url = serve(Shows)
    x, y = link.Pairing(relay=url), link.Pairing(relay=url)
    ex, ey = one(x), one(y)
    check("with a relay in the middle swapping keys, the two apps show different words", (ex[0], ey[0], ex[1] != ey[1], x.code != y.code), ("words", "words", True, True))
    srv.shutdown()
    srv, url = serve(Lies)
    z = link.Pairing(relay=url)
    check("a key that doesn't match what was promised stops the pairing", one(z), ("error", "The pairing was interfered with. Don't go on."))
    srv.shutdown()

    # ---- a page and a desktop app, and the engine's commands
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
LUA
""")
    page = export_html(os.path.join(WORK, "talk.vml"), os.path.join(WORK, "talk.html"))
    chat = export_html(os.path.join(HERE, "apps", "LinkChat.vml"), os.path.join(WORK, "chat.html"))
    with sync_playwright() as p:
        br = p.chromium.launch()
        def open_page(path, **more):
            ctx = br.new_context(**more)
            ctx.add_init_script(f"window.VML_LINK_URL = {json.dumps(URL)};")
            pg = ctx.new_page()
            pg.goto("file://" + str(path))
            pg.wait_for_selector("#vml_status[data-ready='1']", state="attached", timeout=20000)
            return pg
        V = lambda pg, *a: pg.evaluate("a => window.vml.Vml(...a)", list(a))
        def until(pg, text, secs=12):
            try:
                pg.wait_for_function("t => document.querySelector('#v_lblGot').innerText.includes(t)", arg=text, timeout=secs * 1000)
            except Exception:
                pass
            return pg.inner_text("#v_lblGot")

        pg = open_page(page)
        check("a page: LinkPair starts, and there is no link or code until it is accepted", (V(pg, "LinkPair", "Got"), V(pg, "LinkCode"), V(pg, "LinkSend", "x"), V(pg, "LinkAccept")), ("true", "", "", ""))
        desk = link.Pairing()
        ed = one(desk)
        heard = until(pg, "words:")
        check("a page and a desktop app that press together show the same three words", (ed[0], heard), ("words", f"words:{ed[1]}|"))
        code = V(pg, "LinkAccept")
        far = link.Link(desk.code)
        check("accepted, the page's link has the code the desktop worked out, and they join", (code == desk.code, one(far), "joined:|" in until(pg, "joined:|")), (True, ("joined", ""), True))
        far.send("over the paired link")
        check("and talk", until(pg, "over the paired link").endswith("message:over the paired link|"), True)
        far.close(); V(pg, "LinkClose")
        settle()

        solo = open_page(page)
        V(solo, "LinkPair", "Got"); V(solo, "LinkClose")
        solo.wait_for_timeout(1500)
        check("a page: closing while it looks stops it, and nothing more is said", solo.inner_text("#v_lblGot"), "")
        settle()

        # Link Chat: both press Press together, both say the words are the same
        asked = []
        def yes(d): asked.append(d.message); d.accept()
        ann, bob = open_page(chat, viewport={"width": 360, "height": 640}), open_page(chat, viewport={"width": 360, "height": 640})
        ann.on("dialog", yes); bob.on("dialog", yes)
        ann.click("#v_btnPair"); bob.click("#v_btnPair")
        for who in (ann, bob):
            who.wait_for_function("document.querySelector('#v_lblState').innerText.startsWith('Linked')", timeout=15000)
        words = [re.search(r"words\?\s+(\w+ \w+ \w+)\s", m).group(1) for m in asked]
        check("Link Chat: Press together on both asks each the same three words, and yes on both links them", (len(words), words[0] == words[-1], ann.inner_text("#v_lblState")), (2, True, "Linked. Nobody in between can read this."))
        ann.fill("#v_txtSay", "no code needed"); ann.click("#v_btnSend")
        bob.wait_for_function("document.querySelector('#v_lblLog').innerText.includes('no code needed')", timeout=8000)
        check("Link Chat: and they talk", bob.inner_text("#v_lblLog").strip(), "Them: no code needed")
        box = lambda pg, sel: pg.eval_on_selector(sel, "e => { const r = e.getBoundingClientRect(); return [Math.round(r.top), Math.round(r.bottom)]; }")
        check("Link Chat: the three buttons, the state and the conversation don't overlap",
              box(ann, "#v_btnStart")[1] <= box(ann, "#v_btnPair")[0] and box(ann, "#v_btnPair")[1] <= box(ann, "#v_lblState")[0] and box(ann, "#v_lblState")[1] <= box(ann, "#v_lblLog")[0] and box(ann, "#v_lblLog")[1] <= box(ann, "#v_txtSay")[0], True)
        settle()
        cat, dan = open_page(chat), open_page(chat)
        cat.on("dialog", lambda d: d.dismiss()); dan.on("dialog", lambda d: d.accept())
        cat.click("#v_btnPair"); dan.click("#v_btnPair")
        cat.wait_for_function("document.querySelector('#v_lblState').innerText.startsWith('Not linked')", timeout=15000)
        dan.wait_for_timeout(2500)
        check("Link Chat: if one says the words differ, there is no link", (cat.inner_text("#v_lblState"), dan.inner_text("#v_lblState").startswith("Linked")), ("Not linked. Press together again.", False))
        br.close()
    settle()

    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication
    from vml.engine import Engine
    eng = Engine()
    app = QApplication.instance()
    got = []
    eng.run_script = lambda name, *args, origin=None: got.append((name,) + tuple(args))
    def spin(want, secs=12):
        end = time.time() + secs
        while len(got) < want and time.time() < end:
            app.processEvents(); time.sleep(0.02)
        out = list(got); got.clear()
        return out
    check("desktop: LinkPair starts; no code, nothing to accept and nothing sent until the words are in", (eng.vml("LinkPair", "Got"), eng.vml("LinkCode"), eng.vml("LinkAccept")), ("true", "", ""))
    far = link.Pairing()
    ef = one(far)
    check("desktop: the handler is given the three words the other end has", spin(1), [("Got", "words", ef[1])])
    code = eng.vml("LinkAccept")
    peer = link.Link(far.code)
    check("desktop: LinkAccept opens the link with the agreed code, and the two join", (code == far.code, eng.vml("LinkCode") == code, spin(1), one(peer)), (True, True, [("Got", "joined", "")], ("joined", "")))
    peer.send("to the engine")
    check("desktop: and talk", (spin(1), eng.vml("LinkSend", "and back"), one(peer)), ([("Got", "message", "to the engine")], "true", ("message", "and back")))
    eng.vml("LinkClose"); peer.close()

    # an idle link asks less and less often
    quiet = link.Link()
    asks = lambda: sqlite3.connect(DB).execute("select coalesce(sum(n), 0) from counts where what like 'a:%'").fetchone()[0]
    time.sleep(1.0)
    quiet.active = time.time() - 7200
    time.sleep(2.0); n = asks(); time.sleep(4.0)
    check("a link nobody has used for an hour hardly troubles the relay", asks() - n <= 1, True)
    quiet.close()

    # a wrapped label's words start at the top of its box on the desktop, as they do on a page
    eng2 = Engine()
    eng2.load(os.path.join(HERE, "apps", "LinkChat.vml"))
    w = next((n.widget for n in eng2.nodes.values() if getattr(n, "name", "") == "lblLog"), None)
    check("desktop: a conversation starts at the top of its box, not half way down", bool(w is not None and w.alignment() & Qt.AlignTop), True)
finally:
    php.terminate()

print(f"\n{sum(ok)}/{len(ok)} passed")
sys.exit(0 if all(ok) else 1)
