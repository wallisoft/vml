"""
The reference half of the help: every control with its properties and events, every Vml() command, and the vml
command line, written as wiki pages straight from the engine, so it can't fall behind it.

    QT_QPA_PLATFORM=offscreen python3 tools/make_reference.py OUTDIR

Writes OUTDIR/Reference.md, Reference-Controls.md, Reference-Commands.md and Reference-Command-Line.md. A property's
description is the comment on its line in vml/registry.py (or vml/design.py); a command's is its docstring.
"""
import inspect
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication(sys.argv)

from vml import __version__  # noqa: E402
__version__ = os.environ.get("VML_VERSION") or __version__      # (VML_VERSION=1.3.0: the release these pages are for)
from vml.engine import Engine  # noqa: E402
from vml.registry import COMMON, REGISTRY  # noqa: E402

HIDE_CONTROLS = {"DesignSurface", "PropertyGrid"}             # the designer's own
KINDS = {"text": "text", "number": "number", "bool": "true/false", "colour": "colour", "choice": "choice",
         "thickness": "thickness", "list": "list", "slider": "number (slider)"}


# What a property does, where its line in the source has no comment to say so (a comment there wins).
DESCRIBE = {
    "Name": "The control's name: how scripts refer to it.",
    "Text": "The text shown (or typed, in a TextBox).",
    "Content": "What a button or check box says.",
    "Header": "The heading text.",
    "Title": "The window's title.",
    "Width": "Its width, in pixels.", "Height": "Its height, in pixels.",
    "MinWidth": "The narrowest it can be, in pixels.", "MinHeight": "The shortest it can be, in pixels.",
    "MaxWidth": "The widest it can be, in pixels.", "MaxHeight": "The tallest it can be, in pixels.",
    "X": "Where it is now, from the left, in pixels (read only).", "Y": "Where it is now, from the top, in pixels (read only).",
    "Canvas.Left": "Its place on a Canvas: pixels from the left.", "Canvas.Top": "Its place on a Canvas: pixels from the top.",
    "Anchor": "The Canvas edges it keeps its distance from as the form is resized: anchored to both sides, it stretches.",
    "Margin": "Space outside it: one number, or left,top,right,bottom.",
    "Padding": "Space inside it, between its edge and what it holds: one number, or left,top,right,bottom.",
    "HorizontalAlignment": "Where it sits across a panel's space.", "VerticalAlignment": "Where it sits up and down a panel's space.",
    "DockPanel.Dock": "The side of a DockPanel it docks to.",
    "Grid.Row": "Its row in a Grid, from 0.", "Grid.Column": "Its column in a Grid, from 0.",
    "Grid.RowSpan": "How many Grid rows it spans.", "Grid.ColumnSpan": "How many Grid columns it spans.",
    "ColumnDefinitions": "A Grid's columns, comma-separated.", "RowDefinitions": "A Grid's rows, comma-separated.",
    "LastChildFill": "The last control fills the space that's left.",
    "Orientation": "Vertical or Horizontal.", "Spacing": "The gap between the controls it holds, in pixels.",
    "FontSize": "Text size, in pixels.", "FontWeight": "How bold the text is.", "FontFamily": "The typeface.",
    "TextAlignment": "Left, Center or Right.",
    "TextWrapping": "Wrap: long text runs onto more lines. NoWrap: one line.",
    "AcceptsReturn": "A box of several lines: Enter starts a new line.",
    "IsReadOnly": "Can be read and selected, but not changed.",
    "Watermark": "Grey hint text, shown while the box is empty.",
    "IsVisible": "Shown, or hidden.", "IsHitTestVisible": "Takes clicks (false: clicks go through to what's behind).",
    "Focusable": "Can take the keyboard.", "ToolTip": "Text shown when the pointer rests on it.",
    "Items": "Its list, comma-separated: Items=Red,Green,Blue.",
    "SelectedIndex": "Which item is chosen, from 0 (-1: none).", "SelectedItem": "The chosen item (a DataGrid: its row, as JSON).",
    "SelectedValue": "The chosen row's value.", "Columns": "Its column headings, comma-separated.",
    "RowCount": "How many rows it has (read only).", "AlternatingRows": "Every other row shaded, for easier reading.",
    "IsChecked": "Ticked, or not.", "GroupName": "Radio buttons with the same GroupName make one choice.",
    "Value": "Its value.", "Minimum": "The lowest its value can be.", "Maximum": "The highest its value can be.",
    "BarStyle": "How the bar is drawn.",
    "Source": "A picture: a file beside the form, a web address, or a data: address.",
    "Stretch": "How a picture fits its box: Uniform (all of it, in proportion), Fill, UniformToFill (fills it, cropped), None.",
    "Fill": "A shape's colour.", "Stroke": "A shape's edge colour.", "StrokeThickness": "A shape's edge width, in pixels.",
    "CornerRadius": "How rounded its corners are, in pixels.",
    "BorderThickness": "Its edge's width: one number, or left,top,right,bottom.",
    "ShadowStyle": "Soft (the default), 3D (a solid edge below, as if raised) or Glow (light all round).",
    "GradientDirection": "Which way GradientTo runs.", "HoverForeground": "Its text colour under the pointer.",
    "IsSeparator": "A line between menu items, instead of an item.", "Shortcut": "A menu item's key, such as Ctrl+S.",
    "IsExpanded": "Its items shown open.", "OpenOnHover": "The menus open as the pointer passes over them.",
    "AttachTo": "The control this menu opens on, when it's right-clicked.",
    "PopupBackground": "The background of the menus that drop down.", "PopupBorder": "The edge of the menus that drop down.",
    "HorizontalScrollBarVisibility": "When the sideways scroll bar shows.", "VerticalScrollBarVisibility": "When the up-and-down scroll bar shows.",
    "Thickness": "How wide the bar is, in pixels.",
    "Modal": "Opened as a dialog: the rest of the app waits until it closes.",
    "PhoneFit": "On a phone: Fit scales the form to the screen's width; None leaves it at its own size.",
    "Background": "Its background colour.", "Foreground": "Its text colour.", "BorderBrush": "Its edge's colour.",
    "Class": "The names of shared @Style styles it takes, space-separated.", "Style": "CSS for this control alone.",
    "GradientTo": "A second colour its background fades into.", "HoverBackground": "Its background colour under the pointer.",
    "Opacity": "100 is solid, 0 is see-through.", "Shadow": "0 is none, 10 looks like it's floating.",
    "ShadowColour": "The shadow's colour (black unless you say).", "IsEnabled": "false greys it out and stops it taking clicks or typing.",
}


