"""The controls added in 1.0: option buttons, a password box, pictures, a grid, a tree; the window's edge; dialogs."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("VML_PREFS", os.path.join(__import__("tempfile").mkdtemp(prefix="vml-prefs-"), "prefs.json"))   # never the real settings
from PySide6.QtCore import QPoint, QTimer, Qt
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLineEdit, QPushButton
from vml import dialogs
from vml.engine import Engine

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
eng = Engine().load(os.path.join(HERE, "tests", "controls", "controls.vml"))
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

def steps():
    settle()
    # ---- option buttons
    check("option buttons start as the form says", [get(n, "IsChecked") for n in ("optSmall", "optLarge", "optRed", "optBlue")], ["true", "false", "true", "false"])
    QTest.mouseClick(w("optLarge"), Qt.LeftButton, pos=QPoint(8, 8)); settle()
    check("choosing one clears the other in its group", (get("optSmall", "IsChecked"), get("optLarge", "IsChecked")), ("false", "true"))
    check("...and leaves another group alone", (get("optRed", "IsChecked"), get("optBlue", "IsChecked")), ("true", "false"))
    check("...and one inside a frame is its own set", (get("optPost", "IsChecked"), get("optCourier", "IsChecked")), ("true", "false"))
    check("OnChecked ran for the one chosen", get("lblSize", "Text"), "size: Large")
    QTest.mouseClick(w("optLarge"), Qt.LeftButton, pos=QPoint(8, 8)); settle()
    check("clicking the chosen one leaves it chosen", get("optLarge", "IsChecked"), "true")
    eng.cmd_SetProperty("optBlue", "IsChecked", "true"); settle()
    check("a script choosing one clears its group too", (get("optRed", "IsChecked"), get("optBlue", "IsChecked")), ("false", "true"))
    QTest.mouseClick(w("optCourier"), Qt.LeftButton, pos=QPoint(8, 8)); settle()
    check("inside the frame, choosing works the same", (get("optPost", "IsChecked"), get("optCourier", "IsChecked"), get("optLarge", "IsChecked")), ("false", "true", "true"))

    # ---- password box
    check("a password box hides what is typed, and scripts still read it", (w("txtSecret").echoMode() == QLineEdit.Password, get("txtSecret", "Text")), (True, "hunter2"))
    eng.cmd_SetProperty("txtSecret", "IsPassword", "false")
    check("...and can be shown again", w("txtSecret").echoMode() == QLineEdit.Normal)

    # ---- pictures
    check("a picture beside the form is found and loaded", (w("imgDot").pix is not None, w("imgDot").pix.width() if w("imgDot").pix else 0), (True, 16))
    check("it is drawn at the control's size, in its own colour", (w("imgDot").width(), w("imgDot").height(), w("imgDot").grab().toImage().pixelColor(30, 20).name()), (64, 48, "#2563eb"))
    check("a picture kept inside the form (a data: address) loads too", w("imgInline").pix is not None)
    check("a picture that isn't there shows nothing, and breaks nothing", (w("imgMissing").pix, w("imgMissing").width()), (None, 40))
    eng.cmd_SetProperty("imgMissing", "Source", "dot.png"); settle()
    check("setting Source later loads it", w("imgMissing").pix is not None)

    # ---- grid
    g = w("grid")
    check("a grid shows the rows written into the form, under its headings", (g.columnCount(), g.rowCount(), g.horizontalHeaderItem(1).text(), g.item(2, 0).text()), (2, 3, "Age", "Cy, Jr"))
    check("nothing is selected to begin with", (get("grid", "SelectedIndex"), get("grid", "SelectedValue"), get("grid", "SelectedItem")), (-1, "", ""))
    g.setCurrentCell(1, 0); settle()
    check("selecting a row tells the script which, with the whole row", get("lblGrid", "Text"), '1 Bob {"Name": "Bob", "Age": "27"}')
    eng.cmd_SetProperty("grid", "SelectedIndex", "0"); settle()
    check("a script can select a row", (get("grid", "SelectedIndex"), get("grid", "SelectedValue")), (0, "Ann"))
    g.cellDoubleClicked.emit(0, 0); settle()
    check("double-clicking a row runs OnDoubleClick", eng.store.get_setting("opened"), "grid:Ann")
    n = eng.cmd_GridSetData("grid", json.dumps([{"City": "Leeds", "Pop": 800}, {"City": "York", "Pop": 200}])); settle()
    check("GridSetData replaces the rows and takes headings from the data", (n, g.horizontalHeaderItem(0).text(), g.item(1, 1).text(), get("grid", "RowCount")), (2, "City", "200", 2))
    check("GridGetData hands them back", json.loads(eng.cmd_GridGetData("grid"))[1], {"City": "York", "Pop": "200"})
    check("a grid can't be typed into", g.editTriggers() == g.EditTrigger.NoEditTriggers)

    # ---- tree
    t = w("tree")
    check("a tree is built from paths", (t.topLevelItemCount(), t.topLevelItem(0).text(0), t.topLevelItem(0).childCount(), t.topLevelItem(0).child(1).text(0), t.topLevelItem(2).text(0)), (3, "Forms", 2, "Login", "Notes"))
    check("it starts expanded", t.topLevelItem(0).isExpanded())
    t.setCurrentItem(t.topLevelItem(0).child(1)); settle()
    check("selecting an item gives its whole path", (get("lblTree", "Text"), get("tree", "SelectedItem")), ("Forms/Login", "Forms/Login"))
    eng.cmd_SetProperty("tree", "SelectedItem", "Modules/helpers"); settle()
    check("a script can select by path (and, as everywhere, that isn't a user's click: no event)", (get("tree", "SelectedItem"), get("lblTree", "Text")), ("Modules/helpers", "Forms/Login"))
    t.itemDoubleClicked.emit(t.currentItem(), 0); settle()
    check("double-clicking runs OnDoubleClick", eng.store.get_setting("opened"), "tree:Modules/helpers")
    eng.cmd_SetProperty("tree", "Items", "Modules/helpers,Modules/extra"); settle()
    check("new Items keep the selection when it is still there", (t.topLevelItemCount(), get("tree", "SelectedItem")), (1, "Modules/helpers"))
    w("lst").setCurrentRow(1); w("lst").itemDoubleClicked.emit(w("lst").currentItem()); settle()
    check("a list has OnDoubleClick too", eng.store.get_setting("opened"), "list:Two")

    # ---- the window's edge
    win = w("Controls")
    from vml.theme import theme
    check("a plain form has an edge all the same: 2px, a quiet grey", (win.edge_name(), win.edge.width_px), (theme().edge.lower(), 2))
    eng.cmd_SetProperty("Controls", "BorderBrush", "#1E3A8A"); settle()
    img = win.grab().toImage()
    check("BorderBrush draws its edge round the window (2px unless it says)", (win.edge_name(), img.pixelColor(0, 100).name(), img.pixelColor(img.width() - 1, 100).name(), img.pixelColor(100, img.height() - 1).name(), img.pixelColor(3, 100).name()),
          ("#1e3a8a", "#1e3a8a", "#1e3a8a", "#1e3a8a", "#ffffff"))
    check("...without moving or shrinking what is inside", (w("ControlsCanvas").width(), w("ControlsCanvas").x()), (win.width(), 0))
    eng.cmd_SetProperty("Controls", "BorderThickness", "0"); settle()
    check("BorderThickness=0 takes it away", win.edge_name(), "")
    eng.cmd_SetProperty("Controls", "BorderThickness", "1"); settle()

    # the designer's own windows wear the colour of their menu bar
    eng.load(os.path.join(HERE, "designer", "designer.vml")); settle()
    dwin = eng.find("Designer").widget
    check("a form with a coloured menu bar gets an edge to match, unasked", dwin.edge_name(), "#1e3a8a")

    # ---- Visualised's own dialogs
    seen = {}
    def press(label, typed=None, tries=[0]):
        tries[0] = 0
        def go():
            box = next((x for x in app.topLevelWidgets() if isinstance(x, dialogs.Box) and x.isVisible()), None)
            if box is None:                                    # not on screen yet (a slower machine): look again
                tries[0] += 1
                if tries[0] < 100:
                    QTimer.singleShot(100, go)
                return
            seen["edge"], seen["text"], seen["buttons"] = box.edge.name(), box.text.text(), box.buttons
            seen["selectable"] = bool(box.text.textInteractionFlags() & Qt.TextSelectableByMouse)
            if typed is not None:
                box.input.setText(typed)
            next(b for b in box.findChildren(QPushButton) if b.text() == label).click()
        QTimer.singleShot(150, go)
    press("OK"); eng.cmd_InfoDialog("Saved to disk.", "Done")
    check("a message box has its window's edge colour, and text that can be copied", (seen["edge"], seen["text"], seen["buttons"], seen["selectable"]), ("#1e3a8a", "Saved to disk.", ["OK"], True))
    press("Yes"); yes = eng.cmd_ConfirmDialog("Really?", "Sure")
    press("No"); no = eng.cmd_ConfirmDialog("Really?", "Sure")
    check("a question answers Yes or No", (yes, no), (True, False))
    press("OK", "VSL1-abc"); typed = eng.cmd_PromptDialog("Key", "Paste it:", "")
    press("Cancel", "ignored"); cancelled = eng.cmd_PromptDialog("Key", "Paste it:", "start")
    check("a prompt hands back what was typed, or nothing if cancelled", (typed, cancelled), ("VSL1-abc", ""))
    long = dialogs.Box(None, "Report", "\n".join(f"line {i}: something was brought across" for i in range(120)))
    check("a long message scrolls instead of running off the screen", long.sizeHint().height() < 620)
    one = "That project couldn't be imported: choose a new folder for the Visualised project, not the original one."
    wide = dialogs.Box(None, "Import", one, edge="#1e3a8a")
    check("a box is as wide as what it says, so one line stays one line", wide.text.heightForWidth(wide.text.minimumWidth()) <= wide.text.fontMetrics().lineSpacing() + 2)
    wide.resize(wide.sizeHint())
    shot = wide.grab().toImage()
    from vml.dialogs import SHADOW, ACCENT
    mid = shot.width() // 2
    check("drawn as a card: its own head, no desktop frame, the opener's colour along its top, see-through round it",
          (wide.bar.caption.text(), bool(wide.windowFlags() & Qt.FramelessWindowHint), shot.pixelColor(mid, SHADOW + 1).name(),
           shot.pixelColor(0, 0).alpha()),
          ("Import", True, "#1e3a8a", 0))
    check("its buttons sit on a pale band along the foot",
          shot.pixelColor(SHADOW + 30, wide.footer.mapTo(wide, wide.footer.rect().topLeft()).y() + 6).name(), "#f7f8fa")

    # ---- on the design surface
    for kind in ("RadioButton", "Image", "DataGrid", "TreeView"):
        name = eng.cmd_AddDesignControl(kind, 40, 40)
        check(f"the designer can add a {kind}", (name, eng.cmd_GetControlType(name)), (f"{kind}1", kind))
    check("a new option button is captioned with its name", get("RadioButton1", "Content"), "RadioButton1")
    eng.cmd_SetProperty("TextBox1", "IsPassword", "true") if eng.find("TextBox1") else None
    path = os.path.join(__import__("tempfile").mkdtemp(prefix="vml-controls-"), "saved.vml")
    eng.cmd_ExportVml("Surface", path)
    text = open(path, encoding="utf-8").read()
    check("they are saved as ordinary VML", all(f"@{k} {k}1" in text for k in ("RadioButton", "Image", "DataGrid", "TreeView")))
    check("...and open again", (eng.cmd_ImportVml(path, "Surface"), eng.cmd_GetControlType("DataGrid1"), get("TreeView1", "Items")), (True, "DataGrid", "Parent/Child One,Parent/Child Two,Other"))
    eng.cmd_SetProperty("Surface", "FormBorder", "#B91C1C")
    eng.cmd_ExportVml("Surface", path)
    check("a designed form can have an edge colour of its own, saved on its window", "BorderBrush=#B91C1C" in open(path, encoding="utf-8").read().split("@Canvas")[0])
    eng.cmd_ClearDesign("Surface")
    check("a new form starts without the last one's edge", get("Surface", "FormBorder"), "")
    check("...and opening the saved one brings it back", (eng.cmd_ImportVml(path, "Surface"), get("Surface", "FormBorder")), (True, "#B91C1C"))
    eng.cmd_PreviewDesign("Surface"); settle()
    prev = [x for x in eng.windows if "vml-preview" in x.scope][-1]
    check("running it shows that edge", prev.widget.edge_name(), "#b91c1c")
    print(f"\n{sum(ok)}/{len(ok)} passed")
    app.quit()

def guarded():
    """Run the steps; if one raises, say what and stop, rather than leave the event loop running for ever."""
    import traceback
    try:
        steps()
    except Exception:
        traceback.print_exc()
        ok.append(False)
        app.quit()


QTimer.singleShot(400, guarded)
app.exec()
sys.exit(0 if all(ok) else 1)
