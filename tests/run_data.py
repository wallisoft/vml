"""Databases (SQLite and ODBC) and controls that fill themselves: ItemsSource, {control} parameters, cascades."""
import json, os, sqlite3, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("VML_PREFS", os.path.join(tempfile.mkdtemp(prefix="vml-prefs-"), "prefs.json"))   # never the real settings
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from vml.engine import Engine

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
eng = Engine().load(os.path.join(HERE, "tests", "data", "cascade.vml"))
app, ok = QApplication.instance(), []

def check(label, got, want=True):
    passed = got == want
    ok.append(passed)
    print(f"{'PASS' if passed else 'FAIL'}  {label}: {got!r}" + ("" if passed else f" (wanted {want!r})"))

def settle(n=8):
    for _ in range(n):
        app.processEvents()

w = lambda name: eng.find(name).widget
get = lambda name, prop: eng.cmd_GetProperty(name, prop)
items = lambda name: [w(name).item(i).text() for i in range(w(name).count())]
combo = lambda name: [w(name).itemText(i) for i in range(w(name).count())]
grid = lambda name: w(name).data

def steps():
    settle()
    # ---- filled when the form opens, after OnOpened has opened the database
    check("a combo fills itself from its query", combo("cboCategory"), ["Memory", "Speed"])
    check("a list fills from the combo's choice, with no script", items("lstQuestion"), ["Recalls digits", "Recalls O'Brien's story"])
    check("a grid waits for a choice in the list", grid("grdAnswers"), [])
    w("lstQuestion").setCurrentRow(0); settle()
    check("choosing in the list fills the grid", grid("grdAnswers"), [["Seven forward", "10"], ["Three back", "4"]])
    check("the grid shows its own headings", [w("grdAnswers").horizontalHeaderItem(i).text() for i in range(2)], ["Answer", "Score"])
    w("lstQuestion").setCurrentRow(1); settle()
    check("a value with a quote in it is passed safely, not pasted into the SQL", grid("grdAnswers"), [["All of it", "9"]])
    w("cboCategory").setCurrentIndex(1); settle()
    check("changing the first control refills the second...", items("lstQuestion"), ["Symbol search", "Coding"])
    check("...and what hangs off the second empties, because its choice has gone", (get("lstQuestion", "SelectedItem"), grid("grdAnswers")), ("", []))
    w("lstQuestion").setCurrentRow(1); settle()
    check("and fills again from the new choice", grid("grdAnswers"), [["Fast", "8"]])
    eng.cmd_SetProperty("cboCategory", "SelectedItem", "Memory"); settle()
    check("a script changing the first control refills the rest too", items("lstQuestion"), ["Recalls digits", "Recalls O'Brien's story"])

    # ---- other kinds of control as the thing depended on
    check("a list that depends on a text box starts empty", items("lstFound"), [])
    w("txtFind").setText("ecal"); settle()
    check("typing doesn't ask the database on every key...", items("lstFound"), [])
    QTimer.singleShot(400, typed)

