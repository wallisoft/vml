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
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QListWidget, QListWidgetItem, QMessageBox, QPushButton, QCheckBox, QColorDialog, QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QMenu, QMenuBar,
                               QScrollArea, QSizePolicy, QSlider, QSpinBox, QToolButton, QVBoxLayout, QWidget)

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
                if node.type.name in ("Frame", "Canvas", "TabPage"):    # a page or a frame: what's inside it first
                    return self.hit(pos, node) or node
                if node.type.name == "TabStrip":                    # the page showing, then the strip (its tabs)
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
        if node is not None and node.type.name == "TabStrip" and e.button() == Qt.LeftButton:
            tab = node.widget.tab_at(node.widget.mapFrom(v.page, pos))
            if tab >= 0:                                         # a tab: show its page, to design on
                node.widget.select(tab)
                v.engine.cmd_SetProperty(node.name, "SelectedIndex", str(tab))
                page = node.widget.pages()[tab]
                v.select(page.name, user=True)
                self.update()
                return
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
        self.page.setStyleSheet("#DesignPage { background: #d4d7dd; }")
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
        pal.setColor(vp.backgroundRole(), QColor("#d4d7dd"))
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
        """The deepest Frame or Canvas under a point, ignoring exclude and everything inside it; None means the form."""
        found, container = None, self.node
        while True:
            nxt = None
            for n in reversed(container.children):
                if n is exclude or n.type.name not in ("Frame", "Canvas", "TabStrip", "TabPage") or not n.host.isVisible():
                    continue
                if self.overlay.rect_of(n).contains(page_pos):
                    nxt = n
                    break
            if nxt is None:
                return found
            if nxt.type.name == "TabStrip":                 # (a strip itself holds only pages: look in the one showing)
                container = nxt
                continue
            found = container = nxt

    def select(self, name, user=False):
        name = name or ""
        changed = name != self.selected
        self.selected = name
        self.bring_forward(self.selected_node())
        self.overlay.update()
        if changed and user:
            self.emit("OnSelectionChanged", {"selected_control": name})

    # layers: pages (canvases or frames) stacked in one place, as a form whose script switches pages has them.
    # Only one of each stack is shown while designing (the one that starts visible, unless another is chosen), so
    # they don't draw over each other; the bar beside the form switches between them. Nothing here is saved.
    def layer_groups(self):
        groups = []

        def overlap(a, b):
            ra, rb = a.host.geometry(), b.host.geometry()
            both = ra.intersected(rb)
            small = min(ra.width() * ra.height(), rb.width() * rb.height())
            return small > 0 and both.width() * both.height() >= small / 2

        def visit(container):
            pages = [k for k in container.children if k.type.name in ("Canvas", "Frame")]
            taken = set()
            for i, a in enumerate(pages):
                if a.name in taken:
                    continue
                group = [a] + [b for b in pages[i + 1:] if b.name not in taken and overlap(a, b)]
                taken.update(n.name for n in group)
                if len(group) > 1:
                    groups.append(group)
            for k in container.children:
                if k.type.container:
                    visit(k)
        visit(self.node)
        return groups

    def arrange_layers(self, fresh=False):
        """Show the front page of each stack and hide the others ("" shows them all, those starting hidden faded)."""
        from .registry import set_visible
        if getattr(self, "_arranging", False):
            return
        self._arranging = True
        try:
            fronts = {} if fresh else getattr(self, "layer_front", {})
            self.layer_front, self.layers_now = {}, self.layer_groups()
            for group in self.layers_now:
                key = tuple(n.name for n in group)
                front = next((v for k, v in fronts.items() if set(k) & set(key) and (v == "" or v in key)), None)
                if front is None:
                    front = next((n.name for n in group if str(n.props.get("IsVisible", "true")).lower() != "false"), group[0].name)
                self.layer_front[key] = front
                for n in group:
                    if front == "":
                        set_visible(n, n.props.get("IsVisible"))
                    else:
                        n.host.setVisible(n.name == front)
                        if n.name == front:
                            n.host.setGraphicsEffect(None)
            self.layer_bar()
        finally:
            self._arranging = False
        self.overlay.update()

    def show_layer(self, key, name):
        self.layer_front[key] = name
        self.arrange_layers()

    def bring_forward(self, node):
        """A control chosen in a page that's hidden behind another: bring its page (and any page it's in) forward."""
        changed = False
        while node is not None:
            for key, front in getattr(self, "layer_front", {}).items():
                if node.name in key and front not in ("", node.name):
                    self.layer_front[key] = node.name
                    changed = True
            node = node.parent
        if changed:
            self.arrange_layers()

    def layer_bar(self):
        """The switch beside the form: one button per page of each stack, and All."""
        from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout
        old = getattr(self, "bar", None)
        if old is not None:
            old.deleteLater()
            self.bar = None
        if not self.layers_now:
            self.set_page_size()
            return
        bar = QWidget(self.page)
        bar.setObjectName("LayerBar")
        bar.setStyleSheet("#LayerBar { background: #ffffff; border: 1px solid #cbd5e1; border-radius: 6px; }"
                          "QPushButton { text-align: left; padding: 3px 8px; border: 1px solid transparent; border-radius: 4px; background: transparent; }"
                          "QPushButton:checked { background: #dbeafe; border-color: #93c5fd; }"
                          "QPushButton:hover { border-color: #cbd5e1; }")
        lay = QVBoxLayout(bar)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(2)
        for key in [tuple(n.name for n in g) for g in self.layers_now]:
            title = QLabel("Pages")
            title.setStyleSheet("color: #6b7280; font-size: 11px; padding: 2px 4px;")
            lay.addWidget(title)
            for name in list(key) + [""]:
                b = QPushButton(name or "All, faded")
                b.setCheckable(True)
                b.setChecked(self.layer_front.get(key) == name)
                b.clicked.connect(lambda _=False, k=key, n=name: self.show_layer(k, n))
                lay.addWidget(b)
        bar.adjustSize()
        bar.move(self.form.x() + self.form.width() + 16, self.form.y())
        bar.show()
        self.bar = bar
        self.set_page_size()

    def set_page_size(self):
        """The work area: room for the form (and the layer bar beside it when there is one), and never smaller than
        the view, so the whole pane is one grey desk with the form sitting on it. A big form (up to 4K and beyond)
        makes it scroll, as an image bigger than the window does in GIMP."""
        w = self.form.x() + self.form.width() + PAGE_MARGIN + 40
        bar = getattr(self, "bar", None)
        if bar is not None:
            w = max(w, bar.x() + bar.width() + PAGE_MARGIN)
        h = self.form.y() + self.form.height() + PAGE_MARGIN + 40
        vp = self.viewport().size()
        self.page.resize(max(w, vp.width()), max(h, vp.height()))
        self.overlay.setGeometry(self.page.rect())
        self.overlay.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.set_page_size()

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
        if getattr(self, "bar", None) is not None:
            self.bar.move(self.form.x() + self.form.width() + 16, self.form.y())
        self.set_page_size()
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
        if node.type.name in ("Canvas", "Frame"):
            self.arrange_layers()
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
          # about the app the form is: kept in its @Window, used when it goes to the web, a phone or an Android app
          Prop("FormVersion", "text", "App"), Prop("FormIcon", "text", "App"), Prop("FormWebAddress", "text", "App"),
          Prop("FormPhoneFit", "choice", "App", options=("", "Fit", "None")),
          Prop("FormWebFit", "choice", "App", options=("", "Window", "Fill")),
          Prop("FormAndroidPackage", "text", "App"), Prop("FormAndroidKey", "text", "App"),
          Prop("GridSize", "number", "Behaviour", default="8", apply=set_grid),
          Prop("ShowGrid", "bool", "Behaviour", default="true", apply=set_show_grid),
          Prop("SnapToGrid", "bool", "Behaviour", default="true", apply=set_snap),
          Prop("Selected", "text", "Behaviour", apply=lambda n, v: n.widget.select(str(v or "")),
               read=lambda n: n.widget.selected)])
