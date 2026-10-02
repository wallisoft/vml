"""
Optional C# scripting: a small .NET host (csharp/VmlCSharpHost) that compiles scripts with Roslyn,
caches them, and calls back into the engine for every Vml(...). Started on first use; if .NET or the
built host isn't present, C# simply isn't offered. Build it once with:  ./vml.py setup-csharp
"""
import atexit
import json
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROJECT = ROOT / "csharp" / "VmlCSharpHost"
HOST_DLL = ROOT / "csharp" / "bin" / "VmlCSharpHost.dll"


def find_dotnet():
    for candidate in (shutil.which("dotnet"), os.path.join(os.environ.get("DOTNET_ROOT", ""), "dotnet"),
                      str(Path.home() / ".dotnet" / "dotnet"), "/usr/share/dotnet/dotnet", "/usr/lib/dotnet/dotnet",
                      r"C:\Program Files\dotnet\dotnet.exe"):
        if candidate and os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


def available():
    return HOST_DLL.is_file() and find_dotnet() is not None


def build():
    """Compile the host (needs the .NET SDK). Returns (ok, message)."""
    dotnet = find_dotnet()
    if dotnet is None:
        return False, "The .NET SDK isn't installed. Get it from https://dotnet.microsoft.com/download (8.0 or later)."
    r = subprocess.run([dotnet, "build", str(PROJECT), "-c", "Release", "-o", str(HOST_DLL.parent), "--nologo", "-v", "q"],
                       capture_output=True, text=True, env=dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT="1", DOTNET_NOLOGO="1"))
    if r.returncode != 0 or not HOST_DLL.is_file():
        return False, (r.stdout + r.stderr).strip()[-2000:]
    return True, f"C# scripting is ready ({HOST_DLL})"


class CSharpHost:
    def __init__(self, engine, log):
        self.engine, self.log, self.proc, self.next_id = engine, log, None, 0

    def _start(self):
        dotnet = find_dotnet()
        self.proc = subprocess.Popen([dotnet, str(HOST_DLL)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     text=True, bufsize=1, encoding="utf-8")
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
        self._send({"type": "run", "id": self.next_id, "code": code, "args": [str(a) for a in args], "key": key})
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
            elif t == "log":
                self.log(f"[{label}] {msg.get('text', '')}")
            elif t == "done":
                if msg.get("error"):
                    self.log(f"C# error in {label}:\n{msg['error']}")
                    return ""
                return msg.get("value", "")
