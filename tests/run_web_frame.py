"""A form as a web page on a screen with plenty of room: shown as a window in the middle, at the size it was
drawn, with an edge. On a phone (and on a screen not much bigger than the form) nothing changes."""
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

WORK = tempfile.mkdtemp(prefix="vml-frame-")
ok = []

def check(label, got, want=True):
    passed = got == want
    ok.append(passed)
    print(f"{'PASS' if passed else 'FAIL'}  {label}" + ("" if passed else f": got {got!r}, wanted {want!r}"))

FORM = """@Window App
Title=App
Width=360
Height=640
%s
@Canvas c
Parent=App
Background=#FFF7ED

@Button btnFoot
Parent=c
Canvas.Left=12
Canvas.Top=586
Width=336
Height=42
Content=At the foot
Anchor=Left,Right,Bottom
"""
def page(name, extra=""):
    path = os.path.join(WORK, name + ".vml")
    open(path, "w").write(FORM % extra)
    return export_html(path, os.path.join(WORK, name + ".html"))
plain, fill = page("plain"), page("fill", "WebFit=Fill\n")

with sync_playwright() as p:
    b = p.chromium.launch()
    def look(path, w, h):
        pg = b.new_page(viewport={"width": w, "height": h})
        pg.goto("file://" + str(path))
        pg.wait_for_selector("#vml_status[data-ready='1']", state="attached", timeout=20000)
        box = lambda sel: [round(v) for v in pg.eval_on_selector(sel, "e => { const r = e.getBoundingClientRect(); return [r.left, r.top, r.width, r.height]; }")]
        return pg, box
    pg, box = look(plain, 1280, 900)
    check("in a computer's browser a phone-sized form is a window in the middle, at the size it was drawn", (box("#vml_window"), pg.evaluate("document.body.classList.contains('framed')")), ([460, 130, 360, 640], True))
    style = pg.eval_on_selector("#vml_window", "e => { const s = getComputedStyle(e); return [s.borderRadius, s.boxShadow.includes('0px 0px 0px 1px'), s.boxShadow.split('rgb').length > 2]; }")
    check("with an edge, rounded corners and a shadow, on a quiet page", (style, pg.evaluate("getComputedStyle(document.body).backgroundColor")), (["10px", True, True], "rgb(233, 236, 241)"))
    foot = box("#v_btnFoot"); win = box("#vml_window")
    check("what is anchored to its foot is at the window's foot, not the page's", (foot[0] - win[0], win[1] + win[3] - (foot[1] + foot[3]), foot[2]), (12, 12, 336))
    def size(w, h):
        pg.set_viewport_size({"width": w, "height": h})
        pg.wait_for_timeout(200)
    size(1280, 500)
    check("in a browser shorter than the form the window is as tall as fits, and the foot still shows", (box("#vml_window"), box("#v_btnFoot")[1] + 42 <= 500 - 16), ([460, 16, 360, 468], True))
    size(412, 915)
    check("on a phone a little wider than the form nothing changes: it fills the screen, as before", (box("#vml_window"), pg.evaluate("document.body.classList.contains('framed')")), ([0, 0, 412, 915], False))
    size(320, 640)
    check("and on a narrower one it is still scaled to fit", (pg.evaluate("document.body.classList.contains('phone')"), pg.evaluate("document.body.classList.contains('framed')"), box("#vml_window")[2]), (True, False, 320))
    size(1280, 900)
    check("turned back, it is a window again", box("#vml_window"), [460, 130, 360, 640])
    pg.screenshot(path=os.environ.get("VML_FRAME_SHOT") or os.path.join(WORK, "framed.png"))
    pg2, box2 = look(fill, 1280, 900)
    check("WebFit=Fill on the Window fills the page instead", (box2("#vml_window"), pg2.evaluate("document.body.classList.contains('framed')")), ([0, 0, 1280, 900], False))
    b.close()

print(f"\n{sum(ok)}/{len(ok)} passed")
sys.exit(0 if all(ok) else 1)
