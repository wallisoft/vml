"""Choosing a file or folder (vml/filebox.py): what shows, finding, moving about, and what comes back."""
import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("VML_PREFS", os.path.join(tempfile.mkdtemp(prefix="vml-prefs-"), "prefs.json"))
from PySide6.QtCore import QSettings, QTimer
from PySide6.QtWidgets import QApplication
from vml.filebox import FileBox, parse_filters, matches
from vml import dialogs

ok = []
def check(label, got, want):
    passed = got == want
    ok.append(passed)
    print(f"{'PASS' if passed else 'FAIL'}  {label}: {got!r}" + ("" if passed else f" (wanted {want!r})"))

app = QApplication.instance() or QApplication([])
saved = QSettings("Visualised", "FileBox")               # (the user's own choices: put back at the end)
kept = {k: saved.value(k) for k in saved.allKeys()}
saved.clear()
d = tempfile.mkdtemp(prefix="vml-fb-")
os.makedirs(os.path.join(d, "sub", "deeper"))
for n in ("Form1.vml", "notes.txt", ".secret", "Mountie.vml"):
    open(os.path.join(d, n), "w").write("x")

check("filters are read as VB and Qt write them", parse_filters("VML forms (*.vml);;All files (*)"),
      [("VML forms (*.vml)", ["*.vml"]), ("All files (*)", ["*"])])
check("a pattern matches whatever the case", (matches("FORM.VML", ["*.vml"]), matches("a.txt", ["*.vml"])), (True, False))

names = lambda b: [b.list.topLevelItem(i).text(0) for i in range(b.list.topLevelItemCount())]
b = FileBox(None, "Open", d, "VML forms (*.vml);;All files (*)", "open")
check("folders first, then the files of the kind chosen; hidden ones left out", names(b), ["sub", "Form1.vml", "Mountie.vml"])
b.kind.setCurrentIndex(1)
check("All files shows the rest", names(b), ["sub", "Form1.vml", "Mountie.vml", "notes.txt"])
b.set_show("hidden", True)
check("hidden ones when asked", ".secret" in names(b), True)
b.set_show("hidden", False)
b.search.setText("mount")
check("the search finds part of a name, any case", names(b), ["Mountie.vml"])
b.search.setText("*.txt")
check("...or a pattern", names(b), ["notes.txt"])
b.search.clear()
b.go(os.path.join(d, "sub"))
check("into a folder: the path shows it, Back is there", (b.here.endswith("sub"), b.b_back.isEnabled()), (True, True))
b.go_back()
check("Back comes back, Forward goes again", (b.here == d, b.b_fwd.isEnabled()), (True, True))
b.go_fwd(); b.go_up()
check("Up goes up", b.here, d)
b.name.setText("Form1.vml"); b.accept_choice()
check("open: a file that's there comes back", b.path, os.path.join(d, "Form1.vml"))

s = FileBox(None, "Save", d, "VML forms (*.vml)", "save", name="NewForm")
s.accept_choice()
check("save: the kind's extension goes on a bare name", s.path, os.path.join(d, "NewForm.vml"))
s2 = FileBox(None, "Save", d, "VML forms (*.vml)", "save", name="Form1.vml")
QTimer.singleShot(200, lambda: next(x for x in app.topLevelWidgets() if isinstance(x, dialogs.Box) and x.isVisible()).choose("Cancel"))
s2.accept_choice()
check("save over a file asks first (and Cancel keeps it)", s2.path, "")
s3 = FileBox(None, "Save", d, "VML forms (*.vml)", "save", name="Form1.vml")
QTimer.singleShot(200, lambda: next(x for x in app.topLevelWidgets() if isinstance(x, dialogs.Box) and x.isVisible()).choose("Replace"))
s3.accept_choice()
check("...and Replace goes ahead", s3.path, os.path.join(d, "Form1.vml"))

f = FileBox(None, "Folder", d, "", "folder")
check("folder: only folders show", names(f), ["sub"])
f.accept_choice()
check("Select folder with none picked gives the one we're in", f.path, d)

saved.clear()
for k, v in kept.items():
    saved.setValue(k, v)
print(f"{sum(ok)}/{len(ok)} passed")
sys.exit(0 if all(ok) else 1)
