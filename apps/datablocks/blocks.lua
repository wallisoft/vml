-- blocks: the data blocks themselves. Every form in the project can call these.
--
-- A data block is one row of up to five pieces of text, filed under a tag. Each tag names its own fields, so
-- "Findings" has Room, Finding and Advice where "Sign-offs" has Name and Text. Forms then look blocks up with
-- ordinary queries (see report.vml's ItemsSource lines): no code is needed to make one list narrow another.

local json = require("dkjson")
Blocks = Blocks or {}
local DB = "blocks"                     -- the database the project names (DataBlocks.vmlproj)

local function rows(sql, ...)
    return json.decode(Vml("DbQuery", DB, sql, ...)) or {}
end

-- Make the tables the first time, with a little content to try things on.
function Blocks.setup()
    Vml("DbExecute", DB, "CREATE TABLE IF NOT EXISTS tags (tag TEXT PRIMARY KEY, f1 TEXT, f2 TEXT, f3 TEXT, f4 TEXT, f5 TEXT)")
    Vml("DbExecute", DB, "CREATE TABLE IF NOT EXISTS blocks (id INTEGER PRIMARY KEY, tag TEXT, f1 TEXT, f2 TEXT, f3 TEXT, f4 TEXT, f5 TEXT)")
    if #rows("SELECT tag FROM tags LIMIT 1") > 0 then return end
    Blocks.add_tag("Findings", {"Room", "Finding", "Advice"})
    Blocks.add_tag("Sign-offs", {"Name", "Text"})
    local findings = {
        {"Bathroom", "The sealant round the bath has failed", "Rake it out and reseal with sanitary silicone."},
        {"Bathroom", "The sealant round the bath has failed", "Check the bath is supported along its length before resealing."},
        {"Bathroom", "The extractor fan is not clearing steam", "Fit a fan with a run-on timer, ducted outside."},
        {"Bathroom", "Tiles are loose behind the basin", "Lift them, check the wall is dry, and refix with flexible adhesive."},
        {"Kitchen", "The worktop joint has swollen", "Replace that length of worktop and seal the new joint."},
        {"Kitchen", "The tap drips when closed", "Replace the ceramic cartridges."},
        {"Kitchen", "No isolating valve under the sink", "Fit isolating valves to the hot and cold supplies."},
        {"Hall", "The radiator is cold at the top", "Bleed it, then check the system pressure."},
    }
    for _, f in ipairs(findings) do Blocks.save("Findings", "", f) end
    Blocks.save("Sign-offs", "", {"Standard", "Surveyed by eye only. No floors were lifted and no fittings were removed."})
    Blocks.save("Sign-offs", "", {"Follow-up", "A second visit is advised once the work above is done."})
end

-- The names a tag gives its fields, in order.
function Blocks.fields(tag)
    local r = rows("SELECT f1, f2, f3, f4, f5 FROM tags WHERE tag = ?", tag)[1] or {}
    local out = {}
    for i = 1, 5 do
        local name = r["f" .. i]
        if name and name ~= "" then out[#out + 1] = name end
    end
    return out
end

function Blocks.add_tag(tag, names)
    Vml("DbExecute", DB, "INSERT OR REPLACE INTO tags (tag, f1, f2, f3, f4, f5) VALUES (?, ?, ?, ?, ?, ?)",
        tag, names[1] or "", names[2] or "", names[3] or "", names[4] or "", names[5] or "")
end

-- A tag's blocks as JSON for a grid: one object per block, its values under the tag's own field names.
function Blocks.rows(tag)
    local names, out = Blocks.fields(tag), {}
    for _, r in ipairs(rows("SELECT id, f1, f2, f3, f4, f5 FROM blocks WHERE tag = ? ORDER BY f1, f2, id", tag)) do
        local parts = {'"id": ' .. json.encode(r.id)}          -- written by hand so the columns keep their order
        for i, name in ipairs(names) do parts[#parts + 1] = json.encode(name) .. ": " .. json.encode(r["f" .. i] or "") end
        out[#out + 1] = "{" .. table.concat(parts, ", ") .. "}"
    end
    return "[" .. table.concat(out, ", ") .. "]"
end

-- One block's values, in field order.
function Blocks.get(id)
    local r = rows("SELECT f1, f2, f3, f4, f5 FROM blocks WHERE id = ?", id)[1] or {}
    return {r.f1 or "", r.f2 or "", r.f3 or "", r.f4 or "", r.f5 or ""}
end

-- Save a block: a new one if id is "", otherwise that one.
function Blocks.save(tag, id, v)
    if id == nil or id == "" then
        Vml("DbExecute", DB, "INSERT INTO blocks (tag, f1, f2, f3, f4, f5) VALUES (?, ?, ?, ?, ?, ?)",
            tag, v[1] or "", v[2] or "", v[3] or "", v[4] or "", v[5] or "")
    else
        Vml("DbExecute", DB, "UPDATE blocks SET f1 = ?, f2 = ?, f3 = ?, f4 = ?, f5 = ? WHERE id = ?",
            v[1] or "", v[2] or "", v[3] or "", v[4] or "", v[5] or "", id)
    end
end

function Blocks.delete(id)
    Vml("DbExecute", DB, "DELETE FROM blocks WHERE id = ?", id)
end
