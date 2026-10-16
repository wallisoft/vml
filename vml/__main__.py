"""vml [form.vml | app.vmlproj] [--db path/to/vml.db] [--shot out.png]   (no form: open the VML designer)
   vml setup-csharp                                         (optional: build the C# script host)
   vml apk form.vml [out.apk] [--new-app]                   (an Android app of its own: Pro)
   vml apk-key [save FILE | restore FILE [--replace]]       (the key your Android apps are signed with: keep a copy)
   vml html form.vml [out.html] [--open] [--cdn] [--no-pass]  (a web page, Lua engine inside it; --cdn: load it online instead;
                                                            --no-pass: leave out this licence's pass for the Link relay)"""
import argparse
import os
import sys
from pathlib import Path

from PySide6.QtCore import QTimer


def _no_console_fix():
    """Windows, in a built app (started from the Start menu, or from a tray): a program run with no stdin given
    inherits an input handle that may not exist, and Python fails with "[WinError 6] The handle is invalid" (net use,
    PowerShell, WinFsp's helpers...). No program Visualised starts needs typing into, so anything left unset gets an
    empty input, always; and an empty output too when there's no console to show it in."""
    if not sys.platform.startswith("win"):
        return
    import subprocess

    def usable(stream):
        try:
            import msvcrt
            return stream is not None and msvcrt.get_osfhandle(stream.fileno()) not in (-1, -2, None)
        except Exception:
            return False
    console = usable(sys.stdout) and usable(sys.stderr)
    original = subprocess.Popen.__init__

    def init(self, *args, **kw):
        if kw.get("stdin") is None:
            kw["stdin"] = subprocess.DEVNULL
        if not console:
            for k in ("stdout", "stderr"):
                if kw.get(k) is None:
                    kw[k] = subprocess.DEVNULL
            kw.setdefault("creationflags", getattr(subprocess, "CREATE_NO_WINDOW", 0))
        original(self, *args, **kw)
    subprocess.Popen.__init__ = init


_no_console_fix()

from .engine import Engine


