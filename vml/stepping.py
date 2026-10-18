"""
Break mode, as VB had it: breakpoints in Lua scripts, and stepping through them a line at a time.

    a breakpoint      a script's name (or a module's file) and a line: the script stops there, before running it
    Step into  F8      the next line, following into a script it runs (RunScript) or a function it calls
    Step over  ⇧F8     the next line here, running whatever it calls without stopping
    Step out   ⌃⇧F8    to the end of this script, stopping where it was called from
    Continue   F5      on to the next breakpoint

How: Lua's own line hook, set in each form's Lua state only while there are breakpoints or a step is going (so
scripts run at full speed otherwise). At a stop the hook asks pause() here, which keeps the app's windows drawing
(a Qt event loop of its own) while the debugger looks: its locals and call stack, and Lua typed in the debugger
runs then. Meanwhile the app's events and timers are held off (handled() says no), so nothing runs into the
middle of a script that's stopped. A debugger attached from another process (vml/debugger.py) does the same
through DebugPauseInfo and DebugResume.

Lua, C# and Python: the C# host (csharp/VmlCSharpHost) compiles a script with a line hook while there are
breakpoints or a step going, the Python worker (vml/pyhost.py) follows one with sys.settrace, and their pauses come
here the same way (vml/csharp.py). Shell scripts are programs of their own, and aren't stepped.
"""
import json

from PySide6.QtCore import QEventLoop

# the hook, in each Lua state: cheap when there's nothing to do, the work only at a stop
HOOK_LUA = r"""
local pause = ...
local getinfo, getlocal = debug.getinfo, debug.getlocal
local function depth()
  local d = 2
  while getinfo(d + 1, "l") do d = d + 1 end
  return d
end
local function hook(_, line)
  if __vml_paused then return end
  local src = getinfo(2, "S").source
  if src:sub(1, 1) ~= "=" then return end
  src = src:sub(2)
  local stop, st = false, __vml_step
  if st then
    if st.mode == "into" then stop = true
    elseif st.mode == "over" then stop = depth() <= st.depth
    elseif st.mode == "out" then stop = depth() < st.depth end
  end
  if not stop then
    local b = __vml_bp and __vml_bp[src]
    stop = b ~= nil and b[line] == true
  end
  if not stop then return end
  local locals, i = {}, 1
  while true do
    local n, v = getlocal(2, i)
    if not n then break end
    if n:sub(1, 1) ~= "(" then
      locals[#locals + 1] = n .. "\t" .. type(v) .. "\t" .. (type(v) == "string" and string.format("%q", v) or tostring(v))
    end
    i = i + 1
  end
  local stack = {}
  for lv = 2, 40 do
    local inf = getinfo(lv, "Sln")
    if not inf then break end
    if inf.source:sub(1, 1) == "=" and inf.source ~= "=[C]" then
      stack[#stack + 1] = inf.source:sub(2) .. "\t" .. tostring(inf.currentline or 0) .. "\t" .. tostring(inf.name or "")
    end
  end
  pause(src, line, depth(), table.concat(locals, "\n"), table.concat(stack, "\n"))
end
__vml_hook = hook
"""


STEPPABLE = ("lua", "csharp", "c#", "cs", "python", "python3", "py")


