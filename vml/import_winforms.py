"""Import a Windows Forms form (Visual Studio, VB.NET or C#) as a Visualised canvas form.

    convert("frmLogin.Designer.vb")  ->  (vml text, notes)

What it reads
  * the designer file (frmLogin.Designer.vb / .Designer.cs): every control, where it sits, what it says, the menus;
  * the code beside it (frmLogin.vb / .cs), if it is there: each event handler is carried across as a script on the
    control it belonged to. The Visual Basic or C# is kept as comments, for reference: it cannot run here, and
    nothing is thrown away;
  * the resources beside it (frmLogin.resx), if there: text that Visual Studio stored there instead of in the code.

What comes out is an ordinary canvas form: controls at the same places and sizes, inside the same frames. Controls
Visualised has no equal for yet (a grid, a tree, a picture) become a captioned frame of the same size, so the
layout stays true, and the notes say exactly which those were.
"""
import re
import xml.etree.ElementTree as ET
from pathlib import Path

MENU_BAR = 24            # a Windows Forms MenuStrip's height: controls below it are measured from under it here
PT_TO_PX = 96.0 / 72.0

# Windows Forms control -> (Visualised control, the property its text goes in, a note if it is only an approximation)
CONTROLS = {
    "Label": ("TextBlock", "Text", ""), "LinkLabel": ("TextBlock", "Text", "a link label becomes plain text"),
    "Button": ("Button", "Content", ""),
    "TextBox": ("TextBox", "Text", ""), "MaskedTextBox": ("TextBox", "Text", "an input mask is not carried over"),
    "RichTextBox": ("TextBox", "Text", "rich text becomes a plain multi-line box"),
    "CheckBox": ("CheckBox", "Content", ""),
    "RadioButton": ("CheckBox", "Content", "an option button becomes a check box (no option buttons yet)"),
    "ComboBox": ("ComboBox", "", ""), "ListBox": ("ListBox", "", ""),
    "CheckedListBox": ("ListBox", "", "a checked list becomes a plain list"),
    "GroupBox": ("Frame", "Text", ""), "Panel": ("Frame", "", ""), "FlowLayoutPanel": ("Frame", "", ""),
    "TableLayoutPanel": ("Frame", "", "a table layout is turned into fixed positions"),
    "SplitContainer": ("Frame", "", "a split container becomes two fixed areas"),
    "TabControl": ("Frame", "", ""), "TabPage": ("Frame", "Text", ""),
    "NumericUpDown": ("TextBox", "", "a number spinner becomes a text box"),
    "DateTimePicker": ("TextBox", "", "a date picker becomes a text box"),
}
CONTAINERS = {"GroupBox", "Panel", "FlowLayoutPanel", "TableLayoutPanel", "SplitContainer", "TabControl", "TabPage"}
STRIPS = {"MenuStrip", "ContextMenuStrip", "ToolStrip", "StatusStrip"}
STRIP_ITEMS = {"ToolStripMenuItem", "ToolStripSeparator", "ToolStripButton", "ToolStripLabel", "ToolStripStatusLabel",
               "ToolStripDropDownButton", "ToolStripSplitButton", "ToolStripTextBox", "ToolStripComboBox",
               "ToolStripProgressBar"}

