"""vml [form.vml | app.vmlproj] [--db path/to/vml.db] [--shot out.png]   (no form: open the VML designer)
   vml setup-csharp                                         (optional: build the C# script host)
   vml apk form.vml [out.apk]                               (an Android app of its own: Pro)
   vml html form.vml [out.html] [--open] [--cdn] [--no-pass]  (a web page, Lua engine inside it; --cdn: load it online instead;
                                                            --no-pass: leave out this licence's pass for the Link relay)"""
import argparse
import os
import sys
from pathlib import Path

from PySide6.QtCore import QTimer

from .engine import Engine


def main():
    ap = argparse.ArgumentParser(prog="vml")
    ap.add_argument("vml", nargs="?", help="the form to open (default: the VML designer)")
    ap.add_argument("extra", nargs="*", help=argparse.SUPPRESS)
    ap.add_argument("--db", help="project database to use (default: a fresh temporary one)")
    ap.add_argument("--shot", help="save a screenshot of the first window and exit")
    a = ap.parse_known_args()[0]                            # (vml html has options of its own, read below)
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
                made = apk.from_page(page, rest[1] if len(rest) > 1 else str(Path(rest[0]).with_suffix(".apk")), owner=licence.current().get("name", ""))
            except apk.ApkError as exc:
                raise SystemExit(str(exc))
        print(f"{made['path']}\n  {made['package']}, version {made['version']}, {made['size'] // 1024} KB\n  asks the phone for: "
              + ", ".join(p for p in made["permissions"]))
        if made["new_key"]:
            print(f"\nIMPORTANT: your signing key was made just now. Keep a copy of both files, somewhere safe and private:\n  {made['key']}\n  "
                  f"{made['key'][:-4]}.cert\nAndroid only accepts an update to an app if it is signed with the same key.")
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
    if not a.vml:
        a.vml = str(Path(__file__).resolve().parent.parent / "designer" / "designer.vml")
    eng = Engine(a.db)
    if a.vml.lower().endswith(".vmlproj"):                  # a project: its modules and databases, then its start-up form
        start = eng.open_project(a.vml)
        if not start:
            raise SystemExit(f"{a.vml} has no forms yet")
        a.vml = start
    eng.load(a.vml)
    if a.shot:
        def snap():
            eng.windows[0].widget.grab().save(a.shot)
            eng.app.quit()
        QTimer.singleShot(400, snap)
    raise SystemExit(eng.run())


if __name__ == "__main__":
    main()