def main():
    if sys.argv[1:2] == ["--serve-drive"] and len(sys.argv) == 4:   # a built Mountie serving a folder or RAM drive
        from .localdrives import serve
        serve(sys.argv[2], sys.argv[3])
        return
    if sys.argv[1:2] == ["onl-key"]:                                # vml onl-key KEY: the TinyWeb key vml.onl publishing uses
        from . import licence
        if len(sys.argv) != 3 or len(sys.argv[2].strip()) < 20:
            raise SystemExit("usage: vml onl-key YOURKEY   (the key tiny-web.uk sent you when you signed up)")
        prefs = licence.load_prefs()
        prefs["tinyweb_key"] = sys.argv[2].strip()
        licence.save_prefs(prefs)
        print("saved: publish_site (vml.onl) will use it")
        return
    if sys.argv[1:2] == ["mcp"]:                                    # Visualised for an AI assistant (vml/mcp.py)
        from .mcp import serve as serve_mcp
        serve_mcp()
        return
    ap =argparse.ArgumentParser(prog="vml")
    ap.add_argument("vml", nargs="?", help="the form to open (default: the VML designer)")
    ap.add_argument("extra", nargs="*", help=argparse.SUPPRESS)
    ap.add_argument("--db", help="project database to use (default: a fresh temporary one)")
    ap.add_argument("--shot", help="save a screenshot of the first window and exit")
    if any(x in ("--version", "-V") for x in sys.argv[1:]):   # (the compiled program answers this sooner, in vml.py)
        from . import __version__
        print("Visualised " + __version__)
        return
    a = ap.parse_known_args()[0]                            # (vml html has options of its own, read below)
    if a.vml == "apk-key":                                  # vml apk-key [save file | restore file [--replace]]
        from . import apk
        rest = [x for x in sys.argv[2:] if not x.startswith("-")]
        try:
            if rest[:1] == ["save"] and len(rest) == 2:
                print("a copy of your signing key: " + apk.save_key(rest[1]) + "\nKeep it somewhere safe and private.")
            elif rest[:1] == ["restore"] and len(rest) == 2:
                print("signing key restored: " + apk.restore_key(rest[1], replace="--replace" in sys.argv))
            else:
                info = apk.key_info()
                print(info["problem"] or (f"signing key {info['id']}, made {info['made']}, at {info['path']}\n"
                      + ("a copy was saved on " + info["saved"] if info["saved"] else "NO COPY HAS BEEN SAVED: vml apk-key save FILE")
                      if info["exists"] else "no signing key yet: one is made the first time you export an Android app"))
        except apk.ApkError as exc:
            raise SystemExit(str(exc) + (" (To replace it: add --replace.)" if "already a different" in str(exc) else ""))
        return
    if a.vml == "apk":                                      # vml apk form.vml [out.apk]
        import tempfile
        from . import apk, licence
        from .html import export_html
        rest = [x for x in sys.argv[2:] if not x.startswith("-")]
        if not rest:
            raise SystemExit("usage: vml apk form.vml [out.apk]")
        if not licence.allows("export"):
            raise SystemExit("Exporting a form as an Android app is part of Visualised Pro.")
        with tempfile.TemporaryDirectory() as folder:
            page = export_html(rest[0], os.path.join(folder, "index.html"))
            try:
                fresh = {"package": "", "signed_with": ""} if "--new-app" in sys.argv else {}
                made = apk.from_page(page, rest[1] if len(rest) > 1 else str(Path(rest[0]).with_suffix(".apk")), owner=licence.current().get("name", ""), **fresh)
            except apk.OtherKey as exc:
                raise SystemExit(str(exc) + "\n(To export it as a new app from here: add --new-app.)")
            except apk.ApkError as exc:
                raise SystemExit(str(exc))
        apk.remember(rest[0], made["package"], made["key_id"])     # so the next export is an update to this same app
        print(f"{made['path']}\n  {made['package']}, version {made['version']}, {made['size'] // 1024} KB\n  asks the phone for: "
              + ", ".join(p for p in made["permissions"]))
        if not apk.key_info()["saved"]:
            print("\nIMPORTANT: keep a copy of your signing key" + (", which was made just now" if made["new_key"] else "") + ". Android only accepts an update\n"
                  "to an app if it is signed with the same key, and it exists only on this computer. To save a copy as one file:\n"
                  "  vml apk-key save ~/visualised-android-key.pem        (and on another computer: vml apk-key restore that-file)")
        return
    if a.vml == "html":                                     # vml html form.vml [out.html]
        from .html import export_html
        rest = [x for x in sys.argv[2:] if not x.startswith("-")]
        if not rest:
            raise SystemExit("usage: vml html form.vml [out.html]")
        if "--no-pass" in sys.argv:                         # for a page anyone may copy, such as an example: its links go on the free allowance
            os.environ["VML_NO_LINK_PASS"] = "1"
        out = export_html(rest[0], rest[1] if len(rest) > 1 else None, offline="--cdn" not in sys.argv)
        print(out)
        if "--open" in sys.argv:                            # serve it locally and open it in the browser
            import functools
            import webbrowser
            from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
            folder = Path(out).resolve().parent
            server = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(SimpleHTTPRequestHandler, directory=str(folder)))
            url = f"http://127.0.0.1:{server.server_address[1]}/{Path(out).name}"
            print(f"serving at {url}  (Ctrl+C to stop)")
            webbrowser.open(url)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
        raise SystemExit(0)
    if a.vml == "setup-csharp":                             # optional: build the C# script host once
        from . import csharp
        ok, msg = csharp.build()
        print(msg)
        raise SystemExit(0 if ok else 1)
    md = a.extra[0] if a.vml == "md" and a.extra else a.vml if a.vml and a.vml.lower().endswith((".md", ".markdown")) else None
    if md:                                                  # vml README.md (or vml md README.md --edit): the Markdown window
        eng = Engine(a.db)
        if "--edit" in sys.argv:
            eng.cmd_EditMarkdown(md, Path(md).name, save_to=md)
            raise SystemExit(0)
        box = eng._reader(md, Path(md).name)
        if a.shot:
            QTimer.singleShot(600, lambda: (box.grab().save(a.shot), eng.app.quit()))
        raise SystemExit(eng.run())
    if not a.vml:
        a.vml = str(Path(__file__).resolve().parent.parent / "designer" / "designer.vml")
    eng = Engine(a.db)
    if a.vml.lower().endswith(".vmlproj"):                  # a project: its modules and databases, then its start-up form
        start = eng.open_project(a.vml)
        if not start:
            raise SystemExit(f"{a.vml} has no forms yet")
        a.vml = start
    designer = Path(a.vml).resolve() == (Path(__file__).resolve().parent.parent / "designer" / "designer.vml").resolve()
    if not a.db and not designer:                           # an app on its own keeps its settings, as on a phone
        eng.keep_settings(a.vml)
    eng.load(a.vml)
    if a.shot:
        def snap():
            eng.windows[0].widget.grab().save(a.shot)
            eng.app.quit()
        QTimer.singleShot(400, snap)
    raise SystemExit(eng.run())


if __name__ == "__main__":
    main()
