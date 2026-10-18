-- The Visualised designer: the design surface: adding, selecting and arranging controls, and their scripts.
-- One of the modules of designer/Designer.vmlproj. Each function here is a handler: a control or menu item of the
-- designer names it (OnClick=FileSave), or another handler runs it with Vml("RunScript", "FileSave").

function AddControl(...)
    local args = { ... }
    local name = Vml("AddDesignControl", args[1], Vml("GetSetting", "click_x"), Vml("GetSetting", "click_y"))
    if name ~= "" then Vml("SetStatusText", "Added " .. name) end
end

function ShowSurfaceMenu(...)
    local selected = Vml("GetProperty", "Surface", "Selected") ~= ""
    for _, item in ipairs({"CtxEditScript", "CtxCut", "CtxCopy", "CtxDuplicate", "CtxFront", "CtxBack", "CtxDelete"}) do
        Vml("SetMenuItemEnabled", item, selected)
    end
    Vml("SetMenuItemEnabled", "CtxPaste", Vml("CanPaste") == "true")
    Vml("SetMenuItemEnabled", "CtxAlign", Vml("GetProperty", "Surface", "SelectedAll"):find(",") ~= nil)   -- a group
    Vml("SetMenuItemEnabled", "CtxAddMenu", Vml("GetDesignMenu", "Surface") == "[]")
    Vml("ShowContextMenu", "SurfaceMenu")
end

function SelectionChanged(...)
    local sel = Vml("GetProperty", "Surface", "Selected")
    Vml("SetProperty", "Props", "Target", sel ~= "" and sel or "Surface")
    Vml("RunScript", "ShowGeometry")
end

function DesignChanged(...)
    Vml("UndoMark")
    Vml("SetSetting", "dirty", "true")
    Vml("RunScript", "UpdateTitle")
    Vml("RunScript", "ShowGeometry")
end

