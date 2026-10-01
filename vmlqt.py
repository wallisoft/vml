"""
VML on Qt: proof of concept.

    VML file --(Steve's Lua parser, run unchanged via lupa)--> SQL
             --> SQLite (ui_tree, ui_properties, scripts)
             --> PySide6 widgets, following Avalonia's layout rules

Usage: python3 vmlqt.py form.vml [--shot out.png]
"""
import sqlite3
import sys
from pathlib import Path

from lupa import lua54
from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtWidgets import (QApplication, QFrame, QGridLayout, QHBoxLayout, QLabel, QLayout, QLineEdit,
                               QListWidget, QPushButton, QSizePolicy, QVBoxLayout, QWidget)

HERE = Path(__file__).resolve().parent
SCHEMA = """
CREATE TABLE ui_tree (id INTEGER PRIMARY KEY AUTOINCREMENT, parent_id INTEGER, control_type TEXT, name TEXT,
                      display_order INTEGER, is_root INTEGER, source_file TEXT, imported_at INTEGER);
CREATE TABLE ui_properties (id INTEGER PRIMARY KEY AUTOINCREMENT, ui_tree_id INTEGER,
                            property_name TEXT, property_value TEXT);
CREATE TABLE scripts (name TEXT PRIMARY KEY, interpreter TEXT, instance TEXT, content TEXT,
                      source_file TEXT, created_at INTEGER);
"""


# ---------------------------------------------------------------- parse (Lua)

def parse_vml(vml_path: str) -> str:
    """Run vml-parser.lua exactly as-is inside an embedded Lua 5.4; return the SQL it prints."""
    lua = lua54.LuaRuntime(unpack_returned_tuples=True)
    out = []
    lua.globals().print = lambda *a: out.append("\t".join(str(x) for x in a))
    lua.execute("arg = {...}", vml_path)                      # arg[1] = the VML file, as on the command line
    src = (HERE / "vml-parser.lua").read_text(encoding="utf-8")
    if src.startswith("#!"):
        src = src.split("\n", 1)[1]                          # load() doesn't accept a shebang line
    lua.execute(src)
    return "\n".join(out)


def load_db(sql: str) -> sqlite3.Connection:
    db = sqlite3.connect(":memory:")
    db.executescript(SCHEMA)
    db.executescript(sql)
    return db


# ---------------------------------------------------------------- Avalonia value helpers

def thickness(v, default=(0, 0, 0, 0)):
    """Avalonia Thickness: 'u' | 'h,v' | 'l,t,r,b' -> (l, t, r, b)."""
    if not v:
        return default
    n = [int(float(x)) for x in str(v).split(",")]
    if len(n) == 1:
        return (n[0],) * 4
    if len(n) == 2:
        return (n[0], n[1], n[0], n[1])
    return tuple(n) if len(n) == 4 else default


WEIGHTS = {"Thin": 100, "Light": 300, "Normal": 400, "Medium": 500, "SemiBold": 600, "Bold": 700,
           "ExtraBold": 800, "Black": 900}


def style_for(name, p, padding=True):
    css = []
    if p.get("Background"):
        css.append(f"background-color: {p['Background']};")
    if p.get("Foreground"):
        css.append(f"color: {p['Foreground']};")
    if p.get("FontSize"):
        css.append(f"font-size: {int(float(p['FontSize']))}px;")
    if p.get("FontWeight"):
        css.append(f"font-weight: {WEIGHTS.get(p['FontWeight'], 400)};")
    if p.get("CornerRadius"):
        css.append(f"border-radius: {int(float(p['CornerRadius'].split(',')[0]))}px;")
    if padding and p.get("Padding"):
        l, t, r, b = thickness(p["Padding"])
        css.append(f"padding: {t}px {r}px {b}px {l}px;")
    return f"#{name} {{ {' '.join(css)} }}" if css else ""


# ---------------------------------------------------------------- DockPanel layout (Avalonia rules)

