-- Mountie: disk images and partitions: the ISO, VHD and Partitions tabs.
-- A module of the Mountie project: every script in Mountie.vml can use what's here.

Disk = {}

function KeepImages() Vml("SetSetting", "images", json.encode(Images)) end

-- ── disk images and partitions ──
local DISKDOT = { mounted = "●", mounting = "◌", error = "✕" }

function DiskItems()                       -- what the tab shows: images of its kind, or the partitions
  if Tab == "Part" then return Parts end
  local out = {}
  for _, im in ipairs(Images) do if im.kind == (Tab == "Iso" and "iso" or "vhd") then out[#out + 1] = im end end
  return out
end

function DiskSelected()
  local i = tonumber(Vml("GetProperty", "lstDisk", "SelectedIndex") or "-1") or -1
  local items = DiskItems()
  if i >= 0 and items[i + 1] then return items[i + 1] end
end

function Places(detail) return ((detail or ""):gsub(" %([^)]*%)$", "")) end

function DiskLabel(it)
  local s = DiskState[it.name] or {}
  if Tab == "Part" then
    local where = s.state == "mounted" and Places(s.detail) or it.mounted
    local dot = it.system and "■" or (where ~= "" and "●" or (DISKDOT[s.state] or "·"))
    return dot .. " " .. it.name .. "   " .. (it.label ~= "" and (it.label .. "  ") or "") .. it.fstype .. "  " .. it.size
      .. (where ~= "" and ("   →  " .. where) or "") .. (it.system and "  (this computer's own)" or "")
  end
  local label = (DISKDOT[s.state] or "·") .. " " .. it.name .. (it.readonly and "   read only" or "")
  if s.state == "mounted" then label = label .. "   →  " .. Tilde(Places(s.detail)):gsub(", ", "   ") end
  return label
end

function RefreshDisk()
  local rows = {}
  for _, it in ipairs(DiskItems()) do rows[#rows + 1] = (DiskLabel(it):gsub(",", " ")) end
  local keep = Vml("GetProperty", "lstDisk", "SelectedIndex")
  Vml("SetProperty", "lstDisk", "Items", table.concat(rows, ","))
  if keep and keep ~= "-1" and tonumber(keep) < #rows then Vml("SetProperty", "lstDisk", "SelectedIndex", keep) end
  Disk.DiskPicked()
  Refresh()
end

function ListParts()
  local got = json.decode(Vml("DiskList") or "") or {}
  if got.error then Say("✕ " .. got.error, true); Parts = {}; return end
  Parts = {}
  for _, p in ipairs(got) do
    Parts[#Parts + 1] = { name = p.name, path = p.path, kind = "part", label = p.label or "", fstype = p.fstype or "",
                          size = p.size or "", mounted = p.mounted or "", system = p.system, readonly = false }
  end
end

function DiskMount(it)
  DiskState[it.name] = { state = "mounting", detail = "" }
  Vml("DiskMount", json.encode({ name = it.name, path = it.path, kind = it.kind, readonly = it.readonly }), "OnDisk")
end

-- the events

function Disk.DiskPicked(args)
  args = args or {}
  local it = DiskSelected()
  local s = it and DiskState[it.name] or {}
  local up = s.state == "mounted" or s.state == "mounting" or (Tab == "Part" and it and it.mounted ~= "")
  Vml("SetProperty", "btnDiskToggle", "Content", up and "Unmount" or "Mount")
  for _, n in ipairs({ "btnDiskToggle", "btnDiskOpen", "btnDiskRemove", "chkDiskRO", "chkDiskAuto" }) do
    Vml("SetProperty", n, "IsEnabled", tostring(it ~= nil and not (n == "btnDiskToggle" and it.system)))
  end
  if it then
    Vml("SetProperty", "chkDiskRO", "IsChecked", tostring(it.readonly == true))
    Vml("SetProperty", "chkDiskAuto", "IsChecked", tostring(it.automount == true))
    if s.state == "error" then Say("✕ " .. it.name .. ": " .. s.detail, true)
    elseif s.state == "mounted" then Say(it.name .. ": " .. Places(s.detail) .. "\nDouble-click it to open it.")
    elseif it.system then Say(it.name .. " is part of this computer's own system, so Mountie leaves it alone.")
    elseif Tab ~= "Part" then Say(it.name .. ": " .. Tilde(it.path))
    elseif Tab == "Part" and it.mounted ~= "" then Say(it.name .. " is at " .. it.mounted .. ". Double-click it to open it.") end
  end
end

function Disk.DiskToggle(args)
  args = args or {}
  local it = DiskSelected()
  if not it or it.system then return end
  local s = DiskState[it.name] or {}
  if s.state == "mounted" or s.state == "mounting" or (Tab == "Part" and it.mounted ~= "") then
    Say("Unmounting " .. it.name .. "...")
    Vml("DiskUnmount", json.encode({ name = it.name, path = it.path, kind = it.kind }), "OnDisk")
  else
    Say("Mounting " .. it.name .. "...")
    DiskMount(it)
  end
  RefreshDisk()
end

function Disk.OnDisk(args)
  args = args or {}
  local name, state, detail = args[1] or "", args[2] or "", args[3] or ""
  DiskState[name] = { state = state, detail = detail }
  if state == "mounted" then
    Say(name .. ": " .. Places(detail) .. "\nDouble-click it to open it.")
    Vml("TrayMessage", name .. " mounted", Places(detail))
  elseif state == "error" then
    Say("✕ " .. name .. ": " .. detail, true)
  elseif state == "off" then
    Say(name .. " unmounted.")
    DiskState[name] = nil
  end
  if Tab == "Part" then ListParts() end
  if Tab ~= "Ssh" then RefreshDisk() else Refresh() end
end

function Disk.DiskOpen(args)
  args = args or {}
  local it = DiskSelected()
  if not it then return end
  local s = DiskState[it.name] or {}
  local where = s.state == "mounted" and Places(s.detail):match("^[^,]+") or (it.mounted ~= "" and it.mounted) or nil
  if not where then return Disk.DiskToggle() end    -- not mounted yet: mount it
  local why = Vml("OpenFolder", where) or ""
  if why ~= "" then Say("✕ " .. why, true) end
end

function Disk.DiskAdd(args)
  args = args or {}
  if Tab == "Part" then ListParts(); return RefreshDisk() end
  local iso = Tab == "Iso"
  local path = Vml("FileOpenDialog", iso and "Choose a disk image" or "Choose a virtual disk",
    iso and "iso,img,dmg" or (Can.windows and "vhd,vhdx" or "vhd,vhdx,img,raw,vmdk,qcow2,vdi"), (Can.home or "~") .. "/Downloads") or ""
  if path == "" then return end
  for _, im in ipairs(Images) do if im.path == path then return Say(im.name .. " is here already.") end end
  local name = path:match("[^/\\]+$") or path
  local n, base = 2, name
  while true do
    local clash = false
    for _, im in ipairs(Images) do if im.name == name then clash = true end end
    if not clash then break end
    name = base .. " (" .. n .. ")"; n = n + 1
  end
  local it = { name = name, path = path, kind = iso and "iso" or "vhd", readonly = iso, automount = false }
  Images[#Images + 1] = it
  KeepImages()
  RefreshDisk()
  local items = DiskItems()
  for i, x in ipairs(items) do if x.name == name then Vml("SetProperty", "lstDisk", "SelectedIndex", tostring(i - 1)) end end
  Disk.DiskPicked()
  Say(name .. " added. Mount it to open it" .. (iso and "." or " (Windows asks for admin for a VHD)."))
end

function Disk.DiskRemove(args)
  args = args or {}
  local it = DiskSelected()
  if not it or Tab == "Part" then return end
  if (DiskState[it.name] or {}).state == "mounted" then Vml("DiskUnmount", json.encode(it), "OnDisk") end
  for i, im in ipairs(Images) do if im.name == it.name then table.remove(Images, i) break end end
  KeepImages()
  Say(it.name .. " taken off the list (the file itself is left where it is).")
  RefreshDisk()
end

function Disk.DiskOptions(args)
  args = args or {}
  local it = DiskSelected()
  if not it then return end
  it.readonly = Vml("GetProperty", "chkDiskRO", "IsChecked") == "true"
  it.automount = Vml("GetProperty", "chkDiskAuto", "IsChecked") == "true"
  if Tab ~= "Part" then KeepImages() end
  if (DiskState[it.name] or {}).state == "mounted" then Say("Read only takes effect the next time " .. it.name .. " is mounted.") end
  RefreshDisk()
end
