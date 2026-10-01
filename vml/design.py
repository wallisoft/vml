"""
Design-time building blocks, registered as ordinary VML controls:

  DesignSurface  a form being designed. Real controls, made click-through; an overlay on top does
                 selection, drag-to-move, eight resize handles, snap-to-grid and arrow-key nudging.
                 Events: OnSelectionChanged, OnContextMenu, OnChanged, OnDoubleClick.
  PropertyGrid   every property of its Target, grouped, with the right editor for each, straight from
                 the registry. Edits write back through SetProperty; changes made anywhere else show
                 up live, so it can never go stale.

The designer itself stays a VML form with Lua scripts; the mechanics live here, written once.
"""
import json

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QScrollArea,
                               QSizePolicy, QToolButton, QVBoxLayout, QWidget)

from .registry import COMMON, REGISTRY, ControlType, Prop, colour, num, register, truthy

GROUP_ORDER = ["Form", "Control", "Common", "Text", "Appearance", "Layout", "Placement", "Behaviour", "Events"]
HIDDEN_IN_GRID = {"X", "Y", "Name", "IsHitTestVisible", "Focusable"}
HANDLE = 7
PAGE_MARGIN = 28


def inert(widget):
    """Design-time controls look real but don't react: the overlay gets every click."""
    for w in [widget, *widget.findChildren(QWidget)]:
        w.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        w.setFocusPolicy(Qt.NoFocus)


# ====================================================================== DesignSurface

