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

-- ── tabs ──
function ShowTab(t)
  Tab = t
  for _, n in ipairs({ "Ssh", "Iso", "Vhd", "Part" }) do
    Vml("SetProperty", "btnTab" .. n, "Background", n == t and "#127A68" or "#E5E7EB")
    Vml("SetProperty", "btnTab" .. n, "Foreground", n == t and "#FFFFFF" or "#374151")
  end
  Show(LIST, t == "Ssh"); Show(DISK, t ~= "Ssh"); Show(FOOT, true)
  if t ~= "Ssh" then
    Vml("SetProperty", "btnDiskAdd", "Content", t == "Part" and "Refresh" or "Add")
    Vml("SetProperty", "btnDiskRemove", "IsVisible", tostring(t ~= "Part"))
    Vml("SetProperty", "chkDiskAuto", "IsVisible", tostring(t ~= "Part"))
    if t == "Part" then ListParts() end
    RefreshDisk()
    Say(t == "Iso" and "Disk images (ISO, IMG, DMG). Add one, then Mount it: it opens like a CD or a stick."
        or t == "Vhd" and "Virtual disks (VHD, VHDX" .. (Can.windows and "" or ", VMDK, QCOW2") .. "). Each partition inside becomes a drive."
        or "This computer's disks and sticks. The ones it runs from are left alone.")
  else
    Refresh()
    Say(#Drives == 0 and "Add a folder on one of your servers to start: Add, then Test, then Save." or "")
  end
end
