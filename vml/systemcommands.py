"""
Commands for apps that live beside the user's other programs: SSH drives, a tray icon, starting with the computer.

    SshMount(drive, handler)    a folder on an SSH server as a drive (see vml/sshdrive.py for what `drive` holds, as
                                JSON). handler gets (name, state, detail) each time it changes: connecting, mounted
                                (detail: where, and how), offline (it keeps trying), error (it waits for the user),
                                off; and once (name, "hostkey", fingerprint) the first time a server is met, for the
                                app to keep in the drive's "hostkey".
    SshUnmount(name)            ("" for all of them)
    SshAllowSudo(drive, password, handler) let the drive act as its "actas" user (root, www-data...) without a
                                password: a sudoers rule of its own for sftp-server only; handler gets (name, ok/error, detail)
    SshStatus(name)             JSON {state, detail}, or of all of them by name
    SshTest(drive, handler)     try a drive without mounting it: handler gets (name, "ok", what it reached, the server's
                                key) or (name, "error", what went wrong, "")
    DiskList()                  the computer's partitions, as JSON
    DiskMount(item, handler)    mount a disk image (ISO, IMG, VHD, VHDX...) or a partition: item {name, path, kind, readonly}
    DiskUnmount(item, handler)  unmount it (a partition mounted elsewhere too)
                                (kind "folder": {path, hide, showonly, readonly}; kind "ram": {size MB, keep zip})
    OpenTerminal(folder, drive) a terminal in a folder, or (drive JSON) an ssh session in that drive's folder
    FolderPreview(path, hide, showonly)   what a folder drive would show, as JSON
    IgnoreUsual()               the ready-made ignore lists, as JSON
    SshMethods()                JSON: what this computer can use (winfsp, webdav, sshfs), free drive letters, the user's
                                likely key files (keys, likeliest first) and whether an SSH agent has keys (agent)
    OpenFolder(path)            show a folder (or a drive letter) in the file manager; answers "" or why not
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

    def cmd_SshAllowSudo(self, drive="{}", password="", handler=""):
        """Let the drive's user act as its "actas" user without a password, for SSH Drive's file access only (a
        sudoers rule of its own on the server, checked with visudo). The sudo password is used once and not kept.
        handler gets (name, "ok" or "error", what happened)."""
        import threading
        try:
            d = json.loads(drive) if isinstance(drive, str) else dict(drive)
        except ValueError:
            return "That drive isn't JSON."
        name = d.get("name") or d.get("host") or ""
        q = self._sys_queue()
        origin = self._script_stack[-1] if self._script_stack else None

        def run():
            try:
                from .sshdrive import allow_sudo
                ok, detail = allow_sudo(d, str(password or ""))
            except Exception as exc:
                ok, detail = False, str(exc)
            q.put((str(handler or ""), (name, "ok" if ok else "error", detail), origin))
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

    def cmd_OpenFolder(self, path=""):
        """Show a folder (or a drive, "S:") in the computer's own file manager. Answers "" or why not."""
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        p = os.path.expanduser(str(path or ""))
        if len(p) == 2 and p[1] == ":":
            p += "\\"
        if not os.path.isdir(p):
            return f"There's no folder at {p}."
        return "" if QDesktopServices.openUrl(QUrl.fromLocalFile(p)) else f"Couldn't open {p}."

    # ── disk images and partitions (vml/diskmount.py) ──
    def _disks(self):
        if getattr(self, "_disk_mgr", None) is None:
            from .diskmount import Disks
            q = self._sys_queue()
            self._disk_handlers = {}

            def changed(name, state, detail):
                h, origin = self._disk_handlers.get(name, ("", None))
                q.put((h, (name, state, detail), origin))
            self._disk_mgr = Disks(on_change=changed)
            QApplication.instance().aboutToQuit.connect(self._disk_mgr.down_all)
        return self._disk_mgr

    def cmd_DiskList(self):
        """The computer's partitions as JSON: [{path, name, label, fstype, size, mounted, removable, system}]."""
        try:
            from .diskmount import partitions
            return json.dumps(partitions())
        except Exception as exc:
            return json.dumps({"error": str(exc)})

    def cmd_DiskInfo(self, path=""):
        """What a disk image is, as JSON: {size, size_text, format, label, partitions, folder} (read from the file)."""
        from .diskmount import info
        return json.dumps(info(os.path.expanduser(str(path))))

    def cmd_OpenTerminal(self, folder="", drive=""):
        """A terminal in a folder; or, given an SSH drive (JSON), an ssh session to it, in its folder. "" or why not."""
        from . import terminal
        if str(drive or "").strip().startswith("{"):
            try:
                d = json.loads(drive)
            except ValueError:
                return "That isn't JSON."
            return terminal.open_terminal("", terminal.ssh_argv(d))
        return terminal.open_terminal(str(folder or ""))

    def cmd_FolderPreview(self, path="", hide="", showonly="0"):
        """What a folder drive would show, as JSON {shown, hidden, names (the first shown)}: for the ignore box."""
        from . import ignore
        p = os.path.expanduser(str(path))
        pats = ignore.patterns(hide)
        try:
            names = sorted(os.listdir(p), key=str.lower)
        except OSError as e:
            return json.dumps({"error": e.strerror or str(e)})
        only = str(showonly).lower() in ("1", "true", "yes")
        dirs = {n for n in names if os.path.isdir(os.path.join(p, n))}
        shown = [n for n in names if (ignore.hidden(pats, n, n in dirs) == only) or not pats]
        return json.dumps({"shown": len(shown), "hidden": len(names) - len(shown), "names": shown[:12],
                           "folders_out": len(dirs - set(shown))})       # (so the box can say when it's folders going)

    def cmd_IgnoreUsual(self):
        """The ready-made ignore lists, as JSON [{key, label, patterns}]."""
        from . import ignore
        return json.dumps([{"key": k, "label": l, "patterns": p} for k, l, p in ignore.USUAL])

    def cmd_DiskMount(self, item="{}", handler=""):
        """Mount a disk image (ISO, IMG, VHD, VHDX...) or a partition: item is JSON {name, path, kind, readonly}.
        handler gets (name, state, detail): mounting, mounted (detail: where, comma-separated, and how), error, off."""
        try:
            d = json.loads(item) if isinstance(item, str) else dict(item)
        except ValueError:
            return "That isn't JSON."
        name = d.get("name") or os.path.basename(str(d.get("path", "")))
        d["name"] = name
        mgr = self._disks()
        self._disk_handlers[name] = (str(handler or ""), self._script_stack[-1] if self._script_stack else None)
        mgr.up(d)
        return ""

    def cmd_DiskUnmount(self, item="{}", handler=""):
        """Unmount one (item JSON, or just its name); a partition mounted elsewhere is unmounted all the same."""
        import threading
        try:
            d = json.loads(item) if str(item).strip().startswith("{") else {"name": str(item)}
        except ValueError:
            d = {"name": str(item)}
        name = d.get("name") or os.path.basename(str(d.get("path", "")))
        mgr = self._disks()
        if handler:
            self._disk_handlers[name] = (str(handler), self._script_stack[-1] if self._script_stack else None)
        threading.Thread(target=mgr.down, args=(name, d), daemon=True).start()
        return ""

    # ── the tray ──
    def cmd_Tray(self, tooltip="", menu="", handler=""):
        """An icon in the tray. menu: items with | between ("-" a line; "Title>one;two" a submenu, whose items come
        to the handler as "Title>one"); handler gets the item picked, or "open" when the icon itself is clicked."""
        app = QApplication.instance()
        old = getattr(self, "_tray", None)
        if not tooltip:
            if old:
                old.hide()
                self._tray = None
                self._tray_menu = None
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
        m = getattr(self, "_tray_menu", None)
        fresh = m is None
        if fresh:
            try:
                from . import startupnote
                startupnote.notes()           # (listening from now on, for GNOME's tray-click spinner)
            except Exception:
                pass
        if fresh:                             # one menu for good, refilled: a desktop panel shows the tray's menu
            m = QMenu()                       # over D-Bus, and some never notice a new one swapped in
            self._tray_menu = m               # (Qt doesn't keep the menu alive for us)
        m.clear()
        for item in [x.strip() for x in str(menu or "").split("|") if x.strip()]:
            if item == "-":
                m.addSeparator()
                continue
            if ">" in item:                    # "Title>one;two": a submenu; picking one hands the handler "Title>one"
                title, kids = item.split(">", 1)
                sub = m.addMenu(title.replace("&", "&&"))
                for kid in [k.strip() for k in kids.split(";") if k.strip()]:
                    act = QAction(kid.replace("&", "&&"), sub)
                    act.triggered.connect(lambda _=False, t=f"{title}>{kid}": (_picked(), q.put((handler, (t,), origin))))
                    sub.addAction(act)
                continue
            act = QAction(item.replace("&", "&&"), m)            # (& would underline the next letter)
            act.triggered.connect(lambda _=False, t=item: (_picked(), q.put((handler, (t,), origin))))
            m.addAction(act)
        if fresh or tray.contextMenu() is not m:
            tray.setContextMenu(m)
        if getattr(self, "_tray_hooked", None) is tray:          # (once: disconnecting nothing makes PySide warn)
            try:
                tray.activated.disconnect()
            except (TypeError, RuntimeError):
                pass
        self._tray_hooked = tray
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
        """Quit (the app's own Exit). The tray icon goes first, and the quitting a moment later: a desktop panel
        that sent "this menu item was picked" waits for the answer, and spins until it gives up if the app has
        already gone."""
        tray = getattr(self, "_tray", None)
        if tray:
            tray.hide()
        QTimer.singleShot(500, QApplication.instance().quit)
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
        if _store_app():                      # a Store app: Windows' own startup switch (see its AppxManifest.xml)
            from PySide6.QtCore import QUrl
            from PySide6.QtGui import QDesktopServices
            QDesktopServices.openUrl(QUrl("ms-settings:startupapps"))
            return (f"In the Settings that just opened, switch {name} on (or off) under Startup apps: "
                    "a Store app starts with Windows only from there.")
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
        at_boot = AT_BOOT in sys.argv or Path(sys.executable).stem.lower().endswith("atboot")   # (a Store app's
        return "true" if at_boot else "false"                                                 # startup copy)


def _picked():
    """A tray menu item was picked: finish the "launching" spinner GNOME starts for it (vml/startupnote.py)."""
    try:
        from . import startupnote
        startupnote.picked()
    except Exception:
        pass


def _store_app():
    """Installed from the Microsoft Store (an MSIX package: it runs from WindowsApps)?"""
    return sys.platform.startswith("win") and "\\windowsapps\\" in sys.executable.lower()


def _sh(a):
    """Quote one argument for a .desktop file's Exec line."""
    return a if a and all(c.isalnum() or c in "/._-=:" for c in a) else '"' + a.replace("\\", "\\\\").replace('"', '\\"') + '"'
