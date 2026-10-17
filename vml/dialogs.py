"""Visualised's own message, question and input boxes, and its file and colour choosers.

Drawn as today's desktops draw theirs: a white card with rounded corners (as round as the desktop rounds its own),
a soft shadow, a thin line round it, the title in bold at its head, the buttons on a pale band along its foot. The
colour of the window that opened it runs along its top edge and fills its main button. The text can be selected and
copied, and long messages scroll instead of running off the screen."""
from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (QApplication, QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea, QToolButton,
                               QVBoxLayout, QWidget)

NEUTRAL = "#6B7280"
EDGE = 3                                                         # (the Markdown window's frame, which keeps the old look)
SHADOW = 16                                                      # room round a box's card for its shadow
ACCENT = 3                                                       # the opener's colour along the card's top


def strong(colour):
    """A frame colour that shows against a white or pale form: darkened until it stands out (3:1 against white)."""
    c = QColor(colour)

    def lum(q):
        ch = [x / 255 for x in (q.red(), q.green(), q.blue())]
        ch = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in ch]
        return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2]
    for _ in range(12):
        if 1.05 / (lum(c) + 0.05) >= 3.0:
            break
        c = c.darker(118)
    return c


def box_sheet(edge):
    """The look of a box: white, quiet text, and buttons like the rest of Visualised (the first in the edge's colour)."""
    ink = "#FFFFFF" if edge.lightnessF() < 0.6 else "#111827"
    e, dark = edge.name(), edge.darker(115).name()
    return (f"QDialog#VmlBox {{ background: transparent; }}"
            f" QDialog#VmlBox QLabel {{ color: #1F2937; font-size: 13px; background: transparent; }}"
            f" QDialog#VmlBox QPushButton {{ background: #FFFFFF; color: #1F2937; border: 1px solid #D1D5DB; border-radius: 6px;"
            f" padding: 7px 18px; font-size: 13px; }}"
            f" QDialog#VmlBox QPushButton:hover {{ background: #F3F4F6; }}"
            f" QDialog#VmlBox QPushButton:default {{ background: {e}; color: {ink}; border: 1px solid {e}; font-weight: 600; }}"
            f" QDialog#VmlBox QPushButton:default:hover {{ background: {dark}; border-color: {dark}; }}"
            f" QDialog#VmlBox QPushButton:focus {{ outline: none; }}"
            f" QDialog#VmlBox QLineEdit {{ border: 1px solid #D1D5DB; border-radius: 8px; padding: 6px 8px; background: #FFFFFF; color: #111827; }}"
            f" QDialog#VmlBox QLineEdit:focus {{ border: 1px solid {e}; }}")
MAX_TEXT_H = 420
MIN_TEXT_W, MAX_TEXT_W = 300, 760


class _Bar(QWidget):
    """A box's own title bar, in the colour of its edge, so the edge and the bar read as one frame round all of it.
    Drag it to move the box."""

    def __init__(self, box, title, colour, look="solid"):
        super().__init__(box)
        self.box = box
        card = look == "card"                                   # a box's head: no fill, the title in bold, a quiet close
        self.setAutoFillBackground(not card)
        self.setFixedHeight(52 if card else 30)
        ink = "#FFFFFF" if colour.lightnessF() < 0.6 else "#111827"
        if card:
            self.setStyleSheet("QWidget#VmlBar { background: transparent; }"
                               " QLabel { color: #111827; font-weight: 600; font-size: 15px; background: transparent; }"
                               " QToolButton { color: #6B7280; border: none; border-radius: 6px; background: transparent; font-size: 13px; }"
                               " QToolButton:hover { background: #F3F4F6; color: #111827; }")
        else:
            self.setStyleSheet(f"_Bar, QWidget#VmlBar {{ background: {colour.name()}; }}"
                               f" QLabel {{ color: {ink}; font-weight: 600; background: transparent; }}"
                               f" QToolButton {{ color: {ink}; border: none; background: transparent; font-size: 15px; padding: 0 6px; }}"
                               f" QToolButton:hover {{ background: rgba(127,127,127,0.35); }}")
        self.setObjectName("VmlBar")
        self.setAttribute(Qt.WA_StyledBackground, True)
        row = QHBoxLayout(self)
        row.setContentsMargins(*((22, 8, 10, 0) if card else (12, 0, 4, 0)))
        self.caption = QLabel(str(title))
        row.addWidget(self.caption, 1)
        close = QToolButton()
        close.setText("\u2715")
        close.setFocusPolicy(Qt.NoFocus)
        close.setFixedSize(28, 24)
        close.clicked.connect(box.reject)
        row.addWidget(close)

    def mousePressEvent(self, e):
        handle = self.box.windowHandle()
        if e.button() == Qt.LeftButton and handle is not None:
            handle.startSystemMove()                            # the desktop moves it: works on Windows, X11 and Wayland


