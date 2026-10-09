"""The importer library: importers are VML files, found in designer/importers and the user's own folder, listed in
File > Import and run by the engine; and the general commands they are written with (files, folders, patterns)."""
import base64, json, os, shutil, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("VML_PREFS", os.path.join(tempfile.mkdtemp(prefix="vml-prefs-"), "prefs.json"))   # never the real settings
from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
import vml.library as library
from vml.engine import Engine

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = Path(tempfile.mkdtemp(prefix="vml-library-")).resolve()
library.HOME_IMPORTERS = WORK / "home-importers"          # the user's own importers, for this test
ok, said, picked = [], [], {}

def check(label, got, want=True):
    passed = got == want
    ok.append(passed)
    print(f"{'PASS' if passed else 'FAIL'}  {label}: {got!r}" + ("" if passed else f" (wanted {want!r})"))

eng = Engine()
app = QApplication.instance()
app.setQuitOnLastWindowClosed(False)
eng.licence_override = "pro"
eng.cmd_InfoDialog = lambda msg, title="": said.append(f"{title}|{msg}")
eng.cmd_ConfirmDialog = lambda msg, title="": True
eng.cmd_FileOpenDialog = lambda title="", ext="": (picked.__setitem__("ext", ext), picked.get("file", ""))[1]
eng.cmd_FolderDialog = lambda title="", start="": picked.get("folder", "")

def settle(n=8):
    for _ in range(n):
        app.processEvents()

# ---------------------------------------------------------------- the commands importers are written with
V = eng.vml
check("RegexMatch gives the whole match and its groups", json.loads(V("RegexMatch", r"(\w+)\s*=\s*(\d+)?", "  Width = 120 'px")), ["Width = 120", "Width", "120"])
check("a group that took no part is an empty string, and no match at all is nothing", (json.loads(V("RegexMatch", r"(a)(b)?", "a")), V("RegexMatch", "z", "abc")), (["a", "a", ""], ""))
check("flags: i ignores case, s lets . cross lines", (json.loads(V("RegexMatch", "end sub", "END SUB", "i"))[0], json.loads(V("RegexMatch", "a(.*)c", "a\nb\nc", "s"))[1]), ("END SUB", "\nb\n"))
check("RegexFindAll gives every match", json.loads(V("RegexFindAll", r"Me\.(\w+)", "Me.a, Me.b")), [["Me.a", "a"], ["Me.b", "b"]])
check("RegexReplace replaces every match, with groups", V("RegexReplace", r"(\w+)@(\w+)", r"\2 at \1", "bob@home, al@work"), "home at bob, work at al")
check("a pattern that isn't valid is an error in the log, not a crash", V("RegexMatch", "(", "x"), "")
old = WORK / "old.frm"
old.write_bytes("Caption = \"Caf\xe9 \xa35\"\r\n".encode("cp1252"))
check("FileRead reads an older Windows file (not UTF-8) rightly", V("FileRead", str(old)), 'Caption = "Café £5"\r\n')
(WORK / "new.txt").write_text("naïve ✓", encoding="utf-8")
check("...and a UTF-8 one too", V("FileRead", str(WORK / "new.txt")), "naïve ✓")
check("FileWrite makes the folders it needs", (V("FileWrite", str(WORK / "a" / "b" / "c.txt"), "hello"), (WORK / "a" / "b" / "c.txt").read_text()), ("true", "hello"))
raw = bytes(range(256))
check("FileWriteBase64 and FileReadBase64 carry any bytes, whole or in part", (V("FileWriteBase64", str(WORK / "bin.dat"), base64.b64encode(raw).decode()),
      base64.b64decode(V("FileReadBase64", str(WORK / "bin.dat"))) == raw, base64.b64decode(V("FileReadBase64", str(WORK / "bin.dat"), 250, 4))), ("true", True, bytes([250, 251, 252, 253])))
check("FileCopy, FileSize and FileExists", (V("FileCopy", str(WORK / "bin.dat"), str(WORK / "a" / "copy.dat")), V("FileSize", str(WORK / "a" / "copy.dat")), V("FileSize", str(WORK / "nope")), V("FileExists", str(WORK / "nope"))), ("true", 256, -1, "false"))
check("FileList finds files by pattern, in a folder or all the way down", (json.loads(V("FileList", str(WORK), "*.TXT;*.frm")), [Path(x).name for x in json.loads(V("FileList", str(WORK), "*.txt", "true"))]),
      ([(WORK / "new.txt").as_posix(), (WORK / "old.frm").as_posix()], ["c.txt", "new.txt"]))

# ---------------------------------------------------------------- finding and running importers
names = lambda: [i["name"] for i in json.loads(eng.cmd_GetImporters())]
check("the importers that come with Visualised are found", names(), ["VB6", "WinForms"])
check("each says what it reads", {i["name"]: (i["files"], i["project_files"]) for i in json.loads(eng.cmd_GetImporters())},
      {"VB6": (["frm"], ["vbp"]), "WinForms": (["vb", "cs"], ["vbproj", "csproj"])})