# Where the same property means something different on different controls
PER_CONTROL = {
    ("ColorPicker", "Value"): "The colour chosen: #4F46E5.",
    ("DatePicker", "Value"): "The date chosen, year-month-day: 2026-10-16 (empty: today).",
    ("Calendar", "Value"): "The day chosen, year-month-day: 2026-10-16 (empty: today).",
    ("DatePicker", "Minimum"): "The earliest date it allows, year-month-day.", ("DatePicker", "Maximum"): "The latest date it allows, year-month-day.",
    ("Calendar", "Minimum"): "The earliest day it allows, year-month-day.", ("Calendar", "Maximum"): "The latest day it allows, year-month-day.",
    ("TimePicker", "Value"): "The time chosen, 24-hour: 14:30.",
    ("NumberBox", "Value"): "The number shown.",
    ("NumberBox", "Step"): "How much each arrow adds or takes away.",
    ("NumberBox", "Decimals"): "Places after the point (0: whole numbers).",
    ("ToggleSwitch", "Accent"): "The switch's colour when on.",
    ("HyperlinkButton", "NavigateUri"): "The web page it opens (empty: it only runs OnClick).",
    ("AutoCompleteBox", "Items"): "What it suggests, comma-separated.",
    ("MarkdownView", "Text"): "The Markdown it shows. In a form, write \\\\n for a new line.",
    ("MarkdownView", "Source"): "Where its Markdown comes from instead: a file, a web address, or help:Page for a page of Visualised's help. Links in it open in place.",
    ("MarkdownEditor", "Text"): "The Markdown written in it.",
    ("MarkdownEditor", "ShowPreview"): "How the Markdown looks, shown beside it as you type.",
}


def prop_notes():
    """Property name -> the comment on the line that declares it (else DESCRIBE's line)."""
    notes = {}
    for f in ("vml/registry.py", "vml/design.py"):
        for line in (ROOT / f).read_text(encoding="utf-8").splitlines():
            m = re.search(r'Prop\("([\w.]+)".*#\s*(.+)$', line)
            if m and m.group(1) not in notes:
                notes[m.group(1)] = m.group(2).strip()
    for k, v in DESCRIBE.items():
        notes.setdefault(k, v)
    return notes


