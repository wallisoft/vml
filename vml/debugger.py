"""
The debugger: what a running form's scripts are doing, while they do it. F12 in the designer (or in any form it is
running) opens it.

    Calls       every Vml() a script makes: when, which form, which script, the call, and what came back.
                Errors (a failed call, a script that stopped with an error) in red. Pause, clear, filter.
    Variables   a running form's Lua globals: its numbers, text, true/false and tables (open a table to see
                inside), refreshed as they change. Below, a line of Lua to run in that form: print(score),
                score = 10, Vml("GetProperty", "txtName", "Text").

The designer's own forms are left out, so what it shows is the app being tested.
"""
import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (QCheckBox, QComboBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPushButton, QTabWidget,
                               QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

MAX_ROWS = 4000
SHOW = 140                                                 # characters of an argument or a result shown in the list


def _short(v):
    s = str(v)
    s = s.replace("\r", " ").replace("\n", "⏎ ")
    return s if len(s) <= SHOW else s[:SHOW] + f"… ({len(str(v))} characters)"


class Debugger(QWidget):
    def __init__(self, engine):
        super().__init__(None, Qt.Window)
        self.engine = engine
        self.setWindowTitle("Visualised debugger")
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
        self.gets = QCheckBox("Include GetProperty")
        self.gets.setChecked(True)
        self.gets.toggled.connect(self.refilter)
        for w in (self.pause_btn, clear):
            bar.addWidget(w)
        bar.addWidget(self.filter, 1)
        bar.addWidget(self.errors_only)
        bar.addWidget(self.gets)
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

        self.timer = QTimer(self)                        # rows are added in batches: a busy script never stalls
        self.timer.setInterval(120)
        self.timer.timeout.connect(self.flush)
        self.timer.start()
        self.var_timer = QTimer(self)
        self.var_timer.setInterval(1000)
        self.var_timer.timeout.connect(lambda: self.isVisible() and self.tabs.currentIndex() == 1 and self.show_vars(keep=True))
        self.var_timer.start()
        QShortcut(QKeySequence("F12"), self, activated=self.hide)

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
        for key in self.engine.luas:
            if key and not self.engine.debug_hidden(key):
                self.state.addItem(self.engine.debug_name(key), key)
        i = self.state.findData(keep)
        self.state.setCurrentIndex(i if i >= 0 else 0)
        self.state.blockSignals(False)
        self.show_vars()

    def _rt(self):
        key = self.state.currentData()
        return self.engine.luas.get(key) if key is not None else None

    def show_vars(self, keep=False):
        rt = self._rt()
        opened = {self.vars.topLevelItem(i).text(0) for i in range(self.vars.topLevelItemCount())
                  if self.vars.topLevelItem(i).isExpanded()} if keep else set()
        scroll = self.vars.verticalScrollBar().value()
        self.vars.clear()
        if rt is None:
            return
        try:
            names = rt.execute(VARS_LUA, self.functions.isChecked())
        except Exception as exc:
            self.vars.addTopLevelItem(QTreeWidgetItem(["(couldn't read)", "", str(exc)]))
            return
        rows = sorted((names or {}).items(), key=lambda kv: str(kv[0]).lower())
        shared = getattr(getattr(self.engine, "shared", None), "values", None)
        rows = [r for r in rows if str(r[0]) != "Project"]
        if shared is not None:                           # the Project table every form shares: its values
            inner = ", ".join(f"{k}={v!r}" for k, v in list(shared.items())[:6]) + (", …" if len(shared) > 6 else "")
            it = QTreeWidgetItem(["Project", "shared", "{" + inner + "}"])
            for k, v in sorted(shared.items()):
                it.addChild(QTreeWidgetItem([f"[{k}]", type(v).__name__, _short(repr(v))]))
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
        rt = self._rt()
        if rt is None:
            return
        try:
            inside = rt.execute(TABLE_LUA, item.data(0, Qt.UserRole))
        except Exception as exc:
            item.addChild(QTreeWidgetItem(["", "", str(exc)]))
            return
        for k, desc in sorted((inside or {}).items(), key=lambda kv: (len(str(kv[0])), str(kv[0]))):
            kind, shown = str(desc).split("\t", 1) if "\t" in str(desc) else ("", str(desc))
            c = QTreeWidgetItem([f"[{k}]", kind, _short(shown)])
            c.setToolTip(2, shown[:4000])
            item.addChild(c)

    def run_line(self):
        rt, code = self._rt(), self.lua_line.text().strip()
        if rt is None or not code:
            return
        try:
            try:
                r = rt.execute("return " + code)            # an expression: show its value
            except Exception:
                r = rt.execute(code)
            self.answer.setText("= " + ("nil" if r is None else _short(r)))
            self.answer.setStyleSheet("color: #065F46;")
        except Exception as exc:
            self.answer.setText(str(exc))
            self.answer.setStyleSheet("color: #B91C1C;")
        self.show_vars(keep=True)


# a form's own globals (not Lua's standard ones), each as "type<TAB>value"
VARS_LUA = r"""
local functions = ...
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
