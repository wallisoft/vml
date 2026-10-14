"""
Commands for apps that live beside the user's other programs: SSH drives, a tray icon, starting with the computer.

    SshMount(drive, handler)    a folder on an SSH server as a drive (see vml/sshdrive.py for what `drive` holds, as
                                JSON). handler gets (name, state, detail) each time it changes: connecting, mounted
                                (detail: where, and how), offline (it keeps trying), error (it waits for the user),
                                off; and once (name, "hostkey", fingerprint) the first time a server is met, for the
                                app to keep in the drive's "hostkey".
    SshUnmount(name)            ("" for all of them)
    SshStatus(name)             JSON {state, detail}, or of all of them by name
    SshTest(drive, handler)     try a drive without mounting it: handler gets (name, "ok", what it reached, the server's
                                key) or (name, "error", what went wrong, "")
    SshMethods()                JSON: what this computer can use (winfsp, webdav, sshfs), free drive letters, the user's
                                likely key files (keys, likeliest first) and whether an SSH agent has keys (agent)
    PickTextFile(handler, title, start) the user picks a file: handler gets (path, text, why not); answers the path
    Tray(tooltip, menu, handler) an icon by the clock; menu is items separated by | ("-" for a line). Clicking the
                                icon runs handler("open"), a menu item handler(its text). Closing the last window then
                                leaves the app running in the tray. Tray("") takes the icon away.
    TrayMessage(title, text)    a note from the tray icon
    StartAtBoot(on)             start this app when the user signs in to the computer ("false" stops it). Answers
                                "on" or "off". Started that way, LaunchedAtBoot() answers "true" (so an app can start
                                in the tray rather than open its window).
    Quit()                      close the app (drives are unmounted first)

On a phone (vml/html.py) SshMount adds the drive to the phone's Files app instead; the tray and starting at boot
mean nothing there and answer quietly.
"""
import json
import os
import queue
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication, QMenu, QStyle, QSystemTrayIcon

AT_BOOT = "--at-boot"


