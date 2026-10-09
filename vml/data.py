"""
Data: databases a form can open, and controls that fill themselves from a query.

Databases
    Vml("DbOpen", "main", "sqlite:data.db")              a SQLite file (a path beside the form will do)
    Vml("DbOpen", "sales", "odbc:DSN=Sales;UID=me")       anything with an ODBC driver: SQL Server, MySQL, Access...
    Vml("DbQuery", "main", "SELECT * FROM people WHERE age > ?", 30)      -> JSON, one object per row
    Vml("DbExecute", "main", "UPDATE people SET age = ? WHERE id = ?", 31, 7)
    Vml("DbCopyTable", "sales", "Orders", "main")        a table and its rows, from any database into a SQLite one
    A project can name its databases in the project file, and they open by themselves when first used.

Passwords need not be written down. In any address, ${NAME} is replaced by the environment variable of that name, and
PWD=? asks for the password the first time the app connects:
    odbc:Driver={ODBC Driver 18 for SQL Server};Server=db1;Database=Sales;UID=reports;PWD=?
    odbc:DSN=Sales;UID=${SALES_USER};PWD=${SALES_PASSWORD}
    odbc:Driver={ODBC Driver 18 for SQL Server};Server=db1;Database=Sales;Trusted_Connection=Yes     (Windows sign-in)

ItemsSource
    A ListBox, ComboBox, DataGrid or TreeView with ItemsSource fills itself, and fills itself again whenever a
    control it names changes:

        @ComboBox cboCategory
        ItemsSource=SELECT DISTINCT category FROM questions ORDER BY 1

        @ListBox lstQuestion
        ItemsSource=SELECT question FROM questions WHERE category = {cboCategory}

    {cboCategory} is that control's current choice ({txtName} a text box's text, {chkAll} "true" or "false",
    {grid.SelectedItem} any property by name). Values are passed to the database as parameters, never pasted
    into the SQL, so a quote in a name can't break the query. ItemsSource can also name a script,
    ItemsSource=LoadQuestions(cboCategory), which returns a JSON array or one item per line.
"""
import json
import os
import re
import sqlite3
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (QAbstractButton, QComboBox, QLineEdit, QListWidget, QPlainTextEdit, QTableWidget,
                               QTreeWidget)

from .registry import set_item_list

ENV = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
ASKED = re.compile(r"(?i)\b(pwd|password)\s*=\s*\?\s*(?=;|$)")
REF = re.compile(r"\{\s*([A-Za-z_]\w*)(?:\.([A-Za-z_][\w.]*))?\s*\}")
CALL = re.compile(r"^\s*([A-Za-z_]\w*)\s*(?:\((.*)\))?\s*$")
SQLITE_ENDINGS = (".db", ".db3", ".sqlite", ".sqlite3", ".s3db")
OWN_VALUE = {"ComboBox": "SelectedItem", "ListBox": "SelectedItem", "TreeView": "SelectedItem", "DataGrid": "SelectedValue",
             "CheckBox": "IsChecked", "RadioButton": "IsChecked", "Button": "Content"}


def plain(value):
    """A database value as something JSON and a list box can both hold."""
    if value is None or isinstance(value, (int, float, str)):
        return value
    if isinstance(value, (bytes, bytearray, memoryview)):
        return f"({len(bytes(value))} bytes)"
    return str(value)                                       # dates, decimals, GUIDs...


def _sql_type(kind):
    """The SQLite type for a column, from the Python type its driver hands its values back as."""
    import datetime
    import decimal
    if kind in (int, bool):
        return "INTEGER"
    if kind in (float, decimal.Decimal):
        return "REAL"
    if kind in (bytes, bytearray):
        return "BLOB"
    if kind in (datetime.datetime, datetime.date, datetime.time):
        return "DATETIME"
    return "TEXT" if kind is not None else ""


