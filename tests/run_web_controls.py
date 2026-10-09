"""The controls added in 1.0, as a web page in a real (headless) browser; and a project's modules in the page."""
import json, os, shutil, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("VML_PREFS", os.path.join(tempfile.mkdtemp(prefix="vml-prefs-"), "prefs.json"))   # never the real settings
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("playwright isn't installed (pip install playwright; python3 -m playwright install chromium): skipping\n0/0 passed")
    raise SystemExit(0)
from vml.html import export_html

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = tempfile.mkdtemp(prefix="vml-web-")
ok = []

def check(label, got, want=True):
    passed = got == want
    ok.append(passed)
    print(f"{'PASS' if passed else 'FAIL'}  {label}: {got!r}" + ("" if passed else f" (wanted {want!r})"))

shutil.copytree(os.path.join(HERE, "tests", "controls"), os.path.join(WORK, "controls"))
shutil.copytree(os.path.join(HERE, "tests", "project"), os.path.join(WORK, "project"))
page_path = export_html(os.path.join(WORK, "controls", "controls.vml"))
project_page = export_html(os.path.join(WORK, "project", "main.vml"))
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 640, "height": 420})
    logs = []
    pg.on("console", lambda m: logs.append(m.text))
    pg.goto("file://" + os.path.abspath(page_path))
    pg.wait_for_selector("#vml_status[data-ready='1']", state="attached", timeout=20000)
    V = lambda *a: pg.evaluate("a => vml.Vml(...a)", list(a))

    check("option buttons start as the form says", [V("GetProperty", n, "IsChecked") for n in ("optSmall", "optLarge", "optRed", "optBlue", "optPost")], ["true", "false", "true", "false", "true"])
    pg.click("#v_optLarge")
    check("choosing one clears the other in its group, and no other group", [V("GetProperty", n, "IsChecked") for n in ("optSmall", "optLarge", "optRed", "optPost")], ["false", "true", "true", "true"])
    check("OnChecked ran in Lua", pg.inner_text("#v_lblSize"), "size: Large")
    check("a password box is a password box, and scripts still read it", (pg.get_attribute("#v_txtSecret", "type"), V("GetProperty", "txtSecret", "Text")), ("password", "hunter2"))
    img = pg.eval_on_selector("#v_imgDot", "e => [e.naturalWidth, e.clientWidth, e.clientHeight, getComputedStyle(e).objectFit, e.src.slice(0, 22)]")
    check("a picture beside the form is put inside the page, at its control's size", img, [16, 64, 48, "fill", "data:image/png;base64,"])
    check("a picture already inside the form loads too", pg.eval_on_selector("#v_imgInline", "e => e.naturalWidth"), 1)

    check("a grid shows its headings and rows", (pg.locator("#v_grid th").all_inner_texts(), pg.locator("#v_grid tbody tr").count(), pg.locator("#v_grid tbody tr >> nth=2").locator("td").first.inner_text()), (["Name", "Age"], 3, "Cy, Jr"))
    pg.click("#v_grid tbody tr >> nth=1")
    check("clicking a row selects it and runs SelectionChanged", pg.inner_text("#v_lblGrid"), '1 Bob {"Name":"Bob","Age":"27"}')
    pg.dblclick("#v_grid tbody tr >> nth=0")
    check("double-clicking runs OnDoubleClick", V("GetSetting", "opened"), "grid:Ann")
    n = V("GridSetData", "grid", json.dumps([{"City": "Leeds", "Pop": 800}, {"City": "York", "Pop": 200}]))
    check("GridSetData works in the browser", (n, pg.locator("#v_grid th").all_inner_texts(), json.loads(V("GridGetData", "grid"))[1]), ("2", ["City", "Pop"], {"City": "York", "Pop": "200"}))

    check("a tree is built from paths", (pg.locator("#v_tree > .ti").count(), pg.locator("#v_tree > .ti >> nth=0").locator(".kids .ti").count()), (3, 2))
    pg.click("#v_tree .ti[data-path='Forms/Login'] > span")
    check("clicking an item selects it, by its whole path", (pg.inner_text("#v_lblTree"), V("GetProperty", "tree", "SelectedItem")), ("Forms/Login", "Forms/Login"))
    V("SetProperty", "tree", "Items", "A/One,A/Two,B")
    check("a script can refill a tree", (pg.locator("#v_tree > .ti").count(), V("GetProperty", "tree", "SelectedItem")), (2, ""))
    pg.dblclick("#v_lst option >> nth=1")
    check("a list's OnDoubleClick", V("GetSetting", "opened"), "list:Two")
    check("nothing went wrong in the page", [l for l in logs if "error" in l.lower()], [])
    check("a picture that isn't there leaves a gap, not a broken-picture mark", pg.eval_on_selector("#v_imgMissing", "e => getComputedStyle(e).visibility"), "hidden")
    pg.screenshot(path=os.path.join(WORK, "controls.png"))

    # a form that belongs to a project: its modules are in the page; its database is not
    logs.clear()
    pg.goto("file://" + os.path.abspath(project_page))
    pg.wait_for_selector("#vml_status[data-ready='1']", state="attached", timeout=20000)
    check("a project's modules are in the page, so its scripts still find their functions", pg.inner_text("#v_lblHello"), "HELLO! from Demo")
    check("the Project table is there to share values", pg.evaluate("() => vml.settings") is not None and not [l for l in logs if "Project" in l and "nil" in l], True)
    check("its database file wasn't there when the page was made, so it starts empty, and the list says why it has nothing", sum("lstItems.ItemsSource" in l and "no such table" in l for l in logs), 1)
    b.close()

print(f"\n{sum(ok)}/{len(ok)} passed")
sys.exit(0 if all(ok) else 1)
