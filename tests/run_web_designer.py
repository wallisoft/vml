"""Designed in the designer, exported from it, used in a browser."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("VML_PREFS", os.path.join(__import__("tempfile").mkdtemp(prefix="vml-prefs-"), "prefs.json"))   # never the real settings
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("playwright isn't installed: skipping\n0/0 passed")
    raise SystemExit(0)
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from vml.engine import Engine

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
eng = Engine().load(os.path.join(HERE, "designer", "designer.vml"))
eng.licence_override = "pro"                     # exporting is a Pro feature
app, ok = QApplication.instance(), []

def check(label, got, want):
    passed = got == want
    ok.append(passed)
    print(f"{'PASS' if passed else 'FAIL'}  {label}: {got!r}" + ("" if passed else f" (wanted {want!r})"))

def steps():
    eng.cmd_SetProperty("Surface", "FormTitle", "Designed, then on the web")
    eng.handle("AddMenu", eng.find("CtxAddMenu"))
    box = eng.cmd_AddDesignControl("TextBox", 24, 24)
    eng.cmd_SetProperty(box, "Width", "592"); eng.cmd_SetProperty(box, "Anchor", "Top,Left,Right")
    btn = eng.cmd_AddDesignControl("Button", 520, 432)
    eng.cmd_SetProperty(btn, "Anchor", "Bottom,Right")
    eng.cmd_SetDesignScript(btn, "OnClick", "Lua",
        'Vml("SetProperty", "%s", "Content", "Hi " .. Vml("GetProperty", "%s", "Text"))' % (btn, box))
    out = eng.cmd_ExportHtml("Surface", "/tmp/designed.html")
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 640, "height": 506})
        dialogs = []
        pg.on("dialog", lambda d: (dialogs.append(d.message), d.accept()))
        pg.goto("file://" + out)
        pg.wait_for_selector("#vml_status[data-ready='1']", state="attached", timeout=20000)
        check("title", pg.title(), "Designed, then on the web")
        check("the starter menu came too", pg.eval_on_selector_all(".mtop > .mt", "els => els.map(e => e.textContent)"), ["File", "Edit", "Help"])
        pg.fill(f"#v_{box}", "Firefox"); pg.click(f"#v_{btn}")
        check("the script written in the script editor runs in the browser", pg.inner_text(f"#v_{btn}"), "Hi Firefox")
        pg.click("#v_mnuHelp"); pg.click("#v_mnuAbout")
        check("the starter About works in the browser", dialogs[:1] and dialogs[0].startswith("Designed, then on the web"), True)
        x0 = pg.eval_on_selector(f"#v_{btn}", "e => e.getBoundingClientRect().x")
        pg.set_viewport_size({"width": 900, "height": 506}); pg.wait_for_timeout(100)
        x1 = pg.eval_on_selector(f"#v_{btn}", "e => e.getBoundingClientRect().x")
        check("anchored button follows the browser edge", round(x1 - x0), 260)
        pg.screenshot(path=os.path.join(HERE, "tests", "web", "designed-browser.png"))
        b.close()
    print(f"\n{sum(ok)}/{len(ok)} passed")
    app.quit()

QTimer.singleShot(500, steps)
eng.run()