# Windows Forms event -> Visualised event, per Visualised control
EVENTS = {
    "Click": "OnClick", "TextChanged": "TextChanged", "SelectedIndexChanged": "SelectionChanged",
    "SelectedValueChanged": "SelectionChanged", "SelectionChangeCommitted": "SelectionChanged",
    "CheckedChanged": "OnChecked", "KeyDown": "OnKeyDown", "KeyUp": "OnKeyUp", "KeyPress": "OnKeyDown",
    "Enter": "OnGotFocus", "GotFocus": "OnGotFocus", "Leave": "OnLostFocus", "LostFocus": "OnLostFocus",
    "MouseDown": "OnPointerPressed", "MouseUp": "OnPointerReleased", "MouseMove": "OnPointerMoved",
    "Load": "OnOpened", "Shown": "OnOpened", "FormClosing": "OnClosing", "Closing": "OnClosing",
}
SUPPORTS = {
    "Button": {"OnClick", "OnKeyDown", "OnKeyUp", "OnPointerPressed", "OnPointerReleased", "OnPointerMoved", "OnLostFocus", "OnGotFocus"},
    "CheckBox": {"OnClick", "OnChecked", "OnKeyDown", "OnKeyUp", "OnPointerPressed", "OnPointerReleased", "OnPointerMoved", "OnLostFocus", "OnGotFocus"},
    "TextBox": {"TextChanged", "OnKeyDown", "OnKeyUp", "OnPointerPressed", "OnPointerReleased", "OnPointerMoved", "OnLostFocus", "OnGotFocus"},
    "ComboBox": {"SelectionChanged", "OnKeyDown", "OnKeyUp"}, "ListBox": {"SelectionChanged", "OnKeyDown", "OnKeyUp"},
    "TextBlock": {"OnPointerPressed", "OnPointerReleased", "OnPointerMoved", "OnLostFocus", "OnGotFocus"},
    "Frame": {"OnPointerPressed", "OnPointerReleased", "OnPointerMoved", "OnLostFocus", "OnGotFocus"},
    "MenuItem": {"OnClick"}, "Window": {"OnOpened", "OnClosing", "OnKeyDown", "OnKeyUp"},
}
SYSTEM_COLOURS = {
    "Control": "#f0f0f0", "ControlText": "#000000", "Window": "#ffffff", "WindowText": "#000000",
    "ControlDark": "#a0a0a0", "ControlDarkDark": "#696969", "ControlLight": "#e3e3e3", "ControlLightLight": "#ffffff",
    "Highlight": "#0078d7", "HighlightText": "#ffffff", "GrayText": "#6d6d6d", "Info": "#ffffe1", "InfoText": "#000000",
    "ActiveCaption": "#99b4d1", "ActiveCaptionText": "#000000", "InactiveCaption": "#bfcddb", "AppWorkspace": "#ababab",
    "ButtonFace": "#f0f0f0", "ButtonHighlight": "#ffffff", "ButtonShadow": "#a0a0a0", "Desktop": "#000000",
    "Menu": "#f0f0f0", "MenuText": "#000000", "ScrollBar": "#c8c8c8", "HotTrack": "#0066cc",
}


# ---------------------------------------------------------------- reading the designer file
def _statements(text, csharp):
    """The statements inside InitializeComponent, one per item, written the Visual Basic way whichever language
    the file is in (Me.X = New T(...)), so the rest of the importer reads one dialect."""
    if csharp:
        m = re.search(r"void\s+InitializeComponent\s*\(\s*\)\s*\{", text)
        if not m:
            return []
        depth, i = 1, m.end()
        while i < len(text) and depth:
            depth += {"{": 1, "}": -1}.get(text[i], 0)
            i += 1
        body = re.sub(r"//[^\n]*", "", text[m.end():i - 1])
        out = []
        for st in re.split(r";\s*\n", body):
            st = " ".join(st.split())
            if not st:
                continue
            st = re.sub(r"\bthis\.", "Me.", st)
            st = re.sub(r"\bnew\b", "New", st)
            st = re.sub(r"\btrue\b", "True", st)
            st = re.sub(r"\bfalse\b", "False", st)
            out.append(st.rstrip(";").strip())
        return out
    m = re.search(r"Sub\s+InitializeComponent\s*\(\s*\)(.*?)\n\s*End\s+Sub", text, re.S | re.I)
    if not m:
        return []
    body = re.sub(r"[ \t]+_[ \t]*\r?\n[ \t]*", " ", m.group(1))             # a trailing " _" joins two lines
    return [ln.strip() for ln in body.splitlines() if ln.strip() and not ln.strip().startswith("'")]


def _split_args(text):
    """Split "a, f(b, c), "d, e"" at the commas that are not inside brackets or a string."""
    out, depth, cur, quote = [], 0, "", False
    for ch in text:
        if ch == '"':
            quote = not quote
        if not quote:
            if ch in "([{":
                depth += 1
            elif ch in ")]}":
                depth -= 1
            elif ch == "," and depth == 0:
                out.append(cur.strip())
                cur = ""
                continue
        cur += ch
    if cur.strip():
        out.append(cur.strip())
    return out


def _string(value, resources, csharp=False):
    """The text of a string value, or None if the value is not a string."""
    value = value.strip()
    m = re.match(r'resources\.GetString\("([^"]+)"\)', value)
    if m:
        return resources.get(m.group(1), "")
    if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        inner = value[1:-1]
        if csharp:
            return inner.replace('\\"', '"').replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\t", " ").replace("\\\\", "\\")
        return inner.replace('""', '"')
    if csharp and len(value) >= 3 and value[:2] == '@"' and value[-1] == '"':
        return value[2:-1].replace('""', '"')
    return None


