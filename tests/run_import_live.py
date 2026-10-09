"""What an imported app does without being rewritten: the plain steps of its Basic are made to run (open a form, close
this one, a message, a simple setting), grids and lists that were bound to a data control ask the database themselves,
and Access data is copied into SQLite where this computer can read Access. Nothing else is made to run."""
import json, os, shutil, sqlite3, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("VML_PREFS", os.path.join(tempfile.mkdtemp(prefix="vml-prefs-"), "prefs.json"))
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from vml.engine import Engine

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = tempfile.mkdtemp(prefix="vml-live-")
ok = []

def check(label, got, want=True):
    passed = got == want
    ok.append(passed)
    print(f"{'PASS' if passed else 'FAIL'}  {label}" + ("" if passed else f": got {got!r}, wanted {want!r}"))

eng = Engine()
eng.licence_override = "pro"
app = QApplication.instance()
app.setQuitOnLastWindowClosed(False)
said = []
eng.cmd_InfoDialog = lambda msg, title="Information": said.append((str(msg), str(title)))
V = eng.vml

def settle(n=8):
    for _ in range(n):
        app.processEvents()

# ---------------------------------------------------------------- the steps themselves
rt = eng.lua_state("steps-test")
rt.execute("package.path = ... .. '/?.lua;' .. package.path", os.path.join(HERE, "designer", "importers", "lib").replace("\\", "/"))
steps_of = rt.eval('''function(text, net, closing, alone, opening)
    local kit = require("importkit")
    local ctx = { form = "frmMain", net = net, closing = closing, opening = opening, forms = not alone and { frmabout = "frmAbout" } or nil,
        controls = { cmdok = { name = "cmdOK", kind = "Button", text = "Content" }, lblstate = { name = "lblState", kind = "TextBlock", text = "Text" },
                     ["cmdqty(1)"] = { name = "cmdQty_1", kind = "Button", text = "Content" }, mnuexit = { name = "mnuExit", kind = "MenuItem" } } }
    local out, n = kit.basic_steps(kit.lines(text), ctx)
    local live = {}
    for _, line in ipairs(out) do if line:sub(1, 2) ~= "--" then live[#live + 1] = (line:gsub("%s+%-%- was: .*$", "")) end end
    return table.concat(live, "\\n") .. "|" .. n .. "|" .. #out
end''')

def steps(body, net=False, closing=False, alone=False, opening=False):
    text = "Private Sub x_Click()\n" + body + "\nEnd Sub"
    live, n, lines = str(steps_of(text, net, closing, alone, opening)).rsplit("|", 2)
    assert int(lines) == len(text.splitlines())            # a line out for every line in: nothing is lost
    return live.split("\n") if live else []

check("showing a form opens it, modal if it was",
      steps("frmAbout.Show\nfrmAbout.Show vbModal, Me\nfrmAbout.Show 1\nCall frmOther.Show"),
      ['Vml("FormOpen", "frmAbout")', 'Vml("FormOpenModal", "frmAbout")', 'Vml("FormOpenModal", "frmAbout")'])
check("closing this form and another form", steps("Unload frmAbout\nUnload Me"), ['Vml("CloseForm", "frmAbout")', 'Vml("CloseSelf")'])
check("hiding is not closing: Hide is left alone, and nothing after it is taken for certain", steps("Me.Hide\nfrmAbout.Show\nMe.Show"), [])
check("nor is another form's Hide", steps("frmAbout.Hide"), [])
check("the handler that opens a form may not close it or end the app, though its other plain steps run",
      steps('cmdOK.Enabled = False\nUnload Me\nEnd', opening=True), ['Vml("SetProperty", "cmdOK", "IsEnabled", "false")'])
check(".NET: the same in a Load handler", steps('Me.Text = "Shop"\nMe.Close()\nApplication.Exit()', net=True, opening=True), ['Vml("SetProperty", "frmMain", "Title", "Shop")'])
check("End ends the app", steps("End"), ['Vml("AppExit")'])
check("a message whose words are written out is shown, title and all; one that is worked out is left",
      steps('MsgBox "Saved: ""all"" done." & vbCrLf & "Bye", vbInformation, "Shop"\nMsgBox "Total " & n\nMsgBox Err.Description'),
      ['Vml("InfoDialog", "Saved: \\"all\\" done.\\nBye", "Shop")'])
