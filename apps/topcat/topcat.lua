-- TopCat: this machine's side. The agent (tools/topcat/agent.py, a background service) answers TopCat's hub with
-- this machine's apps; this window shows it working: on or off, who asked what, and a build's lines as they come.
-- A module of the TopCat project: every script in TopCat.vml can use what's here.

local json = require("dkjson")

TopCat = { rows = {}, size = -1, job = nil, on = nil }

local function set(n, p, v) Vml("SetProperty", n, p, v) end
local function get(n, p) return Vml("GetProperty", n, p) or "" end
local function trim(s) return ((s or ""):gsub("^%s+", ""):gsub("%s+$", "")) end
local function sh(cmd) return Vml("Shell", cmd) or "" end
local function cell(s) return (tostring(s or ""):gsub("[|;\n]", " ")) end
local HOME = os.getenv("HOME") or "~"
local CACHE = HOME .. "/.cache/topcat"

function TopCat.Repo()
  local pref = Vml("GetPreference", "topcat_repo", "")
  return trim(sh('printf %s "${TOPCAT_REPO:-' .. (pref ~= "" and pref or "$HOME/projects/vml-github") .. '}"'))
end

function TopCat.Opened()
  local conf = json.decode(sh("cat ~/.config/topcat/agent.json 2>/dev/null")) or {}
  local lv = ({ look = 0, ["do"] = 1, ask = 2 })[conf.level or "ask"] or 2
  TopCat.level = ({ "look", "do", "ask" })[lv + 1]
  TopCat.ShowLevel()
  if not conf.token then
    set("lblState", "Text", "Not set up on this machine yet: tools/topcat/agent.py has the steps.")
  end
  set("chkBoot", "IsChecked", Vml("GetSetting", "at_boot") == "on" and "true" or "false")
  local boot = trim(sh("cat /proc/sys/kernel/random/boot_id 2>/dev/null"))
  TopCat.shell = (conf.shell == true or conf.shell == "always") and "always" or
                 ((conf.shell == "session" and conf.boot == boot) and "session" or "off")
  TopCat.ShowShell()
  if conf.token and trim(sh("systemctl --user is-active topcat-agent 2>/dev/null")) ~= "active" then
    sh("systemctl --user enable --now topcat-agent 2>&1")     -- (opening TopCat lets it in; untick to shut it out)
  end
  TopCat.Tick()
  set("tmr", "IsEnabled", "true")
  if Vml("LaunchedAtBoot") == "true" and TopCat.inTray then Vml("HideForm", "TopCat") end
end

