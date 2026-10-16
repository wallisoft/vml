-- The Visualised designer: File > Import: the importer library (see designer/importers).
-- One of the modules of designer/Designer.vmlproj. Each function here is a handler: a control or menu item of the
-- designer names it (OnClick=FileSave), or another handler runs it with Vml("RunScript", "FileSave").

-- Importers are not built in: each is a VML file in the importer library (designer/importers, and ~/.vml/importers
-- for your own). The Import menu lists whatever is there.
function BuildImportMenu(...)
    local function item(name, text, onclick)
        Vml("CreateControl", "MenuItem", name, "FileImport")
        Vml("SetProperty", name, "Text", text)
        if onclick then Vml("SetEvent", name, "OnClick", onclick) else Vml("SetProperty", name, "IsEnabled", "false") end
    end
    item("FileImportVml", "Visualised form (.vml)...", "ImportVmlCopy")       -- a copy of a form, as a new one: for everyone
    for _, imp in ipairs(require("dkjson").decode(Vml("GetImporters"))) do
        if #imp.files > 0 then item("FileImport_" .. imp.name, imp.title .. "...", "ImportFormWith(" .. imp.name .. ")") end
        if #imp.project_files > 0 then item("FileImportProject_" .. imp.name, imp.project_title .. "...", "ImportProjectWith(" .. imp.name .. ")") end
    end
    Vml("CreateControl", "MenuItem", "FileImportSep", "FileImport")
    Vml("SetProperty", "FileImportSep", "IsSeparator", "true")
    item("FileImportSoon", "Coming soon:")
    item("FileImportDelphi", "Delphi form (.dfm)...")
    item("FileImportLiveCode", "LiveCode stack (.livecode, .rev)...")
    item("FileImportPowerBuilder", "PowerBuilder window (.srw)...")
    item("FileImportQt", "Qt Designer (.ui)...")
    item("FileImportXaml", "XAML (WPF, Avalonia)...")
    item("FileImportHtml", "Web page (HTML form)...")
    Vml("CreateControl", "MenuItem", "FileImportSep2", "FileImport")
    Vml("SetProperty", "FileImportSep2", "IsSeparator", "true")
    item("FileImportAdd", "Add an importer...", "AddImporter")
end

function AddImporter(...)
    -- File > Import > Add an importer: a .vml file with an @Importer in it, copied into your own library
    local path = Vml("FileOpenDialog", "Add an importer: choose its .vml file", "vml")
    if path == "" then return end
    local why = Vml("AddImporter", path)
    if why ~= "" then
        Vml("InfoDialog", "That importer wasn't added: " .. why .. ".", "Add an importer")
        return
    end
    Vml("InfoDialog", "Added. It will be in File > Import the next time Visualised starts.\n\nYour importers are kept in the folder .vml/importers in your home folder.", "Add an importer")
end

function ImportFormWith(...)
    local args = { ... }
    -- File > Import > one form, with the importer named
    local imp
    for _, i in ipairs(require("dkjson").decode(Vml("GetImporters"))) do if i.name == args[1] then imp = i end end
    if not imp then return end
    if SaveFirst() ~= "true" then return end
    local path = Vml("FileOpenDialog", "Import: choose a " .. imp.title .. " file", table.concat(imp.files, ","))
    if path == "" then return end
    if Vml("ImportForm", imp.name, path, "Surface") == "true" then
        Vml("SetSetting", "current_file", "")
        Vml("SetSetting", "dirty", "true")
        Vml("RunScript", "ApplySettings")
        Vml("RunScript", "SelectionChanged")
        Vml("RunScript", "UpdateTitle")
        Vml("SetStatusText", "Imported " .. path .. " (the original is untouched)")
        Vml("InfoDialog", Vml("GetSetting", "import_notes") .. "\n\nThis is a new form: Save will ask for a name, and the original files are untouched.", "Imported: " .. imp.title)
    else
        local why = Vml("GetSetting", "import_notes")
        if why ~= "" then Vml("InfoDialog", "That file couldn't be imported: " .. why, "Import") end
    end
end

function ImportProjectWith(...)
    local args = { ... }
    -- File > Import > a whole project, with the importer named
    local imp
    for _, i in ipairs(require("dkjson").decode(Vml("GetImporters"))) do if i.name == args[1] then imp = i end end
    if not imp then return end
    if SaveFirst() ~= "true" then return end
    local source = Vml("FileOpenDialog", "Import: choose the " .. imp.project_title .. " file", table.concat(imp.project_files, ","))
    if source == "" then return end
    local folder = Vml("FolderDialog", "Where shall the new Visualised project go?  (The original is only read. Its own folder is fine: a new folder is made inside it.)", (source:gsub("[/\\][^/\\]*$", "")))
    if folder == "" then return end
    Vml("SetStatusText", "Importing " .. source .. "...")
    local raw = Vml("ImportProject", imp.name, source, folder)
    if raw == "" then
        local why = Vml("GetSetting", "import_notes")
        Vml("SetStatusText", "Nothing was imported")
        if why ~= "" then Vml("InfoDialog", "That project couldn't be imported: " .. why, "Import") end
        return
    end
    local result = require("dkjson").decode(raw)
    Vml("RunScript", "ProjectLoad", result.project)
    Vml("InfoDialog", result.summary, "Imported: " .. imp.project_title)
    local access = result.access or {}
    if #(access.missing or {}) > 0 and #(access.waiting or {}) == 0 then
        -- its code names Access files that are not with it: say so now, not only in the notes
        Vml("InfoDialog", "This project's code uses Access data that isn't with the project: " .. table.concat(access.missing, ", ") .. ".\n\n"
            .. "Everything else was brought across. To bring the data too, put a copy of " .. (#access.missing == 1 and "that file" or "those files")
            .. " beside the original project file and import the project again: the tables are then copied into a SQLite file that travels with the app."
            .. "\n\nOr name a database yourself in Settings > Databases (ODBC).", "Access data")
    end
    if #(access.waiting or {}) > 0 then
        -- the project has Access data and this computer can't read Access: say so now, not only in the notes
        local windows = package.config:sub(1, 1) == "\\"
        local how = windows and "Install Microsoft's free Access Database Engine (the 64-bit one), then import the project again."
            or "In a terminal:   sudo apt install unixodbc odbc-mdbtools\nThen import the project again."
        if Vml("ConfirmDialog", "This project keeps its data in Access (" .. table.concat(access.waiting, ", ") .. "), and this computer has no ODBC driver for Access, so the data was not brought across. Everything else was.\n\n"
            .. how .. " The tables are then copied into a SQLite file that travels with the app.\n\nSee which drivers this computer has now?", "Access data") == "true" then
            Vml("RunScript", "DatabasesShow")
        end
    end
end
