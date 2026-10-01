#!/usr/bin/env lua
-- VML Parser v3.0 - Complete Lua implementation
-- Features: Heredoc, @Include, @Variables, @ForEach, @If, @Ignore, @Debug
-- Usage: lua vml-parser.lua input.vml > output.sql
--        lua vml-parser.lua --export db.db form_name > output.vml

-- ============================================================================
-- EXPORT MODE (DB → VML)
-- ============================================================================
if arg[1] == "--export" then
    if #arg < 3 then
        io.stderr:write("Usage: vml-parser.lua --export <db-file> <form-name> > output.vml\n")
        os.exit(1)
    end
    
    local db_file = arg[2]
    local form_name = arg[3]
    
    -- Use sqlite3 to export
    local cmd = string.format("sqlite3 -separator '|' '%s' \"SELECT control_type, name FROM ui_tree WHERE source_file LIKE '%%%s%%' ORDER BY display_order;\"", db_file, form_name)
    local handle = io.popen(cmd)
    
    print("# Exported VML from " .. form_name)
    print("")
    
    for line in handle:lines() do
        local ctype, cname = line:match("([^|]+)|([^|]+)")
        print("@" .. ctype .. " " .. cname)
        
        -- Get properties
        local prop_cmd = string.format("sqlite3 -separator '|' '%s' \"SELECT property_name, property_value FROM ui_properties up JOIN ui_tree ut ON up.ui_tree_id = ut.id WHERE ut.name='%s' AND ut.source_file LIKE '%%%s%%';\"", db_file, cname, form_name)
        local prop_handle = io.popen(prop_cmd)
        
        for prop_line in prop_handle:lines() do
            local pname, pvalue = prop_line:match("([^|]+)|([^|]*)")
            print(pname .. "=" .. pvalue)
        end
        prop_handle:close()
        print("")
    end
    handle:close()
    
    os.exit(0)
end

-- ============================================================================
-- IMPORT MODE (VML → SQL)
-- ============================================================================

if #arg < 1 then
    io.stderr:write("Usage: vml-parser.lua <input.vml> > output.sql\n")
    io.stderr:write("       vml-parser.lua --export <db> <form> > output.vml\n")
    os.exit(1)
end

local source_file = arg[1]
local timestamp = os.time()
local debug_mode = false

-- State
local control_id = 1
local display_order = 1
local variables = {}
local ignore_mode = false
local debug_section = false
local in_heredoc = false
local heredoc_term = nil
local in_script = false
local script_content = ""
local foreach_active = false
local foreach_items = {}
local foreach_template = {}
local if_condition = nil

-- Control storage
local controls = {}
local current_control = nil

-- ============================================================================
-- HELPER FUNCTIONS
-- ============================================================================

local function expand_variables(text)
    return text:gsub("%${([%w_]+)}", function(name)
        return variables[name] or ("${" .. name .. "}")
    end)
end

local function sql_escape(str)
    return str:gsub("'", "''")
end