-- the tray: the hat, with the switch and the level on its menu
local LEVELS = { { "look", "look" }, { "do", "look and do" }, { "ask", "do and ask" } }
function TopCat.TrayUpdate()
  local levels = {}
  for _, l in ipairs(LEVELS) do levels[#levels + 1] = (TopCat.level == l[1] and "✓ " or "    ") .. l[2] end
  local menu = { "Open TopCat", "-", (TopCat.on and "✓ " or "    ") .. "Let TopCat in",
                 "Callers may>" .. table.concat(levels, ";"), "-", "Exit" }
  local tip = TopCat.on and ("TopCat: on" .. (TopCat.machine and (", " .. TopCat.machine) or "")) or "TopCat: off"
  TopCat.inTray = (Vml("Tray", tip, table.concat(menu, "|"), "TopCatTray") or "") == ""
end

function TopCat.Tray(args)
  local what = (args or {})[1] or ""
  if what == "open" or what == "Open TopCat" then
    Vml("ShowForm", "TopCat")
  elseif what == "Exit" then
    Vml("Quit")
  elseif what:find("Let TopCat in", 1, true) then
    set("chkOn", "IsChecked", TopCat.on and "false" or "true")
    TopCat.Toggle()
  elseif what:sub(1, 12) == "Callers may>" then
    for i, l in ipairs(LEVELS) do
      if what:match(l[2] .. "%s*$") then
        TopCat.level = l[1]
        TopCat.Level()
      end
    end
  end
end

function TopCat.Boot()
  local on = get("chkBoot", "IsChecked") == "true"
  local now = Vml("StartAtBoot", tostring(on))
  if now == "on" or now == "off" then Vml("SetSetting", "at_boot", now) else set("StatusBar", "Text", now) end
end

-- every second and a half: on or off, anything new, the followed job's lines
function TopCat.Tick()
  local raw = sh('cd ' .. CACHE .. ' 2>/dev/null; printf \'{"state":%s,"active":"%s","size":%s}\' ' ..
                 '"$(cat state.json 2>/dev/null || echo null)" "$(systemctl --user is-active topcat-agent 2>/dev/null)" ' ..
                 '"$(stat -c %s log.jsonl 2>/dev/null || echo 0)"')
  local s = json.decode(raw) or {}
  local st = type(s.state) == "table" and s.state or {}
  local running = s.active == "active"
  local fresh = st.at and (os.time() - math.floor(st.at)) < 60
  local on = running and fresh and st.on
  TopCat.machine = st.machine
  if TopCat.on ~= running then
    TopCat.on = running
    TopCat.TrayUpdate()
    TopCat.quiet = true
    set("chkOn", "IsChecked", running and "true" or "false")
    TopCat.quiet = false
  end
  set("dot", "Background", on and "#16A34A" or (running and "#F59E0B" or "#9CA3AF"))
  if on then
    set("lblState", "Text", "Connected as " .. (st.machine or "?") .. " to " .. ((st.hub or ""):match("//([^/]+)") or "the hub"))
  elseif running then
    set("lblState", "Text", "Trying to reach the hub" .. ((st.why or "") ~= "" and (": " .. st.why) or "…"))
  else
    set("lblState", "Text", "Off: nobody can ask this machine anything.")
  end
  local size = tonumber(s.size) or 0
  if size ~= TopCat.size then
    TopCat.size = size
    TopCat.Log()
  end
end

function TopCat.Log()
  local rows, items = {}, {}
  for line in sh("tail -n 80 " .. CACHE .. "/log.jsonl 2>/dev/null"):gmatch("[^\n]+") do
    local r = json.decode(line)
    if r then table.insert(rows, 1, r) end
  end
  for _, r in ipairs(rows) do
    local args = {}
    for k, v in pairs(r.args or {}) do args[#args + 1] = k .. "=" .. tostring(v) end
    items[#items + 1] = table.concat({ cell(os.date("%H:%M:%S", math.floor(r.at or 0))), cell(r.caller),
      cell(r.app .. " " .. r.command .. (#args > 0 and (" " .. table.concat(args, " ")) or "")), cell(r.level), cell(r.said) }, "|")
  end
  local first = #TopCat.rows == 0
  local news = rows[1] and (not TopCat.rows[1] or rows[1].id ~= TopCat.rows[1].id)
  TopCat.rows = rows
  set("grdLog", "Items", table.concat(items, ";"))
  if news and not first then
    local r = rows[1]
    set("StatusBar", "Text", (r.caller ~= "" and r.caller or "Someone") .. " asked " .. r.app .. " " .. r.command .. ": " .. (r.said or ""))
    if r.job then TopCat.Watch(r.job) end                 -- (a build just started: show it as it goes)
  end
end

function TopCat.Picked()
  local r = TopCat.rows[(tonumber(get("grdLog", "SelectedIndex")) or -1) + 1]
  if r and r.job then TopCat.Watch(r.job) end
end

function TopCat.Watch(job)
  local id = tostring(job):gsub("[^%w%-]", "")
  if TopCat.proc then Vml("CancelProcess", TopCat.proc) end
  TopCat.job = id
  set("lstJob", "Items", "")
  set("lblJob", "Text", "Job " .. id .. ": going…")
  set("lblJob", "Foreground", "#B45309")
  local f = HOME .. "/.cache/vml/jobs/" .. id
  -- its lines as they come, until it ends (then a second more, for the last of them)
  TopCat.proc = Vml("RunProcess", "tail -n 300 -F " .. f .. ".log 2>/dev/null & T=$!; while [ ! -e " .. f ..
                    ".exit ]; do sleep 1; done; sleep 1; kill $T", "lstJob", "TopCatJobDone")
end

function TopCat.JobDone()
  local id = TopCat.job
  if not id then return end
  local code = trim(sh("cat " .. HOME .. "/.cache/vml/jobs/" .. id .. ".exit 2>/dev/null"))
  if code == "" then return end                         -- (stopped by picking another one)
  set("lblJob", "Text", "Job " .. id .. ": " .. (code == "0" and "finished, all good" or ("ended badly (exit " .. code .. ")")))
  set("lblJob", "Foreground", code == "0" and "#16A34A" or "#B91C1C")
  TopCat.proc = nil
end

function TopCat.Toggle()
  if TopCat.quiet then return end
  local want = get("chkOn", "IsChecked") == "true"
  sh("systemctl --user " .. (want and "enable --now" or "disable --now") .. " topcat-agent 2>&1")
  set("StatusBar", "Text", want and "Letting TopCat in: the agent is starting." or "Shut out: the agent is stopped, and won't start at login.")
  TopCat.on = nil
  TopCat.Tick()
end

-- the shell: off unless you say (for this session, or always); even then, each command needs your yes
-- one colour per how much is allowed, the same on both buttons: green the least, amber more, red the most
local GREEN, AMBER, RED = "#16A34A", "#D97706", "#DC2626"
local SHELL_LOOK = { off = { "Shell: off", GREEN }, session = { "Shell: this session", AMBER },
                     always = { "Shell: always on", RED } }
local LEVEL_LOOK = { look = { "Callers: look", GREEN }, ["do"] = { "Callers: look and do", AMBER },
                     ask = { "Callers: do and ask", RED } }
local function paint(btn, s)
  set(btn, "Content", s[1])
  set(btn, "Background", s[2])
  set(btn .. "Arrow", "Background", s[2])
end
function TopCat.ShowLevel() paint("btnLevel", LEVEL_LOOK[TopCat.level or "ask"]) end

function TopCat.LevelNext()
  TopCat.level = ({ look = "do", ["do"] = "ask", ask = "look" })[TopCat.level or "ask"]
  TopCat.Level()
end
function TopCat.ShowShell() paint("btnShell", SHELL_LOOK[TopCat.shell or "off"]) end

function TopCat.Shell()
  TopCat.shell = ({ off = "session", session = "always", always = "off" })[TopCat.shell or "off"]
  local value = ({ off = "false", session = '"session"', always = '"always"' })[TopCat.shell]
  local boot = trim(sh("cat /proc/sys/kernel/random/boot_id 2>/dev/null"))
  local f = HOME .. "/.config/topcat/agent.json"
  sh("python3 -c 'import json,sys;p=sys.argv[1];c=json.load(open(p));c[\"shell\"]=json.loads(sys.argv[2]);c[\"boot\"]=sys.argv[3];json.dump(c,open(p,\"w\"))' " ..
     f .. " '" .. value .. "' '" .. boot .. "' 2>/dev/null && systemctl --user is-active -q topcat-agent && systemctl --user restart topcat-agent")
  TopCat.ShowShell()
  set("StatusBar", "Text", ({ off = "No shell: callers can only ask this machine's apps.",
    session = "Shell on until this computer restarts: each command still needs your yes.",
    always = "Shell always on: each command still needs your yes. Click again to turn it off." })[TopCat.shell])
end

function TopCat.Level()
  local lv = TopCat.level or "ask"
  TopCat.ShowLevel()
  TopCat.TrayUpdate()
  local f = HOME .. "/.config/topcat/agent.json"
  sh("python3 -c 'import json,sys;p=sys.argv[1];c=json.load(open(p));c[\"level\"]=sys.argv[2];json.dump(c,open(p,\"w\"))' " ..
     f .. " " .. lv .. " 2>/dev/null && systemctl --user is-active -q topcat-agent && systemctl --user restart topcat-agent")
  set("StatusBar", "Text", ({ look = "Look only: callers can read, never change anything.",
    ["do"] = "Look and do: callers can change things here, but nothing that goes out or can't be undone.",
    ask = "Everything, but anything that goes out or can't be undone needs your yes, each time." })[lv])
end
