"""
The importer library, and the general commands importers (and any other script) are written with.

An importer is not part of the engine. It is a VML file with Lua scripts, in designer/importers (the ones that come
with Visualised) or ~/.vml/importers (your own, and the community's):

    @Importer VB6
    Title=Visual Basic 5/6 form
    Files=frm
    ProjectTitle=Visual Basic 5/6 project
    ProjectFiles=vbp

    @Script Library          (optional) run once: functions the other two share
    @Script ImportForm       args[1] = the file, args[2] = a folder for its pictures, or ""
                             returns JSON: {"vml": "...", "notes": ["...", ...]}  or  {"error": "why not"}
    @Script ImportProject    args[1] = the project file, args[2] = the new folder to fill
                             returns JSON: {"project": "the new .vmlproj", "summary": "...", ...}  or  {"error": ...}

An importer can go both ways. The two script names for the way back are part of the format now, so files written
today stay valid, though nothing in 1.0 calls them yet:

    @Script ExportForm       args[1] = a .vml form, args[2] = the file to write in the other tool's format
    @Script ExportProject    args[1] = a .vmlproj, args[2] = the new folder to fill
                             both return JSON: {"files": [...], "notes": [...]}  or  {"error": ...}

The names of the importers that come with Visualised, and of the ones on their way (Delphi, Qt, XAML, HTML), can't be
taken by a file in your own folder: to change a built-in importer, copy it and give the copy a name of its own.

The engine's side is small: find the importers, run one, and put what it hands back on the design surface. What an
importer needs to do its job is here as ordinary Vml() commands, useful to any script: reading and writing files
(text and binary), listing folders, and regular expressions.
"""
import base64
import fnmatch
import json
import os
import re
import shutil
from pathlib import Path

HOME_IMPORTERS = Path.home() / ".vml" / "importers"
RESERVED = ("delphi", "qt", "xaml", "html")              # names kept for importers that are on their way
FLAGS = {"i": re.I, "m": re.M, "s": re.S, "x": re.X}


def _flags(text):
    out = 0
    for ch in str(text or "").lower():
        out |= FLAGS.get(ch, 0)
    return out


