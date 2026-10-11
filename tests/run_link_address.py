"""Link, joined by pointing any phone's camera at a code: the picture holds an address that opens the app with
the link's code after the #. The site's open page hands the code to the phone app beside the address, so it is
never sent to a web server."""
import json, os, re, sys, tempfile, time
from urllib.parse import unquote
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["VML_PREFS"] = os.path.join(tempfile.mkdtemp(prefix="vml-prefs-"), "prefs.json")
try:
    import cryptography  # noqa: F401
    from playwright.sync_api import sync_playwright
except ImportError:
    print("playwright or the cryptography package isn't installed: skipping\n0/0 passed")
    raise SystemExit(0)
from link_relay import Relay
from vml import link
from vml.html import export_html

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OPEN = os.environ.get("VML_OPEN_PAGE") or next((p for p in (os.path.join(HERE, "server", "site", "open.html"),) if os.path.exists(p)), "")
WORK = tempfile.mkdtemp(prefix="vml-addr-")
ok = []

def check(label, got, want=True):
    passed = got == want
    ok.append(passed)
    print(f"{'PASS' if passed else 'FAIL'}  {label}" + ("" if passed else f": got {got!r}, wanted {want!r}"))

def one(end, secs=8):
    try:
        return end.events.get(timeout=secs)
    except Exception:
        return None

relay = Relay()
os.environ["VML_LINK_URL"] = relay.url
CODE = link.new_code()
APP = "https://visualised.io/apps/linkchat.html"
ADDR = link.address(CODE, APP)

check("an address for a link opens the site's open page, with the app and the code after the #",
      (ADDR.split("#")[0], unquote(ADDR.split("#", 1)[1]), len(ADDR) <= 213), ("https://visualised.io/open.html", f"{APP}#{CODE}", True))
check("an app that isn't on the web has no address to give: the code itself", (link.address(CODE), link.address(CODE, "http://192.168.1.5:8000/")), (CODE, CODE))
check("a code is found in an address, in the middle of words, or alone; other text is left as it came",
      (link.code_in(ADDR), link.code_in(f"join me: {APP}#{CODE} now"), link.code_in(" " + CODE + " "), link.code_in("hello"), link.code_in(CODE + "x")), (CODE, CODE, CODE, "hello", CODE + "x"))
a = link.Link(CODE); time.sleep(0.4); z = link.Link(ADDR)
check("an end given the address joins the link the code names", (z.code, one(a), one(z)), (CODE, ("joined", ""), ("joined", "")))
a.close(); z.close()