class SteppingCommands:
    """Mixed into the Engine."""

    def _stepping_init(self):
        self.breaks = {}                 # chunk name -> {line, ...}
        self.step = None                 # ("into" | "over" | "out", depth) for the next stop
        self.paused = None               # where it's stopped: {name, line, depth, locals, stack}
        self._pause_loop = None

    # ---- the hook in each Lua state
    def stepping_active(self):
        return bool(self.breaks) or self.step is not None

    def _hook_state(self, rt):
        """Set (or take away) the hook in one Lua state, with the breakpoints and step it's to look for."""
        g = rt.globals()
        if g["__vml_hook"] is None:
            rt.execute(HOOK_LUA, self._stepping_pause)
        g["__vml_bp"] = rt.table_from({k: rt.table_from({ln: True for ln in v}) for k, v in self.breaks.items()})
        g["__vml_step"] = rt.table_from({"mode": self.step[0], "depth": self.step[1]}) if self.step else None
        g["__vml_paused"] = self.paused is not None
        if self.stepping_active():
            rt.execute('debug.sethook(__vml_hook, "l")')
        else:
            rt.execute("debug.sethook()")

    def _hook_all(self):
        for rt in list(self.luas.values()):
            try:
                self._hook_state(rt)
            except Exception as exc:
                self.log_line(f"debugger: couldn't set the hook ({exc})")

    def _stepping_pause(self, name, line, depth, locals_, stack):
        """Called by the hook at a stop: keep the windows drawing until Continue or a Step."""
        if self.paused is not None:                          # (already stopped: one at a time)
            return
        self.step = None
        self.paused = {"name": str(name), "line": int(line), "depth": int(depth),
                       "locals": [l.split("\t", 2) for l in str(locals_ or "").split("\n") if l],
                       "stack": [s.split("\t", 2) for s in str(stack or "").split("\n") if s]}
        self._hook_all()                                     # (marks every state paused: the debugger's Lua runs freely)
        self.log_line(f"paused in {name} at line {line}")
        for d in (getattr(self, "debugger", None), getattr(self, "_tap", None)):
            if d is not None and hasattr(d, "paused_at"):
                try:
                    d.paused_at(self.paused)
                except Exception as exc:
                    self.log_line(f"debugger: {exc}")
        if getattr(self, "debugger", None) is None and getattr(self, "_tap", None) is None:
            self.cmd_ShowDebugger()                          # a breakpoint with no debugger open: open it
            self.debugger.paused_at(self.paused)
        loop = self._pause_loop = QEventLoop()
        loop.exec()                                          # (until resume() quits it)
        self._pause_loop = None

    def resume(self, mode=""):
        """Carry on: mode "" to the next breakpoint, or "into", "over", "out" for a step."""
        if self.paused is None:
            return
        depth = self.paused["depth"]
        self.step = (mode, depth) if mode in ("into", "over", "out") else None
        self.paused = None
        self._hook_all()
        for d in (getattr(self, "debugger", None), getattr(self, "_tap", None)):
            if d is not None and hasattr(d, "resumed"):
                d.resumed()
        if self._pause_loop is not None:
            self._pause_loop.quit()

    def held(self, what):
        """While a script is stopped, the app's own events and timers wait (dropped, as VB did in break mode)."""
        if self.paused is None:
            return False
        return True

    # ---- the commands (the debugger here, or one attached from another process)
    def cmd_DebugBreaks(self, spec=""):
        """Set the breakpoints: JSON {name: [line, ...]}; none: what they are now."""
        if spec != "":
            got = json.loads(spec) if isinstance(spec, str) else spec
            self.breaks = {str(k): set(int(x) for x in v) for k, v in (got or {}).items() if v}
            self._hook_all()
        return json.dumps({k: sorted(v) for k, v in self.breaks.items()})

    def cmd_DebugPauseInfo(self):
        """Where a script is stopped (JSON), or "" if nothing is."""
        return json.dumps(self.paused) if self.paused is not None else ""

    def cmd_DebugResume(self, mode=""):
        self.resume(str(mode))
        return "true"

    def cmd_DebugScripts(self, key=""):
        """The Lua a form runs, to set breakpoints in: JSON [{name, code}] (its scripts, then its project's modules)."""
        out, key = [], str(key)
        try:
            rows = self.store.db.execute("SELECT name, interpreter, content, instance, source_file FROM scripts").fetchall()
        except Exception:
            rows = []
        for name, interp, content, instance, source in rows:
            if str(interp or "lua").split()[0].lower() not in STEPPABLE if str(interp or "").strip() else False:
                continue                                     # (Lua, C# and Python stop at breakpoints: shell scripts run as programs)
            home = "instance:" + instance if instance else str(source or "")
            if not key or home == key or (key.startswith("instance:") and str(interp or "").split()[1:2] == [key[9:]]):
                out.append({"name": name, "code": content or ""})
        if not key:                                          # the form being designed: its event scripts, by the names
            for scope in list(self.scopes.values()):         # they run under, so a breakpoint can go in before F5
                for n in list(scope.values()):
                    for event, (interp, code) in (getattr(n, "design_scripts", None) or {}).items():
                        if str(interp or "lua").split()[0].lower() in STEPPABLE and str(code).strip():
                            name = n.props.get(event) or (f"Form_{event}" if n.type.name == "DesignSurface" else f"{n.name}_{event}")
                            if not any(o["name"] == name for o in out):
                                out.append({"name": name, "code": code})
        project = self._project_of(key) if key and hasattr(self, "_project_of") else None
        if project is not None:
            for rel in project.modules:
                try:
                    out.append({"name": str(rel), "code": project.absolute(rel).read_text(encoding="utf-8-sig", errors="replace")})
                except OSError:
                    pass
        return json.dumps(out)
