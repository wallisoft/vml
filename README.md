# VML (Visualised Markup Language)

**A cross-platform RAD IDE that designs itself**

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

## Quick start

Requires Python 3.10+.

```bash
pip install -r requirements.txt
python3 -m vml designer/designer.vml        # the designer
python3 -m vml path/to/any-form.vml         # run any VML form
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
- **Menu Editor** (Ctrl+M, or click the form's menu bar), after VB5's: type a caption, press Next, indent with the
  arrows for submenus, add shortcuts and separators, and give each item a script. The form shows its real menu bar
  as you design.
- **Bring to Front / Send to Back, Duplicate (Ctrl+D), Delete.**
- **The property grid** edits whatever is selected: grouped, with checkboxes, dropdowns and colour pickers, and
  live, so it never goes stale. Click the empty form to edit the form itself.
- **Double-click a control to script it.** Choose the event and the language (Lua, or the OS shell), and write.
  Scripts are saved into the form as ordinary `@Script` blocks.
- **F5 previews** the form running for real. **Ctrl+S** saves plain VML; **Ctrl+O** opens it again.

## Scripting

| Language | How it runs |
|---|---|
| **Lua** | Embedded (Lua 5.4 via `lupa`), in-process and fast. Shares state between scripts. `require("dkjson")` available. |
| **Bash** | As a subprocess, with `$VML_DB_PATH` pointing at the form's database and `vml-parse` on the `PATH`. |
| **PowerShell** | As a subprocess, on Windows (or anywhere `pwsh` is installed). |

Events include clicks, text changes, selection, pointer, focus and keys (`OnKeyDown` and `OnKeyUp` receive
the key, its text and the Ctrl/Shift/Alt modifiers). Event handlers can name a script (`OnClick=SaveScript`), pass it arguments (`OnClick=AddItem(Button)`), call an
engine command (`OnClick=FormOpenModal about.vml`), or be a line of Lua.

Commonly used `Vml()` commands:

| | |
|---|---|
| Properties | `SetProperty` · `GetProperty` · `GetControlPropertiesJson` |
| Controls | `CreateControl` · `DeleteControl` · `ControlExists` · `GetChildControls` · `ClearChildren` |
| Shared state | `GetSetting` · `SetSetting` |
| Scripts | `RunScript` · `ExecuteScript` · `Shell` |
| Data | `SqlQuery` (JSON) · `SqlExecute` |
| Forms and dialogs | `FormOpen` · `FormOpenModal` · `CloseSelf` · `InfoDialog` · `ConfirmDialog` · `FileOpenDialog` · `FileSaveDialog` |
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
```

## Tests

```bash
python3 tests/run_step1.py      # events, Lua, settings, shell, reflection
python3 tests/run_designer.py   # the designer: add, drag, resize, edit, script, save, reopen, preview
python3 tests/run_anchors.py    # anchors, in the designer and at runtime
python3 tests/run_frames.py     # frames, nesting, keys, live geometry, window options
python3 tests/run_menus.py      # the Menu Editor, menus saved, reopened and run
```

`tests/run_step2.py` exercises the original Avalonia-era designer from `~/.vml/designer`, if present.

## Roadmap

- Named interpreter instances (`Interpreter=lua mygame`): scripts sharing a name share their state
- Designing layout-based forms
- Undo and redo
- Packaged releases (Linux, Windows installer, Microsoft Store)

## History

VML began as Visual Bash Designer, a YAML-driven form builder, and grew into a .NET/Avalonia engine. In October 2026
it was rebuilt on Python and Qt, keeping the parser and the SQLite model. The Avalonia version is preserved in this
repository's history at the tag `avalonia-final`.

## Licence

Dual-licensed: see [LICENSE-MIT.md](LICENSE-MIT.md) and [LICENSE-COMMERCIAL.md](LICENSE-COMMERCIAL.md).

Built by Wallisoft with Claude.
