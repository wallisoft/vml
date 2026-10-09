"""Settings > Databases: the project's databases, this computer's ODBC drivers and data sources, addresses that keep
no password (PWD=? asks, ${NAME} reads the environment), testing a connection, copying an ODBC database into SQLite,
and being told at once when an imported project's Access data could not be read."""
import json, os, shutil, sqlite3, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("VML_PREFS", os.path.join(tempfile.mkdtemp(prefix="vml-prefs-"), "prefs.json"))
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QLineEdit
import vml.engine as engine_module
from vml import data, dialogs
from vml.engine import Engine

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = tempfile.mkdtemp(prefix="vml-dbs-")
ok, logged = [], []
_log = engine_module.log
engine_module.log = lambda msg: (logged.append(str(msg)), _log(msg))[0]

def check(label, got, want=True):
    passed = got == want
    ok.append(passed)
    print(f"{'PASS' if passed else 'FAIL'}  {label}" + ("" if passed else f": got {got!r}, wanted {want!r}"))

eng = Engine()
eng.licence_override = "pro"
app = QApplication.instance()
app.setQuitOnLastWindowClosed(False)
V = eng.vml
said, asked, confirms, answers, yes = [], [], [], [], [True]
picked = []
eng.cmd_FileOpenDialog = lambda title="", ext="": picked.pop(0) if picked else ""
eng.cmd_InfoDialog = lambda msg, title="": said.append(str(msg))
eng.cmd_ConfirmDialog = lambda msg, title="": (confirms.append(str(msg)), yes[0])[1]
def prompt(title="", text="", default="", secret=""):
    asked.append((str(title), str(secret)))
    return answers.pop(0) if answers else ""
eng.cmd_PromptDialog = prompt

def settle(n=10):
    for _ in range(n):
        app.processEvents()

# ---------------------------------------------------------------- addresses that keep no password
os.environ["VML_TEST_USER"], os.environ["VML_TEST_WORD"] = "reports", "s3cret"
check("${NAME} is read from the environment", eng._address("sales", "odbc:DSN=Sales;UID=${VML_TEST_USER};PWD=${VML_TEST_WORD}"), "odbc:DSN=Sales;UID=reports;PWD=s3cret")
try:
    eng._address("sales", "odbc:DSN=Sales;PWD=${VML_NOT_SET_ANYWHERE}"); missing = ""
except LookupError as exc:
    missing = str(exc)
check("a variable that isn't set is an error that names it", "VML_NOT_SET_ANYWHERE" in missing)
answers.append("pa;ss")
check("PWD=? asks for the password, with dots, and a ; in it is kept whole",
      (eng._address("sales", "odbc:DSN=Sales;UID=reports;PWD=?;Encrypt=yes"), asked[-1]), ("odbc:DSN=Sales;UID=reports;PWD={pa;ss};Encrypt=yes", ("Password for sales", "true")))
try:
    eng._address("sales", "odbc:DSN=Sales;UID=reports;PWD=?"); refused = ""
except PermissionError as exc:
    refused = str(exc)
check("no password given: it doesn't try to connect without one", refused, "no password was given for 'sales'")
check("a password is never in what is logged or reported",
      (data.hide_password("Driver={X};UID=me;PWD=hunter2;Server=a"), data.hide_password("connect string 'DSN=S;Password={a;b}}c};x=1'")), ("Driver={X};UID=me;PWD=***;Server=a", "connect string 'DSN=S;Password=***;x=1'"))
box = dialogs.Box(None, "t", "m", ("OK", "Cancel"), ask="")
box.input.setEchoMode(QLineEdit.Password)
check("the password box shows dots", box.input.echoMode(), QLineEdit.Password)
box.deleteLater()

