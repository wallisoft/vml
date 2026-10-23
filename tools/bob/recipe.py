"""
Bob's recipes and machines, written in VML: what to build and where, read the same way as a form.

    # Mountie: what Bob builds, and where
    @Recipe Mountie
    Version=Mountie.vml:Version          the file and key the version is read from (or just 1.0)
    Project=Mountie.vmlproj              the project (or a single form, CleverClogs.vml)
    Icon=mountie.png
    Company=Wallisoft
    Launcher=../../packaging/mountie/mountie.py     (a script to compile; else one is made)
    Pip=paramiko                         more for the build venv; .Linux / .Windows for one OS only
    Pip.Linux=mfusepy, python-xlib
    PipOptional.Windows=winfspy: --include-package=winfspy     (tried; its Nuitka flag only if it installed)
    Nuitka=--include-package=paramiko    more Nuitka flags; .Linux / .Windows too
    Installer=../../packaging/mountie/mountie.iss    (Windows: an Inno Setup script)
    Extras.Linux=../../packaging/mountie/install.sh  (files to send back with the build)

    @Msix Store                          (Windows: the Store package)
    Manifest=../../packaging/mountie/AppxManifest.xml
    Identity=tiny-web.mountie
    Publisher=CN=9D975A63-...
    PublisherDisplay=tiny-web
    Copy=Mountie.exe > MountieAtBoot.exe

    @Build Linux                         a card in Bob: built here, compiled
    Machine=here
    Kind=compiled                        compiled | export | script

    @Build QuickExport
    Text=Quick export                    (the name Bob shows, when it isn't the same)
    Machine=here
    Kind=export
    Platforms=linux, windows

    @Build GitHub                        a release on GitHub: tags the pushed commit, pushes the tag, and
    Text=GitHub release                  follows the Actions run it starts, live, on its card
    Kind=github                          (not part of Build all: only when its own Build is pressed)
    Tag=mountie-v{version}
    Workflow=Mountie release

    A fix (1.2.5, not 1.2.0) needn't wait for GitHub's clean build: with Assets, Bob tags it and publishes the
    named builds' results from here as a pre-release, which apps offer as a fix (the website stays on the last
    clean release):
    Assets=Linux, Windows                (the builds whose results go up: build them first)
    AssetsRepo=wallisoft/vml-releases    (where the release goes, if not the project's own repo)
    AssetFiles=packaging/install.sh      (more files to go up with them)

    Any framework (npm, cargo, dotnet, go, flutter, Python, make...): a command, run in the project's folder, here
    or on another machine (the project is sent there first), and what it made brought back:
    @Build Windows
    Machine=a8
    Kind=command
    Run=npm ci && npm run build          (Run.Windows / Run.Linux for one OS only)
    Results=dist                         (files or folders, from the project's folder; Results.Windows too)

    @Build Windows                       a script of the project's own, run here: {host} {install} {version}
    Machine=a8
    Kind=script
    Run=tools/build-windows.sh {host}
    Results=~/.cache/vml-build-windows

The machines (~/.config/bob/machines.vml):
    @Machine here
    OS=linux

    @Machine a8
    Host=a8                              a name from ~/.ssh/config (or user@address)
    OS=windows

Paths are relative to the recipe's own folder. Bob's tools work on the plain structure underneath (to_dict), so a
recipe goes to JSON and back without loss: run.py --json RECIPE, and run.py --to-vml RECIPE.json.
"""
import json
import re
from pathlib import Path

OSES = ("linux", "windows")


def parse(text):
    """VML's plain shape: @Type Name blocks of Key=Value lines (# comments). Keys may repeat (a list then)."""
    blocks, cur = [], None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("@"):
            kind, _, name = line[1:].partition(" ")
            cur = {"type": kind.strip(), "name": name.strip(), "props": {}}
            blocks.append(cur)
        elif "=" in line and cur is not None:
            k, _, v = line.partition("=")
            k, v = k.strip(), v.strip()
            if k in cur["props"]:
                old = cur["props"][k]
                cur["props"][k] = (old if isinstance(old, list) else [old]) + [v]
            else:
                cur["props"][k] = v
    return blocks


def _items(v, sep=","):
    vals = v if isinstance(v, list) else [v]
    out = []
    for x in vals:
        out += [p.strip() for p in (x.split(sep) if sep else x.split()) if p.strip()]
    return out


def _per_os(props, key, sep=","):
    """Key, Key.Linux, Key.Windows -> {"all": [...], "linux": [...], "windows": [...]} (empty parts left out)."""
    out = {}
    for scope, k in (("all", key),) + tuple((o, f"{key}.{o.capitalize()}") for o in OSES):
        if k in props:
            out[scope] = _items(props[k], sep)
    return out


