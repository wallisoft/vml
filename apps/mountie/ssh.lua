-- Mountie: SSH drives: the SSH tab and its form.
-- A module of the Mountie project: every script in Mountie.vml can use what's here.

Ssh = {}

-- the drive as the form has it
function FormDrive()
  local function get(box) return (Vml("GetProperty", box, "Text") or ""):match("^%s*(.-)%s*$") end
  local host = get("txtHost")
  local a = tostring(Vml("GetProperty", "cmbAuth", "SelectedIndex"))
  local auth = a == "0" and "password" or a == "1" and "key" or "agent"
  local d = {
    name = get("txtName") ~= "" and get("txtName") or host,
    host = host, port = tonumber(get("txtPort")) or 22, user = get("txtUser"), remote = get("txtRemote"),
    mount = get("txtMount"), auth = auth, actas = get("txtActAs"),
    automount = Vml("GetProperty", "chkAuto", "IsChecked") == "true",
    readonly = Vml("GetProperty", "chkReadOnly", "IsChecked") == "true",
  }
  if auth == "password" then d.password = get("txtSecret") end
  if auth == "key" then
    local k = get("txtKey")
    if PickedKey and k == PickedKey.label then d.keytext = PickedKey.text
    elseif k:find("PRIVATE KEY") then d.keytext = k                     -- the key itself, pasted
    else d.key = k end
    d.passphrase = get("txtSecret")
  end
  local old = Editing and Drives[Editing]
  if old and old.host == d.host and old.port == d.port then d.hostkey = old.hostkey end   -- same server: keep its key
  if not d.hostkey and Tested and Tested.host == d.host and Tested.port == d.port then d.hostkey = Tested.hostkey end
  return d
end

function Keep() Vml("SetSetting", "drives", json.encode(Drives)) end

function Find(name) for i, d in ipairs(Drives) do if d.name == name then return i, d end end end

function Selected()
  local i = tonumber(Vml("GetProperty", "lstDrives", "SelectedIndex") or "-1") or -1
  if i >= 0 and Drives[i + 1] then return i + 1, Drives[i + 1] end
end

local DOT = { mounted = "●", connecting = "◌", offline = "○", error = "✕" }

