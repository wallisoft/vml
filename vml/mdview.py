"""
Reading and writing Markdown inside an app, so help, tutorials and terms open in a window of the app instead of
sending people off to the browser.

    MarkdownBox       a framed reader (the same bar and edge as every box), with back, forward, find and
                      "open in the browser"; with editing on, Markdown on the left and how it looks on the right.
    MarkdownView      a control showing Markdown: Text, or Source (a file, a web address, or help:Page).
    MarkdownEditor    a control for writing it: the text, and how it looks beside it as you type.

Where a page comes from (a "source"):
    help:Page         a page of Visualised's help (the tutorials and reference that come with it), else the wiki's
    a web address     fetched; Markdown is shown as Markdown, a web page as its text and links
    a file            read from disk
    anything else     taken as Markdown itself
"""
import os
import re
from pathlib import Path
from urllib.parse import urljoin

from PySide6.QtCore import QEvent, QObject, QTimer, QUrl, Qt
from PySide6.QtGui import QColor, QDesktopServices, QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (QApplication, QDialog, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton,
                               QSizeGrip, QSplitter, QTextBrowser, QToolButton, QVBoxLayout, QWidget)

from . import markdown

WIKI = "https://github.com/wallisoft/vml/wiki/"
RAW_WIKI = "https://raw.githubusercontent.com/wiki/wallisoft/vml/"
HELP_DIRS = (Path(__file__).resolve().parent / "web" / "help", Path(__file__).resolve().parent.parent / "web" / "help")
HELP_PAGE = re.compile(r"^https?://github\.com/wallisoft/vml/wiki/?([^?#]*)(?:#(.*))?$")


def help_file(page):
    """The copy of a help page that comes with Visualised, or None."""
    for d in HELP_DIRS:
        f = d / f"{page or 'Home'}.md"
        if f.is_file():
            return f
    return None


def web_page_html(text):
    """A web page's readable part, for Qt's rich text: no scripts, styles or head."""
    text = re.sub(r"(?is)<(script|style|head|noscript|svg)\b.*?</\1>", "", text)
    m = re.search(r"(?is)<body\b[^>]*>(.*)</body>", text)
    body = m.group(1) if m else text
    body = re.sub(r"(?is)<(nav|header|footer)\b.*?</\1>", "", body) or body
    return f'<div style="font-size:16px; color:{markdown.INK}">{body}</div>'


class _Column(QObject):
    """Keeps a Markdown page to a reading column, as GitHub does: wide windows get margins, not mile-long lines."""
    WIDTH = 900

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Resize:
            fit_column(obj)
        return False


