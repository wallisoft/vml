"""`vml-parse file.vml` -> SQL on stdout, as the Avalonia engine's Bash scripts expect."""
import sys

from .store import parse_vml

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] == "--export":
        sys.exit("usage: vml-parse <file.vml>   (--export comes later)")
    print(parse_vml(sys.argv[1]))
