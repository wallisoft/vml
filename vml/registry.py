"""
The control registry: the single source of truth.

Each control type is declared once: which Qt widget it becomes, whether it holds children and
how they're placed, every property it has (kind, editor, group, how to set it, how to read it
back) and its events. The renderer, the Vml() script API and the property panel all read from
here, so a property added once shows up everywhere.
"""
from dataclasses import dataclass, field
from typing import Callable, Optional

from PySide6.QtCore import QEvent, QObject, QRect, QSize, Qt
from PySide6.QtGui import QColor as _QColor, QKeySequence, QPainter as _QPainter, QPen as _QPen, QPixmap as _QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLayout,
                               QLineEdit, QListWidget, QPlainTextEdit, QPushButton, QRadioButton, QScrollArea, QSizePolicy,
                               QTableWidget, QTableWidgetItem, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

# ------------------------------------------------------------------ value helpers

def css_id(name):
    """A control name made safe for a Qt stylesheet selector (dots and dashes would break it)."""
    import re
    return re.sub(r'[^A-Za-z0-9_]', '_', str(name))


def thickness(v):
    """Avalonia Thickness: 'u' | 'h,v' | 'l,t,r,b' -> (l, t, r, b)."""
    try:
        n = [int(float(x)) for x in str(v).split(",") if x.strip() != ""]
    except ValueError:
        return (0, 0, 0, 0)
    if len(n) == 1:
        return (n[0],) * 4
    if len(n) == 2:
        return (n[0], n[1], n[0], n[1])
    return tuple(n[:4]) if len(n) >= 4 else (0, 0, 0, 0)


def truthy(v):
    return str(v).strip().lower() in ("true", "1", "yes")


def num(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def colour(v):
    """Avalonia colours: names, #rgb, #rrggbb, and #aarrggbb (alpha first) -> CSS."""
    v = str(v).strip()
    if v.lower() == "transparent":
        return "transparent"
    if v.startswith("#") and len(v) == 9:
        a, r, g, b = (int(v[i:i + 2], 16) for i in (1, 3, 5, 7))
        return f"rgba({r},{g},{b},{a / 255:.3f})"
    return v


def qcolour(v, default="#000000"):
    """A colour as Qt wants it: names, #rgb, #rrggbb and Avalonia's #aarrggbb."""
    v = str(v or "").strip()
    if v.startswith("#") and len(v) == 9:
        a, r, g, b = (int(v[i:i + 2], 16) for i in (1, 3, 5, 7))
        return _QColor(r, g, b, a)
    c = _QColor(v)
    return c if c.isValid() else _QColor(default)


WEIGHTS = {"Thin": 100, "ExtraLight": 200, "Light": 300, "Normal": 400, "Medium": 500, "SemiBold": 600,
           "Bold": 700, "ExtraBold": 800, "Black": 900}
H_ALIGN = {"Left": Qt.AlignLeft, "Right": Qt.AlignRight, "Center": Qt.AlignHCenter}
V_ALIGN = {"Top": Qt.AlignTop, "Bottom": Qt.AlignBottom, "Center": Qt.AlignVCenter}


# ------------------------------------------------------------------ declarations

@dataclass
class Prop:
    name: str
    kind: str = "text"                 # text | number | bool | colour | choice | thickness | list
    group: str = "Common"
    options: tuple = ()                # for choice
    apply: Optional[Callable] = None   # (node, value) -> None; None = just stored (read by parent layout etc.)
    read: Optional[Callable] = None    # (node) -> live value; None = stored value
    default: str = ""

    @property
    def editor(self):
        return {"bool": "checkbox", "choice": "dropdown", "colour": "colour", "number": "number"}.get(self.kind, "text")


@dataclass
class ControlType:
    name: str
    make: Callable                                     # (node) -> QWidget
    props: dict = field(default_factory=dict)
    events: dict = field(default_factory=dict)         # event name -> hook(node, fire)
    container: bool = False
    add_child: Optional[Callable] = None               # (parent_node, child_node)
    place_child: Optional[Callable] = None             # re-place after an attached property changes
    remove_child: Optional[Callable] = None
    category: str = "Common"


REGISTRY: dict[str, ControlType] = {}


def register(ct: ControlType, *prop_lists):
    for plist in prop_lists:
        for p in plist:
            ct.props[p.name] = p
    REGISTRY[ct.name] = ct
    return ct


# ------------------------------------------------------------------ styling: one stylesheet per node, rebuilt on change

def restyle(node):
    s = node.style
    css = []
    for key, val in s.items():
        if val not in (None, ""):
            css.append(f"{key}: {val};")
    sel = f"#{css_id(node.name)}"
    sheet = f"{sel} {{ {' '.join(css)} }}" if css else ""
    if isinstance(node.widget, QPushButton) and "background-color" in s:
        sheet += f" {sel} {{ border: none; border-radius: 6px; }} {sel}:hover {{ border: 1px solid rgba(255,255,255,0.35); }}"
    node.widget.setStyleSheet(sheet)


def style(key, fmt=lambda v: v):
    def apply(node, value):
        node.style[key] = fmt(value) if value not in (None, "") else None
        restyle(node)
    return apply


def set_border(node, _value):
    p = node.props
    if p.get("BorderThickness") or p.get("BorderBrush"):
        l, t, r, b = thickness(p.get("BorderThickness", "1"))
        node.style["border-style"] = "solid"
        node.style["border-width"] = f"{t}px {r}px {b}px {l}px"
        node.style["border-color"] = colour(p.get("BorderBrush", "#808080"))
    restyle(node)


def set_size(dim):
    def apply(node, value):
        w = node.widget
        if node.type.name == "Window":
            size = w.size()
            w.resize(int(num(value, size.width())) if dim == "w" else size.width(),
                     int(num(value, size.height())) if dim == "h" else size.height())
            return
        if value in (None, "", "Auto", "NaN"):
            (w.setMinimumWidth if dim == "w" else w.setMinimumHeight)(0)
            (w.setMaximumWidth if dim == "w" else w.setMaximumHeight)(16777215)
        else:
            (w.setFixedWidth if dim == "w" else w.setFixedHeight)(int(num(value)))
    return apply


def set_margin(node, value):
    node.host.layout().setContentsMargins(*thickness(value or 0))


def set_visible(node, value):
    node.host.setVisible(truthy(value) if value not in (None, "") else True)


def set_alignment(node, _value):
    if node.parent and node.parent.type.place_child:
        node.parent.type.place_child(node.parent, node)


def read_geom(what):
    def read(node):
        g = node.host.geometry()
        return {"X": g.x(), "Y": g.y(), "Width": node.widget.width(), "Height": node.widget.height()}[what]
    return read


COMMON = [
    Prop("Name", "text", "Common"),
    Prop("Background", "colour", "Appearance", apply=style("background-color", colour)),
    Prop("Foreground", "colour", "Appearance", apply=style("color", colour)),
    Prop("BorderBrush", "colour", "Appearance", apply=set_border),
    Prop("BorderThickness", "thickness", "Appearance", apply=set_border),
    Prop("CornerRadius", "number", "Appearance", apply=style("border-radius", lambda v: f"{int(num(str(v).split(',')[0]))}px")),
    Prop("FontSize", "number", "Text", apply=style("font-size", lambda v: f"{int(num(v, 12))}px")),
    Prop("FontWeight", "choice", "Text", options=tuple(WEIGHTS), apply=style("font-weight", lambda v: WEIGHTS.get(v, 400))),
    Prop("FontFamily", "text", "Text", apply=style("font-family", lambda v: str(v))),
    Prop("Width", "number", "Layout", apply=set_size("w"), read=read_geom("Width")),
    Prop("Height", "number", "Layout", apply=set_size("h"), read=read_geom("Height")),
    Prop("MinWidth", "number", "Layout", apply=lambda n, v: n.widget.setMinimumWidth(int(num(v)))),
    Prop("MinHeight", "number", "Layout", apply=lambda n, v: n.widget.setMinimumHeight(int(num(v)))),
    Prop("Margin", "thickness", "Layout", apply=set_margin),
    Prop("HorizontalAlignment", "choice", "Layout", options=("Stretch", "Left", "Center", "Right"), apply=set_alignment),
    Prop("VerticalAlignment", "choice", "Layout", options=("Stretch", "Top", "Center", "Bottom"), apply=set_alignment),
    Prop("IsVisible", "bool", "Behaviour", apply=set_visible, default="true"),
    Prop("IsEnabled", "bool", "Behaviour", apply=lambda n, v: n.widget.setEnabled(truthy(v) if v not in (None, "") else True),
         default="true"),
    Prop("ToolTip", "text", "Behaviour", apply=lambda n, v: n.widget.setToolTip(str(v or ""))),
    Prop("X", "number", "Layout", read=read_geom("X")),
    Prop("Y", "number", "Layout", read=read_geom("Y")),
]
ATTACHED = [                                            # read by the parent container when placing a child
    Prop("Grid.Row", "number", "Placement", apply=set_alignment), Prop("Grid.Column", "number", "Placement", apply=set_alignment),
    Prop("Grid.RowSpan", "number", "Placement", apply=set_alignment), Prop("Grid.ColumnSpan", "number", "Placement", apply=set_alignment),
    Prop("DockPanel.Dock", "choice", "Placement", options=("Left", "Top", "Right", "Bottom"), apply=set_alignment),
    Prop("Canvas.Left", "number", "Placement", apply=set_alignment), Prop("Canvas.Top", "number", "Placement", apply=set_alignment),
    Prop("Anchor", "choice", "Placement", default="Top,Left", apply=set_alignment,
         options=("Top,Left", "Top,Right", "Bottom,Left", "Bottom,Right", "Top,Left,Right", "Bottom,Left,Right",
                  "Top,Bottom,Left", "Top,Bottom,Right", "Top,Bottom,Left,Right")),
]
PADDING_STYLE = [Prop("Padding", "thickness", "Layout",
                      apply=style("padding", lambda v: "{1}px {2}px {3}px {0}px".format(*thickness(v))))]
PADDING_LAYOUT = [Prop("Padding", "thickness", "Layout",
                       apply=lambda n, v: n.widget.layout() and n.widget.layout().setContentsMargins(*thickness(v or 0)))]


# ------------------------------------------------------------------ events

class _Filter(QObject):
    """Mouse and focus events for any widget; pointer details go into settings first, as scripts expect."""

    def __init__(self, node, kinds, fire):
        super().__init__(node.widget)
        self.node, self.kinds, self.fire = node, kinds, fire

    def eventFilter(self, obj, ev):
        t = ev.type()
        if t in self.kinds:
            details = {}
            if t in (QEvent.KeyPress, QEvent.KeyRelease):
                mods = ev.modifiers()
                names = [n for flag, n in ((Qt.ControlModifier, "Ctrl"), (Qt.ShiftModifier, "Shift"),
                                           (Qt.AltModifier, "Alt"), (Qt.MetaModifier, "Meta")) if mods & flag]
                code = int(getattr(ev.key(), "value", ev.key()))
                details = {"event_key": KEY_NAMES_BY_CODE.get(code) or QKeySequence(code).toString() or str(code),
                           "event_key_text": ev.text(), "event_modifiers": "+".join(names),
                           "event_repeat": "true" if ev.isAutoRepeat() else "false"}
            if t in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease, QEvent.MouseMove):
                p = ev.position()
                btn = {Qt.LeftButton: "Left", Qt.RightButton: "Right", Qt.MiddleButton: "Middle"}.get(ev.button(), "")
                details = {"event_x": int(p.x()), "event_y": int(p.y()), "mouse_button": btn or "Left"}
            self.fire(details)
        return False


