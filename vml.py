#!/usr/bin/env python3
"""VML: run a form, open the designer, or talk to a running form.

    ./vml.py                       the designer (or, renamed to MyApp, runs MyApp.vml beside it)
    ./vml.py myform.vml            run a form
    ./vml.py html form.vml         write the form as a web page (form.html); add --open to view it
    ./vml.py parse form.vml        print the SQL the parser makes
    ./vml.py setup-csharp          (optional) build the C# script host
    ./vml.py get txtName Text      talk to the running form: get / set / setting / run / any Vml command
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
APP_VERBS = ("setup-csharp", "html", "parse")
first = sys.argv[1] if len(sys.argv) > 1 else ""

if not first:
    # an exported app: this binary renamed MyApp(.exe), with MyApp.vml beside it, runs that app
    me = Path(sys.argv[0]).resolve()
    own = me.with_suffix(".vml") if me.suffix.lower() == ".exe" else me.parent / (me.name + ".vml")
    if own.is_file() and me.stem.lower() not in ("vml", "vml.py"):
        sys.argv.append(str(own))
        first = str(own)

if first == "parse":
    from vml.store import parse_vml   # noqa: E402
    print(parse_vml(sys.argv[2]) if len(sys.argv) > 2 else "usage: vml parse form.vml")
    sys.exit(0)
if first and not first.startswith("-") and first not in APP_VERBS and not first.endswith(".vml") \
        and not os.path.exists(first):
    from vml.client import main as client   # noqa: E402  (no Qt: quick)
    sys.exit(client())
from vml.__main__ import main  # noqa: E402  (the package, not this file: packages win the import)

main()
