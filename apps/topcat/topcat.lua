-- TopCat: this machine's side. The agent (tools/topcat/agent.py, a background service) answers TopCat's hub with
-- this machine's apps; this window shows it working: on or off, who asked what, and a build's lines as they come.
-- A module of the TopCat project: every script in TopCat.vml can use what's here.

local json = require("dkjson")

TopCat = { rows = {}, size = -1, job = nil, on = nil }

local function set(n, p, v) Vml("SetProperty", n, p, v) end
local function get(n, p) return Vml("GetProperty", n, p) or "" end
local function trim(s) return ((s or ""):gsub("^%s+", ""):gsub("%s+$", "")) end
local function cell(s) return (tostring(s or ""):gsub("[|;\n]", " ")) end
local HOME = os.getenv("HOME") or os.getenv("USERPROFILE") or "."
local CONF = HOME .. "/.config/topcat/agent.json"
local CACHE = HOME .. "/.cache/topcat"
local JOBS = HOME .. "/.cache/vml/jobs"

local HUB_DEFAULT = "https://api.tiny-web.uk/topcat.php"

-- read/write a file ourselves (the same on Linux and Windows)
local function read(path) return Vml("FileRead", path) or "" end
local function write(path, text) return Vml("FileWrite", path, text) end

-- how to run the agent to switch it on/off/round, or follow a job: python + agent, from agent.json
TopCat.conf = {}
local function agent(args, into, after)
  local py, a = TopCat.conf.python, TopCat.conf.agent
  if not py or not a then return "" end
  return Vml("RunProcess", '"' .. py .. '" "' .. a .. '" ' .. args, into or "", after or "", "none")
end

-- First run on this machine: ask for the hub, a name for this machine and its key, write them, and start the agent.
-- No command line, no repo: the agent travels inside TopCat, and conf.python/agent already say how to call it.
function TopCat.Setup()
  local c = TopCat.conf
  local host = (os.getenv("COMPUTERNAME") or trim(read("/etc/hostname")) or ""):lower()
  local machine = Vml("PromptDialog", "Set up this machine", "A short name for this machine (callers use it):",
                      c.machine ~= "" and c.machine or host, "")
  if trim(machine) == "" then return false end
  local token = Vml("PromptDialog", "Set up this machine",
                    "This machine's key, from TopCat's hub (keep it secret):", "", "true")
  if trim(token) == "" then return false end
  local hub = Vml("PromptDialog", "Set up this machine", "TopCat hub address (leave as-is unless you host your own):",
                  c.hub ~= "" and c.hub or HUB_DEFAULT, "")
  if trim(hub) == "" then hub = HUB_DEFAULT end
  c.machine, c.token, c.hub = trim(machine), trim(token), trim(hub)
  c.level = TopCat.level or "ask"
  if not write(CONF, json.encode(c, { indent = true })) then
    set("StatusBar", "Text", "Couldn't save the settings (" .. CONF .. ").")
    return false
  end
  agent("--install")                                          -- registers the agent to start at login, and starts it now
  set("StatusBar", "Text", "Set up as " .. c.machine .. ": starting the agent…")
  return true
end

function TopCat.Opened()
  local conf = json.decode(read(CONF)) or {}
  TopCat.conf = conf
  TopCat.level = (conf.level == "look" or conf.level == "do" or conf.level == "ask") and conf.level or "ask"
  TopCat.ShowLevel()
  if not conf.token then
    set("lblState", "Text", "This machine isn't set up yet — tick \"Let TopCat in\" to begin.")
  end
  set("chkBoot", "IsChecked", Vml("GetSetting", "at_boot") == "on" and "true" or "false")
  TopCat.shell = (conf.shell == true or conf.shell == "always") and "always" or (conf.shell == "session" and "session" or "off")
  TopCat.ShowShell()
  -- Opening no longer forces the agent on. Exit shuts it out (agent --off: stops it now and at login);
  -- it stays out until you tick "Let TopCat in". The agent is a service of its own; here we only reflect its state.
  TopCat.Tick()
  set("tmr", "IsEnabled", "true")
  TopCat.UpdateButtons()                                      -- grey Pause/Kill/Delete until something's selected
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
    set("StatusBar", "Text", "Shutting TopCat out: stopping the agent…")
    if (agent("--off", nil, "TopCatExitDone") or "") == "" then Vml("Quit") end   -- nothing to stop: just go
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