# ---------------------------------------------------------------- testing an address, and what this computer has
good = os.path.join(WORK, "good.db")
c = sqlite3.connect(good); c.execute("CREATE TABLE people (name TEXT, age INTEGER)"); c.executemany("INSERT INTO people VALUES (?,?)", [("Ann", 41), ("Bob", 7)])
c.execute("CREATE TABLE places (name TEXT)"); c.commit(); c.close()
check("DbTest: a SQLite file that is there", json.loads(V("DbTest", "sqlite:" + good)), {"ok": True, "kind": "sqlite", "tables": 2, "error": ""})
r = json.loads(V("DbTest", "sqlite:nowhere.db", WORK))
check("DbTest: one that isn't there is said to be missing, and is not made by asking", (r["ok"], "isn't there yet" in r["error"], os.path.exists(os.path.join(WORK, "nowhere.db"))), (False, True, False))
r = json.loads(V("DbTest", "odbc:Driver={No Such Driver};Server=x;UID=me;PWD=hunter2"))
check("DbTest: an ODBC address that can't connect says why, without the password", (r["ok"], r["error"] != "", "hunter2" in r["error"]), (False, True, False))
check("DbTest: nonsense is an error, not a crash", json.loads(V("DbTest", "what is this"))["ok"], False)
drivers = json.loads(V("DbDrivers"))
check("DbSources lists the data sources, each with its driver", all(set(s) == {"name", "driver"} for s in json.loads(V("DbSources"))))
ODBC = "SQLite3" in drivers
if not ODBC:
    print("SKIP  ODBC: no SQLite ODBC driver here, so connecting and copying through ODBC are not tested")

# ---------------------------------------------------------------- the screen
PROJ = os.path.join(WORK, "proj")
os.mkdir(PROJ)
SALES = "odbc:Driver={ODBC Driver 99 for Nothing};Server=db1,1433;Database=Sales;UID=reports;PWD=?;Encrypt=yes"
with open(os.path.join(PROJ, "T.vmlproj"), "w") as f:
    f.write(f"# Visualised project\nName=T\nStartup=a.vml\nForm=a.vml\nDatabase=main=sqlite:data.db\nDatabase=sales={SALES}\n")
with open(os.path.join(PROJ, "a.vml"), "w") as f:
    f.write("@Window a\nTitle=a\n")
shutil.copy(good, os.path.join(PROJ, "data.db"))
get = lambda name, prop="Text": V("GetProperty", name, prop)
def put(name, value, prop="Text"):
    V("SetProperty", name, prop, value); settle()
    eng.run_script("DbCompose"); settle()                    # (what typing in the box, or clicking it, runs)
project = lambda: json.loads(V("ProjectInfo"))["databases"]

def inside():
    """Runs while the Databases window is open (it is modal)."""
    win = next(x for x in eng.windows if x.name == "Databases")
    try:
        inside_window(win)
    finally:
        win.widget.close()                                    # whatever happens, the test must not be left waiting

