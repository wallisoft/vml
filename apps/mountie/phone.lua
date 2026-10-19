-- Mountie: the Phone tab.
--   on a computer:  phones on this Wi-Fi that are sharing themselves, each added as a drive in a click; and
--                   "Pair a phone": a QR code with this computer's key, for the phone to scan (once)
--   on a phone:     "Share this phone": its storage, as a drive on your paired computers (an SFTP server in the
--                   phone app); "Pair a computer" scans a computer's code. No passwords: only paired computers get in.
-- A module of the Mountie project: every script in Mountie.vml can use what's here.

Phone = { found = {}, pairing = false }

local function set(n, p, v) Vml("SetProperty", n, p, v) end

function Phone.Show()
  Tab = "Phone"
  Say("")
  if Can.android then
    Vml("SetProperty", "chkBoot", "IsVisible", "false")
    Vml("SetControlPosition", "lblStatus", "24", "604")     -- (under the list of paired computers)
    Vml("SetProperty", "lblStatus", "Height", "54")
    Phone.Refresh()
  else
    Phone.PairHide()
    Phone.Find()
  end
end

-- ── on a computer ────────────────────────────────────────────────────────────

function Phone.Find()
  set("lblPhone", "Text", "Looking for phones on this network…")
  set("lstPhones", "Items", "")
  local got = json.decode(Vml("PhonesNearby", "1.5") or "") or {}
  Phone.found = got
  local rows = {}
  for _, p in ipairs(got) do rows[#rows + 1] = p.name .. "   (" .. p.host .. ")" end
  set("lstPhones", "Items", table.concat(rows, ","))
  if #got > 0 then
    set("lstPhones", "SelectedIndex", "0")
    set("lblPhone", "Text", (#got == 1 and "A phone is sharing itself." or (#got .. " phones are sharing themselves.")) ..
        " Add it as a drive. (Paired it yet? Pair a phone, once, first.)")
  else
    set("lblPhone", "Text", "No phones found. On the phone: Mountie, the Share tab, Share this phone (on the same Wi-Fi as " ..
        "this computer). Then Look again. First time? Pair a phone.")
  end
end

-- the QR code with this computer's key, for the phone to scan
function Phone.PairShow()
  if Phone.pairing then Phone.PairHide() Phone.Find() return end
  local p = json.decode(Vml("PhonePairCode") or "") or {}
  if not p.code then Say("Couldn't make this computer's key for phones: see the log.", true) return end
  Phone.pairing = true
  set("imgPair", "Source", Vml("QrCode", p.code, "5"))
  Show({ "lstPhones" }, false)
  Show({ "imgPair" }, true)
  set("btnPhonePair", "Content", "Done")
  set("lblPhone", "Text", "On the phone: Mountie, the Share tab, Pair a computer, and point it at this code. " ..
      "Once is enough: from then on this computer gets in with its key, no password.")
end

function Phone.PairHide()
  Phone.pairing = false
  Show({ "imgPair" }, false)
  Show({ "lstPhones" }, true)
  set("btnPhonePair", "Content", "Pair a phone")
end

function Phone.Add()
  local i = tonumber(Vml("GetProperty", "lstPhones", "SelectedIndex")) or -1
  local p = Phone.found[i + 1]
  if not p then Say("Pick a phone first (Look again if the list is empty).", true) return end
  local pair = json.decode(Vml("PhonePairCode") or "") or {}
  Phone.PairHide()
  Ssh.AddDrive({})
  set("txtName", "Text", p.name)
  set("txtHost", "Text", p.host)
  set("txtPort", "Text", tostring(p.port))
  set("txtUser", "Text", p.user or "phone")
  set("cmbAuth", "SelectedIndex", "1")
  Ssh.AuthChanged({})
  set("txtKey", "Text", pair.key or "")
  set("txtSecret", "Text", "")
  set("lblTest", "Text", "This computer's key for phones is filled in. Paired with the phone? Save and connect. " ..
      "If not: Cancel, Pair a phone, and scan its code on the phone first.")
end

-- ── on a phone ───────────────────────────────────────────────────────────────

function Phone.Refresh()
  local s = json.decode(Vml("PhoneShareStatus") or "") or {}
  local pcs = s.computers or {}
  set("btnShare", "Content", s.on and "Stop sharing" or "Share this phone")
  set("btnShare", "Background", s.on and "#B91C1C" or "#127A68")
  set("lstComputers", "Items", table.concat(pcs, ","))
  if #pcs > 0 then set("lstComputers", "SelectedIndex", "0") end
  Show({ "btnForget" }, #pcs > 0)
  local paired = #pcs == 0 and "No computers paired yet: Pair a computer, and scan the code its Mountie shows (Phone tab, Pair a phone)."
      or ("Paired: " .. table.concat(pcs, ", ") .. ". Only these get in.")
  if s.on then
    set("lblPhone", "Text", "Shared on this Wi-Fi" .. (s.address ~= "" and (" (" .. s.address .. ")") or "") ..
        ". On your computer: Mountie, the Phone tab, and this phone is in the list.\n\n" .. paired ..
        "\n\nEverything a file manager sees on this phone: photos (DCIM), Download, Documents… Stop sharing when you're done.")
  elseif s.error and s.error ~= "" then
    set("lblPhone", "Text", "Sharing stopped: " .. s.error)
  else
    set("lblPhone", "Text", "Share this phone's storage with your computers, over Wi-Fi: its photos, downloads and documents " ..
        "as a drive in Mountie on your computer.\n\n" .. paired ..
        "\n\nThe first time, Android asks you to allow \"All files access\" for this app: turn it on, come back and press Share again.")
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

function Phone.Pair()
  Vml("ScanCode", "PhonePaired", "The code Mountie shows on your computer (Phone tab, Pair a phone):")
end

function Phone.Paired(a)
  local code, problem = a[1] or "", a[2] or ""
  if code == "" then if problem ~= "" then Say(problem, true) end return end
  local why = Vml("PhoneSharePair", code) or ""
  if why ~= "" then Say(why, true) else Say("Paired: that computer can mount this phone now.") end
  Phone.Refresh()
end

function Phone.Forget()
  local name = Vml("GetProperty", "lstComputers", "SelectedItem") or ""
  if name == "" then return end
  local yes = Vml("ConfirmDialog", "Forget " .. name .. "? It won't be able to get in until it's paired again.", "Forget a computer")
  if yes == true or yes == "true" or yes == "True" then
    Vml("PhoneShareForget", name)
    Phone.Refresh()
  end
end
