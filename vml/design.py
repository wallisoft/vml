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
from PySide6.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QMenu, QMenuBar,
                               QScrollArea, QSizePolicy, QToolButton, QVBoxLayout, QWidget)

from .registry import (COMMON, REGISTRY, ControlType, Prop, anchor_set, anchored_rect, colour, num, register, theme_sheets,
                       truthy)

GROUP_ORDER = ["Form", "Control", "Common", "Data", "Placement", "Layout", "Text", "Appearance", "Behaviour", "Events"]
# On a canvas form these only matter inside layout panels, so the grid leaves them out; and it uses VB's names.
CANVAS_HIDDEN = {"DockPanel.Dock", "Grid.Row", "Grid.Column", "Grid.RowSpan", "Grid.ColumnSpan",
                 "HorizontalAlignment", "VerticalAlignment", "Margin"}
CANVAS_LABELS = {"Canvas.Left": "Left", "Canvas.Top": "Top"}
PLACEMENT_ORDER = {"Canvas.Left": 0, "Canvas.Top": 1, "Anchor": 2}
HIDDEN_IN_GRID = {"X", "Y", "Name", "IsHitTestVisible", "Focusable"}
HANDLE = 7
PAGE_MARGIN = 28
TITLE_H = 30                 # the pretend window title bar above the form


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
        return QRect(node.host.mapTo(self.view.page, QPoint(0, 0)), node.host.size())

    def handles(self, r):
        cx, cy = r.center().x(), r.center().y()
        pts = {"TopLeft": (r.left(), r.top()), "Top": (cx, r.top()), "TopRight": (r.right(), r.top()),
               "Right": (r.right(), cy), "BottomRight": (r.right(), r.bottom()), "Bottom": (cx, r.bottom()),
               "BottomLeft": (r.left(), r.bottom()), "Left": (r.left(), cy)}
        return {k: QRect(x - HANDLE // 2, y - HANDLE // 2, HANDLE, HANDLE) for k, (x, y) in pts.items()}

    def form_grip(self):
        f = self.view.form.geometry()
        return QRect(f.right() - 4, f.bottom() - 4, 10, 10)

    def hit(self, pos, container=None):
        """The deepest control under pos (page coordinates): a control inside a Frame wins over the Frame."""
        container = container or self.view.node
        for node in reversed(container.children):
            if node.host.isVisible() and self.rect_of(node).contains(pos):
                if node.type.name == "Frame":
                    return self.hit(pos, node) or node
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
        if v.selected == "menubar":
            p.setPen(QPen(QColor("#2563eb"), 1, Qt.DashLine))
            p.setBrush(Qt.NoBrush)
            p.drawRect(v.menubar.geometry().adjusted(0, 0, -1, -1))
        if v.selected.startswith("menu:"):
            act = next((a for a in v.menubar.actions() if a.data() == v.selected[5:]), None)
            if act is not None:
                g = v.menubar.actionGeometry(act).translated(v.menubar.pos())
                p.setPen(QPen(QColor("#2563eb"), 1, Qt.DashLine))
                p.setBrush(Qt.NoBrush)
                p.drawRect(g.adjusted(0, 0, -1, -1))
        sel = v.selected_node()
        if sel is not None:
            r = self.rect_of(sel)
            p.setPen(QPen(QColor("#2563eb"), 1, Qt.DashLine))
            p.setBrush(Qt.NoBrush)
            p.drawRect(r.adjusted(-1, -1, 0, 0))
            a = anchor_set(sel.props.get("Anchor"))
            if a != {"Top", "Left"}:
                f = v.form.geometry()
                p.setPen(QPen(QColor(37, 99, 235, 120), 1, Qt.DotLine))
                cx, cy = r.center().x(), r.center().y()
                if "Left" in a:
                    p.drawLine(f.left(), cy, r.left(), cy)
                if "Right" in a:
                    p.drawLine(r.right(), cy, f.right(), cy)
                if "Top" in a:
                    p.drawLine(cx, f.top(), cx, r.top())
                if "Bottom" in a:
                    p.drawLine(cx, r.bottom(), cx, f.bottom())
            p.setPen(QPen(QColor("#2563eb"), 1))
            p.setBrush(QColor("white"))
            for h in self.handles(r).values():
                p.drawRect(h)
        p.setPen(QPen(QColor("#9ca3af"), 1))
        p.setBrush(QColor("#9ca3af"))
        p.drawRect(self.form_grip())
        self.paint_title_bar(p)
        p.end()

    def paint_title_bar(self, p):
        """A window title bar above the form, so it looks like the window it will become."""
        v, f = self.view, self.view.form.geometry()
        bar = QRect(f.left(), f.top() - v.menu_h() - TITLE_H, f.width(), TITLE_H)
        p.setPen(QPen(QColor("#9ca3af"), 1))
        p.setBrush(QColor("#f3f4f6"))
        p.drawRect(bar.adjusted(0, 0, -1, 0))
        title = str(v.node.props.get("FormTitle") or v.node.props.get("FormName") or "Form1")
        p.setPen(QColor("#111827"))
        p.drawText(bar.adjusted(12, 0, -120, 0), Qt.AlignVCenter | Qt.AlignLeft, title)
        resizable = str(v.node.props.get("FormResizable", "true")).lower() != "false"
        x = bar.right() - 36
        for glyph in ("close", "max", "min"):
            r = QRect(x, bar.top() + 7, 16, 16)
            p.setPen(QPen(QColor("#9ca3af") if glyph == "max" and not resizable else QColor("#374151"), 1.4))
            if glyph == "close":
                p.drawLine(r.left() + 3, r.top() + 3, r.right() - 3, r.bottom() - 3)
                p.drawLine(r.right() - 3, r.top() + 3, r.left() + 3, r.bottom() - 3)
            elif glyph == "max":
                p.setBrush(Qt.NoBrush)
                p.drawRect(r.adjusted(3, 3, -3, -3))
            else:
                p.drawLine(r.left() + 3, r.center().y() + 3, r.right() - 3, r.center().y() + 3)
            x -= 36

    def geometry_moved(self):
        self.view.emit("OnGeometry", {})

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
            # anchored controls follow the form as it resizes: remember where they started
            self.anchored = [(n, dict(n.props), n.widget.sizeHint()) for n in v.node.children
                             if anchor_set(n.props.get("Anchor")) != {"Top", "Left"}]
            return
        sel = v.selected_node()
        if e.button() == Qt.LeftButton and sel is not None:
            for name, r in self.handles(self.rect_of(sel)).items():
                if r.adjusted(-2, -2, 2, 2).contains(pos):
                    self.mode, self.handle, self.orig = "resize", name, QRect(sel.host.geometry())
                    return
        if v.menu_items and v.menubar.geometry().contains(pos):
            local = v.menubar.mapFrom(v.page, pos)
            act = v.menubar.actionAt(local)
            name = act.data() if act is not None else ""
            target = f"menu:{name}" if name else "menubar"
            v.select(target, user=True)
            if e.button() == Qt.RightButton:
                v.emit("OnMenuContextMenu", {"selected_control": target})
            elif act is not None and act.menu() is not None:
                geo = v.menubar.actionGeometry(act)
                act.menu().popup(v.menubar.mapToGlobal(geo.bottomLeft()))
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
            if v.menu_items and truthy(v.menu_settings.get("OpenOnHover", "false")) and v.menubar.geometry().contains(pos):
                act = v.menubar.actionAt(v.menubar.mapFrom(v.page, pos))
                if act is not None and act.menu() is not None and not act.menu().isVisible():
                    act.menu().popup(v.menubar.mapToGlobal(v.menubar.actionGeometry(act).bottomLeft()))
            return
        d = pos - self.start
        snap = (lambda n: n) if e.modifiers() & Qt.AltModifier else v.snap
        if self.mode == "form":
            nw, nh = max(80, snap(self.orig.width() + d.x())), max(60, snap(self.orig.height() + d.y()))
            v.set_form_size(nw, nh)
            for node, props, natural in getattr(self, "anchored", []):
                x, y, w, h, stretched = anchored_rect(props, natural, (self.orig.width(), self.orig.height()), (nw, nh))
                if stretched:
                    node.widget.setFixedSize(w, h)
                    node.host.setGeometry(x, y, w, h)
                else:
                    node.host.move(x, y)
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
        self.geometry_moved()

    def mouseReleaseEvent(self, e):
        v, mode = self.view, self.mode
        self.mode = None
        node = v.selected_node()
        if mode == "form":
            v.commit_form()
        elif mode in ("move", "resize") and node is not None:
            g = node.host.geometry()
            if mode == "move":
                target = v.container_at(e.position().toPoint(), exclude=node) or v.node
                if target is not node.parent:
                    v.engine.cmd_SetParent(node.name, target.name)
                    self.update()
                    v.emit("OnChanged", {"selected_control": node.name})
                    return
            if g != self.orig:
                v.commit(node, g, resized=(mode == "resize"))

    def mouseDoubleClickEvent(self, e):
        node = self.hit(e.position().toPoint())
        self.mode = None
        self.view.select(node.name if node else "", user=True)   # whatever was double-clicked; nothing = the form
        self.view.emit("OnDoubleClick", {"selected_control": node.name if node else ""})

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
            self.geometry_moved()
        elif e.key() == Qt.Key_Escape:
            v.select("", user=True)
        else:
            super().keyPressEvent(e)


class SurfaceView(QScrollArea):
    def __init__(self, node):
        super().__init__()
        self.node, self.engine = node, node.engine
        self.handlers, self.selected, self.grid, self.show_grid, self.snap_on = {}, "", 8, True, True
        self.setWidgetResizable(False)
        self.setFrameShape(QFrame.NoFrame)
        self.page = QWidget()
        self.page.setObjectName("DesignPage")
        self.page.setStyleSheet("#DesignPage { background: #e5e7eb; }")
        self.form = QWidget(self.page)
        self.form.setObjectName("DesignForm")
        self.form.setAttribute(Qt.WA_StyledBackground, True)
        self.form.move(PAGE_MARGIN, PAGE_MARGIN + TITLE_H)
        self.menu_items, self.menu_settings = [], {}
        self.menubar = QMenuBar(self.page)                  # the designed form's menu, shown as it will look
        self.menubar.setNativeMenuBar(False)
        self.menubar.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.menubar.hide()
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
    def walk(self, container=None):
        for n in (container or self.node).children:
            yield n
            if n.type.container:
                yield from self.walk(n)

    def selected_node(self):
        return next((n for n in self.walk() if n.name == self.selected), None)

    def container_at(self, page_pos, exclude=None):
        """The deepest Frame under a point, ignoring exclude and everything inside it; None means the form."""
        found, container = None, self.node
        while True:
            nxt = None
            for n in reversed(container.children):
                if n is exclude or n.type.name != "Frame" or not n.host.isVisible():
                    continue
                if self.overlay.rect_of(n).contains(page_pos):
                    nxt = n
                    break
            if nxt is None:
                return found
            found = container = nxt

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
        return int(round(n / self.grid) * self.grid) if self.snap_on and self.grid > 1 else int(n)

    def menu_h(self):
        return self.menubar.sizeHint().height() if self.menu_items else 0

    def set_menu(self, items):
        """Show the designed form's menu bar with real dropdowns. In the designer, choosing an item in a
        dropdown selects it, and right-clicking one offers Add / Delete / Edit Script."""
        self.menu_items = list(items)
        self.menubar.clear()
        self._menu_filters = []
        parents, items = {}, self.menu_items
        for i, it in enumerate(items):
            level = int(it.get("level", 0))
            target = self.menubar if level == 0 else parents.get(level - 1)
            if target is None:
                continue
            if it.get("separator"):
                act = target.addSeparator()
                act.setData(it["name"])
                continue
            has_kids = i + 1 < len(items) and int(items[i + 1].get("level", 0)) > level
            if has_kids or level == 0:
                menu = QMenu(it.get("text") or "", target)
                menu.installEventFilter(self._menu_filter(menu))
                act = target.addMenu(menu)
                parents[level] = menu
            else:
                act = target.addAction(it.get("text") or "")
                act.triggered.connect(lambda _=False, n=it["name"]: self.select(f"menu:{n}", user=True))
            act.setData(it["name"])
            act.setEnabled(bool(it.get("enabled", True)))
            if it.get("shortcut"):
                act.setShortcut(it["shortcut"])
        self.menubar.setVisible(bool(self.menu_items))
        self.set_form_size(self.form.width(), self.form.height())

    def apply_menu_settings(self):
        """The bar's colours, as the running form will show them (a MenuTheme)."""
        st = {k: v for k, v in self.menu_settings.items() if v and k != "OpenOnHover"}
        if st:
            bar_css, popup_css = theme_sheets(st)
            self.menubar.setStyleSheet(bar_css + popup_css)
        else:
            self.menubar.setStyleSheet("")
        self.overlay.update()

    def reopen_menu_for(self, name):
        """After an edit, open the dropdown holding this item again, so you can carry on where you were."""
        idx = next((i for i, it in enumerate(self.menu_items) if it["name"] == name), None)
        if idx is None:
            return
        top = idx
        while top > 0 and self.menu_items[top]["level"] > 0:
            top -= 1
        top_name = self.menu_items[top]["name"]
        act = next((a for a in self.menubar.actions() if a.data() == top_name), None)
        if act is not None and act.menu() is not None and (self.menu_items[idx]["level"] > 0 or idx != top):
            act.menu().popup(self.menubar.mapToGlobal(self.menubar.actionGeometry(act).bottomLeft()))

    def _menu_filter(self, menu):
        from PySide6.QtCore import QEvent, QObject
        view = self

        class F(QObject):
            def eventFilter(self, obj, ev):
                if ev.type() == QEvent.MouseButtonPress:
                    act = menu.actionAt(ev.position().toPoint())
                    if act is not None and act.data():
                        if ev.button() == Qt.RightButton:
                            view.select(f"menu:{act.data()}", user=True)
                            menu.setActiveAction(act)          # stays open; the item menu pops up over it
                            view.emit("OnMenuContextMenu", {"selected_control": f"menu:{act.data()}"})
                            return True
                        if act.menu() is not None or act.isSeparator():   # submenu parents and separators: select them too
                            view.select(f"menu:{act.data()}", user=True)
                            menu.close()
                            return True
                return False
        f = F(menu)
        self._menu_filters.append(f)
        return f

    def set_form_size(self, w, h):
        mh = self.menu_h()
        self.form.move(PAGE_MARGIN, PAGE_MARGIN + TITLE_H + mh)
        self.form.resize(int(w), int(h))
        self.menubar.setGeometry(PAGE_MARGIN, PAGE_MARGIN + TITLE_H, int(w), mh)
        self.page.resize(int(w) + 2 * PAGE_MARGIN + 40, int(h) + 2 * PAGE_MARGIN + TITLE_H + mh + 40)
        self.overlay.setGeometry(self.page.rect())
        self.overlay.raise_()
        self.overlay.update()

    def set_form_bg(self, value):
        """The form's background (None: leave it as it is), and its edge, in its own colour if it has one."""
        if value is not None or not hasattr(self, "form_bg"):
            self.form_bg = colour(value or "#ffffff")
        edge = colour(self.node.props.get("FormBorder") or "#9ca3af")
        self.form.setStyleSheet(f"#DesignForm {{ background: {self.form_bg}; border: 1px solid {edge}; }}")

    def commit(self, node, g, resized=False):
        e = self.engine
        kids = [(k, k.host.geometry(), k.widget.size()) for k in node.children] if resized and node.type.name == "Frame" else []
        e.cmd_SetProperty(node.name, "Canvas.Left", str(g.x()))
        e.cmd_SetProperty(node.name, "Canvas.Top", str(g.y()))
        if resized:
            e.cmd_SetProperty(node.name, "Width", str(g.width()))
            e.cmd_SetProperty(node.name, "Height", str(g.height()))
        for k, kg, ks in kids:                               # keep where the frame's anchors put them
            if anchor_set(k.props.get("Anchor")) == {"Top", "Left"}:
                continue
            e.cmd_SetProperty(k.name, "Canvas.Left", str(kg.x()))
            e.cmd_SetProperty(k.name, "Canvas.Top", str(kg.y()))
            e.cmd_SetProperty(k.name, "Width", str(ks.width()))
            e.cmd_SetProperty(k.name, "Height", str(ks.height()))
        self.overlay.update()
        self.emit("OnChanged", {"selected_control": node.name})

    def commit_form(self):
        e = self.engine
        e.cmd_SetProperty(self.node.name, "FormWidth", str(self.form.width()))
        e.cmd_SetProperty(self.node.name, "FormHeight", str(self.form.height()))
        for node in self.node.children:
            a = anchor_set(node.props.get("Anchor"))
            if a == {"Top", "Left"}:
                continue
            kids = [(k, k.host.geometry(), k.widget.size()) for k in node.children] if node.type.name == "Frame" else []
            g = node.host.geometry()
            e.cmd_SetProperty(node.name, "Canvas.Left", str(g.x()))
            e.cmd_SetProperty(node.name, "Canvas.Top", str(g.y()))
            if ("Left" in a and "Right" in a) or ("Top" in a and "Bottom" in a):
                e.cmd_SetProperty(node.name, "Width", str(node.widget.width()))
                e.cmd_SetProperty(node.name, "Height", str(node.widget.height()))
            for k, kg, ks in kids:                           # a stretched frame keeps its contents where its anchors put them
                if anchor_set(k.props.get("Anchor")) == {"Top", "Left"}:
                    continue
                e.cmd_SetProperty(k.name, "Canvas.Left", str(kg.x()))
                e.cmd_SetProperty(k.name, "Canvas.Top", str(kg.y()))
                e.cmd_SetProperty(k.name, "Width", str(ks.width()))
                e.cmd_SetProperty(k.name, "Height", str(ks.height()))
        self.overlay.update()
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


def set_snap(node, v):
    node.widget.snap_on = truthy(v) if v not in (None, "") else True


def set_show_grid(node, v):
    node.widget.show_grid = truthy(v) if v not in (None, "") else True
    node.widget.overlay.update()


register(ControlType("DesignSurface", make_surface, container=True, add_child=surface_add, place_child=surface_place,
                     remove_child=surface_remove, category="Design",
                     events={e: surface_event(e) for e in ("OnSelectionChanged", "OnContextMenu", "OnChanged", "OnDoubleClick",
                                                           "OnGeometry", "OnMenuBarClick", "OnMenuContextMenu")}),
         [p for p in COMMON if p.name in ("Margin", "IsVisible", "Width", "Height", "HorizontalAlignment", "VerticalAlignment")],
         [Prop("FormName", "text", "Form", default="Form1"),
          Prop("FormTitle", "text", "Form", default="Form1", apply=lambda n, v: n.widget.overlay.update()),
          Prop("FormWidth", "number", "Form", default="640",
               apply=lambda n, v: n.widget.set_form_size(num(v, 640), n.widget.form.height()),
               read=lambda n: n.widget.form.width()),
          Prop("FormHeight", "number", "Form", default="480",
               apply=lambda n, v: n.widget.set_form_size(n.widget.form.width(), num(v, 480)),
               read=lambda n: n.widget.form.height()),
          Prop("FormBackground", "colour", "Form", default="#ffffff", apply=lambda n, v: n.widget.set_form_bg(v)),
          Prop("FormBorder", "colour", "Form", apply=lambda n, v: n.widget.set_form_bg(None)),    # an edge round the window
          Prop("FormResizable", "bool", "Form", default="true", apply=lambda n, v: n.widget.overlay.update()),
          Prop("FormModal", "bool", "Form", default="false"),
          Prop("FormMinWidth", "number", "Form"), Prop("FormMinHeight", "number", "Form"),
          Prop("FormMaxWidth", "number", "Form"), Prop("FormMaxHeight", "number", "Form"),
          Prop("GridSize", "number", "Behaviour", default="8", apply=set_grid),
          Prop("ShowGrid", "bool", "Behaviour", default="true", apply=set_show_grid),
          Prop("SnapToGrid", "bool", "Behaviour", default="true", apply=set_snap),
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
        if self.target.startswith("menu:"):
            self.rebuild_menu_item(body, lay)
            return
        if self.target == "menubar":
            head = QLabel("<b>Menu</b>  <span style='color:#6b7280'>the form's menu bar</span>")
            head.setStyleSheet("font-size: 13px; padding: 2px 0 6px 0;")
            lay.addWidget(head)
            title = QLabel("MENU BAR")
            title.setStyleSheet("color: #2563eb; font-size: 10px; font-weight: 700; padding: 8px 0 2px 0;")
            lay.addWidget(title)
            for p in json.loads(self.engine.cmd_GetControlPropertiesJson("menubar")):
                lay.addLayout(self.row_layout(p["name"], self.editor(p)))
            lay.addStretch(1)
            self.setWidget(body)
            return
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
        on_canvas = target.parent is not None and target.parent.type.name in ("DesignSurface", "Canvas")
        groups = {}
        for p in props:
            if p["name"] in HIDDEN_IN_GRID or (design_form and p["group"] != "Form"):
                continue
            if on_canvas and p["name"] in CANVAS_HIDDEN:
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
            rows = groups[g]
            if g == "Placement":
                rows = sorted(rows, key=lambda p: PLACEMENT_ORDER.get(p["name"], 9))
            for p in rows:
                label = CANVAS_LABELS.get(p["name"], p["name"]) if on_canvas else p["name"]
                lay.addLayout(self.row_layout(label, self.editor(p)))
        lay.addStretch(1)
        self.setWidget(body)

    def rebuild_menu_item(self, body, lay):
        """A menu item on the design surface: its caption, shortcut, enabled and separator, and its script."""
        head = QLabel(f"<b>MenuItem</b>  <span style='color:#6b7280'>{self.target[5:]}</span>")
        head.setStyleSheet("font-size: 13px; padding: 2px 0 6px 0;")
        lay.addWidget(head)
        lay.addLayout(self.row_layout("Name", self.name_editor(self.target[5:])))
        title = QLabel("COMMON")
        title.setStyleSheet("color: #2563eb; font-size: 10px; font-weight: 700; padding: 8px 0 2px 0;")
        lay.addWidget(title)
        for p in json.loads(self.engine.cmd_GetControlPropertiesJson(self.target)):
            lay.addLayout(self.row_layout(p["name"], self.editor(p)))
        title = QLabel("EVENTS")
        title.setStyleSheet("color: #2563eb; font-size: 10px; font-weight: 700; padding: 8px 0 2px 0;")
        lay.addWidget(title)
        handler = QLineEdit(self.engine.cmd_GetProperty(self.target, "OnClick"))
        handler.setReadOnly(True)
        handler.setPlaceholderText("double-click the item, or right-click > Edit Script")
        handler.setStyleSheet("font-size: 11px; color: #4b5563;")
        self.editors["OnClick"] = handler
        lay.addLayout(self.row_layout("OnClick", handler))
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
        is_menu = self.target.startswith("menu:")
        current = self.target[5:] if is_menu else self.target
        if new and new != current:
            if self.engine.cmd_RenameControl(self.target, new):
                self.target = ("menu:" + new) if is_menu else new
                self.node.props["Target"] = self.target
            ed.setText(self.target[5:] if self.target.startswith("menu:") else self.target)

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
        if self.target.startswith("menu:") or self.target == "menubar":
            if str(self.engine.cmd_GetProperty(self.target, prop)) != str(value):
                self.engine.cmd_SetProperty(self.target, prop, value)
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
    "RadioButton": {"Content": "RadioButton"},
    "Image": {"Width": "120", "Height": "90"},
    "DataGrid": {"Columns": "Name,Value", "Width": "300", "Height": "160"},
    "TreeView": {"Items": "Parent/Child One,Parent/Child Two,Other", "Width": "180", "Height": "160"},
    "ComboBox": {"Items": "One,Two,Three", "SelectedIndex": "0", "Width": "140"},
    "ListBox": {"Items": "One,Two,Three", "Width": "140", "Height": "100"},
    "Border": {"Width": "200", "Height": "120", "Background": "#F3F4F6", "BorderBrush": "#9CA3AF",
               "BorderThickness": "1", "CornerRadius": "6"},
    "StackPanel": {"Width": "200", "Height": "120", "Background": "#F9FAFB"},
    "Grid": {"Width": "200", "Height": "120", "Background": "#F9FAFB"},
    "DockPanel": {"Width": "200", "Height": "120", "Background": "#F9FAFB"},
    "Rectangle": {"Width": "120", "Height": "80", "Fill": "#BFDBFE", "Stroke": "#2563EB", "StrokeThickness": "1"},
    "ScrollViewer": {"Width": "200", "Height": "120"},
    "Frame": {"Width": "240", "Height": "160"},
}