class SystemCommands:

    # ── answers from other threads, run on the main one ──
    def _sys_queue(self):
        if getattr(self, "_sysq", None) is None:
            self._sysq = queue.Queue()
            self._sys_timer = QTimer()
            self._sys_timer.setInterval(100)
            self._sys_timer.timeout.connect(self._sys_drain)
            self._sys_timer.start()
        return self._sysq

    def _sys_drain(self):
        while True:
            try:
                handler, args, origin = self._sysq.get_nowait()
            except queue.Empty:
                break
            if handler:
                try:
                    self.run_script(handler, *args, origin=origin)
                except Exception as exc:
                    self.log_line(f"{handler}: {exc}")

    # ── SSH drives ──
    def _drives(self):
        if getattr(self, "_ssh_drives", None) is None:
            from .sshdrive import Drives
            q = self._sys_queue()
            self._ssh_handlers = {}

            def changed(name, state, detail):
                h, origin = self._ssh_handlers.get(name, ("", None))
                q.put((h, (name, state, detail), origin))

            def hostkey(name, fp):
                h, origin = self._ssh_handlers.get(name, ("", None))
                q.put((h, (name, "hostkey", fp), origin))
            self._ssh_drives = Drives(on_change=changed, on_hostkey=hostkey)
            QApplication.instance().aboutToQuit.connect(self._ssh_drives.down_all)
        return self._ssh_drives

    def cmd_SshMount(self, drive="{}", handler=""):
        try:
            d = json.loads(drive) if isinstance(drive, str) else dict(drive)
        except ValueError:
            return "That drive isn't JSON."
        if not d.get("host"):
            return "A drive needs a host."
        name = d.get("name") or d["host"]
        d["name"] = name
        drives = self._drives()
        self._ssh_handlers[name] = (str(handler or ""), self._script_stack[-1] if self._script_stack else None)
        try:
            import paramiko  # noqa: F401
        except ImportError:
            self._sys_queue().put((str(handler or ""), (name, "error", "This copy of Visualised can't do SSH (paramiko is missing)."), None))
            return ""
        drives.up(d)
        return ""

    def cmd_SshTest(self, drive="{}", handler=""):
        """Try a drive without mounting it: handler gets (name, "ok", what it reached, the server's key) or
        (name, "error", what went wrong, "")."""
        import threading
        try:
            d = json.loads(drive) if isinstance(drive, str) else dict(drive)
        except ValueError:
            return "That drive isn't JSON."
        name = d.get("name") or d.get("host") or ""
        q = self._sys_queue()
        origin = self._script_stack[-1] if self._script_stack else None
        handler = str(handler or "")

        def run():
            try:
                from .sshdrive import test
                ok, detail, fp = test(d)
            except ImportError:
                ok, detail, fp = False, "This copy of Visualised can't do SSH (paramiko is missing).", ""
            q.put((handler, (name, "ok" if ok else "error", detail, fp), origin))
        if not d.get("host"):
            q.put((handler, (name, "error", "Which server? (Server is empty)", ""), origin))
        else:
            threading.Thread(target=run, daemon=True).start()
        return ""

    def cmd_SshUnmount(self, name=""):
        import threading
        drives = self._drives()
        names = [str(name)] if name else list(set(drives.wanted) | set(drives.running))
        for n in names:
            threading.Thread(target=drives.down, args=(n,), daemon=True).start()
        return ""

    def cmd_SshStatus(self, name=""):
        drives = self._drives()
        return json.dumps(drives.status.get(str(name), {"state": "off", "detail": ""}) if name else drives.status)

    def cmd_SshMethods(self):
        import shutil
        import string
        from .sshdrive import WINDOWS, winfsp_available
        letters = []
        if WINDOWS:
            import ctypes
            mask = ctypes.windll.kernel32.GetLogicalDrives()
            letters = [L + ":" for i, L in enumerate(string.ascii_uppercase) if i >= 3 and not mask >> i & 1]
        try:
            import wsgidav  # noqa: F401
            dav = True
        except ImportError:
            dav = False
        try:
            from .sshdrive import agent_available, likely_keys
            keys, agent = likely_keys(), agent_available()
        except ImportError:
            keys, agent = [], False
        return json.dumps({"winfsp": winfsp_available(), "webdav": dav, "sshfs": bool(shutil.which("sshfs")),
                           "windows": WINDOWS, "letters": letters, "keys": keys, "agent": agent,
                           "home": os.path.expanduser("~")})

    def cmd_PickTextFile(self, handler="", title="Open", start=""):
        """The user picks a file; handler gets (its path, its text, why not). On a phone the same command opens the
        phone's file picker (and the name is just the file's name)."""
        from . import dialogs
        path = dialogs.open_file(self._parent_window(), str(title or "Open"), os.path.expanduser(str(start or "")), edge=self._edge())
        if path and handler:
            try:
                if os.path.getsize(path) > 1048576:
                    raise OSError("That file is too big to read as text.")
                with open(path, encoding="utf-8", errors="replace") as f:
                    text, why = f.read(), ""
            except OSError as exc:
                text, why = "", str(exc)
            self._sys_queue().put((str(handler), (path, text, why), self._script_stack[-1] if self._script_stack else None))
        return path

    # ── the tray ──
    def cmd_Tray(self, tooltip="", menu="", handler=""):
        app = QApplication.instance()
        old = getattr(self, "_tray", None)
        if not tooltip:
            if old:
                old.hide()
                self._tray = None
            app.setQuitOnLastWindowClosed(True)
            return ""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return "This desktop has no tray."
        tray = old or QSystemTrayIcon(app)
        icon = app.windowIcon()
        if icon.isNull():
            win = QApplication.activeWindow() or next((w for w in app.topLevelWidgets() if w.isWindow()), None)
            icon = win.windowIcon() if win and not win.windowIcon().isNull() else app.style().standardIcon(QStyle.SP_DriveNetIcon)
        tray.setIcon(icon)
        tray.setToolTip(str(tooltip))
        origin = self._script_stack[-1] if self._script_stack else None
        handler = str(handler or "")
        q = self._sys_queue()
        m = QMenu()
        for item in [x.strip() for x in str(menu or "").split("|") if x.strip()]:
            if item == "-":
                m.addSeparator()
                continue
            act = QAction(item, m)
            act.triggered.connect(lambda _=False, t=item: q.put((handler, (t,), origin)))
            m.addAction(act)
        tray.setContextMenu(m)
        self._tray_menu = m                   # (Qt doesn't keep the menu alive for us)
        try:
            tray.activated.disconnect()
        except (TypeError, RuntimeError):
            pass
        tray.activated.connect(lambda reason: q.put((handler, ("open",), origin))
                               if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick) else None)
        tray.show()
        self._tray = tray
        if not getattr(self, "_tray_quit_hooked", False):          # gone before Qt is (no icon left behind)
            app.aboutToQuit.connect(lambda: getattr(self, "_tray", None) and self._tray.hide())
            self._tray_quit_hooked = True
        app.setQuitOnLastWindowClosed(False)  # closing the window leaves it in the tray
        return ""

    def cmd_TrayMessage(self, title="", text=""):
        tray = getattr(self, "_tray", None)
        if tray:
            tray.showMessage(str(title), str(text), QSystemTrayIcon.Information, 6000)
        return ""

    def cmd_Quit(self):
        QTimer.singleShot(0, QApplication.instance().quit)
        return ""

    # ── starting with the computer ──
    @staticmethod
    def _launch_command():
        """How this app was started, to start it the same way at sign-in."""
        args = [a for a in sys.argv[1:] if a != AT_BOOT]
        if "__compiled__" in globals() or getattr(sys, "frozen", False) or not sys.argv[0].endswith(".py"):
            cmd = [sys.executable] + args
        elif sys.argv[0].endswith("__main__.py"):
            cmd = [sys.executable, "-m", Path(sys.argv[0]).parent.name] + args
        else:
            cmd = [sys.executable, os.path.abspath(sys.argv[0])] + args
        return [os.path.abspath(a) if a.endswith((".vml", ".vmlproj")) and os.path.exists(a) else a for a in cmd] + [AT_BOOT]

    def _boot_name(self):
        win = QApplication.activeWindow()
        title = (win.windowTitle() if win else "") or "Visualised app"
        return "".join(c for c in title if c.isalnum() or c in " -_").strip() or "Visualised app"

    def cmd_StartAtBoot(self, on="true"):
        on = str(on).lower() not in ("false", "0", "no", "off", "")
        name, cmd = self._boot_name(), self._launch_command()
        try:
            if sys.platform.startswith("win"):
                import winreg
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE)
                with key:
                    if on:
                        winreg.SetValueEx(key, name, 0, winreg.REG_SZ, subprocess.list2cmdline(cmd))
                    else:
                        try:
                            winreg.DeleteValue(key, name)
                        except FileNotFoundError:
                            pass
            elif sys.platform == "darwin":
                p = Path.home() / "Library" / "LaunchAgents" / f"io.visualised.{name.replace(' ', '-').lower()}.plist"
                if on:
                    p.parent.mkdir(parents=True, exist_ok=True)
                    items = "".join(f"<string>{a}</string>" for a in cmd)
                    p.write_text('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
                                 '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n<plist version="1.0"><dict>'
                                 f"<key>Label</key><string>{p.stem}</string><key>ProgramArguments</key><array>{items}</array>"
                                 "<key>RunAtLoad</key><true/></dict></plist>\n")
                elif p.exists():
                    p.unlink()
            else:
                p = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "autostart" / f"{name.replace(' ', '-').lower()}.desktop"
                if on:
                    p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_text(f"[Desktop Entry]\nType=Application\nName={name}\nExec={' '.join(_sh(a) for a in cmd)}\n"
                                 "X-GNOME-Autostart-enabled=true\nTerminal=false\n")
                elif p.exists():
                    p.unlink()
        except OSError as exc:
            return f"Couldn't change starting with the computer: {exc}"
        return "on" if on else "off"

    def cmd_LaunchedAtBoot(self):
        return "true" if AT_BOOT in sys.argv else "false"


def _sh(a):
    """Quote one argument for a .desktop file's Exec line."""
    return a if a and all(c.isalnum() or c in "/._-=:" for c in a) else '"' + a.replace("\\", "\\\\").replace('"', '\\"') + '"'