function Refresh()
  local rows = {}
  for _, d in ipairs(Drives) do
    local s = State[d.name] or {}
    local where = d.user ~= "" and (d.user .. "@" .. d.host) or d.host
    local label = (DOT[s.state] or "·") .. " " .. d.name .. "   " .. where .. ":" .. (d.remote ~= "" and d.remote or "~")
      .. ((d.actas or "") ~= "" and ("  as " .. d.actas) or "")
    if s.state == "mounted" then label = label .. "   →  " .. (s.detail or ""):gsub(" %(.*%)", "") end
    rows[#rows + 1] = label:gsub(",", " ")
  end
  local keep = Vml("GetProperty", "lstDrives", "SelectedIndex")
  Vml("SetProperty", "lstDrives", "Items", table.concat(rows, ","))
  if keep and keep ~= "-1" then Vml("SetProperty", "lstDrives", "SelectedIndex", keep) end
  Ssh.Picked()
  local up = 0
  for _, s in pairs(State) do if s.state == "mounted" then up = up + 1 end end
  for _, s in pairs(DiskState) do if s.state == "mounted" then up = up + 1 end end
  InTray = (Vml("Tray", "Mountie: " .. up .. " mounted", TrayMenu(), "TrayClick") or "") == ""
end

-- the tray's menu: who made it, Exit, then every drive with a dot for how it is (picking one mounts or unmounts it)
local TRAYDOT = { mounted = "●", mounting = "◌", connecting = "◌", error = "✕" }
TrayItems = {}
function TrayMenu()
  TrayItems = {}
  local top = "Mountie " .. VERSION .. "  ·  Steve & Claude, Wallisoft"
  local menu = { top, "Open Mountie", "Exit" }
  local function add(name, state, what)
    local label = (TRAYDOT[state] or "○") .. "  " .. name:gsub("|", "/")
    while TrayItems[label] do label = label .. " " end           -- (two with one name: both still pickable)
    TrayItems[label] = what
    if #menu == 3 then menu[#menu + 1] = "-" end
    menu[#menu + 1] = label
  end
  for _, d in ipairs(Drives) do add(d.name, (State[d.name] or {}).state, { ssh = d }) end
  for _, im in ipairs(Images or {}) do
    if im.enabled ~= false then add(im.name, (DiskState[im.name] or {}).state, { image = im }) end
  end
  TrayTop = top
  return table.concat(menu, "|")
end

function TrayToggle(what)
  if what.ssh then
    local d, s = what.ssh, (State[what.ssh.name] or {}).state
    if s == "mounted" or s == "connecting" then Vml("SshUnmount", d.name) else Mount(d) end
    Refresh()
  else
    local it, s = what.image, (DiskState[what.image.name] or {}).state
    if s == "mounted" or s == "mounting" then
      Vml("DiskUnmount", json.encode({ name = it.name, path = it.path, kind = it.kind }), "OnDisk")
    else DiskMount(it) end
    if Tab ~= "Ssh" then RefreshDisk() else Refresh() end
  end
end

function Mount(d) State[d.name] = { state = "connecting", detail = "" }; Vml("SshMount", json.encode(d), "OnDrive") end

-- the events (each script in Mountie.vml is one line calling one of these)

function Ssh.Closing(args)
  args = args or {}
  -- the window goes, the drives stay: say so the first time, so nobody wonders where it went
  if InTray and not ToldTray then
    ToldTray = true
    Vml("TrayMessage", "Mountie is still running", "Your drives stay connected. To quit, use Exit on the hat's menu.")
  end
end

function Ssh.OnDrive(args)
  args = args or {}
  local name, state, detail = args[1] or "", args[2] or "", args[3] or ""
  local i, d = Find(name)
  if state == "hostkey" then
    if d then d.hostkey = detail; Keep() end           -- remembered: a different key next time is refused
    return
  end
  State[name] = { state = state, detail = detail }
  if state == "mounted" then
    Vml("TrayMessage", name .. " connected", (detail:gsub(" %(.*%)", "")))
  elseif state == "error" then
    Say("✕ " .. name .. ": " .. detail, true)
    Vml("TrayMessage", name .. " didn't connect", detail)
  elseif state == "offline" then
    Say("○ " .. name .. " is out of reach; it keeps trying. (" .. detail .. ")", true)
  end
  Refresh()
end

function Ssh.Picked(args)
  args = args or {}
  local i, d = Selected()
  local s = d and State[d.name] or {}
  local up = s.state == "mounted" or s.state == "connecting" or s.state == "offline"
  Vml("SetProperty", "btnToggle", "Content", up and "Disconnect" or "Connect")
  for _, n in ipairs({ "btnToggle", "btnEdit", "btnRemove" }) do Vml("SetProperty", n, "IsEnabled", tostring(d ~= nil)) end
  if d and s.detail and s.detail ~= "" then
    if s.state == "mounted" then Say(d.name .. ": " .. s.detail .. (Can.android and "" or "\nDouble-click it to open it."))
    elseif s.state == "error" then Say("✕ " .. d.name .. ": " .. s.detail, true)
    elseif s.state == "offline" then Say("○ " .. d.name .. " is out of reach; it keeps trying. (" .. s.detail .. ")", true) end
  end
end

function Ssh.Toggle(args)
  args = args or {}
  local i, d = Selected()
  if not d then return end
  local s = State[d.name] or {}
  if s.state == "mounted" or s.state == "connecting" or s.state == "offline" then
    Vml("SshUnmount", d.name)
  else
    Mount(d)
  end
  Refresh()
end

function Ssh.OpenDrive(args)
  args = args or {}
  -- a connected drive opens in the file manager; one that isn't, connects
  local i, d = Selected()
  if not d then return end
  local s = State[d.name] or {}
  if s.state == "mounted" and not Can.android then
    local where = (s.detail or ""):gsub(" %(.*%)$", "")
    local why = where:match("^%a+://") and (Vml("OpenUrl", where) or "") or (Vml("OpenFolder", where) or "")
    if why ~= "" then Say("✕ " .. why, true) end
  else
    Ssh.Toggle()
  end
end

function Ssh.About(args)
  args = args or {}
  Vml("InfoDialog", "Mountie " .. VERSION .. "\n\n"
    .. "Everything you might open as a drive, in one place:\n"
    .. "folders on your SSH servers, disk images (ISO, IMG, VHD, VHDX),\n"
    .. "the computer's own partitions, your folders through an ignore list,\n"
    .. "and RAM disks. A drive letter on Windows,\n"
    .. "a folder in Files on Linux and macOS, the Files app on Android.\n\n"
    .. "Your passwords and keys stay on this device.\n\n"
    .. "Made by Steve (Wallisoft) and Claude, in Visualised.", "About Mountie")
end

function Ssh.TrayClick(args)
  args = args or {}
  local what = args[1] or ""
  if what == "open" or what == "Open Mountie" then
    Vml("ShowForm", "Mountie")
  elseif what == TrayTop then
    Ssh.About()
  elseif what == "Exit" then
    Vml("Quit")
  elseif TrayItems[what] then
    TrayToggle(TrayItems[what])
  end
end

function Ssh.BootChanged(args)
  args = args or {}
  local on = Vml("GetProperty", "chkBoot", "IsChecked") == "true"
  local now = Vml("StartAtBoot", tostring(on))
  if now == "on" or now == "off" then
    Vml("SetSetting", "at_boot", now)
  else
    Say(now)
  end
end

function Ssh.OpenForm(args)
  args = args or {}
  -- a new drive starts with the likeliest way in: the agent if it has keys, else the user's own key file, else a password
  local guess = Can.agent and "agent" or (Can.keys and #Can.keys > 0) and "key" or "password"
  local d = Editing and Drives[Editing] or { port = 22, auth = guess, automount = true, key = Can.keys and Tilde(Can.keys[1]) }
  Tested, PickedKey = nil, nil
  Vml("SetProperty", "lblTest", "Text", "")
  Vml("SetProperty", "lblForm", "Text", Editing and ("Change " .. d.name) or "A new drive")
  local function put(box, v) Vml("SetProperty", box, "Text", v == nil and "" or tostring(v)) end
  put("txtName", d.name); put("txtMount", d.mount); put("txtHost", d.host); put("txtPort", d.port ~= 22 and d.port or "")
  put("txtUser", d.user); put("txtRemote", d.remote); put("txtActAs", d.actas)
  if d.keytext and d.keytext ~= "" then
    PickedKey = { label = "(the key saved with this drive)", text = d.keytext }
    put("txtKey", PickedKey.label)
  else
    put("txtKey", d.key)
  end
  put("txtSecret", d.auth == "key" and d.passphrase or d.password)
  Vml("SetProperty", "cmbAuth", "SelectedIndex", d.auth == "password" and "0" or d.auth == "key" and "1" or "2")
  Vml("SetProperty", "chkAuto", "IsChecked", tostring(d.automount ~= false))
  Vml("SetProperty", "chkReadOnly", "IsChecked", tostring(d.readonly == true))
  Show(LIST, false); Show(TABS, false); Show(FOOT, false); Show(FORM, true)
  Vml("SetProperty", "btnAllow", "IsVisible", "false")          -- only when a Test finds sudo needs allowing
  Ssh.AuthChanged()
end

function Ssh.AuthChanged(args)
  args = args or {}
  local a = tostring(Vml("GetProperty", "cmbAuth", "SelectedIndex"))
  Vml("SetProperty", "txtSecret", "Watermark", a == "1" and "Key passphrase (if it has one)" or "Password")
  Vml("SetProperty", "txtSecret", "IsVisible", tostring(a ~= "2" and Vml("GetProperty", "btnSave", "IsVisible") == "true"))
  local keyOn = a == "1" and Vml("GetProperty", "btnSave", "IsVisible") == "true"
  Vml("SetProperty", "txtKey", "IsVisible", tostring(keyOn))
  Vml("SetProperty", "btnBrowse", "IsVisible", tostring(keyOn))
  if keyOn and (Vml("GetProperty", "txtKey", "Text") or "") == "" and Can.keys and Can.keys[1] then
    Vml("SetProperty", "txtKey", "Text", Tilde(Can.keys[1]))          -- the likeliest key
  end
end

function Ssh.AddDrive(args)
  args = args or {}
  Editing = nil
  Ssh.OpenForm()
end

function Ssh.EditDrive(args)
  args = args or {}
  Editing = Selected()
  if Editing then Ssh.OpenForm() end
end

function Ssh.CloseForm(args)
  args = args or {}
  Show(FORM, false); Show(LIST, true); Show(FOOT, true); if not Can.android then Show(TABS, true) end
  Refresh()
end

function Ssh.SaveDrive(args)
  args = args or {}
  local d = FormDrive()
  if d.host == "" then return Vml("SetProperty", "lblForm", "Text", "Which server? (Server is empty)") end
  local old = Editing and Drives[Editing]
  if old then
    Vml("SshUnmount", old.name)
    State[old.name] = nil
    Drives[Editing] = d
  else
    if Find(d.name) then return Vml("SetProperty", "lblForm", "Text", "There's already a drive called " .. d.name) end
    Drives[#Drives + 1] = d
  end
  Keep()
  Show(FORM, false); Show(LIST, true); Show(FOOT, true); if not Can.android then Show(TABS, true) end
  Mount(d)
  Refresh()
  Vml("SetProperty", "lstDrives", "SelectedIndex", tostring((Find(d.name)) - 1))   -- the drive just saved, picked
  Ssh.Picked()
end

function Ssh.RemoveDrive(args)
  args = args or {}
  local i, d = Selected()
  if not d then return end
  Vml("SshUnmount", d.name)
  State[d.name] = nil
  table.remove(Drives, i)
  Keep()
  Say(d.name .. " removed.")
  Refresh()
end

function Ssh.TestDrive(args)
  args = args or {}
  local d = FormDrive()
  if d.host == "" then return Vml("SetProperty", "lblTest", "Text", "Which server? (Server is empty)") end
  Vml("SetProperty", "lblTest", "Text", "Trying " .. d.host .. "...")
  Vml("SetProperty", "btnTest", "IsEnabled", "false")
  Vml("SshTest", json.encode(d), "OnTest")
end

function Ssh.OnTest(args)
  args = args or {}
  local name, state, detail, key = args[1] or "", args[2] or "", args[3] or "", args[4] or ""
  Vml("SetProperty", "btnTest", "IsEnabled", "true")
  local function marked(mark, text)                -- each step of the way comes with its own mark; a plain answer gets one
    if text:find("^✓") or text:find("^✕") then return text end
    return mark .. " " .. text
  end
  if state == "ok" then
    local d = FormDrive()
    Tested = { host = d.host, port = d.port, hostkey = key }
    local seen = (d.hostkey and d.hostkey ~= key) and "" or ("\nThe server's key: " .. key .. (d.hostkey == key and " (as before)" or " (remembered when you save)"))
    Vml("SetProperty", "lblTest", "Text", marked("✓", detail) .. (key ~= "" and seen or ""))
  else
    Vml("SetProperty", "lblTest", "Text", marked("✕", detail))
    if detail:find("Allow it on the server", 1, true) then Vml("SetProperty", "btnAllow", "IsVisible", "true") end
  end
end

function Ssh.BrowseKey(args)
  args = args or {}
  -- a computer keeps the key's path; a phone keeps the key itself (its files can't be read later)
  Vml("PickTextFile", "OnKeyFile", "Choose your SSH key", (Can.home or "~") .. "/.ssh")
end

function Ssh.OnKeyFile(args)
  args = args or {}
  local path, text, why = args[1] or "", args[2] or "", args[3] or ""
  if why ~= "" then return Vml("SetProperty", "lblTest", "Text", "✕ " .. why) end
  if path:match("%.pub$") or text:match("^ssh%-") or text:match("^ecdsa%-") then
    return Vml("SetProperty", "lblTest", "Text", "✕ That's the public half of a key (.pub): choose the file without .pub.")
  end
  if not text:find("PRIVATE KEY") then
    return Vml("SetProperty", "lblTest", "Text", "✕ That doesn't look like a private key (it should start -----BEGIN ... PRIVATE KEY-----).")
  end
  if Can.android then
    PickedKey = { label = (path:match("[^/\\]+$") or "key") .. " (picked)", text = text }
    Vml("SetProperty", "txtKey", "Text", PickedKey.label)
  else
    PickedKey = nil
    Vml("SetProperty", "txtKey", "Text", Tilde(path))
  end
  Vml("SetProperty", "lblTest", "Text", "Picked. If the key has a passphrase, put it in the box beside the sign-in choice, then Test.")
end

function Ssh.AllowSudo(args)
  args = args or {}
  -- once: a sudoers rule on the server letting this user run Mountie's file access as that user, no password after
  local d = FormDrive()
  local pw = Vml("PromptDialog", "Allow it on the server",
    "Your sudo password on " .. d.host .. ", so " .. (d.user ~= "" and d.user or "you") .. " can work as " .. d.actas
    .. " through Mountie.\nIt's used once and not kept.", "", "true") or ""
  if pw == "" then return end
  Vml("SetProperty", "lblTest", "Text", "Setting it up on " .. d.host .. "...")
  Vml("SshAllowSudo", json.encode(d), pw, "OnAllowed")
end

function Ssh.OnAllowed(args)
  args = args or {}
  local name, state, detail = args[1] or "", args[2] or "", args[3] or ""
  if state == "ok" then
    Vml("SetProperty", "btnAllow", "IsVisible", "false")
    Vml("SetProperty", "lblTest", "Text", "✓ " .. detail .. "\nTesting again...")
    Ssh.TestDrive()
  else
    Vml("SetProperty", "lblTest", "Text", "✕ " .. detail)
  end
end
