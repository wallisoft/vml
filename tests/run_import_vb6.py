"""Importing Visual Basic 5/6: a small shop's order form with the awkward parts (a menu, control arrays, a .frx with a
picture and lists, a pixel-scaled picture box, an OCX with no equal here), an About box, a form of oddities, and the
project they belong to. All were written for these tests; the .frx is built here, into a copy, so no binary is kept."""
import json, os, re, shutil, struct, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("VML_PREFS", os.path.join(tempfile.mkdtemp(prefix="vml-prefs-"), "prefs.json"))   # never the real settings
import vml.engine as engine_module
from vml.engine import Engine

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURES = os.path.join(HERE, "tests", "vb6")
ok, logged = [], []
_log = engine_module.log
engine_module.log = lambda msg: (logged.append(str(msg)), _log(msg))[0]

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

def script(vml, name):
    """The lines of one script in a VML text."""
    tag = "END_" + name.upper()
    return vml.split(f"<<{tag}\n")[1].split(f"\n{tag}")[0].splitlines()

def tree(folder):
    """Every file under a folder with its contents, to show a folder was left alone."""
    return {os.path.relpath(os.path.join(d, f), folder): open(os.path.join(d, f), "rb").read()
            for d, _, files in os.walk(folder) for f in files}

# ---------------------------------------------------------------- the fixtures, copied, with the .frx built beside them
WORK = tempfile.mkdtemp(prefix="vml-vb6-")
SHOP = os.path.join(WORK, "Shop")
shutil.copytree(FIXTURES, SHOP)

BMP = (b"BM" + struct.pack("<IHHI", 70, 0, 0, 54) + struct.pack("<IiiHHIIiiII", 40, 2, 2, 1, 24, 0, 16, 2835, 2835, 0, 0)
       + bytes([0, 0, 255, 255, 255, 255, 0, 0]) * 2)                         # 2 x 2 pixels, red and white

def frx_list(items):
    data = struct.pack("<HH", len(items), 0x0103)
    for item in items:
        raw = item.encode("cp1252")
        data += struct.pack("<H", len(raw)) + raw
    return data

def frx_picture(raw):
    return struct.pack("<I4sI", len(raw) + 8, b"lt\0\0", len(raw)) + raw

NOTE = "Leave by the side gate.\r\nRing twice.".encode("cp1252")
parts = [(0x0000, frx_picture(BMP)),                                          # imgLogo.Picture
         (0x0052, frx_list(["Tea", "Coffee, ground", "Crème brûlée"])),       # lstProducts.List
         (0x0079, struct.pack("<HH", 3, 0x0103) + struct.pack("<III", 10, 20, 30)),   # lstProducts.ItemData
         (0x0089, bytes([len(NOTE)]) + NOTE),                                 # txtNotes.Text
         (0x00AE, frx_list(["Groceries", "Drinks", "Household"]))]            # cboCategory.List
frx = b""
for offset, part in parts:
    assert len(frx) == offset, f"the .frx offsets in frmMain.frm no longer match: {len(frx):#06x} is not {offset:#06x}"
    frx += part
with open(os.path.join(SHOP, "frmMain.frx"), "wb") as f:
    f.write(frx)

eng = Engine()

def convert(file, assets="", folder=SHOP):
    return eng.run_importer("VB6", "ImportForm", os.path.join(folder, file).replace("\\", "/"), assets)

# ---------------------------------------------------------------- the importer itself
found = eng.importers().get("vb6", {})
check("the importer is found, and says which files it reads", (found.get("title"), found.get("files"), found.get("project_files")),
      ("Visual Basic 5/6 form", ["frm"], ["vbp"]))

# ---------------------------------------------------------------- the main form
r = convert("frmMain.frm")
check("the main form converts without an error", r.get("error"), None)
vml, notes = r.get("vml", ""), r.get("notes", [])
b = blocks(vml)
win = b["frmMain"][1]
check("the form's title comes across", (b["frmMain"][0], win["Title"]), ("Window", "Corner Shop - Orders"))
check("its size is turned from twips to pixels, with room added for the menu bar", (win["Width"], win["Height"]), ("600", "439"))
check("a form that can be resized is left that way", win.get("Resizable"), None)
check("a form with a menu is a dock panel holding the menu bar and the canvas",
      [(n, b[n][0], b[n][1].get("Parent")) for n in ("frmMainRoot", "frmMainMenu", "frmMainCanvas")],
      [("frmMainRoot", "DockPanel", "frmMain"), ("frmMainMenu", "TinyMenu", "frmMainRoot"), ("frmMainCanvas", "Canvas", "frmMainRoot")])
check("the menu bar is docked at the top", b["frmMainMenu"][1].get("DockPanel.Dock"), "Top")
check("the form's colour is read blue-green-red, the way Visual Basic writes it", b["frmMainCanvas"][1]["Background"], "#ffe0c0")

