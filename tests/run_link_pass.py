"""Link, and who the relay carries it for: free to the people who use an app, part of Pro for whoever makes one.
A Pro licence gets a pass from the relay; Visualised puts it into the apps its holder saves and exports; a link
that shows one is carried in full, and one that doesn't is on the free allowance. The real relay is used, so PHP
is needed."""
import base64, hashlib, hmac, json, os, re, shutil, socket, sqlite3, subprocess, sys, tempfile, time, urllib.error, urllib.request
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
WORK = tempfile.mkdtemp(prefix="vml-pass-")
os.environ["VML_PREFS"] = os.path.join(WORK, "prefs.json")
if not shutil.which("php"):
    print("php isn't installed: skipping\n0/0 passed")
    raise SystemExit(0)
try:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from playwright.sync_api import sync_playwright
except ImportError:
    print("playwright or the cryptography package isn't installed: skipping\n0/0 passed")
    raise SystemExit(0)
from vml import licence as L, link
from vml.html import export_html

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ok = []

def check(label, got, want=True):
    passed = got == want
    ok.append(passed)
    print(f"{'PASS' if passed else 'FAIL'}  {label}" + ("" if passed else f": got {got!r}, wanted {want!r}"))

# a signing key of our own stands in for tiny-web.uk's, here and in the relay
sk = Ed25519PrivateKey.generate()
L.PUBLIC_KEY = sk.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()
b64 = lambda b: base64.urlsafe_b64encode(b).decode().rstrip("=")
make = lambda payload: "VSL1-" + b64(payload.encode()) + "." + b64(sk.sign(payload.encode()))
PRO, ENT, OLD = make("pro|1|V1A2B3|20261008||steve@example.com"), make("enterprise|25|E9|20261008|20991231|Acme Ltd"), make("pro|1|X1|20240101|20241231|old@example.com")
other = Ed25519PrivateKey.generate()
FORGED = "VSL1-" + b64(b"pro|1|V1A2B3|20261008||steve@example.com") + "." + b64(other.sign(b"pro|1|V1A2B3|20261008||steve@example.com"))

s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
DB = os.path.join(WORK, "link.db")
php = subprocess.Popen(["php", "-S", f"127.0.0.1:{port}", "-t", os.path.join(HERE, "server", "link")],
                       env=dict(os.environ, LINK_DB=DB, LINK_LICENCE_PUBLIC=L.PUBLIC_KEY, PHP_CLI_SERVER_WORKERS="4"),
                       stdout=subprocess.DEVNULL, stderr=open(os.environ.get("PAIR_PHP_LOG", os.devnull), "w"))
URL = f"http://127.0.0.1:{port}/link.php"
os.environ["VML_LINK_URL"] = URL
sql = lambda q, *a: (lambda c: (c.execute(q, a).fetchall(), c.commit(), c.close())[0])(sqlite3.connect(DB))

def ask(query, body=None):
    try:
        with urllib.request.urlopen(urllib.request.Request(URL + query, data=None if body is None else json.dumps(body).encode())) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())

def flood(channel, n, carry=""):
    """Send n messages into a channel, a minute's worth at a time so only the allowance is met. The codes that came back."""
    out = []
    for i in range(n):
        if i and i % 100 == 0:
            sql("delete from counts where what like 'c:%' or what like 'a:%'")
        out.append(ask(f"?c={channel}" + (f"&v={carry}" if carry else ""), {"s": "0123456789abcdef", "b": "QUJD"})[0])
    sql("delete from counts where what like 'c:%' or what like 'a:%'")
    return out

def one(end, secs=8):
    try:
        return end.events.get(timeout=secs)
    except Exception:
        return None