def corner():
    """How round this desktop draws its windows' corners: the boxes match (all four)."""
    try:
        from .registry import host_radius
        return max(host_radius())
    except Exception:                                           # (never let a corner stop a box being drawn)
        return 8


class _Framed:
    """What every box of ours shares: the card it's drawn on, and staying in front while it waits."""
    footer = None                                               # a widget along the foot, drawn on the pale band

    def card_setup(self):
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)  # our own head and card: no desktop frame
        self.setAttribute(Qt.WA_TranslucentBackground, True)    # (the corners and the shadow show what's behind)

    def paintEvent(self, e):
        from PySide6.QtCore import QRectF
        from PySide6.QtGui import QPainterPath, QPen
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        card = QRectF(self.rect()).adjusted(SHADOW, SHADOW, -SHADOW, -SHADOW)
        r = corner()
        for k in range(SHADOW, 0, -2):                          # the shadow: soft, a little below
            grow = QRectF(card).adjusted(-k * 0.6, -k * 0.35 + 3, k * 0.6, k * 0.6 + 3)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(0, 0, 0, max(1, int(5 * (1 - k / SHADOW)) + 1)))
            p.drawRoundedRect(grow, r + k * 0.6, r + k * 0.6)
        path = QPainterPath()
        path.addRoundedRect(card, r, r)
        p.fillPath(path, QColor("#FFFFFF"))
        p.save()
        p.setClipPath(path)
        p.fillRect(QRectF(card.left(), card.top(), card.width(), ACCENT), self.edge)     # the opener's colour, along the top
        if self.footer is not None and not self.footer.isHidden():
            top = self.footer.mapTo(self, self.footer.rect().topLeft()).y()
            p.fillRect(QRectF(card.left(), top, card.width(), card.bottom() - top), QColor("#F7F8FA"))
            p.setPen(QPen(QColor("#E5E7EB"), 1))
            p.drawLine(int(card.left()), top, int(card.right()), top)
        p.restore()
        p.setPen(QPen(QColor(0, 0, 0, 40), 1))
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
        p.end()

    def eventFilter(self, watched, event):
        """While this is waiting for an answer, the rest of the app is held. If the user goes to another of its
        windows (clicking it, or its close button), this comes to the front to show them why nothing happens."""
        if event.type() == QEvent.WindowActivate and watched is not self and getattr(watched, "isWindow", lambda: False)() \
                and not self.isAncestorOf(watched):
            QTimer.singleShot(0, self.front)
        return False

    def front(self):
        """Come to the front and take the keyboard: a question nobody can see holds the whole app up."""
        try:
            self.raise_()
            self.activateWindow()
            QApplication.alert(self)                            # where a desktop won't let a window push forward, it can still ask
        except RuntimeError:
            pass


