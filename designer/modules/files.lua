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

-- File > Export > Android app: the form as an .apk anyone with an Android phone can install.
-- An Android app is signed with its maker's key, and can only ever be updated with that same key, so the key is
-- looked after here: explained before it is first made, offered as a copy to keep, and checked against the key
-- the form was last exported with.
local function AndroidKeyOf()
    return require("dkjson").decode(Vml("AndroidKey"))
end

-- Save a copy of the key where the user chooses. true if one was written.
function AndroidKeyCopy(...)
    local path = Vml("FileSaveDialog", "Save a copy of your signing key", "visualised-android-key", "pem")
    if path == "" then return false end
    local problem = Vml("AndroidKeySave", path)
    if problem ~= "" then
        Vml("InfoDialog", problem, "Android signing key")
        return false
    end
    Vml("InfoDialog", "A copy of your signing key is in:\n" .. path .. "\n\nPut it somewhere that isn't this computer (a memory stick, "
        .. "a password manager) and keep it private: whoever has it can sign apps as you.", "Android signing key")
    return true
end

-- Put the key back from a copy. true if it is now the key on this computer.
function AndroidKeyBack(...)
    local path = Vml("FileOpenDialog", "Restore your signing key from its copy", "pem")
    if path == "" then return false end
    local problem = Vml("AndroidKeyRestore", path)
    if problem:find("already a different", 1, true) then
        if Vml("ChoiceDialog", problem .. "\n\nThe key that is here now would be kept beside the restored one, renamed, not thrown away.",
               "Android signing key", "Cancel|Replace it") ~= "Replace it" then return false end
        problem = Vml("AndroidKeyRestore", path, "true")
    end
    if problem ~= "" then
        Vml("InfoDialog", problem, "Android signing key")
        return false
    end
    Vml("SetStatusText", "Signing key restored: " .. AndroidKeyOf().id)
    return true
end

-- Settings > Android Signing Key
function AndroidKeyShow(...)
    local key = AndroidKeyOf()
    if key.problem ~= "" then
        if Vml("ChoiceDialog", key.problem, "Android signing key", "Restore from a copy...|Close") == "Restore from a copy..." then AndroidKeyBack() end
        return
    end
    if not key.exists then
        local said = Vml("ChoiceDialog", "There is no signing key on this computer yet.\n\nAndroid apps are signed with their maker's key, and an "
            .. "app can only be updated with the key it was first signed with. Yours is made the first time you export an Android app "
            .. "(File, Export, Android app).\n\nIf you have exported apps from another computer, restore that key here first.",
            "Android signing key", "Close|Restore from a copy...")
        if said == "Restore from a copy..." then AndroidKeyBack() end
        return
    end
    local said = Vml("ChoiceDialog", "Your Android apps are signed with key " .. key.id .. ", made on " .. key.made .. ".\n\n" .. key.path
        .. "\n\n" .. (key.saved ~= "" and ("A copy was saved on " .. key.saved .. ".")
            or "NO COPY HAS BEEN SAVED. If this computer is lost, nobody can update the apps you have given out.")
        .. "\n\nAn app can only be updated with the key it was first signed with.",
        "Android signing key", key.saved ~= "" and "Close|Save a copy...|Restore from a copy..." or "Save a copy...|Restore from a copy...|Close")
    if said == "Save a copy..." then AndroidKeyCopy() elseif said == "Restore from a copy..." then AndroidKeyBack() end
end

