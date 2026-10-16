# How To Let People Pick Dates, Colours and More

## Introduction

Typing a date or a colour code is fiddly and easy to get wrong. **Pickers** let people choose instead: a calendar for a date, a colour box for a colour, arrows for a number, a switch for on and off. Each one hands your script a tidy value (`2026-10-16`, `#4F46E5`, `14:30`), so there's nothing to check or convert.

On the desktop they're Visualised's own controls; on the web and on phones they're the browser's, so a phone shows its own date and time pickers.

| Control | What it's for | Its value |
|---|---|---|
| `ColorPicker` | a colour | `Value=#4F46E5` |
| `DatePicker` | a date, from a drop-down calendar | `Value=2026-10-16` |
| `Calendar` | a date, from a calendar that's always open | `Value=2026-10-16` |
| `TimePicker` | a time of day | `Value=14:30` |
| `NumberBox` | a number, typed or stepped | `Value=2.5` (and `Minimum`, `Maximum`, `Step`, `Decimals`) |
| `ToggleSwitch` | on or off | `IsChecked=true` |
| `ToggleButton` | a button that stays in or out | `IsChecked=true` |
| `AutoCompleteBox` | text, with suggestions as you type | `Text=Lewes` (suggestions in `Items`) |
| `HyperlinkButton` | a link to a web page | `NavigateUri=https://...` |

Every one runs **`ValueChanged`** when the user changes it.

## Prerequisites

- Visualised 1.2 or later.
- [How To Build Your First Visualised App](How-To-Build-Your-First-Visualised-App), or the same basics.

## Step 1: Pick a colour, a date, a time and a number

`Pickers.vml`:

```
@Window Pickers
Title=Pickers
Width=340
Height=330
Background=#F8FAFC

@Canvas c
Parent=Pickers

@ColorPicker colTheme
Parent=c
Canvas.Left=20
Canvas.Top=20
Width=150
Height=30
Value=#4F46E5
ValueChanged=Show

@DatePicker datDue
Parent=c
Canvas.Left=20
Canvas.Top=64
Width=150
Height=30
Value=2026-10-16
ValueChanged=Show

@TimePicker timAt
Parent=c
Canvas.Left=190
Canvas.Top=64
Width=130
Height=30
Value=14:30
ValueChanged=Show

@NumberBox numQty
Parent=c
Canvas.Left=20
Canvas.Top=108
Width=150
Height=30
Minimum=0
Maximum=10
Step=0.5
Decimals=1
Value=2.5
ValueChanged=Show

@ToggleSwitch tglOn
Parent=c
Canvas.Left=20
Canvas.Top=152
Width=200
Height=30
Content=Remind me
IsChecked=true
ValueChanged=Show

@TextBlock lblOut
Parent=c
Canvas.Left=20
Canvas.Top=200
Width=300
Height=110
TextWrapping=Wrap
FontSize=13
Text=

@Script Show
Interpreter=lua
<<LUA
local g = function(n, p) return Vml("GetProperty", n, p or "Value") end
Vml("SetProperty", "lblOut", "Text", "colour " .. g("colTheme") .. "\ndate " .. g("datDue") .. " at " .. g("timAt")
  .. "\nquantity " .. g("numQty") .. "\nremind " .. g("tglOn", "IsChecked"))
LUA
```

Every picker runs the same `Show` script when it changes; the script reads each one's `Value` (or `IsChecked`) and writes them out.

## Step 2: Try it

Open `Pickers.vml`. Change the date to Christmas Day, the time to 09:05, the quantity to 7.5 and turn the switch off. The label reads:

```
colour #4F46E5
date 2026-12-25 at 09:05
quantity 7.5
remind false
```

Click the colour swatch to open the colour box. Then make it a web page (`vml html Pickers.vml --open`) and do the same in the browser.

## Step 3: A calendar, suggestions, a toggle and a link

`More.vml`:

```
@Window More
Title=More controls
Width=360
Height=420
Background=#F8FAFC

@Canvas c
Parent=More

@Calendar calDay
Parent=c
Canvas.Left=20
Canvas.Top=16
Width=320
Height=220
Value=2026-10-16
ValueChanged=Show

@AutoCompleteBox acCity
Parent=c
Canvas.Left=20
Canvas.Top=250
Width=200
Height=30
Items=Eastbourne,Brighton,Hastings,Lewes,Bexhill
Watermark=Town
ValueChanged=Show

@ToggleButton tbBold
Parent=c
Canvas.Left=232
Canvas.Top=250
Width=108
Height=30
Content=Bold
ValueChanged=Show

@HyperlinkButton lnkHelp
Parent=c
Canvas.Left=20
Canvas.Top=292
Width=200
Height=24
Content=Visualised help
NavigateUri=https://github.com/wallisoft/vml/wiki

@TextBlock lblOut
Parent=c
Canvas.Left=20
Canvas.Top=326
Width=320
Height=80
TextWrapping=Wrap
FontSize=13
Text=

@Script Show
Interpreter=lua
<<LUA
Vml("SetProperty", "lblOut", "Text", "day " .. Vml("GetProperty", "calDay", "Value") .. "\ntown " .. Vml("GetProperty", "acCity", "Text")
  .. "\nbold " .. Vml("GetProperty", "tbBold", "IsChecked"))
Vml("SetProperty", "lblOut", "FontWeight", Vml("GetProperty", "tbBold", "IsChecked") == "true" and "Bold" or "Normal")
LUA
```

- The **Calendar** stays open: click a day, or the arrows for another month.
- The **AutoCompleteBox** suggests from its `Items` as you type: type `le` and pick *Lewes*. `ValueChanged` runs when a suggestion is picked; `TextChanged` runs on every key.
- The **ToggleButton** stays pressed in until it's clicked again; here it makes the label bold.
- The **HyperlinkButton** opens its `NavigateUri` in the browser. Leave `NavigateUri` empty and give it an `OnClick` instead to make a link that runs a script.

## Step 4: Set them from a script

They're properties like any other:

```
Vml("SetProperty", "datDue", "Value", os.date("%Y-%m-%d"))      -- today
Vml("SetProperty", "colTheme", "Value", "#10B981")
Vml("SetProperty", "numQty", "Maximum", "20")
Vml("SetProperty", "tglOn", "IsChecked", "false")
```

Setting a value from a script doesn't run `ValueChanged`: only the user changing it does.

## Conclusion

Pickers save your users typing and save your scripts checking. Every property is listed in the [controls reference](Reference-Controls).

Next: [How To Style Controls with CSS](How-To-Style-Controls-with-CSS).
