#!/usr/bin/env python3
"""
Build a Visualised project as a program of its own, on this computer, from its recipe (recipe.vml).

    python3 tools/bob/appbuild.py --config apps/mountie/recipe.vml --kind compiled --out ~/.cache/bob/Mountie/Linux
    python3 tools/bob/appbuild.py --config apps/mountie/recipe.vml --kind export --platform windows --out ...

compiled   Nuitka: the project's own program (its name, its icon), smoke-tested, then packed: a .tar.gz on Linux;
           on Windows a portable .zip, and the setup .exe and Store package (.msix) when the recipe has them.
           The same steps as a GitHub release job, so a green build here means the same as a green one there.
export     Quick: the Visualised runtime (downloaded once, as the designer's Export does) with the project's files
           beside it, as a .zip (Windows) or .tar.gz (Linux). Seconds, no compiler; any computer can make either.

It works out where things are from the recipe's own folder (the project's) and the repo (two folders up from this
file), keeps a build venv in ~/.cache/bob (Windows: %LOCALAPPDATA%\\bob), and writes "==> " lines as it goes,
which is what Bob shows as each build's stage. Python 3.10 or later; nothing outside the standard library to start.

The recipe: recipe.vml beside the project (every path in it relative to it); tools/bob/recipe.py has it all.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.request
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import recipe as vmlrecipe                                   # noqa: E402  (recipes in VML: recipe.py)
WINDOWS = sys.platform.startswith("win")
HERE_OS = "windows" if WINDOWS else "linux"
RELEASES = "https://github.com/wallisoft/vml-releases/releases/latest/download/"
RUNTIMES = {"windows": ("vml-windows-x64.zip", "vml.exe", ".exe"), "linux": ("vml-linux-x86_64.tar.gz", "vml", "")}
STARTED = time.time()


def step(text):
    print(f"==> {text}", flush=True)


def fail(text, log=None):
    print(f"FAILED: {text}", flush=True)
    if log and Path(log).is_file():
        print("\n".join(Path(log).read_text(errors="replace").splitlines()[-40:]), flush=True)
    sys.exit(1)


def took():
    s = int(time.time() - STARTED)
    return f"{s // 60}m {s % 60:02d}s"


def run(argv, log=None, **kw):
    """Run a program, its output shown as it comes (and kept in log, if given). Its exit code."""
    print("    $ " + " ".join(str(a) for a in argv)[:300], flush=True)
    with open(log, "w", encoding="utf-8") if log else open(os.devnull, "w") as keep:
        p = subprocess.Popen([str(a) for a in argv], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                             errors="replace", bufsize=1, **kw)
        for line in p.stdout:
            keep.write(line)
            if not log or line.startswith(("Nuitka:", "Nuitka-")) and ("INFO" not in line or "Completed" in line):
                print("    " + line.rstrip(), flush=True)
        return p.wait()


class Recipe:
    def __init__(self, path):
        self.path = Path(path).resolve()
        self.folder = self.path.parent
        self.data = vmlrecipe.load(self.path)
        self.name = self.data.get("name") or self.folder.name
        self.slug = re.sub(r"[^a-z0-9]+", "", self.name.lower()) or "app"

    def get(self, key, default=None):
        return self.data.get(key, default)

    def file(self, rel):
        return (self.folder / rel).resolve() if rel else None

    def per_os(self, key):
        """A recipe list that may differ by OS: {"all": [...], "linux": [...], "windows": [...]} (or a plain list)."""
        v = self.data.get(key) or []
        if isinstance(v, list):
            return list(v)
        return list(v.get("all", [])) + list(v.get(HERE_OS, []))

    def version(self):
        spec = self.data.get("version") or ""
        if ":" not in spec:
            return spec or "0.0.0"
        rel, key = spec.rsplit(":", 1)
        text = self.file(rel).read_text(encoding="utf-8", errors="replace")
        m = re.search(rf"^\s*{re.escape(key)}\s*[=:]\s*[\"']?([^\"'\r\n]+)", text, re.M)
        return m.group(1).strip() if m else "0.0.0"

    def project(self):
        return self.file(self.data.get("project") or f"{self.name}.vmlproj")


def project_files(proj):
    """What travels with the app: a project's whole folder; a single form, itself and its own pictures (files named
    like it, and any picture it names), so an app that shares a folder with others takes only what's its."""
    junk = lambda n: n in ("bob.json", "recipe.vml") or n.endswith((".bob.json", ".recipe.vml")) or n.startswith(".") or n in ("__pycache__",) \
        or n.endswith((".pyc", ".db-journal"))
    folder = proj.parent
    if proj.suffix.lower() == ".vmlproj":
        return [p for p in folder.iterdir() if not junk(p.name)]
    keep = {proj}
    keep |= {p for p in folder.iterdir() if p.is_file() and p.stem.lower() == proj.stem.lower() and not junk(p.name)}
    text = proj.read_text(encoding="utf-8", errors="replace")
    for ref in re.findall(r"^(?:Source|Icon|Image)=(.+)$", text, re.M):
        p = (folder / ref.strip()).resolve()
        if p.is_file() and folder in p.parents:
            keep.add(p)
    return sorted(keep)


