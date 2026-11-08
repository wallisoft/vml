#!/usr/bin/env python3
"""
Put another of your machines on TopCat, from this one (which has the repo and ssh to it and to the server).

    python3 tools/topcat/enrol.py a8 --windows      a Windows PC: its key, the agent and its apps, a task at logon
    python3 tools/topcat/enrol.py slim              a Linux machine with the repo already on it: its key, then the
                                                    steps to run there

What it does:
  1. makes the machine a key, and adds it to the hub's keys on the server (ssh SERVER, sudo: your password)
  2. Windows: copies the agent, the API and the apps' API files and workers to ~/topcat on it (Pat, for now: Bob
     builds from here, not there), writes its settings, and starts it now and at every logon
SERVER is tw1 unless TOPCAT_SERVER says otherwise; the hub's keys are in /etc/topcat/tokens.json there.
"""
import base64
import json
import secrets
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SERVER = __import__("os").environ.get("TOPCAT_SERVER", "tw1")
HUB = "https://api.tiny-web.uk/topcat.php"
SSH = ["ssh", "-o", "ConnectTimeout=10"]
# what a Windows machine gets: enough to answer with its apps, nothing more
FILES = ["vml/__init__.py", "vml/appapi.py", "tools/topcat/agent.py", "apps/pat/api.vml", "tools/pat/pat.py"]

ADD_KEY = """import json, sys
p = "/etc/topcat/tokens.json"
t = json.load(open(p))
t.setdefault("machines", {})[sys.argv[1]] = sys.argv[2]
json.dump(t, open(p, "w"))
print("the hub knows " + sys.argv[1] + " now")
"""


def powershell(script):
    return "powershell -NoProfile -ExecutionPolicy Bypass -EncodedCommand " + base64.b64encode(script.encode("utf-16-le")).decode()


FIND_PYTHON = r'''
function Find-Python {
    foreach ($p in "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe", "$env:ProgramFiles\Python312\python.exe") {
        if (Test-Path $p) { return $p }
    }
    $p = & py -3 -c "import sys; print(sys.executable)" 2>$null
    if ($LASTEXITCODE -eq 0 -and $p) { return $p.Trim() }
    return $null
}
$python = Find-Python
if (-not $python) { Write-Host "No Python on this PC: build something there with Bob first (he installs it)"; exit 1 }
'''


def run(argv, **kw):
    print("  $", " ".join(a if len(a) < 60 else a[:57] + "..." for a in argv), flush=True)
    return subprocess.call(argv, **kw)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print(__doc__)
        return 1
    name, windows = args[0].lower(), "--windows" in sys.argv
    key = secrets.token_urlsafe(32)
    print(f"==> {name}: a key, and the hub told about it (sudo on {SERVER})")
    if run(["ssh", "-t", SERVER, "sudo python3 -c " + shlex.quote(ADD_KEY) + " " + shlex.quote(name) + " " + shlex.quote(key)]) != 0:
        print("FAILED: couldn't add the key on the server")
        return 1
    settings = {"hub": HUB, "machine": name, "token": key, "level": "ask"}
    if not windows:
        print(f"\nOn {name}, in its copy of the repo:\n"
              f"  mkdir -p ~/.config/topcat && (umask 077 && echo '{json.dumps(settings)}' > ~/.config/topcat/agent.json)\n"
              f"  python3 tools/topcat/agent.py --install")
        return 0
    print(f"==> {name}: the agent and its apps, to ~/topcat")
    if run(SSH + [name, powershell("New-Item -ItemType Directory -Force topcat/vml, topcat/tools/topcat, topcat/tools/pat, "
                                   "topcat/apps/pat, .config/topcat | Out-Null")]) != 0:
        print(f"FAILED: can't reach {name} over SSH")
        return 1
    for f in FILES:
        if run(["scp", "-q", str(REPO / f), f"{name}:topcat/{f}"]) != 0:
            print(f"FAILED: copying {f}")
            return 1
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as t:
        json.dump(settings, t)
    try:
        if run(["scp", "-q", t.name, f"{name}:.config/topcat/agent.json"]) != 0:
            print("FAILED: its settings")
            return 1
    finally:
        Path(t.name).unlink()
    print(f"==> {name}: started, and at every logon")
    code = run(SSH + [name, powershell(FIND_PYTHON + '& $python "$HOME\\topcat\\tools\\topcat\\agent.py" --install')])
    if code == 0:
        print(f"\n{name} is on TopCat. (Its settings, with its key: .config/topcat/agent.json in its home folder.)")
    return code


if __name__ == "__main__":
    sys.exit(main())