def recipe_from_vml(text):
    """A recipe in VML -> the plain structure the build tools use."""
    blocks = parse(text)
    head = next((b for b in blocks if b["type"] == "Recipe"), {"name": "", "props": {}})
    p = head["props"]
    cfg = {"name": p.get("Text") or head["name"]}
    for k in ("Version", "Project", "Icon", "Company", "Launcher", "Installer"):
        if p.get(k):
            cfg[k.lower()] = p[k]
    for key, sep in (("Pip", ","), ("Nuitka", None), ("Extras", ",")):
        v = _per_os(p, key, sep)
        if v:
            cfg[key.lower()] = v
    opt = {}
    for scope, k in (("all", "PipOptional"),) + tuple((o, f"PipOptional.{o.capitalize()}") for o in OSES):
        for entry in _items(p.get(k, []), ";") if k in p else []:
            pkg, _, flag = entry.partition(":")
            opt.setdefault(scope, {})[pkg.strip()] = flag.strip()
    if opt:
        cfg["pip_optional"] = opt
    msix = next((b for b in blocks if b["type"] == "Msix"), None)
    if msix:
        m = msix["props"]
        cfg["msix"] = {"manifest": m.get("Manifest", ""), "identity": m.get("Identity", ""),
                       "publisher": m.get("Publisher", ""), "publisher_display": m.get("PublisherDisplay", ""),
                       "copies": [[a.strip(), b.strip()] for c in _items(m.get("Copy", []), ";")
                                  for a, _, b in [c.partition(">")] if b]}
    cfg["builds"] = []
    for b in blocks:
        if b["type"] != "Build":
            continue
        q = b["props"]
        build = {"name": q.get("Text") or b["name"], "machine": q.get("Machine", "here"), "kind": q.get("Kind", "compiled")}
        for k in ("Run", "Results", "Platform", "Tag", "Workflow", "Repo", "Form"):
            if q.get(k):
                build[k.lower()] = q[k]
            for o in OSES:                                   # Run.Windows, Results.Linux: for one OS only
                if q.get(f"{k}.{o.capitalize()}"):
                    build[f"{k.lower()}_{o}"] = q[f"{k}.{o.capitalize()}"]
        if q.get("AssetsRepo"):
            build["assets_repo"] = q["AssetsRepo"]
        for k, key in (("Platforms", "platforms"), ("Assets", "assets"), ("AssetFiles", "asset_files")):
            if q.get(k):
                build[key] = _items(q[k])
        cfg["builds"].append(build)
    return cfg


def _ident(text):
    return re.sub(r"[^A-Za-z0-9_]", "", text.title().replace(" ", "")) or "Build"


def recipe_to_vml(cfg, title=None):
    """The plain structure -> a recipe in VML (what --new writes, and --to-vml)."""
    name = cfg.get("name") or "App"
    out = [f"# {title or name + ': what Bob builds, and where (see tools/bob/recipe.py)'}", "", f"@Recipe {_ident(name)}"]
    if _ident(name) != name:
        out.append(f"Text={name}")
    for k in ("version", "project", "icon", "company", "launcher", "installer"):
        if cfg.get(k):
            out.append(f"{k.capitalize()}={cfg[k]}")
    for key, sep in (("pip", ", "), ("nuitka", " "), ("extras", ", ")):
        v = cfg.get(key) or {}
        if isinstance(v, list):
            v = {"all": v}
        for scope in ("all",) + OSES:
            if v.get(scope):
                suffix = "" if scope == "all" else "." + scope.capitalize()
                out.append(f"{key.capitalize() if key != 'pip' else 'Pip'}{suffix}={sep.join(v[scope])}")
    for scope, pkgs in (cfg.get("pip_optional") or {}).items():
        suffix = "" if scope == "all" else "." + scope.capitalize()
        out.append(f"PipOptional{suffix}=" + "; ".join(f"{k}: {f}" if f else k for k, f in pkgs.items()))
    m = cfg.get("msix")
    if m:
        out += ["", "@Msix Store", f"Manifest={m.get('manifest', '')}", f"Identity={m.get('identity', '')}",
                f"Publisher={m.get('publisher', '')}", f"PublisherDisplay={m.get('publisher_display', '')}"]
        out += [f"Copy={a} > {b}" for a, b in m.get("copies") or []]
    for b in cfg.get("builds") or []:
        out += ["", f"@Build {_ident(b['name'])}"]
        if _ident(b["name"]) != b["name"]:
            out.append(f"Text={b['name']}")
        out += [f"Machine={b.get('machine', 'here')}", f"Kind={b.get('kind', 'compiled')}"]
        for k in ("run", "results", "platform", "tag", "workflow", "repo"):
            if b.get(k):
                out.append(f"{k.capitalize()}={b[k]}")
            for o in OSES:
                if b.get(f"{k}_{o}"):
                    out.append(f"{k.capitalize()}.{o.capitalize()}={b[f'{k}_{o}']}")
        if b.get("platforms"):
            out.append("Platforms=" + ", ".join(b["platforms"]))
        if b.get("assets"):
            out.append("Assets=" + ", ".join(b["assets"]))
        if b.get("assets_repo"):
            out.append(f"AssetsRepo={b['assets_repo']}")
        if b.get("asset_files"):
            out.append("AssetFiles=" + ", ".join(b["asset_files"]))
    return "\n".join(out) + "\n"


def load(path):
    """A recipe from a file: VML (recipe.vml, NAME.recipe.vml), or JSON (bob.json) as before."""
    text = Path(path).read_text(encoding="utf-8")
    if str(path).endswith(".json"):
        return json.loads(text)
    return recipe_from_vml(text)


def machines_from_vml(text):
    return {b["name"]: {k.lower(): v for k, v in b["props"].items()} for b in parse(text) if b["type"] == "Machine"}


def machines_to_vml(ms):
    out = ["# The machines Bob builds on: Host is a name from ~/.ssh/config (or user@address); none for this one.",
           "# OS is linux or windows. Add one, save, and pick the project again in Bob."]
    for name, m in ms.items():
        out += ["", f"@Machine {name}"]
        if m.get("host"):
            out.append(f"Host={m['host']}")
        out.append(f"OS={m.get('os', 'linux')}")
    return "\n".join(out) + "\n"