def on_qt_event(*kinds):
    def hook(node, fire):
        f = _Filter(node, set(kinds), fire)
        node.widget.installEventFilter(f)
        if kinds and kinds[0] == QEvent.MouseMove:
            node.widget.setMouseTracking(True)
        node.keep.append(f)
    return hook


def on_signal(signal_name):
    def hook(node, fire):
        getattr(node.widget, signal_name).connect(lambda *a: fire({}))
    return hook


def on_context_menu(node, fire):
    """Right-click (or the menu key). Item views take the press first, so the item under the pointer is selected."""
    w = node.widget
    w.setContextMenuPolicy(Qt.CustomContextMenu)
    w.customContextMenuRequested.connect(lambda pt: fire({"event_x": pt.x(), "event_y": pt.y(), "mouse_button": "Right"}))


KEY_NAMES = {Qt.Key_Return: "Enter", Qt.Key_Enter: "Enter", Qt.Key_Escape: "Escape", Qt.Key_Space: "Space",
             Qt.Key_Backspace: "Backspace", Qt.Key_Delete: "Delete", Qt.Key_Tab: "Tab", Qt.Key_Up: "Up",
             Qt.Key_Down: "Down", Qt.Key_Left: "Left", Qt.Key_Right: "Right"}
KEY_NAMES_BY_CODE = {int(getattr(k, "value", k)): v for k, v in KEY_NAMES.items()}   # Qt reports keys as numbers
KEY_EVENTS = {
    "OnKeyDown": on_qt_event(QEvent.KeyPress),
    "OnKeyUp": on_qt_event(QEvent.KeyRelease),
}

POINTER_EVENTS = {
    "OnPointerPressed": on_qt_event(QEvent.MouseButtonPress),
    "OnPointerReleased": on_qt_event(QEvent.MouseButtonRelease),
    "OnPointerMoved": on_qt_event(QEvent.MouseMove),
    "OnLostFocus": on_qt_event(QEvent.FocusOut),
    "OnGotFocus": on_qt_event(QEvent.FocusIn),
}


# ------------------------------------------------------------------ containers

def host_for(child):
    return child.host


def box_add(parent, child):
    lay = parent.widget.layout()
    lay.insertWidget(lay.count() - 1, child.host)       # keep the trailing stretch last
    box_place(parent, child)


def box_place(parent, child):
    lay = parent.widget.layout()
    horiz = isinstance(lay, QHBoxLayout)
    a = (V_ALIGN if horiz else H_ALIGN).get(child.props.get("VerticalAlignment" if horiz else "HorizontalAlignment"), Qt.Alignment())
    lay.setAlignment(child.host, a)


def single_add(parent, child):
    lay = parent.widget.layout()
    while lay.count():
        it = lay.takeAt(0)
        if it.widget():
            it.widget().setParent(None)
    lay.addWidget(child.host)
    single_place(parent, child)


def single_place(parent, child):
    a = H_ALIGN.get(child.props.get("HorizontalAlignment"), Qt.Alignment()) | \
        V_ALIGN.get(child.props.get("VerticalAlignment"), Qt.Alignment())
    parent.widget.layout().setAlignment(child.host, a)


def layout_remove(parent, child):
    lay = parent.widget.layout()
    lay.removeWidget(child.host)


def grid_defs(spec):
    out = []
    for d in (spec or "*").split(","):
        d = d.strip()
        if d.endswith("*"):
            out.append(("star", int(num(d[:-1] or 1, 1))))
        elif d == "Auto":
            out.append(("auto", 0))
        else:
            out.append(("px", int(num(d))))
    return out


def grid_apply_defs(node, _v=None):
    lay = node.widget.layout()
    for axis, key in (("col", "ColumnDefinitions"), ("row", "RowDefinitions")):
        for i, (kind, n) in enumerate(grid_defs(node.props.get(key))):
            stretch = n if kind == "star" else 0
            (lay.setColumnStretch if axis == "col" else lay.setRowStretch)(i, stretch)
            if kind == "px":
                (lay.setColumnMinimumWidth if axis == "col" else lay.setRowMinimumHeight)(i, n)


def grid_add(parent, child):
    grid_place(parent, child)


def grid_place(parent, child):
    lay = parent.widget.layout()
    lay.removeWidget(child.host)
    p = child.props
    a = H_ALIGN.get(p.get("HorizontalAlignment"), Qt.Alignment()) | V_ALIGN.get(p.get("VerticalAlignment"), Qt.Alignment())
    lay.addWidget(child.host, int(num(p.get("Grid.Row"))), int(num(p.get("Grid.Column"))),
                  max(1, int(num(p.get("Grid.RowSpan"), 1))), max(1, int(num(p.get("Grid.ColumnSpan"), 1))), a)


