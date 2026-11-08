"""TopCat as a program of its own. Two hats in one exe:
    TopCat                 opens the window (the Visualised runtime, running the TopCat project beside it)
    TopCat --agent [args]  runs this machine's agent instead (on/off/restart/set/follow/install), with no window

So a fresh machine needs nothing else installed: the window drives the agent by calling this same exe with --agent,
and the agent that answers the hub is this exe too. (Run from the source, it does the same, using the repo's agent.py.)
Made for tools/bob/appbuild.py (recipe Launcher=)."""
import json
import os
import runpy
import socket
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
COMPILED = "__compiled__" in globals()
CONF = Path(os.environ.get("TOPCAT_CONF") or Path.home() / ".config" / "topcat" / "agent.json")
HUB_DEFAULT = "https://api.tiny-web.uk/topcat.php"


def find(*rels):
    for r in rels:
        p = (HERE / r).resolve()
        if p.exists():
            return p
    return None


def agent_py():
    # bundled beside the project's data (dist: topcat/agent.py); from source: the repo's tools/topcat/agent.py
    return find("topcat/agent.py", "../../tools/topcat/agent.py")


def app_exe():
    # the binary the OS launched us as (compiled: TopCat/TopCat.exe) — NOT sys.executable, which Nuitka can report as a
    # bundled "python". This is what the window and the service call with --agent to be the agent.
    return os.path.realpath(sys.argv[0])


def run_agent(args):
    """Be the agent: run the bundled (or repo) agent.py with this interpreter, telling it which exe we are."""
    agent = agent_py()
    if not agent:
        raise SystemExit("TopCat: the agent files are missing. Reinstall TopCat.")
    os.environ["TOPCAT_FROZEN"] = "1" if COMPILED else ""
    os.environ["TOPCAT_EXE"] = app_exe()
    sys.argv = [str(agent)] + list(args)
    runpy.run_path(str(agent), run_name="__main__")


def seed_conf():
    """So the window can drive the agent on a machine with nothing else installed: make sure agent.json says how to
    call the agent (this exe, with --agent, when compiled) and has sensible defaults. Missing fields only: never
    clobber a machine already set up from the source."""
    try:
        conf = json.loads(CONF.read_text(encoding="utf-8")) if CONF.exists() else {}
    except (OSError, ValueError):
        conf = {}
    before = dict(conf)
    if COMPILED:
        conf.setdefault("python", app_exe())
        conf.setdefault("agent", "--agent")
    else:
        conf.setdefault("python", sys.executable)
        ap = agent_py()
        if ap:
            conf.setdefault("agent", str(ap))
    conf.setdefault("hub", HUB_DEFAULT)
    conf.setdefault("machine", (os.environ.get("COMPUTERNAME") or socket.gethostname().split(".")[0] or "").lower())
    if conf != before:
        try:
            CONF.parent.mkdir(parents=True, exist_ok=True)
            CONF.write_text(json.dumps(conf, indent=1), encoding="utf-8")
        except OSError:
            pass


def project():
    p = find("topcat/TopCat.vmlproj", "TopCat.vmlproj")
    if p:
        return str(p)
    raise SystemExit("TopCat's own files are missing (TopCat.vmlproj): reinstall it.")


if __name__ == "__main__":
    if sys.argv[1:2] == ["--agent"]:
        run_agent(sys.argv[2:])
        sys.exit(0)
    if not COMPILED:
        sys.path.insert(0, str(HERE.parents[1]))             # the repo, when run from the source
    seed_conf()
    if not any(a.lower().endswith((".vmlproj", ".vml")) for a in sys.argv[1:]) and sys.argv[1:2] != ["--serve-drive"]:
        sys.argv[1:1] = [project()]
    from vml.__main__ import main
    main()
