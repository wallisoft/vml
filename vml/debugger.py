"""
The debugger: what a running form's scripts are doing, while they do it. F12 in the designer (or in any form it is
running) opens it.

    Calls       every Vml() a script makes: when, which form, which script, the call, and what came back.
                Errors (a failed call, a script that stopped with an error) in red. Pause, clear, filter.
    Variables   a running form's Lua globals: its numbers, text, true/false and tables (open a table to see
                inside), refreshed as they change. Below, a line of Lua to run in that form: print(score),
                score = 10, Vml("GetProperty", "txtName", "Text").

The designer's own forms are left out, so what it shows is the app being tested.

Attached: the same window on another running Visualised app (Tools > Attach the debugger to a running app): Bob,
Mountie, anything started from a .vml. It asks that app's engine over its local API (vml/api.py: 127.0.0.1 and a
secret only you can read), and the app keeps a short record of its calls (Tap) while a debugger is reading it.
"""
import json
import time
from collections import deque
from types import SimpleNamespace

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (QCheckBox, QComboBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QPushButton, QSplitter, QTabWidget, QTreeWidget, QTreeWidgetItem,
                               QVBoxLayout, QWidget)

from .registry import WindowWidget

MAX_ROWS = 4000
SHOW = 140                                                 # characters of an argument or a result shown in the list


def _short(v):
    s = str(v)
    s = s.replace("\r", " ").replace("\n", "⏎ ")
    return s if len(s) <= SHOW else s[:SHOW] + f"… ({len(str(v))} characters)"


class Tap:
    """In an app a debugger is attached to: its calls, kept for the debugger to collect. Let go by itself when nothing
    has asked for a while (the debugger closed, or went with the app it ran in)."""

    def __init__(self, gone):
        self.rows, self.seq, self.everything, self.gone = deque(maxlen=MAX_ROWS), 0, False, gone
        self.paused = None
        self.touch()

    def paused_at(self, info):
        self.paused = info
        self.touch()                                     # (stopped for as long as it takes: don't let go meanwhile)

    def resumed(self):
        self.paused = None

    def touch(self):
        self.asked = time.time()

    def record(self, form, script, call, result, error=False):
        if time.time() - self.asked > 30:
            self.gone()
            return
        self.seq += 1
        t = time.strftime("%H:%M:%S") + f".{int(time.time() * 1000) % 1000:03d}"
        self.rows.append([self.seq, t, form, script, _short(call), _short(result), bool(error)])

    def since(self, n):
        self.touch()
        return {"seq": self.seq, "rows": [r for r in self.rows if r[0] > n], "paused": self.paused}


