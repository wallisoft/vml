"""Visualised's own message, question and input boxes.

They have their own title bar and a thin edge, both in the colour of the window that opened them, so the frame goes
all the way round and a white box over a white form can still be seen; the text can be selected and copied, and long messages scroll instead of running off the screen."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea, QToolButton,
                               QVBoxLayout, QWidget)

NEUTRAL = "#6B7280"
MAX_TEXT_H = 420
MIN_TEXT_W, MAX_TEXT_W = 300, 760


class _Bar(QWidget):
    """A box's own title bar, in the colour of its edge, so the edge and the bar read as one frame round all of it.
    Drag it to move the box."""

    def __init__(self, box, title, colour):
        super().__init__(box)
        self.box = box
        self.setAutoFillBackground(True)
        self.setFixedHeight(30)
        ink = "#FFFFFF" if colour.lightnessF() < 0.6 else "#111827"
        self.setStyleSheet(f"_Bar, QWidget#VmlBar {{ background: {colour.name()}; }}"
                           f" QLabel {{ color: {ink}; font-weight: 600; background: transparent; }}"
                           f" QToolButton {{ color: {ink}; border: none; background: transparent; font-size: 15px; padding: 0 6px; }}"
                           f" QToolButton:hover {{ background: rgba(127,127,127,0.35); }}")
        self.setObjectName("VmlBar")
        self.setAttribute(Qt.WA_StyledBackground, True)
        row = QHBoxLayout(self)
        row.setContentsMargins(12, 0, 4, 0)
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


class Box(QDialog):
    def __init__(self, parent, title, message, buttons=("OK",), edge="", ask=None, picture=None):
        super().__init__(parent)
        self.setWindowTitle(str(title))
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)  # our own bar and edge: one frame, all the way round
        self.setModal(True)
        self.edge = QColor(edge or NEUTRAL)
        self.answer, self.buttons, self.input = "", list(buttons), None
        frame = QVBoxLayout(self)
        frame.setContentsMargins(1, 1, 1, 1)
        frame.setSpacing(0)
        self.bar = _Bar(self, title, self.edge)
        frame.addWidget(self.bar)
        outer = QVBoxLayout()
        frame.addLayout(outer)
        outer.setContentsMargins(22, 18, 22, 14)
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
        text = QLabel(str(message))
        text.setWordWrap(True)
        text.setTextFormat(Qt.PlainText)
        text.setTextInteractionFlags(Qt.TextSelectableByMouse)
        fm = text.fontMetrics()
        widest = max((fm.horizontalAdvance(line) for line in str(message).splitlines()), default=0) + 8
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
            outer.addWidget(text)
        if ask is not None:
            self.input = QLineEdit(str(ask))
            self.input.setMinimumWidth(440)
            self.input.selectAll()
            outer.addWidget(self.input)
        row = QHBoxLayout()
        row.addStretch(1)
        for i, label in enumerate(self.buttons):
            b = QPushButton(label)
            b.setMinimumWidth(84)
            b.setDefault(i == 0)
            b.setAutoDefault(i == 0)
            b.clicked.connect(self.pressed)                    # a method, not a lambda holding the box: no cycle to outlive Qt
            row.addWidget(b)
        outer.addLayout(row)
        if self.input is not None:
            self.input.setFocus()

    def pressed(self):
        self.choose(self.sender().text())

    def choose(self, label):
        self.answer = label
        self.accept()

    def paintEvent(self, e):
        super().paintEvent(e)
        p = QPainter(self)
        w, h = self.width(), self.height()
        for r in ((0, 0, w, 1), (0, h - 1, w, 1), (0, 0, 1, h), (w - 1, 0, 1, h)):
            p.fillRect(*r, self.edge)
        p.end()

    def run(self):
        """Show it and wait. Returns the button pressed ("" if it was closed another way)."""
        self.exec()
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
