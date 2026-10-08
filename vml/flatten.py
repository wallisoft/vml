"""Open a form laid out with panels as a canvas form the designer can edit.

Nobody has to understand the panels. The form is built once for real, off screen, and every control is measured where
the layout put it; then it is measured again a little larger, and how each control moved or stretched says which
edges it is anchored to. Panels that only arrange things disappear. A panel you can see (a background or a border),
one a script mentions by name, or one that starts hidden becomes a Frame holding its controls, so scripts that show
and hide it keep working. The file on disk is never touched: this is a one-way conversion into a new canvas form."""
import re
from collections import defaultdict
from pathlib import Path

from PySide6.QtCore import QPoint, Qt

PANELS = {"StackPanel", "Grid", "DockPanel", "Border", "Canvas", "ScrollViewer"}
NOT_PLACED = {"MenuItem", "ContextMenu", "MenuTheme", "TinyMenu"}
# what only means something to a layout panel, or is replaced by the measured position and size
DROPPED = {"DockPanel.Dock", "Grid.Row", "Grid.Column", "Grid.RowSpan", "Grid.ColumnSpan", "HorizontalAlignment",
           "VerticalAlignment", "Margin", "Canvas.Left", "Canvas.Top", "X", "Y", "Width", "Height", "Anchor",
           "MinWidth", "MinHeight", "MaxWidth", "MaxHeight"}
PANEL_ONLY = {"Padding", "Orientation", "Spacing", "LastChildFill", "ColumnDefinitions", "RowDefinitions"}
GROW = (120, 80)


def _settle(eng):
    for _ in range(8):
        eng.app.processEvents()


def _snapshot(eng, win):
    """name -> (x, y, w, h, natural w, natural h) in window coordinates, for every control in the window."""
    out, hidden = {}, []

    def measure(n):
        p = n.widget.mapTo(win.widget, QPoint(0, 0))
        hint = n.widget.sizeHint()
        out[n.name] = (p.x(), p.y(), n.widget.width(), n.widget.height(), hint.width(), hint.height())

    def walk(n):
        for k in n.children:
            if k.host is not k.widget and k.host.isHidden():
                hidden.append(k)
                continue
            measure(k)
            walk(k)

    walk(win)
    for h in list(hidden):                     # controls that start hidden: show each briefly to see where it goes
        h.host.setVisible(True)
        _settle(eng)
        measure(h)
        walk(h)
        h.host.setVisible(False)
        _settle(eng)
    return out, {h.name for h in hidden}


def _anchor(a, b, pa, pb):
    """Which edges of its container (pa at the first size, pb at the second) a control at a, then b, follows."""
    def axis(i):
        grow = pb[i + 2] - pa[i + 2]
        if grow < 8:
            return (True, False)
        near = (b[i] - pb[i]) - (a[i] - pa[i])                                     # how far its near edge moved
        far = (b[i] - pb[i] + b[i + 2]) - (a[i] - pa[i] + a[i + 2])                # and its far edge
        return (near < grow / 2, far > grow / 2)
    (left, right), (top, bottom) = axis(0), axis(1)
    v = ["Top"] if top or not bottom else []
    v += ["Bottom"] if bottom else []
    h = ["Left"] if left or not right else []
    h += ["Right"] if right else []
    partial = any(8 <= abs(d) < g - 8 for d, g in (
        ((b[0] - pb[0]) - (a[0] - pa[0]), pb[2] - pa[2]), (b[2] - a[2], pb[2] - pa[2]),
        ((b[1] - pb[1]) - (a[1] - pa[1]), pb[3] - pa[3]), (b[3] - a[3], pb[3] - pa[3])) if g >= 8)
    return ",".join(v + h), partial


def _forget(eng, path, win):
    """Take the measuring copy of a form back out of the engine.

    This is a function, not lines in the `finally` that calls it, on purpose: Nuitka (which compiles Visualised)
    crashes on a list built inside a `finally` block that an early `return` also has to run.
    """
    if win is not None:
        win.widget.hide()
    roots = [n for n in list(eng.scopes.get(path, {}).values()) if n.parent is None]
    for n in roots:
        eng.delete(n.name, path)
    eng.scopes.pop(path, None)
    eng.luas.pop(path, None)
    getattr(eng, "themes", {}).pop(path, None)


