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
    BuildRecentMenu()
    Vml("RunScript", "ApplySettings")
    Vml("RunScript", "ApplyLicence")
    Vml("SetMenuItemText", "HelpVersion", "Visualised " .. Vml("VmlVersion"))
    Vml("RunScript", "ApplyCSharp")
    Vml("RunScript", "RefreshProject")
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
