"""
Pickers: controls for choosing a value rather than typing it, on the desktop and the web alike.

    ColorPicker    a colour: Value=#4F46E5. A swatch and its code; clicking opens the colour box.
    DatePicker     a date: Value=2026-10-16 (year-month-day), with a calendar to pick from. Minimum, Maximum.
    TimePicker     a time of day: Value=14:30 (24-hour).
    NumberBox      a number, typed or stepped with arrows: Value, Minimum, Maximum, Step, Decimals.
    ToggleSwitch   on or off, as a sliding switch: IsChecked, Content (its words), Accent (its colour when on).

Each runs ValueChanged when the user changes it. On the web they are the browser's own inputs (a colour, date,
time and number input, and a checkbox drawn as a switch), so a phone shows its own pickers.
"""
from PySide6.QtCore import QDate, QRectF, QSize, Qt, QTime, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (QAbstractButton, QDateEdit, QDoubleSpinBox, QFrame, QHBoxLayout, QLabel, QSizePolicy,
                               QTimeEdit)

from .registry import ATTACHED, COMMON, ControlType, Prop, num, qcolour, register, truthy

PLAIN = [p for p in COMMON if p.name not in ("Background", "CornerRadius")]


def _changed(node, fire):
    node.widget.changed.connect(lambda *a: fire({}))


# ------------------------------------------------------------------ ColorPicker

class ColourPickerWidget(QFrame):
    changed = Signal()

    def __init__(self, node):
        super().__init__()
        self.node, self._value = node, "#4F46E5"
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        self.swatch = QFrame()
        self.swatch.setFixedSize(28, 22)
        self.code = QLabel()
        lay.addWidget(self.swatch)
        lay.addWidget(self.code, 1)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumSize(80, 22)
        self.refresh()

    def value(self):
        return self._value

    def refresh(self):
        v = str(self.node.props.get("Value") or "").strip()
        c = QColor(v) if v else QColor("#4F46E5")
        self._value = c.name().upper() if c.isValid() else "#4F46E5"
        self.swatch.setStyleSheet(f"background: {self._value}; border: 1px solid #9CA3AF; border-radius: 4px;")
        self.code.setText(self._value)

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.LeftButton or not self.isEnabled():
            return
        from . import dialogs
        c = dialogs.choose_colour(self.window(), self._value, "Choose a colour")
        if c.isValid() and c.name().upper() != self._value:
            self.node.props["Value"] = c.name().upper()
            self.refresh()
            self.changed.emit()


register(ControlType("ColorPicker", lambda n: ColourPickerWidget(n), events={"ValueChanged": _changed}),
         PLAIN, ATTACHED,
         [Prop("Value", "colour", "Common", default="#4F46E5", apply=lambda n, v: n.widget.refresh(),
               read=lambda n: n.widget.value())])


# ------------------------------------------------------------------ DatePicker, TimePicker

class DatePickerWidget(QDateEdit):
    changed = Signal()

    def __init__(self, node):
        super().__init__()
        self.node = node
        self.setCalendarPopup(True)
        self.setDisplayFormat("d MMM yyyy")
        self.setDate(QDate.currentDate())
        self.dateChanged.connect(lambda *a: None if self.signalsBlocked() else self.changed.emit())
        self.refresh()

    def value(self):
        return self.date().toString("yyyy-MM-dd")

    def refresh(self):
        p = self.node.props
        self.blockSignals(True)
        for key, setter in (("Minimum", self.setMinimumDate), ("Maximum", self.setMaximumDate)):
            d = QDate.fromString(str(p.get(key) or ""), "yyyy-MM-dd")
            if d.isValid():
                setter(d)
        d = QDate.fromString(str(p.get("Value") or ""), "yyyy-MM-dd")
        self.setDate(d if d.isValid() else QDate.currentDate())
        self.blockSignals(False)


class TimePickerWidget(QTimeEdit):
    changed = Signal()

    def __init__(self, node):
        super().__init__()
        self.node = node
        self.setDisplayFormat("HH:mm")
        self.timeChanged.connect(lambda *a: None if self.signalsBlocked() else self.changed.emit())
        self.refresh()

    def value(self):
        return self.time().toString("HH:mm")

    def refresh(self):
        self.blockSignals(True)
        t = QTime.fromString(str(self.node.props.get("Value") or ""), "HH:mm")
        self.setTime(t if t.isValid() else QTime(12, 0))
        self.blockSignals(False)