def layout_to_canvas(eng, path, rows, props, scripts, window, log=print):
    """(rows, props, canvas row, notes) describing the same form on a canvas, or None if it can't be measured."""
    # Measured from a copy beside the original (so pictures and other forms it refers to are still found). That way
    # a form that is running right now can be opened too, the designer's own form included.
    src = Path(path).expanduser().resolve()
    copy = src.with_name(f".{src.stem}.measuring.vml")
    try:
        copy.write_bytes(src.read_bytes())
    except OSError:
        import tempfile
        copy = Path(tempfile.gettempdir()) / f"{src.stem}.measuring.vml"
        copy.write_bytes(src.read_bytes())
    path = str(copy.resolve())
    try:
        eng.load(path, show=False)
    finally:
        copy.unlink(missing_ok=True)
    win = next((n for n in eng.scopes.get(path, {}).values() if n.type.name == "Window" and n.parent is None), None)
    try:
        if win is None:
            return None
        w = win.widget
        w.setAttribute(Qt.WA_DontShowOnScreen, True)
        w.resize(w.size().expandedTo(w.minimumSizeHint()))
        w.show()
        _settle(eng)
        w.resize(w.size().expandedTo(w.minimumSizeHint()))       # the engine grows a window to fit its content
        _settle(eng)
        size_a = (w.width(), w.height())
        a, hidden = _snapshot(eng, win)
        resizable = str(props[window[0]].get("Resizable", "true")).lower() != "false"
        b, size_b = a, size_a
        if resizable:
            w.resize(size_a[0] + GROW[0], size_a[1] + GROW[1])
            _settle(eng)
            size_b = (w.width(), w.height())
            b, _ = _snapshot(eng, win)
        window_bg = w.palette().window().color().name()
    finally:
        _forget(eng, path, win)             # in a function of its own: see _forget

    kids = defaultdict(list)
    for r in rows:
        kids[r[1]].append(r)
    code = "\n".join(str(c) for _, c in scripts.values())
    named = lambda n: f'"{n}"' in code or f"'{n}'" in code       # a script that addresses it: Vml("SetProperty", "JobBar", ...)
    menu = next((a[r[3]] for r in rows if r[2] == "TinyMenu" and r[3] in a), None)
    top = menu[1] + menu[3] if menu and menu[1] + menu[3] < size_a[1] / 2 else 0
    form_a, form_b = (0, top, size_a[0], size_a[1] - top), (0, top, size_b[0], size_b[1] - top)

    canvas_id = max(r[0] for r in rows) + 1
    new_rows, new_props, gone = {}, {cid: dict(p) for cid, p in props.items()}, set()
    notes = {"frames": 0, "dissolved": 0, "controls": 0, "partial": [], "hidden": sorted(hidden), "scroll": []}

    def keep_panel(cid, name):
        p = props[cid]
        return bool(p.get("Background") or p.get("BorderBrush") or name in hidden or named(name)
                    or any(v in scripts for k, v in p.items() if k.startswith("On")))

    def place(row, parent_id, pa, pb):
        cid, _pid, ctype, name = row
        if ctype in NOT_PLACED:
            return
        if name not in a or name not in b:
            gone.add(cid)
            return
        is_panel = ctype in PANELS
        if is_panel and not keep_panel(cid, name):
            gone.add(cid)
            notes["dissolved"] += 1
            if ctype == "ScrollViewer":
                notes["scroll"].append(name)
            for k in kids[cid]:
                place(k, parent_id, pa, pb)
            return
        ra, rb, old = a[name], b[name], props[cid]
        p = {k: v for k, v in old.items() if k not in DROPPED and not (is_panel and k in PANEL_ONLY)}
        p["Canvas.Left"], p["Canvas.Top"] = str(ra[0] - pa[0]), str(ra[1] - pa[1])
        anchor, partial = _anchor(ra, rb, pa, pb)
        if partial:
            notes["partial"].append(name)
        if is_panel or old.get("Width") or abs(ra[2] - ra[4]) > 2 or ("Left" in anchor and "Right" in anchor):
            p["Width"] = str(ra[2])
        if is_panel or old.get("Height") or abs(ra[3] - ra[5]) > 2 or ("Top" in anchor and "Bottom" in anchor):
            p["Height"] = str(ra[3])
        if anchor != "Top,Left":
            p["Anchor"] = anchor
        if is_panel:
            if not old.get("BorderBrush"):
                p["BorderThickness"] = "0"
            notes["frames"] += 1
            for k in kids[cid]:
                place(k, cid, ra, rb)
        else:
            notes["controls"] += 1
        new_rows[cid] = (cid, parent_id, "Frame" if is_panel else ctype, name)
        new_props[cid] = p

    for r in kids[window[0]]:
        place(r, canvas_id, form_a, form_b)
    out = [new_rows.get(r[0], r) for r in rows if r[0] not in gone]
    canvas = (canvas_id, window[0], "Canvas", window[3] + "Canvas")
    out.append(canvas)
    wp = props[window[0]]
    new_props[canvas_id] = {"Background": wp.get("Background") or window_bg}
    new_props[window[0]] = dict(wp, Width=str(size_a[0]), Height=str(size_a[1]))
    return out, new_props, canvas, notes
