"""
StatusBar: the strip along the foot of a form, as VB's had, on the desktop and the web alike.

    Panels   the panels, left to right, split by |  e.g.  Ready|{date}|{time}
             The first panel takes the room that's left; the others are as wide as what they say.
             {time} {date} {datetime} keep themselves up to date, like VB's sbrTime and sbrDate panels.
    Text     the first panel's words, for scripts:  Vml("SetProperty", "StatusBar1", "Text", "Saving...")

The designer puts a new one along the bottom of the form, full width, anchored so it stays there when the form is
resized. Background, Foreground and FontSize work as on any control.
"""
import datetime

from PySide6.QtCore import QRect, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QStyle, QStyleOption, QWidget

from .registry import ATTACHED, COMMON, ControlType, POINTER_EVENTS, Prop, qcolour, register

LINE = "#D1D5DB"
INK = "#374151"


def fill(text, now=None):
    """A panel's words with {time}, {date} and {datetime} filled in."""
    if "{" not in text:
        return text
    now = now or datetime.datetime.now()
    date = f"{now.day} {now.strftime('%b %Y')}"
    return (text.replace("{datetime}", f"{date} {now.strftime('%H:%M')}")
                .replace("{date}", date).replace("{time}", now.strftime("%H:%M")))


class StatusBarWidget(QWidget):
    PAD = 10

    def __init__(self, node):
        super().__init__()
        self.node, self.panels, self.first = node, ["Ready"], None
        self.setMinimumHeight(20)
        self.clock = QTimer(self)                          # (only the clock panels change by themselves)
        self.clock.timeout.connect(self.update)
        self.clock.start(1000)

    def set_panels(self, value):
        parts = [s.strip() for s in str(value if value not in (None, "") else "Ready").split("|")]
        self.panels = parts or [""]
        self.update()

    def set_text(self, value):
        self.first = None if value is None else str(value)
        self.update()

    def shown(self):
        out = [fill(t) for t in self.panels]
        if self.first is not None:
            out[0] = fill(self.first)
        return out

    def text(self):
        return self.shown()[0]

    def sizeHint(self):
        return QSize(320, max(22, self.fontMetrics().height() + 10))

    def paintEvent(self, event):
        opt = QStyleOption()
        opt.initFrom(self)
        g = QPainter(self)
        self.style().drawPrimitive(QStyle.PE_Widget, opt, g, self)    # Background (and any Style) as on any control
        g.setPen(QColor(LINE))
        g.drawLine(0, 0, self.width(), 0)
        ink = qcolour(self.node.props.get("Foreground") or INK)
        fm, pad, h = self.fontMetrics(), self.PAD, self.height()
        texts = self.shown()
        right = self.width()
        for t in reversed(texts[1:]):                      # the fixed panels, from the right
            w = fm.horizontalAdvance(t) + 2 * pad
            left = right - w
            g.setPen(ink)
            g.drawText(QRect(left, 0, w, h), Qt.AlignCenter, t)
            g.setPen(QColor(LINE))
            g.drawLine(left, 5, left, h - 5)
            right = left
        g.setPen(ink)
        first = fm.elidedText(texts[0], Qt.ElideRight, max(0, right - 2 * pad))
        g.drawText(QRect(pad, 0, max(0, right - 2 * pad), h), Qt.AlignVCenter | Qt.AlignLeft, first)
        g.end()


register(ControlType("StatusBar", lambda n: StatusBarWidget(n), events=dict(POINTER_EVENTS)),
         [p for p in COMMON if p.name not in ("CornerRadius",)], ATTACHED,
         [Prop("Panels", "text", "Common", default="Ready", apply=lambda n, v: n.widget.set_panels(v)),
          Prop("Text", "text", "Common", apply=lambda n, v: n.widget.set_text(v), read=lambda n: n.widget.text())])
