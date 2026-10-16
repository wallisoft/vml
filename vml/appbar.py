"""
The app bar: Terms · About · the version, along the foot of a form's window, with a ⚠ when a newer version is out.
Clicking the ⚠ installs it. How newer decides how loud: a new major version (2.0 after 1.x) is red, a new minor one
(1.3 after 1.2) yellow, and a fix (1.2.5 after 1.2.4) shows nothing until About is opened, which offers it.

    @Window TinyTalk
    Version=0.7.0
    AppBar=true
    Terms=https://tiny-talk.world/terms.html                 (optional: no Terms link without it)
    About=Say it in pictures anyone can read.                 (optional: a line or two for the About box)
    UpdateFrom=https://visualised.org/downloads/TinyTalk.vml  (optional: where the newest copy of this form is;
                                                               github:owner/repo for an app released on GitHub;
                                                               github:owner/repo/path/App.vml for a .vml app kept
                                                               in a public repo: tags stable, main the edge)
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
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QPushButton, QWidget

HEIGHT = 24
SETUP_EXE = "https://github.com/wallisoft/vml-releases/releases/latest/download/Visualised-Setup.exe"
INSTALL_SH = "https://github.com/wallisoft/vml-releases/releases/latest/download/install.sh"
VISUALISED_TERMS = "https://tiny-web.uk/terms.php"            # Visualised is a TinyWeb service: TinyWeb's terms


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


# ---- GitHub releases: UpdateFrom=github:owner/repo (or the repo's https://github.com/... address). The repo must be
# public. The newest release is found from where its latest download points (no API, so no rate limit), and the
# installer for this computer comes from it: NAME-Setup.exe on Windows, install.sh on Linux, NAME.apk on a phone.
GITHUB = re.compile(r"^(?:github:|https?://(?:www\.)?github\.com/)([\w.-]+)/([\w.-]+?)(?:\.git)?(?:/.*)?$", re.I)


def github_repo(url):
    m = GITHUB.match(str(url or "").strip())
    return f"{m.group(1)}/{m.group(2)}" if m else ""


def github_asset(name):
    if sys.platform.startswith("win"):
        return f"{name}-Setup.exe"
    if sys.platform.startswith("linux"):
        return "install.sh"
    return ""


class _Stay(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None                                      # (the redirect itself is the answer: it names the tag)


def github_latest(repo, asset):
    """The newest release's tag (without a leading v), from where releases/latest/download/ASSET points; failing that,
    GitHub's API. "" if neither says."""
    import urllib.error
    if asset:
        req = urllib.request.Request(f"https://github.com/{repo}/releases/latest/download/{asset}",
                                     headers={"User-Agent": "Visualised"}, method="HEAD")
        try:
            urllib.request.build_opener(_Stay).open(req, timeout=10)
        except urllib.error.HTTPError as e:
            m = re.search(r"/releases/download/([^/]+)/", e.headers.get("Location", "") or "")
            if m:
                return m.group(1).lstrip("vV")
        except Exception:
            pass
    try:
        req = urllib.request.Request(f"https://api.github.com/repos/{repo}/releases/latest",
                                     headers={"User-Agent": "Visualised", "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return str(json.load(r).get("tag_name", "")).lstrip("vV")
    except Exception:
        return ""


# ---- a .vml app kept in a public GitHub repo: UpdateFrom=github:owner/repo/path/App.vml (@branch, default main).
# Stable: the repo's release tags (v1.3.0...), read the way git reads them, not through the API; a new major or minor
# one turns the ⚠ red or yellow, and installs that tag's copy of the file. Edge: the file on the branch, newer than
# any tag: only About mentions it ("Latest from main"), for whoever wants it. Either way the old copy is kept as
# .vml.bak, and About offers to go back to it.
VMLFILE = re.compile(r"^github:([\w.-]+)/([\w.-]+)/(.+?\.vml)(?:@([\w./-]+))?$", re.I)


def github_vml(url):
    m = VMLFILE.match(str(url or "").strip())
    return {"repo": f"{m.group(1)}/{m.group(2)}", "path": m.group(3), "branch": m.group(4) or "main"} if m else None


def github_tags(repo):
    """The repo's tags that are versions, newest last, from git's own list of refs (anyone may read a public one)."""
    data = _get(f"https://github.com/{repo}.git/info/refs?service=git-upload-pack", 4 * 1024 * 1024).decode("latin-1")
    tags = {t for t in re.findall(r"refs/tags/([^\s^]+)", data) if number(t)}
    return sorted(tags, key=number)


def raw_url(spec, ref):
    return f"https://raw.githubusercontent.com/{spec['repo']}/{ref}/{spec['path']}"


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
        self.latest, self.level, self.info, self.edge_version = "", "", {}, ""
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
                elif github_vml(url):
                    spec = github_vml(url)
                    tags = github_tags(spec["repo"])
                    stable = tags[-1] if tags else ""
                    try:
                        edge = form_version(_get(raw_url(spec, spec["branch"]), 32768, rng=True).decode("utf-8", "replace"))
                    except Exception:
                        edge = ""
                    out = {"spec": spec, "tag": stable, "latest": stable.lstrip("vV"), "edge": edge,
                           "url": f"https://github.com/{spec['repo']}/releases"}
                    out["newer"] = newer(out["latest"], self.version)
                elif github_repo(url):
                    repo = github_repo(url)
                    out = {"latest": github_latest(repo, github_asset(self.node.name)),
                           "url": f"https://github.com/{repo}/releases/latest", "repo": repo}
                    out["newer"] = newer(out["latest"], self.version)
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
        edge = self.info.get("edge", "")
        self.edge_version = edge if edge and newer(edge, self.version) and newer(edge, self.info.get("latest") or "0") else ""
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
            self.engine.cmd_ShowMarkdown(self.terms, "Terms")      # in a window of the app: reading them shouldn't mean leaving it
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
        from . import dialogs
        buttons = []
        if self.latest:
            lines += ["", f"{self.title} {self.latest} is available."]
            buttons.append(f"Install {self.latest}")
        if self.edge_version:
            lines += ["", f"The latest from {self.info['spec']['branch']} is {self.edge_version}: not a release yet, so not tested"
                          " as much. You can go back afterwards."]
            buttons.append(f"Latest from {self.info['spec']['branch']} ({self.edge_version})")
        back = self.backup()
        if back:
            lines += ["", f"The copy before the last update ({back}) is kept, if this one doesn't suit."]
            buttons.append(f"Go back to {back}")
        if not buttons:
            dialogs.message(self.window(), f"About {self.title}", "\n".join(lines), self.edge())
            return
        picked = dialogs.choose(self.window(), f"About {self.title}", "\n".join(lines), tuple(buttons) + ("Close",), self.edge())
        if picked.startswith("Install "):
            self.install(asked=True)
        elif picked.startswith("Latest from "):
            self.install(asked=True, edge=True)
        elif picked.startswith("Go back to "):
            self.go_back()

    def backup(self):
        """The Version of the copy kept from before the last update ("" if there's none)."""
        if self.designer or not str(self.node.scope).endswith(".vml"):
            return ""
        try:
            with open(str(self.node.scope) + ".bak", "rb") as f:
                return form_version(f.read(65536).decode("utf-8", "replace"))
        except OSError:
            return ""

    def go_back(self):
        """Swap the kept copy back in (the newer one becomes the kept copy, so this can be undone too) and reopen."""
        path = Path(self.node.scope)
        bak, tmp = Path(str(path) + ".bak"), Path(str(path) + ".swap")
        try:
            path.replace(tmp)
            bak.replace(path)
            tmp.replace(bak)
        except OSError as exc:
            self.say(f"Go back", f"It couldn't swap the copies back:\n\n{exc}")
            return
        self.engine.log_line(f"{path.name}: back to the copy kept before the last update")
        subprocess.Popen(restart_command(), cwd=os.getcwd())
        QApplication.quit()

    def edge(self):
        """The boxes' frame: the colour of this window's menu bar, as the app's own boxes have."""
        try:
            return self.engine._edge()
        except Exception:
            return ""

    def say(self, title, text):
        from . import dialogs
        dialogs.message(self.window(), title, text, self.edge())

    # ---- installing the newer one
    def install(self, asked=False, edge=False):
        from . import dialogs
        self._edge_install = edge
        if not asked and not dialogs.confirm(self.window(), f"Update {self.title}",
                                             f"{self.title} {self.latest} is out (this is {self.version}).\n\nInstall it now? "
                                             f"{self.title} will close and open again.", self.edge()):
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            problem = self._install_visualised() if self.designer else \
                self._install_release() if self.info.get("repo") and not self.info.get("spec") else self._install_form()
        except Exception as exc:
            problem = str(exc)
        finally:
            QApplication.restoreOverrideCursor()
        if problem:
            self.say(f"Update {self.title}", f"It couldn't be updated here:\n\n{problem}\n\nThe download page will open instead.")
            self.engine.cmd_OpenUrl(self.info.get("url") or str(self.node.props.get("UpdateFrom") or ""))

    def _install_form(self):
        url = str(self.node.props.get("UpdateFrom") or "")
        spec = self.info.get("spec")
        if spec:                                         # a GitHub repo's file: the release tag's copy, or the branch's
            url = raw_url(spec, spec["branch"] if getattr(self, "_edge_install", False) else self.info["tag"])
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

    def _install_release(self):
        """A newer release on GitHub: its installer for this computer, run; then the app opens again."""
        repo, asset = self.info["repo"], github_asset(self.node.name)
        if sys.argv and sys.argv[0].endswith(".py"):
            return f"This {self.title} runs from its source code: update it with git."
        if not asset:
            return f"There's no {self.title} installer for this computer in its releases."
        url = f"https://github.com/{repo}/releases/latest/download/{asset}"
        folder = tempfile.mkdtemp(prefix="vml-update-")
        path = os.path.join(folder, asset)
        with open(path, "wb") as f:
            f.write(_get(url, 1024 * 1024 * 1024))
        if asset.endswith(".exe"):
            subprocess.Popen([path, "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART"], close_fds=True)
            QApplication.quit()
            return ""
        r = subprocess.run(["bash", path], capture_output=True, text=True, timeout=900, stdin=subprocess.DEVNULL)
        if r.returncode != 0:
            return (r.stdout + r.stderr)[-600:]
        self.engine.log_line(f"{self.title} updated to {self.latest} from {repo}")
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
        w = max(self.bar.sizeHint().width(), self.bar.minimumSizeHint().width()) + 8
        h = min(self.bar.height() or HEIGHT, self.host.height())
        self.bar.setGeometry(max(0, self.host.width() - w), max(0, (self.host.height() - h) // 2), w, h)
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
        colour = str(text.props.get("Foreground") or "") if text else ""
        if not colour:                                   # dark text on a light bar, light on a dark one
            from PySide6.QtGui import QColor
            from .registry import qcolour
            bg = status.props.get("Background") or ""
            colour = "#DBEAFE" if bg and qcolour(bg).lightnessF() < 0.55 else "#4B5563"
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
