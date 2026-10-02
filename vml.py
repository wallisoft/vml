#!/usr/bin/env python3
"""VML: run a form, or with no form, open the VML designer.

    ./vml.py                  the designer
    ./vml.py myform.vml       run a form
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from vml.__main__ import main  # noqa: E402  (the package, not this file: packages win the import)

main()
