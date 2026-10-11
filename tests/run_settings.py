"""The Settings menu, the licence tiers and what they switch on and off, driven like a user."""
import base64, json, os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HOME = tempfile.mkdtemp(prefix="vml-home-")
os.environ["HOME"] = os.environ["USERPROFILE"] = HOME          # this user's preferences go here, not in the real home
from pathlib import Path
from PySide6.QtWidgets import QApplication
from vml import licence as L
L.PREFS_FILE = Path(HOME) / ".vml" / "prefs.json"
from vml.engine import Engine
from vml import __version__ as V
import vml.engine as E

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DESIGNER = os.path.join(HERE, "designer", "designer.vml")
ok, said, opened = [], [], []

def check(label, got, want=True):
    passed = got == want
    ok.append(passed)
    print(f"{'PASS' if passed else 'FAIL'}  {label}" + ("" if passed else f": got {got!r}, wanted {want!r}"))

def designer(answer_prompt="", answer_confirm=True):
    eng = Engine()
    eng.cmd_InfoDialog = lambda msg, title="": said.append(str(msg))
    eng.cmd_ErrorDialog = lambda msg, title="": said.append(str(msg))
    eng.cmd_PromptDialog = lambda title="", prompt="", default="": designer.prompt
    eng.cmd_ConfirmDialog = lambda msg, title="": (said.append(str(msg)), designer.confirm)[1]
    eng.cmd_OpenUrl = lambda url: opened.append(str(url))
    eng.load(DESIGNER)
    for _ in range(6):
        QApplication.instance().processEvents()
    return eng
designer.prompt, designer.confirm = "", True

def text(eng, name): return eng.find(name).action.text()
def enabled(eng, name): return eng.find(name).action.isEnabled()
def click(eng, name):
    eng.find(name).action.trigger()
    for _ in range(4):
        QApplication.instance().processEvents()

# a signing key of our own stands in for the server's; the private half is made with the standard library
try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization
except ImportError:
    print("SKIP  (the cryptography package is needed to make test keys)"); sys.exit(0)
sk = Ed25519PrivateKey.generate()
L.PUBLIC_KEY = sk.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()
b64 = lambda b: base64.b64encode(b).decode().replace("+", "-").replace("/", "_").rstrip("=")
make = lambda payload: "VSL1-" + b64(payload.encode()) + "." + b64(sk.sign(payload.encode()))
PRO, ENT, OLD = make("pro|1|V1A2B3|20261008||steve@example.com"), make("enterprise|25|E9|20261008|20991231|Acme Ltd"), make("pro|1|X1|20240101|20241231|old@example.com")

# ---------------------------------------------------------------- Community, as installed
eng = designer()
bar = [a.text() for a in eng.find("File").action.menu().parent().actions()] if False else None
check("File has Import and Export", [text(eng, n) for n in ("FileImport", "FileExport")], ["Import", "Export"])
imports = ["FileImport_VB6", "FileImportProject_VB6", "FileImport_WinForms", "FileImportProject_WinForms", "FileImportDelphi", "FileImportQt", "FileImportXaml", "FileImportHtml"]
check("Community: every import is listed and greyed", [enabled(eng, n) for n in imports], [False] * 8)
check("the importers in the library are marked Pro; those not written yet are listed as still to come", (text(eng, "FileImport_WinForms"), text(eng, "FileImportProject_VB6"), text(eng, "FileImportDelphi")),
      ("Windows Forms form (Visual Studio, VB or C#)...   (Pro)", "Visual Basic 5/6 project...   (Pro)", "Delphi form (.dfm)..."))
