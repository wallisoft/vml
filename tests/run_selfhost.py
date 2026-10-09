"""The designer is itself a Visualised project (designer/Designer.vmlproj): its menus and controls name functions in
the project's modules. It has to keep working while it runs somebody else's project, and a form's handler can be a
function in one of its project's modules anywhere, on the desktop and in a browser."""
import json, os, shutil, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("VML_PREFS", os.path.join(tempfile.mkdtemp(prefix="vml-prefs-"), "prefs.json"))
from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
import vml.engine as engine_module
from vml.engine import Engine
from vml.projects import Project, project_for

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DESIGNER = os.path.join(HERE, "designer")
WORK = tempfile.mkdtemp(prefix="vml-self-")
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
said = []
eng.cmd_InfoDialog = lambda msg, title="": said.append(str(msg))
eng.cmd_ConfirmDialog = lambda msg, title="": True

def settle(n=10):
    for _ in range(n):
        app.processEvents()

# ---------------------------------------------------------------- the designer's own project
designer = Project.load(os.path.join(DESIGNER, "Designer.vmlproj"))
check("the designer is a project: five forms, starting at the designer itself", (designer.startup, sorted(designer.forms)),
      ("designer.vml", ["databases.vml", "designer.vml", "menu-editor.vml", "module-editor.vml", "script-editor.vml"]))
check("every form and module it names is there", [f for f in designer.forms + designer.modules if not designer.absolute(f).is_file()], [])
text = open(os.path.join(DESIGNER, "designer.vml"), encoding="utf-8").read()
check("the designer's form holds its layout and none of its code", ("@Script" in text, len(text.splitlines()) < 700), (False, True))
handlers = set()
import re
for m in re.finditer(r"^(?:On\w+|SelectionChanged|TextChanged|ItemsSource)=([A-Za-z_]\w*)", text, re.M):
    handlers.add(m.group(1))
code = "\n".join(designer.absolute(m).read_text(encoding="utf-8") for m in designer.modules)
functions = set(re.findall(r"^function (\w+)\(", code, re.M))
check("every handler the form names is a function in a module, or a command", sorted(h for h in handlers if h not in functions and not hasattr(eng, "cmd_" + h)), [])
check("no function is defined twice", len(functions), len(re.findall(r"^function (\w+)\(", code, re.M)))
called = set(re.findall(r'Vml\("RunScript", "(\w+)"', code))
check("every handler another handler runs is there too", sorted(called - functions), [])

# ---------------------------------------------------------------- a small project of the user's, with a handler in a module
APP = os.path.join(WORK, "app")
os.mkdir(APP)
with open(os.path.join(APP, "App.vmlproj"), "w") as f:
    f.write("# Visualised project\nName=App\nStartup=main.vml\nForm=main.vml\nForm=other.vml\nModule=code.lua\n")
with open(os.path.join(APP, "code.lua"), "w") as f:
    f.write('''function Hello(control)
    Project.count = (Project.count or 0) + 1
    Vml("SetProperty", "lblOut", "Text", "Hello from " .. control .. " " .. Project.count)
end
function Greet(name, twice)
    Vml("SetProperty", "lblOut", "Text", "Greetings, " .. name .. (twice and (" and " .. twice) or ""))
    return "greeted " .. name
end
function Names() return '["Ann", "Bob"]' end
function About() Vml("SetProperty", "lblOut", "Text", "the app's own About") end
function OpenOther() Vml("FormOpen", "other") end
''')
with open(os.path.join(APP, "main.vml"), "w") as f:
    f.write('''@Window main
Title=Main
Width=300
Height=200
OnOpened=Greet(World)

@Canvas c
Parent=main

@Button btnHello
Parent=c
Content=Hello
OnClick=Hello

@Button btnGreet
Parent=c
Canvas.Top=30
Content=Greet
OnClick=Greet(Ann, Bob)

@Button btnAbout
Parent=c
Canvas.Top=60
Content=About
OnClick=About

@Button btnOwn
Parent=c
Canvas.Top=90
Content=Own
OnClick=Own

@Button btnOther
Parent=c
Canvas.Top=120
Content=Other
OnClick=OpenOther

@ListBox lstNames
Parent=c
Canvas.Left=150
Width=100
Height=80
ItemsSource=Names

@TextBlock lblOut
Parent=c
Canvas.Top=150
Text=-

@Script Own
Interpreter=lua
<<LUA
Vml("SetProperty", "lblOut", "Text", Vml("RunScript", "Greet", "Own"))
LUA
''')
with open(os.path.join(APP, "other.vml"), "w") as f:
    f.write("@Window other\nTitle=Other\nWidth=200\nHeight=100\n\n@Canvas oc\nParent=other\n\n@Button btnHi\nParent=oc\nContent=Hi\nOnClick=Hello\n\n@TextBlock lblOut\nParent=oc\nCanvas.Top=40\nText=-\n")

def window(name):
    return next((x for x in eng.windows if x.name == name and x.widget.isVisible()), None)

