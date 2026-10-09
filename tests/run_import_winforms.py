"""Importing Windows Forms forms: a VB.NET sign-in box in the older Visual Studio style, and a C# form with the awkward
parts (menus, tabs, a table layout). Both were written for these tests."""
import json, os, re, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("VML_PREFS", os.path.join(tempfile.mkdtemp(prefix="vml-prefs-"), "prefs.json"))   # never the real settings
from PySide6.QtWidgets import QApplication
from vml.engine import Engine

class W:
    """The Windows Forms importer (designer/importers/winforms.vml), run the way the designer runs it."""
    engine = None

    @classmethod
    def convert(cls, path, assets_dir=None):
        cls.engine = cls.engine or Engine()
        r = cls.engine.run_importer("WinForms", "ImportForm", os.path.abspath(path).replace(os.sep, "/"), (assets_dir or "").replace(os.sep, "/"))
        if r.get("error"):
            raise ValueError(r["error"])
        return r["vml"], r["notes"]

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FORMS = os.path.join(HERE, "tests", "winforms")
ok, said = [], []

def check(label, got, want=True):
    passed = got == want
    ok.append(passed)
    print(f"{'PASS' if passed else 'FAIL'}  {label}" + ("" if passed else f": got {got!r}, wanted {want!r}"))

def blocks(vml):
    """{name: (kind, {property: value})} for every control in a VML text."""
    out = {}
    for m in re.finditer(r"^@(\w+) (\w+)\n((?:[^@\n<][^\n]*\n)*)", vml, re.M):
        out[m.group(2)] = (m.group(1), dict(ln.split("=", 1) for ln in m.group(3).splitlines() if "=" in ln))
    return out

# ---------------------------------------------------------------- a real VB.NET form
vml, notes = W.convert(os.path.join(FORMS, "SignIn.Designer.vb"))
b = blocks(vml)
check("VB: the form's title and size come across", (b["SignIn"][1]["Title"], b["SignIn"][1]["Width"], b["SignIn"][1]["Height"]), ("Sign in", "401", "193"))
check("VB: labels, boxes and buttons become their Visualised equals", [b[n][0] for n in ("NameLabel", "txtName", "txtPass", "OK", "Cancel")], ["TextBlock", "TextBox", "TextBox", "Button", "Button"])
check("VB: a control keeps its place and size", [b["OK"][1][k] for k in ("Canvas.Left", "Canvas.Top", "Width", "Height")], ["197", "161", "94", "23"])
check("VB: the & shortcut marks are taken out of captions", (b["NameLabel"][1]["Text"], b["OK"][1]["Content"]), ("User name", "OK"))
check("VB: a picture box becomes an Image of the same size", (b["Logo"][0], b["Logo"][1]["Width"], b["Logo"][1]["Height"]), ("Image", "165", "193"))
check("VB: its picture comes out of the form's resources, into the form itself", b["Logo"][1]["Source"].startswith("data:image/png;base64,iVBOR"))
import tempfile as _t
_assets = os.path.join(_t.mkdtemp(prefix="vml-assets-"), "images")
_vml2, _ = W.convert(os.path.join(FORMS, "SignIn.Designer.vb"), assets_dir=_assets)
check("VB: given a folder, the picture is saved there as a file and the form points at it",
      (blocks(_vml2)["Logo"][1]["Source"], open(os.path.join(_assets, "SignIn_Logo.png"), "rb").read(4)), ("images/SignIn_Logo.png", b"\x89PNG"))
check("VB: a password box hides what is typed", b["txtPass"][1].get("IsPassword"), "true")
# a picture kept in the project's own resources (My.Resources.Banner), not the form's
import shutil as _sh
_proj = _t.mkdtemp(prefix="vml-shared-")
os.makedirs(os.path.join(_proj, "My Project")); os.makedirs(os.path.join(_proj, "Resources"))
_sh.copy(os.path.join(HERE, "tests", "controls", "dot.png"), os.path.join(_proj, "Resources", "banner.png"))
open(os.path.join(_proj, "My Project", "Resources.resx"), "w").write('<root><data name="Banner" type="System.Resources.ResXFileRef, System.Windows.Forms"><value>..\\Resources\\banner.png;System.Drawing.Bitmap, System.Drawing</value></data></root>')
open(os.path.join(_proj, "SignIn.Designer.vb"), "w").write(open(os.path.join(FORMS, "SignIn.Designer.vb")).read().replace(
    'CType(resources.GetObject("Logo.Image"), System.Drawing.Image)', "Global.Shop.My.Resources.Resources.Banner"))
_vml3, _notes3 = W.convert(os.path.join(_proj, "SignIn.Designer.vb"), assets_dir=os.path.join(_proj, "out", "images"))
check("VB: a picture from the project's shared resources is found and saved too",
      (blocks(_vml3)["Logo"][1].get("Source"), os.path.isfile(os.path.join(_proj, "out", "images", "SignIn_Logo.png"))), ("images/SignIn_Logo.png", True))
