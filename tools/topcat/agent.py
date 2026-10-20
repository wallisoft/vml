#!/usr/bin/env python3
"""
TopCat's agent: runs on each of your machines, dials out to TopCat's hub and waits for work. Whatever is asked is
answered by this machine's apps through their API (vml/appapi.py: Bob, Pat... look, do and ask), never a raw shell.
Nothing listens here: the agent only ever makes outgoing HTTPS requests.

    python3 tools/topcat/agent.py                 run (Ctrl+C to stop); TOPCAT_DEBUG=1 says what it's doing
    python3 tools/topcat/agent.py --install       run it now and at every login (Linux: a systemd user service;
                                                  Windows: a Task Scheduler task at logon)
    python3 tools/topcat/agent.py --uninstall

Its settings, ~/.config/topcat/agent.json (only you can read it):
    {"hub": "https://api.tiny-web.uk/topcat.php", "machine": "a9", "token": "...", "level": "ask"}
level caps what this machine will do for a caller: look, do, or ask (ask: still only with the person's yes).
"""
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from vml import appapi                                       # noqa: E402

CONF = Path(os.environ.get("TOPCAT_CONF") or Path.home() / ".config" / "topcat" / "agent.json")
HERE = Path(os.environ.get("TOPCAT_CACHE") or Path.home() / ".cache" / "topcat")
LOG, STATE = HERE / "log.jsonl", HERE / "state.json"          # what TopCat's window shows: who asked what, and are we on
DEBUG = os.environ.get("TOPCAT_DEBUG")


def say(*a):
    if DEBUG:
        print(time.strftime("%H:%M:%S"), *a, flush=True)


def conf():
    try:
        c = json.loads(CONF.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        sys.exit(f"TopCat agent: no settings yet. Make {CONF} with hub, machine and token (see the top of this file).")
    c.setdefault("hub", "https://api.tiny-web.uk/topcat.php")
    c.setdefault("machine", socket.gethostname().split(".")[0].lower())
    c.setdefault("level", "ask")
    return c


def state(c, on, why=""):
    try:
        HERE.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps({"on": on, "at": time.time(), "hub": c["hub"], "machine": c["machine"],
                                     "level": c["level"], "why": why}), encoding="utf-8")
    except OSError:
        pass


def summary(result):
    if isinstance(result, dict):
        if result.get("error"):
            return "refused: " + str(result["error"])[:160]
        if result.get("job"):
            return "started job " + result["job"]
        if "exit" in result and "out" in result:
            first = (result.get("out") or result.get("err") or "").strip().splitlines()[:1]
            return f"exit {result['exit']}" + (f": {first[0][:120]}" if first else "")
        if result.get("said"):
            return str(result["said"])[:160]
        return ", ".join(list(result)[:6]) or "done"
    if isinstance(result, list):
        return f"{len(result)} item" + ("" if len(result) == 1 else "s")
    return str(result)[:160]


def record(job, result, level):
    """One line per request, for TopCat's window (and a desktop notice when it changes something)."""
    line = {"at": time.time(), "id": job.get("id"), "caller": job.get("caller", ""), "app": job.get("app", ""),
            "command": job.get("command", ""), "args": job.get("args") or {}, "level": level,
            "job": result.get("job") if isinstance(result, dict) else None, "said": summary(result)}
    try:
        HERE.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
    except OSError:
        pass
    if level in ("do", "ask") and os.name != "nt":
        try:
            subprocess.run(["notify-send", "-a", "TopCat", f"{line['caller'] or 'Someone'}: {line['app']} {line['command']}",
                            line["said"]], timeout=5, check=False, capture_output=True)
        except (OSError, subprocess.TimeoutExpired):
            pass


def notify(title, text):
    if os.name == "nt":
        return
    try:
        subprocess.run(["notify-send", "-a", "TopCat", title, text], timeout=5, check=False, capture_output=True)
    except (OSError, subprocess.TimeoutExpired):
        pass


