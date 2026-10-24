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


def accent_for(edge):
    """The colour a box wears: the window's that opened it, else the desktop's accent; made strong enough to read
    as a button and a line on a light card (a dark card shows any colour well enough)."""
    from .theme import theme
    t = theme()
    c = QColor(edge or t.accent)
    return c if t.dark else strong(c)


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
    """The look of a box, in the desktop's colours (vml/theme.py), light or dark: its buttons like the rest of
    Visualised, the first in the colour it was given (the window's that opened it, or the desktop's accent)."""
    from .theme import theme
    t = theme()
    ink = "#FFFFFF" if edge.lightnessF() < 0.6 else "#111827"
    e, dark = edge.name(), edge.darker(115).name()
    return (f"QDialog#VmlBox {{ background: transparent; }}"
            f" QDialog#VmlBox QLabel {{ color: {t.ink}; font-size: 13px; background: transparent; }}"
            f" QDialog#VmlBox QPushButton {{ background: {t.surface}; color: {t.ink}; border: 1px solid {t.line}; border-radius: 6px;"
            f" padding: 7px 18px; font-size: 13px; }}"
            f" QDialog#VmlBox QPushButton:hover {{ background: {t.band}; }}"
            f" QDialog#VmlBox QPushButton:default {{ background: {e}; color: {ink}; border: 1px solid {e}; font-weight: 600; }}"
            f" QDialog#VmlBox QPushButton:default:hover {{ background: {dark}; border-color: {dark}; }}"
            f" QDialog#VmlBox QPushButton:focus {{ outline: none; }}"
            f" QDialog#VmlBox QLineEdit {{ border: 1px solid {t.line}; border-radius: 6px; padding: 6px 8px; background: {t.surface}; color: {t.ink}; }}"
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
            from .theme import theme
            t = theme()
            self.setStyleSheet("QWidget#VmlBar { background: transparent; }"
                               f" QLabel {{ color: {t.ink}; font-weight: 600; font-size: 15px; background: transparent; }}"
                               f" QToolButton {{ color: {t.muted}; border: none; border-radius: 6px; background: transparent; font-size: 13px; }}"
                               f" QToolButton:hover {{ background: {t.band}; color: {t.ink}; }}")
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
        from .theme import theme
        return theme().corner()
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
        from .theme import theme
        t = theme()
        path = QPainterPath()
        path.addRoundedRect(card, r, r)
        p.fillPath(path, QColor(t.surface))
        p.save()
        p.setClipPath(path)
        p.fillRect(QRectF(card.left(), card.top(), card.width(), ACCENT), self.edge)     # the opener's colour, along the top
        if self.footer is not None and not self.footer.isHidden():
            top = self.footer.mapTo(self, self.footer.rect().topLeft()).y()
            p.fillRect(QRectF(card.left(), top, card.width(), card.bottom() - top), QColor(t.band))
            p.setPen(QPen(QColor(t.line), 1))
            p.drawLine(int(card.left()), top, int(card.right()), top)
        p.restore()
        p.setPen(QPen(QColor(255, 255, 255, 30) if t.dark else QColor(0, 0, 0, 40), 1))
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
        self.edge = accent_for(edge)
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


def __getattr__(name):
    """FileBox lives in vml/filebox.py (it's built from the pieces above): dialogs.FileBox still finds it."""
    if name == "FileBox":
        from .filebox import FileBox
        return FileBox
    raise AttributeError(name)


class ColourBox(_Framed, QDialog):
    """Choosing a colour, in the same frame as the other boxes: Qt's colour picker sits inside our bar and edge (a
    desktop that gives Qt's own dialogs no frame would otherwise show it with none)."""

    def __init__(self, parent, start, title="Choose a colour", edge=""):
        from PySide6.QtWidgets import QColorDialog
        super().__init__(parent if parent is not None else QApplication.activeWindow())
        self.setWindowTitle(str(title))
        self.card_setup()
        self.setModal(True)
        self.edge = accent_for(edge)
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


class ItemsBox(_Framed, QDialog):
    """Edit a list of items — a ListBox or ComboBox's, one to a line: add, rename (double-click), remove, reorder
    (the arrows, or drag). Returns the list, or None if cancelled. Drawn in the same card as the other boxes."""

    def __init__(self, parent, items, title="Edit items", edge=""):
        from PySide6.QtWidgets import QAbstractItemView, QListWidget, QListWidgetItem
        super().__init__(parent if parent is not None else QApplication.activeWindow())
        self.setWindowTitle(str(title))
        self.card_setup()
        self.setModal(True)
        self.edge = accent_for(edge)
        self.result = None
        self.setObjectName("VmlBox")
        from .theme import theme
        t = theme()
        self.setStyleSheet(box_sheet(self.edge)
                           + f" QDialog#VmlBox QListWidget {{ border: 1px solid {t.line}; border-radius: 6px;"
                             f" background: {t.surface}; color: {t.ink}; }}"
                             f" QDialog#VmlBox QListWidget::item {{ padding: 4px 6px; }}"
                             f" QDialog#VmlBox QListWidget::item:selected {{ background: {self.edge.name()}; color: #FFFFFF; }}")
        frame = QVBoxLayout(self)
        frame.setContentsMargins(SHADOW, SHADOW + ACCENT, SHADOW, SHADOW)
        frame.setSpacing(0)
        frame.addWidget(_Bar(self, title, self.edge, look="card"))
        outer = QVBoxLayout()
        frame.addLayout(outer)
        outer.setContentsMargins(22, 2, 22, 16)
        outer.setSpacing(10)

        self.list = QListWidget()
        self.list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.list.setDragDropMode(QAbstractItemView.InternalMove)
        self.list.setMinimumSize(360, 240)
        self.list.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        self._ItemClass = QListWidgetItem
        for it in items:
            self._add_row(str(it))
        outer.addWidget(self.list, 1)

        add = QHBoxLayout()
        add.setSpacing(6)
        self.entry = QLineEdit()
        self.entry.setPlaceholderText("New item — type and press Add (or Enter)")
        self.entry.returnPressed.connect(self._add_from_entry)
        addbtn = QPushButton("Add")
        addbtn.setAutoDefault(False)
        addbtn.clicked.connect(self._add_from_entry)
        add.addWidget(self.entry, 1)
        add.addWidget(addbtn)
        outer.addLayout(add)

        tools = QHBoxLayout()
        tools.setSpacing(6)
        for label, slot in (("↑ Up", lambda: self._move(-1)), ("↓ Down", lambda: self._move(1)),
                            ("Edit", self._edit), ("Script…", self._edit_script), ("Remove", self._remove)):
            b = QPushButton(label)
            b.setAutoDefault(False)
            b.clicked.connect(slot)
            tools.addWidget(b)
        tools.addStretch(1)
        outer.addLayout(tools)

        self.footer = QWidget()
        self.footer.setAttribute(Qt.WA_TranslucentBackground, True)
        row = QHBoxLayout(self.footer)
        row.setContentsMargins(22, 14, 22, 14)
        row.setSpacing(8)
        row.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.setAutoDefault(False)
        cancel.setMinimumWidth(84)
        cancel.clicked.connect(self.reject)
        ok = QPushButton("OK")
        ok.setDefault(True)
        ok.setAutoDefault(True)
        ok.setMinimumWidth(84)
        ok.clicked.connect(self._ok)
        row.addWidget(cancel)
        row.addWidget(ok)
        frame.addWidget(self.footer)

    def _add_row(self, text):
        label, _, script = str(text).partition("::")        # an item may arrive as Label::ScriptName
        it = self._ItemClass(label.strip())
        it.setFlags(it.flags() | Qt.ItemIsEditable)
        script = script.strip()
        if script:
            it.setData(Qt.UserRole, script)
            it.setToolTip(f"⚡ runs: {script}")
        self.list.addItem(it)
        return it

    def _edit_script(self):
        it = self.list.currentItem()
        if it is None:
            return
        cur = it.data(Qt.UserRole) or ""
        box = Box(self, "Item script", "The @Script to run when this item is used (blank for none):",
                  ("OK", "Cancel"), self.edge.name(), ask=cur)
        if box.run() == "OK":
            s = box.reply.strip()
            it.setData(Qt.UserRole, s or None)
            it.setToolTip(f"⚡ runs: {s}" if s else "")

    def _add_from_entry(self):
        t = self.entry.text().strip()
        if t:
            self.list.setCurrentItem(self._add_row(t))
            self.entry.clear()
        self.entry.setFocus()

    def _edit(self):
        it = self.list.currentItem()
        if it is not None:
            self.list.editItem(it)                        # rename the selected item in place (same as double-click)

    def _remove(self):
        r = self.list.currentRow()
        if r >= 0:
            self.list.takeItem(r)

    def _move(self, d):
        r = self.list.currentRow()
        if r < 0 or not (0 <= r + d < self.list.count()):
            return
        self.list.insertItem(r + d, self.list.takeItem(r))
        self.list.setCurrentRow(r + d)

    def _ok(self):
        out = []
        for i in range(self.list.count()):
            it = self.list.item(i)
            label = it.text().strip()
            if not label:
                continue
            s = it.data(Qt.UserRole)
            out.append(f"{label}::{s}" if s else label)
        self.result = out
        self.accept()

    def run(self):
        QTimer.singleShot(0, self.front)
        app = QApplication.instance()
        app.installEventFilter(self)
        try:
            self.exec()
        finally:
            app.removeEventFilter(self)
        self.deleteLater()
        return self.result


def edit_list(parent, items, title="Edit items", edge=""):
    """Edit a list of strings in a box. Returns the new list, or None if cancelled."""
    return ItemsBox(parent, list(items), title, edge).run()


def open_file(parent, title, start="", filters="All files (*)", edge=""):
    from .filebox import FileBox
    return FileBox(parent, title, start, filters, "open", edge).run()


def save_file(parent, title, name="", filters="All files (*)", edge=""):
    from .filebox import FileBox
    import os
    start = os.path.dirname(str(name)) if os.path.dirname(str(name)) else ""
    return FileBox(parent, title, start, filters, "save", edge, name=os.path.basename(str(name)) if start else str(name)).run()


def choose_folder(parent, title, start="", edge=""):
    from .filebox import FileBox
    return FileBox(parent, title, start, "", "folder", edge).run()
