-- The Visualised designer: starting up, the title bar, About and updates.
-- One of the modules of designer/Designer.vmlproj. Each function here is a handler: a control or menu item of the
-- designer names it (OnClick=FileSave), or another handler runs it with Vml("RunScript", "FileSave").

function DesignerInit(...)
    local json = require("dkjson")
    -- Add: a submenu for each group of controls, as a VB toolbox has them
    local group, n = "", 0
    for _, t in ipairs(json.decode(Vml("GetControlTypes"))) do
        if t.group ~= group then
            group, n = t.group, n + 1
            if group == "Layout (advanced)" or group == "Your controls" then
                local sep = "AddSep_" .. n
                Vml("CreateControl", "MenuItem", sep, "CtxAdd")
                Vml("SetProperty", sep, "IsSeparator", "true")
            end
            Vml("CreateControl", "MenuItem", "AddGroup_" .. n, "CtxAdd")
            Vml("SetProperty", "AddGroup_" .. n, "Text", group)
        end
        local item = "Add_" .. t.name
        Vml("CreateControl", "MenuItem", item, "AddGroup_" .. n)
        Vml("SetProperty", item, "Text", t.name)
        Vml("SetEvent", item, "OnClick", "AddControl(" .. t.name .. ")")
    end
    Vml("SetSetting", "current_file", "")
    Vml("SetSetting", "dirty", "false")
    Vml("SetProperty", "Props", "Target", "Surface")
    Vml("RunScript", "BuildImportMenu")
    BuildToolsMenu()
    BuildRecentMenu()
    Vml("RunScript", "ApplySettings")
    Vml("RunScript", "ApplyLicence")
    Vml("SetMenuItemText", "HelpVersion", "Visualised " .. Vml("VmlVersion"))
    Vml("RunScript", "ApplyCSharp")
    Vml("RunScript", "RefreshProject")
    Vml("UndoReset")                                  -- the form as it opens: what Undo comes back to
    Vml("SetStatusText", "Right-click the form to add a control")
end

function UpdateTitle(...)
    local file = Vml("GetSetting", "current_file")
    local name = file ~= "" and file:match("([^/\\]+)$") or "Untitled"
    local star = Vml("GetSetting", "dirty") == "true" and " *" or ""
    local info = Vml("ProjectInfo")
    local project = info ~= "" and (require("dkjson").decode(info).name .. " - ") or ""
    Vml("SetProperty", "Designer", "Title", "Visualised - " .. project .. name .. star)
end

function About(...)
    local lic = require("dkjson").decode(Vml("GetLicence"))
    Vml("InfoDialog", "Visualised™ " .. Vml("VmlVersion") .. " (" .. lic.label .. ")\n\nDesign apps for the desktop, the web and Android.\nThe designer is itself a Visualised project: designer/Designer.vmlproj.\n\nhttps://visualised.io\nMade by Steve Wallis and Claude, at Wallisoft.\nVisualised is a trade mark of Steve Wallis, trading as Wallisoft.", "About Visualised")
end

function CheckUpdates(...)
    Vml("SetStatusText", "Checking for a newer Visualised...")
    local u = require("dkjson").decode(Vml("CheckForUpdate"))
    if u.store then
        Vml("SetStatusText", "Visualised " .. u.current)
        Vml("InfoDialog", "You have Visualised " .. u.current .. ".\n\nThis copy came from the Microsoft Store, which keeps it up to date for you.", "Updates")
    elseif u.error ~= "" or u.latest == "" then
        Vml("SetStatusText", "Couldn't check for updates")
        Vml("InfoDialog", "Couldn't check for updates just now. You have Visualised " .. u.current .. ".", "Updates")
    elseif u.newer then
        Vml("SetStatusText", "Visualised " .. u.latest .. " is available")
        if Vml("ConfirmDialog", "Visualised " .. u.latest .. " is available (you have " .. u.current .. ").\n\nOpen the download page?", "Updates") == "true" then
            Vml("OpenUrl", u.url)
        end
    else
        Vml("SetStatusText", "Visualised " .. u.current .. " is the latest")
        Vml("InfoDialog", "You have the latest Visualised (" .. u.current .. ").", "Updates")
    end
end