check("Community: exporting an app of its own is greyed and marked Pro", [(enabled(eng, n), text(eng, n).endswith("(Pro)")) for n in ("FileExportWin", "FileExportLinux", "FileExportAndroid")], [(False, True)] * 3)
check("Community: exporting a web page is free", (enabled(eng, "FileExportWeb"), text(eng, "FileExportWeb")), (True, "Web page..."))
check("Community can still save: New, Open, Save and Save As are live", [enabled(eng, n) for n in ("FileNew", "FileOpen", "FileSave", "FileSaveAs")], [True] * 4)
check("Settings shows the licence", text(eng, "SetLicenceInfo"), "Licence: Community")
check("and offers to enter a key and to upgrade to Pro", [text(eng, "SetLicenceEnter"), text(eng, "SetLicenceUpgrade"), enabled(eng, "SetLicenceRemove")], ["Enter Licence Key...", "Upgrade to Pro...", False])
said.clear(); out = eng.cmd_ExportHtml("Surface", os.path.join(HOME, "x.html"))
check("Community: a web page really is written", (out == os.path.join(HOME, "x.html"), os.path.getsize(out) > 1000, said), (True, True, []))
said.clear(); out = eng.cmd_ExportApk("Surface", os.path.join(HOME, "x.apk"))
check("Community: exporting an Android app is refused in the engine too, with an explanation", (out, "Visualised Pro" in (said or [""])[-1], os.path.exists(os.path.join(HOME, "x.apk"))), ("", True, False))
import webbrowser
webbrowser.open = lambda url: opened.append(url)
said.clear(); opened.clear(); eng.cmd_PreviewInBrowser("Surface")
check("but Preview in Browser still works for everyone", (len(opened), said), (1, []))
opened.clear(); click(eng, "SetLicenceUpgrade")
check("Upgrade to Pro opens the pricing page", opened, [L.BUY_URL])

# ---------------------------------------------------------------- grid and snapping
surf = eng.find("Surface").widget
check("snap to grid starts on, grid 8, ticked in the menu", (surf.snap_on, surf.grid, surf.snap(13), text(eng, "SetSnap").strip()), (True, 8, 16, "\u2713  Snap to Grid"))
click(eng, "SetSnap")
check("clicking Snap to Grid turns snapping off: 13 stays 13, and the tick goes", (surf.snap_on, surf.snap(13), text(eng, "SetSnap").strip()), (False, 13, "Snap to Grid"))
click(eng, "SetSnap")
check("clicking again turns it back on", (surf.snap_on, surf.snap(13)), (True, 16))
click(eng, "SetGrid16")
check("Grid Size 16: the grid changes and that size is ticked", (surf.grid, surf.snap(13), text(eng, "SetGrid16").strip(), text(eng, "SetGrid8").strip()), (16, 16, "\u2713  16 pixels", "8 pixels"))
click(eng, "ViewGrid")
check("Show Grid switches off and loses its tick", (surf.show_grid, text(eng, "ViewGrid").strip()), (False, "Show Grid"))
click(eng, "FileNew")
check("a new form keeps the grid settings", (surf.grid, surf.show_grid, surf.snap_on), (16, False, True))
eng2 = designer(); surf2 = eng2.find("Surface").widget
check("the settings are remembered the next time Visualised starts", (surf2.grid, surf2.show_grid, surf2.snap_on, text(eng2, "SetGrid16").strip()), (16, False, True, "\u2713  16 pixels"))