check("simple settings: text, enabled, visible, the window's caption, one of a control array",
      steps('lblState.Caption = "Ready"   \' tell them\ncmdOK.Enabled = False\ncmdQty(1).Visible = True\nMe.Caption = "Shop"\nCaption = "Shop"'),
      ['Vml("SetProperty", "lblState", "Text", "Ready")', 'Vml("SetProperty", "cmdOK", "IsEnabled", "false")', 'Vml("SetProperty", "cmdQty_1", "IsVisible", "true")',
       'Vml("SetProperty", "frmMain", "Title", "Shop")', 'Vml("SetProperty", "frmMain", "Title", "Shop")'])
check("a setting that is worked out, or on something unknown, is left", steps('lblState.Caption = Format(n)\ntxtNope.Text = "x"\nmnuExit.Enabled = False\ncmdOK.Show'), [])
check("nothing inside an If, a loop, a With or a Select is made to run",
      steps('If n > 3 Then\n    frmAbout.Show\nEnd If\nFor i = 1 To 3\n    MsgBox "hi"\nNext i\nWith cmdOK\n    .Enabled = False\nEnd With\nSelect Case n\n    Case 1\n        Unload Me\nEnd Select\nDo While x\n  End\nLoop'), [])
check("nor anything after a line that might have left the routine", steps('If lst.ListIndex < 0 Then Exit Sub\nfrmAbout.Show'), [])
check("nor after a block that might have", steps('If Not ok Then\n    Exit Sub\nEnd If\nfrmAbout.Show'), [])
check("a step before such a line still runs, and Exit Sub is honoured", steps('frmAbout.Show\nExit Sub\nMsgBox "never"'), ['Vml("FormOpen", "frmAbout")', "do return end"])
check("an error handler below Exit Sub is not run as if it were the next step",
      steps('On Error GoTo Oops\ncmdOK.Enabled = False\nExit Sub\nOops:\nMsgBox "It failed"'), ['Vml("SetProperty", "cmdOK", "IsEnabled", "false")', "do return end"])
check("two steps on one line, and a step carried over lines, are left alone", steps('MsgBox "a": MsgBox "b"\nMsgBox "long" & _\n    "er"\nUnload Me'), ['Vml("CloseSelf")'])
check("nothing in the handler of the form closing is made to run", steps('MsgBox "Goodbye"\nEnd', closing=True), [])
check("with one form on its own, a name that isn't a control is taken to be a form", steps("frmAbout.Show\ncmdOK.Show\nfrmWhatever.Show", alone=True), ['Vml("FormOpen", "frmAbout")', 'Vml("FormOpen", "frmWhatever")'])
check(".NET: a form made with New, in a Dim or a Using, and shown",
      steps("Dim f As New frmAbout\nf.ShowDialog()\nUsing g As New frmAbout\n    g.ShowDialog(Me)\nEnd Using\nMy.Forms.frmAbout.Show()", net=True),
      ['Vml("FormOpenModal", "frmAbout")', 'Vml("FormOpenModal", "frmAbout")', 'Vml("FormOpen", "frmAbout")'])
check(".NET: messages, Me.Text, Me.Close, Application.Exit",
      steps('MessageBox.Show("Saved.", "Shop", MessageBoxButtons.OK)\nMsgBox("Hello")\nMe.Text = "Shop"\nlblState.Text = "Done"\nMe.Close()', net=True),
      ['Vml("InfoDialog", "Saved.", "Shop")', 'Vml("InfoDialog", "Hello")', 'Vml("SetProperty", "frmMain", "Title", "Shop")', 'Vml("SetProperty", "lblState", "Text", "Done")', 'Vml("CloseSelf")'])
check(".NET: Return leaves, and nothing in a Try is made to run", steps('Try\n    Me.Close()\nCatch ex As Exception\nEnd Try\nMsgBox("after")', net=True), [])

