# How To Build an App with Several Forms

## Introduction

When an app outgrows one form, make it a **project**: one small `.vmlproj` file that lists the app's forms and its **modules** (Lua files of shared functions). Forms open each other by name, pass answers back, and share values through the `Project` table.

In this tutorial you'll build a small contacts app: a main form with a list, and an edit form that asks for a name and hands it back.

## Prerequisites

- Visualised installed.
- [How To Build Your First Visualised App](How-To-Build-Your-First-Visualised-App), or the same basics.

## Step 1: Make the project file

Make a folder called `Contacts`, and in it `Contacts.vmlproj`:

```
# Visualised project
Name=Contacts
Startup=frmMain.vml
Form=frmMain.vml
Form=frmEdit.vml
Module=common.lua
```

`Startup=` is the form the app opens with. Every form and module the app uses is listed.

## Step 2: Write a shared module

`common.lua`. Every form in the project can call its functions:

```
-- shared by every form in the project
function Tidy(name)
  return (name:gsub("^%s+", ""):gsub("%s+$", ""):gsub("%s+", " "))
end
```

## Step 3: Make the main form

`frmMain.vml`:

```
@Window frmMain
Title=Contacts
Width=320
Height=300

@Canvas c
Parent=frmMain

@ListBox lstNames
Parent=c
Canvas.Left=20
Canvas.Top=20
Width=280
Height=190

@Button btnAdd
Parent=c
Canvas.Left=20
Canvas.Top=226
Width=280
Height=40
Content=Add a contact
OnClick=AddContact

@Script AddContact
Interpreter=lua
<<LUA
local name = Vml("FormOpenModal", "frmEdit")
if name ~= "" then
  Names = Names or {}
  Names[#Names + 1] = name
  Vml("SetProperty", "lstNames", "Items", table.concat(Names, ","))
  Project.count = #Names
end
LUA
```

- `Vml("FormOpenModal", "frmEdit")` opens the other form by its name and waits until it closes, then gives back its answer.
- `Names` is a global of this form's own: each form keeps its own Lua variables.
- `Project.count` is shared by every form in the app.

## Step 4: Make the edit form

`frmEdit.vml`:

```
@Window frmEdit
Title=New contact
Width=300
Height=150

@Canvas c
Parent=frmEdit

@TextBox txtName
Parent=c
Canvas.Left=20
Canvas.Top=20
Width=260
Height=32
Watermark=Their name

@Button btnOK
Parent=c
Canvas.Left=20
Canvas.Top=70
Width=260
Height=40
Content=OK
OnClick=Save

@Script Save
Interpreter=lua
<<LUA
Vml("SetDialogResult", Tidy(Vml("GetProperty", "txtName", "Text") or ""))
Vml("CloseForm", "frmEdit")
LUA
```

`Tidy()` comes from the module. `SetDialogResult` is the answer the main form receives.

## Step 5: Run it

Open the project: double-click `Contacts.vmlproj`, or on Linux from a terminal:

```
vml Contacts/Contacts.vmlproj
```

Press **Add a contact**, type `  Ada   Lovelace ` (spaces and all) and press **OK**. The list shows `Ada Lovelace`, tidied by the module.

In the designer, **Preview This Form Only** runs the form you're working on, with the project's modules and its other forms to hand; **Run Project** starts from the start-up form, with your unsaved changes standing in. While either is running, properties you change in the designer show straight away.

## Conclusion

A project is just a list: forms open each other by name, modules hold the shared code, and `Project` holds shared values.

Next: [How To Debug Your Scripts](How-To-Debug-Your-Scripts).