local function parse_line(line, line_num)
    -- Heredoc terminator check
    if in_heredoc and line == heredoc_term then
        in_heredoc = false
        in_script = false
        if current_control then
            current_control.properties.Content = script_content
        end
        script_content = ""
        if debug_section then
            io.stderr:write(string.format("[%03d] HEREDOC END\n", line_num))
        end
        return
    end
    
    -- Inside heredoc - capture everything
    if in_heredoc then
        script_content = script_content .. line .. "\n"
        return
    end
    
    -- Heredoc start
    local hd_term = line:match("^<<([A-Za-z_][A-Za-z0-9_]*)$")
    if hd_term then
        in_heredoc = true
        heredoc_term = hd_term
        if debug_section then
            io.stderr:write(string.format("[%03d] HEREDOC START (%s)\n", line_num, hd_term))
        end
        return
    end
    
    -- Debug control
    if line == "@DEBUG" then
        debug_section = true
        io.stderr:write(string.format("\n=== DEBUG SECTION START (line %d) ===\n", line_num))
        return
    end
    if line == "@DEBUG-END" then
        io.stderr:write(string.format("=== DEBUG SECTION END (line %d) ===\n\n", line_num))
        debug_section = false
        return
    end
    
    -- Ignore control
    if line == "@IGNORE-START" then
        ignore_mode = true
        if debug_section then io.stderr:write(string.format("[%03d] IGNORE START\n", line_num)) end
        return
    end
    if line == "@IGNORE-END" then
        ignore_mode = false
        if debug_section then io.stderr:write(string.format("[%03d] IGNORE END\n", line_num)) end
        return
    end
    
    if ignore_mode then return end
    
    -- Skip comments and blank lines
    if line:match("^%s*#") or line:match("^%s*$") then
        if in_script and not line:match("^%s*$") then
            script_content = script_content .. line .. "\n"
        end
        return
    end
    
    -- Variables block
    if line == "@Variables" then
        if debug_section then io.stderr:write(string.format("[%03d] VARIABLES BLOCK\n", line_num)) end
        return
    end
    
    -- Include directive
    local include_path = line:match("^@Include%s+(.+)")
    if include_path then
        include_path = expand_variables(include_path)
        if debug_section then io.stderr:write(string.format("[%03d] INCLUDE: %s\n", line_num, include_path)) end
        parse_file(include_path)
        return
    end
    
    -- ForEach directive
    local foreach_items_str = line:match("^@ForEach%s+items=(.+)")
    if foreach_items_str then
        foreach_items_str = expand_variables(foreach_items_str)
        foreach_items = {}
        for item in foreach_items_str:gmatch("[^,]+") do
            table.insert(foreach_items, item:match("^%s*(.-)%s*$"))
        end
        foreach_active = true
        foreach_template = {}
        if debug_section then io.stderr:write(string.format("[%03d] FOREACH: %d items\n", line_num, #foreach_items)) end
        return
    end
    
    -- If directive
    local if_var = line:match("^@If%s+(.+)")
    if if_var then
        if_var = expand_variables(if_var)
        if_condition = (variables[if_var] == "true" or variables[if_var] == "1")
        if debug_section then io.stderr:write(string.format("[%03d] IF: %s = %s\n", line_num, if_var, tostring(if_condition))) end
        return
    end
    
    if line == "@EndIf" then
        if_condition = nil
        return
    end
    
    if line == "@EndForEach" then
        -- Expand foreach template for each item
        for _, item in ipairs(foreach_items) do
            local saved_item = variables["item"]
            variables["item"] = item
            
            for _, template_line in ipairs(foreach_template) do
                local expanded = expand_variables(template_line)
                parse_line(expanded, line_num)
            end
            
            variables["item"] = saved_item
        end
        
        foreach_active = false
        foreach_template = {}
        foreach_items = {}
        return
    end
    
    -- If we're in foreach, capture template
    if foreach_active and not line:match("^@EndForEach") then
        table.insert(foreach_template, line)
        return
    end
    
    -- If we're in a false if block, skip
    if if_condition == false then
        return
    end
    
    -- Control declaration (@Type Name)
    -- local ctype, cname = line:match("^@([A-Za-z_][A-Za-z0-9_]*)%s*([A-Za-z0-9_]*)")
    local ctype, cname = line:match("^@(%S+)%s*(%S*)")
    if ctype then
        -- Finalize previous script if any
        if in_script and script_content ~= "" and current_control then
            current_control.properties.Content = script_content
            script_content = ""
        end
        in_script = false
        
        -- Expand variables in name
        if cname == "" then cname = ctype .. "_" .. control_id end
        cname = expand_variables(cname)
        ctype = expand_variables(ctype)
        
        -- Create control
        current_control = {
            id = control_id,
            type = ctype,
            name = cname,
            properties = {},
            display_order = display_order
        }
        
        table.insert(controls, current_control)
        
        -- Enter script mode for @Script
        if ctype == "Script" then
            in_script = true
        end
        
        control_id = control_id + 1
        display_order = display_order + 1
        
        if debug_section then
            io.stderr:write(string.format("[%03d] CONTROL: #%d %s \"%s\"\n", line_num, current_control.id, ctype, cname))
        end
        return
    end
    
    -- Property (key=value)
    local pname, pvalue = line:match("^([A-Za-z_][A-Za-z0-9_.]+)=(.*)$")
    if pname and current_control then
        pvalue = expand_variables(pvalue)
        
        -- In script mode, treat = as content EXCEPT Interpreter/Instance
        if in_script and pname ~= "Interpreter" and pname ~= "Instance" and pname ~= "Description" then
            script_content = script_content .. line .. "\n"
            return
        end
        
        -- Store variable
        if variables.__in_variables_block then
            variables[pname] = pvalue
            if debug_section then io.stderr:write(string.format("[%03d] VAR: %s=%s\n", line_num, pname, pvalue)) end
            return
        end
        
        current_control.properties[pname] = pvalue
        
        if debug_section then
            io.stderr:write(string.format("[%03d] PROP: %s=%s\n", line_num, pname, pvalue:sub(1,30)))
        end
        return
    end
    
    -- Other lines in script mode
    if in_script then
        script_content = script_content .. line .. "\n"
    end
end

function parse_file(filepath)
    local file = io.open(filepath, "r")
    if not file then
        io.stderr:write("Error: Cannot open " .. filepath .. "\n")
        return
    end
    
    local line_num = 0
    for line in file:lines() do
        line_num = line_num + 1
        line = line:match("^%s*(.-)%s*$")  -- Trim
        parse_line(line, line_num)
    end
    
    -- Finalize last script
    if in_script and script_content ~= "" and current_control then
        current_control.properties.Content = script_content
    end
    
    file:close()
end

-- ============================================================================
-- MAIN EXECUTION
-- ============================================================================

io.stderr:write("VML Parser v3.0 - Parsing " .. source_file .. "\n")

-- Mark that we're not in variables block initially
variables.__in_variables_block = false

parse_file(source_file)

io.stderr:write(string.format("✓ Parsed %d controls\n", #controls))

-- ============================================================================
-- SQL GENERATION
-- ============================================================================

io.stderr:write("Generating SQL...\n")

-- DEBUG: Print all controls
io.stderr:write("DEBUG: Controls in array:\n")
for i, ctrl in ipairs(controls) do
    io.stderr:write(string.format("  %d. %s (%s)\n", i, ctrl.name, ctrl.type))
end


for _, ctrl in ipairs(controls) do
    -- Handle @Script specially
    if ctrl.type == "Script" then
        local interp = ctrl.properties.Interpreter or "bash"
        local inst = ctrl.properties.Instance or ""
        local cont = ctrl.properties.Content or ""
        
        print(string.format(
            "INSERT OR REPLACE INTO scripts (name,interpreter,instance,content,source_file,created_at) VALUES ('%s','%s','%s','%s','%s',%d);",
            sql_escape(ctrl.name),
            sql_escape(interp),
            sql_escape(inst),
            sql_escape(cont),
            sql_escape(source_file),
            timestamp
        ))
    else
        -- Regular controls
        local parent_ref = ctrl.properties.Parent
        local parent_sql = "NULL"
        local is_root = 1

        if parent_ref and parent_ref ~= "" then
            -- Check if parent exists in our controls list
            local parent_exists = false
            for _, other_ctrl in ipairs(controls) do
                if other_ctrl.name == parent_ref and other_ctrl.id < ctrl.id then
                    parent_exists = true
                    break
                end
            end

            if parent_exists then
                parent_sql = string.format("(SELECT id FROM ui_tree WHERE name='%s' AND source_file='%s' ORDER BY id DESC LIMIT 1)", sql_escape(parent_ref), sql_escape(source_file))
                is_root = 0
            end
            -- If parent doesn't exist, leave as root (NULL parent)
        end

        print(string.format(
            "INSERT INTO ui_tree (parent_id,control_type,name,display_order,is_root,source_file,imported_at) VALUES (%s,'%s','%s',%d,%d,'%s',%d);",
            parent_sql,
            sql_escape(ctrl.type),
            sql_escape(ctrl.name),
            ctrl.display_order,
            is_root,
            sql_escape(source_file),
            timestamp
        ))
        
        -- Properties
        for pname, pvalue in pairs(ctrl.properties) do
            if pname ~= "Parent" and pname ~= "Interpreter" and not (pname == "Content" and ctrl.type == "Script") then
                print(string.format(
                    "INSERT INTO ui_properties (ui_tree_id,property_name,property_value) VALUES ((SELECT id FROM ui_tree WHERE name='%s' AND source_file='%s' ORDER BY id DESC LIMIT 1),'%s','%s');",
                    sql_escape(ctrl.name),
                    sql_escape(source_file),
                    sql_escape(pname),
                    sql_escape(pvalue)
                ))
            end
        end
    end
end

io.stderr:write("✓ Conversion complete\n")
