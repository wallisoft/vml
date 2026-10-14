-- Mountie: what every tab uses (groups of controls, the status line, the tabs).
-- A module of the Mountie project: every script in Mountie.vml can use what's here.

-- a path in the user's home, shown the short way (~/.ssh/id_ed25519); the drive keeps it so and expands it later
function Tilde(p)
  local home = Can and Can.home or ""
  if p and home ~= "" and p:sub(1, #home) == home then return "~" .. p:sub(#home + 1) end
  return p
end

function Show(names, on) for _, n in ipairs(names) do Vml("SetProperty", n, "IsVisible", tostring(on)) end end

function Say(text, bad)                -- a problem in red, so it isn't missed
  Vml("SetProperty", "lblStatus", "Foreground", bad and "#B91C1C" or "#374151")
  Vml("SetProperty", "lblStatus", "Text", text)
end

-- ── the log: what happened to the drives, newest first; ⚠ on the Log button until new problems are looked at ──
function LogAdd(text, bad)
  if LOG[1] and LOG[1].text == text then return end              -- (a drive that keeps failing the same way: once)
  table.insert(LOG, 1, { t = os.date("%d %b %H:%M"), text = text, bad = bad == true })
  while #LOG > 200 do table.remove(LOG) end
  if bad then Unseen = Unseen + 1 end
  Vml("SetSetting", "log", json.encode(LOG))
  Vml("SetSetting", "log_unseen", tostring(Unseen))
  LogButton()
end

function LogButton()
  local new = Unseen > 0
  Vml("SetProperty", "btnLog", "Content", new and ("⚠ " .. Unseen) or "Log")
  Vml("SetProperty", "btnLog", "Background", new and "#FEF3C7" or "#E4EAE8")
  Vml("SetProperty", "btnLog", "Foreground", new and "#92400E" or "#4B5563")
  Vml("SetProperty", "btnLog", "ToolTip", new and (Unseen .. " new problem" .. (Unseen == 1 and "" or "s") .. ": click to see")
    or "What happened to the drives")
end

function ShowLog()
  Unseen = 0
  Vml("SetSetting", "log_unseen", "0")
  LogButton()
  Refresh()                                                     -- (the tray's Log item too)
  if Vml("FormOpenModal", "Log.vml") == "clear" then
    LOG = {}
    Vml("SetSetting", "log", "[]")
  end
end

-- the status bar: how many are mounted
function BarText(up)
  Vml("SetProperty", "lblBar", "Text", up == 0 and "Nothing mounted" or (up == 1 and "● 1 drive mounted" or ("● " .. up .. " drives mounted")))
end

-- a list's item moved one place up (-1) or down (1) among those of its kind; returns its new place or nil
function MoveIn(list, item, step, same)
  local at
  for i, x in ipairs(list) do if x == item then at = i end end
  if not at then return end
  local j = at + step
  while list[j] and not same(list[j]) do j = j + step end
  if not list[j] then return end
  list[at], list[j] = list[j], list[at]
  return j
end

-- ── tabs ──
local TABNAMES = { "Ssh", "Iso", "Vhd", "Part", "Fold", "Ram" }
local HELP = {
  Iso = "Disk images (ISO, IMG, DMG). Add one, then Mount it: it opens like a CD or a stick.",
  Part = "This computer's disks and sticks. The ones it runs from are left alone.",
  Fold = "A folder of yours as a drive of its own, showing only what you want: ~/Downloads as DownloadFiles, "
    .. "without the installers and the clutter. Every app's Open box sees it too.",
  Ram = "A RAM disk: very fast, and gone when Mountie stops (unless you tell it to keep what's on it).",
}

function Local() return Tab == "Fold" or Tab == "Ram" end      -- the tabs whose drives Mountie makes itself

function ShowTab(t)
  Tab = t
  for _, n in ipairs(TABNAMES) do
    Vml("SetProperty", "btnTab" .. n, "Background", n == t and "#127A68" or "#E5E7EB")
    Vml("SetProperty", "btnTab" .. n, "Foreground", n == t and "#FFFFFF" or "#374151")
  end
  Show(LIST, t == "Ssh"); Show(DISK, t ~= "Ssh"); Show(FOOT, true)
  Show({ "btnDiskShows" }, Local())
  Vml("SetProperty", "btnDiskShows", "Content", t == "Ram" and "Size and keeping..." or "What it shows...")
  Vml("SetControlPosition", "chkBoot", "24", Local() and "490" or "446")      -- room for the button above
  Vml("SetControlPosition", "lblStatus", "24", Local() and "524" or "480")
  Vml("SetProperty", "lblStatus", "Height", Local() and "128" or "172")
  if t ~= "Ssh" then
    Vml("SetProperty", "btnDiskAdd", "Content", t == "Part" and "Refresh" or "Add")
    for _, n in ipairs({ "btnDiskRemove", "btnDiskRename", "chkDiskAuto", "chkDiskOn" }) do
      Vml("SetProperty", n, "IsVisible", tostring(t ~= "Part"))
    end
    Vml("SetProperty", "chkDiskRO", "IsVisible", tostring(t ~= "Ram"))
    if t == "Part" then ListParts() end
    RefreshDisk()
    Say(HELP[t] or ("Virtual disks (VHD, VHDX" .. (Can.windows and "" or ", IMG as no-stick makes them, VMDK, QCOW2")
      .. "). Each partition inside becomes a drive."))
  else
    Refresh()
    Say(#Drives == 0 and "Add a folder on one of your servers to start: Add, then Test, then Save." or (TrayNote or ""))
  end
end
