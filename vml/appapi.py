"""
The apps' API: what each Visualised app (Bob, Pat, Mountie...) lets another program ask of it, written down in one
small VML file beside it, api.vml. One shape for them all, so one assistant (vml mcp now; TopCat later, over the
network) can drive every one of them. (vml/api.py is something else: the live line into a running form.)

    @Api Pat                                       the app, and how to run its worker (from the repo it's in)
    Run=python3 tools/pat/pat.py
    About=Posts your news, and keeps the books on what it earned

    @Command report                                one thing it can be asked
    Level=look                                     look: only reads; do: changes things here, harmlessly;
    About=The books: totals per channel...         ask: goes out into the world or can't be undone, so only
    Run=report                                     with the person's yes to that exact thing
    Param=product:integer:The product's number     name:type:what it is (name? when it may be left out); types:
                                                   text, integer, json (handed over as a file), a|b|c (one of them)
    Background=yes                                 slow (a build): it starts, and the answer is a job to follow

    In Run, {product} is the value, quoted for the shell; {product?--flag} is "--flag VALUE", or nothing if left out.

From a terminal:
    vml api                                        every app, and what each can be asked
    vml api pat report                             ask one (name=value for its parameters; --yes for an "ask" one)
    vml api job [ID]                               background jobs: still going? their last lines

Apps are found in apps/*/api.vml in the Visualised source, and in any folder named in VML_API_PATH (: between them).
VML_API_LEVEL caps what may be asked: look, do or ask (ask, the default, still needs the person's yes each time).
"""
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEVELS = ("look", "do", "ask")
JOBS = Path(os.environ.get("VML_API_JOBS") or Path.home() / ".cache" / "vml" / "jobs")


class ApiError(Exception):
    pass


def _parse(text):
    """api.vml: blocks of @Kind Name, then Key=Value lines (Param may repeat)."""
    blocks, cur = [], None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("@"):
            kind, _, name = line[1:].partition(" ")
            cur = {"kind": kind.strip().lower(), "name": name.strip(), "params": []}
            blocks.append(cur)
        elif cur is not None and "=" in line:
            k, _, v = line.partition("=")
            k = k.strip().lower()
            if k == "param":
                cur["params"].append(v.strip())
            else:
                cur[k] = v.strip()
    return blocks


def _param(spec):
    name, _, rest = spec.partition(":")
    kind, _, about = rest.partition(":")
    name = name.strip()
    return {"name": name.rstrip("?"), "type": kind.strip() or "text", "about": about.strip(), "optional": name.endswith("?")}


def folders():
    out = [ROOT / "apps"]
    for f in (os.environ.get("VML_API_PATH") or "").split(os.pathsep):
        if f.strip():
            out.append(Path(f.strip()).expanduser())
    return out


def _repo_of(path):
    d = path.parent
    while d != d.parent:
        if (d / "vml").is_dir() or (d / ".git").exists():
            return d
        d = d.parent
    return path.parent


def apps():
    """Every app with an api.vml: {key: {name, about, run, cwd, file, commands: {name: {...}}}}."""
    found = {}
    for folder in folders():
        files = [folder / "api.vml"] if (folder / "api.vml").is_file() else sorted(folder.glob("*/api.vml"))
        for f in files:
            try:
                blocks = _parse(f.read_text(encoding="utf-8"))
            except OSError:
                continue
            head = next((b for b in blocks if b["kind"] == "api"), None)
            if not head or not head["name"]:
                continue
            key = re.sub(r"[^a-z0-9]+", "_", head["name"].lower()).strip("_")
            cmds = {}
            for b in blocks:
                if b["kind"] == "command" and b["name"]:
                    level = b.get("level", "ask").lower()
                    cmds[b["name"]] = {"name": b["name"], "about": b.get("about", ""), "run": b.get("run", ""),
                                       "level": level if level in LEVELS else "ask",
                                       "background": b.get("background", "").lower() in ("yes", "true", "1"),
                                       "params": [_param(p) for p in b["params"]]}
            found.setdefault(key, {"name": head["name"], "about": head.get("about", ""), "run": head.get("run", ""),
                                   "cwd": str(_repo_of(f)), "file": str(f), "commands": cmds})
    return found


def describe():
    """Everything that can be asked, for a person or an assistant to read."""
    out = []
    for key, a in sorted(apps().items()):
        out.append({"app": key, "name": a["name"], "about": a["about"],
                    "commands": [{"command": c["name"], "level": c["level"], "about": c["about"],
                                  "background": c["background"],
                                  "params": [{k: p[k] for k in ("name", "type", "about", "optional")} for p in c["params"]]}
                                 for c in a["commands"].values()]})
    return out


