-- Pat: the driver and the accountant. The window reads and writes the books (~/.vml/pat/pat.db, SQLite) itself;
-- tools/pat/pat.py does the talking to the platforms (posting, logging in, counting) and the first drafts.
-- A module of the Pat project: every script in Pat.vml can use what's here.

local json = require("dkjson")

Pat = { kinds = {}, post = nil, channel = nil, product = nil, busy = nil, products = {} }

local function set(n, p, v) Vml("SetProperty", n, p, v) end
local function get(n, p) return Vml("GetProperty", n, p) or "" end
local function say(t) set("StatusBar", "Text", t) end
local function trim(s) return ((s or ""):gsub("^%s+", ""):gsub("%s+$", "")) end
local function query(sql, ...) return json.decode(Vml("DbQuery", "pat", sql, ...) or "[]") or {} end
local function exec(sql, ...) return Vml("DbExecute", "pat", sql, ...) end
local function enable(names, on) for _, n in ipairs(names) do set(n, "IsEnabled", on and "true" or "false") end end

local function picked(grid)
  local row = json.decode(get(grid, "SelectedItem")) or {}
  return tonumber(row["#"])
end

-- where things are: the repo (PAT_REPO, else the pat_repo preference, else ~/projects/vml-github) and the books
function Pat.Repo()
  local pref = Vml("GetPreference", "pat_repo", "")
  local r = Vml("Shell", 'printf %s "${PAT_REPO:-' .. (pref ~= "" and pref or "$HOME/projects/vml-github") .. '}"')
  return trim(r)
end

function Pat.Cmd(what)
  return 'cd "' .. Pat.Repo() .. '" && python3 -u tools/pat/pat.py ' .. what
end

-- a quick one (drafting, the kinds): its JSON answer, or nil
local function now(what)
  return json.decode(trim(Vml("Shell", Pat.Cmd(what) .. " 2>/dev/null")))
end

-- a slow one (anything that goes out on the network): runs without holding up the window; then(answer) after
function Pat.Run(what, label, after)
  if Pat.busy then say("Still busy with " .. Pat.busy .. "…") return end
  Pat.busy, Pat.after = label, after
  set("txtOut", "Text", "")
  say(label .. "…")
  Vml("RunProcess", Pat.Cmd(what) .. " 2>&1", "txtOut", "PatDone")
end

function Pat.Done()
  local text, answer = get("txtOut", "Text"), nil
  for line in text:gmatch("[^\n]+") do
    local j = line:match("^%s*({.*})%s*$")
    if j then answer = json.decode(j) or answer end
  end
  local after = Pat.after
  Pat.busy, Pat.after = nil, nil
  if after then after(answer or { ok = false, said = trim(text) ~= "" and trim(text):sub(1, 300) or "Pat didn't answer." }) end
end

-- ── starting ─────────────────────────────────────────────────────────────────