def stage_project(proj, dest):
    """The project's files (as project_files has them) copied into dest."""
    dest.mkdir(parents=True, exist_ok=True)
    for item in project_files(proj):
        rel = item.relative_to(proj.parent)
        if item.is_dir():
            shutil.copytree(item, dest / rel, dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".*", "bob.json", "*.bob.json", "recipe.vml", "*.recipe.vml"))
        else:
            (dest / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, dest / rel)


# ------------------------------------------------------------------------------------------------ the build venv
def venv_python(recipe):
    base = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "bob" if WINDOWS else Path.home() / ".cache" / "bob"
    venv = base / "venv"
    py = venv / ("Scripts/python.exe" if WINDOWS else "bin/python")
    if not py.is_file():
        step("Making the build venv (first time only)")
        if run([sys.executable, "-m", "venv", venv]) != 0:
            fail("making the venv (on Ubuntu: sudo apt install python3-venv python3-dev)")
    step("Build requirements")
    run([py, "-m", "pip", "install", "-q", "--upgrade", "pip"])
    if run([py, "-m", "pip", "install", "-q", "-r", REPO / "packaging" / "build-requirements.txt",
            *recipe.per_os("pip")]) != 0:
        fail("installing the build requirements")
    if not WINDOWS and not shutil.which("patchelf"):        # (Nuitka needs it on Linux: the pip one will do)
        run([py, "-m", "pip", "install", "-q", "patchelf"])
    flags = []
    optional = (recipe.get("pip_optional") or {})
    for scope in ("all", HERE_OS):
        for package, flag in (optional.get(scope) or {}).items():
            ok = run([py, "-m", "pip", "install", "-q", package]) == 0 and \
                run([py, "-c", f"import {package}"]) == 0
            print(f"    {package}: " + ("yes" if ok else "not this time (it's optional)"), flush=True)
            if ok and flag:
                flags.append(flag)
    return py, flags


# ------------------------------------------------------------------------------------------------ compiled
LAUNCHER = '''"""{name} as a program of its own: the Visualised runtime, running the {name} project beside it.
(Made by tools/bob/appbuild.py; run from the source, it does the same.)"""
import sys
from pathlib import Path


def project():
    here = Path(__file__).resolve().parent
    for p in (here / "{data}" / "{project}", Path(r"{source}")):
        if p.exists():
            return str(p)
    raise SystemExit("{name}'s own files are missing ({project}): reinstall it.")


if __name__ == "__main__":
    if "__compiled__" not in globals():
        sys.path.insert(0, r"{repo}")
    if not any(a.lower().endswith((".vmlproj", ".vml")) for a in sys.argv[1:]) and sys.argv[1:2] != ["--serve-drive"]:
        sys.argv[1:1] = [project()]
    from vml.__main__ import main
    main()
'''


