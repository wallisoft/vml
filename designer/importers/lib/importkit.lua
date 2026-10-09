-- importkit: what importers are written with. An importer does  local kit = require("importkit").
--
--   kit.match(pattern, text [, flags])     Python-style regular expression, from the START of the text:
--                                          returns the groups (or the whole match if there are none), or nil
--   kit.search(pattern, text [, flags])    the same, anywhere in the text
--   kit.findall(pattern, text [, flags])   every match: a list of strings (no or one group) or of lists (more)
--   kit.sub(pattern, replacement, text)    replace every match (\1 is group 1)
--   kit.split(pattern, text)               the pieces of the text between matches
--   kit.trim / lines / round / contains / plural / caption / safe_name         small things
--   kit.read / write / exists / find_file / list / copy / size                 files
--   kit.read_b64 / write_b64 / picture_kind / is_sqlite                        files that aren't text
--   kit.dirname / basename / stem / ending / join / slashes                    paths (always with / between)
--   kit.form()                             a VML form being written: f:emit(kind, name, parent, {{key, value}, ...}),
--                                          f:comment(text), f:script(name, body), f:text()
--   kit.commented(lines)                   an event handler's code as Lua comments (for f:script)
--   kit.basic_steps(lines, ctx)            the same, with the plain steps of Basic turned into Lua that runs (see below)
--   kit.as_comments(heading, lines)        a whole file of code kept for reference: every line a Lua comment
--   kit.project(folder, name)              a Visualised project being written (see below)
--   kit.json                               dkjson

local json = require("dkjson")
local kit = { json = json }

