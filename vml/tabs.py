"""
TabStrip, TabPage and Toolbar: the two things a VB form most often had that Visualised didn't, on the desktop and
the web alike.

    TabStrip   tabs, a page under each. Its children are TabPages, in tab order. SelectedIndex (from 0);
               TabPlacement Top, Bottom, Left or Right (down the side, TabWidth wide); Accent (the chosen tab's
               mark); a border of its own (BorderThickness, BorderBrush, CornerRadius). SelectionChanged when the
               user picks a tab. TabStyle Underline (a bar under the chosen tab) or Folder (filing-cabinet tabs,
               the chosen one open into its page).  Vml("SetProperty", "Tabs1", "SelectedIndex", "2") picks one.
    TabPage    one page of a TabStrip: Header (the tab's words). Holds controls as a Canvas does, anchors and all.
               SameAs=pOther: this tab shows pOther's page (tabs that share one set of controls, told apart by script).
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

    @staticmethod
    def hidden(page):
        """A page with IsVisible=false has no tab (an app shows only the tabs that make sense where it's running)."""
        return str(page.props.get("IsVisible", "true")).lower() == "false"

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

    def showing(self):
        """The page on show: the chosen tab's, or the page it shares (SameAs), so tabs can share one set of controls."""
        pages = self.pages()
        if not pages:
            return None
        page = pages[self.current()]
        same = str(page.props.get("SameAs") or "").strip()
        return next((p for p in pages if p.name == same), page) if same else page

    def lay_out(self):
        _, _, _, page = strip_geometry(self.node.props, self.width(), self.height())
        shown = self.showing()
        for pg in self.pages():
            pg.host.setGeometry(*page)
            pg.host.setVisible(pg is shown and not self.hidden(pg))

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
        folder = str(props.get("TabStyle") or "").lower() == "folder"
        turned = upright(props)
        # the line between the tabs and the page: [(x1, y1, x2, y2)]; a folder tab breaks it where it opens on its page
        divider = {"Top": (bx, by + bh - 1, bx + bw, by + bh - 1), "Bottom": (bx, by, bx + bw, by),
                   "Left": (bx + bw - 1, by, bx + bw - 1, by + bh), "Right": (bx, by, bx, by + bh)}[place]
        gap = 2 if folder else 0
        self.rects = []
        x, y = bx + 4, by + 6
        pages = self.pages()
        for k, text in enumerate(self.headers()):
            if k < len(pages) and self.hidden(pages[k]):
                self.rects.append(QRect())                      # (no tab: the indexes stay the pages')
                continue
            if place in ("Top", "Bottom"):
                w = fm.horizontalAdvance(text) + 28
                r = QRect(x, by, w, HEADER - 1) if place == "Top" else QRect(x, by + 1, w, HEADER - 1)
                x += w + gap
            elif turned:
                tall = fm.horizontalAdvance(text) + 28
                r = QRect(bx + (2 if folder else 0), y, bw - (3 if folder else 0), tall) if place == "Left" else QRect(bx + 1, y, bw - 3 if folder else bw, tall)
                y += tall + 2
            else:
                r = QRect(bx + 4, y, bw - (5 if folder else 8), HEADER) if place == "Left" else QRect(bx + 1 if folder else bx + 4, y, bw - (5 if folder else 8), HEADER)
                y += HEADER + 2
            self.rects.append(r)
            chosen = k == self.current()
            if folder:
                self.folder_tab(g, place, r, chosen, divider, accent,     # (the chosen tab is the page's colour)
                                qcolour(props["Background"]) if props.get("Background") else self.palette().window().color())
            elif chosen and place in ("Left", "Right"):
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
            elif turned:                                    # turned: reading up the left side, down the right
                g.save()
                g.translate(r.center())
                g.rotate(-90 if place == "Left" else 90)
                g.drawText(QRect(-r.height() // 2, -r.width() // 2, r.height(), r.width()), Qt.AlignCenter, text)
                g.restore()
            else:
                g.drawText(r.adjusted(12, 0, -8, 0), Qt.AlignVCenter | Qt.AlignLeft, fm.elidedText(text, Qt.ElideRight, r.width() - 20))
            if chosen and not folder:
                g.setPen(Qt.NoPen)
                g.setBrush(accent)
                bar = {"Top": QRect(r.x() + 6, by + HEADER - 3, r.width() - 12, 3),
                       "Bottom": QRect(r.x() + 6, by, r.width() - 12, 3),
                       "Left": QRect(r.x(), r.y() + 6, 3, r.height() - 12),
                       "Right": QRect(r.right() - 2, r.y() + 6, 3, r.height() - 12)}[place]
                g.drawRoundedRect(bar, 1.5, 1.5)
        g.setPen(QColor(LINE))
        g.setBrush(Qt.NoBrush)
        x1, y1, x2, y2 = divider
        cut = self.rects[self.current()] if folder and self.rects else None
        if cut is None:
            g.drawLine(x1, y1, x2, y2)
        elif place in ("Top", "Bottom"):                    # the line, with the open folder tab's mouth left out
            g.drawLine(x1, y1, cut.left(), y1)
            g.drawLine(cut.right() + 1, y1, x2, y2)
        else:
            g.drawLine(x1, y1, x1, cut.top())
            g.drawLine(x1, cut.bottom() + 1, x2, y2)
        if b > 0:                                           # the strip's own border, round the lot
            pen = QPen(qcolour(props.get("BorderBrush") or "#CBD5E1"), b)
            g.setPen(pen)
            g.setBrush(Qt.NoBrush)
            radius = num(props.get("CornerRadius"), 6)
            g.drawRoundedRect(QRectF(b / 2, b / 2, self.width() - b, self.height() - b), radius, radius)
        g.end()

    def folder_tab(self, g, place, r, chosen, divider, accent, page):
        """An old-school filing-cabinet tab: rounded on its outer edge, open into its page when chosen, the others
        a shade darker and set back a little."""
        from PySide6.QtGui import QPainterPath
        back = 0 if chosen else 3                           # the others sit a little further back
        out = {"Top": (0, back, 0, 0), "Bottom": (0, 0, 0, -back), "Left": (back, 0, 0, 0), "Right": (0, 0, -back, 0)}[place]
        tab = QRectF(r).adjusted(*out)
        reach = {"Top": (0, 0, 0, 10), "Bottom": (0, -10, 0, 0), "Left": (0, 0, 10, 0), "Right": (-10, 0, 0, 0)}[place]
        shape = QPainterPath()
        shape.addRoundedRect(tab.adjusted(*reach), 7, 7)    # rounded all round, then the page side cut square below
        keep = QPainterPath()
        open_by = 1 if chosen else 0                        # the chosen one covers the line, so it opens on its page
        keep.addRect(QRectF(r).adjusted(*{"Top": (-1, -1, 1, open_by), "Bottom": (-1, -open_by, 1, 1),
                                         "Left": (-1, -1, open_by, 1), "Right": (-open_by, -1, 1, 1)}[place]))
        shape = shape.intersected(keep)
        g.setPen(QPen(QColor("#D1D5DB"), 1))
        g.setBrush(page if chosen else QColor("#EEF1F4"))
        g.drawPath(shape)
        if chosen:                                          # a strip of the accent along its outer edge
            edge = {"Top": QRectF(tab.x() + 1, tab.y() + 1, tab.width() - 2, 3),
                    "Bottom": QRectF(tab.x() + 1, tab.bottom() - 4, tab.width() - 2, 3),
                    "Left": QRectF(tab.x() + 1, tab.y() + 1, 3, tab.height() - 2),
                    "Right": QRectF(tab.right() - 4, tab.y() + 1, 3, tab.height() - 2)}[place]
            band = QPainterPath()
            band.addRect(edge)
            g.setPen(Qt.NoPen)
            g.setBrush(accent)
            g.drawPath(band.intersected(shape))


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
          Prop("TabStyle", "choice", "Common", options=("Underline", "Folder"), default="Underline",
               apply=_redraw),                                       # Folder: old-school filing-cabinet tabs
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


def _page_shown(n, v):
    n.props["IsVisible"] = str(v)
    if n.parent is not None and n.parent.type.name == "TabStrip":
        n.parent.widget.lay_out()
        n.parent.widget.update()


register(ControlType("TabPage", lambda n: TabPageWidget(n), container=True, add_child=canvas_add, place_child=canvas_place,
                     remove_child=canvas_remove, category="Containers", events=dict(POINTER_EVENTS)),
         [p for p in COMMON if p.name != "IsVisible"], ATTACHED,
         [Prop("Header", "text", "Common", apply=_header),
          Prop("IsVisible", "bool", "Common", default="true", apply=_page_shown),                # false: no tab at all
          Prop("SameAs", "text", "Common", apply=lambda n, v: n.parent is not None and n.parent.type.name == "TabStrip"
               and n.parent.widget.lay_out())])                       # another page's name: this tab shows that page


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
