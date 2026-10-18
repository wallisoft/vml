"""
The VML engine.

  Store (SQLite) -> Nodes (one per control: Qt widget + a host for margins) -> windows on screen.
  Scripts talk to all of it through one function, Vml("Command", args...), exactly as in the
  Avalonia engine, so existing Lua scripts run unchanged.

  Each opened form is a *scope*: two forms may both have a "MainGrid", and a script finds the one
  in its own form first.
"""
import json
from html import unescape as html_unescape
import os
import re
import shutil
import subprocess
import threading
import sys
import tempfile
import time
from pathlib import Path

from lupa import lua54
from PySide6.QtCore import QEventLoop, QRect, Qt, QTimer, QUrl
from PySide6.QtGui import QCursor, QDesktopServices
from PySide6.QtWidgets import QApplication, QFileDialog, QLabel, QVBoxLayout, QWidget

from .registry import (REGISTRY, ControlType, box_add, box_place, css_id, layout_remove, make_box, theme_sheets,
                       truthy)
from .design import DESIGN_DEFAULTS  # importing design also registers DesignSurface and PropertyGrid
from . import statusbar  # noqa: F401  (registers StatusBar)
from . import tabs  # noqa: F401  (registers TabStrip, TabPage, Toolbar)
from . import pickers  # noqa: F401  (registers ColorPicker, DatePicker, TimePicker, NumberBox, ToggleSwitch)
from . import mdview  # noqa: F401  (registers MarkdownView, MarkdownEditor)
from . import codeedit  # noqa: F401  (registers CodeEditor)
from .store import LUA_DIR, PARSER_LOG, Store
from .data import DataCommands
from .projects import ProjectCommands
from .library import LibraryCommands
from .systemcommands import SystemCommands
from .stepping import SteppingCommands
from . import dialogs, licence as licences


def _alive(widget):
    """Whether a window of ours is still there (Qt may have deleted it once it closed)."""
    try:
        return widget.isVisible()
    except RuntimeError:
        return False

# Every Python script starts with this: Vml() talks straight to the engine over its local socket.
PYTHON_PRELUDE = """import sys, os, json, socket
def Vml(command, *a):
    host, port = os.environ["VML_API"].rsplit(":", 1)
    with socket.create_connection((host, int(port)), timeout=30) as s:
        s.sendall((json.dumps({"token": os.environ["VML_TOKEN"], "cmd": command, "args": [str(x) for x in a]}) + "\\n").encode())
        data = b""
        while not data.endswith(b"\\n"):
            chunk = s.recv(65536)
            if not chunk:
                break
            data += chunk
    reply = json.loads(data or b"{}")
    if not reply.get("ok"):
        raise RuntimeError(reply.get("error", "no reply"))
    return reply.get("value")
args = sys.argv[2:]
"""     # every Python script starts with this; argv[1] is the script name
FROZEN = "__compiled__" in globals()      # running as a compiled (Nuitka) binary

PLACEHOLDER = ControlType("Placeholder", make_box, container=True, add_child=box_add, place_child=box_place,
                          remove_child=layout_remove)
SYSTEM_DIR = Path.home() / ".vml" / "system"


def log(msg):
    print(f"[vml {time.strftime('%H:%M:%S')}] {msg}", file=sys.stderr, flush=True)


class Node:
    def __init__(self, ctype, name, cid, props, scope):
        self.type, self.name, self.cid, self.scope = ctype, name, cid, scope
        self.props = dict(props)
        self.style, self.children, self.keep, self.hooked = {}, [], [], set()
        self.parent = self.widget = self.host = None
        self.maps = {}             # composites: property -> (inner node name, inner property)
        self.inner = []            # composites: the template's inner nodes

    def __repr__(self):
        return f"<{self.type.name} {self.name}>"


class Template:
    def __init__(self, name, rows, props):
        self.name = name
        self.parts, self.maps = [], {}
        ids = {}
        for cid, parent_id, ctype, cname in rows:
            p = props.get(cid, {})
            if ctype == "ControlTemplate":
                continue
            if ctype == "PropertyMap":
                self.maps[cname] = (p.get("TargetControl", ""), p.get("TargetProperty", cname))
                continue
            ids[cid] = cname
            self.parts.append((cname, ctype, ids.get(parent_id), p))
        self.root = self.parts[0][0] if self.parts else None


# Scrollbars as they are drawn now: thin, rounded, no arrows, on a clear track, darker under the pointer.
SCROLLBARS = """
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px 2px 2px 0; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 0 2px 2px 2px; }
QScrollBar::handle:vertical { background: rgba(60, 70, 80, 0.28); border-radius: 3px; min-height: 28px; margin: 0 2px; }
QScrollBar::handle:horizontal { background: rgba(60, 70, 80, 0.28); border-radius: 3px; min-width: 28px; margin: 2px 0; }
QScrollBar::handle:hover, QScrollBar::handle:pressed { background: rgba(60, 70, 80, 0.5); }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; border: none; background: none; }
QScrollBar::add-page, QScrollBar::sub-page { background: none; }
"""


