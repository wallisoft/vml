#!/usr/bin/env python3
"""VML: run a form, open the designer, or talk to a running form.

    ./vml.py                       the designer (or, renamed to MyApp, runs MyApp.vml beside it)
    ./vml.py myform.vml            run a form
    ./vml.py myapp.vmlproj         run a project (several forms and modules) from its start-up form
    ./vml.py html form.vml         write the form as a web page (form.html); add --open to view it
    ./vml.py apk form.vml          make the form an Android app of its own (Pro); apk-key: its signing key
    ./vml.py mcp                   Visualised for an AI assistant (an MCP server on stdin/stdout)
    ./vml.py onl-key KEY           the TinyWeb key that publishing to NAME.vml.onl uses
    ./vml.py parse form.vml        print the SQL the parser makes
    ./vml.py --version             which Visualised this is
    ./vml.py setup-csharp          (optional) build the C# script host
    ./vml.py get txtName Text      talk to the running form: get / set / setting / run / any Vml command
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
APP_VERBS = ("setup-csharp", "html", "parse", "apk", "apk-key", "mcp", "onl-key")
first = sys.argv[1] if len(sys.argv) > 1 else ""
if first in ("--version", "-V", "version"):                    # before anything heavy is loaded: just the number
    from vml import __version__
    print("Visualised " + __version__)
    raise SystemExit(0)

def own_app(program):
    """An exported app: this program renamed MyApp(.exe), with MyApp.vmlproj (a project) or MyApp.vml (one form)
    beside it, runs that app."""
    me = Path(program).resolve()
    if me.stem.lower() in ("vml", "vml.py"):
        return None
    for ending in (".vmlproj", ".vml"):
        own = me.with_suffix(ending) if me.suffix.lower() == ".exe" else me.parent / (me.name + ending)
        if own.is_file():
            return own
    return None


def where_am_i():
    """Every reliable answer to "which program am I?" (compiled builds report it in different places)."""
    places = []
    try:
        places.append(os.readlink("/proc/self/exe"))        # Linux: the kernel's own answer
    except OSError:
        pass
    places += [sys.argv[0], sys.executable]
    compiled = globals().get("__compiled__")
    if compiled is not None and getattr(compiled, "original_argv0", None):
        places.append(compiled.original_argv0)               # Nuitka: how this program was started
    return [p for p in places if p]


if (not first or first.startswith("-")) and first != "--serve-drive":   # no form named (options like --shot don't
                                                                         # count; a drive being served isn't an app)
    candidates = where_am_i()
    found = next((f for f in (own_app(c) for c in candidates) if f is not None), None)
    if os.environ.get("VML_DEBUG"):
        print(f"vml: program locations {candidates} -> app {found}", file=sys.stderr)
    if found is not None:
        sys.argv.insert(1, str(found))
        first = str(found)

if first == "parse":
    from vml.store import parse_vml   # noqa: E402
    print(parse_vml(sys.argv[2]) if len(sys.argv) > 2 else "usage: vml parse form.vml")
    sys.exit(0)
if first and not first.startswith("-") and first not in APP_VERBS and not first.endswith((".vml", ".vmlproj")) \
        and not os.path.exists(first):
    from vml.client import main as client   # noqa: E402  (no Qt: quick)
    sys.exit(client())
def crashed(exc_type, exc, tb):
    """A GUI program that dies at start-up dies silently: write down why, and say where."""
    import traceback
    log = Path.home() / ".vml" / "crash.log"
    text = "".join(traceback.format_exception(exc_type, exc, tb))
    try:
        log.parent.mkdir(parents=True, exist_ok=True)
        with open(log, "a", encoding="utf-8") as f:
            import time
            f.write(f"--- {time.strftime('%Y-%m-%d %H:%M:%S')}  {' '.join(sys.argv)}\n{text}\n")
    except OSError:
        pass
    print(text, file=sys.stderr)
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox
        QApplication.instance() or QApplication(sys.argv)
        QMessageBox.critical(None, "Visualised", f"Visualised hit a problem and has to close.\n\n{exc}\n\n"
                                                 f"The details are in:\n{log}")
    except Exception:
        pass


sys.excepthook = crashed
from vml.__main__ import main  # noqa: E402  (the package, not this file: packages win the import)

try:
    main()
except SystemExit:
    raise
except Exception:
    crashed(*sys.exc_info())
    sys.exit(1)
