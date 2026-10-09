"""
Projects: several forms and modules that make one app, as in Visual Basic's .vbp.

A project is one small text file, MyApp.vmlproj, in the folder that holds the app:

    # Visualised project
    Name=MyApp
    Startup=frmMain.vml
    Form=frmMain.vml
    Form=frmLogin.vml
    Module=helpers.lua
    Database=main=sqlite:data.db

  Form      a form in the app. Any form opens another with Vml("FormOpen", "frmLogin").
  Startup   the form that opens first when the app runs.
  Module    a Lua file of functions (and values) that every form's scripts can use, with no require().
  Database  a database the app uses, opened the first time it's asked for (see vml/data.py).

Each form still has its own Lua state. For a value every form must share, modules and scripts use the Project
table: Project.user = "steve" in one form is Project.user in all of them.
"""
import json
import os
import re
import shutil
import tempfile
from pathlib import Path

ENDING = ".vmlproj"


class Project:
    def __init__(self, path):
        self.path = Path(path).resolve()
        self.name, self.startup = self.path.stem, ""
        self.forms, self.modules, self.databases = [], [], {}

    @property
    def folder(self):
        return self.path.parent

    @classmethod
    def load(cls, path):
        p = cls(path)
        for line in p.path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = (x.strip() for x in line.split("=", 1))
            key = key.lower()
            if key == "name" and value:
                p.name = value
            elif key == "startup":
                p.startup = p.tidy(value)
            elif key == "form" and value and p.tidy(value) not in p.forms:
                p.forms.append(p.tidy(value))
            elif key == "module" and value and p.tidy(value) not in p.modules:
                p.modules.append(p.tidy(value))
            elif key == "database" and "=" in value:
                name, address = (x.strip() for x in value.split("=", 1))
                p.databases[name] = address
        if p.startup and p.startup not in p.forms:
            p.forms.insert(0, p.startup)
        if not p.startup and p.forms:
            p.startup = p.forms[0]
        return p

    def save(self):
        out = ["# Visualised project", f"Name={self.name}"]
        if self.startup:
            out.append(f"Startup={self.startup}")
        out += [f"Form={f}" for f in self.forms] + [f"Module={m}" for m in self.modules]
        out += [f"Database={n}={a}" for n, a in self.databases.items()]
        self.path.write_text("\n".join(out) + "\n", encoding="utf-8")

    @staticmethod
    def tidy(value):
        return re.sub(r"/+", "/", str(value).strip().strip('"').replace("\\", "/"))

    def relative(self, path):
        """A file's path as the project file writes it: relative to the project's folder, with forward slashes."""
        p = Path(os.path.expanduser(str(path)))
        if not p.is_absolute():
            p = self.folder / p
        try:
            return p.resolve().relative_to(self.folder).as_posix()
        except ValueError:
            return None                                   # not inside the project's folder

    def absolute(self, rel):
        return self.folder / rel

    def holds(self, path):
        rel = self.relative(path)
        return rel is not None and (rel in self.forms or rel in self.modules)

    def info(self):
        return {"file": str(self.path), "folder": str(self.folder), "name": self.name, "startup": self.startup,
                "forms": list(self.forms), "modules": list(self.modules), "databases": dict(self.databases)}


def is_designer(form_path):
    """Is this one of the designer's own forms? The designer is a project too (designer/Designer.vmlproj), but it is
    never "the project being run": that is the one it runs for you."""
    try:
        return Path(form_path).resolve().parent == Path(__file__).resolve().parent.parent / "designer"
    except OSError:
        return False


def project_for(form_path):
    """The project a form belongs to: a .vmlproj in the form's folder that lists it. None if there isn't one."""
    form = Path(form_path).resolve()
    try:
        candidates = sorted(form.parent.glob("*" + ENDING))
    except OSError:
        return None
    for c in candidates:
        try:
            p = Project.load(c)
        except OSError:
            continue
        if p.relative(form) in p.forms:
            return p
    return None