class Debugger(WindowWidget):
    """A window like a form's: our own title bar, and the edge round it all. remote: another running app to attach
    to ({pid, title, info} from vml/api.py running()), else the forms this engine is running."""

    def __init__(self, engine, remote=None):
        super().__init__(SimpleNamespace(name="Debugger", props={}))
        self.engine, self.remote, self.seen = engine, remote, 0
        self.setWindowTitle("Visualised debugger" + (f": {remote['title']}" if remote else ""))
        self.resize(900, 560)
        self.paused = False
        self.pending = []
        mono = QFont("monospace")
        mono.setStyleHint(QFont.Monospace)
        mono.setPointSizeF(max(8.0, self.font().pointSizeF() - 0.5))
        col = QVBoxLayout(self)
        col.setContentsMargins(8, 8, 8, 8)
        self.tabs = QTabWidget()
        col.addWidget(self.tabs)

        # ---- Calls
        calls = QWidget()
        cl = QVBoxLayout(calls)
        cl.setContentsMargins(4, 6, 4, 4)
        bar = QHBoxLayout()
        self.pause_btn = QPushButton("Pause")
        self.pause_btn.setCheckable(True)
        self.pause_btn.toggled.connect(self.set_paused)
        clear = QPushButton("Clear")
        clear.clicked.connect(lambda: self.calls.clear())
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Filter: a command, a control, a script, a form...")
        self.filter.textChanged.connect(self.refilter)
        self.errors_only = QCheckBox("Errors only")
        self.errors_only.toggled.connect(self.refilter)
        self.everything = QCheckBox("Designer's forms too")
        self.everything.setToolTip("Also the designer's own forms: for working on the designer itself")
        self.everything.toggled.connect(lambda _on: self.fill_states())
        self.gets = QCheckBox("Include GetProperty")
        self.gets.setChecked(True)
        self.gets.toggled.connect(self.refilter)
        for w in (self.pause_btn, clear):
            bar.addWidget(w)
        bar.addWidget(self.filter, 1)
        bar.addWidget(self.errors_only)
        bar.addWidget(self.gets)
        bar.addWidget(self.everything)
        cl.addLayout(bar)
        self.calls = QTreeWidget()
        self.calls.setHeaderLabels(["Time", "Form", "Script", "Call", "Result"])
        self.calls.setRootIsDecorated(False)
        self.calls.setUniformRowHeights(True)
        self.calls.setAlternatingRowColors(True)
        self.calls.setFont(mono)
        h = self.calls.header()
        for i, w in enumerate((86, 170, 110, 330)):
            self.calls.setColumnWidth(i, w)
        h.setStretchLastSection(True)
        cl.addWidget(self.calls, 1)
        self.tabs.addTab(calls, "Calls")

        # ---- Variables
        vars_ = QWidget()
        vl = QVBoxLayout(vars_)
        vl.setContentsMargins(4, 6, 4, 4)
        top = QHBoxLayout()
        top.addWidget(QLabel("Form:"))
        self.state = QComboBox()
        self.state.currentIndexChanged.connect(lambda _i: self.show_vars())
        top.addWidget(self.state, 1)
        self.functions = QCheckBox("Functions too")
        self.functions.toggled.connect(lambda _on: self.show_vars())
        top.addWidget(self.functions)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.show_vars)
        top.addWidget(refresh)
        vl.addLayout(top)
        self.vars = QTreeWidget()
        self.vars.setHeaderLabels(["Name", "Type", "Value"])
        self.vars.setFont(mono)
        self.vars.setColumnWidth(0, 200)
        self.vars.setColumnWidth(1, 80)
        self.vars.itemExpanded.connect(self.expand)
        vl.addWidget(self.vars, 1)
        run = QHBoxLayout()
        self.lua_line = QLineEdit()
        self.lua_line.setFont(mono)
        self.lua_line.setPlaceholderText('Lua to run in this form, e.g.  score = 10   or   return Vml("GetProperty", "txtName", "Text")')
        self.lua_line.returnPressed.connect(self.run_line)
        go = QPushButton("Run")
        go.clicked.connect(self.run_line)
        run.addWidget(self.lua_line, 1)
        run.addWidget(go)
        vl.addLayout(run)
        self.answer = QLabel("")
        self.answer.setFont(mono)
        self.answer.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.answer.setWordWrap(True)
        vl.addWidget(self.answer)
        self.tabs.addTab(vars_, "Variables")
        self.tabs.currentChanged.connect(lambda i: i == 1 and self.fill_states())

        # ---- Stepping: breakpoints, and a script stopped at one
        step = QWidget()
        sl = QVBoxLayout(step)
        sl.setContentsMargins(4, 6, 4, 4)
        top = QHBoxLayout()
        top.addWidget(QLabel("Script:"))
        self.script = QComboBox()
        self.script.currentIndexChanged.connect(lambda _i: self.show_code())
        top.addWidget(self.script, 1)
        reload_ = QPushButton("Refresh")
        reload_.clicked.connect(self.fill_scripts)
        top.addWidget(reload_)
        clear_bp = QPushButton("Clear breakpoints")
        clear_bp.clicked.connect(self.clear_breaks)
        top.addWidget(clear_bp)
        sl.addLayout(top)
        split = QSplitter(Qt.Horizontal)
        self.code = QListWidget()
        self.code.setFont(mono)
        self.code.itemDoubleClicked.connect(self.toggle_break)
        self.code.setToolTip("Double-click a line for a breakpoint (red): the script stops there, before running it")
        split.addWidget(self.code)
        side = QWidget()
        sd = QVBoxLayout(side)
        sd.setContentsMargins(6, 0, 0, 0)
        self.where = QLabel("Running. Double-click a line for a breakpoint.")
        self.where.setWordWrap(True)
        sd.addWidget(self.where)
        btns = QHBoxLayout()
        self.step_btns = []
        for text, mode, key in (("Continue", "", "F5"), ("Step into", "into", "F8"), ("Step over", "over", "Shift+F8"),
                                ("Step out", "out", "Ctrl+Shift+F8")):
            b = QPushButton(text)
            b.setToolTip(key)
            b.setEnabled(False)
            b.clicked.connect(lambda _c=False, m=mode: self.resume(m))
            QShortcut(QKeySequence(key), self, activated=lambda m=mode: self.resume(m))
            btns.addWidget(b)
            self.step_btns.append(b)
        sd.addLayout(btns)
        sd.addWidget(QLabel("Locals"))
        self.locals_ = QTreeWidget()
        self.locals_.setHeaderLabels(["Name", "Type", "Value"])
        self.locals_.setFont(mono)
        self.locals_.setRootIsDecorated(False)
        self.locals_.setColumnWidth(0, 120)
        self.locals_.setColumnWidth(1, 70)
        sd.addWidget(self.locals_, 2)
        sd.addWidget(QLabel("Call stack"))
        self.stack = QListWidget()
        self.stack.setFont(mono)
        self.stack.itemDoubleClicked.connect(self.show_frame)
        sd.addWidget(self.stack, 1)
        split.addWidget(side)
        split.setSizes([520, 360])
        sl.addWidget(split, 1)
        self.tabs.addTab(step, "Stepping")
        self.tabs.currentChanged.connect(lambda i: i == 2 and self.script.count() == 0 and self.fill_scripts())
        self.scripts, self.bps, self.stopped = {}, {}, None

        self.timer = QTimer(self)                        # rows are added in batches: a busy script never stalls
        self.timer.setInterval(120)
        self.timer.timeout.connect(self.flush)
        self.timer.start()
        self.var_timer = QTimer(self)
        self.var_timer.setInterval(1000)
        self.var_timer.timeout.connect(lambda: self.isVisible() and self.tabs.currentIndex() == 1 and self.show_vars(keep=True))
        self.var_timer.start()
        QShortcut(QKeySequence("F12"), self, activated=self.hide)
        if remote:                                       # attached: collect what the other app has recorded, as it goes
            self.everything.toggled.connect(lambda on: self._ask("DebugAttach", "true" if on else "false"))
            self.collect = QTimer(self)
            self.collect.setInterval(300)
            self.collect.timeout.connect(self.collect_calls)
            self._ask("DebugAttach", "false")
            self.collect.start()
        from .theme import theme, tool_sheet
        self.setStyleSheet(tool_sheet())
        self.set_title_bar("Own")
        self.set_edge(theme().edge, 2)
        col.setContentsMargins(8, 8 + self.bar_h(), 8, 8)    # (under the title bar)

    # ---------------------------------------------------------------- attached to another app
    def _ask(self, cmd, *args):
        from .api import ask
        return ask(self.remote["info"], cmd, *args)

    def collect_calls(self):
        try:
            got = json.loads(self._ask("DebugCalls", self.seen) or "{}")
        except Exception:
            self.collect.stop()
            self.setWindowTitle(f"Visualised debugger: {self.remote['title']} (it has closed)")
            return
        self.seen = got.get("seq", self.seen)
        p = got.get("paused")
        if p and p != self.stopped:
            self.paused_at(p)
        elif not p and self.stopped:
            self.resumed()
        for _seq, t, form, script, call, result, error in got.get("rows", []):
            if not self.paused:
                self.pending.append((t, form, script, call, result, error))

    def closeEvent(self, e):
        if self.stopped:                                 # (closing it mustn't leave the app stuck at a breakpoint)
            self.resume("")
        if self.remote:
            self.collect.stop()
            try:
                self._ask("DebugDetach")
            except Exception:
                pass
        super().closeEvent(e)

    # ---------------------------------------------------------------- stepping
    def fill_scripts(self):
        keep = self.script.currentText()
        self.scripts = {}
        try:
            keys = [k for k, _n in self._states()]
            for k in keys or [""]:
                got = self._ask("DebugScripts", k) if self.remote else self.engine.cmd_DebugScripts(k)
                for s in json.loads(got or "[]"):
                    self.scripts.setdefault(s["name"], s["code"])
            self.bps = {k: set(v) for k, v in json.loads((self._ask("DebugBreaks") if self.remote else self.engine.cmd_DebugBreaks()) or "{}").items()}
        except Exception as exc:
            self.where.setText(f"Couldn't ask the app: {exc}")
        self.script.blockSignals(True)
        self.script.clear()
        for name in sorted(self.scripts, key=lambda n: (("/" in n or n.endswith(".lua")), n.lower())):
            self.script.addItem(name + ("   ●" if self.bps.get(name) else ""), name)
        i = self.script.findData(keep.replace("   ●", ""))
        self.script.setCurrentIndex(max(0, i))
        self.script.blockSignals(False)
        self.show_code()

    def show_code(self, line=None):
        name = self.script.currentData()
        self.code.clear()
        if name is None:
            return
        marks = self.bps.get(name, set())
        here = self.stopped["line"] if self.stopped and self.stopped["name"] == name else None
        for n, text in enumerate(self.scripts.get(name, "").split("\n"), 1):
            it = QListWidgetItem(f"{'●' if n in marks else ' '} {n:4}  {text}")
            it.setData(Qt.UserRole, n)
            if n in marks:
                it.setForeground(QColor("#B91C1C"))
            if n == here:
                it.setBackground(QColor("#FEF08A"))
            self.code.addItem(it)
        target = line or here
        if target and target <= self.code.count():
            self.code.scrollToItem(self.code.item(target - 1), QListWidget.PositionAtCenter)
            if target == here:
                self.code.clearSelection()                   # (the yellow line is where it's stopped)
            else:
                self.code.setCurrentRow(target - 1)

    def _send_breaks(self):
        spec = json.dumps({k: sorted(v) for k, v in self.bps.items() if v})
        try:
            self._ask("DebugBreaks", spec) if self.remote else self.engine.cmd_DebugBreaks(spec)
        except Exception as exc:
            self.where.setText(f"Couldn't set it: {exc}")
        name = self.script.currentData()
        self.script.setItemText(self.script.currentIndex(), name + ("   ●" if self.bps.get(name) else ""))

    def toggle_break(self, item):
        name, n = self.script.currentData(), item.data(Qt.UserRole)
        marks = self.bps.setdefault(name, set())
        marks.symmetric_difference_update({n})
        self._send_breaks()
        self.show_code(line=n)

    def clear_breaks(self):
        self.bps = {}
        self._send_breaks()
        self.fill_scripts()

    def paused_at(self, info):
        """A script has stopped (here, or in the app attached to): show where, and what it has."""
        self.stopped = info
        self.show()
        self.raise_()
        self.activateWindow()
        self.tabs.setCurrentIndex(2)
        if info["name"] not in self.scripts:
            self.fill_scripts()
        i = self.script.findData(info["name"])
        if i >= 0 and i != self.script.currentIndex():
            self.script.setCurrentIndex(i)
        else:
            self.show_code()
        self.where.setText(f"<b>Stopped</b> in {info['name']}, line {info['line']}. The app waits: its clicks and "
                           f"timers are held till you carry on.")
        self.locals_.clear()
        for row in info.get("locals", []):
            name, kind, value = (row + ["", "", ""])[:3]
            it = QTreeWidgetItem([name, kind, _short(value)])
            it.setToolTip(2, value[:4000])
            self.locals_.addTopLevelItem(it)
        self.stack.clear()
        for row in info.get("stack", []):
            name, line, fn = (row + ["", "", ""])[:3]
            it = QListWidgetItem(f"{name}, line {line}" + (f"  ({fn})" if fn and fn != name else ""))
            it.setData(Qt.UserRole, (name, int(line or 0)))
            self.stack.addItem(it)
        for b in self.step_btns:
            b.setEnabled(True)

    def resumed(self):
        self.stopped = None
        for b in self.step_btns:
            b.setEnabled(False)
        self.where.setText("Running. Double-click a line for a breakpoint.")
        self.locals_.clear()
        self.stack.clear()
        self.show_code()

    def resume(self, mode=""):
        if not self.stopped:
            return
        try:
            self._ask("DebugResume", mode) if self.remote else self.engine.resume(mode)
        except Exception as exc:
            self.where.setText(f"Couldn't carry on: {exc}")
        if self.remote:
            self.resumed()

    def show_frame(self, item):
        name, line = item.data(Qt.UserRole)
        i = self.script.findData(name)
        if i >= 0:
            self.script.setCurrentIndex(i)
            self.show_code(line=line)

    # where the forms and their Lua are: here, or in the app attached to
    def _states(self):
        if self.remote:
            return [tuple(x) for x in json.loads(self._ask("DebugStates") or "[]")]
        return [(k, self.engine.debug_name(k)) for k in self.engine.luas if k and not self.engine.debug_hidden(k)]

    def _lua(self, code, arg=None):
        key = self.state.currentData()
        if key is None:
            return None
        if self.remote:
            got = json.loads(self._ask("DebugLua", key, code, "" if arg is None else arg) or "{}")
            return got["table"] if "table" in got else got.get("value")
        rt = self.engine.luas.get(key)
        if rt is None:
            return None
        return rt.execute(code, arg) if arg is not None else rt.execute(code)

    def _shared(self):
        if self.remote:
            got = json.loads(self._ask("DebugShared") or "null")
            return None if got is None else {k: tuple(v) for k, v in got.items()}
        shared = getattr(getattr(self.engine, "shared", None), "values", None)
        return None if shared is None else {k: (type(v).__name__, repr(v)) for k, v in shared.items()}

    # ---------------------------------------------------------------- calls
    def record(self, form, script, call, result, error=False):
        if self.paused:
            return
        self.pending.append((time.strftime("%H:%M:%S") + f".{int(time.time() * 1000) % 1000:03d}", form, script, call, result, error))
        if len(self.pending) > MAX_ROWS:
            del self.pending[:-MAX_ROWS]

    def flush(self):
        if not self.pending:
            return
        rows, self.pending = self.pending, []
        sb = self.calls.verticalScrollBar()
        at_end = sb.value() >= sb.maximum() - 4
        items = []
        for t, form, script, call, result, error in rows:
            it = QTreeWidgetItem([t, form, script, _short(call), _short(result)])
            it.setToolTip(3, str(call)[:4000])
            it.setToolTip(4, str(result)[:4000])
            if error:
                for c in range(5):
                    it.setForeground(c, QColor("#B91C1C"))
                it.setData(0, Qt.UserRole, "error")
            items.append(it)
        self.calls.addTopLevelItems(items)
        extra = self.calls.topLevelItemCount() - MAX_ROWS
        for _ in range(max(0, extra)):
            self.calls.takeTopLevelItem(0)
        for it in items:
            it.setHidden(not self.wanted(it))
        if at_end:
            self.calls.scrollToBottom()

    def wanted(self, it):
        if self.errors_only.isChecked() and it.data(0, Qt.UserRole) != "error":
            return False
        if not self.gets.isChecked() and it.text(3).startswith("GetProperty("):
            return False
        q = self.filter.text().strip().lower()
        return not q or any(q in it.text(c).lower() for c in range(5))

    def refilter(self, *_):
        for i in range(self.calls.topLevelItemCount()):
            it = self.calls.topLevelItem(i)
            it.setHidden(not self.wanted(it))

    def set_paused(self, on):
        self.paused = on
        self.pause_btn.setText("Resume" if on else "Pause")

    # ---------------------------------------------------------------- variables
    def fill_states(self):
        keep = self.state.currentData()
        self.state.blockSignals(True)
        self.state.clear()
        try:
            for key, name in self._states():
                self.state.addItem(name, key)
        except Exception as exc:
            self.answer.setText(f"Couldn't ask the app: {exc}")
        i = self.state.findData(keep)
        self.state.setCurrentIndex(i if i >= 0 else 0)
        self.state.blockSignals(False)
        self.show_vars()

    def show_vars(self, keep=False):
        opened = {self.vars.topLevelItem(i).text(0) for i in range(self.vars.topLevelItemCount())
                  if self.vars.topLevelItem(i).isExpanded()} if keep else set()
        scroll = self.vars.verticalScrollBar().value()
        self.vars.clear()
        if self.state.currentData() is None:
            return
        try:
            names = self._lua(VARS_LUA, self.functions.isChecked() if not self.remote else ("true" if self.functions.isChecked() else ""))
        except Exception as exc:
            self.vars.addTopLevelItem(QTreeWidgetItem(["(couldn't read)", "", str(exc)]))
            return
        rows = sorted((names or {}).items(), key=lambda kv: str(kv[0]).lower())
        try:
            shared = self._shared()
        except Exception:
            shared = None
        rows = [r for r in rows if str(r[0]) != "Project"]
        if shared is not None:                           # the Project table every form shares: its values
            inner = ", ".join(f"{k}={v[1]}" for k, v in list(shared.items())[:6]) + (", …" if len(shared) > 6 else "")
            it = QTreeWidgetItem(["Project", "shared", "{" + inner + "}"])
            for k, (kind, shown) in sorted(shared.items()):
                it.addChild(QTreeWidgetItem([f"[{k}]", kind, _short(shown)]))
            self.vars.addTopLevelItem(it)
            if "Project" in opened:
                it.setExpanded(True)
        for name, desc in rows:
            kind, shown = str(desc).split("\t", 1) if "\t" in str(desc) else ("", str(desc))
            it = QTreeWidgetItem([str(name), kind, _short(shown)])
            it.setToolTip(2, shown[:4000])
            if kind == "table":
                it.setChildIndicatorPolicy(QTreeWidgetItem.ShowIndicator)
                it.setData(0, Qt.UserRole, str(name))
            self.vars.addTopLevelItem(it)
            if str(name) in opened:
                it.setExpanded(True)
        self.vars.verticalScrollBar().setValue(scroll)

    def expand(self, item):
        if item.childCount() or item.data(0, Qt.UserRole) is None:
            return
        try:
            inside = self._lua(TABLE_LUA, item.data(0, Qt.UserRole))
        except Exception as exc:
            item.addChild(QTreeWidgetItem(["", "", str(exc)]))
            return
        for k, desc in sorted((inside or {}).items(), key=lambda kv: (len(str(kv[0])), str(kv[0]))):
            kind, shown = str(desc).split("\t", 1) if "\t" in str(desc) else ("", str(desc))
            c = QTreeWidgetItem([f"[{k}]", kind, _short(shown)])
            c.setToolTip(2, shown[:4000])
            item.addChild(c)

    def run_line(self):
        code = self.lua_line.text().strip()
        if self.state.currentData() is None or not code:
            return
        try:
            said = True
            try:
                r = self._lua("return " + code)              # an expression: show its value
            except Exception:
                r, said = self._lua(code), False             # a statement (score = 10): it's done
            self.answer.setText("Done" if (r is None and not said) else "= " + ("nil" if r is None else _short(r)))
            self.answer.setStyleSheet("color: #065F46;")
        except Exception as exc:
            self.answer.setText(str(exc))
            self.answer.setStyleSheet("color: #B91C1C;")
        self.show_vars(keep=True)


