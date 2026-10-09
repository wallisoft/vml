"""The designer and your files: unsaved changes are never lost without a word, File > Open Recent, a copy of a
form brought in with Import, and the two new controls (Timer, ProgressBar) on the desktop."""
import json, os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("VML_PREFS", os.path.join(tempfile.mkdtemp(prefix="vml-prefs-"), "prefs.json"))
from PySide6.QtCore import QTimer
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QApplication
import vml.engine as engine_module
from vml.engine import Engine

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = tempfile.mkdtemp(prefix="vml-files-")
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
said, asked, answer, picked, saved_as, quits = [], [], ["Cancel"], [], [], []
eng.cmd_InfoDialog = lambda msg, title="": said.append(str(msg))
eng.cmd_ChoiceDialog = lambda msg, title="", buttons="": (asked.append((str(msg), str(buttons))), answer[0])[1]
eng.cmd_FileOpenDialog = lambda title="", ext="": picked.pop(0) if picked else ""
eng.cmd_FileSaveDialog = lambda title="", default="", ext="": saved_as.pop(0) if saved_as else ""
eng.cmd_AppExit = lambda: quits.append(1)

def settle(n=10):
    for _ in range(n):
        app.processEvents()

def form(name, title):
    path = os.path.join(WORK, name)
    with open(path, "w") as f:
        f.write(f"@Window {name[:-4]}\nTitle={title}\nWidth=300\nHeight=200\n\n@Canvas c\nParent={name[:-4]}\n\n@Button btn{title}\nParent=c\nContent={title}\n")
    return path