# ---------------------------------------------------------------- copying a table from one database to another
a, b = os.path.join(WORK, "a.db"), os.path.join(WORK, "b.db")
c = sqlite3.connect(a)
c.execute("CREATE TABLE \"order lines\" (id INTEGER, item TEXT, price REAL, made DATETIME, pic BLOB)")
c.executemany("INSERT INTO \"order lines\" VALUES (?,?,?,?,?)", [(i, f"item {i}", i * 1.5, "2001-02-03 04:05:06", b"\x00\x01") for i in range(1203)])
c.execute("CREATE VIEW dear AS SELECT * FROM \"order lines\" WHERE price > 5")
c.commit(); c.close()
V("DbOpen", "src", "sqlite:" + a); V("DbOpen", "dst", "sqlite:" + b)
check("DbTables can leave the views out", (json.loads(V("DbTables", "src")), json.loads(V("DbTables", "src", "tables"))), (["dear", "order lines"], ["order lines"]))
check("DbCopyTable copies a table, its columns and every row", V("DbCopyTable", "src", "order lines", "dst"), 1203)
got = sqlite3.connect(b)
check("the copy has the same columns, types and values",
      (got.execute("SELECT sql FROM sqlite_master").fetchone()[0], got.execute("SELECT * FROM \"order lines\" WHERE id = 1202").fetchone()),
      ('CREATE TABLE "order lines" ("id" INTEGER, "item" TEXT, "price" REAL, "made" DATETIME, "pic" BLOB)', (1202, "item 1202", 1803.0, "2001-02-03 04:05:06", b"\x00\x01")))
got.close()
check("copying over a table that is there is refused, and says so", (V("DbCopyTable", "src", "order lines", "dst"), "already a table" in V("DbError")), ("", True))
check("it can be given a new name", (V("DbCopyTable", "src", "dear", "dst", "dear_ones"), json.loads(V("DbTables", "dst"))), (1199, ["dear_ones", "order lines"]))
check("a table that isn't there is an error, not a crash", (V("DbCopyTable", "src", "nope", "dst"), V("DbError") != ""), ("", True))
if "SQLite3" in json.loads(V("DbDrivers")):
    V("DbOpen", "viaodbc", "odbc:Driver={SQLite3};Database=" + a)
    check("ODBC: a table comes out of an ODBC database into SQLite", V("DbCopyTable", "viaodbc", "order lines", "dst", "from_odbc"), 1203)
    got = sqlite3.connect(b)
    check("ODBC: with usable types and the same values", got.execute("SELECT id, item, price FROM from_odbc WHERE id = 7").fetchone(), (7, "item 7", 10.5))
    got.close(); V("DbClose", "viaodbc")
else:
    print("SKIP  ODBC: no SQLite ODBC driver here")
V("DbClose", "src"); V("DbClose", "dst")

# ---------------------------------------------------------------- a Visual Basic project with a data control
SRC = os.path.join(WORK, "Stock")
os.mkdir(SRC)
for f in ("Stock.vbp", "frmStock.frm", "frmAbout.frm"):
    shutil.copy(os.path.join(HERE, "tests", "vb6", f), SRC)
c = sqlite3.connect(os.path.join(SRC, "stock.db"))                # the data, already as SQLite beside the project
c.execute("CREATE TABLE items (name TEXT, price REAL)")
c.executemany("INSERT INTO items VALUES (?,?)", [("Tea", 1.5), ("Jam", 2.75), ("Honey", 4.2)])
c.commit(); c.close()
with open(os.path.join(SRC, "old.mdb"), "wb") as f:               # and something that only says it is an Access file
    f.write(b"\x00\x01\x00\x00Standard Jet DB\x00" + b"\x00" * 200)
OUT = os.path.join(WORK, "Stock-new")
raw = eng.cmd_ImportProject("VB6", os.path.join(SRC, "Stock.vbp"), OUT)
p = json.loads(raw or "{}")
vml = open(os.path.join(OUT, "frmStock.vml"), encoding="utf-8").read()
notes = open(os.path.join(OUT, "IMPORT-NOTES.txt"), encoding="utf-8").read()
proj = open(os.path.join(OUT, "Stock.vmlproj"), encoding="utf-8").read().splitlines()
check("the project comes across, with its SQLite database named", (p.get("forms"), "Database=stock=sqlite:stock.db" in proj), (["frmStock.vml", "frmAbout.vml"], True))
def prop(control, key):
    block = vml.split(f"\n@{control}\n", 1)[1].split("\n\n", 1)[0] if f"\n@{control}\n" in vml else ""
    return next((ln.split("=", 1)[1] for ln in block.splitlines() if ln.startswith(key + "=")), None)