check("the right importer is found from a file's ending", (eng.importer_for("", "x.frm"), eng.importer_for("", "x.Designer.cs"), eng.importer_for("", "p.vbp", project=True), eng.importer_for("", "x.dfm"), eng.importer_for("vs", "")), ("VB6", "WinForms", "VB6", None, "WinForms"))

# an importer of your own is just a VML file in your importers folder
library.HOME_IMPORTERS.mkdir()
(library.HOME_IMPORTERS / "toy.vml").write_text('''@Importer Toy
Title=Toy form
Files=toy

@Script Library
Interpreter=lua
<<TOY_LIB
kit = require("importkit")
function shout(s) return s:upper() end
TOY_LIB

@Script ImportForm
Interpreter=lua
<<TOY_FORM
-- a .toy file is lines of:  button Name x y
local f = kit.form()
f:emit("Window", "ToyForm", "", {{"Title", shout("toy")}, {"Width", 300}, {"Height", 200}})
f:emit("Canvas", "ToyFormCanvas", "ToyForm", {{"Background", "#ffffff"}})
local n = 0
for _, line in ipairs(kit.lines(kit.read(args[1]))) do
    local name, x, y = kit.match([[button\\s+(\\w+)\\s+(\\d+)\\s+(\\d+)]], line)
    if name then
        n = n + 1
        f:emit("Button", name, "ToyFormCanvas", {{"Canvas.Left", x}, {"Canvas.Top", y}, {"Content", name}, {"Empty", ""}})
    end
end
if n == 0 then return kit.json.encode({error = "there are no buttons in that file"}) end
return kit.json.encode({vml = f:text(), notes = {kit.plural(n, "button") .. " brought across."}})
TOY_FORM
''')
(WORK / "two.toy").write_text("button btnGo 20 30\nbutton btnStop 120 30\nnonsense\n")
(WORK / "none.toy").write_text("nothing here\n")
check("an importer dropped into your own folder is found, with the built-in ones", names(), ["Toy", "VB6", "WinForms"])
r = eng.run_importer("Toy", "ImportForm", str(WORK / "two.toy"), "")
check("it runs: its Library script first, then ImportForm with the file", (r.get("notes"), "@Button btnStop" in r.get("vml", ""), "Title=TOY" in r.get("vml", ""), "Empty=" in r.get("vml", "")), (["2 buttons brought across."], True, True, False))
check("an importer can say why it couldn't", eng.run_importer("Toy", "ImportForm", str(WORK / "none.toy"), ""), {"error": "there are no buttons in that file"})
check("asking for something an importer doesn't do is refused plainly", "no ImportProject script" in eng.run_importer("Toy", "ImportProject", "x", "y")["error"])
check("so is an importer that isn't there", eng.run_importer("Nope", "ImportForm", "x", "")["error"], "there's no importer called 'Nope'")
(library.HOME_IMPORTERS / "broken.vml").write_text("@Importer Broken\nTitle=Broken\nFiles=brk\n\n@Script ImportForm\nInterpreter=lua\n<<B\nlocal x = nil\nreturn x.y\nB\n")
check("an importer with a mistake in it reports the mistake; nothing else is disturbed", ("hit a problem" in eng.run_importer("Broken", "ImportForm", "x", "")["error"], eng.run_importer("Toy", "ImportForm", str(WORK / "two.toy"), "")["notes"]), (True, ["2 buttons brought across."]))
(library.HOME_IMPORTERS / "silent.vml").write_text("@Importer Silent\nTitle=Silent\nFiles=sil\n\n@Script ImportForm\nInterpreter=lua\n<<B\nlocal nothing = 1\nB\n")
check("one that hands nothing back is reported too", eng.run_importer("Silent", "ImportForm", "x", "")["error"], "the Silent importer didn't hand anything back")
(library.HOME_IMPORTERS / "notone.vml").write_text("@Window JustAForm\nTitle=x\n")
check("a VML file that isn't an importer is left out", "JustAForm" in names(), False)
os.remove(library.HOME_IMPORTERS / "broken.vml"); os.remove(library.HOME_IMPORTERS / "silent.vml")

# the built-in importers keep their names: a copy has to take a name of its own
shutil.copy(os.path.join(HERE, "designer", "importers", "vb6.vml"), library.HOME_IMPORTERS / "vb6.vml")
check("your own file can't take a built-in importer's name", [i["builtin"] for i in eng.importers().values() if i["name"] == "VB6"], [True])
(WORK / "mine.vml").write_text(open(os.path.join(HERE, "designer", "importers", "vb6.vml"), encoding="utf-8").read())
check("adding one under a built-in name is refused, and says what to do", "name of its own" in V("AddImporter", str(WORK / "mine.vml")), True)
(WORK / "soon.vml").write_text("@Importer Delphi\nTitle=x\nFiles=dfm\n\n@Script ImportForm\nInterpreter=lua\n<<B\nreturn '{}'\nB\n")
check("so is a name kept for one on its way", "name of its own" in V("AddImporter", str(WORK / "soon.vml")), True)
(WORK / "mine.vml").write_text(open(os.path.join(HERE, "designer", "importers", "vb6.vml"), encoding="utf-8").read().replace("@Importer VB6", "@Importer MyVB", 1))
check("renamed, it is added to your own library", (V("AddImporter", str(WORK / "mine.vml")), (library.HOME_IMPORTERS / "myvb.vml").is_file(), "MyVB" in names()), ("", True, True))
check("a file that isn't an importer is refused", "no @Importer" in V("AddImporter", str(library.HOME_IMPORTERS / "notone.vml")), True)
os.remove(library.HOME_IMPORTERS / "myvb.vml")
os.remove(library.HOME_IMPORTERS / "vb6.vml")

