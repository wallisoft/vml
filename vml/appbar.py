"""
The app bar: Terms · About · the version, along the foot of a form's window, with a ⚠ when a newer version is out.
Clicking the ⚠ installs it. How newer decides how loud: a new major version (2.0 after 1.x) is red, a new minor one
(1.3 after 1.2) yellow, and a fix (1.2.5 after 1.2.4) shows nothing until About is opened, which offers it.

    @Window TinyTalk
    Version=0.7.0
    AppBar=true
    Terms=https://tiny-talk.world/terms.html                 (optional: no Terms link without it)
    About=Say it in pictures anyone can read.                 (optional: a line or two for the About box)
    UpdateFrom=https://visualised.org/downloads/TinyTalk.vml  (optional: where the newest copy of this form is)
    UpdateApk=https://visualised.org/downloads/TinyTalk.apk   (optional: the same for the phone app)

If the form has a control called StatusBar, the bar's pieces sit at its right-hand end instead of in a strip of
their own. The designer always has the bar, and its ⚠ updates Visualised itself (not from the Microsoft Store,
which keeps its copies up to date).

Updating a form: the newer .vml is downloaded, checked (it must be a form, and newer), the old one kept beside it
as .vml.bak, and the app opened again. On a phone, the new APK is opened, for Android to install. A web page is
loaded afresh.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.request
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, Qt, QTimer, Signal
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QMessageBox, QPushButton, QWidget

HEIGHT = 24
SETUP_EXE = "https://github.com/wallisoft/vml-releases/releases/latest/download/Visualised-Setup.exe"
INSTALL_SH = "https://github.com/wallisoft/vml-releases/releases/latest/download/install.sh"
VISUALISED_TERMS = "https://visualised.io/terms.html"


def number(v):
    return tuple(int(x) for x in re.findall(r"\d+", str(v or ""))[:4])


def newer(latest, current):
    return bool(number(latest)) and number(latest) > number(current)


def level(latest, current):
    """How much newer: "major", "minor", "fix", or "" (not newer)."""
    if not newer(latest, current):
        return ""
    a, b = number(latest) + (0, 0), number(current) + (0, 0)
    return "major" if a[0] > b[0] else "minor" if a[:2] > b[:2] else "fix"


def form_version(text):
    """The Version= of a form's window, from the start of a .vml."""
    m = re.search(r"^@Window\b[^\n]*\n(?:(?!^@)[^\n]*\n)*?Version=([^\n]*)", text, re.M)
    return m.group(1).strip() if m else ""


def _get(url, limit, rng=False):
    head = {"User-Agent": "Visualised"}
    if rng:
        head["Range"] = f"bytes=0-{limit - 1}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=head), timeout=60 if not rng else 8) as r:
        return r.read(limit + 1)


def wanted(engine, node):
    from .projects import is_designer
    return node.type.name == "Window" and (str(node.props.get("AppBar", "")).lower() in ("true", "1", "yes")
                                           or is_designer(node.scope))


def restart_command():
    argv = list(sys.argv)
    if argv and argv[0].endswith("__main__.py"):
        return [sys.executable, "-m", "vml"] + argv[1:]
    if argv and argv[0].endswith(".py"):
        return [sys.executable] + argv
    return [sys.executable] + argv[1:]


class _Done(QObject):
    done = Signal(object)