class DockLayout(QLayout):
    """Avalonia DockPanel: children dock in order, each carving space from what's left; last fills."""

    def __init__(self):
        super().__init__()
        self.items, self.last_fill = [], True
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item):
        self.items.append(item)

    def count(self):
        return len(self.items)

    def itemAt(self, i):
        return self.items[i] if 0 <= i < len(self.items) else None

    def takeAt(self, i):
        return self.items.pop(i) if 0 <= i < len(self.items) else None

    def _dock(self, item):
        w = item.widget()
        node = getattr(w, "vml_node", None)
        return node.props.get("DockPanel.Dock", "Left") if node else "Left"

    def _measure(self, which):
        w = h = 0
        for i in range(len(self.items) - 1, -1, -1):
            item = self.items[i]
            if item.widget() and item.widget().isHidden():
                continue
            s = getattr(item, which)()
            if self.last_fill and i == len(self.items) - 1:
                w, h = s.width(), s.height()
            elif self._dock(item) in ("Top", "Bottom"):
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
        for i, item in enumerate(self.items):
            if item.widget() and item.widget().isHidden():
                continue
            if self.last_fill and i == len(self.items) - 1:
                item.setGeometry(r)
                break
            h, d = item.sizeHint(), self._dock(item)
            if d == "Top":
                item.setGeometry(QRect(r.x(), r.y(), r.width(), h.height())); r.setTop(r.top() + h.height())
            elif d == "Bottom":
                item.setGeometry(QRect(r.x(), r.bottom() - h.height() + 1, r.width(), h.height())); r.setBottom(r.bottom() - h.height())
            elif d == "Right":
                item.setGeometry(QRect(r.right() - h.width() + 1, r.y(), h.width(), r.height())); r.setRight(r.right() - h.width())
            else:
                item.setGeometry(QRect(r.x(), r.y(), h.width(), r.height())); r.setLeft(r.left() + h.width())


def dock_add(parent, child):
    parent.widget.layout().addWidget(child.host)


def dock_place(parent, child):
    parent.widget.layout().invalidate()


def canvas_add(parent, child):
    child.host.setParent(parent.widget)
    canvas_place(parent, child)
    child.host.show()


ANCHORS = ("Top,Left", "Top,Right", "Bottom,Left", "Bottom,Right", "Top,Left,Right", "Bottom,Left,Right",
           "Top,Bottom,Left", "Top,Bottom,Right", "Top,Bottom,Left,Right")


def anchor_set(value):
    parts = {p.strip().capitalize() for p in str(value or "").split(",") if p.strip()}
    return parts or {"Top", "Left"}


def anchored_rect(props, natural, ref, cur):
    """Where a control anchored to some edges belongs when its container goes from size ref to size cur.
    Pinned to both opposite edges, it stretches; pinned only to the far edge, it moves; otherwise it stays."""
    x0, y0 = num(props.get("Canvas.Left", props.get("X"))), num(props.get("Canvas.Top", props.get("Y")))
    w0 = num(props.get("Width"), natural.width()) if props.get("Width") not in (None, "", "Auto") else natural.width()
    h0 = num(props.get("Height"), natural.height()) if props.get("Height") not in (None, "", "Auto") else natural.height()
    a = anchor_set(props.get("Anchor"))
    dx, dy = cur[0] - ref[0], cur[1] - ref[1]
    x, w = x0, w0
    if "Left" in a and "Right" in a:
        w = max(8, w0 + dx)
    elif "Right" in a:
        x = x0 + dx
    y, h = y0, h0
    if "Top" in a and "Bottom" in a:
        h = max(8, h0 + dy)
    elif "Bottom" in a:
        y = y0 + dy
    stretched = ("Left" in a and "Right" in a) or ("Top" in a and "Bottom" in a)
    return int(x), int(y), int(w), int(h), stretched


class CanvasWidget(QWidget):
    """A Canvas: children at Canvas.Left/Top, re-placed by their Anchor whenever the canvas resizes.
    Its reference size is the form's designed size (the Window's Width/Height) when it fills a window."""

    def __init__(self, node):
        super().__init__()
        self.node, self._ref = node, None
        self.setMinimumSize(50, 50)

    def ref_size(self):
        if self._ref is None:
            p = self.node.parent
            if p is not None and p.type.name == "Window" and p.props.get("Width") and p.props.get("Height"):
                self._ref = (num(p.props["Width"]), num(p.props["Height"]))
            elif self.width() > 60:
                self._ref = (self.width(), self.height())
        return self._ref

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.laid_out = True                     # anchors only mean something once we've a real size
        for child in list(self.node.children):
            canvas_place(self.node, child)


def canvas_place(parent, child):
    child.host.adjustSize()
    w = parent.widget
    ref = w.ref_size() if isinstance(w, CanvasWidget) and getattr(w, "laid_out", False) else None
    if ref is None or anchor_set(child.props.get("Anchor")) == {"Top", "Left"}:
        child.host.move(int(num(child.props.get("Canvas.Left", child.props.get("X")))),
                        int(num(child.props.get("Canvas.Top", child.props.get("Y")))))
        return
    x, y, cw, ch, stretched = anchored_rect(child.props, child.widget.sizeHint(), ref, (w.width(), w.height()))
    if stretched:
        child.widget.setFixedSize(cw, ch)
        child.host.adjustSize()
    child.host.move(x, y)


def canvas_remove(parent, child):
    child.host.setParent(None)


def scroll_add(parent, child):
    parent.widget.setWidget(child.host)


SCROLL_POLICY = {"Auto": Qt.ScrollBarAsNeeded, "Visible": Qt.ScrollBarAlwaysOn, "Hidden": Qt.ScrollBarAlwaysOff,
                 "Disabled": Qt.ScrollBarAlwaysOff}


# ------------------------------------------------------------------ makers

class _Edge(QWidget):
    """The thin line round a window, drawn on top of its outermost pixels (so nothing inside moves or shrinks)."""

    def __init__(self, window):
        super().__init__(window)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.colour, self.width_px = None, 0
        self.hide()

    def paintEvent(self, e):
        if self.colour is None:
            return
        p = _QPainter(self)
        w, h, m = self.width(), self.height(), self.width_px
        for r in ((0, 0, w, m), (0, h - m, w, m), (0, 0, m, h), (w - m, 0, m, h)):
            p.fillRect(*r, self.colour)
        p.end()


class WindowWidget(QWidget):
    """A form's window. It can draw a thin edge round itself (BorderBrush, BorderThickness): a white form on a
    white desktop otherwise has no visible edge on desktops that draw no frame of their own."""

    def __init__(self, node):
        super().__init__()
        self.node = node
        self.edge = _Edge(self)

    def set_edge(self, value, width=1):
        on = bool(value) and int(width) > 0
        self.edge.colour, self.edge.width_px = (qcolour(value), max(1, int(width))) if on else (None, 0)
        self.edge.setGeometry(self.rect())
        self.edge.setVisible(on)
        self.edge.raise_()
        self.edge.update()

    def edge_name(self):
        return self.edge.colour.name() if self.edge.colour is not None else ""

    def closeEvent(self, e):
        """The window is being closed: its OnClosing handler runs first, and can keep it open (CancelClose)."""
        asked = getattr(self, "closing", None)
        if asked is not None and not getattr(self, "_closing_now", False):
            self._closing_now = True
            try:
                if asked(e.spontaneous()) is False:
                    e.ignore()
                    return
            finally:
                self._closing_now = False
        super().closeEvent(e)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.edge.setGeometry(self.rect())
        self.edge.raise_()


def make_window(node):
    w = WindowWidget(node)
    lay = QVBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    w.resize(800, 600)
    return w


def window_edge(node, _value=None):
    p = node.props
    width = thickness(p["BorderThickness"])[0] if p.get("BorderThickness") not in (None, "") else 1
    node.widget.set_edge(p.get("BorderBrush") or "", width)


def make_box(node):
    w = QWidget()
    horiz = node.props.get("Orientation") == "Horizontal"
    lay = QHBoxLayout(w) if horiz else QVBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(int(num(node.props.get("Spacing"))))
    lay.addStretch(1)
    return w


def make_frame(node):
    w = QFrame()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    return w


def make_grid(node):
    w = QWidget()
    lay = QGridLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(0)
    return w


def make_dock(node):
    w = QWidget()
    w.setLayout(DockLayout())
    return w


def make_canvas(node):
    return CanvasWidget(node)


def make_scroll(node):
    w = QScrollArea()
    w.setWidgetResizable(True)
    w.setFrameShape(QFrame.NoFrame)
    return w


def make_label(node):
    w = QLabel()
    w.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
    return w


def place_label_text(w, across=None):
    """Where a TextBlock's words sit in its box. One line sits in the middle of its height; words that wrap
    start at the top and run down, as they do on a page and on a phone."""
    across = (w.alignment() & Qt.AlignHorizontal_Mask) if across is None else across
    w.setAlignment(across | (Qt.AlignTop if w.wordWrap() else Qt.AlignVCenter))


def make_textbox(node):
    w = QPlainTextEdit() if truthy(node.props.get("AcceptsReturn")) else QLineEdit()
    w.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
    return w


