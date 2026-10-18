#!/usr/bin/env python3
"""
Run one of a project's builds (from its recipe.vml) on the machine it names: this computer, or another one over SSH.
What Bob runs for each card; fine from a terminal too.

    python3 tools/bob/run.py --config apps/mountie/recipe.vml --build Windows
    python3 tools/bob/run.py --config apps/mountie/recipe.vml --list         the builds, as JSON (what Bob reads)
    python3 tools/bob/run.py --config apps/mountie/recipe.vml --build Windows --stop
    python3 tools/bob/run.py --projects                                    every recipe.vml in the repo, as JSON
    python3 tools/bob/run.py --machines                                    the machines, as JSON
    python3 tools/bob/run.py --candidates                                  projects with no recipe yet, as JSON
    python3 tools/bob/run.py --new apps/CleverClogs.vml                    make one (its path is the answer)

A recipe (recipe.vml beside a project, or NAME.recipe.vml beside a single form) is VML: tools/bob/recipe.py has it all.
Its builds, each a card in Bob:
    @Build Windows                 compiled there (tools/bob/appbuild.py)
    Machine=a8
    Kind=compiled
    @Build QuickExport             the runtime and the project's files, for each platform
    Text=Quick export
    Machine=here
    Kind=export
    Platforms=windows, linux
    @Build Linux                   a command run here, in the repo: {host} the machine's SSH name, {install} "" or
    Machine=here                   --no-install (Bob's tick), {version}; for builds that do their own travelling,
    Kind=script                    like Visualised's. Results= says where its results go (Bob's Builds button).
    Run=tools/build-local.sh {install}

The machines (~/.config/bob/machines.vml, made the first time; Bob's Machines… opens it):
    @Machine here                  @Machine a8
    OS=linux                       Host=a8
                                   OS=windows
    Host is a name from ~/.ssh/config (or user@address); the machine needs Python 3.10+ (Windows: it's installed
    with winget the first time if missing) and, for compiled builds, a C compiler (Nuitka fetches one on Windows).

Everything a build makes comes back to ~/.cache/bob/<project>/<build>/.
"""
import argparse
import base64
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import recipe as vmlrecipe                                   # noqa: E402  (recipes and machines in VML: recipe.py)
MACHINES = Path(os.environ.get("BOB_MACHINES") or Path.home() / ".config" / "bob" / "machines.vml")
DEFAULT_MACHINES = {"here": {"os": "windows" if sys.platform.startswith("win") else "linux"},
                    "a8": {"host": "a8", "os": "windows"}}
SSH = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "-o", "ServerAliveInterval=30", "-o", "ServerAliveCountMax=6"]
STARTED = time.time()


def step(text):
    print(f"==> {text}", flush=True)


def fail(text):
    print(f"FAILED: {text}", flush=True)
    sys.exit(1)


def machines():
    if MACHINES.suffix == ".json":                          # (BOB_MACHINES pointing at a JSON file: as it was)
        return json.loads(MACHINES.read_text()) if MACHINES.is_file() else dict(DEFAULT_MACHINES)
    if not MACHINES.is_file():
        MACHINES.parent.mkdir(parents=True, exist_ok=True)
        old = MACHINES.with_suffix(".json")                  # Bob 2.0's machines.json, kept, now in VML
        ms = json.loads(old.read_text()) if old.is_file() else DEFAULT_MACHINES
        MACHINES.write_text(vmlrecipe.machines_to_vml(ms))
    return vmlrecipe.machines_from_vml(MACHINES.read_text(encoding="utf-8"))


def recipe(path):
    p = Path(path).resolve()
    return p, vmlrecipe.load(p)


def version_of(cfg_path, cfg):
    spec = cfg.get("version") or ""
    if ":" not in spec:
        return spec
    rel, key = spec.rsplit(":", 1)
    try:
        text = (cfg_path.parent / rel).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    m = re.search(rf"^\s*{re.escape(key)}\s*[=:]\s*[\"']?([^\"'\r\n]+)", text, re.M)
    return m.group(1).strip() if m else ""


def out_dir(cfg, build):
    slug = lambda s: re.sub(r"[^A-Za-z0-9._-]+", "-", s).strip("-") or "build"
    return Path.home() / ".cache" / "bob" / slug(cfg.get("name") or "project") / slug(build["name"])