def watch(job, jid):
    """A background job (a build) that a caller started: say how it ended, in the log and on the desktop."""
    import threading

    def wait():
        done = appapi.JOBS / f"{jid}.exit"
        while not done.exists():
            time.sleep(3)
        code = done.read_text().strip()
        said = "finished, all good" if code == "0" else f"ended badly (exit {code})"
        try:
            with LOG.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"at": time.time(), "id": f"{job.get('id')}-done", "caller": job.get("caller", ""),
                                    "app": job.get("app", ""), "command": job.get("command", ""), "args": job.get("args") or {},
                                    "level": "", "job": jid, "said": said}, ensure_ascii=False) + "\n")
        except OSError:
            pass
        args = " ".join(str(v) for v in (job.get("args") or {}).values())
        notify(f"{job.get('app', '')} {job.get('command', '')} {args}".strip() + (": done" if code == "0" else ": failed"), said)
    threading.Thread(target=wait, daemon=True).start()


def level_of(job):
    if job.get("app") == "topcat":
        return "ask" if job.get("command") == "shell" else "look"
    try:
        return appapi.apps()[job.get("app", "")]["commands"][job.get("command", "")]["level"]
    except (KeyError, TypeError):
        return "look"


def post(c, action, body, timeout=40):
    req = urllib.request.Request(f"{c['hub']}?a={action}", data=json.dumps(body).encode(), method="POST",
                                 headers={"Authorization": "Bearer " + c["token"], "Content-Type": "application/json",
                                          "User-Agent": "TopCat agent"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8") or "{}")


def shell(c, job, args):
    """A command line, run as you. Off unless this machine allows it (TopCat's window: Allow a shell), needs the "ask"
    level, and needs the person's yes each time. Answers its exit code and the end of what it printed; background=true
    for something long (a job to follow, like a build)."""
    if not c.get("shell"):
        return {"error": "this machine doesn't allow a shell (TopCat's window: Allow a shell)"}
    if c["level"] != "ask":
        return {"error": "a shell needs this machine's callers to be allowed \"do and ask\""}
    if not job.get("yes"):
        return {"error": "a shell command needs the person's yes: show them the exact command first"}
    cmd = str(args.get("command") or "").strip()
    if not cmd:
        return {"error": "shell needs a command"}
    argv = ["powershell", "-NoProfile", "-Command", cmd] if os.name == "nt" else ["bash", "-lc", cmd]
    cwd = os.path.expanduser(str(args.get("cwd") or "~"))
    if args.get("background") in (True, "true", "1", 1, "yes"):
        return appapi._start({"name": "shell", "cwd": cwd}, "shell", argv)
    try:
        p = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           stdin=subprocess.DEVNULL, timeout=max(1, min(int(args.get("timeout") or 120), 600)))
    except subprocess.TimeoutExpired:
        return {"error": "it took too long (timeout); for something long, background=true"}
    out, err = p.stdout, p.stderr
    return {"exit": p.returncode, "out": out[-6000:], "err": err[-2000:],
            **({"cut": f"showing the last 6000 of {len(out)} characters"} if len(out) > 6000 else {})}


def answer(c, job):
    """One request, answered by this machine's apps."""
    app, command, args = job.get("app", ""), job.get("command", ""), job.get("args") or {}
    try:
        if app == "topcat":                                   # the agent itself: who's here and what they can do
            if command == "apps":
                return appapi.describe()
            if command == "job":
                return appapi.job(args["job"]) if args.get("job") else appapi.jobs()
            if command == "hello":
                return {"machine": c["machine"], "level": c["level"], "python": sys.version.split()[0],
                        "repo": str(REPO), "apps": sorted(appapi.apps()), "shell": bool(c.get("shell")),
                        "os": "windows" if os.name == "nt" else sys.platform}
            if command == "shell":
                return shell(c, job, args)
            return {"error": f"the agent can be asked hello, apps, job or shell, not {command!r}"}
        return appapi.call(app, command, args, yes=bool(job.get("yes")), cap=c["level"])
    except appapi.ApiError as e:
        return {"error": str(e)}
    except Exception as e:                                    # (never let one bad request stop the agent)
        return {"error": f"{type(e).__name__}: {e}"}


def run():
    c = conf()
    apps = [{"app": a["app"], "commands": [x["command"] for x in a["commands"]]} for a in appapi.describe()]
    say(f"{c['machine']} -> {c['hub']} ({len(apps)} apps, level {c['level']})")
    first, wait = True, 2
    while True:
        try:
            job = post(c, "next", {"machine": c["machine"], **({"apps": apps} if first else {})})
            first, wait = False, 2
            state(c, True)
            if job.get("id"):
                say("asked:", job.get("app"), job.get("command"), json.dumps(job.get("args"))[:120])
                result = answer(c, job)
                post(c, "answer", {"id": job["id"], "result": result})
                record(job, result, level_of(job))
                if isinstance(result, dict) and result.get("job"):
                    watch(job, result["job"])
                say("answered", job["id"])
            elif job.get("error"):
                say("hub says:", job["error"])
                time.sleep(30)
        except urllib.error.HTTPError as e:
            say("hub:", e.code, e.read()[:200])
            state(c, False, f"the hub said {e.code}" + (" (wrong key?)" if e.code == 401 else ""))
            if e.code == 401:
                time.sleep(300)                               # (a wrong token won't fix itself: check rarely)
            else:
                time.sleep(wait)
                wait = min(wait * 2, 120)
        except (urllib.error.URLError, OSError, ValueError) as e:
            say("no hub:", e)                                 # (asleep, no Wi-Fi, hub restarting: try again soon)
            state(c, False, "can't reach the hub")
            time.sleep(wait)
            wait = min(wait * 2, 120)


UNIT = """[Unit]
Description=TopCat agent (answers TopCat's hub with this machine's apps)
After=network-online.target

[Service]
ExecStart={python} {me}
Restart=always
RestartSec=10

[Install]
WantedBy=default.target
"""


def install():
    conf()                                                    # (settings first)
    if os.name == "nt":                                       # Windows: a task at logon, with no console window
        pyw = Path(sys.executable).with_name("pythonw.exe")
        run = f'"{pyw if pyw.exists() else sys.executable}" "{Path(__file__).resolve()}"'
        made = subprocess.run(["schtasks", "/Create", "/F", "/SC", "ONLOGON", "/TN", "TopCat agent", "/TR", run]).returncode == 0
        if not made:                                          # (not allowed a logon task: the Startup folder, and a
            startup = Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
            (startup / "TopCat agent.cmd").write_text(f'@start "" {run}\r\n', encoding="utf-8")
            subprocess.run(["schtasks", "/Create", "/F", "/SC", "ONCE", "/ST", "00:00", "/TN", "TopCat agent", "/TR", run])
        subprocess.run(["schtasks", "/Run", "/TN", "TopCat agent"], check=False)   # (now, in your own session)
        print("TopCat agent: running, and starts at every logon")
        return
    unit = Path.home() / ".config" / "systemd" / "user" / "topcat-agent.service"
    unit.parent.mkdir(parents=True, exist_ok=True)
    unit.write_text(UNIT.format(python=sys.executable, me=Path(__file__).resolve()), encoding="utf-8")
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
    subprocess.run(["systemctl", "--user", "enable", "--now", "topcat-agent.service"], check=False)
    print("TopCat agent: running, and starts at every login (systemctl --user status topcat-agent)")


if __name__ == "__main__":
    if "--install" in sys.argv:
        install()
    elif "--uninstall" in sys.argv and os.name == "nt":
        subprocess.run(["schtasks", "/End", "/TN", "TopCat agent"], check=False)
        subprocess.run(["schtasks", "/Delete", "/F", "/TN", "TopCat agent"], check=False)
        print("TopCat agent: stopped, and won't start at logon")
    elif "--uninstall" in sys.argv:
        subprocess.run(["systemctl", "--user", "disable", "--now", "topcat-agent.service"], check=False)
        print("TopCat agent: stopped, and won't start at login")
    else:
        try:
            run()
        except KeyboardInterrupt:
            pass