class LibraryCommands:
    """Mixed into the Engine."""

    # ------------------------------------------------------------------ regular expressions
    def cmd_RegexMatch(self, pattern, text, flags=""):
        """The first match of a regular expression in some text, as JSON: [whole match, group 1, group 2, ...]
        ("" for a group that took no part). Returns "" if there is no match. flags: any of i (ignore case),
        m (^ and $ match at each line), s (. matches a newline too). Start the pattern with ^ to match from the start."""
        m = re.search(str(pattern), str(text), _flags(flags))
        return json.dumps([m.group(0), *["" if g is None else g for g in m.groups()]]) if m else ""

    def cmd_RegexFindAll(self, pattern, text, flags=""):
        """Every match, as JSON: a list of [whole match, group 1, ...]."""
        return json.dumps([[m.group(0), *["" if g is None else g for g in m.groups()]]
                           for m in re.finditer(str(pattern), str(text), _flags(flags))])

    def cmd_RegexReplace(self, pattern, replacement, text, flags=""):
        r"""The text with every match replaced. In the replacement, \1 is group 1 and so on."""
        return re.sub(str(pattern), str(replacement), str(text), flags=_flags(flags))

    # ------------------------------------------------------------------ files and folders
    def cmd_FileRead(self, path, encoding=""):
        """A text file's contents ("" if it can't be read). With no encoding named, UTF-8 is tried first and, if the
        file isn't UTF-8, Windows-1252 (which older Windows programs wrote)."""
        try:
            raw = self._form_path(path).read_bytes()
        except OSError as exc:
            self.log_line(f"FileRead: {exc}")
            return ""
        if encoding:
            return raw.decode(str(encoding), errors="replace")
        try:
            return raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            return raw.decode("cp1252", errors="replace")

    def cmd_FileWrite(self, path, text=""):
        """Write a text file as UTF-8 (relative paths are beside this form; missing folders are made).
        Returns "true" if it was written."""
        try:
            target = self._form_path(path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(str(text), encoding="utf-8")
            return True
        except OSError as exc:
            self.log_line(f"FileWrite: {exc}")
            return False

    def cmd_FileReadBase64(self, path, offset=0, length=-1):
        """Part (or all) of any file, as base64: for pictures and other files that aren't text."""
        try:
            with open(self._form_path(path), "rb") as f:
                f.seek(max(0, int(float(offset or 0))))
                n = int(float(length))
                return base64.b64encode(f.read() if n < 0 else f.read(n)).decode()
        except (OSError, ValueError) as exc:
            self.log_line(f"FileReadBase64: {exc}")
            return ""

    def cmd_FileWriteBase64(self, path, data):
        """Write a file from base64. Returns "true" if it was written."""
        try:
            target = self._form_path(path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(base64.b64decode(str(data)))
            return True
        except (OSError, ValueError) as exc:
            self.log_line(f"FileWriteBase64: {exc}")
            return False

    def cmd_FileCopy(self, source, target):
        """Copy a file (missing folders are made). Returns "true" if it was copied."""
        try:
            dst = self._form_path(target)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(self._form_path(source), dst)
            return True
        except OSError as exc:
            self.log_line(f"FileCopy: {exc}")
            return False

    def cmd_FileSize(self, path):
        """A file's size in bytes (-1 if it isn't there)."""
        try:
            return self._form_path(path).stat().st_size
        except OSError:
            return -1

    def cmd_FileIsFolder(self, path):
        return self._form_path(path).is_dir()

    def cmd_FileList(self, folder, pattern="*", recursive=""):
        """The files in a folder whose names match a pattern (*.frm), as a JSON list of full paths, sorted.
        Several patterns can be given, separated by ; and recursive ("true") looks in the folders inside too."""
        base = self._form_path(folder)
        patterns = [p.strip().lower() for p in str(pattern or "*").split(";") if p.strip()] or ["*"]
        deep = str(recursive).strip().lower() in ("true", "1", "yes")
        out = []
        try:
            walker = base.rglob("*") if deep else base.glob("*")
            for p in walker:
                if p.is_file() and any(fnmatch.fnmatch(p.name.lower(), pat) for pat in patterns):
                    out.append(p.as_posix())
        except OSError as exc:
            self.log_line(f"FileList: {exc}")
        return json.dumps(sorted(out))

    # ------------------------------------------------------------------ importers
    def importer_dirs(self):
        own = Path(__file__).resolve().parent.parent / "designer" / "importers"
        return [d for d in (own, HOME_IMPORTERS) if d.is_dir()]

    def importers(self):
        """Every importer found, by name: {name: {name, file, title, files, project_title, project_files, ...}}.
        The built-in ones come first and keep their names: one in the user's own folder can't replace them."""
        found = {}
        for folder in self.importer_dirs():
            builtin = folder != HOME_IMPORTERS
            for file in sorted(folder.glob("*.vml")):
                try:
                    rows, props, scripts = self._parsed_importer(file)
                except Exception as exc:
                    self.log_line(f"importer {file.name}: {exc}")
                    continue
                head = next((r for r in rows if r[2] == "Importer"), None)
                if head is None:
                    continue
                if not builtin and (head[3].lower() in found or head[3].lower() in RESERVED):
                    self.log_line(f"importer {file.name}: the name {head[3]} is taken; give it a name of its own")
                    continue
                p = props.get(head[0], {})
                exts = lambda v: [e.strip().lstrip(".").lower() for e in str(v or "").split(",") if e.strip()]
                found[head[3].lower()] = {
                    "name": head[3], "file": str(file), "title": p.get("Title") or head[3],
                    "files": exts(p.get("Files")) if "ImportForm" in scripts else [],
                    "project_title": p.get("ProjectTitle") or (p.get("Title") or head[3]) + " project",
                    "project_files": exts(p.get("ProjectFiles")) if "ImportProject" in scripts else [],
                    "description": p.get("Description", ""), "builtin": builtin,
                    "free": builtin and str(p.get("Free", "")).lower() in ("true", "1", "yes"),   # (only ours can say so)
                    "exports": [n for n in ("ExportForm", "ExportProject") if n in scripts]}
        return found

    def _parsed_importer(self, file):
        """An importer file, parsed; kept until the file changes, so the menu and each import don't read it afresh."""
        from .store import PARSER_LOG
        cache = self.__dict__.setdefault("_importer_cache", {})
        stamp = (file.stat().st_mtime_ns, file.stat().st_size)
        if cache.get(str(file), (None,))[0] != stamp:
            before = len(PARSER_LOG)
            cache[str(file)] = (stamp, self.store.parse_form(str(file)))
            del PARSER_LOG[before:]                           # its "parsed N controls" chatter is nobody's business
        return cache[str(file)][1]

    def cmd_GetImporters(self):
        """The importers available, as JSON: name, title, files (the endings it reads), project_title, project_files."""
        return json.dumps(sorted(self.importers().values(), key=lambda i: i["title"].lower()))

    def cmd_AddImporter(self, path):
        """Add an importer (a .vml file with an @Importer in it) to your own library, ~/.vml/importers.
        Returns "" if it was added, or why it wasn't."""
        source = Path(os.path.expanduser(str(path)))
        try:
            rows, _props, scripts = self.store.parse_form(str(source))
        except Exception as exc:
            return f"that file couldn't be read ({exc})"
        head = next((r for r in rows if r[2] == "Importer"), None)
        if head is None:
            return "that isn't an importer: it has no @Importer line"
        if not {"ImportForm", "ImportProject", "ExportForm", "ExportProject"} & set(scripts):
            return "that importer has no ImportForm or ImportProject script"
        name = head[3].lower()
        taken = self.importers().get(name)
        if name in RESERVED or (taken and taken["builtin"]):
            return (f"the name {head[3]} belongs to an importer that comes with Visualised. "
                    f"Change the @Importer line to a name of its own and add it again")
        try:
            HOME_IMPORTERS.mkdir(parents=True, exist_ok=True)
            target = Path(taken["file"]) if taken else HOME_IMPORTERS / (re.sub(r"[^a-z0-9_-]+", "-", name) + ".vml")
            if source.resolve() != target.resolve():
                shutil.copy2(source, target)
        except OSError as exc:
            return f"it couldn't be copied ({exc})"
        self.log_line(f"added importer {head[3]} ({target})")
        return ""

    def run_importer(self, name, script, *args):
        """Run one of an importer's scripts and return what it hands back, as a dict ({"error": ...} if it failed)."""
        imp = self.importers().get(str(name).lower())
        if imp is None:
            return {"error": f"there's no importer called '{name}'"}
        rows, props, scripts = self._parsed_importer(Path(imp["file"]))
        if script not in scripts:
            return {"error": f"the {imp['name']} importer can't do that (it has no {script} script)"}
        key = "importer:" + imp["file"]
        self.luas.pop(key, None)                             # afresh each time: an edited importer is picked up at once
        rt = self.lua_state(key)
        here = Path(imp["file"]).parent
        places = [here, here / "lib"]                        # its own folder first, then the toolkit that comes with Visualised
        for folder in self.importer_dirs():
            places += [d for d in (folder, folder / "lib") if d not in places]
        for d in reversed(places):
            rt.execute("local d = ...; package.path = d .. '/?.lua;' .. package.path", d.as_posix())
        self._script_stack.append(None)
        try:
            g = rt.globals()
            if "Library" in scripts:
                g.arg = g.args = rt.table_from([])
                rt.execute(scripts["Library"][1])
            g.arg = g.args = rt.table_from([str(a) for a in args])
            result = rt.execute(scripts[script][1], *[str(a) for a in args])
        except Exception as exc:
            self.log_line(f"importer {imp['name']}.{script}: {exc}")
            return {"error": f"the {imp['name']} importer hit a problem: {exc}"}
        finally:
            self._script_stack.pop()
            self.luas.pop(key, None)
        try:
            data = json.loads(str(result)) if result not in (None, "") else None
        except ValueError:
            data = None
        if not isinstance(data, dict):
            return {"error": f"the {imp['name']} importer didn't hand anything back"}
        return data

    def importer_for(self, kind, path="", project=False):
        """The importer to use: the one named, or else the one that reads this kind of file."""
        found = self.importers()
        alias = {"vs": "winforms", "visualstudio": "winforms"}.get(str(kind).lower(), str(kind).lower())
        if alias in found:
            return found[alias]["name"]
        ending = Path(str(path)).suffix.lstrip(".").lower()
        for imp in found.values():
            if ending and ending in (imp["project_files"] if project else imp["files"]):
                return imp["name"]
        return None
