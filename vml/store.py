"""The form database: same schema as the Avalonia engine's per-project vml.db."""
import json
import re
import sqlite3
from pathlib import Path

from lupa import lua54

LUA_DIR = Path(__file__).resolve().parent / "lua"
PARSER_LOG = []          # drained into the engine log after each parse

SCHEMA = """
CREATE TABLE IF NOT EXISTS ui_tree (id INTEGER PRIMARY KEY AUTOINCREMENT, parent_id INTEGER, control_type TEXT NOT NULL,
    name TEXT, source_file TEXT, is_root INTEGER DEFAULT 0, display_order INTEGER DEFAULT 0, imported_at INTEGER,
    UNIQUE(name, source_file), FOREIGN KEY (parent_id) REFERENCES ui_tree(id) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS ui_properties (id INTEGER PRIMARY KEY AUTOINCREMENT, ui_tree_id INTEGER NOT NULL,
    property_name TEXT NOT NULL, property_value TEXT, FOREIGN KEY (ui_tree_id) REFERENCES ui_tree(id) ON DELETE CASCADE);
CREATE UNIQUE INDEX IF NOT EXISTS idx_prop_unique ON ui_properties(ui_tree_id, property_name);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT, description TEXT);
CREATE TABLE IF NOT EXISTS scripts (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE, interpreter TEXT NOT NULL,
    instance TEXT, content TEXT NOT NULL, source_file TEXT, created_at INTEGER);
"""


def parse_vml(vml_path: str) -> str:
    """Run vml-parser.lua, unchanged, inside embedded Lua 5.4; return the SQL it prints."""
    lua = lua54.LuaRuntime(unpack_returned_tuples=True)
    out = []
    lua.globals().print = lambda *a: out.append("\t".join(str(x) for x in a))
    # the parser's progress chatter goes to the log; only its summary and any errors are worth seeing
    def chatter(_self, text):
        for line in str(text).splitlines():
            if line.startswith(("Error", "\u2713 Parsed")):
                PARSER_LOG.append(f"{Path(vml_path).name}: {line.lstrip(chr(0x2713)).strip()}")
    lua.execute("local w = ...; io.stderr = { write = function(self, s) w(self, s) end }", chatter)
    lua.execute("arg = {...}", str(vml_path))
    src = (LUA_DIR / "vml-parser.lua").read_text(encoding="utf-8")
    if src.startswith("#!"):
        src = src.split("\n", 1)[1]
    lua.execute(src)
    return "\n".join(out)