# a form's own globals (not Lua's standard ones), each as "type<TAB>value"
VARS_LUA = r"""
local functions = ...
if functions == "" or functions == "false" then functions = false end
local std = {}
for _, n in ipairs({"_G","_VERSION","assert","collectgarbage","coroutine","debug","dofile","error","getmetatable","io","ipairs",
  "load","loadfile","math","next","os","package","pairs","pcall","print","rawequal","rawget","rawlen","rawset","require",
  "select","setmetatable","string","table","tonumber","tostring","type","utf8","xpcall","Vml","arg","args","python"}) do std[n] = true end
local function show(v)
  local t = type(v)
  if t == "string" then return t .. "\t" .. string.format("%q", v) end
  if t == "table" then
    local n, parts = 0, {}
    for k, x in pairs(v) do
      n = n + 1
      if #parts < 6 then parts[#parts + 1] = tostring(k) .. "=" .. (type(x) == "string" and string.format("%q", x) or tostring(x)) end
    end
    return t .. "\t{" .. table.concat(parts, ", ") .. (n > 6 and (", … " .. n .. " in all") or "") .. "}"
  end
  return t .. "\t" .. tostring(v)
end
local out = {}
for k, v in pairs(_G) do
  if type(k) == "string" and not std[k] and (functions or type(v) ~= "function") then out[k] = show(v) end
end
return out
"""

# one table's insides, a level deep
TABLE_LUA = r"""
local name = ...
local t = _G[name]
local out = {}
if type(t) ~= "table" then return out end
local n = 0
for k, v in pairs(t) do
  n = n + 1
  if n > 400 then out["…"] = "\t(more)" break end
  local s
  if type(v) == "string" then s = string.format("%q", v)
  elseif type(v) == "table" then
    local m, parts = 0, {}
    for k2, x in pairs(v) do m = m + 1; if #parts < 5 then parts[#parts + 1] = tostring(k2) .. "=" .. tostring(x) end end
    s = "{" .. table.concat(parts, ", ") .. (m > 5 and ", …" or "") .. "}"
  else s = tostring(v) end
  out[tostring(k)] = type(v) .. "\t" .. s
end
return out
"""