function TopCat.ExitDone()
  Vml("Quit")                                                 -- the agent is stopped; now close the window
end

function TopCat.Boot()
  local on = get("chkBoot", "IsChecked") == "true"
  local now = Vml("StartAtBoot", tostring(on))
  if now == "on" or now == "off" then Vml("SetSetting", "at_boot", now) else set("StatusBar", "Text", now) end
end

-- every second and a half: on or off, anything new, the followed job's lines. The agent writes state.json each
-- loop (within the last minute means it's running); we read it ourselves, so this is the same on every system.
function TopCat.Marks()
  local function mark(btn, on)
    set(btn, "Content", on and "✔" or "✘")                -- heavy check / cross, bolder than ✓/✗
    set(btn, "Foreground", on and "#16A34A" or "#DC2626")
  end
  mark("chkOnBtn", get("chkOn", "IsChecked") == "true")
  mark("chkBootBtn", get("chkBoot", "IsChecked") == "true")
end

function TopCat.OnToggle()
  local want = not TopCat.on
  set("chkOn", "IsChecked", want and "true" or "false")
  TopCat.want, TopCat.wantAt = want, os.time()            -- remember the intent so Tick doesn't snap it back
  TopCat.Marks()                                          -- flip the ✔/✘ at once, before the agent catches up
  TopCat.Toggle()
end

function TopCat.OnBoot()
  set("chkBoot", "IsChecked", get("chkBoot", "IsChecked") == "true" and "false" or "true")
  TopCat.Marks()                                          -- instant feedback
  TopCat.Boot()
end

function TopCat.Who(id)
  for _, r in ipairs(TopCat.rows or {}) do
    if r.job and tostring(r.job):gsub("[^%w%-]", "") == id then
      return (r.caller ~= "" and r.caller or "someone")
    end
  end
  return "?"
end

function TopCat.Tick()
  local st = json.decode(read(CACHE .. "/state.json")) or {}
  local running = st.at and (os.time() - math.floor(st.at)) < 60 and true or false
  local on = running and st.on and true or false
  TopCat.machine = st.machine
  if TopCat.want ~= nil and (running == TopCat.want or (os.time() - (TopCat.wantAt or 0)) >= 10) then
    TopCat.want = nil                                   -- the agent reached the wanted state (or we waited long enough)
  end
  local waiting = TopCat.want ~= nil and running ~= TopCat.want
  if not waiting and TopCat.on ~= running then
    TopCat.on = running
    TopCat.TrayUpdate()
    TopCat.quiet = true
    set("chkOn", "IsChecked", running and "true" or "false")
    TopCat.quiet = false
  end
  set("dot", "Background", on and "#16A34A" or (running and "#F59E0B" or "#9CA3AF"))
  TopCat.Marks()
  if on then
    set("lblState", "Text", "Connected as " .. (st.machine or "?") .. " to " .. ((st.hub or ""):match("//([^/]+)") or "the hub"))
  elseif running then
    set("lblState", "Text", "Trying to reach the hub" .. ((st.why or "") ~= "" and (": " .. st.why) or "…"))
  else
    set("lblState", "Text", "Off: nobody can ask this machine anything.")
  end
  local log = read(CACHE .. "/log.jsonl")
  if #log ~= TopCat.size then
    TopCat.size = #log
    TopCat.Log(log)
  end
  if TopCat.proc and TopCat.autoscroll then          -- follow the tail, but only while the user is at it
    pcall(function()
      TopCat.quietScroll = true
      set("lstJob", "SelectedIndex", "99999")
      TopCat.lastIdx = tonumber(get("lstJob", "SelectedIndex"))
      TopCat.quietScroll = false
    end)
  end
end

function TopCat.Log(log)
  local rows, items = {}, {}
  for line in (log or ""):gmatch("[^\n]+") do
    local r = json.decode(line)
    if r then table.insert(rows, 1, r) end
  end
  while #rows > 80 do table.remove(rows) end
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

-- the jobs behind the selected rows (grid index i -> TopCat.rows[i+1]); only rows that are builds
function TopCat.SelectedJobs()
  local out = {}
  for tok in tostring(get("grdLog", "SelectedIndices")):gmatch("%d+") do
    local r = TopCat.rows[tonumber(tok) + 1]
    if r and (r.job or r.id) then out[#out + 1] = tostring(r.job or r.id):gsub("[^%w%-]", "") end
  end
  return out
end

function TopCat.UpdateButtons()
  local on = (#TopCat.SelectedJobs() > 0)
  local flag = on and "true" or "false"
  local GREY = "#434A54"                                 -- a custom Background ignores Qt's disabled look, so grey it ourselves
  set("btnPause", "IsEnabled", flag); set("btnPause", "Background", on and (TopCat.paused and "#2563EB" or "#D97706") or GREY)
  set("btnKill",  "IsEnabled", flag); set("btnKill",  "Background", on and "#DC2626" or GREY)
  set("btnDel",   "IsEnabled", flag); set("btnDel",   "Background", on and "#6B7280" or GREY)
end

function TopCat.Picked()
  TopCat.UpdateButtons()
  local jobs = TopCat.SelectedJobs()
  if #jobs >= 1 then TopCat.Watch(jobs[1]) end          -- the log panel follows the first of the selection
end

function TopCat.GridMenuShow()
  Vml("ShowContextMenu", "gridMenu")
end

function TopCat.SelAll()
  set("grdLog", "SelectAll", "1")
  TopCat.UpdateButtons()
end

function TopCat.JobScroll()
  -- user touched the log: stop autoscroll unless they are on the last line (then resume)
  if TopCat.quietScroll then return end
  local i = tonumber(get("lstJob", "SelectedIndex")) or -1
  TopCat.autoscroll = (TopCat.lastIdx ~= nil and i >= TopCat.lastIdx)
end

function TopCat.Watch(job)
  local id = tostring(job):gsub("[^%w%-]", "")
  if TopCat.proc then Vml("CancelProcess", TopCat.proc) end
  TopCat.job = id
  TopCat.autoscroll = true
  TopCat.paused = false
  set("btnPause", "Content", "Pause"); set("btnPause", "Background", "#D97706")
  set("lstJob", "Items", "")
  set("lblJob", "Text", id .. "  ·  " .. TopCat.Who(id) .. "  ·  running…")
  set("lblJob", "Foreground", "#B45309")
  -- the agent streams the job's lines, as they come, until it ends (the same on every system)
  TopCat.proc = agent("--follow " .. id, "lstJob", "TopCatJobDone")
end

function TopCat.JobDone()
  local id = TopCat.job
  if not id then return end
  local code = trim(read(JOBS .. "/" .. id .. ".exit"))
  if code == "" then return end                         -- (stopped by picking another one)
  local label, colour
  if code == "0" then
    label, colour = "finished, all good", "#16A34A"
  elseif code == "-15" or code == "-9" then
    label, colour = "stopped", "#B45309"                -- you stopped it, so not a failure
  else
    label, colour = "failed (exit " .. code .. ")", "#B91C1C"
  end
  set("lblJob", "Text", id .. "  ·  " .. TopCat.Who(id) .. "  ·  " .. label)
  set("lblJob", "Foreground", colour)
  TopCat.paused = false
  set("btnPause", "Content", "Pause"); set("btnPause", "Background", "#D97706")
  TopCat.proc = nil
end

-- the three buttons (and the right-click menu): pause/resume, stop, delete. Each acts on every
-- selected build. They are greyed (IsEnabled=false) while nothing is selected.
local function plural(n) return n == 1 and "" or "s" end
local function running_only(jobs)
  local out = {}
  for _, id in ipairs(jobs) do
    if trim(read(JOBS .. "/" .. id .. ".exit")) == "" then out[#out + 1] = id end
  end
  return out
end

function TopCat.JobPause()
  local jobs = TopCat.SelectedJobs()
  if #jobs == 0 then set("StatusBar", "Text", "Select a build (or more) first."); return end
  local live = running_only(jobs)
  TopCat.paused = not TopCat.paused
  for _, id in ipairs(live) do agent((TopCat.paused and "--pause " or "--resume ") .. id) end
  set("btnPause", "Content", TopCat.paused and "Resume" or "Pause")
  set("btnPause", "Background", TopCat.paused and "#2563EB" or "#D97706")
  set("StatusBar", "Text", (TopCat.paused and "Paused " or "Resumed ") .. #live .. " build" .. plural(#live) .. ".")
end

function TopCat.JobKill()
  local jobs = TopCat.SelectedJobs()
  if #jobs == 0 then set("StatusBar", "Text", "Select a build (or more) first."); return end
  local live = running_only(jobs)
  for _, id in ipairs(live) do agent("--kill " .. id) end   -- JobDone shows each as "stopped"
  set("StatusBar", "Text", "Stopping " .. #live .. " build" .. plural(#live) .. "…")
end

function TopCat.JobDel()
  local jobs = TopCat.SelectedJobs()
  if #jobs == 0 then set("StatusBar", "Text", "Select a build (or more) first."); return end
  if TopCat.proc then Vml("CancelProcess", TopCat.proc); TopCat.proc = nil end
  agent("--rm " .. table.concat(jobs, " "))               -- one atomic call: no concurrent log-rewrite races
  TopCat.job = nil
  set("lstJob", "Items", "")
  set("lblJob", "Text", "Console output — pick a build above")
  set("lblJob", "Foreground", "#374151")
  set("StatusBar", "Text", "Deleted " .. #jobs .. " build" .. plural(#jobs) .. ".")
  TopCat.size = -1                                        -- force Tick to rebuild from the pruned log
  TopCat.UpdateButtons()
end

function TopCat.Toggle()
  if TopCat.quiet then return end
  local want = get("chkOn", "IsChecked") == "true"
  if want and not TopCat.conf.token then                       -- first time in: set this machine up, then it's on
    if not TopCat.Setup() then
      TopCat.quiet = true
      set("chkOn", "IsChecked", "false")                       -- cancelled: leave it off
      TopCat.quiet = false
      return
    end
    TopCat.on = nil
    TopCat.Tick()
    return
  end
  agent(want and "--on" or "--off")
  set("StatusBar", "Text", want and "Letting TopCat in: the agent is starting." or "Shut out: the agent is stopped, and won't start at login.")
  TopCat.on = nil
  TopCat.Tick()
end

-- the shell: off unless you say (for this session, or always); even then, each command needs your yes
-- the colours: green, the least; orange, more (but still asks); red, things change without asking
local GREEN, ORANGE, RED = "#16A34A", "#D97706", "#DC2626"
local SHELL_LOOK = { off = { "Shell: off", GREEN }, session = { "Shell: this session", ORANGE },
                     always = { "Shell: always on", RED } }
local LEVEL_LOOK = { look = { "Callers: look", GREEN }, ["do"] = { "Callers: look and do", RED },
                     ask = { "Callers: do and ask", ORANGE } }
local function paint(btn, s)
  set(btn, "Content", s[1] .. "     ▾")
  set(btn, "Background", s[2])
end
function TopCat.ShowLevel()
  paint("btnLevel", LEVEL_LOOK[TopCat.level or "ask"])
  set("chkOnBtn", "BorderBrush", LEVEL_LOOK[TopCat.level or "ask"][2])      -- Let-in border matches Callers
end

function TopCat.LevelNext()
  TopCat.level = ({ look = "do", ["do"] = "ask", ask = "look" })[TopCat.level or "ask"]
  TopCat.Level()
end
function TopCat.ShowShell()
  paint("btnShell", SHELL_LOOK[TopCat.shell or "off"])
  set("chkBootBtn", "BorderBrush", SHELL_LOOK[TopCat.shell or "off"][2])    -- Start-with border matches Shell
end

function TopCat.Shell()
  TopCat.shell = ({ off = "session", session = "always", always = "off" })[TopCat.shell or "off"]
  agent("--set shell " .. TopCat.shell)                       -- the agent writes it and restarts itself
  TopCat.ShowShell()
  set("StatusBar", "Text", ({ off = "No shell: callers can only ask this machine's apps.",
    session = "Shell on until this computer restarts: each command still needs your yes.",
    always = "Shell always on: each command still needs your yes. Click again to turn it off." })[TopCat.shell])
end

function TopCat.Level()
  local lv = TopCat.level or "ask"
  TopCat.ShowLevel()
  TopCat.TrayUpdate()
  agent("--set level " .. lv)
  set("StatusBar", "Text", ({ look = "Look only: callers can read, never change anything.",
    ["do"] = "Look and do: callers can change things here, but nothing that goes out or can't be undone.",
    ask = "Everything, but anything that goes out or can't be undone needs your yes, each time." })[lv])
end