class DockLayout(QLayout):
    """Children dock in order (Top/Bottom/Left/Right, default Left), each carving space off the
    remaining rectangle; with LastChildFill the last child takes whatever is left."""

    def __init__(self, last_fill=True):
        super().__init__()
        self.items, self.last_fill = [], last_fill
        self.setContentsMargins(0, 0, 0, 0)

    def add(self, widget, dock):
        self.addWidget(widget)
        self.items[-1] = (self.items[-1][0], dock)

    def addItem(self, item):
        self.items.append((item, "Left"))

    def count(self):
        return len(self.items)

    def itemAt(self, i):
        return self.items[i][0] if 0 <= i < len(self.items) else None

    def takeAt(self, i):
        return self.items.pop(i)[0] if 0 <= i < len(self.items) else None

    def _measure(self, which):
        """Avalonia's measure pass: work back from the filling child, adding each docked child around it."""
        w = h = 0
        for i in range(len(self.items) - 1, -1, -1):
            item, dock = self.items[i]
            s = getattr(item, which)()
            if self.last_fill and i == len(self.items) - 1:
                w, h = s.width(), s.height()
            elif dock in ("Top", "Bottom"):
                w, h = max(w, s.width()), h + s.height()
            else:
                w, h = w + s.width(), max(h, s.height())
        return QSize(w, h)

    def sizeHint(self):
        return self._measure("sizeHint")

    def minimumSize(self):
        return self._measure("minimumSize")

    def setGeometry(self, rect):
        super().setGeometry(rect)
        r = QRect(rect)
        for i, (item, dock) in enumerate(self.items):
            if self.last_fill and i == len(self.items) - 1:
                item.setGeometry(r)
                break
            h = item.sizeHint()
            if dock == "Top":
                item.setGeometry(QRect(r.x(), r.y(), r.width(), h.height())); r.setTop(r.top() + h.height())
            elif dock == "Bottom":
                item.setGeometry(QRect(r.x(), r.bottom() - h.height() + 1, r.width(), h.height())); r.setBottom(r.bottom() - h.height())
            elif dock == "Right":
                item.setGeometry(QRect(r.right() - h.width() + 1, r.y(), h.width(), r.height())); r.setRight(r.right() - h.width())
            else:
                item.setGeometry(QRect(r.x(), r.y(), h.width(), r.height())); r.setLeft(r.left() + h.width())


# ---------------------------------------------------------------- renderer