chat = export_html(os.path.join(HERE, "apps", "LinkChat.vml"), os.path.join(WORK, "chat.html"))
with sync_playwright() as p:
    br = p.chromium.launch()
    def open_page(path, tail="", **more):
        ctx = br.new_context(**more)
        ctx.add_init_script(f"window.VML_LINK_URL = {json.dumps(relay.url)};")
        pg = ctx.new_page()
        pg.goto("file://" + str(path) + tail)
        return pg
    def ready(pg):
        pg.wait_for_selector("#vml_status[data-ready='1']", state="attached", timeout=20000)
        return pg
    V = lambda pg, *a: pg.evaluate("a => window.vml.Vml(...a)", list(a))

    ann = ready(open_page(chat, viewport={"width": 360, "height": 640}))
    ann.click("#v_btnStart")
    code = ann.input_value("#v_txtCode")
    addr = V(ann, "LinkAddress")
    check("Link Chat: the picture it shows holds an address that opens Link Chat with the link's code",
          (unquote(addr.split("#", 1)[1]), V(ann, "LinkAddress", code) == addr, ann.get_attribute("#v_imgCode", "src") == V(ann, "QrCode", addr, "4")), (f"{APP}#{code}", True, True))
    box = ann.eval_on_selector("#v_imgCode", "e => { const r = e.getBoundingClientRect(); return [Math.round(r.width), Math.round(r.height)]; }")
    check("and the picture still fits its place", box, [220, 220])
    check("an app not opened from such an address has no invitation", V(ann, "LinkInvite"), "")

    bob = ready(open_page(chat, "#" + code, viewport={"width": 360, "height": 640}))
    for who in (ann, bob):
        who.wait_for_function("document.querySelector('#v_lblState').innerText.startsWith('Linked')", timeout=10000)
    check("Link Chat opened with a code after the # joins by itself, and the code is taken out of the address bar",
          (bob.inner_text("#v_lblState"), "#" in bob.url, V(bob, "LinkInvite")), ("Linked. Nobody in between can read this.", False, ""))
    bob.fill("#v_txtSay", "the camera brought me"); bob.click("#v_btnSend")
    ann.wait_for_function("document.querySelector('#v_lblLog').innerText.includes('camera')", timeout=8000)
    check("and they talk", ann.inner_text("#v_lblLog").strip(), "Them: the camera brought me")

    cat = ready(open_page(chat, viewport={"width": 360, "height": 640}))
    cat.once("dialog", lambda d: d.accept(addr))             # the app's own scanner reads the same picture
    cat.click("#v_btnJoin")
    cat.wait_for_function("document.querySelector('#v_lblState').innerText.startsWith('Linked')", timeout=10000)
    check("Link Chat: Join one, given the address its own scanner would read, joins too", cat.inner_text("#v_lblState")[:6], "Linked")
    check("the relay was never given the code, in an address or out of one", code in json.dumps(relay.messages), False)

    if OPEN:
        ask = lambda pg: pg.evaluate("""() => ({ shown: !document.getElementById('shared').hidden, nothing: !document.getElementById('nothing').hidden,
            title: document.querySelector('#shared h1').textContent, address: document.getElementById('address').textContent,
            open: document.getElementById('open').getAttribute('href'), browser: document.getElementById('browser1').getAttribute('href') })""")
        phone = "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Mobile Safari/537.36"
        got = ask(open_page(OPEN, "#" + addr.split("#", 1)[1], user_agent=phone))
        intent = got["open"]
        check("the open page, on a phone: the button opens Visualised with the app's address, and the code beside it, not in it",
              (got["shown"], intent.startswith("intent://visualised.io/apps/linkchat.html#Intent;scheme=visualised;package=io.visualised.app;S.link=" + code + ";S.browser_fallback_url="),
               code in intent.split("#Intent")[0]), (True, True, False))
        check("it says what is happening, shows where the app is from without the code, and the browser link keeps the code",
              (got["title"], got["address"], got["browser"]), ("Someone is inviting you to link", APP, f"{APP}#{code}"))
        plain = ask(open_page(OPEN, "#" + APP, user_agent=phone))
        check("an app shared without a link is offered as before", (plain["title"], "S.link=" in plain["open"]), ("Someone has shared an app with you", False))
        sly = ask(open_page(OPEN, "#" + APP + "%23VL1" + "A" * 43 + ";S.evil=1", user_agent=phone))
        check("what follows the # must be exactly a link code, or it is left out of what is handed to the app", ("S.link" in sly["open"], "evil" in sly["open"].split("S.browser_fallback_url")[0]), (False, False))
    else:
        print("      (the site's open page isn't to hand: set VML_OPEN_PAGE to its file to try it)")
    br.close()

from PySide6.QtWidgets import QApplication
from vml.engine import Engine
eng = Engine(); eng.load(os.path.join(HERE, "apps", "LinkChat.vml"))
code = eng.vml("Link", "Got")
check("desktop: LinkAddress gives the same address for Link Chat's link, and a QR code can hold it",
      (unquote(eng.vml("LinkAddress").split("#", 1)[1]), eng.vml("QrCode", eng.vml("LinkAddress"), "4")[:22], eng.vml("LinkInvite")), (f"{APP}#{code}", "data:image/png;base64,", ""))
eng.vml("LinkClose")
check("desktop: with no link open there is no address", eng.vml("LinkAddress"), "")
relay.close()

print(f"\n{sum(ok)}/{len(ok)} passed")
sys.exit(0 if all(ok) else 1)