def anchor(name):
    return name.lower().replace(" ", "-").replace(".", "")


def md(text):
    return str(text).replace("|", "\\|")


# ---------------------------------------------------------------------------------------------------- controls

def controls_page():
    notes = prop_notes()
    common = {p.name for p in COMMON}

    def row(p, control=""):
        opts = f" ({', '.join(p.options)})" if p.kind == "choice" and p.options else \
            f" ({p.options[0]} to {p.options[1]})" if p.kind == "slider" and len(p.options) == 2 else ""
        default = f" Default `{p.default}`." if p.default else ""
        note = PER_CONTROL.get((control, p.name)) or (DESCRIBE.get(p.name) if p.name in common else "") or notes.get(p.name, "")
        if note:
            note = note[0].upper() + note[1:]
            note = note if note.rstrip().endswith((".", ")", "!", "?")) else note + "."
        return f"| `{p.name}` | {KINDS.get(p.kind, p.kind)}{md(opts)} | {md(note)}{default} |"

    out = [f"# Controls reference", "",
           f"Every control in Visualised {__version__}, with its properties and events. Generated from the engine "
           "itself (`tools/make_reference.py`).", "",
           "Set a property in the form (`Background=#FFFFFF`) or from a script "
           "(`Vml(\"SetProperty\", \"btnGo\", \"Background\", \"#FFFFFF\")`); read it with `GetProperty`. "
           "An event's value is the script to run (`OnClick=SaveIt`).", "",
           "**Controls:** " + " · ".join(f"[{n}](#{anchor(n)})" for n in sorted(REGISTRY) if n not in HIDE_CONTROLS), "",
           "## Every control", "", "Most controls have these as well as their own.", "",
           "| Property | Kind | What it does |", "|---|---|---|"]
    out += [row(p) for p in sorted(COMMON, key=lambda p: (p.group, p.name)) if p.name not in ("Name",)]
    out.append("")
    for name in sorted(REGISTRY):
        if name in HIDE_CONTROLS:
            continue
        ct = REGISTRY[name]
        own = [p for p in ct.props.values() if p.name not in common]
        out += [f"## {name}", ""]
        if getattr(ct, "category", ""):
            out += [f"*{ct.category}*{' · holds other controls' if getattr(ct, 'container', False) else ''}", ""]
        has_common = sum(1 for p in ct.props.values() if p.name in common)
        if has_common:
            out += [f"Has the properties [every control](#every-control) has" +
                    ("." if has_common >= len(common) - 2 else ", or most of them."), ""]
        if own:
            out += ["| Property | Kind | What it does |", "|---|---|---|"]
            out += [row(p, name) for p in sorted(own, key=lambda p: (p.group, p.name))]
            out.append("")
        events = sorted(e for e, v in ct.events.items() if v is not None or e in ("OnOpened", "OnClosing"))
        if events:
            out += ["**Events:** " + ", ".join(f"`{e}`" for e in events), ""]
    return "\n".join(out)


# ---------------------------------------------------------------------------------------------------- commands

SECTIONS = [
    ("Properties and controls", r"^(Set|Get)Property$|Control|^ClearChildren$|^GetChildControls$|^BringToFront$|^SendToBack$|^SetCanvasPosition$"),
    ("Forms and dialogs", r"^Form|Form$|^(Show|Hide|Close)Form$|^CloseSelf$|Dialog|Markdown$|^AppExit$|^Quit$|^CancelClose$|^SetDialogResult$"),
    ("Scripts, events and programs", r"^(Run|Execute)Script$|^SetEvent$|^Shell$|Process|^Log$|^SetStatusText$|^ShowDebugger$|^Help"),
    ("Settings and preferences", r"Setting$|Preference$"),
    ("Data", r"^Sql|^Db|^Requery|Database|Table"),
    ("Web and the network", r"^Fetch$|^OpenUrl$|^Push|^OnPush$|^SignIn$"),
    ("Link (app to app)", r"^Link|^ScanCode$|^QrCode$"),
    ("Phone and device", r"^Vibrate$|^KeepAwake$|^Share$|^Notify$|^GetLocation$|^RunInBackground$|^Brightness$|^Torch$|"
                         r"^Speak$|^SaveFile$|Bluetooth|^Pressure$|Sms|Contact|^Lookup|^OnMessages$|^Listen$|^Flash$|"
                         r"Light|Photo$|^DeviceInfo$|^Clipboard"),
    ("Drives (as Mountie uses them)", r"^Ssh|^Disk|^Folder|^Ram|Terminal|^Ignore|Drive|Mount|Partition|^Image"),
    ("Licence, version and updates", r"Licen|^CheckForUpdate$|^VmlVersion$|^CSharp|^InstallDotnet$|^GetLanguages$|^GetShellName$"),
]
DESIGNER = r"Design|^Export|^Import|^Project|^Preview|^Phone|^Menu|^(Get|Set)DesignMenu|^AddDesign|^ClearDesign|^Duplicate|^Rename|^SetParent|" \
           r"^GetControlTypes$|^GetControlEvents$|^RunProject$|^Library|^Template|^LoadControlTemplate$|^Undo|^Redo|^Select|^GetCurrent|" \
           r"^SetCurrent|^Get(Selected|Focused)|^ShowContextMenu$|^GetResizeZone$|^GetControlAt$|^Android"


