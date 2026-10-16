"""
Styles: CSS on any control, and shared styles a form's controls can share.

    @Style pill                            a shared style (any number of them, anywhere in the form)
    <<CSS
    background: #FFFFFF; border: 1.5px solid #DDD6FE; border-radius: 17px
    :hover { background: #F5F3FF }
    :pressed { background: #EDE9FE }
    CSS

    @Button btnGo
    Class=pill big                         one or more shared styles, applied in that order
    Style=box-shadow: 0 4px 12px #0003     CSS for this control alone (one line; :hover { ... } blocks too)

Order, last wins: the control's ordinary properties (Background, CornerRadius...), then its Class styles, then its
Style. States: :hover, :pressed (also :active), :focus, :disabled, :checked.

On the web (pages, phones) the CSS is used as written: everything CSS can do. On the desktop it becomes a Qt style
sheet, which covers colours, gradients (linear-gradient is converted), borders, rounded corners, padding, margins,
fonts and the states; box-shadow becomes a drop shadow. Anything else (transitions, transforms, animations...) is
web only, and the log says so once.
"""
import math
import re

STATES = {"hover": "hover", "pressed": "pressed", "active": "pressed", "focus": "focus", "disabled": "disabled",
          "checked": "checked"}
WEB_STATE = {"hover": ":hover", "pressed": ":active", "focus": ":focus-within", "disabled": ":disabled",
             "checked": ":has(input:checked)"}
QT_STATE = {"hover": ":hover", "pressed": ":pressed", "focus": ":focus", "disabled": ":disabled", "checked": ":checked"}

# what a Qt style sheet understands (the rest is web only)
QT_PROPS = {
    "background", "background-color", "color", "border", "border-color", "border-style", "border-width", "border-radius",
    "border-top", "border-right", "border-bottom", "border-left",
    "border-top-color", "border-right-color", "border-bottom-color", "border-left-color",
    "border-top-width", "border-right-width", "border-bottom-width", "border-left-width",
    "border-top-left-radius", "border-top-right-radius", "border-bottom-left-radius", "border-bottom-right-radius",
    "padding", "padding-top", "padding-right", "padding-bottom", "padding-left",
    "margin", "margin-top", "margin-right", "margin-bottom", "margin-left",
    "font", "font-family", "font-size", "font-style", "font-weight", "text-decoration", "outline",
    "min-width", "min-height", "max-width", "max-height", "selection-color", "selection-background-color",
}


def _split(text, sep=","):
    """Split at sep, but not inside brackets: "a, rgb(1,2,3), b" -> three parts."""
    out, depth, cur = [], 0, ""
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        if ch == sep and depth == 0:
            out.append(cur)
            cur = ""
        else:
            cur += ch
    out.append(cur)
    return [p.strip() for p in out if p.strip()]


def parse(text):
    """CSS declarations, with :state { ... } blocks -> {"": [(prop, value)...], "hover": [...], ...}."""
    text = re.sub(r"/\*.*?\*/", "", str(text or ""), flags=re.S)
    sheet = {}
    def add(state, body):
        for decl in _split(body, ";"):
            if ":" not in decl:
                continue
            prop, value = decl.split(":", 1)
            prop, value = prop.strip().lower(), value.strip()
            if prop and value and re.match(r"^-?[a-z][a-z0-9-]*$", prop):
                sheet.setdefault(state, []).append((prop, value))
    base = ""
    pos = 0
    for m in re.finditer(r":([a-zA-Z-]+)\s*\{([^}]*)\}", text):
        base += text[pos:m.start()] + ";"
        pos = m.end()
        state = STATES.get(m.group(1).lower())
        if state:
            add(state, m.group(2))
    base += text[pos:]
    add("", base)
    return sheet


NAMED = {"black": (0, 0, 0), "white": (255, 255, 255), "red": (255, 0, 0), "blue": (0, 0, 255), "green": (0, 128, 0),
         "gray": (128, 128, 128), "grey": (128, 128, 128), "purple": (128, 0, 128), "orange": (255, 165, 0)}


def shadow_level(level, tint=""):
    """Shadow=0..10 (and ShadowColour) -> a box-shadow: 0 none, 1 a hairline lift, 10 floating well clear."""
    try:
        n = max(0, min(10, int(round(float(level or 0)))))
    except ValueError:
        n = 0
    if not n:
        return ""
    t = str(tint or "").strip().lstrip("#")
    if len(t) == 8:                                     # (Avalonia's #aarrggbb: the colour, not its alpha)
        t = t[2:]
    if len(t) == 3:
        t = "".join(c * 2 for c in t)
    try:
        r, g, b = (int(t[i:i + 2], 16) for i in (0, 2, 4)) if len(t) == 6 else NAMED.get(t.lower(), (0, 0, 0))
    except ValueError:
        r, g, b = 0, 0, 0
    tinted = (r, g, b) != (0, 0, 0)
    alpha = (0.18 if tinted else 0.10) + n * (0.03 if tinted else 0.017)
    return f"0 {round(n * 1.6)}px {round(n * 3.6)}px rgba({r},{g},{b},{alpha:.2f})"


def merge(*sheets):
    """Later sheets win, property by property and state by state. -> {state: {prop: value}} (order kept)."""
    out = {}
    for sheet in sheets:
        for state, decls in (sheet or {}).items():
            d = out.setdefault(state, {})
            for prop, value in (decls.items() if isinstance(decls, dict) else decls):
                d.pop(prop, None)                   # (moved to the end: the latest one is the one that counts)
                d[prop] = value
    return out


def classes(value):
    return [c for c in re.split(r"[\s,]+", str(value or "")) if c]


