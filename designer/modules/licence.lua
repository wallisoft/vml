-- The Visualised designer: the licence: Community and Pro.
-- One of the modules of designer/Designer.vmlproj. Each function here is a handler: a control or menu item of the
-- designer names it (OnClick=FileSave), or another handler runs it with Vml("RunScript", "FileSave").

-- Community designs, runs, saves and shares forms, and exports one as a web page. Pro and Enterprise add exporting
-- one as an app of its own (Windows, Linux, Android), and the imports as they arrive.
function ApplyLicence(...)
    local raw = Vml("GetLicence")
    if raw == "" then return end
    local lic = require("dkjson").decode(raw)
    local paid = lic.tier ~= "community"
    -- (a web page is free: it is the app turned into a program of its own that is Pro)
    local exports = {FileExportWin = "Windows app...", FileExportLinux = "Linux app...", FileExportAndroid = "Android app..."}
    for item, text in pairs(exports) do
        Vml("SetMenuItemEnabled", item, paid and "true" or "false")
        Vml("SetMenuItemText", item, text .. (paid and "" or "   (Pro)"))
    end
    for _, imp in ipairs(require("dkjson").decode(Vml("GetImporters"))) do
        for item, title in pairs({["FileImport_" .. imp.name] = imp.title, ["FileImportProject_" .. imp.name] = imp.project_title}) do
            if Vml("ControlExists", item) == "true" then
                Vml("SetMenuItemEnabled", item, paid and "true" or "false")
                Vml("SetMenuItemText", item, title .. "..." .. (paid and "" or "   (Pro)"))
            end
        end
    end
    Vml("SetMenuItemText", "SetLicenceInfo", "Licence: " .. lic.label)
    Vml("SetMenuItemText", "SetLicenceEnter", lic.key ~= "" and "Change Licence Key..." or "Enter Licence Key...")
    Vml("SetMenuItemEnabled", "SetLicenceRemove", lic.key ~= "" and "true" or "false")
    local upgrade = {community = "Upgrade to Pro...", pro = "Upgrade to Enterprise...", enterprise = "Upgrade Licence..."}
    Vml("SetMenuItemText", "SetLicenceUpgrade", upgrade[lic.tier])
    Vml("SetMenuItemEnabled", "SetLicenceUpgrade", lic.tier ~= "enterprise" and "true" or "false")
end

function LicenceShow(...)
    local lic = require("dkjson").decode(Vml("GetLicence"))
    local function day(d) return #d == 8 and (d:sub(7, 8) .. "/" .. d:sub(5, 6) .. "/" .. d:sub(1, 4)) or d end
    local text
    if lic.expired then
        text = "Your Visualised " .. (lic.was == "enterprise" and "Enterprise" or "Pro") .. " licence ran out on " .. day(lic.expires)
            .. ", so Visualised is running as Community.\n\nYour forms are untouched. Renew to get the app exports back."
    elseif lic.tier == "community" then
        text = "Visualised Community\n\nDesign, run, save and share forms, and put them on the web, free.\n\nVisualised Pro adds exporting a form "
            .. "as an app of its own for Windows, Linux or Android, importing forms from other tools, and Link without limits."
    else
        text = "Visualised " .. lic.label .. (lic.name ~= "" and ("\nLicensed to " .. lic.name) or "") .. "\nLicence " .. lic.id
            .. ", issued " .. day(lic.issued) .. (lic.expires ~= "" and ("\nValid until " .. day(lic.expires)) or "")
    end
    Vml("InfoDialog", text, "Visualised licence")
end

function LicenceEnter(...)
    local key = Vml("PromptDialog", "Visualised licence", "Paste the licence key from your email:", "")
    if key == "" then return end
    local problem = Vml("SetLicenceKey", key)
    if problem ~= "" then
        Vml("InfoDialog", problem, "Visualised licence")
        return
    end
    Vml("RunScript", "ApplyLicence")
    local lic = require("dkjson").decode(Vml("GetLicence"))
    Vml("SetStatusText", "Visualised " .. lic.label .. " is active")
    Vml("InfoDialog", "Visualised " .. lic.label .. " is active on this computer.", "Visualised licence")
end

function LicenceRemove(...)
    if Vml("ConfirmDialog", "Remove the licence key from this computer and go back to Visualised Community?\n\nKeep a copy of the key: you can enter it again at any time.") ~= "true" then return end
    Vml("RemoveLicenceKey")
    Vml("RunScript", "ApplyLicence")
    Vml("SetStatusText", "Licence key removed: Visualised Community")
end

function LicenceUpgrade(...)
    local lic = require("dkjson").decode(Vml("GetLicence"))
    if lic.tier == "community" then
        Vml("OpenUrl", lic.buy_url)
    else
        Vml("OpenUrl", "mailto:hello@tiny-web.uk?subject=Visualised%20Enterprise")
    end
end