class Engine(DataCommands, ProjectCommands, LibraryCommands, SystemCommands, SteppingCommands):
    log_line = staticmethod(log)

    def __init__(self, db_path=None, lua_paths=()):
        self.app = QApplication.instance() or QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(True)
        # one look on every desktop: Qt's own Fusion style (in the desktop's light or dark), rather than whatever
        # each desktop's Qt happens to pick (QT_STYLE_OVERRIDE or -style still win, for anyone who wants theirs)
        if not os.environ.get("QT_STYLE_OVERRIDE") and "-style" not in sys.argv and not getattr(self.app, "_vml_styled", False):
            self.app.setStyle("Fusion")
            self.app._vml_styled = True
        if SCROLLBARS not in (self.app.styleSheet() or ""):
            self.app.setStyleSheet((self.app.styleSheet() or "") + SCROLLBARS)
        if db_path is None:
            fd, db_path = tempfile.mkstemp(prefix="vml-", suffix=".db")
            os.close(fd)
        self.store = Store(db_path)
        self.scopes: dict[str, dict[str, Node]] = {}
        self.windows, self.templates, self.themes, self.menubars = [], {}, {}, {}
        self.styles = {}                        # @Style name -> parsed CSS (vml/styles.py), shared by every form
        self.current_control = ""
        self.licence_override = None           # tests set a tier here; nothing a script can reach
        self.listeners = []                    # called (name, prop, value) after every SetProperty
        self._quiet = 0                        # >0 while scripts set properties: Qt signals then aren't user events
        self._script_stack, self._scope_stack = [], []
        self._init_data()
        self._init_projects()
        self._init_lua(lua_paths)
        from .api import ApiServer
        self.api = ApiServer(self, log)                     # scripts in any language call back through this
        self._init_shell()
        self._seed_settings()

    def _seed_settings(self):
        """Settings the Avalonia engine provided, which scripts rely on; never overwrites a project's own."""
        defaults = {"system_path": str(SYSTEM_DIR), "vml_home": str(SYSTEM_DIR.parent), "db_path": self.store.path,
                    "engine": "vml-qt", "platform": sys.platform}
        for k, v in defaults.items():
            if not self.store.get_setting(k):
                self.store.set_setting(k, v)

    # ================================================================ lookup

    def active_scope(self):
        for node in reversed(self._script_stack):
            if node is not None:
                return node.scope
        if self._scope_stack:
            return self._scope_stack[-1]
        return self.windows[-1].scope if self.windows else ""

    def find(self, name, scope=None):
        name = str(name)
        if "." in name:                                     # "Main.lblStatus": a control on another form
            form, ctrl = name.split(".", 1)
            for sc, nodes in self.scopes.items():
                win = nodes.get(form)
                if win is not None and win.type.name == "Window" and win.parent is None:
                    return nodes.get(ctrl)
            return None
        scope = scope or self.active_scope()
        if name in self.scopes.get(scope, {}):
            return self.scopes[scope][name]
        for nodes in reversed(list(self.scopes.values())):
            if name in nodes:
                return nodes[name]
        return None

    @property
    def nodes(self):
        merged = {}
        for nodes in self.scopes.values():
            merged.update(nodes)
        return merged

    # ================================================================ building

    def load(self, vml_path, show=True, modal=False):
        vml_path = str(Path(vml_path).resolve())
        origin = self._script_stack[-1] if getattr(self, "_script_stack", None) else None
        if getattr(self, "_running", 0) or (origin is not None and origin.scope in getattr(self, "_run_scopes", ())):
            self._run_scopes.add(vml_path)                   # (for the debugger: part of the app being tested)
        self._adopt_project(vml_path)
        self._forget_sources(vml_path)
        self.store.import_vml(vml_path)
        while PARSER_LOG:
            log(PARSER_LOG.pop(0))
        self._lua_paths_add(str(Path(vml_path).parent))
        self.scopes[vml_path] = {}
        self._scope_stack.append(vml_path)
        windows = []
        try:
            from . import styles as _styles
            roots = list(self.store.roots(vml_path))
            for cid, ctype, name in roots:                    # shared styles first, wherever they are in the file
                if ctype == "Style":
                    self.styles[name] = _styles.parse(self.store.props(cid).get("Content", ""))
            for cid, ctype, name in roots:
                if ctype == "Style":
                    continue
                node = self.build(cid, ctype, name, None, scope=vml_path)
                if node.type.name == "Window":
                    windows.append(node)
                elif node.type.name == "MenuItem":
                    self._attach_to_menubar(node)
                elif node.type.name == "MenuTheme":
                    self._apply_theme(node)
                elif node.type.name not in ("ContextMenu",):
                    log(f"{node.name} ({node.type.name}) has no parent in this form, so it isn't shown")
        finally:
            self._scope_stack.pop()
        if show:
            for w in windows:
                self.show_window(w, modal=modal)
        return self

    def build(self, cid, ctype, name, parent, props=None, scope=None):
        if ctype == "Style":                                  # (a shared style given a Parent: still just a style)
            from . import styles as _styles
            self.styles[name] = _styles.parse((self.store.props(cid) if props is None else props).get("Content", ""))
            return parent
        node = self.make_node(ctype, name, cid, self.store.props(cid) if props is None else props, parent, scope)
        for kid in self.store.children(cid):
            self.build(*kid, node, scope=node.scope)
        return node

    def make_node(self, ctype, name, cid, props, parent, scope=None):
        scope = scope or (parent.scope if parent else self.active_scope())
        if parent is not None and parent.type.name == "DesignSurface":
            scope = "design:" + parent.name          # designed controls never clash with the designer's own names
        tmpl = None
        ct = REGISTRY.get(ctype)
        if ct is None:
            tmpl = self.template(ctype)
            if tmpl and tmpl.root:
                ct = REGISTRY.get(tmpl.parts[0][1], PLACEHOLDER)
            else:
                log(f"'{ctype}' isn't in the registry or a known composite: showing {name} as a placeholder")
                ct = PLACEHOLDER
        existing = self.scopes.get(scope, {}).get(name)
        if existing is not None:
            self.delete(name, scope)
        root_props = dict(tmpl.parts[0][3]) if tmpl else {}
        if tmpl:
            root_props.update({k: v for k, v in props.items() if k not in tmpl.maps or tmpl.maps[k][0] == tmpl.root})
        node = Node(ct, name, cid, root_props if tmpl else props, scope)
        node.engine = self
        node.widget = ct.make(node)
        node.widget.setObjectName(css_id(name))
        node.widget.setAttribute(Qt.WA_StyledBackground, True)
        node.widget.vml_node = node
        if ct.name == "Window" or getattr(ct, "virtual", False):
            node.host = node.widget
        else:
            node.host = QWidget()
            node.host.setObjectName(name + "__host")
            lay = QVBoxLayout(node.host)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.addWidget(node.widget)
            node.host.vml_node = node
        if ct is PLACEHOLDER:
            node.widget.layout().insertWidget(0, QLabel(f"[{ctype} {name}]"))
        self.scopes.setdefault(scope, {})[name] = node
        self._quiet += 1
        try:
            for pname, value in list(node.props.items()):
                self.apply(node, pname, value)
        finally:
            self._quiet -= 1
        if parent is not None:
            node.parent = parent
            parent.children.append(node)
            if parent.type.add_child:
                parent.type.add_child(parent, node)
        if tmpl:
            self._instantiate(node, tmpl, props)
        if scope.startswith("design:"):
            from .design import inert
            inert(node.host)
        return node

    def apply(self, node, pname, value):
        p = node.type.props.get(pname)
        if p and p.apply:
            try:
                p.apply(node, value)
            except Exception as exc:
                log(f"{node.name}.{pname}={value!r}: {exc}")
        if pname in node.type.events:
            self.hook(node, pname)

    def hook(self, node, event):
        if event in node.hooked or node.type.events.get(event) is None:
            return
        node.hooked.add(event)
        node.type.events[event](node, lambda details, n=node, e=event: self.fire(n, e, details))

    def show_window(self, node, modal=False):
        w = node.widget
        need = w.minimumSizeHint()
        if need.height() > w.height() or need.width() > w.width():
            w.resize(w.size().expandedTo(need))
        if modal or truthy(node.props.get("Modal", "false")):
            w.setWindowModality(Qt.ApplicationModal)
        theme = self.themes.get(node.scope) or {}
        if hasattr(w, "set_title_bar") and not node.props.get("TitleBar"):
            w.set_title_bar("Own")                             # our own title bar unless the form asks for the desktop's
        if hasattr(w, "set_edge") and not node.props.get("BorderBrush") and node.props.get("BorderThickness") in (None, ""):
            from .theme import theme as desktop                # every form has an edge, 2px, unless it says otherwise:
            w.set_edge(theme.get("Background") or desktop().edge, 2)     # its menu bar's colour, else a quiet grey
        if hasattr(w, "closeEvent") and isinstance(w, QWidget):
            w.closing = lambda by_user=False: self._closing(node, by_user)
        try:
            from . import appbar
            appbar.attach(self, node)                        # Terms · About · version, if the form asks (and the designer)
        except Exception as exc:
            log(f"app bar: {exc}")
        from .projects import is_designer
        if is_designer(node.scope):
            self._designing = True
        if getattr(self, "_designing", False) and not getattr(w, "_f12", None):
            from PySide6.QtGui import QKeySequence, QShortcut
            w._f12 = QShortcut(QKeySequence("F12"), w, activated=self.cmd_ShowDebugger)   # (only where the designer runs forms)
        if is_designer(node.scope) and not getattr(w, "_f1", None):
            from PySide6.QtGui import QKeySequence, QShortcut
            w._f1 = QShortcut(QKeySequence("F1"), w, activated=self.help_here)          # help on what's selected
        if node.props.get("OnResized") and hasattr(w, "set_title_bar"):     # (VB's Form_Resize: once it settles)
            settle = QTimer(w)
            settle.setSingleShot(True)
            settle.setInterval(120)
            settle.timeout.connect(lambda: self.fire(node, "OnResized", {"width": w.width(), "height": w.height() - w.bar_h()}))
            w.on_resized = settle.start
        if node.props.get("OnActivated") and hasattr(w, "set_title_bar"):   # (VB's Form_Activate: brought to the front)
            w.on_activated = lambda: self.fire(node, "OnActivated", {})
        opening = bool(node.props.get("OnOpened"))
        if opening:
            w.setWindowOpacity(0.0)                          # build first, then appear: no half-drawn flash
        state = (node.props.get("WindowState") or "").lower()
        if state == "auto":                                  # maximised on an HD screen or smaller, its own size on a bigger one
            from PySide6.QtGui import QGuiApplication
            scr = w.screen() or QGuiApplication.primaryScreen()
            state = "maximized" if scr and scr.availableGeometry().width() <= 1920 else ""
        if state in ("maximized", "maximised"):
            w.showMaximized()
        elif state == "fullscreen":
            w.showFullScreen()
        else:
            w.show()
        if node.props.get("Resizable", "true").lower() == "false":
            w.setFixedSize(w.size())
        self.windows.append(node)

        def opened():
            try:
                if opening:
                    self.fire(node, "OnOpened", {})
            finally:
                if opening:
                    self.app.processEvents()
                    w.setWindowOpacity(1.0)
            if self.scopes.get(node.scope, {}).get(node.name) is node:
                self.sources_opened(node.scope)              # controls that fill themselves, once OnOpened has set things up
        QTimer.singleShot(0, opened)

    def delete(self, name, scope=None):
        node = self.find(name, scope) if scope is None else self.scopes.get(scope, {}).get(name)
        if not node:
            return False
        for kid in list(node.children) + list(node.inner):
            self.delete(kid.name, kid.scope)
        if node.parent:
            if node.parent.type.remove_child:
                node.parent.type.remove_child(node.parent, node)
            if node in node.parent.children:
                node.parent.children.remove(node)
        node.host.setParent(None)
        node.host.deleteLater()
        self.scopes.get(node.scope, {}).pop(name, None)
        self._forget_sources(node.scope, name)
        if node.cid is not None:
            self.store.delete_control(node.cid)
        return True

    # ================================================================ composites

    def template(self, type_name, path=None):
        if type_name in self.templates:
            return self.templates[type_name]
        candidates = [Path(path)] if path else []
        for scope in [self.active_scope(), *self.scopes]:
            if scope:
                candidates.append(Path(scope).parent / "CompositeControls" / f"{type_name}.vml")
        candidates.append(SYSTEM_DIR / "CompositeControls" / f"{type_name}.vml")
        for c in candidates:
            if c.is_file():
                head = c.read_text(encoding="utf-8", errors="ignore").lstrip()
                if head.startswith("<"):
                    log(f"{c.name} is Avalonia XAML, not VML: it needs converting before it can be used")
                    return None
                rows, props = self.store.template_rows(str(c))
                while PARSER_LOG:
                    PARSER_LOG.pop(0)
                t = Template(type_name, rows, props)
                self.templates[type_name] = t
                log(f"composite {type_name} loaded from {c} ({len(t.parts)} parts, {len(t.maps)} mapped properties)")
                return t
        return None

    def _instantiate(self, node, tmpl, props):
        """Build the template's inner controls under node (named node_part) and route mapped properties."""
        names = {tmpl.root: node.name}
        for cname, ctype, parent_name, p in tmpl.parts[1:]:
            inner_name = f"{node.name}_{cname}"
            names[cname] = inner_name
            parent = self.find(names.get(parent_name, node.name), node.scope) or node
            child = self.make_node(ctype, inner_name, None, p, parent, node.scope)
            node.inner.append(child)
            if child in parent.children and parent is not node:
                pass
        node.maps = {k: (names.get(t, node.name), tp) for k, (t, tp) in tmpl.maps.items()}
        node.template = tmpl.name
        self._quiet += 1
        try:
            for k, v in props.items():
                if k in node.maps and node.maps[k][0] != node.name:
                    target = self.find(node.maps[k][0], node.scope)
                    if target:
                        target.props[node.maps[k][1]] = v
                        self.apply(target, node.maps[k][1], v)
        finally:
            self._quiet -= 1

    # ================================================================ menus

    def _attach_to_menubar(self, item):
        bar = self._menubar(item.scope)
        if bar is None:
            log(f"menu item {item.name} has no TinyMenu bar to go on")
            return
        bar.widget.addAction(item.action)
        self._style_menus(item.scope)

    def _menubar(self, scope):
        for node in self.scopes.get(scope, {}).values():
            if node.type.name == "TinyMenu":
                return node
        return None

    def _apply_theme(self, theme):
        self.themes[theme.scope] = theme.props
        self._style_menus(theme.scope)

    def _retheme(self, theme):
        """A theme changed while its form is open: the bar, its menus and the window's edge all follow."""
        self._apply_theme(theme)
        colour = theme.props.get("Background")
        for node in self.windows:
            w = node.widget
            if node.scope == theme.scope and colour and hasattr(w, "set_edge") and not node.props.get("BorderBrush") \
                    and node.props.get("BorderThickness") in (None, ""):
                w.set_edge(colour, 1)

    def _style_menus(self, scope):
        t = self.themes.get(scope)
        if not t:
            return
        bar = self._menubar(scope)                      # (our menus draw themselves from the theme: vml/menus.py)
        if bar:
            bar.widget.menu_theme = dict(t)
            if hasattr(bar.widget, "set_height"):
                bar.widget.set_height(float(t.get("Height") or 0))
            bar.widget.update()
        for node in self.scopes.get(scope, {}).values():
            if getattr(node, "menu", None) is not None:
                node.menu.menu_theme = dict(t)

    # ================================================================ events

    HANDLER_CALL = re.compile(r"^\s*([A-Za-z_]\w*)\s*\((.*)\)\s*$")
    HANDLER_CMD = re.compile(r"^\s*([A-Za-z_]\w*)\s+(.+?)\s*$")

    def _closing(self, node, by_user=False):
        """A form's window is about to close: run its OnClosing. False keeps it open (the handler called CancelClose).
        The setting closing_by_user says whether a person closed it (its X, Alt+F4) or the program did."""
        if not str(node.props.get("OnClosing") or "").strip() or str(node.scope).startswith("design:"):
            return True
        self.store.set_setting("closing_by_user", "true" if by_user else "false")
        self._cancel_close = False
        try:
            self.fire(node, "OnClosing", {})
        except Exception as exc:
            log(f"OnClosing of {node.name}: {exc}")
        cancelled, self._cancel_close = self._cancel_close, False
        return not cancelled

    def cmd_CancelClose(self):
        """In a form's OnClosing handler: keep the form open after all (VB's Cancel = True)."""
        self._cancel_close = True
        return True

    def fire(self, node, event, details):
        if self._quiet:
            return
        if isinstance(node, str):                           # an event raised by name: find the control (and say so)
            log(f"event {event} was raised for '{node}' by name, not by control: please report this")
            node = self.find(node)
            if node is None:
                return
        handler = str(node.props.get(event) or "").strip()
        if not handler:
            return
        for k, v in details.items():
            self.store.set_setting(k, v)
        self.store.set_setting("event_control", node.name)
        self.store.set_setting("event_name", event)
        if node.type.name == "MenuItem" and event == "OnClick":
            self._style_menus(node.scope)
        self.handle(handler, node)

    def handle(self, handler, node):
        """Script name | Script(arg, ...) | a module's function, the same two ways | VmlCommand arg ... | Lua code."""
        if self.held(handler):                               # a script is stopped at a breakpoint: events wait
            return None
        if self.runnable(handler, node):
            return self.run_script(handler, node.name, origin=node)
        m = self.HANDLER_CALL.match(handler)
        if m and self.runnable(m.group(1), node):
            args = [a.strip().strip("'\"") for a in m.group(2).split(",") if a.strip()]
            return self.run_script(m.group(1), *args, origin=node)
        m = self.HANDLER_CMD.match(handler)
        if m and hasattr(self, "cmd_" + m.group(1)) and "(" not in handler:
            self._script_stack.append(node)
            try:
                return self.vml(m.group(1), *m.group(2).split())
            finally:
                self._script_stack.pop()
        if hasattr(self, "cmd_" + handler):
            self._script_stack.append(node)                  # so CloseSelf etc. know which form asked
            try:
                return self.vml(handler)
            finally:
                self._script_stack.pop()
        if re.fullmatch(r"[A-Za-z_]\w*", handler):
            log(f"{node.name}: {handler} isn't a script in this form or an engine command")
            return None
        return self.lua_exec(handler, (node.name,), label=f"{node.name} handler", origin=node)

    # ================================================================ scripts

    def _init_lua(self, extra_paths):
        """Lua states are made on demand: one per form, plus one per named instance (Interpreter=lua mygame),
        so each form's globals are its own unless scripts deliberately share an instance."""
        self.luas = {}
        self.debugger, self._debug_labels = None, []
        self._tap = None                                     # (a debugger in another process, attached: vml/debugger.py Tap)
        self._stepping_init()                                # breakpoints and stepping (vml/stepping.py)
        self._run_scopes, self._running = set(), 0          # forms the designer is running, and what they opened
        self.lua_paths = [str(LUA_DIR), str(SYSTEM_DIR / "lua"), *extra_paths]
        self.lua = self.lua_state("")                       # the engine's own, for code with no form

    def lua_state(self, key):
        rt = self.luas.get(key)
        if rt is None:
            rt = lua54.LuaRuntime(unpack_returned_tuples=True)
            g = rt.globals()
            g.Vml = self.vml
            g.print = lambda *a: log("[lua] " + "\t".join("nil" if x is None else str(x) for x in a))
            for d in reversed(self.lua_paths):
                rt.execute("local d = ...; package.path = d .. '/?.lua;' .. package.path", d)
            self.luas[key] = rt
            self._load_modules(rt, key)                      # a project's modules: there for every one of its forms
            if self.stepping_active():
                self._hook_state(rt)                         # (breakpoints set: this form's Lua stops at them too)
        return rt

    def _lua_paths_add(self, *dirs):
        for d in dirs:
            if d not in self.lua_paths:
                self.lua_paths.append(d)
                for rt in self.luas.values():
                    rt.execute("local d = ...; package.path = d .. '/?.lua;' .. package.path", d)

    def lua_key(self, script=None, origin=None):
        """Which Lua state code runs in: a named instance if the script has one, else its form's own."""
        if script:
            instance, source = self.store.script_home(script)
            if instance:
                return "instance:" + instance
            if source:
                return str(source)
        if origin is not None:
            return origin.scope
        return self.active_scope() or ""

    def lua_exec(self, code, args=(), label="lua", origin=None, key=None):
        self._script_stack.append(origin)
        self._debug_labels.append(label)
        rt = self.lua_state(self.lua_key(origin=origin) if key is None else key)
        g = rt.globals()
        saved = (g.arg, g.args)
        try:
            g.arg = g.args = rt.table_from(list(args))
            return rt.execute(code, *args, name="=" + str(label))       # (named: breakpoints and errors say which script)
        except Exception as exc:
            log(f"script error in {label}: {exc}")
            if self.debugger is not None or self._tap is not None:
                self.debug_record("script error", (label,), str(exc), error=True)
            return None
        finally:
            g.arg, g.args = saved
            self._debug_labels.pop()
            self._script_stack.pop()

    def _init_shell(self):
        """Bash scripts call `vml-parse` and read $VML_DB_PATH, as in the Avalonia engine."""
        self.bin_dir = Path(tempfile.mkdtemp(prefix="vml-bin-"))
        for name, module, verb in (("vml-parse", "vml.parsecli", "parse"), ("vml", "vml.client", "")):
            if FROZEN:                                  # a compiled build: the binary itself answers
                run_sh, run_cmd = f'"{sys.executable}" {verb}'.rstrip(), f'"{sys.executable}" {verb}'.rstrip()
            else:
                run_sh = run_cmd = f'"{sys.executable}" -m {module}'
            shim = self.bin_dir / name
            shim.write_text(f'#!/bin/sh\nexec {run_sh} "$@"\n')
            shim.chmod(0o755)
            (self.bin_dir / f"{name}.cmd").write_text(f'@{run_cmd} %*\r\n')
        self.env = dict(os.environ, VML_DB_PATH=self.store.path, **self.api.env(),
                        PATH=f"{self.bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
                        PYTHONPATH=str(Path(__file__).resolve().parent.parent))

    IDENT = re.compile(r"^[A-Za-z_]\w*$")

    def lua_function(self, name, origin=None):
        """A Lua function of this name that a handler may call: one a project's module defined (or a script of the
        form did), in the Lua state of the form that asked. With nobody asking, the first open form that has one.
        Returns (the function, its state's key, the control it runs for), or None."""
        if not self.IDENT.match(str(name)):
            return None
        if origin is not None:
            places = [(origin.scope, origin)]
        else:
            places = []
            for w in self.windows:
                if w.parent is None and all(w.scope != k for k, _ in places):
                    places.append((w.scope, w))
        for key, node in places:
            if not key or str(key).startswith("design:"):
                continue
            if key not in self.luas and self._project_of(key) is None:
                continue                                     # a form with no modules and no scripts run yet has none
            try:
                f = self.lua_state(key).globals()[name]
            except Exception:
                f = None
            if f is not None and lua54.lua_type(f) == "function":
                return f, key, node
        return None

    def runnable(self, name, origin=None):
        """Is there a script, or a module's function, of this name for this control's form?"""
        return bool(self.store.script(name)) or self.lua_function(name, origin) is not None

    def run_function(self, found, name, args):
        f, key, node = found
        self._script_stack.append(node)
        self._debug_labels.append(name)
        try:
            r = f(*[a if isinstance(a, (bool, int, float)) else str(a) for a in args])
            return "" if r is None else r
        except Exception as exc:
            log(f"script error in {name}: {exc}")
            if self.debugger is not None or self._tap is not None:
                self.debug_record("script error", (name,), str(exc), error=True)
            return ""
        finally:
            self._debug_labels.pop()
            self._script_stack.pop()

    def run_script(self, name, *args, origin=None):
        found = self.store.script(name)
        if not found:
            function = self.lua_function(name, origin)
            if function is not None:                         # not a script: a function in one of the project's modules
                return self.run_function(function, name, args)
            log(f"RunScript: no script called '{name}'")
            return ""
        interp, content = (found[0] or "lua").lower().split()[0] if (found[0] or "").strip() else "lua", found[1] or ""
        if origin is None:                                   # run for nobody in particular: it acts as its own form
            _, source = self.store.script_home(name)
            origin = next((n for n in self.scopes.get(str(source), {}).values()
                           if n.type.name == "Window" and n.parent is None), None)
        if interp == "lua":
            r = self.lua_exec(content, args, label=name, origin=origin, key=self.lua_key(script=name))
            return "" if r is None else r
        if interp in ("bash", "sh"):
            return self.shell(["bash", "-c", content, name, *map(str, args)], name, origin)
        if interp in ("csharp", "c#", "cs"):
            return self.run_csharp(content, args, name, origin)
        if interp in ("python", "python3", "py"):
            py = self.python_exe()
            if not py:
                log(f"{name}: Python isn't installed on this machine")
                return ""
            return self.shell([py, "-c", PYTHON_PRELUDE + content, name, *map(str, args)], name, origin)
        if interp in ("powershell", "pwsh"):
            exe = shutil.which("pwsh") or shutil.which("powershell")
            if not exe:
                log(f"{name}: PowerShell isn't installed on this machine")
                return ""
            return self.shell([exe, "-NoProfile", "-Command", content, *map(str, args)], name, origin)
        log(f"{name}: '{interp}' scripts aren't supported by this engine (Lua, Bash and PowerShell are)")
        return ""

    def run_csharp(self, code, args, label, origin=None):
        from . import csharp
        if not csharp.available():
            log(f"{label}: C# scripting isn't set up on this computer (Settings, C# Scripting, in the designer)")
            return ""
        if getattr(self, "_csharp", None) is None:
            self._csharp = csharp.CSharpHost(self, log)
        self._script_stack.append(origin)
        try:
            return self._csharp.run(code, args, self.lua_key(script=label), label)
        except Exception as exc:
            log(f"{label}: {exc}")
            return ""
        finally:
            self._script_stack.pop()

    def cmd_VmlVersion(self):
        """The running Visualised runtime version, e.g. "0.17.1". Apps can check they have a new enough engine."""
        from . import __version__
        return __version__

    def cmd_CSharpStatus(self):
        """Where C# scripting stands here, as JSON: ready, dotnet (its path), sdk (version), sdk_ok, download."""
        from . import csharp
        return json.dumps(csharp.status())

    def cmd_CSharpSetup(self):
        """Build the C# script host (needs the .NET SDK; about a minute the first time). Returns "" when C# is
        ready, otherwise why it isn't."""
        from . import csharp
        self.cmd_SetStatusText("Setting up C# scripting (this takes about a minute the first time)...")
        self.app.processEvents()
        ok, msg = csharp.build()
        log(msg)
        if ok and getattr(self, "_csharp", None) is not None:
            self._csharp.stop()
            self._csharp = None
        self.cmd_SetStatusText("C# scripting is ready" if ok else "C# scripting couldn't be set up")
        return "" if ok else msg

    def cmd_InstallDotnet(self):
        """Start installing the .NET SDK where that can be done for the user: on Windows, with winget, in a window
        of its own. Returns "started", or "" if it has to be downloaded by hand (see CSharpStatus's download).
        A copy from the Microsoft Store never installs other software itself: it only shows where to get it."""
        if sys.platform.startswith("win") and shutil.which("winget") and "windowsapps" not in sys.executable.lower():
            try:
                subprocess.Popen(["cmd", "/c", "start", "Installing the .NET SDK", "cmd", "/k",
                                  "winget install --id Microsoft.DotNet.SDK.8 -e --accept-source-agreements "
                                  "--accept-package-agreements & echo. & echo You can close this window when it has finished."])
                return "started"
            except OSError as exc:
                log(f"InstallDotnet: {exc}")
        return ""

    def cmd_GetLanguages(self):
        """The script languages this machine can run, for the script editor."""
        from . import csharp
        langs = ["Lua", f"Shell ({self.cmd_GetShellName()})"]
        if self.python_exe():
            langs.append("Python")
        if csharp.available():
            langs.append("C#")
        return json.dumps(langs)

    @staticmethod
    def python_exe():
        """The user's own Python (with their pip packages); the engine's, when running from source."""
        found = shutil.which("python3") or shutil.which("python")
        if found:
            return found
        return sys.executable if "python" in Path(sys.executable).name.lower() else None

    def shell(self, argv, label="shell", origin=None, timeout=120):
        """Run a program, answering its `vml ...` calls while it runs (as the form that started it)."""
        self._script_stack.append(origin)
        try:
            with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
                try:
                    proc = subprocess.Popen(argv, stdout=out, stderr=err, stdin=subprocess.DEVNULL, env=self.env)
                except Exception as exc:
                    log(f"{label}: {exc}")
                    return ""
                started = time.time()
                while proc.poll() is None:
                    self.api.poll()
                    if time.time() - started > timeout:
                        proc.kill()
                        log(f"{label}: stopped after {timeout}s")
                        break
                    time.sleep(0.003)
                self.api.poll()
                out.seek(0)
                err.seek(0)
                stdout = out.read().decode(errors="replace")
                stderr = err.read().decode(errors="replace")
        finally:
            self._script_stack.pop()
        for line in (stdout + stderr).splitlines():
            log(f"[{label}] {line}")
        return stdout.rstrip("\n")

    # ================================================================ the Vml() API

    def vml(self, command, *args):
        """Scripts' Vml(): forgiving. A bad call is logged and gives an empty result."""
        if self.debugger is None and self._tap is None:
            try:
                return self.vml_strict(command, *args)
            except Exception as exc:
                log(f'Vml("{command}"): {exc}')
                return ""
        try:
            r = self.vml_strict(command, *args)
            self.debug_record(command, args, r)
            return r
        except Exception as exc:
            log(f'Vml("{command}"): {exc}')
            self.debug_record(command, args, str(exc), error=True)
            return ""

    # ---- the debugger (vml/debugger.py): F12 while the designer is running forms
    def debug_hidden(self, scope):
        """The designer's own forms (and its design surface) are not the app being tested, unless the designer is
        running them (the designer opened as a project, say), or the debugger's "Designer's forms too" is ticked."""
        from .projects import is_designer
        scope = str(scope or "")
        if (self.debugger is not None and self.debugger.everything.isChecked()) or (self._tap is not None and self._tap.everything):
            return not scope
        if scope in self._run_scopes:
            return False
        return not scope or scope.startswith("design:") or is_designer(scope)

    def debug_name(self, scope):
        scope = str(scope or "")
        if scope.startswith("instance:"):
            return scope + " (shared)"
        name = next((n.name for n in self.scopes.get(scope, {}).values() if n.type.name == "Window" and n.parent is None), "")
        file = Path(scope).name
        if file.startswith("vml-preview-"):
            return f"{name or file} (being designed)"
        return name or file

    def debug_record(self, command, args, result, error=False):
        origin = self._script_stack[-1] if self._script_stack else None
        scope = origin.scope if origin is not None else (self.active_scope() or "")
        if self.debug_hidden(scope):
            return
        shown = ", ".join(str(a) if isinstance(a, (int, float)) and not isinstance(a, bool) else json.dumps("" if a is None else str(a), ensure_ascii=False)
                          for a in args)
        label = self._debug_labels[-1] if self._debug_labels else ""
        for d in (self.debugger, self._tap):
            if d is not None:
                d.record(self.debug_name(scope), label, f"{command}({shown})", result, error)

    HELP = "https://github.com/wallisoft/vml/wiki/"

    def cmd_Help(self, page="", section=""):
        """Open a page of Visualised's help, in the app's help window: "" for the tutorials, "Reference" for the
        reference, or any page's name ("Reference-Commands", "How-To-Style-Controls-with-CSS"); section: a heading on
        it. Returns its address on the wiki."""
        name = str(page).strip().replace(" ", "-") or "Home"
        anchor = re.sub(r"[^a-z0-9-]", "", str(section).strip().lower().replace(" ", "-")) if str(section).strip() else ""
        box = getattr(self, "_help_box", None)
        try:
            if box is not None and box.isVisible():               # one help window: it goes to the page asked for
                box.reader.open("help:" + name + (f"#{anchor}" if anchor else ""))
                box.raise_()
                box.activateWindow()
                return self.HELP + name + (f"#{anchor}" if anchor else "")
        except RuntimeError:
            pass
        self._help_box = self._reader("help:" + name + (f"#{anchor}" if anchor else ""), "")
        return self.HELP + name + (f"#{anchor}" if anchor else "")

    def _reader(self, source, title):
        from .mdview import MarkdownBox
        box = MarkdownBox(self._parent_window(), source, title, self._edge())
        self._readers = [b for b in getattr(self, "_readers", []) if _alive(b)] + [box]
        box.show()
        box.raise_()
        box.activateWindow()
        return box

    def cmd_ShowMarkdown(self, source, title=""):
        """Show Markdown in a window of its own, beside the app: source is the Markdown itself, a file, a web address
        (a web page shows as its text and links) or help:Page for a page of Visualised's help. Links in it open in the
        same window (back and forward as in a browser); links to other sites open in the browser."""
        self._reader(source, title)
        return "true"

    def cmd_EditMarkdown(self, source="", title="Edit", save_to="", handler=""):
        """Let the user write Markdown, seeing how it looks beside it as they type. source: the Markdown to start with
        (or a file of it); save_to: a file Save writes to. Returns what they saved, or "" if they cancelled. handler: a
        script to run with what was saved (a web page can't wait for the answer, so use it there)."""
        from .mdview import MarkdownBox
        src = str(source or "")
        if not src.strip():
            src = "\n"                                           # an empty page to write on, not an empty source
        out = MarkdownBox(self._parent_window(), src, title, self._edge(), editable=True, save_to=save_to).run()
        if out is not None and str(handler or "").strip():
            self.cmd_RunScript(str(handler), out)
        return "" if out is None else out

    def help_here(self):
        """F1 in the designer: the reference entry for the selected control's kind; with nothing selected, the reference."""
        name = str(getattr(self, "current_control", "") or "")
        node = self.find(name) if name else None
        if node is not None and not node.type.name in ("DesignSurface", "PropertyGrid"):
            return self.cmd_Help("Reference-Controls", getattr(node, "template", None) or node.type.name)
        return self.cmd_Help("Reference")

    # ---- a debugger in another process, attached to this app (vml/debugger.py: Tap, Remote)
    def cmd_DebugTitle(self):
        """What this app is, for a debugger's list of running apps."""
        wins = [n for sc in self.scopes.values() for n in sc.values() if n.type.name == "Window" and n.parent is None
                and n.widget is not None and n.widget.isVisible()]
        title = next((str(n.props.get("Title") or n.name) for n in wins), "") or "an app with no window showing"
        return f"{title}  (pid {os.getpid()})"

    def cmd_DebugAttach(self, everything="false"):
        """Start keeping a record of Vml() calls for an attached debugger to collect (DebugCalls)."""
        from .debugger import Tap
        if self._tap is None:
            self._tap = Tap(lambda: setattr(self, "_tap", None))
        self._tap.everything = str(everything).lower() == "true"
        self._tap.touch()
        return "true"

    def cmd_DebugDetach(self):
        self._tap = None
        return "true"

    def cmd_DebugCalls(self, since="0"):
        """The calls recorded since a number: JSON {seq, rows}."""
        if self._tap is None:
            self.cmd_DebugAttach()
        return json.dumps(self._tap.since(int(since or 0)))

    def cmd_DebugStates(self):
        """The forms with Lua running, for the Variables tab: JSON [[key, name]]."""
        everything = self._tap is not None and self._tap.everything
        return json.dumps([[k, self.debug_name(k)] for k in self.luas
                           if k and (not self.debug_hidden(k) or (everything and k))])

    def cmd_DebugLua(self, key, code, arg=""):
        """Run Lua in one of this app's forms (the Variables tab); a table comes back as {name: "type<TAB>value"}."""
        rt = self.luas.get(key)
        if rt is None:
            raise KeyError("that form isn't running Lua now")
        r = rt.execute(code, arg) if arg != "" else rt.execute(code)
        if hasattr(r, "items"):
            return json.dumps({"table": {str(k): str(v) for k, v in r.items()}})
        return json.dumps({"value": None if r is None else str(r)})

    def cmd_DebugShared(self):
        shared = getattr(getattr(self, "shared", None), "values", None)
        return json.dumps(None if shared is None else {str(k): [type(v).__name__, repr(v)] for k, v in shared.items()})

    def cmd_DebugApps(self):
        """The other Visualised apps running now: JSON [{pid, title}], for "Attach to a running app"."""
        from .api import running
        return json.dumps([{"pid": a["pid"], "title": a["title"]} for a in running(os.getpid())])

    def cmd_AttachDebugger(self, pid=""):
        """Open a debugger on another running Visualised app (by its pid; none: choose from a list)."""
        from .api import running
        from .debugger import Debugger
        apps = running(os.getpid())
        if not apps:
            self.cmd_InfoDialog("No other Visualised app is running just now.\n\nStart one (any .vml), then attach to it.",
                                "Attach the debugger")
            return ""
        pick = next((a for a in apps if str(a["pid"]) == str(pid)), None)
        if pick is None:
            from PySide6.QtWidgets import QMenu
            from PySide6.QtGui import QCursor
            menu = QMenu()
            for a in apps:
                menu.addAction(a["title"]).setData(a["pid"])
            chosen = menu.exec(QCursor.pos())
            if chosen is None:
                return ""
            pick = next(a for a in apps if a["pid"] == chosen.data())
        win = Debugger(self, remote=pick)
        self.__dict__.setdefault("_remotes", []).append(win)
        win.show()
        win.raise_()
        return "true"

    def cmd_ShowDebugger(self):
        """Open the debugger: every Vml() call the running forms' scripts make, and their variables."""
        if self.debugger is None:
            from .debugger import Debugger
            self.debugger = Debugger(self)
        self.debugger.show()
        self.debugger.raise_()
        self.debugger.activateWindow()
        return "true"

    def vml_strict(self, command, *args):
        """The same, but a bad call raises, so the `vml` command can exit with an error."""
        fn = getattr(self, "cmd_" + str(command), None)
        if fn is None:
            raise LookupError(f"{command} isn't a VML command")
        args = ["" if a is None else (a if isinstance(a, (int, float)) else str(a)) for a in args]
        try:
            r = fn(*args)
        except TypeError as exc:
            raise TypeError(f"wrong arguments for {command} ({exc})") from None
        if isinstance(r, bool):
            return "true" if r else "false"
        return "" if r is None else r

    def _node(self, name):
        node = self.find(name)
        if node is None:
            raise KeyError(f"no control called '{name}'")
        return node

    def _resolve(self, node, prop):
        """Composite properties route to the inner control they're mapped to."""
        if prop in node.maps:
            target = self.find(node.maps[prop][0], node.scope)
            if target is not None and target is not node:
                return target, node.maps[prop][1]
        return node, prop

    # --- properties
    def cmd_SetProperty(self, name, prop, value=""):
        if name == "menubar" and self._menubar_surface() is not None:
            surf = self._menubar_surface()
            surf.widget.menu_settings[prop] = str(value)
            surf.widget.apply_menu_settings()
            surf.widget.emit("OnChanged", {"selected_control": "menubar"})
            for listener in list(self.listeners):
                listener("menubar", prop, value)
            return
        if self._menu_target(name):
            return self._menu_set(name, prop, value)
        outer = self._node(name)
        node, prop2 = self._resolve(outer, prop)
        node.props[prop2] = value
        if node is not outer:
            outer.props[prop] = value
        self._quiet += 1
        try:
            self.apply(node, prop2, value)
        finally:
            self._quiet -= 1
        self.store.set_prop(outer.cid, prop, value)
        if outer.type.name == "MenuTheme":
            self._retheme(outer)
        self._reflow(outer)
        for listener in list(self.listeners):
            try:
                listener(outer.name, prop, value)
            except Exception as exc:
                log(f"property listener: {exc}")
        if str(outer.scope).startswith("design:") and prop not in outer.type.events:
            self._mirror(outer, prop, value)

    def _mirror(self, outer, prop, value):
        """A change made in the designer shows at once in the form it is running (Preview, or Run Project), if that
        is open: the same control there gets the same property. (Scripts and new or deleted controls wait for the
        next run.)"""
        preview = str((Path(tempfile.gettempdir()) / f"vml-preview-{outer.scope[len('design:'):]}.vml").resolve())
        twin = self.scopes.get(preview, {}).get(outer.name)
        if twin is None or not any(w.scope == preview for w in self.windows):
            return
        try:
            node, prop2 = self._resolve(twin, prop)
            node.props[prop2] = value
            if node is not twin:
                twin.props[prop] = value
            self.apply(node, prop2, value)
            self._reflow(twin)
        except Exception as exc:
            log(f"live preview: {twin.name}.{prop}: {exc}")

    def _reflow(self, node):
        """Canvas children aren't in a layout: re-place them when anything that affects their size changes."""
        while node is not None:
            parent = node.parent
            if parent is not None and parent.type.name in ("Canvas", "DesignSurface", "Frame") and parent.type.place_child:
                parent.type.place_child(parent, node)
                return
            node = parent

    def cmd_GetProperty(self, name, prop):
        if name == "menubar" and self._menubar_surface() is not None:
            return self._menubar_surface().widget.menu_settings.get(prop, "")
        if self._menu_target(name):
            return self._menu_get(name, prop)
        node, prop = self._resolve(self._node(name), prop)
        p = node.type.props.get(prop)
        if p and p.read:
            return p.read(node)
        return node.props.get(prop, p.default if p else "")

    def cmd_GetControlPropertiesJson(self, name):
        """Reflection: every property this control has, with its live value and editor; composites list their mapped ones first."""
        if name == "menubar":
            return self._menubar_props_json()
        if self._menu_target(name):
            return self._menu_props_json(name)
        node = self._node(name)
        out, seen = [], set()
        for prop, (target, tprop) in node.maps.items():
            t = self.find(target, node.scope) or node
            p = t.type.props.get(tprop)
            value = self.cmd_GetProperty(name, prop)
            out.append({"name": prop, "value": "" if value is None else str(value), "type": p.editor if p else "text",
                        "kind": p.kind if p else "text", "group": "Control", "options": list(p.options) if p else []})
            seen.add(prop)
        for p in sorted(node.type.props.values(), key=lambda p: (p.group, p.name)):
            if p.name in seen:
                continue
            value = self.cmd_GetProperty(name, p.name)
            out.append({"name": p.name, "value": "" if value is None else str(value), "type": p.editor,
                        "kind": p.kind, "group": p.group, "options": list(p.options)})
        return json.dumps(out)

    def cmd_GetControlType(self, name):
        if name == "menubar":
            return "Menu"
        if self._menu_target(name):
            return "MenuItem"
        node = self._node(name)
        return getattr(node, "template", None) or node.type.name

    # --- settings
    # An app run on its own keeps its settings for next time, as it does on a phone or in a browser: they go to
    # ~/.vml/kept/<app>.json (readable by this user only) as well as the form's database. keep_settings() turns it on.
    def keep_settings(self, app_path):
        name = re.sub(r"[^\w.-]+", "_", Path(str(app_path)).stem) or "app"
        self._kept_path = Path(os.environ.get("VML_KEPT") or Path.home() / ".vml" / "kept") / f"{name}.json"
        try:
            self._kept = json.loads(self._kept_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self._kept = {}
        for k, v in self._kept.items():
            self.store.set_setting(k, v)

    def _keep(self, key, value):
        path = getattr(self, "_kept_path", None)
        if path is None:
            return
        self._kept[str(key)] = "" if value is None else str(value)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self._kept, f, indent=1)
            os.replace(tmp, path)
        except OSError as exc:
            log(f"couldn't keep the setting {key}: {exc}")

    def cmd_GetSetting(self, key):
        return self.store.get_setting(key)

    def cmd_SetSetting(self, key, value=""):
        self.store.set_setting(key, value)
        self._keep(key, value)

    # --- this user's preferences and licence: kept between runs, unlike settings, which belong to the open form
    def cmd_GetPreference(self, key, default=""):
        """A preference this user set earlier (snap to grid, grid size...), or `default` if they never have."""
        return str(licences.load_prefs().get(str(key), default))

    def cmd_SetPreference(self, key, value=""):
        prefs = licences.load_prefs()
        prefs[str(key)] = str(value)
        licences.save_prefs(prefs)

    def licence(self):
        """The licence in force, as a dict with at least 'tier': community, pro or enterprise."""
        info = licences.current()
        if self.licence_override:
            info = dict(info, tier=self.licence_override)
        return info

    def cmd_GetLicence(self):
        """The licence as JSON: tier, label, name (who it is licensed to), id, issued, expires, key, expired, was."""
        info = self.licence()
        return json.dumps({"tier": info["tier"], "label": licences.TIER_NAMES[info["tier"]], "name": info.get("name", ""),
                           "id": info.get("id", ""), "issued": info.get("issued", ""), "expires": info.get("expires", ""),
                           "key": info.get("key", ""), "expired": bool(info.get("expired")), "was": info.get("was", ""),
                           "buy_url": licences.BUY_URL})

    def cmd_GetLicenceTier(self):
        return self.licence()["tier"]

    def cmd_LicenceAllows(self, feature):
        """"true" if this licence includes a feature ("export", "import"), else "false"."""
        return "true" if licences.allows(str(feature), self.licence()["tier"]) else "false"

    def cmd_SetLicenceKey(self, key):
        """Store a licence key. Returns "" if it was accepted, otherwise why not."""
        info = licences.read_licence(key)
        if not info:
            return "That isn't a valid Visualised licence key. Paste the whole key from your email; it starts with VSL1-."
        if info["expired"]:
            return f"That licence ran out on {info['expires'][6:8]}/{info['expires'][4:6]}/{info['expires'][0:4]}."
        self.cmd_SetPreference("licence_key", info["key"])
        log(f"licence accepted: {info['tier']}")
        threading.Thread(target=licences.link_pass, daemon=True).start()       # its pass for the Link relay, for the apps it saves
        return ""

    def cmd_RemoveLicenceKey(self):
        prefs = licences.load_prefs()
        prefs.pop("licence_key", None)
        licences.save_prefs(prefs)

    def needs(self, feature, doing):
        """True if the licence includes a feature. If not, say so (what the user was `doing`) and return False."""
        if licences.allows(feature, self.licence()["tier"]):
            return True
        self.cmd_InfoDialog(f"{doing} is part of Visualised Pro.\n\nVisualised Community designs, runs, saves and "
                            "shares forms. See Settings, Upgrade Licence.", "Visualised Pro")
        return False

    def cmd_CheckForUpdate(self):
        """Ask whether a newer Visualised has been released. JSON: current, latest, newer, url, error if the check
        couldn't be made, and store (true for a copy from the Microsoft Store, which updates itself: no check is made)."""
        from . import __version__
        import urllib.request
        out = {"current": __version__, "latest": "", "newer": False,
               "url": "https://github.com/wallisoft/vml-releases/releases/latest", "error": "",
               "store": "windowsapps" in sys.executable.lower()}
        if out["store"]:                     # a copy from the Microsoft Store is kept up to date by the Store
            return json.dumps(out)
        try:
            # every release, the fixes too (pre-releases, made by Bob from a tested build): the newest wins
            req = urllib.request.Request("https://api.github.com/repos/wallisoft/vml-releases/releases?per_page=20",
                                         headers={"User-Agent": f"Visualised/{__version__}"})
            with urllib.request.urlopen(req, timeout=6) as r:
                releases = [x for x in json.load(r) if not x.get("draft")]
            number = lambda v: tuple(int(x) for x in re.findall(r"\d+", v)[:3])
            best = max(releases, key=lambda x: number(str(x.get("tag_name", ""))) or (0,), default={})
            out["tag"] = str(best.get("tag_name", ""))
            out["latest"] = out["tag"].lstrip("v")
            out["url"] = best.get("html_url") or out["url"]
            out["newer"] = bool(out["latest"]) and number(out["latest"]) > number(__version__)
        except Exception as exc:
            out["error"] = str(exc)
        return json.dumps(out)

    def cmd_OpenUrl(self, url):
        """Open a web page (or a mailto: link) in the user's own browser or mail program."""
        url = str(url)
        if url.startswith(("https://", "http://", "mailto:")):
            QDesktopServices.openUrl(QUrl(url))

    # --- controls
    def cmd_CreateControl(self, ctype, name, parent_name=""):
        parent = self.find(parent_name) if parent_name else None
        if parent_name and parent is None:
            raise KeyError(f"no parent called '{parent_name}'")
        if ctype not in REGISTRY and not self.template(ctype):
            log(f"CreateControl: unknown control type '{ctype}'")
            return "Failed"
        cid = self.store.add_control(ctype, name, parent.cid if parent else None)
        self.make_node(ctype, name, cid, {}, parent)
        return name

    def cmd_LoadControlTemplate(self, path, name=""):
        name = name or Path(path).stem
        self.templates.pop(name, None)
        return bool(self.template(name, path))

    def cmd_ControlExists(self, name):
        return self.find(name) is not None

    def cmd_DeleteControl(self, name):
        return self.delete(name)

    def cmd_ClearChildren(self, name):
        for kid in list(self._node(name).children):
            self.delete(kid.name, kid.scope)

    def cmd_GetChildControls(self, name):
        return json.dumps([k.name for k in self._node(name).children])

    def cmd_SetControlVisible(self, name, visible):
        self.cmd_SetProperty(name, "IsVisible", "true" if truthy(visible) else "false")

    def cmd_SetControlSize(self, name, w, h):
        self.cmd_SetProperty(name, "Width", w)
        self.cmd_SetProperty(name, "Height", h)

    def cmd_SetControlPosition(self, name, x, y):
        self.cmd_SetProperty(name, "Canvas.Left", x)
        self.cmd_SetProperty(name, "Canvas.Top", y)

    cmd_SetCanvasPosition = cmd_SetControlPosition

    def cmd_GetControlX(self, name):
        return self._node(name).host.x()

    def cmd_GetControlY(self, name):
        return self._node(name).host.y()

    def cmd_GetControlWidth(self, name):
        return self._node(name).widget.width()

    def cmd_GetControlHeight(self, name):
        return self._node(name).widget.height()

    def cmd_GetControlAt(self, x, y, container="DesignCanvas"):
        """The topmost child of the container (default: the design canvas) at x,y in its coordinates."""
        box = self.find(container) or self.find(self.store.get_setting("event_control"))
        if box is None:
            return ""
        x, y = int(float(x or 0)), int(float(y or 0))
        for kid in reversed(box.children):
            if kid.props.get("IsHitTestVisible", "true").lower() == "false" or not kid.host.isVisible():
                continue
            if kid.host.geometry().contains(x, y):
                return kid.name
        return ""

    def cmd_GetResizeZone(self, name, x, y, grip=6):
        """Which edge or corner of a control a point (in the control's coordinates) is on, or nothing."""
        node = self._node(name)
        w, h = node.host.width(), node.host.height()
        x, y, g = float(x or 0), float(y or 0), float(grip)
        v = "Top" if y <= g else "Bottom" if y >= h - g else ""
        hz = "Left" if x <= g else "Right" if x >= w - g else ""
        return (v + hz) or None

    def cmd_SetEvent(self, name, event, handler):
        node = self._node(name)
        node.props[event] = handler
        self.hook(node, event)
        self.store.set_prop(node.cid, event, handler)
        for listener in list(self.listeners):
            listener(node.name, event, handler)

    def cmd_SetCurrentControl(self, name):
        self.current_control = name
        self.store.set_setting("selected_control", name)

    def cmd_GetCurrentControl(self):
        return self.current_control

    cmd_SelectControl = cmd_SetCurrentControl
    cmd_GetSelectedControlName = cmd_GetCurrentControl

    def cmd_GetFocusedControlName(self):
        w = QApplication.focusWidget()
        while w is not None and not hasattr(w, "vml_node"):
            w = w.parent()
        return w.vml_node.name if w is not None else ""

    # --- menus and status
    def cmd_ShowContextMenu(self, name, x=None, y=None):
        node = self._node(name)
        self._style_menus(node.scope)
        node.menu.popup(QCursor.pos())

    def cmd_SetMenuItemEnabled(self, name, enabled):
        self.cmd_SetProperty(name, "IsEnabled", "true" if truthy(enabled) else "false")

    def cmd_SetMenuItemText(self, name, text):
        self.cmd_SetProperty(name, "Text", text)

    def cmd_SetStatusText(self, text):
        for candidate in ("statusText", "StatusText", "lblStatus"):
            if self.find(candidate):
                self.cmd_SetProperty(candidate, "Text", text)
                return
        log(f"[status] {text}")

    # --- scripts
    def cmd_RunScript(self, name, *args):
        origin = self._script_stack[-1] if self._script_stack else None
        return self.run_script(name, *args, origin=origin)

    def cmd_ExecuteScript(self, code, *args):
        return self.lua_exec(code, args, label="ExecuteScript")

    def cmd_Shell(self, command):
        origin = next((o for o in reversed(self._script_stack) if o is not None), None)
        return self.shell(["bash", "-c", command], "shell", origin)


    # --- long-running jobs: start, stream output into a control, progress, cancel (for installers etc.)
    def _init_processes(self):
        self.processes = {}            # id -> {"proc", "thread", "control", "on_exit", "origin", "code", "running"}
        self._proc_seq = 0

    def cmd_RunProcess(self, command, output_control="", on_exit="", shell="bash"):
        """Start a command WITHOUT waiting. Its output streams, line by line, into output_control (a
        TextBox or ListBox) as it arrives. When it ends, on_exit runs (settings: exit_code, process_id).
        Returns a job id. shell: bash | powershell | none (run the command as given)."""
        import shlex
        if not hasattr(self, "processes"):
            self._init_processes()
        sh = str(shell).lower()
        if sh in ("bash", "sh"):
            argv = ["bash", "-lc", command]
        elif sh in ("powershell", "pwsh"):
            exe = shutil.which("pwsh") or shutil.which("powershell")
            argv = [exe, "-NoProfile", "-Command", command] if exe else None
        else:
            argv = shlex.split(command)
        if not argv:
            log("RunProcess: no shell available")
            return ""
        try:
            proc = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    stdin=subprocess.DEVNULL, env=self.env, bufsize=1, text=True, errors="replace")
        except Exception as exc:
            log(f"RunProcess: {exc}")
            return ""
        self._proc_seq += 1
        pid = f"proc{self._proc_seq}"
        origin = next((o for o in reversed(self._script_stack) if o is not None), None)
        scope = origin.scope if origin is not None else self.active_scope()
        job = {"proc": proc, "control": output_control, "on_exit": on_exit, "origin": origin,
               "scope": scope, "code": None, "running": True, "lines": []}
        self.processes[pid] = job

        def pump():
            for line in proc.stdout:                       # blocks in this thread only
                job["lines"].append(line.rstrip("\n"))
            proc.wait()
            job["code"] = proc.returncode
            job["running"] = False
        job["thread"] = threading.Thread(target=pump, daemon=True)
        job["thread"].start()
        self._watch_process(pid)
        return pid

    def _watch_process(self, pid):
        """On the GUI thread: drain new output lines into the control, then finish or check again soon."""
        job = self.processes.get(pid)
        if job is None:
            return
        if not job["running"] and job["thread"].is_alive():
            job["thread"].join(0.2)               # let the pump finish appending its last lines first
        self._drain(pid)
        if job["running"]:
            QTimer.singleShot(50, lambda: self._watch_process(pid))
        else:
            self._drain(pid)                      # one more, in case lines landed between join and now
            self.store.set_setting("exit_code", str(job["code"]))
            self.store.set_setting("process_id", pid)
            if job["on_exit"]:
                self.handle(job["on_exit"], job["origin"] or self._any_window())

    def _drain(self, pid):
        job = self.processes.get(pid)
        if not job or not job["lines"]:
            return
        lines, job["lines"] = job["lines"], []
        node = self.find(job["control"], job["scope"]) if job["control"] else None
        for line in lines:
            if node is not None:
                self._append_to(node, line)
            log(f"[{pid}] {line}")

    def _append_line(self, name, line):
        node = self.find(name)
        if node is not None:
            self._append_to(node, line)

    def _append_to(self, node, line):
        w = node.widget
        from PySide6.QtWidgets import QComboBox, QLineEdit, QListWidget, QPlainTextEdit
        if isinstance(w, QListWidget):
            w.addItem(line)
            w.scrollToBottom()
        elif isinstance(w, QPlainTextEdit):
            w.appendPlainText(line)
        elif isinstance(w, (QLineEdit, QComboBox)):
            node.props["Text"] = line
            self.apply(node, "Text", line)
        else:                                              # a TextBlock etc.: keep the last ~200 lines
            prev = (node.props.get("Text", "") or "").split("\n")[-200:]
            node.props["Text"] = "\n".join(prev + [line])
            self.apply(node, "Text", node.props["Text"])

    def _any_window(self):
        return self.windows[-1] if self.windows else None

    def cmd_ProcessRunning(self, pid):
        job = getattr(self, "processes", {}).get(str(pid))
        return bool(job and job["running"])

    def cmd_ProcessExitCode(self, pid):
        job = getattr(self, "processes", {}).get(str(pid))
        return "" if not job or job["code"] is None else str(job["code"])

    def cmd_CancelProcess(self, pid):
        job = getattr(self, "processes", {}).get(str(pid))
        if job and job["running"]:
            try:
                job["proc"].terminate()
            except Exception:
                pass
            return True
        return False

    # --- data
    def cmd_SqlQuery(self, sql, *args):
        return self.store.query_json(sql, *args)

    def cmd_SqlExecute(self, sql, *args):
        return self.store.execute(sql, *args)

    def cmd_FileExists(self, path):
        return Path(os.path.expanduser(path)).exists()


    # ================================================================ design commands (used by designer.vml)

    def _surface(self, name):
        node = self._node(name or "Surface")
        if node.type.name != "DesignSurface":
            raise KeyError(f"'{name}' isn't a DesignSurface")
        return node

    def _unique(self, base):
        n = 1
        while self.find(f"{base}{n}") is not None:
            n += 1
        return f"{base}{n}"

    # The designer's Add menu, in groups as a VB toolbox has them (anything not named here goes in "More")
    ADD_GROUPS = [
        ("Text", ["TextBlock", "TextBox", "AutoCompleteBox", "HyperlinkButton"]),
        ("Buttons and choices", ["Button", "CheckBox", "RadioButton", "ToggleButton", "ToggleSwitch", "ComboBox"]),
        ("Pickers", ["DatePicker", "TimePicker", "Calendar", "ColorPicker", "NumberBox", "Slider"]),
        ("Lists and data", ["ListBox", "DataGrid", "TreeView"]),
        ("Documents and media", ["MarkdownView", "MarkdownEditor", "Image", "Rectangle"]),
        ("Bars", ["Toolbar", "StatusBar", "ProgressBar"]),
        ("Containers", ["Canvas", "Frame", "TabStrip", "TabPage", "Border", "ScrollViewer"]),
        ("Layout (advanced)", ["StackPanel", "DockPanel", "Grid"]),
        ("Behind the scenes", ["Timer"]),
    ]

    def cmd_GetControlTypes(self):
        """Every control type a designer can add: built-ins from the registry, plus VML composites. Each has its
        category, and the group the Add menu puts it in (in the order the menu shows them)."""
        out = []
        group_of = {n: g for g, names in self.ADD_GROUPS for n in names}
        for ct in REGISTRY.values():
            if getattr(ct, "virtual", False) or getattr(ct, "design_only", False) or ct.name in ("Window", "TinyMenu", "Splitter"):
                continue
            out.append({"name": ct.name, "category": ct.category, "container": ct.container,
                        "group": group_of.get(ct.name, "More")})
        comp_dir = SYSTEM_DIR / "CompositeControls"
        if comp_dir.is_dir():
            for f in sorted(comp_dir.glob("*.vml")):
                if f.stem.startswith("Dummy") or f.read_text(errors="ignore").lstrip().startswith("<"):
                    continue
                out.append({"name": f.stem, "category": "Composite", "container": False, "group": "Your controls"})
        groups = [g for g, _ in self.ADD_GROUPS] + ["More", "Your controls"]
        place = {n: i for _, names in self.ADD_GROUPS for i, n in enumerate(names)}
        return json.dumps(sorted(out, key=lambda t: (groups.index(t["group"]), place.get(t["name"], 99), t["name"])))

    def cmd_AddDesignControl(self, ctype, x=0, y=0, surface="Surface"):
        """Add a control where the user right-clicked: inside a Frame if the click was in one."""
        surf = self._surface(surface)
        view = surf.widget
        from PySide6.QtCore import QPoint
        page_pt = view.form.pos() + QPoint(int(float(x or 0)), int(float(y or 0)))
        container = view.container_at(page_pt) or surf
        if ctype in ("Toolbar", "StatusBar"):          # these belong to the form itself, wherever it was right-clicked
            container = surf
        if container is not surf:
            local = container.widget.mapFrom(view.page, page_pt)
            x, y = local.x(), local.y()
        if ctype == "TabPage":                      # a page goes on the tab strip that was right-clicked, as its last tab
            strip = container.parent if container.type.name == "TabPage" else container
            if strip is None or strip.type.name != "TabStrip":
                self.cmd_InfoDialog("Right-click on a tab strip to add a page to it.", "Add a page")
                return ""
            name = self._unique("TabPage")
            self.cmd_CreateControl("TabPage", name, strip.name)
            self.cmd_SetProperty(name, "Header", f"Tab {len(strip.widget.pages())}")
            self.cmd_SetProperty(strip.name, "SelectedIndex", str(len(strip.widget.pages()) - 1))
            surf.widget.select(name, user=True)
            surf.widget.emit("OnChanged", {"selected_control": name})
            return name
        name = self._unique(ctype)
        if self.cmd_CreateControl(ctype, name, container.name) == "Failed":
            return ""
        defaults = dict(DESIGN_DEFAULTS.get(ctype, {}))
        if ctype == "Frame":
            defaults["Text"] = ""
        for key in ("Content", "Text"):
            if key in defaults and ctype in ("Button", "CheckBox", "RadioButton", "TextBlock", "Frame"):
                defaults[key] = name
        snap = surf.widget.snap
        defaults["Canvas.Left"], defaults["Canvas.Top"] = str(snap(float(x or 0))), str(snap(float(y or 0)))
        box = container.widget if container is not surf else view.form
        if ctype == "StatusBar":                    # along the foot of the form, full width, staying there as it's resized
            h = int(float(defaults.get("Height", 26)))
            defaults.update({"Canvas.Left": "0", "Canvas.Top": str(max(0, box.height() - h)), "Width": str(box.width())})
        if ctype == "Toolbar":                      # along the top, full width
            defaults.update({"Canvas.Left": "0", "Canvas.Top": "0", "Width": str(box.width())})
        for k, v in defaults.items():
            self.cmd_SetProperty(name, k, v)
        if ctype == "TabStrip":                     # two pages to start with
            for k in (1, 2):
                page = self._unique("TabPage")
                self.cmd_CreateControl("TabPage", page, name)
                self.cmd_SetProperty(page, "Header", f"Tab {k}")
            self.cmd_SetProperty(name, "SelectedIndex", "0")
        surf.widget.select(name, user=True)
        surf.widget.emit("OnChanged", {"selected_control": name})
        return name

    # ---- Tools > Add a control: controls stacked down the form's left, for those who never right-click
    STACK_GAP, STACK_COL = 8, 180

    def cmd_AddStackedControl(self, ctype, surface="Surface"):
        """Put a control on the form, stacked down the left: top first, each under the last one added (a new column
        when the form's full), started again when the last one added has gone. Then drag it where it belongs."""
        surf = self._surface(surface)
        x, y, last = getattr(self, "_stack", (16, 16, ""))
        if not last or self.find(last) is None:
            x, y = 16, 16
        name = self.cmd_AddDesignControl(ctype, x, y, surface)
        if not name:
            return ""
        if ctype not in ("Toolbar", "StatusBar"):          # (those go along the top and foot, not in the stack)
            node = self.find(name)
            try:
                h = int(float(node.props.get("Height") or 0))
            except ValueError:
                h = 0
            h = h or (node.widget.height() if node.widget is not None else 30)
            y += h + self.STACK_GAP
            if y + 24 > surf.widget.form.height():
                x, y = x + self.STACK_COL, 16
            self._stack = (x, y, name)
        self.cmd_SetStatusText(f"Added {name}")
        return name

    # ---- undo and redo: the whole design, as the VML it saves as, after each change (the save and open that are
    # used every day, so a step back is exactly what was there). New and Open start the list again.
    UNDO_MAX = 200

    def _design_text(self, surface):
        if not getattr(self, "_undo_file", None):
            fd, self._undo_file = tempfile.mkstemp(prefix="vml-undo-", suffix=".vml")
            os.close(fd)
        self._hush = True                                  # (no "saved" in the log for this)
        try:
            self.cmd_ExportVml(surface, self._undo_file)
        finally:
            self._hush = False
        return Path(self._undo_file).read_text(encoding="utf-8")

    def _history(self, surface):
        if not hasattr(self, "_undo"):
            self._undo = {}
        return self._undo.setdefault(surface, {"states": [], "at": -1})

    def cmd_UndoReset(self, surface="Surface"):
        """Start the undo list again from the design as it is (a new form, one just opened)."""
        if getattr(self, "_restoring", False):
            return ""
        h = self._history(surface)
        h["states"], h["at"] = [self._design_text(surface)], 0
        return ""

    def cmd_UndoMark(self, surface="Surface"):
        """The design has changed: remember it, so Undo can come back to it (and forget what Redo had)."""
        if getattr(self, "_restoring", False):
            return ""
        h = self._history(surface)
        text = self._design_text(surface)
        if h["states"] and h["states"][h["at"]] == text:          # (a click that only selected something)
            return ""
        if not h["states"]:
            h["states"], h["at"] = [text], 0
            return ""
        del h["states"][h["at"] + 1:]
        h["states"].append(text)
        if len(h["states"]) > self.UNDO_MAX:
            del h["states"][0]
        h["at"] = len(h["states"]) - 1
        return ""

    def cmd_CanUndo(self, surface="Surface"):
        return "true" if self._history(surface)["at"] > 0 else "false"

    def cmd_CanRedo(self, surface="Surface"):
        h = self._history(surface)
        return "true" if 0 <= h["at"] < len(h["states"]) - 1 else "false"

    def cmd_Undo(self, surface="Surface"):
        h = self._history(surface)
        if h["at"] <= 0:
            return ""
        h["at"] -= 1
        return self._restore(surface, h["states"][h["at"]])

    def cmd_Redo(self, surface="Surface"):
        h = self._history(surface)
        if h["at"] >= len(h["states"]) - 1:
            return ""
        h["at"] += 1
        return self._restore(surface, h["states"][h["at"]])

    def _restore(self, surface, text):
        surf = self._surface(surface)
        selected = str(self.cmd_GetProperty(surf.name, "Selected") or "")
        group = [n for n in str(self.cmd_GetProperty(surf.name, "SelectedAll") or "").split(",") if n]
        Path(self._undo_file).write_text(text, encoding="utf-8")
        self._restoring, self._hush = True, True
        try:
            self.cmd_ImportVml(self._undo_file, surface)
            keep = [n for n in (group or [selected]) if n and self.find(n) is not None]   # (a group stays a group)
            surf.widget.select_group(keep)
            surf.widget.emit("OnChanged", {"selected_control": keep[0] if keep else ""})
        finally:
            self._restoring, self._hush = False, False
        return "true"

    # ---- cut, copy and paste: a control (and whatever's inside it), its properties and its scripts. On the
    # clipboard as text too, so it pastes into another Visualised designer.
    CLIP_MARK = "VML-CONTROLS:"

    def _control_spec(self, node):
        ctype = getattr(node, "template", None) or node.type.name
        spec = {"type": ctype, "name": node.name,
                "props": {k: v for k, v in node.props.items() if k not in ("Name", "X", "Y")},
                "scripts": {ev: list(s) for ev, s in getattr(node, "design_scripts", {}).items()}, "children": []}
        if node.type.container and not getattr(node, "template", None):
            spec["children"] = [self._control_spec(k) for k in node.children]
        return spec

    def cmd_CopyControl(self, names):
        """Copy controls (and what's inside them) for Paste: one name, or several comma-separated (a group).
        One that's inside another being copied goes with it, not twice."""
        nodes = [self.find(n.strip()) for n in str(names or "").split(",")
                 if n.strip() and not n.strip().startswith("menu:") and n.strip() != "menubar"]
        nodes = [n for n in nodes if n is not None]
        def inside(n, others):
            p = n.parent
            while p is not None:
                if p in others:
                    return True
                p = p.parent
            return False
        nodes = [n for n in nodes if not inside(n, nodes)]
        if not nodes:
            return ""
        self._clip, self._pastes = [self._control_spec(n) for n in nodes], 0
        self.cmd_ClipboardSet(self.CLIP_MARK + json.dumps(self._clip))
        return "true"

    def _clip_spec(self):
        text = self.cmd_ClipboardGet() or ""
        if text.startswith(self.CLIP_MARK):
            try:
                spec = json.loads(text[len(self.CLIP_MARK):])
                spec = spec if isinstance(spec, list) else [spec]
                if spec != getattr(self, "_clip", None):
                    self._clip, self._pastes = spec, 0
            except ValueError:
                pass
        return getattr(self, "_clip", None)

    def cmd_CanPaste(self):
        return "true" if self._clip_spec() else "false"

    def _make_from_spec(self, spec, parent):
        name = self._unique(spec["type"])
        if self.cmd_CreateControl(spec["type"], name, parent) == "Failed":
            return ""
        for k, v in spec["props"].items():
            if k in ("Text", "Content") and v == spec["name"]:   # (a button still called Button1 becomes Button2)
                v = name
            self.cmd_SetProperty(name, k, v)
        for event, (interp, code) in spec.get("scripts", {}).items():
            self.cmd_SetDesignScript(name, event, interp, code)
        for kid in spec.get("children", []):
            self._make_from_spec(kid, name)
        return name

    def cmd_PasteControl(self, x="", y="", surface="Surface"):
        """Paste what was copied: where the form was right-clicked (x, y), or a step down and right of the original.
        A group keeps its shape. What's pasted is selected (all of it), and its names are the answer, comma-separated."""
        specs = self._clip_spec()
        if not specs:
            return ""
        surf = self._surface(surface)
        specs = json.loads(json.dumps(specs))
        pos = lambda s, k: int(float(s["props"].get(k, 0) or 0))
        if x not in ("", None) and y not in ("", None):             # the group's top-left goes where it was clicked
            left, top = min(pos(s, "Canvas.Left") for s in specs), min(pos(s, "Canvas.Top") for s in specs)
            dx, dy = surf.widget.snap(float(x)) - left, surf.widget.snap(float(y)) - top
        else:
            self._pastes = getattr(self, "_pastes", 0) + 1
            dx = dy = 16 * self._pastes
        for s in specs:
            s["props"]["Canvas.Left"], s["props"]["Canvas.Top"] = str(pos(s, "Canvas.Left") + dx), str(pos(s, "Canvas.Top") + dy)
        names = [n for n in (self._make_from_spec(s, surf.name) for s in specs) if n]
        if names:
            surf.widget.select_group(names)
            surf.widget.emit("OnChanged", {"selected_control": names[0]})
        return ",".join(names)

    # ---- lining a group up (right-click > Align): left, centre, right, top, middle, bottom; spaced evenly; the
    # same size; or Tidy, which makes a neat column (or a row, if they're spread across) with even gaps
    ALIGN_GAP = 8

    def cmd_AlignControls(self, how, surface="Surface"):
        surf = self._surface(surface)
        view = surf.widget
        nodes = view.group()
        if len(nodes) < 2:
            return ""
        how = str(how).lower()
        r = {n.name: QRect(n.host.geometry()) for n in nodes}
        left, top = min(g.left() for g in r.values()), min(g.top() for g in r.values())
        right, bottom = max(g.right() for g in r.values()), max(g.bottom() for g in r.values())
        sized = {}
        if how == "tidy":                                 # the way they mostly run (by their middles): a column, or a row
            xs, ys = [g.center().x() for g in r.values()], [g.center().y() for g in r.values()]
            how = "row" if (max(xs) - min(xs)) > (max(ys) - min(ys)) else "column"
        if how == "column":
            y = top
            for n in sorted(nodes, key=lambda n: (r[n.name].top(), r[n.name].left())):
                r[n.name].moveTo(left, y)
                y += r[n.name].height() + self.ALIGN_GAP
        elif how == "row":
            x = left
            for n in sorted(nodes, key=lambda n: (r[n.name].left(), r[n.name].top())):
                r[n.name].moveTo(x, top)
                x += r[n.name].width() + self.ALIGN_GAP
        elif how in ("left", "right", "centre", "center"):
            mid = (left + right) // 2
            for g in r.values():
                g.moveLeft(left if how == "left" else right - g.width() + 1 if how == "right" else mid - g.width() // 2)
        elif how in ("top", "bottom", "middle"):
            mid = (top + bottom) // 2
            for g in r.values():
                g.moveTop(top if how == "top" else bottom - g.height() + 1 if how == "bottom" else mid - g.height() // 2)
        elif how in ("across", "down"):                    # the first and last stay; the gaps between come out even
            key = (lambda n: r[n.name].left()) if how == "across" else (lambda n: r[n.name].top())
            order = sorted(nodes, key=key)
            span = (lambda g: g.width()) if how == "across" else (lambda g: g.height())
            room = (right - left + 1 if how == "across" else bottom - top + 1) - sum(span(r[n.name]) for n in order)
            gap, at = room / (len(order) - 1), (left if how == "across" else top)
            for n in order:
                g = r[n.name]
                g.moveLeft(round(at)) if how == "across" else g.moveTop(round(at))
                at += span(g) + gap
        elif how in ("width", "height"):                    # the same size as the one the properties show
            first = r[nodes[0].name]
            for n in nodes[1:]:
                sized[n.name] = (first.width(), r[n.name].height()) if how == "width" else (r[n.name].width(), first.height())
        else:
            return ""
        for name, (w, h) in sized.items():
            self.cmd_SetProperty(name, "Width", str(w))
            self.cmd_SetProperty(name, "Height", str(h))
        view.commit_group({name: QRect(max(0, g.x()), max(0, g.y()), g.width(), g.height()) for name, g in r.items()})
        return "true"

    def cmd_DuplicateControl(self, name):
        node = self._node(name)
        surf = node.parent
        ctype = getattr(node, "template", None) or node.type.name
        new = self._unique(ctype)
        self.cmd_CreateControl(ctype, new, surf.name)
        for k, v in node.props.items():
            if k not in ("Name", "X", "Y"):
                self.cmd_SetProperty(new, k, v)
        for k in ("Canvas.Left", "Canvas.Top"):
            self.cmd_SetProperty(new, k, str(int(float(node.props.get(k, 0) or 0)) + 16))
        for event, (interp, code) in getattr(node, "design_scripts", {}).items():
            self.cmd_SetDesignScript(new, event, interp, code)
        if surf is not None and surf.type.name == "DesignSurface":
            surf.widget.select(new, user=True)
            surf.widget.emit("OnChanged", {"selected_control": new})
        return new

    def cmd_SetParent(self, name, parent_name):
        """Move a control into another container (or back onto the form), keeping its place on screen."""
        node, new_parent = self._node(name), self._node(parent_name)
        old_parent = node.parent
        if new_parent is old_parent or new_parent is node:
            return False
        p = new_parent
        while p is not None:                                  # never into itself or its own children
            if p is node:
                return False
            p = p.parent
        from PySide6.QtCore import QPoint
        screen_pos = node.host.mapToGlobal(QPoint(0, 0))
        if old_parent is not None:
            if old_parent.type.remove_child:
                old_parent.type.remove_child(old_parent, node)
            old_parent.children.remove(node)
        target = new_parent.widget.form if new_parent.type.name == "DesignSurface" else new_parent.widget
        local = target.mapFromGlobal(screen_pos)
        node.props["Canvas.Left"], node.props["Canvas.Top"] = str(max(0, local.x())), str(max(0, local.y()))
        node.parent = new_parent
        new_parent.children.append(node)
        new_parent.type.add_child(new_parent, node)
        for k in ("Canvas.Left", "Canvas.Top"):
            self.store.set_prop(node.cid, k, node.props[k])
        if node.cid is not None:
            self.store.db.execute("UPDATE ui_tree SET parent_id=? WHERE id=?", (new_parent.cid, node.cid))
        for listener in list(self.listeners):
            listener(node.name, "Canvas.Left", node.props["Canvas.Left"])
            listener(node.name, "Canvas.Top", node.props["Canvas.Top"])
        return True

    def cmd_RenameControl(self, old, new):
        surf, items, i = self._menu_item(old)
        if i is not None:                                   # renaming a menu item
            new = str(new).strip()
            if not re.fullmatch(r"[A-Za-z_]\w*", new) or any(it["name"] == new for it in items):
                return False
            items[i]["name"] = new
            surf.widget.set_menu(items)
            surf.widget.selected = "menu:" + new
            surf.widget.emit("OnChanged", {"selected_control": "menu:" + new})
            return True
        node = self._node(old)
        new = str(new).strip()
        if not re.fullmatch(r"[A-Za-z_]\w*", new) or self.find(new, node.scope) is not None:
            log(f"RenameControl: '{new}' isn't a valid, unused name")
            return False
        nodes = self.scopes[node.scope]
        nodes[new] = nodes.pop(old)
        node.name = new
        node.widget.setObjectName(css_id(new))
        from .registry import restyle
        restyle(node)
        if node.cid is not None:
            self.store.db.execute("UPDATE ui_tree SET name=? WHERE id=?", (new, node.cid))
        if node.parent is not None and node.parent.type.name == "DesignSurface" and node.parent.widget.selected == old:
            node.parent.widget.selected = new
            node.parent.widget.emit("OnChanged", {"selected_control": new})
        if self.current_control == old:
            self.current_control = new
        return True

    def cmd_SetTabs(self, strip_name, spec):
        """A tab strip's pages, in tab order: JSON [{"page": its name, or "" for a new one, "header": its words}].
        A page left out is deleted, with what's on it. The designer's Edit Tabs box uses this."""
        strip = self._node(strip_name)
        want = json.loads(spec) if isinstance(spec, str) else spec
        have = {p.name: p for p in strip.widget.pages()}
        keep = {w.get("page") for w in want if w.get("page") in have}
        for name, page in have.items():
            if name not in keep:
                self.delete(name, page.scope)
        order = []
        for w in want:
            name = w.get("page") if w.get("page") in have else ""
            if not name:
                name = self._unique("TabPage")
                self.cmd_CreateControl("TabPage", name, strip.name)
            self.cmd_SetProperty(name, "Header", str(w.get("header") or name))
            order.append(self.find(name, strip.scope))
        strip.children[:] = [p for p in order if p is not None] + [c for c in strip.children if c.type.name != "TabPage"]
        strip.widget.select(strip.widget.wanted)
        surf = strip
        while surf is not None and surf.type.name != "DesignSurface":
            surf = surf.parent
        if surf is not None:
            surf.widget.emit("OnChanged", {"selected_control": strip.name})
        return "true"

    def cmd_BringToFront(self, name):
        node = self._node(name)
        if node.parent is not None:
            node.parent.children.remove(node)
            node.parent.children.append(node)
        node.host.raise_()
        if node.parent is not None and node.parent.type.name == "DesignSurface":
            node.parent.widget.overlay.raise_()
            node.parent.widget.emit("OnChanged", {"selected_control": name})

    def cmd_SendToBack(self, name):
        node = self._node(name)
        if node.parent is not None:
            node.parent.children.remove(node)
            node.parent.children.insert(0, node)
        node.host.lower()
        if node.parent is not None and node.parent.type.name == "DesignSurface":
            node.parent.widget.emit("OnChanged", {"selected_control": name})

    def cmd_ClearDesign(self, surface="Surface"):
        surf = self._surface(surface)
        for kid in list(surf.children):
            self.delete(kid.name, kid.scope)
        surf.widget.select("")
        surf.menu_scripts = {}
        surf.design_scripts, surf.form_scripts = {}, {}
        surf.export_names, surf.carried = {}, []
        for ev in ("OnOpened", "OnClosing", "OnKeyDown", "OnKeyUp", "OnResized", "OnActivated"):
            surf.props.pop(ev, None)
        for prop in ("FormBorder", "FormBorderThickness", "FormTitleBar", "FormTitleBackground", "FormResizable", "FormModal", "FormMinWidth", "FormMinHeight", "FormMaxWidth", "FormMaxHeight",
                     *(p for _, p in self.APP_KEYS)):
            if surf.props.get(prop):                         # the last form's window options don't carry over
                self.cmd_SetProperty(surf.name, prop, "")
        surf.widget.menu_settings = {}
        surf.widget.set_menu([])
        surf.widget.apply_menu_settings()
        for k, v in (("FormName", "Form1"), ("FormTitle", "Form1"), ("FormWidth", "640"), ("FormHeight", "480"),
                     ("FormBackground", "#ffffff"), ("FormTitleBar", "Own")):    # a new form wears its own title bar
            self.cmd_SetProperty(surf.name, k, v)
        if not getattr(self, "_importing", False):
            self.cmd_UndoReset(surf.name)

    # What a form says about the app it is, in its @Window, and the designer's name for each: read when a form is
    # opened and written back when it is saved, so a form keeps its version, picture and the rest through the designer.
    APP_KEYS = (("Version", "FormVersion"), ("Icon", "FormIcon"), ("WebAddress", "FormWebAddress"), ("PhoneFit", "FormPhoneFit"), ("WebFit", "FormWebFit"),
                ("AndroidPackage", "FormAndroidPackage"), ("AndroidKey", "FormAndroidKey"))

    def cmd_ExportVml(self, surface, path):
        """Write the designed form as VML: a Window holding a Canvas holding the controls."""
        surf = self._surface(surface)
        g = lambda k, d: str(self.cmd_GetProperty(surf.name, k) or d)
        form, canvas = g("FormName", "Form1"), g("FormName", "Form1") + "Canvas"
        menu = surf.widget.menu_items
        mh = surf.widget.menu_h()
        # the #! line lets a form run as a program on Linux and macOS once it's made executable (chmod +x): left to
        # the user, as with any script. Windows and VML itself read it as a comment.
        out = ["#!/usr/bin/env vml", f"# {form}: designed in the VML designer", "", f"@Window {form}", f"Title={g('FormTitle', form)}",
               f"Width={g('FormWidth', 640)}", f"Height={int(float(g('FormHeight', 480))) + mh}", ""]
        settings = {k: v for k, v in surf.widget.menu_settings.items() if v not in ("", None)}
        if menu:
            out += [f"@DockPanel {form}Root", f"Parent={form}", "",
                    f"@TinyMenu {form}Menu", f"Parent={form}Root", "DockPanel.Dock=Top"]
            if str(settings.get("OpenOnHover", "")).lower() == "true":
                out.append("OpenOnHover=true")
            out.append("")
        theme = {k: v for k, v in settings.items() if k != "OpenOnHover"}
        if theme:                                       # (kept with or without a menu bar: it colours the form's dialogs too)
            out += [f"@MenuTheme {form}MenuTheme", *([] if menu else [f"Parent={form}"]), *[f"{k}={v}" for k, v in theme.items()], ""]
        out += [f"@Canvas {canvas}", f"Parent={form + 'Root' if menu else form}", f"Background={g('FormBackground', '#ffffff')}"]
        for key, prop in (("Resizable", "FormResizable"), ("Modal", "FormModal"), ("MinWidth", "FormMinWidth"),
                          ("MinHeight", "FormMinHeight"), ("MaxWidth", "FormMaxWidth"), ("MaxHeight", "FormMaxHeight"),
                          ("BorderBrush", "FormBorder"), ("BorderThickness", "FormBorderThickness"), ("TitleBar", "FormTitleBar"), ("TitleBackground", "FormTitleBackground"),
                          *self.APP_KEYS,
                          ("OnOpened", "OnOpened"), ("OnClosing", "OnClosing"), ("OnKeyDown", "OnKeyDown"), ("OnKeyUp", "OnKeyUp"),
                          ("OnResized", "OnResized"), ("OnActivated", "OnActivated")):
            v = str(surf.props.get(prop, "") or "")
            if v and not (key == "Resizable" and v == "true") and not (key == "Modal" and v == "false") \
                    and not (key == "TitleBar" and v == "Own"):
                end = out.index("", out.index(f"@Window {form}"))   # the end of the window's own lines
                out.insert(end, f"{key}={v}")
        first = ["Canvas.Left", "Canvas.Top", "Width", "Height"]
        real = lambda n: getattr(surf, "export_names", {}).get(n, n)   # a working name back to the form's own name

        def walk(container, parent_name):              # every control, however deep: a canvas in a canvas keeps its own
            for kid in container.children:
                yield kid, parent_name
                if kid.type.container and kid.children:
                    yield from walk(kid, kid.name)
        everything = list(walk(surf, canvas))
        for kid, parent_name in everything:
            ctype = getattr(kid, "template", None) or kid.type.name
            skip = dict(self.templates[ctype].parts[0][3]) if ctype in self.templates else {}
            out += ["", f"@{ctype} {real(kid.name)}", f"Parent={real(parent_name)}"]
            keys = [k for k in first if k in kid.props] + sorted(k for k in kid.props if k not in first)
            for k in keys:
                v = str(kid.props.get(k, ""))
                if k in ("Name", "X", "Y", "IsHitTestVisible", "Focusable") or v == "" or skip.get(k) == v:
                    continue
                out.append(f"{k}={v.replace(chr(10), ' ')}")
        for ctype, name, parent, cprops in getattr(surf, "carried", []):     # right-click menus and styles, exactly as they came
            if ctype == "Style":
                out += ["", f"@Style {name}", "<<CSS", *str(cprops.get("Content", "")).rstrip("\n").split("\n"), "CSS"]
                continue
            out += ["", f"@{ctype} {name}"] + ([f"Parent={parent}"] if parent else [])
            out += [f"{k}={str(v).replace(chr(10), ' ')}" for k, v in cprops.items() if str(v) != ""]
        parents = {}
        for it in menu:                                 # top-level items go on the menu bar; others under their parent
            parents[it["level"]] = it["name"]
            out += ["", f"@MenuItem {it['name']}", f"Parent={'MenuBar' if it['level'] == 0 else parents[it['level'] - 1]}"]
            if it["separator"]:
                out.append("IsSeparator=true")
                continue
            out.append(f"Text={it['text']}")
            if it["shortcut"]:
                out.append(f"Shortcut={it['shortcut']}")
            if not it["enabled"]:
                out.append("IsEnabled=false")
            if it.get("onclick"):
                out.append(f"OnClick={it['onclick']}")
        for handler, (interp, code) in getattr(surf, "menu_scripts", {}).items():
            if any(it.get("onclick") == handler for it in menu):
                term = "END_" + re.sub(r"\W", "_", handler).upper()
                out += ["", f"@Script {handler}", f"Interpreter={interp}", f"<<{term}", *code.rstrip("\n").split("\n"), term]
        written = set()
        for kid in [surf] + [k for k, _ in everything]:
            for event, (interp, code) in getattr(kid, "design_scripts", {}).items():
                name = kid.props.get(event) or f"{real(kid.name)}_{event}"
                term = "END_" + re.sub(r"\W", "_", name).upper()
                out += ["", f"@Script {name}", f"Interpreter={interp}", f"<<{term}", *code.rstrip("\n").split("\n"), term]
                written.add(name)
        for name, (interp, code) in getattr(surf, "form_scripts", {}).items():   # helpers other scripts call
            if name not in written:
                term = "END_" + re.sub(r"\W", "_", name).upper()
                out += ["", f"@Script {name}", f"Interpreter={interp}", f"<<{term}", *code.rstrip("\n").split("\n"), term]
        if re.search(r"""["']Link(Pair)?["']""", "\n".join(out)):               # an app that uses Link goes out with its maker's pass
            carry = licences.link_pass()
            if carry:
                out.insert(out.index("", out.index(f"@Window {form}")), f"LinkPass={carry}")
        Path(os.path.expanduser(path)).write_text("\n".join(out) + "\n", encoding="utf-8")
        if not getattr(self, "_hush", False):
            log(f"saved {len(everything)} controls to {path}")
        return True

    def cmd_ImportVml(self, path, surface="Surface"):
        """Open a VML form for editing: its Window becomes the form, its Canvas's controls the design."""
        self._importing = True
        try:
            done = self._import_vml(path, surface)
        finally:
            self._importing = False
        if done is not False:
            self.cmd_UndoReset(surface)                     # (a form just opened: nothing to undo yet)
        return done

    def _import_vml(self, path, surface="Surface"):
        surf = self._surface(surface)
        rows, props, scripts = self.store.parse_form(os.path.expanduser(path))
        while PARSER_LOG:
            line = PARSER_LOG.pop(0)
            if not getattr(self, "_hush", False):        # (an undo or redo opens the design quietly)
                log(line)
        window = next((r for r in rows if r[2] == "Window"), None)
        canvas = next((r for r in rows if window and r[1] == window[0] and r[2] == "Canvas"), None)
        if window is not None and canvas is None:            # a form with a menu: Window > DockPanel > Canvas
            dock = next((r for r in rows if r[1] == window[0] and r[2] == "DockPanel"), None)
            canvas = next((r for r in rows if dock and r[1] == dock[0] and r[2] == "Canvas"), None)
        notes = None
        if window is not None and canvas is None:           # laid out with panels: measure it and put it on a canvas
            from .flatten import layout_to_canvas
            flat = layout_to_canvas(self, path, rows, props, scripts, window, log)
            if flat:
                rows, props, canvas, notes = flat
        self.store.set_setting("import_converted", "true" if notes else "false")
        self.store.set_setting("import_notes", "")
        if window is None or canvas is None:
            log(f"{path}: couldn't be opened as a form (no Window, or its layout couldn't be measured)")
            return False
        # A designed control with the same name as one of the designer's own (Root, Props, ...) would be mistaken for
        # it, so it gets a new name here, and the scripts that address it by name follow.
        rows, own, renamed = list(rows), self.scopes.get(surf.scope, {}), {}
        taken = {r[3] for r in rows}
        for i, (cid, parent_id, ctype, name) in enumerate(rows):
            if name in own and cid not in (window[0], canvas[0]) and ctype not in ("MenuItem", "MenuTheme", "TinyMenu", "ContextMenu"):
                n = 2
                while f"{name}{n}" in own or f"{name}{n}" in taken:
                    n += 1
                renamed[name] = f"{name}{n}"
                taken.add(renamed[name])
                rows[i] = (cid, parent_id, ctype, renamed[name])
        if renamed:
            log("shown under a working name, because the designer has controls of its own with these names "
                "(they are saved under their real names): " + ", ".join(f"{a} as {b}" for a, b in renamed.items()))
        # Right-click menus aren't something the designer edits yet: carry them through untouched, so that saving
        # the form doesn't lose them (and so their items don't turn up on the form's menu bar).
        by_row = {r[0]: r for r in rows}
        def in_context_menu(cid):
            while cid in by_row:
                if by_row[cid][2] == "ContextMenu":
                    return True
                cid = by_row[cid][1]
            return False
        carried_ids = {r[0] for r in rows if (r[2] in ("ContextMenu", "MenuItem") and in_context_menu(r[0])) or r[2] == "Style"}
        carried = [(r[2], r[3], by_row[r[1]][3] if r[1] in by_row else None, dict(props.get(r[0], {})))
                   for r in rows if r[0] in carried_ids]
        self.cmd_ClearDesign(surf.name)
        surf.export_names, surf.carried = {new: old for old, new in renamed.items()}, carried
        from . import styles as _styles
        for ctype, sname, _parent, sprops in carried:          # shared styles: the design shows them, the save keeps them
            if ctype == "Style":
                self.styles[sname] = _styles.parse(sprops.get("Content", ""))
        wp, cp = props[window[0]], props[canvas[0]]
        by_id, menu = {r[0]: r for r in rows}, []
        for cid, parent_id, ctype, name in rows:
            if ctype != "MenuItem" or cid in carried_ids:
                continue
            level, p_id = 0, parent_id
            while p_id in by_id and by_id[p_id][2] == "MenuItem":
                level, p_id = level + 1, by_id[p_id][1]
            mp = props[cid]
            item = {"name": name, "text": mp.get("Text", ""), "shortcut": mp.get("Shortcut", ""), "level": level,
                    "separator": mp.get("IsSeparator", "").lower() == "true", "enabled": mp.get("IsEnabled", "true").lower() != "false"}
            if mp.get("OnClick") in scripts:
                surf.menu_scripts = getattr(surf, "menu_scripts", {})
                surf.menu_scripts[mp["OnClick"]] = scripts[mp["OnClick"]]
                item["onclick"] = mp["OnClick"]
            menu.append(item)
        settings = {}
        for cid, parent_id, ctype, name in rows:
            if ctype == "MenuTheme":
                settings.update(props[cid])
            elif ctype == "TinyMenu" and props[cid].get("OpenOnHover"):
                settings["OpenOnHover"] = props[cid]["OpenOnHover"]
        surf.widget.menu_settings = settings
        surf.widget.set_menu(menu)
        surf.widget.apply_menu_settings()
        if menu:
            wp = dict(wp, Height=str(int(float(wp.get("Height", 480))) - surf.widget.menu_h()))
        for k, v in (("FormName", window[3]), ("FormTitle", wp.get("Title", window[3])),
                     ("FormWidth", wp.get("Width", "640")), ("FormHeight", wp.get("Height", "480")),
                     ("FormBackground", cp.get("Background", "#ffffff"))):
            self.cmd_SetProperty(surf.name, k, v)
        for key, prop in (("Resizable", "FormResizable"), ("Modal", "FormModal"), ("MinWidth", "FormMinWidth"),
                          ("MinHeight", "FormMinHeight"), ("MaxWidth", "FormMaxWidth"), ("MaxHeight", "FormMaxHeight"),
                          ("BorderBrush", "FormBorder"), ("BorderThickness", "FormBorderThickness"), ("TitleBar", "FormTitleBar"), ("TitleBackground", "FormTitleBackground"),
                          *self.APP_KEYS):
            if wp.get(key):
                self.cmd_SetProperty(surf.name, prop, wp[key])
        if not wp.get("TitleBar"):
            self.cmd_SetProperty(surf.name, "FormTitleBar", "Own")        # (our own title bar is the default now)
        count, placed = 0, {canvas[0]: surf.name}
        for cid, parent_id, ctype, name in rows:               # parents always come before their children
            if parent_id not in placed:
                continue
            if self.cmd_CreateControl(ctype, name, placed[parent_id]) == "Failed":
                continue
            placed[cid] = name
            node = self.find(name)
            for k, v in props[cid].items():
                if k in node.type.events and v in scripts:
                    node.design_scripts = getattr(node, "design_scripts", {})
                    node.design_scripts[k] = scripts[v]
                    self.cmd_SetEvent(name, k, v)
                else:
                    self.cmd_SetProperty(name, k, v)
            count += 1
        used = set()
        for cid, parent_id, ctype, name in rows:
            if cid in carried_ids:                           # their scripts are kept with the form's own
                continue
            for k, v in props.get(cid, {}).items():
                if v in scripts:
                    used.add(v)
        surf.design_scripts = {}
        for ev in ("OnOpened", "OnClosing", "OnKeyDown", "OnKeyUp", "OnResized", "OnActivated"):
            handler = wp.get(ev)
            if handler and handler in scripts:
                surf.design_scripts[ev] = scripts[handler]
                self.cmd_SetEvent(surf.name, ev, handler)
            elif handler:                                    # a module's function, or Name(arguments): kept as written
                self.cmd_SetEvent(surf.name, ev, handler)
        surf.form_scripts = {n: v for n, v in scripts.items() if n not in used}
        if hasattr(surf.widget, "arrange_layers"):
            surf.widget.arrange_layers(fresh=True)
        if not getattr(self, "_hush", False):
            log(f"opened {path}: {count} controls")
        if notes:
            said = [f"Converted from a panel layout: {notes['controls']} controls placed, {notes['frames']} panels kept as "
                    f"frames, {notes['dissolved']} layout-only panels removed."]
            if notes["hidden"]:
                said.append("Starts hidden, so check where it sits: " + ", ".join(notes["hidden"]) + ".")
            if notes["partial"]:
                said.append("Shared space in proportion, which anchors can't do exactly: " + ", ".join(notes["partial"]) + ".")
            if notes["scroll"]:
                said.append("Scrolling areas were flattened: " + ", ".join(notes["scroll"]) + ".")
            if renamed:
                said.append("Shown under a working name because the designer has its own control of that name (saved "
                            "under the real name): " + ", ".join(f"{a} as {b}" for a, b in renamed.items()) + ".")
            self.store.set_setting("import_notes", " ".join(said))
            log(" ".join(said))
        return True



    # --- the designed form's menu (the Menu Editor's side)
    def _menu_slug(self, text):
        base = re.sub(r"[^A-Za-z0-9]", "", str(text).replace("&", "")) or "Item"
        return "mnu" + base[0].upper() + base[1:]

    def cmd_ImportForm(self, kind, path, surface="Surface"):
        """Bring a form made in another tool onto the design surface, using an importer from the library. kind: the
        importer's name ("WinForms", "VB6"), or "" to go by the file's ending. Returns "true" if it opened; the
        setting import_notes then says what was and was not brought across. (Pro.)"""
        source = Path(os.path.expanduser(str(path)))
        name = self.importer_for(kind, source)
        free = bool(name and (self.importers().get(str(name).lower()) or {}).get("free"))   # (VB: free, the way in)
        if not free and not self.needs("import", "Importing forms from other tools"):
            return ""
        if name is None:
            raise ValueError(f"there's no importer for {kind or source.suffix or 'that kind of file'}")
        result = self.run_importer(name, "ImportForm", source.resolve().as_posix(), "") if source.is_file() \
            else {"error": f"{source} isn't a file"}
        text = str(result.get("vml") or "")
        found = re.search(r"^@Window (\w+)", text, re.M)
        if result.get("error") or not found:
            why = result.get("error") or "the importer made nothing that could be opened as a form"
            log(f"{path}: couldn't be imported ({why})")
            self.store.set_setting("import_notes", why)
            return ""
        notes = [str(n) for n in (result.get("notes") or [])]
        folder = Path(tempfile.mkdtemp(prefix="vml-import-"))
        target = folder / f"{found.group(1)}.vml"
        target.write_text(text, encoding="utf-8")
        opened = self.cmd_ImportVml(str(target), surface)
        shutil.rmtree(folder, ignore_errors=True)
        self.store.set_setting("import_converted", "true")          # it is a new form: Save will ask where to put it
        self.store.set_setting("import_notes", "\n\n".join(notes))
        log(f"imported {source.name}: {notes[0] if notes else ''}")
        return "true" if opened else ""

    def cmd_GetDesignMenu(self, surface="Surface"):
        surf = self._surface(surface)
        return json.dumps(surf.widget.menu_items)

    def cmd_SetDesignMenu(self, surface, items_json):
        """Replace the designed form's menu: a flat list of items with indent levels, as in VB's Menu Editor."""
        surf = self._surface(surface)
        try:
            raw = json.loads(items_json) if items_json else []
        except ValueError:
            raw = []
        if isinstance(raw, dict):                     # an empty Lua table encodes as {}
            raw = list(raw.values())
        old = {it["name"]: it for it in surf.widget.menu_items}
        scripts = getattr(surf, "menu_scripts", {})
        items, names, prev_level = [], set(), -1
        for it in raw:
            sep = bool(it.get("separator"))
            text = str(it.get("text", "") or "")
            if not sep and not text.strip():
                continue                               # blank rows are dropped, as VB did
            name = str(it.get("name", "") or "") or (f"mnuSep{len(items) + 1}" if sep else self._menu_slug(text))
            base, n = name, 2
            while name in names:
                name, n = f"{base}{n}", n + 1
            names.add(name)
            level = max(0, min(int(it.get("level", 0) or 0), prev_level + 1, 3))
            prev_level = level
            item = {"name": name, "text": text, "shortcut": str(it.get("shortcut", "") or ""), "level": level,
                    "separator": sep, "enabled": it.get("enabled", True) not in (False, "false", 0)}
            handler = it.get("onclick") or old.get(name, {}).get("onclick") or f"{name}_Click"
            if handler in scripts:
                item["onclick"] = handler
            items.append(item)
        surf.widget.set_menu(items)
        surf.widget.emit("OnChanged", {"selected_control": ""})
        return len(items)

    def _menu_target(self, name):
        """'menu:mnuSave' -> (surface node, item name); otherwise None."""
        if not str(name).startswith("menu:"):
            return None
        surf = next((n for n in self.nodes.values() if n.type.name == "DesignSurface"), None)
        return (surf, str(name)[5:]) if surf is not None else None


    # --- menu items as controls on the design surface ("menu:mnuFile")
    MENU_PROPS = (("Text", "text", "text"), ("Shortcut", "shortcut", "text"), ("IsEnabled", "enabled", "bool"),
                  ("IsSeparator", "separator", "bool"))

    MENUBAR_PROPS = (("Background", "colour"), ("Foreground", "colour"), ("HoverBackground", "colour"),
                     ("HoverForeground", "colour"), ("PopupBackground", "colour"), ("PopupBorder", "colour"),
                     ("OpenOnHover", "bool"))

    def _menubar_surface(self):
        return next((n for n in self.nodes.values() if n.type.name == "DesignSurface"), None)

    def _menubar_props_json(self):
        surf = self._menubar_surface()
        st = surf.widget.menu_settings if surf else {}
        return json.dumps([{"name": p, "value": str(st.get(p, "")), "type": "checkbox" if k == "bool" else
                            ("colour" if k == "colour" else "text"), "kind": k, "group": "Menu bar", "options": []}
                           for p, k in self.MENUBAR_PROPS])

    def _menu_item(self, target):
        mt = self._menu_target(target)
        if not mt:
            return None, None, None
        surf, name = mt
        items = surf.widget.menu_items
        i = next((k for k, it in enumerate(items) if it["name"] == name), None)
        return surf, items, i

    def _menu_get(self, target, prop):
        surf, items, i = self._menu_item(target)
        if i is None:
            return ""
        it = items[i]
        if prop == "Name":
            return it["name"]
        if prop == "OnClick":
            return it.get("onclick", "")
        for p, key, kind in self.MENU_PROPS:
            if p == prop:
                v = it.get(key, "")
                return ("true" if v else "false") if kind == "bool" else str(v)
        return ""

    def _menu_set(self, target, prop, value):
        surf, items, i = self._menu_item(target)
        if i is None:
            return
        for p, key, kind in self.MENU_PROPS:
            if p == prop:
                items[i][key] = truthy(value) if kind == "bool" else str(value)
        surf.widget.set_menu(items)
        surf.widget.emit("OnChanged", {"selected_control": target})
        for listener in list(self.listeners):
            listener(target, prop, value)

    def _menu_props_json(self, target):
        surf, items, i = self._menu_item(target)
        if i is None:
            return "[]"
        out = [{"name": p, "value": self._menu_get(target, p), "type": "checkbox" if kind == "bool" else "text",
                "kind": kind, "group": "Common", "options": []} for p, key, kind in self.MENU_PROPS]
        return json.dumps(out)

    STARTER_MENU = [("mnuFile", "&File", "", 0), ("mnuNew", "&New", "Ctrl+N", 1), ("mnuOpen", "&Open...", "Ctrl+O", 1),
                    ("mnuSave", "&Save", "Ctrl+S", 1), ("mnuSaveAs", "Save &As...", "Ctrl+Shift+S", 1),
                    ("mnuFileSep", "-", "", 1), ("mnuExit", "E&xit", "", 1),
                    ("mnuEdit", "&Edit", "", 0), ("mnuCut", "Cu&t", "Ctrl+X", 1), ("mnuCopy", "&Copy", "Ctrl+C", 1),
                    ("mnuPaste", "&Paste", "Ctrl+V", 1),
                    ("mnuHelp", "&Help", "", 0), ("mnuAbout", "&About...", "", 1)]

    def cmd_MenuAddItem(self, target="", where="after", surface="Surface"):
        """Add a menu item before or after another, as its first submenu item ("child"), at the end of the bar
        ("end"), or, on a form with no menu, start one with the usual File, Edit and Help menus."""
        surf = self._surface(surface)
        items = surf.widget.menu_items
        if not items and not target:
            title = str(surf.props.get("FormTitle") or surf.props.get("FormName") or "Form1").replace('"', "'")
            items[:] = [{"name": n, "text": "" if t == "-" else t, "shortcut": k, "level": lv, "separator": t == "-",
                         "enabled": True} for n, t, k, lv in self.STARTER_MENU]
            surf.menu_scripts = {
                "mnuExit_Click": ("lua", 'Vml("CloseSelf")\n'),
                "mnuAbout_Click": ("lua", f'Vml("InfoDialog", "{title}\\n\\nVersion 1.0\\nMade with VML", "About {title}")\n'),
            }
            for it in items:
                if f"{it['name']}_Click" in surf.menu_scripts:
                    it["onclick"] = f"{it['name']}_Click"
            surf.widget.set_menu(items)
            surf.widget.select("menu:mnuFile", user=True)
            surf.widget.emit("OnChanged", {"selected_control": "menu:mnuFile"})
            return "menu:mnuFile"
        existing = {it["name"] for it in items}
        n = 1
        while f"mnuItem{n}" in existing:
            n += 1
        new = {"name": f"mnuItem{n}", "text": f"Item{n}", "shortcut": "", "level": 0, "separator": False, "enabled": True}
        _, _, i = self._menu_item(target) if target and target != "menubar" else (None, None, None)
        if i is None:
            items.append(new)                              # "end", or the bar's own right-click menu
        else:
            level = items[i]["level"]
            end = i + 1                                    # the end of this item's own submenu
            while end < len(items) and items[end]["level"] > level:
                end += 1
            if where == "before":
                new["level"] = level
                items.insert(i, new)
            elif where == "child":
                new["level"] = min(level + 1, 3)
                items.insert(i + 1, new)
            else:
                new["level"] = level
                items.insert(end, new)
        surf.widget.set_menu(items)
        surf.widget.select("menu:" + new["name"], user=True)
        surf.widget.emit("OnChanged", {"selected_control": "menu:" + new["name"]})
        QTimer.singleShot(0, lambda: surf.widget.reopen_menu_for(new["name"]))
        return "menu:" + new["name"]

    def cmd_MenuDeleteItem(self, target, surface="Surface"):
        """Delete a menu item and everything in its submenu."""
        surf, items, i = self._menu_item(target)
        if i is None:
            return False
        level, end = items[i]["level"], i + 1
        while end < len(items) and items[end]["level"] > level:
            end += 1
        for it in items[i:end]:
            getattr(surf, "menu_scripts", {}).pop(it.get("onclick", ""), None)
        parent = next((items[k]["name"] for k in range(i - 1, -1, -1) if items[k]["level"] < level), None)
        del items[i:end]
        surf.widget.set_menu(items)
        surf.widget.select("", user=True)
        surf.widget.emit("OnChanged", {"selected_control": ""})
        if parent:
            QTimer.singleShot(0, lambda: surf.widget.reopen_menu_for(parent))
        return True

    # --- design scripts (the script editor's side)
    SHELL = "powershell" if sys.platform.startswith("win") else "bash"

    def _lang_interp(self, lang):
        lang = lang.lower()
        if lang == "lua":
            return "lua"
        if lang in ("c#", "csharp", "cs"):
            return "csharp"
        if lang in ("python", "py"):
            return "python"
        return lang if lang in ("bash", "powershell") else self.SHELL

    @staticmethod
    def _lang_label(interp):
        return {"lua": "Lua", "csharp": "C#", "python": "Python"}.get(interp, "Shell")

    def cmd_GetShellName(self):
        return "PowerShell" if self.SHELL == "powershell" else "Bash"

    def cmd_GetControlEvents(self, name):
        mt = self._menu_target(name)
        if mt:
            surf, item = mt
            return json.dumps([{"name": "OnClick", "has_script": f"{item}_Click" in getattr(surf, "menu_scripts", {})}])
        node = self._node(name)
        scripts = getattr(node, "design_scripts", {})
        if node.type.name == "DesignSurface":                # the form itself: the window's events
            events = ["OnOpened", "OnClosing", "OnResized", "OnActivated", "OnKeyDown", "OnKeyUp"]
            return json.dumps([{"name": e, "has_script": e in scripts} for e in events])
        events = sorted(e for e, hook in node.type.events.items() if hook is not None)
        if "OnClick" in events:                       # the one people want first, as in VB
            events.remove("OnClick")
            events.insert(0, "OnClick")
        return json.dumps([{"name": e, "has_script": e in scripts} for e in events])

    def cmd_GetDesignScript(self, name, event):
        mt = self._menu_target(name)
        if mt:
            surf, item = mt
            handler = next((it.get("onclick") for it in surf.widget.menu_items if it["name"] == item and it.get("onclick")),
                           f"{item}_Click")
            interp, code = getattr(surf, "menu_scripts", {}).get(handler, ("lua", ""))
            return json.dumps({"language": self._lang_label(interp), "code": code, "script": handler})
        node = self._node(name)
        interp, code = getattr(node, "design_scripts", {}).get(event, ("lua", ""))
        return json.dumps({"language": self._lang_label(interp), "code": code,
                           "script": node.props.get(event, "")})

    def cmd_SetDesignScript(self, name, event, language, code):
        """Attach (or, with empty code, remove) a control's event script."""
        mt = self._menu_target(name)
        if mt:
            surf, item = mt
            surf.menu_scripts = getattr(surf, "menu_scripts", {})
            handler = next((it.get("onclick") for it in surf.widget.menu_items if it["name"] == item and it.get("onclick")),
                           f"{item}_Click")
            lang = str(language).lower()
            if not str(code).strip():
                surf.menu_scripts.pop(handler, None)
                for it in surf.widget.menu_items:
                    if it["name"] == item:
                        it.pop("onclick", None)
                return ""
            surf.menu_scripts[handler] = (self._lang_interp(lang), str(code))
            for it in surf.widget.menu_items:
                if it["name"] == item:
                    it["onclick"] = handler
            surf.widget.emit("OnChanged", {"selected_control": ""})
            return handler
        node = self._node(name)
        node.design_scripts = getattr(node, "design_scripts", {})
        if not str(code).strip():
            node.design_scripts.pop(event, None)
            self.cmd_SetEvent(name, event, "")
            return ""
        node.design_scripts[event] = (self._lang_interp(str(language).lower()), str(code))
        script_name = node.props.get(event) or (f"Form_{event}" if node.type.name == "DesignSurface" else f"{name}_{event}")
        self.cmd_SetEvent(name, event, script_name)
        if node.type.name == "DesignSurface":
            node.widget.emit("OnChanged", {"selected_control": ""})
        surf = node.parent if node.parent is not None and node.parent.type.name == "DesignSurface" else None
        if surf is not None:
            surf.widget.emit("OnChanged", {"selected_control": name})
        return script_name

    def cmd_ExportHtml(self, source="Surface", out=""):
        """Write a form as one self-contained web page. source: a design surface, or a .vml file."""
        return self._export_html(source, out)

    def cmd_AndroidKey(self):
        """About the key this user's Android apps are signed with, as JSON: exists, id (a short name for it), path,
        made (the day), saved (the day a copy was last saved, or ""), problem (if it is there but can't be read)."""
        from . import apk
        return json.dumps(apk.key_info())

    def cmd_AndroidKeySave(self, path):
        """Write a copy of the signing key to a file, to be kept somewhere safe. "" if done, otherwise why not."""
        from . import apk
        try:
            apk.save_key(path)
            return ""
        except apk.ApkError as exc:
            return str(exc)

    def cmd_AndroidKeyRestore(self, path, replace=""):
        """Put the signing key back from a copy. With a different key already here it refuses unless replace is
        "true" (the one that was here is kept beside it, renamed). "" if done, otherwise why not."""
        from . import apk
        try:
            apk.restore_key(path, replace=str(replace).strip().lower() in ("true", "1", "yes"))
            return ""
        except apk.ApkError as exc:
            return str(exc)

    def cmd_ExportApk(self, source="Surface", out=""):
        """Write a form as an Android app of its own: one .apk, with the app's name, picture and version, asking
        only for what its scripts use, and signed with this user's key (made the first time, and kept beside
        their Visualised settings: it must be backed up, since an app can only be updated with the key it was
        first signed with). source: a design surface, or a .vml file. Returns what was made as JSON: path,
        package, version, permissions, size, key (where the key is), key_id and new_key (true when the key was made
        just now); or other_key and a message, when the form was last exported with a different key from the one
        here. The form is told its package and key, to make an update of the same app next time. "" if it couldn't
        be done, having said why. (Pro.)"""
        if not self.needs("export", "Exporting a form as an Android app"):
            return ""
        from . import apk
        folder = Path(tempfile.mkdtemp(prefix="vml-apk-"))
        try:
            page = Path(self._export_html(source, str(folder / "index.html")))
            out = str(out or Path(self.store.get_setting("current_file") or "App").with_suffix(".apk"))
            made = apk.from_page(page, out, owner=self.licence().get("name", ""))
            # the form remembers the app it has become: the same package and key next time make an update to it
            node = self.find(source) if source and not str(source).lower().endswith(".vml") else None
            if node is not None and node.type.name == "DesignSurface":
                made["remembered"] = (node.props.get("FormAndroidPackage") or "", node.props.get("FormAndroidKey") or "") != (made["package"], made["key_id"])
                self.cmd_SetProperty(node.name, "FormAndroidPackage", made["package"])
                self.cmd_SetProperty(node.name, "FormAndroidKey", made["key_id"])
            else:
                made["remembered"] = apk.remember(self._form_path(source), made["package"], made["key_id"])
        except apk.OtherKey as exc:
            return json.dumps({"other_key": True, "message": str(exc)})
        except apk.ApkError as exc:
            self.cmd_InfoDialog(str(exc), "Export")
            return ""
        except Exception as exc:
            log(f"ExportApk: {exc!r}")
            self.cmd_InfoDialog("The Android app couldn't be made. The form itself is untouched.", "Export")
            return ""
        finally:
            shutil.rmtree(folder, ignore_errors=True)
        log(f"Android app written: {made['path']} ({made['package']})")
        return json.dumps(made)

    def _export_html(self, source="Surface", out=""):
        from .html import export_html
        node = self.find(source) if source and not str(source).lower().endswith(".vml") else None
        project = base = None
        if node is not None and node.type.name == "DesignSurface":
            saved = self.store.get_setting("current_file")
            vml = Path(tempfile.gettempdir()) / f"vml-web-{node.name}.vml"
            self.cmd_ExportVml(node.name, str(vml))
            out = out or (str(Path(saved).with_suffix(".html")) if saved else str(vml.with_suffix(".html")))
            base = self.asset_dir("design:")                 # its pictures are beside the real form, not the copy
            dp = self.design_project
            project = dp if dp is not None and saved and dp.relative(saved) in dp.forms else None
        else:
            vml = self._form_path(source)
            out = out or str(Path(vml).with_suffix(".html"))
        path = export_html(str(vml), out, project=project, base_dir=base)
        log(f"web page written: {path}")
        return path

    # --- exporting an app: the compiled runtime, renamed after the app, with the app's forms beside it
    RELEASES = "https://github.com/wallisoft/vml-releases/releases/latest/download/"
    RUNTIMES = {"windows": ("vml-windows-x64.zip", "vml.exe", ".exe"), "linux": ("vml-linux-x86_64.tar.gz", "vml", "")}

    def _runtime(self, platform):
        """A folder holding the compiled runtime for a platform: this program's own when it matches,
        otherwise downloaded once from the latest release and kept in ~/.vml/runtimes."""
        asset, exe, _ = self.RUNTIMES[platform]
        here = "windows" if sys.platform.startswith("win") else "linux" if sys.platform.startswith("linux") else ""
        if FROZEN and platform == here:
            return Path(sys.executable).resolve().parent
        cache = SYSTEM_DIR.parent / "runtimes" / platform
        folder = cache / "vml"
        if (folder / exe).is_file():
            return folder
        cache.mkdir(parents=True, exist_ok=True)
        archive = cache / asset
        import urllib.request
        self.cmd_SetStatusText(f"Downloading the {platform} runtime (first time only)...")
        with urllib.request.urlopen(self.RELEASES + asset, timeout=60) as r, open(archive, "wb") as f:
            total, done = int(r.headers.get("Content-Length") or 0), 0
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                if total:
                    self.cmd_SetStatusText(f"Downloading the {platform} runtime: {done * 100 // total}%")
                self.app.processEvents()
        shutil.rmtree(folder, ignore_errors=True)
        if asset.endswith(".zip"):
            import zipfile
            with zipfile.ZipFile(archive) as z:
                z.extractall(cache)
        else:
            import tarfile
            with tarfile.open(archive) as t:
                t.extractall(cache, filter="tar") if hasattr(tarfile, "data_filter") else t.extractall(cache)
        archive.unlink(missing_ok=True)
        if not (folder / exe).is_file():
            raise RuntimeError(f"the {platform} runtime download didn't contain {exe}")
        return folder

    def cmd_ExportApp(self, platform, out="", surface="Surface"):
        """Package the app as something that runs by itself: a .zip (Windows) or .tar.gz (Linux) holding MyApp(.exe)
        and, with a project open, every form, module, picture and local database in it; otherwise the form on
        screen and any other forms saved beside it. Double-click MyApp to run."""
        platform = str(platform).lower()
        if platform not in self.RUNTIMES:
            raise ValueError(f"unknown platform {platform!r} (windows or linux)")
        if not self.needs("export", "Exporting a form as an app"):
            return ""
        surf = self._surface(surface)
        saved = self.store.get_setting("current_file")
        project = self.design_project
        name = re.sub(r"[^A-Za-z0-9_-]", "", str((project.name if project else None) or surf.props.get("FormName") or "MyApp")) or "MyApp"
        _, exe, suffix = self.RUNTIMES[platform]
        runtime = self._runtime(platform)
        stage = Path(tempfile.mkdtemp(prefix="vml-export-")) / name
        shutil.copytree(runtime, stage)
        (stage / exe).rename(stage / f"{name}{suffix}")
        if project is not None:                              # a project: every form, module and local database, as laid out
            for rel in project.forms + project.modules:
                src = project.absolute(rel)
                if src.is_file():
                    (stage / rel).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, stage / rel)
            for address in project.databases.values():       # a SQLite file kept in the project's folder travels with it
                kind, _, rest = address.partition(":")
                rel = rest.strip() if kind.strip().lower() == "sqlite" else address
                src = project.folder / rel
                if not Path(rel).is_absolute() and src.is_file() and "=" not in rel:
                    (stage / rel).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, stage / rel)
            for rel in project.forms:
                self._copy_pictures(project.absolute(rel), stage / Path(rel).parent)
            current = project.relative(saved) if saved else None
            if current in project.forms:                     # the form on screen goes as it is now, saved or not
                self.cmd_ExportVml(surf.name, str(stage / current))
            shutil.copy2(project.path, stage / f"{name}.vmlproj")
        else:
            if saved and Path(saved).is_file():              # other forms of a multi-form app come too
                for other in Path(saved).parent.glob("*.vml"):
                    if other.resolve() != Path(saved).resolve():
                        shutil.copy2(other, stage / other.name)
                        self._copy_pictures(other, stage)
            self.cmd_ExportVml(surf.name, str(stage / f"{name}.vml"))
            if saved:
                self._copy_pictures(stage / f"{name}.vml", stage, Path(saved).parent)
        (stage / "README.txt").write_text(
            f"{name}\r\n\r\nTo run it: double-click {name}{suffix}"
            + ("" if suffix else f" (or run ./{name} in a terminal)") +
            "\r\n\r\nMade with Visualised: https://visualised.io\r\n", encoding="utf-8")
        if platform == "linux":
            (stage / name).chmod(0o755)
        default = Path(saved).parent if saved else Path.home()
        out = Path(out) if out else default / (f"{name}-windows.zip" if platform == "windows" else f"{name}-linux.tar.gz")
        out.parent.mkdir(parents=True, exist_ok=True)
        if platform == "windows":
            base = str(out)[:-4] if str(out).endswith(".zip") else str(out)
            path = shutil.make_archive(base, "zip", stage.parent, name)
        else:
            import tarfile
            path = str(out) if str(out).endswith(".tar.gz") else str(out) + ".tar.gz"
            with tarfile.open(path, "w:gz") as t:
                t.add(stage, arcname=name)
        shutil.rmtree(stage.parent, ignore_errors=True)
        log(f"exported {name} for {platform}: {path}")
        self.cmd_SetStatusText(f"Exported {name} for {platform}: {path}")
        return path

    @staticmethod
    def _copy_pictures(form, into, beside=None):
        """Copy the picture files a form's Image controls point at (Source=logo.png) so they travel with it."""
        beside = Path(beside) if beside else Path(form).parent
        try:
            text = Path(form).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return
        for rel in re.findall(r"^Source=(?!data:)(.+)$", text, re.M):
            rel = rel.strip()
            src = beside / rel
            if not Path(rel).is_absolute() and ".." not in Path(rel).parts and src.is_file():
                (Path(into) / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, Path(into) / rel)

    def cmd_PreviewInBrowser(self, surface="Surface"):
        """Open the form being designed in the default web browser, served from a tiny local web server:
        browsers (snap-packaged ones especially) won't run a page opened from disk that loads code from the web."""
        node = self._surface(surface)
        folder = Path(tempfile.gettempdir()) / "vml-web"
        folder.mkdir(exist_ok=True)
        out = folder / f"{node.name}.html"
        self._export_html(node.name, str(out))          # previewing is for everyone; keeping the page is Pro
        url = f"{self._web_server(folder)}/{out.name}"
        import webbrowser
        webbrowser.open(url)
        return url

    def _web_server(self, folder):
        """Start (once) a local web server on 127.0.0.1 for browser previews; returns its address."""
        if getattr(self, "_web_url", None) is None:
            import functools
            import threading
            from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

            class Quiet(SimpleHTTPRequestHandler):
                def log_message(self, *a):
                    pass
            server = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(folder)))
            threading.Thread(target=server.serve_forever, daemon=True).start()
            self._web_server_obj = server
            self._web_url = f"http://127.0.0.1:{server.server_address[1]}"
        return self._web_url

    def cmd_PreviewOnPhone(self, surface="Surface"):
        """Put the form being designed where a phone on the same network can open it, and return its address
        ("" if this computer has no network address). The page is served from a folder that holds nothing else,
        for as long as Visualised is open; anyone on the network who has the address can open it."""
        import socket
        node = self._surface(surface)
        folder = Path(tempfile.gettempdir()) / "vml-phone"
        folder.mkdir(exist_ok=True)
        out = folder / "index.html"                             # so the address is just the computer and a number
        self._export_html(node.name, str(out))
        out.write_text(out.read_text(encoding="utf-8").replace(                # so the page offers the phone app
            "</head>", "<script>window.VML_PREVIEW = true;</script>\n</head>", 1), encoding="utf-8")
        try:
            probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            probe.connect(("10.255.255.255", 1))               # nothing is sent: this only asks which address would be used
            address = probe.getsockname()[0]
            probe.close()
        except OSError:
            address = ""
        if not address or address.startswith("127."):
            return ""
        if getattr(self, "_phone_server", None) is None:
            import functools
            import threading
            from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

            class Quiet(SimpleHTTPRequestHandler):
                def log_message(self, *a):
                    pass

                def do_GET(handler):                            # a phone that opens the page says how big its screen is
                    if handler.path.startswith("/_log?"):       # a line the app on the phone wants its maker to see
                        from urllib.parse import parse_qs
                        said = parse_qs(handler.path.split("?", 1)[1]).get("t", [""])[0]
                        print("[phone] " + said[:6000].replace("\r", " ").replace("\n", " "), flush=True)
                        handler.send_response(204)
                        handler.end_headers()
                        return
                    if handler.path.startswith("/_size?"):
                        from urllib.parse import parse_qs
                        said = parse_qs(handler.path.split("?", 1)[1])
                        try:
                            w, h = int(float(said["w"][0])), int(float(said["h"][0]))
                            if 200 <= w <= 2000 and 200 <= h <= 4000:
                                self._phone_size = f"{w}x{h}"
                        except (KeyError, ValueError, IndexError):
                            pass
                        handler.send_response(204)
                        handler.end_headers()
                        return
                    super().do_GET()

                def end_headers(self):                          # always the newest: a phone keeps old pages hard
                    self.send_header("Cache-Control", "no-store")
                    super().end_headers()
            self._phone_server = ThreadingHTTPServer(("0.0.0.0", 0), functools.partial(Quiet, directory=str(folder)))
            threading.Thread(target=self._phone_server.serve_forever, daemon=True).start()
        return f"http://{address}:{self._phone_server.server_address[1]}/"

    def cmd_PhoneSize(self):
        """The screen of the phone that last opened Preview on Phone, as "360x668": what is left for a form once
        the phone's own bars are taken off. "" until a phone has."""
        size = getattr(self, "_phone_size", "")
        if size and size != self.store.get_setting("phone_size"):
            self.store.set_setting("phone_size", size)
        return size or self.store.get_setting("phone_size") or ""

    def cmd_PreviewDesign(self, surface="Surface"):
        """Run the form being designed, for real, in its own window."""
        surf = self._surface(surface)
        path = Path(tempfile.gettempdir()) / f"vml-preview-{surf.name}.vml"
        for w in [w for w in self.windows if w.scope == str(path.resolve())]:
            w.widget.close()
            self.windows.remove(w)
        self.cmd_ExportVml(surf.name, str(path))
        saved = self.store.get_setting("current_file")
        self.form_dirs[str(path.resolve())] = str(Path(saved).parent) if saved else self.asset_dir("design:")
        self.form_overrides = {}                              # (a run of the whole project may have left this file standing in for another form)
        self.use_design_project(saved)                        # one form of a project still has the project's modules
        self.luas.pop(str(path.resolve()), None)              # a fresh Lua state for each preview
        self._running += 1
        try:
            self.load(path)
        finally:
            self._running -= 1
        return str(path)

    # --- forms and dialogs
    def asset_dir(self, scope=None):
        """The folder a form's own files (pictures, databases, other forms) are looked for in."""
        scope = str(scope or self.active_scope() or "")
        if scope.startswith("design:"):
            current = self.store.get_setting("current_file")
            if current:
                return str(Path(current).parent)
            return str(self.design_project.folder) if self.design_project is not None else os.getcwd()
        if scope in self.form_dirs:
            return str(self.form_dirs[scope])
        return str(Path(scope).parent) if scope else os.getcwd()

    def _form_path(self, path):
        p = Path(os.path.expanduser(str(path)))
        if not p.is_absolute():
            p = Path(self.asset_dir()) / p
        if not p.suffix and not p.exists() and p.with_name(p.name + ".vml").exists():
            p = p.with_name(p.name + ".vml")                 # FormOpen("frmLogin"): a form by its name
        return p

    def _form_to_run(self, path):
        """The file to open for a form: itself, or (running from the designer) the copy being designed."""
        p = self._form_path(path)
        try:
            return Path(self.form_overrides.get(str(p.resolve()), p))
        except OSError:
            return p

    def _window_of_scope(self, scope):
        return next((w for w in self.windows if w.scope == scope and w.widget.isVisible()), None)

    def cmd_FormOpen(self, path):
        """Open another form (relative paths are next to this one). If it's already open, bring it forward."""
        p = self._form_to_run(path)
        open_already = self._window_of_scope(str(p.resolve()))
        if open_already is not None:
            open_already.widget.raise_()
            open_already.widget.activateWindow()
            return open_already.name
        before = len(self.windows)
        self.load(p)
        return self.windows[before].name if len(self.windows) > before else ""

    def _form_window(self, name):
        """The newest window with this name, preferring one that's on screen."""
        matches = [w for w in reversed(self.windows) if w.name == name]
        return next((w for w in matches if w.widget.isVisible()), matches[0] if matches else None)

    def cmd_ShowForm(self, name):
        w = self._form_window(name)
        if w is not None:
            w.widget.show()
            w.widget.raise_()
            return True
        return False

    def cmd_HideForm(self, name):
        w = self._form_window(name)
        if w is not None:
            w.widget.hide()
            return True
        return False

    def cmd_CloseForm(self, name):
        w = self._form_window(name)
        if w is not None:
            w.widget.close()
            return True
        return False

    def cmd_SetDialogResult(self, value=""):
        """A form opened with FormOpenModal hands this back to whoever opened it."""
        self.store.set_setting("dialog_result", value)

    def cmd_FormOpenModal(self, path):
        """Open a form and wait until it closes; returns whatever it passed to SetDialogResult."""
        p = self._form_to_run(path)
        self.store.set_setting("dialog_result", "")
        before = len(self.windows)
        self.load(p, modal=True)
        opened = self.windows[before:]
        if not opened:
            return ""
        loop = QEventLoop()
        win = opened[0].widget
        win.setAttribute(Qt.WA_DeleteOnClose, False)
        win.installEventFilter(self._closer(loop))
        loop.exec()
        for n in opened:
            if n in self.windows:
                self.windows.remove(n)
        scope = str(p.resolve())
        for name in list(self.scopes.get(scope, {})):
            node = self.scopes[scope].get(name)
            if node is not None and node.parent is None:
                self.delete(name, scope)
        self.scopes.pop(scope, None)
        self._forget_sources(scope)
        self.luas.pop(scope, None)                           # its own Lua state goes with it
        return self.store.get_setting("dialog_result")

    def _closer(self, loop):
        from PySide6.QtCore import QEvent, QObject

        class Closer(QObject):
            def eventFilter(self, obj, ev):
                if ev.type() == QEvent.Close:
                    QTimer.singleShot(0, loop.quit)
                return False
        c = Closer(self.app)
        self._keep_closer = c
        return c

    def _parent_window(self):
        """The window a dialog belongs to: the one in use. A dialog is kept in front of the window it belongs to
        and nothing else, so the wrong choice here can leave it hidden behind the window the user is looking at,
        which then answers to nothing, not even its close button. So: the window in use; or, in the moment
        after another dialog has shut when no window is 'in use', the one the last dialog belonged to; and only
        then the newest still on screen."""
        active = QApplication.activeWindow()
        while active is not None and getattr(active, "vml_node", None) is None:      # a dialog of ours: the window behind it
            active = active.parentWidget().window() if active.parentWidget() is not None else None
        if active is not None and active.isVisible():
            self._dialog_parent = active
            return active
        last = getattr(self, "_dialog_parent", None)
        try:
            if last is not None and last.isVisible():
                return last
        except RuntimeError:                                    # that window has gone
            pass
        shown = [w.widget for w in self.windows if w.widget.isVisible()]
        self._dialog_parent = shown[-1] if shown else None
        return self._dialog_parent

    def _edge(self):
        """The colour for a dialog's edge: its window's own (which is its menu bar's), else a quiet grey."""
        w = self._parent_window()
        return (w.edge_name() if w is not None and hasattr(w, "edge_name") else "") or dialogs.NEUTRAL

    def cmd_InfoDialog(self, message, title="Information", picture=""):
        """A message with an OK button. picture: a picture to show above it (a file, or a data: address such as
        QrCode gives)."""
        dialogs.message(self._parent_window(), title, message, self._edge(), picture=str(picture or "") or None)

    def cmd_QrCode(self, text, scale=6):
        """A QR code for some text (an address, usually), as a picture: a data: address to give an Image as its
        Source, or InfoDialog as its picture. Up to 213 characters. "" if it is too long."""
        import base64
        from . import qr
        try:
            return "data:image/png;base64," + base64.b64encode(qr.png(str(text), max(1, int(float(scale or 6))))).decode()
        except ValueError as exc:
            self.log_line(f"QrCode: {exc}")
            return ""

    def cmd_ErrorDialog(self, message, title="Error"):
        dialogs.message(self._parent_window(), title, message, self._edge())

    def cmd_ConfirmDialog(self, message, title="Confirm"):
        return dialogs.confirm(self._parent_window(), title, message, self._edge())

    def cmd_ChoiceDialog(self, message, title="Choose", buttons="Yes|No|Cancel"):
        """A question with your own answers: buttons is their captions with | between them (the first is the
        one Enter presses). Returns the caption pressed, or "" if the box was closed without one."""
        labels = [b.strip() for b in str(buttons).split("|") if b.strip()] or ["OK"]
        return dialogs.choose(self._parent_window(), title, message, labels, self._edge())

    def cmd_PromptDialog(self, title="", prompt="", default="", secret=""):
        """Ask for one line of text. Returns what was typed, or "" if cancelled. secret "true" shows dots, for a password."""
        return dialogs.prompt(self._parent_window(), title or "Enter a value", prompt, default, self._edge(),
                              secret=str(secret).strip().lower() in ("true", "1", "yes"))

    def cmd_ClipboardSet(self, text=""):
        """Put text on the clipboard, ready to paste."""
        QApplication.clipboard().setText(str(text))
        return True

    def cmd_ClipboardGet(self):
        return QApplication.clipboard().text()

    # --- the phone. On a computer these do the nearest sensible thing, so the same script runs in both places.
    def cmd_DeviceInfo(self):
        """What the app is running on, as JSON: platform is "desktop" here, "android-app" in the Visualised app
        on a phone, "android-browser", "ios-browser" or "browser" on a web page; app is true only in the app."""
        import platform
        return json.dumps({"platform": "desktop", "app": False, "system": platform.system()})

    def cmd_Vibrate(self, milliseconds=200):
        """Buzz the phone. Nothing happens on a computer."""
        return ""

    def cmd_KeepAwake(self, on="true"):
        """Keep the phone's screen on while the app is in front. Nothing happens on a computer."""
        return ""

    def cmd_Share(self, text="", title=""):
        """Hand some text to another app on the phone (messages, email, notes). On a computer it goes on the clipboard."""
        QApplication.clipboard().setText(str(text))
        return ""

    def cmd_Notify(self, title="", text=""):
        """A notification in the phone's own list. On a computer, a message box."""
        dialogs.message(self._parent_window(), str(title) or "Notice", str(text), self._edge())
        return ""

    def cmd_GetLocation(self, handler):
        """Find where the phone is, then run handler with the latitude, the longitude and how many metres out that
        might be; or with three blanks and what went wrong, which on a computer is always."""
        origin = self._script_stack[-1] if self._script_stack else None
        QTimer.singleShot(0, lambda: self.run_script(str(handler), "", "", "", "A computer doesn't know where it is.", origin=origin))
        return ""

    def cmd_RunInBackground(self, on="true"):
        """Keep the app going on a phone while the phone is used for something else, for six hours from the last
        time it was asked (so an app that must keep going asks again now and then). A computer does that anyway."""
        return ""

    def cmd_Brightness(self, percent=""):
        """How bright the phone's screen is while this app is in front, 0 to 100; nothing puts it back to the
        phone's own setting. A computer's screen is left alone."""
        return ""

    def cmd_Torch(self, on="true"):
        """The phone's torch, on or off. Nothing happens on a computer."""
        return ""

    def cmd_Speak(self, text=""):
        """Say some text out loud, where there is a voice to say it with."""
        try:
            from PySide6.QtTextToSpeech import QTextToSpeech
            if getattr(self, "_voice", None) is None:
                self._voice = QTextToSpeech()
            self._voice.say(str(text))
        except Exception:                                        # no voice on this computer: silence is the honest answer
            pass
        return ""

    def cmd_SaveFile(self, name, text=""):
        """Give the user a file: on a phone it goes to Downloads, in a browser it downloads, on a computer the
        user is asked where to put it. Returns where it went, or "" if it didn't."""
        path = dialogs.save_file(self._parent_window(), "Save", str(name), edge=self._edge())
        if not path:
            return ""
        Path(path).write_text(str(text), encoding="utf-8")
        return path

    def cmd_BluetoothDevices(self, handler):
        """The Bluetooth devices a phone is paired with: handler gets them as JSON (name, address, watched) and a
        blank; or "[]" and what went wrong, which on a computer is always."""
        origin = self._script_stack[-1] if self._script_stack else None
        QTimer.singleShot(0, lambda: self.run_script(str(handler), "[]", "Bluetooth devices need the Visualised app on a phone.", origin=origin))
        return ""

    def cmd_WatchBluetooth(self, address, on="true", handler=""):
        """On a phone: note where the phone is whenever a paired device (a car, say) connects or goes away, even
        with the app shut. handler hears "watching", "stopped" or "partly", and any problem."""
        if handler:
            origin = self._script_stack[-1] if self._script_stack else None
            QTimer.singleShot(0, lambda: self.run_script(str(handler), "stopped", "Watching a Bluetooth device needs the Visualised app on a phone.", origin=origin))
        return ""

    def cmd_BluetoothLog(self):
        """What a phone has noted, newest first, as JSON: device, name, what, time, and where. "[]" on a computer."""
        return "[]"

    def cmd_Pressure(self):
        """The air pressure in hectopascals from a phone's barometer (it tells one floor from the next). "" here."""
        return ""

    def cmd_Fetch(self, url, body="", handler=""):
        """Ask a web address for something: with no body it is fetched, with one it is sent (POST; as JSON when
        it looks like JSON). handler is then run with what came back and a blank, or what came back (if
        anything) and what went wrong. The app carries on meanwhile."""
        import queue
        import urllib.error
        import urllib.request
        origin = self._script_stack[-1] if self._script_stack else None
        url, body, handler = str(url), str(body or ""), str(handler or "")
        if getattr(self, "_fetched", None) is None:
            self._fetched = queue.Queue()
            self._fetch_timer = QTimer()
            self._fetch_timer.setInterval(50)
            self._fetch_timer.timeout.connect(self._fetch_events)
        self._fetch_timer.start()

        def go():
            answer, problem = "", ""
            try:
                if not re.match(r"(?i)https?://", url):
                    raise ValueError("Only http:// and https:// addresses can be fetched.")
                data = body.encode("utf-8") if body else None
                kind = "application/json" if body.lstrip()[:1] in ("{", "[") else "text/plain; charset=utf-8"
                req = urllib.request.Request(url, data=data, headers={"User-Agent": "Visualised", **({"Content-Type": kind} if data else {})})
                with urllib.request.urlopen(req, timeout=30) as r:
                    answer = r.read(2 * 1024 * 1024 + 1).decode("utf-8", "replace")
                if len(answer) > 2 * 1024 * 1024:
                    answer, problem = "", "The answer was over 2 MB."
            except urllib.error.HTTPError as exc:
                answer, problem = exc.read().decode("utf-8", "replace"), f"The server said {exc.code}."
            except Exception as exc:
                problem = str(getattr(exc, "reason", "") or exc) or "It couldn't be reached."
            self._fetched.put((handler, answer, problem, origin))
        threading.Thread(target=go, daemon=True).start()
        return ""

    def _fetch_events(self):
        while True:
            try:
                handler, answer, problem, origin = self._fetched.get_nowait()
            except Exception:
                break
            if handler:
                self.run_script(handler, answer, problem, origin=origin)

    def cmd_PushSend(self, address="", text="", handler=""):
        """Send a short text to a push address (one an app's phone copy got from OnPush): the phone is woken and its
        handler gets ("message", text, this computer's push address). Handler gets "sent", or a blank and why not."""
        import queue
        import urllib.request
        origin = self._script_stack[-1] if self._script_stack else None
        handler = str(handler or "")
        relay = os.environ.get("VML_PUSH_RELAY", "https://tiny-web.uk/api/push.php")
        if getattr(self, "_fetched", None) is None:
            self._fetched = queue.Queue()
            self._fetch_timer = QTimer()
            self._fetch_timer.setInterval(50)
            self._fetch_timer.timeout.connect(self._fetch_events)
        self._fetch_timer.start()
        try:
            carry = licences.link_pass(fetch=False)
        except Exception:
            carry = ""
        win = QApplication.activeWindow()
        title = win.windowTitle() if win else ""
        mine = {"address": self.cmd_GetSetting("_push_address"), "secret": self.cmd_GetSetting("_push_secret")}
        kept = queue.Queue()

        def ask(body):
            req = urllib.request.Request(relay, data=json.dumps(dict({"app": title, "v": carry}, **body)).encode("utf-8"),
                                         headers={"User-Agent": "Visualised", "Content-Type": "text/plain; charset=utf-8"})
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read(65536).decode("utf-8", "replace") or "{}")

        def go():
            answer, problem = "", ""
            try:
                me = dict(mine)
                if not me["address"]:
                    d = ask({"action": "register", "token": ""})
                    if not d.get("ok"):
                        raise RuntimeError(d.get("error") or "The push service refused.")
                    me = {"address": d["address"], "secret": d["secret"]}
                    kept.put(me)
                d = ask({"action": "send", "from": me["address"], "secret": me["secret"], "to": str(address), "text": str(text)})
                if not d.get("ok"):
                    raise RuntimeError(d.get("error") or "Not sent.")
                answer = "sent"
            except Exception as exc:
                problem = str(getattr(exc, "reason", "") or exc) or "The push service couldn't be reached."
            self._fetched.put((handler, answer, problem, origin))

        def keep():
            try:
                me = kept.get_nowait()
                self.cmd_SetSetting("_push_address", me["address"])
                self.cmd_SetSetting("_push_secret", me["secret"])
            except Exception:
                pass
        QTimer.singleShot(3000, keep)
        QTimer.singleShot(15000, keep)
        threading.Thread(target=go, daemon=True).start()
        return ""

    def cmd_SignIn(self, provider="google", handler=""):
        """Sign in with Google or GitHub: the user's browser opens at the provider's own sign-in, and handler then
        gets JSON {provider, id, name, email, picture, token}, or a blank and why not. The token is signed by
        tiny-web, so an app's own server can check it (tiny-web.uk/api/oauth.php, action "verify")."""
        import queue
        import urllib.request
        origin = self._script_stack[-1] if self._script_stack else None
        handler = str(handler or "")
        relay = os.environ.get("VML_SIGNIN_RELAY", "https://tiny-web.uk/api/oauth.php")
        if getattr(self, "_fetched", None) is None:
            self._fetched = queue.Queue()
            self._fetch_timer = QTimer()
            self._fetch_timer.setInterval(50)
            self._fetch_timer.timeout.connect(self._fetch_events)
        self._fetch_timer.start()
        opened = queue.Queue()
        try:
            carry = licences.link_pass(fetch=False)
        except Exception:
            carry = ""
        win = QApplication.activeWindow()
        title = win.windowTitle() if win else ""

        def ask(body):
            req = urllib.request.Request(relay, data=json.dumps(body).encode("utf-8"),
                                         headers={"User-Agent": "Visualised", "Content-Type": "text/plain; charset=utf-8"})
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read(65536).decode("utf-8", "replace") or "{}")

        def go():
            answer, problem = "", ""
            try:
                s = ask({"action": "start", "provider": str(provider).lower(), "app": title, "v": carry})
                if not s.get("ok"):
                    raise RuntimeError(s.get("error") or "Not signed in.")
                opened.put(s["url"])
                until = time.time() + int(s.get("wait") or 600)
                while time.time() < until:
                    time.sleep(2)
                    try:
                        p = ask({"action": "poll", "code": s["code"], "secret": s["secret"]})
                    except Exception:
                        continue
                    if not p.get("ok"):
                        raise RuntimeError(p.get("error") or "Not signed in.")
                    if p.get("done"):
                        answer = json.dumps(dict(p.get("user") or {}, token=p.get("token", "")))
                        break
                else:
                    problem = "Signing in took too long."
            except Exception as exc:
                problem = str(getattr(exc, "reason", "") or exc) or "The sign-in service couldn't be reached."
            self._fetched.put((handler, answer, problem, origin))

        def show():
            try:
                QDesktopServices.openUrl(QUrl(opened.get_nowait()))
                watch.stop()
            except Exception:
                pass
        watch = self._signin_watch = QTimer()
        watch.setInterval(100)
        watch.timeout.connect(show)
        watch.start()
        QTimer.singleShot(60000, watch.stop)
        threading.Thread(target=go, daemon=True).start()
        return ""

    def cmd_SmsSend(self, number, text="", handler=""):
        """Send a text message from the phone, then run handler with "sent", or a blank and what went wrong.
        Only an app exported on its own for Android can (vml apk); here the handler hears why not."""
        if handler:
            origin = self._script_stack[-1] if self._script_stack else None
            QTimer.singleShot(0, lambda: self.run_script(str(handler), "", "Sending texts needs the app exported for an Android phone.", origin=origin))
        return ""

    def cmd_OnSms(self, handler=""):
        """Hear text messages as they arrive: handler gets who from and what they said, for each. A blank "from"
        means it couldn't, and the text says why (as here: an app exported for an Android phone only). "" stops."""
        if handler:
            origin = self._script_stack[-1] if self._script_stack else None
            QTimer.singleShot(0, lambda: self.run_script(str(handler), "", "Texts arrive only in an app exported for an Android phone.", origin=origin))
        return ""

    def cmd_ReadContacts(self, handler=""):
        """The phone's address book, as JSON [{"name", "number", "label"}], to handler; or a blank and why not (as here: an
        app exported for an Android phone only)."""
        if handler:
            origin = self._script_stack[-1] if self._script_stack else None
            QTimer.singleShot(0, lambda: self.run_script(str(handler), "", "The address book is read only by an app exported for an Android phone.", origin=origin))
        return ""

    def cmd_SaveContact(self, name="", number="", oldName="", handler=""):
        """Adds to or changes the phone's address book; to handler the name, or a blank and why not (as here: an app
        exported for an Android phone only)."""
        if handler:
            origin = self._script_stack[-1] if self._script_stack else None
            QTimer.singleShot(0, lambda: self.run_script(str(handler), "", "The address book is changed only by an app exported for an Android phone.", origin=origin))
        return ""

    def cmd_LookupNumber(self, name="", prefer="", handler=""):
        """A number for a name in the phone's address book, to handler; or a blank and why not (as here: an app
        exported for an Android phone only)."""
        if handler:
            origin = self._script_stack[-1] if self._script_stack else None
            QTimer.singleShot(0, lambda: self.run_script(str(handler), "", "Numbers are looked up only by an app exported for an Android phone.", origin=origin))
        return ""

    def cmd_LookupNames(self, numbers="[]", handler=""):
        """Names for some numbers from the phone's address book, as JSON {number: name}, to handler; or a blank and
        why not (as here: an app exported for an Android phone only)."""
        if handler:
            origin = self._script_stack[-1] if self._script_stack else None
            QTimer.singleShot(0, lambda: self.run_script(str(handler), "", "Names are looked up only by an app exported for an Android phone.", origin=origin))
        return ""

    def cmd_OnMessages(self, handler=""):
        """Hear messages that arrive in the phone's messaging apps (RCS included), read from their notices: handler
        gets who from and what they said. A blank "from" means it can't, and the text says why (as here: an app
        exported for an Android phone only). "" stops."""
        if handler:
            origin = self._script_stack[-1] if self._script_stack else None
            QTimer.singleShot(0, lambda: self.run_script(str(handler), "", "Messages arrive only in an app exported for an Android phone.", origin=origin))
        return ""

    def cmd_OnPush(self, handler="", firebase=""):
        """Hear push messages, on a phone. With firebase (a project's public values as JSON) they come from the app's
        own server: handler gets ("token", the phone's Firebase token) and ("message", the push's data). With none,
        through Visualised's own push service: ("address", this phone's push address) and ("message", text, from)
        for each PushSend to it. Or a blank and what went wrong (as here: an app exported for Android only)."""
        if handler:
            origin = self._script_stack[-1] if self._script_stack else None
            QTimer.singleShot(0, lambda: self.run_script(str(handler), "", "Pushes arrive only in an app exported for an Android phone.", origin=origin))
        return ""

    def cmd_Log(self, text=""):
        """Write a line where the app's maker can see it: the terminal Visualised was started from. From an app
        being previewed on a phone, the line comes back to that same terminal."""
        print("[log] " + str(text), flush=True)
        return ""

    def cmd_LightReport(self):
        """On a phone, how WatchLight has gone, in a line: how evenly the camera's pictures came and how long
        its light took to switch. "" on a computer."""
        return ""

    # ---- Link: this app talking to another, anywhere, with nobody between able to read it (see vml/link.py)
    def cmd_Link(self, handler, code="", start=""):
        """Start a link, or join one. With no code a new link is started and its code is returned, to show the
        other app (QrCode makes a picture of it); with a code, that link is joined. handler is then run with
        "joined" when the other side arrives, "message" and the text when it sends, "left" when it closes, and
        "error" and what went wrong. start: "start" to be given the messages of the last day too. "" and the
        handler told why if it couldn't be done."""
        from . import link
        origin = self._script_stack[-1] if self._script_stack else None
        self.cmd_LinkClose()
        try:
            made = link.Link(code, start=str(start), carry=self._link_carry(origin))
        except link.LinkError as exc:
            QTimer.singleShot(0, lambda why=str(exc): self.run_script(str(handler), "error", why, origin=origin))
            return ""
        self._link, self._link_handler, self._link_origin = made, str(handler), origin
        self._link_listen()
        return made.code

    def cmd_LinkPair(self, handler):
        """Agree a link with another app by pressing together: both run this within a few seconds of each
        other, with nothing to show or scan. handler is run with "words" and three words, which the other app
        shows too; when the two people see they are the same, LinkAccept opens the link (and the handler then
        hears "joined", "message" and the rest, as with Link). Or with "error" and what went wrong: nobody
        else pressed, or too many did."""
        from . import link
        origin = self._script_stack[-1] if self._script_stack else None
        self.cmd_LinkClose()
        self._link, self._link_handler, self._link_origin = link.Pairing(), str(handler), origin
        self._link_listen()
        return "true"

    def cmd_LinkAccept(self):
        """The three words LinkPair gave are the same on both: open the link. Its code, or "" if there is no
        pairing waiting to be accepted."""
        from . import link
        made = getattr(self, "_link", None)
        if not isinstance(made, link.Pairing) or not made.code:
            return ""
        try:
            self._link = link.Link(made.code, carry=self._link_carry(self._link_origin))
        except link.LinkError as exc:
            made.events.put(("error", str(exc)))
            return ""
        return self._link.code

    def _link_carry(self, origin=None):
        """The pass this app's links go out with: the one its maker's Visualised Pro put in the form, or failing
        that this computer's own, if it has a Pro licence (so a form is carried in full while it is being made)."""
        win = origin
        while win is not None and win.parent is not None:
            win = win.parent
        if win is None or win.type.name != "Window":
            win = next((n for n in self.nodes.values() if n.type.name == "Window" and n.parent is None), None)
        stamped = str(win.props.get("LinkPass", "") or "") if win is not None else ""
        return stamped if stamped.startswith("VP1-") else licences.link_pass(fetch=False)

    def _link_listen(self):
        if getattr(self, "_link_timer", None) is None:
            self._link_timer = QTimer()
            self._link_timer.setInterval(100)
            self._link_timer.timeout.connect(self._link_events)
        self._link_timer.start()

    def _link_events(self):
        made = getattr(self, "_link", None)
        if made is None:
            return
        for _ in range(50):                                      # what has arrived since last looked
            try:
                what, text = made.events.get_nowait()
            except Exception:
                break
            if what == "online":
                continue
            self.run_script(self._link_handler, what, text, origin=self._link_origin)
            if getattr(self, "_link", None) is not made:         # the handler closed it, or started another
                break

    def cmd_LinkSend(self, text=""):
        """Send some text to the other end of the link. "true", or "" (and the handler is told why)."""
        from . import link
        made = getattr(self, "_link", None)
        if made is None:
            return ""
        try:
            made.send(str(text))
            return "true"
        except link.LinkError as exc:
            made.events.put(("error", str(exc)))
            return ""

    def cmd_LinkAddress(self, code=""):
        """What to show as a QR code (QrCode) so any phone's camera can join this app's link, not only the
        scanner inside the app: an address that opens this app with the link's code. It needs the app to be on
        the web, and its Window to say where (WebAddress=https://...); without that, the code itself is given
        back, which another copy of the app can still scan or have pasted in. code: the link's code (the one
        open now if left out)."""
        from . import link
        code = str(code or "") or self.cmd_LinkCode()
        if not code:
            return ""
        win = next((n for n in self.nodes.values() if n.type.name == "Window" and n.parent is None), None)
        return link.address(code, win.props.get("WebAddress", "") if win is not None else "")

    def cmd_LinkInvite(self):
        """The link code this app was opened with, when it was opened from an address made by LinkAddress (a QR
        code pointed at by a phone's camera): give it to Link to join. "" otherwise, and always on a computer."""
        return ""

    def cmd_LinkCode(self):
        """The code of the link this app has open, or ""."""
        from . import link
        made = getattr(self, "_link", None)
        return made.code if isinstance(made, link.Link) else ""

    def cmd_LinkClose(self):
        """Close the link. The other end is told."""
        made = getattr(self, "_link", None)
        if made is not None:
            self._link = None
            self._link_timer.stop()
            threading.Thread(target=made.close, daemon=True).start()
        return ""

    def cmd_ScanCode(self, handler, prompt=""):
        """Read a QR code with the camera, then run handler with what it says; or with a blank and what went
        wrong. A computer asks for it to be pasted instead."""
        text = dialogs.prompt(self._parent_window(), "Code", str(prompt) or "Paste the code here:", "", self._edge())
        origin = self._script_stack[-1] if self._script_stack else None
        self.run_script(str(handler), str(text or "").strip(), "" if text else "Nothing was given.", origin=origin)
        return ""

    def cmd_Listen(self, handler, prompt=""):
        """Hear what the user says, then run handler with the words; or with a blank and what went wrong.
        A computer asks them to type it instead."""
        words = dialogs.prompt(self._parent_window(), "Listen", str(prompt) or "Type what you would have said:", "", self._edge())
        origin = self._script_stack[-1] if self._script_stack else None
        self.run_script(str(handler), words, "" if words else "Nothing was said.", origin=origin)
        return ""

    def cmd_Flash(self, pattern="", handler=""):
        """Signal with light: pattern is milliseconds on, off, on, off... A phone uses its torch and a web page
        lights the whole screen; a computer only waits that long. Then handler is run. "" stops it."""
        steps = [float(t) for t in re.split(r"[,\s]+", str(pattern)) if t.replace(".", "", 1).isdigit()]
        if steps and handler:
            origin = self._script_stack[-1] if self._script_stack else None
            QTimer.singleShot(int(sum(steps)), lambda: self.run_script(str(handler), origin=origin))
        return ""

    def cmd_WatchLight(self, handler="", where=""):
        """Watch for a light going on and off through the phone's camera: each change runs handler with "on" or
        "off" and how many milliseconds the state before lasted; or with "error", 0 and what went wrong, which on
        a computer is always. where: a control to show the camera's picture over. No handler stops watching."""
        if handler:
            origin = self._script_stack[-1] if self._script_stack else None
            QTimer.singleShot(0, lambda: self.run_script(str(handler), "error", "0", "A computer has no camera to watch with.", origin=origin))
        return ""

    def cmd_PickPhoto(self, image, handler=""):
        """Put a picture the user chooses into an Image, then run handler (if given) with the Image's name.
        Returns the file chosen here; on a phone the answer comes later, so use the handler."""
        path = dialogs.open_file(self._parent_window(), "Choose a picture", "",
                                 "Pictures (*.png *.jpg *.jpeg *.gif *.bmp *.webp);;All files (*)", edge=self._edge())
        if not path:
            return ""
        self.cmd_SetProperty(image, "Source", path)
        if handler:
            origin = self._script_stack[-1] if self._script_stack else None
            self.run_script(str(handler), str(image), origin=origin)
        return path

    def cmd_TakePhoto(self, image, handler=""):
        """Take a photo with the phone's camera and put it in an Image, then run handler. A computer asks for a
        picture file instead."""
        return self.cmd_PickPhoto(image, handler)

    # --- Tools: the apps in the tools folder (~/.vml/tools), on the designer's Tools menu
    def tools_folder(self):
        return Path(os.path.expanduser("~")) / ".vml" / "tools"

    def cmd_ToolsList(self):
        """The tools, as JSON [{name, path}]: each .vml or .vmlproj in the tools folder, and each folder in it that
        holds a .vmlproj or a .vml (a link to an app's folder will do: ln -s ~/projects/x/apps/bob ~/.vml/tools/Bob)."""
        import json
        found, root = [], self.tools_folder()
        try:
            entries = sorted(root.iterdir(), key=lambda p: p.name.lower())
        except OSError:
            entries = []                                     # (no tools folder yet: Bob may still be there)
        for p in entries:
            if p.name.startswith("."):
                continue
            if p.is_file() and p.suffix.lower() in (".vml", ".vmlproj"):
                found.append({"name": p.stem, "path": str(p)})
            elif p.is_dir():
                inside = sorted(p.glob("*.vmlproj")) or sorted(p.glob(f"{p.name}.vml"), key=str) or \
                    sorted([q for q in p.glob("*.vml") if q.stem.lower() == p.name.lower()]) or sorted(p.glob("*.vml"))
                if inside:
                    found.append({"name": p.name, "path": str(inside[0])})
        for t in found:                                      # a form's own title, when it has one ("Bob build tool")
            try:
                head = Path(t["path"]).read_text(encoding="utf-8", errors="replace")[:4000]
                m = re.search(r"^Title=(.+)$", head, re.M) if t["path"].lower().endswith(".vml") else None
                if m and m.group(1).strip():
                    t["name"] = m.group(1).strip()
            except OSError:
                pass
        if not any(Path(t["path"]).name == "Bob.vml" for t in found):  # Bob, wherever Visualised's source is
            here = Path(__file__).resolve().parent.parent
            repo = Path(os.path.expanduser(os.environ.get("BOB_REPO") or "~/projects/vml-github"))
            for root in (here, repo):
                bob = root / "apps" / "bob" / "Bob.vml"
                if bob.is_file() and (root / "tools" / "bob" / "run.py").is_file():
                    found.insert(0, {"name": "Bob build tool", "path": str(bob), "builtin": True})
                    break
        return json.dumps(found)

    def cmd_ToolsFolder(self):
        """The tools folder (made if it isn't there yet)."""
        root = self.tools_folder()
        root.mkdir(parents=True, exist_ok=True)
        return str(root)

    def cmd_RunApp(self, path, project=""):
        """Start a form or project as an app of its own, in its own process: it carries on if this one closes.
        project: the project (or form) the designer has open, for a tool to work on: it finds it in VML_PROJECT."""
        p = Path(os.path.expanduser(str(path)))
        if not p.exists():
            return ""
        argv = [sys.executable, str(p)] if FROZEN else [sys.executable, "-m", "vml", str(p)]
        env = dict(os.environ)
        if project:
            env["VML_PROJECT"] = str(project)
        if not FROZEN:                                       # (from the source: it needs to find the vml package)
            env["PYTHONPATH"] = str(Path(__file__).resolve().parent.parent) + os.pathsep + env.get("PYTHONPATH", "")
        try:
            subprocess.Popen(argv, cwd=str(p.parent), env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, start_new_session=True)
            return "true"
        except OSError as exc:
            log(f"RunApp: {exc}")
            return ""

    def cmd_FileOpenDialog(self, title="Open", ext="", start=""):
        kinds = [e.strip().lstrip(".") for e in str(ext).split(",") if e.strip()]       # "vml", or "vb,cs" for several
        if len(kinds) > 1:
            filt = f"{' and '.join(k.upper() for k in kinds)} files ({' '.join('*.' + k for k in kinds)});;All files (*)"
        else:
            filt = f"{ext.upper()} files (*.{ext});;All files (*)" if ext else "All files (*)"
        return dialogs.open_file(self._parent_window(), str(title), os.path.expanduser(str(start or "")), filt, edge=self._edge())

    def cmd_FileSaveDialog(self, title="Save", default="", ext=""):
        filt = f"{ext.upper()} files (*.{ext});;All files (*)" if ext else "All files (*)"
        name = f"{default}.{ext}" if default and ext and not str(default).endswith("." + ext) else str(default)
        return dialogs.save_file(self._parent_window(), str(title), name, filt, edge=self._edge())

    # --- app
    def cmd_AppExit(self):
        QTimer.singleShot(0, self.app.quit)

    def cmd_CloseSelf(self):
        origin = next((o for o in reversed(self._script_stack) if o is not None), None)
        while origin is not None and origin.parent is not None:
            origin = origin.parent
        target = origin if origin is not None and origin.type.name == "Window" else None
        if target is None:
            scope = self.active_scope()
            target = next((w for w in reversed(self.windows) if w.scope == scope), None)
        if target:
            target.widget.close()

    def run(self):
        # Ctrl-C (and a plain kill) in the terminal close the app properly, drives unmounted and all: Qt keeps Python
        # from seeing signals while it waits, so a timer gives Python a moment to notice them.
        import signal
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(sig, lambda *_: self.app.quit())
            except (ValueError, OSError):
                pass
        self._signal_tick = QTimer()
        self._signal_tick.timeout.connect(lambda: None)
        self._signal_tick.start(300)
        return self.app.exec()
