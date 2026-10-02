"""vml [form.vml] [--db path/to/vml.db] [--shot out.png]   (no form: open the VML designer)
   vml setup-csharp                                         (optional: build the C# script host)
   vml html form.vml [out.html] [--open]                    (write the form as a web page; --open serves and opens it)"""
import argparse
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
    a = ap.parse_args()
    if a.vml == "html":                                     # vml html form.vml [out.html]
        from .html import export_html
        rest = [x for x in sys.argv[2:] if not x.startswith("-")]
        if not rest:
            raise SystemExit("usage: vml html form.vml [out.html]")
        out = export_html(rest[0], rest[1] if len(rest) > 1 else None)
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
    eng = Engine(a.db).load(a.vml)
    if a.shot:
        def snap():
            eng.windows[0].widget.grab().save(a.shot)
            eng.app.quit()
        QTimer.singleShot(400, snap)
    raise SystemExit(eng.run())


if __name__ == "__main__":
    main()