def make_button(node):
    w = QPushButton()
    w.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
    return w


def text_of(w):
    return w.toPlainText() if isinstance(w, QPlainTextEdit) else w.text()


def set_text(w, v):
    v = "" if v is None else str(v)
    if text_of(w) != v:
        (w.setPlainText if isinstance(w, QPlainTextEdit) else w.setText)(v)


def set_items(node, value):
    w = node.widget
    keep = w.currentText() if isinstance(w, QComboBox) else None
    w.clear()
    items = [s.strip() for s in str(value or "").split(",") if s.strip()]
    w.addItems(items)
    if keep and keep in items:
        w.setCurrentText(keep)


def set_item_list(node, items):
    """Fill a list or combo from a real list of strings (commas in an item are kept), keeping the selection if it can."""
    w = node.widget
    keep = read_selected_item(node)
    w.blockSignals(True)
    w.clear()
    w.addItems([str(i) for i in items])
    if isinstance(w, QComboBox):
        w.setCurrentIndex(w.findText(keep) if keep and w.findText(keep) >= 0 else (0 if w.count() else -1))
    else:
        found = w.findItems(keep, Qt.MatchExactly) if keep else []
        w.setCurrentItem(found[0] if found else None)
    w.blockSignals(False)
    now = read_selected_item(node)
    if now != keep:                                       # tell whoever depends on this that its choice changed
        (w.currentIndexChanged if isinstance(w, QComboBox) else w.currentRowChanged).emit(
            w.currentIndex() if isinstance(w, QComboBox) else w.currentRow())


def set_text_wrap(node, value):
    """A multi-line box: wrap long lines (the default) or scroll sideways (NoWrap), as code wants."""
    if isinstance(node.widget, QPlainTextEdit):
        node.widget.setLineWrapMode(QPlainTextEdit.NoWrap if value == "NoWrap" else QPlainTextEdit.WidgetWidth)


def set_password(node, value):
    if isinstance(node.widget, QLineEdit):
        node.widget.setEchoMode(QLineEdit.Password if truthy(value) else QLineEdit.Normal)


def set_selected_index(node, value):
    i = int(num(value, -1))
    (node.widget.setCurrentIndex if isinstance(node.widget, QComboBox) else node.widget.setCurrentRow)(i)


def read_selected_item(node):
    w = node.widget
    if isinstance(w, QComboBox):
        return w.currentText()
    it = w.currentItem()
    return it.text() if it else ""


def set_selected_item(node, value):
    w = node.widget
    if isinstance(w, QComboBox):
        i = w.findText(str(value))
        if i < 0 and value not in (None, ""):
            w.addItem(str(value)); i = w.count() - 1
        w.setCurrentIndex(i)
    else:
        found = w.findItems(str(value), Qt.MatchExactly)
        if found:
            w.setCurrentItem(found[0])


# ------------------------------------------------------------------ the registry

register(ControlType("Window", make_window, container=True, add_child=single_add, place_child=single_place,
                     remove_child=layout_remove, category="Containers",
                     events={"OnOpened": None, "OnClosing": None, **KEY_EVENTS}),   # OnOpened/OnClosing fired by the engine
         COMMON, [Prop("Title", "text", "Common", apply=lambda n, v: n.widget.setWindowTitle(str(v or ""))),
                  Prop("Version", "text", "Common"),                             # the app's own version; a phone shows it beside the app
                  Prop("Icon", "text", "Common"),                                # a picture for the app: its icon on a phone
                  Prop("WebAddress", "text", "Common"),                          # where the app is on the web, if it is: LinkAddress builds on it
                  Prop("AndroidPackage", "text", "Common"),                      # its package name as an Android app, to choose one's own (com.example.myapp)
                  Prop("LinkPass", "text", "Behaviour"),                         # put in by Visualised Pro when it saves an app that uses Link: see vml/link.py
                  Prop("PhoneFit", "choice", "Behaviour", options=("Fit", "None")),  # as a web page on a phone: scale to the screen's width, or leave alone
                  Prop("BorderBrush", "colour", "Appearance", apply=window_edge),    # an edge round the window
                  Prop("BorderThickness", "thickness", "Appearance", apply=window_edge),
                  Prop("Resizable", "bool", "Behaviour", default="true"),        # applied by the engine when shown
                  Prop("Modal", "bool", "Behaviour", default="false"),
                  Prop("MaxWidth", "number", "Layout", apply=lambda n, v: n.widget.setMaximumWidth(int(num(v, 16777215)) or 16777215)),
                  Prop("MaxHeight", "number", "Layout", apply=lambda n, v: n.widget.setMaximumHeight(int(num(v, 16777215)) or 16777215))])

register(ControlType("StackPanel", make_box, container=True, add_child=box_add, place_child=box_place,
                     remove_child=layout_remove, category="Containers", events=dict(POINTER_EVENTS)),
         COMMON, ATTACHED, PADDING_LAYOUT,
         [Prop("Orientation", "choice", "Layout", options=("Vertical", "Horizontal")),
          Prop("Spacing", "number", "Layout", apply=lambda n, v: n.widget.layout().setSpacing(int(num(v))))])

register(ControlType("Border", make_frame, container=True, add_child=single_add, place_child=single_place,
                     remove_child=layout_remove, category="Containers", events=dict(POINTER_EVENTS)),
         COMMON, ATTACHED, PADDING_LAYOUT)

register(ControlType("Grid", make_grid, container=True, add_child=grid_add, place_child=grid_place,
                     remove_child=layout_remove, category="Containers", events=dict(POINTER_EVENTS)),
         COMMON, ATTACHED,
         [Prop("ColumnDefinitions", "text", "Layout", apply=grid_apply_defs),
          Prop("RowDefinitions", "text", "Layout", apply=grid_apply_defs)])

register(ControlType("DockPanel", make_dock, container=True, add_child=dock_add, place_child=dock_place,
                     remove_child=layout_remove, category="Containers", events=dict(POINTER_EVENTS)),
         COMMON, ATTACHED,
         [Prop("LastChildFill", "bool", "Layout", default="true",
               apply=lambda n, v: setattr(n.widget.layout(), "last_fill", truthy(v) if v not in (None, "") else True))])

register(ControlType("Canvas", make_canvas, container=True, add_child=canvas_add, place_child=canvas_place,
                     remove_child=canvas_remove, category="Containers", events=dict(POINTER_EVENTS)),
         COMMON, ATTACHED)

register(ControlType("ScrollViewer", make_scroll, container=True, add_child=scroll_add, remove_child=lambda p, c: p.widget.takeWidget(),
                     category="Containers"),
         COMMON, ATTACHED,
         [Prop("VerticalScrollBarVisibility", "choice", "Behaviour", options=tuple(SCROLL_POLICY),
               apply=lambda n, v: n.widget.setVerticalScrollBarPolicy(SCROLL_POLICY.get(v, Qt.ScrollBarAsNeeded))),
          Prop("HorizontalScrollBarVisibility", "choice", "Behaviour", options=tuple(SCROLL_POLICY),
               apply=lambda n, v: n.widget.setHorizontalScrollBarPolicy(SCROLL_POLICY.get(v, Qt.ScrollBarAsNeeded)))])

register(ControlType("TextBlock", make_label, events=dict(POINTER_EVENTS)),
         COMMON, ATTACHED, PADDING_STYLE,
         [Prop("Text", "text", "Common", apply=lambda n, v: n.widget.setText(str(v or ""))),
          Prop("TextWrapping", "choice", "Text", options=("NoWrap", "Wrap"),
               apply=lambda n, v: (n.widget.setWordWrap(v == "Wrap"), place_label_text(n.widget))),
          Prop("TextAlignment", "choice", "Text", options=("Left", "Center", "Right"),
               apply=lambda n, v: place_label_text(n.widget, {"Center": Qt.AlignHCenter, "Right": Qt.AlignRight}.get(v, Qt.AlignLeft)))])

register(ControlType("TextBox", make_textbox,
                     events={"TextChanged": on_signal("textChanged"), **KEY_EVENTS, **POINTER_EVENTS}),
         COMMON, ATTACHED, PADDING_STYLE,
         [Prop("Text", "text", "Common", apply=lambda n, v: set_text(n.widget, v), read=lambda n: text_of(n.widget)),
          Prop("Watermark", "text", "Common", apply=lambda n, v: n.widget.setPlaceholderText(str(v or ""))),
          Prop("IsReadOnly", "bool", "Behaviour", apply=lambda n, v: n.widget.setReadOnly(truthy(v))),
          Prop("IsPassword", "bool", "Behaviour", apply=set_password),      # dots instead of what is typed
          Prop("TextWrapping", "choice", "Text", options=("Wrap", "NoWrap"), apply=set_text_wrap),
          Prop("AcceptsReturn", "bool", "Behaviour")])

