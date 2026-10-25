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
import shutil
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
    if rel.endswith(".json"):                                # package.json:version
        try:
            return str(json.loads(text).get(key, ""))
        except (ValueError, AttributeError):
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


def project_root(cfg_path):
    """Where a project's commands run: the git repo its recipe is in, else the recipe's own folder."""
    d = Path(cfg_path).resolve().parent
    r = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=d, capture_output=True, text=True)
    return Path(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip() else d


def pack_source(root=None):
    """The project as it is (uncommitted changes too, not what .gitignore leaves out), zipped."""
    root = Path(root or REPO)
    try:
        names = subprocess.run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"], cwd=root,
                               capture_output=True, check=True).stdout.decode().split("\0")
    except (OSError, subprocess.CalledProcessError):
        names = [str(p.relative_to(root)) for p in walk(root)]
    names = [n for n in names if n and (root / n).is_file()]
    fd, path = tempfile.mkstemp(prefix="bob-src-", suffix=".zip")
    os.close(fd)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for n in names:
            z.write(root / n, n)
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
    if incremental(build, version):
        return fix_release(cfg_path, cfg, build, version, tag)
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


def incremental(build, version):
    """A fix (1.5.1, not 1.5.0) in a recipe that names Assets: released from the builds here, no clean build."""
    nums = re.findall(r"\d+", str(version))
    return bool(build.get("assets")) and len(nums) >= 3 and nums[2] != "0"


