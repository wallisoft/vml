"""The data browser: a project's databases, their tables, the first rows of each, and a SELECT of your own. It only reads."""
import json, os, sqlite3, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("VML_PREFS", os.path.join(tempfile.mkdtemp(prefix="vml-prefs-"), "prefs.json"))
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
import vml.engine as engine_module
from vml.engine import Engine

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = tempfile.mkdtemp(prefix="vml-browse-")
ok, logged = [], []
_log = engine_module.log
engine_module.log = lambda msg: (logged.append(str(msg)), _log(msg))[0]

def check(label, got, want=True):
    passed = got == want
    ok.append(passed)
    print(f"{'PASS' if passed else 'FAIL'}  {label}" + ("" if passed else f": got {got!r}, wanted {want!r}"))

eng = Engine()
app = QApplication.instance()
app.setQuitOnLastWindowClosed(False)
V = eng.vml
said = []
eng.cmd_InfoDialog = lambda msg, title="": said.append(str(msg))

def settle(n=10):
    for _ in range(n):
        app.processEvents()

with open(os.path.join(WORK, "T.vmlproj"), "w") as f:
    f.write("# Visualised project\nName=Corner Shop\nStartup=a.vml\nForm=a.vml\nDatabase=shop=sqlite:shop.db\nDatabase=empty=sqlite:empty.db\n")
with open(os.path.join(WORK, "a.vml"), "w") as f:
    f.write("@Window a\nTitle=a\n")
shop = os.path.join(WORK, "shop.db")
c = sqlite3.connect(shop)
c.execute("CREATE TABLE products (id INTEGER, name TEXT, price REAL)")
c.executemany("INSERT INTO products VALUES (?,?,?)", [(i, f"Product {i}", i * 1.25) for i in range(1, 1500)])
c.execute('CREATE TABLE "order lines" (item TEXT, n INTEGER)')
c.executemany('INSERT INTO "order lines" VALUES (?,?)', [("Tea", 2), ("Jam", 1)])
c.execute("CREATE VIEW dear AS SELECT * FROM products WHERE price > 1800")
c.commit(); c.close()
sqlite3.connect(os.path.join(WORK, "empty.db")).close()
other = os.path.join(WORK, "elsewhere.db")
c = sqlite3.connect(other); c.execute("CREATE TABLE notes (said TEXT)"); c.execute("INSERT INTO notes VALUES ('hello')"); c.commit(); c.close()

def inside(win, then):
    try:
        then(lambda name: eng.scopes[win.scope][name].widget)
    finally:
        win.widget.close()

def browser(then):
    def go():
        win = next((x for x in eng.windows if x.name == "Browser"), None)
        if win is not None:
            inside(win, then)
    QTimer.singleShot(400, go)

def from_project(w):
    items = lambda name: [w(name).item(i).text() for i in range(w(name).count())]
    status = lambda: w("lblBrStatus").text()
    check("the project's databases are offered, in its order, and the first is open", ([w("cboBrDb").itemText(i) for i in range(w("cboBrDb").count())], w("cboBrDb").currentText()), (["shop", "empty"], "shop"))
    check("its tables and views are listed", (items("lstBrTables"), status()), (["dear", "order lines", "products"], "3 tables and views. Choose one."))
    w("lstBrTables").setCurrentRow(2); settle()
    check("a big table shows its first 200 rows, in the database's column order, and says how many there are",
          (w("grdBr").cols, len(w("grdBr").data), w("grdBr").data[0], status()), (["id", "name", "price"], 200, ["1", "Product 1", "1.25"], "products: the first 200 rows of 1,499, 3 columns."))
    w("lstBrTables").setCurrentRow(1); settle()
    check("a small one, with a space in its name, shows all of it", (w("grdBr").data, status()), ([["Tea", "2"], ["Jam", "1"]], "order lines: 2 rows, 2 columns."))
    w("lstBrTables").setCurrentRow(0); settle()
    check("a view is shown like a table", (len(w("grdBr").data), status()), (59, "dear: 59 rows, 3 columns."))
    w("txtBrSql").setText("SELECT name, price FROM products WHERE id IN (3, 4) ORDER BY id DESC;"); w("btnBrRun").click(); settle()
    check("a SELECT of your own is run", (w("grdBr").cols, w("grdBr").data, status()), (["name", "price"], [["Product 4", "5.0"], ["Product 3", "3.75"]], "Your query: 2 rows, 2 columns."))
    w("txtBrSql").setText("SELECT * FROM products"); w("btnBrRun").click(); settle()
    check("a big answer is capped, and says there is more", (len(w("grdBr").data), status()), (200, "Your query: the first 200 rows (there are more), 3 columns."))
    for bad in ("DELETE FROM products", "UPDATE products SET price = 0", "DROP TABLE products", "SELECT 1; DELETE FROM products"):
        w("txtBrSql").setText(bad); w("btnBrRun").click(); settle()
        check(f"it only reads: {bad.split()[0]} is refused", "this only reads" in status())
    got = sqlite3.connect(shop)
    check("and nothing was changed", (got.execute("SELECT COUNT(*), MIN(price) FROM products").fetchone(), [r[0] for r in got.execute("SELECT name FROM sqlite_master ORDER BY 1")]), ((1499, 1.25), ["dear", "order lines", "products"]))
    got.close()
    w("txtBrSql").setText("SELECT nope FROM nowhere"); w("btnBrRun").click(); settle()
    check("a mistake in a query is reported, not fatal", ("no such table" in status(), w("lblBrStatus").isVisible()), (True, True))
    w("cboBrDb").setCurrentIndex(1); settle()
    check("choosing another database shows its tables (none, here) and clears the grid", (items("lstBrTables"), status(), len(w("grdBr").data)), ([], "There are no tables in this database.", 0))
    w("cboBrDb").setCurrentIndex(0); settle()
    check("and back again", items("lstBrTables"), ["dear", "order lines", "products"])

