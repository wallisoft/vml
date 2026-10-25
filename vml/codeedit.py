"""
CodeEditor: a control for writing code in, the way a code editor should be. The Script Editor is made of one; any
form can have one.

    Text            the code
    Language        Lua (the default), Python, Shell or CSharp: what it's coloured as
    Breakpoints     the lines with a breakpoint, "3, 12": click in the margin to set one (a red dot), again to clear
    CurrentLine     the line a script is stopped at (yellow), 0 for none
    IsReadOnly, FontSize
    TextChanged, BreakpointsChanged

Line numbers; colours for keywords, text, numbers, comments and Vml("Command"); the line you're on lit; Enter keeps
the indent (and adds one after then / do / function / {); Tab and Shift+Tab indent and outdent a line or a
selection by four spaces; Ctrl+/ comments lines in and out; Ctrl+F finds (F3 the next one). Its own monospaced
font on every desktop (Cascadia Mono or Consolas on Windows, the desktop's own elsewhere).
On the web it's a plain text area.
"""
import re

from PySide6.QtCore import QModelIndex, QRect, QRegularExpression, QSize, Qt
from PySide6.QtGui import (QColor, QFont, QFontDatabase, QKeySequence, QPainter, QShortcut, QStandardItem,
                           QStandardItemModel, QSyntaxHighlighter, QTextCharFormat, QTextCursor, QTextFormat)
from PySide6.QtWidgets import QCompleter, QInputDialog, QPlainTextEdit, QTextEdit, QWidget

from .registry import (ATTACHED, COMMON, ControlType, Prop, completion_pool, lang_rules, num, register,
                       truthy)

GUTTER_BG, GUTTER_INK, BREAK, STOPPED, LINE_LIT = "#F3F4F6", "#9CA3AF", "#DC2626", "#FEF08A", "#F5F8FF"

KEYWORDS = {
    "lua": "and break do else elseif end false for function goto if in local nil not or repeat return then true until while",
    "python": "and as assert async await break class continue def del elif else except False finally for from global if "
              "import in is lambda None nonlocal not or pass raise return True try while with yield",
    "shell": "if then else elif fi for while until do done case esac function in select return local export echo exit",
    "csharp": "abstract as base bool break byte case catch char class const continue decimal default do double else enum "
              "false finally float for foreach if in int interface internal is long namespace new null object out "
              "override private protected public readonly ref return sealed short static string struct switch this "
              "throw true try typeof uint ulong using var virtual void while",
    "vb": "and as boolean byref byval call case dim do double each else elseif empty end exit false for function if "
          "in integer is long loop mod new next not nothing null object or private public rem return select set "
          "single step string sub then to true until variant wend while with xor",
}
COMMENT = {"lua": "--", "python": "#", "shell": "#", "csharp": "//", "vb": "'"}

# member completion. The rules for each language (its functions, control methods, whether events appear) are owned
# by that language's interpreter and registered with the registry; the editor just lays out and filters the result.
# A language whose interpreter hasn't registered rules still gets plain property completion from the shared model.
_LANG_MODULE = {"vb": "vbscript"}                 # languages whose rules a module registers on import (imported lazily)
_KIND_GLYPH = {"prop": "\u2261", "method": "\u0192", "func": "\u0192", "event": "\u26a1",
               "ctrl": "\u25a2", "kw": "\u00b7"}


def _subseq(term, s):            # is `term` a subsequence of `s`? (so "fsz" finds "FontSize")
    i = 0
    for ch in s:
        if i < len(term) and ch == term[i]:
            i += 1
    return i == len(term)


def _fuzzy(pool, term):
    """Prefix matches first (keeping the pool's order), then looser subsequence matches."""
    if not term:
        return list(pool)
    t = term.lower()
    pref, sub = [], []
    for m in pool:
        nl = m["name"].lower()
        if nl.startswith(t):
            pref.append(m)
        elif _subseq(t, nl):
            sub.append(m)
    return pref + sub



def code_font(size=0):
    """A monospaced font that reads well on each desktop."""
    families = set(QFontDatabase.families())
    for name in ("Cascadia Mono", "Consolas", "JetBrains Mono", "Ubuntu Mono", "DejaVu Sans Mono", "Menlo"):
        if name in families:
            f = QFont(name)
            break
    else:
        f = QFontDatabase.systemFont(QFontDatabase.FixedFont)
    f.setStyleHint(QFont.Monospace)
    f.setPointSizeF(size or 10.5)
    return f