register(ControlType("Button", make_button, events={"OnClick": on_signal("clicked"), **KEY_EVENTS, **POINTER_EVENTS}),
         COMMON, ATTACHED, PADDING_STYLE,
         [Prop("Content", "text", "Common", apply=lambda n, v: n.widget.setText(str(v or "")))])

register(ControlType("CheckBox", lambda n: QCheckBox(),
                     events={"OnClick": on_signal("clicked"), "OnChecked": on_signal("toggled"), **KEY_EVENTS, **POINTER_EVENTS}),
         COMMON, ATTACHED,
         [Prop("Content", "text", "Common", apply=lambda n, v: n.widget.setText(str(v or ""))),
          Prop("IsChecked", "bool", "Common", apply=lambda n, v: n.widget.setChecked(truthy(v)),
               read=lambda n: "true" if n.widget.isChecked() else "false")])

def _source(node, _value):
    node.engine.source_changed(node)


DATA = [Prop("ItemsSource", "text", "Data", apply=_source),   # a query (or a script) that fills the control: see vml/data.py
        Prop("Database", "text", "Data", apply=_source)]      # which opened database it asks; empty = the main one

register(ControlType("ComboBox", lambda n: QComboBox(), events={"SelectionChanged": on_signal("currentIndexChanged"), **KEY_EVENTS}),
         COMMON, ATTACHED, DATA,
         [Prop("Items", "list", "Common", apply=set_items),
          Prop("SelectedIndex", "number", "Common", apply=set_selected_index, read=lambda n: n.widget.currentIndex()),
          Prop("SelectedItem", "text", "Common", apply=set_selected_item, read=read_selected_item)])

register(ControlType("ListBox", lambda n: QListWidget(),
                     events={"SelectionChanged": on_signal("currentRowChanged"), "OnDoubleClick": on_signal("itemDoubleClicked"),
                             "OnContextMenu": on_context_menu, **KEY_EVENTS}),
         COMMON, ATTACHED, DATA,
         [Prop("Items", "list", "Common", apply=set_items),
          Prop("SelectedIndex", "number", "Common", apply=set_selected_index, read=lambda n: n.widget.currentRow()),
          Prop("SelectedItem", "text", "Common", apply=set_selected_item, read=read_selected_item)])

class SplitterBar(QFrame):
    """A bar between two docked panes that is dragged to resize the one before it (or the one named in Target).
    Docked Top or Bottom it changes that pane's Height; docked Left or Right, its Width."""

    def __init__(self, node):
        super().__init__()
        self.node, self.start, self.fire = node, None, None
        self.setMouseTracking(True)
        thick = int(num(node.props.get("Thickness"), 5))        # 5 pixels unless Thickness says otherwise
        if self.upright():
            self.setFixedWidth(thick)
        else:
            self.setFixedHeight(thick)
        if not node.props.get("Background"):
            self.setStyleSheet("background-color: #CBD5E1;")

    def side(self):
        return str(self.node.props.get("DockPanel.Dock") or "Top")

    def upright(self):
        return self.side() in ("Left", "Right")

    def target(self):
        named = str(self.node.props.get("Target") or "").strip()
        parent = self.node.parent
        if parent is None:
            return None
        if named:
            return next((c for c in parent.children if c.name == named), None)
        at = parent.children.index(self.node) if self.node in parent.children else 0
        return parent.children[at - 1] if at > 0 else None

    def enterEvent(self, e):
        self.setCursor(Qt.SplitHCursor if self.upright() else Qt.SplitVCursor)

    def mousePressEvent(self, e):
        t = self.target()
        if e.button() == Qt.LeftButton and t is not None and t.widget is not None:
            pos = e.globalPosition().toPoint()
            self.start = (pos.x() if self.upright() else pos.y(), t.widget.width() if self.upright() else t.widget.height())

    def mouseMoveEvent(self, e):
        t = self.target()
        if self.start is None or t is None:
            return
        pos = e.globalPosition().toPoint()
        moved = (pos.x() if self.upright() else pos.y()) - self.start[0]
        if self.side() in ("Bottom", "Right"):
            moved = -moved
        room = (self.node.parent.widget.width() if self.upright() else self.node.parent.widget.height())
        least = int(num(self.node.props.get("MinSize"), 60))
        size = max(least, min(max(least, room - least), self.start[1] + moved))
        self.resize_target(t, size)

    def resize_target(self, t, size):
        key = "Width" if self.upright() else "Height"
        t.props[key] = str(int(size))
        set_size("w" if self.upright() else "h")(t, int(size))
        if self.node.parent.widget.layout() is not None:
            self.node.parent.widget.layout().invalidate()

    def mouseReleaseEvent(self, e):
        if self.start is not None and self.fire is not None:
            self.fire({})
        self.start = None


def splitter_moved(node, fire):
    node.widget.fire = fire


def splitter_size(node, _value=None):
    thick = int(num(node.props.get("Thickness"), 5))
    if node.widget.upright():
        node.widget.setFixedWidth(thick)
    else:
        node.widget.setFixedHeight(thick)


class TimerMark(QLabel):
    """A Timer: it runs its OnTick script every Interval milliseconds while IsEnabled. On the design surface it is
    a small clock to pick up and set; in the running form it is not seen."""

    def __init__(self, node):
        super().__init__("⏱")
        from PySide6.QtCore import QTimer
        self.node, self.fire = node, None
        self.designing = str(node.scope).startswith("design:")
        self.ticker = QTimer(self)
        self.ticker.timeout.connect(self.tick)
        self.setAlignment(Qt.AlignCenter)
        self.setFixedSize(28, 28)
        self.setStyleSheet("background-color: #FEF3C7; border: 1px solid #D97706; border-radius: 4px; font-size: 15px;")
        self.setToolTip("Timer: runs OnTick every Interval milliseconds. It isn't seen when the form runs.")
        if not self.designing:
            self.setFixedSize(0, 0)
            self.hide()

    def setVisible(self, on):
        super().setVisible(bool(on) and self.designing)        # never seen in a running form, whatever asks

    def tick(self):
        if self.fire is not None and not self.designing:
            self.fire({})

    def refresh(self):
        gap = max(1, int(num(self.node.props.get("Interval"), 1000)))
        on = str(self.node.props.get("IsEnabled", "true")).strip().lower() != "false"
        if self.designing or not on:
            self.ticker.stop()
        elif not self.ticker.isActive() or self.ticker.interval() != gap:
            self.ticker.start(gap)


def timer_tick(node, fire):
    node.widget.fire = fire
    node.widget.refresh()


register(ControlType("Timer", lambda n: TimerMark(n), events={"OnTick": timer_tick}),
         [Prop("Name", "text", "Common"),
          Prop("Interval", "number", "Behaviour", default="1000", apply=lambda n, v: n.widget.refresh()),   # milliseconds between ticks
          Prop("IsEnabled", "bool", "Behaviour", default="true", apply=lambda n, v: n.widget.refresh())],  # false stops it
         ATTACHED)