class Store:
    def __init__(self, path):
        self.path = str(path)
        self.db = sqlite3.connect(self.path, isolation_level=None)       # autocommit: scripts' sqlite3 sees changes
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.executescript(SCHEMA)

    def import_vml(self, vml_path):
        """(Re)import a form: any earlier copy of the same file is replaced. A control name declared
        twice is kept for the first and renamed (Name_2) for the next, with a note in the log."""
        vml_path = str(vml_path)
        self.db.execute("DELETE FROM ui_tree WHERE source_file=?", (vml_path,))
        self.db.execute("DELETE FROM scripts WHERE source_file=?", (vml_path,))
        text = Path(vml_path).read_text(encoding="utf-8", errors="replace")
        seen, lines, renamed = {}, text.split("\n"), []
        for i, line in enumerate(lines):
            m = re.match(r"^(\s*@[A-Za-z_][\w]*\s+)([A-Za-z0-9_]+)\s*$", line)
            if not m or m.group(1).strip() in ("@Script", "@Include", "@ForEach", "@If"):
                continue
            name = m.group(2)
            seen[name] = seen.get(name, 0) + 1
            if seen[name] > 1:
                new_name = f"{name}_{seen[name]}"
                lines[i] = m.group(1) + new_name
                renamed.append(f"line {i + 1}: '{name}' is declared again; using '{new_name}' for this one")
        if not renamed:
            sql = parse_vml(vml_path)
        else:
            for note in renamed:
                PARSER_LOG.append(f"{Path(vml_path).name} {note}")
            tmp = Path(vml_path).with_name(f".{Path(vml_path).name}.vmlfix")
            tmp.write_text("\n".join(lines), encoding="utf-8")
            try:
                sql = parse_vml(str(tmp)).replace(str(tmp), vml_path)
                PARSER_LOG[:] = [m.replace(tmp.name, Path(vml_path).name) for m in PARSER_LOG]
            finally:
                tmp.unlink(missing_ok=True)
        self.db.executescript("BEGIN;" + sql + "COMMIT;")

    def parse_form(self, vml_path):
        """Parse a form into a throwaway database: (rows, props by id, scripts by name)."""
        tmp = sqlite3.connect(":memory:")
        tmp.executescript(SCHEMA)
        tmp.executescript(parse_vml(vml_path))
        rows = tmp.execute("SELECT id, parent_id, control_type, name FROM ui_tree ORDER BY display_order").fetchall()
        props = {cid: dict(tmp.execute("SELECT property_name, property_value FROM ui_properties WHERE ui_tree_id=?", (cid,)))
                 for cid, *_ in rows}
        scripts = {n: (i, c) for n, i, c in tmp.execute("SELECT name, interpreter, content FROM scripts")}
        tmp.close()
        return rows, props, scripts

    def template_rows(self, vml_path):
        """Parse a composite-control file into a throwaway database and return its rows."""
        tmp = sqlite3.connect(":memory:")
        tmp.executescript(SCHEMA)
        tmp.executescript(parse_vml(vml_path))
        rows = tmp.execute("SELECT t.id, t.parent_id, t.control_type, t.name FROM ui_tree t ORDER BY t.display_order").fetchall()
        props = {cid: dict(tmp.execute("SELECT property_name, property_value FROM ui_properties WHERE ui_tree_id=?", (cid,)))
                 for cid, *_ in rows}
        tmp.close()
        return rows, props

    # tree
    def roots(self, source_file=None):
        q = "SELECT id, control_type, name FROM ui_tree WHERE is_root=1"
        args = ()
        if source_file:
            q += " AND source_file LIKE ?"
            args = (f"%{source_file}%",)
        return self.db.execute(q + " ORDER BY display_order", args).fetchall()

    def children(self, cid):
        return self.db.execute("SELECT id, control_type, name FROM ui_tree WHERE parent_id=? ORDER BY display_order, id",
                               (cid,)).fetchall()

    def props(self, cid):
        return dict(self.db.execute("SELECT property_name, property_value FROM ui_properties WHERE ui_tree_id=?", (cid,)))

    # write-through
    def set_prop(self, cid, name, value):
        if cid is None:
            return
        self.db.execute("INSERT INTO ui_properties (ui_tree_id, property_name, property_value) VALUES (?,?,?) "
                        "ON CONFLICT(ui_tree_id, property_name) DO UPDATE SET property_value=excluded.property_value",
                        (cid, name, str(value)))

    def add_control(self, ctype, name, parent_id, source="runtime"):
        order = self.db.execute("SELECT COALESCE(MAX(display_order), 0) + 1 FROM ui_tree").fetchone()[0]
        cur = self.db.execute("INSERT OR REPLACE INTO ui_tree (parent_id, control_type, name, display_order, is_root, source_file) "
                              "VALUES (?,?,?,?,?,?)", (parent_id, ctype, name, order, 0 if parent_id else 1, source))
        return cur.lastrowid

    def delete_control(self, cid):
        if cid is not None:
            self.db.execute("DELETE FROM ui_tree WHERE id=?", (cid,))

    # settings: the scripts' shared memory
    def get_setting(self, key):
        r = self.db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return r[0] if r and r[0] is not None else ""

    def set_setting(self, key, value):
        self.db.execute("INSERT INTO settings (key, value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                        (key, "" if value is None else str(value)))

    # scripts
    def script(self, name):
        return self.db.execute("SELECT interpreter, content FROM scripts WHERE name=?", (name,)).fetchone()

    def script_home(self, name):
        """(instance, source_file) for a script: which Lua state it belongs to."""
        r = self.db.execute("SELECT interpreter, instance, source_file FROM scripts WHERE name=?", (name,)).fetchone()
        if not r:
            return "", ""
        interp, instance, source = r
        parts = str(interp or "").split()                  # "Interpreter=lua mygame" names an instance too
        return (instance or (parts[1] if len(parts) > 1 else "")), (source or "")

    def query_json(self, sql, *args):
        cur = self.db.execute(sql, args)
        cols = [d[0] for d in cur.description] if cur.description else []
        return json.dumps([dict(zip(cols, r)) for r in cur.fetchall()])

    def execute(self, sql, *args):
        return self.db.execute(sql, args).rowcount
