-- The Visualised designer: File: new, open, save, preview (F5, F6) and export.
-- One of the modules of designer/Designer.vmlproj. Each function here is a handler: a control or menu item of the
-- designer names it (OnClick=FileSave), or another handler runs it with Vml("RunScript", "FileSave").

function FileNew(...)
    if Vml("GetSetting", "dirty") == "true" and Vml("ConfirmDialog", "Discard the current form?") ~= "true" then return end
    Vml("ClearDesign", "Surface")
    Vml("SetSetting", "current_file", "")
    Vml("SetSetting", "dirty", "false")
    Vml("RunScript", "ApplySettings")
    Vml("RunScript", "SelectionChanged")
    Vml("RunScript", "UpdateTitle")
end

function FileNewQuiet(...)
    Vml("ClearDesign", "Surface")
    Vml("SetSetting", "current_file", "")
    Vml("SetSetting", "dirty", "false")
    Vml("RunScript", "ApplySettings")
    Vml("RunScript", "SelectionChanged")
    Vml("RunScript", "UpdateTitle")
end

function FileOpen(...)
    local path = Vml("FileOpenDialog", "Open a VML form", "vml")
    if path == "" then return end
    if Vml("ImportVml", path, "Surface") == "true" then
        local converted = Vml("GetSetting", "import_converted") == "true"
        -- a converted layout form is a new, unsaved canvas form: Save asks for a name, so the original is never overwritten
        Vml("SetSetting", "current_file", converted and "" or path)
        Vml("SetSetting", "dirty", converted and "true" or "false")
        Vml("RunScript", "ApplySettings")
        Vml("RunScript", "SelectionChanged")
        Vml("RunScript", "UpdateTitle")
        if converted then
            Vml("SetStatusText", "Converted " .. path .. " to a canvas form (the original is untouched)")
            Vml("InfoDialog", Vml("GetSetting", "import_notes") .. "\n\nThis is a new canvas form: Save will ask for a name, and the original file is untouched.")
        else
            Vml("SetStatusText", "Opened " .. path)
        end
    else
        Vml("InfoDialog", "That file couldn't be opened as a form.")
    end
end

function OpenFormFile(...)
    local args = { ... }
    -- put a saved form on the design surface (no questions asked: callers check for unsaved changes first)
    local path = args[1]
    if Vml("ImportVml", path, "Surface") ~= "true" then
        Vml("InfoDialog", "That form couldn't be opened:\n" .. path, "Open")
        return "false"
    end
    local converted = Vml("GetSetting", "import_converted") == "true"
    Vml("SetSetting", "current_file", converted and "" or path)
    Vml("SetSetting", "dirty", converted and "true" or "false")
    Vml("RunScript", "ApplySettings")
    Vml("RunScript", "SelectionChanged")
    Vml("RunScript", "UpdateTitle")
    return "true"
end

function FileSave(...)
    local path = Vml("GetSetting", "current_file")
    if path == "" then return Vml("RunScript", "FileSaveAs") end
    Vml("ExportVml", "Surface", path)
    Vml("SetSetting", "dirty", "false")
    if Vml("ProjectInFolder", path) == "true" then
        -- a form saved into the project's folder is part of the project, as in VB
        Vml("ProjectAdd", "form", path)
        Vml("RunScript", "RefreshProject")
    end
    Vml("RunScript", "UpdateTitle")
    Vml("SetStatusText", "Saved " .. path)
end

function FileSaveAs(...)
    local name = Vml("GetProperty", "Surface", "FormName")
    local info = Vml("ProjectInfo")
    if info ~= "" then name = require("dkjson").decode(info).folder .. "/" .. name end     -- start in the project's folder
    local path = Vml("FileSaveDialog", "Save the form as", name, "vml")
    if path == "" then return end
    Vml("SetSetting", "current_file", path)
    Vml("RunScript", "FileSave")
end

function Preview(...)
    -- F5: with a project open, run the whole app from its start-up form; otherwise, the form on screen
    local info = Vml("ProjectInfo")
    if info == "" then return Vml("RunScript", "PreviewForm") end
    local project = require("dkjson").decode(info)
    if project.startup == "" then
        Vml("InfoDialog", "This project has no forms yet.\n\nSave this form into the project's folder (or Project, Add Existing Form), then press F5.", "Run")
        return
    end
    if Vml("RunProject", "Surface") ~= "" then
        Vml("SetStatusText", "Running " .. project.name .. " from " .. project.startup .. "   (Shift+F5 previews only this form)")
    end
end

function PreviewForm(...)
    Vml("PreviewDesign", "Surface")
    Vml("SetStatusText", "Previewing " .. Vml("GetProperty", "Surface", "FormName"))
end

function PreviewBrowser(...)
    -- the same form, as a web page, in your browser
    local path = Vml("PreviewInBrowser", "Surface")
    Vml("SetStatusText", "Opened in your browser: " .. path)
end

function ExportHtml(...)
    local path = Vml("FileSaveDialog", "Export as a web page", Vml("GetProperty", "Surface", "FormName"), "html")
    if path == "" then return end
    Vml("ExportHtml", "Surface", path)
    Vml("SetStatusText", "Web page written: " .. path)
end

function ExportWindows(...)
    local name = Vml("GetProperty", "Surface", "FormName")
    local path = Vml("FileSaveDialog", "Export as a Windows app", name .. "-windows", "zip")
    if path == "" then return end
    local out = Vml("ExportApp", "windows", path)
    if out ~= "" then Vml("InfoDialog", "Exported " .. name .. " for Windows:\n" .. out .. "\n\nUnzip it anywhere and double-click " .. name .. ".exe.", "Export") end
end

function ExportLinux(...)
    local name = Vml("GetProperty", "Surface", "FormName")
    local path = Vml("FileSaveDialog", "Export as a Linux app", name .. "-linux", "tar.gz")
    if path == "" then return end
    local out = Vml("ExportApp", "linux", path)
    if out ~= "" then Vml("InfoDialog", "Exported " .. name .. " for Linux:\n" .. out .. "\n\nUnpack it anywhere and run ./" .. name .. ".", "Export") end
end