# controls
check("labels, boxes, buttons, ticks and options become their Visualised equals",
      [b[n][0] for n in ("lblCustomer", "txtCustomer", "cmdDelete", "chkGift", "optStandard", "cboCategory", "lstProducts", "fraDelivery")],
      ["TextBlock", "TextBox", "Button", "CheckBox", "RadioButton", "ComboBox", "ListBox", "Frame"])
check("a control keeps its place and size, in pixels", [b["txtCustomer"][1][k] for k in ("Canvas.Left", "Canvas.Top", "Width", "Height")], ["104", "40", "273", "21"])
check("the & shortcut marks are taken out of captions", (b["lblCustomer"][1]["Text"], b["cmdDelete"][1]["Content"], b["fraDelivery"][1]["Text"], b["chkGift"][1]["Content"]),
      ("Customer:", "Delete", "Delivery", "Gift wrap"))
check("a file in Windows-1252 is read properly (the pound sign)", b["lblTotal"][1]["Text"], "Total (£):")
check("a label of a fixed size wraps its text", b["lblCustomer"][1].get("TextWrapping"), "Wrap")
check("a label's alignment is kept (1 is right, 2 is centre)", (b["lblTotal"][1].get("TextAlignment"), b["lblStatus"][1].get("TextAlignment"), b["lblCustomer"][1].get("TextAlignment")), ("Right", "Center", None))
check("controls in a frame belong to it, at their own positions inside it",
      [(b[n][1]["Parent"], b[n][1]["Canvas.Left"], b[n][1]["Canvas.Top"]) for n in ("optStandard", "optExpress", "chkGift")],
      [("fraDelivery", "8", "16"), ("fraDelivery", "96", "16"), ("fraDelivery", "184", "16")])
check("the chosen option and the ticked box stay chosen and ticked", (b["optStandard"][1].get("IsChecked"), b["optExpress"][1].get("IsChecked"), b["chkGift"][1].get("IsChecked")), ("true", None, "true"))
check("a multi-line box, a locked box and a password box keep what makes them so",
      (b["txtNotes"][1].get("AcceptsReturn"), b["txtTotal"][1].get("IsReadOnly"), b["txtPin"][1].get("IsPassword"), b["txtCustomer"][1].get("IsPassword")), ("true", "true", "true", None))
check("a text box's starting text comes across", b["txtTotal"][1]["Text"], "0.00")
check("a multi-line box's text is read out of the .frx", b["txtNotes"][1].get("Text"), "Leave by the side gate. Ring twice.")
check("a tool tip survives its quotes, and the comment mark inside it", b["txtCustomer"][1].get("ToolTip"), "Who the order is for ('Mr' or \"Mrs\" too)")

# ScaleMode
check("a picture box that holds controls becomes a frame", (b["picToolbar"][0], b["picToolbar"][1]["Width"], b["picToolbar"][1]["Height"]), ("Frame", "600", "32"))
check("inside a picture box that measures in pixels (ScaleMode 3), positions are taken as pixels",
      [b["cmdRefresh"][1][k] for k in ("Parent", "Canvas.Left", "Canvas.Top", "Width", "Height")], ["picToolbar", "8", "4", "80", "24"])

# control arrays
check("a control array's elements are named by their index", [(n in b, b[n][1]["Content"]) for n in ("cmdQty_0", "cmdQty_1", "cmdQty_2")], [(True, "+1"), (True, "+5"), (True, "+10")])
check("each element keeps its own place", [b[n][1]["Canvas.Left"] for n in ("cmdQty_0", "cmdQty_1", "cmdQty_2")], ["16", "88", "160"])
check("the array's one handler is attached to every element", [b[n][1].get("OnClick") for n in ("cmdQty_0", "cmdQty_1", "cmdQty_2")], ["cmdQty_OnClick"] * 3)
check("and it is one script, not three", vml.count("@Script cmdQty_OnClick\n"), 1)
check("the shared handler keeps its Index argument", "--   Private Sub cmdQty_Click(Index As Integer)" in script(vml, "cmdQty_OnClick"))

# menus
check("the menu keeps its shape: top items on the bar, the rest under their parents",
      [(n, b[n][0], b[n][1].get("Parent")) for n in ("mnuFile", "mnuFileNew", "mnuFileRecent", "mnuRecent_0", "mnuRecent_1", "mnuFileSep", "mnuFileExit", "mnuEdit", "mnuEditDelete", "mnuHelp", "mnuHelpAbout")],
      [("mnuFile", "MenuItem", "MenuBar"), ("mnuFileNew", "MenuItem", "mnuFile"), ("mnuFileRecent", "MenuItem", "mnuFile"), ("mnuRecent_0", "MenuItem", "mnuFileRecent"),
       ("mnuRecent_1", "MenuItem", "mnuFileRecent"), ("mnuFileSep", "MenuItem", "mnuFile"), ("mnuFileExit", "MenuItem", "mnuFile"), ("mnuEdit", "MenuItem", "MenuBar"),
       ("mnuEditDelete", "MenuItem", "mnuEdit"), ("mnuHelp", "MenuItem", "MenuBar"), ("mnuHelpAbout", "MenuItem", "mnuHelp")])
