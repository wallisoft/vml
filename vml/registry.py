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
from PySide6.QtGui import QColor as _QColor, QKeySequence, QPainter as _QPainter, QPen as _QPen
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLayout, QLineEdit,
                               QListWidget, QPlainTextEdit, QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget)

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

def make_window(node):
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    w.resize(800, 600)
    return w


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
          Prop("TextWrapping", "choice", "Text", options=("NoWrap", "Wrap"), apply=lambda n, v: n.widget.setWordWrap(v == "Wrap")),
          Prop("TextAlignment", "choice", "Text", options=("Left", "Center", "Right"),
               apply=lambda n, v: n.widget.setAlignment({"Center": Qt.AlignHCenter, "Right": Qt.AlignRight}.get(v, Qt.AlignLeft)
                                                        | Qt.AlignVCenter))])

register(ControlType("TextBox", make_textbox,
                     events={"TextChanged": on_signal("textChanged"), **KEY_EVENTS, **POINTER_EVENTS}),
         COMMON, ATTACHED, PADDING_STYLE,
         [Prop("Text", "text", "Common", apply=lambda n, v: set_text(n.widget, v), read=lambda n: text_of(n.widget)),
          Prop("Watermark", "text", "Common", apply=lambda n, v: n.widget.setPlaceholderText(str(v or ""))),
          Prop("IsReadOnly", "bool", "Behaviour", apply=lambda n, v: n.widget.setReadOnly(truthy(v))),
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

register(ControlType("ComboBox", lambda n: QComboBox(), events={"SelectionChanged": on_signal("currentIndexChanged"), **KEY_EVENTS}),
         COMMON, ATTACHED,
         [Prop("Items", "list", "Common", apply=set_items),
          Prop("SelectedIndex", "number", "Common", apply=set_selected_index, read=lambda n: n.widget.currentIndex()),
          Prop("SelectedItem", "text", "Common", apply=set_selected_item, read=read_selected_item)])

register(ControlType("ListBox", lambda n: QListWidget(), events={"SelectionChanged": on_signal("currentRowChanged"), **KEY_EVENTS}),
         COMMON, ATTACHED,
         [Prop("Items", "list", "Common", apply=set_items),
          Prop("SelectedIndex", "number", "Common", apply=set_selected_index, read=lambda n: n.widget.currentRow()),
          Prop("SelectedItem", "text", "Common", apply=set_selected_item, read=read_selected_item)])

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
