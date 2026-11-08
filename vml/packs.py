"""Capability packs: the heavy native libraries behind certain commands, kept
out of the base runtime so it stays lean.

A pack is a hosted zip of wheels for one platform + Python version, downloaded
once into a writable per-user dir and added to sys.path. The base runtime always
carries the COMMANDS; a pack only supplies their libs - so a command is always
present, it just asks for its pack the first time it runs without it.

Free packs install straight away; a Pro pack checks the licence first, which an
AAC or student grant satisfies for free (see licence.allows).

Security note: a pack is executable native code, so a download is verified
against a sha256 in the registry when one is set. For production the registry
(or a manifest beside the zips) should itself be signed like a licence - that
hardening is a TODO; until then only set hashes you control.
"""
import os
import sys
import json
import zipfile
import hashlib
import urllib.request

from . import licence


def _root():
    if sys.platform.startswith("win"):
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        d = os.path.join(base, "Visualised", "packs")
    else:
        d = os.path.join(os.path.expanduser("~"), ".local", "share", "visualised", "packs")
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        pass
    return d


PACKS_DIR = _root()
BASE_URL = os.environ.get("VML_PACKS_URL", "https://visualised.org/packs")  # where built packs are hosted

# The known packs. needs = licence feature/grant ("" is free); provides = the
# imports that prove it's present; sha256 = {platform-tag: hex} when pinned.
REGISTRY = {
    "headmouse": {
        "name": "Head-mouse",
        "needs": "headmouse",
        "provides": ["cv2", "mediapipe"],
        "about": "Webcam head-tracking (MediaPipe + OpenCV) for hands-free cursor and AAC.",
        "sha256": {},
    },
}


def _tag():
    return "%s-cp%d%d" % (
        "win" if sys.platform.startswith("win") else "mac" if sys.platform == "darwin" else "linux",
        sys.version_info[0], sys.version_info[1])


def pack_dir(name):
    return os.path.join(PACKS_DIR, name)


def is_installed(name):
    return os.path.isfile(os.path.join(pack_dir(name), ".installed"))


def has_libs(name):
    import importlib.util
    for mod in REGISTRY.get(name, {}).get("provides", []):
        try:
            if importlib.util.find_spec(mod) is None:
                return False
        except Exception:
            return False
    return True


def ensure_on_path():
    """Put every installed pack's libs on sys.path. Idempotent and cheap - safe to
    call before any command that might need a pack."""
    try:
        for name in os.listdir(PACKS_DIR):
            d = pack_dir(name)
            if os.path.isfile(os.path.join(d, ".installed")) and d not in sys.path:
                sys.path.insert(0, d)
    except OSError:
        pass


def available(name):
    """'' if the pack's libs are importable (installed, or already in the base
    runtime), else 'missing'. A command calls this to decide whether to prompt."""
    ensure_on_path()
    return "" if has_libs(name) else "missing"


def allowed(name):
    """Whether the licence permits this pack. Free packs ('' needs) always pass;
    a Pro pack passes on Pro/Enterprise or an explicit grant (AAC/student)."""
    need = REGISTRY.get(name, {}).get("needs", "")
    return (not need) or licence.allows(need)


def url_for(name):
    return "%s/%s-%s.zip" % (BASE_URL, name, _tag())


def _verify(name, path):
    want = REGISTRY.get(name, {}).get("sha256", {}).get(_tag())
    if not want:
        return True
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest() == want


def install(name, on_progress=None):
    """Fetch + unpack the pack, licence permitting. Returns '' on success, or an
    error string ('unknown pack', 'locked', 'install failed: ...'). Network is
    needed once; after that the pack is local and works offline."""
    say = on_progress or (lambda s: None)
    if name not in REGISTRY:
        return "unknown pack: %s" % name
    if has_libs(name):
        ensure_on_path()
        return ""
    if not allowed(name):
        return "locked"                      # caller offers the AAC/student pass or Pro
    d = pack_dir(name)
    try:
        os.makedirs(d, exist_ok=True)
        tmp = os.path.join(d, "_pack.zip")
        say("downloading %s..." % REGISTRY[name]["name"])
        urllib.request.urlretrieve(url_for(name), tmp)
        if not _verify(name, tmp):
            os.remove(tmp)
            return "install failed: the download didn't match its checksum"
        say("unpacking...")
        with zipfile.ZipFile(tmp) as z:
            z.extractall(d)
        os.remove(tmp)
        open(os.path.join(d, ".installed"), "w").close()
        ensure_on_path()
        say("done")
        return "" if has_libs(name) else "installed, but its libraries still won't import"
    except Exception as e:
        return "install failed: %s" % e


class PackCommands:
    """Mixed into Engine: Vml("Pack", action, name).
        available <name>   '' if present, 'missing' if the pack is needed
        allowed   <name>   '1' if the licence permits it, '' if locked
        install   <name>   install it (licence permitting); '' ok, else error/'locked'
        installed          JSON list of installed pack names
        list               JSON of every known pack {name, needs, installed}
        info      <name>   the pack's registry entry as JSON
        status             the latest install progress line
    """

    def cmd_Pack(self, action="list", name=""):
        action = (action or "list").strip().lower()
        name = (name or "").strip()
        if action in ("available", "check"):
            return available(name)
        if action == "allowed":
            return "1" if allowed(name) else ""
        if action == "install":
            if not allowed(name):
                return "locked"
            return install(name, on_progress=lambda s: setattr(self, "_pack_status", s)) or "ok"
        if action == "installed":
            return json.dumps([n for n in REGISTRY if is_installed(n)])
        if action == "info":
            r = REGISTRY.get(name)
            return json.dumps(r) if r else ""
        if action == "status":
            return getattr(self, "_pack_status", "")
        if action == "list":
            return json.dumps({n: {"name": r["name"], "needs": r.get("needs", ""),
                                   "installed": is_installed(n)} for n, r in REGISTRY.items()})
        return ""
