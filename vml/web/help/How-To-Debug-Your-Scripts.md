# How To Debug Your Scripts

## Introduction

The debugger shows what your app's scripts are doing while they do it: every `Vml()` call with its form, script and result, the errors in red, and each form's variables, live. It also has a line where you can run Lua inside a running form.

## Prerequisites

- An app to try it on, such as the contacts app from [How To Build an App with Several Forms](How-To-Build-an-App-with-Several-Forms).

## Step 1: Open it

Run your app from the designer (**Preview**, or **Run Project**), then press **F12**, in the designer or in the running app.

(F12 only does this when the designer is running your app. An app run on its own doesn't open a debugger.)

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

## Conclusion

Calls show what your scripts asked for and what they got; Variables show what they remember. Between the two, most bugs show themselves within a minute.

Next: [How To Style Controls with CSS](How-To-Style-Controls-with-CSS).
