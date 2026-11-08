"""
Optional C# scripting: a small .NET host (csharp/VmlCSharpHost) that compiles scripts with Roslyn,
caches them, and calls back into the engine for every Vml(...). Started on first use; if .NET or the
built host isn't present, C# simply isn't offered.

Turning it on needs the free .NET SDK (8 or later) and one build of the host, which Settings > C# Scripting
does (or, from a terminal, vml setup-csharp). The host is built into the user's own folder (~/.vml/csharp), so
it works for an installed copy too, where the program's own folder can't be written to.
"""
import atexit
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOME = Path.home() / ".vml" / "csharp"
HOST = "VmlCSharpHost.dll"
SDK_URL = "https://dotnet.microsoft.com/download/dotnet/8.0"
QUIET = dict(DOTNET_CLI_TELEMETRY_OPTOUT="1", DOTNET_NOLOGO="1", DOTNET_SKIP_FIRST_TIME_EXPERIENCE="1")


def project_dir():
    """The host's source: beside the package from source, at the top of a compiled build."""
    for base in (ROOT, ROOT.parent, Path(sys.executable).resolve().parent):
        p = base / "csharp" / "VmlCSharpHost"
        if (p / "VmlCSharpHost.csproj").is_file():
            return p
    return ROOT / "csharp" / "VmlCSharpHost"


def host_dll():
    """The built host: the user's own (built from Settings), or one built beside the source."""
    for p in (HOME / "bin" / HOST, ROOT / "csharp" / "bin" / HOST):
        if p.is_file():
            return p
    return HOME / "bin" / HOST


def find_dotnet():
    for candidate in (shutil.which("dotnet"), os.path.join(os.environ.get("DOTNET_ROOT", ""), "dotnet"),
                      str(Path.home() / ".dotnet" / "dotnet"), "/usr/share/dotnet/dotnet", "/usr/lib/dotnet/dotnet",
                      "/usr/local/share/dotnet/dotnet", r"C:\Program Files\dotnet\dotnet.exe"):
        if candidate and os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


def _hidden():
    """On Windows, don't flash a console window for each dotnet call."""
    return {"creationflags": 0x08000000} if sys.platform.startswith("win") else {}


def sdk_version():
    """The newest .NET SDK installed ("" if there's only a runtime, or nothing)."""
    dotnet = find_dotnet()
    if dotnet is None:
        return ""
    try:
        r = subprocess.run([dotnet, "--list-sdks"], capture_output=True, text=True, timeout=20,
                           env=dict(os.environ, **QUIET), **_hidden())
    except (OSError, subprocess.SubprocessError):
        return ""
    versions = [ln.split()[0] for ln in r.stdout.splitlines() if ln.strip() and ln[0].isdigit()]
    key = lambda v: tuple(int(x) for x in v.split("-")[0].split(".") if x.isdigit())
    return max(versions, key=key) if versions else ""


def available():
    return host_dll().is_file() and find_dotnet() is not None


def status():
    """Where C# scripting stands on this computer."""
    sdk = sdk_version()
    major = int(sdk.split(".")[0]) if sdk[:1].isdigit() else 0
    return {"ready": available(), "dotnet": find_dotnet() or "", "sdk": sdk, "sdk_ok": major >= 8,
            "host": str(host_dll()), "download": SDK_URL, "source": project_dir().is_dir()}


def build():
    """Compile the host (needs the .NET SDK, and the internet the first time, for the C# compiler package).
    Returns (ok, message)."""
    dotnet = find_dotnet()
    if dotnet is None or not sdk_version():
        return False, f"The .NET SDK isn't installed. Get it from {SDK_URL} (8.0 or later)."
    src = project_dir()
    if not src.is_dir():
        return False, "This copy of Visualised doesn't include the C# host's source."
    work = HOME / "src"                                  # the program's own folder may be read-only: build in ours
    try:
        shutil.rmtree(work, ignore_errors=True)
        work.mkdir(parents=True, exist_ok=True)
        for f in src.iterdir():
            if f.is_file():
                shutil.copy2(f, work / f.name)
        out = HOME / "bin"
        r = subprocess.run([dotnet, "build", str(work), "-c", "Release", "-o", str(out), "--nologo", "-v", "q"],
                           capture_output=True, text=True, env=dict(os.environ, **QUIET), **_hidden())
    except (OSError, subprocess.SubprocessError) as exc:
        return False, str(exc)
    if r.returncode != 0 or not (out / HOST).is_file():
        return False, (r.stdout + r.stderr).strip()[-2000:] or "the build failed"
    return True, f"C# scripting is ready ({out / HOST})"