def compiled(recipe, out):
    version = recipe.version()
    name, slug = recipe.name, recipe.slug
    step(f"{name} {version}: {HERE_OS} build on {os.environ.get('COMPUTERNAME') or os.uname().nodename}")
    proj = recipe.project()
    if not proj or not proj.exists():
        fail(f"the project isn't there: {proj}")
    py, optional_flags = venv_python(recipe)
    build = REPO / "build"
    shutil.rmtree(build / f"{slug}.dist", ignore_errors=True)
    shutil.rmtree(build / f"{slug}.build", ignore_errors=True)
    build.mkdir(exist_ok=True)

    launcher = recipe.file(recipe.get("launcher"))
    if launcher is None:                                    # one made for it: runs the project that travels inside
        launcher = build / f"{slug}.py"
        launcher.write_text(LAUNCHER.format(name=name, data=slug, project=proj.name, source=str(proj), repo=str(REPO)),
                            encoding="utf-8")
    elif launcher.stem != slug:                             # (Nuitka names the program's folder after the script)
        copy = build / f"{slug}.py"
        shutil.copy2(launcher, copy)
        launcher = copy

    data = build / f"{slug}-data"                           # what travels inside: the project's own files
    shutil.rmtree(data, ignore_errors=True)
    stage_project(proj, data)
    flags = ["--standalone", "--assume-yes-for-downloads", "--enable-plugin=pyside6",
             "--include-package=vml", "--include-package=lupa",
             f"--include-data-dir={REPO / 'designer'}=designer", f"--include-data-dir={REPO / 'vml' / 'lua'}=lua",
             f"--include-data-dir={REPO / 'vml' / 'web'}=web", f"--include-data-dir={data}={slug}",
             f"--output-filename={name}{'.exe' if WINDOWS else ''}", f"--output-dir={build}",
             *recipe.per_os("nuitka"), *optional_flags]
    icon = recipe.file(recipe.get("icon"))
    if WINDOWS:
        if icon and icon.is_file():
            ico = build / f"{slug}.ico"
            run([py, "-c", "import sys; from PIL import Image; Image.open(sys.argv[1]).convert('RGBA').save(sys.argv[2], "
                 "sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])", icon, ico])
            flags.append(f"--windows-icon-from-ico={ico}")
        flags += ["--windows-console-mode=attach", f"--company-name={recipe.get('company') or name}",
                  f"--product-name={name}", f"--file-version={version}", f"--product-version={version}"]
        try:                                                 # Defender scans each file the compiler writes: skip ours
            subprocess.run(["powershell", "-NoProfile", "-Command",
                            f"Add-MpPreference -ExclusionPath '{build}', \"$env:LOCALAPPDATA\\Nuitka\" -ErrorAction Stop"],
                           capture_output=True, timeout=30)
        except Exception:
            pass
    step("Compiling with Nuitka (the cache makes the next build much quicker)")
    log = build / f"{slug}-nuitka.log"
    env = dict(os.environ, PYTHONPATH=str(REPO), PATH=str(Path(py).parent) + os.pathsep + os.environ.get("PATH", ""))
    if run([py, "-m", "nuitka", *flags, launcher], log=log, env=env, cwd=REPO) != 0:
        fail("compiling", log)
    dist = build / f"{slug}.dist"
    exe = dist / f"{name}{'.exe' if WINDOWS else ''}"
    if not exe.is_file():
        fail(f"Nuitka finished but {exe.name} isn't there", log)

    step("Smoke test: it opens its window")
    shot, slog = build / f"{slug}-shot.png", build / f"{slug}-run.log"
    shot.unlink(missing_ok=True)
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", VML_KEPT=str(build / f"{slug}-kept"))
    with open(slog, "w") as err:
        try:
            subprocess.run([exe, "--shot", shot], stdout=err, stderr=err, env=env, timeout=90, cwd=build)
        except subprocess.TimeoutExpired:
            pass
    if not shot.is_file():
        fail(f"{name} didn't open its window", slog)
    if re.search(r"Traceback|script error", slog.read_text(errors="replace")):
        fail(f"{name}'s scripts failed as it opened", slog)
    print(f"    {name} opens its window", flush=True)

    step("Packing it up")
    out.mkdir(parents=True, exist_ok=True)
    licence = REPO / "LICENSE"
    if WINDOWS:
        stage = build / f"{slug}-stage" / name
        shutil.rmtree(stage.parent, ignore_errors=True)
        shutil.copytree(dist, stage)
        if licence.is_file():
            shutil.copy2(licence, stage / "LICENSE.txt")
        zipped = shutil.make_archive(str(out / f"{name}-windows-x64"), "zip", stage.parent, name)
        print(f"    {Path(zipped).name}", flush=True)
        iss = recipe.file(recipe.get("installer"))
        if iss and iss.is_file():
            iscc = find_iscc()
            if iscc is None:
                print("    (no Inno Setup on this PC: no setup .exe this time; winget install JRSoftware.InnoSetup)", flush=True)
            elif run([iscc, f"/DAppVersion={version}", iss], log=build / f"{slug}-inno.log") != 0:
                fail("making the setup .exe", build / f"{slug}-inno.log")
            else:
                for made in (iss.parent / "Output").glob("*.exe"):
                    shutil.copy2(made, out / made.name)
                    print(f"    {made.name}", flush=True)
        msix(recipe, version, dist, out, py)
    else:
        stage = build / f"{slug}-stage"
        shutil.rmtree(stage, ignore_errors=True)
        shutil.copytree(dist, stage)
        (stage / "VERSION").write_text(version + "\n")
        if licence.is_file():
            shutil.copy2(licence, stage / "LICENSE.txt")
        tgz = out / f"{slug}-linux-x86_64.tar.gz"
        with tarfile.open(tgz, "w:gz") as t:
            t.add(stage, arcname=slug)
        print(f"    {tgz.name}", flush=True)
    for extra in recipe.per_os("extras"):
        src = recipe.file(extra)
        if src and src.is_file():
            shutil.copy2(src, out / src.name)
            print(f"    {src.name}", flush=True)
    shutil.copy2(shot, out / f"{slug}-shot.png")
    step(f"{name} {version} for {HERE_OS} in {took()}: {out}")


