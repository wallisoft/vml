-- Mountie: the Phone tab.
--   on a computer:  phones on this Wi-Fi that are sharing themselves, each added as an SSH drive in a click
--   on a phone:     "Share this phone": its storage, as a drive on your computers (an SFTP server in the phone app)
-- A module of the Mountie project: every script in Mountie.vml can use what's here.

Phone = { found = {} }

local function set(n, p, v) Vml("SetProperty", n, p, v) end

function Phone.Show()
  Tab = "Phone"
  Say("")
  if Can.android then Vml("SetProperty", "chkBoot", "IsVisible", "false") Phone.Refresh() else Phone.Find() end
end

-- ── on a computer ────────────────────────────────────────────────────────────

function Phone.Find()
  set("lblPhone", "Text", "Looking for phones on this network…")
  set("lstPhones", "Items", "")
  local got = json.decode(Vml("PhonesNearby", "2") or "") or {}
  Phone.found = got
  local rows = {}
  for _, p in ipairs(got) do rows[#rows + 1] = p.name .. "   (" .. p.host .. ")" end
  set("lstPhones", "Items", table.concat(rows, ","))
  if #got > 0 then
    set("lstPhones", "SelectedIndex", "0")
    set("lblPhone", "Text", #got == 1 and "One phone is sharing itself. Add it, and type the password its Mountie shows."
        or (#got .. " phones are sharing themselves. Pick one, add it, and type the password its Mountie shows."))
  else
    set("lblPhone", "Text", "No phones found. On the phone: Mountie, the Share tab, Share this phone (same Wi-Fi as this computer). Then Look again.")
  end
end

function Phone.Add()
  local i = tonumber(Vml("GetProperty", "lstPhones", "SelectedIndex")) or -1
  local p = Phone.found[i + 1]
  if not p then Say("Pick a phone first (Look again if the list is empty).", true) return end
  Ssh.AddDrive({})
  set("txtName", "Text", p.name)
  set("txtHost", "Text", p.host)
  set("txtPort", "Text", tostring(p.port))
  set("txtUser", "Text", p.user or "phone")
  set("cmbAuth", "SelectedIndex", "0")
  set("txtSecret", "Text", "")
  set("lblTest", "Text", "Type the password the phone's Mountie shows (Share tab), then Test or Save and connect.")
end

-- ── on a phone ───────────────────────────────────────────────────────────────

function Phone.Refresh()
  local s = json.decode(Vml("PhoneShareStatus") or "") or {}
  set("btnShare", "Content", s.on and "Stop sharing" or "Share this phone")
  set("btnShare", "Background", s.on and "#B91C1C" or "#127A68")
  set("btnSharePass", "IsVisible", s.on and "true" or "false")
  if s.on then
    set("lblPhone", "Text", "Shared on this Wi-Fi. On your computer: Mountie, the Phone tab, and this phone is in the list.\n\n" ..
        "Address   " .. (s.address ~= "" and s.address or "(no Wi-Fi?)") .. ":" .. tostring(s.port) ..
        "\nUser        " .. (s.user or "phone") ..
        "\nPassword  " .. (s.password or "") ..
        "\n\nEverything a file manager sees on this phone: photos (DCIM), Download, Documents… Stop sharing when you're done.")
  elseif s.error and s.error ~= "" then
    set("lblPhone", "Text", "Sharing stopped: " .. s.error)
  else
    set("lblPhone", "Text", "Share this phone's storage with your computers, over Wi-Fi: its photos, downloads and documents " ..
        "as a drive in Mountie on your computer. Only someone with the password it shows can get in.\n\n" ..
        "The first time, Android asks you to allow \"All files access\" for this app: turn it on, come back and press Share again.")
  end
end

function Phone.Toggle()
  local s = json.decode(Vml("PhoneShareStatus") or "") or {}
  Vml("PhoneShare", s.on and "0" or "1", "OnPhoneShare")
  set("btnShare", "Content", s.on and "Stopping…" or "Starting…")
end

function Phone.On(a)
  local state, detail = a[1] or "", a[2] or ""
  if state == "files" then
    set("lblPhone", "Text", "Turn on \"All files access\" for this app in the Settings that opened, then come back and press Share this phone again.")
    set("btnShare", "Content", "Share this phone")
    return
  end
  if state == "error" then LogAdd("Sharing this phone: " .. detail, true) end
  Phone.Refresh()
end

function Phone.NewPass()
  local yes = Vml("ConfirmDialog", "Make a new password? A computer with the old one will have to be told the new one.", "New password")
  if yes == true or yes == "true" or yes == "True" then
    Vml("PhoneSharePassword")
    Phone.Refresh()
  end
end
