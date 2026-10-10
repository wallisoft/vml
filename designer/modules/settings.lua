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
    Vml("RunScript", "ApplyTheme")
end

-- The designer's themes: its menu bar, the edge of its window and the boxes it shows all take these colours.
-- { bar, bar text, hover, hover text, menu background, menu border }
THEMES = {
    Classic  = { "#1E3A8A", "White",   "#2563EB", "White",   "White", "#1E3A8A" },
    Slate    = { "#334155", "White",   "#475569", "White",   "White", "#334155" },
    Forest   = { "#14532D", "White",   "#15803D", "White",   "White", "#14532D" },
    Plum     = { "#581C87", "White",   "#7E22CE", "White",   "White", "#581C87" },
    Charcoal = { "#111827", "#F9FAFB", "#374151", "White",   "White", "#111827" },
    Paper    = { "#E5E7EB", "#111827", "#CBD5E1", "#111827", "White", "#9CA3AF" },
}
THEME_ORDER = { "Classic", "Slate", "Forest", "Plum", "Charcoal", "Paper" }

function ApplyTheme(...)
    local name = Vml("GetPreference", "theme", "Classic")
    if not THEMES[name] then name = "Classic" end
    for i, prop in ipairs({ "Background", "Foreground", "HoverBackground", "HoverForeground", "PopupBackground", "PopupBorder" }) do
        Vml("SetProperty", "Theme", prop, THEMES[name][i])
    end
    for _, n in ipairs(THEME_ORDER) do
        Vml("SetMenuItemText", "SetTheme" .. n, (n == name and "\226\156\147  " or "     ") .. n)
    end
end

function SetTheme(...)
    local args = { ... }
    Vml("SetPreference", "theme", args[1])
    Vml("RunScript", "ApplyTheme")
    Vml("SetStatusText", "Theme: " .. args[1])
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
-- The one line that sets ODBC up on Linux: ODBC itself, the drivers that are a package away, and Python's ODBC
-- module if that is what is missing. (The Databases screen uses this too: every form of the project has the modules.)
function OdbcSetupLine()
    local state = require("dkjson").decode(Vml("DbOdbcState"))
    local line = "sudo apt install -y unixodbc odbc-mdbtools libsqliteodbc odbc-postgresql odbc-mariadb"
    if not state.module then line = line .. " && pip install --break-system-packages pyodbc" end
    return line
end

-- Before the Databases screen opens: if this computer can't use ODBC at all, say so, with what to do about it.
-- Once a session is enough; the screen still opens, because a SQLite file needs no ODBC.
function OdbcCheck()
    local state = require("dkjson").decode(Vml("DbOdbcState"))
    if state.ready or Vml("GetSetting", "odbc_told") == "true" then return end
    Vml("SetSetting", "odbc_told", "true")
    if package.config:sub(1, 1) == "\\" then
        Vml("InfoDialog", "ODBC isn't available on this computer (" .. state.why .. "), so databases on a server can't be reached yet.\n\nSQLite files work as they are, and the Databases screen opens next for those.", "ODBC isn't set up")
        return
    end
    local line = OdbcSetupLine()
    if Vml("ConfirmDialog", "ODBC isn't set up on this computer yet: " .. state.why .. ".\n\n"
        .. "Until it is, a project can use SQLite files but not SQL Server, MySQL, PostgreSQL, Access or anything else reached through a driver.\n\n"
        .. "This one line, in a terminal, sets it up, with the drivers for Access files, SQLite, PostgreSQL and MySQL or MariaDB:\n\n" .. line
        .. "\n\nCopy that line, ready to paste into a terminal?\n\n(The Databases screen opens next either way: SQLite files need none of this.)", "ODBC isn't set up") == "true" then
        Vml("ClipboardSet", line)
        Vml("SetStatusText", "Copied: paste it into a terminal. When it has finished, press Get a driver in the Databases screen and the lists fill.")
    end
end

function DatabasesShow(...)
    local args = { ... }
    local want = args[1] or ""
    if want ~= "+" and Vml("ControlExists", want) == "true" then want = "" end      -- chosen from the menu: no database in particular
    OdbcCheck()
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

-- Project > Browse Data: look inside the project's databases (or, from the Databases screen, the address on screen).
-- args: a database's name and an address, both optional.
function BrowseData(...)
    local args = { ... }
    local name, address = args[1] or "", args[2] or ""
    if Vml("ControlExists", name) == "true" then name = "" end            -- chosen from the menu: no database in particular
    if address == "" and Vml("ProjectInfo") == "" then
        return Vml("InfoDialog", "Open a project first: the browser shows the databases a project names.\n\n(Or use Browse in Settings > Databases (ODBC), which shows whatever address is on screen.)", "Browse Data")
    end
    Vml("SetSetting", "db_browse_name", name)
    Vml("SetSetting", "db_browse_address", address)
    Vml("FormOpenModal", "browser.vml")
end
