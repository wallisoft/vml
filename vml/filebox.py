"""
Choosing a file or a folder: Visualised's own, drawn in the desktop's colours (vml/theme.py) on the same card as
its other boxes, the same on every desktop. Laid out as today's desktops lay theirs out:

    [<] [>] [^]   Home > projects > vml-github            [ Search vml-github ] [...]
    Home          Name                          Modified          Type       Size
    Desktop       designer                      17 Oct, 12:36     Folder
    Documents     Form1.vml                     17 Oct, 17:57     VML form   1.6 KB
    Downloads     ...
    ----------
    Computer
    ==================================================================================
    File name [ Form1.vml                       ] [ VML forms (*.vml) v ]  [Save] [Cancel]

The path is a row of places to click back to (click beside it, or Ctrl+L, to type one). The search box finds as
you type (part of a name, or a pattern like *.iso). The ... menu chooses what shows: folders, files, links, hidden
ones, what a folder's .gitignore hides, and patterns to hide (as a .gitignore has them). Those choices are kept for
next time, for every app.
    Enter or a double-click opens; Backspace goes up a folder; Alt+Left and Alt+Right go back and forward.
"""
import os
import time

from PySide6.QtCore import QFileInfo, QSettings, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (QApplication, QComboBox, QDialog, QFileIconProvider, QHBoxLayout, QHeaderView, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem, QPushButton, QStackedWidget, QToolButton,
                               QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from .dialogs import ACCENT, SHADOW, Box, _Bar, _Framed, _found, _hidden_by, accent_for, box_sheet

SHOW = (("folders", "Folders", True), ("files", "Files", True), ("links", "Links", True),
        ("hidden", "Hidden files", False), ("noignored", "Hide what .gitignore hides", False))
KINDS = {".vml": "VML form", ".vmlproj": "VML project", ".lua": "Lua script", ".md": "Markdown", ".txt": "Text",
         ".png": "PNG picture", ".jpg": "JPEG picture", ".jpeg": "JPEG picture", ".svg": "SVG picture", ".iso": "Disc image",
         ".zip": "Zip archive", ".py": "Python", ".json": "JSON", ".csv": "CSV", ".pdf": "PDF", ".apk": "Android app",
         ".exe": "Program", ".sh": "Shell script", ".html": "Web page", ".db": "Database", ".sqlite": "Database"}


def parse_filters(text):
    """ "VML forms (*.vml);;All files (*)" -> [("VML forms (*.vml)", ["*.vml"]), ("All files (*)", ["*"])] """
    out = []
    for part in str(text or "").split(";;"):
        part = part.strip()
        if not part:
            continue
        pats = part[part.find("(") + 1:part.rfind(")")].split() if "(" in part else part.split()
        out.append((part, pats or ["*"]))
    return out or [("All files (*)", ["*"])]


def matches(name, patterns):
    from fnmatch import fnmatch
    return any(p == "*" or fnmatch(name.lower(), p.lower()) for p in patterns)


def nice_size(n):
    for unit in ("bytes", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n} {unit}" if unit == "bytes" else f"{n:.1f} {unit}"
        n /= 1024


def nice_time(t):
    lt, now = time.localtime(t), time.localtime()
    if lt.tm_year == now.tm_year and lt.tm_yday == now.tm_yday:
        return "Today, " + time.strftime("%H:%M", lt)
    if lt.tm_year == now.tm_year:
        return time.strftime("%-d %b, %H:%M", lt) if os.name != "nt" else time.strftime("%d %b, %H:%M", lt).lstrip("0")
    return time.strftime("%-d %b %Y", lt) if os.name != "nt" else time.strftime("%d %b %Y", lt).lstrip("0")


def places():
    """The usual places down the side, then the drives."""
    home = os.path.expanduser("~")
    first = [("Home", home)] + [(n, os.path.join(home, n)) for n in ("Desktop", "Documents", "Downloads", "Pictures")]
    out = [(n, p) for n, p in first if os.path.isdir(p)]
    drives = []
    if os.name == "nt":
        from PySide6.QtCore import QDir
        drives = [(d.absolutePath().rstrip("/"), d.absolutePath()) for d in QDir.drives()]
    else:
        drives = [("Computer", "/")]
        user = os.environ.get("USER", "")
        for base in (f"/media/{user}", "/mnt", "/run/media/" + user):
            try:
                drives += [(n, os.path.join(base, n)) for n in sorted(os.listdir(base)) if os.path.isdir(os.path.join(base, n))]
            except OSError:
                pass
    return out, drives


class _Crumbs(QWidget):
    """The path as a row of places to click back to; click beside them (or Ctrl+L) to type one instead."""

    def __init__(self, box):
        super().__init__()
        self.box = box
        self.stack = QStackedWidget()
        self.row_holder = QWidget()
        self.row = QHBoxLayout(self.row_holder)
        self.row.setContentsMargins(6, 0, 6, 0)
        self.row.setSpacing(0)
        self.edit = QLineEdit()
        self.edit.returnPressed.connect(self.typed)
        self.edit.installEventFilter(self)
        self.stack.addWidget(self.row_holder)
        self.stack.addWidget(self.edit)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.stack)
        self.setObjectName("Crumbs")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.path = ""

    def show_path(self, path):
        self.path = path
        while self.row.count():
            it = self.row.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        parts, p = [], os.path.abspath(path)
        while True:
            head, tail = os.path.split(p)
            parts.append((tail or head, p))
            if not tail or head == p:
                break
            p = head
        parts.reverse()
        home = os.path.expanduser("~")
        if path == home or path.startswith(home + os.sep):          # start from Home, as people think of it
            parts = [("Home", home)] + [x for x in parts if len(x[1]) > len(home)]
        room = max(200, self.width() - 40)
        fm = self.fontMetrics()
        shown = []
        for label, full in reversed(parts):                         # the nearest places first, as many as fit
            room -= fm.horizontalAdvance(label) + 36
            if room < 0 and shown:
                shown.append(("…", full))
                break
            shown.append((label, full))
        for i, (label, full) in enumerate(reversed(shown)):
            if i:
                sep = QLabel("›")
                sep.setObjectName("CrumbSep")
                self.row.addWidget(sep)
            b = QToolButton()
            b.setText(label)
            b.setObjectName("Crumb")
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, f=full: self.box.go(f))
            self.row.addWidget(b)
        self.row.addStretch(1)
        self.stack.setCurrentIndex(0)

    def mousePressEvent(self, e):                                   # beside the crumbs: type a path
        self.start_typing()

    def start_typing(self):
        self.edit.setText(self.path)
        self.stack.setCurrentIndex(1)
        self.edit.setFocus()
        self.edit.selectAll()

    def typed(self):
        p = os.path.expanduser(self.edit.text().strip())
        if os.path.isdir(p):
            self.box.go(p)
        elif os.path.isfile(p):
            self.box.go(os.path.dirname(p))
            self.box.name.setText(os.path.basename(p))
            self.box.accept_choice()
        else:
            self.edit.setStyleSheet("color: #DC2626;")
            QTimer.singleShot(900, lambda: self.edit.setStyleSheet(""))

    def eventFilter(self, obj, ev):
        from PySide6.QtCore import QEvent
        if obj is self.edit and ev.type() == QEvent.FocusOut:
            self.stack.setCurrentIndex(0)
        if obj is self.edit and ev.type() == QEvent.KeyPress and ev.key() == Qt.Key_Escape:
            self.stack.setCurrentIndex(0)
            return True
        return False

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.path:
            self.show_path(self.path)


