# Visualised

*Apps are written in VML, Visualised's own markup.*

**A cross-platform RAD IDE that designs itself, for the desktop and the web**

VML is a lightweight, patent-pending application development system: simple flat markup, scripted in Lua or the
operating system's own shell, running as real native desktop applications on Linux, Windows and macOS. Think Visual
Basic 5, rebuilt for 2026: draw a form, double-click a button, write what it does, press F5.

The designer is itself a VML form. So is its script editor. VML builds VML.

![The VML designer](docs/designer.png)

## What makes VML unique

### The Parent= innovation

Unlike nested UI markup (XML, XAML, HTML), VML uses a **flat structure with named parent references**:

```vml
@Window MainWindow
Title=My Application
Width=800
Height=600

@StackPanel Container
Parent=MainWindow
Margin=20

@Button SaveBtn
Parent=Container
Content=Save
OnClick=SaveScript

@Script SaveScript
Interpreter=lua
<<LUA
Vml("InfoDialog", "Saved!")
LUA
```

- No closing tags, no nesting hell
- grep, sed and awk friendly
- Refactor by changing one `Parent=` line
- Human readable, machine parseable

### Architecture

```
VML file (.vml)
    ↓
Lua parser (vml-parser.lua, ~300 lines)
    ↓
SQLite (controls, properties, scripts)
    ↓
Control registry → Qt widgets (PySide6)
    ↓
Scripts: Lua (embedded) · Bash · PowerShell
```

Every script talks to the running application through one function:

```lua
local name = Vml("GetProperty", "txtName", "Text")
Vml("SetProperty", "lblHello", "Text", "Hello, " .. name)
```

The **control registry** is the single source of truth: each control type is declared once, with every property
(its kind, editor, group, how to set it and read it back) and its events. Rendering, the `Vml()` API and the
designer's property panel are all driven from it, so a property added once appears everywhere.

## Download

