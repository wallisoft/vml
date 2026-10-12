"""
VML -> HTML: one self-contained page per form.

The form is read exactly as the desktop engine reads it (the Lua parser, into SQLite), then each control
becomes an element. Canvas forms are absolutely positioned and their anchors become CSS, so they move and
stretch as the browser window resizes. Layout panels map to flexbox and CSS grid; DockPanel's
carve-the-space rule is rebuilt with nested flexboxes. Lua scripts run in the browser (Lua 5.4 compiled to
WebAssembly, via Wasmoon) against a JavaScript Vml() that speaks the same commands.
"""
import html
import json
import os
import re
from pathlib import Path

from .registry import anchor_set, colour, num, thickness
from .store import LUA_DIR, Store

# Wasmoon (Lua in WebAssembly), bundled so pages work offline. Beside the package from source; at the top of a
# compiled build (like the Lua files).
WEB_DIR = next((d for d in (Path(__file__).resolve().parent / "web", Path(__file__).resolve().parent.parent / "web")
                if (d / "glue.wasm").is_file()), Path(__file__).resolve().parent / "web")

WASMOON = "https://cdn.jsdelivr.net/npm/wasmoon@1.16.0/+esm"
SQLJS = "https://cdn.jsdelivr.net/npm/sql.js@1.13.0/dist/"      # SQLite in WebAssembly, for pages that use a database
MAX_DATABASE = 16_000_000        # a SQLite file bigger than this isn't put inside a page
MENU_H = 26
WEIGHTS = {"Thin": 100, "ExtraLight": 200, "Light": 300, "Normal": 400, "Medium": 500, "SemiBold": 600,
           "Bold": 700, "ExtraBold": 800, "Black": 900}
EVENT_NAMES = ("OnClick", "TextChanged", "SelectionChanged", "OnKeyDown", "OnKeyUp", "OnPointerPressed",
               "OnPointerReleased", "OnPointerMoved", "OnLostFocus", "OnGotFocus", "OnChecked", "OnOpened", "OnDoubleClick", "OnTick",
               "ValueChanged")
FIT = {"Fill": "fill", "UniformToFill": "cover", "None": "none"}        # Image.Stretch -> CSS object-fit
EMBED_LIMIT = 2_000_000          # a picture file smaller than this goes inside the page, so the page stays one file
MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif", ".bmp": "image/bmp",
        ".svg": "image/svg+xml", ".webp": "image/webp"}


def css_id(name):
    return "v_" + re.sub(r"[^A-Za-z0-9_]", "_", str(name))


def esc(s):
    return html.escape(str(s or ""), quote=True)


class Page:
    def __init__(self, vml_path, project=None, base_dir=None):
        self.path = Path(vml_path)
        self.base = Path(base_dir) if base_dir else self.path.parent      # where the form's pictures are
        rows, props, scripts = Store(":memory:").parse_form(str(vml_path))
        self.rows = rows
        self.props = props
        self.scripts = scripts
        self.by_id = {r[0]: r for r in rows}
        self.kids = {}
        for cid, parent_id, ctype, name in rows:
            self.kids.setdefault(parent_id, []).append(cid)
        self.handlers = []                 # (element id, event, handler, control name)
        self.names = {}                    # control name -> element id
        self.menus = {}                    # ContextMenu name -> html
        self.modules = []                  # a project's modules: Lua every script can use
        from .projects import project_for
        project = project or project_for(self.path)
        self.project = project
        self.project_name = project.name if project is not None else ""
        if project is not None:
            for rel in project.modules:
                try:
                    self.modules.append({"name": rel, "code": project.absolute(rel).read_text(encoding="utf-8-sig", errors="replace")})
                except OSError:
                    pass

    def link_pass(self, wp, scripts):
        """The pass a page that uses Link goes out with: the one saved in the form, or else this computer's own
        if it has a Pro licence. "" otherwise: its links are then on the relay's free allowance. (vml/link.py)"""
        stamped = str(wp.get("LinkPass") or "")
        if stamped.startswith("VP1-"):
            return stamped
        if os.environ.get("VML_NO_LINK_PASS") or not any(re.search(r"""["']Link(Pair)?["']""", s["code"]) for s in scripts.values()):
            return ""
        try:
            from . import licence
            return licence.link_pass()
        except Exception:
            return ""

    def sources(self):
        """The controls that fill themselves: [{name, src, db}]."""
        return [{"name": self.by_id[c][3], "src": self.props[c]["ItemsSource"], "db": self.props[c].get("Database", "")}
                for c in self.props if str(self.props[c].get("ItemsSource") or "").strip() and c in self.by_id]

    def uses_data(self):
        """Does this page need a database engine? Yes if anything fills itself from a query, or a script asks one."""
        code = "\n".join(c or "" for _, c in self.scripts.values()) + "\n".join(m["code"] for m in self.modules)
        return bool(self.sources()) or bool(re.search(r"""["'](Db[A-Z]\w+|SqlQuery|SqlExecute|Requery)["']""", code))

    def databases(self):
        """The project's SQLite files, to travel inside the page: {name: {file, data (base64), hash}}."""
        import base64
        import hashlib
        out = {}
        if self.project is None:
            return out
        for name, address in self.project.databases.items():
            kind, _, rest = address.partition(":")
            rel = rest.strip() if kind.strip().lower() == "sqlite" else address.strip()
            if "=" in rel or kind.strip().lower() == "odbc":
                continue                                    # ODBC: there is no such thing in a web page
            file = Path(rel) if Path(rel).is_absolute() else self.project.folder / rel
            try:
                if file.stat().st_size > MAX_DATABASE:
                    continue
                raw = file.read_bytes()
            except OSError:
                raw = b""                                   # not made yet: it starts empty in the page, as it would on disk
            out[name] = {"file": file.name, "data": base64.b64encode(raw).decode(),
                         "hash": hashlib.sha1(raw).hexdigest()[:12] if raw else "new"}
        return out

    def app_tags(self, wp):
        """The app's version and icon, where a browser's tab and the phone app look for them."""
        out = ""
        if str(wp.get("Version") or "").strip():
            out += f'<meta name="app-version" content="{esc(str(wp["Version"]).strip())}">\n'
        if str(wp.get("AndroidPackage") or "").strip():              # its own name as an Android app, if its maker chose one (vml/apk.py)
            out += f'<meta name="android-package" content="{esc(str(wp["AndroidPackage"]).strip())}">\n'
        if str(wp.get("AndroidKey") or "").strip():                  # and which key it was last exported with
            out += f'<meta name="android-key" content="{esc(str(wp["AndroidKey"]).strip())}">\n'
        icon = self.picture(wp.get("Icon"))
        if icon:
            out += f'<link rel="icon" href="{esc(icon)}">\n<link rel="apple-touch-icon" href="{esc(icon)}">\n'
        return out

    def picture(self, src):
        """An Image's Source for the page: a small file beside the form goes inside the page itself."""
        src = str(src or "").strip()
        if not src or src.startswith(("data:", "http://", "https://")):
            return src
        file = Path(src) if Path(src).is_absolute() else self.base / src
        try:
            if file.suffix.lower() in MIME and file.stat().st_size <= EMBED_LIMIT:
                import base64
                return f"data:{MIME[file.suffix.lower()]};base64,{base64.b64encode(file.read_bytes()).decode()}"
        except OSError:
            pass
        return src

    # ------------------------------------------------------------------ styles

    def style(self, p, ctype):
        css = []
        if p.get("Background") and ctype not in ("Rectangle",):
            css.append(f"background:{colour(p['Background'])}")
        if p.get("Fill"):
            css.append(f"background:{colour(p['Fill'])}")
        if p.get("Foreground"):
            css.append(f"color:{colour(p['Foreground'])}")
        if p.get("FontSize"):
            css.append(f"font-size:{int(num(p['FontSize'], 13))}px")
        if p.get("FontWeight"):
            css.append(f"font-weight:{WEIGHTS.get(p['FontWeight'], 400)}")
        if p.get("FontFamily"):
            css.append(f"font-family:{p['FontFamily']}")
        brush = p.get("BorderBrush") or p.get("Stroke")
        width = p.get("BorderThickness") or p.get("StrokeThickness")
        if (brush or width) and ctype != "Frame":
            l, t, r, b = thickness(width or "1")
            css.append(f"border-style:solid;border-color:{colour(brush or '#808080')};border-width:{t}px {r}px {b}px {l}px")
        if p.get("CornerRadius"):
            css.append(f"border-radius:{int(num(str(p['CornerRadius']).split(',')[0]))}px")
        if p.get("Padding"):
            l, t, r, b = thickness(p["Padding"])
            css.append(f"padding:{t}px {r}px {b}px {l}px")
        if p.get("Margin"):
            l, t, r, b = thickness(p["Margin"])
            css.append(f"margin:{t}px {r}px {b}px {l}px")
        if str(p.get("IsVisible", "true")).lower() == "false":
            css.append("display:none")
        return css

    def size(self, p):
        css = []
        for prop, key in (("Width", "width"), ("Height", "height"), ("MinWidth", "min-width"), ("MinHeight", "min-height"),
                          ("MaxWidth", "max-width"), ("MaxHeight", "max-height")):
            v = p.get(prop)
            if v not in (None, "", "Auto", "NaN"):
                css.append(f"{key}:{int(num(v))}px")
        return css

    def placed(self, p, parent_type, ref):
        """How a child sits in its parent: absolutely (Canvas, Frame) with anchors as CSS, or in the flow."""
        if parent_type not in ("Canvas", "Frame"):
            return self.size(p)
        x, y = int(num(p.get("Canvas.Left"))), int(num(p.get("Canvas.Top")))
        has_w = p.get("Width") not in (None, "", "Auto")
        has_h = p.get("Height") not in (None, "", "Auto")
        w, h = int(num(p.get("Width"))), int(num(p.get("Height")))
        a = anchor_set(p.get("Anchor"))
        css = ["position:absolute"]
        if "Left" in a and "Right" in a and ref and has_w:
            css += [f"left:{x}px", f"right:{int(ref[0] - x - w)}px"]
        elif "Right" in a and ref and has_w:
            css += [f"right:{int(ref[0] - x - w)}px", f"width:{w}px"]
        else:
            css += [f"left:{x}px"] + ([f"width:{w}px"] if has_w else [])
        if "Top" in a and "Bottom" in a and ref and has_h:
            css += [f"top:{y}px", f"bottom:{int(ref[1] - y - h)}px"]
        elif "Bottom" in a and ref and has_h:
            css += [f"bottom:{int(ref[1] - y - h)}px", f"height:{h}px"]
        else:
            css += [f"top:{y}px"] + ([f"height:{h}px"] if has_h else [])
        return css

    # ------------------------------------------------------------------ elements

    def render(self, cid, parent_type=None, ref=None, extra_css=()):
        _, _, ctype, name = self.by_id[cid]
        p = self.props.get(cid, {})
        eid = css_id(name)
        self.names[name] = eid
        for ev in EVENT_NAMES:
            if p.get(ev) and ctype != "Window":
                self.handlers.append((eid, ev, p[ev], name))
        css = self.style(p, ctype) + self.placed(p, parent_type, ref) + list(extra_css)
        disabled = " disabled" if str(p.get("IsEnabled", "true")).lower() == "false" else ""
        tip = f' title="{esc(p["ToolTip"])}"' if p.get("ToolTip") else ""
        attrs = f'id="{eid}" data-name="{esc(name)}" data-type="{ctype}"{tip}'
        kids = self.kids.get(cid, [])

        def inner(ptype, ref_size=None):
            return "".join(self.render(k, ptype, ref_size) for k in kids if self.by_id[k][2] not in ("ContextMenu",))

        if ctype == "Button":
            return f'<button {attrs} style="{";".join(css)}"{disabled}>{esc(p.get("Content", name))}</button>'
        if ctype == "TextBlock":
            wrap = "pre-wrap" if p.get("TextWrapping") == "Wrap" else "pre"            # (line breaks in the text are kept, as on the desktop)
            align = {"Center": "center", "Right": "right"}.get(p.get("TextAlignment"), "left")
            css += [f"white-space:{wrap}", f"text-align:{align}"]
            return f'<div {attrs} class="tb" style="{";".join(css)}">{esc(p.get("Text", ""))}</div>'
        if ctype == "TextBox":
            ph = esc(p.get("Watermark", ""))
            ro = " readonly" if str(p.get("IsReadOnly", "")).lower() == "true" else ""
            if str(p.get("AcceptsReturn", "")).lower() == "true":
                wrap = ' wrap="off"' if p.get("TextWrapping") == "NoWrap" else ""
                return f'<textarea {attrs}{wrap} placeholder="{ph}" style="{";".join(css)}"{ro}{disabled}>{esc(p.get("Text", ""))}</textarea>'
            kind = "password" if str(p.get("IsPassword", "")).lower() == "true" else "text"
            return f'<input type="{kind}" {attrs} value="{esc(p.get("Text", ""))}" placeholder="{ph}" style="{";".join(css)}"{ro}{disabled}>'
        if ctype == "RadioButton":
            checked = " checked" if str(p.get("IsChecked", "")).lower() == "true" else ""
            group = esc(f"{self.by_id[self.by_id[cid][1]][3] if self.by_id[cid][1] in self.by_id else 'form'}.{p.get('GroupName', '')}")
            return (f'<label {attrs} class="cb" style="{";".join(css)}"><input type="radio" name="{group}"{checked}{disabled}>'
                    f'<span>{esc(p.get("Content", ""))}</span></label>')
        if ctype == "Image":
            css.append(f"object-fit:{FIT.get(p.get('Stretch'), 'contain')}")
            src = self.picture(p.get("Source"))
            return f'<img {attrs} alt="" src="{esc(src)}" onerror="this.removeAttribute(\'src\')" style="{";".join(css)}">' if src else f'<img {attrs} alt="" style="{";".join(css)}">'
        if ctype == "DataGrid":
            cols = [c.strip() for c in str(p.get("Columns", "")).split(",") if c.strip()]
            rows = [[c.strip() for c in r.split("|")] for r in str(p.get("Items", "")).split(";") if r.strip()]
            return (f'<div {attrs} class="grid" tabindex="0" data-cols="{esc(json.dumps(cols))}" data-rows="{esc(json.dumps(rows))}" '
                    f'style="{";".join(css)}"></div>')
        if ctype == "TreeView":
            paths = [x.strip() for x in re.split(r"[,\n]", str(p.get("Items", ""))) if x.strip()]
            return f'<div {attrs} class="tree" tabindex="0" data-paths="{esc(json.dumps(paths))}" style="{";".join(css)}"></div>'
        if ctype == "CheckBox":
            checked = " checked" if str(p.get("IsChecked", "")).lower() == "true" else ""
            return (f'<label {attrs} class="cb" style="{";".join(css)}"><input type="checkbox"{checked}{disabled}>'
                    f'<span>{esc(p.get("Content", ""))}</span></label>')
        if ctype in ("ComboBox", "ListBox"):
            items = [s.strip() for s in str(p.get("Items", "")).split(",") if s.strip()]
            sel = int(num(p.get("SelectedIndex"), -1))
            opts = "".join(f'<option{" selected" if i == sel else ""}>{esc(t)}</option>' for i, t in enumerate(items))
            size = ' size="6"' if ctype == "ListBox" else ""
            return f'<select {attrs}{size} style="{";".join(css)}"{disabled}>{opts}</select>'
        if ctype == "Timer":                                    # not seen: it ticks (see wire() in the page)
            on = "false" if str(p.get("IsEnabled", "true")).lower() == "false" else "true"
            return f'<span {attrs} data-interval="{int(num(p.get("Interval"), 1000))}" data-on="{on}" hidden></span>'
        if ctype == "ProgressBar":
            css = [c for c in css if not c.startswith(("background:", "color:"))]
            style = str(p.get("BarStyle") or "Solid").lower()
            flags = "".join(f' data-{k}="{v}"' for k, v in (
                ("value", num(p.get("Value"), 0)), ("min", num(p.get("Minimum"), 0)), ("max", num(p.get("Maximum"), 100)),
                ("style", style), ("text", str(p.get("ShowText", "")).lower() == "true"),
                ("busy", str(p.get("IsIndeterminate", "")).lower() == "true"),
                ("upright", str(p.get("Orientation", "")).lower() == "vertical")))
            css += [f"--track:{colour(p.get('Background') or '#E5E7EB')}", f"--bar:{colour(p.get('Foreground') or '#2563EB')}"]
            return f'<div {attrs} class="pbar"{flags} style="{";".join(css)}"><i></i><b></b></div>'
        if ctype == "Slider":
            css = [c for c in css if not c.startswith(("background:", "color:"))]
            low, high = int(num(p.get("Minimum"), 0)), int(num(p.get("Maximum"), 100))
            return (f'<input type="range" {attrs} class="slide" min="{low}" max="{max(low, high)}" '
                    f'value="{int(num(p.get("Value"), low))}" style="{";".join(css)}"{disabled}>')
        if ctype == "Rectangle":
            return f'<div {attrs} style="{";".join(css)}"></div>'
        if ctype == "Frame":
            ref_size = (num(p.get("Width")), num(p.get("Height"))) if p.get("Width") and p.get("Height") else None
            caption = f'<span class="cap">{esc(p.get("Text", ""))}</span>' if p.get("Text") else ""
            border = colour(p.get("BorderBrush") or "#9CA3AF")
            css += [f"border:1px solid {border}", "border-radius:4px"]
            return f'<div {attrs} class="frame" style="{";".join(css)}">{caption}{inner("Frame", ref_size)}</div>'
        if ctype == "Canvas":
            win = next((r for r in self.rows if r[2] == "Window"), None)
            wp = self.props.get(win[0], {}) if win else {}
            menu = any(r[2] == "TinyMenu" for r in self.rows)
            ref = (num(wp.get("Width"), 640), num(wp.get("Height"), 480) - (MENU_H if menu else 0))
            css += ["position:relative", "flex:1", "min-height:0", "overflow:hidden"]
            return f'<div {attrs} class="canvas" style="{";".join(css)}">{inner("Canvas", ref)}</div>'
        if ctype == "StackPanel":
            horiz = p.get("Orientation") == "Horizontal"
            css += ["display:flex", f"flex-direction:{'row' if horiz else 'column'}", f"gap:{int(num(p.get('Spacing')))}px"]
            return f'<div {attrs} style="{";".join(css)}">{inner("StackPanel")}</div>'
        if ctype == "Grid":
            def track(spec):
                out = []
                for d in str(spec or "*").split(","):
                    d = d.strip()
                    out.append(f"{num(d[:-1] or 1, 1):g}fr" if d.endswith("*") else ("auto" if d == "Auto" else f"{int(num(d))}px"))
                return " ".join(out)
            css += ["display:grid", f"grid-template-columns:{track(p.get('ColumnDefinitions'))}",
                    f"grid-template-rows:{track(p.get('RowDefinitions'))}"]
            cells = []
            for k in kids:
                kp = self.props.get(k, {})
                r, c = int(num(kp.get("Grid.Row"))) + 1, int(num(kp.get("Grid.Column"))) + 1
                rs, cs = max(1, int(num(kp.get("Grid.RowSpan"), 1))), max(1, int(num(kp.get("Grid.ColumnSpan"), 1)))
                cells.append(self.render(k, "Grid", None, [f"grid-row:{r} / span {rs}", f"grid-column:{c} / span {cs}", "min-width:0"]))
            return f'<div {attrs} style="{";".join(css)}">{"".join(cells)}</div>'
        if ctype == "DockPanel":
            last_fill = str(p.get("LastChildFill", "true")).lower() != "false"
            css += ["display:flex", "flex-direction:column"]
            return f'<div {attrs} style="{";".join(css)}">{self.dock(kids, last_fill)}</div>'
        if ctype == "Border":
            centre = any(self.props.get(k, {}).get("VerticalAlignment") == "Center" for k in kids)
            css += ["display:flex", "flex-direction:column"] + (["justify-content:center"] if centre else [])
            return f'<div {attrs} style="{";".join(css)}">{inner("Border")}</div>'
        if ctype == "ScrollViewer":
            css += ["overflow:auto"]
            return f'<div {attrs} style="{";".join(css)}">{inner("ScrollViewer")}</div>'
        if ctype == "TinyMenu":
            return self.menubar(eid, attrs, css, p)
        if ctype in ("MenuItem", "MenuTheme", "Script"):
            return ""
        return f'<div {attrs} style="{";".join(css)};border:1px dashed orange">[{esc(ctype)} {esc(name)}]</div>'

    def dock(self, kids, last_fill):
        """Avalonia's DockPanel, rebuilt: each child takes its edge of whatever space is left."""
        kids = [k for k in kids if self.by_id[k][2] not in ("ContextMenu", "MenuItem", "MenuTheme")]
        if not kids:
            return ""
        if len(kids) == 1 and last_fill:
            return f'<div style="flex:1;min-height:0;min-width:0;display:flex;flex-direction:column">{self.render(kids[0], "DockFill", None, ["flex:1", "min-height:0"])}</div>'
        first, rest = kids[0], self.dock(kids[1:], last_fill)
        side = self.props.get(first, {}).get("DockPanel.Dock", "Left")
        child = self.render(first, "Dock")
        remaining = f'<div style="flex:1;min-height:0;min-width:0;display:flex;flex-direction:column">{rest}</div>'
        direction = "column" if side in ("Top", "Bottom") else "row"
        order = (child + remaining) if side in ("Top", "Left") else (remaining + child)
        return f'<div style="flex:1;min-height:0;min-width:0;display:flex;flex-direction:{direction}">{order}</div>'

    # ------------------------------------------------------------------ menus

    def menu_items(self, parent_id, top=False):
        out = []
        for k in self.kids.get(parent_id, []):
            _, _, ctype, name = self.by_id[k]
            if ctype != "MenuItem":
                continue
            p = self.props.get(k, {})
            eid = css_id(name)
            self.names[name] = eid
            if str(p.get("IsSeparator", "")).lower() == "true":
                out.append('<div class="msep"></div>')
                continue
            text = esc(p.get("Text") or p.get("Header") or name)
            text = re.sub(r"&amp;(\w)", r"<u>\1</u>", text)
            sub = self.menu_items(k)
            if p.get("OnClick"):
                self.handlers.append((eid, "OnClick", p["OnClick"], name))
            disabled = " disabled" if str(p.get("IsEnabled", "true")).lower() == "false" else ""
            key = f'<span class="key">{esc(p.get("Shortcut", ""))}</span>' if p.get("Shortcut") and not top else ""
            cls = "mtop" if top else "mi"
            out.append(f'<div class="{cls}{" has" if sub else ""}" id="{eid}" data-name="{esc(name)}" data-type="MenuItem"'
                       f'{disabled}><span class="mt">{text}</span>{key}'
                       + (f'<div class="drop">{sub}</div>' if sub else "") + "</div>")
        return "".join(out)

    def menubar(self, eid, attrs, css, p):
        roots = [r for r in self.rows if r[2] == "MenuItem" and r[1] is None]
        items = "".join(self.menu_items_for(r[0]) for r in roots)
        hover = " hover" if str(p.get("OpenOnHover", "")).lower() == "true" else ""
        return f'<div {attrs} class="menubar{hover}" style="{";".join(css + [f"min-height:{MENU_H}px"])}">{items}</div>'

    def menu_items_for(self, cid):
        # a top-level item rendered as if it were the only child of an invisible parent
        self.kids.setdefault(f"__top{cid}", [cid])
        return self.menu_items(f"__top{cid}", top=True)

    def theme_css(self):
        theme = next((self.props[r[0]] for r in self.rows if r[2] == "MenuTheme"), {})
        if not theme:
            return ""
        bg, fg = colour(theme.get("Background", "#f3f4f6")), colour(theme.get("Foreground", "#111827"))
        hbg, hfg = colour(theme.get("HoverBackground", bg)), colour(theme.get("HoverForeground", fg))
        pbg, pb = colour(theme.get("PopupBackground", "#ffffff")), colour(theme.get("PopupBorder", "#c0c0c0"))
        return (f".menubar{{background:{bg};color:{fg}}} .mtop:hover,.mtop.open{{background:{hbg};color:{hfg}}}"
                f" .drop{{background:{pbg};border-color:{pb}}}")

    def context_menus(self):
        out = []
        for r in self.rows:
            if r[2] == "ContextMenu":
                out.append(f'<div class="ctx drop" id="{css_id(r[3])}" data-name="{esc(r[3])}">{self.menu_items(r[0])}</div>')
                self.names[r[3]] = css_id(r[3])
        return "".join(out)

    # ------------------------------------------------------------------ the page

    def build(self, offline=True):
        win = next((r for r in self.rows if r[2] == "Window"), None)
        if win is None:
            raise ValueError(f"{self.path.name} has no @Window")
        wp = self.props.get(win[0], {})
        self.names[win[3]] = "vml_window"
        body = "".join(self.render(k, "Window") for k in self.kids.get(win[0], [])
                       if self.by_id[k][2] not in ("ContextMenu", "MenuItem", "MenuTheme"))
        scripts = {n: {"interp": (i or "lua").split()[0].lower(), "code": c} for n, (i, c) in self.scripts.items()}
        dkjson = (LUA_DIR / "dkjson.lua").read_text(encoding="utf-8")
        self.with_data = self.uses_data()
        main = next(iter(self.project.databases), "") if self.project is not None else ""
        theme = next((self.props[r[0]] for r in self.rows if r[2] == "MenuTheme"), {})
        self.bar_colour = colour(theme.get("Background") or wp.get("Background") or "#ffffff")
        data = {"form": win[3], "names": self.names, "scripts": scripts, "onOpened": wp.get("OnOpened", ""),
                "design": [int(num(wp.get("Width"), 0)), int(num(wp.get("Height"), 0))],     # the size it was drawn at
                "fit": str(wp.get("PhoneFit") or "Fit"), "webFit": str(wp.get("WebFit") or "Window"), "linkPass": self.link_pass(wp, scripts), "webAddress": str(wp.get("WebAddress") or ""),
                "modules": self.modules, "project": self.project_name, "sources": self.sources(),
                "data": self.with_data, "databases": self.databases() if self.with_data else {}, "mainDb": main,
                "sqljs": SQLJS, "named": list(self.project.databases) if self.project is not None else [],
                "handlers": [{"id": e, "event": ev, "handler": h, "name": n} for e, ev, h, n in self.handlers]}
        bg = colour(wp.get("Background", "#ffffff"))
        return TEMPLATE.replace("%%TITLE%%", esc(wp.get("Title", win[3]))).replace("%%BG%%", bg) \
            .replace("%%THEME%%", self.theme_css()).replace("%%BODY%%", body + self.context_menus()) \
            .replace("%%DATA%%", json.dumps(data).replace("</", "<\\/")) \
            .replace("%%DKJSON%%", json.dumps(dkjson).replace("</", "<\\/")).replace("%%WASMOON%%", WASMOON) \
            .replace("%%SOURCE%%", esc(self.path.name)).replace("%%BAR%%", self.bar_colour) \
            .replace("%%APP%%", self.app_tags(wp)) \
            .replace("%%BUNDLE%%", self.bundle() if offline else "")

    def bundle(self):
        """The Lua engine inside the page: no CDN, works offline and behind strict firewalls."""
        import base64
        js = (WEB_DIR / "wasmoon.js").read_text(encoding="utf-8").replace("</script", "<\\/script")
        wasm = base64.b64encode((WEB_DIR / "glue.wasm").read_bytes()).decode()
        out = (f"<script>{js}</script>\n"
               f'<script>window.VML_WASM = "data:application/wasm;base64,{wasm}";</script>')
        if self.with_data:                                  # SQLite too, only for pages that use a database
            sql = (WEB_DIR / "sql-wasm.js").read_text(encoding="utf-8").replace("</script", "<\\/script")
            sqlwasm = base64.b64encode((WEB_DIR / "sql-wasm.wasm").read_bytes()).decode()
            out += f'\n<script>{sql}</script>\n<script>window.VML_SQLWASM = "{sqlwasm}";</script>'
        return out


