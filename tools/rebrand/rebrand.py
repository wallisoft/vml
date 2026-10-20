#!/usr/bin/env python3
"""Rebrand a project from one name to another: rename files, swap every identifier (all case variants),
mint a fresh GUID for the Inno AppId, and report before touching anything.

    python3 rebrand.py --repo ~/projects/airshare --from juska --to kato --also airshare=kato \
                       --literal "Juska KVM=Kato" --keep juska.uk --iss packaging/juska.iss      # dry run
    python3 rebrand.py ... --apply                          # do it (run in a committed repo; reversible with git)

--from X --to Y expands to x->y, X->Y (Title), XUPPER->YUPPER, longest matched first. --also A=B adds a pair.
--literal "Old=New" is verbatim (matched first; good for "Juska KVM"=Kato). --keep SUBSTR protects a substring
(e.g. a domain to retain). --iss FILE mints a fresh AppId GUID.
"""
import argparse
import os
import re
import sys
import uuid
from pathlib import Path

SKIP_DIRS = {".git", "venv", ".venv", "__pycache__", "node_modules", ".mypy_cache", "dist", "build"}
BINARY_EXT = {".png", ".jpg", ".jpeg", ".ico", ".gif", ".webp", ".pdf", ".zip", ".exe", ".dll", ".so",
              ".pyc", ".woff", ".woff2", ".ttf", ".otf", ".mp4", ".wasm"}


def variants(a, b):
    out = []
    for fa, fb in ((a.lower(), b.lower()), (a.capitalize(), b.capitalize()), (a.upper(), b.upper())):
        if fa and (fa, fb) not in out:
            out.append((fa, fb))
    return out


def build_pairs(args):
    pairs = []
    for lit in args.literal or []:
        k, _, v = lit.partition("="); pairs.append((k, v))
    pairs += variants(args.from_, args.to)
    for al in args.also or []:
        k, _, v = al.partition("="); pairs += variants(k, v)
    seen, uniq = set(), []
    for k, v in pairs:
        if k and k not in seen:
            seen.add(k); uniq.append((k, v))
    return sorted(uniq, key=lambda kv: -len(kv[0]))


def swap(text, pairs, keeps):
    """Apply all pairs, with keep-substrings masked so they're left untouched."""
    for i, kw in enumerate(keeps):
        text = text.replace(kw, f"\x00K{i}\x00")
    n = 0
    for k, v in pairs:
        n += text.count(k)
        text = text.replace(k, v)
    for i, kw in enumerate(keeps):
        text = text.replace(f"\x00K{i}\x00", kw)
    return text, n


def rename_name(name, pairs):
    for k, v in pairs:
        if " " not in k:
            name = name.replace(k, v)
    return name


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--from", dest="from_", required=True)
    ap.add_argument("--to", required=True)
    ap.add_argument("--also", action="append")
    ap.add_argument("--literal", action="append")
    ap.add_argument("--iss", action="append")
    ap.add_argument("--keep", action="append")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    keeps = args.keep or []

    repo = Path(os.path.expanduser(args.repo)).resolve()
    if not repo.is_dir():
        sys.exit(f"no such repo: {repo}")
    pairs = build_pairs(args)

    edits, renames = [], []
    for root, dirs, files in os.walk(repo):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fn in files:
            p = Path(root) / fn
            rel = p.relative_to(repo)
            if p.suffix.lower() not in BINARY_EXT:
                try:
                    text = p.read_text(encoding="utf-8")
                except (UnicodeDecodeError, OSError):
                    text = None
                if text is not None:
                    new, n = swap(text, pairs, keeps)
                    if new != text:
                        edits.append((rel, n, new))
            newname = rename_name(fn, pairs)
            if newname != fn:
                renames.append((rel, Path(root).relative_to(repo) / newname))

    guid_changes = []
    for issrel in args.iss or []:
        issp = repo / issrel
        if not issp.exists():
            issp = repo / rename_name(issrel, pairs)
        if issp.exists():
            t = issp.read_text(encoding="utf-8")
            m = re.search(r"AppId=\{\{([0-9A-Fa-f-]{36})", t)
            if m:
                guid_changes.append((issp.relative_to(repo), m.group(1), str(uuid.uuid4()).upper()))

    print(f"REBRAND {repo.name}:  " + ", ".join(f"{k}->{v}" for k, v in pairs))
    if keeps:
        print("  (keeping: " + ", ".join(keeps) + ")")
    print(f"\n{len(renames)} file(s) to rename:")
    for a, b in renames:
        print(f"  {a}  ->  {b}")
    print(f"\n{len(edits)} file(s) with content changes:")
    for rel, n, _ in edits:
        print(f"  {rel}  ({n} occurrence{'s' if n != 1 else ''})")
    print(f"\n{len(guid_changes)} Inno AppId GUID(s) to refresh:")
    for rel, old, new in guid_changes:
        print(f"  {rel}  {old} -> {new}")

    if not args.apply:
        print("\n(dry run — nothing changed. Re-run with --apply)")
        return

    for rel, _, new in edits:
        (repo / rel).write_text(new, encoding="utf-8")
    for rel, old, new in guid_changes:
        p = repo / rel; p.write_text(p.read_text(encoding="utf-8").replace(old, new), encoding="utf-8")
    for a, b in sorted(renames, key=lambda ab: -len(str(ab[0]))):
        (repo / b).parent.mkdir(parents=True, exist_ok=True)
        os.rename(repo / a, repo / b)
    print(f"\nAPPLIED: {len(edits)} edited, {len(renames)} renamed, {len(guid_changes)} GUID(s) refreshed.")


if __name__ == "__main__":
    main()
