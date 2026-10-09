"""Databases inside a web page: ItemsSource, cascades and the Db commands in a real (headless) browser, as on the desktop."""
import json, os, shutil, sqlite3, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("VML_PREFS", os.path.join(tempfile.mkdtemp(prefix="vml-prefs-"), "prefs.json"))   # never the real settings
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("playwright isn't installed (pip install playwright; python3 -m playwright install chromium): skipping\n0/0 passed")
    raise SystemExit(0)
from vml.html import export_html

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = tempfile.mkdtemp(prefix="vml-webdata-")
ok = []

def check(label, got, want=True):
    passed = got == want
    ok.append(passed)
    print(f"{'PASS' if passed else 'FAIL'}  {label}: {got!r}" + ("" if passed else f" (wanted {want!r})"))

shutil.copytree(os.path.join(HERE, "tests", "data"), os.path.join(WORK, "data"))
shutil.copytree(os.path.join(HERE, "tests", "project"), os.path.join(WORK, "project"))
db = sqlite3.connect(os.path.join(WORK, "project", "stock.db"))
db.execute("CREATE TABLE stock (item TEXT, qty INTEGER)")
db.executemany("INSERT INTO stock VALUES (?, ?)", [("bolts", 40), ("nuts", 12), ("widgets", 3)])
db.commit(); db.close()
cascade = export_html(os.path.join(WORK, "data", "cascade.vml"))
project_page = export_html(os.path.join(WORK, "project", "main.vml"))
plain = export_html(os.path.join(HERE, "tests", "web", "demo.vml"), os.path.join(WORK, "demo.html"))
check("a page with no database in it doesn't carry the database engine", (os.path.getsize(plain) < 700_000, os.path.getsize(cascade) > 1_200_000), (True, True))