def _fmt(colour, bold=False, italic=False):
    f = QTextCharFormat()
    f.setForeground(QColor(colour))
    if bold:
        f.setFontWeight(QFont.Bold)
    f.setFontItalic(italic)
    return f


class Highlighter(QSyntaxHighlighter):
    def __init__(self, doc, language="lua"):
        super().__init__(doc)
        self.set_language(language)

    def set_language(self, language):
        lang = (str(language or "lua").lower().replace("c#", "csharp").split() or ["lua"])[0]
        lang = {"cs": "csharp", "bash": "shell", "sh": "shell", "powershell": "shell", "py": "python",
                "vbscript": "vb", "basic": "vb"}.get(lang, lang)
        if lang == "vml":
            self.lang = "vml"
            self.rules = [
                (QRegularExpression(r"^@\w+"), _fmt("#7C3AED", bold=True)),          # @Window, @Button, @Script
                (QRegularExpression(r"^\s*[A-Za-z_]\w*(?==)"), _fmt("#1D4ED8")),     # a property name before =
                (QRegularExpression(r"<<\w+|^\s*[A-Z_]{3,}\s*$"), _fmt("#B45309")),  # heredoc start/end markers
                (QRegularExpression(r'"(?:[^"\\]|\\.)*"'), _fmt("#047857")),
            ]
            self.comment = QRegularExpression(r"^\s*#.*$")                           # # only at line start (not #RRGGBB values)
            self.comment_fmt = _fmt("#6B7280", italic=True)
            self.rehighlight()
            return
        self.lang = lang if lang in KEYWORDS else "lua"
        words = "|".join(KEYWORDS[self.lang].split())
        kw_rx = QRegularExpression(r"\b(?:" + words + r")\b")
        if self.lang == "vb":                                # VB is case-insensitive, so Dim == dim
            kw_rx.setPatternOptions(QRegularExpression.CaseInsensitiveOption)
        self.rules = [
            (kw_rx, _fmt("#7C3AED", bold=True)),
            (QRegularExpression(r"\b\d+(?:\.\d+)?\b"), _fmt("#B45309")),
            (QRegularExpression(r"\bVml\b|\bargs\b|\bProject\b"), _fmt("#0369A1", bold=True)),
            (QRegularExpression(r"\b[A-Za-z_]\w*(?=\s*\()"), _fmt("#1D4ED8")),
            (QRegularExpression(r'"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\''), _fmt("#047857")),
        ]
        self.comment = QRegularExpression(re.escape(COMMENT[self.lang]) + ".*$")
        self.comment_fmt = _fmt("#6B7280", italic=True)
        self.rehighlight()

    def highlightBlock(self, text):
        for rx, fmt in self.rules:
            it = rx.globalMatch(text)
            while it.hasNext():
                m = it.next()
                self.setFormat(m.capturedStart(), m.capturedLength(), fmt)
        # a comment, unless the marker is inside a string
        it = self.comment.globalMatch(text)
        while it.hasNext():
            m = it.next()
            before = text[:m.capturedStart()]
            if before.count('"') % 2 == 0 and before.count("'") % 2 == 0:
                self.setFormat(m.capturedStart(), len(text) - m.capturedStart(), self.comment_fmt)
                break