def steps():
    eng.load(os.path.join(DESIGNER, "designer.vml")); settle()
    dwin = window("Designer")
    dscope = dwin.scope
    check("the designer starts, and is not 'the project being run'", (dwin is not None, eng.project, V("ProjectName")), (True, None, ""))
    check("its modules are in its Lua state", [n for n in ("FileSave", "ProjectLoad", "ApplyLicence", "BuildImportMenu") if eng.lua_function(n, dwin) is None], [])
    check("DesignerInit ran from a module: the Import menu was built and the licence applied", (eng.find("FileImport_VB6") is not None, "Licence:" in str(V("GetProperty", "SetLicenceInfo", "Text"))), (True, True))
    eng.find("HelpAbout").action.trigger() if eng.find("HelpAbout") else eng.run_script("About"); settle()
    check("a menu item runs its function", any("Visualised" in s for s in said))
    check("with nobody asking, a handler runs for the designer", (eng.run_script("UpdateTitle"), "Visualised" in dwin.widget.windowTitle()), ("", True))

    # the designer runs the user's project, twice
    eng.run_script("ProjectLoad", os.path.join(APP, "App.vmlproj")); settle()
    check("the user's project opens in the designer", (json.loads(V("ProjectInfo"))["name"], eng.project), ("App", None))
    for turn in (1, 2):
        eng.run_script("Preview"); settle(20)
        main = window("main")
        w = lambda name: eng.scopes[main.scope][name].widget
        check(f"run {turn}: the app's start-up form opens, and the designer is still there", (main is not None, window("Designer") is dwin, eng.project.name), (True, True, "App"))
        check(f"run {turn}: OnOpened named a module's function, with an argument", w("lblOut").text(), "Greetings, World")
        w("btnHello").click(); settle()
        check(f"run {turn}: a button's handler is a function in the project's module, and is told which control", w("lblOut").text(), "Hello from btnHello 1")
        w("btnGreet").click(); settle()
        check(f"run {turn}: Name(a, b) passes arguments to the function", w("lblOut").text(), "Greetings, Ann and Bob")
        w("btnOwn").click(); settle()
        check(f"run {turn}: a script can run a module's function and have what it returns", w("lblOut").text(), "greeted Own")
        check(f"run {turn}: ItemsSource can name a module's function", [w("lstNames").item(i).text() for i in range(w("lstNames").count())], ["Ann", "Bob"])
        w("btnAbout").click(); settle()
        check(f"run {turn}: the app's About is the app's, though the designer has one of the same name", (w("lblOut").text(), len(said)), ("the app's own About", 1))
        w("btnOther").click(); settle()
        other = window("other")
        eng.scopes[other.scope]["btnHi"].widget.click(); settle()
        check(f"run {turn}: a second form has the modules too, acts on itself, and shares the Project table",
              (eng.scopes[other.scope]["lblOut"].widget.text(), w("lblOut").text()), ("Hello from btnHi 2", "the app's own About"))
        check(f"run {turn}: the app's functions are not in the designer, nor the designer's in the app",
              (eng.lua_function("Hello", dwin), eng.lua_function("FileSave", main)), (None, None))
        check(f"run {turn}: the designer's Project table is its own", eng.lua_state(dscope).eval("Project.count"), None)
    eng.find("HelpAbout").action.trigger() if eng.find("HelpAbout") else eng.run_script("About"); settle()
    check("after running the app, the designer's menus still work", len(said), 2)
    eng.run_script("FileNewQuiet"); settle()
    name = V("AddDesignControl", "Button", 40, 40)
    check("and its design surface still takes controls", (name, V("GetControlType", name)), ("Button1", "Button"))
    QTimer.singleShot(300, lambda: [x.widget.close() for x in eng.windows if x.name == "ScriptEditor"])
    eng.run_script("EditScript"); settle()
    check("the script editor opens and closes after an app was run", window("ScriptEditor"), None)
    for x in [x for x in eng.windows if x.name in ("main", "other")]:
        x.widget.close()
    settle()

    # the designer, opened in itself and run
    eng.run_script("ProjectClose"); settle()
    eng.store.set_setting("dirty", "false")
    check("the designer opens in the designer", V("ImportVml", os.path.join(DESIGNER, "designer.vml"), "Surface"), "true")
    eng.store.set_setting("current_file", os.path.join(DESIGNER, "designer.vml"))
    before = len(said)
    eng.run_script("PreviewForm"); settle(30)
    second = [x for x in eng.windows if x.name == "Designer" and x is not dwin and x.widget.isVisible()]
    check("F5 runs a second designer beside the first", len(second), 1)
    if second:
        check("the second one has the modules, from the project its form belongs to", eng.lua_function("FileSave", second[0]) is not None)
        eng.handle("About", second[0]); settle()               # (what its Help > About does)
        check("and its menus work", len(said), before + 1)
        second[0].widget.close(); settle()
    eng.store.set_setting("current_file", ""); eng.store.set_setting("dirty", "false")

    # in a browser
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("SKIP  web: playwright isn't installed")
        return finish()
    out = os.path.join(WORK, "main.html")
    from vml.html import export_html
    export_html(os.path.join(APP, "main.vml"), out)
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page()
        errors = []
        pg.on("console", lambda m: errors.append(m.text) if m.type in ("error", "warning") else None)
        pg.goto("file://" + out)
        pg.wait_for_selector("#vml_status[data-ready='1']", state="attached", timeout=20000)
        pg.wait_for_timeout(200)
        check("web: OnOpened named a module's function", pg.inner_text("#v_lblOut"), "Greetings, World")
        pg.click("#v_btnHello")
        check("web: a button's handler is a function in the module", pg.inner_text("#v_lblOut"), "Hello from btnHello 1")
        pg.click("#v_btnGreet")
        check("web: with arguments", pg.inner_text("#v_lblOut"), "Greetings, Ann and Bob")
        pg.click("#v_btnOwn")
        check("web: and from a script, with what it returns", pg.inner_text("#v_lblOut"), "greeted Own")
        check("web: nothing went wrong in the page", [e for e in errors if "no script" in e or "error" in e.lower()], [])
        b.close()
    finish()

def finish():
    check("nothing failed along the way", [l for l in logged if "script error" in l or "no script called" in l or "Traceback" in l], [])
    print(f"\n{sum(ok)}/{len(ok)} passed")
    app.quit()

QTimer.singleShot(200, steps)
app.exec()
sys.exit(0 if all(ok) else 1)