class FileBox(_Framed, QDialog):
    """Choosing a file to open, a name to save as, or a folder. run() gives back the path ("" if cancelled)."""

    def __init__(self, parent, title, start="", filters="All files (*)", mode="open", edge="", name=""):
        super().__init__(parent if parent is not None else QApplication.activeWindow())
        from .theme import theme
        t = self.t = theme()
        self.setWindowTitle(str(title))
        self.card_setup()
        self.setModal(True)
        self.setObjectName("VmlBox")
        self.edge = accent_for(edge)
        self.mode, self.path = mode, ""
        self.filters = parse_filters(filters if mode != "folder" else "Folders (*)")
        self.settings = QSettings("Visualised", "FileBox")
        self.on = {k: str(self.settings.value(k, d)).lower() in ("true", "1") for k, _, d in SHOW}
        self.hide_patterns = str(self.settings.value("hide", "") or "")
        self.ignored = {}
        self.back, self.fwd, self.here = [], [], ""
        self.icons = QFileIconProvider()
        self.setStyleSheet(box_sheet(self.edge) + self.sheet())

        frame = QVBoxLayout(self)
        frame.setContentsMargins(SHADOW, SHADOW + ACCENT, SHADOW, SHADOW)
        frame.setSpacing(0)
        self.bar = _Bar(self, title, self.edge, look="card")
        frame.addWidget(self.bar)

        tools = QHBoxLayout()                                       # back, forward, up, the path, search, ...
        tools.setContentsMargins(16, 0, 16, 10)
        tools.setSpacing(4)
        self.b_back = self.tool("←", "Back (Alt+Left)", self.go_back)
        self.b_fwd = self.tool("→", "Forward (Alt+Right)", self.go_fwd)
        self.b_up = self.tool("↑", "Up a folder (Backspace)", self.go_up)
        for b in (self.b_back, self.b_fwd, self.b_up):
            tools.addWidget(b)
        tools.addSpacing(6)
        self.crumbs = _Crumbs(self)
        self.crumbs.setFixedHeight(34)
        tools.addWidget(self.crumbs, 1)
        tools.addSpacing(6)
        self.search = QLineEdit()
        self.search.setObjectName("Search")
        self.search.setClearButtonEnabled(True)
        self.search.setFixedWidth(230)
        self.search.setFixedHeight(34)
        self.search.textChanged.connect(lambda *_: self.fill())
        tools.addWidget(self.search)
        self.b_view = self.tool("⋯", "What shows", self.view_menu)
        tools.addWidget(self.b_view)
        frame.addLayout(tools)

        body = QHBoxLayout()                                        # places | the folder's contents
        body.setContentsMargins(10, 0, 16, 12)
        body.setSpacing(10)
        self.side = QListWidget()
        self.side.setObjectName("Places")
        self.side.setFixedWidth(176)
        self.side.setFocusPolicy(Qt.NoFocus)
        self.side.itemClicked.connect(lambda it: it.data(Qt.UserRole) and self.go(it.data(Qt.UserRole)))
        first, drives = places()
        for label, p in first:
            self.place(label, p)
        if drives:
            gap = QListWidgetItem("")
            gap.setFlags(Qt.NoItemFlags)
            gap.setSizeHint(QSize(10, 12))
            self.side.addItem(gap)
            for label, p in drives:
                self.place(label, p)
        body.addWidget(self.side)
        self.list = QTreeWidget()
        self.list.setObjectName("Files")
        self.list.setHeaderLabels(["Name", "Modified", "Type", "Size"])
        self.list.setRootIsDecorated(False)
        self.list.setUniformRowHeights(True)
        self.list.setIconSize(QSize(18, 18))
        self.list.setSortingEnabled(False)
        self.list.setAllColumnsShowFocus(True)
        h = self.list.header()
        h.setStretchLastSection(False)
        h.setSectionResizeMode(0, QHeaderView.Stretch)
        for c in (1, 2, 3):
            h.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        h.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.list.itemDoubleClicked.connect(self.opened)
        self.list.currentItemChanged.connect(self.picked)
        body.addWidget(self.list, 1)
        frame.addLayout(body)

        self.footer = QWidget()                                     # on the pale band: the name, the kind, the buttons
        self.footer.setAttribute(Qt.WA_TranslucentBackground, True)
        foot = QHBoxLayout(self.footer)
        foot.setContentsMargins(20, 14, 20, 14)
        foot.setSpacing(8)
        self.name = QLineEdit(str(name or ""))
        self.name.returnPressed.connect(self.accept_choice)
        if mode != "folder":
            foot.addWidget(QLabel("File name"))
            foot.addWidget(self.name, 1)
            self.kind = QComboBox()
            for label, _ in self.filters:
                self.kind.addItem(label)
            self.kind.currentIndexChanged.connect(lambda *_: self.fill())
            self.kind.setVisible(len(self.filters) > 1 or self.filters[0][1] != ["*"])
            foot.addWidget(self.kind)
        else:
            self.kind = None
            self.where = QLabel("")
            self.where.setObjectName("Muted")
            foot.addWidget(self.where, 1)
        go_words = {"open": "Open", "save": "Save", "folder": "Select folder"}[mode]
        self.ok = QPushButton(go_words)
        self.ok.setDefault(True)
        self.ok.clicked.connect(self.accept_choice)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        foot.addSpacing(8)
        foot.addWidget(self.ok)
        foot.addWidget(cancel)
        frame.addWidget(self.footer)

        for keys, fn in (("Alt+Left", self.go_back), ("Alt+Right", self.go_fwd), ("Backspace", self.go_up),
                         ("Ctrl+L", self.crumbs.start_typing), ("Ctrl+F", self.search.setFocus)):
            QShortcut(QKeySequence(keys), self, activated=fn)
        start = os.path.expanduser(str(start or "")) or os.getcwd()
        if os.path.isfile(start):
            self.name.setText(self.name.text() or os.path.basename(start))
            start = os.path.dirname(start)
        self.go(start if os.path.isdir(start) else os.path.expanduser("~"), remember=False)
        self.resize(940, 600)
        (self.name if mode == "save" else self.list).setFocus()
        if mode == "save":
            stem = os.path.splitext(self.name.text())[0]
            QTimer.singleShot(0, lambda: self.name.setSelection(0, len(stem)))

    # ------------------------------------------------------------ look
    def sheet(self):
        t, e = self.t, self.edge
        sel = QColor(e)
        sel.setAlpha(46 if not t.dark else 90)
        hov = QColor(t.ink)
        hov.setAlpha(14 if not t.dark else 22)
        rgba = lambda c: f"rgba({c.red()},{c.green()},{c.blue()},{c.alpha()})"
        return (f" QToolButton#Tool {{ border: none; border-radius: 6px; color: {t.ink}; font-size: 16px; min-width: 34px; min-height: 34px; }}"
                f" QToolButton#Tool:hover {{ background: {rgba(hov)}; }} QToolButton#Tool:disabled {{ color: {t.line}; }}"
                f" QWidget#Crumbs {{ border: 1px solid {t.line}; border-radius: 6px; background: {t.surface}; }}"
                f" QToolButton#Crumb {{ border: none; border-radius: 4px; padding: 4px 6px; color: {t.ink}; }}"
                f" QToolButton#Crumb:hover {{ background: {rgba(hov)}; }}"
                f" QLabel#CrumbSep {{ color: {t.muted}; padding: 0 2px; }} QLabel#Muted {{ color: {t.muted}; }}"
                f" QWidget#Crumbs QLineEdit {{ border: none; background: transparent; padding: 0 8px; }}"
                f" QListWidget#Places {{ border: none; background: transparent; color: {t.ink}; outline: none; }}"
                f" QListWidget#Places::item {{ height: 32px; padding-left: 8px; border-radius: 6px; }}"
                f" QListWidget#Places::item:hover {{ background: {rgba(hov)}; }}"
                f" QListWidget#Places::item:selected {{ background: {rgba(sel)}; color: {t.ink}; }}"
                f" QTreeWidget#Files {{ border: 1px solid {t.line}; border-radius: 6px; background: {t.surface}; color: {t.ink};"
                f" outline: none; selection-background-color: {rgba(sel)}; selection-color: {t.ink}; }}"
                f" QTreeWidget#Files::item {{ height: 30px; border: none; }}"
                f" QTreeWidget#Files::item:hover {{ background: {rgba(hov)}; }}"
                f" QTreeWidget#Files::item:selected {{ background: {rgba(sel)}; color: {t.ink}; }}"
                f" QHeaderView::section {{ background: {t.surface}; color: {t.muted}; border: none;"
                f" border-bottom: 1px solid {t.line}; padding: 6px 8px; font-size: 12px; }}"
                f" QComboBox {{ border: 1px solid {t.line}; border-radius: 6px; padding: 5px 10px; background: {t.surface}; color: {t.ink}; }}"
                f" QComboBox::drop-down {{ border: none; width: 22px; }}"
                f" QScrollBar:vertical {{ width: 10px; background: transparent; margin: 2px; }}"
                f" QScrollBar::handle:vertical {{ background: {t.line}; border-radius: 3px; min-height: 30px; }}"
                f" QScrollBar::handle:vertical:hover {{ background: {t.muted}; }}"
                f" QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}"
                f" QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}"
                f" QScrollBar:horizontal {{ height: 10px; background: transparent; margin: 2px; }}"
                f" QScrollBar::handle:horizontal {{ background: {t.line}; border-radius: 3px; min-width: 30px; }}")

    def tool(self, glyph, tip, fn):
        b = QToolButton()
        b.setObjectName("Tool")
        b.setText(glyph)
        b.setToolTip(tip)
        b.setCursor(Qt.PointingHandCursor)
        b.clicked.connect(fn)
        return b

    def place(self, label, path):
        it = QListWidgetItem(self.icons.icon(QFileInfo(path)), label)
        it.setData(Qt.UserRole, path)
        it.setToolTip(path)
        self.side.addItem(it)

    # ------------------------------------------------------------ moving about
    def go(self, path, remember=True):
        path = os.path.abspath(path)
        if not os.path.isdir(path):
            return
        if remember and self.here and path != self.here:
            self.back.append(self.here)
            self.fwd.clear()
        self.here = path
        self.search.clear()
        self.search.setPlaceholderText(f"Search {os.path.basename(path) or path}")
        self.crumbs.show_path(path)
        for i in range(self.side.count()):                          # the place we're in, picked out down the side
            it = self.side.item(i)
            it.setSelected(it.data(Qt.UserRole) == path)
        if self.mode == "folder":
            self.where.setText(path)
        self.fill()

    def go_back(self):
        if self.back:
            self.fwd.append(self.here)
            self.go(self.back.pop(), remember=False)

    def go_fwd(self):
        if self.fwd:
            self.back.append(self.here)
            self.go(self.fwd.pop(), remember=False)

    def go_up(self):
        if QApplication.focusWidget() in (self.name, self.search, self.crumbs.edit):
            return                                                  # (Backspace in a box deletes, as ever)
        up = os.path.dirname(self.here)
        if up and up != self.here:
            self.go(up)

    # ------------------------------------------------------------ what's here
    def shows(self, entry, is_dir):
        name = entry.name
        try:
            link = entry.is_symlink()
        except OSError:
            link = False
        if link and not self.on["links"]:
            return False
        if is_dir and not self.on["folders"] and self.mode != "folder":
            return False
        if not is_dir and (not self.on["files"] or self.mode == "folder"):
            return False
        if name.startswith(".") and not self.on["hidden"]:
            return False
        if self.hide_patterns and _hidden_by(self.hide_patterns, name, is_dir):
            return False
        if self.on["noignored"] and name in (self.git_ignored(self.here) or ()):
            return False
        find = self.search.text().strip()
        if find and not _found(find, name):
            return False
        if not is_dir and self.kind is not None:
            return matches(name, self.filters[self.kind.currentIndex()][1])
        return True

    def git_ignored(self, folder):
        if folder in self.ignored:
            return self.ignored[folder]
        import subprocess
        names = None
        try:
            r = subprocess.run(["git", "-C", folder, "check-ignore", "--stdin"], input="\n".join(os.listdir(folder)),
                               capture_output=True, text=True, timeout=3)
            if r.returncode in (0, 1):
                names = {os.path.basename(x.rstrip("/")) for x in r.stdout.splitlines() if x.strip()}
        except (OSError, Exception):
            pass
        self.ignored[folder] = names
        return names

    def fill(self):
        self.list.clear()
        rows = []
        try:
            with os.scandir(self.here) as it:
                for entry in it:
                    try:
                        is_dir = entry.is_dir()
                        st = entry.stat()
                    except OSError:
                        continue
                    if self.shows(entry, is_dir):
                        rows.append((not is_dir, entry.name.lower(), entry, is_dir, st))
        except OSError as exc:
            item = QTreeWidgetItem([f"Can't look in here: {exc.strerror or exc}", "", "", ""])
            item.setFlags(Qt.NoItemFlags)
            self.list.addTopLevelItem(item)
            rows = []
        rows.sort(key=lambda r: (r[0], r[1]))
        for _, _, entry, is_dir, st in rows:
            ext = os.path.splitext(entry.name)[1].lower()
            kind = "Folder" if is_dir else KINDS.get(ext, (ext[1:].upper() + " file") if ext else "File")
            item = QTreeWidgetItem([entry.name, nice_time(st.st_mtime), kind, "" if is_dir else nice_size(st.st_size)])
            item.setIcon(0, self.icons.icon(QFileInfo(entry.path)))
            item.setData(0, Qt.UserRole, (entry.path, is_dir))
            self.list.addTopLevelItem(item)
        self.b_back.setEnabled(bool(self.back))
        self.b_fwd.setEnabled(bool(self.fwd))
        self.b_up.setEnabled(os.path.dirname(self.here) != self.here)
        want = self.name.text().strip()
        if want:                                                    # the name being saved as, picked out if it's here
            for i in range(self.list.topLevelItemCount()):
                if self.list.topLevelItem(i).text(0) == want:
                    self.list.setCurrentItem(self.list.topLevelItem(i))
                    break

    def view_menu(self):
        from .menus import VmlMenu
        m = VmlMenu(self)
        for key, label, _ in SHOW:
            if self.mode == "folder" and key in ("files", "folders"):
                continue
            a = m.addAction(label)
            a.setCheckable(True)
            a.setChecked(self.on[key])
            a.toggled.connect(lambda on, k=key: self.set_show(k, on))
        m.addSeparator()
        m.addAction("Hide these too…" + (f"  ({self.hide_patterns})" if self.hide_patterns else "")).triggered.connect(self.ask_hide)
        m.popup(self.b_view.mapToGlobal(self.b_view.rect().bottomLeft()))

    def set_show(self, key, on):
        self.on[key] = bool(on)
        self.settings.setValue(key, "true" if on else "false")
        self.fill()

    def ask_hide(self):
        b = Box(self, "Hide these too", "Patterns to leave out, as a .gitignore has them: *.log  node_modules  build/  !keep.log",
                ("OK", "Cancel"), self.edge.name(), ask=self.hide_patterns)
        if b.run() == "OK":
            self.hide_patterns = b.reply.strip()
            self.settings.setValue("hide", self.hide_patterns)
            self.fill()

    # ------------------------------------------------------------ choosing
    def picked(self, item, _old=None):
        if item is None:
            return
        data = item.data(0, Qt.UserRole)
        if not data:
            return
        path, is_dir = data
        if not is_dir and self.mode != "folder":
            self.name.setText(os.path.basename(path))

    def opened(self, item, _col=0):
        data = item.data(0, Qt.UserRole)
        if not data:
            return
        path, is_dir = data
        if is_dir:
            self.go(path)
        elif self.mode != "folder":
            self.name.setText(os.path.basename(path))
            self.accept_choice()

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Return, Qt.Key_Enter) and self.list.hasFocus():
            item = self.list.currentItem()
            if item is not None:
                self.opened(item)
                return
        super().keyPressEvent(e)

    def accept_choice(self):
        if self.mode == "folder":
            item = self.list.currentItem()
            data = item.data(0, Qt.UserRole) if item is not None and item.isSelected() else None
            self.path = data[0] if data and data[1] else self.here
            self.accept()
            return
        typed = os.path.expanduser(self.name.text().strip())
        if not typed:
            return
        path = typed if os.path.isabs(typed) else os.path.join(self.here, typed)
        if os.path.isdir(path):                                     # a folder's name: go into it
            self.go(path)
            self.name.clear()
            return
        if self.mode == "open":
            if not os.path.isfile(path):
                Box(self, "Not found", f"There's no file called {os.path.basename(path)} here.", ("OK",), self.edge.name()).run()
                return
        else:
            pats = self.filters[self.kind.currentIndex()][1] if self.kind is not None else ["*"]
            if not os.path.splitext(path)[1] and len(pats) == 1 and pats[0].startswith("*.") and "*" not in pats[0][2:]:
                path += pats[0][1:]                                 # Form1 -> Form1.vml
            if os.path.exists(path):
                answer = Box(self, "Replace it?", f"{os.path.basename(path)} is here already. Replace it?",
                             ("Replace", "Cancel"), self.edge.name()).run()
                if answer != "Replace":
                    return
        self.path = path
        self.accept()

    def run(self):
        """Show it and wait. Returns the path chosen, or "" if the user closed it."""
        QTimer.singleShot(0, self.front)
        app = QApplication.instance()
        app.installEventFilter(self)
        try:
            self.exec()
        finally:
            app.removeEventFilter(self)
        self.hide()
        self.deleteLater()
        return self.path
