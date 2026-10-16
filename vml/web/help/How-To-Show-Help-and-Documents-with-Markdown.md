# How To Show Help and Documents with Markdown

## Introduction

Sending people to a web browser to read your help or your terms takes them out of your app. Visualised can show Markdown itself: in a window beside your app, in a control on your form, or as an editor with a live preview. It's the same window Visualised uses for its own help, tutorials and terms.

In this tutorial you'll add a help window to an app, put a page of notes on a form, and let people write their own notes with a preview beside them.

## Prerequisites

- Visualised 1.3.0 or later.
- A form to add to. [Your first app](How-To-Build-Your-First-Visualised-App) is a good one.

## Step 1: Show a window of Markdown

Add a button and give it a script:

```
@Button btnHelp
Parent=c
Canvas.Left=20
Canvas.Top=20
Width=120
Height=30
Content=Help
OnClick=ShowHelp

@Script ShowHelp
Interpreter=lua
<<LUA
Vml("ShowMarkdown", "# Tip Calculator\n\nType the **bill**, pick a **tip**, press **Work it out**.\n\n| Tip | Good for |\n|---|---|\n| 10% | okay service |\n| 15% | good service |")
LUA
```

Press the button and a window opens in your app's colours, with the page laid out: the heading, bold words, the table. It has back and forward buttons, **Ctrl+F** to find, and **Esc** to close.

`ShowMarkdown` takes Markdown, or where to find it:

| Source | What it shows |
|---|---|
| `# Some Markdown` | the Markdown itself |
| `C:\Docs\guide.md` or `~/notes.md` | a file |
| `https://example.com/terms.md` | a page on the web: Markdown, or an ordinary web page |
| `help:Reference-Controls` | a page of Visualised's own help |

Links in the page open in the same window when they lead to another Markdown page, so a folder of `.md` files that link to each other works like a little help system. Links to other sites open in the browser.

A second argument sets the window's title: `Vml("ShowMarkdown", "help.md", "Tip Calculator help")`.

## Step 2: Put Markdown on a form

A **MarkdownView** shows Markdown as part of your form: welcome text, instructions, release notes.

```
@MarkdownView mdNotes
Parent=c
Canvas.Left=20
Canvas.Top=60
Width=360
Height=220
Source=notes.md
```

`Source` can be anything `ShowMarkdown` takes. Or put the Markdown in the form with `Text`, writing `\n` for each new line (`Text=## Welcome\n\nPress **Start**.`), or set it from a script:

```lua
Vml("SetProperty", "mdNotes", "Text", "## Today\n\n- Bill split three ways\n- Tip: 15%")
```

## Step 3: Let people write Markdown

A **MarkdownEditor** is a box to write in, with how it looks beside it, updated as you type:

```
@MarkdownEditor mdWrite
Parent=c
Canvas.Left=20
Canvas.Top=300
Width=560
Height=240
TextChanged=Changed
```

Read what's written with `Vml("GetProperty", "mdWrite", "Text")`. Set `ShowPreview=false` for just the text.

For editing in a window of its own, with **Save** and **Cancel**, use `EditMarkdown`. On the desktop it waits and returns what was saved (`""` if they cancelled). A web page can't wait, so give it a script to run with the result, and the same form works in both places:

```lua
Vml("EditMarkdown", Vml("GetProperty", "mdNotes", "Text"), "Edit the notes", "", "Saved")
```

```
@Script Saved
Interpreter=lua
<<LUA
local text = ...
Vml("SetProperty", "mdNotes", "Text", text)
LUA
```

The third argument, if you give one, is a file that **Save** writes to (on the desktop).

## Step 4: Your terms, in your app

If your form has an [app bar](How-To-Ship-Updates-to-Your-Users), its **Terms** link now opens your terms in this window instead of the browser:

```
@Window TipCalc
AppBar=true
Terms=https://example.com/terms.md
```

Markdown terms look best. An ordinary web page works too: on the desktop it shows the page's text and links; on a web page it shows the page itself, in a frame inside the window.

## Step 5: Visualised's own help

Your scripts can open Visualised's help at any page and heading:

```lua
Vml("Help", "Reference-Controls", "MarkdownView")
```

It opens the same window. In the designer, **F1** does the same for the selected control. The help comes with Visualised, so it works offline and matches the version you have; the **↗** button opens the latest on the wiki.

## Conclusion

You've shown Markdown in a window, on a form, and in an editor with a live preview, and moved your terms into your app.

- Every property: [MarkdownView](Reference-Controls#markdownview) and [MarkdownEditor](Reference-Controls#markdowneditor).
- Every command: [ShowMarkdown](Reference-Commands#showmarkdown), [EditMarkdown](Reference-Commands#editmarkdown) and [Help](Reference-Commands#help).
- The example form `Tour.vml` (in the wiki's examples) tries every dialog, picker and Markdown control in one place.

Raw HTML inside Markdown is shown as text and never run, so it's safe to show Markdown that other people wrote.
