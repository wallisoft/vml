"""
`vml`: drive a running VML form from Bash, PowerShell, or any program.

    vml get <control> <property>          print a property
    vml set <control> <property> <value>  set one
    vml setting <key> [value]             read or write a shared setting
    vml run <script> [args...]            run a script (Lua, C#, shell...) and print what it returns
    vml <Command> [args...]               any Vml() command, e.g.  vml InfoDialog "Saved!"

Scripts started by VML find it through VML_API and VML_TOKEN. Other programs use ~/.vml/api.json,
written by the running engine and readable only by you. No Qt here, so it starts fast.
"""
import json
import os
import socket
import sys
from pathlib import Path

DISCOVERY = Path.home() / ".vml" / "api.json"
VERBS = {"get": "GetProperty", "set": "SetProperty", "run": "RunScript"}


def endpoint():
    if os.environ.get("VML_API") and os.environ.get("VML_TOKEN"):
        host, port = os.environ["VML_API"].rsplit(":", 1)
        return host, int(port), os.environ["VML_TOKEN"]
    try:
        d = json.loads(DISCOVERY.read_text())
        return d["host"], int(d["port"]), d["token"]
    except (OSError, ValueError, KeyError):
        return None


def call(command, *args):
    ep = endpoint()
    if ep is None:
        raise ConnectionError("no VML engine is running")
    host, port, token = ep
    with socket.create_connection((host, port), timeout=30) as s:
        s.sendall((json.dumps({"token": token, "cmd": command, "args": [str(a) for a in args]}) + "\n").encode())
        data = b""
        while not data.endswith(b"\n"):
            chunk = s.recv(65536)
            if not chunk:
                break
            data += chunk
    reply = json.loads(data or b"{}")
    if not reply.get("ok"):
        raise RuntimeError(reply.get("error", "no reply"))
    return reply.get("value")


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__.strip())
        return 0
    verb, rest = argv[0], argv[1:]
    if verb == "setting":
        command, rest = ("SetSetting" if len(rest) > 1 else "GetSetting"), rest
    else:
        command = VERBS.get(verb, verb)
    try:
        value = call(command, *rest)
    except Exception as exc:
        print(f"vml: {exc}", file=sys.stderr)
        return 1
    if value not in (None, ""):
        print(value)
    return 0


if __name__ == "__main__":
    sys.exit(main())