# ---------------------------------------------------------------- entering a licence
designer.prompt = "VSL1-not-a-real-key.at-all"; said.clear(); click(eng2, "SetLicenceEnter")
check("a wrong key is refused with a plain explanation, and nothing changes", ("isn't a valid" in said[-1], text(eng2, "SetLicenceInfo")), (True, "Licence: Community"))
designer.prompt = OLD; said.clear(); click(eng2, "SetLicenceEnter")
check("a key past its date is refused, saying when it ran out", ("ran out on 31/12/2024" in said[-1], text(eng2, "SetLicenceInfo")), (True, "Licence: Community"))
designer.prompt = "  " + PRO[:40] + "\n" + PRO[40:] + " "; said.clear(); click(eng2, "SetLicenceEnter")
check("a Pro key (even wrapped over two lines) is accepted", (said[-1], text(eng2, "SetLicenceInfo")), ("Visualised Pro is active on this computer.", "Licence: Pro"))
check("Pro: the exports are live and no longer marked", [(enabled(eng2, n), text(eng2, n)) for n in ("FileExportWeb", "FileExportWin", "FileExportLinux", "FileExportAndroid")], [(True, "Web page..."), (True, "Windows app..."), (True, "Linux app..."), (True, "Android app...")])
check("Pro: every importer in the library is live; the ones not written yet stay greyed", [enabled(eng2, n) for n in imports], [True] * 4 + [False] * 4)
check("Pro: the menu offers Change, Remove and Upgrade to Enterprise", [text(eng2, "SetLicenceEnter"), enabled(eng2, "SetLicenceRemove"), text(eng2, "SetLicenceUpgrade")], ["Change Licence Key...", True, "Upgrade to Enterprise..."])
out = eng2.cmd_ExportHtml("Surface", os.path.join(HOME, "pro.html"))
check("Pro: exporting a web page really writes one", os.path.exists(out) and os.path.getsize(out) > 1000)
said.clear(); click(eng2, "SetLicenceInfo")
check("the licence line shows who it is licensed to and when", ("Licensed to steve@example.com" in said[-1], "Licence V1A2B3, issued 08/10/2026" in said[-1]), (True, True))
said.clear(); click(eng2, "HelpAbout")
check("About shows the version and the tier", said[-1].startswith(f"Visualised {V} (Pro)"))
eng3 = designer()
check("the licence is remembered the next time Visualised starts", (text(eng3, "SetLicenceInfo"), enabled(eng3, "FileExportWin")), ("Licence: Pro", True))
designer.prompt = ENT; click(eng3, "SetLicenceEnter")
check("an Enterprise key replaces it", (text(eng3, "SetLicenceInfo"), enabled(eng3, "SetLicenceUpgrade"), enabled(eng3, "FileExportAndroid")), ("Licence: Enterprise", False, True))
said.clear(); click(eng3, "SetLicenceInfo")
check("and shows its expiry date", "Valid until 31/12/2099" in said[-1])
designer.confirm = False; click(eng3, "SetLicenceRemove")
check("Remove asks first; answering No keeps the licence", text(eng3, "SetLicenceInfo"), "Licence: Enterprise")
designer.confirm = True; click(eng3, "SetLicenceRemove")
check("answering Yes goes back to Community, exports greyed again", (text(eng3, "SetLicenceInfo"), enabled(eng3, "FileExportAndroid"), text(eng3, "FileExportAndroid")), ("Licence: Community", False, "Android app...   (Pro)"))
check("and the grid settings survive all of that", (eng3.find("Surface").widget.grid, json.loads(L.PREFS_FILE.read_text()).get("grid_size")), (16, "16"))

# ---------------------------------------------------------------- updates
import urllib.request, io
class Reply(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): return False
def releases(tag): urllib.request.urlopen = lambda req, timeout=0: Reply(json.dumps({"tag_name": tag}).encode())
releases("v99.0.0"); said.clear(); opened.clear(); designer.confirm = True; click(eng3, "SetUpdate")
check("a newer release is offered, and Yes opens the download page", (f"99.0.0 is available (you have {V})" in said[-1], opened), (True, ["https://github.com/wallisoft/vml-releases/releases/latest"]))
releases("v" + V); said.clear(); opened.clear(); click(eng3, "SetUpdate")
check("when up to date it says so and opens nothing", (said[-1], opened), (f"You have the latest Visualised ({V}).", []))
releases("v0.9.9"); said.clear(); click(eng3, "SetUpdate")
check("this version is rightly seen as newer than 0.9.9", said[-1], f"You have the latest Visualised ({V}).")
def offline(req, timeout=0): raise OSError("no network")
urllib.request.urlopen = offline; said.clear(); click(eng3, "SetUpdate")
check("with no network it says it couldn't check, without an error", said[-1].startswith("Couldn't check for updates just now"))