check("menu items stay in the order they were written", [n for n in b if b[n][0] == "MenuItem"][:5], ["mnuFile", "mnuFileNew", "mnuFileRecent", "mnuRecent_0", "mnuRecent_1"])
check("a caption of - is a separator, with no text", (b["mnuFileSep"][1].get("IsSeparator"), "Text" in b["mnuFileSep"][1]), ("true", False))
check("menu captions lose their & marks, keep a doubled one as a real &, and keep quoted text",
      (b["mnuFileNew"][1]["Text"], b["mnuFileExit"][1]["Text"], b["mnuRecent_0"][1]["Text"], b["mnuHelpAbout"][1]["Text"]), ("New Order", "Exit", "Smith & Sons", 'About "Corner Shop"...'))
check("shortcuts are rewritten: ^N, ^{F4}, {DEL}, {F1} and +{F1}",
      [b[n][1].get("Shortcut") for n in ("mnuFileNew", "mnuFileExit", "mnuEditDelete", "mnuHelpContents", "mnuHelpTips", "mnuFile")], ["Ctrl+N", "Ctrl+F4", "Del", "F1", "Shift+F1", None])
check("a greyed menu item stays greyed", b["mnuEditDelete"][1].get("IsEnabled"), "false")
check("menu handlers are attached to their items, a menu array's to each of them",
      [b[n][1].get("OnClick") for n in ("mnuFileNew", "mnuFileExit", "mnuHelpAbout", "mnuRecent_0", "mnuRecent_1")],
      ["mnuFileNew_OnClick", "mnuFileExit_OnClick", "mnuHelpAbout_OnClick", "mnuRecent_OnClick", "mnuRecent_OnClick"])
check("the notes say a menu item's tick was not carried over", any("mnuHelpTips" in n and "tick" in n for n in notes))

# colours, fonts, enabled, visible
check("a system colour (the tool tip yellow) and a plain colour (navy, blue first) are both read", (b["lblTotal"][1].get("Background"), b["lblTotal"][1].get("Foreground")), ("#ffffe1", "#000080"))
check("a graphical button keeps its colour", b["cmdDelete"][1].get("Background"), "#ff8080")
check("a bold 12 point Arial becomes 16 pixels, bold", [b["lblTotal"][1].get(k) for k in ("FontFamily", "FontSize", "FontWeight")], ["Arial", "16", "Bold"])
check("a control with Visual Basic's standard font gets its 11 pixels, so captions are not cut off", (b["lblCustomer"][1].get("FontSize"), b["cmdQty_0"][1].get("FontSize"), b["lblCustomer"][1].get("FontWeight")), ("11", "11", None))
check("a disabled control stays disabled, and a hidden one hidden", (b["cmdDelete"][1].get("IsEnabled"), b["lblStatus"][1].get("IsVisible"), b["lblCustomer"][1].get("IsVisible")), ("false", "false", None))

# the .frx: pictures and lists
check("an Image stays an Image, stretched if it was", (b["imgLogo"][0], b["imgLogo"][1]["Width"], b["imgLogo"][1]["Stretch"]), ("Image", "32", "Fill"))
check("with no folder given, its picture comes out of the .frx into the form itself", b["imgLogo"][1].get("Source"), "data:image/bmp;base64," + __import__("base64").b64encode(BMP).decode())
ASSETS = os.path.join(WORK, "assets", "images")
r2 = convert("frmMain.frm", ASSETS)
saved = os.path.join(ASSETS, "frmMain_imgLogo.bmp")
check("given a folder, the picture is saved there as a file and the form points at it",
      (blocks(r2["vml"])["imgLogo"][1].get("Source"), os.path.isfile(saved) and open(saved, "rb").read() == BMP, r2.get("pictures")), ("images/frmMain_imgLogo.bmp", True, 1))
check("a picture kept inside the form is not counted as a saved file", r.get("pictures"), 0)
check("a list box's items are read out of the .frx (accents kept, a comma inside an item taken out)", b["lstProducts"][1].get("Items"), "Tea,Coffee ground,Crème brûlée")
check("a combo box's items are read out of the .frx too", b["cboCategory"][1].get("Items"), "Groceries,Drinks,Household")

# things that are only close, or not there
check("a Line becomes a thin rectangle in the line's colour", (b["linRule"][0], [b["linRule"][1][k] for k in ("Canvas.Left", "Canvas.Top", "Width", "Height", "Fill")]), ("Rectangle", ["16", "248", "568", "1", "#808080"]))
check("the notes say a line is only a rectangle", any(n.startswith("linRule: a line becomes a thin rectangle") for n in notes))
check("a flex grid becomes a DataGrid with its column headings", (b["grdOrders"][0], b["grdOrders"][1].get("Columns"), b["grdOrders"][1]["Width"]), ("DataGrid", "Product,Qty,Price", "568"))
check("the notes say the grid comes across empty", any("comes across empty" in n and "grdOrders" in n for n in notes))
check("an OCX control with no equal yet is a labelled frame of the same size",
      (b["sldDiscount"][0], [b["sldDiscount"][1].get(k) for k in ("Text", "Width", "Height", "Background", "BorderBrush", "BorderThickness")]),
      ("Frame", ["Slider: sldDiscount", "184", "26", "#fafafa", "#9ca3af", "1"]))
