"""
The VML engine.

  Store (SQLite) -> Nodes (one per control: Qt widget + a host for margins) -> windows on screen.
  Scripts talk to all of it through one function, Vml("Command", args...), exactly as in the
  Avalonia engine, so existing Lua scripts run unchanged.

  Each opened form is a *scope*: two forms may both have a "MainGrid", and a script finds the one
  in its own form first.
"""
import json
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
from PySide6.QtCore import QEventLoop, Qt, QTimer, QUrl
from PySide6.QtGui import QCursor, QDesktopServices
from PySide6.QtWidgets import QApplication, QFileDialog, QLabel, QVBoxLayout, QWidget

from .registry import (REGISTRY, ControlType, box_add, box_place, css_id, layout_remove, make_box, theme_sheets,
                       truthy)
from .design import DESIGN_DEFAULTS  # importing design also registers DesignSurface and PropertyGrid
from .store import LUA_DIR, PARSER_LOG, Store
from .data import DataCommands
from .projects import ProjectCommands
from .library import LibraryCommands
from . import dialogs, licence as licences

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


class Engine(DataCommands, ProjectCommands, LibraryCommands):
    log_line = staticmethod(log)

    def __init__(self, db_path=None, lua_paths=()):
        self.app = QApplication.instance() or QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(True)
        if db_path is None:
            fd, db_path = tempfile.mkstemp(prefix="vml-", suffix=".db")
            os.close(fd)
        self.store = Store(db_path)
        self.scopes: dict[str, dict[str, Node]] = {}
        self.windows, self.templates, self.themes, self.menubars = [], {}, {}, {}
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
            for cid, ctype, name in self.store.roots(vml_path):
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
        if hasattr(w, "set_edge") and not node.props.get("BorderBrush") and node.props.get("BorderThickness") in (None, "") \
                and theme.get("Background"):
            w.set_edge(theme["Background"], 1)               # an edge the colour of its menu bar
        if hasattr(w, "closeEvent") and isinstance(w, QWidget):
            w.closing = lambda by_user=False: self._closing(node, by_user)
        opening = bool(node.props.get("OnOpened"))
        if opening:
            w.setWindowOpacity(0.0)                          # build first, then appear: no half-drawn flash
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

    def _style_menus(self, scope):
        t = self.themes.get(scope)
        if not t:
            return
        bar_css, popup_css = theme_sheets(t)
        bar = self._menubar(scope)
        if bar:
            bar.widget.setStyleSheet(bar_css)
        for node in self.scopes.get(scope, {}).values():
            if getattr(node, "menu", None) is not None:
                node.menu.setStyleSheet(popup_css)

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
        rt = self.lua_state(self.lua_key(origin=origin) if key is None else key)
        g = rt.globals()
        saved = (g.arg, g.args)
        try:
            g.arg = g.args = rt.table_from(list(args))
            return rt.execute(code, *args)
        except Exception as exc:
            log(f"script error in {label}: {exc}")
            return None
        finally:
            g.arg, g.args = saved
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
        try:
            r = f(*[a if isinstance(a, (bool, int, float)) else str(a) for a in args])
            return "" if r is None else r
        except Exception as exc:
            log(f"script error in {name}: {exc}")
            return ""
        finally:
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
        try:
            return self.vml_strict(command, *args)
        except Exception as exc:
            log(f'Vml("{command}"): {exc}')
            return ""

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
        self._reflow(outer)
        for listener in list(self.listeners):
            try:
                listener(outer.name, prop, value)
            except Exception as exc:
                log(f"property listener: {exc}")

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
    def cmd_GetSetting(self, key):
        return self.store.get_setting(key)

    def cmd_SetSetting(self, key, value=""):
        self.store.set_setting(key, value)

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
            req = urllib.request.Request("https://api.github.com/repos/wallisoft/vml-releases/releases/latest",
                                         headers={"User-Agent": f"Visualised/{__version__}"})
            with urllib.request.urlopen(req, timeout=6) as r:
                out["latest"] = str(json.load(r).get("tag_name", "")).lstrip("v")
            number = lambda v: tuple(int(x) for x in re.findall(r"\d+", v)[:3])
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

    def cmd_GetControlTypes(self):
        """Every control type a designer can add: built-ins from the registry, plus VML composites."""
        out = []
        for ct in REGISTRY.values():
            if getattr(ct, "virtual", False) or getattr(ct, "design_only", False) or ct.name in ("Window", "TinyMenu", "Splitter"):
                continue
            out.append({"name": ct.name, "category": ct.category, "container": ct.container})
        comp_dir = SYSTEM_DIR / "CompositeControls"
        if comp_dir.is_dir():
            for f in sorted(comp_dir.glob("*.vml")):
                if f.stem.startswith("Dummy") or f.read_text(errors="ignore").lstrip().startswith("<"):
                    continue
                out.append({"name": f.stem, "category": "Composite", "container": False})
        order = {"Common": 0, "Containers": 1, "Composite": 2}
        return json.dumps(sorted(out, key=lambda t: (order.get(t["category"], 9), t["name"])))

    def cmd_AddDesignControl(self, ctype, x=0, y=0, surface="Surface"):
        """Add a control where the user right-clicked: inside a Frame if the click was in one."""
        surf = self._surface(surface)
        view = surf.widget
        from PySide6.QtCore import QPoint
        page_pt = view.form.pos() + QPoint(int(float(x or 0)), int(float(y or 0)))
        container = view.container_at(page_pt) or surf
        if container is not surf:
            local = container.widget.mapFrom(view.page, page_pt)
            x, y = local.x(), local.y()
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
        for k, v in defaults.items():
            self.cmd_SetProperty(name, k, v)
        surf.widget.select(name, user=True)
        surf.widget.emit("OnChanged", {"selected_control": name})
        return name

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
        for ev in ("OnOpened", "OnClosing", "OnKeyDown", "OnKeyUp"):
            surf.props.pop(ev, None)
        for prop in ("FormBorder", "FormResizable", "FormModal", "FormMinWidth", "FormMinHeight", "FormMaxWidth", "FormMaxHeight"):
            if surf.props.get(prop):                         # the last form's window options don't carry over
                self.cmd_SetProperty(surf.name, prop, "")
        surf.widget.menu_settings = {}
        surf.widget.set_menu([])
        surf.widget.apply_menu_settings()
        for k, v in (("FormName", "Form1"), ("FormTitle", "Form1"), ("FormWidth", "640"), ("FormHeight", "480"),
                     ("FormBackground", "#ffffff")):
            self.cmd_SetProperty(surf.name, k, v)

    def cmd_ExportVml(self, surface, path):
        """Write the designed form as VML: a Window holding a Canvas holding the controls."""
        surf = self._surface(surface)
        g = lambda k, d: str(self.cmd_GetProperty(surf.name, k) or d)
        form, canvas = g("FormName", "Form1"), g("FormName", "Form1") + "Canvas"
        menu = surf.widget.menu_items
        mh = surf.widget.menu_h()
        out = [f"# {form}: designed in the VML designer", "", f"@Window {form}", f"Title={g('FormTitle', form)}",
               f"Width={g('FormWidth', 640)}", f"Height={int(float(g('FormHeight', 480))) + mh}", ""]
        settings = {k: v for k, v in surf.widget.menu_settings.items() if v not in ("", None)}
        if menu:
            out += [f"@DockPanel {form}Root", f"Parent={form}", "",
                    f"@TinyMenu {form}Menu", f"Parent={form}Root", "DockPanel.Dock=Top"]
            if str(settings.get("OpenOnHover", "")).lower() == "true":
                out.append("OpenOnHover=true")
            out.append("")
            theme = {k: v for k, v in settings.items() if k != "OpenOnHover"}
            if theme:
                out += [f"@MenuTheme {form}MenuTheme", *[f"{k}={v}" for k, v in theme.items()], ""]
        out += [f"@Canvas {canvas}", f"Parent={form + 'Root' if menu else form}", f"Background={g('FormBackground', '#ffffff')}"]
        for key, prop in (("Resizable", "FormResizable"), ("Modal", "FormModal"), ("MinWidth", "FormMinWidth"),
                          ("MinHeight", "FormMinHeight"), ("MaxWidth", "FormMaxWidth"), ("MaxHeight", "FormMaxHeight"),
                          ("BorderBrush", "FormBorder"),
                          ("OnOpened", "OnOpened"), ("OnClosing", "OnClosing"), ("OnKeyDown", "OnKeyDown"), ("OnKeyUp", "OnKeyUp")):
            v = str(surf.props.get(prop, "") or "")
            if v and not (key == "Resizable" and v == "true") and not (key == "Modal" and v == "false"):
                end = out.index("", out.index(f"@Window {form}"))   # the end of the window's own lines
                out.insert(end, f"{key}={v}")
        first = ["Canvas.Left", "Canvas.Top", "Width", "Height"]
        real = lambda n: getattr(surf, "export_names", {}).get(n, n)   # a working name back to the form's own name

        def walk(container, parent_name):
            for kid in container.children:
                yield kid, parent_name
                if kid.type.name == "Frame":
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
        for ctype, name, parent, cprops in getattr(surf, "carried", []):     # right-click menus, exactly as they came
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
        Path(os.path.expanduser(path)).write_text("\n".join(out) + "\n", encoding="utf-8")
        log(f"saved {len(everything)} controls to {path}")
        return True

    def cmd_ImportVml(self, path, surface="Surface"):
        """Open a VML form for editing: its Window becomes the form, its Canvas's controls the design."""
        surf = self._surface(surface)
        rows, props, scripts = self.store.parse_form(os.path.expanduser(path))
        while PARSER_LOG:
            log(PARSER_LOG.pop(0))
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
        carried_ids = {r[0] for r in rows if r[2] in ("ContextMenu", "MenuItem") and in_context_menu(r[0])}
        carried = [(r[2], r[3], by_row[r[1]][3] if r[1] in by_row else None, dict(props.get(r[0], {})))
                   for r in rows if r[0] in carried_ids]
        self.cmd_ClearDesign(surf.name)
        surf.export_names, surf.carried = {new: old for old, new in renamed.items()}, carried
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
                          ("BorderBrush", "FormBorder")):
            if wp.get(key):
                self.cmd_SetProperty(surf.name, prop, wp[key])
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
        for ev in ("OnOpened", "OnClosing", "OnKeyDown", "OnKeyUp"):
            handler = wp.get(ev)
            if handler and handler in scripts:
                surf.design_scripts[ev] = scripts[handler]
                self.cmd_SetEvent(surf.name, ev, handler)
            elif handler:                                    # a module's function, or Name(arguments): kept as written
                self.cmd_SetEvent(surf.name, ev, handler)
        surf.form_scripts = {n: v for n, v in scripts.items() if n not in used}
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
        if not self.needs("import", "Importing forms from other tools"):
            return ""
        source = Path(os.path.expanduser(str(path)))
        name = self.importer_for(kind, source)
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
            events = ["OnOpened", "OnClosing", "OnKeyDown", "OnKeyUp"]
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
        """Write a form as one self-contained web page. source: a design surface, or a .vml file. (Pro.)"""
        if not self.needs("export", "Exporting a form as a web page"):
            return ""
        return self._export_html(source, out)

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

                def end_headers(self):                          # always the newest: a phone keeps old pages hard
                    self.send_header("Cache-Control", "no-store")
                    super().end_headers()
            self._phone_server = ThreadingHTTPServer(("0.0.0.0", 0), functools.partial(Quiet, directory=str(folder)))
            threading.Thread(target=self._phone_server.serve_forever, daemon=True).start()
        return f"http://{address}:{self._phone_server.server_address[1]}/"

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
        self.load(path)
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
        """The window a dialog belongs to: the one in use, else the newest still on screen."""
        active = QApplication.activeWindow()
        if active is not None and getattr(active, "vml_node", None) is not None and active.isVisible():
            return active
        shown = [w.widget for w in self.windows if w.widget.isVisible()]
        return shown[-1] if shown else None

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

    def cmd_FileOpenDialog(self, title="Open", ext=""):
        kinds = [e.strip().lstrip(".") for e in str(ext).split(",") if e.strip()]       # "vml", or "vb,cs" for several
        if len(kinds) > 1:
            filt = f"{' and '.join(k.upper() for k in kinds)} files ({' '.join('*.' + k for k in kinds)});;All files (*)"
        else:
            filt = f"{ext.upper()} files (*.{ext});;All files (*)" if ext else "All files (*)"
        return QFileDialog.getOpenFileName(self._parent_window(), str(title), "", filt)[0]

    def cmd_FileSaveDialog(self, title="Save", default="", ext=""):
        filt = f"{ext.upper()} files (*.{ext});;All files (*)" if ext else "All files (*)"
        name = f"{default}.{ext}" if default and ext and not str(default).endswith("." + ext) else str(default)
        return QFileDialog.getSaveFileName(self._parent_window(), str(title), name, filt)[0]

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
        return self.app.exec()