# What a command does, where it has no docstring to say so (a docstring wins).
SAY = {
    "SetProperty": "Change a control's property: `Vml(\"SetProperty\", \"lblTotal\", \"Text\", \"£45.00\")`. name can be `Form.control` for a control on another open form. Any property in the [controls reference](Reference-Controls) can be set.",
    "GetProperty": "Read a control's property, as text: `Vml(\"GetProperty\", \"txtName\", \"Text\")`. name can be `Form.control` for a control on another open form.",
    "ControlExists": "\"true\" if there's a control of that name, else \"false\".",
    "DeleteControl": "Remove a control (and what's in it) from the form.",
    "BringToFront": "Put a control in front of the others it overlaps.",
    "GetControlType": "The kind of control it is: \"Button\", \"TextBox\"...",
    "GetControlX": "Where the control is, in pixels from the left of what it's in.",
    "GetControlY": "Where the control is, in pixels from the top of what it's in.",
    "GetControlWidth": "The control's width now, in pixels.", "GetControlHeight": "The control's height now, in pixels.",
    "SetCanvasPosition": "Move a control on its Canvas, to x pixels from the left and y from the top.",
    "SetControlPosition": "Move a control on its Canvas, to x pixels from the left and y from the top.",
    "SetControlSize": "Resize a control, in pixels.",
    "AppExit": "Close the app.",
    "CloseForm": "Close an open form, by its name.", "ShowForm": "Show a form that was hidden, and bring it to the front.",
    "HideForm": "Hide a form, without closing it.",
    "ConfirmDialog": "Ask a yes-or-no question: \"true\" for Yes, \"false\" for No.",
    "FileOpenDialog": "Let the user choose a file: its full path, or \"\" if they cancel. ext: which kinds of file to offer, by ending (\"csv\", or \"vb,cs\" for several).",
    "FolderDialog": "Let the user choose a folder: its full path, or \"\" if they cancel.",
    "RunScript": "Run another script of this form (or a module's function) by name, with arguments; returns what it returns.",
    "SetStatusText": "Show text in the form's status line (a control named statusText, StatusText or lblStatus).",
    "GetSetting": "A value the app saved with SetSetting (\"\" if none). Kept between runs, as on a phone or in a browser.",
    "SetSetting": "Save a value under a name, for this app, to read back with GetSetting, now or the next time it opens.",
    "ProcessExitCode": "How a program started with RunProcess ended: its exit code (\"\" while it's still running).",
    "CancelProcess": "Stop a program started with RunProcess.",
    "SqlExecute": "Run SQL that changes the form's database (INSERT, UPDATE, DELETE...); ? in the SQL are filled from the arguments. Returns how many rows it changed.",
    "DbClose": "Close a database opened with DbOpen.",
    "ClipboardGet": "The text on the clipboard.",
    "FileExists": "\"true\" if there's a file at that path, else \"false\".",
    "SetMenuItemEnabled": "Grey a menu item out (\"false\") or back (\"true\").",
    "StartAtBoot": "Start this app when the user logs in (\"true\"), or not (\"false\").",
    "LaunchedAtBoot": "\"true\" if this run was started at login (by StartAtBoot), not by the user.",
    "TrayMessage": "Show a notification from the app's tray icon.",
    "GetLicenceTier": "Which licence this copy of Visualised has: \"community\", \"pro\" or \"enterprise\".",
    "RemoveLicenceKey": "Forget the licence key on this computer.",
}


