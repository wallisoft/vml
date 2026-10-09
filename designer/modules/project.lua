-- The Visualised designer: the project panel and the Project menu.
-- One of the modules of designer/Designer.vmlproj. Each function here is a handler: a control or menu item of the
-- designer names it (OnClick=FileSave), or another handler runs it with Vml("RunScript", "FileSave").

function RefreshProject(...)
    -- show the open project (or hide the panel), and enable what makes sense
    local info = Vml("ProjectInfo")
    local open = info ~= ""
    Vml("SetProperty", "ProjectPane", "IsVisible", open and "true" or "false")
    Vml("SetProperty", "ProjSplit", "IsVisible", open and "true" or "false")
    for _, item in ipairs({"ProjClose", "ProjAddNew", "ProjAddForm", "ProjAddModule", "ProjAddDatabase", "ProjBrowseData", "ProjStartup", "ProjRemove", "ProjRename"}) do
        Vml("SetMenuItemEnabled", item, open and "true" or "false")
    end
    Vml("SetMenuItemText", "ViewPreview", open and "Run Project" or "Preview")
    Vml("SetMenuItemEnabled", "ViewPreviewForm", open and "true" or "false")
    if open then
        local project = require("dkjson").decode(info)
        Vml("SetProperty", "ProjTitle", "Text", "Project: " .. project.name)
        Vml("SetProperty", "ProjTree", "Items", Vml("ProjectTree"))
    end
    Vml("RunScript", "UpdateTitle")
end

function ProjectNew(...)
    local path = Vml("FileSaveDialog", "New project: choose its folder and name", "MyApp", "vmlproj")
    if path == "" then return end
    local made = Vml("ProjectNew", path)
    if made == "" then return Vml("InfoDialog", "The project couldn't be created there.", "Project") end
    -- the form on screen, if it is already saved in that folder, becomes the project's first form
    local current = Vml("GetSetting", "current_file")
    if Vml("ProjectInFolder", current) == "true" then Vml("ProjectAdd", "form", current) end
    Vml("RunScript", "RefreshProject")
    Vml("SetStatusText", "New project: " .. made .. "   Save forms into its folder to add them")
end

function ProjectOpen(...)
    if SaveFirst() ~= "true" then return end
    local path = Vml("FileOpenDialog", "Open a project", "vmlproj")
    if path == "" then return end
    Vml("RunScript", "ProjectLoad", path)
end

