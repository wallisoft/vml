-- The Visualised designer: File: new, open, save, preview (F5, F6) and export.
-- One of the modules of designer/Designer.vmlproj. Each function here is a handler: a control or menu item of the
-- designer names it (OnClick=FileSave), or another handler runs it with Vml("RunScript", "FileSave").

-- Before the form on screen is replaced or closed: if it has changes, offer to save them.
-- Returns "true" when it is all right to go on (saved, or not wanted), "false" if the user thought better of it.
function SaveFirst()
    if Vml("GetSetting", "dirty") ~= "true" then return "true" end
    local file = Vml("GetSetting", "current_file")
    local name = file ~= "" and (file:match("([^/\\]+)$") or file) or Vml("GetProperty", "Surface", "FormName")
    local answer = Vml("ChoiceDialog", "Save the changes to " .. name .. "?", "Unsaved changes", "Save|Don't Save|Cancel")
    if answer == "Save" then
        Vml("RunScript", "FileSave")
        return Vml("GetSetting", "dirty") == "true" and "false" or "true"      -- still changed: the save was cancelled
    end
    return answer == "Don't Save" and "true" or "false"
end

-- The files and projects opened lately, newest first (kept between sessions): File > Open Recent.
local RECENT_MAX = 8
function RecentList()
    local list = require("dkjson").decode(Vml("GetPreference", "recent_files", "[]")) or {}
    return type(list) == "table" and list or {}
end

function RecentAdd(...)
    local args = { ... }
    local path = (args[1] or ""):gsub("\\", "/")
    if path == "" then return end
    local list = { path }
    for _, p in ipairs(RecentList()) do
        if p ~= path and #list < RECENT_MAX then list[#list + 1] = p end
    end
    Vml("SetPreference", "recent_files", require("dkjson").encode(list))
    BuildRecentMenu()
end