-- Tools: Add a control (stacked down the left) and the debugger; then every app in the tools folder (~/.vml/tools), each started as an app of its own; then the Markdown viewer
-- and a way to the folder. Put a form, a project, or a link to an app's folder in there and it's on the menu.
TOOLS = {}
function BuildToolsMenu()
    TOOLS = require("dkjson").decode(Vml("ToolsList")) or {}
    -- Add a control: the same groups as the right-click Add menu; each one goes under the last
    Vml("CreateControl", "MenuItem", "ToolsAdd", "Tools")
    Vml("SetProperty", "ToolsAdd", "Text", "Add a control")
    local group, n = "", 0
    for _, t in ipairs(require("dkjson").decode(Vml("GetControlTypes"))) do
        if t.group ~= group then
            group, n = t.group, n + 1
            if group == "Layout (advanced)" or group == "Your controls" then
                Vml("CreateControl", "MenuItem", "ToolsAddSep_" .. n, "ToolsAdd")
                Vml("SetProperty", "ToolsAddSep_" .. n, "IsSeparator", "true")
            end
            Vml("CreateControl", "MenuItem", "ToolsGroup_" .. n, "ToolsAdd")
            Vml("SetProperty", "ToolsGroup_" .. n, "Text", group)
        end
        local item = "ToolsAdd_" .. t.name
        Vml("CreateControl", "MenuItem", item, "ToolsGroup_" .. n)
        Vml("SetProperty", item, "Text", t.name)
        Vml("SetEvent", item, "OnClick", "ToolsAddControl(" .. t.name .. ")")
    end
    Vml("CreateControl", "MenuItem", "ToolsAddSepMenu", "ToolsAdd")
    Vml("SetProperty", "ToolsAddSepMenu", "IsSeparator", "true")
    Vml("CreateControl", "MenuItem", "ToolsAddMenu", "ToolsAdd")
    Vml("SetProperty", "ToolsAddMenu", "Text", "Menu")
    Vml("SetEvent", "ToolsAddMenu", "OnClick", "ToolsAddMenu")
    Vml("CreateControl", "MenuItem", "ToolsMenuEditor", "Tools")
    Vml("SetProperty", "ToolsMenuEditor", "Text", "Menu Editor...")
    Vml("SetEvent", "ToolsMenuEditor", "OnClick", "OpenMenuEditor")
    Vml("CreateControl", "MenuItem", "ToolsScriptEditor", "Tools")
    Vml("SetProperty", "ToolsScriptEditor", "Text", "Script Editor...")
    Vml("SetEvent", "ToolsScriptEditor", "OnClick", "ToolsScriptEditor")
    Vml("CreateControl", "MenuItem", "ToolsDebugger", "Tools")
    Vml("SetProperty", "ToolsDebugger", "Text", "Debugger (F12)")
    Vml("SetEvent", "ToolsDebugger", "OnClick", "ToolsDebugger")
    Vml("CreateControl", "MenuItem", "ToolsAttach", "Tools")
    Vml("SetProperty", "ToolsAttach", "Text", "Attach the debugger to a running app...")
    Vml("SetEvent", "ToolsAttach", "OnClick", "ToolsAttach")
    Vml("CreateControl", "MenuItem", "ToolsSep0", "Tools")
    Vml("SetProperty", "ToolsSep0", "IsSeparator", "true")
    for i, t in ipairs(TOOLS) do
        local item = "Tool_" .. i
        Vml("CreateControl", "MenuItem", item, "Tools")
        Vml("SetProperty", item, "Text", t.name)
        Vml("SetProperty", item, "ToolTip", t.path)
        Vml("SetEvent", item, "OnClick", "OpenTool(" .. i .. ")")
    end
    if #TOOLS == 0 then
        Vml("CreateControl", "MenuItem", "ToolsNone", "Tools")
        Vml("SetProperty", "ToolsNone", "Text", "No tools yet: put an app in the tools folder")
        Vml("SetProperty", "ToolsNone", "IsEnabled", "false")
    end
    Vml("CreateControl", "MenuItem", "ToolsSep", "Tools")
    Vml("SetProperty", "ToolsSep", "IsSeparator", "true")
    Vml("CreateControl", "MenuItem", "ToolsMarkdown", "Tools")
    Vml("SetProperty", "ToolsMarkdown", "Text", "Markdown viewer...")
    Vml("SetEvent", "ToolsMarkdown", "OnClick", "ToolsMarkdown")
    Vml("CreateControl", "MenuItem", "ToolsFolder", "Tools")
    Vml("SetProperty", "ToolsFolder", "Text", "Open the tools folder")
    Vml("SetEvent", "ToolsFolder", "OnClick", "ToolsFolder")
end

function OpenTool(...)
    local t = TOOLS[tonumber((...)) or 0]
    if not t then return end
    -- what's open here goes with it (VML_PROJECT): Bob opens on it, say
    local info, current = Vml("ProjectInfo"), Vml("GetSetting", "current_file")
    if info ~= "" then current = (require("dkjson").decode(info) or {}).file or current end
    if Vml("RunApp", t.path, current or "") == "true" then
        Vml("SetStatusText", "Started " .. t.name)
    else
        Vml("InfoDialog", "Couldn't start " .. t.name .. ":\n" .. t.path, "Tools")
    end
end

function ToolsMarkdown(...)
    local path = Vml("FileOpenDialog", "Open a Markdown file", "md")
    if path and path ~= "" then Vml("ShowMarkdown", path) end
end

function ToolsFolder(...)
    Vml("OpenFolder", Vml("ToolsFolder"))
    Vml("SetStatusText", "Tools are read when Visualised starts: restart it to see new ones on the menu")
end

function ToolsAddControl(...)
    local name = Vml("AddStackedControl", (...))
    if name ~= "" then Vml("SetStatusText", "Added " .. name .. ": drag it where it belongs (or right-click the form to add one there)") end
end

function ToolsDebugger(...)
    Vml("ShowDebugger")
end

function ToolsAttach(...)
    -- any Visualised app running on this computer: Bob, Mountie, one you've started: its calls and variables, live
    Vml("AttachDebugger")
end

function ToolsAddMenu(...)
    -- a menu bar for the form; it has one already: the Menu Editor, to add to it
    if Vml("GetDesignMenu", "Surface") == "[]" then
        Vml("RunScript", "AddMenu")
        Vml("SetStatusText", "Added a menu: right-click it to add more, or use Tools > Menu Editor")
    else
        Vml("RunScript", "OpenMenuEditor")
    end
end

function ToolsScriptEditor(...)
    -- the form's own scripts: OnOpened first (VB's Form_Load), then OnClosing, OnResized, OnActivated, the keys
    Vml("SetSetting", "editor_control", "Surface")
    Vml("SetSetting", "editor_event", "OnOpened")
    Vml("FormOpenModal", "script-editor.vml")
    Vml("RunScript", "SelectionChanged")
end