def fix_release(cfg_path, cfg, build, version, tag):
    """Tag a fix and publish this computer's builds of it as a pre-release: apps see it as a fix (About offers it),
    while releases/latest, and so the website's downloads, stay on the last clean release."""
    step(f"{cfg.get('name')} {version}: a fix, released from the builds here (tag {tag}, no clean build)")
    if subprocess.call(["gh", "auth", "status"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) != 0:
        fail("the gh command isn't signed in (or isn't installed): see Bob's help, Getting started")
    if git("status", "--porcelain", "--untracked-files=no"):
        fail("there are changes not committed yet: commit them, then build, then release")
    # the builds must be newer than what's released: the tag's commit if it's made already, else the last one
    since = int(git("log", "-1", "--format=%ct", tag, check=False) or git("log", "-1", "--format=%ct") or "0")
    files, builds = [], {b["name"]: b for b in cfg.get("builds") or []}
    for name in build["assets"]:
        b = builds.get(name)
        if not b:
            fail(f"Assets names {name!r}, but the recipe has no build called that")
        d = Path(os.path.expanduser(b["results"])) if b.get("results") else out_dir(cfg, b)
        found = [f for f in sorted(d.glob("*")) if f.is_file() and not f.name.endswith((".log", ".json"))] if d.is_dir() else []
        if not found:
            fail(f"nothing from the {name} build yet ({d}): build it first")
        stale = [f.name for f in found if f.stat().st_mtime < since]
        if stale:
            fail(f"the {name} build is older than the last commit ({', '.join(stale[:3])}): build it again first")
        files += found
    base = Path(cfg_path).parent
    for extra in build.get("asset_files") or []:
        f = (base / extra).resolve()
        if not f.is_file():
            fail(f"AssetFiles names {extra}, which isn't there")
        files.append(f)
    for f in files:
        if not os.access(f, os.R_OK):                        # (a file copied back from Windows can come with no read bit)
            os.chmod(f, f.stat().st_mode | 0o644)
        print(f"    {f.name}  ({f.stat().st_size // 1024:,} KB)", flush=True)
    if not git("ls-remote", "--tags", "origin", f"refs/tags/{tag}", check=False):
        if git("tag", "-l", tag):
            fail(f"the tag {tag} is here but not on GitHub: an old one? Remove it (git tag -d {tag}) or raise the version")
        branch = git("rev-parse", "--abbrev-ref", "HEAD")
        if (git("rev-list", "--count", f"origin/{branch}..HEAD", check=False) or "0") != "0":
            step(f"Pushing {branch} first")
            git("push", "origin", branch)
        step(f"Tagging {git('rev-parse', '--short', 'HEAD')} as {tag} and pushing it")
        git("tag", tag)
        git("push", "origin", tag)
    repo = build.get("assets_repo") or build.get("repo") or ""
    where = ["-R", repo] if repo else []
    if subprocess.call(["gh", "release", "view", tag, *where], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0:
        step(f"{tag} is released already: nothing new to do. Raise the version for the next fix.")
        return
    step(f"Publishing {tag} as a pre-release" + (f" on {repo}" if repo else ""))
    notes = (f"A fix, built by Bob from {git('rev-parse', '--short', 'HEAD')} (not GitHub's clean build). "
             f"Apps offer it in About; the website's downloads stay on the last clean release.")
    # gh from a snap can't open anything under a hidden folder (~/.cache), so the files go up from a plain one
    stage = Path.home() / f"bob-upload-{re.sub(r'[^A-Za-z0-9._-]', '', tag)}"
    shutil.rmtree(stage, ignore_errors=True)
    stage.mkdir()
    try:
        for f in files:
            shutil.copy2(f, stage / f.name)
        r = subprocess.run(["gh", "release", "create", tag, *where, "--prerelease", "--title", f"{cfg.get('name')} {version}",
                            "--notes", notes, *[str(stage / f.name) for f in files]], capture_output=True, text=True)
    finally:
        shutil.rmtree(stage, ignore_errors=True)
    if r.returncode != 0:
        fail("GitHub wouldn't take the release: " + (r.stderr or r.stdout).strip()[-300:])
    s = int(time.time() - STARTED)
    step(f"Released {tag} in {s // 60}m {s % 60:02d}s: {r.stdout.strip()}")



def build_release(cfg_path, cfg, build, version):
    """Publish THIS computer's builds as the rolling 'build' pre-release: a quiet upstream build apps offer only on
    a version-click (no pill, no 'update available'), while releases/latest and the website stay on the last clean
    release. Unlike a fix it needs no new version - it force-replaces the single 'build' release each time."""
    tag = "build"
    step(f"{cfg.get('name')} {version}: publishing this computer's builds as the rolling {tag!r} (a quiet upstream build)")
    if subprocess.call(["gh", "auth", "status"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) != 0:
        fail("the gh command isn't signed in (or isn't installed): see Bob's help, Getting started")
    if git("status", "--porcelain", "--untracked-files=no"):
        fail("there are changes not committed yet: commit them, then build, then publish the build")
    files, builds = [], {b["name"]: b for b in cfg.get("builds") or []}
    for name in build["assets"]:
        b = builds.get(name)
        if not b:
            fail(f"Assets names {name!r}, but the recipe has no build called that")
        d = Path(os.path.expanduser(b["results"])) if b.get("results") else out_dir(cfg, b)
        found = [f for f in sorted(d.glob("*")) if f.is_file() and not f.name.endswith((".log", ".json"))] if d.is_dir() else []
        if not found:
            fail(f"nothing from the {name} build yet ({d}): build it first")
        files += found
    base = Path(cfg_path).parent
    for extra in build.get("asset_files") or []:
        f = (base / extra).resolve()
        if not f.is_file():
            fail(f"AssetFiles names {extra}, which isn't there")
        files.append(f)
    for f in files:
        if not os.access(f, os.R_OK):                        # (a file copied back from Windows can come with no read bit)
            os.chmod(f, f.stat().st_mode | 0o644)
        print(f"    {f.name}  ({f.stat().st_size // 1024:,} KB)", flush=True)
    repo = build.get("assets_repo") or build.get("repo") or ""
    where = ["-R", repo] if repo else []
    branch = git("rev-parse", "--abbrev-ref", "HEAD")
    if (git("rev-list", "--count", f"origin/{branch}..HEAD", check=False) or "0") != "0":
        step(f"Pushing {branch} first")
        git("push", "origin", branch)
    sha = git("rev-parse", "HEAD")
    # force-replace the single rolling release: drop the old one (and its tag), then make it afresh at this commit
    subprocess.call(["gh", "release", "delete", tag, *where, "-y", "--cleanup-tag"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    step(f"Publishing the {tag!r} pre-release at {sha[:7]}" + (f" on {repo}" if repo else ""))
    notes = (f"A build by Bob from {sha[:7]} - the latest build, not a release and not tested. Apps offer it only on a "
             f"version click; releases/latest and the website's downloads stay on the last clean release.")
    stage = Path.home() / f"bob-upload-{tag}"
    shutil.rmtree(stage, ignore_errors=True)
    stage.mkdir()
    try:
        for f in files:
            shutil.copy2(f, stage / f.name)
        r = subprocess.run(["gh", "release", "create", tag, *where, "--target", sha, "--prerelease",
                            "--title", f"{cfg.get('name')} {version} (build)", "--notes", notes,
                            *[str(stage / f.name) for f in files]], capture_output=True, text=True)
    finally:
        shutil.rmtree(stage, ignore_errors=True)
    if r.returncode != 0:
        fail("GitHub wouldn't take the build: " + (r.stderr or r.stdout).strip()[-300:])
    s2 = int(time.time() - STARTED)
    step(f"Published the {tag!r} build ({version}) in {s2 // 60}m {s2 % 60:02d}s: {r.stdout.strip()}")


def run_build(cfg_path, cfg, build, install):
    if build.get("kind") == "github":
        return github(cfg_path, cfg, build)
    name, m = where(build)
    kind = build.get("kind", "compiled")
    if kind == "export" and is_here(m):                      # (an export here needs nothing the others use)
        return run_build_now(cfg_path, cfg, build, install, name, m, kind)
    with MachineLock(name, f"{cfg.get('name')} {build['name']}"):
        return run_build_now(cfg_path, cfg, build, install, name, m, kind)


def run_command(cfg_path, cfg, build, name, m):
    """Kind=command: any framework's build. The command runs in the project's folder (here, or on the machine
    after the project's sent there), and what Results names comes back to Bob's results folder."""
    root = project_root(cfg_path)
    os_ = (m.get("os") or "linux").lower()
    version = version_of(cfg_path, cfg)
    cmd = (build.get(f"run_{os_}") or build.get("run") or "").replace("{version}", version)
    if not cmd:
        fail(f"the {build['name']} build has nothing to run: give it Run= (or Run.{os_.capitalize()}=) in the recipe")
    results = [r.strip() for r in (build.get(f"results_{os_}") or build.get("results") or "").split(",") if r.strip()]
    out = out_dir(cfg, build)
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True, exist_ok=True)
    if is_here(m):
        step(f"{cfg.get('name')} {build['name']}: {cmd}")
        code = sh(["bash", "-c", cmd], cwd=root)
        if code != 0:
            fail(f"the command ended with {code} (its output is above)")
        for r in results:
            for p in sorted(root.glob(r)):
                (shutil.copytree(p, out / p.name, dirs_exist_ok=True) if p.is_dir() else shutil.copy2(p, out / p.name))
    else:
        host = m["host"]
        work = "bob-build/" + re.sub(r"[^A-Za-z0-9_-]+", "-", (cfg.get("name") or "project")).lower()
        step(f"{cfg.get('name')} {build['name']}: on {name} ({host}, {os_})")
        if subprocess.call(SSH + [host, "echo ok"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) != 0:
            fail(f"can't reach {host} over SSH: is it on, and awake?")
        step("Sending the project")
        src = pack_source(root)
        try:
            mk = powershell(f"New-Item -ItemType Directory -Force '{work}' | Out-Null") if os_ == "windows" else f"mkdir -p {work}"
            if sh(SSH + [host, mk]) != 0 or sh(["scp", "-q", src, f"{host}:{work}/src.zip"]) != 0:
                fail(f"sending the project to {host}")
        finally:
            os.unlink(src)
        step(f"Building on {name}: {cmd}")
        if os_ == "windows":                                 # (Windows PowerShell has no &&: each part, stopping at a failure)
            parts = "\n".join(f"{p.strip()}\nif ($LASTEXITCODE -and $LASTEXITCODE -ne 0) {{ exit $LASTEXITCODE }}"
                               for p in cmd.split("&&") if p.strip())
            fetch = "\n".join(f"Copy-Item -Path '{r}' -Destination ..\\out -Recurse -Force -ErrorAction SilentlyContinue"
                               for r in results)
            script = f'''
$ErrorActionPreference = "Continue"
$root = Join-Path $HOME "{work.replace('/', chr(92))}"
Set-Location $root
if (Test-Path src) {{ Remove-Item -Recurse -Force src }}
if (Test-Path out) {{ Remove-Item -Recurse -Force out }}
New-Item -ItemType Directory src, out | Out-Null
tar -xf src.zip -C src
if ($LASTEXITCODE -ne 0) {{ Write-Host "FAILED: unpacking the project"; exit 1 }}
Set-Location src
{parts}
{fetch}
exit 0
'''
            code = sh(SSH + [host, powershell(script)])
        else:
            fetch = " ".join(f"cp -r {r} ../out/ 2>/dev/null;" for r in results)
            code = sh(SSH + [host, f"cd {work} && rm -rf src out && mkdir -p src out && python3 -m zipfile -e src.zip src && "
                                   f"cd src && ( {cmd} ) && {{ {fetch} true; }}"])
        if code != 0:
            fail(f"the build on {name} (its output is above)")
        if results:
            step("Bringing the results back")
            if sh(["scp", "-q", "-r", f"{host}:{work}/out/*", str(out)]) != 0:
                fail(f"nothing came back from {host}: is Results= right? (it's looked for in the project's folder)")
    made = sorted(out.iterdir())
    for p in made:
        size = sum(f.stat().st_size for f in p.rglob("*") if f.is_file()) if p.is_dir() else p.stat().st_size
        print(f"    {size / 1e6:6.1f} MB  {p.name}{'/' if p.is_dir() else ''}", flush=True)
    if not results:
        print("    (no Results= in the recipe: nothing to bring back)", flush=True)
    s = int(time.time() - STARTED)
    step(f"Done in {s // 60}m {s % 60:02d}s: {out}")


def build_apk(cfg_path, cfg, build, name, m):
    """Kind=apk: a signed Android app built from the project's form (Form=), no Android SDK needed. Always here."""
    root = project_root(cfg_path)
    form = build.get("form") or (cfg.get("project") if str(cfg.get("project", "")).lower().endswith(".vml") else "")
    if not form:
        fail("an apk build needs Form=<a .vml form> in the recipe (Project= is a .vmlproj, not a form)")
    out = out_dir(cfg, build)
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", cfg.get("name") or "app").strip("-") or "app"
    apk = out / f"{slug}.apk"
    step(f"{cfg.get('name')}: the Android app, from {form}")
    code = sh([sys.executable, "-m", "vml", "apk", form, str(apk)], cwd=root)
    if code != 0:
        fail(f"the apk build ended with {code} (its output is above)")
    if apk.is_file():
        print(f"    {apk.stat().st_size / 1e6:6.1f} MB  {apk.name}", flush=True)
    s = int(time.time() - STARTED)
    step(f"Done in {s // 60}m {s % 60:02d}s: {out}")


def run_build_now(cfg_path, cfg, build, install, name, m, kind):
    if kind == "command":
        return run_command(cfg_path, cfg, build, name, m)
    if kind == "apk":
        return build_apk(cfg_path, cfg, build, name, m)
    if kind == "script":
        cmd = build["run"].format(host=m.get("host") or "", install="" if install else "--no-install",
                                  version=version_of(cfg_path, cfg))
        step(f"{cfg.get('name')} {build['name']}: {cmd}")
        code = sh(["bash", "-c", cmd], cwd=project_root(cfg_path))
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


PRUNE = {".git", "build", "dist", "node_modules", "__pycache__", "venv", ".venv"}


def walk(root=None):
    """Every file under the repo, without going into .git, build output and the like (a build folder can hold
    tens of thousands of files: looking through them made Bob slow to open)."""
    for d, dirs, files in os.walk(root or REPO):
        dirs[:] = [x for x in dirs if x not in PRUNE and not x.startswith(".") and not x.endswith((".build", ".dist"))]
        for f in files:
            yield Path(d) / f


def recipes():
    return sorted(p for p in walk() if p.name in ("recipe.vml", "bob.json") or p.name.endswith((".recipe.vml", ".bob.json")))


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
    files = list(walk())
    for p in sorted(f for f in files if f.suffix == ".vmlproj") + sorted(f for f in files if f.suffix == ".vml"):
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


# Any framework: what a folder holds says what it is, and how it's usually built. (name, file that shows it, Run,
# Run.Windows, Results, Results.Windows, where its version is.) A recipe made from one is a start: edit it to suit.
FRAMEWORKS = [
    ("Node", "package.json", "npm ci && npm run build", "", "dist", "", "package.json:version"),
    ("Rust", "Cargo.toml", "cargo build --release", "", "target/release/{name}", "target/release/{name}.exe", "Cargo.toml:version"),
    ("Go", "go.mod", "go build -o out/ ./...", "", "out", "", ""),
    (".NET", "*.csproj", "dotnet publish -c Release -o out", "", "out", "", ""),
    (".NET", "*.sln", "dotnet publish -c Release -o out", "", "out", "", ""),
    ("Flutter", "pubspec.yaml", "flutter build linux --release", "flutter build windows --release",
     "build/linux/x64/release/bundle", "build/windows/x64/runner/Release", "pubspec.yaml:version"),
    ("Python", "pyproject.toml", "python3 -m pip install -q build && python3 -m build", "py -m pip install -q build && py -m build",
     "dist", "", "pyproject.toml:version"),
    ("Python", "setup.py", "python3 -m pip install -q build && python3 -m build", "py -m pip install -q build && py -m build",
     "dist", "", ""),
    ("Make", "Makefile", "make", "", "build", "", ""),
]


def detect(folder):
    """What kind of project a folder is: (framework, its Visualised project or app, or None) or (None, None)."""
    folder = Path(folder)
    vml = next(iter(sorted(folder.glob("*.vmlproj"))), None)
    if vml:
        return "Visualised", vml
    for fw in FRAMEWORKS:
        if next(iter(folder.glob(fw[1])), None):
            return fw[0], fw
    return None, None


def new_folder_recipe(folder):
    """A recipe for any project folder: Visualised's own kind, else a framework's usual build (Kind=command), here
    and on the first Windows machine. recipe.vml in the folder; its path is the answer."""
    folder = Path(folder).resolve()
    target = folder / "recipe.vml"
    if target.exists():
        return str(target)
    kind, fw = detect(folder)
    if kind == "Visualised":
        return new_recipe(fw)
    name = folder.name
    windows = next((k for k, v in machines().items() if (v.get("os") or "").lower() == "windows"), None)
    if fw is None:                                       # (nothing recognised: a command to fill in)
        fw = ("", "", "echo 'Say how to build it: Run= in recipe.vml'", "", "", "", "")
    if fw[0] == "Rust":
        m = re.search(r'^name\s*=\s*"([^"]+)"', (folder / "Cargo.toml").read_text(errors="replace"), re.M)
        name = m.group(1) if m else name
    fill = lambda s: s.replace("{name}", name)
    builds = [{"name": "Linux", "machine": "here", "kind": "command", "run": fw[2], "results": fill(fw[4])}]
    if windows:
        b = {"name": "Windows", "machine": windows, "kind": "command", "run": fw[2], "results": fill(fw[4])}
        if fw[3]:
            b["run_windows"] = fw[3]
        if fw[5]:
            b["results_windows"] = fill(fw[5])
        builds.append(b)
    cfg = {"name": folder.name, "version": fw[6] or "1.0", "builds": builds}
    text = vmlrecipe.recipe_to_vml(cfg, title=f"{folder.name}: what Bob builds, and where" +
                                   (f" ({fw[0]}: the usual build; change Run= and Results= to suit)" if fw[0] else ""))
    target.write_text(text, encoding="utf-8")
    return str(target)


def recipe_files(cfg_path):
    """The files a recipe's builds use, for Bob's recipe editor: the recipe, then the scripts and packaging it names
    (and the files those scripts name in turn, one level down)."""
    cfg_path = Path(cfg_path).resolve()
    cfg = vmlrecipe.load(cfg_path)
    root, here = project_root(cfg_path), cfg_path.parent
    found = [cfg_path]

    def add(text):
        for tok in re.findall(r"[\w./\\-]+\.(?:sh|ps1|py|iss|xml|json|toml|yml|yaml|txt|cmd|bat|vml|lua|mk)\b|Makefile", text or ""):
            for base in (here, root):
                p = (base / tok).resolve()
                if p.is_file() and p not in found and p.stat().st_size < 400_000:
                    found.append(p)
                    break

    names = [str(v) for k, v in cfg.items() if k in ("launcher", "installer")]
    names += [str(v) for k, v in (cfg.get("msix") or {}).items() if k == "manifest"]
    for b in cfg.get("builds") or []:
        names += [str(v) for k, v in b.items() if k.startswith("run")]
        names += [", ".join(b.get("asset_files") or [])]
    for v in (cfg.get("extras") or {}).values():
        names += list(v)
    add(" ".join(names))
    for fw in FRAMEWORKS:                                # the project's own build files: package.json, Makefile...
        for p in sorted(root.glob(fw[1]))[:3]:
            if p.is_file() and p not in found:
                found.append(p)
    for p in list(found[1:]):                            # (what those scripts use: build-windows.sh > .ps1, say)
        if p.suffix not in (".sh", ".ps1", ".cmd", ".bat", ".yml", ".yaml") and p.name != "Makefile":
            continue
        try:
            before = len(found)
            add(p.read_text(encoding="utf-8", errors="replace"))
            found[before:] = [q for q in found[before:] if q.suffix not in (".vml", ".lua", ".py") or q.parent == p.parent]
        except OSError:
            pass
    return [{"path": str(p), "name": str(p.relative_to(root)) if p.is_relative_to(root) else p.name} for p in found]


def reset_machine(name):
    """Start a machine's build environment afresh: Bob's venv and build folders there go (made again next build)."""
    ms = machines()
    m = ms.get(name) if name != "here" else {"os": "linux"}
    if m is None:
        fail(f"no machine called {name}")
    if is_here(m):
        for d in (Path.home() / ".cache" / "bob" / "venv", Path.home() / "bob-build"):
            shutil.rmtree(d, ignore_errors=True)
        step("This computer's build environment is cleared: the next build makes it afresh")
        return
    if (m.get("os") or "").lower() == "windows":
        ps = ('foreach ($d in "$env:LOCALAPPDATA\\bob\\venv", "$HOME\\bob-build", "$HOME\\vml-build") '
              '{ if (Test-Path $d) { Remove-Item -Recurse -Force $d } }; Write-Host cleared')
        code = sh(SSH + [m["host"], powershell(ps)])
    else:
        code = sh(SSH + [m["host"], "rm -rf ~/.cache/bob/venv ~/bob-build ~/vml-build && echo cleared"])
    if code != 0:
        fail(f"couldn't reach {name} to clear it")
    step(f"{name}'s build environment is cleared: the next build there makes it afresh")


def new_recipe(proj):
    """A recipe for a project or an app, with sensible builds: compiled here, compiled on the first Windows machine,
    and a quick export. Beside a project it's recipe.vml; beside a single app, NAME.recipe.vml. Its path is the answer."""
    proj = proj.resolve()
    if proj.is_dir():                                    # a folder: any framework
        return new_folder_recipe(proj)
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


def _queue_build(a):
    """Hand a build to Bob's window instead of running it here: drop a job file Bob picks up, and open Bob if it's
    shut. So every build the API starts shows up live in Bob (what the person watches), not off in a headless shell."""
    if not a.config or not a.build:
        fail("--queue needs --config and --build")
    inbox = Path.home() / ".cache" / "bob" / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    job = {"recipe": os.path.abspath(a.config), "build": a.build, "mode": "edge" if a.edge else "build"}
    (inbox / f"{int(time.time() * 1000)}.json").write_text(json.dumps(job), encoding="utf-8")
    alive = Path.home() / ".cache" / "bob" / "ui.alive"
    up = alive.is_file() and (time.time() - alive.stat().st_mtime) < 6      # Bob touches this ~every 1.5s while open
    opened = False
    if not up:
        bob = Path(__file__).resolve().parents[2] / "apps" / "bob" / "Bob.vml"
        try:
            subprocess.Popen([str(bob)], cwd=str(bob.parents[2]), start_new_session=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
            opened = True
        except Exception as exc:
            print(json.dumps({"queued": True, "build": a.build, "mode": job["mode"], "bob_error": str(exc)}))
            return
    print(json.dumps({"queued": True, "build": a.build, "mode": job["mode"],
                      "bob": "opening" if opened else "already open", "note": "watch it in Bob's window"}))


def main():
    ap = argparse.ArgumentParser(description="Run a project's build, here or on another machine")
    ap.add_argument("--config", help="the project's recipe.vml")
    ap.add_argument("--build", help="which of its builds (by name)")
    ap.add_argument("--list", action="store_true", help="the project's builds and machines, as JSON")
    ap.add_argument("--projects", action="store_true", help="every recipe.vml in the repo, as JSON")
    ap.add_argument("--machines", action="store_true", help="the machines, as JSON")
    ap.add_argument("--candidates", action="store_true", help="projects and apps in the repo without a recipe yet, as JSON")
    ap.add_argument("--new", metavar="PROJECT", help="make a recipe for a project (.vmlproj), an app (.vml) or any project folder: its path")
    ap.add_argument("--files", metavar="RECIPE", help="the files a recipe's builds use, as JSON (for Bob's recipe editor)")
    ap.add_argument("--reset", metavar="MACHINE", help="clear a machine's build environment (venv, build folders)")
    ap.add_argument("--json", metavar="RECIPE", help="a recipe as JSON (for anything that wants JSON)")
    ap.add_argument("--to-vml", metavar="RECIPE_JSON", help="a JSON recipe (bob.json) as VML, written beside it")
    ap.add_argument("--stop", action="store_true")
    ap.add_argument("--no-install", action="store_true", help="(script builds: {install} becomes --no-install)")
    ap.add_argument("--edge", action="store_true",
                    help="publish this computer's builds as the rolling 'build' pre-release (a quiet upstream "
                         "build: no pill, offered only on a version-click) instead of cutting a release")
    ap.add_argument("--queue", action="store_true",
                    help="don't build here: drop the build into Bob's window (opening Bob if it's shut) so it runs "
                         "there where you can watch it - how TopCat/the API start a build")
    a = ap.parse_args()
    if a.queue:
        _queue_build(a)
        return
    if a.projects:
        print(json.dumps(projects()))
        return
    if a.machines:
        print(json.dumps(machines()))
        return
    if a.candidates:
        print(json.dumps(candidates()))
        return
    if a.files:
        print(json.dumps(recipe_files(a.files)))
        return
    if a.reset:
        reset_machine(a.reset)
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
                        "fix": b.get("kind") == "github" and incremental(b, version_of(cfg_path, cfg)),
                        "out": os.path.expanduser(b["results"]) if b.get("results") and b.get("kind") == "script" else str(out_dir(cfg, b))})
        print(json.dumps({"name": cfg.get("name"), "version": version_of(cfg_path, cfg), "builds": out,
                          "machines_file": str(MACHINES)}))
        return
    build = next((b for b in cfg.get("builds") or [] if b["name"] == a.build), None)
    if build is None:
        fail(f"no build called {a.build!r} in {cfg_path}")
    if a.stop:
        stop(cfg_path, cfg, build)
    elif a.edge:
        if build.get("kind") != "github":
            fail("--edge publishes a GitHub build's local artifacts as the rolling 'build'; this build isn't a GitHub one")
        build_release(cfg_path, cfg, build, version_of(cfg_path, cfg))
    else:
        run_build(cfg_path, cfg, build, install=not a.no_install)


if __name__ == "__main__":
    main()