def fit_column(b):
    doc = b.document()
    side = max(32, (b.viewport().width() - _Column.WIDTH) // 2)
    fmt = doc.rootFrame().frameFormat()
    if fmt.leftMargin() != side:
        fmt.setLeftMargin(side); fmt.setRightMargin(side)
        fmt.setTopMargin(24); fmt.setBottomMargin(32)
        doc.rootFrame().setFrameFormat(fmt)


def style_browser(b):
    b.setOpenLinks(False)
    b.document().setDocumentMargin(0)
    b.document().setDefaultStyleSheet(f"a {{ color: {markdown.LINK}; text-decoration: none; }}"
                                      f" code, pre {{ background-color: {markdown.CODE_TINT}; }}")
    b.setStyleSheet("QTextBrowser { background: #FFFFFF; border: none; selection-background-color: #BFDBFE; }")
    b._column = _Column(b)
    b.installEventFilter(b._column)
    b.document().contentsChanged.connect(lambda: QTimer.singleShot(0, lambda: fit_column(b)))


class Reader:
    """What MarkdownBox and MarkdownView share: loading a source into a QTextBrowser, following its links, history."""

    def __init__(self, browser, on_title=None, on_loaded=None):
        self.browser, self.on_title, self.on_loaded = browser, on_title, on_loaded
        self.where = None                     # (kind, place): ("help", page) ("url", address) ("file", path) ("text", "")
        self.back_list, self.forward_list = [], []
        self.markdown_text = ""
        self.tab_lang = "lua"           # which language the ~~~script tabs show
        self.net, self._reply = None, None
        browser.anchorClicked.connect(self.follow)

    # ---- showing
    def show_markdown(self, text, anchor=""):
        self.markdown_text = str(text or "")
        self.browser.setHtml(markdown.to_html(self.markdown_text, tab_lang=self.tab_lang))
        first = re.search(r"^#\s+(.+)$", self.markdown_text, re.M)
        if self.on_title and first:
            self.on_title(first.group(1).strip())
        self._settle(anchor)

    def show_html(self, html_text, anchor=""):
        self.markdown_text = ""
        self.browser.setHtml(web_page_html(html_text))
        t = re.search(r"(?is)<title>(.*?)</title>", html_text)
        if self.on_title and t:
            self.on_title(re.sub(r"\s+", " ", t.group(1)).strip())
        self._settle(anchor)

    def _settle(self, anchor):
        def go():
            if anchor:
                self.browser.scrollToAnchor(markdown.slug(anchor) if not re.match(r"^[a-z0-9-]+$", anchor) else anchor)
            else:
                self.browser.verticalScrollBar().setValue(0)
        QTimer.singleShot(0, go)
        if self.on_loaded:
            self.on_loaded()

    def note(self, text):
        self.browser.setHtml(f'<p style="color:{markdown.MUTED}; font-size:16px">{text}</p>')

    # ---- loading
    def open(self, source, remember=True, base=None):
        """Show a source (see the module's notes). Returns False if it couldn't be shown here."""
        source = str(source or "")
        anchor = ""
        kind, place = self.classify(source, base)
        if "#" in place and kind in ("help", "url"):
            place, anchor = place.split("#", 1)
        if remember and self.where is not None:
            self.back_list.append(self.where)
            self.forward_list.clear()
        self.where = (kind, place)
        return self.load(kind, place, anchor)

    def classify(self, source, base=None):
        s = source.strip()
        m = HELP_PAGE.match(s)
        if m:
            return "help", (m.group(1) or "Home") + (f"#{m.group(2)}" if m.group(2) else "")
        if s.startswith("help:"):
            return "help", s[5:] or "Home"
        if re.match(r"^https?://", s):
            return "url", s
        if "\n" not in s and len(s) < 500 and s and os.path.isfile(os.path.expanduser(s)):
            return "file", os.path.abspath(os.path.expanduser(s))
        return "text", s

    def load(self, kind, place, anchor=""):
        if kind == "text":
            self.show_markdown(place, anchor)
            return True
        if kind == "file":
            try:
                text = Path(place).read_text(encoding="utf-8-sig", errors="replace")
            except OSError as exc:
                self.note(f"Couldn't read {place}: {exc}")
                return False
            self.browser.document().setBaseUrl(QUrl.fromLocalFile(os.path.dirname(place) + os.sep))   # its images
            if place.lower().endswith((".html", ".htm")):
                self.show_html(text, anchor)
            else:
                self.show_markdown(text, anchor)
            return True
        if kind == "help":
            f = help_file(place)
            if f is not None:
                self.show_markdown(f.read_text(encoding="utf-8-sig"), anchor)
                return True
            self.fetch(RAW_WIKI + (place or "Home") + ".md", anchor, fallback=WIKI + (place or "Home"))
            return True
        self.fetch(place, anchor, fallback=place)
        return True

    def fetch(self, url, anchor, fallback):
        from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
        if self.net is None:
            from PySide6.QtNetwork import QNetworkProxyFactory
            QNetworkProxyFactory.setUseSystemConfiguration(True)   # through the computer's proxy, where it has one
            self.net = QNetworkAccessManager(self.browser)
        if self._reply is not None:
            try:
                self._reply.abort()
            except RuntimeError:
                pass
        self.note("Loading…")
        req = QNetworkRequest(QUrl(url))
        req.setRawHeader(b"User-Agent", b"Visualised")
        req.setAttribute(QNetworkRequest.RedirectPolicyAttribute, QNetworkRequest.NoLessSafeRedirectPolicy)
        req.setTransferTimeout(12000)
        reply = self.net.get(req)
        self._reply = reply

        def done():
            if self._reply is not reply:
                return
            self._reply = None
            ok = reply.error() == QNetworkReply.NoError
            body = bytes(reply.readAll()).decode("utf-8", "replace") if ok else ""
            ctype = str(reply.header(QNetworkRequest.ContentTypeHeader) or "").lower()
            reply.deleteLater()
            if not ok or not body.strip():
                self.note(f'This page couldn\'t be loaded here. <a href="{fallback}">Open it in the browser</a>.')
                return
            looks_html = "html" in ctype or re.match(r"(?is)\s*(<!doctype html|<html)", body)
            if looks_html and not url.lower().endswith(".md"):
                self.show_html(body, anchor)
            else:
                self.show_markdown(body, anchor)
        reply.finished.connect(done)

    # ---- links
    def follow(self, qurl):
        href = qurl.toString()
        if href.startswith("#"):
            self.browser.scrollToAnchor(href[1:])
            return
        if href.startswith("lang:"):                 # a ~~~script tab: re-show this page in that language, keep our place
            self.tab_lang = href[5:]
            bar = self.browser.verticalScrollBar()
            pos = bar.value()
            self.browser.setHtml(markdown.to_html(self.markdown_text, tab_lang=self.tab_lang))
            QTimer.singleShot(0, lambda: bar.setValue(pos))
            return
        kind, place = self.where or ("text", "")
        if re.match(r"^(mailto:|tel:)", href):
            QDesktopServices.openUrl(qurl)
            return
        if HELP_PAGE.match(href) or href.startswith("help:"):
            self.open(href)
            return
        if re.match(r"^https?://", href):
            if href.split("#")[0].lower().endswith(".md"):
                self.open(href)
            else:
                QDesktopServices.openUrl(qurl)           # a web page of someone else's: the browser is the place for it
            return
        # a link relative to where we are
        if kind == "help":
            self.open("help:" + href.lstrip("./"))
        elif kind == "url":
            self.open(urljoin(place, href))
        elif kind == "file":
            path, _, anchor = href.partition("#")
            target = os.path.normpath(os.path.join(os.path.dirname(place), path))
            if os.path.isfile(target) and target.lower().endswith((".md", ".markdown", ".txt")):
                self.open(target)
                if anchor:
                    QTimer.singleShot(0, lambda: self.browser.scrollToAnchor(anchor))
            elif os.path.exists(target):
                QDesktopServices.openUrl(QUrl.fromLocalFile(target))
        else:
            QDesktopServices.openUrl(qurl)

    def back(self):
        if self.back_list:
            self.forward_list.append(self.where)
            self.where = self.back_list.pop()
            self.load(*self.where)

    def forward(self):
        if self.forward_list:
            self.back_list.append(self.where)
            self.where = self.forward_list.pop()
            self.load(*self.where)

    def address(self):
        """Where this page lives on the web, if anywhere (for "open in the browser")."""
        kind, place = self.where or ("text", "")
        if kind == "help":
            return WIKI + place
        if kind == "url":
            return place
        if kind == "file":
            return QUrl.fromLocalFile(place).toString()
        return ""


def editor_font():
    f = QFont("monospace")
    f.setStyleHint(QFont.Monospace)
    f.setPointSize(10)
    return f


class Writer(QSplitter):
    """Markdown on the left, how it looks on the right, refreshed as you type (a moment after you stop)."""

    def __init__(self, parent=None):
        super().__init__(Qt.Horizontal, parent)
        self.edit = QPlainTextEdit()
        self.edit.setFont(editor_font())
        self.edit.setTabStopDistance(28)
        self.edit.setStyleSheet("QPlainTextEdit { border: none; border-right: 1px solid #E5E7EB; background: #FAFAFA;"
                                " color: #111827; padding: 10px; }")
        self.preview = QTextBrowser()
        style_browser(self.preview)
        self.preview.anchorClicked.connect(lambda u: self.preview.scrollToAnchor(u.toString()[1:]) if u.toString().startswith("#")
                                           else QDesktopServices.openUrl(u))
        self.addWidget(self.edit)
        self.addWidget(self.preview)
        self.setSizes([500, 500])
        self.setHandleWidth(1)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(200)
        self.timer.timeout.connect(self.refresh)
        self.edit.textChanged.connect(self.timer.start)

    def refresh(self):
        bar = self.preview.verticalScrollBar()
        keep = bar.value()
        self.preview.setHtml(markdown.to_html(self.edit.toPlainText()))
        bar.setValue(keep)

    def text(self):
        return self.edit.toPlainText()

    def set_text(self, text):
        if self.edit.toPlainText() != str(text or ""):
            self.edit.setPlainText(str(text or ""))
            self.refresh()


class MarkdownBox(QDialog):
    """The reader, in the boxes' frame. editable: Markdown can be changed, and Save gives it back."""

    def __init__(self, parent, source="", title="", edge="", editable=False, save_to=""):
        from . import dialogs
        super().__init__(parent if parent is not None else QApplication.activeWindow())
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setWindowTitle(str(title or "Help"))
        from .theme import theme
        # a reader is a window to read in: a light bar as the desktop's own title bars, and a quiet edge, as every
        # form has; the app's colour shows in the accent (its buttons, links and find box), not in a dark band
        self.edge = QColor(theme().edge)
        self.setObjectName("VmlBox")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setAttribute(Qt.WA_DeleteOnClose, not editable)
        self.setStyleSheet(dialogs.box_sheet(dialogs.accent_for(edge)) +
                           " QToolButton#nav { border: none; border-radius: 6px; padding: 3px 8px; color: #374151; font-size: 14px; }"
                           " QToolButton#nav:hover { background: #F3F4F6; } QToolButton#nav:disabled { color: #D1D5DB; }"
                           " QLineEdit#find { padding: 3px 8px; }"
                           f" QDialog#VmlBox {{ background: {theme().surface}; }}"   # (a window, not a card: solid)
                           f" QWidget#MdBand {{ background: {'#242424' if theme().dark else '#ECEFF3'};"
                           f" border-top: 1px solid {theme().line}; border-bottom: 1px solid {theme().line}; }}")
        self.editable, self.save_to, self.saved = bool(editable), str(save_to or ""), None
        self.fixed_title = str(title or "")
        frame = QVBoxLayout(self)
        frame.setContentsMargins(dialogs.EDGE, dialogs.EDGE, dialogs.EDGE, dialogs.EDGE)
        frame.setSpacing(0)
        self.bar = dialogs._Bar(self, self.windowTitle(), QColor(theme().title_bg))
        frame.addWidget(self.bar)

        band = QWidget()                                 # (a shade darker than the page: the tools don't blend into it)
        band.setObjectName("MdBand")
        band.setAttribute(Qt.WA_StyledBackground, True)
        tools = QHBoxLayout(band)
        tools.setContentsMargins(10, 6, 10, 6)
        tools.setSpacing(4)

        def tool(text, tip, fn):
            b = QToolButton()
            b.setObjectName("nav")
            b.setText(text)
            b.setToolTip(tip)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(fn)
            tools.addWidget(b)
            return b
        self.b_back = tool("◀", "Back (Alt+Left)", lambda: self.reader.back())
        self.b_fwd = tool("▶", "Forward (Alt+Right)", lambda: self.reader.forward())
        self.b_home = tool("⌂", "Contents", lambda: self.reader.open("help:Home"))
        self.b_mode = tool("Edit", "Change the Markdown", self.toggle_mode)
        tools.addStretch(1)
        self.find = QLineEdit()
        self.find.setObjectName("find")
        self.find.setPlaceholderText("Find  (Ctrl+F)")
        self.find.setFixedWidth(200)
        self.find.returnPressed.connect(self.find_next)
        tools.addWidget(self.find)
        self.b_web = tool("↗", "Open in the browser", self.open_outside)
        frame.addWidget(band)

        self.browser = QTextBrowser()
        style_browser(self.browser)
        self.reader = Reader(self.browser, on_title=self.titled, on_loaded=self.refresh_tools)
        self.writer = Writer()
        self.writer.hide()
        frame.addWidget(self.browser, 1)
        frame.addWidget(self.writer, 1)

        foot_band = QWidget()
        foot_band.setObjectName("MdBand")
        foot_band.setAttribute(Qt.WA_StyledBackground, True)
        foot = QHBoxLayout(foot_band)
        foot.setContentsMargins(16, 6, 4, 2)
        self.status = QLabel("")
        self.status.setStyleSheet("color: #6B7280; font-size: 12px;")
        foot.addWidget(self.status, 1)
        if self.editable:
            cancel = QPushButton("Cancel")
            cancel.clicked.connect(self.reject)
            save = QPushButton("Save")
            save.setDefault(True)
            save.clicked.connect(self.save)
            foot.addWidget(cancel)
            foot.addWidget(save)
            foot.addSpacing(8)
        foot.addWidget(QSizeGrip(self), 0, Qt.AlignBottom | Qt.AlignRight)
        frame.addWidget(foot_band)

        QShortcut(QKeySequence.Find, self, activated=lambda: (self.find.setFocus(), self.find.selectAll()))
        QShortcut(QKeySequence("Alt+Left"), self, activated=self.reader.back)
        QShortcut(QKeySequence("Alt+Right"), self, activated=self.reader.forward)
        QShortcut(QKeySequence("Escape"), self, activated=self.reject)

        screen = (parent.screen() if parent is not None else QApplication.primaryScreen()).availableGeometry()
        self.resize(min(980 if editable else 860, int(screen.width() * 0.85)), min(720, int(screen.height() * 0.85)))
        if source:
            self.reader.open(source)
        if self.editable:
            self.toggle_mode()
        self.refresh_tools()

    def paintEvent(self, e):
        from PySide6.QtGui import QPainter
        from . import dialogs
        super().paintEvent(e)
        p = QPainter(self)
        w, h, t = self.width(), self.height(), dialogs.EDGE
        for r in ((0, 0, w, t), (0, h - t, w, t), (0, 0, t, h), (w - t, 0, t, h)):
            p.fillRect(*r, self.edge)
        p.end()

    def titled(self, text):
        if not self.fixed_title:
            self.bar.caption.setText(text)
            self.setWindowTitle(text)

    def refresh_tools(self):
        kind = (self.reader.where or ("text", ""))[0]
        self.b_back.setEnabled(bool(self.reader.back_list))
        self.b_fwd.setEnabled(bool(self.reader.forward_list))
        self.b_back.setVisible(not (not self.writer.isHidden()))
        self.b_fwd.setVisible(not (not self.writer.isHidden()))
        self.b_home.setVisible(kind == "help" and not (not self.writer.isHidden()))
        self.b_web.setVisible(kind in ("help", "url") and not (not self.writer.isHidden()))
        self.b_mode.setVisible(self.editable)
        self.find.setVisible(not (not self.writer.isHidden()))
        self.b_mode.setText("Preview" if (not self.writer.isHidden()) else "Edit")
        if kind == "help":
            self.status.setText("Visualised help · the latest is on the wiki (↗)")
        elif kind == "url":
            self.status.setText(self.reader.where[1])
        elif kind == "file":
            self.status.setText(self.reader.where[1])

    def toggle_mode(self):
        if (not self.writer.isHidden()):
            self.reader.show_markdown(self.writer.text())
            self.writer.hide()
            self.browser.show()
        else:
            self.writer.set_text(self.reader.markdown_text)
            self.writer.refresh()
            self.browser.hide()
            self.writer.show()
            self.writer.edit.setFocus()
        self.refresh_tools()

    def find_next(self):
        text = self.find.text()
        if text and not self.browser.find(text):
            c = self.browser.textCursor()
            c.movePosition(c.MoveOperation.Start)
            self.browser.setTextCursor(c)
            if not self.browser.find(text):
                self.status.setText(f"“{text}” isn't on this page")

    def open_outside(self):
        url = self.reader.address()
        if url:
            QDesktopServices.openUrl(QUrl(url))

    def text(self):
        return self.writer.text() if (not self.writer.isHidden()) else self.reader.markdown_text

    def save(self):
        self.saved = self.text()
        if self.save_to:
            try:
                Path(self.save_to).write_text(self.saved, encoding="utf-8")
            except OSError as exc:
                self.status.setText(f"Couldn't save: {exc}")
                return
        self.accept()

    def run(self):
        """Wait for Save or Cancel. Returns the Markdown saved, or None."""
        self.setModal(True)
        QTimer.singleShot(0, lambda: (self.raise_(), self.activateWindow()))
        self.exec()
        out = self.saved
        self.deleteLater()
        return out


# ------------------------------------------------------------------ the controls

from .registry import ATTACHED, COMMON, ControlType, Prop, register, truthy   # noqa: E402

PLAIN = [p for p in COMMON if p.name not in ("CornerRadius",)]


class MarkdownViewWidget(QTextBrowser):
    def __init__(self, node):
        super().__init__()
        self.node = node
        style_browser(self)
        self.reader = Reader(self)


def _view_text(n, v):
    if not str(n.props.get("Source") or "").strip():
        n.widget.reader.where = ("text", "")
        n.widget.reader.show_markdown(str(v or "").replace("\\n", "\n"))    # (a form's line can't break: \n there is a new line)


def _view_source(n, v):
    v = str(v or "").strip()
    if v:
        n.widget.reader.open(v, remember=False)
    else:
        _view_text(n, n.props.get("Text"))


register(ControlType("MarkdownView", lambda n: MarkdownViewWidget(n)),
         PLAIN, ATTACHED,
         [Prop("Text", "text", "Common", apply=_view_text),                      # the Markdown it shows
          Prop("Source", "text", "Common", apply=_view_source)])                 # or where it comes from: a file, an address, help:Page


class MarkdownEditorWidget(Writer):
    def __init__(self, node):
        super().__init__()
        self.node = node
        self.textChanged = self.edit.textChanged


def _ed_preview(n, v):
    n.widget.preview.setVisible(truthy(v) if str(v or "").strip() else True)


register(ControlType("MarkdownEditor", lambda n: MarkdownEditorWidget(n),
                     events={"TextChanged": lambda node, fire: node.widget.edit.textChanged.connect(lambda *a: fire({}))}),
         PLAIN, ATTACHED,
         [Prop("Text", "text", "Common", apply=lambda n, v: n.widget.set_text(v), read=lambda n: n.widget.text()),
          Prop("ShowPreview", "bool", "Common", default="true", apply=_ed_preview)])   # how it looks, beside the text