def _storable(value):
    """A value from any database as one SQLite will keep: dates as text, decimals as numbers."""
    import datetime
    import decimal
    if value is None or isinstance(value, (int, float, str, bytes)):
        return value
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, datetime.datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, (datetime.date, datetime.time)):
        return value.isoformat()
    if isinstance(value, (bytearray, memoryview)):
        return bytes(value)
    return str(value)


def hide_password(text):
    """Any text that might hold a connection string, with the password in it blanked."""
    return re.sub(r"(?i)\b(pwd|password)\s*=\s*(\{(?:[^}]|\}\})*\}|[^;'\"]*)", r"\1=***", str(text))


class Database:
    """One open database. kind is "sqlite" or "odbc"."""

    def __init__(self, name, spec, base_dir="."):
        self.name, self.spec = name, str(spec).strip()
        kind, _, rest = self.spec.partition(":")
        kind = kind.strip().lower()
        if kind == "sqlite":
            self.kind, target = "sqlite", rest.strip()
        elif kind == "odbc":
            self.kind, target = "odbc", rest.strip()
        elif self.spec.lower().endswith(SQLITE_ENDINGS):
            self.kind, target = "sqlite", self.spec
        elif "=" in self.spec:                              # DSN=...; or Driver={...};Server=...
            self.kind, target = "odbc", self.spec
        else:
            raise ValueError(f"'{spec}' isn't a database address: use sqlite:file.db or odbc:DSN=name")
        if self.kind == "sqlite":
            path = Path(os.path.expanduser(target))
            if target != ":memory:" and not path.is_absolute():
                path = Path(base_dir) / path
            self.where = ":memory:" if target == ":memory:" else str(path)
            self.db = sqlite3.connect(self.where, isolation_level=None)
        else:
            try:
                import pyodbc
            except ImportError as exc:
                raise RuntimeError("ODBC isn't available on this computer. On Linux, install unixODBC "
                                   f"(sudo apt install unixodbc) and the driver for your database. ({exc})") from None
            self.where = hide_password(target)                # never log a password
            self.db = pyodbc.connect(target if "=" in target else f"DSN={target}", autocommit=True)

    def query(self, sql, params=()):
        cur = self.db.cursor()
        cur.execute(sql, list(params))
        cols = [d[0] for d in cur.description] if cur.description else []
        rows = [[plain(v) for v in row] for row in cur.fetchall()] if cols else []
        cur.close()
        return cols, rows

    def execute(self, sql, params=()):
        cur = self.db.cursor()
        cur.execute(sql, list(params))
        n = cur.rowcount
        cur.close()
        return n

    def tables(self, views=True):
        kinds = ("table", "view") if views else ("table",)
        if self.kind == "sqlite":
            marks = ",".join("?" * len(kinds))
            return [r[0] for r in self.query(f"SELECT name FROM sqlite_master WHERE type IN ({marks}) "
                                             "AND name NOT LIKE 'sqlite_%' ORDER BY name", kinds)[1]]
        cur = self.db.cursor()
        names = sorted(r.table_name for r in cur.tables() if str(r.table_type).lower() in kinds)
        cur.close()
        return names

    def quoted(self, name):
        """A table or column name, safe to put in SQL for this kind of database."""
        name = str(name)
        return '"' + name.replace('"', '""') + '"' if self.kind == "sqlite" else "[" + name.replace("]", "]]") + "]"

    def close(self):
        try:
            self.db.close()
        except Exception:
            pass


class OwnStore:
    """The form's own working database (what SqlQuery and SqlExecute use), seen as a Database."""
    name, kind, where = "", "sqlite", "(the form's own)"

    def __init__(self, store):
        self.db = store.db

    query = Database.query
    execute = Database.execute
    tables = Database.tables
    quoted = Database.quoted

    def close(self):
        pass