def export_html(vml_path, out_path=None, offline=True, project=None, base_dir=None):
    """offline=True (the default) puts the Lua engine inside the page (about 420 KB more); False loads it from a CDN.
    project: the form's project, when it can't be found from where the file is (its modules go in the page);
    base_dir: where the form's picture files are, if not beside vml_path."""
    page = Page(vml_path, project, base_dir).build(offline=offline)
    out = Path(out_path) if out_path else Path(vml_path).with_suffix(".html")
    out.write_text(page, encoding="utf-8")
    return str(out)


TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="%%BAR%%">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="application-name" content="%%TITLE%%">
%%APP%%<meta name="generator" content="VML (from %%SOURCE%%)">
<title>%%TITLE%%</title>
<style>
  html, body { margin: 0; height: 100%; touch-action: manipulation; -webkit-text-size-adjust: 100%; }
  body.phone { overflow-x: hidden; }
  body { font: 13px system-ui, -apple-system, "Segoe UI", Ubuntu, sans-serif; color: #111827; background: %%BG%%; }
  #vml_window { position: absolute; inset: 0; display: flex; flex-direction: column; overflow: hidden; }
  /* on a screen with room to spare the form is shown as a window: its own size, in the middle, with an edge */
  body.framed { background: #E9ECF1; }
  body.framed #vml_window { background: %%BG%%; border-radius: 10px; box-shadow: 0 0 0 1px #C9CED6, 0 10px 34px rgba(17, 24, 39, .16), 0 2px 6px rgba(17, 24, 39, .08); }   /* (the edge is drawn outside it: the form keeps its exact size) */
  #vml_window > * { flex: 1; min-height: 0; }
  #vml_window > .menubar { flex: 0 0 auto; }
  button { font: inherit; padding: 4px 10px; border: 1px solid #c4c8cf; border-radius: 4px; background: #f7f7f8; cursor: pointer; }
  button:hover { border-color: #9ca3af; } button:active { background: #e5e7eb; }
  input[type=text], input[type=password], textarea, select { font: inherit; box-sizing: border-box; border: 1px solid #c4c8cf; border-radius: 3px; padding: 3px 5px; background: #fff; }
  .grid, .tree { box-sizing: border-box; border: 1px solid #c4c8cf; background: #fff; overflow: auto; outline: none; }
  .grid table { border-collapse: collapse; width: 100%; }
  .grid th { position: sticky; top: 0; background: #f3f4f6; text-align: left; font-weight: 600; border-bottom: 1px solid #c4c8cf; padding: 3px 8px; white-space: nowrap; }
  .grid td { padding: 3px 8px; border-bottom: 1px solid #eef0f3; white-space: nowrap; cursor: default; }
  .grid tr:nth-child(even) td { background: #fafafa; }
  .grid tr.sel td, .tree .ti.sel > span { background: #2563eb; color: #fff; }
  .tree { padding: 3px 0; }
  .tree .ti > span { display: block; padding: 2px 6px; white-space: nowrap; cursor: default; }
  .tree .kids { margin-left: 16px; }
  img[data-type=Image]:not([src]) { visibility: hidden; }
  textarea { resize: none; }
  .cb { display: inline-flex; align-items: center; gap: 6px; white-space: nowrap; }
  .tb { overflow: hidden; text-overflow: ellipsis; }
  .canvas > *, .frame > * { box-sizing: border-box; }
  .slide { margin: 0; padding: 0; accent-color: #2563EB; touch-action: none; }
  .pbar { position: absolute; overflow: hidden; display: flex; align-items: center; }
  .pbar::before { content: ""; position: absolute; inset: 0; background: var(--track); border-radius: 3px; }
  .pbar > i { position: absolute; left: 0; top: 0; bottom: 0; width: 0; background: var(--bar); border-radius: 3px; }
  .pbar > b { position: relative; width: 100%; text-align: center; font-weight: normal; font-size: 12px; color: #111827; }
  .pbar[data-style="thin"]::before, .pbar[data-style="thin"] > i { top: calc(50% - 2px); bottom: calc(50% - 2px); border-radius: 2px; }
  .pbar[data-style="blocks"] > i { background: repeating-linear-gradient(90deg, var(--bar) 0 var(--blk, 10px), transparent var(--blk, 10px) calc(var(--blk, 10px) + 2px)); border-radius: 0; }
  .pbar[data-upright="True"] > i { top: auto; right: 0; width: auto; height: 0; }
  .pbar[data-upright="True"][data-style="blocks"] > i { background: repeating-linear-gradient(0deg, var(--bar) 0 var(--blk, 10px), transparent var(--blk, 10px) calc(var(--blk, 10px) + 2px)); }
  .pbar[data-busy="True"] > i { width: 30%; animation: vmlbusy 1.6s ease-in-out infinite alternate; }
  @keyframes vmlbusy { from { left: 0; } to { left: 70%; } }
  .frame { position: absolute; }
  .frame > .cap { position: absolute; top: -0.7em; left: 8px; padding: 0 4px; background: inherit; background-color: %%BG%%; line-height: 1.2; }
  .menubar { display: flex; align-items: stretch; background: #f3f4f6; border-bottom: 1px solid #e5e7eb; user-select: none; position: relative; z-index: 10; }
  .mtop { position: relative; padding: 4px 10px; cursor: default; display: flex; align-items: center; }
  .mtop:hover, .mtop.open { background: #e5e7eb; }
  .drop { display: none; position: absolute; left: 0; top: 100%; min-width: 180px; background: #fff; color: #222; border: 1px solid #c0c0c0;
          box-shadow: 0 4px 14px rgba(0,0,0,.12); padding: 4px 0; z-index: 20; }
  .mtop.open > .drop, .menubar.hover .mtop:hover > .drop { display: block; }
  .mi { position: relative; display: flex; justify-content: space-between; gap: 24px; padding: 5px 22px; white-space: nowrap; cursor: default; }
  .mi:hover { background: #2563eb; color: #fff; }
  .mi.has::after { content: "\25B8"; }
  .mi.has > .drop { left: 100%; top: -5px; }
  .mi.has:hover > .drop { display: block; }
  .mi[disabled], .mtop[disabled] { color: #9ca3af; pointer-events: none; }
  .key { color: inherit; opacity: .6; }
  .msep { height: 1px; background: #ddd; margin: 4px 8px; }
  .ctx { position: fixed; }
  %%THEME%%
  #vml_status { position: fixed; right: 8px; bottom: 6px; font-size: 11px; color: #6b7280; opacity: .8; pointer-events: none; }
</style>
</head>
<body>
<div id="vml_window">%%BODY%%</div>
<div id="vml_status">loading Lua...</div>
%%BUNDLE%%
<script type="module">
// The VML runtime for the web: Lua 5.4 (WebAssembly) running the form's scripts against a JavaScript Vml().
const VML = %%DATA%%;
const DKJSON = %%DKJSON%%;
const settings = {};
// What a script saves with SetSetting is kept in the browser (or the phone app) for the next time the app is
// opened, as it is on the desktop. Each app has its own. What the engine itself notes (event_x and the like) isn't kept.
const SETTINGS_KEY = `vmlset:${VML.project || ""}:${VML.form}`;
let keptSettings = {};
try { keptSettings = JSON.parse(localStorage.getItem(SETTINGS_KEY) || "{}") || {}; Object.assign(settings, keptSettings); } catch (err) { keptSettings = {}; }
function keepSetting(k, v) { keptSettings[k] = v; try { localStorage.setItem(SETTINGS_KEY, JSON.stringify(keptSettings)); } catch (err) {} }
const status = document.getElementById("vml_status");
const el = name => {
  const s = String(name), dot = s.indexOf(".");
  const id = VML.names[dot > 0 && s.slice(0, dot) === VML.form ? s.slice(dot + 1) : s];
  return id ? document.getElementById(id) : null;
};
const textOf = e => e.matches("input,textarea") ? e.value : e.matches("label.cb") ? e.querySelector("span").textContent
  : e.matches("[data-type=MenuItem]") ? e.querySelector(".mt").textContent : e.textContent;
const setText = (e, v) => { if (e.matches("input,textarea")) e.value = v; else if (e.matches("label.cb")) e.querySelector("span").textContent = v;
  else if (e.matches("[data-type=MenuItem]")) e.querySelector(".mt").textContent = v.replace(/&/g, ""); else e.textContent = v; };
const truthy = v => ["true", "1", "yes"].includes(String(v).toLowerCase());
let lastPointer = { x: 40, y: 40 }, lua = null;
document.addEventListener("mousemove", e => lastPointer = { x: e.clientX, y: e.clientY }, true);

// grids and trees are built here, so the page and a script filling them later go the same way
const changed = e => e.dispatchEvent(new Event("change"));
function fillGrid(e, cols, rows) {
  const keep = gridValue(e);
  e._cols = cols.map(String); e._rows = rows.map(r => r.map(v => v == null ? "" : String(v)));
  const cell = (tag, t) => { const c = document.createElement(tag); c.textContent = t; return c; };
  const table = document.createElement("table"), head = table.createTHead().insertRow(), body = table.createTBody();
  e._cols.forEach(c => head.appendChild(cell("th", c)));
  e._rows.forEach((r, i) => { const tr = body.insertRow(); tr.dataset.i = i; e._cols.forEach((_, c) => tr.appendChild(cell("td", r[c] ?? ""))); });
  e.replaceChildren(table);
  e._sel = keep === "" ? -1 : e._rows.findIndex(r => r[0] === keep);
  markGrid(e);
  if (gridValue(e) !== keep) changed(e);
}
function markGrid(e) { e.querySelectorAll("tbody tr").forEach(tr => tr.classList.toggle("sel", Number(tr.dataset.i) === e._sel)); }
const gridValue = e => e._rows && e._sel >= 0 && e._rows[e._sel] ? (e._rows[e._sel][0] ?? "") : "";
const gridItem = e => e._rows && e._sel >= 0 && e._rows[e._sel] ? JSON.stringify(Object.fromEntries(e._cols.map((c, i) => [c, e._rows[e._sel][i] ?? ""]))) : "";
function rowsFrom(json) {
  const text = String(json ?? "");
  if (!/^\s*[\[{]/.test(text)) return [["Item"], text.split("\n").filter(l => l.trim()).map(l => [l])];   // one item per line
  let data = []; try { data = JSON.parse(text); } catch { data = []; }
  if (!Array.isArray(data)) data = Object.values(data || {});
  if (data.length && data.every(d => d && typeof d === "object" && !Array.isArray(d))) { const cols = Object.keys(data[0]); return [cols, data.map(d => cols.map(c => d[c]))]; }
  if (data.length && data.every(Array.isArray)) return [data[0].map((_, i) => "Column" + (i + 1)), data];
  return [["Item"], data.map(d => [d])];
}
function fillTree(e, paths) {
  const keep = e._path || "";
  const made = new Map(); e.replaceChildren(); e._path = "";
  for (const path of paths) {
    const parts = String(path).split("/").map(s => s.trim()).filter(Boolean);
    parts.forEach((part, d) => {
      const key = parts.slice(0, d + 1).join("/");
      if (made.has(key)) return;
      const item = document.createElement("div"); item.className = "ti"; item.dataset.path = key;
      const label = document.createElement("span"); label.textContent = part; item.appendChild(label);
      const kids = document.createElement("div"); kids.className = "kids"; item.appendChild(kids);
      (d ? made.get(parts.slice(0, d).join("/")).querySelector(":scope > .kids") : e).appendChild(item);
      made.set(key, item);
    });
  }
  if (made.has(keep)) pickTree(e, keep);
  if ((e._path || "") !== keep) changed(e);
}
function fillSelect(e, items) {
  const keep = e.selectedIndex >= 0 ? e.options[e.selectedIndex].text : "";
  e.replaceChildren(...items.map(t => new Option(t)));
  const i = items.indexOf(keep), list = e.dataset.type === "ListBox";
  e.selectedIndex = keep !== "" && i >= 0 ? i : (list || !items.length ? -1 : 0);
  if ((e.selectedIndex >= 0 ? e.options[e.selectedIndex].text : "") !== keep) changed(e);
}
function pickTree(e, path) {
  e._path = ""; e.querySelectorAll(".ti.sel").forEach(t => t.classList.remove("sel"));
  const item = [...e.querySelectorAll(".ti")].find(t => t.dataset.path === path);
  if (item) { item.classList.add("sel"); e._path = path; }
}
document.querySelectorAll(".grid").forEach(e => {
  fillGrid(e, JSON.parse(e.dataset.cols), JSON.parse(e.dataset.rows));
  if (!e._cols.length && e._rows.length) fillGrid(e, e._rows[0].map((_, i) => "Column" + (i + 1)), e._rows);
  e.addEventListener("click", ev => { const tr = ev.target.closest("tbody tr"); if (!tr) return; const i = Number(tr.dataset.i); if (i !== e._sel) { e._sel = i; markGrid(e); changed(e); } });
});
document.querySelectorAll(".tree").forEach(e => {
  fillTree(e, JSON.parse(e.dataset.paths));
  e.addEventListener("click", ev => { const t = ev.target.closest(".ti"); if (!t || t.dataset.path === e._path) return; pickTree(e, t.dataset.path); changed(e); });
});

// ---- databases inside the page (SQLite compiled to WebAssembly): the same Db commands and ItemsSource as on the desktop.
// A project's SQLite files travel in the page. Changes are kept in this browser (localStorage), so they survive a
// reload and are shared by the app's other pages; they never go back into the file the page was made from.
let SQL = null, dbError = "";
const dbs = {}, dbSeen = {}, OWN_DB = "\u0000own";
const b64bytes = t => Uint8Array.from(atob(t), c => c.charCodeAt(0));
const bytesB64 = u => { let t = ""; for (let i = 0; i < u.length; i += 0x8000) t += String.fromCharCode.apply(null, u.subarray(i, i + 0x8000)); return btoa(t); };
const storeKey = name => VML.databases[name] ? `vmldb:${VML.project}:${name}:${VML.databases[name].hash}` : null;
function openStored(name) {
  const key = storeKey(name); let bytes = null;
  try { const saved = localStorage.getItem(key); if (saved) { bytes = b64bytes(saved); dbSeen[name] = localStorage.getItem(key + ":t") || ""; } } catch {}
  if (!bytes && VML.databases[name].data) bytes = b64bytes(VML.databases[name].data);
  return bytes ? new SQL.Database(bytes) : new SQL.Database();
}
function persist(name) {
  const key = storeKey(name); if (!key || !dbs[name]) return;
  try { const t = bytesB64(dbs[name].export()); if (t.length > 4e6) return; localStorage.setItem(key, t); dbSeen[name] = String(Date.now()); localStorage.setItem(key + ":t", dbSeen[name]); } catch {}
}
const dbName = name => name || VML.mainDb || OWN_DB;
function db(name) {
  name = dbName(name);
  if (!SQL) throw new Error("the database engine didn't load in this page");
  if (!dbs[name]) {
    if (VML.databases[name]) dbs[name] = openStored(name);
    else if (name === OWN_DB) { dbs[name] = new SQL.Database(); dbs[name].run("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT)"); for (const [k, v] of Object.entries(settings)) dbs[name].run("INSERT OR REPLACE INTO settings VALUES (?, ?)", [k, v]); }
    else if ((VML.named || []).includes(name)) throw new Error(`the database '${name}' isn't inside this page (only SQLite files up to 16 MB travel with a page)`);
    else throw new Error(`no database called '${name}' is open (DbOpen it first, or name it in the project)`);
  }
  return dbs[name];
}
function query(name, sql, params = []) {
  const st = db(name).prepare(sql);
  try {
    st.bind(params);
    const cols = st.getColumnNames(), rows = [];
    while (st.step()) rows.push(st.get().map(v => v instanceof Uint8Array ? `(${v.length} bytes)` : v));
    return [cols, rows];
  } finally { st.free(); }
}
const REF = /\{\s*([A-Za-z_]\w*)(?:\.([A-Za-z_][\w.]*))?\s*\}/g;
const OWN_VALUE = { ComboBox: "SelectedItem", ListBox: "SelectedItem", TreeView: "SelectedItem", DataGrid: "SelectedValue", CheckBox: "IsChecked", RadioButton: "IsChecked", Button: "Content" };
const valueOf = (name, prop) => commands.GetProperty(name, prop || OWN_VALUE[el(name)?.dataset.type] || "Text");
function plan(src) {
  const m = /^\s*([A-Za-z_]\w*)\s*(?:\((.*)\))?\s*$/.exec(src.src);
  if (m && (VML.scripts[m[1]] || luaFunction(m[1]))) return ["script", m[1], (m[2] || "").split(",").map(a => a.trim().replace(/^['"]|['"]$/g, "")).filter(Boolean).map(a => [a, ""])];
  const refs = [];
  return ["sql", src.src.replace(REF, (_, n, p) => { refs.push([n, p || ""]); return "?"; }), refs];
}
let filling = 0;
const watched = new Set();
function fill(src) {
  const e = el(src.name);
  if (!e || filling > 20 || !String(src.src || "").trim()) return;
  const [kind, text, refs] = plan(src);
  const values = refs.map(([n, p]) => { if (!el(n)) return kind === "script" ? n : ""; watch(n); return valueOf(n, p); });
  filling++;
  try {
    let cols = [], rows = [];
    if (kind === "script") [cols, rows] = rowsFrom(run(text, values));
    else try { [cols, rows] = query(src.db, text, values); dbError = ""; } catch (err) { dbError = String(err.message || err); console.warn(`${src.name}.ItemsSource: ${dbError}`); }
    const first = rows.filter(r => r.length).map(r => r[0] == null ? "" : String(r[0]));
    if (e.matches(".grid")) { const own = JSON.parse(e.dataset.cols); fillGrid(e, own.length && own.length === cols.length ? own : cols, rows); }
    else if (e.matches(".tree")) fillTree(e, first);
    else if (e.matches("select")) fillSelect(e, first);
  } finally { filling--; }
}
function watch(n) {
  if (watched.has(n)) return;
  watched.add(n);
  const outer = el(n), t = outer.matches("label.cb") ? outer.querySelector("input") : outer;
  const again = () => dependents(n);
  if (outer.matches("input[type=text],input[type=password],textarea")) { let timer; t.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(again, 250); }); }
  else t.addEventListener("change", again);
}
function dependents(n) { for (const src of VML.sources) if (plan(src)[2].some(r => r[0] === n)) fill(src); }
function refill(test = () => true) { for (const src of VML.sources) if (test(src)) fill(src); }
window.addEventListener("focus", () => {              // another page of the app may have changed the data
  for (const name of Object.keys(dbs)) {
    const key = storeKey(name); if (!key) continue;
    let t = ""; try { t = localStorage.getItem(key + ":t") || ""; } catch {}
    if (t && t !== (dbSeen[name] || "")) { dbs[name] = openStored(name); refill(src => dbName(src.db) === name); }
  }
});

const commands = {
  DbOpen(name, connection) {
    try {
      const m = /^\s*sqlite\s*:(.*)$/i.exec(connection), target = (m ? m[1] : connection).trim();
      if (/^\s*odbc\s*:/i.test(connection) || (!m && target.includes("="))) throw new Error("ODBC isn't available in a web page: use a SQLite database, which travels inside the page");
      if (!SQL) throw new Error("the database engine didn't load in this page");
      const file = target.split(/[\\/]/).pop(), inside = Object.keys(VML.databases).find(n => VML.databases[n].file === file);
      if (inside === name) { delete dbs[name]; db(name); }
      else if (inside) dbs[name] = new SQL.Database(b64bytes(VML.databases[inside].data));
      else { dbs[name] = new SQL.Database(); if (target !== ":memory:") console.info(`${file} isn't inside this page, so the database '${name}' starts empty here`); }
      dbError = "";
      refill(src => dbName(src.db) === name);
      return "true";
    } catch (err) { dbError = String(err.message || err); console.warn("DbOpen", name, dbError); return ""; }
  },
  DbClose(name) { const had = !!dbs[name]; delete dbs[name]; return had ? "true" : "false"; },
  DbQuery(name, sql, ...params) {
    try { const [cols, rows] = query(name, sql, params); dbError = ""; return JSON.stringify(rows.map(r => Object.fromEntries(cols.map((c, i) => [c, r[i]])))); }
    catch (err) { dbError = String(err.message || err); console.warn("DbQuery", dbError); return "[]"; }
  },
  DbExecute(name, sql, ...params) {
    try { const d = db(name); d.run(sql, params); const n = d.getRowsModified(); dbError = ""; persist(dbName(name)); return String(n); }
    catch (err) { dbError = String(err.message || err); console.warn("DbExecute", dbError); return ""; }
  },
  DbError: () => dbError,
  DbTables(name = "") { try { return JSON.stringify(query(name, "SELECT name FROM sqlite_master WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%' ORDER BY name")[1].map(r => r[0])); } catch { return "[]"; } },
  DbList: () => JSON.stringify([...new Set([...Object.keys(VML.databases), ...Object.keys(dbs).filter(n => n !== OWN_DB)])].map(n => ({ name: n, open: !!dbs[n], kind: dbs[n] ? "sqlite" : "" }))),
  DbDrivers: () => "[]",
  SqlQuery(sql, ...params) { try { const [cols, rows] = query(OWN_DB, sql, params); return JSON.stringify(rows.map(r => Object.fromEntries(cols.map((c, i) => [c, r[i]])))); } catch (err) { console.warn("SqlQuery", err); return "[]"; } },
  SqlExecute(sql, ...params) { try { const d = db(OWN_DB); d.run(sql, params); return String(d.getRowsModified()); } catch (err) { console.warn("SqlExecute", err); return ""; } },
  Requery(control = "") { refill(control ? src => src.name === control : undefined); return "true"; },
  SetProperty(name, prop, value = "") {
    const e = name === VML.form ? null : el(name);
    if (name === VML.form || !e) { if (prop === "Title") document.title = value; return ""; }
    const css = { Background: "background", Foreground: "color", Fill: "background" };
    if (e.dataset.type === "Timer" && (prop === "Interval" || prop === "IsEnabled")) {
      if (prop === "Interval") e.dataset.interval = String(Number(value) || 1000); else e.dataset.on = truthy(value) ? "true" : "false";
      setTimer(e);
    }
    else if (e.matches(".pbar") && (BAR_PROPS[prop] || prop === "Foreground" || prop === "Background")) {
      if (prop === "Foreground") e.style.setProperty("--bar", value);
      else if (prop === "Background") e.style.setProperty("--track", value);
      else if (prop === "BarStyle") e.dataset.style = String(value).toLowerCase();
      else if (prop === "Orientation") e.dataset.upright = String(value).toLowerCase() === "vertical" ? "True" : "False";
      else if (prop === "ShowText" || prop === "IsIndeterminate") e.dataset[BAR_PROPS[prop]] = truthy(value) ? "True" : "False";
      else e.dataset[BAR_PROPS[prop]] = String(Number(value) || 0);
      drawBar(e);
    }
    else if (e.matches(".slide") && ["Value", "Minimum", "Maximum"].includes(prop)) e[{ Value: "value", Minimum: "min", Maximum: "max" }[prop]] = String(Math.round(Number(value) || 0));
    else if (prop === "Text" || prop === "Content" || prop === "Header") setText(e, value);
    else if (css[prop]) e.style[css[prop]] = value;
    else if (prop === "FontSize") e.style.fontSize = value + "px";
    else if (prop === "IsVisible") e.style.display = truthy(value) ? "" : "none";
    else if (prop === "IsEnabled") { const t = e.matches("label.cb") ? e.querySelector("input") : e; truthy(value) ? t.removeAttribute("disabled") : t.setAttribute("disabled", ""); }
    else if (prop === "IsChecked") e.querySelector("input").checked = truthy(value);
    else if (prop === "ItemsSource" || prop === "Database") {
      let src = VML.sources.find(x => x.name === name);
      if (!src) VML.sources.push(src = { name, src: "", db: "" });
      src[prop === "Database" ? "db" : "src"] = value;
      if (lua) fill(src);
    }
    else if (prop === "IsPassword") e.type = truthy(value) ? "password" : "text";
    else if (prop === "Source") value ? e.setAttribute("src", value) : e.removeAttribute("src");
    else if (prop === "Stretch") e.style.objectFit = { Fill: "fill", UniformToFill: "cover", None: "none" }[value] || "contain";
    else if (e.matches(".grid") && prop === "Columns") fillGrid(e, value.split(",").map(s => s.trim()).filter(Boolean), e._rows);
    else if (e.matches(".grid") && prop === "Items") fillGrid(e, e._cols, value.split(";").filter(s => s.trim()).map(r => r.split("|").map(c => c.trim())));
    else if (e.matches(".grid") && prop === "SelectedIndex") { e._sel = Number(value) >= 0 && Number(value) < e._rows.length ? Number(value) : -1; markGrid(e); }
    else if (e.matches(".tree") && prop === "Items") fillTree(e, value.split(/[,\n]/).map(s => s.trim()).filter(Boolean));
    else if (e.matches(".tree") && prop === "SelectedItem") pickTree(e, value);
    else if (prop === "Watermark") e.placeholder = value;
    else if (prop === "Width") e.style.width = value + "px";
    else if (prop === "Height") e.style.height = value + "px";
    else if (prop === "Canvas.Left") e.style.left = value + "px";
    else if (prop === "Canvas.Top") e.style.top = value + "px";
    else if (prop === "Items") { e.innerHTML = ""; String(value).split(",").map(s => s.trim()).filter(Boolean).forEach(t => e.add(new Option(t))); }
    else if (e.tagName === "SELECT" && prop === "Items") {
      const keep = e.value;
      e.innerHTML = "";
      for (const item of value.split(",").map(t => t.trim()).filter(Boolean)) e.appendChild(new Option(item, item));
      if ([...e.options].some(o => o.value === keep)) e.value = keep;
    }
    else if (prop === "SelectedIndex") e.selectedIndex = Number(value);
    else if (prop === "SelectedItem") e.value = value;
    else if (prop === "ToolTip") e.title = value;
    else e.dataset["p_" + prop.replace(/\W/g, "_")] = value;
    if (watched.has(name) && ["SelectedIndex", "SelectedItem", "Text", "IsChecked", "Items"].includes(prop)) dependents(name);
    return "";
  },
  GetProperty(name, prop) {
    const e = el(name);
    if (!e) return "";
    if (prop === "Text" || prop === "Content" || prop === "Header") return textOf(e);
    if (prop === "IsChecked") return e.querySelector("input").checked ? "true" : "false";
    if (e.dataset.type === "Timer") { if (prop === "Interval") return e.dataset.interval; if (prop === "IsEnabled") return e.dataset.on; }
    if (e.matches(".slide") && ["Value", "Minimum", "Maximum"].includes(prop)) return e[{ Value: "value", Minimum: "min", Maximum: "max" }[prop]];
    if (e.matches(".pbar") && ["Value", "Minimum", "Maximum"].includes(prop)) return e.dataset[BAR_PROPS[prop]];
    if (e.matches(".grid")) {
      if (prop === "SelectedIndex") return String(e._sel);
      if (prop === "SelectedValue") return gridValue(e);
      if (prop === "SelectedItem") return gridItem(e);
      if (prop === "RowCount") return String(e._rows.length);
    }
    if (e.matches(".tree") && prop === "SelectedItem") return e._path || "";
    if (prop === "Source") return e.getAttribute("src") || "";
    if (prop === "SelectedIndex") return String(e.selectedIndex);
    if (prop === "SelectedItem") return e.selectedIndex >= 0 ? e.options[e.selectedIndex].text : "";
    if (prop === "IsVisible") return e.style.display === "none" ? "false" : "true";
    if (prop === "IsEnabled") return (e.matches("label.cb") ? e.querySelector("input") : e).hasAttribute("disabled") ? "false" : "true";
    if (prop === "Width") return String(e.offsetWidth);
    if (prop === "Height") return String(e.offsetHeight);
    return e.dataset["p_" + prop.replace(/\W/g, "_")] || "";
  },
  GetSetting: k => settings[k] ?? "",
  SetSetting(k, v = "") { settings[k] = String(v); keepSetting(k, String(v)); if (dbs[OWN_DB]) dbs[OWN_DB].run("INSERT OR REPLACE INTO settings VALUES (?, ?)", [k, String(v)]); return ""; },
  RunScript: (name, ...args) => run(name, args),
  InfoDialog(msg, title) { alert(msg); return ""; },
  ErrorDialog(msg, title) { alert(msg); return ""; },
  ConfirmDialog: (msg, title) => confirm(msg) ? "true" : "false",
  PromptDialog: (title = "", text = "", start = "") => prompt(text || title, start) ?? "",
  SetStatusText(t) { console.log("[status]", t); return ""; },
  ControlExists: name => el(name) ? "true" : "false",
  GetControlType: name => el(name)?.dataset.type ?? "",
  SetMenuItemEnabled(name, on) { return commands.SetProperty(name, "IsEnabled", on); },
  SetMenuItemText(name, t) { return commands.SetProperty(name, "Text", t); },
  ShowContextMenu(name) {
    const m = el(name); if (!m) return "";
    closeMenus(); m.style.display = "block";
    m.style.left = Math.min(lastPointer.x, innerWidth - m.offsetWidth - 4) + "px";
    m.style.top = Math.min(lastPointer.y, innerHeight - m.offsetHeight - 4) + "px";
    return "";
  },
  FormOpen(path) { open(/\.\w+$/.test(path) ? String(path).replace(/\.vml$/i, ".html") : path + ".html", "_blank"); return ""; },
  FormOpenModal(path) { return commands.FormOpen(path); },
  GridSetData(name, json, columns = "") {
    const e = el(name); if (!e || !e.matches(".grid")) return "";
    const [cols, rows] = rowsFrom(json), own = columns.split(",").map(s => s.trim()).filter(Boolean);
    fillGrid(e, own.length === cols.length ? own : cols, rows);
    return String(rows.length);
  },
  GridGetData(name) { const e = el(name); return e && e._rows ? JSON.stringify(e._rows.map(r => Object.fromEntries(e._cols.map((c, i) => [c, r[i] ?? ""])))) : "[]"; },
  // --- the phone. In the Visualised app these go through it; in a browser, through whatever the browser offers.
  DeviceInfo() {
    const ua = navigator.userAgent, screen = { width: window.innerWidth, height: window.innerHeight };
    if (DEV) return JSON.stringify(Object.assign(JSON.parse(DEV.info()), screen));
    return JSON.stringify(Object.assign({ platform: /Android/.test(ua) ? "android-browser" : /iPhone|iPad/.test(ua) ? "ios-browser" : "browser", app: false, online: navigator.onLine }, screen));
  },
  // Asked again while running, it keeps going another six hours (the phone may sleep six hours after the last ask).
  RunInBackground(on = "true") { if (DEV && DEV.background) DEV.background(!/^(false|0|no|)$/i.test(on)); return ""; },
  // The screen's own brightness on a phone, 0 to 100, for an app that is a light or shows a code to scan. ""
  // hands it back to the phone's setting. A browser can't, so nothing happens there.
  Brightness(percent = "") { if (DEV && DEV.brightness) DEV.brightness(percent === "" ? -1 : Math.max(0, Math.min(100, Number(percent) || 0))); return ""; },
  Torch(on = "true") {
    const lit = !/^(false|0|no|)$/i.test(on), lamp = cameraLamp();
    if (lamp) setLamp(lamp, lit); else if (DEV && DEV.torch) DEV.torch(lit);
    return "";
  },
  Speak(text = "") {
    if (DEV && DEV.speak) DEV.speak(text);
    else if (window.speechSynthesis) speechSynthesis.speak(new SpeechSynthesisUtterance(text));
    return "";
  },
  OpenUrl(url) { if (DEV && DEV.open) DEV.open(url); else window.open(url, "_blank"); return ""; },
  // Give the user a file: the phone app puts it in Downloads, a browser downloads it.
  SaveFile(name, text = "") {
    if (DEV && DEV.saveFile) return DEV.saveFile(name, text);
    const a = document.createElement("a");
    a.href = text.startsWith("data:") ? text : URL.createObjectURL(new Blob([text], { type: "text/plain" }));
    a.download = name || "file.txt";
    document.body.appendChild(a); a.click(); a.remove();
    return a.download;
  },
  Vibrate(ms = "200") { const n = Math.max(1, Number(ms) || 200); if (DEV) DEV.vibrate(n); else if (navigator.vibrate) navigator.vibrate(n); return ""; },
  KeepAwake(on = "true") {
    const yes = !/^(false|0|no|)$/i.test(on);
    if (DEV) DEV.keepAwake(yes);
    else if (navigator.wakeLock) { if (yes) navigator.wakeLock.request("screen").then(l => { awake = l; }).catch(() => {}); else if (awake) { awake.release(); awake = null; } }
    return "";
  },
  ClipboardSet(text = "") { if (navigator.clipboard) navigator.clipboard.writeText(text).catch(() => {}); return ""; },
  Share(text = "", title = "") {
    if (DEV) DEV.share(text, title);
    else if (navigator.share) navigator.share(title ? { text, title } : { text }).catch(() => {});
    else commands.ClipboardSet(text);
    return "";
  },
  Notify(title = "", text = "") {
    if (DEV) { DEV.notify(title, text); return ""; }
    const show = () => { try { new Notification(title, { body: text }); } catch (err) { alert(title + (text ? "\n\n" + text : "")); } };
    if (!("Notification" in window) || Notification.permission === "denied") alert(title + (text ? "\n\n" + text : ""));
    else if (Notification.permission === "granted") show();
    else Notification.requestPermission().then(p => p === "granted" ? show() : alert(title + (text ? "\n\n" + text : "")));
    return "";
  },
  // The handler is run with the latitude, longitude and how many metres out it might be; or with three blanks and what went wrong.
  GetLocation(handler) {
    const fail = why => run(handler, ["", "", "", why]);
    if (!navigator.geolocation || !window.isSecureContext) { setTimeout(() => fail("Finding where you are needs the Visualised app, or a secure (https) page."), 0); return ""; }
    navigator.geolocation.getCurrentPosition(
      p => run(handler, [String(p.coords.latitude), String(p.coords.longitude), String(Math.round(p.coords.accuracy)), ""]),
      e => fail(e.code === 1 ? "Location wasn't allowed." : "The phone couldn't find where it is."),
      { enableHighAccuracy: true, timeout: 20000, maximumAge: 10000 });
    return "";
  },
  // How watching has gone since it started, in a line, for when a signal reads wrongly: how evenly the camera's
  // pictures came, how long its light took to switch, and how bright the signal was from picture to picture.
  LightReport() {
    const mid = a => a.length ? [...a].sort((x, y) => x - y)[a.length >> 1] : 0, most = a => a.length ? Math.max(...a) : 0;
    const g = seen.gaps, l = seen.lamp;
    return `pictures ${g.length + 1}, usually ${mid(g)} ms apart, longest ${most(g)} ms, over 100 ms ${g.filter(x => x > 100).length} times; `
      + `light switched ${l.length} times, usually in ${mid(l)} ms, slowest ${most(l)} ms, refused ${seen.refused}; `
      + `camera ${watching && watching.video.videoWidth ? watching.video.videoWidth + "x" + watching.video.videoHeight : "off"}; `
      + `levels ${seen.levels.slice(-600).join(" ")}`;
  },
  // Write a line where its maker can see it: the browser's console, and the terminal the designer was started
  // from when the app is being previewed on a phone.
  Log(text = "") {
    console.log("[log]", text);
    if (DEV && DEV.log) DEV.log(text);                   // the phone app keeps it: press and hold the app in its list
    if (window.VML_PREVIEW && location.protocol !== "file:") fetch("/_log?t=" + encodeURIComponent(text.slice(0, 6000))).catch(() => {});
    return "";
  },
  // Put a photo in an Image: straight from the camera, or one chosen from the phone. Then the handler is run, if there is one.
  // The Bluetooth devices the phone is paired with: the handler gets them as JSON (name, address, watched) and
  // a blank, or "[]" and what went wrong.
  BluetoothDevices(handler) {
    if (DEV && DEV.bluetoothDevices) { paired = handler; DEV.bluetoothDevices(); }
    else setTimeout(() => run(handler, ["[]", "Bluetooth devices need the Visualised app on a phone."]), 0);
    return "";
  },
  // Note where the phone is whenever a paired device (a car, say) connects or goes away, even with the app shut.
  // The handler hears "watching", "stopped", or "partly" (the time is noted but not the place) and any problem.
  WatchBluetooth(address, on = "true", handler = "") {
    if (DEV && DEV.bluetoothWatch) { watched_ = handler; DEV.bluetoothWatch(address, !/^(false|0|no|)$/i.test(on)); }
    else if (handler) setTimeout(() => run(handler, ["stopped", "Watching a Bluetooth device needs the Visualised app on a phone."]), 0);
    return "";
  },
  // What has been noted, newest first, as JSON: device, name, what ("connected" or "disconnected"), time (seconds),
  // and for a device that went away latitude, longitude, accuracy and pressure when they could be found.
  BluetoothLog() { return DEV && DEV.bluetoothLog ? DEV.bluetoothLog() : "[]"; },
  // The air pressure in hectopascals: about 0.12 less for every metre climbed, so it tells one floor from the
  // next. "" where there is no barometer, and for the first moment after asking.
  Pressure() { return DEV && DEV.pressure ? DEV.pressure() : ""; },
  // Ask a web address for something: with no body it is fetched, with one it is sent (POST; as JSON when it looks
  // like JSON). The handler gets what came back and a blank, or what came back (if anything) and what went wrong.
  // In the phone app it goes from the phone itself; in a browser the server has to allow the page (CORS).
  Fetch(url, body = "", handler = "") {
    const id = String(++asked);
    if (DEV && DEV.fetch) { if (handler) waitingFor[id] = handler; DEV.fetch(id, String(url), String(body)); return ""; }
    const json = /^\s*[{[]/.test(String(body));
    const init = body === "" ? {} : { method: "POST", body: String(body), headers: { "Content-Type": json ? "application/json" : "text/plain;charset=UTF-8" } };
    fetch(String(url), init)
      .then(r => r.text().then(t => { if (handler) run(handler, [t, r.ok ? "" : "The server said " + r.status + "."]); }))
      .catch(() => { if (handler) run(handler, ["", "It couldn't be reached (or the server doesn't allow this page)."]); });
    return "";
  },
  // Send a text message from the phone. The handler gets "sent", or a blank and what went wrong. Only an app
  // exported on its own for Android can (vml apk): its phone will ask the user's leave the first time.
  SmsSend(number, text = "", handler = "") {
    const id = String(++asked);
    if (DEV && DEV.smsSend) { if (handler) waitingFor[id] = handler; DEV.smsSend(id, String(number), String(text)); }
    else if (handler) setTimeout(() => run(handler, ["", "Sending texts needs the app exported for an Android phone."]), 0);
    return "";
  },
  // Hear text messages as they arrive: the handler gets who from and what they said, for each one. A blank
  // "from" means it couldn't, and the text says why. OnSms("") stops. An app exported on its own for Android only.
  OnSms(handler = "") {
    onSms = String(handler || "");
    if (DEV && DEV.smsWatch) DEV.smsWatch(onSms !== "");
    else if (onSms) setTimeout(() => run(onSms, ["", "Texts arrive only in an app exported for an Android phone."]), 0);
    return "";
  },
  // A QR code for some text (an address, or a link's code), as a picture: a data: address to give an Image as
  // its Source. Up to 213 characters. "" if it is too long.
  QrCode(text = "", scale = "6") {
    const m = qrMatrix(String(text));
    if (!m) { console.warn("QrCode: that is too long for a QR code made here (213 characters at most)"); return ""; }
    const n = m.length, k = Math.max(1, Math.round(Number(scale) || 6)), c = document.createElement("canvas");
    c.width = c.height = (n + 8) * k;
    const g = c.getContext("2d");
    g.fillStyle = "#fff"; g.fillRect(0, 0, c.width, c.height);          // with the quiet margin a scanner needs
    g.fillStyle = "#000";
    for (let y = 0; y < n; y++) for (let x = 0; x < n; x++) if (m[y][x]) g.fillRect((x + 4) * k, (y + 4) * k, k, k);
    return c.toDataURL("image/png");
  },
  // Read a QR code with the camera and hand the handler what it says; or a blank and what went wrong. Where
  // there is no camera that can (a computer, some browsers) the user is asked to paste what the code says.
  ScanCode(handler, prompt_ = "") {
    const done = (text, problem = "") => setTimeout(() => run(handler, [text, problem]), 0);
    const ask = () => { const t = prompt(prompt_ || "Paste the code here:", ""); done((t || "").trim(), t ? "" : "Nothing was given."); };
    const own = DEV && DEV.readCode;          // the Visualised app reads codes itself: a phone's web view can't be counted on to
    if (!(own || "BarcodeDetector" in window) || !navigator.mediaDevices || !navigator.mediaDevices.getUserMedia || !window.isSecureContext) { ask(); return ""; }
    const box = document.createElement("div");
    box.id = "vml_scan";
    box.style.cssText = "position:fixed;inset:0;z-index:99997;background:#000;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:14px;font:15px system-ui,sans-serif;color:#fff";
    const v = document.createElement("video");
    v.muted = true; v.playsInline = true; v.setAttribute("playsinline", "");
    v.style.cssText = "width:min(86vw,60vh);height:min(86vw,60vh);object-fit:cover;border-radius:14px;background:#111";
    const say = document.createElement("div"); say.textContent = prompt_ || "Point the camera at the code";
    const row = document.createElement("div"); row.style.cssText = "display:flex;gap:10px";
    const btn = (label, go) => { const b = document.createElement("button"); b.textContent = label; b.style.cssText = "font:inherit;padding:9px 18px;border-radius:9px;border:0;background:#fff;color:#111"; b.onclick = go; row.appendChild(b); };
    let stream = null, over = false, timer = 0;
    const finish = (text, problem) => { if (over) return; over = true; clearInterval(timer); if (stream) stream.getTracks().forEach(t => t.stop()); box.remove(); if (text !== null) done(text, problem); };
    btn("Paste it instead", () => { finish(null); ask(); });
    btn("Cancel", () => finish("", "Nothing was scanned."));
    box.append(say, v, row); document.body.appendChild(box);
    navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" }, audio: false }).then(s => {
      if (over) { s.getTracks().forEach(t => t.stop()); return; }
      stream = s; v.srcObject = s; v.play().catch(() => {});
      let reader = null, told = false;
      try { if ("BarcodeDetector" in window) reader = new BarcodeDetector({ formats: ["qr_code"] }); } catch (err) { reader = null; }
      const shot = document.createElement("canvas");
      const look = () => {                    // the picture as brightness alone, small enough to hand over quickly
        const k = Math.min(1, 720 / Math.max(v.videoWidth, v.videoHeight)), w = Math.round(v.videoWidth * k), h = Math.round(v.videoHeight * k);
        shot.width = w; shot.height = h;
        const g = shot.getContext("2d", { willReadFrequently: true });
        g.drawImage(v, 0, 0, w, h);
        const d = g.getImageData(0, 0, w, h).data;
        let s = "";
        for (let i = 0; i < d.length; i += 4) s += String.fromCharCode((d[i] * 77 + d[i + 1] * 150 + d[i + 2] * 29) >> 8);
        const text = DEV.readCode(btoa(s), w, h);
        if (text) finish(String(text), "");
      };
      timer = setInterval(() => {
        if (!v.videoWidth || over) return;
        if (own) { try { look(); } catch (err) { if (!told) { told = true; commands.Log("ScanCode: " + err); } } return; }
        reader.detect(v).then(found => { if (found.length && found[0].rawValue) finish(String(found[0].rawValue), ""); })
          .catch(err => { if (!told) { told = true; commands.Log("ScanCode: " + err); } });
      }, own ? 350 : 250);
    }).catch(err => { finish(null); if (err && err.name === "NotAllowedError") done("", "The camera wasn't allowed."); else ask(); });
    return "";
  },
  // Link: this app talking to another, anywhere, with nobody between able to read it. With no code a new link is
  // started and its code returned, to show the other app; with a code, that link is joined. The handler is run
  // with "joined" when the other side arrives, "message" and the text when it sends, "left" when it closes, and
  // "error" and what went wrong. start: "start" to be given the messages of the last day too.
  Link(handler, code = "", start = "") {
    commands.LinkClose();
    const tell = (what, text = "") => setTimeout(() => run(handler, [what, text]), 0);
    if (!window.crypto || !crypto.subtle) { tell("error", "A link needs a secure page: the Visualised app, or an https address."); return ""; }
    code = linkCodeIn(code);
    if (!code) { const r = crypto.getRandomValues(new Uint8Array(32)); code = "VL1" + btoa(String.fromCharCode(...r)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, ""); }
    let secret;
    try {
      if (!code.startsWith("VL1")) throw 0;
      secret = Uint8Array.from(atob(code.slice(3).replace(/-/g, "+").replace(/_/g, "/")), c => c.charCodeAt(0));
      if (secret.length !== 32) throw 0;
    } catch (err) { tell("error", "That isn't a link code."); return ""; }
    const mine = link = { code, tell, sender: [...crypto.getRandomValues(new Uint8Array(8))].map(b => b.toString(16).padStart(2, "0")).join(""),
      relay: window.VML_LINK_URL || "https://visualised.io/link/", count: 0, seen: {}, since: start === "start" ? 0 : -1, active: Date.now(),
      failing: 0, timer: 0, closed: false, queue: Promise.resolve(), ready: null };
    mine.ready = linkKeys(secret).then(([channel, key]) => { mine.channel = channel; mine.key = key; });
    mine.ready.then(async () => {
      try {
        if (mine.since < 0) mine.since = Number((await linkCall(mine, "&since=-1")).seq) || 0;
        await linkPost(mine, "hello");
      } catch (err) { tell("error", err.message || "The relay couldn't be reached."); }
      linkPoll(mine);
    }).catch(() => tell("error", "This page can't make a link."));
    return code;
  },
  // Agree a link with another app by pressing together: both run this within a few seconds of each other. The
  // handler is run with "words" and three words, which the other app shows too; when they are the same,
  // LinkAccept opens the link. Or with "error" and what went wrong.
  LinkPair(handler) {
    commands.LinkClose();
    const tell = (what, text = "") => setTimeout(() => run(handler, [what, text]), 0);
    if (!window.crypto || !crypto.subtle) { tell("error", "A link needs a secure page: the Visualised app, or an https address."); return ""; }
    const mine = link = { pairing: true, handler, code: "", tell, relay: window.VML_LINK_URL || "https://visualised.io/link/", closed: false };
    linkPair(mine).then(words => { if (!mine.closed) tell("words", words); })
      .catch(err => { if (!mine.closed) tell("error", err && err.told ? err.message : "The pairing went wrong. Press together again."); });
    return "true";
  },
  LinkAccept() {
    const mine = link;
    if (!mine || !mine.pairing || !mine.code) return "";
    return commands.Link(mine.handler, mine.code);
  },
  LinkSend(text = "") {
    const mine = link;
    if (!mine || mine.pairing) return "";
    mine.queue = mine.queue.then(() => mine.ready).then(() => linkPost(mine, "msg", String(text))).catch(err => mine.tell("error", err.message || "The relay couldn't be reached."));
    return "true";
  },
  LinkCode: () => link && !link.pairing ? link.code : "",
  // What to show as a QR code so any phone's camera can join this link: an address that opens this app with the
  // code after the #, where no web server sees it. The app has to be on the web: this page's own address if it
  // is, or the Window's WebAddress. Otherwise the code itself.
  LinkAddress(code = "") {
    code = String(code || "") || commands.LinkCode();
    if (!code) return "";
    const here = /^https:$/.test(location.protocol) && !/\.invalid$/.test(location.hostname) ? location.origin + location.pathname : "";
    const app = String(VML.webAddress || "").startsWith("https://") ? VML.webAddress.split("#")[0] : here;
    return app ? "https://visualised.io/open.html#" + encodeURIComponent(app + "#" + code) : code;
  },
  // The link code this app was opened with (from an address made by LinkAddress), once; "" otherwise.
  LinkInvite() { const code = linkInvite; linkInvite = ""; return code; },
  LinkClose() {
    const mine = link;
    if (!mine) return "";
    link = null; mine.closed = true; clearTimeout(mine.timer);
    if (mine.key) linkPost(mine, "bye").catch(() => {});
    return "";
  },
  // Hear what the user says and hand the handler the words; or a blank and what went wrong.
  Listen(handler, prompt = "") {
    if (DEV && DEV.listen) { heard = handler; DEV.listen(prompt); return ""; }
    const R = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!R) { setTimeout(() => run(handler, ["", "This browser can't listen. The Visualised app on a phone can."]), 0); return ""; }
    const r = new R(); let told = false;
    const tell = (words, problem) => { if (!told) { told = true; run(handler, [words, problem]); } };
    r.onresult = e => tell(e.results[0][0].transcript, "");
    r.onerror = e => tell("", e.error === "not-allowed" ? "The microphone wasn't allowed." : "Nothing was heard.");
    r.onend = () => tell("", "Nothing was heard.");
    try { r.start(); } catch (err) { tell("", "Listening couldn't start."); }
    return "";
  },
  // Signal with light: pattern is milliseconds on, off, on, off... The phone app uses the torch; a browser lights
  // the whole screen, which a phone's camera reads just as well. The handler runs when it is done. "" stops it.
  Flash(pattern = "", handler = "") {
    const steps = pattern.split(/[,\s]+/).filter(t => t !== "").map(Number).filter(n => isFinite(n) && n >= 0);
    stopFlash();
    const lamp = cameraLamp();
    if (lamp) {                                  // the camera is watching and can work its own light: both at once
      if (DEV && DEV.flash) DEV.flash("");
      if (!steps.length) return "";
      flashing = { box: null, timer: 0, lamp };
      let at = 0;
      const turn = () => {
        if (at >= steps.length) { stopFlash(); if (handler) run(handler, []); return; }
        setLamp(lamp, at % 2 === 0);
        flashing.timer = setTimeout(turn, steps[at++]);
      };
      turn();
      return "";
    }
    if (DEV && DEV.flash) {
      // The torch can't be lit while the camera has hold of it, so watching stops for the length of the signal.
      flashed = steps.length ? handler : "";
      resume = steps.length && watching ? watching.asked : null;
      if (resume) stopWatching();
      const go = () => DEV.flash(steps.join(","));
      if (resume) setTimeout(go, 400); else go();              // (the camera takes a moment to let go)
      return "";
    }
    if (!steps.length) return "";
    const box = document.createElement("div");
    box.id = "vml_flash";
    box.style.cssText = "position:fixed;inset:0;z-index:99998;background:#000";
    document.body.appendChild(box);
    flashing = { box, timer: 0 };
    let i = 0;
    const next = () => {
      if (i >= steps.length) { stopFlash(); if (handler) run(handler, []); return; }
      box.style.background = i % 2 === 0 ? "#fff" : "#000";
      flashing.timer = setTimeout(next, steps[i++]);
    };
    next();
    return "";
  },
  // Watch for a light going on and off through the camera: whatever in the picture is flashing. Each change
  // runs the handler with "on" or "off" and how many milliseconds the state before it lasted; with "new" when a
  // light is found (anything read before was something else; how this one began follows at once); or with "error",
  // 0 and what went wrong. where: a control to show the camera's picture over, to aim by. No handler stops it.
  WatchLight(handler = "", where = "") {
    stopWatching();
    if (!handler) return "";
    const fail = why => setTimeout(() => run(handler, ["error", "0", why]), 0);
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia || !window.isSecureContext) { fail("The camera needs the Visualised app, or a secure (https) page."); return ""; }
    const mine = watching = { stream: null, video: document.createElement("video"), timer: 0, asked: [handler, where] };
    const v = mine.video;
    v.muted = true; v.playsInline = true; v.setAttribute("playsinline", "");
    const over = where ? el(where) : null;
    if (over && over.parentElement) {
      v.style.cssText = `position:absolute;left:${over.offsetLeft}px;top:${over.offsetTop}px;width:${over.offsetWidth}px;height:${over.offsetHeight}px;object-fit:cover;z-index:5;background:#000`;
      over.parentElement.appendChild(v);
    }
    navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment", width: { ideal: 640 }, height: { ideal: 480 }, frameRate: { ideal: 60 } }, audio: false }).then(stream => {
      if (watching !== mine) { stream.getTracks().forEach(t => t.stop()); return; }
      mine.stream = stream; v.srcObject = stream; v.play().catch(() => {});
      const tell = (state, ms) => run(handler, [state, String(Math.round(ms)), ""]);
      const W = 320, H = 240, c = document.createElement("canvas"); c.width = W; c.height = H;
      const g = c.getContext("2d", { willReadFrequently: true }), lum = new Uint8Array(W * H), watcher = new LightWatcher(W, H, tell), finder = watcher.finder;
      const ring = document.createElement("div");                  // shows what it has taken to be the signal
      ring.style.cssText = "position:absolute;width:26px;height:26px;margin:-13px 0 0 -13px;border:2px solid #FDE047;border-radius:50%;z-index:6;display:none;pointer-events:none;box-shadow:0 0 0 1px rgba(0,0,0,.5)";
      if (v.parentElement) { v.parentElement.appendChild(ring); mine.ring = ring; }
      seen.gaps = []; seen.lamp = []; seen.levels = []; seen.refused = 0; seen.last = 0;
      const look = time => {
        if (watching !== mine || !v.videoWidth) return;
        if (seen.last) { seen.gaps.push(Math.round(time - seen.last)); if (seen.gaps.length > 3000) seen.gaps.shift(); }
        seen.last = time;
        g.drawImage(v, 0, 0, W, H);
        const px = g.getImageData(0, 0, W, H).data;
        for (let i = 0, j = 0; i < lum.length; i++, j += 4) lum[i] = (px[j] * 2 + px[j + 1] * 5 + px[j + 2]) >> 3;
        const level = watcher.feed(lum, time);
        if (window.VML_RECORD) record(time, finder);
        seen.levels.push(Math.round(level)); if (seen.levels.length > 3000) seen.levels.shift();
        const spot = finder.spot;
        if (!spot || !mine.ring) { ring.style.display = "none"; return; }
        // the picture fills its box and is cropped to fit, so the spot is placed the same way
        const k = Math.max(v.offsetWidth / v.videoWidth, v.offsetHeight / v.videoHeight);
        ring.style.left = v.offsetLeft + (v.offsetWidth - v.videoWidth * k) / 2 + spot.x * v.videoWidth * k + "px";
        ring.style.top = v.offsetTop + (v.offsetHeight - v.videoHeight * k) / 2 + spot.y * v.videoHeight * k + "px";
        ring.style.display = "block";
      };
      if (v.requestVideoFrameCallback && v.parentElement) {      // once for each picture the camera takes, timed by the camera
        const each = (now, frame) => { if (watching !== mine) return; look(frame && frame.captureTime ? frame.captureTime : now); v.requestVideoFrameCallback(each); };
        v.requestVideoFrameCallback(each);
      } else mine.timer = setInterval(() => look(performance.now()), 30);
    }).catch(err => { if (watching === mine) { stopWatching(); fail(err && err.name === "NotAllowedError" ? "The camera wasn't allowed." : "The camera couldn't be started."); } });
    return "";
  },
  TakePhoto(image, handler = "") { return photo(image, handler, true); },
  PickPhoto(image, handler = "") { return photo(image, handler, false); },
  ProjectName() { return VML.project || ""; },
  SetDialogResult() { return ""; },
  CloseSelf() { window.close(); return ""; },
  AppExit() { window.close(); return ""; },
};
const DEV = window.VisualisedDevice || null;    // there when the page is running in the Visualised app on a phone
let heard = "", flashed = "", flashing = null, watching = null, resume = null, paired = "", watched_ = "";
let asked = 0, onSms = "";
const waitingFor = {};                              // Fetch and SmsSend handlers, until their answer comes
window.vmlAway = () => {                                   // the app has left the screen: let go of the camera and its light
  stopFlash();
  if (watching) { const [handler] = watching.asked; stopWatching(); run(handler, ["error", "0", "Watching stopped while the app was away."]); }
};
window.vmlFromPhone = (what, a = "", b = "") => {         // the phone app answering something that takes a while
  if (what === "listen" && heard) { const h = heard; heard = ""; run(h, [a, b]); }
  if (what === "bluetooth" && paired) { const h = paired; paired = ""; run(h, [a, b]); }
  if (what === "watching" && watched_) { const h = watched_; watched_ = ""; run(h, [a, b]); }
  if (what === "sms" && onSms) run(onSms, [a, b]);
  if (what.startsWith("fetch:") || what.startsWith("sms-sent:")) {
    const id = what.slice(what.indexOf(":") + 1), h = waitingFor[id]; delete waitingFor[id];
    if (h) run(h, [a, b]);
  }
  if (what === "flash") {
    if (resume) { const r = resume; resume = null; commands.WatchLight(...r); }
    if (flashed) { const h = flashed; flashed = ""; run(h, []); }
  }
};
// ---- QR codes, made here (the same as vml/qr.py: bytes, error correction M, versions 1 to 10)
const QR_VERSIONS = { 1: [26, 10, [[1, 16]]], 2: [44, 16, [[1, 28]]], 3: [70, 26, [[1, 44]]], 4: [100, 18, [[2, 32]]], 5: [134, 24, [[2, 43]]],
  6: [172, 16, [[4, 27]]], 7: [196, 18, [[4, 31]]], 8: [242, 22, [[2, 38], [2, 39]]], 9: [292, 22, [[3, 36], [2, 37]]], 10: [346, 26, [[4, 43], [1, 44]]] };
const QR_ALIGN = { 1: [], 2: [6, 18], 3: [6, 22], 4: [6, 26], 5: [6, 30], 6: [6, 34], 7: [6, 22, 38], 8: [6, 24, 42], 9: [6, 26, 46], 10: [6, 28, 50] };
const QR_EXP = new Array(512).fill(0), QR_LOG = new Array(256).fill(0);
for (let i = 0, x = 1; i < 255; i++) { QR_EXP[i] = x; QR_LOG[x] = i; x <<= 1; if (x & 0x100) x ^= 0x11D; }
for (let i = 255; i < 512; i++) QR_EXP[i] = QR_EXP[i - 255];
const qrMul = (a, b) => a === 0 || b === 0 ? 0 : QR_EXP[QR_LOG[a] + QR_LOG[b]];
function qrEcc(data, count) {                                   // the Reed-Solomon codewords that follow a block of data
  let gen = [1];
  for (let i = 0; i < count; i++) { const nxt = new Array(gen.length + 1).fill(0); gen.forEach((g, j) => { nxt[j] ^= g; nxt[j + 1] ^= qrMul(g, QR_EXP[i]); }); gen = nxt; }
  const rest = data.concat(new Array(count).fill(0));
  for (let i = 0; i < data.length; i++) { const lead = rest[i]; if (lead) gen.forEach((g, j) => { rest[i + j] ^= qrMul(g, lead); }); }
  return rest.slice(data.length);
}
function qrBch(value, poly, bits) {                             // the remainder that protects the format information
  let reg = value << bits; const top = 32 - Math.clz32(poly);
  for (let shift = (32 - Math.clz32(reg)) - top; shift >= 0; shift--) if (reg >> (shift + top - 1) & 1) reg ^= poly << shift;
  return reg;
}
function qrPenalty(m) {
  const n = m.length; let score = 0;
  const lines = m.concat(m[0].map((_, x) => m.map(row => row[x])));
  for (const row of lines) {
    let run = 0, last = null;
    for (const cell of row) { if (cell === last) run++; else { if (run >= 5) score += run - 2; run = 1; last = cell; } }
    if (run >= 5) score += run - 2;
    const line = row.map(c => c ? "1" : "0").join("");
    score += 40 * (line.split("10111010000").length - 1 + line.split("00001011101").length - 1);
  }
  for (let y = 0; y < n - 1; y++) for (let x = 0; x < n - 1; x++) if (m[y][x] === m[y][x + 1] && m[y][x] === m[y + 1][x] && m[y][x] === m[y + 1][x + 1]) score += 3;
  const dark = Math.floor(m.reduce((a, row) => a + row.filter(Boolean).length, 0) * 100 / (n * n));
  return score + 10 * Math.floor(Math.abs(dark - 50) / 5);
}
const QR_MASKS = [(y, x) => (y + x) % 2 === 0, (y, x) => y % 2 === 0, (y, x) => x % 3 === 0, (y, x) => (y + x) % 3 === 0,
  (y, x) => (Math.floor(y / 2) + Math.floor(x / 3)) % 2 === 0, (y, x) => (y * x) % 2 + (y * x) % 3 === 0,
  (y, x) => ((y * x) % 2 + (y * x) % 3) % 2 === 0, (y, x) => ((y + x) % 2 + (y * x) % 3) % 2 === 0];
// text -> rows of true (dark) and false (light); null if it is too long
function qrMatrix(text) {
  const raw = [...new TextEncoder().encode(text)];
  const room = v => QR_VERSIONS[v][2].reduce((a, [k, size]) => a + k * size, 0);
  const version = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10].find(v => raw.length <= room(v) - (v >= 10 ? 3 : 2));
  if (!version) return null;
  const n = 17 + 4 * version, m = [], fixed = [];
  for (let y = 0; y < n; y++) { m.push(new Array(n).fill(false)); fixed.push(new Array(n).fill(false)); }
  const put = (y, x, dark) => { if (y >= 0 && y < n && x >= 0 && x < n) { m[y][x] = !!dark; fixed[y][x] = true; } };
  for (const [oy, ox] of [[0, 0], [0, n - 7], [n - 7, 0]])        // the three corner squares, with their margins
    for (let y = -1; y < 8; y++) for (let x = -1; x < 8; x++) {
      const inside = y >= 0 && y <= 6 && x >= 0 && x <= 6;
      put(oy + y, ox + x, inside && (y === 0 || y === 6 || x === 0 || x === 6 || (y >= 2 && y <= 4 && x >= 2 && x <= 4)));
    }
  for (const cy of QR_ALIGN[version]) for (const cx of QR_ALIGN[version]) {      // the small squares that keep a big code straight
    if (fixed[cy][cx]) continue;
    for (let y = -2; y < 3; y++) for (let x = -2; x < 3; x++) put(cy + y, cx + x, Math.max(Math.abs(y), Math.abs(x)) !== 1);
  }
  for (let i = 8; i < n - 8; i++) { if (!fixed[6][i]) put(6, i, i % 2 === 0); if (!fixed[i][6]) put(i, 6, i % 2 === 0); }
  put(n - 8, 8, true);
  for (let i = 0; i < 9; i++) for (const [y, x] of [[8, i], [i, 8], [8, n - 1 - i], [n - 1 - i, 8]]) if ((i < 8 || (y === 8 && x === 8)) && !fixed[y][x]) fixed[y][x] = true;
  if (version >= 7) {
    const info = (version << 12) | qrBch(version, 0x1F25, 12);
    for (let i = 0; i < 18; i++) { const bit = info >> i & 1; put(Math.floor(i / 3), n - 11 + i % 3, bit); put(n - 11 + i % 3, Math.floor(i / 3), bit); }
  }
  const [, ec, groups] = QR_VERSIONS[version], capacity = room(version);
  let bits = "0100" + raw.length.toString(2).padStart(version >= 10 ? 16 : 8, "0") + raw.map(b => b.toString(2).padStart(8, "0")).join("");
  bits += "0".repeat(Math.min(4, capacity * 8 - bits.length));
  bits += "0".repeat((8 - bits.length % 8) % 8);
  const data = [];
  for (let i = 0; i < bits.length; i += 8) data.push(parseInt(bits.slice(i, i + 8), 2));
  for (let i = 0; data.length < capacity; i++) data.push(i % 2 ? 0x11 : 0xEC);
  const blocks = []; let at = 0;
  for (const [k, size] of groups) for (let j = 0; j < k; j++) { const block = data.slice(at, at + size); at += size; blocks.push([block, qrEcc(block, ec)]); }
  const words = [];
  for (let i = 0; i < Math.max(...blocks.map(b => b[0].length)); i++) for (const b of blocks) if (i < b[0].length) words.push(b[0][i]);
  for (let i = 0; i < ec; i++) for (const b of blocks) words.push(b[1][i]);
  const stream = [];
  for (const w of words) for (let i = 0; i < 8; i++) stream.push(w >> (7 - i) & 1);
  const cells = []; at = 0;
  for (let x = n - 1, up = true; x > 0; x -= 2, up = !up) {       // the data, in two-wide columns from the right, snaking
    if (x === 6) x--;
    for (let k = 0; k < n; k++) { const y = up ? n - 1 - k : k;
      for (const xx of [x, x - 1]) if (!fixed[y][xx]) { m[y][xx] = at < stream.length ? !!stream[at] : false; at++; cells.push([y, xx]); } }
  }
  let best = null;
  QR_MASKS.forEach((test, mask) => {
    const trial = m.map(row => row.slice());
    for (const [y, xx] of cells) if (test(y, xx)) trial[y][xx] = !trial[y][xx];
    const fmt = ((mask << 10) | qrBch(mask, 0x537, 10)) ^ 0x5412;
    for (let i = 0; i < 15; i++) {
      const bit = !!(fmt >> (14 - i) & 1);
      if (i < 6) trial[8][i] = bit; else if (i === 6) trial[8][7] = bit; else if (i === 7) trial[8][8] = bit; else if (i === 8) trial[7][8] = bit; else trial[14 - i][8] = bit;
      if (i < 7) trial[n - 1 - i][8] = bit; else trial[8][n - 15 + i] = bit;
    }
    trial[n - 8][8] = true;
    const score = qrPenalty(trial);
    if (!best || score < best[0]) best = [score, trial];
  });
  return best[1];
}
// ---- Link (the same as vml/link.py does on a computer: see there for how a message is put together)
let link = null;
// a code may arrive inside an address (what a QR code made with LinkAddress says)
const linkCodeIn = text => { const m = /VL1[A-Za-z0-9_-]{43}(?![A-Za-z0-9_-])/.exec(String(text)); return m ? m[0] : String(text).trim(); };
// opened with a link's code after the # : kept for LinkInvite, and taken out of the address so it isn't left on show
let linkInvite = "";
try {
  const m = /VL1[A-Za-z0-9_-]{43}(?![A-Za-z0-9_-])/.exec(decodeURIComponent(location.hash));
  if (m) { linkInvite = m[0]; history.replaceState(null, "", location.pathname + location.search); }
} catch (err) {}
const linkBytes = t => new TextEncoder().encode(t);
async function linkKeys(secret) {
  const base = await crypto.subtle.importKey("raw", secret, "HKDF", false, ["deriveBits", "deriveKey"]);
  const how = info => ({ name: "HKDF", hash: "SHA-256", salt: linkBytes("visualised-link-v1"), info: linkBytes(info) });
  const channel = [...new Uint8Array(await crypto.subtle.deriveBits(how("channel"), base, 128))].map(b => b.toString(16).padStart(2, "0")).join("");
  return [channel, await crypto.subtle.deriveKey(how("key"), base, { name: "AES-GCM", length: 256 }, false, ["encrypt", "decrypt"])];
}
// Pairing by pressing together (vml/link.py says how, and why three words are enough). The same words, in the same order.
const LINK_WORDS = ("apple arrow badge baker beach berry bison blade bread brick bridge broom brush bucket butter button cabin camel " +
  "candle canoe carpet carrot castle chair chalk cheese cherry circus clock cloud clover coast cobra comet coral " +
  "cotton cradle crane crayon cricket crown daisy dancer desert diamond dinner dolphin donkey dragon drum eagle " +
  "elbow engine falcon farmer feather fence ferry fiddle finger forest fossil fountain fox garden garlic ginger " +
  "giraffe glove goblin goose grape guitar hammer harbour hazel hedge helmet heron honey hornet house island ivory " +
  "jacket jelly jigsaw jungle kettle kitten ladder lagoon lantern lemon lentil lilac lizard lobster locket magnet " +
  "mango maple marble market meadow melon mirror monkey moon mountain muffin mustard napkin needle nettle noodle " +
  "nutmeg oak ocean olive onion orange orchid otter owl oyster paddle panda parrot pasta peach pebble pencil pepper " +
  "piano pickle pigeon pillow pirate planet plum pocket pony poppy potato puddle puffin pumpkin puppet quilt rabbit " +
  "radio raven ribbon river robin rocket saddle sailor salmon sandal satin scarf shadow shell shovel silver skate " +
  "sled snail sofa spider spoon sprout squid stable statue stone storm sugar summer sunset swan table teapot " +
  "thimble thunder ticket tiger timber toast tomato torch tower tractor trumpet tulip tunnel turkey turtle umbrella " +
  "valley velvet violin wagon walnut walrus water whale wheat whistle willow window winter wizard wolf yogurt zebra " +
  "anchor acorn badger banjo basket beetle biscuit blanket bottle cactus candy copper dagger emerald flute gravel " +
  "hamster igloo jaguar kayak koala lemur mitten nugget ostrich parsnip quiver radish sparrow tadpole unicorn " +
  "vulture waffle yacht zipper pelican compass lighthouse").split(" ");
const linkTold = text => Object.assign(new Error(text), { told: true });
async function linkAsk(url, body) {
  let r, answer;
  try {
    r = await fetch(url, body === undefined ? { cache: "no-store" } : { method: "POST", headers: { "Content-Type": "text/plain" }, body: JSON.stringify(body) });
    answer = await r.json().catch(() => ({}));
  } catch (err) { throw linkTold("The relay couldn't be reached."); }
  if (!r.ok || !answer.ok) throw linkTold(answer.error ? `The relay refused that: ${answer.error}.` : "The relay couldn't be reached.");
  return answer;
}
async function linkPair(mine) {
  const hex = b => [...new Uint8Array(b)].map(x => x.toString(16).padStart(2, "0")).join("");
  const url64 = b => btoa(String.fromCharCode(...new Uint8Array(b))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  const pair = await crypto.subtle.generateKey({ name: "ECDH", namedCurve: "P-256" }, false, ["deriveBits"]);
  const pub = new Uint8Array(await crypto.subtle.exportKey("raw", pair.publicKey));
  const promise = hex(await crypto.subtle.digest("SHA-256", pub));
  const me = String((await linkAsk(`${mine.relay}?p=go`, { c: promise })).id);
  const nobody = "Nobody else pressed in time. Press together, within a few seconds of each other.";
  let shown = false;
  for (const end = Date.now() + 40000; !mine.closed && Date.now() < end;) {
    const answer = await linkAsk(`${mine.relay}?p=wait&id=${me}`);
    if (answer.state === "busy") throw linkTold("Someone else was pairing at the same moment. Press together again.");
    if (answer.state === "gone") throw linkTold(nobody);
    if (answer.state === "paired") {
      const theirs = String(answer.c || "");
      if (theirs.length !== 64 || theirs === promise) throw linkTold("The pairing went wrong. Press together again.");
      if (!shown) { await linkAsk(`${mine.relay}?p=key&id=${me}`, { k: url64(pub) }); shown = true; }      // we hold their promise: now ours may be seen
      if (answer.k) {
        const meddled = linkTold("The pairing was interfered with. Don't go on.");
        let raw, shared;
        try { raw = Uint8Array.from(atob(String(answer.k).replace(/-/g, "+").replace(/_/g, "/")), c => c.charCodeAt(0)); } catch (err) { throw meddled; }
        if (hex(await crypto.subtle.digest("SHA-256", raw)) !== theirs) throw meddled;
        try {
          const key = await crypto.subtle.importKey("raw", raw, { name: "ECDH", namedCurve: "P-256" }, false, []);
          shared = await crypto.subtle.deriveBits({ name: "ECDH", public: key }, pair.privateKey, 256);
        } catch (err) { throw meddled; }
        let low = pub, high = raw;
        for (let i = 0; i < pub.length; i++) if (pub[i] !== raw[i]) { if (pub[i] > raw[i]) { low = raw; high = pub; } break; }
        const info = new Uint8Array(low.length + high.length); info.set(low); info.set(high, low.length);
        const base = await crypto.subtle.importKey("raw", shared, "HKDF", false, ["deriveBits"]);
        const out = new Uint8Array(await crypto.subtle.deriveBits({ name: "HKDF", hash: "SHA-256", salt: linkBytes("visualised-link-pair-v1"), info }, base, 280));
        mine.code = "VL1" + url64(out.subarray(0, 32));
        return [...out.subarray(32)].map(b => LINK_WORDS[b]).join(" ");
      }
    }
    await new Promise(done => setTimeout(done, 400));
  }
  throw linkTold(nobody);
}
async function linkCall(mine, query, body) {
  if (body !== undefined && VML.linkPass) query += "&v=" + encodeURIComponent(VML.linkPass);      // its maker's pass: the link is carried in full
  const r = await fetch(`${mine.relay}?c=${mine.channel}${query}`, body === undefined ? { cache: "no-store" }
    : { method: "POST", headers: { "Content-Type": "text/plain" }, body: JSON.stringify(body) });      // (text/plain: no asking first)
  const answer = await r.json().catch(() => ({}));
  if (!r.ok || !answer.ok) throw new Error(answer.error ? `The relay refused that: ${answer.error}.` : "The relay couldn't be reached.");
  return answer;
}
async function linkPost(mine, kind, text = "") {
  const iv = crypto.getRandomValues(new Uint8Array(12)), plain = linkBytes(JSON.stringify({ k: kind, t: text, n: ++mine.count }));
  const sealed = new Uint8Array(await crypto.subtle.encrypt({ name: "AES-GCM", iv, additionalData: linkBytes(mine.channel + mine.sender) }, mine.key, plain));
  const all = new Uint8Array(12 + sealed.length); all.set(iv); all.set(sealed, 12);
  let bin = ""; for (let i = 0; i < all.length; i += 0x8000) bin += String.fromCharCode.apply(null, all.subarray(i, i + 0x8000));
  const body = btoa(bin);
  if (body.length > 24000) throw new Error("That is too much for one message (about 17,000 characters is the most).");
  await linkCall(mine, "", { s: mine.sender, b: body });
  mine.active = Date.now();
}
async function linkTake(mine, sender, body) {
  if (sender === mine.sender) return;
  let m;
  try {
    const raw = Uint8Array.from(atob(body), c => c.charCodeAt(0));
    m = JSON.parse(new TextDecoder().decode(await crypto.subtle.decrypt({ name: "AES-GCM", iv: raw.subarray(0, 12), additionalData: linkBytes(mine.channel + sender) }, mine.key, raw.subarray(12))));
  } catch (err) { return; }                       // not ours to read: someone else's noise on the channel
  const count = Number(m.n) || 0;
  if (count <= (mine.seen[sender] || 0)) return;  // an old one, played back
  const isNew = !(sender in mine.seen);
  mine.seen[sender] = count; mine.active = Date.now();
  if (m.k === "hello") { mine.tell("joined"); linkPost(mine, "ack").catch(() => {}); }
  else if (m.k === "ack") { if (isNew) mine.tell("joined"); }
  else if (m.k === "msg") mine.tell("message", String(m.t ?? ""));
  else if (m.k === "bye") { delete mine.seen[sender]; mine.tell("left"); }
}
async function linkPoll(mine) {
  if (mine.closed) return;
  try {
    const answer = await linkCall(mine, `&since=${mine.since}`);
    mine.failing = 0;
    for (const m of answer.m || []) { mine.since = Math.max(mine.since, Number(m.q) || 0); await linkTake(mine, String(m.s || ""), String(m.b || "")); }
    if (Number(answer.seq) < mine.since) mine.since = Number(answer.seq) || 0;      // (the relay began again)
  } catch (err) {
    if (++mine.failing === 5) mine.tell("error", "The relay can't be reached. It will keep trying.");
  }
  if (mine.closed) return;
  const quiet = Date.now() - mine.active;
  mine.timer = setTimeout(() => linkPoll(mine), mine.failing ? Math.min(30000, 2000 * mine.failing)
    : quiet < 15000 ? 400 : quiet < 120000 ? 1500 : quiet < 600000 ? 5000 : quiet < 3600000 ? 15000 : 60000);      // (unused, it asks less and less often)
}
function stopFlash() {
  if (!flashing) return;
  clearTimeout(flashing.timer);
  if (flashing.box) flashing.box.remove();
  if (flashing.lamp) setLamp(flashing.lamp, false);
  flashing = null;
}
// The light beside the camera, when the camera is watching and the browser lets a page switch it: then a phone
// can signal and watch at once (try it at a mirror). null when it can't.
function cameraLamp() {
  const track = watching && watching.stream && watching.stream.getVideoTracks()[0];
  try { return track && track.getCapabilities && track.getCapabilities().torch ? track : null; } catch (err) { return null; }
}
function setLamp(track, on) {
  const asked = performance.now();
  try { track.applyConstraints({ advanced: [{ torch: on }] }).then(() => { seen.lamp.push(Math.round(performance.now() - asked)); if (seen.lamp.length > 400) seen.lamp.shift(); }).catch(() => { seen.refused++; }); } catch (err) { seen.refused++; }
}
// What watching has been like, for LightReport: how evenly the camera's pictures came, and how long its light took to switch.
const seen = { gaps: [], lamp: [], refused: 0, last: 0, levels: [] };
// For whoever is tuning the reading of lights (set window.VML_RECORD before watching): the last minute of what
// the camera saw, square by square, kept and saved as a file when watching stops, to be played back at a desk.
const taped = [];
function record(time, finder) {
  taped.push({ t: time, cols: finder.cols, rows: finder.rows, now: finder.now.slice() });
  if (taped.length > 1800) taped.shift();
}
function saveRecording() {
  if (!taped.length) return;
  const first = taped[0], bytes = new Uint8Array(taped.length * first.now.length);
  taped.forEach((f, i) => bytes.set(f.now, i * first.now.length));
  let text = ""; for (let i = 0; i < bytes.length; i += 0x8000) text += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
  const file = JSON.stringify({ what: "vml-light-recording", cols: first.cols, rows: first.rows, times: taped.map(f => Math.round(f.t * 10) / 10),
    agent: navigator.userAgent, settings: (() => { try { return watching.stream.getVideoTracks()[0].getSettings(); } catch (err) { return null; } })(), camera: watching && watching.video ? watching.video.videoWidth + "x" + watching.video.videoHeight : "", squares: btoa(text) });
  taped.length = 0;
  commands.SaveFile("light-recording.json", file);
}
function stopWatching() {
  if (!watching) return;
  if (window.VML_RECORD) saveRecording();
  clearInterval(watching.timer);
  if (watching.stream) watching.stream.getTracks().forEach(t => t.stop());
  watching.video.remove();
  if (watching.ring) watching.ring.remove();
  watching = null;
}
// Finds the thing that is flashing in the camera's picture, wherever in the picture it is, and says how bright it
// is now. It looks for what CHANGES, not for what is bright: a street lamp is brighter than a distant torch, but
// only the torch goes on and off.
//
// The picture is cut into small squares, each as bright as its brightest dot (a far light is one dot). A hand is
// never still, so a steady lamp wanders from square to square and would seem to flash in each. So a square
// counts as lit when it is bright itself, but as dark only when its whole neighbourhood is dark: the lamp,
// always somewhere in the neighbourhood, never goes dark, while a torch really does. Each square remembers its
// darkest and brightest lately and how often it has flipped between lit and dark; those that flip most strongly
// are the signal.
class BlinkFinder {
  constructor(width, height, cell = 8, reach = 2) {
    this.w = width; this.h = height; this.cell = cell; this.reach = reach;
    this.cols = Math.ceil(width / cell); this.rows = Math.ceil(height / cell);
    const n = this.cols * this.rows;
    this.now = new Uint8Array(n); this.across = new Uint8Array(n); this.wide = new Uint8Array(n);
    this.lo = new Float32Array(n); this.hi = new Float32Array(n); this.up = new Uint8Array(n); this.flips = new Float32Array(n);
    this.at = -1; this.last = null; this.where = null;
    this.past = [];            // the last few seconds, to read back how a light began once it has been found
    this.moved = false;        // true for the one picture in which a light is found, or a different one taken up
    this.cells = [];           // the squares flashing with the light
  }
  // lum: how bright each dot of the picture is (0 to 255), row by row. time: milliseconds.
  feed(lum, time) {
    const { w, h, cell, cols, now } = this;
    now.fill(0);
    for (let y = 0; y < h; y++) {
      const row = ((y / cell) | 0) * cols, line = y * w;
      for (let x = 0; x < w; x++) { const v = lum[line + x], i = row + ((x / cell) | 0); if (v > now[i]) now[i] = v; }
    }
    return this.squares(time);
  }
  // The same, from the squares themselves (this.now already filled in): each as bright as its brightest dot.
  squares(time) {
    const { reach, cols, rows, now, across, wide, lo, hi, up, flips } = this;
    for (let y = 0; y < rows; y++) for (let x = 0; x < cols; x++) {            // the brightest of the neighbourhood: across, then down
      let m = 0;
      for (let k = Math.max(0, x - reach); k <= Math.min(cols - 1, x + reach); k++) m = Math.max(m, now[y * cols + k]);
      across[y * cols + x] = m;
    }
    for (let y = 0; y < rows; y++) for (let x = 0; x < cols; x++) {
      let m = 0;
      for (let k = Math.max(0, y - reach); k <= Math.min(rows - 1, y + reach); k++) m = Math.max(m, across[k * cols + x]);
      wide[y * cols + x] = m;
    }
    this.moved = false;
    this.past.push({ t: time, wide: wide.slice() });
    while (this.past.length > 600 || time - this.past[0].t > 6000) this.past.shift();
    const first = this.last === null, passed = first ? 0 : Math.max(0, time - this.last) / 1000;
    this.last = time;
    const drift = 40 * passed, fade = Math.pow(0.5, passed / 3);      // a change is forgotten in a few seconds
    let best = -1, bestScore = 0;
    for (let i = 0; i < wide.length; i++) {
      const own = now[i], around = wide[i];
      if (first) { lo[i] = around; hi[i] = own; continue; }
      lo[i] = Math.min(around, lo[i] + drift); hi[i] = Math.max(own, hi[i] - drift);
      const range = hi[i] - lo[i];
      flips[i] *= fade;
      if (range >= 30) {
        if (!up[i] && own > lo[i] + range * 0.6) { up[i] = 1; flips[i] += 1; }
        else if (up[i] && around < lo[i] + range * 0.4) { up[i] = 0; flips[i] += 1; }
      }
      const score = range * Math.min(flips[i], 6);
      if (score > bestScore) { bestScore = score; best = i; }
    }
    const score = i => (hi[i] - lo[i]) * Math.min(flips[i], 6);
    // A hand is never still, so the light wanders: each time, move to the strongest square close by.
    const close = i => { const out = [], cx = i % cols, cy = (i / cols) | 0;
      for (let y = Math.max(0, cy - 3); y <= Math.min(rows - 1, cy + 3); y++) for (let x = Math.max(0, cx - 3); x <= Math.min(cols - 1, cx + 3); x++) out.push(y * cols + x);
      return out; };
    if (this.at >= 0) { let top = this.at; for (const i of close(this.at)) if (score(i) > score(top)) top = i; this.at = top; }
    const mine = this.at < 0 ? 0 : score(this.at);
    // A light is taken up once it has flashed a few times, strongly; and left for another only if that one is
    // somewhere else and flashing half as strongly again.
    if (best >= 0 && bestScore >= 240 && hi[best] - lo[best] >= 50
        && (this.at < 0 || (bestScore > mine * 1.5 && !close(this.at).includes(best)))) { this.at = best; this.moved = true; }
    else if (this.at >= 0 && mine < 80) this.at = -1;
    if (this.at < 0) { this.where = null; this.cells = []; return 0; }
    // Every square within reach of the light flashes with it: the light is in the middle of them.
    const near = score(this.at) * 0.6;
    this.cells = close(this.at).filter(i => score(i) >= near);
    let sx = 0, sy = 0;
    for (const i of this.cells) { sx += i % cols; sy += (i / cols) | 0; }
    this.where = { x: (sx / this.cells.length + 0.5) / cols, y: (sy / this.cells.length + 0.5) / rows };
    return this.level(wide);
  }
  // How lit the light is, 0 to 255: each of its squares measured against its own darkest and brightest, and the
  // middle one taken, so a square that has wandered off the light doesn't spoil the reading.
  level(wide) {
    const { lo, hi } = this, v = this.cells.map(i => (wide[i] - lo[i]) / Math.max(1, hi[i] - lo[i])).sort((a, b) => a - b);
    return v.length ? 255 * Math.max(0, Math.min(1, v[v.length >> 1])) : 0;
  }
  // What the light just found was doing before it was found, as [time, level] pairs: back to the last time it
  // was dark for a good second, because a message starts from darkness.
  history() {
    const all = this.past.map(p => [p.t, this.level(p.wide)]);
    let start = 0, dark = -1;
    all.forEach(([t, l], k) => { if (l < 100) { if (dark < 0) dark = k; if (t - all[dark][0] >= 1000) start = k; } else dark = -1; });
    return all.slice(start);
  }
  // Where in the picture the signal is (0 to 1 across and down), or null when nothing is flashing.
  get spot() { return this.where; }
}
// The two together: pictures in, and out comes "new" (a light has been found: what was reported before was
// something else, and how this one began follows at once), then "on" and "off" with how long the state before lasted.
class LightWatcher {
  constructor(width, height, report) { this.finder = new BlinkFinder(width, height); this.report = report; this.reader = new LightReader(report); }
  feed(lum, time) { this.finder.feed(lum, time); return this.seen(time); }
  squares(time) { this.finder.squares(time); return this.seen(time); }       // (when the finder's squares are filled in already)
  seen(time) {
    const f = this.finder, level = f.spot ? f.level(f.wide) : 0;
    if (f.moved) {
      this.report("new", 0);
      this.reader = new LightReader(this.report);
      for (const [t, l] of f.history().slice(0, -1)) this.reader.feed(l, t);
    }
    if (f.spot) this.reader.feed(level, time);
    return level;
  }
}
// Turns a run of brightness readings into "it went on" and "it went off", each with how long the state before
// lasted. What counts as bright is learned from what it sees: the darkest and brightest readings lately, each
// drifting slowly back toward the present, so a change of scene is forgotten in a minute and a steady scene
// (however bright) is never a signal.
class LightReader {
  constructor(report) { this.report = report; this.lo = null; this.hi = null; this.on = false; this.since = 0; this.last = 0; }
  feed(level, now) {
    if (this.lo === null) { this.lo = this.hi = level; this.since = this.last = now; return; }
    const drift = 4 * (now - this.last) / 1000;
    this.last = now;
    this.lo = Math.min(level, this.lo + drift);
    this.hi = Math.max(level, this.hi - drift);
    const range = this.hi - this.lo;
    if (range < 20) return;                                    // nothing is flashing: only the camera's own flicker
    const state = this.on ? level > this.lo + range * 0.4 : level > this.lo + range * 0.6;
    if (state === this.on) return;
    this.on = state;
    this.report(state ? "on" : "off", now - this.since);
    this.since = now;
  }
}
let awake = null;
function photo(image, handler, camera) {
  const pick = document.createElement("input");
  pick.type = "file"; pick.accept = "image/*";
  if (camera) pick.setAttribute("capture", "environment");
  pick.onchange = () => {
    const file = pick.files && pick.files[0];
    if (!file) return;
    const url = URL.createObjectURL(file), img = new Image();
    img.onload = () => {                          // a phone's photo is huge: 1600 across is plenty for a form, and small enough to keep
      const k = Math.min(1, 1600 / Math.max(img.naturalWidth, img.naturalHeight)), c = document.createElement("canvas");
      c.width = Math.round(img.naturalWidth * k); c.height = Math.round(img.naturalHeight * k);
      c.getContext("2d").drawImage(img, 0, 0, c.width, c.height);
      URL.revokeObjectURL(url);
      commands.SetProperty(image, "Source", c.toDataURL("image/jpeg", 0.85));
      if (handler) run(handler, [image]);
    };
    img.onerror = () => URL.revokeObjectURL(url);
    img.src = url;
  };
  pick.click();
  return "";
}
// A page being previewed from the designer, opened in a phone's browser, offers to open in the app instead.
function offerApp() {
  if (window.VML_PREVIEW && location.protocol !== "file:")      // tell the designer how much room this phone really has
    fetch(`/_size?w=${window.innerWidth}&h=${window.innerHeight}&app=${DEV ? 1 : 0}`).catch(() => {});
  if (!window.VML_PREVIEW || DEV || !/Android/.test(navigator.userAgent) || document.getElementById("vml_offer")) return;
  const b = document.createElement("div");
  b.id = "vml_offer";
  b.style.cssText = "position:fixed;left:8px;right:8px;bottom:8px;z-index:99999;display:flex;align-items:center;gap:8px;padding:10px 12px;border-radius:10px;background:#111827;color:#fff;font:14px system-ui,sans-serif;box-shadow:0 4px 16px rgba(0,0,0,.35)";
  const a = document.createElement("a");
  a.href = "visualised://" + location.host + "/";
  a.textContent = "Open in the Visualised app";
  a.style.cssText = "flex:1;color:#fff;font-weight:600;text-decoration:none";
  const get = document.createElement("a");                    // for someone who hasn't the app yet
  get.href = "https://visualised.io/#download";
  get.textContent = "Get the app";
  get.style.cssText = "color:#93C5FD;text-decoration:none;white-space:nowrap";
  const x = document.createElement("span");
  x.textContent = "×"; x.style.cssText = "padding:0 6px;font-size:20px;cursor:pointer";
  x.onclick = () => b.remove();
  b.append(a, get, x);
  document.body.appendChild(b);
}
function Vml(cmd, ...args) {
  args = args.map(a => a == null ? "" : String(a));
  const f = commands[cmd];
  if (!f) { console.warn(`Vml("${cmd}") isn't available in the browser`); return ""; }
  try { const r = f(...args); return r == null ? "" : String(r); }
  catch (err) { console.error(`Vml("${cmd}")`, err); return ""; }
}

window.vml = { Vml, settings, LightReader, BlinkFinder, LightWatcher, qrMatrix };                 // handy in the browser console: vml.Vml("GetProperty", "txtName", "Text")

let fns = null;
function luaFunction(name) {                    // a function one of the project's modules defined
  if (!lua || !/^[A-Za-z_]\w*$/.test(name)) return null;
  try { const f = lua.global.get(name); return typeof f === "function" ? f : null; } catch (err) { return null; }
}
function run(name, args = []) {
  const s = VML.scripts[name];
  if (!s) {
    const f = luaFunction(name);
    if (!f) { console.warn("no script called", name); return ""; }
    try { const r = f(...args); return r == null ? "" : String(r); }
    catch (err) { console.error(`script error in ${name}:`, err); return ""; }
  }
  if (s.interp !== "lua") { console.warn(`${name} is a ${s.interp} script: that runs on the desktop, not in a browser`); return ""; }
  if (!fns) return "";
  try { const r = fns.get(name)(...args); return r == null ? "" : String(r); }
  catch (err) { console.error(`script error in ${name}:`, err); return ""; }
}

function handle(handler, name, details = {}) {
  for (const [k, v] of Object.entries(details)) settings[k] = String(v);
  settings.event_control = name;
  if (VML.scripts[handler] || luaFunction(handler)) return run(handler, [name]);
  let m = handler.match(/^\s*(\w+)\s*\((.*)\)\s*$/);
  if (m && (VML.scripts[m[1]] || luaFunction(m[1]))) return run(m[1], m[2].split(",").map(s => s.trim().replace(/^['"]|['"]$/g, "")).filter(Boolean));
  m = handler.match(/^\s*(\w+)\s+(.+)$/);
  if (m && commands[m[1]] && !handler.includes("(")) return Vml(m[1], ...m[2].split(/\s+/));
  if (commands[handler]) return Vml(handler);
  if (lua) lua.doString(handler).catch(err => console.error(`handler error (${name}):`, err));
}

const KEYS = { " ": "Space", ArrowUp: "Up", ArrowDown: "Down", ArrowLeft: "Left", ArrowRight: "Right", Esc: "Escape" };
function keyDetails(e) {
  const mods = [e.ctrlKey && "Ctrl", e.shiftKey && "Shift", e.altKey && "Alt", e.metaKey && "Meta"].filter(Boolean).join("+");
  const key = KEYS[e.key] || (e.key.length === 1 ? e.key.toUpperCase() : e.key);
  return { event_key: key, event_key_text: e.key.length === 1 ? e.key : "", event_modifiers: mods, event_repeat: e.repeat ? "true" : "false" };
}
function pointer(e, target) {
  const r = target.getBoundingClientRect();
  return { event_x: Math.round((e.clientX - r.left) / SCALE), event_y: Math.round((e.clientY - r.top) / SCALE), mouse_button: ["Left", "Middle", "Right"][e.button] || "Left" };
}
// a progress bar is drawn from its data- attributes
function drawBar(e) {
  const d = e.dataset, lo = Number(d.min), hi = Number(d.max);
  let f = hi > lo ? Math.max(0, Math.min(1, (Number(d.value) - lo) / (hi - lo))) : 0;
  const bar = e.querySelector("i"), text = e.querySelector("b"), up = d.upright === "True";
  if (d.style === "blocks") {                              // whole blocks only, as on the desktop
    const across = up ? e.clientWidth : e.clientHeight, along = up ? e.clientHeight : e.clientWidth;
    const blk = Math.max(6, Math.round(across * 0.6)), n = Math.max(1, Math.floor((along + 2) / (blk + 2)));
    e.style.setProperty("--blk", blk + "px");
    f = along ? Math.round(f * n) * (blk + 2) / along : 0;
  }
  if (d.busy !== "True") { bar.style[up ? "height" : "width"] = (Math.min(1, f) * 100) + "%"; bar.style.left = ""; }
  const pc = hi > lo ? Math.round(Math.max(0, Math.min(1, (Number(d.value) - lo) / (hi - lo))) * 100) : 0;
  text.textContent = d.text === "True" && d.style !== "thin" && d.busy !== "True" ? pc + "%" : "";
  text.style.color = pc > 55 && d.style !== "blocks" ? "#fff" : "#111827";
}
const BAR_PROPS = { Value: "value", Minimum: "min", Maximum: "max", BarStyle: "style", ShowText: "text", IsIndeterminate: "busy", Orientation: "upright" };

// timers: each runs its OnTick handler every Interval milliseconds while it is on
const ticking = {};
function setTimer(e) {
  clearInterval(ticking[e.id]);
  delete ticking[e.id];
  const h = VML.handlers.find(x => x.id === e.id && x.event === "OnTick");
  if (h && e.dataset.on === "true") ticking[e.id] = setInterval(() => handle(h.handler, h.name), Math.max(1, Number(e.dataset.interval) || 1000));
}

// On a screen narrower than the form was drawn (a phone), the whole form is scaled to the screen's width, and given
// the screen's height at that scale, so what is anchored to the bottom reaches the bottom. PhoneFit=None on the
// Window turns this off. SCALE is what one form pixel measures on screen.
let SCALE = 1;
function fitScreen() {
  const w = document.getElementById("vml_window"), [dw, dh] = VML.design || [0, 0];
  const narrow = VML.fit !== "None" && dw > 0 && window.innerWidth < dw;
  // With plenty of room (half as wide again as the form, or more: a computer's browser, a tablet), the form is a window in the middle of the
  // page at the size it was drawn, not stretched across it. WebFit=Fill on the Window fills the page instead.
  const roomy = !narrow && VML.webFit !== "Fill" && dw > 0 && dh > 0 && window.innerWidth >= dw * 1.5 && window.innerWidth >= dw + 240;
  document.body.classList.toggle("phone", narrow);
  document.body.classList.toggle("framed", roomy);
  if (roomy) {
    SCALE = 1;
    const high = Math.min(dh, window.innerHeight - 32);
    w.style.cssText = `inset:auto;left:${Math.round((window.innerWidth - dw) / 2)}px;top:${Math.max(16, Math.round((window.innerHeight - high) / 2))}px;width:${dw}px;height:${high}px`;
    document.querySelectorAll(".pbar").forEach(drawBar);
    return;
  }
  if (!narrow) {
    if (SCALE !== 1 || w.style.cssText) { SCALE = 1; w.style.cssText = ""; }
    return;
  }
  SCALE = window.innerWidth / dw;
  const tall = Math.max(window.innerHeight / SCALE, VML.fit === "Width" ? dh : 0);
  w.style.inset = "auto"; w.style.left = "0"; w.style.top = "0";
  w.style.width = dw + "px"; w.style.height = tall + "px";
  w.style.transformOrigin = "0 0"; w.style.transform = `scale(${SCALE})`;
  document.querySelectorAll(".pbar").forEach(drawBar);
}
window.addEventListener("resize", fitScreen);
window.addEventListener("orientationchange", fitScreen);

function wire() {
  fitScreen();
  offerApp();
  document.querySelectorAll(".pbar").forEach(drawBar);
  document.querySelectorAll('[data-type="Timer"]').forEach(setTimer);
  for (const h of VML.handlers) {
    const outer = document.getElementById(h.id);
    if (!outer) continue;
    // a checkbox is a <label> around an <input>: listen on the input, or label clicks fire twice
    const e = outer.matches("label.cb") ? outer.querySelector("input") : outer;
    const go = d => handle(h.handler, h.name, d);
    const map = {
      OnClick: () => e.addEventListener("click", ev => { if (outer.dataset.type === "MenuItem") { ev.stopPropagation(); if (e.querySelector(".drop")) return; closeMenus(); } go(); }),
      OnChecked: () => e.addEventListener("change", () => go()),
      TextChanged: () => e.addEventListener("input", () => go()),
      ValueChanged: () => e.addEventListener("input", () => go()),
      SelectionChanged: () => e.addEventListener("change", () => go()),
      OnKeyDown: () => e.addEventListener("keydown", ev => go(keyDetails(ev))),
      OnKeyUp: () => e.addEventListener("keyup", ev => go(keyDetails(ev))),
      OnPointerPressed: () => outer.addEventListener("mousedown", ev => go(pointer(ev, outer))),
      OnPointerReleased: () => outer.addEventListener("mouseup", ev => go(pointer(ev, outer))),
      OnPointerMoved: () => outer.addEventListener("mousemove", ev => go(pointer(ev, outer))),
      OnDoubleClick: () => outer.addEventListener("dblclick", () => go()),
      OnLostFocus: () => e.addEventListener("blur", () => go()),
      OnGotFocus: () => e.addEventListener("focus", () => go()),
    };
    (map[h.event] || (() => {}))();
  }
}

// menus: click a caption to open it; moving across the bar switches menus while one is open
function closeMenus() { document.querySelectorAll(".mtop.open").forEach(m => m.classList.remove("open")); document.querySelectorAll(".ctx").forEach(m => m.style.display = "none"); }
document.querySelectorAll(".mtop").forEach(t => {
  t.addEventListener("click", ev => { if (ev.target.closest(".drop")) return; const was = t.classList.contains("open"); closeMenus(); if (!was) t.classList.add("open"); ev.stopPropagation(); });
  t.addEventListener("mouseenter", () => { if (document.querySelector(".mtop.open")) { closeMenus(); t.classList.add("open"); } });
});
document.addEventListener("click", ev => { if (!ev.target.closest(".drop")) closeMenus(); });
document.addEventListener("contextmenu", ev => { if (VML.handlers.some(h => h.event === "OnPointerPressed")) ev.preventDefault(); });
document.addEventListener("keydown", ev => { if (ev.key === "Escape") closeMenus(); });

wire();
try {
  // bundled in the page (offline), or fetched from the CDN
  const { LuaFactory } = window.wasmoon ? window.wasmoon : await import("%%WASMOON%%");
  if (VML.data) {                                          // only pages that use a database carry the engine for one
    try {
      const init = window.initSqlJs || await new Promise((ok, no) => {      // not bundled: fetch it
        const t = document.createElement("script"); t.src = VML.sqljs + "sql-wasm.js";
        t.onload = () => ok(window.initSqlJs); t.onerror = no; document.head.appendChild(t); });
      SQL = await init(window.VML_SQLWASM ? { wasmBinary: b64bytes(window.VML_SQLWASM) } : { locateFile: f => VML.sqljs + f });
    } catch (err) { console.error("the database engine couldn't load:", err); }
  }
  const factory = new LuaFactory(window.VML_WASM);
  await factory.mountFile("dkjson.lua", DKJSON);
  lua = await factory.createEngine();
  lua.global.set("Vml", Vml);
  lua.global.set("print", (...a) => console.log("[lua]", ...a));
  await lua.doString("Project = {}; __vml_scripts = {}");
  for (const m of VML.modules || []) {                     // a project's modules: there for every script
    try { await lua.doString(m.code); } catch (err) { console.error(`module ${m.name} has an error:`, err); }
  }

  for (const [name, s] of Object.entries(VML.scripts)) {
    if (s.interp !== "lua") continue;
    try { await lua.doString(`__vml_scripts[${JSON.stringify(name)}] = function(...) local args = {...}; local arg = args\n${s.code}\nend`); }
    catch (err) { console.error(`script ${name} has an error:`, err); }
  }
  fns = { get: name => lua.global.get("__vml_scripts")[name] };
  status.textContent = ""; status.dataset.ready = "1";
  if (VML.onOpened) handle(VML.onOpened, VML.form);
  refill();                                                // controls that fill themselves, once OnOpened has set things up
} catch (err) {
  status.textContent = "Lua couldn't load (offline?): scripts are off";
  console.error(err);
}
</script>
</body>
</html>
"""