class Gutter(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.ed = editor
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("Click for a breakpoint: the script stops here when it runs (F12 for the debugger)")

    def sizeHint(self):
        return QSize(self.ed.gutter_width(), 0)

    def paintEvent(self, e):
        self.ed.paint_gutter(e)

    def mousePressEvent(self, e):
        block = self.ed.block_at(e.position().y())
        if block is not None:
            self.ed.toggle_break(block.blockNumber() + 1)


class CodeEditorWidget(QPlainTextEdit):
    # (a breakpoint clicked in: told by a plain Python list of callbacks, not a Qt Signal of our own. Compiled for
    # Windows, connecting to one sometimes crashed Visualised as the script editor opened: 1.6.3, A8.)

    def __init__(self, node):
        super().__init__()
        self.node = node
        self.on_breaks = []
        self.breaks, self.current = set(), 0
        self.setFont(code_font(num(node.props.get("FontSize"), 0)))
        self.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(" ") * 4)
        self.setStyleSheet("QPlainTextEdit { background: #FFFFFF; color: #111827; border: 1px solid #D1D5DB; "
                           "selection-background-color: #BFDBFE; selection-color: #111827; }")
        self.gutter = Gutter(self)
        self.hl = Highlighter(self.document(), node.props.get("Language"))
        self.blockCountChanged.connect(lambda _n: self._margins())
        self.updateRequest.connect(self._scrolled)
        self.cursorPositionChanged.connect(self._lights)
        self._margins()
        self._lights()
        QShortcut(QKeySequence("Ctrl+/"), self, activated=self.toggle_comment)
        QShortcut(QKeySequence.Find, self, activated=self.find_text)
        QShortcut(QKeySequence("F3"), self, activated=lambda: self.find_text(again=True))
        self._find = ""
        # member completion: type `name.` for a control's members, or a bare word for controls + this language's words
        self._omodel = {}                      # {controlName: {type, props, events}}, set by the ObjectModel property
        self._cmp_model = QStandardItemModel(self)
        self._completer = QCompleter(self)
        self._completer.setModel(self._cmp_model)
        self._completer.setWidget(self)
        self._completer.setCompletionMode(QCompleter.UnfilteredPopupCompletion)
        self._completer.setCaseSensitivity(Qt.CaseInsensitive)
        self._completer.activated[QModelIndex].connect(self._insert_completion)
        self._cmp_ctx = None                   # (kind, owner, partial, partial_len) while the popup is up

    # ---- the margin: line numbers and breakpoints
    def gutter_width(self):
        digits = max(3, len(str(self.blockCount())))
        return 22 + self.fontMetrics().horizontalAdvance("9") * digits + 10

    def _margins(self):
        self.setViewportMargins(self.gutter_width(), 0, 0, 0)

    def _scrolled(self, rect, dy):
        if dy:
            self.gutter.scroll(0, dy)
        else:
            self.gutter.update(0, rect.y(), self.gutter.width(), rect.height())

    def resizeEvent(self, e):
        super().resizeEvent(e)
        cr = self.contentsRect()
        self.gutter.setGeometry(QRect(cr.left(), cr.top(), self.gutter_width(), cr.height()))

    def block_at(self, y):
        block = self.firstVisibleBlock()
        top = self.blockBoundingGeometry(block).translated(self.contentOffset()).top()
        while block.isValid():
            bottom = top + self.blockBoundingRect(block).height()
            if top <= y < bottom:
                return block
            block, top = block.next(), bottom
        return None

    def paint_gutter(self, e):
        g = QPainter(self.gutter)
        g.setRenderHint(QPainter.Antialiasing)
        g.fillRect(e.rect(), QColor(GUTTER_BG))
        block = self.firstVisibleBlock()
        top = self.blockBoundingGeometry(block).translated(self.contentOffset()).top()
        h = self.fontMetrics().height()
        w = self.gutter.width()
        here = self.textCursor().blockNumber()
        while block.isValid() and top <= e.rect().bottom():
            bottom = top + self.blockBoundingRect(block).height()
            n = block.blockNumber() + 1
            if block.isVisible() and bottom >= e.rect().top():
                if n == self.current:
                    g.fillRect(0, int(top), w, int(bottom - top), QColor(STOPPED))
                if n in self.breaks:
                    d = min(h - 4, 12)
                    g.setPen(Qt.NoPen)
                    g.setBrush(QColor(BREAK))
                    g.drawEllipse(5, int(top + (h - d) / 2), d, d)
                g.setPen(QColor("#374151" if n - 1 == here else GUTTER_INK))
                g.drawText(0, int(top), w - 8, h, Qt.AlignRight | Qt.AlignVCenter, str(n))
            block, top = block.next(), bottom

    def toggle_break(self, line):
        self.breaks.symmetric_difference_update({line})
        self.node.props["Breakpoints"] = self.breaks_text()
        self.gutter.update()
        for told in list(self.on_breaks):
            told()

    def breaks_text(self):
        return ", ".join(str(n) for n in sorted(self.breaks))

    def set_breaks(self, v):
        self.breaks = {int(x) for x in re.findall(r"\d+", str(v or ""))}
        self.gutter.update()

    def set_current(self, v):
        self.current = int(num(v, 0))
        self._lights()
        self.gutter.update()
        if self.current:
            block = self.document().findBlockByNumber(self.current - 1)
            if block.isValid():
                c = QTextCursor(block)
                self.setTextCursor(c)
                self.centerCursor()

    # ---- the line you're on, and the one a script is stopped at
    def _lights(self):
        sels = []
        if self.current:
            block = self.document().findBlockByNumber(self.current - 1)
            if block.isValid():
                s = QTextEdit.ExtraSelection()
                s.format.setBackground(QColor(STOPPED))
                s.format.setProperty(QTextFormat.FullWidthSelection, True)
                s.cursor = QTextCursor(block)
                sels.append(s)
        if not self.isReadOnly() and (not self.current or self.textCursor().blockNumber() != self.current - 1):
            s = QTextEdit.ExtraSelection()
            s.format.setBackground(QColor(LINE_LIT))
            s.format.setProperty(QTextFormat.FullWidthSelection, True)
            s.cursor = self.textCursor()
            s.cursor.clearSelection()
            sels.append(s)
        self.setExtraSelections(sels)
        self.gutter.update()

    # ---- typing
    def keyPressEvent(self, e):
        k, mods = e.key(), e.modifiers()
        pop = self._completer.popup()
        if pop.isVisible():
            if k == Qt.Key_Escape:
                pop.hide(); return
            if k in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Tab):
                idx = pop.currentIndex()
                if not idx.isValid() and self._cmp_model.rowCount():
                    idx = self._cmp_model.index(0, 0)
                if idx.isValid():
                    self._insert_completion(idx); return
                pop.hide()
            elif k in (Qt.Key_Up, Qt.Key_Down, Qt.Key_PageUp, Qt.Key_PageDown):
                pop.event(e); return
        if k in (Qt.Key_Return, Qt.Key_Enter) and not mods & (Qt.ControlModifier | Qt.ShiftModifier):
            line = self.textCursor().block().text()
            before = line[:self.textCursor().positionInBlock()]
            indent = re.match(r"[ \t]*", line).group(0)
            if re.search(r"(\bthen|\bdo|\bfunction\b.*\)|\belse|\brepeat|[{(\[:])\s*(--.*)?$", before.rstrip()) \
                    and not re.search(r"\bend\b\s*$", before):
                indent += "    "
            self.textCursor().insertText("\n" + indent)
            self.ensureCursorVisible()
            return
        if k == Qt.Key_Tab and not mods & Qt.ControlModifier:
            self._indent(+1)
            return
        if k == Qt.Key_Backtab:
            self._indent(-1)
            return
        if k == Qt.Key_Backspace and not self.textCursor().hasSelection():
            c = self.textCursor()
            before = c.block().text()[:c.positionInBlock()]
            if before and not before.strip() and len(before) % 4 == 0:     # back a whole indent
                for _ in range(4):
                    c.deletePreviousChar()
                return
        super().keyPressEvent(e)
        txt = e.text()
        if k in (Qt.Key_Period, Qt.Key_Colon, Qt.Key_Backspace) or (txt and (txt.isalnum() or txt == "_")):
            self._maybe_complete()
        elif not (mods & (Qt.ControlModifier | Qt.AltModifier)):
            self._completer.popup().hide()

    def set_object_model(self, data):
        """Give the editor the form's object model: {controlName: {type, props, events}} (JSON or a dict)."""
        import json as _json
        try:
            self._omodel = _json.loads(data) if isinstance(data, str) else (data or {})
        except Exception:
            self._omodel = {}

    def _rules(self):
        """This language's completion rules, from whichever interpreter owns them (imported on first need)."""
        lang = self.hl.lang
        r = lang_rules(lang)
        if r is None and lang in _LANG_MODULE:
            try:
                import importlib
                importlib.import_module("vml." + _LANG_MODULE[lang])
            except Exception:
                pass
            r = lang_rules(lang)
        return r or {}

    def _ctx_before(self):
        c = self.textCursor()
        before = c.block().text()[:c.positionInBlock()]
        m = re.search(r"([A-Za-z_]\w*)([.:])(\w*)$", before)
        if m and m.group(2) in self._rules().get("seps", "."):
            return ("dot", m.group(1), m.group(3), len(m.group(3)))
        m = re.search(r"([A-Za-z_]\w*)$", before)
        if m:
            return ("word", None, m.group(1), len(m.group(1)))
        return None

    def _candidates(self, ctx):
        kind, owner, partial, _ = ctx
        if kind == "word" and len(partial) < 2:            # a bare word only pops once there's something to go on
            return []
        names = sorted(self._omodel, key=str.lower)
        return _fuzzy(completion_pool(kind, owner, self._omodel, self._rules(), names), partial)

    def _maybe_complete(self):
        ctx = self._ctx_before()
        cands = self._candidates(ctx) if ctx else []
        if not cands:
            self._completer.popup().hide()
            self._cmp_ctx = None
            return
        self._cmp_model.clear()
        for m in cands[:200]:
            it = QStandardItem("%s  %s" % (_KIND_GLYPH.get(m["kind"], " "), m["name"]))
            it.setData(m["name"], Qt.UserRole)
            it.setEditable(False)
            self._cmp_model.appendRow(it)
        self._cmp_ctx = ctx
        cr = self.cursorRect()
        cr.setWidth(self._completer.popup().sizeHintForColumn(0) + 32)
        self._completer.complete(cr)
        self._completer.popup().setCurrentIndex(self._cmp_model.index(0, 0))

    def _insert_completion(self, index):
        name = self._cmp_model.data(index, Qt.UserRole)
        if not name or not self._cmp_ctx:
            return
        plen = self._cmp_ctx[3]
        c = self.textCursor()
        for _ in range(plen):
            c.deletePreviousChar()
        c.insertText(name)
        self.setTextCursor(c)
        self._completer.popup().hide()
        self._cmp_ctx = None

    def _lines(self):
        c = self.textCursor()
        doc = self.document()
        a, b = doc.findBlock(c.selectionStart()), doc.findBlock(max(c.selectionStart(), c.selectionEnd() - (1 if c.hasSelection() else 0)))
        return a.blockNumber(), b.blockNumber()

    def _indent(self, way):
        c = self.textCursor()
        if way > 0 and not c.hasSelection():
            c.insertText(" " * (4 - c.positionInBlock() % 4))
            return
        first, last = self._lines()
        c.beginEditBlock()
        for n in range(first, last + 1):
            block = self.document().findBlockByNumber(n)
            cur = QTextCursor(block)
            if way > 0:
                cur.insertText("    ")
            else:
                spaces = len(block.text()) - len(block.text().lstrip(" "))
                for _ in range(min(4, spaces)):
                    cur.deleteChar()
        c.endEditBlock()

    def toggle_comment(self):
        mark = COMMENT.get(self.hl.lang, "--")
        first, last = self._lines()
        blocks = [self.document().findBlockByNumber(n) for n in range(first, last + 1)]
        off = all(b.text().lstrip().startswith(mark) for b in blocks if b.text().strip())
        c = self.textCursor()
        c.beginEditBlock()
        for b in blocks:
            if not b.text().strip():
                continue
            lead = len(b.text()) - len(b.text().lstrip())
            cur = QTextCursor(b)
            cur.setPosition(b.position() + lead)
            if off:
                n = len(mark) + (1 if b.text()[lead + len(mark):lead + len(mark) + 1] == " " else 0)
                for _ in range(n):
                    cur.deleteChar()
            else:
                cur.insertText(mark + " ")
        c.endEditBlock()

    def find_text(self, again=False):
        if not again or not self._find:
            text, ok = QInputDialog.getText(self, "Find", "Find:", text=self._find or self.textCursor().selectedText())
            if not ok or not text:
                return
            self._find = text
        if not self.find(self._find):
            self.moveCursor(QTextCursor.Start)                 # (round to the top again)
            self.find(self._find)