def inside_window(win):
    w = lambda name: eng.scopes[win.scope][name].widget
    items = lambda name: [w(name).item(i).text() for i in range(w(name).count())]
    check("the project's databases are listed, in the project's order", items("lstDb"), ["main", "sales"])
    check("it opens on the database asked for, its address exactly as kept", (get("txtDbName"), get("txtDbAddress")), ("sales", SALES))
    check("an address is read into the boxes", (get("txtDbServer"), get("txtDbDatabase"), get("txtDbUser"), get("txtDbPassword"), get("chkDbAsk", "IsChecked"), get("txtDbExtra"), get("rdoOdbc", "IsChecked")),
          ("db1,1433", "Sales", "reports", "", "true", "Encrypt=yes", "true"))
    check("a driver that isn't on this computer is kept, and said to be missing", "ODBC Driver 99 for Nothing" in get("lblDbResult") and "isn't on this computer" in get("lblDbResult"))
    put("txtDbServer", "db2")
    check("changing a box rewrites the address, keeping the absent driver and the rest", get("txtDbAddress"), SALES.replace("db1,1433", "db2"))
    put("chkDbWindows", "true", "IsChecked"); eng.run_script("DbCompose"); settle()
    check("Windows sign-in replaces the user and password", (get("txtDbAddress"), w("txtDbUser").isEnabled()),
          ("odbc:Driver={ODBC Driver 99 for Nothing};Server=db2;Database=Sales;Trusted_Connection=Yes;Encrypt=yes", False))
    put("chkDbWindows", "false", "IsChecked"); put("chkDbAsk", "false", "IsChecked"); eng.run_script("DbCompose"); settle()
    put("txtDbPassword", "pa;ss")
    check("a password can be saved if you insist, kept whole", get("txtDbAddress").endswith("UID=reports;PWD={pa;ss};Encrypt=yes"))
    eng.run_script("DbSave"); settle()
    check("saving one with its password in it says who can read it", ("readable by anyone" in get("lblDbResult"), "PWD={pa;ss}" in project()["sales"]), (True, True))
    check("the drivers and data sources of this computer are shown", (items("lstDrivers") == (drivers or ["(none found: ODBC isn't set up on this computer. See Get a driver.)"]), len(items("lstSources")) >= 1), (True, True))

    # a new SQLite database
    eng.run_script("DbNew"); settle()
    check("New offers a free name and a file in the project", (get("txtDbName"), get("txtDbAddress"), get("rdoSqlite", "IsChecked")), ("data2", "sqlite:data2.db", "true"))
    put("txtDbName", "notes"); put("txtDbFile", "notes.db")
    check("typing a file writes the address", get("txtDbAddress"), "sqlite:notes.db")
    w("txtDbFile").setText("typed.db"); settle()
    typed = get("txtDbAddress")
    w("rdoOdbc").click(); settle()
    w("txtDbServer").setText("srv"); settle()
    by_hand = get("txtDbAddress")
    w("rdoSqlite").click(); settle()
    w("txtDbFile").setText("notes.db"); settle()
    check("the boxes do this themselves as they are typed in and clicked", (typed, by_hand, get("txtDbAddress")), ("sqlite:typed.db", "odbc:Server=srv", "sqlite:notes.db"))
    eng.run_script("DbTestNow"); settle()
    check("Test says a file that isn't there yet will be made", "isn't there yet" in get("lblDbResult"))
    eng.run_script("DbSave"); settle()
    check("Save puts it in the project and the list", (project().get("notes"), items("lstDb")), ("sqlite:notes.db", ["main", "sales", "notes"]))
    V("SetProperty", "txtDbName", "Text", "9 lives"); eng.run_script("DbSave"); settle()
    check("a name that can't be used is refused", ("can't be used as a name" in get("lblDbResult"), "9 lives" in project()), (True, False))
    # being told how to get ODBC, and having the line to paste
    state = json.loads(V("DbOdbcState"))
    check("DbOdbcState says whether ODBC can be used here, and why not if not", (set(state) == {"ready", "module", "library", "drivers", "why"}, state["ready"] == bool(drivers) or state["drivers"] == 0), (True, True))
    if os.name != "nt":
        yes[0] = True; confirms.clear()
        eng.run_script("DbDriverHelp"); settle()
        line = V("ClipboardGet")
        check("Get a driver gives one line that sets ODBC up, and puts it on the clipboard",
              ("sudo apt install -y unixodbc odbc-mdbtools" in confirms[-1], line.startswith("sudo apt install -y unixodbc odbc-mdbtools libsqliteodbc"), "Copied" in get("lblDbResult")), (True, True, True))
        import vml.data as data_module
        real_import = __builtins__.__import__ if hasattr(__builtins__, "__import__") else __import__
        def no_odbc(name, *a, **k):
            if name == "pyodbc":
                raise ImportError("No module named 'pyodbc'")
            return real_import(name, *a, **k)
        import builtins
        builtins.__import__ = no_odbc
        try:
            gone = json.loads(V("DbOdbcState"))
            eng.run_script("DbDriverHelp"); settle()
            check("with ODBC missing altogether, it says what is missing and the line installs that too",
                  (gone["ready"], "pyodbc" in gone["why"], "isn't set up on this computer yet" in confirms[-1], V("ClipboardGet").endswith("pip install --break-system-packages pyodbc"),
                   [w("lstDrivers").item(i).text() for i in range(w("lstDrivers").count())][0].startswith("(none found")), (False, True, True, True, True))
        finally:
            builtins.__import__ = real_import
        eng.run_script("DbDriverHelp"); settle()
        check("once it is there, pressing Get a driver again fills the list without reopening", [w("lstDrivers").item(i).text() for i in range(w("lstDrivers").count())] == (drivers or ["(none found: ODBC isn't set up on this computer. See Get a driver.)"]))

    # starting from a kind of database, and a driver by its file
    w("txtDbServer").setText(""); settle()
    w("cboPreset").setCurrentIndex(1); settle()
    check("Start from SQL Server: its usual driver is named (and said to be missing if it is), with what it usually wants",
          (get("txtDbAddress").startswith("odbc:Driver={") and "SQL Server" in get("txtDbAddress") and get("txtDbAddress").endswith(";Encrypt=yes;TrustServerCertificate=no"),
           get("rdoOdbc", "IsChecked"), w("cboPreset").currentIndex(), "Server: its name" in get("lblDbResult")), (True, "true", 0, True))
    if "SQLite3" in drivers:
        w("cboPreset").setCurrentIndex(6); settle()
        check("Start from: a driver that is on this computer is the one chosen", (get("txtDbAddress"), get("cboDriver", "SelectedItem")), ("odbc:Driver={SQLite3}", "SQLite3"))
    lib = os.path.join(WORK, "libmydriver.so")
    open(lib, "wb").close()
    picked.append(lib)
    eng.run_script("DbDriverBrowse"); settle()
    if os.name == "nt":
        check("Browse: on Windows it explains that a driver has to be installed", "has to be installed" in said[-1])
    else:
        check("Browse: a driver can be chosen by its own file", (get("txtDbAddress"), "Using the driver in" in get("lblDbResult")), ("odbc:Driver={" + lib + "}", True))
        V("SetProperty", "txtDbName", "Text", "byfile"); eng.run_script("DbSave"); settle()
        V("SetProperty", "lstDb", "SelectedItem", "byfile"); eng.run_script("DbPick"); settle()
        check("Browse: saved and shown again, it is kept without a warning", (get("txtDbAddress"), "isn't on this computer" in get("lblDbResult")), ("odbc:Driver={" + lib + "}", False))
        yes[0] = True; eng.run_script("DbRemove"); settle()
    V("SetProperty", "lstDb", "SelectedItem", "main"); eng.run_script("DbPick"); settle()
    eng.run_script("DbTestNow"); settle()
    check("Test connects to the project's own SQLite file, found in the project's folder", get("lblDbResult"), "Connected (SQLite): 2 tables and views.")

    if ODBC:
        eng.run_script("DbNew"); settle()
        put("txtDbName", "remote"); put("rdoOdbc", "true", "IsChecked"); put("rdoSqlite", "false", "IsChecked")
        put("cboDriver", "SQLite3", "SelectedItem"); put("txtDbDatabase", good); eng.run_script("DbCompose"); settle()
        check("ODBC: choosing a driver and a database writes the address", get("txtDbAddress"), "odbc:Driver={SQLite3};Database=" + good)
        eng.run_script("DbTestNow"); settle()
        check("ODBC: Test connects through the driver", get("lblDbResult"), "Connected (ODBC): 2 tables and views.")
        eng.run_script("DbSave"); settle()
        answers.append("carried"); yes[0] = True
        eng.run_script("DbCopyAll"); settle()
        got = sqlite3.connect(os.path.join(PROJ, "carried.db"))
        check("ODBC: Copy brings every table and row into a SQLite file in the project",
              (got.execute("SELECT * FROM people ORDER BY name").fetchall(), [r[0] for r in got.execute("SELECT name FROM sqlite_master ORDER BY 1")]), ([("Ann", 41), ("Bob", 7)], ["people", "places"]))
        got.close()
        check("ODBC: and, when you say so, the project uses the copy under the same name", (project()["remote"], "2 tables and 2 rows copied into carried.db" in confirms[-1]), ("sqlite:carried.db", True))
        answers.append("carried")
        V("SetProperty", "txtDbName", "Text", "remote"); V("SetProperty", "txtDbAddress", "Text", "odbc:Driver={SQLite3};Database=" + good); eng.run_script("DbCopyAll"); settle()
        check("ODBC: a copy never overwrites a file that is there", "already in the project's folder" in get("lblDbResult"))

    V("SetProperty", "lstDb", "SelectedItem", "notes"); eng.run_script("DbPick"); settle()
    yes[0] = True
    eng.run_script("DbRemove"); settle()
    check("Remove takes it out of the project, after asking", ("notes" in project(), "The database itself isn't touched" in confirms[-1]), (False, True))
    win.widget.close()