check("a grid bound to a data control asks for that table itself", (prop("DataGrid grdStock", "ItemsSource"), prop("DataGrid grdStock", "Database")), ('SELECT * FROM "items"', "stock"))
check("a bound list asks for its field", prop("ListBox lstNames", "ItemsSource"), 'SELECT "name" FROM "items" ORDER BY 1')
check("a data control that held a query hands the query on", prop("ComboBox cboDear", "ItemsSource"), 'SELECT "name" FROM (SELECT name, price FROM items WHERE price > 2) ORDER BY 1')
check("the notes say what was bound, and what could not be", ("grdStock (datStock: items)" in notes, "come across unfilled: txtPrice (price)" in notes, "a grid comes across empty" in notes), (True, True, False))
check("an Access file named in the code but not with the project is asked for", "names the Access database stock.mdb, which isn't with the project" in notes)
check("one that is there but can't be read is reported, in the notes and the summary, and the import carries on",
      ("old.mdb" in notes, "NOT brought across" in p.get("summary", ""), "old.mdb" in p.get("summary", ""), os.path.exists(os.path.join(OUT, "old.db"))), (True, True, True, False))
check("the summary counts the steps made to run, and still says the rest does not", ("plain steps of the code" in p.get("summary", ""), "The rest of the code does not run" in p.get("summary", "")), (True, True))

def run():
    eng.load(eng.open_project(os.path.join(OUT, "Stock.vmlproj"))); settle(20)
    win = next(x for x in eng.windows if x.name == "frmStock" and x.widget.isVisible())
    w = lambda name: eng.scopes[win.scope][name].widget
    grid, lst, combo = w("grdStock"), w("lstNames"), w("cboDear")
    check("run: the grid fills from the database", (grid.cols, sorted((r[0], float(r[1])) for r in grid.data)), (["name", "price"], [("Honey", 4.2), ("Jam", 2.75), ("Tea", 1.5)]))
    check("run: so do the list and the combo box", ([lst.item(i).text() for i in range(lst.count())], [combo.itemText(i) for i in range(combo.count())]), (["Honey", "Jam", "Tea"], ["Honey", "Jam"]))
    check("run: Form_Load's plain steps ran, and stopped at Exit Sub", (win.widget.windowTitle(), said), ("Stock", []))

    def in_about():
        about = next((x for x in eng.windows if x.name == "frmAbout" and x.widget.isVisible()), None)
        seen.append(about is not None and about.widget.isModal())
        if about is not None:
            eng.scopes[about.scope]["cmdOK"].widget.click()        # its OK button was Unload Me
    seen = []
    QTimer.singleShot(200, in_about)
    w("cmdAbout").click(); settle()
    check("run: the About button opens the About box, modal, and its OK button closes it",
          (seen, [x.name for x in eng.windows if x.name == "frmAbout" and x.widget.isVisible()]), ([True], []))
    w("cmdCount").click(); settle()
    check("run: a handler that starts with an If does nothing rather than something wrong", said, [])
    w("cmdClose").click(); settle()
    check("run: a Close button behind a test is left for a person to rewrite", win.widget.isVisible(), True)
    win.widget.close(); settle()
    check("run: closing the form shows no message the original only showed on purpose", said, [])
    winforms()

def winforms():
    # ---------------------------------------------------------------- Windows Forms (Visual Basic .NET)
    r = eng.run_importer("WinForms", "ImportForm", os.path.join(HERE, "tests", "winforms", "SignIn.Designer.vb"), "")
    text = r.get("vml", "")
    body = lambda name: text.split(f"<<END_{name.upper()}\n")[1].split(f"\nEND_{name.upper()}")[0].splitlines()
    check(".NET form: Cancel's Me.Close() runs", [ln.split("   -- was: ")[0] for ln in body("Cancel_OnClick") if not ln.startswith("--")], ['Vml("CloseSelf")'])
    check(".NET form: OK's handler, which tests first, is left whole as comments", all(ln.startswith("--") for ln in body("OK_OnClick")))
    check(".NET form: the notes say so", any("plain steps, which were translated and do run: 1 line in 1 script" in n for n in r.get("notes", [])))
    c = eng.run_importer("WinForms", "ImportForm", os.path.join(HERE, "tests", "winforms", "OrderForm.Designer.cs"), "")
    scripts = [ln for part in c.get("vml", "").split("<<END_")[1:] for ln in part.split("\nEND_")[0].splitlines()[1:]]
    check("C# is kept whole as comments: none of it is made to run", (len(scripts) > 5, all(ln.startswith("--") for ln in scripts)), (True, True))
    print(f"\n{sum(ok)}/{len(ok)} passed")
    app.quit()

QTimer.singleShot(200, run)
app.exec()
sys.exit(0 if all(ok) else 1)