def from_screen(w):
    items = lambda name: [w(name).item(i).text() for i in range(w(name).count())]
    check("from the Databases screen: the address on screen is browsed, saved or not", (w("cboBrDb").currentText(), items("lstBrTables")), ("scratch", ["notes"]))
    check("it is offered beside the project's own", [w("cboBrDb").itemText(i) for i in range(w("cboBrDb").count())], ["scratch", "shop", "empty"])
    w("lstBrTables").setCurrentRow(0); settle()
    check("and its rows show", w("grdBr").data, [["hello"]])

def steps():
    # the command the browser is made of
    eng.load(os.path.join(HERE, "tests", "controls", "controls.vml")); settle()
    grid = next((n.name for n in eng.scopes[eng.windows[-1].scope].values() if n.type.name == "DataGrid"), None)
    V("DbOpen", "t", "sqlite:" + shop)
    r = json.loads(V("DbShow", grid, "t", "products", 5))
    check("DbShow puts a table's first rows straight into a grid and says how many there are", (r, eng.find(grid).widget.cols, len(eng.find(grid).widget.data)),
          ({"shown": 5, "total": 1499, "columns": 3, "error": ""}, ["id", "name", "price"], 5))
    check("DbShow refuses anything that isn't a table or one SELECT", [json.loads(V("DbShow", grid, "t", s))["error"] != "" for s in ("DELETE FROM products", "products; DROP TABLE products", "nope")], [True, True, True])
    V("DbClose", "t")
    for x in list(eng.windows):
        x.widget.close()
    settle()

    # what the browser relies on to tidy up: a form's OnClosing runs when its window closes, and can refuse
    form = os.path.join(WORK, "closing.vml")
    with open(form, "w") as f:
        f.write("""@Window Closing
Title=Closing
Width=200
Height=100
OnClosing=Leaving

@Script Leaving
Interpreter=lua
<<LUA
local n = (tonumber(Vml("GetSetting", "asked")) or 0) + 1
Vml("SetSetting", "asked", tostring(n))
if n == 1 then Vml("CancelClose") end
LUA
""")
    eng.store.set_setting("asked", "0")
    eng.load(form); settle()
    win = next(x for x in eng.windows if x.name == "Closing")
    win.widget.close(); settle()
    first = (eng.store.get_setting("asked"), win.widget.isVisible())
    win.widget.close(); settle()
    check("OnClosing runs when a window is closed, and CancelClose keeps it open", (first, eng.store.get_setting("asked"), win.widget.isVisible()), (("1", True), "2", False))

    eng.load(os.path.join(HERE, "designer", "designer.vml")); settle()
    eng.run_script("BrowseData"); settle()
    check("with no project open, Browse Data is greyed, and says to open one if asked anyway", (eng.find("ProjBrowseData").action.isEnabled(), len(said), "Open a project first" in said[0]), (False, 1, True))
    eng.run_script("ProjectLoad", os.path.join(WORK, "T.vmlproj")); settle()
    browser(from_project)
    eng.find("ProjBrowseData").action.trigger(); settle()
    check("closing the browser closes its connection", "vml_browse" in eng.databases, False)
    seen = {}
    browser(lambda w: seen.update(db=w("cboBrDb").currentText()))
    V("SetProperty", "ProjTree", "SelectedItem", "Databases/empty"); eng.run_script("ProjOpenItem"); settle()
    check("double-clicking a database in the project tree opens the browser on it", seen.get("db"), "empty")
    browser(from_screen)
    eng.run_script("BrowseData", "scratch", "sqlite:" + other); settle()
    check("nothing went wrong along the way", [l for l in logged if "script error" in l or "no script called" in l], [])
    print(f"\n{sum(ok)}/{len(ok)} passed")
    app.quit()

QTimer.singleShot(200, steps)
app.exec()
sys.exit(0 if all(ok) else 1)