def _set_text(n, v):
    w = n.widget
    if w.toPlainText() != str(v or ""):
        w.setPlainText(str(v or ""))


def _events_text(node, fire):
    node.widget.textChanged.connect(lambda: fire({}))


def _events_breaks(node, fire):
    w = node.widget
    w.on_breaks.append(lambda: fire({"breakpoints": w.breaks_text()}))


PLAIN = [p for p in COMMON if p.name not in ("Background", "Foreground", "CornerRadius")]
register(ControlType("CodeEditor", lambda n: CodeEditorWidget(n),
                     events={"TextChanged": _events_text, "BreakpointsChanged": _events_breaks}),
         PLAIN, ATTACHED,
         [Prop("Text", "text", "Common", apply=_set_text, read=lambda n: n.widget.toPlainText()),
          Prop("Language", "choice", "Common", options=("Lua", "VB", "Python", "Shell", "CSharp"), default="Lua",
               apply=lambda n, v: n.widget.hl.set_language(v)),
          Prop("Breakpoints", "text", "Behaviour", apply=lambda n, v: n.widget.set_breaks(v),
               read=lambda n: n.widget.breaks_text()),
          Prop("CurrentLine", "number", "Behaviour", default="0", apply=lambda n, v: n.widget.set_current(v)),
          Prop("IsReadOnly", "bool", "Behaviour", default="false", apply=lambda n, v: n.widget.setReadOnly(truthy(v))),
          Prop("FontSize", "number", "Appearance", apply=lambda n, v: n.widget.setFont(code_font(num(v, 0)))),
          Prop("ObjectModel", "text", "Behaviour", apply=lambda n, v: n.widget.set_object_model(v))])