-- ------------------------------------------------------------------ regular expressions (the engine's, so the same everywhere)
local function groups(raw)
    if raw == nil or raw == "" then return nil end
    local m = json.decode(raw)
    if #m == 1 then return m[1] end
    return table.unpack(m, 2)
end

function kit.search(pattern, text, flags)
    return groups(Vml("RegexMatch", pattern, text or "", flags or ""))
end

function kit.match(pattern, text, flags)
    return groups(Vml("RegexMatch", "^(?:" .. pattern .. ")", text or "", flags or ""))
end

function kit.findall(pattern, text, flags)
    local out = {}
    for _, m in ipairs(json.decode(Vml("RegexFindAll", pattern, text or "", flags or "")) or {}) do
        if #m <= 2 then
            out[#out + 1] = m[#m]                       -- the whole match, or its only group
        else
            out[#out + 1] = { table.unpack(m, 2) }
        end
    end
    return out
end

function kit.sub(pattern, replacement, text, flags)
    return Vml("RegexReplace", pattern, replacement, text or "", flags or "")
end

function kit.split(pattern, text, flags)
    local out = {}
    for piece in (kit.sub(pattern, "\1", text, flags) .. "\1"):gmatch("(.-)\1") do out[#out + 1] = piece end
    return out
end

-- ------------------------------------------------------------------ small things Lua leaves out
function kit.trim(s) return (tostring(s or ""):gsub("^%s+", ""):gsub("%s+$", "")) end

function kit.lines(text)
    local out = {}
    text = tostring(text or ""):gsub("\r\n", "\n"):gsub("\r", "\n")
    for line in (text .. "\n"):gmatch("(.-)\n") do out[#out + 1] = line end
    if out[#out] == "" then out[#out] = nil end
    return out
end

function kit.round(n) return math.floor(n + 0.5) end

function kit.contains(list, value)
    for _, v in ipairs(list) do if v == value then return true end end
    return false
end

function kit.plural(n, word) return n .. " " .. word .. (n == 1 and "" or "s") end

-- ------------------------------------------------------------------ files and paths
function kit.read(path, encoding) return Vml("FileRead", path, encoding or "") end
function kit.write(path, text) return Vml("FileWrite", path, text) == "true" end
function kit.exists(path) return Vml("FileExists", path) == "true" end

-- A file by its name whatever the capitals (projects copied from Windows often disagree): its real path, or nil.
function kit.find_file(path)
    if kit.exists(path) then return path end
    local want = kit.basename(path):lower()
    for _, found in ipairs(json.decode(Vml("FileList", kit.dirname(path), "*", "")) or {}) do
        if kit.basename(found):lower() == want then return found end
    end
    return nil
end
function kit.size(path) return tonumber(Vml("FileSize", path)) or -1 end
function kit.copy(from, to) return Vml("FileCopy", from, to) == "true" end
function kit.read_b64(path, offset, length) return Vml("FileReadBase64", path, offset or 0, length or -1) end
function kit.write_b64(path, data) return Vml("FileWriteBase64", path, data) == "true" end

function kit.list(folder, pattern, recursive)
    return json.decode(Vml("FileList", folder, pattern or "*", recursive and "true" or "")) or {}
end

function kit.slashes(path) return (tostring(path or ""):gsub("\\", "/")) end
function kit.dirname(path) return kit.slashes(path):match("^(.*)/[^/]*$") or "." end
function kit.basename(path) return kit.slashes(path):match("([^/]*)$") end
function kit.stem(path) local b = kit.basename(path) return b:match("^(.*)%.[^.]*$") or b end
function kit.ending(path) return (kit.basename(path):match("%.([^.]*)$") or ""):lower() end
function kit.join(a, b) if a == "" or a == "." then return b end return (a:gsub("/+$", "")) .. "/" .. b end
function kit.safe_name(name) local s = tostring(name or ""):gsub("[^%w_]", "_") if s == "" then s = "Item" end return s end

-- A picture's kind from the first bytes of its base64 ("" if it isn't one a form can show).
local PICTURES = { iVBOR = "png", ["/9j/"] = "jpg", R0lG = "gif", Qk = "bmp" }
function kit.picture_kind(b64)
    for start, kind in pairs(PICTURES) do
        if b64:sub(1, #start) == start then return kind end
    end
    return ""
end

function kit.is_sqlite(path)
    return kit.read_b64(path, 0, 16) == "U1FMaXRlIGZvcm1hdCAzAA=="       -- "SQLite format 3\0"
end

-- ------------------------------------------------------------------ a form being written
local Form = {}
Form.__index = Form

function kit.form()
    return setmetatable({ out = {}, scripts = {} }, Form)
end

function Form:comment(text) self.out[#self.out + 1] = "# " .. text; self.out[#self.out + 1] = "" end

-- props is a list of {key, value} pairs, written in that order; nil and "" values are left out.
function Form:emit(kind, name, parent, props)
    local out = self.out
    out[#out + 1] = "@" .. kind .. " " .. name
    if parent and parent ~= "" then out[#out + 1] = "Parent=" .. parent end
    for _, p in ipairs(props or {}) do
        local value = p[2]
        if value ~= nil and value ~= "" then
            out[#out + 1] = p[1] .. "=" .. tostring(value):gsub("\r", ""):gsub("\n", " ")
        end
    end
    out[#out + 1] = ""
end

-- Keep an event handler's original code as a script of comments. Returns the script's name.
function Form:script(name, body) self.scripts[#self.scripts + 1] = { name, body }; return name end

function Form:text()
    local out = {}
    for _, line in ipairs(self.out) do out[#out + 1] = line end
    for _, s in ipairs(self.scripts) do
        local tag = "END_" .. s[1]:gsub("[^%w_]", "_"):upper()
        out[#out + 1] = "@Script " .. s[1]
        out[#out + 1] = "Interpreter=lua"
        out[#out + 1] = "<<" .. tag
        for _, line in ipairs(s[2]) do out[#out + 1] = line end
        out[#out + 1] = tag
        out[#out + 1] = ""
    end
    return table.concat(out, "\n")
end

-- A handler's lines as Lua comments, keeping their shape but not their left margin.
function kit.commented(lines)
    local indent
    for _, line in ipairs(lines) do
        if line:match("%S") then
            local n = #line:match("^%s*")
            if indent == nil or n < indent then indent = n end
        end
    end
    indent = indent or 0
    local out = {}
    for _, line in ipairs(lines) do
        if line:match("%S") then out[#out + 1] = "--   " .. (line:sub(indent + 1):gsub("%s+$", "")) else out[#out + 1] = "--" end
    end
    return out
end

-- A whole file of code, kept for reference: a heading, then every line a comment (runs of blank lines closed up).
function kit.as_comments(heading, lines)
    local out = {}
    for _, h in ipairs(heading) do out[#out + 1] = "-- " .. h end
    out[#out + 1] = "--"
    local blank = false
    for _, line in ipairs(lines) do
        if line:match("%S") then
            out[#out + 1] = "--   " .. (line:gsub("%s+$", ""))
            blank = false
        elseif not blank then
            out[#out + 1] = "--"
            blank = true
        end
    end
    return table.concat(out, "\n") .. "\n"
end

-- ------------------------------------------------------------------ the plain steps of Basic, made to run
-- Most of an event handler has to be rewritten by a person. A few steps mean one thing only, and those are turned
-- into Lua so an imported app opens its own forms, closes them and says what it said:
--     frmAbout.Show / .ShowDialog()      Vml("FormOpen" or "FormOpenModal", "frmAbout")
--     Unload Me / Me.Close() / Me.Hide   Vml("CloseSelf")          Unload frmX      Vml("CloseForm", "frmX")
--     End / Application.Exit()           Vml("AppExit")            Exit Sub/Return  do return end
--     MsgBox "text" / MessageBox.Show    Vml("InfoDialog", ...)    when the text is written out, not worked out
--     x.Enabled / .Visible = True|False, x.Caption / .Text = "text", Me.Caption = "text"
-- Only steps that always happen are turned: nothing inside an If, a loop, a With or a Try, and nothing after a
-- line that might have left the routine early. Everything else stays as a comment, exactly as it was.
--
--   kit.basic_steps(lines, ctx) -> a Lua line for every line given, and how many were made to run
--   ctx.form      this form's name            ctx.forms     { lower name = form name } of the project, or nil if
--   ctx.net       true for Visual Basic .NET                unknown (then any name that isn't a control will do)
--   ctx.controls  { lower name = { name = its name here, kind = "Button", text = "Content" or nil } }
--   ctx.closing   true for the handler of the form closing: nothing in it is turned
local TEXT_WORDS = { vbcrlf = "\r\n", vbnewline = "\r\n", vblf = "\n", vbcr = "\r", vbtab = "\t",
    ["environment.newline"] = "\n", ["controlchars.crlf"] = "\r\n", ["controlchars.newline"] = "\r\n",
    ["controlchars.lf"] = "\n", ["controlchars.tab"] = "\t" }

-- Text that is written out ("a" & vbCrLf & "b"): what it says, or nil if any part of it is worked out.
function kit.basic_text(expr)
    local out, i, n, want = {}, 1, #expr, true
    while true do
        i = expr:find("%S", i)
        if not i then break end
        local c = expr:sub(i, i)
        if want and c == '"' then
            local j, piece = i + 1, {}
            while true do
                local q = expr:find('"', j, true)
                if not q then return nil end
                piece[#piece + 1] = expr:sub(j, q - 1)
                if expr:sub(q + 1, q + 1) == '"' then piece[#piece + 1] = '"'; j = q + 2 else i = q + 1 break end
            end
            out[#out + 1] = table.concat(piece)
            want = false
        elseif want then
            local word = expr:match("^[%a_][%w_.]*", i)
            local text = word and TEXT_WORDS[word:lower()]
            if not text then return nil end
            out[#out + 1] = text
            i = i + #word
            want = false
        elseif c == "&" or c == "+" then
            i, want = i + 1, true
        else
            return nil
        end
    end
    if want then return nil end
    return (table.concat(out):gsub("\r\n", "\n"))
end

local function lua_text(s)
    return '"' .. s:gsub("\\", "\\\\"):gsub('"', '\\"'):gsub("\n", "\\n"):gsub("\r", "\\r"):gsub("\t", "\\t") .. '"'
end
kit.lua_text = lua_text

-- A line of Basic without its comment, and the comment.
local function basic_code(line)
    local quoted = false
    for i = 1, #line do
        local c = line:sub(i, i)
        if c == '"' then quoted = not quoted
        elseif c == "'" and not quoted then return kit.trim(line:sub(1, i - 1)), line:sub(i) end
    end
    return kit.trim(line), ""
end

local function basic_args(text)                              -- split at the commas that aren't inside "" or ()
    local out, depth, quoted, from = {}, 0, false, 1
    for i = 1, #text do
        local c = text:sub(i, i)
        if c == '"' then quoted = not quoted
        elseif not quoted then
            if c == "(" then depth = depth + 1 elseif c == ")" then depth = depth - 1
            elseif c == "," and depth == 0 then out[#out + 1] = kit.trim(text:sub(from, i - 1)); from = i + 1 end
        end
    end
    out[#out + 1] = kit.trim(text:sub(from))
    return out
end

local function unwrapped(text)                               -- (a, b) -> a, b   when the brackets go round all of it
    local inner = text:match("^%((.*)%)$")
    if not inner then return text end
    local depth, quoted = 0, false
    for i = 1, #inner do
        local c = inner:sub(i, i)
        if c == '"' then quoted = not quoted
        elseif not quoted then
            if c == "(" then depth = depth + 1 elseif c == ")" then depth = depth - 1 if depth < 0 then return text end end
        end
    end
    return inner
end

local OPENS = { "^if%s.*%sthen$", "^for%s", "^do$", "^do%s", "^while%s", "^select%s+case", "^with%s", "^try$", "^using%s",
                "^synclock%s", "^#if%s" }
local CLOSES = { "^end%s+if$", "^next$", "^next%s", "^loop$", "^loop%s", "^wend$", "^end%s+while$", "^end%s+select$",
                 "^end%s+with$", "^end%s+try$", "^end%s+using$", "^end%s+synclock$", "^#end%s+if$" }
local LEAVES = { "exit%s+sub", "exit%s+function", "exit%s+property", "%f[%a]goto%f[%A]", "%f[%a]return%f[%A]",
                 "%f[%a]resume%f[%A]", "%f[%a]unload%f[%A]", "%.close%f[%A]", "then%s+end$", "^end$", "%f[%a]throw%f[%A]",
                 "application%.exit" }

local function one_step(code, ctx, vars)
    local low = code:lower()
    local controls, forms = ctx.controls or {}, ctx.forms
    local function form_called(word)
        local key = word:lower()
        if vars[key] then return vars.real[vars[key]] end
        if key == "me" or controls[key] or key:match("^vb") then return nil end
        if forms then return forms[key] end
        return word
    end

    if low == "exit sub" or low == "exit function" or (ctx.net and low == "return") then return "do return end" end
    if low == "end" or low == "application.exit()" or low == "application.exit" then return 'Vml("AppExit")' end
    if low == "unload me" or low == "me.close()" or low == "me.close" or low == "me.hide" or low == "me.hide()"
        or (ctx.net and (low == "close()" or low == "hide()")) then
        return 'Vml("CloseSelf")'
    end
    local other = code:match("^[Uu]nload%s+([%a_][%w_]*)$") or code:match("^([%a_][%w_]*)%.[Cc]lose%(?%)?$")
        or code:match("^([%a_][%w_]*)%.[Hh]ide%(?%)?$")
    if other then
        local form = (forms or vars[other:lower()]) and form_called(other)
        return form and ('Vml("CloseForm", ' .. lua_text(form) .. ")") or nil
    end

    -- opening a form
    local who, how, rest = code:match("^([%a_][%w_.]*)%.([Ss][Hh][Oo][Ww][%a]*)%s*(.*)$")
    if who then
        who = who:gsub("^[Mm]y%.[Ff]orms%.", "")
        local kind = how:lower()
        if (kind == "show" or kind == "showdialog") and not who:find(".", 1, true) then
            local form = form_called(who)
            if form then
                local first = kit.trim(unwrapped(kit.trim(rest))):lower()
                local modal = kind == "showdialog" or first:match("^vbmodal") or first:match("^1%f[%D]")
                return 'Vml("' .. (modal and "FormOpenModal" or "FormOpen") .. '", ' .. lua_text(form) .. ")"
            end
        end
    end
    local made = code:match("^[Nn]ew%s+([%a_][%w_]*)%s*%(?%)?%.[Ss]how[Dd]ialog%(?%)?$")       -- New frmAbout().ShowDialog()
    if made and form_called(made) then return 'Vml("FormOpenModal", ' .. lua_text(form_called(made)) .. ")" end

    -- a message
    local said = code:match("^[Mm][Ss][Gg][Bb][Oo][Xx]%s*(.+)$")
    local title_at = 3
    if not said then
        said = code:match("^[Mm]essage[Bb]ox%.[Ss]how%s*(%(.+%))$") or code:match("^[Mm]sg[Bb]ox[Rr]esult%s*(.+)$")
        title_at = 2
    end
    if said then
        local parts = basic_args(unwrapped(kit.trim(said)))
        local text = parts[1] and kit.basic_text(parts[1])
        if text then
            local title = parts[title_at] and kit.basic_text(parts[title_at])
            return 'Vml("InfoDialog", ' .. lua_text(text) .. (title and title ~= "" and (", " .. lua_text(title)) or "") .. ")"
        end
        return nil
    end

    -- a simple setting
    local target, prop, value = code:match("^([%a_][%w_]*%(?%d*%)?)%.([%a]+)%s*=%s*(.+)$")
    if not target then
        prop, value = code:match("^([Cc]aption)%s*=%s*(.+)$")
        target = prop and "Me" or nil
    end
    if target then
        if not target:find("(", 1, true) then target = target:gsub("%)$", "") end
        local me = target:lower() == "me"
        local c = controls[target:lower()]
        prop = prop:lower()
        local flag = ({ ["true"] = "true", ["false"] = "false" })[value:lower()]
        if me and (prop == "caption" or (ctx.net and prop == "text")) then
            local text = kit.basic_text(value)
            if text then return 'Vml("SetProperty", ' .. lua_text(ctx.form) .. ', "Title", ' .. lua_text(text) .. ")" end
        elseif c and c.kind ~= "MenuItem" and (prop == "enabled" or prop == "visible") and flag then
            return 'Vml("SetProperty", ' .. lua_text(c.name) .. ', "' .. (prop == "enabled" and "IsEnabled" or "IsVisible") .. '", "' .. flag .. '")'
        elseif c and c.text and (prop == "caption" or prop == "text") then
            local text = kit.basic_text(value)
            if text then return 'Vml("SetProperty", ' .. lua_text(c.name) .. ', "' .. c.text .. '", ' .. lua_text(text) .. ")" end
        end
    end
    return nil
end

function kit.basic_steps(lines, ctx)
    local out, made, depth, live, carried, blocks = {}, 0, 0, not ctx.closing, false, {}
    local vars = { real = {} }                                -- Dim f As New frmAbout: f is frmAbout from here on
    local indent
    for _, line in ipairs(lines) do
        if line:match("%S") then
            local n = #line:match("^%s*")
            if indent == nil or n < indent then indent = n end
        end
    end
    indent = indent or 0
    for i, line in ipairs(lines) do
        local kept = line:match("%S") and ("--   " .. (line:sub(indent + 1):gsub("%s+$", ""))) or "--"
        local code, remark = basic_code(line)
        local low = code:lower()
        local continues = code:match("%s_$") ~= nil
        local step
        if code == "" or i == 1 or i == #lines or carried or continues then
            step = nil
        else
            local closes, opens = false, false
            for _, pat in ipairs(CLOSES) do if low:match(pat) then closes = true break end end
            if not closes then for _, pat in ipairs(OPENS) do if low:match(pat) then opens = true break end end end
            local held, holder = code:match("^[Uu]sing%s+([%a_][%w_]*)%s+[Aa]s%s+[Nn]ew%s+([%a_][%w_]*)%s*%(?%)?$")
            local form_held = held and (ctx.forms and ctx.forms[holder:lower()] or (not ctx.forms and not (ctx.controls or {})[holder:lower()] and holder))
            if closes then
                if table.remove(blocks) ~= "form" then depth = math.max(0, depth - 1) end
            elseif opens and form_held and depth == 0 then        -- Using f As New frmAbout: no more than a Dim
                blocks[#blocks + 1] = "form"
                vars[held:lower()] = holder:lower(); vars.real[holder:lower()] = form_held
            elseif opens then
                blocks[#blocks + 1] = "block"
                depth = depth + 1
            elseif depth == 0 and live and not low:match("^on%s+error") and not low:match("^[%a_][%w_]*:$") then
                local var, class = code:match("^[Dd]im%s+([%a_][%w_]*)%s+[Aa]s%s+[Nn]ew%s+([%a_][%w_]*)%s*%(?%)?$")
                if not var then var, class = code:match("^[Dd]im%s+([%a_][%w_]*)%s+[Aa]s%s+[%a_][%w_]*%s*=%s*[Nn]ew%s+([%a_][%w_]*)%s*%(?%)?$") end
                if not var then var, class = code:match("^[Dd]im%s+([%a_][%w_]*)%s*=%s*[Nn]ew%s+([%a_][%w_]*)%s*%(?%)?$") end
                if var then
                    local key = class:lower()
                    local known = ctx.forms and ctx.forms[key] or (not ctx.forms and not (ctx.controls or {})[key] and class)
                    if known then vars[var:lower()] = key; vars.real[key] = known end
                elseif not (code:gsub('"[^"]*"', "")):find(":", 1, true) then     -- one step to a line
                    step = one_step(code, ctx, vars)
                end
            end
        end
        if step then
            made = made + 1
            out[#out + 1] = step .. "   -- was: " .. kit.trim(line)
            if step == "do return end" then live = false end     -- nothing after it happens
        else
            out[#out + 1] = kept
            if live and code ~= "" and i > 1 and i < #lines and not low:match("^on%s+error") then
                for _, pat in ipairs(LEAVES) do
                    if low:match(pat) then live = false break end   -- it might have stopped here: nothing after it is sure to happen
                end
            end
        end
        carried = continues
    end
    return out, made
end

-- Windows marks a letter with & to underline it as a shortcut; && is a real ampersand.
function kit.caption(text)
    return (tostring(text or ""):gsub("&&", "\1"):gsub("&", ""):gsub("\1", "&"))
end

-- ------------------------------------------------------------------ a project being written
--   local p = kit.project(folder, "Shop")
--   p:form("frmMain", vml_text, notes, {controls = 12, menu_items = 3, scripts = 4, pictures = 1}, "frmMain.frm")
--   p:module("Pricing", heading_lines, code_lines)      code kept as comments
--   p:databases(original_folder)                        SQLite files there are copied and named
--   p:access_databases(original_folder, code_text)      Access files there (or named in the code) become SQLite ones
--   return p:finish("frmMain", "Shop.vbp")              the JSON an ImportProject script hands back
local Project = {}
Project.__index = Project

function kit.project(folder, name)
    return setmetatable({ folder = kit.slashes(folder), name = name, forms = {}, modules = {}, dbs = {}, db_files = {},
                          report = {}, taken = {}, totals = { controls = 0, menu_items = 0, scripts = 0, pictures = 0 } }, Project)
end

function Project:free_name(file)
    return not self.taken[file:lower()]
end

function Project:form(name, vml, notes, stats, source)
    local file = name .. ".vml"
    if self.taken[file:lower()] then return false end
    self.taken[file:lower()] = true
    kit.write(kit.join(self.folder, file), vml .. "\n")
    self.forms[#self.forms + 1] = file
    for key, n in pairs(stats or {}) do self.totals[key] = (self.totals[key] or 0) + n end
    self.report[#self.report + 1] = "== " .. name .. "  (" .. (source or "") .. ")"
    for _, note in ipairs(notes or {}) do self.report[#self.report + 1] = "   " .. note end
    self.report[#self.report + 1] = ""
    return true
end

-- Something to say about the project as a whole (a file that was listed but missing, say): it goes in IMPORT-NOTES.txt.
function Project:note(text)
    self.project_notes = self.project_notes or {}
    self.project_notes[#self.project_notes + 1] = text
end

function Project:module(name, heading, lines)
    local base, file, n = kit.safe_name(name), nil, 1
    repeat
        file = (n == 1 and base or (base .. "_" .. n)) .. ".lua"
        n = n + 1
    until not self.taken[file:lower()]
    self.taken[file:lower()] = true
    kit.write(kit.join(self.folder, file), kit.as_comments(heading, lines))
    self.modules[#self.modules + 1] = file
    return file
end

function Project:databases(folder)
    for _, path in ipairs(kit.list(folder, "*")) do
        local size = kit.size(path)
        if size >= 16 and size <= 200 * 1024 * 1024 and kit.is_sqlite(path) then
            local file = kit.basename(path)
            kit.copy(path, kit.join(self.folder, file))
            local name = kit.safe_name(kit.stem(file))
            if not name:match("^[%a_]") then name = "db_" .. name end
            self.dbs[#self.dbs + 1] = { name, "sqlite:" .. file }
            self.db_files[#self.db_files + 1] = file
        end
    end
end

-- Access databases (.mdb, .accdb): the ones in the project's folder, and the ones its code or settings name
-- (mentions: any text to look through). Each one's tables and rows are copied into a SQLite file of the same name
-- in the new project, which the app then carries with it (to the web as well). That needs an ODBC driver for
-- Access on this computer: without one, the notes say what to install, and nothing else about the import changes.
local ACCESS_SKIP = { bin = true, obj = true, [".git"] = true, [".vs"] = true, packages = true }
function Project:access_databases(folder, mentions)
    local found, order = {}, {}
    local function have(path)
        local key = kit.basename(path):lower()
        if not found[key] then found[key] = path; order[#order + 1] = key end
    end
    for _, path in ipairs(kit.list(folder, "*.mdb;*.accdb", true)) do
        local skip = false
        for part in kit.dirname(path:sub(#kit.slashes(folder) + 2)):gmatch("[^/]+") do
            if ACCESS_SKIP[part:lower()] then skip = true end
        end
        if not skip then have(path) end
    end
    local missing = {}
    for _, m in ipairs(kit.findall([[([^"'=;<>|*?\r\n&()]*\.(?:mdb|accdb))\b]], mentions or "", "i")) do
        local named = kit.trim(kit.slashes(m))
        local key = kit.basename(named):lower()
        if key ~= "" and not key:match("^%.") and not found[key] and not missing[key] then
            local real = named:match("^%a:/") and kit.exists(named) and named or kit.find_file(kit.join(folder, kit.basename(named)))
            if real then have(real) else missing[key] = kit.basename(named); missing[#missing + 1] = kit.basename(named) end
        end
    end
    self.access_missing = {}
    for _, name in ipairs(missing) do self.access_missing[#self.access_missing + 1] = name end
    for _, name in ipairs(missing) do
        self:note("The code names the Access database " .. name .. ", which isn't with the project. Put a copy beside the "
            .. "original project file and import again, and its data will come across.")
    end
    if #order == 0 then return end

    local driver
    for _, d in ipairs(json.decode(Vml("DbDrivers")) or {}) do
        local low = d:lower()
        if low:find("access", 1, true) and (not driver or low:find("accdb", 1, true)) then driver = d end
    end
    if not driver then
        for _, d in ipairs(json.decode(Vml("DbDrivers")) or {}) do
            if d:lower():find("mdb", 1, true) then driver = d end
        end
    end
    self.access = { copied = {}, waiting = {}, failed = {} }
    for _, key in ipairs(order) do
        local path, file = found[key], kit.basename(found[key])
        local stem = kit.safe_name(kit.stem(file))
        if not stem:match("^[%a_]") then stem = "db_" .. stem end
        local out = stem .. ".db"
        if not driver then
            self.access.waiting[#self.access.waiting + 1] = file
        elseif self.taken[out:lower()] or kit.exists(kit.join(self.folder, out)) then
            self:note(file .. " was not copied: there is already a " .. out .. " in the new project.")
        else
            local address = path:match("^%a:/") and path:gsub("/", "\\") or path
            local src, dst = "vml_import_from", "vml_import_into"
            Vml("DbClose", src); Vml("DbClose", dst)
            if Vml("DbOpen", src, "odbc:Driver={" .. driver .. "};DBQ=" .. address .. ";") ~= "true" then
                self.access.failed[#self.access.failed + 1] = file
                self:note(file .. " (Access) could not be opened, so its data was not brought across: " .. Vml("DbError"))
            else
                local wanted, tables, rows, left = {}, 0, 0, {}
                for _, t in ipairs(json.decode(Vml("DbTables", src, "tables")) or {}) do
                    if not t:match("^MSys") and not t:match("^~") then wanted[#wanted + 1] = t end
                end
                if #wanted > 0 then Vml("DbOpen", dst, "sqlite:" .. kit.join(self.folder, out)) end   -- (which makes the file)
                for _, t in ipairs(wanted) do
                    local n = tonumber(Vml("DbCopyTable", src, t, dst))
                    if n then tables = tables + 1; rows = rows + n else left[#left + 1] = t end
                end
                Vml("DbClose", src); Vml("DbClose", dst)
                if tables > 0 then
                    self.taken[out:lower()] = true
                    self.dbs[#self.dbs + 1] = { stem, "sqlite:" .. out }
                    self.db_files[#self.db_files + 1] = out
                    self.access.copied[#self.access.copied + 1] = file .. " into " .. out .. " (" .. kit.plural(tables, "table")
                        .. ", " .. kit.plural(rows, "row") .. ")"
                    self:note(file .. " (Access): " .. kit.plural(tables, "table") .. " and " .. kit.plural(rows, "row")
                        .. " copied into " .. out .. ", a SQLite database the project names as " .. stem .. ". The original is untouched. "
                        .. "Queries saved inside the Access file are not copied, and Access's SQL differs from SQLite's in places.")
                else
                    self.access.failed[#self.access.failed + 1] = file
                    self:note(file .. " (Access) was opened, but no tables could be copied from it.")
                end
                if #left > 0 then self:note("Not copied from " .. file .. ": " .. table.concat(left, ", ") .. ".") end
            end
        end
    end
    if #self.access.waiting > 0 then
        self:note("This project uses Access data (" .. table.concat(self.access.waiting, ", ") .. "), which was not brought "
            .. "across because this computer has no ODBC driver for Access. On Windows it comes with Access, or free as "
            .. "Microsoft's Access Database Engine; on Linux: sudo apt install odbc-mdbtools. Then import again and the "
            .. "tables are copied into a SQLite file the project carries with it.")
    end
end

function Project:finish(startup, source)
    if #self.forms == 0 then return json.encode({ error = "no forms were found in that project" }) end
    local start = startup and (startup .. ".vml") or ""
    if not kit.contains(self.forms, start) then
        start = self.forms[1]
        for _, f in ipairs(self.forms) do
            if f:lower():find("main", 1, true) then start = f break end
        end
    end
    local out = { "# Visualised project", "Name=" .. self.name, "Startup=" .. start }
    for _, f in ipairs(self.forms) do out[#out + 1] = "Form=" .. f end
    for _, m in ipairs(self.modules) do out[#out + 1] = "Module=" .. m end
    for _, d in ipairs(self.dbs) do out[#out + 1] = "Database=" .. d[1] .. "=" .. d[2] end
    local project = kit.join(self.folder, kit.safe_name(self.name) .. ".vmlproj")
    kit.write(project, table.concat(out, "\n") .. "\n")

    local t = self.totals
    local summary = { self.name .. ": " .. kit.plural(#self.forms, "form") .. " brought across, with " .. kit.plural(t.controls, "control")
        .. ", " .. kit.plural(t.menu_items, "menu item") .. " and " .. kit.plural(t.scripts, "event handler") .. ".",
        "Start-up form: " .. start .. "." }
    if (t.live or 0) > 0 then
        summary[#summary + 1] = kit.plural(t.live, "plain step") .. " of the code (opening and closing forms, messages, simple "
            .. "settings) " .. (t.live == 1 and "was" or "were") .. " translated and now run" .. (t.live == 1 and "s" or "") .. ". The rest of the code does not run: it is kept as comments to rewrite."
    end
    if #self.modules > 0 then
        summary[#summary + 1] = kit.plural(#self.modules, "module") .. " of original code, kept as comments for reference "
            .. "(the code does not run: it is there to rewrite)."
    end
    if t.pictures > 0 then summary[#summary + 1] = kit.plural(t.pictures, "picture") .. " saved in images/." end
    local access = self.access or { copied = {}, waiting = {}, failed = {} }
    if #access.copied > 0 then
        summary[#summary + 1] = "Access data copied into SQLite, which the project carries with it: " .. table.concat(access.copied, "; ") .. "."
    end
    if #access.waiting > 0 then
        summary[#summary + 1] = "Access data NOT brought across (" .. table.concat(access.waiting, ", ") .. "): this computer has no "
            .. "ODBC driver for Access. IMPORT-NOTES.txt says what to install; then import again."
    end
    if #(self.access_missing or {}) > 0 then
        summary[#summary + 1] = "The code uses Access data that isn't with the project (" .. table.concat(self.access_missing, ", ")
            .. "), so no data was brought for it. Put a copy beside the original project file and import again."
    end
    if #access.failed > 0 then
        summary[#summary + 1] = "Access data NOT brought across: " .. table.concat(access.failed, ", ") .. " (IMPORT-NOTES.txt says why)."
    end
    if #self.db_files > #access.copied then
        summary[#summary + 1] = "Databases named in the project: " .. table.concat(self.db_files, ", ") .. "."
    end
    summary[#summary + 1] = "The original project is untouched. IMPORT-NOTES.txt in the new folder lists every form's details."
    local notes_file = kit.join(self.folder, "IMPORT-NOTES.txt")
    local notes = { "Imported from " .. (source or ""), "" }
    for _, s in ipairs(summary) do notes[#notes + 1] = s end
    notes[#notes + 1] = ""
    for _, n in ipairs(self.project_notes or {}) do notes[#notes + 1] = n end
    if self.project_notes then notes[#notes + 1] = "" end
    for _, r in ipairs(self.report) do notes[#notes + 1] = r end
    kit.write(notes_file, table.concat(notes, "\n") .. "\n")
    return json.encode({ project = project, name = self.name, forms = self.forms, modules = self.modules,
        databases = self.db_files, pictures = t.pictures, controls = t.controls, scripts = t.scripts, startup = start,
        notes_file = notes_file, summary = table.concat(summary, "\n\n"),
        access = { copied = access.copied, waiting = access.waiting, failed = access.failed, missing = self.access_missing or {} } })
end

return kit
