# Commands reference

Every `Vml()` command a script can call, in Visualised 1.6.1. Generated from the engine itself (`tools/make_reference.py`): the descriptions are the engine's own.

A command is called as `Vml("Name", arguments...)` and returns text (`""` when there's nothing to say). Arguments in [brackets] can be left out. A command that goes wrong is logged and returns `""`: press **F12** while the designer runs your app to see every call and what came back.

**Sections:** [Properties and controls](#properties-and-controls) · [Forms and dialogs](#forms-and-dialogs) · [Scripts, events and programs](#scripts,-events-and-programs) · [Settings and preferences](#settings-and-preferences) · [Data](#data) · [Web and the network](#web-and-the-network) · [Link (app to app)](#link-app-to-app) · [Phone and device](#phone-and-device) · [Drives (as Mountie uses them)](#drives-as-mountie-uses-them) · [Licence, version and updates](#licence,-version-and-updates) · [More](#more) · [The designer's own](#the-designers-own)

## Properties and controls

### AddStackedControl

`Vml("AddStackedControl", ctype, [surface])`

Put a control on the form, stacked down the left: top first, each under the last one added (a new column when the form's full), started again when the last one added has gone. Then drag it where it belongs.

### AlignControls

`Vml("AlignControls", how, [surface])`

### BringToFront

`Vml("BringToFront", name)`

Put a control in front of the others it overlaps.

### ClearChildren

`Vml("ClearChildren", name)`

### ControlExists

`Vml("ControlExists", name)`

"true" if there's a control of that name, else "false".

### CopyControl

`Vml("CopyControl", names)`

Copy controls (and what's inside them) for Paste: one name, or several comma-separated (a group). One that's inside another being copied goes with it, not twice.

### CreateControl

`Vml("CreateControl", ctype, name, [parent_name])`

### DeleteControl

`Vml("DeleteControl", name)`

Remove a control (and what's in it) from the form.

### GetChildControls

`Vml("GetChildControls", name)`

### GetControlHeight

`Vml("GetControlHeight", name)`

The control's height now, in pixels.

### GetControlPropertiesJson

`Vml("GetControlPropertiesJson", name)`

Reflection: every property this control has, with its live value and editor; composites list their mapped ones first.

### GetControlType

`Vml("GetControlType", name)`

The kind of control it is: "Button", "TextBox"...

### GetControlWidth

`Vml("GetControlWidth", name)`

The control's width now, in pixels.

### GetControlX

`Vml("GetControlX", name)`

Where the control is, in pixels from the left of what it's in.

### GetControlY

`Vml("GetControlY", name)`

Where the control is, in pixels from the top of what it's in.

### GetProperty

`Vml("GetProperty", name, prop)`

Read a control's property, as text: `Vml("GetProperty", "txtName", "Text")`. name can be `Form.control` for a control on another open form.

### PasteControl

`Vml("PasteControl", [x], [y], [surface])`

Paste what was copied: where the form was right-clicked (x, y), or a step down and right of the original. A group keeps its shape. What's pasted is selected (all of it), and its names are the answer, comma-separated.

### SendToBack

`Vml("SendToBack", name)`

### SetCanvasPosition

`Vml("SetCanvasPosition", name, x, y)`

Move a control on its Canvas, to x pixels from the left and y from the top.

### SetControlPosition

`Vml("SetControlPosition", name, x, y)`

Move a control on its Canvas, to x pixels from the left and y from the top.

### SetControlSize

`Vml("SetControlSize", name, w, h)`

Resize a control, in pixels.

### SetControlVisible

`Vml("SetControlVisible", name, visible)`

### SetProperty

`Vml("SetProperty", name, prop, [value])`

Change a control's property: `Vml("SetProperty", "lblTotal", "Text", "£45.00")`. name can be `Form.control` for a control on another open form. Any property in the [controls reference](Reference-Controls) can be set.

## Forms and dialogs

### AppExit

`Vml("AppExit")`

Close the app.

### CancelClose

`Vml("CancelClose")`

In a form's OnClosing handler: keep the form open after all (VB's Cancel = True).

### ChoiceDialog

`Vml("ChoiceDialog", message, [title], [buttons])`

A question with your own answers: buttons is their captions with | between them (the first is the one Enter presses). Returns the caption pressed, or "" if the box was closed without one.

### CloseForm

`Vml("CloseForm", name)`

Close an open form, by its name.

### CloseSelf

`Vml("CloseSelf")`

### ConfirmDialog

`Vml("ConfirmDialog", message, [title])`

Ask a yes-or-no question: "true" for Yes, "false" for No.

### EditMarkdown

`Vml("EditMarkdown", [source], [title], [save_to], [handler])`

Let the user write Markdown, seeing how it looks beside it as they type. source: the Markdown to start with (or a file of it); save_to: a file Save writes to. Returns what they saved, or "" if they cancelled. handler: a script to run with what was saved (a web page can't wait for the answer, so use it there).

### ErrorDialog

`Vml("ErrorDialog", message, [title])`

### FileOpenDialog

`Vml("FileOpenDialog", [title], [ext], [start])`

Let the user choose a file: its full path, or "" if they cancel. ext: which kinds of file to offer, by ending ("csv", or "vb,cs" for several).

### FileSaveDialog

`Vml("FileSaveDialog", [title], [default], [ext])`

### FolderDialog

`Vml("FolderDialog", [title], [start])`

Let the user choose a folder: its full path, or "" if they cancel.

### FormOpen

`Vml("FormOpen", path)`

Open another form (relative paths are next to this one). If it's already open, bring it forward.

### FormOpenModal

`Vml("FormOpenModal", path)`

Open a form and wait until it closes; returns whatever it passed to SetDialogResult.

### HideForm

`Vml("HideForm", name)`

Hide a form, without closing it.

### InfoDialog

`Vml("InfoDialog", message, [title], [picture])`

A message with an OK button. picture: a picture to show above it (a file, or a data: address such as QrCode gives).

### PromptDialog

`Vml("PromptDialog", [title], [prompt], [default], [secret])`

Ask for one line of text. Returns what was typed, or "" if cancelled. secret "true" shows dots, for a password.

### Quit

`Vml("Quit")`

Quit (the app's own Exit). The windows and the tray icon go at once; the drives are taken down side by side (SSH and disks together, never more than a few seconds however unreachable a server is) while the app keeps answering the desktop, so its panel never spins waiting for a reply; then it quits.

### SetDialogResult

`Vml("SetDialogResult", [value])`

A form opened with FormOpenModal hands this back to whoever opened it.

### ShowForm

`Vml("ShowForm", name)`

Show a form that was hidden, and bring it to the front.

### ShowMarkdown

`Vml("ShowMarkdown", source, [title])`

Show Markdown in a window of its own, beside the app: source is the Markdown itself, a file, a web address (a web page shows as its text and links) or help:Page for a page of Visualised's help. Links in it open in the same window (back and forward as in a browser); links to other sites open in the browser.

## Scripts, events and programs

### CancelProcess

`Vml("CancelProcess", pid)`

Stop a program started with RunProcess.

### ExecuteScript

`Vml("ExecuteScript", code, args...)`

### Help

`Vml("Help", [page], [section])`

Open a page of Visualised's help, in the app's help window: "" for the tutorials, "Reference" for the reference, or any page's name ("Reference-Commands", "How-To-Style-Controls-with-CSS"); section: a heading on it. Returns its address on the wiki.

### Log

`Vml("Log", [text])`

Write a line where the app's maker can see it: the terminal Visualised was started from. From an app being previewed on a phone, the line comes back to that same terminal.

### ProcessExitCode

`Vml("ProcessExitCode", pid)`

How a program started with RunProcess ended: its exit code ("" while it's still running).

### ProcessRunning

`Vml("ProcessRunning", pid)`

### RunProcess

`Vml("RunProcess", command, [output_control], [on_exit], [shell])`

Start a command WITHOUT waiting. Its output streams, line by line, into output_control (a TextBox or ListBox) as it arrives. When it ends, on_exit runs (settings: exit_code, process_id). Returns a job id. shell: bash | powershell | none (run the command as given).

### RunScript

`Vml("RunScript", name, args...)`

Run another script of this form (or a module's function) by name, with arguments; returns what it returns.

### SetEvent

`Vml("SetEvent", name, event, handler)`

### SetStatusText

`Vml("SetStatusText", text)`

Show text in the form's status line (a control named statusText, StatusText or lblStatus).

### Shell

`Vml("Shell", command)`

### ShowDebugger

`Vml("ShowDebugger")`

Open the debugger: every Vml() call the running forms' scripts make, and their variables.

## Settings and preferences

### GetPreference

`Vml("GetPreference", key, [default])`

A preference this user set earlier (snap to grid, grid size...), or `default` if they never have.

### GetSetting

`Vml("GetSetting", key)`

A value the app saved with SetSetting ("" if none). Kept between runs, as on a phone or in a browser.

### SetPreference

`Vml("SetPreference", key, [value])`

### SetSetting

`Vml("SetSetting", key, [value])`

Save a value under a name, for this app, to read back with GetSetting, now or the next time it opens.

## Data

### DbClose

`Vml("DbClose", name)`

Close a database opened with DbOpen.

### DbCopyTable

`Vml("DbCopyTable", source, table, target, [new_name])`

Copy a table, its columns and all its rows, from one open database into a SQLite one (to bring data out of Access or a server into a file the app can carry with it). The table must not be there already. Returns how many rows were copied, or "" with DbError saying why.

### DbDrivers

`Vml("DbDrivers")`

The ODBC drivers installed on this computer (empty if ODBC itself isn't).

### DbError

`Vml("DbError")`

Why the last Db command failed, or "" if it worked.

### DbExecute

`Vml("DbExecute", name, sql, params...)`

Run a statement that changes data. Returns how many rows it touched, or "" with DbError saying why.

### DbList

`Vml("DbList")`

The databases this app knows: open ones, and those its project names.

### DbOdbcState

`Vml("DbOdbcState")`

Can this computer use ODBC at all? JSON: {ready, module, library, drivers, why}. module: Python's ODBC module is here; library: so is the system's ODBC (on Linux, unixODBC); why: what is missing, in words.

### DbOpen

`Vml("DbOpen", name, connection)`

Open a database under a name. connection: sqlite:file.db (or just a path ending .db, .sqlite, .s3db), or odbc:DSN=name;UID=...;PWD=... (any ODBC connection string). Returns "true", or "" with DbError saying why.

### DbQuery

`Vml("DbQuery", name, sql, params...)`

Rows as JSON, one object per row. "" as the name means the project's main database, or the form's own.

### DbShow

`Vml("DbShow", grid, name, source, [limit])`

Show a table (or the rows a SELECT asks for) in a DataGrid, straight from the database: the first rows only (200 unless limit says otherwise), however big it is, with the columns in the database's order. It only reads: anything that isn't a SELECT is refused. Returns JSON: {shown, total, columns, error}; total is -1 when the database wasn't asked to count (a query of your own).

### DbSources

`Vml("DbSources")`

The ODBC data sources (DSNs) set up on this computer, as JSON: [{name, driver}].

### DbTables

`Vml("DbTables", [name], [kind])`

The tables and views of a database, as a JSON list of names. kind "tables" leaves the views out.

### DbTest

`Vml("DbTest", connection, [folder])`

Try an address without keeping it open. Returns JSON: {ok, kind, tables (how many), error}. folder: where a SQLite file given without one is looked for (the open project's folder if left out).

### Requery

`Vml("Requery", [control])`

Fill a control from its ItemsSource again (after the data changed); with no name, every one in this form.

### SqlExecute

`Vml("SqlExecute", sql, args...)`

Run SQL that changes the form's database (INSERT, UPDATE, DELETE...); ? in the SQL are filled from the arguments. Returns how many rows it changed.

### SqlQuery

`Vml("SqlQuery", sql, args...)`

## Web and the network

### Fetch

`Vml("Fetch", url, [body], [handler])`

Ask a web address for something: with no body it is fetched, with one it is sent (POST; as JSON when it looks like JSON). handler is then run with what came back and a blank, or what came back (if anything) and what went wrong. The app carries on meanwhile.

### OnPush

`Vml("OnPush", [handler], [firebase])`

Hear push messages, on a phone. With firebase (a project's public values as JSON) they come from the app's own server: handler gets ("token", the phone's Firebase token) and ("message", the push's data). With none, through Visualised's own push service: ("address", this phone's push address) and ("message", text, from) for each PushSend to it. Or a blank and what went wrong (as here: an app exported for Android only).

### OpenUrl

`Vml("OpenUrl", url)`

Open a web page (or a mailto: link) in the user's own browser or mail program.

### PushSend

`Vml("PushSend", [address], [text], [handler])`

Send a short text to a push address (one an app's phone copy got from OnPush): the phone is woken and its handler gets ("message", text, this computer's push address). Handler gets "sent", or a blank and why not.

### SignIn

`Vml("SignIn", [provider], [handler])`

Sign in with Google or GitHub: the user's browser opens at the provider's own sign-in, and handler then gets JSON {provider, id, name, email, picture, token}, or a blank and why not. The token is signed by tiny-web, so an app's own server can check it (tiny-web.uk/api/oauth.php, action "verify").

## Link (app to app)

### Link

`Vml("Link", handler, [code], [start])`

Start a link, or join one. With no code a new link is started and its code is returned, to show the other app (QrCode makes a picture of it); with a code, that link is joined. handler is then run with "joined" when the other side arrives, "message" and the text when it sends, "left" when it closes, and "error" and what went wrong. start: "start" to be given the messages of the last day too. "" and the handler told why if it couldn't be done.

### LinkAccept

`Vml("LinkAccept")`

The three words LinkPair gave are the same on both: open the link. Its code, or "" if there is no pairing waiting to be accepted.

### LinkAddress

`Vml("LinkAddress", [code])`

What to show as a QR code (QrCode) so any phone's camera can join this app's link, not only the scanner inside the app: an address that opens this app with the link's code. It needs the app to be on the web, and its Window to say where (WebAddress=https://...); without that, the code itself is given back, which another copy of the app can still scan or have pasted in. code: the link's code (the one open now if left out).

### LinkClose

`Vml("LinkClose")`

Close the link. The other end is told.

### LinkCode

`Vml("LinkCode")`

The code of the link this app has open, or "".

### LinkInvite

`Vml("LinkInvite")`

The link code this app was opened with, when it was opened from an address made by LinkAddress (a QR code pointed at by a phone's camera): give it to Link to join. "" otherwise, and always on a computer.

### LinkPair

`Vml("LinkPair", handler)`

Agree a link with another app by pressing together: both run this within a few seconds of each other, with nothing to show or scan. handler is run with "words" and three words, which the other app shows too; when the two people see they are the same, LinkAccept opens the link (and the handler then hears "joined", "message" and the rest, as with Link). Or with "error" and what went wrong: nobody else pressed, or too many did.

### LinkSend

`Vml("LinkSend", [text])`

Send some text to the other end of the link. "true", or "" (and the handler is told why).

### QrCode

`Vml("QrCode", text, [scale])`

A QR code for some text (an address, usually), as a picture: a data: address to give an Image as its Source, or InfoDialog as its picture. Up to 213 characters. "" if it is too long.

### ScanCode

`Vml("ScanCode", handler, [prompt])`

Read a QR code with the camera, then run handler with what it says; or with a blank and what went wrong. A computer asks for it to be pasted instead.

## Phone and device

### BluetoothDevices

`Vml("BluetoothDevices", handler)`

The Bluetooth devices a phone is paired with: handler gets them as JSON (name, address, watched) and a blank; or "[]" and what went wrong, which on a computer is always.

### BluetoothLog

`Vml("BluetoothLog")`

What a phone has noted, newest first, as JSON: device, name, what, time, and where. "[]" on a computer.

### Brightness

`Vml("Brightness", [percent])`

How bright the phone's screen is while this app is in front, 0 to 100; nothing puts it back to the phone's own setting. A computer's screen is left alone.

### ClipboardGet

`Vml("ClipboardGet")`

The text on the clipboard.

### ClipboardSet

`Vml("ClipboardSet", [text])`

Put text on the clipboard, ready to paste.

### DeviceInfo

`Vml("DeviceInfo")`

What the app is running on, as JSON: platform is "desktop" here, "android-app" in the Visualised app on a phone, "android-browser", "ios-browser" or "browser" on a web page; app is true only in the app.

### Flash

`Vml("Flash", [pattern], [handler])`

Signal with light: pattern is milliseconds on, off, on, off... A phone uses its torch and a web page lights the whole screen; a computer only waits that long. Then handler is run. "" stops it.

### GetLocation

`Vml("GetLocation", handler)`

Find where the phone is, then run handler with the latitude, the longitude and how many metres out that might be; or with three blanks and what went wrong, which on a computer is always.

### KeepAwake

`Vml("KeepAwake", [on])`

Keep the phone's screen on while the app is in front. Nothing happens on a computer.

### LightReport

`Vml("LightReport")`

On a phone, how WatchLight has gone, in a line: how evenly the camera's pictures came and how long its light took to switch. "" on a computer.

### Listen

`Vml("Listen", handler, [prompt])`

Hear what the user says, then run handler with the words; or with a blank and what went wrong. A computer asks them to type it instead.

### LookupNames

`Vml("LookupNames", [numbers], [handler])`

Names for some numbers from the phone's address book, as JSON {number: name}, to handler; or a blank and why not (as here: an app exported for an Android phone only).

### LookupNumber

`Vml("LookupNumber", [name], [prefer], [handler])`

A number for a name in the phone's address book, to handler; or a blank and why not (as here: an app exported for an Android phone only).

### Notify

`Vml("Notify", [title], [text])`

A notification in the phone's own list. On a computer, a message box.

### OnMessages

`Vml("OnMessages", [handler])`

Hear messages that arrive in the phone's messaging apps (RCS included), read from their notices: handler gets who from and what they said. A blank "from" means it can't, and the text says why (as here: an app exported for an Android phone only). "" stops.

### OnSms

`Vml("OnSms", [handler])`

Hear text messages as they arrive: handler gets who from and what they said, for each. A blank "from" means it couldn't, and the text says why (as here: an app exported for an Android phone only). "" stops.

### PickPhoto

`Vml("PickPhoto", image, [handler])`

Put a picture the user chooses into an Image, then run handler (if given) with the Image's name. Returns the file chosen here; on a phone the answer comes later, so use the handler.

### Pressure

`Vml("Pressure")`

The air pressure in hectopascals from a phone's barometer (it tells one floor from the next). "" here.

### ReadContacts

`Vml("ReadContacts", [handler])`

The phone's address book, as JSON [{"name", "number", "label"}], to handler; or a blank and why not (as here: an app exported for an Android phone only).

### RunInBackground

`Vml("RunInBackground", [on])`

Keep the app going on a phone while the phone is used for something else, for six hours from the last time it was asked (so an app that must keep going asks again now and then). A computer does that anyway.

### SaveContact

`Vml("SaveContact", [name], [number], [oldName], [handler])`

Adds to or changes the phone's address book; to handler the name, or a blank and why not (as here: an app exported for an Android phone only).

### SaveFile

`Vml("SaveFile", name, [text])`

Give the user a file: on a phone it goes to Downloads, in a browser it downloads, on a computer the user is asked where to put it. Returns where it went, or "" if it didn't.

### Share

`Vml("Share", [text], [title])`

Hand some text to another app on the phone (messages, email, notes). On a computer it goes on the clipboard.

### SmsSend

`Vml("SmsSend", number, [text], [handler])`

Send a text message from the phone, then run handler with "sent", or a blank and what went wrong. Only an app exported on its own for Android can (vml apk); here the handler hears why not.

### Speak

`Vml("Speak", [text])`

Say some text out loud, where there is a voice to say it with.

### TakePhoto

`Vml("TakePhoto", image, [handler])`

Take a photo with the phone's camera and put it in an Image, then run handler. A computer asks for a picture file instead.

### Torch

`Vml("Torch", [on])`

The phone's torch, on or off. Nothing happens on a computer.

### Vibrate

`Vml("Vibrate", [milliseconds])`

Buzz the phone. Nothing happens on a computer.

### WatchBluetooth

`Vml("WatchBluetooth", address, [on], [handler])`

On a phone: note where the phone is whenever a paired device (a car, say) connects or goes away, even with the app shut. handler hears "watching", "stopped" or "partly", and any problem.

### WatchLight

`Vml("WatchLight", [handler], [where])`

Watch for a light going on and off through the phone's camera: each change runs handler with "on" or "off" and how many milliseconds the state before lasted; or with "error", 0 and what went wrong, which on a computer is always. where: a control to show the camera's picture over. No handler stops watching.

## Drives (as Mountie uses them)

### DiskInfo

`Vml("DiskInfo", [path])`

What a disk image is, as JSON: {size, size_text, format, label, partitions, folder} (read from the file).

### DiskList

`Vml("DiskList")`

The computer's partitions as JSON: [{path, name, label, fstype, size, mounted, removable, system}].

### DiskMount

`Vml("DiskMount", [item], [handler])`

Mount a disk image (ISO, IMG, VHD, VHDX...) or a partition: item is JSON {name, path, kind, readonly}. handler gets (name, state, detail): mounting, mounted (detail: where, comma-separated, and how), error, off.

### DiskUnmount

`Vml("DiskUnmount", [item], [handler])`

Unmount one (item JSON, or just its name); a partition mounted elsewhere is unmounted all the same.

### FolderPreview

`Vml("FolderPreview", [path], [hide], [showonly])`

What a folder drive would show, as JSON {shown, hidden, names (the first shown)}: for the ignore box.

### IgnoreUsual

`Vml("IgnoreUsual")`

The ready-made ignore lists, as JSON [{key, label, patterns}].

### OpenTerminal

`Vml("OpenTerminal", [folder], [drive])`

A terminal in a folder; or, given an SSH drive (JSON), an ssh session to it, in its folder. "" or why not.

### SshAllowSudo

`Vml("SshAllowSudo", [drive], [password], [handler])`

Let the drive's user act as its "actas" user without a password, for SSH Drive's file access only (a sudoers rule of its own on the server, checked with visudo). The sudo password is used once and not kept. handler gets (name, "ok" or "error", what happened).

### SshMethods

`Vml("SshMethods")`

### SshMount

`Vml("SshMount", [drive], [handler])`

### SshStatus

`Vml("SshStatus", [name])`

### SshTest

`Vml("SshTest", [drive], [handler])`

Try a drive without mounting it: handler gets (name, "ok", what it reached, the server's key) or (name, "error", what went wrong, "").

### SshUnmount

`Vml("SshUnmount", [name])`

## Licence, version and updates

### CSharpSetup

`Vml("CSharpSetup")`

Build the C# script host (needs the .NET SDK; about a minute the first time). Returns "" when C# is ready, otherwise why it isn't.

### CSharpStatus

`Vml("CSharpStatus")`

Where C# scripting stands here, as JSON: ready, dotnet (its path), sdk (version), sdk_ok, download.

### CheckForUpdate

`Vml("CheckForUpdate")`

Ask whether a newer Visualised has been released. JSON: current, latest, newer, url, error if the check couldn't be made, and store (true for a copy from the Microsoft Store, which updates itself: no check is made).

### GetLanguages

`Vml("GetLanguages")`

The script languages this machine can run, for the script editor.

### GetLicence

`Vml("GetLicence")`

The licence as JSON: tier, label, name (who it is licensed to), id, issued, expires, key, expired, was.

### GetLicenceTier

`Vml("GetLicenceTier")`

Which licence this copy of Visualised has: "community", "pro" or "enterprise".

### GetShellName

`Vml("GetShellName")`

### InstallDotnet

`Vml("InstallDotnet")`

Start installing the .NET SDK where that can be done for the user: on Windows, with winget, in a window of its own. Returns "started", or "" if it has to be downloaded by hand (see CSharpStatus's download). A copy from the Microsoft Store never installs other software itself: it only shows where to get it.

### LicenceAllows

`Vml("LicenceAllows", feature)`

"true" if this licence includes a feature ("export", "import"), else "false".

### RemoveLicenceKey

`Vml("RemoveLicenceKey")`

Forget the licence key on this computer.

### SetLicenceKey

`Vml("SetLicenceKey", key)`

Store a licence key. Returns "" if it was accepted, otherwise why not.

### VmlVersion

`Vml("VmlVersion")`

The running Visualised runtime version, e.g. "0.17.1". Apps can check they have a new enough engine.

## More

### AddImporter

`Vml("AddImporter", path)`

Add an importer (a .vml file with an @Importer in it) to your own library, ~/.vml/importers. Returns "" if it was added, or why it wasn't.

### AttachDebugger

`Vml("AttachDebugger", [pid])`

Open a debugger on another running Visualised app (by its pid; none: choose from a list).

### CanPaste

`Vml("CanPaste")`

### CanRedo

`Vml("CanRedo", [surface])`

### CanUndo

`Vml("CanUndo", [surface])`

### DebugApps

`Vml("DebugApps")`

The other Visualised apps running now: JSON [{pid, title}], for "Attach to a running app".

### DebugAttach

`Vml("DebugAttach", [everything])`

Start keeping a record of Vml() calls for an attached debugger to collect (DebugCalls).

### DebugBreaks

`Vml("DebugBreaks", [spec])`

Set the breakpoints: JSON {name: [line, ...]}; none: what they are now.

### DebugCalls

`Vml("DebugCalls", [since])`

The calls recorded since a number: JSON {seq, rows}.

### DebugDetach

`Vml("DebugDetach")`

### DebugLua

`Vml("DebugLua", key, code, [arg])`

Run Lua in one of this app's forms (the Variables tab); a table comes back as {name: "type<TAB>value"}.

### DebugPauseInfo

`Vml("DebugPauseInfo")`

Where a script is stopped (JSON), or "" if nothing is.

### DebugResume

`Vml("DebugResume", [mode])`

### DebugScripts

`Vml("DebugScripts", [key])`

The Lua a form runs, to set breakpoints in: JSON [{name, code}] (its scripts, then its project's modules).

### DebugShared

`Vml("DebugShared")`

### DebugStates

`Vml("DebugStates")`

The forms with Lua running, for the Variables tab: JSON [[key, name]].

### DebugTitle

`Vml("DebugTitle")`

What this app is, for a debugger's list of running apps.

### FileCopy

`Vml("FileCopy", source, target)`

Copy a file (missing folders are made). Returns "true" if it was copied.

### FileExists

`Vml("FileExists", path)`

"true" if there's a file at that path, else "false".

### FileIsFolder

`Vml("FileIsFolder", path)`

### FileList

`Vml("FileList", folder, [pattern], [recursive])`

The files in a folder whose names match a pattern (*.frm), as a JSON list of full paths, sorted. Several patterns can be given, separated by ; and recursive ("true") looks in the folders inside too.

### FileRead

`Vml("FileRead", path, [encoding])`

A text file's contents ("" if it can't be read). With no encoding named, UTF-8 is tried first and, if the file isn't UTF-8, Windows-1252 (which older Windows programs wrote).

### FileReadBase64

`Vml("FileReadBase64", path, [offset], [length])`

Part (or all) of any file, as base64: for pictures and other files that aren't text.

### FileSize

`Vml("FileSize", path)`

A file's size in bytes (-1 if it isn't there).

### FileWrite

`Vml("FileWrite", path, [text])`

Write a text file as UTF-8 (relative paths are beside this form; missing folders are made). Returns "true" if it was written.

### FileWriteBase64

`Vml("FileWriteBase64", path, data)`

Write a file from base64. Returns "true" if it was written.

### GetImporters

`Vml("GetImporters")`

The importers available, as JSON: name, title, files (the endings it reads), project_title, project_files.

### GridGetData

`Vml("GridGetData", name)`

### GridSetData

`Vml("GridSetData", name, data, [columns])`

Fill a DataGrid from JSON: an array of objects (their keys become the headings) or of arrays. columns: headings to show instead, comma-separated.

### LaunchedAtBoot

`Vml("LaunchedAtBoot")`

"true" if this run was started at login (by StartAtBoot), not by the user.

### OpenFolder

`Vml("OpenFolder", [path])`

Show a folder (or a drive, "S:") in the computer's own file manager. Answers "" or why not.

### PickTextFile

`Vml("PickTextFile", [handler], [title], [start])`

The user picks a file; handler gets (its path, its text, why not). On a phone the same command opens the phone's file picker (and the name is just the file's name).

### RegexFindAll

`Vml("RegexFindAll", pattern, text, [flags])`

Every match, as JSON: a list of [whole match, group 1, ...].

### RegexMatch

`Vml("RegexMatch", pattern, text, [flags])`

The first match of a regular expression in some text, as JSON: [whole match, group 1, group 2, ...] ("" for a group that took no part). Returns "" if there is no match. flags: any of i (ignore case), m (^ and $ match at each line), s (. matches a newline too). Start the pattern with ^ to match from the start.

### RegexReplace

`Vml("RegexReplace", pattern, replacement, text, [flags])`

The text with every match replaced. In the replacement, \1 is group 1 and so on.

### RunApp

`Vml("RunApp", path, [project])`

Start a form or project as an app of its own, in its own process: it carries on if this one closes. project: the project (or form) the designer has open, for a tool to work on: it finds it in VML_PROJECT.

### SetMenuItemEnabled

`Vml("SetMenuItemEnabled", name, enabled)`

Grey a menu item out ("false") or back ("true").

### SetMenuItemText

`Vml("SetMenuItemText", name, text)`

### SetTabs

`Vml("SetTabs", strip_name, spec)`

A tab strip's pages, in tab order: JSON [{"page": its name, or "" for a new one, "header": its words}]. A page left out is deleted, with what's on it. The designer's Edit Tabs box uses this.

### StartAtBoot

`Vml("StartAtBoot", [on])`

Start this app when the user logs in ("true"), or not ("false").

### ToolsFolder

`Vml("ToolsFolder")`

The tools folder (made if it isn't there yet).

### ToolsList

`Vml("ToolsList")`

The tools, as JSON [{name, path}]: each .vml or .vmlproj in the tools folder, and each folder in it that holds a .vmlproj or a .vml (a link to an app's folder will do: ln -s ~/projects/x/apps/bob ~/.vml/tools/Bob).

### Tray

`Vml("Tray", [tooltip], [menu], [handler])`

An icon in the tray. menu: items with | between ("-" a line; "Title>one;two" a submenu, whose items come to the handler as "Title>one"); handler gets the item picked, or "open" when the icon itself is clicked.

### TrayMessage

`Vml("TrayMessage", [title], [text])`

Show a notification from the app's tray icon.

## The designer's own

Commands the designer itself is built from (its forms are VML too). Handy for tools that work on forms; most apps never need them.

`AddDesignControl`, `AndroidKey`, `AndroidKeyRestore`, `AndroidKeySave`, `ClearDesign`, `DuplicateControl`, `ExportApk`, `ExportApp`, `ExportHtml`, `ExportVml`, `GetControlAt`, `GetControlEvents`, `GetControlTypes`, `GetCurrentControl`, `GetDesignMenu`, `GetDesignScript`, `GetFocusedControlName`, `GetResizeZone`, `GetSelectedControlName`, `ImportForm`, `ImportProject`, `ImportVml`, `LoadControlTemplate`, `MenuAddItem`, `MenuDeleteItem`, `PhoneSize`, `PreviewDesign`, `PreviewInBrowser`, `PreviewOnPhone`, `ProjectAdd`, `ProjectClose`, `ProjectDatabase`, `ProjectInFolder`, `ProjectInfo`, `ProjectName`, `ProjectNew`, `ProjectOpen`, `ProjectPath`, `ProjectRemove`, `ProjectSetName`, `ProjectSetStartup`, `ProjectTree`, `Redo`, `RenameControl`, `RunProject`, `SelectControl`, `SetCurrentControl`, `SetDesignMenu`, `SetDesignScript`, `SetParent`, `ShowContextMenu`, `Undo`, `UndoMark`, `UndoReset`