- **Windows:** [Visualised-Setup.exe](https://github.com/wallisoft/vml-releases/releases/latest/download/Visualised-Setup.exe) (no admin needed), or the [portable zip](https://github.com/wallisoft/vml-releases/releases/latest/download/vml-windows-x64.zip)
- **Linux:** `curl -fsSL https://github.com/wallisoft/vml-releases/releases/latest/download/install.sh | bash`
- More at **[vml.eur.bz](https://vml.eur.bz)**, including a live demo in your browser.

## Quick start (from source)

Requires Python 3.10+.

```bash
pip install -r requirements.txt
./vml.py                       # the designer
./vml.py path/to/any-form.vml  # run any VML form
```

## The designer

- **Right-click the form to add a control.** The list comes from the registry, so new control types appear automatically.
- **Drag to move, drag the handles to resize.** Snaps to the grid; hold Alt for free movement. Arrow keys nudge
  (Shift for a grid step).
- **Anchors:** pin a control to the form's edges so it moves or stretches as the window resizes (an OK button in
  the corner, a text box that spans the width, a list that fills the form). Drag the form's corner to see it live.
- **Frames:** right-click inside a Frame to add a control to it, or drag a control onto a frame (and off it
  again). Frames carry their contents with them; anchor the frame and its contents to make whole areas stretch.
- **Live position and size** on the status bar while you drag, resize or nudge.
- **Form options:** title, size, background, resizable, modal, minimum and maximum size, shown on a window title
  bar above the form as you design.
- **Menus, two ways.** Right-click the form and choose **Add Menu** for File, Edit and Help (Exit and About already
  work), then treat menu items like controls: click a
  caption to select it and edit it in the property grid, and right-click any item for Add Before, Add After, Add
  Submenu Item, Delete and Edit Script. Or use the **Menu Editor** (Ctrl+M), after VB5's: type a caption, press
  Next, indent with the arrows. Either way, the form shows its real menu bar as you design. Click the bar's empty
  space for its own properties: colours, and opening dropdowns on hover.
- **Bring to Front / Send to Back, Duplicate (Ctrl+D), Delete.**
- **The property grid** edits whatever is selected: grouped, with checkboxes, dropdowns and colour pickers, and
  live, so it never goes stale. Click the empty form to edit the form itself.
- **Double-click a control to script it.** Choose the event and the language (Lua, or the OS shell), and write.
  Scripts are saved into the form as ordinary `@Script` blocks.
- **Export** (File → Export): a **Windows app** or **Linux app** (the compiled runtime renamed after your app,
  beside your forms: unzip and double-click), or a **web page** with the Lua engine inside it, so it works offline.
- **F5 previews** the form running for real. **Ctrl+S** saves plain VML; **Ctrl+O** opens it again.

## On the web

The same `.vml` file runs in a browser. **View → Preview in Browser** (F6) in the designer, **File → Export to
HTML…**, or from a terminal:

```bash
./vml.py html myform.vml          # writes myform.html: one self-contained page, works offline
./vml.py html myform.vml --open   # ...and opens it in your browser via a tiny local web server
```

Layout is faithful: canvas forms are positioned exactly, and **anchors become CSS**, so controls move and stretch as
the browser window resizes. Frames, menus, StackPanel, Grid, Border and DockPanel all carry across. **Lua scripts run
unchanged** in the browser (Lua 5.4 compiled to WebAssembly, bundled into the page, so no network is needed), against a JavaScript `Vml()` that speaks the same
commands, `require("dkjson")` included. Shell, C# and Python scripts are desktop-only and say so in the browser
console. Open the console and `vml.Vml("GetProperty", "txtName", "Text")` works there too.

![The same form, in a browser](docs/web.png)

## Scripting

| Language | How it runs |
|---|---|
| **Lua** | Embedded (Lua 5.4 via `lupa`), in-process and fast. One state per form, or shared by named instance. `require("dkjson")` available. |
| **Bash** | As a subprocess, with the `vml` command on its `PATH` to talk to the form (and `$VML_DB_PATH`, `vml-parse` as before). |
| **PowerShell** | As a subprocess, on Windows (or anywhere `pwsh` is installed). |
| **Python** | As a subprocess, using your own Python and its packages, with a native `Vml()` function (`from vml.client import call`) and `args`. |
| **C#** (optional) | Compiled with Roslyn by a small .NET host that stays running; cached, so repeat runs are instant. |

Events include clicks, text changes, selection, pointer, focus and keys (`OnKeyDown` and `OnKeyUp` receive
the key, its text and the Ctrl/Shift/Alt modifiers). Event handlers can name a script (`OnClick=SaveScript`), pass it arguments (`OnClick=AddItem(Button)`), call an
engine command (`OnClick=FormOpenModal about.vml`), or be a line of Lua.

**Each form has its own Lua state**, so its globals are its own. To share state deliberately, give scripts the same
**named instance**: `Interpreter=lua mygame` (or `Instance=mygame`). Every script in that instance, in any form, sees
the same globals.

### Bash, PowerShell, and any other language: the `vml` command

Scripts VML runs have a `vml` command on their PATH that talks to the running form:

```bash
name=$(vml get txtName Text)
vml set lblHello Text "Hello, $name"
vml setting last_user "$name"
vml run SaveScript "$name"        # any script, in any language; prints what it returns
vml InfoDialog "Saved!"           # or any Vml() command by name
```

```powershell
$name = vml get txtName Text
vml set lblHello Text "Hello, $name"
```

Plain control names mean the script's own form (`Form.Control` reaches another). A failed call prints an error and
exits with 1, so `||`, `$?` and `$LASTEXITCODE` work. Programs VML didn't start can drive a running form too:
`./vml.py get txtName Text` from a terminal, or any language speaking one line of JSON over the local socket
described in `~/.vml/api.json` (readable only by you; the token in it is required).

### C# (optional)

With the .NET SDK (8.0 or later) installed, build the C# host once:

```bash
./vml.py setup-csharp
```

C# then appears in the script editor alongside Lua and the shell, with the same API:

```csharp
var name = Vml("GetProperty", "txtName", "Text");
State["clicks"] = (State.TryGetValue("clicks", out var c) ? (int)c : 0) + 1;   // State: kept per form
Vml("SetProperty", "lblHello", "Text", $"Hello, {name} ({State["clicks"]})");
```

Script arguments are in `args`, `Console.WriteLine` goes to the log, and C# and Lua can call each other through
`RunScript`. The first run of a script takes about a second to compile; after that it's instant. Without .NET,
nothing changes: C# simply isn't offered.

### Multiple forms

```lua
-- open a form (paths are relative to this one); if it's already open it comes to the front
Vml("FormOpen", "settings.vml")

-- open one and wait for it to close; it hands back whatever it passed to SetDialogResult
local answer = Vml("FormOpenModal", "confirm.vml")

-- in the child: read and write the parent's controls by Form.Control
local name = Vml("GetProperty", "Main.txtName", "Text")
Vml("SetProperty", "Main.lblStatus", "Text", "Saved")
Vml("SetDialogResult", "ok")
Vml("CloseSelf")
```

Plain control names always mean "my own form", so two forms can both have a `btnOK`. `ShowForm`, `HideForm` and
`CloseForm` manage open forms by name. Previewing a saved form in the designer finds its child forms next to the file.

Commonly used `Vml()` commands:

| | |
|---|---|
| Properties | `SetProperty` · `GetProperty` · `GetControlPropertiesJson` |
| Controls | `CreateControl` · `DeleteControl` · `ControlExists` · `GetChildControls` · `ClearChildren` |
| Shared state | `GetSetting` · `SetSetting` |
| Scripts | `RunScript` · `ExecuteScript` · `Shell` |
| Data | `SqlQuery` (JSON) · `SqlExecute` |
| Forms and dialogs | `FormOpen` · `FormOpenModal` · `SetDialogResult` · `ShowForm` · `HideForm` · `CloseForm` · `CloseSelf` · `InfoDialog` · `ConfirmDialog` · `FileOpenDialog` · `FileSaveDialog` |
| Menus | `ShowContextMenu` · `SetMenuItemEnabled` · `SetMenuItemText` |

## Controls

Window, Frame, StackPanel, Grid, DockPanel, Canvas, Border, ScrollViewer, TextBlock, TextBox, Button, CheckBox, ComboBox,
ListBox, Rectangle, menus (TinyMenu, MenuItem, ContextMenu, MenuTheme), and **composite controls** defined in VML
itself with `@ControlTemplate` and `@PropertyMap`. Layout follows Avalonia's rules (DockPanel docking order, Grid
star sizing, Margin outside and Padding inside), so existing forms look the same.