class Shared:
    """The Project table every form's scripts see: plain values, shared by the whole app."""

    def __init__(self):
        self.values = {}

    def __getitem__(self, key):
        return self.values.get(str(key))

    def __setitem__(self, key, value):
        if value is None:
            self.values.pop(str(key), None)
        elif isinstance(value, (bool, int, float, str)):
            self.values[str(key)] = value
        else:                                              # a table belongs to the form that made it: keep its text
            self.values[str(key)] = str(value)


class ProjectCommands:
    """Mixed into the Engine. Two sides: running a project (modules, databases, forms by name), and the designer's
    project panel (the Project* commands)."""

    def _init_projects(self):
        self.project = None            # the project being RUN: its modules load into its forms' Lua states
        self.design_project = None     # the project open in the designer
        self.shared = Shared()
        self.home_projects = {}        # a form's path -> the project that lists it (None if none): see _project_of
        self.home_shared = {}          # that project's file -> its own Project table
        self.form_dirs = {}            # scope -> the folder its sibling forms and files are in (previews)
        self.form_overrides = {}       # a form's real path -> the copy to run instead (the one being designed)

    # ------------------------------------------------------------------ running
    def open_project(self, path):
        """Make a project the one being run. Returns its start-up form's path ("" if it has none)."""
        project = path if isinstance(path, Project) else Project.load(path)
        self.project = project
        self.db_specs = {n: (a, str(project.folder)) for n, a in project.databases.items()}
        for name in [n for n in self.databases if n in self.db_specs]:
            self.cmd_DbClose(name)                          # opened again, from the project's address, when next used
        self._lua_paths_add(str(project.folder))
        return str(project.absolute(project.startup)) if project.startup else ""

    def _adopt_project(self, vml_path):
        """A form run on its own (double-clicked, or an exported app's main form) brings its project with it."""
        if self.project is None and self.design_project is None and not is_designer(vml_path):
            found = project_for(vml_path)
            if found is not None:
                self.open_project(found)
                self.log_line(f"project {found.name}: {len(found.forms)} forms, {len(found.modules)} modules")

    def _in_project(self, key):
        """Does a Lua state (named by its form's path, or an instance name) belong to the project being run?"""
        if self.project is None or not key:
            return False
        if str(key).startswith("instance:"):
            return True
        folder = self.form_dirs.get(key) or Path(key).parent
        try:
            Path(folder).resolve().relative_to(self.project.folder)
            return True
        except (ValueError, OSError):
            return False

    def _project_of(self, key):
        """The project whose modules a form's Lua state gets. The project being run, for its forms; otherwise the
        project beside the form that lists it. So a tool that is itself a project (the designer) keeps its own
        modules, and its own Project table, while it runs somebody else's."""
        if not key or str(key).startswith("design:"):
            return None
        if self._in_project(key):
            return self.project
        if str(key).startswith("instance:"):
            return None
        if key in self.form_dirs or key not in self.home_projects:      # (a preview's file is used again for the next form)
            real = key
            if key in self.form_dirs:                        # a preview: a copy of the form being designed, run from elsewhere
                real = next((src for src, copy in self.form_overrides.items() if str(copy) == str(key)), None) \
                    or self.store.get_setting("current_file") or ""
                if not real or str(Path(real).resolve().parent) != str(Path(self.form_dirs[key]).resolve()):
                    real = ""
            try:
                found = project_for(real) if real and Path(real).is_file() else None
            except OSError:
                found = None
            self.home_projects[key] = found
            if found is not None and found.modules:
                self._lua_paths_add(str(found.folder))
        return self.home_projects[key]

    def _load_modules(self, rt, key):
        project = self._project_of(key)
        if project is None:
            return
        from lupa import lua54
        shared = self.shared if project is self.project else self.home_shared.setdefault(str(project.path), Shared())
        rt.globals().Project = lua54.as_itemgetter(shared)
        for rel in project.modules:
            path = project.absolute(rel)
            try:
                code = path.read_text(encoding="utf-8-sig", errors="replace")
                rt.execute(code)
            except Exception as exc:
                self.log_line(f"module {rel}: {exc}")

    def cmd_ProjectName(self):
        """The name of the app that is running ("" for a form on its own)."""
        return self.project.name if self.project is not None else ""

    # ------------------------------------------------------------------ the designer's project
    def _dp(self):
        if self.design_project is None:
            raise RuntimeError("no project is open")
        return self.design_project

    def cmd_ProjectInfo(self):
        """The open project as JSON (file, folder, name, startup, forms, modules, databases), or "" if none is."""
        return json.dumps(self.design_project.info()) if self.design_project is not None else ""

    def cmd_ProjectNew(self, path, name=""):
        path = Path(os.path.expanduser(str(path)))
        if path.suffix.lower() != ENDING:
            path = path.with_name(path.name + ENDING)
        project = Project(path)
        project.name = str(name).strip() or path.stem
        path.parent.mkdir(parents=True, exist_ok=True)
        project.save()
        self.design_project = project
        return str(project.path)

    def cmd_ProjectOpen(self, path):
        try:
            self.design_project = Project.load(os.path.expanduser(str(path)))
        except OSError as exc:
            self.log_line(f"ProjectOpen: {exc}")
            return ""
        return str(self.design_project.path)

    def cmd_ProjectClose(self):
        self.stop_project()
        self.design_project = None

    def cmd_ProjectAdd(self, kind, path):
        """Add a form or a module to the project. A file from outside the project's folder is copied into it.
        Returns the file's path inside the project."""
        project, kind = self._dp(), str(kind).lower()
        if kind not in ("form", "module"):
            raise ValueError(f"unknown kind {kind!r} (form or module)")
        src = Path(os.path.expanduser(str(path)))
        if not src.is_absolute():
            src = project.folder / src
        rel = project.relative(src)
        if rel is None:                                     # from somewhere else: bring a copy into the project
            target = project.folder / src.name
            if not target.exists():
                shutil.copy2(src, target)
            src, rel = target, target.name
        if kind == "module" and not src.exists():
            src.parent.mkdir(parents=True, exist_ok=True)
            src.write_text(f"-- {src.stem}: functions every form in {project.name} can use\n\n", encoding="utf-8")
        group = project.forms if kind == "form" else project.modules
        if rel not in group:
            group.append(rel)
        if kind == "form" and not project.startup:
            project.startup = rel
        project.save()
        return str(project.absolute(rel))

    def cmd_ProjectRemove(self, path):
        """Take a form or module out of the project. The file itself is left where it is."""
        project = self._dp()
        rel = project.relative(path)
        if rel in project.forms:
            project.forms.remove(rel)
            if project.startup == rel:
                project.startup = project.forms[0] if project.forms else ""
        elif rel in project.modules:
            project.modules.remove(rel)
        else:
            return False
        project.save()
        return True

    def cmd_ProjectSetStartup(self, path):
        project = self._dp()
        rel = project.relative(path)
        if rel not in project.forms:
            return False
        project.startup = rel
        project.save()
        return True

    def cmd_ProjectSetName(self, name):
        project = self._dp()
        if str(name).strip():
            project.name = str(name).strip()
            project.save()
        return project.name

    def cmd_ProjectDatabase(self, name, connection=""):
        """Name a database for the project (it opens when first used), or with no address, forget it."""
        project, name = self._dp(), str(name).strip()
        if not re.fullmatch(r"[A-Za-z_]\w*", name):
            return False
        if str(connection).strip():
            project.databases[name] = str(connection).strip()
        else:
            project.databases.pop(name, None)
        project.save()
        return True

    def cmd_ProjectInFolder(self, path):
        """"true" if a file is inside the open project's folder (so it can be part of the project where it is)."""
        return self.design_project is not None and bool(str(path)) and self.design_project.relative(path) is not None

    def use_design_project(self, form_path):
        """Previewing one form of the open project: make its modules and databases available, as saved."""
        project = self.design_project
        if project is not None and form_path and project.relative(form_path) in project.forms:
            self.open_project(Project.load(project.path))
            return True
        return False

    def cmd_ProjectTree(self):
        """The project as a tree's Items: Forms/..., Modules/..., Databases/... (the start-up form is marked)."""
        if self.design_project is None:
            return ""
        p = self.design_project
        out = [f"Forms/{f}" + ("  (start-up)" if f == p.startup else "") for f in p.forms]
        out += [f"Modules/{m}" for m in p.modules] + [f"Databases/{n}" for n in p.databases]
        return ",".join(o.replace(",", " ") for o in out)

    def cmd_ProjectPath(self, item):
        """A tree item ("Forms/frmMain.vml  (start-up)") back to its file's full path ("" for a heading)."""
        if self.design_project is None:
            return ""
        item = str(item).replace("  (start-up)", "")
        group, _, rel = item.partition("/")
        if group in ("Forms", "Modules") and rel:
            return str(self.design_project.absolute(rel))
        return ""

    def cmd_RunProject(self, surface="Surface"):
        """Run the open project from its start-up form. The form being designed is run as it is on screen, saved
        or not; the others come from their files."""
        project = self._dp()
        surf = self._surface(surface)
        if not project.startup:
            raise RuntimeError("the project has no start-up form yet")
        self.stop_project()
        current = self.store.get_setting("current_file")
        preview = (Path(tempfile.gettempdir()) / f"vml-preview-{surf.name}.vml").resolve()
        startup = project.absolute(project.startup).resolve()
        self.open_project(Project.load(project.path))        # as saved, afresh
        self.form_overrides = {}
        designing_startup = bool(current) and Path(current).resolve() == startup
        if current and project.relative(current) in project.forms:
            self.cmd_ExportVml(surf.name, str(preview))
            self.form_overrides[str(Path(current).resolve())] = str(preview)
            self.form_dirs[str(preview)] = str(Path(current).resolve().parent)
        target = preview if designing_startup else startup
        for w in [w for w in self.windows if w.scope == str(preview)]:      # an earlier preview of this form
            w.widget.close()
            self.windows.remove(w)
        self.luas.pop(str(preview), None)
        self.shared.values.clear()
        self.load(target)
        return str(target)

    def stop_project(self):
        """Close what an earlier run left open, and forget its Lua states, so the next run starts clean."""
        if self.project is None:
            return
        for w in [w for w in self.windows if self._in_project(w.scope)]:
            w.widget.close()
            self.windows.remove(w)
        for key in [k for k in self.luas if self._in_project(k)]:
            self.luas.pop(key, None)
        for name in list(self.databases):
            if name in self.db_specs:
                self.cmd_DbClose(name)
        self.project = None
        self.db_specs = {}

    # ------------------------------------------------------------------ choosing a folder
    def cmd_FolderDialog(self, title="Choose a folder", start=""):
        from PySide6.QtWidgets import QFileDialog
        return QFileDialog.getExistingDirectory(self._parent_window(), str(title), os.path.expanduser(str(start)))

    # ------------------------------------------------------------------ importing a whole project from another tool
    def cmd_ImportProject(self, kind, path, folder):
        """Bring a whole project from another tool into a new folder as a Visualised project, using an importer
        from the library. kind: the importer's name ("WinForms", "VB6"), or "" to go by the file's ending.
        Returns JSON: project (the new .vmlproj), summary, and what else the importer reports; or "" if nothing
        could be imported (the setting import_notes then says why). (Pro.)"""
        if not self.needs("import", "Importing projects from other tools"):
            return ""
        source, target = Path(os.path.expanduser(str(path))), Path(os.path.expanduser(str(folder)))
        name = self.importer_for(kind, source, project=True)
        if name is None:
            why = f"there's no importer for {source.suffix or 'that kind of'} projects"
        elif not source.is_file():
            why = f"{source} isn't a file"
        else:
            if target.resolve() == source.resolve().parent:       # the original's own folder: a new one inside it, then
                target = target / (source.stem + "-visualised")
                n = 2
                while target.exists() and any(target.iterdir()):
                    target = target.with_name(f"{source.stem}-visualised-{n}")
                    n += 1
            result = self.run_importer(name, "ImportProject", source.resolve().as_posix(), target.resolve().as_posix())
            why = result.get("error", "")
            if not why and not result.get("project"):
                why = "nothing was imported"
        if why:
            self.log_line(f"{path}: couldn't be imported ({why})")
            self.store.set_setting("import_notes", why)
            return ""
        self.store.set_setting("import_notes", str(result.get("summary", "")))
        self.log_line(f"imported {source.name}: {str(result.get('summary', '')).splitlines()[0] if result.get('summary') else ''}")
        return json.dumps(result)