class DataCommands:
    """Mixed into the Engine: the Db* commands and ItemsSource."""

    def _init_data(self):
        self.databases = {}            # name -> Database
        self.db_specs = {}             # name -> (address, folder): named by a project, opened when first used
        self.db_error = ""
        self._sources = {}             # scope -> {control name: node}
        self._watched = set()          # (scope, control name) whose changes are already being listened for
        self._opened_scopes = set()
        self._filling = 0

    # ------------------------------------------------------------------ databases
    def _address(self, name, spec):
        """An address ready to connect with: ${NAME} filled in from the environment, and a password written as
        PWD=? asked for. Neither is ever stored or logged."""
        def env(m):
            if m.group(1) not in os.environ:
                raise LookupError(f"the address of '{name}' uses ${{{m.group(1)}}}, and no environment variable of that name is set")
            return os.environ[m.group(1)]
        spec = ENV.sub(env, str(spec))
        if ASKED.search(spec):
            user = re.search(r"(?i)\b(?:uid|user(?:name| id)?)\s*=\s*([^;]*)", spec)
            word = self.cmd_PromptDialog(f"Password for {name}", f"The database '{name}' needs a password"
                                         + (f" for {user.group(1).strip()}" if user and user.group(1).strip() else "")
                                         + ".\n\nIt is used to connect now, and isn't saved.", "", "true")
            if not word:
                raise PermissionError(f"no password was given for '{name}'")
            if re.search(r"[;{}]", word):
                word = "{" + word.replace("}", "}}") + "}"
            spec = ASKED.sub(lambda m: f"{m.group(1)}={word}", spec)
        return spec

    def _db(self, name=""):
        name = str(name or "")
        if not name:
            if self.db_specs:
                name = next(iter(self.db_specs))            # a project's first database is its main one
            else:
                return OwnStore(self.store)
        if name not in self.databases:
            if name not in self.db_specs:
                raise LookupError(f"no database called '{name}' is open (DbOpen it first, or name it in the project)")
            spec, folder = self.db_specs[name]
            self.databases[name] = Database(name, self._address(name, spec), folder)
            self.log_line(f"database {name}: opened {self.databases[name].where}")
        return self.databases[name]

    def cmd_DbOpen(self, name, connection):
        """Open a database under a name. connection: sqlite:file.db (or just a path ending .db, .sqlite, .s3db),
        or odbc:DSN=name;UID=...;PWD=... (any ODBC connection string). Returns "true", or "" with DbError saying why."""
        name = str(name).strip()
        if not re.fullmatch(r"[A-Za-z_]\w*", name):
            self.db_error = f"'{name}' isn't a usable database name (letters, digits and _)"
            return ""
        self.cmd_DbClose(name)
        try:
            self.databases[name] = Database(name, self._address(name, connection), self.asset_dir())
        except Exception as exc:
            self.db_error = hide_password(exc)
            self.log_line(f"DbOpen {name}: {hide_password(exc)}")
            return ""
        self.db_error = ""
        self.log_line(f"database {name}: opened {self.databases[name].where}")
        self._requery_database(name)
        return "true"

    def cmd_DbClose(self, name):
        db = self.databases.pop(str(name), None)
        if db is not None:
            db.close()
            return True
        return False

    def cmd_DbQuery(self, name, sql, *params):
        """Rows as JSON, one object per row. "" as the name means the project's main database, or the form's own."""
        try:
            cols, rows = self._db(name).query(str(sql), params)
        except Exception as exc:
            self.db_error = hide_password(exc)
            self.log_line(f"DbQuery {name or '(default)'}: {hide_password(exc)}")
            return "[]"
        self.db_error = ""
        return json.dumps([dict(zip(cols, r)) for r in rows])

    def cmd_DbExecute(self, name, sql, *params):
        """Run a statement that changes data. Returns how many rows it touched, or "" with DbError saying why."""
        try:
            n = self._db(name).execute(str(sql), params)
        except Exception as exc:
            self.db_error = hide_password(exc)
            self.log_line(f"DbExecute {name or '(default)'}: {hide_password(exc)}")
            return ""
        self.db_error = ""
        return n

    def cmd_DbError(self):
        """Why the last Db command failed, or "" if it worked."""
        return self.db_error

    def cmd_DbTables(self, name="", kind=""):
        """The tables and views of a database, as a JSON list of names. kind "tables" leaves the views out."""
        try:
            return json.dumps(self._db(name).tables(views=str(kind).strip().lower() != "tables"))
        except Exception as exc:
            self.db_error = hide_password(exc)
            return "[]"

    def cmd_DbCopyTable(self, source, table, target, new_name=""):
        """Copy a table, its columns and all its rows, from one open database into a SQLite one (to bring data
        out of Access or a server into a file the app can carry with it). The table must not be there already.
        Returns how many rows were copied, or "" with DbError saying why."""
        try:
            src, dst = self._db(source), self._db(target)
            if dst.kind != "sqlite":
                raise ValueError("the database copied into has to be a SQLite one")
            new = str(new_name or table)
            if new.lower() in (t.lower() for t in dst.tables()):
                raise ValueError(f"there's already a table called {new} in {target}")
            cur = src.db.cursor()
            cur.execute(f"SELECT * FROM {src.quoted(table)}")
            cols = [d[0] for d in cur.description or []]
            if not cols:
                raise ValueError(f"{table} has no columns to copy")
            declared = {}
            if src.kind == "sqlite":
                declared = {r[1]: r[2] for r in src.db.execute(f"PRAGMA table_info({src.quoted(table)})")}
            kinds = [declared.get(d[0]) or _sql_type(d[1]) for d in cur.description]
            dst.db.execute("BEGIN")
            try:
                dst.db.execute(f"CREATE TABLE {dst.quoted(new)} (" +
                               ", ".join(f"{dst.quoted(c)} {k}".rstrip() for c, k in zip(cols, kinds)) + ")")
                put = f"INSERT INTO {dst.quoted(new)} VALUES ({','.join('?' * len(cols))})"
                count, batch = 0, []
                for row in cur:                              # one at a time: some drivers go round again if asked for many
                    batch.append([_storable(v) for v in row])
                    if len(batch) == 500:
                        dst.db.executemany(put, batch)
                        count, batch = count + 500, []
                dst.db.executemany(put, batch)
                count += len(batch)
                dst.db.execute("COMMIT")
            except Exception:
                dst.db.execute("ROLLBACK")
                raise
            finally:
                cur.close()
        except Exception as exc:
            self.db_error = hide_password(exc)
            self.log_line(f"DbCopyTable {table}: {hide_password(exc)}")
            return ""
        self.db_error = ""
        return count

    def cmd_DbList(self):
        """The databases this app knows: open ones, and those its project names."""
        names = list(self.db_specs) + [n for n in self.databases if n not in self.db_specs]
        return json.dumps([{"name": n, "open": n in self.databases,
                            "kind": self.databases[n].kind if n in self.databases else ""} for n in names])

    def cmd_DbSources(self):
        """The ODBC data sources (DSNs) set up on this computer, as JSON: [{name, driver}]."""
        try:
            import pyodbc
            return json.dumps([{"name": n, "driver": d} for n, d in sorted(pyodbc.dataSources().items())])
        except Exception:
            return "[]"

    def cmd_DbTest(self, connection, folder=""):
        """Try an address without keeping it open. Returns JSON: {ok, kind, tables (how many), error}.
        folder: where a SQLite file given without one is looked for (the open project's folder if left out)."""
        base = str(folder or "") or (str(self.design_project.folder) if getattr(self, "design_project", None) else self.asset_dir())
        spec = str(connection).strip()
        try:
            kind = spec.partition(":")[0].strip().lower()
            if kind == "sqlite" or (kind != "odbc" and spec.lower().endswith(SQLITE_ENDINGS)):
                target = Path(os.path.expanduser(spec.partition(":")[2].strip() if kind == "sqlite" else spec))
                if str(target) != ":memory:" and not (target if target.is_absolute() else Path(base) / target).is_file():
                    raise FileNotFoundError(f"{target} isn't there yet (it will be made, empty, the first time the app uses it)")
            db = Database("test", self._address("this database", spec), base)
            try:
                found = len(db.tables())
            finally:
                db.close()
            return json.dumps({"ok": True, "kind": db.kind, "tables": found, "error": ""})
        except Exception as exc:
            return json.dumps({"ok": False, "kind": "", "tables": 0, "error": hide_password(exc)})

    def cmd_DbDrivers(self):
        """The ODBC drivers installed on this computer (empty if ODBC itself isn't)."""
        try:
            import pyodbc
            return json.dumps(sorted(pyodbc.drivers()))
        except Exception:
            return "[]"

    # ------------------------------------------------------------------ ItemsSource
    def source_changed(self, node):
        """A control's ItemsSource or Database was set: remember it, and fill it if its form is already open."""
        if str(node.scope).startswith("design:"):
            return
        if str(node.props.get("ItemsSource") or "").strip():
            self._sources.setdefault(node.scope, {})[node.name] = node
            if node.scope in self._opened_scopes:
                QTimer.singleShot(0, lambda: self._fill(node))
        else:
            self._sources.get(node.scope, {}).pop(node.name, None)

    def sources_opened(self, scope):
        """A form is on screen and its OnOpened has run: fill everything that fills itself."""
        self._opened_scopes.add(scope)
        for node in list(self._sources.get(scope, {}).values()):
            self._fill(node)

    def cmd_Requery(self, control=""):
        """Fill a control from its ItemsSource again (after the data changed); with no name, every one in this form."""
        if control:
            node = self._node(control)
            self._fill(node)
            return True
        for node in list(self._sources.get(self.active_scope(), {}).values()):
            self._fill(node)
        return True

    def _requery_database(self, name):
        for scope in list(self._opened_scopes):
            for node in list(self._sources.get(scope, {}).values()):
                if str(node.props.get("Database") or "") == name:
                    self._fill(node)

    def value_of(self, node, prop=""):
        prop = prop or OWN_VALUE.get(node.type.name, "Text")
        p = node.type.props.get(prop)
        if p is not None and p.read:
            v = p.read(node)
        else:
            v = node.props.get(prop, "")
        return "" if v is None else v

    def _source_plan(self, node):
        """(kind, text, refs): kind "script" (text = its name, refs = its arguments) or "sql" (text has ? for each ref)."""
        src = str(node.props.get("ItemsSource") or "").strip()
        m = CALL.match(src)
        if m and self.runnable(m.group(1), node):
            args = [a.strip().strip("'\"") for a in (m.group(2) or "").split(",") if a.strip()]
            return "script", m.group(1), [(a, "") for a in args]
        refs = [(r.group(1), r.group(2) or "") for r in REF.finditer(src)]
        return "sql", REF.sub("?", src), refs

    def _fill(self, node):
        if self._filling > 20:                              # two controls each waiting on the other
            return
        try:
            if node.widget is None or self.scopes.get(node.scope, {}).get(node.name) is not node:
                self._sources.get(node.scope, {}).pop(node.name, None)
                return
            kind, text, refs = self._source_plan(node)
        except RuntimeError:                                # the control has gone
            self._sources.get(node.scope, {}).pop(node.name, None)
            return
        values = []
        for name, prop in refs:
            dep = self.scopes.get(node.scope, {}).get(name)
            if dep is None:
                values.append(name if kind == "script" else "")       # a script's plain argument; an unknown control
                if kind == "sql":
                    self.log_line(f"{node.name}.ItemsSource names {{{name}}}, and there's no control called that")
                continue
            self._watch(node.scope, dep)
            values.append(self.value_of(dep, prop))
        self._filling += 1
        try:
            if kind == "script":
                cols, rows = self._rows_from(self.run_script(text, *values, origin=node))
            else:
                try:
                    cols, rows = self._db(node.props.get("Database")).query(text, values)
                    self.db_error = ""
                except Exception as exc:
                    self.db_error = hide_password(exc)
                    self.log_line(f"{node.name}.ItemsSource: {hide_password(exc)}")
                    cols, rows = [], []
            self._show(node, cols, rows)
        finally:
            self._filling -= 1

    @staticmethod
    def _rows_from(result):
        """What a script handed back, as (columns, rows): a JSON array of objects, arrays or plain values, or lines."""
        text = "" if result is None else str(result)
        try:
            data = json.loads(text) if text.strip()[:1] in ("[", "{") else None
        except ValueError:
            data = None
        if isinstance(data, dict):                          # an empty Lua table encodes as {}
            data = list(data.values())
        if data is None:
            return ["Item"], [[ln] for ln in text.split("\n") if ln.strip()]
        if data and all(isinstance(d, dict) for d in data):
            cols = list(data[0])
            return cols, [[plain(d.get(c)) for c in cols] for d in data]
        if data and all(isinstance(d, list) for d in data):
            return [f"Column{i + 1}" for i in range(max(len(d) for d in data))], [[plain(v) for v in d] for d in data]
        return ["Item"], [[plain(d)] for d in data]

    def _show(self, node, cols, rows):
        kind = node.type.name
        first = ["" if r[0] is None else str(r[0]) for r in rows if r]
        if kind == "DataGrid":
            own = [c.strip() for c in str(node.props.get("Columns") or "").split(",") if c.strip()]
            node.widget.set_data(own if own and len(own) == len(cols) else cols, rows)
        elif kind == "TreeView":
            node.widget.set_paths(first)
        elif kind in ("ListBox", "ComboBox"):
            set_item_list(node, first)

    def _watch(self, scope, dep):
        """Listen for a control changing, so that whatever fills itself from it can do so again."""
        key = (scope, dep.name)
        if key in self._watched:
            return
        self._watched.add(key)
        w = dep.widget
        again = lambda *a, s=scope, n=dep.name: self._dependents(s, n)
        if isinstance(w, QComboBox):
            w.currentIndexChanged.connect(again)
        elif isinstance(w, QListWidget):
            w.currentRowChanged.connect(again)
        elif isinstance(w, QTreeWidget):
            w.currentItemChanged.connect(again)
        elif isinstance(w, QTableWidget):
            w.itemSelectionChanged.connect(again)
        elif isinstance(w, QAbstractButton):
            w.toggled.connect(again)
        elif isinstance(w, (QLineEdit, QPlainTextEdit)):
            timer = QTimer(w)                               # typing: wait for a pause before asking the database
            timer.setSingleShot(True)
            timer.setInterval(250)
            timer.timeout.connect(again)
            w.textChanged.connect(lambda *a: timer.start())
            dep.keep.append(timer)

    def _dependents(self, scope, name):
        for node in list(self._sources.get(scope, {}).values()):
            try:
                _, _, refs = self._source_plan(node)
            except RuntimeError:
                continue
            if any(r[0] == name for r in refs):
                self._fill(node)

    def _forget_sources(self, scope, name=None):
        if name is None:
            self._sources.pop(scope, None)
            self._opened_scopes.discard(scope)
            self._watched = {k for k in self._watched if k[0] != scope}
        else:
            self._sources.get(scope, {}).pop(name, None)
            self._watched.discard((scope, name))

    # --- grids and trees, filled by a script
    def cmd_GridSetData(self, name, data, columns=""):
        """Fill a DataGrid from JSON: an array of objects (their keys become the headings) or of arrays.
        columns: headings to show instead, comma-separated."""
        node = self._node(name)
        cols, rows = self._rows_from(data)
        own = [c.strip() for c in str(columns or "").split(",") if c.strip()]
        node.widget.set_data(own if own and len(own) == len(cols) else cols, rows)
        return len(rows)

    def cmd_GridGetData(self, name):
        w = self._node(name).widget
        return json.dumps([dict(zip(w.cols, r)) for r in w.data])
