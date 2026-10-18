# Controls reference

Every control in Visualised 1.3.0, with its properties and events. Generated from the engine itself (`tools/make_reference.py`).

Set a property in the form (`Background=#FFFFFF`) or from a script (`Vml("SetProperty", "btnGo", "Background", "#FFFFFF")`); read it with `GetProperty`. An event's value is the script to run (`OnClick=SaveIt`).

**Controls:** [AutoCompleteBox](#autocompletebox) · [Border](#border) · [Button](#button) · [Calendar](#calendar) · [Canvas](#canvas) · [CheckBox](#checkbox) · [ColorPicker](#colorpicker) · [ComboBox](#combobox) · [ContextMenu](#contextmenu) · [DataGrid](#datagrid) · [DatePicker](#datepicker) · [DockPanel](#dockpanel) · [Frame](#frame) · [Grid](#grid) · [HyperlinkButton](#hyperlinkbutton) · [Image](#image) · [ListBox](#listbox) · [MarkdownEditor](#markdowneditor) · [MarkdownView](#markdownview) · [MenuItem](#menuitem) · [MenuTheme](#menutheme) · [NumberBox](#numberbox) · [ProgressBar](#progressbar) · [RadioButton](#radiobutton) · [Rectangle](#rectangle) · [ScrollViewer](#scrollviewer) · [Slider](#slider) · [Splitter](#splitter) · [StackPanel](#stackpanel) · [TextBlock](#textblock) · [TextBox](#textbox) · [TimePicker](#timepicker) · [Timer](#timer) · [TinyMenu](#tinymenu) · [ToggleButton](#togglebutton) · [ToggleSwitch](#toggleswitch) · [TreeView](#treeview) · [Window](#window)

## Every control

Most controls have these as well as their own.

| Property | Kind | What it does |
|---|---|---|
| `Background` | colour | Its background colour. |
| `BorderBrush` | colour | Its edge's colour. |
| `BorderThickness` | thickness | Its edge's width: one number, or left,top,right,bottom. |
| `Class` | text | The names of shared @Style styles it takes, space-separated. |
| `CornerRadius` | number | How rounded its corners are, in pixels. |
| `Foreground` | colour | Its text colour. |
| `GradientDirection` | choice (Down, Right, Diagonal, Up, Left) | Which way GradientTo runs. |
| `GradientTo` | colour | A second colour its background fades into. |
| `HoverBackground` | colour | Its background colour under the pointer. |
| `HoverForeground` | colour | Its text colour under the pointer. |
| `Opacity` | number (slider) (0 to 100) | 100 is solid, 0 is see-through. |
| `Shadow` | number (slider) (0 to 10) | 0 is none, 10 looks like it's floating. |
| `ShadowColour` | colour | The shadow's colour (black unless you say). |
| `ShadowStyle` | choice (Soft, 3D, Glow) | Soft (the default), 3D (a solid edge below, as if raised) or Glow (light all round). |
| `Style` | text | CSS for this control alone. |
| `IsEnabled` | true/false | False greys it out and stops it taking clicks or typing. Default `true`. |
| `IsVisible` | true/false | Shown, or hidden. Default `true`. |
| `ToolTip` | text | Text shown when the pointer rests on it. |
| `Height` | number | Its height, in pixels. |
| `HorizontalAlignment` | choice (Stretch, Left, Center, Right) | Where it sits across a panel's space. |
| `Margin` | thickness | Space outside it: one number, or left,top,right,bottom. |
| `MinHeight` | number | The shortest it can be, in pixels. |
| `MinWidth` | number | The narrowest it can be, in pixels. |
| `VerticalAlignment` | choice (Stretch, Top, Center, Bottom) | Where it sits up and down a panel's space. |
| `Width` | number | Its width, in pixels. |
| `X` | number | Where it is now, from the left, in pixels (read only). |
| `Y` | number | Where it is now, from the top, in pixels (read only). |
| `FontFamily` | text | The typeface. |
| `FontSize` | number | Text size, in pixels. |
| `FontWeight` | choice (Thin, ExtraLight, Light, Normal, Medium, SemiBold, Bold, ExtraBold, Black) | How bold the text is. |

## AutoCompleteBox

*Common*

Has the properties [every control](#every-control) has.

| Property | Kind | What it does |
|---|---|---|
| `Items` | list | What it suggests, comma-separated. |
| `Text` | text | The text shown (or typed, in a TextBox). |
| `Anchor` | choice (Top,Left, Top,Right, Bottom,Left, Bottom,Right, Top,Left,Right, Bottom,Left,Right, Top,Bottom,Left, Top,Bottom,Right, Top,Bottom,Left,Right) | The Canvas edges it keeps its distance from as the form is resized: anchored to both sides, it stretches. Default `Top,Left`. |
| `Canvas.Left` | number | Its place on a Canvas: pixels from the left. |
| `Canvas.Top` | number | Its place on a Canvas: pixels from the top. |
| `DockPanel.Dock` | choice (Left, Top, Right, Bottom) | The side of a DockPanel it docks to. |
| `Grid.Column` | number | Its column in a Grid, from 0. |
| `Grid.ColumnSpan` | number | How many Grid columns it spans. |
| `Grid.Row` | number | Its row in a Grid, from 0. |
| `Grid.RowSpan` | number | How many Grid rows it spans. |
| `Watermark` | text | Grey hint text, shown while the box is empty. |

**Events:** `TextChanged`, `ValueChanged`

## Border

*Containers* · holds other controls

Has the properties [every control](#every-control) has.

| Property | Kind | What it does |
|---|---|---|
| `Focusable` | true/false | Can take the keyboard. |
| `IsHitTestVisible` | true/false | Takes clicks (false: clicks go through to what's behind). Default `true`. |
| `Padding` | thickness | Space inside it, between its edge and what it holds: one number, or left,top,right,bottom. |
| `Anchor` | choice (Top,Left, Top,Right, Bottom,Left, Bottom,Right, Top,Left,Right, Bottom,Left,Right, Top,Bottom,Left, Top,Bottom,Right, Top,Bottom,Left,Right) | The Canvas edges it keeps its distance from as the form is resized: anchored to both sides, it stretches. Default `Top,Left`. |
| `Canvas.Left` | number | Its place on a Canvas: pixels from the left. |
| `Canvas.Top` | number | Its place on a Canvas: pixels from the top. |
| `DockPanel.Dock` | choice (Left, Top, Right, Bottom) | The side of a DockPanel it docks to. |
| `Grid.Column` | number | Its column in a Grid, from 0. |
| `Grid.ColumnSpan` | number | How many Grid columns it spans. |
| `Grid.Row` | number | Its row in a Grid, from 0. |
| `Grid.RowSpan` | number | How many Grid rows it spans. |

**Events:** `OnGotFocus`, `OnLostFocus`, `OnPointerMoved`, `OnPointerPressed`, `OnPointerReleased`

## Button

*Common*

Has the properties [every control](#every-control) has.

| Property | Kind | What it does |
|---|---|---|
| `Focusable` | true/false | Can take the keyboard. |
| `IsHitTestVisible` | true/false | Takes clicks (false: clicks go through to what's behind). Default `true`. |
| `Content` | text | What a button or check box says. |
| `Padding` | thickness | Space inside it, between its edge and what it holds: one number, or left,top,right,bottom. |
| `Anchor` | choice (Top,Left, Top,Right, Bottom,Left, Bottom,Right, Top,Left,Right, Bottom,Left,Right, Top,Bottom,Left, Top,Bottom,Right, Top,Bottom,Left,Right) | The Canvas edges it keeps its distance from as the form is resized: anchored to both sides, it stretches. Default `Top,Left`. |
| `Canvas.Left` | number | Its place on a Canvas: pixels from the left. |
| `Canvas.Top` | number | Its place on a Canvas: pixels from the top. |
| `DockPanel.Dock` | choice (Left, Top, Right, Bottom) | The side of a DockPanel it docks to. |
| `Grid.Column` | number | Its column in a Grid, from 0. |
| `Grid.ColumnSpan` | number | How many Grid columns it spans. |
| `Grid.Row` | number | Its row in a Grid, from 0. |
| `Grid.RowSpan` | number | How many Grid rows it spans. |

**Events:** `OnClick`, `OnGotFocus`, `OnKeyDown`, `OnKeyUp`, `OnLostFocus`, `OnPointerMoved`, `OnPointerPressed`, `OnPointerReleased`

## Calendar

*Common*

Has the properties [every control](#every-control) has.

| Property | Kind | What it does |
|---|---|---|
| `Maximum` | text | The latest day it allows, year-month-day. |
| `Minimum` | text | The earliest day it allows, year-month-day. |
| `Value` | text | The day chosen, year-month-day: 2026-10-16 (empty: today). |
| `Anchor` | choice (Top,Left, Top,Right, Bottom,Left, Bottom,Right, Top,Left,Right, Bottom,Left,Right, Top,Bottom,Left, Top,Bottom,Right, Top,Bottom,Left,Right) | The Canvas edges it keeps its distance from as the form is resized: anchored to both sides, it stretches. Default `Top,Left`. |
| `Canvas.Left` | number | Its place on a Canvas: pixels from the left. |
| `Canvas.Top` | number | Its place on a Canvas: pixels from the top. |
| `DockPanel.Dock` | choice (Left, Top, Right, Bottom) | The side of a DockPanel it docks to. |
| `Grid.Column` | number | Its column in a Grid, from 0. |
| `Grid.ColumnSpan` | number | How many Grid columns it spans. |
| `Grid.Row` | number | Its row in a Grid, from 0. |
| `Grid.RowSpan` | number | How many Grid rows it spans. |

**Events:** `ValueChanged`

## Canvas

*Containers* · holds other controls

Has the properties [every control](#every-control) has.

| Property | Kind | What it does |
|---|---|---|
| `Focusable` | true/false | Can take the keyboard. |
| `IsHitTestVisible` | true/false | Takes clicks (false: clicks go through to what's behind). Default `true`. |
| `Anchor` | choice (Top,Left, Top,Right, Bottom,Left, Bottom,Right, Top,Left,Right, Bottom,Left,Right, Top,Bottom,Left, Top,Bottom,Right, Top,Bottom,Left,Right) | The Canvas edges it keeps its distance from as the form is resized: anchored to both sides, it stretches. Default `Top,Left`. |
| `Canvas.Left` | number | Its place on a Canvas: pixels from the left. |
| `Canvas.Top` | number | Its place on a Canvas: pixels from the top. |
| `DockPanel.Dock` | choice (Left, Top, Right, Bottom) | The side of a DockPanel it docks to. |
| `Grid.Column` | number | Its column in a Grid, from 0. |
| `Grid.ColumnSpan` | number | How many Grid columns it spans. |
| `Grid.Row` | number | Its row in a Grid, from 0. |
| `Grid.RowSpan` | number | How many Grid rows it spans. |

**Events:** `OnGotFocus`, `OnLostFocus`, `OnPointerMoved`, `OnPointerPressed`, `OnPointerReleased`

## CheckBox

*Common*

Has the properties [every control](#every-control) has.

| Property | Kind | What it does |
|---|---|---|
| `Focusable` | true/false | Can take the keyboard. |
| `IsHitTestVisible` | true/false | Takes clicks (false: clicks go through to what's behind). Default `true`. |
| `Content` | text | What a button or check box says. |
| `IsChecked` | true/false | Ticked, or not. |
| `Anchor` | choice (Top,Left, Top,Right, Bottom,Left, Bottom,Right, Top,Left,Right, Bottom,Left,Right, Top,Bottom,Left, Top,Bottom,Right, Top,Bottom,Left,Right) | The Canvas edges it keeps its distance from as the form is resized: anchored to both sides, it stretches. Default `Top,Left`. |
| `Canvas.Left` | number | Its place on a Canvas: pixels from the left. |
| `Canvas.Top` | number | Its place on a Canvas: pixels from the top. |
| `DockPanel.Dock` | choice (Left, Top, Right, Bottom) | The side of a DockPanel it docks to. |
| `Grid.Column` | number | Its column in a Grid, from 0. |
| `Grid.ColumnSpan` | number | How many Grid columns it spans. |
| `Grid.Row` | number | Its row in a Grid, from 0. |
| `Grid.RowSpan` | number | How many Grid rows it spans. |

**Events:** `OnChecked`, `OnClick`, `OnGotFocus`, `OnKeyDown`, `OnKeyUp`, `OnLostFocus`, `OnPointerMoved`, `OnPointerPressed`, `OnPointerReleased`

## ColorPicker

*Common*

Has the properties [every control](#every-control) has.

| Property | Kind | What it does |
|---|---|---|
| `Value` | colour | The colour chosen: #4F46E5. Default `#4F46E5`. |
| `Anchor` | choice (Top,Left, Top,Right, Bottom,Left, Bottom,Right, Top,Left,Right, Bottom,Left,Right, Top,Bottom,Left, Top,Bottom,Right, Top,Bottom,Left,Right) | The Canvas edges it keeps its distance from as the form is resized: anchored to both sides, it stretches. Default `Top,Left`. |
| `Canvas.Left` | number | Its place on a Canvas: pixels from the left. |
| `Canvas.Top` | number | Its place on a Canvas: pixels from the top. |
| `DockPanel.Dock` | choice (Left, Top, Right, Bottom) | The side of a DockPanel it docks to. |
| `Grid.Column` | number | Its column in a Grid, from 0. |
| `Grid.ColumnSpan` | number | How many Grid columns it spans. |
| `Grid.Row` | number | Its row in a Grid, from 0. |
| `Grid.RowSpan` | number | How many Grid rows it spans. |

**Events:** `ValueChanged`

## ComboBox

*Common*

Has the properties [every control](#every-control) has.

| Property | Kind | What it does |
|---|---|---|
| `Focusable` | true/false | Can take the keyboard. |
| `IsHitTestVisible` | true/false | Takes clicks (false: clicks go through to what's behind). Default `true`. |
| `Items` | list | Its list, comma-separated: Items=Red,Green,Blue. |
| `SelectedIndex` | number | Which item is chosen, from 0 (-1: none). |
| `SelectedItem` | text | The chosen item (a DataGrid: its row, as JSON). |
| `Database` | text | Which opened database it asks; empty = the main one. |
| `ItemsSource` | text | A query (or a script) that fills the control: see vml/data.py. |
| `Anchor` | choice (Top,Left, Top,Right, Bottom,Left, Bottom,Right, Top,Left,Right, Bottom,Left,Right, Top,Bottom,Left, Top,Bottom,Right, Top,Bottom,Left,Right) | The Canvas edges it keeps its distance from as the form is resized: anchored to both sides, it stretches. Default `Top,Left`. |
| `Canvas.Left` | number | Its place on a Canvas: pixels from the left. |
| `Canvas.Top` | number | Its place on a Canvas: pixels from the top. |
| `DockPanel.Dock` | choice (Left, Top, Right, Bottom) | The side of a DockPanel it docks to. |
| `Grid.Column` | number | Its column in a Grid, from 0. |
| `Grid.ColumnSpan` | number | How many Grid columns it spans. |
| `Grid.Row` | number | Its row in a Grid, from 0. |
| `Grid.RowSpan` | number | How many Grid rows it spans. |

**Events:** `OnKeyDown`, `OnKeyUp`, `SelectionChanged`

## ContextMenu

*Menus* · holds other controls

| Property | Kind | What it does |
|---|---|---|
| `AttachTo` | text | The control this menu opens on, when it's right-clicked. |

**Events:** `OnOpened`

## DataGrid

*Common*

Has the properties [every control](#every-control) has.

| Property | Kind | What it does |
|---|---|---|
| `Focusable` | true/false | Can take the keyboard. |
| `IsHitTestVisible` | true/false | Takes clicks (false: clicks go through to what's behind). Default `true`. |
| `Columns` | list | Its column headings, comma-separated. |
| `Items` | list | Its list, comma-separated: Items=Red,Green,Blue. |
| `RowCount` | number | How many rows it has (read only). |
| `SelectedIndex` | number | Which item is chosen, from 0 (-1: none). |
| `SelectedItem` | text | The chosen item (a DataGrid: its row, as JSON). |
| `SelectedValue` | text | The chosen row's value. |
| `Database` | text | Which opened database it asks; empty = the main one. |
| `ItemsSource` | text | A query (or a script) that fills the control: see vml/data.py. |
| `Anchor` | choice (Top,Left, Top,Right, Bottom,Left, Bottom,Right, Top,Left,Right, Bottom,Left,Right, Top,Bottom,Left, Top,Bottom,Right, Top,Bottom,Left,Right) | The Canvas edges it keeps its distance from as the form is resized: anchored to both sides, it stretches. Default `Top,Left`. |
| `Canvas.Left` | number | Its place on a Canvas: pixels from the left. |
| `Canvas.Top` | number | Its place on a Canvas: pixels from the top. |
| `DockPanel.Dock` | choice (Left, Top, Right, Bottom) | The side of a DockPanel it docks to. |
| `Grid.Column` | number | Its column in a Grid, from 0. |
| `Grid.ColumnSpan` | number | How many Grid columns it spans. |
| `Grid.Row` | number | Its row in a Grid, from 0. |
| `Grid.RowSpan` | number | How many Grid rows it spans. |

**Events:** `OnContextMenu`, `OnDoubleClick`, `OnKeyDown`, `OnKeyUp`, `SelectionChanged`

## DatePicker

*Common*

Has the properties [every control](#every-control) has.

| Property | Kind | What it does |
|---|---|---|
| `Maximum` | text | The latest date it allows, year-month-day. |
| `Minimum` | text | The earliest date it allows, year-month-day. |
| `Value` | text | The date chosen, year-month-day: 2026-10-16 (empty: today). |
| `Anchor` | choice (Top,Left, Top,Right, Bottom,Left, Bottom,Right, Top,Left,Right, Bottom,Left,Right, Top,Bottom,Left, Top,Bottom,Right, Top,Bottom,Left,Right) | The Canvas edges it keeps its distance from as the form is resized: anchored to both sides, it stretches. Default `Top,Left`. |
| `Canvas.Left` | number | Its place on a Canvas: pixels from the left. |
| `Canvas.Top` | number | Its place on a Canvas: pixels from the top. |
| `DockPanel.Dock` | choice (Left, Top, Right, Bottom) | The side of a DockPanel it docks to. |
| `Grid.Column` | number | Its column in a Grid, from 0. |
| `Grid.ColumnSpan` | number | How many Grid columns it spans. |
| `Grid.Row` | number | Its row in a Grid, from 0. |
| `Grid.RowSpan` | number | How many Grid rows it spans. |

**Events:** `ValueChanged`

## DockPanel

*Containers* · holds other controls

Has the properties [every control](#every-control) has.

| Property | Kind | What it does |
|---|---|---|
| `Focusable` | true/false | Can take the keyboard. |
| `IsHitTestVisible` | true/false | Takes clicks (false: clicks go through to what's behind). Default `true`. |
| `LastChildFill` | true/false | The last control fills the space that's left. Default `true`. |
| `Anchor` | choice (Top,Left, Top,Right, Bottom,Left, Bottom,Right, Top,Left,Right, Bottom,Left,Right, Top,Bottom,Left, Top,Bottom,Right, Top,Bottom,Left,Right) | The Canvas edges it keeps its distance from as the form is resized: anchored to both sides, it stretches. Default `Top,Left`. |
| `Canvas.Left` | number | Its place on a Canvas: pixels from the left. |
| `Canvas.Top` | number | Its place on a Canvas: pixels from the top. |
| `DockPanel.Dock` | choice (Left, Top, Right, Bottom) | The side of a DockPanel it docks to. |
| `Grid.Column` | number | Its column in a Grid, from 0. |
| `Grid.ColumnSpan` | number | How many Grid columns it spans. |
| `Grid.Row` | number | Its row in a Grid, from 0. |
| `Grid.RowSpan` | number | How many Grid rows it spans. |

**Events:** `OnGotFocus`, `OnLostFocus`, `OnPointerMoved`, `OnPointerPressed`, `OnPointerReleased`

## Frame

*Containers* · holds other controls

Has the properties [every control](#every-control) has.

| Property | Kind | What it does |
|---|---|---|
| `Focusable` | true/false | Can take the keyboard. |
| `IsHitTestVisible` | true/false | Takes clicks (false: clicks go through to what's behind). Default `true`. |
| `Text` | text | The text shown (or typed, in a TextBox). |
| `Anchor` | choice (Top,Left, Top,Right, Bottom,Left, Bottom,Right, Top,Left,Right, Bottom,Left,Right, Top,Bottom,Left, Top,Bottom,Right, Top,Bottom,Left,Right) | The Canvas edges it keeps its distance from as the form is resized: anchored to both sides, it stretches. Default `Top,Left`. |
| `Canvas.Left` | number | Its place on a Canvas: pixels from the left. |
| `Canvas.Top` | number | Its place on a Canvas: pixels from the top. |
| `DockPanel.Dock` | choice (Left, Top, Right, Bottom) | The side of a DockPanel it docks to. |
| `Grid.Column` | number | Its column in a Grid, from 0. |
| `Grid.ColumnSpan` | number | How many Grid columns it spans. |
| `Grid.Row` | number | Its row in a Grid, from 0. |
| `Grid.RowSpan` | number | How many Grid rows it spans. |

**Events:** `OnGotFocus`, `OnLostFocus`, `OnPointerMoved`, `OnPointerPressed`, `OnPointerReleased`

## Grid

*Containers* · holds other controls

Has the properties [every control](#every-control) has.

| Property | Kind | What it does |
|---|---|---|
| `Focusable` | true/false | Can take the keyboard. |
| `IsHitTestVisible` | true/false | Takes clicks (false: clicks go through to what's behind). Default `true`. |
| `ColumnDefinitions` | text | A Grid's columns, comma-separated. |
| `RowDefinitions` | text | A Grid's rows, comma-separated. |
| `Anchor` | choice (Top,Left, Top,Right, Bottom,Left, Bottom,Right, Top,Left,Right, Bottom,Left,Right, Top,Bottom,Left, Top,Bottom,Right, Top,Bottom,Left,Right) | The Canvas edges it keeps its distance from as the form is resized: anchored to both sides, it stretches. Default `Top,Left`. |
| `Canvas.Left` | number | Its place on a Canvas: pixels from the left. |
| `Canvas.Top` | number | Its place on a Canvas: pixels from the top. |
| `DockPanel.Dock` | choice (Left, Top, Right, Bottom) | The side of a DockPanel it docks to. |
| `Grid.Column` | number | Its column in a Grid, from 0. |
| `Grid.ColumnSpan` | number | How many Grid columns it spans. |
| `Grid.Row` | number | Its row in a Grid, from 0. |
| `Grid.RowSpan` | number | How many Grid rows it spans. |

**Events:** `OnGotFocus`, `OnLostFocus`, `OnPointerMoved`, `OnPointerPressed`, `OnPointerReleased`

## HyperlinkButton

*Common*

Has the properties [every control](#every-control) has, or most of them.

| Property | Kind | What it does |
|---|---|---|
| `Content` | text | What a button or check box says. |
| `NavigateUri` | text | The web page it opens (empty: it only runs OnClick). |
| `Anchor` | choice (Top,Left, Top,Right, Bottom,Left, Bottom,Right, Top,Left,Right, Bottom,Left,Right, Top,Bottom,Left, Top,Bottom,Right, Top,Bottom,Left,Right) | The Canvas edges it keeps its distance from as the form is resized: anchored to both sides, it stretches. Default `Top,Left`. |
| `Canvas.Left` | number | Its place on a Canvas: pixels from the left. |
| `Canvas.Top` | number | Its place on a Canvas: pixels from the top. |
| `DockPanel.Dock` | choice (Left, Top, Right, Bottom) | The side of a DockPanel it docks to. |
| `Grid.Column` | number | Its column in a Grid, from 0. |
| `Grid.ColumnSpan` | number | How many Grid columns it spans. |
| `Grid.Row` | number | Its row in a Grid, from 0. |
| `Grid.RowSpan` | number | How many Grid rows it spans. |

**Events:** `OnClick`

## Image

*Common*

Has the properties [every control](#every-control) has.

| Property | Kind | What it does |
|---|---|---|
| `Stretch` | choice (Uniform, Fill, UniformToFill, None) | How a picture fits its box: Uniform (all of it, in proportion), Fill, UniformToFill (fills it, cropped), None. |
| `Focusable` | true/false | Can take the keyboard. |
| `IsHitTestVisible` | true/false | Takes clicks (false: clicks go through to what's behind). Default `true`. |
| `Source` | text | A picture: a file beside the form, a web address, or a data: address. |
| `Anchor` | choice (Top,Left, Top,Right, Bottom,Left, Bottom,Right, Top,Left,Right, Bottom,Left,Right, Top,Bottom,Left, Top,Bottom,Right, Top,Bottom,Left,Right) | The Canvas edges it keeps its distance from as the form is resized: anchored to both sides, it stretches. Default `Top,Left`. |
| `Canvas.Left` | number | Its place on a Canvas: pixels from the left. |
| `Canvas.Top` | number | Its place on a Canvas: pixels from the top. |
| `DockPanel.Dock` | choice (Left, Top, Right, Bottom) | The side of a DockPanel it docks to. |
| `Grid.Column` | number | Its column in a Grid, from 0. |
| `Grid.ColumnSpan` | number | How many Grid columns it spans. |
| `Grid.Row` | number | Its row in a Grid, from 0. |
| `Grid.RowSpan` | number | How many Grid rows it spans. |

**Events:** `OnGotFocus`, `OnLostFocus`, `OnPointerMoved`, `OnPointerPressed`, `OnPointerReleased`

## ListBox

*Common*

Has the properties [every control](#every-control) has.

| Property | Kind | What it does |
|---|---|---|
| `AlternatingRows` | true/false | Every other row shaded, for easier reading. |
| `Focusable` | true/false | Can take the keyboard. |
| `IsHitTestVisible` | true/false | Takes clicks (false: clicks go through to what's behind). Default `true`. |
| `Items` | list | Its list, comma-separated: Items=Red,Green,Blue. |
| `SelectedIndex` | number | Which item is chosen, from 0 (-1: none). |
| `SelectedItem` | text | The chosen item (a DataGrid: its row, as JSON). |
| `Database` | text | Which opened database it asks; empty = the main one. |
| `ItemsSource` | text | A query (or a script) that fills the control: see vml/data.py. |
| `Anchor` | choice (Top,Left, Top,Right, Bottom,Left, Bottom,Right, Top,Left,Right, Bottom,Left,Right, Top,Bottom,Left, Top,Bottom,Right, Top,Bottom,Left,Right) | The Canvas edges it keeps its distance from as the form is resized: anchored to both sides, it stretches. Default `Top,Left`. |
| `Canvas.Left` | number | Its place on a Canvas: pixels from the left. |
| `Canvas.Top` | number | Its place on a Canvas: pixels from the top. |
| `DockPanel.Dock` | choice (Left, Top, Right, Bottom) | The side of a DockPanel it docks to. |
| `Grid.Column` | number | Its column in a Grid, from 0. |
| `Grid.ColumnSpan` | number | How many Grid columns it spans. |
| `Grid.Row` | number | Its row in a Grid, from 0. |
| `Grid.RowSpan` | number | How many Grid rows it spans. |

**Events:** `OnContextMenu`, `OnDoubleClick`, `OnKeyDown`, `OnKeyUp`, `SelectionChanged`

## MarkdownEditor

*Common*

Has the properties [every control](#every-control) has.

| Property | Kind | What it does |
|---|---|---|
| `ShowPreview` | true/false | How the Markdown looks, shown beside it as you type. Default `true`. |
| `Text` | text | The Markdown written in it. |
| `Anchor` | choice (Top,Left, Top,Right, Bottom,Left, Bottom,Right, Top,Left,Right, Bottom,Left,Right, Top,Bottom,Left, Top,Bottom,Right, Top,Bottom,Left,Right) | The Canvas edges it keeps its distance from as the form is resized: anchored to both sides, it stretches. Default `Top,Left`. |
| `Canvas.Left` | number | Its place on a Canvas: pixels from the left. |
| `Canvas.Top` | number | Its place on a Canvas: pixels from the top. |
| `DockPanel.Dock` | choice (Left, Top, Right, Bottom) | The side of a DockPanel it docks to. |
| `Grid.Column` | number | Its column in a Grid, from 0. |
| `Grid.ColumnSpan` | number | How many Grid columns it spans. |
| `Grid.Row` | number | Its row in a Grid, from 0. |
| `Grid.RowSpan` | number | How many Grid rows it spans. |

**Events:** `TextChanged`

## MarkdownView

*Common*

Has the properties [every control](#every-control) has.

| Property | Kind | What it does |
|---|---|---|
| `Source` | text | Where its Markdown comes from instead: a file, a web address, or help:Page for a page of Visualised's help. Links in it open in place. |
| `Text` | text | The Markdown it shows. In a form, write \\n for a new line. |
| `Anchor` | choice (Top,Left, Top,Right, Bottom,Left, Bottom,Right, Top,Left,Right, Bottom,Left,Right, Top,Bottom,Left, Top,Bottom,Right, Top,Bottom,Left,Right) | The Canvas edges it keeps its distance from as the form is resized: anchored to both sides, it stretches. Default `Top,Left`. |
| `Canvas.Left` | number | Its place on a Canvas: pixels from the left. |
| `Canvas.Top` | number | Its place on a Canvas: pixels from the top. |
| `DockPanel.Dock` | choice (Left, Top, Right, Bottom) | The side of a DockPanel it docks to. |
| `Grid.Column` | number | Its column in a Grid, from 0. |
| `Grid.ColumnSpan` | number | How many Grid columns it spans. |
| `Grid.Row` | number | Its row in a Grid, from 0. |
| `Grid.RowSpan` | number | How many Grid rows it spans. |

## MenuItem

*Menus* · holds other controls

Has the properties [every control](#every-control) has, or most of them.

| Property | Kind | What it does |
|---|---|---|
| `IsSeparator` | true/false | A line between menu items, instead of an item. |
| `Header` | text | The heading text. |
| `Shortcut` | text | A menu item's key, such as Ctrl+S. |
| `Text` | text | The text shown (or typed, in a TextBox). |

**Events:** `OnClick`

## MenuTheme

*Menus*

Has the properties [every control](#every-control) has, or most of them.

| Property | Kind | What it does |
|---|---|---|
| `PopupBackground` | colour | The background of the menus that drop down. |
| `PopupBorder` | colour | The edge of the menus that drop down. |

## NumberBox

*Common*

Has the properties [every control](#every-control) has.

| Property | Kind | What it does |
|---|---|---|
| `Decimals` | number | Places after the point (0: whole numbers). Default `0`. |
| `Maximum` | number | The highest its value can be. Default `100`. |
| `Minimum` | number | The lowest its value can be. Default `0`. |
| `Step` | number | How much each arrow adds or takes away. Default `1`. |
| `Value` | number | The number shown. Default `0`. |
| `Anchor` | choice (Top,Left, Top,Right, Bottom,Left, Bottom,Right, Top,Left,Right, Bottom,Left,Right, Top,Bottom,Left, Top,Bottom,Right, Top,Bottom,Left,Right) | The Canvas edges it keeps its distance from as the form is resized: anchored to both sides, it stretches. Default `Top,Left`. |
| `Canvas.Left` | number | Its place on a Canvas: pixels from the left. |
| `Canvas.Top` | number | Its place on a Canvas: pixels from the top. |
| `DockPanel.Dock` | choice (Left, Top, Right, Bottom) | The side of a DockPanel it docks to. |
| `Grid.Column` | number | Its column in a Grid, from 0. |
| `Grid.ColumnSpan` | number | How many Grid columns it spans. |
| `Grid.Row` | number | Its row in a Grid, from 0. |
| `Grid.RowSpan` | number | How many Grid rows it spans. |

**Events:** `ValueChanged`

## ProgressBar

*Common*

Has the properties [every control](#every-control) has.

| Property | Kind | What it does |
|---|---|---|
| `BarStyle` | choice (Solid, Blocks, Thin) | How the bar is drawn. Default `Solid`. |
| `Orientation` | choice (Horizontal, Vertical) | Vertical or Horizontal. Default `Horizontal`. |
| `ShowText` | true/false | The percentage, written on the bar. |
| `Focusable` | true/false | Can take the keyboard. |
| `IsHitTestVisible` | true/false | Takes clicks (false: clicks go through to what's behind). Default `true`. |
| `IsIndeterminate` | true/false | Busy, for work of unknown length. |
| `Maximum` | number | The highest its value can be. Default `100`. |
| `Minimum` | number | The lowest its value can be. Default `0`. |
| `Value` | number | Its value. Default `0`. |
| `Anchor` | choice (Top,Left, Top,Right, Bottom,Left, Bottom,Right, Top,Left,Right, Bottom,Left,Right, Top,Bottom,Left, Top,Bottom,Right, Top,Bottom,Left,Right) | The Canvas edges it keeps its distance from as the form is resized: anchored to both sides, it stretches. Default `Top,Left`. |
| `Canvas.Left` | number | Its place on a Canvas: pixels from the left. |
| `Canvas.Top` | number | Its place on a Canvas: pixels from the top. |
| `DockPanel.Dock` | choice (Left, Top, Right, Bottom) | The side of a DockPanel it docks to. |
| `Grid.Column` | number | Its column in a Grid, from 0. |
| `Grid.ColumnSpan` | number | How many Grid columns it spans. |
| `Grid.Row` | number | Its row in a Grid, from 0. |
| `Grid.RowSpan` | number | How many Grid rows it spans. |

**Events:** `OnGotFocus`, `OnLostFocus`, `OnPointerMoved`, `OnPointerPressed`, `OnPointerReleased`

## RadioButton

*Common*

Has the properties [every control](#every-control) has.

| Property | Kind | What it does |
|---|---|---|
| `Focusable` | true/false | Can take the keyboard. |
| `IsHitTestVisible` | true/false | Takes clicks (false: clicks go through to what's behind). Default `true`. |
| `Content` | text | What a button or check box says. |
| `GroupName` | text | Radio buttons with the same GroupName make one choice. |
| `IsChecked` | true/false | Ticked, or not. |
| `Anchor` | choice (Top,Left, Top,Right, Bottom,Left, Bottom,Right, Top,Left,Right, Bottom,Left,Right, Top,Bottom,Left, Top,Bottom,Right, Top,Bottom,Left,Right) | The Canvas edges it keeps its distance from as the form is resized: anchored to both sides, it stretches. Default `Top,Left`. |
| `Canvas.Left` | number | Its place on a Canvas: pixels from the left. |
| `Canvas.Top` | number | Its place on a Canvas: pixels from the top. |
| `DockPanel.Dock` | choice (Left, Top, Right, Bottom) | The side of a DockPanel it docks to. |
| `Grid.Column` | number | Its column in a Grid, from 0. |
| `Grid.ColumnSpan` | number | How many Grid columns it spans. |
| `Grid.Row` | number | Its row in a Grid, from 0. |
| `Grid.RowSpan` | number | How many Grid rows it spans. |

**Events:** `OnChecked`, `OnClick`, `OnGotFocus`, `OnKeyDown`, `OnKeyUp`, `OnLostFocus`, `OnPointerMoved`, `OnPointerPressed`, `OnPointerReleased`

## Rectangle

*Common*

Has the properties [every control](#every-control) has.

| Property | Kind | What it does |
|---|---|---|
| `Fill` | colour | A shape's colour. |
| `Stroke` | colour | A shape's edge colour. |
| `StrokeThickness` | number | A shape's edge width, in pixels. |
| `Focusable` | true/false | Can take the keyboard. |
| `IsHitTestVisible` | true/false | Takes clicks (false: clicks go through to what's behind). Default `true`. |
| `Anchor` | choice (Top,Left, Top,Right, Bottom,Left, Bottom,Right, Top,Left,Right, Bottom,Left,Right, Top,Bottom,Left, Top,Bottom,Right, Top,Bottom,Left,Right) | The Canvas edges it keeps its distance from as the form is resized: anchored to both sides, it stretches. Default `Top,Left`. |
| `Canvas.Left` | number | Its place on a Canvas: pixels from the left. |
| `Canvas.Top` | number | Its place on a Canvas: pixels from the top. |
| `DockPanel.Dock` | choice (Left, Top, Right, Bottom) | The side of a DockPanel it docks to. |
| `Grid.Column` | number | Its column in a Grid, from 0. |
| `Grid.ColumnSpan` | number | How many Grid columns it spans. |
| `Grid.Row` | number | Its row in a Grid, from 0. |
| `Grid.RowSpan` | number | How many Grid rows it spans. |

**Events:** `OnGotFocus`, `OnLostFocus`, `OnPointerMoved`, `OnPointerPressed`, `OnPointerReleased`

## ScrollViewer

*Containers* · holds other controls

Has the properties [every control](#every-control) has.

| Property | Kind | What it does |
|---|---|---|
| `Focusable` | true/false | Can take the keyboard. |
| `HorizontalScrollBarVisibility` | choice (Auto, Visible, Hidden, Disabled) | When the sideways scroll bar shows. |
| `IsHitTestVisible` | true/false | Takes clicks (false: clicks go through to what's behind). Default `true`. |
| `VerticalScrollBarVisibility` | choice (Auto, Visible, Hidden, Disabled) | When the up-and-down scroll bar shows. |
| `Anchor` | choice (Top,Left, Top,Right, Bottom,Left, Bottom,Right, Top,Left,Right, Bottom,Left,Right, Top,Bottom,Left, Top,Bottom,Right, Top,Bottom,Left,Right) | The Canvas edges it keeps its distance from as the form is resized: anchored to both sides, it stretches. Default `Top,Left`. |
| `Canvas.Left` | number | Its place on a Canvas: pixels from the left. |
| `Canvas.Top` | number | Its place on a Canvas: pixels from the top. |
| `DockPanel.Dock` | choice (Left, Top, Right, Bottom) | The side of a DockPanel it docks to. |
| `Grid.Column` | number | Its column in a Grid, from 0. |
| `Grid.ColumnSpan` | number | How many Grid columns it spans. |
| `Grid.Row` | number | Its row in a Grid, from 0. |
| `Grid.RowSpan` | number | How many Grid rows it spans. |

## Slider

*Common*

Has the properties [every control](#every-control) has, or most of them.

| Property | Kind | What it does |
|---|---|---|
| `Focusable` | true/false | Can take the keyboard. |
| `IsHitTestVisible` | true/false | Takes clicks (false: clicks go through to what's behind). Default `true`. |
| `Maximum` | number | The highest its value can be. Default `100`. |
| `Minimum` | number | The lowest its value can be. Default `0`. |
| `Value` | number | Its value. Default `0`. |
| `Anchor` | choice (Top,Left, Top,Right, Bottom,Left, Bottom,Right, Top,Left,Right, Bottom,Left,Right, Top,Bottom,Left, Top,Bottom,Right, Top,Bottom,Left,Right) | The Canvas edges it keeps its distance from as the form is resized: anchored to both sides, it stretches. Default `Top,Left`. |
| `Canvas.Left` | number | Its place on a Canvas: pixels from the left. |
| `Canvas.Top` | number | Its place on a Canvas: pixels from the top. |
| `DockPanel.Dock` | choice (Left, Top, Right, Bottom) | The side of a DockPanel it docks to. |
| `Grid.Column` | number | Its column in a Grid, from 0. |
| `Grid.ColumnSpan` | number | How many Grid columns it spans. |
| `Grid.Row` | number | Its row in a Grid, from 0. |
| `Grid.RowSpan` | number | How many Grid rows it spans. |

**Events:** `OnGotFocus`, `OnLostFocus`, `OnPointerMoved`, `OnPointerPressed`, `OnPointerReleased`, `ValueChanged`

## Splitter

*Common*

Has the properties [every control](#every-control) has.

| Property | Kind | What it does |
|---|---|---|
| `Thickness` | number | How wide the bar is, in pixels. |
| `Focusable` | true/false | Can take the keyboard. |
| `IsHitTestVisible` | true/false | Takes clicks (false: clicks go through to what's behind). Default `true`. |
| `MinSize` | number | The smallest either side may become (60) |
| `Target` | text | The pane it resizes; empty = the one docked just before it. |
| `Anchor` | choice (Top,Left, Top,Right, Bottom,Left, Bottom,Right, Top,Left,Right, Bottom,Left,Right, Top,Bottom,Left, Top,Bottom,Right, Top,Bottom,Left,Right) | The Canvas edges it keeps its distance from as the form is resized: anchored to both sides, it stretches. Default `Top,Left`. |
| `Canvas.Left` | number | Its place on a Canvas: pixels from the left. |
| `Canvas.Top` | number | Its place on a Canvas: pixels from the top. |
| `DockPanel.Dock` | choice (Left, Top, Right, Bottom) | The side of a DockPanel it docks to. |
| `Grid.Column` | number | Its column in a Grid, from 0. |
| `Grid.ColumnSpan` | number | How many Grid columns it spans. |
| `Grid.Row` | number | Its row in a Grid, from 0. |
| `Grid.RowSpan` | number | How many Grid rows it spans. |

**Events:** `OnMoved`

## StackPanel

*Containers* · holds other controls

Has the properties [every control](#every-control) has.

| Property | Kind | What it does |
|---|---|---|
| `Focusable` | true/false | Can take the keyboard. |
| `IsHitTestVisible` | true/false | Takes clicks (false: clicks go through to what's behind). Default `true`. |
| `Orientation` | choice (Vertical, Horizontal) | Vertical or Horizontal. |
| `Padding` | thickness | Space inside it, between its edge and what it holds: one number, or left,top,right,bottom. |
| `Spacing` | number | The gap between the controls it holds, in pixels. |
| `Anchor` | choice (Top,Left, Top,Right, Bottom,Left, Bottom,Right, Top,Left,Right, Bottom,Left,Right, Top,Bottom,Left, Top,Bottom,Right, Top,Bottom,Left,Right) | The Canvas edges it keeps its distance from as the form is resized: anchored to both sides, it stretches. Default `Top,Left`. |
| `Canvas.Left` | number | Its place on a Canvas: pixels from the left. |
| `Canvas.Top` | number | Its place on a Canvas: pixels from the top. |
| `DockPanel.Dock` | choice (Left, Top, Right, Bottom) | The side of a DockPanel it docks to. |
| `Grid.Column` | number | Its column in a Grid, from 0. |
| `Grid.ColumnSpan` | number | How many Grid columns it spans. |
| `Grid.Row` | number | Its row in a Grid, from 0. |
| `Grid.RowSpan` | number | How many Grid rows it spans. |

**Events:** `OnGotFocus`, `OnLostFocus`, `OnPointerMoved`, `OnPointerPressed`, `OnPointerReleased`

## TextBlock

*Common*

Has the properties [every control](#every-control) has.

| Property | Kind | What it does |
|---|---|---|
| `Focusable` | true/false | Can take the keyboard. |
| `IsHitTestVisible` | true/false | Takes clicks (false: clicks go through to what's behind). Default `true`. |
| `Text` | text | The text shown (or typed, in a TextBox). |
| `Padding` | thickness | Space inside it, between its edge and what it holds: one number, or left,top,right,bottom. |
| `Anchor` | choice (Top,Left, Top,Right, Bottom,Left, Bottom,Right, Top,Left,Right, Bottom,Left,Right, Top,Bottom,Left, Top,Bottom,Right, Top,Bottom,Left,Right) | The Canvas edges it keeps its distance from as the form is resized: anchored to both sides, it stretches. Default `Top,Left`. |
| `Canvas.Left` | number | Its place on a Canvas: pixels from the left. |
| `Canvas.Top` | number | Its place on a Canvas: pixels from the top. |
| `DockPanel.Dock` | choice (Left, Top, Right, Bottom) | The side of a DockPanel it docks to. |
| `Grid.Column` | number | Its column in a Grid, from 0. |
| `Grid.ColumnSpan` | number | How many Grid columns it spans. |
| `Grid.Row` | number | Its row in a Grid, from 0. |
| `Grid.RowSpan` | number | How many Grid rows it spans. |
| `TextAlignment` | choice (Left, Center, Right) | Left, Center or Right. |
| `TextWrapping` | choice (NoWrap, Wrap) | Wrap: long text runs onto more lines. NoWrap: one line. |

**Events:** `OnGotFocus`, `OnLostFocus`, `OnPointerMoved`, `OnPointerPressed`, `OnPointerReleased`

## TextBox

*Common*

Has the properties [every control](#every-control) has.

| Property | Kind | What it does |
|---|---|---|
| `AcceptsReturn` | true/false | A box of several lines: Enter starts a new line. |
| `Focusable` | true/false | Can take the keyboard. |
| `IsHitTestVisible` | true/false | Takes clicks (false: clicks go through to what's behind). Default `true`. |
| `IsPassword` | true/false | Dots instead of what is typed. |
| `IsReadOnly` | true/false | Can be read and selected, but not changed. |
| `Text` | text | The text shown (or typed, in a TextBox). |
| `Watermark` | text | Grey hint text, shown while the box is empty. |
| `Padding` | thickness | Space inside it, between its edge and what it holds: one number, or left,top,right,bottom. |
| `Anchor` | choice (Top,Left, Top,Right, Bottom,Left, Bottom,Right, Top,Left,Right, Bottom,Left,Right, Top,Bottom,Left, Top,Bottom,Right, Top,Bottom,Left,Right) | The Canvas edges it keeps its distance from as the form is resized: anchored to both sides, it stretches. Default `Top,Left`. |
| `Canvas.Left` | number | Its place on a Canvas: pixels from the left. |
| `Canvas.Top` | number | Its place on a Canvas: pixels from the top. |
| `DockPanel.Dock` | choice (Left, Top, Right, Bottom) | The side of a DockPanel it docks to. |
| `Grid.Column` | number | Its column in a Grid, from 0. |
| `Grid.ColumnSpan` | number | How many Grid columns it spans. |
| `Grid.Row` | number | Its row in a Grid, from 0. |
| `Grid.RowSpan` | number | How many Grid rows it spans. |
| `TextWrapping` | choice (Wrap, NoWrap) | Wrap: long text runs onto more lines. NoWrap: one line. |

**Events:** `OnGotFocus`, `OnKeyDown`, `OnKeyUp`, `OnLostFocus`, `OnPointerMoved`, `OnPointerPressed`, `OnPointerReleased`, `TextChanged`

## TimePicker

*Common*

Has the properties [every control](#every-control) has.

| Property | Kind | What it does |
|---|---|---|
| `Value` | text | The time chosen, 24-hour: 14:30. |
| `Anchor` | choice (Top,Left, Top,Right, Bottom,Left, Bottom,Right, Top,Left,Right, Bottom,Left,Right, Top,Bottom,Left, Top,Bottom,Right, Top,Bottom,Left,Right) | The Canvas edges it keeps its distance from as the form is resized: anchored to both sides, it stretches. Default `Top,Left`. |
| `Canvas.Left` | number | Its place on a Canvas: pixels from the left. |
| `Canvas.Top` | number | Its place on a Canvas: pixels from the top. |
| `DockPanel.Dock` | choice (Left, Top, Right, Bottom) | The side of a DockPanel it docks to. |
| `Grid.Column` | number | Its column in a Grid, from 0. |
| `Grid.ColumnSpan` | number | How many Grid columns it spans. |
| `Grid.Row` | number | Its row in a Grid, from 0. |
| `Grid.RowSpan` | number | How many Grid rows it spans. |

**Events:** `ValueChanged`

## Timer

*Common*

Has the properties [every control](#every-control) has, or most of them.

| Property | Kind | What it does |
|---|---|---|
| `Focusable` | true/false | Can take the keyboard. |
| `Interval` | number | Milliseconds between ticks. Default `1000`. |
| `IsHitTestVisible` | true/false | Takes clicks (false: clicks go through to what's behind). Default `true`. |
| `Anchor` | choice (Top,Left, Top,Right, Bottom,Left, Bottom,Right, Top,Left,Right, Bottom,Left,Right, Top,Bottom,Left, Top,Bottom,Right, Top,Bottom,Left,Right) | The Canvas edges it keeps its distance from as the form is resized: anchored to both sides, it stretches. Default `Top,Left`. |
| `Canvas.Left` | number | Its place on a Canvas: pixels from the left. |
| `Canvas.Top` | number | Its place on a Canvas: pixels from the top. |
| `DockPanel.Dock` | choice (Left, Top, Right, Bottom) | The side of a DockPanel it docks to. |
| `Grid.Column` | number | Its column in a Grid, from 0. |
| `Grid.ColumnSpan` | number | How many Grid columns it spans. |
| `Grid.Row` | number | Its row in a Grid, from 0. |
| `Grid.RowSpan` | number | How many Grid rows it spans. |

**Events:** `OnTick`

## TinyMenu

*Menus*

Has the properties [every control](#every-control) has.

| Property | Kind | What it does |
|---|---|---|
| `Focusable` | true/false | Can take the keyboard. |
| `IsHitTestVisible` | true/false | Takes clicks (false: clicks go through to what's behind). Default `true`. |
| `OpenOnHover` | true/false | The menus open as the pointer passes over them. |
| `Anchor` | choice (Top,Left, Top,Right, Bottom,Left, Bottom,Right, Top,Left,Right, Bottom,Left,Right, Top,Bottom,Left, Top,Bottom,Right, Top,Bottom,Left,Right) | The Canvas edges it keeps its distance from as the form is resized: anchored to both sides, it stretches. Default `Top,Left`. |
| `Canvas.Left` | number | Its place on a Canvas: pixels from the left. |
| `Canvas.Top` | number | Its place on a Canvas: pixels from the top. |
| `DockPanel.Dock` | choice (Left, Top, Right, Bottom) | The side of a DockPanel it docks to. |
| `Grid.Column` | number | Its column in a Grid, from 0. |
| `Grid.ColumnSpan` | number | How many Grid columns it spans. |
| `Grid.Row` | number | Its row in a Grid, from 0. |
| `Grid.RowSpan` | number | How many Grid rows it spans. |

## ToggleButton

*Common*

Has the properties [every control](#every-control) has.

| Property | Kind | What it does |
|---|---|---|
| `Content` | text | What a button or check box says. |
| `IsChecked` | true/false | Ticked, or not. |
| `Anchor` | choice (Top,Left, Top,Right, Bottom,Left, Bottom,Right, Top,Left,Right, Bottom,Left,Right, Top,Bottom,Left, Top,Bottom,Right, Top,Bottom,Left,Right) | The Canvas edges it keeps its distance from as the form is resized: anchored to both sides, it stretches. Default `Top,Left`. |
| `Canvas.Left` | number | Its place on a Canvas: pixels from the left. |
| `Canvas.Top` | number | Its place on a Canvas: pixels from the top. |
| `DockPanel.Dock` | choice (Left, Top, Right, Bottom) | The side of a DockPanel it docks to. |
| `Grid.Column` | number | Its column in a Grid, from 0. |
| `Grid.ColumnSpan` | number | How many Grid columns it spans. |
| `Grid.Row` | number | Its row in a Grid, from 0. |
| `Grid.RowSpan` | number | How many Grid rows it spans. |

**Events:** `OnClick`, `ValueChanged`

## ToggleSwitch

*Common*

Has the properties [every control](#every-control) has.

| Property | Kind | What it does |
|---|---|---|
| `Accent` | colour | The switch's colour when on. |
| `Content` | text | What a button or check box says. |
| `IsChecked` | true/false | Ticked, or not. |
| `Anchor` | choice (Top,Left, Top,Right, Bottom,Left, Bottom,Right, Top,Left,Right, Bottom,Left,Right, Top,Bottom,Left, Top,Bottom,Right, Top,Bottom,Left,Right) | The Canvas edges it keeps its distance from as the form is resized: anchored to both sides, it stretches. Default `Top,Left`. |
| `Canvas.Left` | number | Its place on a Canvas: pixels from the left. |
| `Canvas.Top` | number | Its place on a Canvas: pixels from the top. |
| `DockPanel.Dock` | choice (Left, Top, Right, Bottom) | The side of a DockPanel it docks to. |
| `Grid.Column` | number | Its column in a Grid, from 0. |
| `Grid.ColumnSpan` | number | How many Grid columns it spans. |
| `Grid.Row` | number | Its row in a Grid, from 0. |
| `Grid.RowSpan` | number | How many Grid rows it spans. |

**Events:** `ValueChanged`

## TreeView

*Common*

Has the properties [every control](#every-control) has.

| Property | Kind | What it does |
|---|---|---|
| `Focusable` | true/false | Can take the keyboard. |
| `IsExpanded` | true/false | Its items shown open. Default `true`. |
| `IsHitTestVisible` | true/false | Takes clicks (false: clicks go through to what's behind). Default `true`. |
| `Items` | list | Its list, comma-separated: Items=Red,Green,Blue. |
| `SelectedItem` | text | The chosen item (a DataGrid: its row, as JSON). |
| `Database` | text | Which opened database it asks; empty = the main one. |
| `ItemsSource` | text | A query (or a script) that fills the control: see vml/data.py. |
| `Anchor` | choice (Top,Left, Top,Right, Bottom,Left, Bottom,Right, Top,Left,Right, Bottom,Left,Right, Top,Bottom,Left, Top,Bottom,Right, Top,Bottom,Left,Right) | The Canvas edges it keeps its distance from as the form is resized: anchored to both sides, it stretches. Default `Top,Left`. |
| `Canvas.Left` | number | Its place on a Canvas: pixels from the left. |
| `Canvas.Top` | number | Its place on a Canvas: pixels from the top. |
| `DockPanel.Dock` | choice (Left, Top, Right, Bottom) | The side of a DockPanel it docks to. |
| `Grid.Column` | number | Its column in a Grid, from 0. |
| `Grid.ColumnSpan` | number | How many Grid columns it spans. |
| `Grid.Row` | number | Its row in a Grid, from 0. |
| `Grid.RowSpan` | number | How many Grid rows it spans. |

**Events:** `OnContextMenu`, `OnDoubleClick`, `OnKeyDown`, `OnKeyUp`, `SelectionChanged`

## Window

*Containers* · holds other controls

Has the properties [every control](#every-control) has.

| Property | Kind | What it does |
|---|---|---|
| `AppBar` | true/false | Terms · About · version along the foot, with ⚠ when there's a newer one: vml/appbar.py. Default `false`. |
| `LinkPass` | text | Put in by Visualised Pro when it saves an app that uses Link: see vml/link.py. |
| `Modal` | true/false | Opened as a dialog: the rest of the app waits until it closes. Default `false`. |
| `PhoneFit` | choice (Fit, None) | On a phone: Fit scales the form to the screen's width; None leaves it at its own size. |
| `Resizable` | true/false | Applied by the engine when shown. Default `true`. |
| `WindowState` | choice (Normal, Maximized, Auto, FullScreen) | How it opens on a computer: Normal (its own size), Maximized, FullScreen, or Auto: maximised on an HD screen (1920 wide) or smaller, its own size on a bigger one. |
| `WebFit` | choice (Window, Fill) | As a web page on a phone: scale to the screen's width, or leave alone. |
| `About` | text | A line or two for its About box. |
| `AndroidKey` | text | Which signing key it was last exported with: put in by the export. |
| `AndroidPackage` | text | Its package name as an Android app, to choose one's own (com.example.myapp) |
| `Icon` | text | A picture for the app: its icon on a phone, and its window's and tray's here. |
| `Terms` | text | The app bar's Terms link. |
| `Title` | text | The window's title. |
| `UpdateApk` | text | And of its phone app (an .apk's address) |
| `UpdateFrom` | text | Where the newest copy of this form is (a .vml's address) |
| `Version` | text | The app's own version; a phone shows it beside the app. |
| `WebAddress` | text | Where the app is on the web, if it is: LinkAddress builds on it. |
| `MaxHeight` | number | The tallest it can be, in pixels. |
| `MaxWidth` | number | The widest it can be, in pixels. |

**Events:** `OnClosing`, `OnKeyDown`, `OnKeyUp`, `OnOpened`