function Pat.Opened()
  Pat.kinds = now("kinds") or {}                        -- (this also makes the books, the first time)
  if #Pat.kinds == 0 then
    say("Couldn't run tools/pat/pat.py in " .. Pat.Repo() .. ": set PAT_REPO, or the pat_repo preference, to the repo")
    return
  end
  local home = os.getenv("PAT_DB") or ((os.getenv("HOME") or os.getenv("USERPROFILE") or "~") .. "/.vml/pat/pat.db")
  if Vml("DbOpen", "pat", "sqlite:" .. home) ~= "true" then
    say("Couldn't open the books (" .. home .. "): " .. (Vml("DbError") or ""))
    return
  end
  local labels = {}
  for _, k in ipairs(Pat.kinds) do labels[#labels + 1] = k.label .. (k.assisted and " (you post)" or "") end
  set("cboKind", "Items", table.concat(labels, ","))
  Pat.Products()
  Pat.Channels()
  Pat.Posts()
  local n = query("SELECT COUNT(*) AS n FROM channels")[1]
  if n and tonumber(n.n) == 0 then
    set("tabs", "SelectedIndex", "3")
    Pat.Tab()
    say("Welcome. First, a product (what you're telling the world about), then your channels.")
  else
    say("Ready")
  end
end

function Pat.Tab()
  local i = tonumber(get("tabs", "SelectedIndex")) or 0
  if i == 0 then Pat.Posts() elseif i == 1 then Pat.Books() elseif i == 2 then Pat.Channels() else Pat.Products() end
end

-- ── posts: drafted, changed, approved, sent ──────────────────────────────────────

function Pat.Posts()
  local pid = Pat.CurrentProduct()
  Vml("DbShow", "grdPosts", "pat",
    "SELECT posts.id AS '#', channels.name AS Channel, posts.status AS Status, products.name AS Product, " ..
    "substr(replace(posts.text, char(10), ' '), 1, 70) AS Words FROM posts " ..
    "LEFT JOIN channels ON channels.id = posts.channel_id LEFT JOIN products ON products.id = posts.product_id " ..
    (pid and ("WHERE posts.product_id = " .. math.floor(pid) .. " ") or "") .. "ORDER BY posts.id DESC", "500")
  Pat.ShowPost(nil)
end

function Pat.CurrentProduct()
  local i = tonumber(get("cboProduct", "SelectedIndex")) or -1
  local p = Pat.products[i + 1]
  return p and tonumber(p.id) or nil
end

function Pat.ShowPost(id)
  local p = id and query("SELECT posts.*, channels.kind, channels.name AS channel FROM posts " ..
                         "LEFT JOIN channels ON channels.id = posts.channel_id WHERE posts.id = ?", id)[1]
  Pat.post = p
  Pat.showing = true
  set("txtTitle", "Text", p and (p.title or "") or "")
  set("txtText", "Text", p and (p.text or "") or "")
  Pat.showing = false
  local open = p and (p.status == "draft" or p.status == "approved" or p.status == "failed")
  enable({ "txtTitle", "txtText", "btnSave" }, open)
  enable({ "btnApprove" }, p and (p.status == "draft" or p.status == "failed"))
  enable({ "btnSend" }, p and p.status == "approved")
  enable({ "btnMark" }, p and (p.status == "assisted" or p.status == "approved"))
  enable({ "btnOpenPost", "btnRemovePost" }, p ~= nil)
  set("btnOpenPost", "Content", p and (p.url or "") ~= "" and "Open it" or "Open")
  if not p then
    set("lblPost", "Text", "Pick a post. Or pick a product, and Draft for every channel: one draft each, shaped for it, for you to change and approve.")
  elseif p.status == "posted" then
    set("lblPost", "Text", "Posted to " .. (p.channel or "?") .. ((p.url or "") ~= "" and (": " .. p.url) or "") .. ". Its numbers are on the Books tab.")
  elseif p.status == "failed" then
    set("lblPost", "Text", "Didn't go: " .. (p.error or "") .. "  (change it if need be, Approve, Send again)")
  elseif p.status == "assisted" then
    set("lblPost", "Text", "Waiting for you to post it on " .. (p.channel or "?") .. ", then Mark posted with its link.")
  elseif p.status == "approved" then
    set("lblPost", "Text", "Approved: Send puts it out on " .. (p.channel or "?") .. ".")
  else
    set("lblPost", "Text", "A draft for " .. (p.channel or "?") .. ": make it yours, then Approve.")
  end
  Pat.Count()
end

function Pat.Picked()
  Pat.ShowPost(picked("grdPosts"))
end

function Pat.Count()
  local p = Pat.post
  if not p then set("lblCount", "Text", "") return end
  local n = utf8 and utf8.len(get("txtText", "Text")) or #get("txtText", "Text")
  local limit = 0
  for _, k in ipairs(Pat.kinds) do if k.kind == p.kind then limit = tonumber(k.limit) or 0 end end
  set("lblCount", "Text", limit > 0 and (n .. " / " .. limit) or (n .. " characters"))
  set("lblCount", "Foreground", (limit > 0 and n > limit) and "#B91C1C" or "#6B7280")
end

function Pat.Typed()
  if not Pat.showing then Pat.Count() end
end

function Pat.Draft()
  local pid = Pat.CurrentProduct()
  if not pid then say("Pick a product first (the Products tab makes one).") return end
  local got = now("draft " .. math.floor(pid))
  if not got then say("Couldn't draft: is tools/pat/pat.py in " .. Pat.Repo() .. "?") return end
  Pat.Posts()
  say(got.made == 0 and "No channels switched on: the Channels tab." or
      (got.made .. " draft" .. (got.made == 1 and "" or "s") .. ": each one is yours to change, then Approve."))
end

local function save()
  local p = Pat.post
  if not p then return false end
  -- (changed words need approving again: what goes out is only ever what you said yes to)
  exec("UPDATE posts SET title = ?, text = ?, status = CASE WHEN status IN ('approved','failed') THEN 'draft' ELSE status END " ..
       "WHERE id = ? AND status IN ('draft','approved','failed')", get("txtTitle", "Text"), get("txtText", "Text"), p.id)
  return true
end

local function reshow(id)
  local keep = id
  Pat.Posts()
  Pat.ShowPost(keep)
end

function Pat.Save()
  if save() then reshow(Pat.post.id) say("Saved.") end
end

function Pat.Approve()
  if not save() then return end
  exec("UPDATE posts SET status = 'approved' WHERE id = ?", Pat.post.id)
  reshow(Pat.post.id)
  say("Approved. Send when you're ready.")
end

function Pat.Send()
  local p = Pat.post
  if not p or p.status ~= "approved" then return end
  local id = p.id
  Pat.Run("send " .. math.floor(tonumber(id)), "Sending to " .. (p.channel or "?"), function(a)
    if a.assisted then
      Vml("ClipboardSet", a.copy or "")
      if (a.open or "") ~= "" then Vml("OpenUrl", a.open) end
    elseif a.ok and (a.url or "") ~= "" then
      Vml("Notify", "Pat", a.said or "Posted")
    end
    reshow(id)
    say(a.said or (a.ok and "Done" or "Didn't go"))
  end)
end

function Pat.Mark()
  local p = Pat.post
  if not p then return end
  local url = trim(Vml("PromptDialog", "Mark posted", "Where is it? (its link, so Pat can find it again; blank will do)", ""))
  exec("UPDATE posts SET status = 'posted', posted = ?, url = ? WHERE id = ?", os.time(), url, p.id)
  reshow(p.id)
  say("Marked posted.")
end

function Pat.OpenPost()
  local p = Pat.post
  if not p then return end
  if (p.url or "") ~= "" then Vml("OpenUrl", p.url) return end
  Vml("ClipboardSet", ((p.title or "") ~= "" and (p.title .. "\n\n") or "") .. get("txtText", "Text"))
  say("Copied to the clipboard.")
end

function Pat.RemovePost()
  local p = Pat.post
  if not p then return end
  local sure = Vml("ChoiceDialog", "Remove this post from the books" .. (p.status == "posted" and
               " (and its numbers)? It stays wherever it was posted." or "?"), "Remove", "Remove|Cancel")
  if sure ~= "Remove" then return end
  exec("DELETE FROM stats WHERE post_id = ?", p.id)
  exec("DELETE FROM posts WHERE id = ?", p.id)
  Pat.Posts()
end

-- ── the books ────────────────────────────────────────────────────────────────

local LATEST = "(SELECT s.* FROM stats s JOIN (SELECT post_id, MAX(at) AS at FROM stats GROUP BY post_id) m " ..
               "ON m.post_id = s.post_id AND m.at = s.at)"

local function totals(grid, column, label)
  Vml("DbShow", grid, "pat",
    "SELECT " .. column .. " AS " .. label .. ", COUNT(*) AS Posts, SUM(COALESCE(l.likes, 0)) AS Likes, " ..
    "SUM(COALESCE(l.reposts, 0)) AS Shares, SUM(COALESCE(l.replies, 0)) AS Replies, SUM(COALESCE(l.views, 0)) AS Views " ..
    "FROM posts LEFT JOIN channels ON channels.id = posts.channel_id LEFT JOIN products ON products.id = posts.product_id " ..
    "LEFT JOIN " .. LATEST .. " l ON l.post_id = posts.id WHERE posts.status = 'posted' " ..
    "GROUP BY " .. column .. " ORDER BY Likes + 2 * Shares + 3 * Replies DESC", "100")
end

function Pat.Books()
  totals("grdByChannel", "channels.name", "Channel")
  totals("grdByProduct", "products.name", "Product")
  Vml("DbShow", "grdBooks", "pat",
    "SELECT posts.id AS '#', date(posts.posted, 'unixepoch', 'localtime') AS Posted, channels.name AS Channel, " ..
    "products.name AS Product, COALESCE(l.likes, 0) AS Likes, COALESCE(l.reposts, 0) AS Shares, " ..
    "COALESCE(l.replies, 0) AS Replies, COALESCE(l.views, 0) AS Views, posts.url AS Link FROM posts " ..
    "LEFT JOIN channels ON channels.id = posts.channel_id LEFT JOIN products ON products.id = posts.product_id " ..
    "LEFT JOIN " .. LATEST .. " l ON l.post_id = posts.id WHERE posts.status = 'posted' ORDER BY posts.posted DESC", "500")
  local last = query("SELECT MAX(at) AS at FROM stats")[1]
  set("lblBooks", "Text", (last and last.at) and ("Counted " .. os.date("%d %b, %H:%M", math.floor(tonumber(last.at)))) ..
      ". Pat counts what each platform will tell him; the ones you post yourself, he can't."
      or "Not counted yet: Count now asks each platform for its numbers.")
end

function Pat.CountNow()
  Pat.Run("stats", "Counting", function(a)
    Pat.Books()
    say(a.counted and ("Counted " .. a.counted .. " post" .. (a.counted == 1 and "" or "s") ..
        ((a.missed or 0) > 0 and (" (" .. a.missed .. " didn't answer)") or "")) or (a.said or "Couldn't count"))
  end)
end

function Pat.OpenBooked()
  local id = picked("grdBooks")
  local p = id and query("SELECT url FROM posts WHERE id = ?", id)[1]
  if p and (p.url or "") ~= "" then Vml("OpenUrl", p.url) end
end

-- ── channels ─────────────────────────────────────────────────────────────────

function Pat.Channels()
  Vml("DbShow", "grdChannels", "pat",
    "SELECT id AS '#', name AS Name, kind AS Kind, handle AS Who, CASE enabled WHEN 1 THEN 'on' ELSE 'off' END AS Drafts " ..
    "FROM channels ORDER BY name", "200")
  Pat.ShowChannel(nil)
end

local function kind_index(kind)
  for i, k in ipairs(Pat.kinds) do if k.kind == kind then return i end end
  return 0
end

function Pat.ShowChannel(id)
  local c = id and query("SELECT * FROM channels WHERE id = ?", id)[1]
  Pat.channel = c
  set("txtChName", "Text", c and c.name or "")
  set("txtHandle", "Text", c and c.handle or "")
  set("txtServer", "Text", c and c.server or "")
  set("txtSecret", "Text", "")
  set("txtSecret", "Watermark", c and (c.secret or "") ~= "" and "(kept: type a new one to change it)" or "Key, token or app password")
  set("chkOn", "IsChecked", (not c or tonumber(c.enabled) == 1) and "true" or "false")
  if c then set("cboKind", "SelectedIndex", tostring(kind_index(c.kind) - 1)) end
  enable({ "btnChTest", "btnChRemove" }, c ~= nil)
  set("btnChSave", "Content", c and "Save" or "Add")
  Pat.KindPicked()
end

function Pat.ChannelPicked()
  Pat.ShowChannel(picked("grdChannels"))
end

function Pat.NewChannel()
  set("grdChannels", "SelectedIndex", "-1")
  Pat.ShowChannel(nil)
  say("A new channel: pick its kind, fill in what it asks for, Add.")
end

function Pat.KindPicked()
  local k = Pat.kinds[(tonumber(get("cboKind", "SelectedIndex")) or -1) + 1]
  set("lblKindHelp", "Text", k and k.help or "Pick a kind of channel.")
  local has = {}
  for _, f in ipairs(k and k.fields or {}) do has[f] = true end
  set("txtServer", "IsEnabled", has.server and "true" or "false")
  set("txtSecret", "IsEnabled", has.secret and "true" or "false")
  set("txtServer", "Watermark", k and k.kind == "reddit" and "Subreddit (r/linux)" or "Server (mastodon.social)")
end

function Pat.SaveChannel()
  local k = Pat.kinds[(tonumber(get("cboKind", "SelectedIndex")) or -1) + 1]
  if not k then say("Pick a kind of channel first.") return end
  local name = trim(get("txtChName", "Text"))
  if name == "" then name = k.label end
  local handle, server, secret = trim(get("txtHandle", "Text")), trim(get("txtServer", "Text")), trim(get("txtSecret", "Text"))
  local on = get("chkOn", "IsChecked") == "true" and 1 or 0
  local id
  if Pat.channel then
    id = Pat.channel.id
    exec("UPDATE channels SET kind = ?, name = ?, handle = ?, server = ?, enabled = ? WHERE id = ?", k.kind, name, handle, server, on, id)
    if secret ~= "" then exec("UPDATE channels SET secret = ? WHERE id = ?", secret, id) end
  else
    exec("INSERT INTO channels (kind, name, handle, server, secret, enabled, created) VALUES (?, ?, ?, ?, ?, ?, ?)",
         k.kind, name, handle, server, secret, on, os.time())
    id = (query("SELECT MAX(id) AS id FROM channels")[1] or {}).id
  end
  Pat.Channels()
  Pat.ShowChannel(id)
  say(k.assisted and (name .. " saved. You post there yourself: Pat drafts it, opens the page and copies the words.")
      or (name .. " saved. Test it: Pat logs in and says who you are there."))
end

function Pat.TestChannel()
  local c = Pat.channel
  if not c then return end
  Pat.Run("channel-test " .. math.floor(tonumber(c.id)), "Testing " .. c.name, function(a)
    say((a.ok and "✓ " or "✗ ") .. (a.said or ""))
  end)
end

function Pat.RemoveChannel()
  local c = Pat.channel
  if not c then return end
  if Vml("ChoiceDialog", "Remove " .. c.name .. " (and its key)? Its posts stay in the books.", "Remove", "Remove|Cancel") ~= "Remove" then return end
  exec("DELETE FROM channels WHERE id = ?", c.id)
  Pat.Channels()
end

-- ── products ─────────────────────────────────────────────────────────────────

function Pat.Products()
  Pat.products = query("SELECT id, name FROM products ORDER BY name")
  local names = {}
  for _, p in ipairs(Pat.products) do names[#names + 1] = (p.name:gsub(",", " ")) end
  set("cboProduct", "Items", table.concat(names, ","))
  if #names > 0 and (tonumber(get("cboProduct", "SelectedIndex")) or -1) < 0 then set("cboProduct", "SelectedIndex", "0") end
  Vml("DbShow", "grdProducts", "pat", "SELECT id AS '#', name AS Name, headline AS Headline, link AS Link FROM products ORDER BY name", "200")
  Pat.ShowProduct(nil)
end

function Pat.ShowProduct(id)
  local p = id and query("SELECT * FROM products WHERE id = ?", id)[1]
  Pat.product = p
  set("txtPName", "Text", p and p.name or "")
  set("txtLink", "Text", p and p.link or "")
  set("txtHeadline", "Text", p and p.headline or "")
  set("txtDesc", "Text", p and p.description or "")
  set("txtTags", "Text", p and p.tags or "")
  enable({ "btnPRemove" }, p ~= nil)
  set("btnPSave", "Content", p and "Save" or "Add")
end

function Pat.ProductPicked()
  Pat.ShowProduct(picked("grdProducts"))
end

function Pat.NewProduct()
  set("grdProducts", "SelectedIndex", "-1")
  Pat.ShowProduct(nil)
end

function Pat.SaveProduct()
  local f = { trim(get("txtPName", "Text")), trim(get("txtLink", "Text")), trim(get("txtHeadline", "Text")),
              trim(get("txtDesc", "Text")), trim(get("txtTags", "Text")) }
  if f[1] == "" then say("A product needs a name.") return end
  local id
  if Pat.product then
    id = Pat.product.id
    exec("UPDATE products SET name = ?, link = ?, headline = ?, description = ?, tags = ? WHERE id = ?", f[1], f[2], f[3], f[4], f[5], id)
  else
    exec("INSERT INTO products (name, link, headline, description, tags, created) VALUES (?, ?, ?, ?, ?, ?)",
         f[1], f[2], f[3], f[4], f[5], os.time())
    id = (query("SELECT MAX(id) AS id FROM products")[1] or {}).id
  end
  Pat.Products()
  Pat.ShowProduct(id)
  local chans = tonumber((query("SELECT COUNT(*) AS n FROM channels")[1] or {}).n) or 0
  say(f[1] .. " saved." .. (chans == 0 and " Next, your channels (the Channels tab)." or " On the Posts tab: Draft for every channel."))
end

function Pat.RemoveProduct()
  local p = Pat.product
  if not p then return end
  if Vml("ChoiceDialog", "Remove " .. p.name .. "? Its posts stay in the books.", "Remove", "Remove|Cancel") ~= "Remove" then return end
  exec("DELETE FROM products WHERE id = ?", p.id)
  Pat.Products()
end