class AppBar(QWidget):
    def __init__(self, engine, node, colour, parent=None):
        super().__init__(parent)
        self.engine, self.node = engine, node
        from .projects import is_designer
        self.designer = is_designer(node.scope)
        p = node.props
        if self.designer:
            from . import __version__
            self.version, self.title = __version__, "Visualised"
            self.terms = str(p.get("Terms") or VISUALISED_TERMS)
        else:
            self.version, self.title = str(p.get("Version") or ""), str(p.get("Title") or node.name)
            self.terms = str(p.get("Terms") or "")
        self.latest, self.level, self.info = "", "", {}
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 0, 8, 0)
        lay.setSpacing(6)
        lay.addStretch(1)
        link = f"color:{colour};text-decoration:none"

        def piece(text, href):
            lab = QLabel(f'<a href="{href}" style="{link}">{text}</a>')
            lab.setTextFormat(Qt.RichText)
            lab.setStyleSheet(f"color:{colour};font-size:11px;background:transparent")
            lab.setCursor(Qt.PointingHandCursor)
            lab.linkActivated.connect(self.clicked)
            return lab

        def dot():
            lab = QLabel("·")
            lab.setStyleSheet(f"color:{colour};font-size:11px;background:transparent")
            return lab
        if self.terms:
            lay.addWidget(piece("Terms", "terms"))
            lay.addWidget(dot())
        lay.addWidget(piece("About", "about"))
        if self.version:
            lay.addWidget(dot())
            lay.addWidget(piece("v" + self.version, "about"))
        self.hazard = QPushButton("⚠")
        self.hazard.setCursor(Qt.PointingHandCursor)
        self.hazard.clicked.connect(self.install)
        self.hazard.hide()
        lay.addWidget(self.hazard)
        self.setFixedHeight(HEIGHT)
        self._sig = _Done()
        self._sig.done.connect(self._checked)
        QTimer.singleShot(1500, self.check)

    # ---- the check (in the background: the app never waits for it)
    def check(self):
        url = str(self.node.props.get("UpdateFrom") or "")
        if not self.designer and not url:
            return

        def go():
            out = {}
            try:
                if self.designer:
                    out = json.loads(self.engine.cmd_CheckForUpdate())
                else:
                    text = _get(url, 32768, rng=True).decode("utf-8", "replace")
                    out = {"latest": form_version(text)}
                    out["newer"] = newer(out["latest"], self.version)
            except Exception as exc:
                out = {"error": str(exc)}
            self._sig.done.emit(out)
        threading.Thread(target=go, daemon=True).start()

    def _checked(self, out):
        self.info = out or {}
        if self.info.get("newer") and not self.info.get("store"):
            self.latest = self.info.get("latest", "")
            self.level = level(self.latest, self.version) or "fix"
            self.engine.log_line(f"{self.title} {self.latest} is out (this is {self.version}): a {self.level} update")
            if self.level == "fix":                          # a fix: About offers it, the bar stays quiet
                return
            bg, fg, hover = ("#DC2626", "#FFFFFF", "#B91C1C") if self.level == "major" else ("#FACC15", "#422006", "#EAB308")
            self.hazard.setStyleSheet(f"QPushButton{{background:{bg};color:{fg};border:0;border-radius:8px;"
                                      f"padding:1px 8px;font-size:11px;font-weight:600}}QPushButton:hover{{background:{hover}}}")
            self.hazard.setText(f"⚠ {self.latest}")
            self.hazard.setToolTip(f"{self.title} {self.latest} is out (this is {self.version}). Click to install it.")
            self.hazard.show()

    # ---- the links
    def clicked(self, what):
        if what == "terms":
            self.engine.cmd_OpenUrl(self.terms)
        else:
            self.about()

    def about(self):
        from . import __version__
        about = str(self.node.props.get("About") or "")
        lines = [f"{self.title} {self.version}".strip()]
        if about:
            lines += ["", about]
        if self.designer:
            lines += ["", "Design desktop, web and phone apps in VML.", "Made by Wallisoft. visualised.io"]
        else:
            lines += ["", f"Made with Visualised {__version__}."]
        if self.latest:
            lines += ["", f"{self.title} {self.latest} is available."]
            box = QMessageBox(QMessageBox.Information, f"About {self.title}", "\n".join(lines), parent=self.window())
            now = box.addButton("Download now", QMessageBox.AcceptRole)
            box.addButton("Later", QMessageBox.RejectRole)
            box.exec()
            if box.clickedButton() is now:
                self.install(asked=True)
            return
        QMessageBox.about(self.window(), f"About {self.title}", "\n".join(lines))

    # ---- installing the newer one
    def install(self, asked=False):
        win = self.window()
        if not asked and QMessageBox.question(win, f"Update {self.title}",
                                f"{self.title} {self.latest} is out (this is {self.version}).\n\nInstall it now? "
                                f"{self.title} will close and open again.") != QMessageBox.Yes:
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            problem = self._install_visualised() if self.designer else self._install_form()
        except Exception as exc:
            problem = str(exc)
        finally:
            QApplication.restoreOverrideCursor()
        if problem:
            QMessageBox.warning(win, f"Update {self.title}", f"It couldn't be updated here:\n\n{problem}\n\n"
                                "The download page will open instead.")
            self.engine.cmd_OpenUrl(self.info.get("url") or str(self.node.props.get("UpdateFrom") or ""))

    def _install_form(self):
        url = str(self.node.props.get("UpdateFrom") or "")
        data = _get(url, 64 * 1024 * 1024)
        text = data.decode("utf-8")
        got = form_version(text)
        if not got or not newer(got, self.version):
            return f"What came back from {url} isn't a newer copy of this form."
        path = Path(self.node.scope)
        shutil.copy2(path, str(path) + ".bak")
        path.write_bytes(data)
        self.engine.log_line(f"{path.name} updated to {got} (the old one is {path.name}.bak)")
        subprocess.Popen(restart_command(), cwd=os.getcwd())
        QApplication.quit()
        return ""

    def _install_visualised(self):
        frozen = not (sys.argv and sys.argv[0].endswith(".py"))
        if not frozen:
            return "This Visualised runs from its source code: update it with git."
        if sys.platform.startswith("win"):
            exe = os.path.join(tempfile.mkdtemp(prefix="vml-update-"), "Visualised-Setup.exe")
            with open(exe, "wb") as f:
                f.write(_get(SETUP_EXE, 512 * 1024 * 1024))
            subprocess.Popen([exe, "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART"], close_fds=True)
            QApplication.quit()
            return ""
        home = Path.home() / ".local" / "opt" / "vml"
        if sys.platform.startswith("linux") and Path(sys.executable).resolve().is_relative_to(home.resolve()):
            script = os.path.join(tempfile.mkdtemp(prefix="vml-update-"), "install.sh")
            with open(script, "wb") as f:
                f.write(_get(INSTALL_SH, 1024 * 1024))
            r = subprocess.run(["bash", script], capture_output=True, text=True, timeout=900, stdin=subprocess.DEVNULL)
            if r.returncode != 0:
                return (r.stdout + r.stderr)[-600:]
            subprocess.Popen([str(home / "vml")] + sys.argv[1:], cwd=os.getcwd())
            QApplication.quit()
            return ""
        return "Visualised can update itself on Windows and from the Linux installer."