def steps():
    eng.load(os.path.join(HERE, "designer", "designer.vml")); settle()
    eng.run_script("ProjectLoad", os.path.join(PROJ, "T.vmlproj")); settle()
    check("Settings has Databases (ODBC)", eng.find("SetDatabases") is not None)

    # before the screen opens: told once if ODBC can't be used here at all
    import builtins
    real_import = builtins.__import__
    def no_odbc(name, *a, **k):
        if name == "pyodbc":
            raise ImportError("No module named 'pyodbc'")
        return real_import(name, *a, **k)
    seen = {}
    def peek():
        win = next((x for x in eng.windows if x.name == "Databases"), None)
        if win is not None:
            seen["name"], seen["note"] = V("GetProperty", "txtDbName", "Text"), V("GetProperty", "lblDbResult", "Text")
            win.widget.close()
    builtins.__import__ = no_odbc
    try:
        yes[0] = True; confirms.clear(); said.clear()
        QTimer.singleShot(300, peek)
        eng.find("SetDatabases").action.trigger(); settle()
        if os.name == "nt":
            check("with no ODBC, choosing Databases says so before the screen opens", (len(said), "ODBC isn't available" in said[0]), (1, True))
        else:
            check("with no ODBC, choosing Databases says so before the screen opens, with the line that sets it up",
                  (len(confirms), "ODBC isn't set up on this computer yet" in confirms[0], V("ClipboardGet").startswith("sudo apt install -y unixodbc"), V("ClipboardGet").endswith("pyodbc")), (1, True, True, True))
        check("the screen still opens, for SQLite, and says ODBC is missing; from the menu it is on no database in particular",
              (seen.get("name"), "ODBC isn't set up on this computer yet" in seen.get("note", "")), ("", True))
        confirms.clear(); said.clear(); seen.clear()
        QTimer.singleShot(300, peek)
        eng.find("SetDatabases").action.trigger(); settle()
        check("it is said once, not every time", (confirms, said, "name" in seen), ([], [], True))
    finally:
        builtins.__import__ = real_import
    eng.store.set_setting("odbc_told", "")

    QTimer.singleShot(300, inside)
    eng.run_script("ProjectEditDatabase", "sales"); settle()         # (what a double-click on it in the project tree runs)
    saved = open(os.path.join(PROJ, "T.vmlproj")).read()
    check("what was done is in the project file", ("Database=main=sqlite:data.db" in saved, "Database=notes" in saved), (True, False))

    # ---------------------------------------------------------------- importing a project whose Access data can't be read
    try:
        import pyodbc
        real = pyodbc.drivers
        pyodbc.drivers = lambda: [d for d in real() if "mdb" not in d.lower() and "access" not in d.lower()]
    except ImportError:
        pass
    src = os.path.join(WORK, "Stock")
    os.mkdir(src)
    for f in ("Stock.vbp", "frmStock.frm", "frmAbout.frm"):
        shutil.copy(os.path.join(HERE, "tests", "vb6", f), src)
    with open(os.path.join(src, "stock.mdb"), "wb") as f:
        f.write(b"\x00\x01\x00\x00Standard Jet DB\x00" + b"\x00" * 200)
    picked.append(os.path.join(src, "Stock.vbp"))
    started = []
    eng.cmd_FolderDialog = lambda title="", start="": (started.append(str(start)), os.path.join(WORK, "Stock-new"))[1]
    yes[0] = False
    eng.store.set_setting("dirty", "false")
    confirms.clear()
    eng.find("FileImportProject_VB6").action.trigger(); settle()
    check("import: Access data with no driver for it is said at once, with what to do",
          (len(confirms), "keeps its data in Access (stock.mdb)" in confirms[0], "no ODBC driver for Access" in confirms[0], "import the project again" in confirms[0]), (1, True, True, True))
    check("import: and everything else still came across", json.loads(V("ProjectInfo"))["name"], "Stock")
    check("import: the folder to put it in is asked for starting where the original is", started, [src])
    os.remove(os.path.join(src, "stock.mdb"))
    picked.append(os.path.join(src, "Stock.vbp"))
    eng.cmd_FolderDialog = lambda title="", start="": os.path.join(WORK, "Stock-again")
    eng.store.set_setting("dirty", "false"); said.clear(); confirms.clear()
    eng.find("FileImportProject_VB6").action.trigger(); settle()
    check("import: Access data the code names but that isn't with the project is said at once too",
          ([m for m in said if "isn't with the project: stock.mdb" in m and "import the project again" in m] != [], confirms), (True, []))
    check("nothing was logged that looks like a password", [l for l in logged if "hunter2" in l or "s3cret" in l or "pa;ss" in l], [])
    print(f"\n{sum(ok)}/{len(ok)} passed")
    app.quit()

QTimer.singleShot(200, steps)
app.exec()
sys.exit(0 if all(ok) else 1)