function ProjectLoad(...)
    local args = { ... }
    -- open a project file and show its start-up form
    if Vml("ProjectOpen", args[1]) == "" then return Vml("InfoDialog", "That project couldn't be opened.", "Project") end
    local project = require("dkjson").decode(Vml("ProjectInfo"))
    Vml("RunScript", "RefreshProject")
    if project.startup ~= "" then
        Vml("RunScript", "OpenFormFile", project.folder .. "/" .. project.startup)
    else
        Vml("RunScript", "FileNewQuiet")
    end
    RecentAdd(project.file)
    Vml("SetStatusText", "Opened project " .. project.name .. ": " .. #project.forms .. " forms, " .. #project.modules .. " modules")
end

function ProjectClose(...)
    if SaveFirst() ~= "true" then return end
    Vml("ProjectClose")
    Vml("RunScript", "RefreshProject")
    Vml("SetStatusText", "Project closed")
end

function ProjOpenItem(...)
    -- double-click in the project tree: a form opens on the surface, a module in the code editor, a database asks its address
    local item = Vml("GetProperty", "ProjTree", "SelectedItem")
    local group, name = item:match("^(%w+)/(.+)$")
    if not group then return end
    if group == "Databases" then return Vml("RunScript", "BrowseData", name) end      -- look inside it (right-click to change its address)
    local path = Vml("ProjectPath", item)
    if path == "" then return end
    if group == "Modules" then
        Vml("SetSetting", "module_file", path)
        Vml("FormOpenModal", "module-editor.vml")
        return
    end
    if path == Vml("GetSetting", "current_file") then return end
    if SaveFirst() ~= "true" then return end
    if Vml("RunScript", "OpenFormFile", path) == "true" then Vml("SetStatusText", "Opened " .. path) end
end

function ProjShowMenu(...)
    local item = Vml("GetProperty", "ProjTree", "SelectedItem")
    local group, name = item:match("^(%w+)/(.+)$")
    Vml("SetMenuItemEnabled", "PmOpen", group and "true" or "false")
    Vml("SetMenuItemEnabled", "PmStartup", group == "Forms" and "true" or "false")
    Vml("SetMenuItemEnabled", "PmRemove", group and "true" or "false")
    Vml("SetMenuItemEnabled", "PmAddress", group == "Databases" and "true" or "false")
    Vml("ShowContextMenu", "ProjMenu")
end

function ProjectAddNewForm(...)
    -- a blank form; saving it into the project's folder adds it to the project
    if SaveFirst() ~= "true" then return end
    Vml("RunScript", "FileNewQuiet")
    local project = require("dkjson").decode(Vml("ProjectInfo"))
    local n = #project.forms + 1
    Vml("SetProperty", "Surface", "FormName", "Form" .. n)
    Vml("SetProperty", "Surface", "FormTitle", "Form" .. n)
    Vml("SetStatusText", "New form: save it (Ctrl+S) to add it to " .. project.name)
end

function ProjectAddForm(...)
    local path = Vml("FileOpenDialog", "Add a form to the project", "vml")
    if path == "" then return end
    local added = Vml("ProjectAdd", "form", path)
    Vml("RunScript", "RefreshProject")
    if added ~= "" then Vml("SetStatusText", "Added " .. added) end
end

function ProjectAddModule(...)
    local name = Vml("PromptDialog", "Add a module", "A module is a Lua file of functions every form in the project can use.\n\nIts name (or the path of a .lua file you already have):", "helpers")
    if name == "" then return end
    if not name:match("%.lua$") then name = name .. ".lua" end
    local added = Vml("ProjectAdd", "module", name)
    Vml("RunScript", "RefreshProject")
    if added ~= "" then
        Vml("SetSetting", "module_file", added)
        Vml("FormOpenModal", "module-editor.vml")
    end
end

function ProjectAddDatabase(...)
    Vml("RunScript", "DatabasesShow", "+")
end

function ProjectEditDatabase(...)
    local args = { ... }
    Vml("RunScript", "DatabasesShow", args[1])
end

function ProjectSetStartup(...)
    -- the form selected in the tree, or else the one on screen
    local path = Vml("ProjectPath", Vml("GetProperty", "ProjTree", "SelectedItem"))
    if path == "" or not path:match("%.vml$") then path = Vml("GetSetting", "current_file") end
    if path == "" or Vml("ProjectSetStartup", path) ~= "true" then
        Vml("InfoDialog", "Choose a form in the project first (click it in the project tree).", "Start-up form")
        return
    end
    Vml("RunScript", "RefreshProject")
    Vml("SetStatusText", "The project now starts with " .. path:match("([^/\\]+)$"))
end

function ProjectRemove(...)
    local item = Vml("GetProperty", "ProjTree", "SelectedItem")
    local group, name = item:match("^(%w+)/(.+)$")
    if not group then return Vml("InfoDialog", "Click a form, module or database in the project tree first.", "Remove from Project") end
    name = name:gsub("  %(start%-up%)$", "")
    if Vml("ConfirmDialog", "Remove " .. name .. " from the project?\n\nThe file itself is not deleted.") ~= "true" then return end
    if group == "Databases" then Vml("ProjectDatabase", name, "") else Vml("ProjectRemove", Vml("ProjectPath", item)) end
    Vml("RunScript", "RefreshProject")
    Vml("SetStatusText", "Removed " .. name .. " from the project")
end

function ProjectRename(...)
    local project = require("dkjson").decode(Vml("ProjectInfo"))
    local name = Vml("PromptDialog", "Rename the project", "The project's name (an exported app is called this):", project.name)
    if name == "" then return end
    Vml("ProjectSetName", name)
    Vml("RunScript", "RefreshProject")
end

-- right-click a database in the project tree > Address...: the Databases screen, on that one
function ProjEditAddress(...)
    local item = Vml("GetProperty", "ProjTree", "SelectedItem")
    local group, name = item:match("^(%w+)/(.+)$")
    if group == "Databases" then Vml("RunScript", "ProjectEditDatabase", name) end
end