def _value(p, v, temps):
    t = p["type"]
    if t == "integer":
        try:
            return str(int(str(v).strip()))
        except ValueError:
            raise ApiError(f"{p['name']} should be a whole number, not {v!r}")
    if t == "json":
        data = v if isinstance(v, str) else json.dumps(v)
        try:
            json.loads(data)
        except ValueError:
            raise ApiError(f"{p['name']} should be JSON")
        fd, path = tempfile.mkstemp(prefix="vml-api-", suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(data)
        temps.append(path)
        return path
    if "|" in t and str(v) not in t.split("|"):
        raise ApiError(f"{p['name']} should be one of: {t.replace('|', ', ')}")
    return str(v)


def command_line(app, cmd, args, temps):
    unknown = set(args) - {p["name"] for p in cmd["params"]}
    if unknown:
        raise ApiError(f"{cmd['name']} doesn't take {', '.join(sorted(unknown))}")
    vals = {}
    for p in cmd["params"]:
        v = args.get(p["name"])
        if v is None or v == "":
            if not p["optional"]:
                raise ApiError(f"{cmd['name']} needs {p['name']} ({p['about'] or p['type']})")
            continue
        vals[p["name"]] = _value(p, v, temps)

    def fill(m):
        name, flag = m.group(1), m.group(2)
        if name not in vals:
            return ""
        return (shlex.quote(flag) + " " if flag else "") + shlex.quote(vals[name])
    return (app["run"] + " " + re.sub(r"\{(\w+)(?:\?([^}]*))?\}", fill, cmd["run"])).strip()


def _answer(out):
    out = out.strip()
    try:
        return json.loads(out)
    except ValueError:
        lines = [l for l in out.splitlines() if l.strip()]
        try:
            return json.loads(lines[-1]) if lines else {}
        except ValueError:
            return {"text": out[-6000:]}


def call(app_key, command, args=None, yes=False, cap=None):
    """Ask an app something. The answer: its JSON (or {"text": ...}); for a background one, {"job": id}."""
    all_apps = apps()
    app = all_apps.get(str(app_key).lower())
    if app is None:
        raise ApiError(f"No app {app_key!r} (there's {', '.join(sorted(all_apps)) or 'none'})")
    cmd = app["commands"].get(command)
    if cmd is None:
        raise ApiError(f"{app['name']} has no {command!r} (it has {', '.join(app['commands'])})")
    cap = (cap or os.environ.get("VML_API_LEVEL") or "ask").lower()
    if LEVELS.index(cmd["level"]) > LEVELS.index(cap if cap in LEVELS else "look"):
        raise ApiError(f"{app['name']} {command} is an {cmd['level']!r} command; only {cap!r} ones are allowed here")
    if cmd["level"] == "ask" and not yes:
        raise ApiError(f"{app['name']} {command} goes out into the world (or can't be undone): ask the person first, "
                       f"then call it again with their yes")
    temps = []
    try:
        line = command_line(app, cmd, dict(args or {}), temps)
        if cmd["background"]:
            return _start(app, command, line)
        p = subprocess.run(line, shell=True, cwd=app["cwd"], capture_output=True, text=True, timeout=300,
                           stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        raise ApiError(f"{app['name']} {command} took more than five minutes")
    finally:
        for t in temps:
            try:
                os.unlink(t)
            except OSError:
                pass
    if p.returncode and not p.stdout.strip():
        raise ApiError(f"{app['name']} {command} failed: {(p.stderr or '').strip()[-1500:] or 'exit ' + str(p.returncode)}")
    return _answer(p.stdout)


# ---------------------------------------------------------------- background jobs (a build takes minutes)

def _start(app, command, line):
    JOBS.mkdir(parents=True, exist_ok=True)
    jid = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
    log, done = JOBS / f"{jid}.log", JOBS / f"{jid}.exit"
    (JOBS / f"{jid}.json").write_text(json.dumps({"job": jid, "app": app["name"], "command": command, "line": line,
                                                  "started": time.time()}), encoding="utf-8")
    wrapped = f"( {line} ) > {shlex.quote(str(log))} 2>&1; echo $? > {shlex.quote(str(done))}"
    kw = {"start_new_session": True} if os.name != "nt" else {"creationflags": 0x00000008}   # (it outlives us)
    subprocess.Popen(["bash", "-c", wrapped], cwd=app["cwd"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, **kw)
    return {"job": jid, "started": True, "follow": "ask for this job: still going, and its last lines"}


def job(jid, lines=40):
    jid = re.sub(r"[^\w-]", "", str(jid))
    meta_f = JOBS / f"{jid}.json"
    if not meta_f.is_file():
        raise ApiError(f"No job {jid}")
    meta = json.loads(meta_f.read_text(encoding="utf-8"))
    log, done = JOBS / f"{jid}.log", JOBS / f"{jid}.exit"
    tail = log.read_text(encoding="utf-8", errors="replace").splitlines()[-int(lines):] if log.exists() else []
    code = done.read_text().strip() if done.exists() else None
    meta.update({"running": code is None, "exit": int(code) if code and code.lstrip("-").isdigit() else code,
                 "minutes": round((time.time() - meta["started"]) / 60, 1), "last": tail})
    return meta


def jobs(n=20):
    out = []
    for f in sorted(JOBS.glob("*.json"), reverse=True)[:n] if JOBS.is_dir() else []:
        try:
            j = job(f.stem, lines=1)
            out.append({k: j[k] for k in ("job", "app", "command", "running", "exit", "minutes")})
        except (ApiError, ValueError, OSError):
            pass
    return out


# ---------------------------------------------------------------- vml api ...

def main(argv):
    try:
        if not argv:
            for a in describe():
                print(f"{a['app']}: {a['about']}")
                for c in a["commands"]:
                    ps = " ".join(f"{p['name']}{'?' if p['optional'] else ''}={p['type']}" for p in c["params"])
                    print(f"    {c['command']:<13} {c['level']:<5} {c['about']}" + (f"   [{ps}]" if ps else ""))
            return 0
        if argv[0] == "job":
            print(json.dumps(job(argv[1]) if len(argv) > 1 else jobs(), indent=1))
            return 0
        if argv[0] == "--json":
            print(json.dumps(describe(), indent=1))
            return 0
        if len(argv) < 2:
            raise ApiError("vml api APP COMMAND [name=value ...] [--yes]")
        args = dict(a.split("=", 1) for a in argv[2:] if "=" in a and not a.startswith("--"))
        print(json.dumps(call(argv[0], argv[1], args, yes="--yes" in argv), indent=1, ensure_ascii=False))
        return 0
    except ApiError as e:
        print(f"vml api: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
