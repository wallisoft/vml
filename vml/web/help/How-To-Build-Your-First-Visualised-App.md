# How To Build Your First Visualised App

## Introduction

A Visualised app is one readable text file, a `.vml` form. It lists the controls on the form, with their properties, and the scripts that run when something happens. The same file runs as a desktop app on Windows and Linux, as a web page, and as an Android app.

In this tutorial you'll build a small tip calculator: type the bill, pick a tip, press the button, see the total. On the way you'll learn how a form is laid out, how a control's events run a script, and how a script reads and changes the form with `Vml()`.

## Prerequisites

- Visualised installed: [visualised.io](https://visualised.io/#download) (Windows installer or Microsoft Store, or the one-line Linux installer).
- Any text editor. You can also build the same form by dragging controls in the designer; this tutorial uses the text so you can see exactly what's there.

## Step 1: Make the form

Create a file called `TipCalc.vml` and put this in it:

```
@Window TipCalc
Title=Tip Calculator
Width=320
Height=260
Version=1.0.0

@Canvas c
Parent=TipCalc
Background=#F8FAFC

@TextBlock lblBill
Parent=c
Canvas.Left=20
Canvas.Top=20
Width=120
Height=30
Text=Bill (£)

@TextBox txtBill
Parent=c
Canvas.Left=150
Canvas.Top=20
Width=150
Height=30
Text=40

@TextBlock lblTip
Parent=c
Canvas.Left=20
Canvas.Top=64
Width=120
Height=30
Text=Tip

@ComboBox cboTip
Parent=c
Canvas.Left=150
Canvas.Top=64
Width=150
Height=30
Items=10%,12.5%,15%,20%
SelectedIndex=1

@Button btnWork
Parent=c
Canvas.Left=20
Canvas.Top=112
Width=280
Height=40
Content=Work it out
OnClick=WorkItOut

@TextBlock lblAnswer
Parent=c
Canvas.Left=20
Canvas.Top=168
Width=280
Height=60
FontSize=18
TextWrapping=Wrap
Text=
```

Every block starts with `@Type Name` and lists its properties underneath, one per line. A few things to notice:

- `@Window` is the form itself: its title, size and version.
- `@Canvas` is the surface the controls sit on. `Parent=` says what each control belongs to.
- `Canvas.Left` and `Canvas.Top` place a control; `Width` and `Height` size it, in pixels.
- `OnClick=WorkItOut` on the button names the script to run when it's pressed. You'll write it next.

## Step 2: Add the script

Add this to the end of the same file:

```
@Script WorkItOut
Interpreter=lua
<<LUA
local bill = tonumber(Vml("GetProperty", "txtBill", "Text")) or 0
local tip = tonumber((Vml("GetProperty", "cboTip", "SelectedItem"):gsub("%%", ""))) or 0
local extra = bill * tip / 100
Vml("SetProperty", "lblAnswer", "Text", string.format("Tip £%.2f\nTotal £%.2f", extra, bill + extra))
LUA
```

The script is ordinary Lua. `Vml()` is how it talks to the form:

- `Vml("GetProperty", "txtBill", "Text")` reads what's typed in the box.
- `Vml("SetProperty", "lblAnswer", "Text", ...)` changes the answer label.

Everything is a property: any property you can set in the file, a script can read and change while the app runs.

## Step 3: Run it

Open `TipCalc.vml` with Visualised: double-click it, or on Linux from a terminal:

```
vml TipCalc.vml
```

Press **Work it out**. With the bill at 40 and the tip at 12.5%, the label shows:

```
Tip £5.00
Total £45.00
```

Change the bill or the tip and press it again.

## Step 4: Try it as a web page

The same file makes a web page, with nothing to change:

```
vml html TipCalc.vml TipCalc.html --open
```

Your browser opens the calculator, working exactly as on the desktop. It's one self-contained file you can put on any website: see [How To Put Your App on the Web](How-To-Put-Your-App-on-the-Web).

## Conclusion

You've built a form, wired a button to a script, and read and changed controls with `Vml()`. That's the whole pattern: everything else is more controls, more properties and more `Vml()` commands.

Next:
- [How To Style Controls with CSS](How-To-Style-Controls-with-CSS), to make it look the part.
- [How To Build an App with Several Forms](How-To-Build-an-App-with-Several-Forms), when one form isn't enough.