check("and the notes say so", "No equal yet for Slider: sldDiscount is shown as a labelled frame of the same size." in notes)
check("a timer and a common dialog are not on the form", ("tmrClock" in b, "dlgFile" in b), (False, False))
check("and the notes list them", any("tmrClock (Timer)" in n and "dlgFile (CommonDialog)" in n and n.startswith("Not on the form itself") for n in notes))

# code
check("the form's Load and Unload are attached to the window opening and closing", (win.get("OnOpened"), win.get("OnClosing")), ("frmMain_OnOpened", "frmMain_OnClosing"))
check("Form_Load wins over Form_Activate for the window opening", "--   Private Sub Form_Load()" in script(vml, "frmMain_OnOpened"))
check("handlers are attached by what they did: a box changing, a list being chosen from and double-clicked, a tick, a grid",
      (b["txtCustomer"][1].get("TextChanged"), b["lstProducts"][1].get("SelectionChanged"), b["lstProducts"][1].get("OnDoubleClick"), b["cboCategory"][1].get("SelectionChanged"),
       b["chkGift"][1].get("OnClick"), b["grdOrders"][1].get("OnDoubleClick"), b["cmdRefresh"][1].get("OnClick")),
      ("txtCustomer_TextChanged", "lstProducts_SelectionChanged", "lstProducts_OnDoubleClick", "cboCategory_SelectionChanged", "chkGift_OnClick", "grdOrders_OnDoubleClick", "cmdRefresh_OnClick"))
check("a picture's Click becomes its pointer being pressed", b["imgLogo"][1].get("OnPointerPressed"), "imgLogo_OnPointerPressed")
check("KeyPress becomes OnKeyDown, but where there is a KeyDown as well, KeyDown has it", (b["txtCustomer"][1].get("OnKeyDown"), b["txtPin"][1].get("OnKeyDown"), "--   Private Sub txtPin_KeyDown(KeyCode As Integer, Shift As Integer)" in script(vml, "txtPin_OnKeyDown")),
      ("txtCustomer_OnKeyDown", "txtPin_OnKeyDown", True))
body = script(vml, "cmdQty_OnClick")
check("a handler's script starts by saying where it came from and that it does not run",
      body[:3], ["-- Imported from frmMain.frm: the original Visual Basic, kept here for reference.",
                 "-- It does not run. Write what this should do below, in Lua (or change the script's language).", "--"])
check("the whole procedure is kept, first line to End Sub, with its shape", (body[3], body[-1], "--       If lstProducts.ListIndex < 0 Then Exit Sub" in body), ("--   Private Sub cmdQty_Click(Index As Integer)", "--   End Sub", True))
every = [ln for name in re.findall(r"^@Script (\w+)$", vml, re.M) for ln in script(vml, name)]
live = [ln for ln in every if not ln.startswith("--")]
check("every script is the original as comments, but for the plain steps, which are Lua with the original beside them",
      (len(every) > 80, sorted(ln.split("   -- was: ")[0] for ln in live), all("   -- was: " in ln for ln in live)),
      (True, sorted(['Vml("SetProperty", "txtCustomer", "Text", "")', 'Vml("CloseSelf")', 'Vml("FormOpenModal", "frmAbout")',
                     'Vml("FormOpenModal", "frmAbout")', 'Vml("SetProperty", "lblStatus", "IsVisible", "false")']), True))
check("nothing inside an If, or after a line that might leave early, is made to run",
      [ln for ln in every if not ln.startswith("--") and ("cmdDelete" in ln or "mOrder" in ln or "KeyAscii" in ln)], [])
check("every handler named on a control has its script in the form", sorted(set(re.findall(r"^(?:On\w+|TextChanged|SelectionChanged)=(\w+)$", vml, re.M)) - set(re.findall(r"^@Script (\w+)$", vml, re.M))), [])
check("handlers with no matching event are kept as scripts all the same", ["@Script " + n + "\n" in vml for n in ("frmMain_Activate", "frmMain_Resize", "txtPin_KeyPress", "sldDiscount_Change")], [True] * 4)
check("and the notes name them as kept but not attached",
      "Kept as scripts but not attached, because there is no matching event here yet: the form.Activate, the form.Resize, txtPin.KeyPress, sldDiscount.Change." in notes)
