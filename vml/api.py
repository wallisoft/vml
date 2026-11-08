"""
The engine's local API: 127.0.0.1, a random port, a secret token. One JSON request per connection:
    {"token": "...", "cmd": "SetProperty", "args": ["lblHello", "Text", "Hi"]}  ->  {"ok": true, "value": "..."}
Requests are answered on the GUI thread: by a socket notifier when idle, and by poll() while the engine
is waiting for a script it started, so scripts can call back into the form that's running them.
"""
import atexit
import json
import os
import secrets
import socket
from pathlib import Path

from PySide6.QtCore import QSocketNotifier

DISCOVERY = Path.home() / ".vml" / "api.json"
RUNNING = Path.home() / ".vml" / "running"                # one file per running app: how to reach it (only you can read them)


class ApiServer:
    def __init__(self, engine, log):
        self.engine, self.log = engine, log
        self.token = secrets.token_hex(16)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(16)
        self.sock.setblocking(False)
        self.host, self.port = self.sock.getsockname()
        self.notifier = QSocketNotifier(self.sock.fileno(), QSocketNotifier.Read)
        self.notifier.activated.connect(lambda *_: self.poll())
        self._write_discovery()

    def env(self):
        return {"VML_API": f"{self.host}:{self.port}", "VML_TOKEN": self.token}

    def _write_discovery(self):
        try:
            DISCOVERY.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(str(DISCOVERY), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)   # only you can read it
            with os.fdopen(fd, "w") as f:
                json.dump({"host": self.host, "port": self.port, "token": self.token, "pid": os.getpid()}, f)
            atexit.register(self._remove_discovery)
        except OSError as exc:
            self.log(f"api: couldn't write {DISCOVERY}: {exc}")
        try:
            import time
            RUNNING.mkdir(parents=True, exist_ok=True)
            mine = RUNNING / f"{os.getpid()}.json"
            fd = os.open(str(mine), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as f:
                json.dump({"host": self.host, "port": self.port, "token": self.token, "pid": os.getpid(),
                           "started": time.time()}, f)
            atexit.register(lambda: mine.unlink(missing_ok=True))
        except OSError as exc:
            self.log(f"api: couldn't write {RUNNING}: {exc}")

    def _remove_discovery(self):
        try:
            if json.loads(DISCOVERY.read_text()).get("pid") == os.getpid():
                DISCOVERY.unlink()
        except (OSError, ValueError):
            pass

    def poll(self):
        """Answer every request waiting right now."""
        return self._poll()

    def _poll(self):
        while True:
            try:
                conn, _ = self.sock.accept()
            except (BlockingIOError, InterruptedError):
                return
            except OSError:
                return
            with conn:
                conn.settimeout(5)
                try:
                    data = b""
                    while not data.endswith(b"\n"):
                        chunk = conn.recv(65536)
                        if not chunk:
                            break
                        data += chunk
                    req = json.loads(data or b"{}")
                    if not secrets.compare_digest(str(req.get("token", "")), self.token):
                        reply = {"ok": False, "error": "bad token"}
                    elif not hasattr(self.engine, "cmd_" + str(req.get("cmd", ""))):
                        reply = {"ok": False, "error": f"unknown command {req.get('cmd')!r}"}
                    else:
                        value = self.engine.vml_strict(req["cmd"], *req.get("args", []))
                        reply = {"ok": True, "value": "" if value is None else str(value)}
                        if str(req["cmd"]).startswith("Debug"):
                            pass                                 # (the debugger's own questions aren't the app's calls)
                        elif getattr(self.engine, "debugger", None) is not None or getattr(self.engine, "_tap", None) is not None:
                            self.engine.debug_record(req["cmd"], req.get("args", []), value)   # (a Python or shell script's call)
                except Exception as exc:
                    reply = {"ok": False, "error": str(exc)}
                try:
                    conn.sendall((json.dumps(reply) + "\n").encode())
                except OSError:
                    pass


def ask(info, cmd, *args, timeout=3.0):
    """Ask another running app's engine (info: its file in ~/.vml/running) to do a command; its answer, or raises."""
    with socket.create_connection((info["host"], int(info["port"])), timeout=timeout) as s:
        s.settimeout(timeout)
        s.sendall((json.dumps({"token": info["token"], "cmd": cmd, "args": [str(a) for a in args]}) + "\n").encode())
        data = b""
        while not data.endswith(b"\n"):
            chunk = s.recv(1 << 20)
            if not chunk:
                break
            data += chunk
    reply = json.loads(data or b"{}")
    if not reply.get("ok"):
        raise RuntimeError(reply.get("error") or "no answer")
    return reply.get("value", "")


def running(exclude_pid=None):
    """The apps running now that a debugger can attach to: [{pid, title, info}], the ones that have gone tidied away."""
    out = []
    for f in sorted(RUNNING.glob("*.json")) if RUNNING.is_dir() else []:
        try:
            info = json.loads(f.read_text())
        except (OSError, ValueError):
            continue
        if info.get("pid") == exclude_pid:
            continue
        try:
            title = ask(info, "DebugTitle", timeout=1.0)
        except (OSError, RuntimeError, ValueError):
            try:
                os.kill(int(info.get("pid", 0)), 0)          # still there, just busy: leave its file alone
            except (OSError, ValueError):
                f.unlink(missing_ok=True)                    # gone
            continue
        out.append({"pid": info.get("pid"), "title": title, "info": info})
    return out
