"""
TabStrip, TabPage and Toolbar: the two things a VB form most often had that Visualised didn't, on the desktop and
the web alike.

    TabStrip   tabs, a page under each. Its children are TabPages, in tab order. SelectedIndex (from 0);
               TabPlacement Top, Bottom, Left or Right (down the side, TabWidth wide); Accent (the chosen tab's
               mark); a border of its own (BorderThickness, BorderBrush, CornerRadius). SelectionChanged when the
               user picks a tab.  Vml("SetProperty", "Tabs1", "SelectedIndex", "2") picks one from a script.
    TabPage    one page of a TabStrip: Header (the tab's words). Holds controls as a Canvas does, anchors and all.
    Toolbar    a row of buttons under the menu. Items, comma-separated, left to right:
                   📄 New=FileNew, 📂 Open=FileOpen, |, 💾 Save
               "words=Handler" runs Handler when that button is pressed; | is a divider. OnClick runs for every
               button, with the settings toolbar_item (its words) and toolbar_index (from 0).

In the designer a new TabStrip comes with two pages, and clicking a tab shows that page so you can design on it.
Adding a TabPage with the strip right-clicked adds a page to it. A new Toolbar goes along the top of the form, full
width, with New, Open and Save on it.
"""
from PySide6.QtCore import QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QStyle, QStyleOption, QToolButton, QWidget

from .registry import (ATTACHED, COMMON, POINTER_EVENTS, CanvasWidget, ControlType, Prop, canvas_add, canvas_place,
                       canvas_remove, num, qcolour, register)

HEADER = 34
ACCENT = "#4F46E5"
LINE = "#E5E7EB"


def _paint_background(widget, painter):
    opt = QStyleOption()
    opt.initFrom(widget)
    widget.style().drawPrimitive(QStyle.PE_Widget, opt, painter, widget)


# ------------------------------------------------------------------ TabStrip

PLACES = ("Top", "Bottom", "Left", "Right")


def upright(props):
    """Tabs down a side with their words running along the side (TabOrientation=Vertical)."""
    return str(props.get("TabOrientation") or "").lower() == "vertical" and \
        str(props.get("TabPlacement") or "Top").capitalize() in ("Left", "Right")


def strip_geometry(props, w, h):
    """Where a strip's tab band and its page go, for a strip w x h: shared by the desktop, the designer and the web.
    Returns (place, border, band, page) with band and page as (x, y, width, height)."""
    place = str(props.get("TabPlacement") or "Top").capitalize()
    place = place if place in PLACES else "Top"
    b = int(num(props.get("BorderThickness"), 0))
    side = HEADER if upright(props) else int(num(props.get("TabWidth"), 120))
    iw, ih = max(0, w - 2 * b), max(0, h - 2 * b)
    if place == "Top":
        band, page = (b, b, iw, HEADER), (b, b + HEADER, iw, ih - HEADER)
    elif place == "Bottom":
        band, page = (b, b + ih - HEADER, iw, HEADER), (b, b, iw, ih - HEADER)
    elif place == "Left":
        band, page = (b, b, side, ih), (b + side, b, iw - side, ih)
    else:
        band, page = (b + iw - side, b, side, ih), (b, b, iw - side, ih)
    return place, b, band, tuple(max(0, v) for v in page)