check("the timer's handler is left behind, and the notes say so", ("tmrClock_Timer" in vml, "Handlers for things that were not brought across were left behind: tmrClock.Timer." in notes), (False, True))
other = r.get("other_code", [])
check("the rest of the code is handed back whole: declarations, helpers, and the timer's handler",
      [ln in other for ln in ("Option Explicit", 'Private Declare Function GetTickCount Lib "kernel32" () As Long', "Dim mOrder As clsOrder", "Private Sub RefreshTotals()",
                              "Private Function LineTotal(ByVal UnitPrice As Currency, ByVal Quantity As Integer) As Currency", "Private Sub tmrClock_Timer()")], [True] * 6)
check("no attached handler is in the rest, and no Attribute line", [ln for ln in other if "cmdQty_Click(Index" in ln or "Form_Load" in ln or ln.startswith("Attribute ")], [])
check("a Declare line is not mistaken for the start of a procedure", "Private mDirty As Boolean" in other)

# notes and numbers
check("the notes start with what came across", notes[0], "frmMain: 23 controls brought across, and 12 menu items.")
check("the numbers handed back agree with the notes", (r.get("name"), r.get("controls"), r.get("menu_items"), r.get("scripts")), ("frmMain", 23, 12, 21))
check("the notes count the handlers and say plainly that the code does not run",
      "21 event handlers from frmMain.frm came across as scripts. The Visual Basic is kept as comments for reference; it does not run." in notes)
check("the notes count the code that is not in the form", "18 other lines of code in frmMain.frm (helpers, variables) are not in the form; the original file is untouched." in notes)
claims = re.compile(r"\b(runs|will run|works|is working|converted to lua|translated)\b", re.I)
check("the notes claim only the plain steps run, and say to check them", [n for n in notes if claims.search(n)],
      ["Except the plain steps, which were translated and do run: 5 lines in 5 scripts (opening and closing forms, messages, simple settings). Check them."])

# ---------------------------------------------------------------- a missing .frx
BARE = os.path.join(WORK, "bare")
os.makedirs(BARE)
shutil.copy(os.path.join(FIXTURES, "frmMain.frm"), BARE)
r3 = convert("frmMain.frm", folder=BARE)
b3 = blocks(r3.get("vml", ""))
check("a form whose .frx is missing still comes across, every control of it", (r3.get("error"), r3.get("controls"), "imgLogo" in b3, "lstProducts" in b3), (None, 23, True, True))
check("its picture and lists are left empty", (b3["imgLogo"][1].get("Source"), b3["lstProducts"][1].get("Items"), b3["txtNotes"][1].get("Text")), (None, None, None))
check("and the notes say the .frx wasn't there, for the picture, the lists and the text",
      [any(n.startswith(who) and "frmMain.frx, which wasn't beside the form" in n for n in r3["notes"]) for who in ("imgLogo: its picture", "cboCategory, lstProducts: its list", "txtNotes: its text")], [True] * 3)
with open(os.path.join(BARE, "frmMain.frx"), "wb") as f:
    f.write(b"not a real frx")
r4 = convert("frmMain.frm", folder=BARE)
check("a .frx that makes no sense is not fatal either, and the notes say what couldn't be read",
      (r4.get("error"), r4.get("controls"), any("imgLogo: its picture couldn't be read from frmMain.frx" in n for n in r4.get("notes", []))), (None, 23, True))

with open(os.path.join(FIXTURES, "frmAbout.frm"), newline="") as f:
    cut = f.read().replace("   End\r\nEnd\r\n", "   End\r\n")
with open(os.path.join(BARE, "frmCut.frm"), "w", newline="") as f:
    f.write(cut)
r5 = convert("frmCut.frm", folder=BARE)
check("a form that has lost its closing End is still read, up to where its code starts", (r5.get("error"), r5.get("controls"), r5.get("scripts")), (None, 3, 1))

# ---------------------------------------------------------------- the About box
ra = convert("frmAbout.frm")
ba = blocks(ra.get("vml", ""))
check("a fixed dialog cannot be resized, and with no menu its height is just its own", (ba["frmAbout"][1]["Title"], ba["frmAbout"][1]["Width"], ba["frmAbout"][1]["Height"], ba["frmAbout"][1].get("Resizable")),
      ("About Corner Shop", "300", "160", "false"))
check("with no menu, the canvas sits straight on the window", (ba["frmAboutCanvas"][1]["Parent"], "frmAboutRoot" in ba, "frmAboutMenu" in ba), ("frmAbout", False, False))
check("the OK button is where it was, with its handler", [ba["cmdOK"][1].get(k) for k in ("Canvas.Left", "Canvas.Top", "Width", "Height", "Content", "OnClick")], ["208", "124", "81", "25", "OK", "cmdOK_OnClick"])
check("a label that sizes itself to its text is given no size here", ("Width" in ba["lblName"][1], "Height" in ba["lblName"][1], ba["lblName"][1].get("TextWrapping")), (False, False, None))
check("14.25 point bold becomes 19 pixels, bold", (ba["lblName"][1].get("FontSize"), ba["lblName"][1].get("FontWeight"), ba["lblName"][1].get("FontFamily")), ("19", "Bold", "Arial"))
check("the About box's notes: three controls, one handler, one other line", ra.get("notes"),
      ["frmAbout: 3 controls brought across.",
       "1 event handler from frmAbout.frm came across as scripts. The Visual Basic is kept as comments for reference; it does not run.",
       "Except the plain steps, which were translated and do run: 1 line in 1 script (opening and closing forms, messages, simple settings). Check them.",
       "1 other line of code in frmAbout.frm is not in the form; the original file is untouched."])

