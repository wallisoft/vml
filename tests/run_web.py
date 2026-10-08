"""The HTML renderer, in a real (headless) browser: layout, anchors on resize, Lua scripts, menus, events."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("VML_PREFS", os.path.join(__import__("tempfile").mkdtemp(prefix="vml-prefs-"), "prefs.json"))   # never the real settings
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("playwright isn't installed (pip install playwright; python3 -m playwright install chromium): skipping\n0/0 passed")
    raise SystemExit(0)
from vml.html import export_html

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ok = []

def check(label, got, want):
    passed = got == want
    ok.append(passed)
    print(f"{'PASS' if passed else 'FAIL'}  {label}: {got!r}" + ("" if passed else f" (wanted {want!r})"))

page_path = export_html(os.path.join(HERE, "tests", "web", "demo.vml"))
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 640, "height": 420})
    logs, dialogs = [], []
    pg.on("console", lambda m: logs.append(m.text))
    pg.on("dialog", lambda d: (dialogs.append(d.message), d.accept()))
    pg.goto("file://" + os.path.abspath(page_path))
    pg.wait_for_selector("#vml_status[data-ready='1']", state="attached", timeout=20000)
    box = lambda sel: pg.eval_on_selector(sel, "e => { const r = e.getBoundingClientRect(); return [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)]; }")
    text = lambda sel: pg.inner_text(sel)

    check("title from the form", pg.title(), "VML in the browser")
    check("OnOpened ran in Lua", pg.eval_on_selector("#v_lstLog", "e => e.options[0].text"), "Lua is running in the browser")
    pg.fill("#v_txtName", "Steve"); pg.click("#v_btnGo")
    check("button click ran Lua, which read the text box", text("#v_lblHello"), "Hello, Steve")
    pg.click("#v_chkShout")
    check("checkbox event", text("#v_lblHello"), "HELLO, STEVE!")
    import json as _json
    last = _json.loads(pg.evaluate("() => vml.settings.last"))
    check("Lua globals persist across clicks; dkjson encoded the setting", (last["name"], last["count"]), ("Steve", 2))
    check("the console API works too", pg.evaluate('() => vml.Vml("GetProperty", "txtName", "Text")'), "Steve")
    pg.select_option("#v_cboColour", "Red")
    check("dropdown changed the title colour", pg.eval_on_selector("#v_lblTitle", "e => getComputedStyle(e).color"), "rgb(153, 27, 27)")

    btn0, txt0, lst0, lbl0 = box("#v_btnGo"), box("#v_txtName"), box("#v_lstLog"), box("#v_lblHello")
    pg.set_viewport_size({"width": 840, "height": 520})
    pg.wait_for_timeout(100)
    btn1, txt1, lst1, lbl1 = box("#v_btnGo"), box("#v_txtName"), box("#v_lstLog"), box("#v_lblHello")
    check("anchors: Bottom,Right button follows the corner", (btn1[0] - btn0[0], btn1[1] - btn0[1]), (200, 100))
    check("anchors: Top,Left,Right text box stretches", txt1[2] - txt0[2], 200)
    check("anchors: list inside a stretching frame fills it", (lst1[2] - lst0[2], lst1[3] - lst0[3]), (200, 100))
    check("anchors: Bottom,Left label moves down only", (lbl1[0] - lbl0[0], lbl1[1] - lbl0[1]), (0, 100))
    pg.screenshot(path=os.path.join(HERE, "tests", "web", "demo-resized.png"))

    pg.click("#v_mnuFile")
    check("menu opens on click", pg.is_visible("#v_mnuClear"), True)
    pg.screenshot(path=os.path.join(HERE, "tests", "web", "demo-menu.png"))
    pg.click("#v_mnuClear")
    check("menu item ran its Lua script", pg.eval_on_selector("#v_lstLog", "e => e.options.length"), 0)
    check("menu closed afterwards", pg.is_visible("#v_mnuClear"), False)
    pg.click("#v_mnuFile"); pg.click("#v_mnuShell")
    check("a shell script declines politely in the browser", any("runs on the desktop, not in a browser" in l for l in logs), True)
    pg.click("#v_mnuHelp"); pg.click("#v_mnuAbout")
    check("InfoDialog becomes a browser alert", dialogs[-1:], ["VML in the browser\n\nSame .vml file, same Lua scripts."])
    b.close()

# a layout-panel form too: No-Stick's boot manager (DockPanel, Grid, Border, StackPanel)
nostick = export_html(os.path.join(HERE, "tests", "nostick.vml"), os.path.join(HERE, "tests", "web", "nostick.html"))
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 820, "height": 648})
    pg.goto("file://" + os.path.abspath(nostick))
    pg.wait_for_timeout(300)
    r = lambda s: pg.eval_on_selector(s, "e => { const r = e.getBoundingClientRect(); return [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)]; }")
    head, live, inst, foot = r("#v_HeaderBorder"), r("#v_LiveCard"), r("#v_InstallCard"), r("#v_FooterBorder")
    check("DockPanel: header across the top", (head[1], head[3]), (0, 90))
    check("DockPanel: footer along the bottom", (foot[1] + foot[3], foot[3]), (648, 140))
    check("Grid: two cards side by side, equal widths", (live[1] == inst[1], abs(live[2] - inst[2]) <= 1, inst[0] > live[0]), (True, True, True))
    pg.screenshot(path=os.path.join(HERE, "tests", "web", "nostick-browser.png"))
    b.close()
print(f"\n{sum(ok)}/{len(ok)} passed")