def where(build):
    if build.get("kind") == "github":                       # (GitHub's own machines: nothing to look up)
        return "github", {"host": "", "os": "github"}
    name = build.get("machine") or "here"
    m = machines().get(name)
    if m is None:
        fail(f"no machine called {name!r} in {MACHINES}: add it there")
    return name, m


def is_here(m):
    return not m.get("host") or m.get("host") in ("here", "localhost")


def appbuild_args(cfg_rel, build, platform, out):
    args = ["tools/bob/appbuild.py", "--config", cfg_rel, "--kind", build.get("kind", "compiled"), "--out", out]
    if platform:
        args += ["--platform", platform]
    return args


def sh(argv, **kw):
    """Run, its output passed straight through. Its exit code."""
    return subprocess.call(argv, **kw)


def pack_source():
    """The repo as it is (uncommitted changes too, not what .gitignore leaves out), zipped."""
    try:
        names = subprocess.run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"], cwd=REPO,
                               capture_output=True, check=True).stdout.decode().split("\0")
    except (OSError, subprocess.CalledProcessError):
        names = [str(p.relative_to(REPO)) for p in REPO.rglob("*") if p.is_file() and ".git" not in p.parts]
    names = [n for n in names if n and (REPO / n).is_file()]
    fd, path = tempfile.mkstemp(prefix="bob-src-", suffix=".zip")
    os.close(fd)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for n in names:
            z.write(REPO / n, n)
    print(f"    {len(names)} files", flush=True)
    return path


def powershell(script):
    return "powershell -NoProfile -ExecutionPolicy Bypass -EncodedCommand " + base64.b64encode(script.encode("utf-16-le")).decode()


PS_PYTHON = r'''
function Find-Python {
    foreach ($p in "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe", "$env:ProgramFiles\Python312\python.exe") {
        if (Test-Path $p) { return $p }
    }
    $p = & py -3 -c "import sys; print(sys.executable)" 2>$null
    if ($LASTEXITCODE -eq 0 -and $p) { return $p.Trim() }
    return $null
}
$python = Find-Python
if (-not $python) {
    Write-Host "==> Installing Python 3.12 (first time only)"
    winget install -e --id Python.Python.3.12 --scope user --silent --accept-package-agreements --accept-source-agreements | Out-Host
    $python = Find-Python
    if (-not $python) { Write-Host "FAILED: no Python on this PC, and winget couldn't install it"; exit 1 }
}
'''


