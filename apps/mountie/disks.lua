-- Mountie: disk images and partitions: the ISO, VHD and Partitions tabs.
-- A module of the Mountie project: every script in Mountie.vml can use what's here.

Disk = {}

function KeepImages() Vml("SetSetting", "images", json.encode(Images)) end

-- ── disk images and partitions ──
local DISKDOT = { mounted = "●", mounting = "◌", error = "✕" }

function DiskItems()                       -- what the tab shows: images of its kind, or the partitions
  if Tab == "Part" then return Parts end
  local kind = ({ Iso = "iso", Vhd = "vhd", Fold = "folder", Ram = "ram" })[Tab]
  local out = {}
  for _, im in ipairs(Images) do if im.kind == kind then out[#out + 1] = im end end
  return out
end

function DiskSelected()
  local i = tonumber(Vml("GetProperty", "lstDisk", "SelectedIndex") or "-1") or -1
  local items = DiskItems()
  if i >= 0 and items[i + 1] then return items[i + 1] end
end

function Places(detail) return ((detail or ""):gsub(" %([^)]*%)$", "")) end

-- what an image is (format, size, label, partitions), read from the file once
function ImageInfo(it)
  if it.kind == "folder" or it.kind == "ram" then return LocalInfo(it) end
  if not Info[it.path] then Info[it.path] = json.decode(Vml("DiskInfo", it.path) or "") or {} end
  return Info[it.path]
end
function InfoLine(i)                       -- "ISO 9660 'Ubuntu 24.04 LTS', 5.8 GB" / "raw disk, 2 partitions, 20 GB"
  local bits = { (i.format or "") ~= "" and i.format or "disk image" }
  if (i.label or "") ~= "" then bits[1] = bits[1] .. " '" .. i.label .. "'" end
  if (i.partitions or 0) > 0 then bits[#bits + 1] = i.partitions .. (i.partitions == 1 and " partition" or " partitions") end
  if (i.size_text or "") ~= "" then bits[#bits + 1] = i.size_text end
  return table.concat(bits, ", ")
end

-- a folder or RAM drive, described the way an image is ("format": what it shows; "size_text")
function Rules(hide)                       -- how many rules (lines) an ignore list has
  local n = 0
  for line in ((hide or "") .. "\n"):gmatch("([^\n]*)\n") do
    if line:match("%S") and not line:match("^%s*#") then n = n + 1 end
  end
  return n
end
function LocalInfo(it)
  if it.kind == "ram" then
    return { format = "RAM disk", size_text = (it.size or 512) .. " MB" .. (it.keep and it.keep ~= "" and ", kept" or "") }
  end
  local n = Rules(it.hide)
  return { format = Tilde(it.path), size_text = n == 0 and "everything" or
           ((it.showonly and "only " or "less ") .. n .. (n == 1 and " rule" or " rules")) }
end

function DiskLabel(it)
  local s = DiskState[it.name] or {}
  if Tab == "Part" then
    local where = s.state == "mounted" and Places(s.detail) or it.mounted
    local dot = it.system and "■" or (where ~= "" and "●" or (DISKDOT[s.state] or "·"))
    return dot .. " " .. it.name .. "   " .. (it.label ~= "" and (it.label .. "  ") or "") .. it.fstype .. "  " .. it.size
      .. (where ~= "" and ("   →  " .. where) or "") .. (it.system and "  (this computer's own)" or "")
  end
  local i = ImageInfo(it)
  if it.enabled == false then return "–  " .. it.name .. "   (off)   " .. (i.format or "") .. "  " .. (i.size_text or "") end
  local label = (DISKDOT[s.state] or "·") .. " " .. it.name .. "   " .. (i.format or "") .. "  " .. (i.size_text or "")
    .. (it.readonly and "  read only" or "")
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
  Vml("DiskMount", json.encode({ name = it.name, path = it.path, kind = it.kind, readonly = it.readonly, hide = it.hide,
                                 showonly = it.showonly, size = it.size, keep = it.keep }), "OnDisk")
end

-- a name nothing else here has
function FreeName(name)
  local n, base = 2, name
  while true do
    local clash = false
    for _, im in ipairs(Images) do if im.name == name then clash = true end end
    if not clash then return name end
    name = base .. " " .. n; n = n + 1
  end
end

function Select(name)
  for i, x in ipairs(DiskItems()) do if x.name == name then Vml("SetProperty", "lstDisk", "SelectedIndex", tostring(i - 1)) end end
  Disk.DiskPicked()
end

function AddLocal()
  local it
  if Tab == "Fold" then
    local path = Vml("FolderDialog", "Choose a folder to show as a drive", (Can.home or "~") .. "/Downloads") or ""
    if path == "" then return end
    local base = (path:match("([^/\\]+)[/\\]*$") or "Folder"):gsub("^%l", string.upper)
    local name = (Vml("PromptDialog", "Name it", "What to call the drive (it shows by this name in Files):",
      FreeName(base .. "Files")) or ""):match("^%s*(.-)%s*$")
    if name == "" then return end
    it = { name = FreeName(name), path = Tilde(path), kind = "folder", hide = "", showonly = false, readonly = false,
           automount = true, enabled = true }
  else
    local name = (Vml("PromptDialog", "Name it", "What to call the RAM disk:", FreeName("RamDisk")) or ""):match("^%s*(.-)%s*$")
    if name == "" then return end
    it = { name = FreeName(name), path = "", kind = "ram", size = 512, keep = "", automount = false, enabled = true }
  end
  Images[#Images + 1] = it
  KeepImages()
  RefreshDisk()
  Select(it.name)
  if it.kind == "folder" then
    Disk.DiskShows()                                   -- straight on to what it should show
  else
    Say(it.name .. " added: 512 MB, emptied each time. \"Size and keeping\" changes that; Mount starts it.")
  end
end

-- the events

-- right-click on an image, a folder, a RAM disk or a partition
function Disk.MenuShow(args)
  local it = DiskSelected()
  if not it then return end
  local s = DiskState[it.name] or {}
  local where = s.state == "mounted" and Places(s.detail):match("^[^,]+") or (it.mounted ~= nil and it.mounted ~= "" and it.mounted)
    or (it.kind == "folder" and it.path) or nil
  TermAt = where
  local items = DiskItems()
  local first, last = items[1] == it, items[#items] == it
  Vml("SetProperty", "mnuDiskTerm", "IsEnabled", tostring(where ~= nil))
  Vml("SetProperty", "mnuDiskTerm", "Text", where and "Open a terminal there" or "Open a terminal there (mount it first)")
  for _, n in ipairs({ "mnuDiskUp", "mnuDiskDown", "mnuDiskRename", "mnuDiskRemove", "mnuDiskSep2" }) do
    Vml("SetProperty", n, "IsVisible", tostring(Tab ~= "Part"))
  end
  Vml("SetProperty", "mnuDiskUp", "IsEnabled", tostring(not first))
  Vml("SetProperty", "mnuDiskDown", "IsEnabled", tostring(not last))
  Vml("ShowContextMenu", "DiskMenu")
end

function Disk.Term(args)
  if not TermAt then return end
  local why = Vml("OpenTerminal", TermAt) or ""
  if why ~= "" then Say("✕ " .. why, true) end
end

function Disk.Move(step)
  local it = DiskSelected()
  if not it or Tab == "Part" then return end
  if not MoveIn(Images, it, step, function(x) return x.kind == it.kind end) then return end
  KeepImages()
  RefreshDisk()
  Select(it.name)
end

function Disk.RemoveAsk(args)
  local it = DiskSelected()
  if not it or Tab == "Part" then return end
  local what = it.kind == "ram" and "\n(What's on it goes too, unless it's kept.)" or "\n(The " .. (it.kind == "folder" and "folder" or "file")
    .. " itself is left where it is.)"
  if Vml("ChoiceDialog", "Remove " .. it.name .. " from Mountie?" .. what, "Remove", "Remove|Cancel") == "Remove" then
    Disk.DiskRemove()
  end
end

function Disk.DiskShows(args)
  local it = DiskSelected()
  if not it or not Local() then return Say("Pick a drive in the list first.", true) end
  local up = (DiskState[it.name] or {}).state == "mounted"
  if it.kind == "ram" then
    local mb = tonumber((Vml("PromptDialog", "Size", "How big " .. it.name .. " can grow, in MB:", tostring(it.size or 512)) or "")
      :match("%d+") or "")
    if not mb then return end
    it.size = math.max(1, mb)
    local keep = Vml("ChoiceDialog", "When Mountie stops, should " .. it.name .. " keep what's on it for next time?\n"
      .. "(It's saved to a file in your home folder, and put back when it starts.)", "Keeping", "Keep it|Start empty each time")
    if keep == "Keep it" then it.keep = "~/.mountie/" .. it.name:gsub("[^%w%-_]", "_") .. ".zip"
    elseif keep ~= "" then it.keep = "" end
  else
    Vml("SetSetting", "hide_edit", json.encode({ name = it.name, path = it.path, hide = it.hide or "", showonly = it.showonly }))
    local got = json.decode(Vml("FormOpenModal", "Hide.vml") or "")
    if type(got) ~= "table" then return end
    it.hide, it.showonly = got.hide or "", got.showonly == true
  end
  KeepImages()
  RefreshDisk()
  Say(it.name .. ": " .. InfoLine(ImageInfo(it)) .. (up and "\nUnmount and mount it again to see the change." or ""))
end

function Disk.DiskPicked(args)
  args = args or {}
  local it = DiskSelected()
  local s = it and DiskState[it.name] or {}
  local up = s.state == "mounted" or s.state == "mounting" or (Tab == "Part" and it and it.mounted ~= "")
  Vml("SetProperty", "btnDiskToggle", "Content", up and "Unmount" or "Mount")
  for _, n in ipairs({ "btnDiskToggle", "btnDiskOpen", "btnDiskRename", "btnDiskRemove", "chkDiskRO", "chkDiskAuto", "chkDiskOn" }) do
    local off = it ~= nil and it.enabled == false and (n == "btnDiskToggle" or n == "btnDiskOpen")
    Vml("SetProperty", n, "IsEnabled", tostring(it ~= nil and not off and not (n == "btnDiskToggle" and it.system)))
  end
  if it then
    Vml("SetProperty", "chkDiskRO", "IsChecked", tostring(it.readonly == true))
    Vml("SetProperty", "chkDiskAuto", "IsChecked", tostring(it.automount == true))
    Vml("SetProperty", "chkDiskOn", "IsChecked", tostring(it.enabled ~= false))
    if s.state == "error" then Say("✕ " .. it.name .. ": " .. s.detail, true)
    elseif s.state == "mounted" then
      Say(it.name .. (Tab ~= "Part" and (": " .. InfoLine(ImageInfo(it))) or "") .. "\nMounted at " .. Tilde(Places(s.detail))
        .. ". Double-click it to open it.")
    elseif it.system then Say(it.name .. " is part of this computer's own system, so Mountie leaves it alone.")
    elseif Tab ~= "Part" then
      local i = ImageInfo(it)
      Say(it.name .. ": " .. InfoLine(i) .. (Local() and "" or ("\n" .. Tilde(it.path)))
        .. (it.enabled == false and "\nOff: tick Enabled to use it." or ""), i.error ~= nil)
    elseif Tab == "Part" and it.mounted ~= "" then Say(it.name .. " is at " .. it.mounted .. ". Double-click it to open it.") end
  end
end

function Disk.DiskToggle(args)
  args = args or {}
  local it = DiskSelected()
  if not it or it.system then return end
  if it.enabled == false then return Say(it.name .. " is off: tick Enabled to use it.", true) end
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
    LogAdd("● " .. name .. " mounted at " .. Tilde(Places(detail)))
    Say(name .. ": " .. Places(detail) .. "\nDouble-click it to open it.")
    Vml("TrayMessage", name .. " mounted", Places(detail))
  elseif state == "error" then
    LogAdd("✕ " .. name .. ": " .. detail, true)
    Say("✕ " .. name .. ": " .. detail, true)
  elseif state == "off" then
    LogAdd("○ " .. name .. " unmounted")
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
  if Local() then return AddLocal() end
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
  local given = (Vml("PromptDialog", "Name it", "What to call it in Mountie (" .. name .. "):", (name:gsub("%.%w+$", ""))) or "")
    :match("^%s*(.-)%s*$")
  if given ~= "" and given ~= name then
    local taken = false
    for _, im in ipairs(Images) do if im.name == given then taken = true end end
    if not taken then name = given end
  end
  local it = { name = name, path = path, kind = iso and "iso" or "vhd", readonly = iso, automount = false, enabled = true }
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
  if Tab ~= "Part" then
    local was = it.enabled ~= false
    it.enabled = Vml("GetProperty", "chkDiskOn", "IsChecked") == "true"
    if was and not it.enabled and (DiskState[it.name] or {}).state == "mounted" then
      Vml("DiskUnmount", json.encode(it), "OnDisk")              -- switched off: unmounted too
    end
    KeepImages()
  end
  if (DiskState[it.name] or {}).state == "mounted" then Say("Read only takes effect the next time " .. it.name .. " is mounted.") end
  RefreshDisk()
end

function Disk.DiskRename(args)
  args = args or {}
  local it = DiskSelected()
  if not it or Tab == "Part" then return end
  local new = (Vml("PromptDialog", "Rename", "A new name for " .. it.name .. ":", it.name) or ""):match("^%s*(.-)%s*$")
  if new == "" or new == it.name then return end
  for _, im in ipairs(Images) do if im.name == new then return Say("There's already one called " .. new .. ".", true) end end
  if (DiskState[it.name] or {}).state == "mounted" then return Say("Unmount " .. it.name .. " first, then rename it.", true) end
  it.name = new
  KeepImages()
  RefreshDisk()
  Say("Renamed: " .. new .. ".")
end