function ExportAndroid(...)
    if Vml("LicenceAllows", "export") ~= "true" then return Vml("ExportApk", "Surface", "") end      -- (it says why not)
    local name = Vml("GetProperty", "Surface", "FormName")
    local key, was = AndroidKeyOf(), Vml("GetProperty", "Surface", "FormAndroidKey")
    if key.problem ~= "" then
        if Vml("ChoiceDialog", key.problem, "Export", "Restore from a copy...|Cancel") ~= "Restore from a copy..." or not AndroidKeyBack() then return end
        key = AndroidKeyOf()
    end
    if was ~= "" and key.id ~= was then
        -- exported before, with a key that isn't the one here: an update signed with another key is refused by every phone that has the app
        local said = Vml("ChoiceDialog", name .. " was last exported with signing key " .. was .. ", and "
            .. (key.exists and ("the key on this computer is a different one (" .. key.id .. ").") or "there is no signing key on this computer.")
            .. "\n\nPhones that already have " .. name .. " would refuse an export from here as an update."
            .. "\n\nRestore your key from its copy to carry on with the same app. Or export it as a new app: it installs beside the old one, "
            .. "and people start afresh.", "Export", "Restore my key...|Export as a new app|Cancel")
        if said == "Restore my key..." then
            if not AndroidKeyBack() then return end
            if AndroidKeyOf().id ~= was then
                return Vml("InfoDialog", "That is not the key " .. name .. " was exported with (" .. was .. "). Nothing was exported.", "Export")
            end
        elseif said == "Export as a new app" then
            Vml("SetProperty", "Surface", "FormAndroidPackage", "")
            Vml("SetProperty", "Surface", "FormAndroidKey", "")
        else
            return
        end
        key = AndroidKeyOf()
    end
    if not key.exists then
        local said = Vml("ChoiceDialog", "Before your first Android app: its signing key.\n\nEvery Android app is signed by its maker, and a phone "
            .. "will only take an update to an app if it is signed with the same key. Visualised will make your key now and keep it on this "
            .. "computer. You will be offered a copy to keep safe: without one, losing this computer means never being able to update your apps."
            .. "\n\nIf you have already exported apps on another computer, restore that key instead.",
            "Export", "Make my key and export|Restore a key I have...|Cancel")
        if said == "Restore a key I have..." then
            if not AndroidKeyBack() then return end
        elseif said ~= "Make my key and export" then
            return
        end
    end
    local path = Vml("FileSaveDialog", "Export as an Android app", name, "apk")
    if path == "" then return end
    Vml("SetStatusText", "Making the Android app...")
    local out = Vml("ExportApk", "Surface", path)
    if out == "" then return Vml("SetStatusText", "") end
    local made = require("dkjson").decode(out)
    if made.other_key then
        Vml("SetStatusText", "")
        return Vml("InfoDialog", made.message, "Export")
    end
    if made.remembered then Vml("SetSetting", "dirty", "true"); Vml("RunScript", "UpdateTitle") end
    Vml("SetStatusText", "Android app written: " .. made.path)
    local uses = {}
    for _, p in ipairs(made.permissions) do
        if p ~= "INTERNET" and p ~= "ACCESS_NETWORK_STATE" then uses[#uses + 1] = (p:lower():gsub("_", " ")) end
    end
    local text = "Exported " .. name .. " for Android:\n" .. made.path .. "\n\nVersion " .. made.version .. ", "
        .. math.floor(made.size / 1024 + 0.5) .. " KB. It will ask the phone for: "
        .. (#uses > 0 and table.concat(uses, ", ") or "nothing beyond the internet") .. "."
        .. "\n\nSend the file to an Android phone and open it there. The phone will ask to allow the install, because it "
        .. "hasn't come from a store. For Google Play a different kind of file is needed, which Visualised doesn't make yet."
        .. (made.remembered and ("\n\nSave the form: it now remembers the app it has become (" .. made.package .. "), so the next export is an update to it.") or "")
    if AndroidKeyOf().saved ~= "" then
        return Vml("InfoDialog", text, "Export")
    end
    if Vml("ChoiceDialog", text .. "\n\nYOUR SIGNING KEY HAS NO COPY YET. It exists only on this computer, and " .. name
           .. " can only ever be updated with it.", "Export", "Save a copy of my key...|Later") == "Save a copy of my key..." then
        AndroidKeyCopy()
    end
end

function ExportLinux(...)
    local name = Vml("GetProperty", "Surface", "FormName")
    local path = Vml("FileSaveDialog", "Export as a Linux app", name .. "-linux", "tar.gz")
    if path == "" then return end
    local out = Vml("ExportApp", "linux", path)
    if out ~= "" then Vml("InfoDialog", "Exported " .. name .. " for Linux:\n" .. out .. "\n\nUnpack it anywhere and run ./" .. name .. ".", "Export") end
end