REGISTRY["DesignSurface"].design_only = True


# ====================================================================== PropertyGrid

class TabsBox(QDialog):
    """Edit Tabs: a strip's tabs in order. Add, rename (double-click, or Rename), delete, move up and down."""

    def __init__(self, parent, tabs):
        super().__init__(parent)
        self.setWindowTitle("Edit Tabs")
        self.setMinimumWidth(360)
        lay = QVBoxLayout(self)
        tip = QLabel("The tabs, in order. Double-click one to rename it.")
        tip.setStyleSheet("color: #6b7280; font-size: 11px;")
        lay.addWidget(tip)
        row = QHBoxLayout()
        self.list = QListWidget()
        for page, header, count in tabs:
            self.add_item(header, page, count)
        self.list.itemDoubleClicked.connect(self.list.editItem)
        row.addWidget(self.list, 1)
        side = QVBoxLayout()
        for text, fn in (("Add", self.add), ("Rename", self.rename), ("Delete", self.remove), ("Move Up", lambda: self.move(-1)),
                         ("Move Down", lambda: self.move(1))):
            b = QPushButton(text)
            b.clicked.connect(fn)
            side.addWidget(b)
        side.addStretch(1)
        row.addLayout(side)
        lay.addLayout(row)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)
        if self.list.count():
            self.list.setCurrentRow(0)

    def add_item(self, header, page="", count=0):
        item = QListWidgetItem(header)
        item.setData(Qt.UserRole, page)
        item.setData(Qt.UserRole + 1, count)
        item.setFlags(item.flags() | Qt.ItemIsEditable)
        self.list.addItem(item)
        return item

    def add(self):
        item = self.add_item(f"Tab {self.list.count() + 1}")
        self.list.setCurrentItem(item)
        self.list.editItem(item)

    def rename(self):
        if self.list.currentItem() is not None:
            self.list.editItem(self.list.currentItem())

    def remove(self):
        item = self.list.currentItem()
        if item is None:
            return
        count = int(item.data(Qt.UserRole + 1) or 0)
        if count and QMessageBox.question(self, "Delete a tab", f"'{item.text()}' has {count} control{'s' if count != 1 else ''} "
                                          "on its page. Delete the tab and everything on it?") != QMessageBox.Yes:
            return
        self.list.takeItem(self.list.row(item))

    def move(self, step):
        row = self.list.currentRow()
        if row < 0 or not 0 <= row + step < self.list.count():
            return
        item = self.list.takeItem(row)
        self.list.insertItem(row + step, item)
        self.list.setCurrentRow(row + step)

    def result_tabs(self):
        return [{"page": self.list.item(i).data(Qt.UserRole) or "", "header": self.list.item(i).text().strip()}
                for i in range(self.list.count())]


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
        from . import dialogs
        c = dialogs.choose_colour(self.window(), start.name(), "Choose a colour", "#1E3A8A")
        if c.isValid():
            self.edit.setText(c.name().upper())
            self.edit.editingFinished.emit()