check("VB: the OK button's code came across as a script, attached to its click", b["OK"][1].get("OnClick"), "OK_OnClick")
check("VB: a declaration that runs over two lines is still recognised", "--   Private Sub OK_Click(ByVal sender As System.Object, _" in vml)
check("VB: the original Visual Basic is in the script as comments, and nothing else is", ("--   Private Sub OK_Click" in vml, all(ln.startswith("--") for ln in vml.split("<<END_OK_ONCLICK\n")[1].split("\nEND_OK_ONCLICK")[0].splitlines())), (True, True))
check("VB: the form's Load code is attached to the window opening", b["SignIn"][1].get("OnOpened"), "SignIn_OnOpened")
check("VB: nothing on this form needed approximating, and the notes don't pretend otherwise", any("No equal yet" in n or "password" in n for n in notes), False)
check("VB: the notes never claim the code runs", any("does not run" in n for n in notes))

# ---------------------------------------------------------------- a C# form with the awkward parts
vml, notes = W.convert(os.path.join(FORMS, "OrderForm.Designer.cs"))
b = blocks(vml)
check("C#: read as well as VB (title, fixed size)", (b["OrderForm"][1]["Title"], b["OrderForm"][1].get("Resizable")), ("New order", "false"))
check("C#: the menu bar keeps its shape", [(n, b[n][1].get("Parent")) for n in ("fileMenu", "newItem", "sep1", "exitItem", "helpMenu", "aboutItem")],
      [("fileMenu", "MenuBar"), ("newItem", "fileMenu"), ("sep1", "fileMenu"), ("exitItem", "fileMenu"), ("helpMenu", "MenuBar"), ("aboutItem", "helpMenu")])
check("C#: shortcuts, separators and quoted text survive", (b["newItem"][1]["Shortcut"], b["aboutItem"][1]["Shortcut"], b["sep1"][1].get("IsSeparator"), b["aboutItem"][1]["Text"]), ("Ctrl+N", "F1", "true", 'About "Orders"'))
check("C#: controls under the menu bar are measured from below it", b["tabs"][1]["Canvas.Top"], "12")
check("C#: controls stay inside their containers, at their own positions", (b["lblTotal"][1]["Parent"], b["grpTotals"][1]["Parent"], b["pageOrder"][1]["Parent"], b["lblTotal"][1]["Canvas.Left"]), ("grpTotals", "pageOrder", "tabs", "12"))
check("C#: only the first tab's page shows; the second is there but hidden", (b["pageOrder"][1].get("IsVisible"), b["pageNotes"][1].get("IsVisible")), (None, "false"))
check("C#: a list's items come across", b["cmbSize"][1]["Items"], "Small,Medium,Large")
check("C#: ticked, disabled and multi-line are kept", (b["chkGift"][1].get("IsChecked"), b["btnCancel"][1].get("IsEnabled"), b["txtNotes"][1].get("AcceptsReturn")), ("true", "false", "true"))
check("C#: colours, font and alignment are kept", [b["lblTotal"][1].get(k) for k in ("Background", "Foreground", "FontFamily", "FontSize", "FontWeight", "TextAlignment")], ["#ffffc0", "navy", "Arial", "16", "Bold", "Right"])
check("C#: anchoring is kept, and docking becomes anchoring", (b["tabs"][1]["Anchor"], b["txtCustomer"][1]["Anchor"], b["table"][1]["Anchor"], b["txtNotes"][1]["Anchor"]), ("Top,Bottom,Left,Right", "Top,Left,Right", "Bottom,Right", "Top,Bottom,Left,Right"))
check("C#: the table layout's two buttons sit side by side inside it", (int(b["btnSave"][1]["Canvas.Left"]) < int(b["btnCancel"][1]["Canvas.Left"]), b["btnSave"][1]["Parent"]), (True, "table"))
check("C#: option buttons stay option buttons, the chosen one chosen", (b["optExpress"][0], b["optStandard"][0], b["optStandard"][1].get("IsChecked"), b["optStandard"][1]["Content"]), ("RadioButton", "RadioButton", "true", "Standard"))
check("C#: a PIN box hides what is typed", b["txtPin"][1].get("IsPassword"), "true")
check("C#: a tree becomes a TreeView", (b["tree"][0], b["tree"][1]["Width"]), ("TreeView", "188"))
check("C#: events wired in the designer file are attached", (b["btnSave"][1].get("OnClick"), b["txtCustomer"][1].get("TextChanged"), b["newItem"][1].get("OnClick"), b["OrderForm"][1].get("OnOpened")), ("btnSave_OnClick", "txtCustomer_TextChanged", "newItem_OnClick", "OrderForm_OnOpened"))
save = vml.split("<<END_BTNSAVE_ONCLICK\n")[1].split("\nEND_BTNSAVE_ONCLICK")[0].splitlines()
check("C#: the whole method is kept, from its first line to its closing brace, with its shape", (save[3], save[-1], "--           MessageBox.Show(\"Who is it for?\");" in save), ("--   private void btnSave_Click(object sender, EventArgs e)", "--   }", True))
check("C#: a timer is not on the form, and the notes list it", any("timer1 (Timer)" in n for n in notes))
check("C#: a grid becomes a DataGrid with its column headings, and its double-click handler", (b["grid"][0], b["grid"][1].get("Columns"), b["grid"][1].get("OnDoubleClick")), ("DataGrid", "Item,Quantity", "grid_OnDoubleClick"))
check("C#: the notes say the grid comes across empty", any("comes across empty" in n and "grid" in n for n in notes))
check("C#: a control with no equal yet is a labelled frame of the same size, and the notes say so", (b["progress"][0], b["progress"][1]["Text"], b["progress"][1]["Width"], any("No equal yet for ProgressBar" in n for n in notes)), ("Frame", "ProgressBar: progress", "200", True))