function BuildRecentMenu()
    local list = RecentList()
    for i = 1, RECENT_MAX do
        local item, path = "FileRecent" .. i, list[i]
        Vml("SetProperty", item, "IsVisible", path and "true" or "false")
        if path then
            local name, folder = path:match("([^/]+)$") or path, path:match("^(.*)/[^/]+$") or ""
            Vml("SetMenuItemText", item, i .. "  " .. name .. (folder ~= "" and ("     " .. folder) or ""))
        end
    end
    Vml("SetProperty", "FileRecentNone", "IsVisible", #list == 0 and "true" or "false")
    Vml("SetMenuItemEnabled", "FileRecentClear", #list > 0 and "true" or "false")
end

function RecentOpen(...)
    local args = { ... }
    local path = RecentList()[tonumber(args[1]) or 0]
    if not path then return end
    if Vml("FileExists", path) ~= "true" then
        local kept = {}
        for _, p in ipairs(RecentList()) do if p ~= path then kept[#kept + 1] = p end end
        Vml("SetPreference", "recent_files", require("dkjson").encode(kept))
        BuildRecentMenu()
        return Vml("InfoDialog", "That file isn't there any more, so it has been taken off the list:\n" .. path, "Open Recent")
    end
    if SaveFirst() ~= "true" then return end
    if path:lower():match("%.vmlproj$") then
        Vml("RunScript", "ProjectLoad", path)
    else
        if Vml("ProjectInfo") ~= "" and Vml("ProjectInFolder", path) ~= "true" then Vml("RunScript", "ProjectClose") end
        if Vml("RunScript", "OpenFormFile", path) == "true" then
            Vml("SetStatusText", "Opened " .. path)
            RecentAdd(path)
        end
    end
end

function RecentClear()
    Vml("SetPreference", "recent_files", "[]")
    BuildRecentMenu()
end

-- File > Exit, and the window's own close button: not without a word about unsaved changes.
function DesignerExit()
    if SaveFirst() ~= "true" then return end
    Vml("SetSetting", "dirty", "false")
    Vml("AppExit")
end

function DesignerClosing()
    if Vml("GetSetting", "closing_by_user") ~= "true" then return end      -- closed by the program (Exit has already asked)
    if SaveFirst() ~= "true" then return Vml("CancelClose") end
    Vml("SetSetting", "dirty", "false")
end

-- File > Import > Visualised form: a copy of somebody else's .vml as a new, unsaved form (the original is untouched)
function ImportVmlCopy()
    if SaveFirst() ~= "true" then return end
    local path = Vml("FileOpenDialog", "Import: choose a Visualised form", "vml")
    if path == "" then return end
    if Vml("ImportVml", path, "Surface") ~= "true" then return Vml("InfoDialog", "That file couldn't be opened as a form.", "Import") end
    Vml("SetSetting", "current_file", "")
    Vml("SetSetting", "dirty", "true")
    Vml("RunScript", "ApplySettings")
    Vml("RunScript", "SelectionChanged")
    Vml("RunScript", "UpdateTitle")
    Vml("SetStatusText", "Imported a copy of " .. path .. ": Save will ask for a name, and the original is untouched")
end

function FileNew(...)
    if SaveFirst() ~= "true" then return end
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
    if SaveFirst() ~= "true" then return end
    local path = Vml("FileOpenDialog", "Open a VML form", "vml")
    if path == "" then return end
    if Vml("ImportVml", path, "Surface") == "true" then
        RecentAdd(path)
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
    if Vml("ProjectInfo") == "" then RecentAdd(path) end        -- (a project's forms are reached through the project)
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

-- View > Preview on Phone: the form as a web page, where a phone on the same Wi-Fi can open it
function PreviewPhone()
    local url = Vml("PreviewOnPhone", "Surface")
    if url == "" then
        return Vml("InfoDialog", "This computer doesn't seem to be on a network, so a phone can't reach it.\n\nConnect both to the same Wi-Fi and try again.", "Preview on Phone")
    end
    Vml("ClipboardSet", url)
    Vml("SetStatusText", "On your phone, open " .. url)
    Vml("InfoDialog", "Point your phone's camera at the square, or type this address into the Visualised app or the phone's browser:\n\n" .. url
        .. "\n\nThe phone has to be on the same Wi-Fi as this computer. After a change, choose Preview on Phone again and refresh on the phone."
        .. "\n\nA form wider than the phone's screen is scaled to fit. For an app that feels at home on a phone, draw it phone-sized: File > New Phone Form."
        .. "\n\nAnyone on your network who has the address can open the page, for as long as Visualised is open.", "Preview on Phone", Vml("QrCode", url, 5))
    PhoneSizeOffer()
end

-- The phone has said how much room it really has (its own bars taken off). A phone-shaped form that is a
-- different size is offered the phone's size, once for each pairing of form size and phone size.
function PhoneSizeOffer()
    local size = Vml("PhoneSize")
    local pw, ph = size:match("^(%d+)x(%d+)$")
    if not pw then return end
    local fw, fh = Vml("GetProperty", "Surface", "FormWidth"), Vml("GetProperty", "Surface", "FormHeight")
    if (tonumber(fw) or 9999) > 600 or (tonumber(fw) == tonumber(pw) and tonumber(fh) == tonumber(ph)) then return end
    fw, fh = tostring(math.floor(tonumber(fw))), tostring(math.floor(tonumber(fh) or 0))
    local pairing = fw .. "x" .. fh .. ">" .. size
    if Vml("GetSetting", "phone_size_asked") == pairing then return end
    Vml("SetSetting", "phone_size_asked", pairing)
    local answer = Vml("ChoiceDialog", "Your phone has room for " .. pw .. " x " .. ph .. " once its own bars are taken off.\nThis form is " .. fw .. " x " .. fh
        .. ".\n\nMake the form the phone's size?", "Preview on Phone", "Resize|Leave")
    if answer ~= "Resize" then return end
    Vml("SetProperty", "Surface", "FormWidth", pw)
    Vml("SetProperty", "Surface", "FormHeight", ph)
    Vml("PreviewOnPhone", "Surface")
    Vml("SetStatusText", "The form is now " .. pw .. " x " .. ph .. ". Refresh on the phone.")
end

-- File > New Phone Form: a blank form the size of a phone held upright: the phone that last opened Preview on
-- Phone, or one that leaves room for a browser's address bar
function FileNewPhone()
    if SaveFirst() ~= "true" then return end
    local w, h = Vml("PhoneSize"):match("^(%d+)x(%d+)$")
    local known = w ~= nil
    w, h = w or "360", h or "640"
    Vml("RunScript", "FileNewQuiet")
    Vml("SetProperty", "Surface", "FormWidth", w)
    Vml("SetProperty", "Surface", "FormHeight", h)
    Vml("RunScript", "UpdateTitle")
    Vml("SetStatusText", (known and "A form the size of your phone's screen" or "A phone-sized form") .. " (" .. w .. " x " .. h .. "). Anchor what should stretch, then View > Preview on Phone.")
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

-- File > Export > Android app: the form as an .apk anyone with an Android phone can install
function ExportAndroid(...)
    local name = Vml("GetProperty", "Surface", "FormName")
    local path = Vml("FileSaveDialog", "Export as an Android app", name, "apk")
    if path == "" then return end
    Vml("SetStatusText", "Making the Android app...")
    local out = Vml("ExportApk", "Surface", path)
    if out == "" then return Vml("SetStatusText", "") end
    local made = require("dkjson").decode(out)
    Vml("SetStatusText", "Android app written: " .. made.path)
    local uses = {}
    for _, p in ipairs(made.permissions) do
        if p ~= "INTERNET" and p ~= "ACCESS_NETWORK_STATE" then uses[#uses + 1] = p:lower():gsub("_", " ") end
    end
    local text = "Exported " .. name .. " for Android:\n" .. made.path .. "\n\nVersion " .. made.version .. ", "
        .. math.floor(made.size / 1024 + 0.5) .. " KB. It will ask the phone for: "
        .. (#uses > 0 and table.concat(uses, ", ") or "nothing beyond the internet") .. "."
        .. "\n\nSend the file to an Android phone and open it there. The phone will ask to allow the install, because it "
        .. "hasn't come from a store. For Google Play a different kind of file is needed, which Visualised doesn't make yet."
    Vml("InfoDialog", text, "Export")
    if made.new_key then
        Vml("InfoDialog", "IMPORTANT: keep a copy of your signing key.\n\nYour Android apps are signed with a key that was made just now "
            .. "and is kept on this computer:\n\n" .. made.key .. "\n" .. made.key:gsub("%.pem$", ".cert")
            .. "\n\nAndroid will only accept an update to an app if it is signed with the same key. If these two files are lost, "
            .. "nobody can ever update the apps you have given out: people would have to remove them and install afresh."
            .. "\n\nCopy both files somewhere safe now, and keep them private: whoever has them can sign apps as you.", "Your signing key")
    end
end

function ExportLinux(...)
    local name = Vml("GetProperty", "Surface", "FormName")
    local path = Vml("FileSaveDialog", "Export as a Linux app", name .. "-linux", "tar.gz")
    if path == "" then return end
    local out = Vml("ExportApp", "linux", path)
    if out ~= "" then Vml("InfoDialog", "Exported " .. name .. " for Linux:\n" .. out .. "\n\nUnpack it anywhere and run ./" .. name .. ".", "Export") end
end