class ProgressWidget(QFrame):
    """A progress bar, drawn the same everywhere. BarStyle: Solid, Blocks (the classic row of squares) or Thin
    (a line). ShowText puts the percentage on it; IsIndeterminate sweeps to and fro for work of unknown length."""

    def __init__(self, node):
        super().__init__()
        from PySide6.QtCore import QTimer
        self.node, self.phase = node, 0.0
        self.sweep = QTimer(self)
        self.sweep.timeout.connect(self.step)
        self.setMinimumSize(8, 4)

    def fraction(self):
        p = self.node.props
        low, high = num(p.get("Minimum"), 0), num(p.get("Maximum"), 100)
        if high <= low:
            return 0.0
        return max(0.0, min(1.0, (num(p.get("Value"), 0) - low) / (high - low)))

    def step(self):
        self.phase = (self.phase + 0.02) % 2.0
        self.update()

    def refresh(self):
        busy = str(self.node.props.get("IsIndeterminate", "")).lower() == "true" and not str(self.node.scope).startswith("design:")
        if busy and not self.sweep.isActive():
            self.sweep.start(30)
        elif not busy and self.sweep.isActive():
            self.sweep.stop()
        self.update()

    def paintEvent(self, e):
        p = self.node.props
        g = _QPainter(self)
        g.setRenderHint(_QPainter.Antialiasing)
        w, h = self.width(), self.height()
        upright = str(p.get("Orientation", "")).lower() == "vertical"
        style = str(p.get("BarStyle") or "Solid").lower()
        track, bar = qcolour(p.get("Background") or "#E5E7EB"), qcolour(p.get("Foreground") or "#2563EB")
        length, across = (h, w) if upright else (w, h)
        thick = min(across, 4) if style == "thin" else across
        off = (across - thick) / 2
        radius = min(num(str(p.get("CornerRadius") or (2 if style == "thin" else 3)).split(",")[0]), thick / 2)

        def box(start, size, colour):
            g.setPen(Qt.NoPen)
            g.setBrush(colour)
            if upright:
                g.drawRoundedRect(QRect(int(off), int(length - start - size), int(thick), int(size)), radius, radius)
            else:
                g.drawRoundedRect(QRect(int(start), int(off), int(size), int(thick)), radius, radius)

        box(0, length, track)
        if str(p.get("IsIndeterminate", "")).lower() == "true":
            piece = length * 0.3
            at = self.phase if self.phase <= 1 else 2 - self.phase
            box(at * (length - piece), piece, bar)
        elif style == "blocks":
            block = max(6, int(thick * 0.6))
            gap = 2
            count = max(1, int((length + gap) // (block + gap)))
            lit = int(round(self.fraction() * count))
            for i in range(lit):
                box(i * (block + gap), block, bar)
        else:
            filled = self.fraction() * length
            if filled >= 1:
                box(0, filled, bar)
        if str(p.get("ShowText", "")).lower() == "true" and style != "thin" and str(p.get("IsIndeterminate", "")).lower() != "true":
            g.setPen(qcolour(p.get("TextColour") or ("#FFFFFF" if self.fraction() > 0.55 and style != "blocks" else "#111827")))
            g.drawText(self.rect(), Qt.AlignCenter, f"{int(round(self.fraction() * 100))}%")
        g.end()


_progress = lambda n, v=None: n.widget.refresh()
register(ControlType("ProgressBar", lambda n: ProgressWidget(n), events=dict(POINTER_EVENTS)),
         [p for p in COMMON if p.name not in ("Background", "Foreground", "CornerRadius")], ATTACHED,
         [Prop("Value", "number", "Common", default="0", apply=_progress),
          Prop("Minimum", "number", "Common", default="0", apply=_progress),
          Prop("Maximum", "number", "Common", default="100", apply=_progress),
          Prop("BarStyle", "choice", "Appearance", options=("Solid", "Blocks", "Thin"), default="Solid", apply=_progress),
          Prop("ShowText", "bool", "Appearance", apply=_progress),              # the percentage, written on the bar
          Prop("IsIndeterminate", "bool", "Behaviour", apply=_progress),         # busy, for work of unknown length
          Prop("Orientation", "choice", "Appearance", options=("Horizontal", "Vertical"), default="Horizontal", apply=_progress),
          Prop("Foreground", "colour", "Appearance", apply=_progress),           # the bar
          Prop("Background", "colour", "Appearance", apply=_progress),           # the track behind it
          Prop("CornerRadius", "number", "Appearance", apply=_progress)])


class SliderWidget(QFrame):
    """A slider: a track with a knob the user drags. Value runs from Minimum to Maximum in whole numbers."""

    def __init__(self, node):
        super().__init__()
        from PySide6.QtWidgets import QSlider, QHBoxLayout
        self.node = node
        self.bar = QSlider(Qt.Horizontal, self)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.bar)
        self.valueChanged = self.bar.valueChanged
        self.setMinimumSize(24, 16)
        self.refresh()

    def refresh(self):
        p = self.node.props
        low, high = int(num(p.get("Minimum"), 0)), int(num(p.get("Maximum"), 100))
        self.bar.blockSignals(True)                     # only the user moving it is a change to tell the form about
        self.bar.setRange(low, max(low, high))
        self.bar.setValue(int(num(p.get("Value"), low)))
        self.bar.blockSignals(False)


_slider = lambda n, v=None: n.widget.refresh()
register(ControlType("Slider", lambda n: SliderWidget(n), events={"ValueChanged": on_signal("valueChanged"), **POINTER_EVENTS}),
         [p for p in COMMON if p.name not in ("Background", "Foreground", "CornerRadius")], ATTACHED,
         [Prop("Value", "number", "Common", default="0", apply=_slider, read=lambda n: str(n.widget.bar.value())),
          Prop("Minimum", "number", "Common", default="0", apply=_slider),
          Prop("Maximum", "number", "Common", default="100", apply=_slider)])


# For docked layouts (a DockPanel), so it is not offered on the design surface, where controls sit on a canvas.
register(ControlType("Splitter", lambda n: SplitterBar(n), events={"OnMoved": splitter_moved}),
         COMMON, ATTACHED,
         [Prop("Target", "text", "Behaviour"),                  # the pane it resizes; empty = the one docked just before it
          Prop("MinSize", "number", "Behaviour"),               # the smallest either side may become (60)
          Prop("Thickness", "number", "Appearance", apply=splitter_size)])

register(ControlType("Rectangle", lambda n: QFrame(), events=dict(POINTER_EVENTS)),
         COMMON, ATTACHED,
         [Prop("Fill", "colour", "Appearance", apply=style("background-color", colour)),
          Prop("Stroke", "colour", "Appearance", apply=lambda n, v: (n.props.__setitem__("BorderBrush", v), set_border(n, v))),
          Prop("StrokeThickness", "number", "Appearance",
               apply=lambda n, v: (n.props.__setitem__("BorderThickness", v), set_border(n, v)))])


# ------------------------------------------------------------------ menus (virtual nodes: they own a QAction / QMenu, not a widget on screen)

from PySide6.QtGui import QAction          # noqa: E402
from PySide6.QtWidgets import QMenu, QMenuBar             # noqa: E402

KEY_NAMES = {"Del": "Delete", "Esc": "Escape", "Ins": "Insert", "PgUp": "PgUp", "PgDn": "PgDown"}


def make_menuitem(node):
    sep = truthy(node.props.get("IsSeparator", ""))
    node.action = QAction("" if sep else (node.props.get("Text") or node.props.get("Header") or node.name))
    node.menu = None
    return QWidget()


def ensure_menu(node):
    if node.menu is None:
        node.menu = QMenu(node.action.text())
        node.action.setMenu(node.menu)
    return node.menu


def menu_add(parent, child):
    target = parent.menu if parent.type.name == "ContextMenu" else ensure_menu(parent)
    target.addAction(child.action)


def menu_remove(parent, child):
    if parent.menu is not None:
        parent.menu.removeAction(child.action)


def menu_text(node, value):
    node.action.setText(str(value or ""))
    if node.menu is not None:
        node.menu.setTitle(str(value or ""))


def shortcut(node, value):
    v = str(value or "")
    for k, q in KEY_NAMES.items():
        v = "+".join(q if part == k else part for part in v.split("+"))
    node.action.setShortcut(QKeySequence(v))
    node.action.setShortcutContext(Qt.WindowShortcut)       # each window's shortcuts are its own


def set_separator(node, value):
    """A separator is just a line: no text (some Qt styles would show its name as a heading)."""
    on = truthy(value)
    node.action.setSeparator(on)
    if on:
        node.action.setText("")


def make_contextmenu(node):
    node.menu = QMenu()
    node.action = None
    return QWidget()


MENU_PROPS = [
    Prop("Text", "text", "Common", apply=menu_text),
    Prop("Header", "text", "Common", apply=menu_text),
    Prop("Shortcut", "text", "Common", apply=shortcut),
    Prop("IsEnabled", "bool", "Behaviour", default="true",
         apply=lambda n, v: n.action.setEnabled(truthy(v) if v not in (None, "") else True)),
    Prop("IsVisible", "bool", "Behaviour", default="true",
         apply=lambda n, v: n.action.setVisible(truthy(v) if v not in (None, "") else True)),
    Prop("IsSeparator", "bool", "Behaviour", apply=lambda n, v: set_separator(n, v)),
    Prop("ToolTip", "text", "Behaviour", apply=lambda n, v: n.action.setToolTip(str(v or ""))),
]

register(ControlType("MenuItem", make_menuitem, container=True, add_child=menu_add, remove_child=menu_remove,
                     category="Menus", events={"OnClick": lambda node, fire: node.action.triggered.connect(lambda *a: fire({}))}),
         MENU_PROPS)
REGISTRY["MenuItem"].virtual = True

register(ControlType("ContextMenu", make_contextmenu, container=True, add_child=menu_add, remove_child=menu_remove,
                     category="Menus", events={"OnOpened": lambda node, fire: node.menu.aboutToShow.connect(lambda: fire({}))}),
         [Prop("AttachTo", "text", "Common")])
REGISTRY["ContextMenu"].virtual = True

register(ControlType("MenuTheme", lambda n: QWidget(), category="Menus"),
         [Prop(p, "colour", "Appearance") for p in ("Background", "Foreground", "HoverBackground", "HoverForeground",
                                                     "PopupBackground", "PopupBorder")] + [Prop("Height", "number", "Layout")])
REGISTRY["MenuTheme"].virtual = True


def make_menubar(node):
    bar = QMenuBar()
    bar.setNativeMenuBar(False)
    return bar


class _HoverOpen(QObject):
    """Open a menu bar's dropdowns as the pointer passes over them, without a click."""

    def __init__(self, bar):
        super().__init__(bar)
        self.bar = bar

    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.MouseMove:
            act = self.bar.actionAt(ev.position().toPoint())
            if act is not None and act.menu() is not None and self.bar.activeAction() is not act:
                self.bar.setActiveAction(act)
        return False


def set_open_on_hover(node, value):
    bar = node.widget
    on = truthy(value)
    if on and not getattr(bar, "_hover", None):
        bar._hover = _HoverOpen(bar)
        bar.installEventFilter(bar._hover)
        bar.setMouseTracking(True)
    elif not on and getattr(bar, "_hover", None):
        bar.removeEventFilter(bar._hover)
        bar._hover = None


register(ControlType("TinyMenu", make_menubar, category="Menus"), COMMON, ATTACHED,
         [Prop("OpenOnHover", "bool", "Behaviour", apply=set_open_on_hover)])


def theme_sheets(t):
    """MenuTheme properties -> stylesheets for the bar and its popups."""
    bg, fg = colour(t.get("Background", "#f0f0f0")), colour(t.get("Foreground", "#000000"))
    hbg, hfg = colour(t.get("HoverBackground", bg)), colour(t.get("HoverForeground", fg))
    pbg, pb = colour(t.get("PopupBackground", "#ffffff")), colour(t.get("PopupBorder", "#c0c0c0"))
    h = int(num(t.get("Height", 0)))
    bar = (f"QMenuBar {{ background: {bg}; color: {fg}; {f'min-height: {h}px;' if h else ''} }}"
           f"QMenuBar::item {{ background: transparent; padding: 4px 10px; }}"
           f"QMenuBar::item:selected {{ background: {hbg}; color: {hfg}; border-bottom: 2px solid {hfg}; }}")
    popup = (f"QMenu {{ background: {pbg}; color: #222; border: 1px solid {pb}; padding: 4px 0; }}"
             f"QMenu::item {{ padding: 5px 26px 5px 22px; }}"
             f"QMenu::item:selected {{ background: {bg}; color: {fg}; }}"
             f"QMenu::item:disabled {{ color: #999; }}"
             f"QMenu::separator {{ height: 1px; background: #ddd; margin: 4px 8px; }}")
    return bar, popup


# hit-testing: IsHitTestVisible=false lets clicks fall through to whatever is underneath
def hit_test(node, value):
    through = value not in (None, "") and not truthy(value)
    for w in (node.widget, node.host):
        w.setAttribute(Qt.WA_TransparentForMouseEvents, through)


for _ct in REGISTRY.values():
    if not getattr(_ct, "virtual", False) and _ct.name not in ("Window",):
        _ct.props["IsHitTestVisible"] = Prop("IsHitTestVisible", "bool", "Behaviour", apply=hit_test, default="true")
        _ct.props["Focusable"] = Prop("Focusable", "bool", "Behaviour",
                                      apply=lambda n, v: n.widget.setFocusPolicy(Qt.StrongFocus if truthy(v) else Qt.NoFocus))



# ------------------------------------------------------------------ Frame (VB's Frame: a captioned container)

class FrameWidget(CanvasWidget):
    """Children are placed at Left/Top inside the frame and anchored to its edges. Its reference size is its own
    designed Width/Height, so anchored children follow the frame when it stretches."""
    CAPTION_GAP = 8

    def ref_size(self):
        p = self.node.props
        if p.get("Width") and p.get("Height"):
            return (num(p["Width"]), num(p["Height"]))
        return (self.width(), self.height())

    def paintEvent(self, e):
        super().paintEvent(e)
        p = _QPainter(self)
        p.setRenderHint(_QPainter.Antialiasing)
        props = self.node.props
        text = str(props.get("Text", "") or "")
        border = _QColor(colour(props.get("BorderBrush") or "#9CA3AF"))
        fm = p.fontMetrics()
        top = fm.height() // 2 if text else 0
        p.setPen(_QPen(border, 1))
        sides = thickness(props["BorderThickness"]) if props.get("BorderThickness") not in (None, "") else None
        if sides is None or (len(set(sides)) == 1 and sides[0] > 0):
            p.drawRoundedRect(0, top, self.width() - 1, self.height() - 1 - top, 4, 4)
        else:                                                # only the sides asked for (none at all for 0)
            p.setRenderHint(_QPainter.Antialiasing, False)
            r, bt = self.width() - 1, self.height() - 1
            for on, line in zip(sides, ((0, top, 0, bt), (0, top, r, top), (r, top, r, bt), (0, bt, r, bt))):
                if on > 0:
                    p.drawLine(*line)
        if text:
            w = fm.horizontalAdvance(text) + 8
            bg = self.palette().window().color()
            colour_bg = props.get("Background")
            p.fillRect(self.CAPTION_GAP, 0, w, fm.height(), _QColor(colour(colour_bg)) if colour_bg else bg)
            fg = props.get("Foreground")
            p.setPen(_QColor(colour(fg)) if fg else self.palette().windowText().color())
            p.drawText(self.CAPTION_GAP + 4, fm.ascent(), text)
        p.end()


register(ControlType("Frame", lambda n: FrameWidget(n), container=True, add_child=canvas_add, place_child=canvas_place,
                     remove_child=canvas_remove, category="Containers", events=dict(POINTER_EVENTS)),
         COMMON, ATTACHED,
         [Prop("Text", "text", "Common", apply=lambda n, v: n.widget.update()),
          Prop("BorderBrush", "colour", "Appearance", apply=lambda n, v: n.widget.update()),
          Prop("BorderThickness", "thickness", "Appearance")])


# ------------------------------------------------------------------ RadioButton (VB's OptionButton)

class Radio(QRadioButton):
    """One of a set: choosing it clears the others in the same container with the same GroupName. (Each control
    here sits in a host of its own, so Qt's own grouping, which goes by a shared parent widget, can't be used.)"""

    def __init__(self, node):
        super().__init__()
        self.node = node
        self.setAutoExclusive(False)
        self.toggled.connect(self.chosen)

    def nextCheckState(self):                             # clicking the chosen one leaves it chosen
        if not self.isChecked():
            self.setChecked(True)

    def chosen(self, on):
        parent = self.node.parent
        if not on or parent is None:
            return
        group = str(self.node.props.get("GroupName") or "")
        for other in parent.children:
            if other is not self.node and other.type.name == "RadioButton" and \
                    str(other.props.get("GroupName") or "") == group and other.widget.isChecked():
                other.widget.setChecked(False)


register(ControlType("RadioButton", lambda n: Radio(n),
                     events={"OnClick": on_signal("clicked"), "OnChecked": on_signal("toggled"), **KEY_EVENTS, **POINTER_EVENTS}),
         COMMON, ATTACHED,
         [Prop("Content", "text", "Common", apply=lambda n, v: n.widget.setText(str(v or ""))),
          Prop("IsChecked", "bool", "Common", apply=lambda n, v: n.widget.setChecked(truthy(v)),
               read=lambda n: "true" if n.widget.isChecked() else "false"),
          Prop("GroupName", "text", "Common")])


# ------------------------------------------------------------------ Image (VB's PictureBox / Image)

class ImageWidget(QFrame):
    """A picture: a file beside the form (Source=logo.png), or carried inside the form as a data: address."""

    def __init__(self, node):
        super().__init__()
        self.node, self.pix = node, None

    def load(self):
        src = str(self.node.props.get("Source") or "").strip()
        pix = _QPixmap()
        if src.startswith("data:") and "," in src:
            import base64
            try:
                pix.loadFromData(base64.b64decode(src.split(",", 1)[1]))
            except ValueError:
                pass
        elif src:
            import os
            path = os.path.expanduser(src)
            if not os.path.isabs(path):
                path = os.path.join(self.node.engine.asset_dir(self.node.scope), path)
            pix.load(path)
        self.pix = None if pix.isNull() else pix
        self.updateGeometry()
        self.update()

    def sizeHint(self):
        return self.pix.size() if self.pix is not None else QSize(120, 90)

    def minimumSizeHint(self):
        return QSize(4, 4)

    def paintEvent(self, e):
        super().paintEvent(e)
        p = _QPainter(self)
        if self.pix is None:
            if str(self.node.scope).startswith("design:"):   # on the design surface, show where it will go
                p.setPen(_QPen(_QColor("#9ca3af"), 1, Qt.DashLine))
                p.drawRect(0, 0, self.width() - 1, self.height() - 1)
                p.drawText(self.rect(), Qt.AlignCenter, "Image")
            p.end()
            return
        mode = str(self.node.props.get("Stretch") or "Uniform")
        if mode == "None":
            p.drawPixmap(0, 0, self.pix)
        elif mode == "Fill":
            p.setRenderHint(_QPainter.SmoothPixmapTransform)
            p.drawPixmap(self.rect(), self.pix)
        else:
            aspect = Qt.KeepAspectRatioByExpanding if mode == "UniformToFill" else Qt.KeepAspectRatio
            scaled = self.pix.scaled(self.size(), aspect, Qt.SmoothTransformation)
            p.drawPixmap((self.width() - scaled.width()) // 2, (self.height() - scaled.height()) // 2, scaled)
        p.end()


register(ControlType("Image", lambda n: ImageWidget(n), events=dict(POINTER_EVENTS)),
         COMMON, ATTACHED,
         [Prop("Source", "text", "Common", apply=lambda n, v: n.widget.load()),
          Prop("Stretch", "choice", "Appearance", options=("Uniform", "Fill", "UniformToFill", "None"),
               apply=lambda n, v: n.widget.update())])


# ------------------------------------------------------------------ DataGrid (rows and columns, read-only)

class GridWidget(QTableWidget):
    def __init__(self, node):
        super().__init__()
        self.node, self.cols, self.data = node, [], []
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setAlternatingRowColors(True)
        self.verticalHeader().hide()
        self.verticalHeader().setDefaultSectionSize(24)
        self.horizontalHeader().setStretchLastSection(True)
        self.horizontalHeader().setHighlightSections(False)

    def set_data(self, cols, rows):
        """cols: the headings; rows: a list of lists, one value per column."""
        keep = self.selected_value()
        self.cols, self.data = [str(c) for c in cols], [["" if v is None else str(v) for v in r] for r in rows]
        self.blockSignals(True)
        self.clear()
        self.setColumnCount(len(self.cols))
        self.setRowCount(len(self.data))
        self.setHorizontalHeaderLabels(self.cols)
        for r, row in enumerate(self.data):
            for c in range(len(self.cols)):
                self.setItem(r, c, QTableWidgetItem(row[c] if c < len(row) else ""))
        back = next((r for r, row in enumerate(self.data) if keep and row and row[0] == keep), -1)
        self.setCurrentCell(back, 0) if back >= 0 else self.setCurrentItem(None)
        self.blockSignals(False)
        if len(self.data) <= 500:
            self.resizeColumnsToContents()
        if self.selected_value() != keep:
            self.itemSelectionChanged.emit()

    def set_headings(self, cols):
        self.set_data(cols, self.data)

    def selected_row(self):
        r = self.currentRow()
        return r if 0 <= r < len(self.data) and self.selectionModel().hasSelection() else -1

    def selected_value(self):
        r = self.selected_row()
        return self.data[r][0] if r >= 0 and self.data[r] else ""

    def selected_json(self):
        import json
        r = self.selected_row()
        return json.dumps(dict(zip(self.cols, self.data[r]))) if r >= 0 else ""


def grid_static(node, _value=None):
    """Columns=Name,Age and Items=Ann|34;Bob|27: a few rows written into the form itself."""
    p = node.props
    cols = [c.strip() for c in str(p.get("Columns") or "").split(",") if c.strip()]
    rows = [[cell.strip() for cell in row.split("|")] for row in str(p.get("Items") or "").split(";") if row.strip()]
    if not cols and rows:
        cols = [f"Column{i + 1}" for i in range(max(len(r) for r in rows))]
    node.widget.set_data(cols, rows)


def grid_select(node, value):
    i = int(num(value, -1))
    node.widget.setCurrentCell(i, 0) if 0 <= i < node.widget.rowCount() else node.widget.setCurrentItem(None)


register(ControlType("DataGrid", lambda n: GridWidget(n),
                     events={"SelectionChanged": on_signal("itemSelectionChanged"), "OnDoubleClick": on_signal("cellDoubleClicked"),
                             "OnContextMenu": on_context_menu, **KEY_EVENTS}),
         COMMON, ATTACHED, DATA,
         [Prop("Columns", "list", "Common", apply=grid_static),
          Prop("Items", "list", "Common", apply=grid_static),
          Prop("SelectedIndex", "number", "Common", apply=grid_select, read=lambda n: n.widget.selected_row()),
          Prop("SelectedValue", "text", "Common", read=lambda n: n.widget.selected_value()),
          Prop("SelectedItem", "text", "Common", read=lambda n: n.widget.selected_json()),
          Prop("RowCount", "number", "Common", read=lambda n: len(n.widget.data))])


# ------------------------------------------------------------------ TreeView (Items are paths: Forms/Main,Forms/Login)

class TreeWidget(QTreeWidget):
    def __init__(self, node):
        super().__init__()
        self.node = node
        self.setHeaderHidden(True)
        self.setIndentation(16)

    @staticmethod
    def path_of(item):
        parts = []
        while item is not None:
            parts.insert(0, item.text(0))
            item = item.parent()
        return "/".join(parts)

    def set_paths(self, paths):
        keep = self.selected()
        self.blockSignals(True)
        self.clear()
        made = {}
        for path in paths:
            parts = [x.strip() for x in str(path).split("/") if x.strip()]
            for depth in range(1, len(parts) + 1):
                key = "/".join(parts[:depth])
                if key not in made:
                    owner = made.get("/".join(parts[:depth - 1]))
                    made[key] = QTreeWidgetItem(owner if owner is not None else self, [parts[depth - 1]])
        if str(self.node.props.get("IsExpanded", "true")).lower() != "false":
            self.expandAll()
        self.setCurrentItem(made.get(keep))
        self.blockSignals(False)
        if self.selected() != keep:
            self.currentItemChanged.emit(self.currentItem(), None)

    def selected(self):
        return self.path_of(self.currentItem())

    def select(self, path):
        want = "/".join(x.strip() for x in str(path or "").split("/") if x.strip())
        stack = [self.topLevelItem(i) for i in range(self.topLevelItemCount())]
        while stack:
            it = stack.pop()
            if self.path_of(it) == want:
                return self.setCurrentItem(it)
            stack += [it.child(i) for i in range(it.childCount())]
        self.setCurrentItem(None)


def tree_items(node, value):
    node.widget.set_paths([s for s in re_split_items(value)])


def re_split_items(value):
    import re
    return [s.strip() for s in re.split(r"[,\n]", str(value or "")) if s.strip()]


register(ControlType("TreeView", lambda n: TreeWidget(n),
                     events={"SelectionChanged": on_signal("currentItemChanged"), "OnDoubleClick": on_signal("itemDoubleClicked"),
                             "OnContextMenu": on_context_menu, **KEY_EVENTS}),
         COMMON, ATTACHED, DATA,
         [Prop("Items", "list", "Common", apply=tree_items),
          Prop("SelectedItem", "text", "Common", apply=lambda n, v: n.widget.select(v), read=lambda n: n.widget.selected()),
          Prop("IsExpanded", "bool", "Behaviour", default="true",
               apply=lambda n, v: n.widget.expandAll() if truthy(v) or v in (None, "") else n.widget.collapseAll())])


for _name in ("Frame", "RadioButton", "Image", "DataGrid", "TreeView"):
    REGISTRY[_name].props.setdefault("IsHitTestVisible", Prop("IsHitTestVisible", "bool", "Behaviour", apply=hit_test, default="true"))
    REGISTRY[_name].props.setdefault("Focusable", Prop("Focusable", "bool", "Behaviour",
                                                       apply=lambda n, v: n.widget.setFocusPolicy(Qt.StrongFocus if truthy(v) else Qt.NoFocus)))