The designer's own building blocks, `DesignSurface` and `PropertyGrid`, are ordinary registered controls, available
to any VML application.

## Project layout

```
vml/            the engine
  registry.py   every control type, property and event
  engine.py     rendering, the Vml() API, the script host
  design.py     DesignSurface and PropertyGrid
  store.py      SQLite, and the Lua parser runner
  lua/          vml-parser.lua, dkjson.lua
designer/       the designer and script editor (VML + Lua)
tests/          tests that drive forms like a user does
packaging/      icon, installers (Windows, Linux) and the Store manifest
.github/        the release workflow: tag a version, get every download
```

## Tests

```bash
python3 tests/run_step1.py      # events, Lua, settings, shell, reflection
python3 tests/run_designer.py   # the designer: add, drag, resize, edit, script, save, reopen, preview
python3 tests/run_anchors.py    # anchors, in the designer and at runtime
python3 tests/run_frames.py     # frames, nesting, keys, live geometry, window options
python3 tests/run_menus.py      # menus: editor, menu bar and items as controls, saved, reopened and run
python3 tests/run_multiform.py  # forms opening forms, Form.Control names, dialog results, Lua states
python3 tests/run_csharp.py     # C# scripting (skips itself if .NET isn't set up)
python3 tests/run_api.py        # the vml command and Python: calling back, chains across languages, outside programs
python3 tests/run_web.py        # the HTML renderer in a real browser (needs: pip install playwright)
```

`tests/run_step2.py` exercises the original Avalonia-era designer from `~/.vml/designer`, if present.

## Roadmap

- Designing layout-based forms
- Undo and redo
- Mobile, via a renderer for phones
- The Microsoft Store listing
- Exporting your app as a Windows or Linux program

## History

VML began as Visual Bash Designer, a YAML-driven form builder, and grew into a .NET/Avalonia engine. In October 2026
it was rebuilt on Python and Qt, keeping the parser and the SQLite model. The Avalonia version is preserved in this
repository's history at the tag `avalonia-final`.

## Licence

Dual-licensed: see [LICENSE-MIT.md](LICENSE-MIT.md) and [LICENSE-COMMERCIAL.md](LICENSE-COMMERCIAL.md).

Built by Wallisoft with Claude.
