"""
Python scripts, built in: one Python worker per running app (your own Python, with your own pip packages), started
on the first Python script and kept, as the C# host is (vml/csharp.py: the same messages, one JSON per line).

    Each form keeps its own variables between scripts, as its Lua does (count = count + 1 goes on counting).
    Vml(...) and args are there; what a script prints is its answer, as before.
    Break mode: with breakpoints, or Step into, the worker follows the script line by line (sys.settrace) and stops
    where it should, with its locals; otherwise it runs at full speed.

Why a worker of its own and not inside Visualised: your scripts' imports, pip packages and anything they change in
Python itself stay in that process, and can't upset Visualised's own Python (or the other way round); a compiled
Visualised has no pip packages of yours at all. One worker for all the app's Python scripts: start-up paid once.
"""
from .csharp import CSharpHost

WORKER = r'''
import io, json, os, sys, traceback

proto_in, proto_out = sys.stdin, sys.__stdout__
states = {}


def send(msg):
    proto_out.write(json.dumps(msg) + "\n")
    proto_out.flush()


def wait_for(wanted):
    """Read until an answer of this type, running any script that comes first (a Vml() call can run another)."""
    for line in proto_in:
        msg = json.loads(line)
        if msg.get("type") == wanted:
            return msg
        if msg.get("type") == "run":
            run(msg)
    os._exit(0)


def Vml(command, *a):
    send({"type": "call", "cmd": command, "args": ["" if x is None else str(x) for x in a]})
    return wait_for("result").get("value", "")


class Debug:
    """Break mode: where to stop in a script, and the stop itself (the engine shows it)."""

    def __init__(self, spec, filename):
        self.name, self.file = spec.get("name") or "", filename
        self.breaks = set(spec.get("breaks") or [])
        self.mode, self.depth = spec.get("step"), 10 ** 6

    def depth_of(self, frame):
        d = 0
        while frame is not None:
            d, frame = d + 1, frame.f_back
        return d

    def trace(self, frame, event, arg):
        if frame.f_code.co_filename != self.file:
            return None                                 # (not the script: library code runs untraced)
        return self.line if event == "call" else None

    def line(self, frame, event, arg):
        if event != "line":
            return self.line
        depth = self.depth_of(frame)
        stop = {"into": True, "over": depth <= self.depth, "out": depth < self.depth}.get(self.mode, False)
        if not stop and frame.f_lineno not in self.breaks:
            return self.line
        shown = []
        for k, v in list(frame.f_locals.items()):
            if k.startswith("__") or k in ("Vml", "args") or type(v).__name__ in ("module", "function", "type", "builtin_function_or_method"):
                continue
            try:
                text = repr(v)
            except Exception:
                text = "?"
            shown.append([k, type(v).__name__, text[:400]])
        stack, f = [], frame
        while f is not None:
            if f.f_code.co_filename == self.file:
                stack.append([self.name, f.f_lineno, "" if f.f_code.co_name == "<module>" else f.f_code.co_name])
            f = f.f_back
        send({"type": "pause", "name": self.name, "line": frame.f_lineno, "depth": depth, "locals": shown, "stack": stack})
        answer = wait_for("resume")
        self.mode = answer.get("mode") or None
        self.depth = depth
        self.breaks = set(answer.get("breaks") or [])
        return self.line


def run(msg):
    name = (msg.get("debug") or {}).get("name") or msg.get("name") or "script"
    g = states.setdefault(msg.get("key", ""), {"__name__": "__vml__", "__builtins__": __builtins__})
    g["Vml"], g["args"] = Vml, list(msg.get("args") or [])
    sys.argv = ["-c", name, *g["args"]]                # (as before: a script's own sys.argv[2:] is still its args)
    out, before = io.StringIO(), sys.stdout
    sys.stdout = out
    filename = f"<vml:{name}>"
    debug = Debug(msg["debug"], filename) if msg.get("debug") else None
    error = None
    try:
        code = compile(msg.get("code", ""), filename, "exec")
        if debug:
            sys.settrace(debug.trace)
        exec(code, g)
    except SystemExit:
        pass
    except BaseException:
        kind, exc, tb = sys.exc_info()
        lines = [f"{name}, line {f.lineno}: {f.line or ''}".rstrip() for f in traceback.extract_tb(tb) if f.filename == filename]
        error = (lines[-1] + "\n" if lines else "") + f"{kind.__name__}: {exc}"
    finally:
        if debug:
            sys.settrace(None)
        sys.stdout = before
    send({"type": "done", "id": msg.get("id"), "value": out.getvalue().rstrip("\n"), "error": error})


send({"type": "ready"})
for line in proto_in:
    m = json.loads(line)
    if m.get("type") == "run":
        run(m)
'''


class PythonHost(CSharpHost):
    """The same conversation as the C# host's; only the worker differs."""
    lang = "Python"

    def __init__(self, engine, log, python):
        super().__init__(engine, log)
        self.python = python

    def _start(self):
        import atexit
        import os
        import subprocess
        from .csharp import _hidden
        env = dict(getattr(self.engine, "env", None) or os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8")
        self.proc = subprocess.Popen([self.python, "-u", "-c", WORKER], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     text=True, bufsize=1, encoding="utf-8", env=env, **_hidden())
        ready = self.proc.stdout.readline()
        if '"ready"' not in ready:
            raise RuntimeError(f"Python didn't start: {ready!r}")
        atexit.register(self.stop)