class Overlay(QWidget):
    def __init__(self, view):
        super().__init__(view.page)
        self.view = view
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True)
        self.mode, self.start, self.orig, self.handle = None, QPoint(), QRect(), None

    # geometry helpers (all in page coordinates)
    def rect_of(self, node):
        return node.host.geometry().translated(self.view.form.pos())

    def handles(self, r):
        cx, cy = r.center().x(), r.center().y()
        pts = {"TopLeft": (r.left(), r.top()), "Top": (cx, r.top()), "TopRight": (r.right(), r.top()),
               "Right": (r.right(), cy), "BottomRight": (r.right(), r.bottom()), "Bottom": (cx, r.bottom()),
               "BottomLeft": (r.left(), r.bottom()), "Left": (r.left(), cy)}
        return {k: QRect(x - HANDLE // 2, y - HANDLE // 2, HANDLE, HANDLE) for k, (x, y) in pts.items()}

    def form_grip(self):
        f = self.view.form.geometry()
        return QRect(f.right() - 4, f.bottom() - 4, 10, 10)

    def hit(self, pos):
        fpos = pos - self.view.form.pos()
        for node in reversed(self.view.node.children):
            if node.host.isVisible() and node.host.geometry().contains(fpos):
                return node
        return None

    # painting: grid dots, selection, handles, form grip
    def paintEvent(self, _):
        p = QPainter(self)
        v = self.view
        if v.show_grid:
            p.setPen(QPen(QColor(0, 0, 0, 38), 1))
            f, g = v.form.geometry(), v.grid
            for x in range(f.left(), f.right(), g):
                for y in range(f.top(), f.bottom(), g):
                    p.drawPoint(x, y)
        sel = v.selected_node()
        if sel is not None:
            r = self.rect_of(sel)
            p.setPen(QPen(QColor("#2563eb"), 1, Qt.DashLine))
            p.setBrush(Qt.NoBrush)
            p.drawRect(r.adjusted(-1, -1, 0, 0))
            p.setPen(QPen(QColor("#2563eb"), 1))
            p.setBrush(QColor("white"))
            for h in self.handles(r).values():
                p.drawRect(h)
        p.setPen(QPen(QColor("#9ca3af"), 1))
        p.setBrush(QColor("#9ca3af"))
        p.drawRect(self.form_grip())
        p.end()

    def cursor_for(self, pos):
        if self.form_grip().contains(pos):
            return Qt.SizeFDiagCursor
        sel = self.view.selected_node()
        if sel is not None:
            for name, r in self.handles(self.rect_of(sel)).items():
                if r.adjusted(-2, -2, 2, 2).contains(pos):
                    return {"TopLeft": Qt.SizeFDiagCursor, "BottomRight": Qt.SizeFDiagCursor,
                            "TopRight": Qt.SizeBDiagCursor, "BottomLeft": Qt.SizeBDiagCursor,
                            "Top": Qt.SizeVerCursor, "Bottom": Qt.SizeVerCursor}.get(name, Qt.SizeHorCursor)
        return Qt.SizeAllCursor if self.hit(pos) is not None else Qt.ArrowCursor

    # mouse
    def mousePressEvent(self, e):
        self.setFocus()
        pos, v = e.position().toPoint(), self.view
        self.start, self.handle, self.mode = pos, None, None
        if e.button() == Qt.LeftButton and self.form_grip().contains(pos):
            self.mode, self.orig = "form", QRect(v.form.geometry())
            return
        sel = v.selected_node()
        if e.button() == Qt.LeftButton and sel is not None:
            for name, r in self.handles(self.rect_of(sel)).items():
                if r.adjusted(-2, -2, 2, 2).contains(pos):
                    self.mode, self.handle, self.orig = "resize", name, QRect(sel.host.geometry())
                    return
        node = self.hit(pos)
        v.select(node.name if node else "", user=True)
        fpos = pos - v.form.pos()
        v.engine.store.set_setting("click_x", fpos.x())
        v.engine.store.set_setting("click_y", fpos.y())
        if e.button() == Qt.RightButton:
            v.emit("OnContextMenu", {"click_x": fpos.x(), "click_y": fpos.y()})
        elif node is not None:
            self.mode, self.orig = "move", QRect(node.host.geometry())

    def mouseMoveEvent(self, e):
        pos, v = e.position().toPoint(), self.view
        if self.mode is None:
            self.setCursor(self.cursor_for(pos))
            return
        d = pos - self.start
        snap = (lambda n: n) if e.modifiers() & Qt.AltModifier else v.snap
        if self.mode == "form":
            v.set_form_size(max(80, snap(self.orig.width() + d.x())), max(60, snap(self.orig.height() + d.y())))
        elif self.mode == "move":
            node = v.selected_node()
            if node is not None:
                node.host.move(max(0, snap(self.orig.x() + d.x())), max(0, snap(self.orig.y() + d.y())))
        elif self.mode == "resize":
            node = v.selected_node()
            if node is not None:
                o, h = self.orig, self.handle
                x, y, w, hgt = o.x(), o.y(), o.width(), o.height()
                if "Right" in h:
                    w = max(8, snap(o.width() + d.x()))
                if "Bottom" in h:
                    hgt = max(8, snap(o.height() + d.y()))
                if "Left" in h:
                    x = min(snap(o.x() + d.x()), o.x() + o.width() - 8)
                    w = o.x() + o.width() - x
                if "Top" in h:
                    y = min(snap(o.y() + d.y()), o.y() + o.height() - 8)
                    hgt = o.y() + o.height() - y
                node.widget.setFixedSize(w, hgt)
                node.host.setGeometry(QRect(x, y, w, hgt))
        self.update()

    def mouseReleaseEvent(self, e):
        v, mode = self.view, self.mode
        self.mode = None
        node = v.selected_node()
        if mode == "form":
            v.commit_form()
        elif mode in ("move", "resize") and node is not None:
            g = node.host.geometry()
            if g != self.orig:
                v.commit(node, g, resized=(mode == "resize"))

    def mouseDoubleClickEvent(self, e):
        node = self.hit(e.position().toPoint())
        if node is not None:
            self.mode = None
            self.view.select(node.name, user=True)        # whatever was double-clicked is what we act on
            self.view.emit("OnDoubleClick", {"selected_control": node.name})

    def keyPressEvent(self, e):
        v = self.view
        node = v.selected_node()
        step = v.grid if e.modifiers() & Qt.ShiftModifier else 1
        moves = {Qt.Key_Left: (-step, 0), Qt.Key_Right: (step, 0), Qt.Key_Up: (0, -step), Qt.Key_Down: (0, step)}
        if node is not None and e.key() in moves:
            dx, dy = moves[e.key()]
            g = node.host.geometry()
            g.moveTo(max(0, g.x() + dx), max(0, g.y() + dy))
            v.commit(node, g)
        elif e.key() == Qt.Key_Escape:
            v.select("", user=True)
        else:
            super().keyPressEvent(e)


class SurfaceView(QScrollArea):
    def __init__(self, node):
        super().__init__()
        self.node, self.engine = node, node.engine
        self.handlers, self.selected, self.grid, self.show_grid = {}, "", 8, True
        self.setWidgetResizable(False)
        self.setFrameShape(QFrame.NoFrame)
        self.page = QWidget()
        self.page.setObjectName("DesignPage")
        self.page.setStyleSheet("#DesignPage { background: #e5e7eb; }")
        self.form = QWidget(self.page)
        self.form.setObjectName("DesignForm")
        self.form.setAttribute(Qt.WA_StyledBackground, True)
        self.form.move(PAGE_MARGIN, PAGE_MARGIN)
        self.overlay = Overlay(self)
        self.setWidget(self.page)
        vp = self.viewport()                     # a palette colour, not a stylesheet: it can't cascade into the form
        pal = vp.palette()
        pal.setColor(vp.backgroundRole(), QColor("#e5e7eb"))
        vp.setPalette(pal)
        vp.setAutoFillBackground(True)
        self.set_form_bg("#ffffff")
        self.set_form_size(640, 480)

    # selection
    def selected_node(self):
        return next((n for n in self.node.children if n.name == self.selected), None)

    def select(self, name, user=False):
        name = name or ""
        changed = name != self.selected
        self.selected = name
        self.overlay.update()
        if changed and user:
            self.emit("OnSelectionChanged", {"selected_control": name})

    def emit(self, event, details):
        fire = self.handlers.get(event)
        if fire:
            fire(details)

    # geometry
    def snap(self, n):
        return int(round(n / self.grid) * self.grid) if self.grid > 1 else int(n)

    def set_form_size(self, w, h):
        self.form.resize(int(w), int(h))
        self.page.resize(int(w) + 2 * PAGE_MARGIN + 40, int(h) + 2 * PAGE_MARGIN + 40)
        self.overlay.setGeometry(self.page.rect())
        self.overlay.raise_()
        self.overlay.update()

    def set_form_bg(self, value):
        self.form_bg = colour(value or "#ffffff")
        self.form.setStyleSheet(f"#DesignForm {{ background: {self.form_bg}; border: 1px solid #9ca3af; }}")

    def commit(self, node, g, resized=False):
        e = self.engine
        e.cmd_SetProperty(node.name, "Canvas.Left", str(g.x()))
        e.cmd_SetProperty(node.name, "Canvas.Top", str(g.y()))
        if resized:
            e.cmd_SetProperty(node.name, "Width", str(g.width()))
            e.cmd_SetProperty(node.name, "Height", str(g.height()))
        self.overlay.update()
        self.emit("OnChanged", {"selected_control": node.name})

    def commit_form(self):
        self.engine.cmd_SetProperty(self.node.name, "FormWidth", str(self.form.width()))
        self.engine.cmd_SetProperty(self.node.name, "FormHeight", str(self.form.height()))
        self.emit("OnChanged", {"selected_control": ""})


def make_surface(node):
    return SurfaceView(node)


def surface_add(parent, child):
    view = parent.widget
    child.host.setParent(view.form)
    surface_place(parent, child)
    child.host.show()
    inert(child.host)
    view.overlay.raise_()


def surface_place(parent, child):
    child.host.adjustSize()
    child.host.move(int(num(child.props.get("Canvas.Left"))), int(num(child.props.get("Canvas.Top"))))
    inert(child.host)
    parent.widget.overlay.update()


def surface_remove(parent, child):
    view = parent.widget
    child.host.setParent(None)
    if view.selected == child.name:
        view.selected = ""
    view.overlay.update()


def surface_event(name):
    def hook(node, fire):
        node.widget.handlers[name] = fire
    return hook


def set_grid(node, v):
    node.widget.grid = max(1, int(num(v, 8)))
    node.widget.overlay.update()


def set_show_grid(node, v):
    node.widget.show_grid = truthy(v) if v not in (None, "") else True
    node.widget.overlay.update()


register(ControlType("DesignSurface", make_surface, container=True, add_child=surface_add, place_child=surface_place,
                     remove_child=surface_remove, category="Design",
                     events={e: surface_event(e) for e in ("OnSelectionChanged", "OnContextMenu", "OnChanged", "OnDoubleClick")}),
         [p for p in COMMON if p.name in ("Margin", "IsVisible", "Width", "Height", "HorizontalAlignment", "VerticalAlignment")],
         [Prop("FormName", "text", "Form", default="Form1"),
          Prop("FormTitle", "text", "Form", default="Form1"),
          Prop("FormWidth", "number", "Form", default="640",
               apply=lambda n, v: n.widget.set_form_size(num(v, 640), n.widget.form.height()),
               read=lambda n: n.widget.form.width()),
          Prop("FormHeight", "number", "Form", default="480",
               apply=lambda n, v: n.widget.set_form_size(n.widget.form.width(), num(v, 480)),
               read=lambda n: n.widget.form.height()),
          Prop("FormBackground", "colour", "Form", default="#ffffff", apply=lambda n, v: n.widget.set_form_bg(v)),
          Prop("GridSize", "number", "Behaviour", default="8", apply=set_grid),
          Prop("ShowGrid", "bool", "Behaviour", default="true", apply=set_show_grid),
          Prop("Selected", "text", "Behaviour", apply=lambda n, v: n.widget.select(str(v or "")),
               read=lambda n: n.widget.selected)])
REGISTRY["DesignSurface"].design_only = True


# ====================================================================== PropertyGrid

class Swatch(QToolButton):
    def __init__(self, edit):
        super().__init__()
        self.edit = edit
        self.setFixedSize(20, 20)
        self.clicked.connect(self.pick)
        edit.textChanged.connect(self.paint)
        self.paint(edit.text())

    def paint(self, value):
        c = colour(value) if value else "transparent"
        self.setStyleSheet(f"QToolButton {{ background: {c}; border: 1px solid #9ca3af; border-radius: 3px; }}")

    def pick(self):
        start = QColor(self.edit.text()) if QColor.isValidColorName(self.edit.text()) else QColor("white")
        c = QColorDialog.getColor(start, self, "Choose a colour")
        if c.isValid():
            self.edit.setText(c.name().upper())
            self.edit.editingFinished.emit()


class GridView(QScrollArea):
    def __init__(self, node):
        super().__init__()
        self.node, self.engine = node, node.engine
        self.target, self.editors, self._loading = "", {}, False
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.engine.listeners.append(self.on_changed)
        self.rebuild()

    def rebuild(self):
        self.editors = {}
        body = QWidget()
        body.setObjectName("PropGridBody")
        lay = QVBoxLayout(body)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(2)
        target = self.engine.find(self.target) if self.target else None
        if target is None:
            msg = QLabel("Select a control to see its properties.")
            msg.setStyleSheet("color: #6b7280;")
            msg.setWordWrap(True)
            lay.addWidget(msg)
            lay.addStretch(1)
            self.setWidget(body)
            return
        design_form = target.type.name == "DesignSurface"
        head = QLabel(f"<b>{'Form' if design_form else self.engine.cmd_GetControlType(target.name)}</b>"
                      + ("" if design_form else f"  <span style='color:#6b7280'>{target.name}</span>"))
        head.setStyleSheet("font-size: 13px; padding: 2px 0 6px 0;")
        lay.addWidget(head)
        if not design_form:
            lay.addLayout(self.row_layout("Name", self.name_editor(target.name)))
        props = json.loads(self.engine.cmd_GetControlPropertiesJson(target.name))
        groups = {}
        for p in props:
            if p["name"] in HIDDEN_IN_GRID or (design_form and p["group"] != "Form"):
                continue
            if design_form is False and p["group"] == "Form":
                continue
            groups.setdefault(p["group"], []).append(p)
        if not design_form:
            events = sorted(e for e in target.type.events if target.type.events[e] is not None)
            if events:
                groups["Events"] = [{"name": e, "value": target.props.get(e, ""), "type": "text", "kind": "event",
                                     "options": []} for e in events]
        for g in sorted(groups, key=lambda g: GROUP_ORDER.index(g) if g in GROUP_ORDER else 99):
            title = QLabel(g.upper())
            title.setStyleSheet("color: #2563eb; font-size: 10px; font-weight: 700; padding: 8px 0 2px 0;")
            lay.addWidget(title)
            for p in groups[g]:
                lay.addLayout(self.row_layout(p["name"], self.editor(p)))
        lay.addStretch(1)
        self.setWidget(body)

    def row_layout(self, label, editor):
        row = QHBoxLayout()
        row.setSpacing(6)
        lbl = QLabel(label)
        lbl.setFixedWidth(118)
        lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        lbl.setStyleSheet("color: #4b5563; font-size: 11px;")
        lbl.setToolTip(label)
        row.addWidget(lbl)
        row.addWidget(editor, 1)
        return row

    def name_editor(self, name):
        ed = QLineEdit(name)
        ed.setStyleSheet("font-size: 11px; font-weight: 600;")
        ed.editingFinished.connect(lambda: self.rename(ed))
        return ed

    def rename(self, ed):
        new = ed.text().strip()
        if new and new != self.target:
            if self.engine.cmd_RenameControl(self.target, new):
                self.target = new
                self.node.props["Target"] = new
            ed.setText(self.target)

    def editor(self, p):
        name, value, kind = p["name"], p["value"], p.get("kind", "text")
        if kind == "bool":
            ed = QCheckBox()
            ed.setChecked(truthy(value) if value != "" else p["name"] in ("IsEnabled", "IsVisible"))
            ed.toggled.connect(lambda on, n=name: self.commit(n, "true" if on else "false"))
            widget = ed
        elif kind == "choice":
            ed = QComboBox()
            ed.addItems([""] + list(p["options"]))
            ed.setCurrentText(value)
            ed.currentTextChanged.connect(lambda v, n=name: self.commit(n, v))
            widget = ed
        else:
            ed = QLineEdit(value)
            ed.setStyleSheet("font-size: 11px;")
            if kind == "event":
                ed.setPlaceholderText("script name")
            ed.editingFinished.connect(lambda n=name, e=ed: self.commit(n, e.text()))
            widget = ed
            if kind == "colour":
                box = QWidget()
                h = QHBoxLayout(box)
                h.setContentsMargins(0, 0, 0, 0)
                h.setSpacing(4)
                h.addWidget(ed, 1)
                h.addWidget(Swatch(ed))
                widget = box
        widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.editors[name] = ed
        return widget

    def commit(self, prop, value):
        if self._loading or not self.target:
            return
        node = self.engine.find(self.target)
        if node is None:
            return
        current = self.engine.cmd_GetProperty(self.target, prop)
        if str(current) == str(value):
            return
        if prop in node.type.events:
            self.engine.cmd_SetEvent(self.target, prop, value)
        else:
            self.engine.cmd_SetProperty(self.target, prop, value)
        surface = node.parent if node.parent is not None and node.parent.type.name == "DesignSurface" else None
        if surface is not None:
            surface.widget.emit("OnChanged", {"selected_control": node.name})
        elif node.type.name == "DesignSurface":
            node.widget.emit("OnChanged", {"selected_control": ""})

    def on_changed(self, name, prop, value):
        """Something changed a property anywhere: if it's ours, show it (unless the user is typing in that box)."""
        if name != self.target or prop not in self.editors:
            return
        ed = self.editors[prop]
        if ed.hasFocus():
            return
        if prop in ("Canvas.Left", "Canvas.Top", "Width", "Height", "FormWidth", "FormHeight"):
            value = self.engine.cmd_GetProperty(name, prop)
        self._loading = True
        try:
            if isinstance(ed, QCheckBox):
                ed.setChecked(truthy(value))
            elif isinstance(ed, QComboBox):
                ed.setCurrentText(str(value))
            else:
                ed.setText(str(value))
        finally:
            self._loading = False


def set_target(node, value):
    view = node.widget
    view.target = str(value or "")
    view.rebuild()


register(ControlType("PropertyGrid", GridView, category="Design"),
         [p for p in COMMON if p.name in ("Margin", "IsVisible", "Width", "Height", "Background")],
         [Prop("Target", "text", "Common", apply=set_target)])
REGISTRY["PropertyGrid"].design_only = True

# Sensible starting points for controls added on a design surface
DESIGN_DEFAULTS = {
    "Button": {"Content": "Button", "Width": "100", "Height": "30"},
    "TextBox": {"Width": "160", "Height": "26", "Watermark": ""},
    "TextBlock": {"Text": "Label"},
    "CheckBox": {"Content": "CheckBox"},
    "ComboBox": {"Items": "One,Two,Three", "SelectedIndex": "0", "Width": "140"},
    "ListBox": {"Items": "One,Two,Three", "Width": "140", "Height": "100"},
    "Border": {"Width": "200", "Height": "120", "Background": "#F3F4F6", "BorderBrush": "#9CA3AF",
               "BorderThickness": "1", "CornerRadius": "6"},
    "StackPanel": {"Width": "200", "Height": "120", "Background": "#F9FAFB"},
    "Grid": {"Width": "200", "Height": "120", "Background": "#F9FAFB"},
    "DockPanel": {"Width": "200", "Height": "120", "Background": "#F9FAFB"},
    "Rectangle": {"Width": "120", "Height": "80", "Fill": "#BFDBFE", "Stroke": "#2563EB", "StrokeThickness": "1"},
    "ScrollViewer": {"Width": "200", "Height": "120"},
}