# ---------------------------------------------------------------- a form of oddities
rx = convert("frmExtras.frm")
bx, nx = blocks(rx.get("vml", "")), rx.get("notes", [])
check("on a form that measures in pixels, the form's own size is still twips and its controls are pixels",
      (bx["frmExtras"][1]["Width"], bx["frmExtras"][1]["Height"], [bx["lvwStock"][1][k] for k in ("Canvas.Left", "Canvas.Top", "Width", "Height")]), ("400", "300", ["136", "130", "256", "100"]))
check("a fixed single border cannot be resized", bx["frmExtras"][1].get("Resizable"), "false")
check("a list view becomes a DataGrid with its column headings, and a tree a TreeView", (bx["lvwStock"][0], bx["lvwStock"][1].get("Columns"), bx["tvwGroups"][0]), ("DataGrid", "Item,In stock", "TreeView"))
check("a round, filled shape becomes a rounded, filled rectangle", (bx["shpLamp"][0], [bx["shpLamp"][1].get(k) for k in ("Fill", "Stroke", "StrokeThickness", "CornerRadius")]), ("Rectangle", ["#00ff00", "#800000", "1", "12"]))
check("a sloping line is drawn level, as thick as it was, and the notes own up to it",
      ([bx["linSlope"][1][k] for k in ("Canvas.Left", "Canvas.Top", "Width", "Height")], any(n.startswith("linSlope: a sloping line can't be drawn yet") for n in nx)), (["8", "236", "52", "2"], True))
check("two controls of a kind with no equal yet are named together", "No equal yet for HScrollBar: hsbPan, hsbZoom are shown as a labelled frame of the same size." in nx)
check("an SSTab becomes a frame captioned with its front tab; controls inside are in twips even on a pixel form",
      (bx["tabDetails"][0], bx["tabDetails"][1].get("Text"), [bx["txtStreet"][1][k] for k in ("Parent", "Canvas.Left", "Canvas.Top", "Width")]), ("Frame", "Address", ["tabDetails", "16", "36", "220"]))
check("a control on another tab is brought back into place and hidden", (bx["txtMemo"][1]["Canvas.Left"], bx["txtMemo"][1].get("IsVisible"), bx["txtStreet"][1].get("IsVisible")), ("16", "false", None))
check("the notes explain the tabs", any(n.startswith("tabDetails has 2 tabs") and "hidden" in n for n in nx))
check("a measuring scale other than twips or pixels is noted, not guessed at", any(n.startswith("picGauge: has its own measuring scale (ScaleMode 6)") for n in nx))
check("a see-through label has no background, keeps its system text colour, and its && when shortcuts are off",
      (bx["lblHint"][1].get("Background"), bx["lblHint"][1].get("Foreground"), bx["lblHint"][1].get("Text")), (None, "#6d6d6d", "Fish && Chips"))
check("a data control is not placed, and is listed", ("datStock" in bx, any("datStock (Data)" in n for n in nx)), (False, True))
check("a form with no code has no scripts and no note about code", (rx.get("scripts"), [n for n in nx if "code" in n or "handler" in n]), (0, []))

# ---------------------------------------------------------------- the forms open in the engine
def opens(text, name, wanted):
    """Load a converted form in a fresh engine: (controls found, lines of the log that show something went wrong)."""
    folder = tempfile.mkdtemp(prefix="vml-vb6-open-")
    path = os.path.join(folder, name + ".vml")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text + "\n")
    del logged[:]
    e = Engine().load(path, show=False)
    bad = [ln for ln in logged if "placeholder" in ln or "isn't in the registry" in ln or "declared again" in ln or "error" in ln.lower()]
    return [e.find(n) is not None and e.find(n).type.name for n in wanted], bad, e

kinds, bad, e1 = opens(vml, "frmMain", ["frmMain", "cmdQty_2", "optStandard", "cmdRefresh", "grdOrders", "sldDiscount", "mnuRecent_1", "linRule"])
check("the main form opens in the engine: every control is a real one, with nothing left as a placeholder",
      (kinds, bad), (["Window", "Button", "RadioButton", "Button", "DataGrid", "Frame", "MenuItem", "Rectangle"], []))
check("in the engine, the controls in the frame are its children and the picture from the .frx is showing",
      (e1.find("optStandard").parent.name, e1.find("cmdRefresh").parent.name, e1.find("imgLogo").widget.pix is not None), ("fraDelivery", "picToolbar", True))