class TabStripWidget(QWidget):
    changed = Signal()

    def __init__(self, node):
        super().__init__()
        self.node, self.wanted, self.rects = node, 0, []
        self.setMinimumSize(120, HEADER + 40)

    def pages(self):
        return [c for c in self.node.children if c.type.name == "TabPage"]

    def headers(self):
        return [str(c.props.get("Header") or c.name) for c in self.pages()]

    def current(self):
        """The tab showing: the one asked for, or the nearest there is (pages arrive after SelectedIndex is read)."""
        n = len(self.pages())
        return max(0, min(self.wanted, n - 1)) if n else 0

    def select(self, index, user=False):
        before = self.current()
        self.wanted = int(num(index, 0))
        self.node.props["SelectedIndex"] = str(self.wanted)
        self.lay_out()
        self.update()
        if user and self.current() != before:
            self.changed.emit()

    def lay_out(self):
        _, _, _, page = strip_geometry(self.node.props, self.width(), self.height())
        shown = self.current()
        for k, pg in enumerate(self.pages()):
            pg.host.setGeometry(*page)
            pg.host.setVisible(k == shown)

    def tab_at(self, pos):
        for k, r in enumerate(self.rects):
            if r.contains(pos):
                return k
        return -1

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.lay_out()

    def mousePressEvent(self, e):
        k = self.tab_at(e.position().toPoint())
        if k >= 0:
            self.select(k, user=True)

    def paintEvent(self, e):
        g = QPainter(self)
        _paint_background(self, g)
        g.setRenderHint(QPainter.Antialiasing)
        props = self.node.props
        place, b, band, _ = strip_geometry(props, self.width(), self.height())
        bx, by, bw, bh = band
        fm = self.fontMetrics()
        accent = qcolour(props.get("Accent") or ACCENT)
        ink = qcolour(props.get("Foreground") or "#111827")
        g.setPen(QColor(LINE))                              # the line between the tabs and the page
        if place == "Top":
            g.drawLine(bx, by + bh - 1, bx + bw, by + bh - 1)
        elif place == "Bottom":
            g.drawLine(bx, by, bx + bw, by)
        elif place == "Left":
            g.drawLine(bx + bw - 1, by, bx + bw - 1, by + bh)
        else:
            g.drawLine(bx, by, bx, by + bh)
        self.rects = []
        x, y = bx + 4, by + 6
        for k, text in enumerate(self.headers()):
            if place in ("Top", "Bottom"):
                w = fm.horizontalAdvance(text) + 28
                r = QRect(x, by, w, HEADER - 1)
                x += w
            elif upright(props):
                tall = fm.horizontalAdvance(text) + 28
                r = QRect(bx, y, bw, tall)
                y += tall + 2
            else:
                r = QRect(bx + 4, y, bw - 8, HEADER)
                y += HEADER + 2
            self.rects.append(r)
            chosen = k == self.current()
            if chosen and place in ("Left", "Right"):
                tint = QColor(accent)
                tint.setAlpha(28)
                g.setPen(Qt.NoPen)
                g.setBrush(tint)
                g.drawRoundedRect(r, 6, 6)
            f = g.font()
            f.setBold(chosen)
            g.setFont(f)
            g.setPen(ink if chosen else QColor("#6B7280"))
            if place in ("Top", "Bottom"):
                g.drawText(r, Qt.AlignCenter, text)
            elif upright(props):                            # turned: reading up the left side, down the right
                g.save()
                g.translate(r.center())
                g.rotate(-90 if place == "Left" else 90)
                g.drawText(QRect(-r.height() // 2, -r.width() // 2, r.height(), r.width()), Qt.AlignCenter, text)
                g.restore()
            else:
                g.drawText(r.adjusted(12, 0, -8, 0), Qt.AlignVCenter | Qt.AlignLeft, fm.elidedText(text, Qt.ElideRight, r.width() - 20))
            if chosen:
                g.setPen(Qt.NoPen)
                g.setBrush(accent)
                bar = {"Top": QRect(r.x() + 6, by + HEADER - 3, r.width() - 12, 3),
                       "Bottom": QRect(r.x() + 6, by, r.width() - 12, 3),
                       "Left": QRect(r.x(), r.y() + 6, 3, r.height() - 12),
                       "Right": QRect(r.right() - 2, r.y() + 6, 3, r.height() - 12)}[place]
                g.drawRoundedRect(bar, 1.5, 1.5)
        if b > 0:                                           # the strip's own border, round the lot
            pen = QPen(qcolour(props.get("BorderBrush") or "#CBD5E1"), b)
            g.setPen(pen)
            g.setBrush(Qt.NoBrush)
            radius = num(props.get("CornerRadius"), 6)
            g.drawRoundedRect(QRectF(b / 2, b / 2, self.width() - b, self.height() - b), radius, radius)
        g.end()


def tabs_add(parent, child):
    child.host.setParent(parent.widget)
    parent.widget.lay_out()
    parent.widget.update()


def tabs_remove(parent, child):
    child.host.setParent(None)
    parent.widget.lay_out()
    parent.widget.update()


_redraw = lambda n, v: (n.widget.lay_out(), n.widget.update())
register(ControlType("TabStrip", lambda n: TabStripWidget(n), container=True, add_child=tabs_add, remove_child=tabs_remove,
                     place_child=lambda p, c: p.widget.lay_out(), category="Containers",
                     events={"SelectionChanged": lambda node, fire: node.widget.changed.connect(lambda *a: fire({}))}),
         [p for p in COMMON if p.name not in ("CornerRadius", "BorderBrush", "BorderThickness")], ATTACHED,
         [Prop("SelectedIndex", "number", "Common", default="0", apply=lambda n, v: n.widget.select(v),
               read=lambda n: str(n.widget.current())),
          Prop("TabPlacement", "choice", "Common", options=PLACES, default="Top", apply=_redraw),     # Left/Right: tabs down the side
          Prop("TabWidth", "number", "Common", default="120", apply=_redraw),                        # the side tabs' width
          Prop("TabOrientation", "choice", "Common", options=("Horizontal", "Vertical"), default="Horizontal",
               apply=_redraw),                                       # Vertical: side tabs' words run along the side
          Prop("Accent", "colour", "Appearance", apply=_redraw),
          Prop("BorderBrush", "colour", "Appearance", apply=_redraw),
          Prop("BorderThickness", "number", "Appearance", apply=_redraw),
          Prop("CornerRadius", "number", "Appearance", apply=_redraw)])


# ------------------------------------------------------------------ TabPage

class TabPageWidget(CanvasWidget):
    """A Canvas whose designed size is its strip's page: so anchors inside it work as on a form."""

    def ref_size(self):
        strip = self.node.parent
        if strip is not None and strip.props.get("Width") and strip.props.get("Height"):
            page = strip_geometry(strip.props, num(strip.props["Width"]), num(strip.props["Height"]))[3]
            return (page[2], page[3])
        return super().ref_size()


def _header(n, v):
    if n.parent is not None and n.parent.type.name == "TabStrip":
        n.parent.widget.update()


register(ControlType("TabPage", lambda n: TabPageWidget(n), container=True, add_child=canvas_add, place_child=canvas_place,
                     remove_child=canvas_remove, category="Containers", events=dict(POINTER_EVENTS)),
         COMMON, ATTACHED,
         [Prop("Header", "text", "Common", apply=_header)])


# ------------------------------------------------------------------ Toolbar

def toolbar_items(value):
    """[(words, handler)] from Items; ("|", "") is a divider."""
    out = []
    for part in str(value or "").split(","):
        part = part.strip()
        if not part:
            continue
        words, _, handler = part.partition("=")
        out.append((words.strip(), handler.strip()))
    return out


class ToolbarWidget(QWidget):
    clicked = Signal(str, int)

    def __init__(self, node):
        super().__init__()
        self.node = node
        self.row = QHBoxLayout(self)
        self.row.setContentsMargins(6, 3, 6, 3)
        self.row.setSpacing(2)
        self.setMinimumHeight(30)

    def set_items(self, value):
        while self.row.count():
            item = self.row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        index = 0
        for words, handler in toolbar_items(value):
            if words == "|":
                bar = QWidget()
                bar.setFixedSize(1, 20)
                bar.setStyleSheet(f"background: {LINE};")
                self.row.addSpacing(4)
                self.row.addWidget(bar)
                self.row.addSpacing(4)
                continue
            b = QToolButton()
            b.setText(words)
            b.setCursor(Qt.PointingHandCursor)
            b.setAutoRaise(True)
            b.setStyleSheet("QToolButton { border: 1px solid transparent; border-radius: 6px; padding: 3px 8px; background: transparent; }"
                            "QToolButton:hover { background: rgba(79,70,229,0.08); border-color: rgba(79,70,229,0.25); }"
                            "QToolButton:pressed { background: rgba(79,70,229,0.18); }")
            b.clicked.connect(lambda *a, w=words, h=handler, i=index: self.pressed(w, h, i))
            self.row.addWidget(b)
            index += 1
        self.row.addStretch(1)

    def pressed(self, words, handler, index):
        eng = getattr(self.node, "engine", None)
        if eng is not None:
            eng.store.set_setting("toolbar_item", words)
            eng.store.set_setting("toolbar_index", index)
            if handler:
                eng.store.set_setting("event_control", self.node.name)
                eng.handle(handler, self.node)
        self.clicked.emit(words, index)

    def sizeHint(self):
        return QSize(320, 34)

    def paintEvent(self, e):
        g = QPainter(self)
        _paint_background(self, g)
        g.setPen(QColor(LINE))
        g.drawLine(0, self.height() - 1, self.width(), self.height() - 1)
        g.end()


register(ControlType("Toolbar", lambda n: ToolbarWidget(n), category="Common",
                     events={"OnClick": lambda node, fire: node.widget.clicked.connect(
                         lambda w, i: fire({"toolbar_item": w, "toolbar_index": i}))}),
         [p for p in COMMON if p.name not in ("CornerRadius",)], ATTACHED,
         [Prop("Items", "text", "Common", apply=lambda n, v: n.widget.set_items(v))])
