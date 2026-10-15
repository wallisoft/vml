"""
vml mcp: Visualised as an MCP server, so an AI assistant (Claude Desktop, Claude Code, anything that speaks MCP)
can make, check and build Visualised apps on this computer: "make me an app that..." to an APK in one conversation.

It talks JSON-RPC over stdin/stdout, one message per line, and needs nothing beyond Visualised itself.
  Claude Code:     claude mcp add visualised -- python3 /path/to/vml.py mcp
  Claude Desktop:  "mcpServers": {"visualised": {"command": "python3", "args": ["/path/to/vml.py", "mcp"]}}

Make: find, make, read, write, check, export to the web, build an APK.
Ship: publish_site puts the app at NAME.vml.onl (its web version, with the APK to download), vml_onl_status lists them.
(Needs a free TinyWeb account's key: vml onl-key YOURKEY, or $TW_KEY.)
"""
import json
import os
import tempfile
import uuid
import zipfile
import subprocess
import sys
from pathlib import Path

PROTOCOL = "2025-06-18"
VML_ONL = os.environ.get("VML_ONL_API", "https://tiny-web.uk/api/vml-onl.php")
HOME = Path(os.environ.get("VML_APPS", "~/visualised")).expanduser()

HELLO = """# {title}: made by Visualised.
@Window {name}
Title={title}
Version=1.0
Width=380
Height=300
OnOpened=Start

@Canvas c
Parent={name}
Background=#FFFFFF

@TextBlock lblTitle
Parent=c
Canvas.Left=20
Canvas.Top=20
Width=340
Height=32
FontSize=22
FontWeight=Bold
Text={title}

@Button btnHello
Parent=c
Canvas.Left=20
Canvas.Top=80
Width=140
Height=40
Content=Say hello
OnClick=SayHello

@Script Start
Interpreter=lua
<<LUA
Clicks = 0
LUA

@Script SayHello
Interpreter=lua
<<LUA
Clicks = Clicks + 1
Vml("SetProperty", "lblTitle", "Text", "Hello! (" .. Clicks .. ")")
LUA
"""


def _schema(props, required=()):
    return {"type": "object", "properties": {k: {"type": t, "description": d} for k, (t, d) in props.items()},
            "required": list(required)}


TOOLS = [
    ("list_apps", "List the Visualised apps (.vml forms and .vmlproj projects) in a folder.",
     _schema({"folder": ("string", f"Folder to look in (default {HOME})")})),
    ("new_app", "Make a new app: a starter form with a title, a button and a script, ready to change.",
     _schema({"name": ("string", "App name, letters and digits (it names the window and the file)"),
              "title": ("string", "Title shown in the app"),
              "folder": ("string", f"Folder to make it in (default {HOME})")}, ["name"])),
    ("read_app", "Read an app's source (a .vml form or .lua module).",
     _schema({"path": ("string", "The file")}, ["path"])),
    ("write_app", "Write an app's source (the whole file). Run check_app after.",
     _schema({"path": ("string", "The file"), "text": ("string", "Its whole new content")}, ["path", "text"])),
    ("check_app", "Check an app: every Lua script compiles, and the form loads and exports. Returns the problems, or OK.",
     _schema({"path": ("string", "The .vml form")}, ["path"])),
    ("export_web", "Export an app as a web page (one self-contained .html that runs in any browser).",
     _schema({"path": ("string", "The .vml form"), "out": ("string", "Where to write the .html (default beside it)")}, ["path"])),
    ("build_apk", "Build an app as an Android APK, signed and ready to install or release. Needs Visualised Pro.",
     _schema({"path": ("string", "The .vml form"), "out": ("string", "Where to write the .apk (default beside it)")}, ["path"])),
    ("publish_site", "Publish an app to its own website, NAME.vml.onl: the app itself at /app/ (it runs in the browser) "
                     "and, with Visualised Pro, its Android APK at /downloads/. The site's front page is kept; a new site "
                     "gets a plain one, to be replaced with a proper page about the app (write index.html and publish it "
                     "with the TinyHost connector's vmlonl_publish). Run again to update the app. Community accounts get "
                     "one site whose name can't change later, so confirm the name with the user first.",
     _schema({"path": ("string", "The .vml form"),
              "site": ("string", "The site name: NAME.vml.onl (3-63 lowercase letters, digits, hyphens)"),
              "apk": ("boolean", "Build and offer the Android app too (default: yes, when the licence allows)")},
             ["path", "site"])),
    ("vml_onl_status", "The user's vml.onl sites, their downloads and their plan (Community or Pro).", _schema({})),
]