with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={"width": 640, "height": 420})
    pg = ctx.new_page()
    logs = []
    pg.on("console", lambda m: logs.append(m.text))
    pg.goto("file://" + os.path.abspath(cascade))
    pg.wait_for_selector("#vml_status[data-ready='1']", state="attached", timeout=30000)
    V = lambda *a: pg.evaluate("a => vml.Vml(...a)", list(a))
    options = lambda name: pg.eval_on_selector(f"#v_{name}", "e => [...e.options].map(o => o.text)")
    rows = lambda name: pg.evaluate("n => document.getElementById('v_' + n)._rows", name)

    check("a combo fills itself from its query", options("cboCategory"), ["Memory", "Speed"])
    check("a list fills from the combo's choice, with no script", options("lstQuestion"), ["Recalls digits", "Recalls O'Brien's story"])
    check("a grid waits for a choice in the list", rows("grdAnswers"), [])
    pg.select_option("#v_lstQuestion", "Recalls digits")
    check("choosing in the list fills the grid, under its own headings", (rows("grdAnswers"), pg.locator("#v_grdAnswers th").all_inner_texts()), ([["Seven forward", "10"], ["Three back", "4"]], ["Answer", "Score"]))
    pg.select_option("#v_lstQuestion", "Recalls O'Brien's story")
    check("a value with a quote in it is passed safely", rows("grdAnswers"), [["All of it", "9"]])
    pg.select_option("#v_cboCategory", "Speed")
    check("changing the first control refills the second, and empties what hangs off it", (options("lstQuestion"), V("GetProperty", "lstQuestion", "SelectedItem"), rows("grdAnswers")), (["Symbol search", "Coding"], "", []))
    pg.select_option("#v_lstQuestion", "Coding")
    check("and fills again from the new choice", rows("grdAnswers"), [["Fast", "8"]])
    V("SetProperty", "cboCategory", "SelectedItem", "Memory")
    check("a script changing the first control refills the rest too", options("lstQuestion"), ["Recalls digits", "Recalls O'Brien's story"])

    check("a list that depends on a text box starts empty", options("lstFound"), [])
    pg.type("#v_txtFind", "ecal")
    pg.wait_for_timeout(450)
    check("typing fills it once the typing pauses", options("lstFound"), ["Recalls digits", "Recalls O'Brien's story"])
    check("a tree fills from paths in the first column", (pg.locator("#v_treAll > .ti").count(), pg.locator("#v_treAll > .ti >> nth=0").locator(".kids .ti").count()), (1, 2))
    pg.click("#v_chkAll")
    check("a check box's {name} is true or false", pg.locator("#v_treAll > .ti").count(), 2)
    check("ItemsSource can be a script, given the controls it names", options("lstScript"), ["MEMORY!", "second line"])
    pg.select_option("#v_cboCategory", "Speed")
    check("...and it runs again when they change", options("lstScript"), ["SPEED!", "second line"])
    check("with no Database named, a query asks the form's own (its settings are there)", options("lstOwn"), ["hello from the form's own database"])

    V("DbExecute", "q", "INSERT INTO questions (category, question) VALUES ('Speed', 'Cancellation')")
    V("Requery", "lstQuestion")
    check("Requery fills one again after the data changed", options("lstQuestion"), ["Symbol search", "Coding", "Cancellation"])
    check("DbQuery gives JSON, one object per row, with parameters", json.loads(V("DbQuery", "q", "SELECT answer, score FROM answers WHERE score > ? ORDER BY score", 8)), [{"answer": "All of it", "score": 9}, {"answer": "Seven forward", "score": 10}])
    check("DbExecute says how many rows it touched", V("DbExecute", "q", "UPDATE answers SET score = score + 1 WHERE category = ?", "Memory"), "3")
    check("a bad statement gives nothing back, and DbError says why", (V("DbQuery", "q", "SELEKT"), "SELEKT" in V("DbError") or "syntax" in V("DbError")), ("[]", True))
    check("DbTables lists the tables", json.loads(V("DbTables", "q")), ["answers", "questions"])
    check("ODBC is refused plainly: a web page has no drivers", (V("DbOpen", "x", "odbc:DSN=Sales"), "ODBC isn't available in a web page" in V("DbError")), ("", True))
    V("SetProperty", "lstOwn", "ItemsSource", "SELECT 'changed while running'")
    check("setting ItemsSource on a running page fills it straight away", options("lstOwn"), ["changed while running"])
    check("nothing went wrong in the page that wasn't meant to", [l for l in logs if "error" in l.lower() and "SELEKT" not in l and "ODBC" not in l], [])

    # ---- a project: its SQLite file travels inside the page
    logs.clear()
    pg.goto("file://" + os.path.abspath(project_page))
    pg.wait_for_selector("#vml_status[data-ready='1']", state="attached", timeout=30000)
    check("a project's database is inside the page: its list fills", options("lstItems"), ["bolts", "nuts", "widgets"])
    pg.select_option("#v_lstItems", "nuts"); pg.click("#v_btnQty")
    check("a module's function reads the project's database by name", pg.inner_text("#v_lblQty"), "nuts: 12")
    V("DbExecute", "stock", "UPDATE stock SET qty = 99 WHERE item = 'nuts'")
    pg.reload()
    pg.wait_for_selector("#vml_status[data-ready='1']", state="attached", timeout=30000)
    pg.select_option("#v_lstItems", "nuts"); pg.click("#v_btnQty")
    check("a change made in the page is still there after a reload (kept in this browser)", pg.inner_text("#v_lblQty"), "nuts: 99")
    other = ctx.new_page()
    other.goto("file://" + os.path.abspath(project_page))
    other.wait_for_selector("#vml_status[data-ready='1']", state="attached", timeout=30000)
    check("...and the app's other pages see it too", json.loads(other.evaluate("() => vml.Vml('DbQuery', 'stock', 'SELECT qty FROM stock WHERE item = ?', 'nuts')")), [{"qty": 99}])
    check("the file the page was made from is untouched", sqlite3.connect(os.path.join(WORK, "project", "stock.db")).execute("SELECT qty FROM stock WHERE item='nuts'").fetchone()[0], 12)
    check("nothing went wrong in the project's page", [l for l in logs if "error" in l.lower()], [])
    b.close()

print(f"\n{sum(ok)}/{len(ok)} passed")
sys.exit(0 if all(ok) else 1)