class Box(_Framed, QDialog):
    def __init__(self, parent, title, message, buttons=("OK",), edge="", ask=None, picture=None):
        super().__init__(parent if parent is not None else QApplication.activeWindow())     # never adrift: it stays in front of a window
        self.setWindowTitle(str(title))
        self.card_setup()
        self.setModal(True)
        self.edge = strong(edge or NEUTRAL)
        self.setObjectName("VmlBox")
        self.setStyleSheet(box_sheet(self.edge))
        self.answer, self.buttons, self.input = "", list(buttons), None
        frame = QVBoxLayout(self)
        frame.setContentsMargins(SHADOW, SHADOW + ACCENT, SHADOW, SHADOW)
        frame.setSpacing(0)
        self.bar = _Bar(self, title, self.edge, look="card")
        frame.addWidget(self.bar)
        outer = QVBoxLayout()
        frame.addLayout(outer)
        outer.setContentsMargins(22, 2, 22, 20)
        outer.setSpacing(12)
        self.picture = None
        if picture:                                             # a picture above the words: a data: address, or a file
            from PySide6.QtGui import QPixmap
            pix = QPixmap()
            text_form = str(picture)
            if text_form.startswith("data:"):
                import base64
                pix.loadFromData(base64.b64decode(text_form.split(",", 1)[1]))
            else:
                pix.load(text_form)
            if not pix.isNull():
                self.picture = QLabel()
                self.picture.setPixmap(pix)
                self.picture.setAlignment(Qt.AlignCenter)
                outer.addWidget(self.picture)
        import re
        shown = re.sub(r"\S{40,}", lambda m: re.sub(r"([/\\_.\-])", "\\1\u200b", m.group(0)), str(message))
        text = QLabel(shown)
        text.setWordWrap(True)
        text.setTextFormat(Qt.PlainText)
        text.setTextInteractionFlags(Qt.TextSelectableByMouse)
        fm = text.fontMetrics()
        widest = max((fm.horizontalAdvance(line) for line in shown.splitlines()), default=0) + 8
        fit = max(MIN_TEXT_W, min(MAX_TEXT_W, widest))          # as wide as what it says, within reason
        text.setMinimumWidth(fit)
        text.setMaximumWidth(MAX_TEXT_W)
        text.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.text = text
        need = text.heightForWidth(fit)
        if need > MAX_TEXT_H:                                   # a long report: scroll it
            area = QScrollArea()
            area.setFrameShape(QFrame.NoFrame)
            area.setWidgetResizable(True)
            area.setWidget(text)
            area.setFixedHeight(MAX_TEXT_H)
            area.setMinimumWidth(fit + 24)
            outer.addWidget(area)
        elif str(message):
            text.setMinimumHeight(need + fm.lineSpacing() // 2)   # (a dialog sizes itself before a wrapped label knows its lines)
            outer.addWidget(text)
        if ask is not None:
            self.input = QLineEdit(str(ask))
            self.input.setMinimumWidth(440)
            self.input.selectAll()
            outer.addWidget(self.input)
        self.footer = QWidget()                                 # the buttons, on a pale band along the foot
        self.footer.setAttribute(Qt.WA_TranslucentBackground, True)
        row = QHBoxLayout(self.footer)
        row.setContentsMargins(22, 14, 22, 14)
        row.setSpacing(8)
        row.addStretch(1)
        for i, label in enumerate(self.buttons):
            b = QPushButton(label)
            b.setMinimumWidth(84)
            b.setDefault(i == 0)
            b.setAutoDefault(i == 0)
            b.clicked.connect(self.pressed)                    # a method, not a lambda holding the box: no cycle to outlive Qt
            row.addWidget(b)
        frame.addWidget(self.footer)
        if self.input is not None:
            self.input.setFocus()

    def pressed(self):
        self.choose(self.sender().text())

    def choose(self, label):
        self.answer = label
        self.accept()

    def run(self):
        """Show it and wait. Returns the button pressed ("" if it was closed another way)."""
        QTimer.singleShot(0, self.front)                        # once it is on screen
        app = QApplication.instance()
        app.installEventFilter(self)                            # (see eventFilter)
        try:
            self.exec()
        finally:
            app.removeEventFilter(self)
        self.reply = self.input.text() if self.input is not None else ""
        self.hide()
        self.deleteLater()                                      # Qt's to tidy away, now: not Python's at shutdown
        return self.answer


def message(parent, title, text, edge="", picture=None):
    Box(parent, title, text, ("OK",), edge, picture=picture).run()


def confirm(parent, title, text, edge=""):
    return Box(parent, title, text, ("Yes", "No"), edge).run() == "Yes"


def prompt(parent, title, text, default="", edge="", secret=False):
    box = Box(parent, title, text, ("OK", "Cancel"), edge, ask=default)
    if secret:
        box.input.setEchoMode(QLineEdit.Password)
    return box.reply if box.run() == "OK" else ""


def choose(parent, title, text, buttons, edge=""):
    """A question with answers of your own. Returns the one pressed ("" if the box was closed another way)."""
    return Box(parent, title, text, tuple(buttons), edge).run()


SHOW_KINDS = (("folders", "Folders", True), ("files", "Files", True), ("links", "Links", True),
              ("hidden", "Hidden", False), ("noignored", "+ .gitignore", False))


def _patterns(text):
    from . import ignore
    return ignore.patterns(text)


def _hidden_by(text, name, is_dir):
    """Does a pattern in the Hide box hide this? (.gitignore's rules: see vml/ignore.py)"""
    from . import ignore
    return ignore.hidden_by(text, name, is_dir)


def _found(text, name):
    """The Find box: a pattern (with * or ?) matches the whole name, anything else any part of it; any case."""
    from fnmatch import fnmatch
    t = text.lower()
    return fnmatch(name.lower(), t) if any(c in t for c in "*?[") else t in name.lower()


class _Showing:
    """What the file list shows (folders, files, links, hidden ones, git-ignored ones): a filter between Qt's
    file system model and the list. The folders on the way to the one being looked at always show, or the list
    would have nowhere to stand. Kept between boxes, for every app."""

    def __init__(self, fd):
        from PySide6.QtCore import QSettings, QSortFilterProxyModel
        self.settings = QSettings("Visualised", "FileBox")
        self.on = {k: str(self.settings.value(k, d)).lower() in ("true", "1") for k, _, d in SHOW_KINDS}
        self.fd = fd
        self.ignored = {}                                      # folder -> the names git ignores there (or None: no repo)
        self.find = ""                                         # the Find box: part of a name, or a pattern like *.iso
        self.hide = str(self.settings.value("hide", "") or "")   # the Hide box: patterns, as a .gitignore has them
        outer = self

        class Proxy(QSortFilterProxyModel):
            def filterAcceptsRow(self, row, parent):
                return outer.accepts(self.sourceModel(), self.sourceModel().index(row, 0, parent))
        self.proxy = Proxy(fd)
        from PySide6.QtCore import QDir
        fd.setFilter(QDir.AllEntries | QDir.NoDotAndDotDot | QDir.Hidden | QDir.System | QDir.AllDirs)
        fd.setProxyModel(self.proxy)

    def accepts(self, model, index):
        import os
        info = model.fileInfo(index)
        path = info.absoluteFilePath()
        here = self.fd.directory().absolutePath()
        if info.isDir() and (here == path or here.startswith(path.rstrip("/") + "/")):
            return True                                        # on the way to where we are
        if info.isSymLink() and not self.on["links"]:
            return False
        if info.isDir() and not self.on["folders"] and not self.fd.testOption(self.fd.Option.ShowDirsOnly):
            return False
        if info.isFile() and not info.isDir() and not self.on["files"]:
            return False
        if (info.fileName().startswith(".") or info.isHidden()) and not self.on["hidden"]:
            return False
        name = info.fileName()
        if self.hide and _hidden_by(self.hide, name, info.isDir()):
            return False
        if self.on["noignored"] and name in (self._ignored(os.path.dirname(path)) or ()):
            return False
        if self.find and not _found(self.find, name):
            return False
        return True

    def _ignored(self, folder):
        """The names in a folder that git ignores there (None outside a repository). Asked once per folder."""
        import os
        import subprocess
        if folder in self.ignored:
            return self.ignored[folder]
        names = None
        try:
            entries = os.listdir(folder)
            r = subprocess.run(["git", "-C", folder, "check-ignore", "--stdin"], input="\n".join(entries),
                               capture_output=True, text=True, timeout=3)
            if r.returncode in (0, 1):                          # 1: nothing ignored (128: not a repository)
                names = {os.path.basename(line.rstrip("/")) for line in r.stdout.splitlines() if line.strip()}
        except (OSError, subprocess.SubprocessError):
            pass
        self.ignored[folder] = names
        return names

    def set_find(self, text):
        self.find = str(text or "").strip()
        self.proxy.invalidateFilter()

    def set_hide(self, text):
        self.hide = str(text or "").strip()
        self.settings.setValue("hide", self.hide)
        self.proxy.invalidateFilter()

    def set(self, key, on):
        self.on[key] = bool(on)
        self.settings.setValue(key, "true" if on else "false")
        self.proxy.invalidateFilter()


class FileBox(_Framed, QDialog):
    """Choosing a file or folder, in the same frame as the boxes above: our own title bar (with its close button)
    and edge. Qt's own file dialog sits inside it, so it looks and behaves the same everywhere, title bar or none
    from the desktop (GNOME on Wayland gives Qt's dialogs none)."""

    def __init__(self, parent, title, start="", filters="All files (*)", mode="open", edge="", name=""):
        from PySide6.QtWidgets import QFileDialog
        super().__init__(parent if parent is not None else QApplication.activeWindow())
        self.setWindowTitle(str(title))
        self.card_setup()
        self.setModal(True)
        self.edge = strong(edge or NEUTRAL)
        self.path = ""
        frame = QVBoxLayout(self)
        frame.setContentsMargins(SHADOW + 6, SHADOW + ACCENT, SHADOW + 6, SHADOW + 6)
        frame.setSpacing(0)
        self.bar = _Bar(self, title, self.edge, look="card")
        frame.addWidget(self.bar)
        fd = QFileDialog(self, str(title), str(start or ""), str(filters or "All files (*)"))
        fd.setOption(QFileDialog.DontUseNativeDialog, True)    # a desktop's own would come with its own window again
        fd.setWindowFlags(Qt.Widget)                           # a part of this box, not a window of its own
        if mode == "save":
            fd.setAcceptMode(QFileDialog.AcceptSave)
            fd.setFileMode(QFileDialog.AnyFile)
            if name:
                fd.selectFile(str(name))
                QTimer.singleShot(0, lambda: self._name_box() and not self._name_box().text() and self._name_box().setText(str(name)))
        elif mode == "folder":
            fd.setFileMode(QFileDialog.Directory)
            fd.setOption(QFileDialog.ShowDirsOnly, True)
        else:
            fd.setFileMode(QFileDialog.ExistingFile)
        fd.accepted.connect(self._took)
        fd.rejected.connect(self.reject)
        frame.addWidget(fd)
        self.fd = fd
        self.showing = _Showing(fd)
        fd.directoryEntered.connect(lambda _: self.showing.proxy.invalidateFilter())
        row = QHBoxLayout()                                    # Show: [x] Folders [x] Files [x] Links [ ] Hidden ...
        row.setContentsMargins(12, 2, 12, 8)
        row.setSpacing(14)
        row.addWidget(QLabel("Show:"))
        from PySide6.QtWidgets import QCheckBox
        self.boxes = {}
        for key, label, _ in SHOW_KINDS:
            if (mode == "folder" and key in ("files", "folders")) or key == "noignored":
                continue                                       # (+ .gitignore sits with the Hide box)
            box = QCheckBox(label)
            box.setChecked(self.showing.on[key])
            box.toggled.connect(lambda on, k=key: self.showing.set(k, on))
            row.addWidget(box)
            self.boxes[key] = box
        row.addStretch(1)
        frame.addLayout(row)
        row2 = QHBoxLayout()                                   # Find: [   ]   Hide: [*.log  node_modules  build/]
        row2.setContentsMargins(12, 0, 12, 10)
        row2.setSpacing(10)
        row2.addWidget(QLabel("Find:"))
        self.find_box = QLineEdit()
        self.find_box.setPlaceholderText("part of a name, or *.iso")
        self.find_box.setClearButtonEnabled(True)
        self.find_box.setFixedWidth(220)
        self.find_box.textChanged.connect(self.showing.set_find)
        row2.addWidget(self.find_box)
        row2.addSpacing(12)
        row2.addWidget(QLabel("Hide:"))
        self.hide_box = QLineEdit(self.showing.hide)
        self.hide_box.setPlaceholderText("as a .gitignore: *.log  node_modules  build/  !keep.log")
        self.hide_box.setClearButtonEnabled(True)
        self.hide_box.textChanged.connect(self.showing.set_hide)
        row2.addWidget(self.hide_box, 1)
        git = QCheckBox("+ .gitignore")
        git.setToolTip("Also hide what the folder's .gitignore hides")
        git.setChecked(self.showing.on["noignored"])
        git.toggled.connect(lambda on: self.showing.set("noignored", on))
        row2.addWidget(git)
        self.boxes["noignored"] = git
        frame.addLayout(row2)
        import os
        from PySide6.QtCore import QUrl
        home = os.path.expanduser("~")                         # the usual places, Downloads among them, to one side
        places = [home] + [os.path.join(home, p) for p in ("Downloads", "Desktop", "Documents")] + ["/" if os.name != "nt" else "C:\\"]
        fd.setSidebarUrls([QUrl.fromLocalFile(p) for p in places if os.path.isdir(p)])
        from PySide6.QtWidgets import QHeaderView, QTreeView
        view = fd.findChild(QTreeView, "treeView")             # the name wide, the rest as wide as they need
        if view is not None:
            view.header().setSectionResizeMode(0, QHeaderView.Stretch)
            for c in (1, 2, 3):
                view.header().setSectionResizeMode(c, QHeaderView.ResizeToContents)
        from PySide6.QtWidgets import QSplitter
        split = fd.findChild(QSplitter, "splitter")
        if split is not None:
            split.setSizes([150, 650])
        self.resize(820, 520)

    def _name_box(self):
        return self.fd.findChild(QLineEdit, "fileNameEdit")

    def _took(self):
        files = self.fd.selectedFiles()
        self.path = files[0] if files else ""
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


class ColourBox(_Framed, QDialog):
    """Choosing a colour, in the same frame as the other boxes: Qt's colour picker sits inside our bar and edge (a
    desktop that gives Qt's own dialogs no frame would otherwise show it with none)."""

    def __init__(self, parent, start, title="Choose a colour", edge=""):
        from PySide6.QtWidgets import QColorDialog
        super().__init__(parent if parent is not None else QApplication.activeWindow())
        self.setWindowTitle(str(title))
        self.card_setup()
        self.setModal(True)
        self.edge = strong(edge or NEUTRAL)
        self.colour = QColor()
        frame = QVBoxLayout(self)
        frame.setContentsMargins(SHADOW + 6, SHADOW + ACCENT, SHADOW + 6, SHADOW + 6)
        frame.setSpacing(0)
        frame.addWidget(_Bar(self, title, self.edge, look="card"))
        cd = QColorDialog(QColor(start), self)
        cd.setWindowFlags(Qt.Widget)
        cd.setOption(QColorDialog.DontUseNativeDialog, True)
        cd.accepted.connect(lambda: (setattr(self, "colour", cd.selectedColor()), self.accept()))
        cd.rejected.connect(self.reject)
        frame.addWidget(cd)

    def run(self):
        QTimer.singleShot(0, self.front)
        self.exec()
        self.deleteLater()
        return self.colour


def choose_colour(parent, start="#FFFFFF", title="Choose a colour", edge=""):
    """A colour (a QColor: isValid() is False if the box was closed without choosing)."""
    return ColourBox(parent, start, title, edge).run()


def open_file(parent, title, start="", filters="All files (*)", edge=""):
    return FileBox(parent, title, start, filters, "open", edge).run()


def save_file(parent, title, name="", filters="All files (*)", edge=""):
    import os
    start = os.path.dirname(str(name)) if os.path.dirname(str(name)) else ""
    return FileBox(parent, title, start, filters, "save", edge, name=os.path.basename(str(name)) if start else str(name)).run()


def choose_folder(parent, title, start="", edge=""):
    return FileBox(parent, title, start, "", "folder", edge).run()