def _numbers(value):
    return [float(n) for n in re.findall(r"(?<![\w.])-?\d+(?:\.\d+)?", value)]


def _pair(value):
    """(x, y) out of New System.Drawing.Point(12, 34) or Size(100, 23)."""
    m = re.search(r"(?:Point|Size|SizeF)\((.*)\)", value)
    nums = _numbers(m.group(1)) if m else []
    return (int(round(nums[0])), int(round(nums[1]))) if len(nums) >= 2 else None


def _colour(value):
    m = re.search(r"Color\.FromArgb\((.*)\)", value)
    if m:
        nums = [int(n) for n in re.findall(r"\((\d+),\s*(?:System\.)?Byte\)", m.group(1))] or [int(n) for n in _numbers(m.group(1))]
        nums = [n for n in nums if 0 <= n <= 255]
        if len(nums) >= 3:
            r, g, b = nums[-3:]
            return f"#{r:02x}{g:02x}{b:02x}"
        return None
    m = re.search(r"SystemColors\.(\w+)", value)
    if m:
        return SYSTEM_COLOURS.get(m.group(1))
    m = re.search(r"Color\.(\w+)", value)
    if m and m.group(1) not in ("Transparent", "Empty"):
        return m.group(1).lower()
    return None


def _font(value):
    """(family, size in pixels, bold) out of New System.Drawing.Font("Arial", 9.75!, FontStyle.Bold, ...)."""
    m = re.search(r'Font\(\s*"([^"]+)"\s*,\s*([\d.]+)', value)
    if not m:
        return None
    return m.group(1), round(float(m.group(2)) * PT_TO_PX), "FontStyle.Bold" in value


def _shortcut(value):
    keys = re.findall(r"Keys\.(\w+)", value)
    keys = [k for k in keys if k != "Keys"]
    mods = [n for k, n in (("Control", "Ctrl"), ("Shift", "Shift"), ("Alt", "Alt")) if k in keys]
    main = [k for k in keys if k not in ("Control", "Shift", "Alt", "None")]
    if not main:
        return ""
    key = re.sub(r"^D(\d)$", r"\1", main[-1])
    return "+".join(mods + [key])


def _caption(text):
    """Windows marks a letter with & to underline it as a shortcut; && is a real ampersand."""
    return re.sub(r"&(?!&)", "", text or "").replace("&&", "&")


def _resources(designer):
    """Text that Visual Studio keeps in the .resx beside the form (when a form is marked as translatable)."""
    stem = re.sub(r"\.designer$", "", designer.stem, flags=re.I)
    resx = designer.with_name(stem + ".resx")
    out = {}
    try:
        for data in ET.parse(resx).getroot().iter("data"):
            value = data.find("value")
            if value is not None and "type" not in data.attrib and "mimetype" not in data.attrib:
                out[data.attrib.get("name", "")] = value.text or ""
    except (OSError, ET.ParseError):
        pass
    return out