def usage(name, fn):
    try:
        params = list(inspect.signature(fn).parameters.values())[1:]
    except (TypeError, ValueError):
        params = []
    bits = []
    for p in params:
        if p.kind is p.VAR_POSITIONAL:
            bits.append(f"{p.name}...")
        elif p.default is inspect.Parameter.empty:
            bits.append(p.name)
        else:
            bits.append(f"[{p.name}]")
    return f'Vml("{name}"' + "".join(", " + b for b in bits) + ")"


def commands_page():
    cmds = sorted((n[4:], getattr(Engine, n)) for n in dir(Engine) if n.startswith("cmd_") and len(n) > 4)
    placed = {s: [] for s, _ in SECTIONS}
    designer, more = [], []
    for name, fn in cmds:
        for section, pattern in SECTIONS:
            if re.search(pattern, name) and not re.search(DESIGNER, name):
                placed[section].append((name, fn))
                break
        else:
            (designer if re.search(DESIGNER, name) else more).append((name, fn))
    out = ["# Commands reference", "",
           f"Every `Vml()` command a script can call, in Visualised {__version__}. Generated from the engine itself "
           "(`tools/make_reference.py`): the descriptions are the engine's own.", "",
           "A command is called as `Vml(\"Name\", arguments...)` and returns text (`\"\"` when there's nothing to say). "
           "Arguments in [brackets] can be left out. A command that goes wrong is logged and returns `\"\"`: "
           "press **F12** while the designer runs your app to see every call and what came back.", "",
           "**Sections:** " + " · ".join(f"[{s}](#{anchor(re.sub(r'[()]', '', s))})" for s, _ in SECTIONS if placed[s])
           + (" · [More](#more)" if more else "") + " · [The designer's own](#the-designers-own)", ""]

    def entry(name, fn):
        doc = inspect.getdoc(fn) or SAY.get(name, "")
        first = doc.split("\n\n")[0].replace("\n", " ").strip()
        rest = "\n\n".join(p.replace("\n", " ").strip() for p in doc.split("\n\n")[1:])
        lines = [f"### {name}", "", f"`{usage(name, fn)}`", ""]
        if first:
            lines += [first, ""]
        if rest:
            lines += [rest, ""]
        return lines
    for section, _ in SECTIONS:
        if placed[section]:
            out += [f"## {section}", ""]
            for name, fn in placed[section]:
                out += entry(name, fn)
    if more:
        out += ["## More", ""]
        for name, fn in more:
            out += entry(name, fn)
    out += ["## The designer's own", "",
            "Commands the designer itself is built from (its forms are VML too). Handy for tools that work on forms; "
            "most apps never need them.", "",
            ", ".join(f"`{n}`" for n, _ in designer), ""]
    return "\n".join(out)


def command_line_page():
    import vml.__main__ as main
    doc = (main.__doc__ or "").strip()
    out = ["# Command line reference", "", f"The `vml` command, Visualised {__version__}.", "", "```", doc,
           "vml onl-key KEY                                         (the TinyWeb key vml.onl publishing uses)",
           "vml mcp                                                 (an MCP server, so an AI assistant can make and publish apps)",
           "```", "",
           "On Windows the same commands are run with `vml.exe` from Visualised's folder; double-clicking a `.vml` "
           "or `.vmlproj` file opens it.", ""]
    return "\n".join(out)


def index_page():
    return "\n".join([
        "# Reference", "",
        f"Everything in Visualised {__version__}, generated from the engine itself. For step-by-step guides, see the "
        "[tutorials](Home).", "",
        "- [Controls](Reference-Controls): every control, its properties and events.",
        "- [Commands](Reference-Commands): every `Vml()` command a script can call.",
        "- [Command line](Reference-Command-Line): the `vml` command.", "",
        "In the designer, **F1** opens the entry for the selected control.", ""])


def main():
    out = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    out.mkdir(parents=True, exist_ok=True)
    for name, text in (("Reference.md", index_page()), ("Reference-Controls.md", controls_page()),
                       ("Reference-Commands.md", commands_page()), ("Reference-Command-Line.md", command_line_page())):
        (out / name).write_text(text, encoding="utf-8")
        print(f"{out / name}: {len(text):,} characters")


if __name__ == "__main__":
    main()