def find_iscc():
    for p in (Path(os.environ.get("ProgramFiles(x86)", "")) / "Inno Setup 6/ISCC.exe",
              Path(os.environ.get("ProgramFiles", "")) / "Inno Setup 6/ISCC.exe",
              Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/Inno Setup 6/ISCC.exe"):
        if p.is_file():
            return p
    return None


def msix(recipe, version, dist, out, py):
    m = recipe.get("msix") or {}
    manifest = recipe.file(m.get("manifest"))
    if not (manifest and manifest.is_file() and m.get("identity") and m.get("publisher")):
        return
    kits = sorted(Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)")).glob("Windows Kits/10/bin/*/x64/makeappx.exe"))
    if not kits:
        print("    (no Windows SDK on this PC: no Store package this time; winget install Microsoft.WindowsSDK.10.0.22621)", flush=True)
        return
    step("The Store package (.msix)")
    parts = (version.split(".") + ["0", "0", "0"])[:3]
    stage = REPO / "build" / f"{recipe.slug}-msix"
    shutil.rmtree(stage, ignore_errors=True)
    shutil.copytree(dist, stage)
    (stage / "Assets").mkdir(exist_ok=True)
    for a, b in m.get("copies") or []:
        if (stage / a).is_file():
            shutil.copy2(stage / a, stage / b)
    licence = REPO / "LICENSE"
    if licence.is_file():
        shutil.copy2(licence, stage / "LICENSE.txt")
    icon = recipe.file(recipe.get("icon"))
    run([py, "-c", "import sys; from PIL import Image; im = Image.open(sys.argv[1]).convert('RGBA'); "
         "[im.resize((n, n), Image.LANCZOS).save(sys.argv[2] + f'/{f}.png') for f, n in "
         "(('Square150x150Logo', 150), ('Square44x44Logo', 44), ('StoreLogo', 50))]", icon, stage / "Assets"])
    text = manifest.read_text(encoding="utf-8").replace("@IDENTITY_NAME@", m["identity"]) \
        .replace("@PUBLISHER@", m["publisher"]).replace("@PUBLISHER_DISPLAY@", m.get("publisher_display", "")) \
        .replace("@VERSION@", ".".join(parts) + ".0")
    (stage / "AppxManifest.xml").write_text(text, encoding="utf-8")
    target = out / f"{recipe.name}.msix"
    if run([kits[-1], "pack", "/d", stage, "/p", target, "/o"], log=REPO / "build" / f"{recipe.slug}-msix.log") != 0:
        fail("making the .msix", REPO / "build" / f"{recipe.slug}-msix.log")
    print(f"    {target.name}", flush=True)


# ------------------------------------------------------------------------------------------------ quick export
def runtime(platform):
    """The Visualised runtime for a platform, downloaded once and kept where the designer keeps it (~/.vml/runtimes)."""
    asset, exe, _ = RUNTIMES[platform]
    cache = Path.home() / ".vml" / "runtimes" / platform
    folder = cache / "vml"
    if (folder / exe).is_file():
        return folder
    step(f"Downloading the {platform} runtime (first time only)")
    cache.mkdir(parents=True, exist_ok=True)
    archive = cache / asset
    with urllib.request.urlopen(RELEASES + asset, timeout=120) as r, open(archive, "wb") as f:
        shutil.copyfileobj(r, f)
    shutil.rmtree(folder, ignore_errors=True)
    if asset.endswith(".zip"):
        with zipfile.ZipFile(archive) as z:
            z.extractall(cache)
    else:
        with tarfile.open(archive) as t:
            t.extractall(cache, filter="tar") if hasattr(tarfile, "data_filter") else t.extractall(cache)
    archive.unlink(missing_ok=True)
    if not (folder / exe).is_file():
        fail(f"the {platform} runtime download didn't contain {exe}")
    return folder


def export(recipe, out, platform):
    version, name = recipe.version(), recipe.name
    step(f"{name} {version}: quick export for {platform}")
    proj = recipe.project()
    if not proj or not proj.exists():
        fail(f"the project isn't there: {proj}")
    rt = runtime(platform)
    _, exe, suffix = RUNTIMES[platform]
    stage = Path(os.environ.get("TMPDIR", "/tmp") if not WINDOWS else os.environ["TEMP"]) / f"bob-export-{recipe.slug}-{platform}"
    shutil.rmtree(stage, ignore_errors=True)
    step("The runtime and the project's files")
    shutil.copytree(rt, stage / name)
    (stage / name / exe).rename(stage / name / f"{proj.stem}{suffix}")
    stage_project(proj, stage / name)                      # forms, modules, pictures, databases
    (stage / name / "README.txt").write_text(
        f"{name} {version}\r\n\r\nTo run it: double-click {proj.stem}{suffix}"
        + ("" if suffix else f" (or run ./{proj.stem} in a terminal)") +
        "\r\n\r\nMade with Visualised: https://visualised.io\r\n", encoding="utf-8")
    if platform == "linux":
        (stage / name / proj.stem).chmod(0o755)
    step("Packing it up")
    out.mkdir(parents=True, exist_ok=True)
    if platform == "windows":
        made = shutil.make_archive(str(out / f"{name}-{version}-windows"), "zip", stage, name)
    else:
        made = str(out / f"{name}-{version}-linux.tar.gz")
        with tarfile.open(made, "w:gz") as t:
            t.add(stage / name, arcname=name)
    print(f"    {Path(made).name}", flush=True)
    shutil.rmtree(stage, ignore_errors=True)
    step(f"{name} {version} for {platform} (export) in {took()}: {out}")


def main():
    ap = argparse.ArgumentParser(description="Build a Visualised project from its recipe")
    ap.add_argument("--config", required=True, help="the project's recipe (recipe.vml)")
    ap.add_argument("--kind", default="compiled", choices=("compiled", "export"))
    ap.add_argument("--platform", default=HERE_OS, choices=("linux", "windows"), help="(export: which runtime)")
    ap.add_argument("--out", required=True, help="where the results go")
    a = ap.parse_args()
    recipe = Recipe(a.config)
    out = Path(os.path.expanduser(a.out)).resolve()
    if a.kind == "export":
        export(recipe, out, a.platform)
    else:
        if a.platform != HERE_OS:
            fail(f"a compiled build for {a.platform} has to be made on {a.platform}: give the build a {a.platform} machine")
        compiled(recipe, out)


if __name__ == "__main__":
    main()