register(ControlType("DatePicker", lambda n: DatePickerWidget(n), events={"ValueChanged": _changed}),
         PLAIN, ATTACHED,
         [Prop("Value", "text", "Common", apply=lambda n, v: n.widget.refresh(), read=lambda n: n.widget.value()),  # year-month-day: 2026-10-16 (empty: today)
          Prop("Minimum", "text", "Common", apply=lambda n, v: n.widget.refresh()),                                 # the earliest date it allows
          Prop("Maximum", "text", "Common", apply=lambda n, v: n.widget.refresh())])                                # the latest date it allows

register(ControlType("TimePicker", lambda n: TimePickerWidget(n), events={"ValueChanged": _changed}),
         PLAIN, ATTACHED,
         [Prop("Value", "text", "Common", apply=lambda n, v: n.widget.refresh(), read=lambda n: n.widget.value())])  # 24-hour: 14:30


# ------------------------------------------------------------------ NumberBox

class NumberBoxWidget(QDoubleSpinBox):
    changed = Signal()

    def __init__(self, node):
        super().__init__()
        self.node = node
        self.valueChanged.connect(lambda *a: None if self.signalsBlocked() else self.changed.emit())
        self.refresh()

    def value_text(self):
        v = self.value()
        return str(int(round(v))) if self.decimals() == 0 else f"{v:.{self.decimals()}f}"

    def refresh(self):
        p = self.node.props
        self.blockSignals(True)
        self.setDecimals(max(0, min(8, int(num(p.get("Decimals"), 0)))))
        low, high = num(p.get("Minimum"), 0), num(p.get("Maximum"), 100)
        self.setRange(low, max(low, high))
        self.setSingleStep(num(p.get("Step"), 1) or 1)
        self.setValue(num(p.get("Value"), low))
        self.blockSignals(False)


_nb = lambda n, v=None: n.widget.refresh()
register(ControlType("NumberBox", lambda n: NumberBoxWidget(n), events={"ValueChanged": _changed}),
         PLAIN, ATTACHED,
         [Prop("Value", "number", "Common", default="0", apply=_nb, read=lambda n: n.widget.value_text()),
          Prop("Minimum", "number", "Common", default="0", apply=_nb),
          Prop("Maximum", "number", "Common", default="100", apply=_nb),
          Prop("Step", "number", "Common", default="1", apply=_nb),        # how much each arrow adds or takes away
          Prop("Decimals", "number", "Common", default="0", apply=_nb)])   # places after the point (0: whole numbers)


# ------------------------------------------------------------------ ToggleSwitch

class ToggleWidget(QAbstractButton):
    changed = Signal()
    TRACK_W, TRACK_H = 40, 22

    def __init__(self, node):
        super().__init__()
        self.node = node
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.toggled.connect(lambda *a: None if self.signalsBlocked() else self.changed.emit())

    def sizeHint(self):
        fm = self.fontMetrics()
        return QSize(self.TRACK_W + (10 + fm.horizontalAdvance(self.text()) if self.text() else 0), max(self.TRACK_H, fm.height()) + 4)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        y = (self.height() - self.TRACK_H) / 2
        on = self.isChecked()
        accent = qcolour(self.node.props.get("Accent") or "#4F46E5")
        track = accent if on else QColor("#D1D5DB")
        if not self.isEnabled():
            track.setAlpha(110)
        p.setPen(Qt.NoPen)
        p.setBrush(track)
        p.drawRoundedRect(QRectF(0, y, self.TRACK_W, self.TRACK_H), self.TRACK_H / 2, self.TRACK_H / 2)
        knob = self.TRACK_H - 6
        p.setBrush(QColor("#FFFFFF"))
        p.drawEllipse(QRectF((self.TRACK_W - knob - 3) if on else 3, y + 3, knob, knob))
        if self.text():
            p.setPen(qcolour(self.node.props.get("Foreground") or "#111827"))
            p.drawText(QRectF(self.TRACK_W + 10, 0, self.width() - self.TRACK_W - 10, self.height()),
                       Qt.AlignVCenter | Qt.AlignLeft, self.text())
        p.end()


def _toggle_set(n, v):
    n.widget.blockSignals(True)
    n.widget.setChecked(truthy(v))
    n.widget.blockSignals(False)
    n.widget.update()


register(ControlType("ToggleSwitch", lambda n: ToggleWidget(n), events={"ValueChanged": _changed}),
         PLAIN, ATTACHED,
         [Prop("IsChecked", "bool", "Common", apply=_toggle_set, read=lambda n: "true" if n.widget.isChecked() else "false"),
          Prop("Content", "text", "Common", apply=lambda n, v: (n.widget.setText(str(v or "")), n.widget.updateGeometry())),
          Prop("Accent", "colour", "Appearance", apply=lambda n, v: n.widget.update())])      # its colour when on
