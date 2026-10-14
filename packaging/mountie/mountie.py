"""Mountie as a program of its own: the Visualised runtime, running the Mountie project that sits beside it.
(What mountie-release.yml compiles. Run from source it does the same: python packaging/mountie/mountie.py)"""
import sys
from pathlib import Path


def project():
    here = Path(__file__).resolve().parent
    for p in (here / "mountie" / "Mountie.vmlproj", here.parent.parent / "apps" / "mountie" / "Mountie.vmlproj"):
        if p.exists():
            return str(p)
    raise SystemExit("Mountie's own files are missing (Mountie.vmlproj): reinstall it.")


if __name__ == "__main__":
    if "__compiled__" not in globals():                      # from source: the runtime is two folders up
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    if sys.argv[1:2] != ["--serve-drive"] and not any(a.lower().endswith(".vmlproj") for a in sys.argv[1:]):
        sys.argv[1:1] = [project()]
    from vml.__main__ import main
    main()