class CSharpHost:
    lang = "C#"

    def __init__(self, engine, log):
        self.engine, self.log, self.proc, self.next_id = engine, log, None, 0

    def _start(self):
        dotnet = find_dotnet()
        try:                                             # (Visualised updated with a newer host: build it again, once)
            src = project_dir() / "Program.cs"
            if src.is_file() and host_dll().is_file() and src.stat().st_mtime > host_dll().stat().st_mtime and sdk_version():
                self.log("C# host: updating it to this Visualised's (once, a few seconds)")
                ok, said = build()
                if not ok:
                    self.log(f"C# host: couldn't update it ({said[-300:]}): using the one there")
        except OSError:
            pass
        self.proc = subprocess.Popen([dotnet, str(host_dll())], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     text=True, bufsize=1, encoding="utf-8", env=dict(os.environ, **QUIET), **_hidden())
        ready = self.proc.stdout.readline()
        if '"ready"' not in ready:
            raise RuntimeError(f"C# host didn't start: {ready!r}")
        atexit.register(self.stop)

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.stdin.close()
            self.proc.terminate()

    def _send(self, msg):
        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()

    def run(self, code, args, key, label):
        """Run one script. Vml() calls it makes are answered here, as they arrive, by the engine itself."""
        if self.proc is None or self.proc.poll() is not None:
            self._start()
        self.next_id += 1
        msg = {"type": "run", "id": self.next_id, "code": code, "args": [str(a) for a in args], "key": key, "name": label}
        breaks = sorted(getattr(self.engine, "breaks", {}).get(label, ()))
        step = getattr(self.engine, "step", None)
        stepping = "into" if step and step[0] == "into" else None      # (over/out a Lua line: don't stop inside)
        if breaks or stepping:
            msg["debug"] = {"name": label, "breaks": breaks, "step": stepping}
        self._send(msg)
        while True:
            line = self.proc.stdout.readline()
            if not line:
                self.log(f"{label}: the C# host stopped unexpectedly")
                self.proc = None
                return ""
            msg = json.loads(line)
            t = msg.get("type")
            if t == "call":
                value = self.engine.vml(msg["cmd"], *msg.get("args", []))
                self._send({"type": "result", "value": "" if value is None else str(value)})
            elif t == "pause":                             # stopped at a breakpoint or a step: the debugger shows it
                name = msg.get("name") or label
                locals_ = "\n".join("\t".join(str(x) for x in row) for row in msg.get("locals") or [])
                stack = "\n".join("\t".join(str(x) for x in row) for row in msg.get("stack") or []) or \
                    f"{name}\t{msg.get('line', 0)}\t{self.lang}"
                self.engine._stepping_pause(name, msg.get("line", 0), msg.get("depth", 0), locals_, stack)
                step = getattr(self.engine, "step", None)
                self.engine._cs_stepping = step is not None
                self._send({"type": "resume", "mode": step[0] if step else "",
                            "breaks": sorted(getattr(self.engine, "breaks", {}).get(name, ()))})
            elif t == "log":
                self.log(f"[{label}] {msg.get('text', '')}")
            elif t == "done":
                if getattr(self.engine, "_cs_stepping", False):  # (stepped to the end of a C# script: stop at the next Lua line)
                    self.engine._cs_stepping = False
                    if getattr(self.engine, "step", None) is not None:
                        self.engine.step = ("into", 0)
                        self.engine._hook_all()
                if msg.get("error"):
                    self.log(f"{self.lang} error in {label}:\n{msg['error']}")
                    if getattr(self.engine, "debugger", None) is not None or getattr(self.engine, "_tap", None) is not None:
                        self.engine.debug_record("script error", (label,), msg["error"], error=True)
                    return ""
                return msg.get("value", "")
