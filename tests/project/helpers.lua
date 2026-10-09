-- helpers: functions every form in Demo can use

loads = (loads or 0) + 1          -- counts how often this module was loaded into a form's Lua

function Shout(text)
    return string.upper(text) .. "!"
end

function Stock(item)
    -- the project's database, by the name the project gives it
    local rows = require("dkjson").decode(Vml("DbQuery", "stock", "SELECT qty FROM stock WHERE item = ?", item))
    return rows[1] and rows[1].qty or 0
end