class Problem(Exception):
    pass


def _me():
    """How to run this same Visualised: the compiled program, or this source."""
    if "__compiled__" in globals() or getattr(sys, "frozen", False):
        return [sys.executable]
    return [sys.executable, "-m", "vml"]


def _run(*args):
    root = Path(__file__).resolve().parent.parent
    p = subprocess.run(_me() + list(args), cwd=str(root), capture_output=True, text=True, stdin=subprocess.DEVNULL,
                       timeout=600)
    out = (p.stdout + ("\n" + p.stderr if p.stderr.strip() else "")).strip()
    if p.returncode:
        raise Problem(out or f"failed (exit {p.returncode})")
    return out


def _file(path, must=True):
    f = Path(path).expanduser()
    if not f.is_absolute():
        f = HOME / f
    if must and not f.is_file():
        raise Problem(f"No such file: {f}")
    return f


def _scripts(text):
    """(name, line, code) of each Lua script in a form."""
    out, name, start, buf, inside = [], "", 0, [], False
    for n, line in enumerate(text.splitlines(), 1):
        if line.startswith("@Script "):
            name = line.split(None, 1)[1].strip()
        elif line.strip() == "<<LUA":
            inside, start, buf = True, n + 1, []
        elif inside and line.strip() == "LUA":
            inside = False
            out.append((name, start, "\n".join(buf)))
        elif inside:
            buf.append(line)
    return out


def list_apps(folder=""):
    top = Path(folder).expanduser() if folder else HOME
    if not top.is_dir():
        return f"No folder {top} yet (new_app makes it)."
    found = sorted(str(p) for ext in ("*.vml", "*.vmlproj") for p in top.rglob(ext) if ".git" not in p.parts)
    return "\n".join(found) or f"No apps in {top}."


def new_app(name, title="", folder=""):
    if not name.replace("_", "").isalnum() or not name[0].isalpha():
        raise Problem("The name needs to be letters and digits, starting with a letter.")
    top = Path(folder).expanduser() if folder else HOME
    top.mkdir(parents=True, exist_ok=True)
    f = top / f"{name}.vml"
    if f.exists():
        raise Problem(f"{f} is there already.")
    f.write_text(HELLO.format(name=name, title=title or name), encoding="utf-8")
    return f"Made {f}"


def read_app(path):
    return _file(path).read_text(encoding="utf-8")


def write_app(path, text):
    f = _file(path, must=False)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(text, encoding="utf-8")
    return f"Wrote {f} ({len(text)} characters). Run check_app next."


def check_app(path):
    f = _file(path)
    problems = []
    try:
        from lupa import LuaRuntime
        lua = LuaRuntime()
        compile_ = lua.eval("function(code, name) local f, e = load(code, name); return e end")
        texts = [(f.name, f.read_text(encoding="utf-8"))]
        for name, line, code in _scripts(texts[0][1]):
            err = compile_(code, f"@Script {name}")
            if err:
                problems.append(f"Script {name} (from line {line}): {err}")
        for mod in sorted(f.parent.glob("*.lua")):
            err = compile_(mod.read_text(encoding="utf-8"), mod.name)
            if err:
                problems.append(f"{mod.name}: {err}")
    except ImportError:
        problems.append("(Lua scripts not checked: lupa isn't installed)")
    if f.suffix == ".vml":
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            try:
                _run("html", str(f), os.path.join(tmp, "check.html"))
            except Problem as exc:
                problems.append(f"The form doesn't load: {exc}")
    return "\n".join(problems) if problems else f"OK: {f.name} loads and its scripts compile."


def export_web(path, out=""):
    f = _file(path)
    return _run("html", str(f), str(Path(out).expanduser()) if out else str(f.with_suffix(".html")))


def build_apk(path, out=""):
    f = _file(path)
    return _run("apk", str(f), str(Path(out).expanduser()) if out else str(f.with_suffix(".apk")))


def _tinyweb_key():
    from . import licence
    key = os.environ.get("TW_KEY") or licence.load_prefs().get("tinyweb_key", "")
    if not key:
        raise Problem("This needs a TinyWeb key: sign up free at https://tiny-web.uk (an email and a text), then on this "
                      "computer run:  vml onl-key YOURKEY")
    return key