def steps():
    # ---------------------------------------------------------------- in the designer
    eng.load(os.path.join(HERE, "designer", "designer.vml")); settle()
    menu = [a.text() for a in eng.find("FileImport").menu.actions()]
    check("File > Import lists every importer in the library, what is still to come, and a way to add one",
          menu, ["Toy form...", "Visual Basic 5/6 form...", "Visual Basic 5/6 project...", "Windows Forms form (Visual Studio, VB or C#)...",
                 "Visual Studio project (.vbproj, .csproj)...", "", "Coming soon:", "Delphi form (.dfm)...", "Qt Designer (.ui)...", "XAML (WPF, Avalonia)...", "Web page (HTML form)...", "", "Add an importer..."])
    picked["file"] = str(WORK / "two.toy")
    eng.find("FileImport_Toy").action.trigger(); settle()
    check("choosing your own importer in the menu asks for its kind of file, and puts the form on the surface", (picked["ext"], eng.cmd_GetProperty("Surface", "FormName"), eng.cmd_GetControlType("btnStop"), eng.cmd_GetProperty("btnStop", "Canvas.Left")), ("toy", "ToyForm", "Button", "120"))
    check("...and says what came across", said[-1].startswith("Imported: Toy form|2 buttons brought across."))
    picked["file"] = str(WORK / "none.toy"); eng.store.set_setting("dirty", "false")
    eng.find("FileImport_Toy").action.trigger(); settle()
    check("a file it can't read gives its reason, and leaves the surface alone", (said[-1], eng.cmd_GetProperty("Surface", "FormName")), ("Import|That file couldn't be imported: there are no buttons in that file", "ToyForm"))

    # a Visual Basic 6 form and project, through the menu
    picked["file"] = os.path.join(HERE, "tests", "vb6", "frmAbout.frm"); eng.store.set_setting("dirty", "false")
    eng.find("FileImport_VB6").action.trigger(); settle()
    check("a Visual Basic 6 form opens on the surface from the menu", (picked["ext"], eng.cmd_GetProperty("Surface", "FormName"), "does not run" in said[-1]), ("frm", "frmAbout", True))
    vb = WORK / "vb6"
    shutil.copytree(os.path.join(HERE, "tests", "vb6"), vb)
    picked["file"], picked["folder"] = str(vb / "Shop.vbp"), str(WORK / "shop-from-vb6")
    eng.store.set_setting("dirty", "false")
    eng.find("FileImportProject_VB6").action.trigger(); settle()
    info = json.loads(eng.cmd_ProjectInfo())
    check("a Visual Basic 6 project comes in whole, and opens as a project on its start-up form", (picked["ext"], info["name"], sorted(info["forms"]), info["startup"], eng.cmd_GetProperty("Surface", "FormName")),
          ("vbp", "Shop", ["frmAbout.vml", "frmMain.vml"], "frmMain.vml", "frmMain"))
    check("its modules and classes are there as modules of comments", (sorted(info["modules"]), all(l.startswith("--") or not l.strip() for m in info["modules"] for l in (WORK / "shop-from-vb6" / m).read_text().splitlines())),
          (["clsOrder.lua", "frmMain_code.lua", "modPricing.lua"], True))
    eng.run_script("Preview"); settle()
    run = [x for x in eng.windows if x.name == "frmMain" and x.widget.isVisible()]
    check("F5 runs it: the main form opens, and nothing complains", len(run), 1)
    picked["folder"] = str(vb); eng.store.set_setting("dirty", "false")
    eng.find("FileImportProject_VB6").action.trigger(); settle()
    check("choosing the original project's own folder puts it in a new folder inside that one", (json.loads(eng.cmd_ProjectInfo())["name"], (vb / "Shop-visualised" / "Shop.vmlproj").is_file(), (vb / "frmMain.vml").exists()), ("Shop", True, False))
    eng.licence_override = "community"
    check("importing stays part of Pro", (eng.cmd_ImportForm("VB6", str(vb / "frmAbout.frm")), "Visualised Pro" in said[-1]), ("", True))
    print(f"\n{sum(ok)}/{len(ok)} passed")
    app.quit()

QTimer.singleShot(300, steps)
app.exec()
sys.exit(0 if all(ok) else 1)
