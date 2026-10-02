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
import sys
import tempfile
import time
from pathlib import Path

from lupa import lua54
from PySide6.QtCore import QEventLoop, Qt, QTimer
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QApplication, QFileDialog, QLabel, QMessageBox, QVBoxLayout, QWidget

from .registry import (REGISTRY, ControlType, box_add, box_place, css_id, layout_remove, make_box, theme_sheets,
                       truthy)
from .design import DESIGN_DEFAULTS  # importing design also registers DesignSurface and PropertyGrid
from .store import LUA_DIR, PARSER_LOG, Store

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


class Engine:
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
        self.listeners = []                    # called (name, prop, value) after every SetProperty
        self._quiet = 0                        # >0 while scripts set properties: Qt signals then aren't user events
        self._script_stack, self._scope_stack = [], []
        self._init_lua(lua_paths)
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
        opening = bool(node.props.get("OnOpened"))
        if opening:
            w.setWindowOpacity(0.0)                          # build first, then appear: no half-drawn flash
        w.show()
        if node.props.get("Resizable", "true").lower() == "false":
            w.setFixedSize(w.size())
        self.windows.append(node)
        if opening:
            def opened():
                try:
                    self.fire(node, "OnOpened", {})
                finally:
                    self.app.processEvents()
                    w.setWindowOpacity(1.0)
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
        """Script name | Script(arg, ...) | VmlCommand arg ... | Lua code."""
        if self.store.script(handler):
            return self.run_script(handler, node.name, origin=node)
        m = self.HANDLER_CALL.match(handler)
        if m and self.store.script(m.group(1)):
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
        self.lua = lua54.LuaRuntime(unpack_returned_tuples=True)
        g = self.lua.globals()
        g.Vml = self.vml
        g.print = lambda *a: log("[lua] " + "\t".join("nil" if x is None else str(x) for x in a))
        self._lua_paths_add(str(LUA_DIR), str(SYSTEM_DIR / "lua"), *extra_paths)

    def _lua_paths_add(self, *dirs):
        for d in dirs:
            self.lua.execute("local d = ...; package.path = d .. '/?.lua;' .. package.path", d)

    def lua_exec(self, code, args=(), label="lua", origin=None):
        self._script_stack.append(origin)
        g = self.lua.globals()
        saved = (g.arg, g.args)
        try:
            g.arg = g.args = self.lua.table_from(list(args))
            return self.lua.execute(code, *args)
        except Exception as exc:
            log(f"script error in {label}: {exc}")
            return None
        finally:
            g.arg, g.args = saved
            self._script_stack.pop()

    def _init_shell(self):
        """Bash scripts call `vml-parse` and read $VML_DB_PATH, as in the Avalonia engine."""
        self.bin_dir = Path(tempfile.mkdtemp(prefix="vml-bin-"))
        shim = self.bin_dir / "vml-parse"
        shim.write_text(f'#!/bin/sh\nexec "{sys.executable}" -m vml.parsecli "$@"\n')
        shim.chmod(0o755)
        self.env = dict(os.environ, VML_DB_PATH=self.store.path,
                        PATH=f"{self.bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
                        PYTHONPATH=str(Path(__file__).resolve().parent.parent))

    def run_script(self, name, *args, origin=None):
        found = self.store.script(name)
        if not found:
            log(f"RunScript: no script called '{name}'")
            return ""
        interp, content = (found[0] or "lua").lower(), found[1] or ""
        if interp == "lua":
            r = self.lua_exec(content, args, label=name, origin=origin)
            return "" if r is None else r
        if interp in ("bash", "sh"):
            return self.shell(["bash", "-c", content, name, *map(str, args)], name)
        if interp in ("powershell", "pwsh"):
            exe = shutil.which("pwsh") or shutil.which("powershell")
            if not exe:
                log(f"{name}: PowerShell isn't installed on this machine")
                return ""
            return self.shell([exe, "-NoProfile", "-Command", content], name)
        log(f"{name}: '{interp}' scripts aren't supported by this engine (Lua, Bash and PowerShell are)")
        return ""

    def shell(self, argv, label="shell"):
        try:
            r = subprocess.run(argv, capture_output=True, text=True, env=self.env, timeout=120)
        except Exception as exc:
            log(f"{label}: {exc}")
            return ""
        for line in (r.stdout + r.stderr).splitlines():
            log(f"[{label}] {line}")
        return r.stdout.rstrip("\n")

    # ================================================================ the Vml() API

    def vml(self, command, *args):
        fn = getattr(self, "cmd_" + str(command), None)
        if fn is None:
            log(f'Vml("{command}") isn\'t implemented yet')
            return ""
        args = ["" if a is None else (a if isinstance(a, (int, float)) else str(a)) for a in args]
        try:
            r = fn(*args)
        except TypeError as exc:
            log(f'Vml("{command}"): wrong arguments ({exc})')
            return ""
        except Exception as exc:
            log(f'Vml("{command}"): {exc}')
            return ""
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
        if self._menu_target(name):
            return self._menu_get(name, prop)
        node, prop = self._resolve(self._node(name), prop)
        p = node.type.props.get(prop)
        if p and p.read:
            return p.read(node)
        return node.props.get(prop, p.default if p else "")

    def cmd_GetControlPropertiesJson(self, name):
        """Reflection: every property this control has, with its live value and editor; composites list their mapped ones first."""
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
        if self._menu_target(name):
            return "MenuItem"
        node = self._node(name)
        return getattr(node, "template", None) or node.type.name

    # --- settings
    def cmd_GetSetting(self, key):
        return self.store.get_setting(key)

    def cmd_SetSetting(self, key, value=""):
        self.store.set_setting(key, value)

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
        return self.shell(["bash", "-c", command], "shell")

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
            if getattr(ct, "virtual", False) or getattr(ct, "design_only", False) or ct.name in ("Window", "TinyMenu"):
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
            if key in defaults and ctype in ("Button", "CheckBox", "TextBlock", "Frame"):
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
        surf.widget.set_menu([])
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
        if menu:
            out += [f"@DockPanel {form}Root", f"Parent={form}", "",
                    f"@TinyMenu {form}Menu", f"Parent={form}Root", "DockPanel.Dock=Top", ""]
        out += [f"@Canvas {canvas}", f"Parent={form + 'Root' if menu else form}", f"Background={g('FormBackground', '#ffffff')}"]
        for key, prop in (("Resizable", "FormResizable"), ("Modal", "FormModal"), ("MinWidth", "FormMinWidth"),
                          ("MinHeight", "FormMinHeight"), ("MaxWidth", "FormMaxWidth"), ("MaxHeight", "FormMaxHeight")):
            v = str(surf.props.get(prop, "") or "")
            if v and not (key == "Resizable" and v == "true") and not (key == "Modal" and v == "false"):
                out.insert(out.index(f"@Canvas {canvas}") - 1, f"{key}={v}")      # with the window's own lines
        first = ["Canvas.Left", "Canvas.Top", "Width", "Height"]

        def walk(container, parent_name):
            for kid in container.children:
                yield kid, parent_name
                if kid.type.name == "Frame":
                    yield from walk(kid, kid.name)
        everything = list(walk(surf, canvas))
        for kid, parent_name in everything:
            ctype = getattr(kid, "template", None) or kid.type.name
            skip = dict(self.templates[ctype].parts[0][3]) if ctype in self.templates else {}
            out += ["", f"@{ctype} {kid.name}", f"Parent={parent_name}"]
            keys = [k for k in first if k in kid.props] + sorted(k for k in kid.props if k not in first)
            for k in keys:
                v = str(kid.props.get(k, ""))
                if k in ("Name", "X", "Y", "IsHitTestVisible", "Focusable") or v == "" or skip.get(k) == v:
                    continue
                out.append(f"{k}={v.replace(chr(10), ' ')}")
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
        for kid, _ in everything:
            for event, (interp, code) in getattr(kid, "design_scripts", {}).items():
                name = kid.props.get(event) or f"{kid.name}_{event}"
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
        if window is None or canvas is None:
            log(f"{path}: only forms laid out on a Canvas can be designed here (this one uses layout panels)")
            return False
        self.cmd_ClearDesign(surf.name)
        wp, cp = props[window[0]], props[canvas[0]]
        by_id, menu = {r[0]: r for r in rows}, []
        for cid, parent_id, ctype, name in rows:
            if ctype != "MenuItem":
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
        surf.widget.set_menu(menu)
        if menu:
            wp = dict(wp, Height=str(int(float(wp.get("Height", 480))) - surf.widget.menu_h()))
        for k, v in (("FormName", window[3]), ("FormTitle", wp.get("Title", window[3])),
                     ("FormWidth", wp.get("Width", "640")), ("FormHeight", wp.get("Height", "480")),
                     ("FormBackground", cp.get("Background", "#ffffff"))):
            self.cmd_SetProperty(surf.name, k, v)
        for key, prop in (("Resizable", "FormResizable"), ("Modal", "FormModal"), ("MinWidth", "FormMinWidth"),
                          ("MinHeight", "FormMinHeight"), ("MaxWidth", "FormMaxWidth"), ("MaxHeight", "FormMaxHeight")):
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
        log(f"opened {path}: {count} controls")
        return True



    # --- the designed form's menu (the Menu Editor's side)
    def _menu_slug(self, text):
        base = re.sub(r"[^A-Za-z0-9]", "", str(text).replace("&", "")) or "Item"
        return "mnu" + base[0].upper() + base[1:]

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

    def cmd_MenuAddItem(self, target="", where="after", surface="Surface"):
        """Add a menu item before or after another, as its first submenu item ("child"), or start a menu ("first")."""
        surf = self._surface(surface)
        items = surf.widget.menu_items
        existing = {it["name"] for it in items}
        n = 1
        while f"mnuItem{n}" in existing:
            n += 1
        new = {"name": f"mnuItem{n}", "text": f"Item{n}", "shortcut": "", "level": 0, "separator": False, "enabled": True}
        _, _, i = self._menu_item(target) if target else (None, None, None)
        if i is None:
            if not items:
                new.update(name="mnuFile" if "mnuFile" not in existing else new["name"], text="&File")
            items.append(new)
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
        del items[i:end]
        surf.widget.set_menu(items)
        surf.widget.select("", user=True)
        surf.widget.emit("OnChanged", {"selected_control": ""})
        return True

    # --- design scripts (the script editor's side)
    SHELL = "powershell" if sys.platform.startswith("win") else "bash"

    def cmd_GetShellName(self):
        return "PowerShell" if self.SHELL == "powershell" else "Bash"

    def cmd_GetControlEvents(self, name):
        mt = self._menu_target(name)
        if mt:
            surf, item = mt
            return json.dumps([{"name": "OnClick", "has_script": f"{item}_Click" in getattr(surf, "menu_scripts", {})}])
        node = self._node(name)
        scripts = getattr(node, "design_scripts", {})
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
            return json.dumps({"language": "Lua" if interp == "lua" else "Shell", "code": code, "script": handler})
        node = self._node(name)
        interp, code = getattr(node, "design_scripts", {}).get(event, ("lua", ""))
        return json.dumps({"language": "Lua" if interp == "lua" else "Shell", "code": code,
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
            surf.menu_scripts[handler] = ("lua" if lang == "lua" else self.SHELL, str(code))
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
        lang = str(language).lower()
        interp = "lua" if lang == "lua" else (lang if lang in ("bash", "powershell") else self.SHELL)
        node.design_scripts[event] = (interp, str(code))
        script_name = node.props.get(event) or f"{name}_{event}"
        self.cmd_SetEvent(name, event, script_name)
        surf = node.parent if node.parent is not None and node.parent.type.name == "DesignSurface" else None
        if surf is not None:
            surf.widget.emit("OnChanged", {"selected_control": name})
        return script_name

    def cmd_PreviewDesign(self, surface="Surface"):
        """Run the form being designed, for real, in its own window."""
        surf = self._surface(surface)
        path = Path(tempfile.gettempdir()) / f"vml-preview-{surf.name}.vml"
        for w in [w for w in self.windows if w.scope == str(path.resolve())]:
            w.widget.close()
            self.windows.remove(w)
        self.cmd_ExportVml(surf.name, str(path))
        self.load(path)
        return str(path)

    # --- forms and dialogs
    def _form_path(self, path):
        p = Path(os.path.expanduser(path))
        if not p.is_absolute():
            p = Path(self.active_scope() or ".").parent / p
        return p

    def cmd_FormOpen(self, path):
        self.load(self._form_path(path))

    def cmd_FormOpenModal(self, path):
        p = self._form_path(path)
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
        return self.windows[-1].widget if self.windows else None

    def cmd_InfoDialog(self, message, title="Information"):
        QMessageBox.information(self._parent_window(), str(title), str(message))

    def cmd_ErrorDialog(self, message, title="Error"):
        QMessageBox.critical(self._parent_window(), str(title), str(message))

    def cmd_ConfirmDialog(self, message, title="Confirm"):
        return QMessageBox.question(self._parent_window(), str(title), str(message)) == QMessageBox.Yes

    def cmd_FileOpenDialog(self, title="Open", ext=""):
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