def _call(method="GET", fields=None, files=None):
    """The vml.onl endpoint: fields (text) and files ({field: path}) as multipart; the JSON reply."""
    import urllib.error
    import urllib.request
    data, headers = None, {"Authorization": "Bearer " + _tinyweb_key(), "User-Agent": "Visualised-MCP"}
    if method == "POST":
        edge = uuid.uuid4().hex
        parts = []
        for k, v in (fields or {}).items():
            parts.append(f'--{edge}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
        for k, path in (files or {}).items():
            parts.append(f'--{edge}\r\nContent-Disposition: form-data; name="{k}"; filename="{Path(path).name}"\r\n'
                         f'Content-Type: application/octet-stream\r\n\r\n'.encode() + Path(path).read_bytes() + b"\r\n")
        data = b"".join(parts) + f"--{edge}--\r\n".encode()
        headers["Content-Type"] = f"multipart/form-data; boundary={edge}"
    req = urllib.request.Request(VML_ONL, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode())
        except ValueError:
            return {"ok": False, "error": f"vml.onl answered {e.code}"}
    except (urllib.error.URLError, OSError) as e:
        raise Problem(f"Couldn't reach vml.onl: {e}")


def publish_site(path, site, apk=True):
    from . import licence
    f = _file(path)
    notes = []
    with tempfile.TemporaryDirectory() as tmp:
        _run("html", str(f), os.path.join(tmp, "index.html"))
        pages = os.path.join(tmp, "site.zip")
        with zipfile.ZipFile(pages, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(os.path.join(tmp, "index.html"), "app/index.html")     # the app at /app/: the front page is the site's own
        files = {"zip": pages}
        if apk:
            made = os.path.join(tmp, f"{f.stem}.apk")
            try:
                _run("apk", str(f), made)
                files["apk"] = made
            except Problem as exc:
                notes.append(f"(No APK this time: {str(exc).splitlines()[0]})")
        lic = licence.current()
        fields = {"site": site.strip().lower(), "merge": "1"}
        if lic["tier"] != "community":
            fields["licence"] = lic["key"]
        got = _call("POST", fields, files)
    if not got.get("ok"):
        raise Problem(got.get("error") or "vml.onl said no.")
    lines = [f"Live at {got['url']} ({got.get('status')}, {got.get('tier')})"]
    if got.get("apk"):
        lines.append(f"Android app: {got['apk']}")
    if got.get("mail"):
        lines.append(f"Mail: {got['mail']}")
    return "\n".join(lines + notes)


def vml_onl_status():
    got = _call("GET")
    if not got.get("ok"):
        raise Problem(got.get("error") or "vml.onl said no.")
    out = [f"{got['tier'].title()}: {len(got['sites'])} of {got['max_sites']} sites"]
    for s in got["sites"]:
        out.append(f"  {s['url']}" + "".join(f"\n    {d['url']} ({d['bytes'] // 1024} KB)" for d in s.get("downloads", [])))
    return "\n".join(out)


DO = {"publish_site": publish_site, "vml_onl_status": vml_onl_status, "list_apps": list_apps, "new_app": new_app, "read_app": read_app, "write_app": write_app,
      "check_app": check_app, "export_web": export_web, "build_apk": build_apk}


def handle(msg):
    """One JSON-RPC message in; the reply out (None for a notification)."""
    method, mid = msg.get("method", ""), msg.get("id")
    if mid is None:
        return None
    if method == "initialize":
        from . import __version__
        result = {"protocolVersion": msg.get("params", {}).get("protocolVersion") or PROTOCOL,
                  "capabilities": {"tools": {}},
                  "serverInfo": {"name": "visualised", "version": __version__},
                  "instructions": "Visualised makes desktop, web and Android apps from .vml forms with Lua scripts. "
                                  "Start with list_apps or new_app; after changing a form, run check_app."}
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": [{"name": n, "description": d, "inputSchema": s} for n, d, s in TOOLS]}
    elif method == "tools/call":
        p = msg.get("params", {})
        fn = DO.get(p.get("name", ""))
        if not fn:
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32602, "message": f"No tool {p.get('name')}"}}
        try:
            text, bad = fn(**(p.get("arguments") or {})), False
        except (Problem, OSError, TypeError, subprocess.TimeoutExpired) as exc:
            text, bad = str(exc), True
        result = {"content": [{"type": "text", "text": text}], "isError": bad}
    else:
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"No method {method}"}}
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def serve():
    out = sys.stdout
    sys.stdout = sys.stderr                     # anything else printed must not land in the conversation
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            reply = handle(json.loads(line))
        except Exception as exc:                # (a broken message: say so, keep going)
            reply = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": str(exc)}}
        if reply is not None:
            out.write(json.dumps(reply) + "\n")
            out.flush()