def steps():
    # ---------------------------------------------------------------- the two controls, running
    live = os.path.join(WORK, "live.vml")
    with open(live, "w") as f:
        f.write("""@Window Live
Title=Live
Width=320
Height=200

@Canvas c
Parent=Live

@Timer tmr
Parent=c
Canvas.Left=8
Canvas.Top=8
Interval=20
OnTick=Tick

@Timer tmrOff
Parent=c
Interval=20
IsEnabled=false
OnTick=TickOff

@ProgressBar bar
Parent=c
Canvas.Left=10
Canvas.Top=60
Width=200
Height=18
Value=25

@ProgressBar blocks
Parent=c
Canvas.Left=10
Canvas.Top=90
Width=200
Height=18
Value=50
BarStyle=Blocks
Foreground=#16A34A

@Script Tick
Interpreter=lua
<<LUA
local n = (tonumber(Vml("GetSetting", "ticks")) or 0) + 1
Vml("SetSetting", "ticks", tostring(n))
Vml("SetProperty", "bar", "Value", tostring(math.min(100, n * 10)))
if n >= 5 then Vml("SetProperty", "tmr", "IsEnabled", "false") end
LUA

@Script TickOff
Interpreter=lua
<<LUA
Vml("SetSetting", "off_ticked", "true")
LUA
""")
    eng.store.set_setting("ticks", "0"); eng.store.set_setting("off_ticked", "")
    eng.load(live); settle()
    import time
    end = time.time() + 2
    while time.time() < end and eng.store.get_setting("ticks") != "5":
        app.processEvents(); time.sleep(0.01)
    time.sleep(0.15); settle()
    check("a Timer runs its OnTick every Interval, and stops when its script turns it off", eng.store.get_setting("ticks"), "5")
    check("one that starts with IsEnabled false never ticks", eng.store.get_setting("off_ticked"), "")
    check("a Timer isn't seen in the running form", (eng.find("tmr").widget.isVisible(), eng.find("tmr").widget.width()), (False, 0))
    bar, blocks = eng.find("bar").widget, eng.find("blocks").widget
    check("a ProgressBar follows its Value", (V("GetProperty", "bar", "Value"), round(bar.fraction(), 2)), ("50", 0.5))
    shot = bar.grab().toImage()
    check("it is drawn: filled on the left in its bar colour, the track on the right", (shot.pixelColor(20, 9).name(), shot.pixelColor(180, 9).name()), ("#2563eb", "#e5e7eb"))
    shot = blocks.grab().toImage()
    row = [shot.pixelColor(x, 9).name() for x in range(0, 200)]
    check("Blocks draws whole blocks with gaps, in the colour asked for, up to the value", ("#16a34a" in row[:96], "#16a34a" in row[110:], row[:100].count("#e5e7eb") > 5), (True, False, True))
    V("SetProperty", "bar", "Minimum", "50"); V("SetProperty", "bar", "Maximum", "150"); V("SetProperty", "bar", "Value", "75")
    check("Minimum and Maximum set the scale", round(bar.fraction(), 2), 0.25)
    V("SetProperty", "bar", "IsIndeterminate", "true"); settle()
    check("IsIndeterminate sets it sweeping", bar.sweep.isActive())
    for x in list(eng.windows):
        x.widget.close()
    settle()

    # ---------------------------------------------------------------- in the designer
    eng.load(os.path.join(HERE, "designer", "designer.vml")); settle()
    kinds = [t["name"] for t in json.loads(eng.cmd_GetControlTypes())]
    check("the designer offers both", ("Timer" in kinds, "ProgressBar" in kinds), (True, True))
    V("SetSetting", "dirty", "false")
    t = V("AddDesignControl", "Timer", 30, 30); p = V("AddDesignControl", "ProgressBar", 30, 80)
    check("on the design surface a Timer is a small clock you can see and set, and never ticks", (eng.find(t).widget.isVisible(), eng.find(t).widget.width(), eng.find(t).widget.ticker.isActive(), V("GetProperty", t, "Interval")), (True, 28, False, "1000"))
    check("a new ProgressBar has a sensible size and a value to show", (str(V("GetProperty", p, "Width")), V("GetProperty", p, "Value")), ("200", "40"))
    out = os.path.join(WORK, "made.vml")
    V("ExportVml", "Surface", out)
    text = open(out).read()
    check("both are saved in the form", ("@Timer Timer1" in text and "Interval=1000" in text, "@ProgressBar ProgressBar1" in text and "Value=40" in text), (True, True))

    # unsaved changes
    a, b = form("a.vml", "A"), form("b.vml", "B")
    V("SetSetting", "dirty", "true"); V("SetSetting", "current_file", "")
    name = V("GetProperty", "Surface", "FormName")
    answer[0] = "Cancel"; picked.append(a); asked.clear()
    eng.run_script("FileOpen"); settle()
    check("opening another form with changes unsaved asks first, with three answers", (len(asked), asked[0][0], asked[0][1]), (1, f"Save the changes to {name}?", "Save|Don't Save|Cancel"))
    check("Cancel: nothing is opened and the changes are still there", (V("GetProperty", "Surface", "FormName"), V("GetSetting", "dirty"), picked), (name, "true", [a]))
    answer[0] = "Save"; saved_as.append(os.path.join(WORK, "mine.vml"))
    eng.run_script("FileOpen"); settle()
    check("Save: the form is saved (asking where, as it has no file yet), then the other opens", (os.path.isfile(os.path.join(WORK, "mine.vml")), V("GetProperty", "Surface", "FormName"), V("GetSetting", "dirty")), (True, "a", "false"))
    V("SetSetting", "dirty", "true"); answer[0] = "Save"; picked.append(b); saved_as.clear()
    made = V("AddDesignControl", "Button", 100, 100)
    eng.run_script("FileOpen"); settle()
    check("Save on a form that has a file saves it there, then goes on", (made in open(a).read(), V("GetProperty", "Surface", "FormName")), (True, "b"))
    V("SetSetting", "dirty", "true"); answer[0] = "Save"; saved_as.clear(); V("SetSetting", "current_file", ""); picked.append(a)
    eng.run_script("FileOpen"); settle()
    check("Save, then cancelling the Save As box, stops there", (V("GetProperty", "Surface", "FormName"), picked), ("b", [a]))
    picked.clear(); answer[0] = "Don't Save"
    eng.run_script("FileNew"); settle()
    check("Don't Save: on it goes, and the changes are gone", (V("GetProperty", "Surface", "FormName") != "b", V("GetSetting", "dirty")), (True, "false"))
    asked.clear(); eng.run_script("FileNew"); settle()
    check("with nothing changed, nothing is asked", asked, [])

    # leaving
    win = next(x for x in eng.windows if x.name == "Designer")
    V("SetSetting", "dirty", "true"); answer[0] = "Cancel"; asked.clear()
    eng.run_script("DesignerExit"); settle()
    check("Exit with unsaved changes asks, and Cancel stays", (len(asked), quits), (1, []))
    check("closing the window yourself asks too, and Cancel keeps it open", (eng._closing(win, True), len(asked), win.widget.isVisible()), (False, 2, True))
    answer[0] = "Don't Save"
    eng.run_script("DesignerExit"); settle()
    check("Don't Save leaves", quits, [1])

    # recent
    V("SetPreference", "recent_files", "[]"); eng.run_script("BuildRecentMenu"); settle()
    text_of = lambda i: V("GetProperty", f"FileRecent{i}", "Text")
    shown = lambda: [i for i in range(1, 9) if eng.find(f"FileRecent{i}").action.isVisible()]
    check("Open Recent starts empty, and says so", (shown(), eng.find("FileRecentNone").action.isVisible(), eng.find("FileRecentClear").action.isEnabled()), ([], True, False))
    V("SetSetting", "dirty", "false")
    for f in (a, b, a):
        picked.append(f); eng.run_script("FileOpen"); settle()
    recent = json.loads(V("GetPreference", "recent_files"))
    check("opened files are remembered, newest first, each once", (recent, shown(), text_of(1).startswith("1  a.vml"), WORK in text_of(1)), ([a, b], [1, 2], True, True))
    eng.find("FileRecent2").action.trigger(); settle()
    check("choosing one opens it and moves it to the top", (V("GetProperty", "Surface", "FormName"), json.loads(V("GetPreference", "recent_files"))), ("b", [b, a]))
    proj = os.path.join(WORK, "P.vmlproj")
    with open(proj, "w") as f:
        f.write("# Visualised project\nName=P\nStartup=a.vml\nForm=a.vml\n")
    eng.run_script("ProjectLoad", proj); settle()
    check("projects are remembered too", json.loads(V("GetPreference", "recent_files"))[0], proj)
    eng.run_script("ProjectClose"); settle()
    eng.find("FileRecent1").action.trigger(); settle()
    check("and open as projects", (json.loads(V("ProjectInfo") or "{}").get("name"), V("GetProperty", "Surface", "FormName")), ("P", "a"))
    os.remove(b); said.clear()
    i = json.loads(V("GetPreference", "recent_files")).index(b) + 1
    eng.find(f"FileRecent{i}").action.trigger(); settle()
    check("one that has gone is said to be gone, and taken off the list", (len(said), b in json.loads(V("GetPreference", "recent_files"))), (1, False))
    eng2 = json.loads(open(os.environ["VML_PREFS"]).read())
    check("the list is kept between sessions", json.loads(eng2["recent_files"])[0], proj)
    eng.find("FileRecentClear").action.trigger(); settle()
    check("Clear This List empties it", (json.loads(V("GetPreference", "recent_files")), shown()), ([], []))

    # a copy of a form
    eng.run_script("ProjectClose"); settle()
    V("SetSetting", "dirty", "false"); picked.append(a)
    eng.find("FileImportVml").action.trigger(); settle()
    check("File > Import > Visualised form brings in a copy: a new form, unsaved, with no file", (V("GetProperty", "Surface", "FormName"), V("GetSetting", "current_file"), V("GetSetting", "dirty")), ("a", "", "true"))
    eng.licence_override = "community"; eng.run_script("ApplyLicence"); settle()
    check("and that is for everyone, not only Pro", (eng.find("FileImportVml").action.isEnabled(), eng.find("FileImport_VB6").action.isEnabled()), (True, False))
    check("nothing went wrong along the way", [l for l in logged if "script error" in l or "no script called" in l], [])
    print(f"\n{sum(ok)}/{len(ok)} passed")
    app.quit()

QTimer.singleShot(200, steps)
app.exec()
sys.exit(0 if all(ok) else 1)