class _Follow(QObject):
    """Keeps a bar at the right-hand end of a StatusBar as it changes size."""

    def __init__(self, host, bar):
        super().__init__(host)
        self.host, self.bar = host, bar
        host.installEventFilter(self)
        self.place()

    def place(self):
        w = max(self.bar.sizeHint().width(), self.bar.minimumSizeHint().width())
        self.bar.setGeometry(max(0, self.host.width() - w), 0, w, self.host.height())
        self.bar.raise_()

    def eventFilter(self, obj, e):
        if e.type() in (QEvent.Resize, QEvent.Show, QEvent.LayoutRequest):
            QTimer.singleShot(0, self.place)
        return False


def attach(engine, node):
    """Give a window its app bar (once), before it is shown."""
    w = node.widget
    if getattr(w, "_appbar", None) is not None or not wanted(engine, node):
        return
    status = engine.scopes.get(node.scope, {}).get("StatusBar")
    if status is not None:
        text = engine.scopes.get(node.scope, {}).get("statusText")
        colour = str((text.props.get("Foreground") if text else "") or "#DBEAFE")
        bar = AppBar(engine, node, colour, parent=status.widget)
        bar.setStyleSheet("background:transparent")
        bar._follow = _Follow(status.widget, bar)
        bar.show()
    else:
        bar = AppBar(engine, node, "#6B7280")
        bar.setObjectName("vml_appbar")
        bar.setAttribute(Qt.WA_StyledBackground, True)
        bar.setStyleSheet("#vml_appbar{border-top:1px solid #E5E7EB}")
        w.layout().addWidget(bar)
        w.resize(w.width(), w.height() + HEIGHT)
    w._appbar = bar