def remote(cfg_path, cfg, build, name, m, platform):
    host, os_ = m["host"], (m.get("os") or "linux").lower()
    work = "bob-build/" + re.sub(r"[^A-Za-z0-9_-]+", "-", (cfg.get("name") or "project")).lower()
    step(f"{cfg.get('name')} {build['name']}: on {name} ({host}, {os_})")
    if subprocess.call(SSH + [host, "echo ok"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) != 0:
        fail(f"can't reach {host} over SSH: is it on, and awake?")
    step("Sending the source")
    src = pack_source()
    try:
        mk = powershell(f"New-Item -ItemType Directory -Force '{work}' | Out-Null") if os_ == "windows" else f"mkdir -p {work}"
        if sh(SSH + [host, mk]) != 0 or sh(["scp", "-q", src, f"{host}:{work}/src.zip"]) != 0:
            fail(f"sending the source to {host}")
    finally:
        os.unlink(src)
    cfg_rel = str(cfg_path.relative_to(REPO)).replace("\\", "/")
    args = appbuild_args(cfg_rel, build, platform, "../out")
    step(f"Building on {name}")
    if os_ == "windows":
        quoted = " ".join("'" + a.replace("'", "''") + "'" for a in args)
        script = PS_PYTHON + f'''
$root = Join-Path $HOME "{work.replace('/', chr(92))}"
Set-Location $root
if (Test-Path src) {{ Remove-Item -Recurse -Force src }}
if (Test-Path out) {{ Remove-Item -Recurse -Force out }}
New-Item -ItemType Directory src, out | Out-Null
tar -xf src.zip -C src
if ($LASTEXITCODE -ne 0) {{ Write-Host "FAILED: unpacking the source"; exit 1 }}
Set-Location src
& $python {quoted}
exit $LASTEXITCODE
'''
        code = sh(SSH + [host, powershell(script)])
    else:
        cmd = (f"cd {work} && rm -rf src out && mkdir -p src out && python3 -m zipfile -e src.zip src && cd src && "
               + " ".join(shlex.quote(a) for a in ["python3", *args]))
        code = sh(SSH + [host, cmd])
    if code != 0:
        fail(f"the build on {name} (its log is above)")
    step("Bringing the results back")
    out = out_dir(cfg, build)
    if out.exists():
        for f in out.iterdir():
            f.unlink() if f.is_file() else None
    out.mkdir(parents=True, exist_ok=True)
    if sh(["scp", "-q", f"{host}:{work}/out/*", str(out)]) != 0:
        fail(f"copying the results back from {host}")
    for f in sorted(out.iterdir()):
        print(f"    {f.stat().st_size / 1e6:6.1f} MB  {f.name}", flush=True)


class MachineLock:
    """One build at a time on each machine (they share its build folder and venv): a second waits its turn."""

    def __init__(self, machine, label):
        self.machine, self.label, self.f = machine, label, None

    def __enter__(self):
        try:
            import fcntl
        except ImportError:                                  # (Windows running Bob: no waiting, as before)
            return self
        d = Path.home() / ".cache" / "bob" / "locks"
        d.mkdir(parents=True, exist_ok=True)
        self.f = open(d / f"{self.machine}.lock", "a+")
        try:
            fcntl.flock(self.f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.f.seek(0)
            other = self.f.read().strip() or "another build"
            step(f"Waiting: {other} is building on {self.machine}")
            fcntl.flock(self.f, fcntl.LOCK_EX)
            step(f"{self.machine} is free: starting")
        self.f.seek(0)
        self.f.truncate()
        self.f.write(self.label)
        self.f.flush()
        return self

    def __exit__(self, *exc):
        if self.f is not None:
            self.f.close()


def git(*args, check=True):
    p = subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True)
    if check and p.returncode != 0:
        fail(f"git {' '.join(args)}: {(p.stderr or p.stdout).strip()[-300:]}")
    return p.stdout.strip()


def gh_json(*args):
    p = subprocess.run(["gh", *args], cwd=REPO, capture_output=True, text=True)
    if p.returncode != 0:
        return None
    try:
        return json.loads(p.stdout or "null")
    except ValueError:
        return None


def github(cfg_path, cfg, build):
    """A release on GitHub: tag the commit that's pushed, push the tag, and follow the run it starts, live."""
    version = version_of(cfg_path, cfg)
    tag = (build.get("tag") or "v{version}").format(version=version)
    workflow = build.get("workflow") or ""
    repo = ["-R", build["repo"]] if build.get("repo") else []
    step(f"{cfg.get('name')} {version}: a release on GitHub, tag {tag}")
    if subprocess.call(["gh", "auth", "status"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) != 0:
        fail("the gh command isn't signed in (or isn't installed): see Bob's help, Getting started")
    if git("status", "--porcelain", "--untracked-files=no"):
        fail("there are changes not committed yet: commit them first (a release is built from what's on GitHub)")
    remote_has = git("ls-remote", "--tags", "origin", f"refs/tags/{tag}", check=False)
    if not remote_has:
        if git("tag", "-l", tag):
            fail(f"the tag {tag} is here but not on GitHub: an old one? Remove it (git tag -d {tag}) or raise the version")
        branch = git("rev-parse", "--abbrev-ref", "HEAD")
        ahead = git("rev-list", "--count", f"origin/{branch}..HEAD", check=False) or "0"
        if ahead != "0":
            step(f"Pushing {branch} first ({ahead} commit{'s' if ahead != '1' else ''} GitHub hasn't got)")
            git("push", "origin", branch)
        step(f"Tagging {git('rev-parse', '--short', 'HEAD')} as {tag} and pushing it")
        git("tag", tag)
        git("push", "origin", tag)
    else:
        last = gh_json("run", "list", *repo, "--branch", tag, "--limit", "1", "--json", "status,conclusion,url,createdAt",
                       *(["--workflow", workflow] if workflow else [])) or []
        if last and last[0].get("status") == "completed" and last[0].get("conclusion") == "success":
            step(f"{tag} was released already ({last[0].get('createdAt', '')[:16].replace('T', ' ')} UTC): nothing new to do. "
                 f"Raise the version for the next release: {last[0].get('url')}")
            return
        step(f"{tag} is on GitHub already: following its run")
    step("Waiting for GitHub to start the run")
    run = None
    for _ in range(40):                                        # (up to 2 minutes)
        args = ["run", "list", *repo, "--branch", tag, "--limit", "1", "--json", "databaseId,status,conclusion,url,workflowName"]
        if workflow:
            args += ["--workflow", workflow]
        runs = gh_json(*args) or []
        if runs:
            run = runs[0]
            break
        time.sleep(3)
    if run is None:
        fail(f"no run started for {tag}" + (f" (workflow {workflow!r})" if workflow else "") + ": is the workflow set off by this tag?")
    rid = run["databaseId"]
    (Path.home() / ".cache" / "bob" / "locks").mkdir(parents=True, exist_ok=True)
    (Path.home() / ".cache" / "bob" / "locks" / f"github-{rid}.run").write_text(f"{cfg_path}\n{build['name']}\n")
    print(f"    {run.get('workflowName')}: {run.get('url')}", flush=True)
    said = {}
    while True:
        info = gh_json("run", "view", str(rid), *repo, "--json", "status,conclusion,jobs") or {}
        for job in info.get("jobs") or []:
            steps = job.get("steps") or []
            current = next((s for s in steps if s.get("status") == "in_progress"), None)
            state = (job.get("status"), job.get("conclusion"), current.get("name") if current else "")
            if said.get(job["name"]) != state:
                said[job["name"]] = state
                if job.get("status") == "completed":
                    step(f"{job['name']}: {job.get('conclusion')}")
                elif current:
                    step(f"{job['name']}: {current['name']}")
                elif job.get("status") == "queued":
                    print(f"    {job['name']}: waiting for a machine", flush=True)
        if info.get("status") == "completed":
            break
        time.sleep(8)
    for f in (Path.home() / ".cache" / "bob" / "locks").glob(f"github-{rid}.run"):
        f.unlink()
    if info.get("conclusion") != "success":
        fail(f"the run ended {info.get('conclusion')}: {run.get('url')}")
    s = int(time.time() - STARTED)
    step(f"Green on GitHub in {s // 60}m {s % 60:02d}s: {run.get('url')}")


def run_build(cfg_path, cfg, build, install):
    if build.get("kind") == "github":
        return github(cfg_path, cfg, build)
    name, m = where(build)
    kind = build.get("kind", "compiled")
    if kind == "export" and is_here(m):                      # (an export here needs nothing the others use)
        return run_build_now(cfg_path, cfg, build, install, name, m, kind)
    with MachineLock(name, f"{cfg.get('name')} {build['name']}"):
        return run_build_now(cfg_path, cfg, build, install, name, m, kind)


def run_build_now(cfg_path, cfg, build, install, name, m, kind):
    if kind == "script":
        cmd = build["run"].format(host=m.get("host") or "", install="" if install else "--no-install",
                                  version=version_of(cfg_path, cfg))
        step(f"{cfg.get('name')} {build['name']}: {cmd}")
        code = sh(["bash", "-c", cmd], cwd=REPO)
        if code != 0:
            sys.exit(code)
        return
    platforms = build.get("platforms") or [build.get("platform") or (m.get("os") or "linux")] if kind == "export" else [None]
    for platform in platforms:
        if is_here(m):
            out = out_dir(cfg, build)
            if kind != "export":
                out.mkdir(parents=True, exist_ok=True)
            code = sh([sys.executable, *appbuild_args(str(cfg_path), build, platform, str(out))], cwd=REPO)
            if code != 0:
                sys.exit(code)
        else:
            remote(cfg_path, cfg, build, name, m, platform)
    s = int(time.time() - STARTED)
    step(f"Done in {s // 60}m {s % 60:02d}s: {out_dir(cfg, build)}")


def stop(cfg_path, cfg, build):
    """Stop a build: here, and on the machine it runs on (stopping the ssh alone would leave it running there)."""
    if build.get("kind") == "github":                       # a release: cancel its run on GitHub
        for f in (Path.home() / ".cache" / "bob" / "locks").glob("github-*.run"):
            if f.read_text().split("\n")[:2] == [str(cfg_path), build["name"]]:
                subprocess.call(["gh", "run", "cancel", f.stem.split("-", 1)[1]], cwd=REPO,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                f.unlink()
        subprocess.call(["pkill", "-f", f"run.py --config {cfg_path} --build {build['name']}"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return
    name, m = where(build)
    if not is_here(m):
        if (m.get("os") or "").lower() == "windows":
            ps = ('Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like "*appbuild.py*" -or '
                  '$_.CommandLine -like "*nuitka*" } | ForEach-Object { taskkill /F /T /PID $_.ProcessId | Out-Null }')
            subprocess.call(SSH + [m["host"], powershell(ps)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            subprocess.call(SSH + [m["host"], "pkill -f appbuild.py; pkill -f nuitka; true"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    pattern = f"run.py --config {cfg_path} --build {build['name']}"
    subprocess.call(["pkill", "-f", pattern], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if is_here(m):
        subprocess.call(["pkill", "-f", "tools/bob/appbuild.py"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if build.get("kind") == "script":
            first = build["run"].split()[0]
            subprocess.call(["pkill", "-f", first], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def recipes():
    found = set()
    for pattern in ("recipe.vml", "*.recipe.vml", "bob.json", "*.bob.json"):
        found |= set(REPO.rglob(pattern))
    return sorted(found)


def projects():
    found = []
    for p in recipes():
        if any(part in (".git", "build", "node_modules") or part.startswith(".") for part in p.relative_to(REPO).parts):
            continue
        try:
            cfg = vmlrecipe.load(p)
        except ValueError:
            continue
        found.append({"name": cfg.get("name") or p.parent.name, "config": str(p), "version": version_of(p, cfg)})
    return found


SKIP = (".git", "build", "node_modules", "designer", "tests", "vml", "packaging", "csharp", "tools", "tmp")


def candidates():
    """Projects (a .vmlproj) and apps (a .vml with a window, a version or an icon) that have no recipe yet."""
    have = set()
    for r in recipes():
        try:
            cfg = vmlrecipe.load(r)
        except ValueError:
            continue
        have.add(str((r.parent / (cfg.get("project") or "")).resolve()))
    out = []
    for p in sorted(REPO.rglob("*.vmlproj")) + sorted(REPO.rglob("*.vml")):
        rel = p.relative_to(REPO)
        if any(part in SKIP or part.startswith(".") for part in rel.parts[:-1]) or str(p.resolve()) in have:
            continue
        if p.suffix == ".vml":
            if any(q.suffix == ".vmlproj" for q in p.parent.iterdir()):   # (a form of a project: the project's the one)
                continue
            head = p.read_text(encoding="utf-8", errors="replace")[:4000]
            if not re.search(r"^@Window ", head, re.M) or not re.search(r"^(Version|Icon)=", head, re.M):
                continue
        out.append({"name": p.stem, "path": str(p), "where": str(rel.parent)})
    return out


def new_recipe(proj):
    """A recipe for a project or an app, with sensible builds: compiled here, compiled on the first Windows machine,
    and a quick export. Beside a project it's recipe.vml; beside a single app, NAME.recipe.vml. Its path is the answer."""
    proj = proj.resolve()
    if not proj.is_file():
        fail(f"no such file: {proj}")
    folder, name = proj.parent, proj.stem
    form = proj
    if proj.suffix == ".vmlproj":
        text = proj.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"^Name=(.+)$", text, re.M)
        name = m.group(1).strip() if m else name
        m = re.search(r"^Startup=(.+)$", text, re.M) or re.search(r"^Form=(.+)$", text, re.M)
        form = folder / m.group(1).strip() if m else proj
        target = folder / "recipe.vml"
    else:
        target = folder / f"{proj.stem}.recipe.vml"
    if target.exists():
        return str(target)
    head = form.read_text(encoding="utf-8", errors="replace") if form.is_file() else ""
    icon = ""
    m = re.search(r"^Icon=(.+)$", head, re.M)
    if m and (folder / m.group(1).strip()).is_file():
        icon = m.group(1).strip()
    else:
        for ext in (".png", ".svg"):
            for cand in (folder / f"{proj.stem}{ext}", folder / f"{proj.stem.lower()}{ext}"):
                if cand.is_file():
                    icon = cand.name
                    break
            if icon:
                break
    windows = next((k for k, v in machines().items() if (v.get("os") or "").lower() == "windows"), None)
    builds = [{"name": "Linux", "machine": "here", "kind": "compiled"}]
    if windows:
        builds.append({"name": "Windows", "machine": windows, "kind": "compiled"})
    builds.append({"name": "Quick export", "machine": "here", "kind": "export", "platforms": ["linux", "windows"]})
    cfg = {"name": name, "version": f"{form.relative_to(folder).as_posix()}:Version" if re.search(r"^Version=", head, re.M) else "1.0",
           "project": proj.name, "icon": icon, "company": "", "builds": builds}
    target.write_text(vmlrecipe.recipe_to_vml(cfg), encoding="utf-8")
    return str(target)


def main():
    ap = argparse.ArgumentParser(description="Run a project's build, here or on another machine")
    ap.add_argument("--config", help="the project's recipe.vml")
    ap.add_argument("--build", help="which of its builds (by name)")
    ap.add_argument("--list", action="store_true", help="the project's builds and machines, as JSON")
    ap.add_argument("--projects", action="store_true", help="every recipe.vml in the repo, as JSON")
    ap.add_argument("--machines", action="store_true", help="the machines, as JSON")
    ap.add_argument("--candidates", action="store_true", help="projects and apps in the repo without a recipe yet, as JSON")
    ap.add_argument("--new", metavar="PROJECT", help="make a recipe for a project (.vmlproj) or an app (.vml): its path")
    ap.add_argument("--json", metavar="RECIPE", help="a recipe as JSON (for anything that wants JSON)")
    ap.add_argument("--to-vml", metavar="RECIPE_JSON", help="a JSON recipe (bob.json) as VML, written beside it")
    ap.add_argument("--stop", action="store_true")
    ap.add_argument("--no-install", action="store_true", help="(script builds: {install} becomes --no-install)")
    a = ap.parse_args()
    if a.projects:
        print(json.dumps(projects()))
        return
    if a.machines:
        print(json.dumps(machines()))
        return
    if a.candidates:
        print(json.dumps(candidates()))
        return
    if a.new:
        print(new_recipe(Path(a.new)))
        return
    if a.json:
        print(json.dumps(vmlrecipe.load(a.json), indent=2))
        return
    if a.to_vml:
        src = Path(a.to_vml)
        dest = src.with_name("recipe.vml" if src.name == "bob.json" else src.name.replace(".bob.json", ".recipe.vml"))
        dest.write_text(vmlrecipe.recipe_to_vml(vmlrecipe.load(src)), encoding="utf-8")
        print(dest)
        return
    if not a.config:
        ap.error("--config is needed")
    cfg_path, cfg = recipe(a.config)
    if a.list:
        ms = machines()
        out = []
        for b in cfg.get("builds") or []:
            m = ms.get(b.get("machine") or "here", {}) if b.get("kind") != "github" else {"os": "github"}
            out.append({"name": b["name"], "machine": b.get("machine") or "here" if b.get("kind") != "github" else "GitHub",
                        "host": m.get("host") or "",
                        "os": m.get("os") or "", "kind": b.get("kind", "compiled"),
                        "uses_install": "{install}" in b.get("run", ""),
                        "tag": (b.get("tag") or "v{version}").format(version=version_of(cfg_path, cfg)) if b.get("kind") == "github" else "",
                        "out": os.path.expanduser(b["results"]) if b.get("results") else str(out_dir(cfg, b))})
        print(json.dumps({"name": cfg.get("name"), "version": version_of(cfg_path, cfg), "builds": out,
                          "machines_file": str(MACHINES)}))
        return
    build = next((b for b in cfg.get("builds") or [] if b["name"] == a.build), None)
    if build is None:
        fail(f"no build called {a.build!r} in {cfg_path}")
    if a.stop:
        stop(cfg_path, cfg, build)
    else:
        run_build(cfg_path, cfg, build, install=not a.no_install)


if __name__ == "__main__":
    main()