check("in the engine, the list has its three items and the menu its shortcut", (e1.find("lstProducts").widget.count(), e1.find("mnuFileNew").action.shortcut().toString()), (3, "Ctrl+N"))
kinds, bad, _ = opens(ra["vml"], "frmAbout", ["frmAbout", "cmdOK", "lblName"])
check("the About box opens in the engine too", (kinds, bad), (["Window", "Button", "TextBlock"], []))
kinds, bad, _ = opens(rx["vml"], "frmExtras", ["shpLamp", "tabDetails", "txtMemo", "tvwGroups", "hsbPan"])
check("and so does the form of oddities", (kinds, bad), (["Rectangle", "Frame", "TextBox", "TreeView", "Frame"], []))

# ---------------------------------------------------------------- files that are not forms
rn = convert("modPricing.bas")
check("a file that is not a form is refused with a reason", ("vml" in rn, "no form was found" in rn.get("error", "")), (False, True))
rn = eng.run_importer("VB6", "ImportForm", os.path.join(SHOP, "nothing-here.frm"), "")
check("so is a file that is not there", ("vml" in rn, "no form was found" in rn.get("error", "")), (False, True))

# ---------------------------------------------------------------- the whole project
before = tree(SHOP)
OUT = os.path.join(WORK, "new", "Shop")
p = eng.run_importer("VB6", "ImportProject", os.path.join(SHOP, "Shop.vbp"), OUT)
check("the project imports without an error", p.get("error"), None)
check("the project takes its name from the .vbp, and its file is made", (p.get("name"), os.path.basename(p.get("project", "")), os.path.isfile(p.get("project", ""))), ("Shop", "Shop.vmlproj", True))
check("each form in the project is written as a .vml", (p.get("forms"), [os.path.isfile(os.path.join(OUT, f)) for f in p.get("forms", [])]), (["frmAbout.vml", "frmMain.vml"], [True, True]))
check("the start-up form is the one the .vbp names", p.get("startup"), "frmMain.vml")
check("the modules: the main form's own code, the .bas and the .cls (the About box has too little to need one)", p.get("modules"), ["frmMain_code.lua", "modPricing.lua", "clsOrder.lua"])
proj = open(os.path.join(OUT, "Shop.vmlproj"), encoding="utf-8").read().splitlines()
check("the project file names the forms, the start-up form and the modules",
      proj, ["# Visualised project", "Name=Shop", "Startup=frmMain.vml", "Form=frmAbout.vml", "Form=frmMain.vml", "Module=frmMain_code.lua", "Module=modPricing.lua", "Module=clsOrder.lua"])
mods = {m: open(os.path.join(OUT, m), encoding="utf-8").read().splitlines() for m in p.get("modules", [])}
check("every module is comments and nothing but comments", [all(ln.startswith("--") for ln in lines) and len(lines) > 8 for lines in mods.values()], [True] * 3)
check("the form's module says what it is, in four lines", mods["frmMain_code.lua"][:5],
      ["-- frmMain: the rest of frmMain.frm (Visual Basic), kept for reference.",
       "-- The event handlers are on the form's controls (Edit Script). What is here is everything else:",
       "-- the form's own routines and variables. It does not run: rewrite what you need below, in Lua,",
       "-- and every form in the project can call it.", "--"])
check("the form's module holds its helpers, not the handlers already on the controls",
      ("--   Private Sub RefreshTotals()" in mods["frmMain_code.lua"], "--   Dim mOrder As clsOrder" in mods["frmMain_code.lua"], any("cmdQty_Click(Index" in ln for ln in mods["frmMain_code.lua"])), (True, True, False))
check("a .bas module comes across under its name, without its Attribute line",
      (mods["modPricing.lua"][:3], "--   Public Const VAT_RATE As Double = 0.2" in mods["modPricing.lua"], any("Attribute" in ln for ln in mods["modPricing.lua"])),
      (["-- modPricing: imported from modPricing.bas (Visual Basic), kept for reference.",
        "-- It does not run: rewrite what you need below, in Lua, and every form in the project can call it.", "--"], True, False))
check("a class comes across without the VERSION, BEGIN ... END and Attribute lines above its code",
      (mods["clsOrder.lua"][0], mods["clsOrder.lua"][3], "--   Public Property Get Customer() As String" in mods["clsOrder.lua"], [ln for ln in mods["clsOrder.lua"] if "MultiUse" in ln or "VERSION" in ln or "Attribute" in ln]),
      ("-- clsOrder: imported from clsOrder.cls (Visual Basic), kept for reference.", "--   Option Explicit", True, []))
pm = blocks(open(os.path.join(OUT, "frmMain.vml"), encoding="utf-8").read())
check("in a project, a form's picture is saved in images/ and the form points at it",
      (pm["imgLogo"][1].get("Source"), os.path.isfile(os.path.join(OUT, "images", "frmMain_imgLogo.bmp")), p.get("pictures")), ("images/frmMain_imgLogo.bmp", True, 1))
