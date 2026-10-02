#!/usr/bin/env python3
"""VML: run a form, open the designer, or talk to a running form.

    ./vml.py                       the designer
    ./vml.py myform.vml            run a form
    ./vml.py setup-csharp          (optional) build the C# script host
    ./vml.py html form.vml         write the form as a web page (form.html); add --open to view it
    ./vml.py get txtName Text      talk to the running form: get / set / setting / run / any Vml command
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
first = sys.argv[1] if len(sys.argv) > 1 else ""
if first and not first.startswith("-") and first not in ("setup-csharp", "html") and not first.endswith(".vml") \
        and not os.path.exists(first):
    from vml.client import main as client   # noqa: E402  (no Qt: quick)
    sys.exit(client())
from vml.__main__ import main  # noqa: E402  (the package, not this file: packages win the import)

main()
