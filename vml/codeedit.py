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

from PySide6.QtCore import QRect, QRegularExpression, QSize, Qt
from PySide6.QtGui import (QColor, QFont, QFontDatabase, QKeySequence, QPainter, QShortcut, QSyntaxHighlighter,
                           QTextCharFormat, QTextCursor, QTextFormat)
from PySide6.QtWidgets import QInputDialog, QPlainTextEdit, QTextEdit, QWidget

from .registry import ATTACHED, COMMON, ControlType, Prop, num, register, truthy

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
}
COMMENT = {"lua": "--", "python": "#", "shell": "#", "csharp": "//"}


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
        lang = {"cs": "csharp", "bash": "shell", "sh": "shell", "powershell": "shell", "py": "python"}.get(lang, lang)
        self.lang = lang if lang in KEYWORDS else "lua"
        words = "|".join(KEYWORDS[self.lang].split())
        self.rules = [
            (QRegularExpression(r"\b(?:" + words + r")\b"), _fmt("#7C3AED", bold=True)),
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
          Prop("Language", "choice", "Common", options=("Lua", "Python", "Shell", "CSharp"), default="Lua",
               apply=lambda n, v: n.widget.hl.set_language(v)),
          Prop("Breakpoints", "text", "Behaviour", apply=lambda n, v: n.widget.set_breaks(v),
               read=lambda n: n.widget.breaks_text()),
          Prop("CurrentLine", "number", "Behaviour", default="0", apply=lambda n, v: n.widget.set_current(v)),
          Prop("IsReadOnly", "bool", "Behaviour", default="false", apply=lambda n, v: n.widget.setReadOnly(truthy(v))),
          Prop("FontSize", "number", "Appearance", apply=lambda n, v: n.widget.setFont(code_font(num(v, 0))))])
