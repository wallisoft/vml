"""vml [form.vml] [--db path/to/vml.db] [--shot out.png]   (no form: open the VML designer)"""
import argparse
from pathlib import Path

from PySide6.QtCore import QTimer

from .engine import Engine


def main():
    ap = argparse.ArgumentParser(prog="vml")
    ap.add_argument("vml", nargs="?", help="the form to open (default: the VML designer)")
    ap.add_argument("--db", help="project database to use (default: a fresh temporary one)")
    ap.add_argument("--shot", help="save a screenshot of the first window and exit")
    a = ap.parse_args()
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