check("the project's totals add up across its forms", (p.get("controls"), p.get("scripts")), (26, 22))
check("the summary says what came across, and that the code does not run",
      ("Shop: 2 forms brought across, with 26 controls, 12 menu items and 22 event handlers." in p.get("summary", ""), "the code does not run" in p.get("summary", ""), "1 picture saved in images/." in p.get("summary", "")), (True, True, True))
report = open(p.get("notes_file", ""), encoding="utf-8").read() if p.get("notes_file") else ""
check("IMPORT-NOTES.txt is written, with each form's notes under its name",
      (os.path.basename(p.get("notes_file", "")), report.startswith("Imported from Shop.vbp\n"), "== frmMain  (frmMain.frm)" in report, "== frmAbout  (frmAbout.frm)" in report,
       "   No equal yet for Slider: sldDiscount is shown as a labelled frame of the same size." in report), ("IMPORT-NOTES.txt", True, True, True, True))
check("the notes file claims only the plain steps run", [ln.strip()[:40] for ln in report.splitlines() if claims.search(ln)],
      ["6 plain steps of the code (opening and c", "Except the plain steps, which were trans", "Except the plain steps, which were trans"])
check("the original project folder is untouched", tree(SHOP) == before)
del logged[:]
e2 = Engine().load(os.path.join(OUT, "frmMain.vml"), show=False)
check("the imported project's start-up form opens in the engine, picture and all",
      (e2.find("cmdQty_0") is not None, e2.find("imgLogo").widget.pix is not None, [ln for ln in logged if "placeholder" in ln or "isn't in the registry" in ln]), (True, True, []))

# a project whose start-up form is not the one a guess would pick, with a form that has gone missing and awkward paths
ALT = os.path.join(WORK, "Alt")
os.makedirs(os.path.join(ALT, "forms"))
for name in ("frmMain.frm", "frmMain.frx", "frmAbout.frm"):
    shutil.copy(os.path.join(SHOP, name), os.path.join(ALT, "forms", name.upper() if name == "frmAbout.frm" else name))
shutil.copy(os.path.join(SHOP, "modPricing.bas"), ALT)
with open(os.path.join(ALT, "Alt.vbp"), "w", newline="\r\n") as f:
    f.write('Type=Exe\nForm=forms\\frmMain.frm\nForm=forms\\frmGone.frm\nForm=forms\\frmAbout.frm\nModule=modPricing; modPricing.bas\nModule=modGone; modGone.bas\nStartup="frmAbout"\nName="CornerShop"\n')
OUT2 = os.path.join(WORK, "new", "Alt")
p2 = eng.run_importer("VB6", "ImportProject", os.path.join(ALT, "Alt.vbp"), OUT2)
check("forms in a folder of their own (written with a backslash) are found, and one that has gone is passed over", (p2.get("error"), p2.get("forms")), (None, ["frmMain.vml", "frmAbout.vml"]))
check("a form whose file name has different capitals from the project's is still found", os.path.isfile(os.path.join(OUT2, "frmAbout.vml")))
check("the start-up form is the .vbp's choice, not a guess from the names", (p2.get("startup"), p2.get("name"), os.path.basename(p2.get("project", ""))), ("frmAbout.vml", "CornerShop", "CornerShop.vmlproj"))
check("a module that has gone is passed over too", p2.get("modules"), ["frmMain_code.lua", "modPricing.lua"])

# a project that starts from Sub Main falls back to a sensible form; one with no forms is an error
with open(os.path.join(ALT, "SubMain.vbp"), "w", newline="\r\n") as f:
    f.write('Type=Exe\nForm=forms\\frmAbout.frm\nForm=forms\\frmMain.frm\nModule=modPricing; modPricing.bas\nStartup="Sub Main"\nName="FromMain"\n')
p3 = eng.run_importer("VB6", "ImportProject", os.path.join(ALT, "SubMain.vbp"), os.path.join(WORK, "new", "SubMain"))
check("a project that starts in Sub Main still gets a start-up form", (p3.get("error"), p3.get("startup")), (None, "frmMain.vml"))
with open(os.path.join(ALT, "Empty.vbp"), "w", newline="\r\n") as f:
    f.write('Type=Exe\nModule=modPricing; modPricing.bas\nStartup="Sub Main"\nName="Empty"\n')
OUT4 = os.path.join(WORK, "new", "Empty")
p4 = eng.run_importer("VB6", "ImportProject", os.path.join(ALT, "Empty.vbp"), OUT4)
check("a project with no forms is refused with a reason, and no project file is made", (p4.get("error"), "project" in p4, os.path.isfile(os.path.join(OUT4, "Empty.vmlproj"))), ("no forms were found in that project", False, False))
p5 = eng.run_importer("VB6", "ImportProject", os.path.join(SHOP, "Shop.vbp"), SHOP)
check("importing into the Visual Basic project's own folder is refused, and nothing is written there", ("new folder" in p5.get("error", ""), tree(SHOP) == before), (True, True))

print(f"{sum(ok)}/{len(ok)} passed")
sys.exit(0 if all(ok) else 1)