def shrinkable(editor):
    """Let a property's editor be as narrow as the pane: a choice list otherwise insists on the width of its longest
    option, and with bigger fonts that pushes the whole grid past the right-hand edge of the window."""
    for w in [editor] + editor.findChildren(QWidget):
        if isinstance(w, QComboBox):
            w.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
            w.setMinimumContentsLength(4)
        if isinstance(w, (QComboBox, QLineEdit)):
            w.setMinimumWidth(40)
            w.setSizePolicy(QSizePolicy.Ignored, w.sizePolicy().verticalPolicy())
    editor.setSizePolicy(QSizePolicy.Ignored, editor.sizePolicy().verticalPolicy())


# The Style box's ready-made looks: plain CSS (vml/styles.py), the same on the desktop and the web. Each replaces
# whatever Style the control had; Background, Shadow and the rest still apply underneath.
STYLE_PRESETS = (
    ("Card", "background: #FFFFFF; color: #111827; border: 1px solid #E5E7EB; border-radius: 14px;"
             " box-shadow: 0 6px 20px rgba(17,24,39,0.12); :hover { border: 1px solid #C7D2FE }"),
    ("Primary", "background: linear-gradient(135deg, #6366F1, #4F46E5); color: #FFFFFF; border: none; border-radius: 10px;"
                " font-weight: 600; box-shadow: 0 6px 16px rgba(79,70,229,0.40); :hover { background: #4338CA } :pressed { background: #3730A3 }"),
    ("3D raised", "background: #6366F1; color: #FFFFFF; border: none; border-bottom: 5px solid #3730A3; border-radius: 12px;"
                  " font-weight: 700; :hover { background: #818CF8 } :pressed { border-bottom: 1px solid #3730A3 }"),
    ("Outline", "background: transparent; color: #4F46E5; border: 2px solid #4F46E5; border-radius: 10px; font-weight: 600;"
                " :hover { background: #EEF2FF }"),
    ("Ghost", "background: transparent; color: #4F46E5; border: none; border-radius: 10px; font-weight: 600;"
              " :hover { background: #EEF2FF }"),
    ("Link", "background: transparent; color: #2563EB; border: none; text-decoration: underline; :hover { color: #1E40AF }"),
    ("Pill", "background: #111827; color: #FFFFFF; border: none; border-radius: 22px; padding: 4px 22px; font-weight: 600;"
             " :hover { background: #374151 }"),
    ("Glass", "background: rgba(255,255,255,0.55); color: #111827; border: 1px solid rgba(255,255,255,0.9); border-radius: 16px;"
              " box-shadow: 0 8px 24px rgba(31,41,55,0.15); :hover { background: rgba(255,255,255,0.8) }"),
    ("Neon", "background: #0F172A; color: #A5F3FC; border: 1px solid #22D3EE; border-radius: 10px; font-weight: 600;"
             " box-shadow: 0 0 18px rgba(34,211,238,0.65); :hover { background: #1E293B }"),
    ("Brutalist", "background: #FDE047; color: #111827; border: 2px solid #111827; border-radius: 0px; font-weight: 800;"
                  " box-shadow: 5px 5px 0 #111827; :pressed { background: #FACC15 }"),
    ("Sunset", "background: linear-gradient(135deg, #F59E0B, #EC4899); color: #FFFFFF; border: none; border-radius: 12px;"
               " font-weight: 600; box-shadow: 0 6px 16px rgba(236,72,153,0.35)"),
    ("Ocean", "background: linear-gradient(135deg, #06B6D4, #3B82F6); color: #FFFFFF; border: none; border-radius: 12px;"
              " font-weight: 600; box-shadow: 0 6px 16px rgba(59,130,246,0.35)"),
    ("Danger", "background: #DC2626; color: #FFFFFF; border: none; border-radius: 10px; font-weight: 600; :hover { background: #B91C1C }"),
    ("Input field", "background: #FFFFFF; border: 2px solid #DDD6FE; border-radius: 12px; padding: 0 10px;"
                    " :focus { border: 2px solid #6366F1 }"),
    ("Note", "background: #FEF3C7; color: #78350F; border: 1px solid #FDE68A; border-left: 5px solid #F59E0B; border-radius: 8px;"
             " padding: 4px 10px"),
    ("(none)", ""),
)