class Form:
    """Everything the designer file says, sorted into: which components exist, their properties, who holds whom."""

    def __init__(self, designer_path):
        self.path = Path(designer_path)
        text = self.path.read_text(encoding="utf-8-sig", errors="replace")
        self.csharp = self.path.suffix.lower() == ".cs"
        self.resources = _resources(self.path)
        m = re.search(r"(?:Partial\s+Class|partial\s+class)\s+(\w+)", text)
        self.name = m.group(1) if m else re.sub(r"\W", "", self.path.name.split(".")[0]) or "Form1"
        self.types, self.props, self.form = {}, {}, {}
        self.children, self.items, self.cells = {}, {}, {}       # container -> [names], strip/menu -> [names], child -> (col,row)
        self.parent, self.events = {}, []                        # child -> container; (control, event, handler) from C#
        # the declarations name every control's type too, in case the way one was created is not recognised
        declared = dict(re.findall(r"(?:Friend|Private|Public|Protected)\s+WithEvents\s+(\w+)\s+As\s+(?:New\s+)?([\w.]+)", text))
        declared.update({n: t for t, n in re.findall(r"(?:private|internal|public|protected)\s+([\w.]+)\s+(\w+)\s*;", text)} if self.csharp else {})
        for st in _statements(text, self.csharp):
            self._read(st)
        for name, kind in declared.items():
            if name not in self.types and (name in self.props or name in self.parent) and not kind.startswith("System.ComponentModel"):
                self.types[name] = kind.split(".")[-1]
                self.props.setdefault(name, {})

    def _read(self, st):
        m = re.match(r"Me\.(\w+)\s*=\s*New\s+([\w.]+)\s*(?:\(.*)?$", st)      # older Visual Basic leaves the () off
        # (Me.ClientSize = New System.Drawing.Size(...) is a property of the form, not a new control)
        if m and m.group(1) != "components" and not m.group(2).startswith("System.Drawing"):
            self.types[m.group(1)] = m.group(2).split(".")[-1]
            self.props.setdefault(m.group(1), {})
            return
        m = re.match(r"Me\.(\w+)((?:\.Panel[12])?)\.Controls\.Add(Range)?\((.*)\)$", st)
        if m:
            holder = m.group(1) + m.group(2)
            names = re.findall(r"Me\.(\w+)", m.group(4))
            if not m.group(3) and names:                           # Add(Me.X, column, row) inside a table layout
                rest = _numbers(m.group(4).split(")", 1)[0].split(",", 1)[1]) if "," in m.group(4) else []
                if len(rest) >= 2:
                    self.cells[names[0]] = (int(rest[0]), int(rest[1]))
                names = names[:1]
            for n in names:
                self.children.setdefault(holder, []).append(n)
                self.parent[n] = holder
            return
        m = re.match(r"Me\.Controls\.Add(Range)?\((.*)\)$", st)
        if m:
            for n in re.findall(r"Me\.(\w+)", m.group(2)):
                self.children.setdefault("", []).append(n)
                self.parent[n] = ""
            return
        m = re.match(r"Me\.(\w+)\.(Items|DropDownItems|TabPages)\.Add(Range)?\((.*)\)$", st)
        if m:
            holder, kind, inner = m.group(1), m.group(2), m.group(4)
            names = re.findall(r"Me\.(\w+)", inner)
            if kind == "TabPages" or names:
                target = self.children if kind == "TabPages" else self.items
                for n in names:
                    target.setdefault(holder, []).append(n)
                    self.parent[n] = holder
            else:                                                  # a list of plain strings: a combo or list box
                brace = re.search(r"\{(.*)\}", inner)
                values = [_string(v, self.resources, self.csharp) for v in _split_args(brace.group(1) if brace else inner)]
                self.props.setdefault(holder, {}).setdefault("__items", []).extend(v for v in values if v is not None)
            return
        m = re.match(r"Me\.(\w+)\.(\w+)\s*\+=\s*New\s+[\w.]+\(Me\.(\w+)\)", st)      # C#: an event wired in the designer
        if m:
            self.events.append((m.group(1), m.group(2), m.group(3)))
            return
        m = re.match(r"Me\.(\w+)\s*\+=\s*New\s+[\w.]+\(Me\.(\w+)\)", st)
        if m:
            self.events.append(("", m.group(1), m.group(2)))
            return
        m = re.match(r"Me\.(\w+)\.(\w+)\s*=\s*(.+)$", st)
        if m and m.group(1) in self.types:
            self.props[m.group(1)][m.group(2)] = m.group(3)
            return
        m = re.match(r"Me\.(\w+)\s*=\s*(.+)$", st)
        if m:
            self.form[m.group(1)] = m.group(2)


# ---------------------------------------------------------------- the code beside the form
def _handlers(code_path, csharp, wired):
    """{(control, event): (handler name, its source lines)} and everything else in the file as a list of lines."""
    try:
        text = code_path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return {}, []
    lines = text.splitlines()
    found, used = {}, set()
    if csharp:
        by_name = {h: (c, e) for c, e, h in wired}
        i = 0
        while i < len(lines):
            m = re.match(r"\s*(?:private|protected|public|internal)?\s*(?:async\s+)?void\s+(\w+)\s*\(", lines[i])
            if m and m.group(1) in by_name:
                depth, j, seen = 0, i, False
                while j < len(lines):
                    depth += lines[j].count("{") - lines[j].count("}")
                    seen = seen or "{" in lines[j]
                    if seen and depth <= 0:
                        break
                    j += 1
                found[by_name[m.group(1)]] = (m.group(1), lines[i:j + 1])
                used.update(range(i, j + 1))
                i = j
            i += 1
    else:
        i = 0
        while i < len(lines):
            line, j = lines[i], i
            while line.rstrip().endswith(" _") and j + 1 < len(lines):      # a declaration can run over lines
                j += 1
                line = line.rstrip()[:-1] + lines[j].strip()
            m = re.match(r"\s*(?:\w+\s+)*Sub\s+(\w+)\s*\(.*\)\s*Handles\s+(.+)$", line, re.I)
            if m:
                end = j
                while end < len(lines) and not re.match(r"\s*End\s+Sub\b", lines[end], re.I):
                    end += 1
                for target in m.group(2).split(","):
                    target = target.strip()
                    if "." in target:
                        control, event = target.rsplit(".", 1)
                        control = "" if control.lower() in ("me", "mybase", "myclass") else control
                        found.setdefault((control, event), (m.group(1), lines[i:end + 1]))
                used.update(range(i, end + 1))
                i = end
            i += 1
    rest = [ln for n, ln in enumerate(lines) if n not in used]
    return found, rest


