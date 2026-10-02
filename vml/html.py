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
import re
from pathlib import Path

from .registry import anchor_set, colour, num, thickness
from .store import LUA_DIR, Store

WASMOON = "https://cdn.jsdelivr.net/npm/wasmoon@1.16.0/+esm"
MENU_H = 26
WEIGHTS = {"Thin": 100, "ExtraLight": 200, "Light": 300, "Normal": 400, "Medium": 500, "SemiBold": 600,
           "Bold": 700, "ExtraBold": 800, "Black": 900}
EVENT_NAMES = ("OnClick", "TextChanged", "SelectionChanged", "OnKeyDown", "OnKeyUp", "OnPointerPressed",
               "OnPointerReleased", "OnPointerMoved", "OnLostFocus", "OnGotFocus", "OnChecked", "OnOpened")


def css_id(name):
    return "v_" + re.sub(r"[^A-Za-z0-9_]", "_", str(name))


def esc(s):
    return html.escape(str(s or ""), quote=True)


class Page:
    def __init__(self, vml_path):
        self.path = Path(vml_path)
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
            wrap = "normal" if p.get("TextWrapping") == "Wrap" else "nowrap"
            align = {"Center": "center", "Right": "right"}.get(p.get("TextAlignment"), "left")
            css += [f"white-space:{wrap}", f"text-align:{align}"]
            return f'<div {attrs} class="tb" style="{";".join(css)}">{esc(p.get("Text", ""))}</div>'
        if ctype == "TextBox":
            ph = esc(p.get("Watermark", ""))
            ro = " readonly" if str(p.get("IsReadOnly", "")).lower() == "true" else ""
            if str(p.get("AcceptsReturn", "")).lower() == "true":
                return f'<textarea {attrs} placeholder="{ph}" style="{";".join(css)}"{ro}{disabled}>{esc(p.get("Text", ""))}</textarea>'
            return f'<input type="text" {attrs} value="{esc(p.get("Text", ""))}" placeholder="{ph}" style="{";".join(css)}"{ro}{disabled}>'
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

    def build(self):
        win = next((r for r in self.rows if r[2] == "Window"), None)
        if win is None:
            raise ValueError(f"{self.path.name} has no @Window")
        wp = self.props.get(win[0], {})
        self.names[win[3]] = "vml_window"
        body = "".join(self.render(k, "Window") for k in self.kids.get(win[0], [])
                       if self.by_id[k][2] not in ("ContextMenu", "MenuItem", "MenuTheme"))
        scripts = {n: {"interp": (i or "lua").split()[0].lower(), "code": c} for n, (i, c) in self.scripts.items()}
        dkjson = (LUA_DIR / "dkjson.lua").read_text(encoding="utf-8")
        data = {"form": win[3], "names": self.names, "scripts": scripts, "onOpened": wp.get("OnOpened", ""),
                "handlers": [{"id": e, "event": ev, "handler": h, "name": n} for e, ev, h, n in self.handlers]}
        bg = colour(wp.get("Background", "#ffffff"))
        return TEMPLATE.replace("%%TITLE%%", esc(wp.get("Title", win[3]))).replace("%%BG%%", bg) \
            .replace("%%THEME%%", self.theme_css()).replace("%%BODY%%", body + self.context_menus()) \
            .replace("%%DATA%%", json.dumps(data).replace("</", "<\\/")) \
            .replace("%%DKJSON%%", json.dumps(dkjson).replace("</", "<\\/")).replace("%%WASMOON%%", WASMOON) \
            .replace("%%SOURCE%%", esc(self.path.name))


def export_html(vml_path, out_path=None):
    page = Page(vml_path).build()
    out = Path(out_path) if out_path else Path(vml_path).with_suffix(".html")
    out.write_text(page, encoding="utf-8")
    return str(out)


TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="generator" content="VML (from %%SOURCE%%)">
<title>%%TITLE%%</title>
<style>
  html, body { margin: 0; height: 100%; }
  body { font: 13px system-ui, -apple-system, "Segoe UI", Ubuntu, sans-serif; color: #111827; background: %%BG%%; }
  #vml_window { position: absolute; inset: 0; display: flex; flex-direction: column; overflow: hidden; }
  #vml_window > * { flex: 1; min-height: 0; }
  #vml_window > .menubar { flex: 0 0 auto; }
  button { font: inherit; padding: 4px 10px; border: 1px solid #c4c8cf; border-radius: 4px; background: #f7f7f8; cursor: pointer; }
  button:hover { border-color: #9ca3af; } button:active { background: #e5e7eb; }
  input[type=text], textarea, select { font: inherit; box-sizing: border-box; border: 1px solid #c4c8cf; border-radius: 3px; padding: 3px 5px; background: #fff; }
  textarea { resize: none; }
  .cb { display: inline-flex; align-items: center; gap: 6px; white-space: nowrap; }
  .tb { overflow: hidden; text-overflow: ellipsis; }
  .canvas > *, .frame > * { box-sizing: border-box; }
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
<script type="module">
// The VML runtime for the web: Lua 5.4 (WebAssembly) running the form's scripts against a JavaScript Vml().
const VML = %%DATA%%;
const DKJSON = %%DKJSON%%;
const settings = {};
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

const commands = {
  SetProperty(name, prop, value = "") {
    const e = name === VML.form ? null : el(name);
    if (name === VML.form || !e) { if (prop === "Title") document.title = value; return ""; }
    const css = { Background: "background", Foreground: "color", Fill: "background" };
    if (prop === "Text" || prop === "Content" || prop === "Header") setText(e, value);
    else if (css[prop]) e.style[css[prop]] = value;
    else if (prop === "FontSize") e.style.fontSize = value + "px";
    else if (prop === "IsVisible") e.style.display = truthy(value) ? "" : "none";
    else if (prop === "IsEnabled") { const t = e.matches("label.cb") ? e.querySelector("input") : e; truthy(value) ? t.removeAttribute("disabled") : t.setAttribute("disabled", ""); }
    else if (prop === "IsChecked") e.querySelector("input").checked = truthy(value);
    else if (prop === "Watermark") e.placeholder = value;
    else if (prop === "Width") e.style.width = value + "px";
    else if (prop === "Height") e.style.height = value + "px";
    else if (prop === "Canvas.Left") e.style.left = value + "px";
    else if (prop === "Canvas.Top") e.style.top = value + "px";
    else if (prop === "Items") { e.innerHTML = ""; String(value).split(",").map(s => s.trim()).filter(Boolean).forEach(t => e.add(new Option(t))); }
    else if (prop === "SelectedIndex") e.selectedIndex = Number(value);
    else if (prop === "SelectedItem") e.value = value;
    else if (prop === "ToolTip") e.title = value;
    else e.dataset["p_" + prop.replace(/\W/g, "_")] = value;
    return "";
  },
  GetProperty(name, prop) {
    const e = el(name);
    if (!e) return "";
    if (prop === "Text" || prop === "Content" || prop === "Header") return textOf(e);
    if (prop === "IsChecked") return e.querySelector("input").checked ? "true" : "false";
    if (prop === "SelectedIndex") return String(e.selectedIndex);
    if (prop === "SelectedItem") return e.selectedIndex >= 0 ? e.options[e.selectedIndex].text : "";
    if (prop === "IsVisible") return e.style.display === "none" ? "false" : "true";
    if (prop === "IsEnabled") return (e.matches("label.cb") ? e.querySelector("input") : e).hasAttribute("disabled") ? "false" : "true";
    if (prop === "Width") return String(e.offsetWidth);
    if (prop === "Height") return String(e.offsetHeight);
    return e.dataset["p_" + prop.replace(/\W/g, "_")] || "";
  },
  GetSetting: k => settings[k] ?? "",
  SetSetting(k, v = "") { settings[k] = String(v); return ""; },
  RunScript: (name, ...args) => run(name, args),
  InfoDialog(msg, title) { alert(msg); return ""; },
  ErrorDialog(msg, title) { alert(msg); return ""; },
  ConfirmDialog: (msg, title) => confirm(msg) ? "true" : "false",
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
  FormOpen(path) { open(String(path).replace(/\.vml$/i, ".html"), "_blank"); return ""; },
  FormOpenModal(path) { open(String(path).replace(/\.vml$/i, ".html"), "_blank"); return ""; },
  SetDialogResult() { return ""; },
  CloseSelf() { window.close(); return ""; },
  AppExit() { window.close(); return ""; },
};
function Vml(cmd, ...args) {
  args = args.map(a => a == null ? "" : String(a));
  const f = commands[cmd];
  if (!f) { console.warn(`Vml("${cmd}") isn't available in the browser`); return ""; }
  try { const r = f(...args); return r == null ? "" : String(r); }
  catch (err) { console.error(`Vml("${cmd}")`, err); return ""; }
}

window.vml = { Vml, settings };                 // handy in the browser console: vml.Vml("GetProperty", "txtName", "Text")

let fns = null;
function run(name, args = []) {
  const s = VML.scripts[name];
  if (!s) { console.warn("no script called", name); return ""; }
  if (s.interp !== "lua") { console.warn(`${name} is a ${s.interp} script: that runs on the desktop, not in a browser`); return ""; }
  if (!fns) return "";
  try { const r = fns.get(name)(...args); return r == null ? "" : String(r); }
  catch (err) { console.error(`script error in ${name}:`, err); return ""; }
}

function handle(handler, name, details = {}) {
  for (const [k, v] of Object.entries(details)) settings[k] = String(v);
  settings.event_control = name;
  if (VML.scripts[handler]) return run(handler, [name]);
  let m = handler.match(/^\s*(\w+)\s*\((.*)\)\s*$/);
  if (m && VML.scripts[m[1]]) return run(m[1], m[2].split(",").map(s => s.trim().replace(/^['"]|['"]$/g, "")).filter(Boolean));
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
  return { event_x: Math.round(e.clientX - r.left), event_y: Math.round(e.clientY - r.top), mouse_button: ["Left", "Middle", "Right"][e.button] || "Left" };
}
function wire() {
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
      SelectionChanged: () => e.addEventListener("change", () => go()),
      OnKeyDown: () => e.addEventListener("keydown", ev => go(keyDetails(ev))),
      OnKeyUp: () => e.addEventListener("keyup", ev => go(keyDetails(ev))),
      OnPointerPressed: () => outer.addEventListener("mousedown", ev => go(pointer(ev, outer))),
      OnPointerReleased: () => outer.addEventListener("mouseup", ev => go(pointer(ev, outer))),
      OnPointerMoved: () => outer.addEventListener("mousemove", ev => go(pointer(ev, outer))),
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
  const { LuaFactory } = await import("%%WASMOON%%");
  const factory = new LuaFactory();
  await factory.mountFile("dkjson.lua", DKJSON);
  lua = await factory.createEngine();
  lua.global.set("Vml", Vml);
  lua.global.set("print", (...a) => console.log("[lua]", ...a));
  await lua.doString("__vml_scripts = {}");
  for (const [name, s] of Object.entries(VML.scripts)) {
    if (s.interp !== "lua") continue;
    try { await lua.doString(`__vml_scripts[${JSON.stringify(name)}] = function(...) local args = {...}; local arg = args\n${s.code}\nend`); }
    catch (err) { console.error(`script ${name} has an error:`, err); }
  }
  fns = { get: name => lua.global.get("__vml_scripts")[name] };
  status.textContent = ""; status.dataset.ready = "1";
  if (VML.onOpened) handle(VML.onOpened, VML.form);
} catch (err) {
  status.textContent = "Lua couldn't load (offline?): scripts are off";
  console.error(err);
}
</script>
</body>
</html>
"""
