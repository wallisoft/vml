# How To Debug Your Scripts

## Introduction

The debugger shows what your app's scripts are doing while they do it: every `Vml()` call with its form, script and result, the errors in red, and each form's variables, live. It has a line where you can run Lua inside a running form, and break mode, as Visual Basic had it: breakpoints, then Step Into, Step Over and Step Out, a line at a time, with the script's locals and call stack in front of you. And it can attach to any Visualised app already running on your computer.

## Prerequisites

- An app to try it on, such as the contacts app from [How To Build an App with Several Forms](How-To-Build-an-App-with-Several-Forms).

## Step 1: Open it

Run your app from the designer (**Preview**, or **Run Project**), then press **F12**, in the designer or in the running app. **Tools > Debugger** does the same.

An app that's running on its own (started from its icon, a `.vml` double-clicked, Bob, Mountie) has no F12, but you can still debug it: in the designer, **Tools > Attach the debugger to a running app...**. With one app running it attaches straight away; with several, choose from the list. Everything below works the same on an attached app.

## Step 2: Watch the calls

Use the app. The **Calls** tab fills as it goes:

```
10:24:01.240  frmMain  AddContact  FormOpenModal("frmEdit")                 Ada Lovelace
10:24:01.252  frmMain  AddContact  SetProperty("lstNames", "Items", "...")
```

- A call that failed is red, with what went wrong: `SetProperty("lblMissing", "Text", "oops")` → `no control called 'lblMissing'`. Mistyped control names are the most common bug, and this finds them at once.
- **Filter** narrows the list to a command, a control or a script. **Errors only** and **Include GetProperty** cut the noise. **Pause** freezes it while you read.

## Step 3: Look at the variables

The **Variables** tab shows a running form's Lua globals: numbers, text, true/false and tables (open a table to see inside it), refreshed every second. The shared `Project` table is at the top.

## Step 4: Run a line of Lua

Below the variables, type Lua and press Enter. It runs in the chosen form:

```
#Names
Names[1]
Vml("GetProperty", "lstNames", "SelectedItem")
count = 0
```

An expression shows its value; anything else runs and the variables refresh.

## Step 5: Stop at a breakpoint

A breakpoint is a line where a script stops, before running it, so you can look around. Two ways to set one:

- In the **Script Editor** (double-click a control): click in the margin beside the line. A red dot appears.
- In the debugger's **Stepping** tab: pick the script and double-click the line.

They're the same breakpoints: set one either way and both show it. A module's functions (a project's `.lua` files) can have them too.

Now use the app. When a script reaches the line, it stops, and the debugger comes to the front on **Stepping**:

- the script, with the line it's stopped on in **yellow**
- **Locals**: the script's own variables (its `local`s) and their values just then
- **Call stack**: how it got there, newest first: `Square, line 6` ← `AddUp, line 4`. Double-click one to see that place.

While it's stopped, the app waits: its clicks and timers are held, so nothing runs into the middle of a script. The windows still draw.

## Step 6: Step through it

| Button | Key | What it does |
|---|---|---|
| **Step into** | F8 | Run one line. If it calls another script (`Vml("RunScript", ...)`) or a function, stop at that one's first line. |
| **Step over** | Shift+F8 | Run one line, and anything it calls, without stopping inside. |
| **Step out** | Ctrl+Shift+F8 | Run to the end of this script and stop where it was called from. |
| **Continue** | F5 | Run on, to the next breakpoint. |

**Change things while it's stopped.** The **Variables** tab's Lua line runs while the script waits, like VB's Immediate window: type `count = 100`, press Enter, then **Continue**, and the script carries on with 100. (That's a form's global variables; a `local` shows in Locals but can't be changed yet.)

**Try it**: `apps/BreakDemo.vml` adds up the squares of 1 to 4. Run it, put a breakpoint on line 4 of its **AddUp** script, press **Add them up**, and step in and out of `Square`.

Good to know:

- Breakpoints work in Lua. Scripts in Python, Bash, PowerShell or C# run as programs of their own, so they aren't stepped, though their `Vml()` calls still show in **Calls**.
- Breakpoints last until Visualised closes. **Clear breakpoints** on the Stepping tab takes them all away.
- With no breakpoints set, scripts run at full speed: Lua is only watched line by line while there's something to stop at.
- Closing the debugger while a script is stopped lets it carry on.

## Conclusion

Calls show what your scripts asked for and what they got; Variables show what they remember; a breakpoint and a few F8s show exactly how they got there. Between them, most bugs show themselves within a minute.

Next: [How To Style Controls with CSS](How-To-Style-Controls-with-CSS).
