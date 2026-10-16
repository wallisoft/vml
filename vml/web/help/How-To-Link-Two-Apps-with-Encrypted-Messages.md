# How To Link Two Apps with Encrypted Messages

## Introduction

**Link** connects two copies of an app, on two phones, two computers or one of each, so they can send each other messages. The two apps agree a secret key between themselves (by one showing a QR code that the other scans), and every message is encrypted with it before it leaves the device. Messages pass through Visualised's relay, which can't read them and deletes them within a day (an hour on the free allowance).

In this tutorial you'll build a working chat in about 60 lines of Lua.

## Prerequisites

- Two devices with the app (two phones, or a phone and a computer), both online.
- [How To Build Your First Visualised App](How-To-Build-Your-First-Visualised-App), or the same basics.

## Step 1: Make the form

`LinkChat.vml`, the controls:

```
@Window LinkChat
Title=Link Chat
Width=340
Height=520

@Canvas c
Parent=LinkChat

@Button btnStart
Parent=c
Canvas.Left=20
Canvas.Top=16
Width=145
Height=40
Content=Start a link
OnClick=StartLink

@Button btnJoin
Parent=c
Canvas.Left=175
Canvas.Top=16
Width=145
Height=40
Content=Join a link
OnClick=JoinLink

@Image imgCode
Parent=c
Canvas.Left=70
Canvas.Top=70
Width=200
Height=200
IsVisible=false

@TextBlock lblChat
Parent=c
Canvas.Left=20
Canvas.Top=70
Width=300
Height=330
TextWrapping=Wrap
Text=

@TextBox txtSay
Parent=c
Canvas.Left=20
Canvas.Top=416
Width=220
Height=36

@Button btnSend
Parent=c
Canvas.Left=250
Canvas.Top=416
Width=70
Height=36
Content=Send
OnClick=Send

@TextBlock lblState
Parent=c
Canvas.Left=20
Canvas.Top=466
Width=300
Height=30
Foreground=#6B7280
Text=Not linked
```

## Step 2: Start a link and show its code

```
@Script StartLink
Interpreter=lua
<<LUA
local code = Vml("Link", "Heard")
if code == "" then return end
Vml("SetProperty", "imgCode", "Source", Vml("QrCode", Vml("LinkAddress", code), "4"))
Vml("SetProperty", "imgCode", "IsVisible", "true")
Vml("SetProperty", "lblState", "Text", "Show this code to the other phone: " .. code)
LUA
```

`Vml("Link", "Heard")` starts a link and returns its code; `Heard` is the script that will hear everything that happens on it. `LinkAddress` turns the code into a link any phone's camera can open, and `QrCode` makes a picture of it for the `Image`.

## Step 3: Join from the other device

```
@Script JoinLink
Interpreter=lua
<<LUA
Vml("ScanCode", "Scanned", "Scan the other phone's code")
LUA

@Script Scanned
Interpreter=lua
<<LUA
local text, problem = ...
if text == "" then Vml("SetProperty", "lblState", "Text", problem) return end
if Vml("Link", "Heard", text) ~= "" then              -- (the one who joins is linked at once)
  Vml("SetProperty", "lblState", "Text", "Linked, end to end encrypted")
end
LUA
```

On a phone, `ScanCode` opens the camera; on a computer it asks for the code to be pasted. Joining is `Link` again, with the code.

## Step 4: Hear what happens

```
@Script Heard
Interpreter=lua
<<LUA
local what, text = ...
local function add(line)
  Chat = (Chat or "") .. line .. "\n"
  Vml("SetProperty", "lblChat", "Text", Chat)
end
if what == "joined" then
  Vml("SetProperty", "imgCode", "IsVisible", "false")
  Vml("SetProperty", "lblState", "Text", "Linked, end to end encrypted")
elseif what == "message" then add("Them: " .. text)
elseif what == "left" then Vml("SetProperty", "lblState", "Text", "They left")
elseif what == "error" then Vml("SetProperty", "lblState", "Text", text)
end
LUA
```

The handler is told `joined` (the other side arrived), `message` (with its text), `left`, or `error` (with what went wrong).

## Step 5: Send

```
@Script Send
Interpreter=lua
<<LUA
local text = Vml("GetProperty", "txtSay", "Text") or ""
if text == "" then return end
if Vml("LinkSend", text) == "true" then
  Chat = (Chat or "") .. "Me: " .. text .. "\n"
  Vml("SetProperty", "lblChat", "Text", Chat)
  Vml("SetProperty", "txtSay", "Text", "")
end
LUA
```

`LinkSend` returns `true` once the message is on its way.

## Step 6: Try it

Open the app on both devices. Press **Start a link** on one: it shows a QR code. Press **Join a link** on the other and scan it. Both say *Linked, end to end encrypted*. Type on either and press **Send**: the message appears on the other within a moment.

No camera handy? `Vml("LinkPair", "Heard")` links two devices that press their buttons within a few seconds of each other: both show the same three words, and `Vml("LinkAccept")` opens the link once the people agree they match.

## Conclusion

`Link`, `LinkSend` and a handler are all it takes. The same pieces carry anything you can put in text: moves in a game, a shopping list, readings from a sensor.

Next: [How To Put Your App on the Web](How-To-Put-Your-App-on-the-Web): a web page and a phone can link too.