class Renderer:
    def __init__(self, db):
        self.db = db
        self.widgets = {}                                  # name -> widget, for scripts and events later

    def props(self, cid):
        return dict(self.db.execute("SELECT property_name, property_value FROM ui_properties WHERE ui_tree_id=?", (cid,)))

    def children(self, cid):
        return self.db.execute("SELECT id, control_type, name FROM ui_tree WHERE parent_id=? ORDER BY display_order", (cid,)).fetchall()

    def render_root(self):
        cid, ctype, name = self.db.execute("SELECT id, control_type, name FROM ui_tree WHERE is_root=1 ORDER BY display_order").fetchone()
        win = self.build(cid, ctype, name)
        need = win.minimumSizeHint()
        if need.height() > win.height() or need.width() > win.width():
            print(f"note: {name} asks for {win.width()}x{win.height()} but its content needs "
                  f"{need.width()}x{need.height()}; growing to fit", file=sys.stderr)
            win.resize(win.size().expandedTo(need))
        return win

    def wrap_margin(self, w, p):
        """Avalonia Margin lives outside the control: wrap it in a container with those margins."""
        m = thickness(p.get("Margin"))
        if m == (0, 0, 0, 0):
            return w
        box = QWidget()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(*m)
        lay.addWidget(w)
        return box

    def build(self, cid, ctype, name):
        p = self.props(cid)
        kids = self.children(cid)
        w = self.make(ctype, name, p, kids)
        w.setObjectName(name)
        w.setAttribute(Qt.WA_StyledBackground, True)
        css = style_for(name, p, padding=ctype not in ("Border",))
        if css:
            extra = w.styleSheet().replace(f"#{name} {{", "").rstrip("} ") if w.styleSheet() else ""
            w.setStyleSheet(css[:-1] + " " + extra + " }" if extra else css)
        if ctype in ("TextBlock", "TextBox", "Button"):
            # Avalonia never squashes a control below its natural height (it clips instead); nor do we
            w.setSizePolicy(w.sizePolicy().horizontalPolicy(), QSizePolicy.Minimum)
        if p.get("Height") and ctype != "Window":
            w.setFixedHeight(int(float(p["Height"])))
        if p.get("Width") and ctype != "Window":
            w.setFixedWidth(int(float(p["Width"])))
        self.widgets[name] = w
        return w if ctype == "Window" else self.wrap_margin(w, p)

    def make(self, ctype, name, p, kids):
        if ctype == "Window":
            w = QWidget()
            w.setWindowTitle(p.get("Title", name))
            w.resize(int(float(p.get("Width", 800))), int(float(p.get("Height", 600))))
            lay = QVBoxLayout(w)
            lay.setContentsMargins(0, 0, 0, 0)
            for k in kids:
                lay.addWidget(self.build(*k))
            return w
        if ctype == "DockPanel":
            w = QWidget()
            lay = DockLayout(p.get("LastChildFill", "true").lower() == "true")
            w.setLayout(lay)
            for k in kids:
                lay.add(self.build(*k), self.props(k[0]).get("DockPanel.Dock", "Left"))
            return w
        if ctype == "Border":
            w = QFrame()
            lay = QVBoxLayout(w)
            lay.setContentsMargins(*thickness(p.get("Padding")))
            for k in kids:
                centre = self.props(k[0]).get("VerticalAlignment") == "Center"
                if centre:
                    lay.addStretch(1)
                lay.addWidget(self.build(*k))
                if centre:
                    lay.addStretch(1)
            return w
        if ctype == "StackPanel":
            w = QWidget()
            horiz = p.get("Orientation") == "Horizontal"
            lay = QHBoxLayout(w) if horiz else QVBoxLayout(w)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setSpacing(int(float(p.get("Spacing", 0))))
            for k in kids:
                lay.addWidget(self.build(*k))
            lay.addStretch(1)
            return w
        if ctype == "Grid":
            w = QWidget()
            lay = QGridLayout(w)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setSpacing(0)
            for axis, key in (("col", "ColumnDefinitions"), ("row", "RowDefinitions")):
                for i, d in enumerate((p.get(key) or "*").split(",")):
                    d = d.strip()
                    stretch = (int(float(d[:-1] or 1)) if d.endswith("*") else 0)
                    (lay.setColumnStretch if axis == "col" else lay.setRowStretch)(i, stretch)
                    if d not in ("Auto",) and not d.endswith("*"):
                        (lay.setColumnMinimumWidth if axis == "col" else lay.setRowMinimumHeight)(i, int(float(d)))
            for k in kids:
                kp = self.props(k[0])
                lay.addWidget(self.build(*k), int(kp.get("Grid.Row", 0)), int(kp.get("Grid.Column", 0)),
                              int(kp.get("Grid.RowSpan", 1)), int(kp.get("Grid.ColumnSpan", 1)))
            return w
        if ctype == "TextBlock":
            w = QLabel(p.get("Text", ""))
            w.setWordWrap(p.get("TextWrapping") == "Wrap")
            return w
        if ctype == "TextBox":
            w = QLineEdit(p.get("Text", ""))
            w.setPlaceholderText(p.get("Watermark", ""))
            return w
        if ctype == "Button":
            w = QPushButton(p.get("Content", name))
            if p.get("Background"):
                w.setStyleSheet(f"#{name} {{ border: none; border-radius: 6px; }}")
            return w
        if ctype == "ListBox":
            return QListWidget()
        w = QLabel(f"[{ctype} {name}]")                         # not in the registry yet: show it plainly
        w.setStyleSheet("color: orange;")
        return w


def main():
    vml = sys.argv[1]
    sql = parse_vml(vml)
    db = load_db(sql)
    n = db.execute("SELECT COUNT(*) FROM ui_tree").fetchone()[0]
    print(f"Lua parser produced {len(sql.splitlines())} SQL statements; {n} controls in ui_tree", file=sys.stderr)
    app = QApplication.instance() or QApplication(sys.argv)
    win = Renderer(db).render_root()
    win.show()
    if "--shot" in sys.argv:
        app.processEvents()
        win.grab().save(sys.argv[sys.argv.index("--shot") + 1])
        return
    app.exec()


if __name__ == "__main__":
    main()