real = sys.executable
sys.executable = r"C:\Program Files\WindowsApps\tiny-web.visualised_1.0.0.0_x64__abc\vml.exe"
def must_not_ask(req, timeout=0): raise AssertionError("a Store copy must not go looking for installers")
urllib.request.urlopen = must_not_ask; said.clear(); opened.clear(); click(eng3, "SetUpdate")
sys.executable = real
check("a copy from the Microsoft Store says the Store keeps it up to date, and offers no download", ("Microsoft Store" in said[-1], opened), (True, []))

# ---------------------------------------------------------------- the version, where a user looks for it
check("Help shows which Visualised this is", text(eng3, "HelpVersion"), f"Visualised {V}")
said.clear(); click(eng3, "HelpAbout")
check("and so does About", f"Visualised {V} (Community)" in said[-1])

# ---------------------------------------------------------------- C# scripting: off until .NET is there, and Settings sets it up
from vml import csharp as C
state = {"sdk": "", "ready": False, "built": 0, "build_ok": True, "install": ""}
C.available = lambda: state["ready"]
C.sdk_version = lambda: state["sdk"]
C.find_dotnet = lambda: "/usr/bin/dotnet" if state["sdk"] else None
def fake_build():
    state["built"] += 1
    state["ready"] = state["build_ok"]
    return (True, "C# scripting is ready") if state["build_ok"] else (False, "error CS0000: it broke")
C.build = fake_build
eng4 = designer()
eng4.cmd_InstallDotnet = lambda: state["install"]
check("with no .NET, C# is off and not offered as a script language", (text(eng4, "SetCSharp"), "C#" in json.loads(eng4.cmd_GetLanguages())), ("C# Scripting: Off...", False))
said.clear(); opened.clear(); designer.confirm = False; click(eng4, "SetCSharp")
check("Settings explains that C# needs Microsoft's .NET SDK, and asks before doing anything", ("free .NET SDK" in said[-1], opened, state["built"]), (True, [], 0))
designer.confirm = True; click(eng4, "SetCSharp")
check("saying yes opens Microsoft's download page (on Linux, with the one-line way too)", (opened, "sudo apt install dotnet-sdk-8.0" in said[-1] or not sys.platform.startswith("linux")), (["https://dotnet.microsoft.com/download/dotnet/8.0"], True))
state["install"] = "started"; said.clear(); opened.clear(); click(eng4, "SetCSharp")
check("where it can be installed for the user (Windows, winget), it is, and no page is opened", ("installing in a window of its own" in said[-1], opened), (True, []))
state["sdk"] = "6.0.428"; said.clear(); opened.clear(); state["install"] = ""; click(eng4, "SetCSharp")
check("an SDK older than 8 is not enough, and it says which one is here", ("version 8 or later" in said[0], "6.0.428" in said[0], state["built"]), (True, True, 0))
state["sdk"] = "8.0.131"; said.clear(); designer.confirm = False; click(eng4, "SetCSharp")
check("with the SDK there, it offers to turn C# on, and No leaves it off", ("Turn on C# scripting?" in said[-1], state["built"], text(eng4, "SetCSharp")), (True, 0, "C# Scripting: Off..."))
state["build_ok"] = False; designer.confirm = True; said.clear(); click(eng4, "SetCSharp")
check("if the build fails it says why, and C# stays off", ("couldn't be set up" in said[-1] and "it broke" in said[-1], text(eng4, "SetCSharp")), (True, "C# Scripting: Off..."))
state["build_ok"] = True; said.clear(); click(eng4, "SetCSharp")
check("when it works, C# is on, and in the script editor's languages", (state["built"], "C# scripting is on" in said[-1], text(eng4, "SetCSharp"), "C#" in json.loads(eng4.cmd_GetLanguages())), (2, True, "C# Scripting: On", True))
said.clear(); click(eng4, "SetCSharp")
check("choosing it again just says it is on, and builds nothing", ("C# scripting is on" in said[-1], state["built"]), (True, 2))

print(f"{sum(ok)}/{len(ok)} passed")
sys.exit(0 if all(ok) else 1)