# ---------------------------------------------------------------- writing the Visualised form
class Writer:
    def __init__(self, form):
        self.f, self.out, self.scripts, self.notes = form, [], [], []
        self.unknown, self.silent, self.approx, self.loose = {}, [], {}, []
        code = form.path.with_name(re.sub(r"\.designer$", "", form.path.stem, flags=re.I) + form.path.suffix)
        self.code_path = code
        self.handlers, self.other_code = _handlers(code, form.csharp, form.events)
        self.language = "C#" if form.csharp else "Visual Basic"
        form_font = _font(form.form.get("Font", ""))
        self.base_font = form_font[1] if form_font else 11

    # -- small helpers
    def emit(self, kind, name, parent, props):
        self.out.append(f"@{kind} {name}")
        if parent:
            self.out.append(f"Parent={parent}")
        for key, value in props:
            if value is not None and value != "":
                self.out.append(f"{key}={str(value).replace(chr(13), '').replace(chr(10), ' ')}")
        self.out.append("")

    def text_of(self, name, key="Text"):
        value = self.f.props.get(name, {}).get(key)
        return _string(value, self.f.resources, self.f.csharp) if value is not None else None

    def look(self, name, into, kind):
        """Colours, font, enabled, visible: the properties every control shares."""
        p = self.f.props.get(name, {})
        if "BackColor" in p and _colour(p["BackColor"]):
            into.append(("Background", _colour(p["BackColor"])))
        if "ForeColor" in p and _colour(p["ForeColor"]):
            into.append(("Foreground", _colour(p["ForeColor"])))
        font = _font(p["Font"]) if "Font" in p else None
        if font:
            into += [("FontFamily", font[0]), ("FontSize", font[1])] + ([("FontWeight", "Bold")] if font[2] else [])
        elif kind != "MenuItem":
            # Windows Forms' standard text is 8.25 point (11 pixels), smaller than the default here: without this,
            # captions would be cut off by boxes that were sized for the smaller text.
            into.append(("FontSize", self.base_font))
        if kind == "TextBlock":
            align = re.search(r"ContentAlignment\.\w*?(Left|Center|Right)", p.get("TextAlign", ""))
            if align and align.group(1) != "Left":
                into.append(("TextAlignment", align.group(1)))
        if p.get("Enabled", "").strip() == "False":
            into.append(("IsEnabled", "false"))
        if p.get("Visible", "").strip() == "False":
            into.append(("IsVisible", "false"))
        anchor = self.anchor(p)
        if anchor and anchor != "Top,Left":
            into.append(("Anchor", anchor))

    @staticmethod
    def anchor(p):
        dock = re.search(r"DockStyle\.(\w+)", p.get("Dock", ""))
        if dock:
            return {"Fill": "Top,Bottom,Left,Right", "Top": "Top,Left,Right", "Bottom": "Bottom,Left,Right",
                    "Left": "Top,Bottom,Left", "Right": "Top,Bottom,Right"}.get(dock.group(1), "")
        if "Anchor" not in p:
            return ""
        sides = [s for s in ("Top", "Bottom", "Left", "Right") if re.search(rf"AnchorStyles\.{s}\b", p["Anchor"])]
        return ",".join(sides)

    def script(self, name, target_kind, event, handler):
        """Carry one event handler across as a script: the original code, kept as comments."""
        func, lines = handler
        script = f"{name or self.f.name}_{event}"
        body = [f"-- Imported from {self.code_path.name}: the original {self.language}, kept here for reference.",
                "-- It does not run. Write what this should do below, in Lua (or change the script's language).", "--"]
        indent = min((len(ln) - len(ln.lstrip()) for ln in lines if ln.strip()), default=0)      # keep its shape, lose the margin
        body += ["--   " + ln[indent:].rstrip() if ln.strip() else "--" for ln in lines]
        self.scripts.append((script, body))
        return script

    def wire(self, name, kind, into):
        """Attach the handlers this control had, where Visualised has the matching event."""
        for (control, event), handler in list(self.handlers.items()):
            if control != name:
                continue
            ours = EVENTS.get(event)
            if kind == "TextBlock" and event == "Click":
                ours = "OnPointerPressed"
            if ours and ours in SUPPORTS.get(kind, ()) and not any(k == ours for k, _ in into):
                into.append((ours, self.script(name, kind, ours, handler)))
            else:
                self.loose.append(f"{name or 'the form'}.{event}")
                self.script(name, kind, event, handler)
            del self.handlers[(control, event)]

    # -- geometry
    def box(self, name):
        p = self.f.props.get(name, {})
        loc = _pair(p["Location"]) if "Location" in p else (0, 0)
        size = _pair(p["Size"]) if "Size" in p else None
        return (loc or (0, 0)), size

    def table_cell(self, holder, child, size):
        """Where a control sits inside a table layout: the table is split into equal cells."""
        p = self.f.props.get(holder, {})
        cols = max(1, int((_numbers(p.get("ColumnCount", "1")) or [1])[0]))
        rows = max(1, int((_numbers(p.get("RowCount", "1")) or [1])[0]))
        _, tsize = self.box(holder)
        tw, th = tsize or (cols * 100, rows * 30)
        order = self.f.children.get(holder, [])
        col, row = self.f.cells.get(child, (order.index(child) % cols, order.index(child) // cols))
        cw, ch = tw / cols, th / rows
        w, h = size or (int(cw) - 6, int(ch) - 6)
        return (int(col * cw + max(3, (cw - w) / 2)), int(row * ch + max(3, (ch - h) / 2))), (min(w, int(cw) - 6), min(h, int(ch) - 6))

    # -- controls
    def control(self, name, parent_vml, origin=(0, 0), holder=""):
        kind_wf = self.f.types.get(name, "")
        if kind_wf in STRIPS:
            return
        loc, size = self.box(name)
        holder_kind = self.f.types.get(holder.split(".")[0], "")
        if holder_kind == "TableLayoutPanel":
            loc, size = self.table_cell(holder, name, size)
        elif holder_kind == "TabControl":                          # a page fills its tab control, below the tabs
            _, tsize = self.box(holder)
            loc, size = (0, 22), ((tsize[0], tsize[1] - 22) if tsize else size)
        x, y = loc[0] + origin[0], loc[1] + origin[1]
        vml, text_prop, approx = CONTROLS.get(kind_wf, ("Frame", "Text", None))
        p = self.f.props.get(name, {})
        props = [("Canvas.Left", x), ("Canvas.Top", y)]
        auto = p.get("AutoSize", "").strip() == "True"
        if size and not (auto and vml in ("TextBlock", "CheckBox")):
            props += [("Width", size[0]), ("Height", size[1])]
        if approx:
            self.approx.setdefault(approx, []).append(name)

        if kind_wf not in CONTROLS:                                # nothing like it yet: a labelled frame, same size
            self.unknown.setdefault(kind_wf or "unknown", []).append(name)
            props += [("Text", f"{kind_wf}: {name}"), ("Background", "#fafafa"), ("BorderBrush", "#9ca3af"), ("BorderThickness", 1)]
        elif text_prop:
            text = self.text_of(name)
            if text is not None:
                props.append((text_prop, _caption(text) if vml in ("Button", "CheckBox", "TextBlock", "Frame") else text))
        if vml == "TextBox":
            if p.get("Multiline", "").strip() == "True" or kind_wf == "RichTextBox":
                props.append(("AcceptsReturn", "true"))
            if p.get("ReadOnly", "").strip() == "True":
                props.append(("IsReadOnly", "true"))
            if "PasswordChar" in p or p.get("UseSystemPasswordChar", "").strip() == "True":
                self.approx.setdefault("a password box shows what is typed (no hidden-text box yet)", []).append(name)
        if vml in ("ComboBox", "ListBox") and p.get("__items"):
            props.append(("Items", ",".join(i.replace(",", " ") for i in p["__items"])))
        if vml == "CheckBox" and p.get("Checked", "").strip() == "True":
            props.append(("IsChecked", "true"))
        if vml == "TextBlock" and size and not auto:
            props.append(("TextWrapping", "Wrap"))
        if kind_wf == "Panel" and "BorderStyle" in p and "None" not in p["BorderStyle"]:
            props += [("BorderBrush", "#9ca3af"), ("BorderThickness", 1)]
        if kind_wf == "TabPage" and self.f.children.get(holder, [name])[0] != name:
            props.append(("IsVisible", "false"))                   # only the first page of a tab control shows
        self.look(name, props, vml)
        self.wire(name, vml, props)
        self.emit(vml, name, parent_vml, props)

        if kind_wf == "TabControl":
            pages = self.f.children.get(name, [])
            if len(pages) > 1:
                self.notes.append(f"{name} has {len(pages)} tabs: each became a frame, and only the first ({pages[0]}) is "
                                  "showing. The others are there, hidden: set IsVisible on them to see them.")
        if kind_wf == "SplitContainer":
            self.split(name, size)
        else:
            self.inside(name, name)

    def inside(self, holder, parent_vml, origin=(0, 0)):
        """A container's controls. Windows Forms lists the front-most first; a canvas draws the last on top."""
        for child in reversed(self.f.children.get(holder, [])):
            self.control(child, parent_vml, origin, holder)

    def split(self, name, size):
        p = self.f.props.get(name, {})
        w, h = size or (400, 300)
        dist = int((_numbers(p.get("SplitterDistance", "")) or [w // 2])[0])
        across = "Horizontal" in p.get("Orientation", "")
        self.inside(name + ".Panel1", name, (0, 0))
        self.inside(name + ".Panel2", name, (0, dist + 4) if across else (dist + 4, 0))

    # -- menus
    def menu(self, strip, parent_vml):
        def walk(item, parent):
            kind = self.f.types.get(item, "")
            props = []
            if kind == "ToolStripSeparator":
                props.append(("IsSeparator", "true"))
            else:
                props.append(("Text", _caption(self.text_of(item) or item)))
                keys = _shortcut(self.f.props.get(item, {}).get("ShortcutKeys", ""))
                if keys:
                    props.append(("Shortcut", keys))
                if self.f.props.get(item, {}).get("Enabled", "").strip() == "False":
                    props.append(("IsEnabled", "false"))
                self.wire(item, "MenuItem", props)
            self.emit("MenuItem", item, parent, props)
            for sub in self.f.items.get(item, []):
                walk(sub, item)
        for item in self.f.items.get(strip, []):
            walk(item, parent_vml)

    # -- the whole form
    def build(self):
        f = self.f
        if not f.types and not f.form:
            raise ValueError("no form was found in that file (it has no InitializeComponent)")
        client = _pair(f.form.get("ClientSize", "")) or _pair(f.form.get("Size", "")) or (640, 480)
        # the form's menu bar: normally straight on the form, sometimes tucked inside a panel at the top
        on_form = [n for n, t in f.types.items() if t == "MenuStrip" and f.parent.get(n, "") == ""]
        menus = on_form + [n for n, t in f.types.items() if t == "MenuStrip" and n not in on_form]
        status = [n for n, t in f.types.items() if t == "StatusStrip"]
        tools = [n for n, t in f.types.items() if t == "ToolStrip"]
        top = MENU_BAR if on_form else 0
        title = _string(f.form.get("Text", ""), f.resources, f.csharp)
        win = [("Title", title if title is not None else f.name), ("Width", client[0]), ("Height", client[1] - top + (19 if menus else 0))]
        if re.search(r"FormBorderStyle\.(Fixed|None)", f.form.get("FormBorderStyle", "")):
            win.append(("Resizable", "false"))
        self.wire("", "Window", win)
        self.out.append(f"# {f.name}: imported from {f.path.name} (Windows Forms, {self.language})")
        self.out.append("")
        self.emit("Window", f.name, "", win)
        canvas = f"{f.name}Canvas"
        background = _colour(f.form.get("BackColor", "")) or "#f0f0f0"
        if menus:
            root = f"{f.name}Root"
            self.emit("DockPanel", root, f.name, [])
            self.emit("TinyMenu", f"{f.name}Menu", root, [("DockPanel.Dock", "Top")])
            self.emit("Canvas", canvas, root, [("Background", background)])
            self.menu(menus[0], "MenuBar")
        else:
            self.emit("Canvas", canvas, f.name, [("Background", background)])
        self.inside("", canvas, (0, -top))
        for strip in status:                                       # a status bar: a strip along the bottom with its text
            loc, size = self.box(strip)
            h = (size or (0, 22))[1]
            self.emit("Frame", strip, canvas, [("Canvas.Left", 0), ("Canvas.Top", client[1] - top - h), ("Width", client[0]),
                                               ("Height", h), ("Background", "#f0f0f0"), ("Anchor", "Bottom,Left,Right")])
            x = 6
            for item in f.items.get(strip, []):
                text = _caption(self.text_of(item) or "")
                if text:
                    self.emit("TextBlock", item, strip, [("Canvas.Left", x), ("Canvas.Top", 3), ("Text", text), ("FontSize", self.base_font)])
                    x += max(60, 7 * len(text) + 16)
        for name, kind in f.types.items():                         # right-click menus
            if kind == "ContextMenuStrip":
                self.emit("ContextMenu", name, "", [])
                self.menu(name, name)
        self.report(menus, tools)
        for name, body in self.scripts:
            tag = "END_" + re.sub(r"\W", "_", name).upper()
            self.out += [f"@Script {name}", "Interpreter=lua", f"<<{tag}"] + body + [tag, ""]
        return "\n".join(self.out), self.notes

    def report(self, menus, tools):
        f = self.f
        placed = set(f.parent) | {""}
        counts = {}
        for n, t in f.types.items():
            if n in f.parent and t not in STRIP_ITEMS and t not in STRIPS:
                counts[t] = counts.get(t, 0) + 1
        made = sum(counts.values())
        summary = f"{f.name}: {made} control{'s' if made != 1 else ''} brought across"
        items = sum(1 for t in f.types.values() if t == "ToolStripMenuItem")
        if items:
            summary += f", and {items} menu item{'s' if items != 1 else ''}"
        head = [summary + "."]
        for kind, names in sorted(self.unknown.items()):
            head.append(f"No equal yet for {kind}: {', '.join(names)} "
                        f"{'is' if len(names) == 1 else 'are'} shown as a labelled frame of the same size.")
        for why, names in sorted(self.approx.items()):
            head.append(f"{', '.join(names)}: {why}.")
        if len(menus) > 1:
            head.append(f"The form has {len(menus)} menu bars; the first ({menus[0]}) was used.")
        if tools:
            head.append(f"Toolbars are not brought across yet: {', '.join(tools)}.")
        behind = [n for n, t in f.types.items() if n not in f.parent and t not in STRIPS and t not in STRIP_ITEMS]
        if behind:
            head.append("Not on the form itself, so not brought across (timers, dialogs and the like): "
                        + ", ".join(f"{n} ({f.types[n]})" for n in behind) + ".")
        if self.scripts:
            head.append(f"{len(self.scripts)} event handler{'s' if len(self.scripts) != 1 else ''} from {self.code_path.name} "
                        f"came across as scripts. The {self.language} is kept as comments for reference; it does not run.")
        elif not self.code_path.is_file():
            head.append(f"The code file ({self.code_path.name}) wasn't beside the designer file, so no event code was brought across.")
        if self.loose:
            head.append("Kept as scripts but not attached, because there is no matching event here yet: " + ", ".join(self.loose) + ".")
        left = sorted(f"{c or 'the form'}.{e}" for c, e in self.handlers)
        if left:
            head.append("Handlers for things that were not brought across were left behind: " + ", ".join(left) + ".")
        if any(ln.strip() for ln in self.other_code):
            n = sum(1 for ln in self.other_code if ln.strip())
            head.append(f"{n} other lines of code in {self.code_path.name} (helpers, variables) are not in the form; "
                        "the original file is untouched.")
        self.notes = head + self.notes


def convert(designer_path):
    """Turn a Windows Forms designer file into a Visualised canvas form. Returns (vml text, list of notes)."""
    return Writer(Form(designer_path)).build()


def designer_file_for(path):
    """Given any of a form's files (frmX.vb, frmX.Designer.vb, frmX.resx), the designer file to read."""
    p = Path(path)
    if re.search(r"\.designer\.(vb|cs)$", p.name, re.I):
        return p
    for ext in (".vb", ".cs"):
        for name in (f"{p.stem}.Designer{ext}", f"{p.stem}.designer{ext}"):
            if p.with_name(name).is_file():
                return p.with_name(name)
    return p
