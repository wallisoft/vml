"""Projects: the project file, modules, the shared Project table, databases named by the project, the designer's
project panel, running and exporting a whole project, and importing a Visual Studio project."""
import json, os, shutil, sqlite3, subprocess, sys, tarfile, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("VML_PREFS", os.path.join(tempfile.mkdtemp(prefix="vml-prefs-"), "prefs.json"))   # never the real settings
from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from vml.engine import Engine
from vml.projects import Project, project_for

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = Path(tempfile.mkdtemp(prefix="vml-projects-")).resolve()
DEMO = WORK / "demo"
shutil.copytree(os.path.join(HERE, "tests", "project"), DEMO)
db = sqlite3.connect(DEMO / "stock.db")
db.execute("CREATE TABLE stock (item TEXT, qty INTEGER)")
db.executemany("INSERT INTO stock VALUES (?, ?)", [("bolts", 40), ("nuts", 12), ("widgets", 3)])
db.commit(); db.close()
ok = []

def check(label, got, want=True):
    passed = got == want
    ok.append(passed)
    print(f"{'PASS' if passed else 'FAIL'}  {label}: {got!r}" + ("" if passed else f" (wanted {want!r})"))

# ---------------------------------------------------------------- the project file
p = Project.load(DEMO / "Demo.vmlproj")
check("a project file names the app, its forms, modules, databases and where it starts",
      (p.name, p.startup, p.forms, p.modules, p.databases), ("Demo", "main.vml", ["main.vml", "pick.vml"], ["helpers.lua"], {"stock": "sqlite:stock.db"}))
(WORK / "odd.vmlproj").write_text('Name=Odd\nForm="sub\\\\a.vml"\nForm=sub/a.vml\n\n# a comment\nStartup=b.vml\nnonsense line\n')
odd = Project.load(WORK / "odd.vmlproj")
check("it is forgiving: Windows slashes, quotes, repeats, a start-up form not listed", (odd.forms, odd.startup), (["b.vml", "sub/a.vml"], "b.vml"))
odd.save()
check("saving and loading again gives the same project", Project.load(WORK / "odd.vmlproj").info(), odd.info())
check("a form knows which project it belongs to", (project_for(DEMO / "pick.vml").name, project_for(WORK / "odd.vmlproj")), ("Demo", None))

eng = Engine()
app = QApplication.instance()
app.setQuitOnLastWindowClosed(False)      # this test closes every window part-way through, and carries on
said = []
eng.cmd_InfoDialog = lambda msg, title="": said.append(str(msg))
eng.cmd_ErrorDialog = lambda msg, title="": said.append("ERROR " + str(msg))

def settle(n=8):
    for _ in range(n):
        app.processEvents()

w = lambda name: eng.find(name).widget
get = lambda name, prop: eng.cmd_GetProperty(name, prop)
items = lambda name: [w(name).item(i).text() for i in range(w(name).count())]