function EditScript(...)
    local args = { ... }
    -- open the script editor (itself a VML form) for the selected control
    local sel = Vml("GetProperty", "Surface", "Selected")
    if sel == "menubar" then return end
    local event = args[1] or ""
    if sel == "" then sel, event = "Surface", "OnOpened" end    -- the form itself: its OnOpened (VB's Form_Load)
    Vml("SetSetting", "editor_control", sel)
    Vml("SetSetting", "editor_event", event)
    Vml("FormOpenModal", "script-editor.vml")
    Vml("RunScript", "SelectionChanged")
end

function EditScriptOnClick(...)
    -- double-click: straight to the control's click script, as in VB
    Vml("RunScript", "EditScript", "OnClick")
end

function ShowGeometry(...)
    -- live position and size on the status bar (runs while dragging, resizing and nudging)
    local sel = Vml("GetProperty", "Surface", "Selected")
    if sel == "menubar" then
        Vml("SetStatusText", "Menu bar    right-click for Add Menu / Remove Menu Bar")
    elseif sel:sub(1, 5) == "menu:" then
        Vml("SetStatusText", "Menu item " .. sel:sub(6) .. "    right-click for Add / Delete / Edit Script")
    elseif sel == "" then
        Vml("SetStatusText", string.format("Form    %s x %s", Vml("GetProperty", "Surface", "FormWidth"),
            Vml("GetProperty", "Surface", "FormHeight")))
    else
        Vml("SetStatusText", string.format("%s  (%s)    X %s   Y %s    W %s   H %s", sel, Vml("GetControlType", sel),
            Vml("GetControlX", sel), Vml("GetControlY", sel), Vml("GetControlWidth", sel), Vml("GetControlHeight", sel)))
    end
end

function DeleteSelected(...)
    local sel = Vml("GetProperty", "Surface", "Selected")
    if sel == "" then return end
    if sel == "menubar" then return Vml("RunScript", "MenuBarRemove") end
    if sel:sub(1, 5) == "menu:" then
        Vml("MenuDeleteItem", sel)
        Vml("SetStatusText", "Deleted " .. sel:sub(6))
        return
    end
    local all = Vml("GetProperty", "Surface", "SelectedAll")
    local gone = 0
    for name in string.gmatch(all ~= "" and all or sel, "[^,]+") do
        if Vml("ControlExists", name) == "true" then       -- (one inside a frame went with the frame)
            Vml("DeleteControl", name)
            gone = gone + 1
        end
    end
    Vml("SetProperty", "Surface", "Selected", "")
    Vml("RunScript", "SelectionChanged")
    Vml("RunScript", "DesignChanged")
    Vml("SetStatusText", gone > 1 and ("Deleted " .. gone .. " controls") or ("Deleted " .. sel))
end

function DuplicateSelected(...)
    local sel = Vml("GetProperty", "Surface", "Selected")
    if sel ~= "" then Vml("DuplicateControl", sel) end
end

function BringSelectedToFront(...)
    local sel = Vml("GetProperty", "Surface", "Selected")
    if sel ~= "" then Vml("BringToFront", sel) end
end

function SendSelectedToBack(...)
    local sel = Vml("GetProperty", "Surface", "Selected")
    if sel ~= "" then Vml("SendToBack", sel) end
end

-- ---------------------------------------------------------------- undo, redo, cut, copy, paste
function UndoDesign(...)
    if Vml("Undo") == "true" then
        Vml("SetSetting", "dirty", "true")
        Vml("RunScript", "UpdateTitle")
        Vml("SetStatusText", "Undone")
    else
        Vml("SetStatusText", "Nothing to undo")
    end
end

function RedoDesign(...)
    if Vml("Redo") == "true" then
        Vml("SetSetting", "dirty", "true")
        Vml("RunScript", "UpdateTitle")
        Vml("SetStatusText", "Redone")
    else
        Vml("SetStatusText", "Nothing to redo")
    end
end

local function selected_control()
    -- everything selected (a group), comma-separated; "" for nothing, or a menu
    local sel = Vml("GetProperty", "Surface", "Selected")
    if sel == "" or sel == "menubar" or sel:sub(1, 5) == "menu:" then return "" end
    return Vml("GetProperty", "Surface", "SelectedAll")
end

local function described(names)
    local n = select(2, names:gsub(",", "")) + 1
    return n > 1 and (n .. " controls") or names
end

function CopySelected(...)
    local sel = selected_control()
    if sel == "" then return Vml("SetStatusText", "Select a control to copy") end
    Vml("CopyControl", sel)
    Vml("SetStatusText", "Copied " .. described(sel) .. ": Ctrl+V to paste")
end

function CutSelected(...)
    local sel = selected_control()
    if sel == "" then return Vml("SetStatusText", "Select a control to cut") end
    Vml("CopyControl", sel)
    Vml("RunScript", "DeleteSelected")
    Vml("SetStatusText", "Cut " .. described(sel) .. ": Ctrl+V to paste")
end

function PasteControl(...)
    local names = Vml("PasteControl")
    Vml("SetStatusText", names ~= "" and ("Pasted " .. described(names)) or "Nothing to paste: copy a control first")
end

function PasteHere(...)
    local names = Vml("PasteControl", Vml("GetSetting", "click_x"), Vml("GetSetting", "click_y"))
    Vml("SetStatusText", names ~= "" and ("Pasted " .. described(names)) or "Nothing to paste: copy a control first")
end

function AlignGroup(...)
    local how = (...) or "tidy"
    if Vml("AlignControls", how) == "true" then
        local done = {tidy = "Tidied up", left = "Left edges lined up", centre = "Centres lined up", right = "Right edges lined up",
            top = "Tops lined up", middle = "Middles lined up", bottom = "Bottoms lined up", across = "Spaced evenly across",
            down = "Spaced evenly down", width = "Made the same width", height = "Made the same height"}
        Vml("SetStatusText", (done[how] or "Aligned") .. ": Ctrl+Z to undo")
    else
        Vml("SetStatusText", "Select two or more (draw a box round them, or Ctrl+click) to line them up")
    end
end