def typed():
    settle()
    check("...it asks once the typing pauses", items("lstFound"), ["Recalls digits", "Recalls O'Brien's story"])
    tree = w("treAll")
    check("a tree fills from paths in the first column", (tree.topLevelItemCount(), tree.topLevelItem(0).text(0), tree.topLevelItem(0).childCount()), (1, "Memory", 2))
    w("chkAll").setChecked(True); settle()
    check("a check box's {name} is true or false", (tree.topLevelItemCount(), tree.topLevelItem(1).text(0)), (2, "Speed"))

    # ---- a script as the source; the form's own database as the default
    check("ItemsSource can be a script, given the controls it names", items("lstScript"), ["MEMORY!", "second line"])
    w("cboCategory").setCurrentIndex(1); settle()
    check("...and it runs again when they change", items("lstScript"), ["SPEED!", "second line"])
    check("with no Database named, a query asks the form's own", items("lstOwn"), ["hello from the form's own database"])

    # ---- Requery, and changing ItemsSource while running
    eng.cmd_DbExecute("q", "INSERT INTO questions (category, question) VALUES ('Speed', 'Cancellation')")
    check("the lists don't know the data changed until told", items("lstQuestion"), ["Symbol search", "Coding"])
    eng.cmd_Requery("lstQuestion"); settle()
    check("Requery fills one again", items("lstQuestion"), ["Symbol search", "Coding", "Cancellation"])
    eng.cmd_DbExecute("q", "INSERT INTO questions (category, question) VALUES ('Verbal', 'Similarities')")
    eng.cmd_Requery(); settle()
    check("Requery with no name fills every one, keeping each choice", (combo("cboCategory"), get("cboCategory", "SelectedItem")), (["Memory", "Speed", "Verbal"], "Speed"))
    eng.cmd_SetProperty("lstOwn", "ItemsSource", "SELECT 'changed while running'"); settle()
    check("setting ItemsSource on a running form fills it straight away", items("lstOwn"), ["changed while running"])
    eng.cmd_SetProperty("lstOwn", "ItemsSource", "SELECT nonsense FROM nowhere"); settle()
    check("a query that fails empties the control and says why", (items("lstOwn"), "nowhere" in eng.cmd_DbError()), ([], True))
    eng.cmd_SetProperty("lstOwn", "ItemsSource", ""); settle()

    # ---- the Db commands themselves
    folder = tempfile.mkdtemp(prefix="vml-data-")
    path = os.path.join(folder, "people.db")
    check("DbOpen makes a SQLite file if it isn't there", (eng.cmd_DbOpen("people", path), os.path.exists(path)), ("true", True))
    eng.cmd_DbExecute("people", "CREATE TABLE people (id INTEGER PRIMARY KEY, name TEXT, born DATE, photo BLOB)")
    n = eng.cmd_DbExecute("people", "INSERT INTO people (name, born, photo) VALUES (?, ?, ?)", "Ann", "1990-05-01", "x")
    check("DbExecute says how many rows it touched", n, 1)
    check("DbQuery gives JSON, one object per row", json.loads(eng.cmd_DbQuery("people", "SELECT id, name FROM people WHERE name = ?", "Ann")), [{"id": 1, "name": "Ann"}])
    check("DbTables lists the tables", json.loads(eng.cmd_DbTables("people")), ["people"])
    check("a bad statement gives nothing back, and DbError says why", (eng.cmd_DbQuery("people", "SELEKT"), eng.cmd_DbExecute("people", "DROP TABLE nope"), "nope" in eng.cmd_DbError()), ("[]", "", True))
    check("a good one clears the error", (eng.cmd_DbQuery("people", "SELECT 1 AS one"), eng.cmd_DbError()), ('[{"one": 1}]', ""))
    check("asking a database that isn't open is an error, not a crash", (eng.cmd_DbQuery("nobody", "SELECT 1"), "nobody" in eng.cmd_DbError()), ("[]", True))
    check("an address that makes no sense is refused", (eng.cmd_DbOpen("x", "whatever"), "sqlite:file.db" in eng.cmd_DbError()), ("", True))
    check("DbList names what is open", sorted(d["name"] for d in json.loads(eng.cmd_DbList()) if d["open"]), ["people", "q"])
    check("DbClose closes it", (eng.cmd_DbClose("people"), eng.cmd_DbQuery("people", "SELECT 1")), (True, "[]"))
    check("sqlite: with a relative path means beside the form", (eng.cmd_DbOpen("rel", "sqlite:made-by-test.db"),
          os.path.exists(os.path.join(HERE, "tests", "data", "made-by-test.db"))), ("true", True))
    eng.cmd_DbClose("rel"); os.remove(os.path.join(HERE, "tests", "data", "made-by-test.db"))

    # ---- ODBC, through a real driver if this computer has one for SQLite (it reaches SQL Server, Access etc. the same way)
    drivers = json.loads(eng.cmd_DbDrivers())
    driver = next((d for d in drivers if "sqlite3" in d.lower()), None)
    if driver is None:
        print(f"SKIP  ODBC (no SQLite ODBC driver here to test with; drivers found: {drivers})")
    else:
        db = sqlite3.connect(path); db.execute("INSERT INTO people (name, born) VALUES ('Bob', '1985-12-25')"); db.commit(); db.close()
        check("DbOpen with an odbc: address connects through the ODBC driver", eng.cmd_DbOpen("viaodbc", f"odbc:Driver={{{driver}}};Database={path}"), "true")
        check("queries and parameters work the same over ODBC", json.loads(eng.cmd_DbQuery("viaodbc", "SELECT name FROM people WHERE name LIKE ? ORDER BY name", "%o%")), [{"name": "Bob"}])
        check("so does changing data", (eng.cmd_DbExecute("viaodbc", "UPDATE people SET name = ? WHERE name = ?", "Robert", "Bob"),
              json.loads(eng.cmd_DbQuery("viaodbc", "SELECT count(*) AS n FROM people WHERE name = 'Robert'"))), (1, [{"n": 1}]))
        check("and listing tables", "people" in json.loads(eng.cmd_DbTables("viaodbc")))
        eng.cmd_SetProperty("lstOwn", "Database", "viaodbc")
        eng.cmd_SetProperty("lstOwn", "ItemsSource", "SELECT name FROM people ORDER BY name"); settle()
        check("a list fills from an ODBC database exactly as from SQLite", items("lstOwn"), ["Ann", "Robert"])
        check("a connection that can't be made is reported, with any password kept out of the log",
              (eng.cmd_DbOpen("bad", "odbc:DSN=NoSuchSource;UID=me;PWD=hunter2"), eng.cmd_DbError() != "", "hunter2" in eng.cmd_DbError()), ("", True, False))
        eng.cmd_DbClose("viaodbc")

    # ---- on the design surface nothing is queried
    eng.load(os.path.join(HERE, "designer", "designer.vml")); settle()
    name = eng.cmd_AddDesignControl("ListBox", 40, 40)
    eng.cmd_SetProperty(name, "ItemsSource", "SELECT name FROM people"); settle()
    check("a designed list keeps its ItemsSource as a property and its sample items on screen", (get(name, "ItemsSource"), items(name)), ("SELECT name FROM people", ["One", "Two", "Three"]))
    out = os.path.join(folder, "designed.vml")
    eng.cmd_ExportVml("Surface", out)
    check("...and it is saved with the form", "ItemsSource=SELECT name FROM people" in open(out, encoding="utf-8").read())
    print(f"\n{sum(ok)}/{len(ok)} passed")
    app.quit()

QTimer.singleShot(400, steps)
app.exec()
sys.exit(0 if all(ok) else 1)