class StyleEditor(QWidget):
    """The Style property: the look's name (a ready-made one, kept as a /* comment */ at the front of the CSS, so it
    survives saving and editing) with a ▾ for the ready-made looks, and the CSS below it, a declaration a line, to edit."""

    def __init__(self, grid, value):
        super().__init__()
        self.grid = grid
        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(3)
        top = QHBoxLayout()
        top.setSpacing(4)
        self.name = QLabel()
        self.name.setStyleSheet("font-size: 11px; font-weight: 600; color: #374151; padding: 2px 4px;"
                                " background: #EEF2FF; border: 1px solid #C7D2FE; border-radius: 4px;")
        top.addWidget(self.name, 1)
        pick = QToolButton()
        pick.setText("\u25be")
        pick.setFixedSize(20, 20)
        pick.setToolTip("Ready-made looks")
        pick.setStyleSheet("QToolButton { border: 1px solid #9ca3af; border-radius: 3px; background: #fff; }")
        pick.clicked.connect(lambda: grid.pick_style("Style", self, pick))
        top.addWidget(pick)
        col.addLayout(top)
        from PySide6.QtWidgets import QPlainTextEdit
        self.css = QPlainTextEdit()
        self.css.setPlaceholderText("CSS: background: #fff; border-radius: 12px; :hover { ... }")
        self.css.setStyleSheet("font-family: monospace; font-size: 11px;")
        self.css.setFixedHeight(84)
        self.css.installEventFilter(self)
        col.addWidget(self.css)
        self.setText(value)

    @staticmethod
    def split(value):
        import re
        m = re.match(r"\s*/\*\s*(.*?)\s*\*/\s*(.*)$", str(value or ""), re.S)
        return (m.group(1), m.group(2)) if m else ("", str(value or "").strip())

    def setText(self, value):
        self.value = str(value or "")
        label, css = self.split(self.value)
        self.name.setText(label or ("Custom" if css else "(none)"))
        shown = css.replace("; ", ";\n").replace(" :", "\n:")
        if self.css.toPlainText() != shown:
            self.css.setPlainText(shown)

    def text(self):
        return self.value

    def hasFocus(self):
        return self.css.hasFocus()

    def eventFilter(self, obj, e):
        from PySide6.QtCore import QEvent
        if obj is self.css and e.type() == QEvent.FocusOut:
            self.commit()
        elif obj is self.css and e.type() == QEvent.KeyPress and e.key() in (Qt.Key_Return, Qt.Key_Enter) \
                and e.modifiers() & Qt.ControlModifier:
            self.commit()
            return True
        return False

    def commit(self):
        css = " ".join(line.strip() for line in self.css.toPlainText().splitlines() if line.strip())
        label, before = self.split(self.value)
        value = (f"/* {label} */ {css}" if label and css else css)
        if value != self.value:
            self.value = value
            self.grid.commit("Style", value)


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
        head.setWordWrap(True)                                   # (a long name wraps rather than widening the grid)
        lay.addWidget(head)
        if not design_form:
            lay.addLayout(self.row_layout("Name", self.name_editor(target.name)))
        strip = target if target.type.name == "TabStrip" else target.parent if target.type.name == "TabPage" else None
        if strip is not None:                                    # a tab strip (or one of its pages): its tabs, in one place
            tabs = QPushButton(f"Edit Tabs...   ({len(strip.widget.pages())})")
            tabs.setStyleSheet("font-size: 11px; padding: 4px 10px;")
            tabs.clicked.connect(lambda _=False, s=strip.name: self.edit_tabs(s))
            lay.addLayout(self.row_layout("Tabs", tabs))
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

    def edit_tabs(self, strip_name):
        strip = self.engine.find(strip_name)
        if strip is None:
            return
        box = TabsBox(self.window(), [(p.name, str(p.props.get("Header") or p.name), len(p.children)) for p in strip.widget.pages()])
        if box.exec():
            self.engine.cmd_SetTabs(strip_name, json.dumps(box.result_tabs()))
            self.rebuild()

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
        shrinkable(editor)
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
        elif kind == "slider":
            low, high = (int(num(x)) for x in (list(p.get("options") or []) + ["0", "100"])[:2])
            start = int(num(value, high if name == "Opacity" else low))
            box = QWidget()
            h = QHBoxLayout(box)
            h.setContentsMargins(0, 0, 0, 0)
            h.setSpacing(6)
            bar = QSlider(Qt.Horizontal)
            bar.setRange(low, high)
            bar.setValue(start)
            spin = QSpinBox()
            spin.setRange(low, high)
            spin.setValue(start)
            spin.setFixedWidth(52)
            bar.valueChanged.connect(spin.setValue)
            spin.valueChanged.connect(bar.setValue)
            spin.valueChanged.connect(lambda v, n=name: self.commit(n, str(v)))   # (live: the control changes as it slides)
            h.addWidget(bar, 1)
            h.addWidget(spin)
            ed, widget = spin, box
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
            elif name == "Style":
                ed = StyleEditor(self, value)
                widget = ed
            elif name == "Class":
                box = QWidget()
                h = QHBoxLayout(box)
                h.setContentsMargins(0, 0, 0, 0)
                h.setSpacing(4)
                h.addWidget(ed, 1)
                pick = QToolButton()
                pick.setText("\u25be")
                pick.setFixedSize(20, 20)
                pick.setToolTip("This form's shared styles (@Style)")
                pick.setStyleSheet("QToolButton { border: 1px solid #9ca3af; border-radius: 3px; background: #fff; }")
                pick.clicked.connect(lambda _=False, n=name, e=ed, b=pick: self.pick_style(n, e, b))
                h.addWidget(pick)
                widget = box
        widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.editors[name] = ed
        return widget

    def pick_style(self, prop, ed, button):
        """Style: a menu of ready-made looks (each replaces the Style). Class: the form's @Style names, ticked on and off."""
        menu = QMenu(button)
        if prop == "Style":
            for label, css in STYLE_PRESETS:
                act = menu.addAction(label)
                act.setToolTip(css)
                value = f"/* {label} */ {css}" if css else ""
                act.triggered.connect(lambda _=False, v=value: (ed.setText(v), self.commit("Style", v)))
        else:
            have = [c for c in str(ed.text()).replace(",", " ").split() if c]
            names = sorted(getattr(self.engine, "styles", {}) or {})
            if not names:
                none = menu.addAction("No shared styles in this form yet (@Style blocks)")
                none.setEnabled(False)
            for n in names:
                act = menu.addAction(n)
                act.setCheckable(True)
                act.setChecked(n in have)

                def toggle(on, n=n):
                    now = [c for c in str(ed.text()).replace(",", " ").split() if c and c != n] + ([n] if on else [])
                    ed.setText(" ".join(now))
                    self.commit("Class", " ".join(now))
                act.toggled.connect(toggle)
        menu.exec(button.mapToGlobal(button.rect().bottomLeft()))

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
            elif isinstance(ed, QSpinBox):
                ed.setValue(int(num(value, ed.maximum() if prop == "Opacity" else ed.minimum())))
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
    "Timer": {"Interval": "1000"},
    "ProgressBar": {"Width": "200", "Height": "18", "Value": "40"},
    "Slider": {"Width": "200", "Height": "28", "Value": "40"},
    "ColorPicker": {"Width": "140", "Height": "28"},
    "DatePicker": {"Width": "150", "Height": "28"},
    "TimePicker": {"Width": "110", "Height": "28"},
    "NumberBox": {"Width": "110", "Height": "28"},
    "ToggleSwitch": {"Content": "Switch", "Width": "160", "Height": "28"},
    "Calendar": {"Width": "280", "Height": "200"},
    "AutoCompleteBox": {"Items": "One,Two,Three", "Width": "180", "Height": "28"},
    "HyperlinkButton": {"Content": "A link", "Width": "120", "Height": "24"},
    "ToggleButton": {"Content": "Toggle", "Width": "100", "Height": "30"},
    "MarkdownView": {"Text": "Some **Markdown**, shown as a page.", "Width": "300", "Height": "200"},
    "MarkdownEditor": {"Width": "460", "Height": "240"},
    "StatusBar": {"Panels": "Ready|{date}|{time}", "Height": "26", "Background": "#F3F4F6", "Anchor": "Bottom,Left,Right"},
    "Toolbar": {"Items": "📄 New, 📂 Open, 💾 Save", "Height": "34", "Background": "#F9FAFB", "Anchor": "Top,Left,Right"},
    "TabStrip": {"Width": "320", "Height": "220", "BorderThickness": "2", "BorderBrush": "#CBD5E1", "CornerRadius": "6"},
}