def steps():
    # ---------------------------------------------------------------- running a project
    start = eng.open_project(DEMO / "Demo.vmlproj")
    check("opening a project gives its start-up form", start, str(DEMO / "main.vml"))
    eng.load(start); settle()
    check("a module's functions are there in a form's scripts, with no require", get("lblHello", "Text"), "HELLO! from Demo")
    check("a list with no Database named asks the project's main database", items("lstItems"), ["bolts", "nuts", "widgets"])
    w("lstItems").setCurrentRow(1); w("btnQty").click(); settle()
    check("a module can use the project's database by name", get("lblQty", "Text"), "nuts: 12")

    def in_pick():
        pick = [x for x in eng.windows if x.name == "Pick" and x.widget.isVisible()]
        seen["who"] = eng.scopes[pick[0].scope]["lblWho"].widget.text() if pick else "(no Pick form)"
        if pick:
            eng.scopes[pick[0].scope]["btnOK"].widget.click()
    seen = {}
    QTimer.singleShot(400, in_pick)
    w("btnPick").click(); settle()
    check("FormOpen takes a form's name; the module and the Project table are in that form too", seen.get("who"), "FOR! steve (loads 1)")
    check("what the second form put in the Project table, the first can read", get("lblHello", "Text"), "picked: widgets / shared: widgets")
    check("each form still has its own Lua state (the module loaded once in each)", eng.lua_state(str(DEMO / "main.vml")).globals().loads, 1)
    eng.stop_project(); settle()
    check("stopping a project closes its forms and its databases", ([x.name for x in eng.windows], eng.project, list(eng.databases)), ([], None, []))

    # a form run on its own (double-clicked, or an exported app's main form) brings its project with it
    eng.load(DEMO / "main.vml"); settle()
    check("a form opened on its own finds its project, so its modules still work", (eng.project.name, get("lblHello", "Text")), ("Demo", "HELLO! from Demo"))
    eng.stop_project(); settle()

    # from the command line
    shot = WORK / "cli.png"
    r = subprocess.run([sys.executable, os.path.join(HERE, "vml.py"), str(DEMO / "Demo.vmlproj"), "--shot", str(shot)],
                       capture_output=True, text=True, timeout=60, env=dict(os.environ, QT_QPA_PLATFORM="offscreen"))
    check("vml Demo.vmlproj runs the project from its start-up form", (shot.is_file(), "module" in r.stderr and "error" in r.stderr.lower()), (True, False))

    # ---------------------------------------------------------------- the designer
    eng.licence_override = "pro"
    eng.cmd_ConfirmDialog = lambda msg, title="": True
    eng.load(os.path.join(HERE, "designer", "designer.vml")); settle()
    check("with no project open, the panel is hidden and F5 is Preview", (eng.find("ProjectPane").host.isVisible(), get("ViewPreview", "Text")), (False, "Preview"))
    check("Help shows the version", get("HelpVersion", "Text"), "Visualised " + __import__("vml").__version__)
    new = WORK / "fresh"
    new.mkdir()
    made = eng.cmd_ProjectNew(str(new / "Fresh"))
    eng.run_script("RefreshProject"); settle()
    check("a new project is a .vmlproj file, and the panel appears", (made, (new / "Fresh.vmlproj").is_file(), eng.find("ProjectPane").host.isVisible(), get("ProjTitle", "Text")),
          (str(new / "Fresh.vmlproj"), True, True, "Project: Fresh"))
    check("F5 now runs the project", (get("ViewPreview", "Text"), "Fresh" in w("Designer").windowTitle()), ("Run Project", True))
    eng.run_script("Preview"); settle()
    check("running a project with no forms explains what to do", "no forms yet" in said[-1])

    b = eng.cmd_AddDesignControl("Button", 24, 24)
    eng.cmd_SetDesignScript(b, "OnClick", "Lua", f'Vml("SetProperty", "{b}", "Content", Twice("ab"))')
    eng.cmd_SetProperty("Surface", "FormName", "First")
    eng.store.set_setting("current_file", str(new / "First.vml"))
    eng.run_script("FileSave"); settle()
    tree = lambda: get("ProjTree", "Items").split(",")
    check("saving a form into the project's folder adds it, as the start-up form", tree(), ["Forms/First.vml  (start-up)"])
    eng.cmd_ProjectAdd("module", "tools.lua")
    (new / "tools.lua").write_text("function Twice(s) return s .. s end\n")
    eng.cmd_ProjectDatabase("main", "sqlite:fresh.db")
    outside = WORK / "elsewhere.vml"
    shutil.copy(DEMO / "pick.vml", outside)
    added = eng.cmd_ProjectAdd("form", str(outside))
    eng.run_script("RefreshProject"); settle()
    check("a form from outside the folder is copied in", (added, (new / "elsewhere.vml").is_file()), (str(new / "elsewhere.vml"), True))
    check("the tree shows forms, modules and databases", tree(), ["Forms/First.vml  (start-up)", "Forms/elsewhere.vml", "Modules/tools.lua", "Databases/main"])
    check("a tree item leads back to its file", (eng.cmd_ProjectPath("Forms/First.vml  (start-up)"), eng.cmd_ProjectPath("Modules/tools.lua"), eng.cmd_ProjectPath("Forms")),
          (str(new / "First.vml"), str(new / "tools.lua"), ""))

    # the form on screen runs as designed, saved or not; modules come from the project
    eng.cmd_SetProperty(b, "Width", "222")                                # not saved
    eng.run_script("Preview"); settle()
    run = [x for x in eng.windows if x.name == "First" and x.widget.isVisible()]
    check("F5 runs the project from its start-up form", len(run), 1)
    rb = eng.scopes[run[0].scope][b].widget
    rb.click(); settle()
    check("...as it is on screen (unsaved changes and all), with the project's modules", (rb.width(), rb.text()), (222, "abab"))
    (new / "tools.lua").write_text("function Twice(s) return s .. '+' .. s end\n")
    eng.run_script("Preview"); settle()
    run2 = [x for x in eng.windows if x.name == "First" and x.widget.isVisible()]
    rb = eng.scopes[run2[0].scope][b].widget
    rb.click(); settle()
    check("running again closes the last run and picks up an edited module", (len(run2), rb.text()), (1, "ab+ab"))

    # one form of the project, previewed on its own, still has the project's modules; so does its web page
    eng.stop_project(); settle()
    eng.run_script("PreviewForm"); settle()
    one = [x for x in eng.windows if x.name == "First" and x.widget.isVisible()]
    ob = eng.scopes[one[0].scope][b].widget
    ob.click(); settle()
    check("Shift+F5 previews just this form, with the project's modules there", (len(one), ob.text()), (1, "ab+ab"))
    page = eng._export_html("Surface", str(WORK / "first.html"))
    check("its web page carries the project's modules too", "function Twice(s)" in open(page, encoding="utf-8").read())
    check("the designer knows what is inside the project's folder, whichever way the slashes lean",
          (eng.cmd_ProjectInFolder(str(new / "x.vml")), eng.cmd_ProjectInFolder(str(new).replace("/", os.sep) + os.sep + "y.vml"), eng.cmd_ProjectInFolder(str(WORK / "x.vml")), eng.cmd_ProjectInFolder("")),
          (True, True, False, False))

    # double-click in the tree: a form opens on the surface
    eng.store.set_setting("dirty", "false")
    eng.cmd_SetProperty("ProjTree", "SelectedItem", "Forms/elsewhere.vml")
    eng.run_script("ProjOpenItem"); settle()
    check("double-clicking a form in the tree opens it for design", (eng.store.get_setting("current_file"), get("Surface", "FormName")), (str(new / "elsewhere.vml"), "Pick"))
    eng.run_script("ProjectSetStartup"); settle()
    check("Set as Start-up Form moves the mark", tree()[:2], ["Forms/First.vml", "Forms/elsewhere.vml  (start-up)"])

    # the module editor is a form too
    def edit_module():
        ed = [x for x in eng.windows if x.name == "ModuleEditor" and x.widget.isVisible()]
        if not ed:
            return
        sc = eng.scopes[ed[0].scope]
        seen["module_text"] = sc["txtModule"].widget.toPlainText()
        seen["module_title"] = ed[0].widget.windowTitle()
        seen["module_edge"] = ed[0].widget.edge_name()
        sc["txtModule"].widget.setPlainText("function Twice(s) return 'edited' end\n")
        sc["btnModSave"].widget.click()
    QTimer.singleShot(400, edit_module)
    eng.cmd_SetProperty("ProjTree", "SelectedItem", "Modules/tools.lua")
    eng.run_script("ProjOpenItem"); settle()
    check("double-clicking a module opens it in the module editor", (seen.get("module_title"), "Twice" in seen.get("module_text", ""), seen.get("module_edge")), ("Module - tools.lua", True, "#1e3a8a"))
    check("...and Save writes the file", (new / "tools.lua").read_text(), "function Twice(s) return 'edited' end\n")

    eng.cmd_SetProperty("ProjTree", "SelectedItem", "Forms/First.vml")
    eng.run_script("ProjectRemove"); settle()
    check("Remove takes a form out of the project and leaves its file alone", (tree()[0], (new / "First.vml").is_file()), ("Forms/elsewhere.vml  (start-up)", True))

    # exporting: the whole project travels
    fake = WORK / "runtime"
    fake.mkdir()
    (fake / "vml").write_text("#!/bin/sh\n")
    eng._runtime = lambda platform: fake
    (new / "fresh.db").write_bytes(b"SQLite format 3\x00")
    out = eng.cmd_ExportApp("linux", str(WORK / "Fresh-linux.tar.gz")); settle()
    names = sorted(tarfile.open(out).getnames())
    check("an exported app holds every form, module and local database, and the project under the app's name", names,
          ["Fresh", "Fresh/Fresh", "Fresh/Fresh.vmlproj", "Fresh/README.txt", "Fresh/elsewhere.vml", "Fresh/fresh.db", "Fresh/tools.lua"])

    eng.run_script("ProjectClose"); settle()
    check("closing the project hides the panel again", (eng.find("ProjectPane").host.isVisible(), get("ViewPreview", "Text"), eng.cmd_ProjectInfo()), (False, "Preview", ""))

    # ---------------------------------------------------------------- importing a Visual Studio project
    vs = WORK / "vs" / "Shop"
    (vs / "My Project").mkdir(parents=True)
    (vs / "bin" / "Debug").mkdir(parents=True)
    for f in os.listdir(os.path.join(HERE, "tests", "winforms")):
        shutil.copy(os.path.join(HERE, "tests", "winforms", f), vs / f)
    (vs / "Pricing.vb").write_text("Module Pricing\n    Public Function Vat(ByVal net As Decimal) As Decimal\n        Return net * 0.2D\n    End Function\nEnd Module\n")
    (vs / "bin" / "Debug" / "Old.Designer.vb").write_text("' build output: must be ignored\n")
    (vs / "My Project" / "Application.myapp").write_text("<MyApplicationData><MainForm>SignIn</MainForm></MyApplicationData>")
    (vs / "My Project" / "AssemblyInfo.vb").write_text("' assembly info\n")
    (vs / "Shop.vbproj").write_text('''<?xml version="1.0" encoding="utf-8"?>
<Project ToolsVersion="4.0" xmlns="http://schemas.microsoft.com/developer/msbuild/2003">
  <PropertyGroup><AssemblyName>Shop</AssemblyName><StartupObject>Shop.My.MyApplication</StartupObject></PropertyGroup>
  <ItemGroup>
    <Compile Include="SignIn.vb" /><Compile Include="SignIn.Designer.vb"><DependentUpon>SignIn.vb</DependentUpon></Compile>
    <Compile Include="Pricing.vb" /><Compile Include="My Project\\AssemblyInfo.vb" />
  </ItemGroup>
</Project>
''')
    sdb = sqlite3.connect(vs / "Shop.s3db"); sdb.execute("CREATE TABLE prices (item TEXT)"); sdb.commit(); sdb.close()
    (vs / "notes.txt").write_text("not a database")
    target = WORK / "shop-visualised"
    eng.licence_override = "community"
    check("importing a project is part of Pro", (eng.cmd_ImportProject("vs", str(vs / "Shop.vbproj"), str(target)), "Visualised Pro" in said[-1]), ("", True))
    eng.licence_override = "pro"
    inside = json.loads(eng.cmd_ImportProject("vs", str(vs / "Shop.vbproj"), str(vs)) or "{}")
    again = json.loads(eng.cmd_ImportProject("vs", str(vs / "Shop.vbproj"), str(vs)) or "{}")
    check("given the Visual Studio project's own folder, it goes into a new folder inside it (and a second time, another)",
          (Path(inside.get("project", "x")).parent.name, Path(again.get("project", "x")).parent.name), ("Shop-visualised", "Shop-visualised-2"))
    before = sorted(str(x.relative_to(vs)) for x in vs.rglob("*"))
    result = json.loads(eng.cmd_ImportProject("vs", str(vs / "Shop.vbproj"), str(target)))
    check("every form in the project comes across (VB and C# alike), and nothing from bin/", sorted(result["forms"]), ["OrderForm.vml", "SignIn.vml"])
    check("the start-up form is the one Visual Studio started with", result["startup"], "SignIn.vml")
    check("other code files become modules, kept as comments", ("Pricing.lua" in result["modules"], (target / "Pricing.lua").read_text().splitlines()[-4:-2]),
          (True, ["--       Public Function Vat(ByVal net As Decimal) As Decimal", "--           Return net * 0.2D"]))
    check("a form's own leftover code becomes a module beside it", ("OrderForm_code.lua" in result["modules"], "--           private decimal Price(string size)" in (target / "OrderForm_code.lua").read_text()), (True, True))
    check("every module is nothing but comments, so loading it can't go wrong", all(ln.startswith("--") or not ln.strip() for m in result["modules"] for ln in (target / m).read_text().splitlines()))
    check("assembly info and build output are left out", [m for m in result["modules"] if "Assembly" in m or "Old" in m], [])
    check("pictures are saved in images/, and the form points at them", ((target / "images" / "SignIn_Logo.png").is_file(), "Source=images/SignIn_Logo.png" in (target / "SignIn.vml").read_text()), (True, True))
    check("a SQLite database in the project is copied and named", (result["databases"], Project.load(result["project"]).databases), (["Shop.s3db"], {"Shop": "sqlite:Shop.s3db"}))
    check("the notes file lists each form", all(t in (target / "IMPORT-NOTES.txt").read_text() for t in ("== SignIn", "== OrderForm", "does not run")))
    check("the summary never claims the code runs", ("does not run" in result["summary"], "2 forms" in result["summary"]), (True, True))
    check("the original project is untouched", sorted(str(x.relative_to(vs)) for x in vs.rglob("*")), before)

    # the designer opens it, and it runs
    eng.store.set_setting("dirty", "false")
    eng.run_script("ProjectLoad", result["project"]); settle()
    check("the imported project opens in the designer on its start-up form", (get("ProjTitle", "Text"), get("Surface", "FormName"), eng.cmd_GetControlType("Logo")), ("Project: Shop", "SignIn", "Image"))
    eng.run_script("Preview"); settle()
    run = [x for x in eng.windows if x.name == "SignIn" and x.widget.isVisible()]
    check("F5 runs it: the form opens, with its picture", (len(run), eng.scopes[run[0].scope]["Logo"].widget.pix is not None if run else None), (1, True))
    if run:
        eng.scopes[run[0].scope]["OK"].widget.click(); settle()
        check("its imported handlers are comments, so a click does nothing and breaks nothing", run[0].widget.isVisible())
    check("its database is there to ask", json.loads(eng.cmd_DbTables("Shop")), ["prices"])
    eng.run_script("ProjectClose"); settle()
    print(f"\n{sum(ok)}/{len(ok)} passed")
    app.quit()

QTimer.singleShot(300, steps)
app.exec()
sys.exit(0 if all(ok) else 1)
