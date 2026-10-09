-- The Visualised designer: Settings: grid and snap, C# scripting, databases.
-- One of the modules of designer/Designer.vmlproj. Each function here is a handler: a control or menu item of the
-- designer names it (OnClick=FileSave), or another handler runs it with Vml("RunScript", "FileSave").

function ToggleGrid(...)
    local on = Vml("GetProperty", "Surface", "ShowGrid") ~= "false"
    Vml("SetPreference", "show_grid", on and "false" or "true")
    Vml("RunScript", "ApplySettings")
end

-- The designer's own settings are this user's preferences: they are kept between runs and apply to every form.
function ApplySettings(...)
    local function pref(key, default)
        local v = Vml("GetPreference", key, default)
        return v == "" and default or v
    end
    local snap, grid, show = pref("snap_to_grid", "true"), pref("grid_size", "8"), pref("show_grid", "true")
    Vml("SetProperty", "Surface", "SnapToGrid", snap)
    Vml("SetProperty", "Surface", "GridSize", grid)
    Vml("SetProperty", "Surface", "ShowGrid", show)
    local function tick(on) return on and "\226\156\147  " or "     " end
    Vml("SetMenuItemText", "SetSnap", tick(snap == "true") .. "Snap to Grid")
    Vml("SetMenuItemText", "ViewGrid", tick(show == "true") .. "Show Grid")
    for _, n in ipairs({"4", "8", "16", "24"}) do
        Vml("SetMenuItemText", "SetGrid" .. n, tick(n == grid) .. n .. " pixels")
    end
end

function ToggleSnap(...)
    local on = Vml("GetProperty", "Surface", "SnapToGrid") ~= "false"
    Vml("SetPreference", "snap_to_grid", on and "false" or "true")
    Vml("RunScript", "ApplySettings")
    Vml("SetStatusText", on and "Snap to grid is off: controls move freely" or "Snap to grid is on")
end

function SetGridSize(...)
    local args = { ... }
    Vml("SetPreference", "grid_size", args[1])
    Vml("RunScript", "ApplySettings")
    Vml("SetStatusText", "Grid: " .. args[1] .. " pixels")
end

function ApplyCSharp(...)
    local on = false
    for _, l in ipairs(require("dkjson").decode(Vml("GetLanguages"))) do if l == "C#" then on = true end end
    Vml("SetMenuItemText", "SetCSharp", on and "C# Scripting: On" or "C# Scripting: Off...")
end

function CSharpSetup(...)
    local args = { ... }
    local st = require("dkjson").decode(Vml("CSharpStatus"))
    if st.ready then
        Vml("InfoDialog", "C# scripting is on.\n\nIn the script editor, choose C# in the Language list. Scripts have Vml(...), args and State, exactly as Lua scripts do.\n\n.NET SDK " .. st.sdk, "C# scripting")
        return
    end
    if not st.sdk_ok then
        local have = st.sdk ~= "" and ("  (This computer has " .. st.sdk .. ".)") or ""
        if Vml("ConfirmDialog", "C# scripts need Microsoft's free .NET SDK, version 8 or later, and it isn't on this computer." .. have .. "\n\nGet it now?", "C# scripting") ~= "true" then return end
        if Vml("InstallDotnet") == "started" then
            Vml("InfoDialog", "The .NET SDK is installing in a window of its own.\n\nWhen it has finished, choose Settings, C# Scripting again.", "C# scripting")
        else
            Vml("OpenUrl", st.download)
            local linux = Vml("GetSetting", "platform"):sub(1, 5) == "linux" and "\n\nOn Ubuntu it is quicker from a terminal:\n    sudo apt install dotnet-sdk-8.0" or ""
            Vml("InfoDialog", "The download page is open in your browser. Install the .NET SDK (the SDK, not only the Runtime)." .. linux .. "\n\nThen choose Settings, C# Scripting again.", "C# scripting")
        end
        return
    end
    if Vml("ConfirmDialog", "Turn on C# scripting?\n\nVisualised will build its C# script host with the .NET SDK on this computer (" .. st.sdk .. "). It takes about a minute, and needs the internet the first time.", "C# scripting") ~= "true" then return end
    local problem = Vml("CSharpSetup")
    Vml("RunScript", "ApplyCSharp")
    if problem == "" then
        Vml("InfoDialog", "C# scripting is on.\n\nIn the script editor, choose C# in the Language list.", "C# scripting")
    else
        Vml("InfoDialog", "C# scripting couldn't be set up:\n\n" .. problem, "C# scripting")
    end
end

-- Settings > Databases: the project's databases, and the ODBC drivers and data sources this computer has.
-- args[1]: a database to show ("+" for a new one), or nothing.
function DatabasesShow(...)
    local args = { ... }
    local want = args[1] or ""
    if want == "+" then
        local raw = Vml("ProjectInfo")
        local taken = raw ~= "" and require("dkjson").decode(raw).databases or {}
        local n = 1
        want = "main"
        while taken[want] do n = n + 1; want = "data" .. n end
    end
    Vml("SetSetting", "db_edit", want)
    Vml("FormOpenModal", "databases.vml")
    if Vml("ProjectInfo") ~= "" then Vml("RunScript", "RefreshProject") end
end