try:
    for _ in range(50):
        try:
            urllib.request.urlopen(URL + "?c=" + "0" * 32).read(); break
        except Exception:
            time.sleep(0.1)

    # ---- a pass for a licence
    code, got = ask("?pass", {"key": PRO})
    PASS = got.get("pass", "")
    check("a Pro licence is given a pass, which names the licence and not its holder", (code, bool(re.fullmatch(r"VP1-V1A2B3-0\.[A-Za-z0-9_-]{22}", PASS)), "steve" in PASS), (200, True, False))
    check("the same licence is given the same pass each time; another licence a different one, with its last day",
          (ask("?pass", {"key": PRO})[1]["pass"] == PASS, ask("?pass", {"key": ENT})[1]["pass"][:16]), (True, "VP1-E9-20991231."))
    check("no pass for a licence that has run out, one signed by somebody else, or nonsense",
          [ask("?pass", {"key": k})[0] for k in (OLD, FORGED, "VSL1-abc.def", "", PRO[:-4] + "AAAA")], [403] * 5)
    check("the licence key is not kept by the relay", any(PRO in str(r) or PRO[5:40] in str(r) for t in ("counts", "used", "carried", "revoked", "messages") for r in sql(f"select * from {t}")), False)
    check("the relay's own secret is beside its database, for it alone to read", (os.path.getsize(os.path.join(WORK, "pass.secret")), oct(os.stat(os.path.join(WORK, "pass.secret")).st_mode & 0o777)), (32, "0o600"))
    check("asking for a pass is GET-proof and counted", (ask("?pass")[0], [ask("?pass", {"key": "x"})[0] for _ in range(22)][-2:]), (405, [429, 429]))
    sql("delete from counts")

    # ---- the free allowance, and a link that is carried
    free = flood("f" * 32, 102)
    check("with no pass, a link takes 100 messages in an hour and then says why not", (free[:100] == [200] * 100, free[100:]), (True, [402, 402]))
    said = ask("?c=" + "f" * 32, {"s": "0123456789abcdef", "b": "QUJD"})[1]["error"]
    check("in words that name the allowance and what lifts it", ("free allowance of 100 messages an hour" in said, "Visualised Pro" in said), (True, True))
    check("reading is not stopped: what was sent can still be collected", ask("?c=" + "f" * 32 + "&since=0")[0], 200)
    paid = flood("e" * 32, 230, PASS)
    check("with its maker's pass, a link is not held to the allowance", paid.count(200), 230)
    mixed = [ask("?c=" + "d" * 32 + f"&v={PASS}", {"s": "0123456789abcdef", "b": "QUJD"})[0]] + flood("d" * 32, 120)
    check("once either end has shown a pass, the other end is carried too", mixed.count(200), 121)
    check("what a pass's links have carried is counted, a day at a time, whichever end sent it", sql("select id, n from used"), [("V1A2B3", 351)])
    bad = PASS[:-3] + ("AAA" if not PASS.endswith("AAA") else "BBB")
    forged = flood("c" * 32, 102, bad)
    check("a pass with a made-up seal is no pass: the link is on the free allowance", (forged[:100] == [200] * 100, forged[100:]), (True, [402, 402]))
    secret = open(os.path.join(WORK, "pass.secret"), "rb").read()
    seal = lambda i, u: b64(hmac.new(secret, f"pass|{i}|{u}".encode(), hashlib.sha256).digest()[:16])
    stale = flood("b" * 32, 102, f"VP1-V1A2B3-20250101.{seal('V1A2B3', '20250101')}")
    check("a pass whose licence has since run out stops carrying", stale[100:], [402, 402])

    # an hour for a free link's messages, a day for a carried one
    sql("update messages set at = at - 7200 where channel in (?, ?)", "f" * 32, "e" * 32)
    sql("update carried set at = at - 7200")
    check("a free link's messages are kept an hour, a carried link's a day", (len(ask("?c=" + "f" * 32 + "&since=0")[1]["m"]), len(ask("?c=" + "e" * 32 + "&since=0")[1]["m"]) > 0), (0, True))

    sql("insert into revoked values ('V1A2B3')")
    gone = flood("a" * 32, 102, PASS)
    check("a pass that has been turned off stops carrying, and its licence is given no new one", (gone[100:], ask("?pass", {"key": PRO})[0]), ([402, 402], 403))
    sql("delete from revoked"); sql("delete from counts")

    # ---- two real ends
    a = link.Link(carry=PASS); time.sleep(0.5); z = link.Link(a.code)
    check("two ends of a carried link find each other and talk as before", (one(a), one(z)), (("joined", ""), ("joined", "")))
    a.send("carried"); z.send("in full")
    check("messages go both ways", (one(z), one(a)), (("message", "carried"), ("message", "in full")))
    check("and the relay knows whose link it is, not what it says", sql("select id from carried where channel = ?", a.channel), [("V1A2B3",)])
    a.close(); z.close()

    # ---- Visualised, with and without a licence
    check("Community has no pass, and asks the relay for nothing", (L.link_pass(), sql("select count(*) from counts where what like 'h:k%'")), ("", [(0,)]))
    L.save_prefs({"licence_key": PRO})
    check("with a Pro licence, Visualised fetches its pass once and remembers it", (L.link_pass(fetch=False), L.link_pass() == PASS, L.link_pass(fetch=False) == PASS, sql("select n from counts where what like 'h:k%'")), ("", True, True, [(1,)]))
    L.save_prefs({"licence_key": ENT, "link_pass": PASS})
    check("a pass remembered for a different licence is not used", L.link_pass(fetch=False), "")
    L.save_prefs({"licence_key": PRO, "link_pass": PASS})

    form = """@Window Talk
Title=Talk
Width=320
Height=240
%s
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
%s"""
    start = """
@Script Begin
Interpreter=lua
<<LUA
Vml("Link", "Got")
LUA
"""
    def page_data(name, text):
        path = os.path.join(WORK, name + ".vml")
        open(path, "w").write(text)
        out = export_html(path, os.path.join(WORK, name + ".html"))
        return out, json.loads(re.search(r"const VML = (\{.*?\});\n", open(out).read(), re.S).group(1))
    check("a Pro user's exported page that uses Link goes out with their pass", page_data("uses", form % ("", start))[1]["linkPass"], PASS)
    check("one that doesn't use Link carries nothing", page_data("plain", form % ("", ""))[1]["linkPass"], "")
    stamped_page, data = page_data("stamped", form % ("LinkPass=VP1-SOMEONE-0.aaaaaaaaaaaaaaaaaaaaaa\n", start))
    check("a form already carrying its maker's pass keeps that one", data["linkPass"], "VP1-SOMEONE-0.aaaaaaaaaaaaaaaaaaaaaa")
    L.save_prefs({})
    check("a Community user's exported page carries none", page_data("free", form % ("", start))[1]["linkPass"], "")
    L.save_prefs({"licence_key": PRO, "link_pass": PASS})
    carried_page = page_data("carried", form % ("", start))[0]
    L.save_prefs({})

    with sync_playwright() as p:
        br = p.chromium.launch()
        ctx = br.new_context()
        ctx.add_init_script(f"window.VML_LINK_URL = {json.dumps(URL)};")
        pg = ctx.new_page()
        pg.goto("file://" + str(carried_page))
        pg.wait_for_selector("#vml_status[data-ready='1']", state="attached", timeout=20000)
        code = pg.evaluate("() => window.vml.Vml('Link', 'Got')")
        far = link.Link(code)
        check("a page made by a Pro user: its link is carried, on a computer with no licence at all", (one(far), sql("select id from carried where channel = ?", far.channel)), (("joined", ""), [("V1A2B3",)]))
        far.close()
        br.close()

    # ---- the desktop engine, and the designer saving a form
    from PySide6.QtWidgets import QApplication
    from vml.engine import Engine
    def run_form(text):
        path = os.path.join(WORK, "desk.vml")
        open(path, "w").write(text)
        eng = Engine(); eng.load(path)
        code = eng.vml("Link", "Got")
        far = link.Link(code); got = one(far); who = sql("select id from carried where channel = ?", far.channel)
        eng.vml("LinkClose"); far.close()
        return got, who
    check("desktop, no licence, a form with no pass: the link works, on the free allowance", run_form(form % ("", start)), (("joined", ""), []))
    check("desktop, no licence, a form carrying its maker's pass: carried", run_form(form % (f"LinkPass={PASS}\n", start)), (("joined", ""), [("V1A2B3",)]))
    L.save_prefs({"licence_key": PRO, "link_pass": PASS})
    check("desktop, a Pro user running a form they are still making: carried", run_form(form % ("", start)), (("joined", ""), [("V1A2B3",)]))

    def settle():
        for _ in range(4):
            QApplication.instance().processEvents()
    def designed(text):
        src, out = os.path.join(WORK, "in.vml"), os.path.join(WORK, "out.vml")
        open(src, "w").write(text)
        eng = Engine(); eng.load(os.path.join(HERE, "designer", "designer.vml")); settle()
        eng.cmd_ImportVml(src, "Surface"); settle()
        eng.cmd_ExportVml("Surface", out)
        return [l for l in open(out).read().split("\n") if l.startswith("LinkPass=")]
    uses = form % ("", start.replace("@Script Begin", "@Button go\nParent=c\nCanvas.Left=8\nCanvas.Top=210\nWidth=80\nHeight=24\nContent=Go\nOnClick=Begin\n\n@Script Begin"))
    check("the designer, with a Pro licence, saves a form that uses Link with the pass in it", designed(uses), [f"LinkPass={PASS}"])
    check("and a form that doesn't use Link without", designed(form % ("", "")), [])
    L.save_prefs({})
    check("the designer with no licence saves no pass, and drops one that came with the form", designed(uses.replace("Height=240\n", f"Height=240\nLinkPass={PASS}\n", 1)), [])
finally:
    php.terminate()

print(f"\n{sum(ok)}/{len(ok)} passed")
sys.exit(0 if all(ok) else 1)