# ---------------------------------------------------------------- through the engine, onto the design surface
def designer(tier):
    eng = Engine()
    eng.licence_override = tier
    eng.cmd_InfoDialog = lambda msg, title="": said.append(str(msg))
    eng.cmd_ErrorDialog = lambda msg, title="": said.append("ERROR " + str(msg))
    eng.load(os.path.join(HERE, "designer", "designer.vml"))
    for _ in range(6):
        QApplication.instance().processEvents()
    return eng

eng = designer(None)
check("Community: the Windows Forms import is greyed and marked Pro", (eng.find("FileImport_WinForms").action.isEnabled(), eng.find("FileImport_WinForms").action.text().endswith("(Pro)")), (False, True))
said.clear()
check("Community: importing is refused in the engine too", (eng.cmd_ImportForm("winforms", os.path.join(FORMS, "SignIn.vb")), "Visualised Pro" in said[-1]), ("", True))

eng = designer("pro")
check("Pro: the Windows Forms import is live", (eng.find("FileImport_WinForms").action.isEnabled(), eng.find("FileImport_WinForms").action.text()), (True, "Windows Forms form (Visual Studio, VB or C#)..."))
check("Pro: the importers still to come stay greyed", [eng.find(n).action.isEnabled() for n in ("FileImportDelphi", "FileImportQt", "FileImportXaml", "FileImportHtml")], [False] * 4)
check("Pro: choosing the code file works as well as the designer file", eng.cmd_ImportForm("winforms", os.path.join(FORMS, "SignIn.vb")), "true")
for _ in range(6):
    QApplication.instance().processEvents()
surf = eng.find("Surface")
names = set(json.loads(eng.cmd_GetChildControls("Surface")) if eng.cmd_GetChildControls("Surface").startswith("[") else eng.cmd_GetChildControls("Surface").split(","))
check("Pro: the sign-in form's controls are on the design surface", {"txtName", "txtPass", "OK", "Cancel", "NameLabel"} <= names)
check("Pro: the form took the sign-in box's name and title", (surf.props.get("FormName"), surf.props.get("FormTitle")), ("SignIn", "Sign in"))
check("Pro: the OK button's script can be opened in the script editor", "Private Sub OK_Click" in eng.cmd_GetDesignScript("OK", "OnClick"))
check("Pro: it is a new, unsaved form with its notes ready to show", (eng.cmd_GetSetting("import_converted"), "7 controls brought across" in eng.cmd_GetSetting("import_notes")), ("true", True))
out = os.path.join(tempfile.mkdtemp(), "login.vml")
eng.cmd_ExportVml("Surface", out)
saved = open(out, encoding="utf-8").read()
check("Pro: saved from the designer, it is an ordinary Visualised form with the code still in it", ("@Button OK" in saved, "Private Sub OK_Click" in saved, "@Window SignIn" in saved), (True, True, True))
eng2 = Engine().load(out, show=False)
check("and that saved form opens and runs on its own", any(n.type.name == "Window" for n in list(eng2.scopes.values())[-1].values()))
check("Pro: a file that is not a form is refused with a reason, not an error", (eng.cmd_ImportForm("winforms", __file__), "no form was found" in eng.cmd_GetSetting("import_notes")), ("", True))
check("Pro: the C# form opens on the surface too, menu and all", eng.cmd_ImportForm("winforms", os.path.join(FORMS, "OrderForm.Designer.cs")), "true")
menu = json.loads(eng.cmd_GetDesignMenu("Surface"))
check("Pro: its menu is in the designer's menu editor", [m["text"] for m in menu if m["level"] == 0], ["File", "Help"])

print(f"{sum(ok)}/{len(ok)} passed")
sys.exit(0 if all(ok) else 1)