# ---------------------------------------------------------------- the web

def web_declarations(decls, important=False):
    tail = " !important" if important else ""
    return ";".join(f"{p}:{v}{tail}" for p, v in decls.items())


def web_rules(selector, merged):
    """The state rules for one control (its base goes inline, where it beats the page's own styles)."""
    rules = []
    for state, decls in merged.items():
        if state and decls and state in WEB_STATE:
            rules.append(f"{selector}{WEB_STATE[state]}{{{web_declarations(decls, important=True)}}}")
    return "\n".join(rules)


# ---------------------------------------------------------------- the desktop (Qt)

def _qt_colour(value):
    """CSS's #RGBA and #RRGGBBAA mean something else to Qt (which reads #AARRGGBB): write them as rgba()."""
    def fix(m):
        h = m.group(1)
        if len(h) == 4:
            h = "".join(c * 2 for c in h)
        r, g, b, a = (int(h[i:i + 2], 16) for i in (0, 2, 4, 6))
        return f"rgba({r},{g},{b},{a})"
    value = re.sub(r"#([0-9a-fA-F]{8}|[0-9a-fA-F]{4})\b", fix, value)
    # rgba(r,g,b,0.5): CSS alpha is 0..1 (or a %), Qt's 0..255
    def alpha(m):
        parts = [p.strip() for p in m.group(1).split(",")]
        if len(parts) == 4:
            a = parts[3]
            try:
                if a.endswith("%"):
                    parts[3] = str(round(float(a[:-1]) * 2.55))
                elif "." in a or a in ("0", "1"):
                    parts[3] = str(round(float(a) * 255))
            except ValueError:
                pass
        return f"rgba({','.join(parts)})"
    return re.sub(r"rgba\(([^)]*)\)", alpha, value)


def _qt_gradient(value):
    """linear-gradient(...) -> qlineargradient(...): direction words or an angle, colour stops with or without %."""
    m = re.match(r"^\s*linear-gradient\((.*)\)\s*$", value, re.S)
    if not m:
        return None
    parts = _split(m.group(1))
    angle = 180.0
    words = {"to top": 0, "to right": 90, "to bottom": 180, "to left": 270, "to top right": 45, "to right top": 45,
             "to bottom right": 135, "to right bottom": 135, "to bottom left": 225, "to left bottom": 225,
             "to top left": 315, "to left top": 315}
    if parts and (parts[0].lower() in words or re.match(r"^-?[\d.]+(deg|turn|rad)$", parts[0].lower())):
        d = parts.pop(0).lower()
        if d in words:
            angle = words[d]
        elif d.endswith("deg"):
            angle = float(d[:-3])
        elif d.endswith("turn"):
            angle = float(d[:-4]) * 360
        else:
            angle = math.degrees(float(d[:-3]))
    if len(parts) < 2:
        return None
    rad = math.radians(angle)
    dx, dy = math.sin(rad), -math.cos(rad)
    x1, y1, x2, y2 = 0.5 - dx / 2, 0.5 - dy / 2, 0.5 + dx / 2, 0.5 + dy / 2
    stops = []
    for i, p in enumerate(parts):
        m2 = re.match(r"^(.*?)\s+(-?[\d.]+)%$", p)
        colour, at = (m2.group(1), float(m2.group(2)) / 100) if m2 else (p, i / (len(parts) - 1))
        stops.append(f"stop:{max(0.0, min(1.0, at)):.3g} {_qt_colour(colour.strip())}")
    return f"qlineargradient(x1:{x1:.3g}, y1:{y1:.3g}, x2:{x2:.3g}, y2:{y2:.3g}, {', '.join(stops)})"


def _qt_value(prop, value):
    if prop in ("background", "background-color") and "gradient(" in value:
        g = _qt_gradient(value)
        return g, g is None
    return _qt_colour(value), False


def shadow(value):
    """box-shadow: "x y [blur] [spread] colour" (the first shadow only) -> (x, y, blur, colour) or None."""
    if not value or value.strip().lower() == "none":
        return None
    first = _split(value)[0]
    if "inset" in first:
        return None
    nums = [float(n) for n in re.findall(r"(?<![\w#.])(-?[\d.]+)(?:px)?(?![\w%])", re.sub(r"#\w+|rgba?\([^)]*\)|[a-z]+\([^)]*\)", "", first))]
    cm = re.search(r"(#[0-9a-fA-F]{3,8}|rgba?\([^)]*\)|\b[a-z]+\b)\s*$", first)
    colour = cm.group(1) if cm else "rgba(0,0,0,64)"
    if len(nums) < 2:
        return None
    return nums[0], nums[1], nums[2] if len(nums) > 2 else 0.0, _qt_colour(colour)


def qt_sheet(selector, merged):
    """-> (style sheet, shadow or None, [what was left out as web only])."""
    sheet, left_out = [], []
    drop = None
    for state, decls in merged.items():
        if state and state not in QT_STATE:
            continue
        lines = []
        for prop, value in decls.items():
            value = str(value)                              # (a size from FontSize=12 arrives as a number)
            if prop == "box-shadow":
                if state == "":
                    drop = shadow(value)
                else:
                    left_out.append(f":{state} box-shadow")
                continue
            if prop not in QT_PROPS:
                left_out.append(prop if not state else f":{state} {prop}")
                continue
            v, bad = _qt_value(prop, value)
            if bad:
                left_out.append(f"{prop}: {value}")
                continue
            lines.append(f"{prop}: {v};")
        if lines:
            sheet.append(f"{selector}{QT_STATE.get(state, '')} {{ {' '.join(lines)} }}")
    return " ".join(sheet), drop, left_out
