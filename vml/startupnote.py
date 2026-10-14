"""
GNOME on Xorg: picking an item on an app's tray menu starts a "launching" spinner that waits to hear a window
has arrived. Most tray items open no window (mount, unmount, Exit), so the spinner lingers until GNOME gives up.
This watches for those announcements and finishes the ones that began just after a pick on our own menu.
(After Juska's StartupSequences. Needs python-xlib; without it, or on Wayland, Windows and macOS, it does nothing.)
"""
import os
import re
import sys
import threading
import time

_one = None


class StartupNotes:
    def __init__(self):
        self.d = None
        self.seen = []                     # (when, id) of launches announced lately
        self.lock = threading.Lock()
        if not sys.platform.startswith("linux") or not os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
            return
        try:
            from Xlib import X, display
            self.X = X
            self.d = display.Display()
            self.root = self.d.screen().root
            self.a_begin = self.d.intern_atom("_NET_STARTUP_INFO_BEGIN")
            self.a_more = self.d.intern_atom("_NET_STARTUP_INFO")
            self.sender = self.root.create_window(-10, -10, 1, 1, 0, X.CopyFromParent, override_redirect=True)
            listen = display.Display()
            listen.screen().root.change_attributes(event_mask=X.PropertyChangeMask)
            threading.Thread(target=self._listen, args=(listen,), daemon=True).start()
        except Exception:
            self.d = None

    def _listen(self, listen):
        parts = {}
        while True:
            try:
                ev = listen.next_event()
            except Exception:
                return
            if ev.type != self.X.ClientMessage or ev.client_type not in (self.a_begin, self.a_more):
                continue
            key = ev.window.id
            buf = (b"" if ev.client_type == self.a_begin else parts.get(key, b"")) + bytes(ev.data[1])
            if b"\0" not in buf:
                parts[key] = buf
                continue
            parts.pop(key, None)
            msg = buf.split(b"\0", 1)[0].decode(errors="ignore")
            m = re.search(r'ID=("(?:[^"\\]|\\.)*"|\S+)', msg) if msg.startswith("new:") else None
            if m:
                with self.lock:
                    now = time.monotonic()
                    self.seen = [(t, i) for t, i in self.seen if now - t < 10] + [(now, m.group(1).strip('"'))]

    def finish(self, since):
        """Finish the launches announced since `since` (a monotonic time, a moment before our menu pick)."""
        if not self.d:
            return
        with self.lock:
            ids = [i for t, i in self.seen if t >= since]
            self.seen = [(t, i) for t, i in self.seen if t < since]
        for sid in ids:
            try:
                from Xlib.protocol import event
                data = ('remove: ID="' + sid.replace("\\", "\\\\").replace('"', '\\"') + '"').encode() + b"\0"
                for i in range(0, len(data), 20):
                    ev = event.ClientMessage(window=self.sender, client_type=self.a_begin if i == 0 else self.a_more,
                                             data=(8, data[i:i + 20].ljust(20, b"\0")))
                    self.root.send_event(ev, event_mask=self.X.PropertyChangeMask)
                self.d.flush()
            except Exception:
                pass


def notes():
    global _one
    if _one is None:
        _one = StartupNotes()
    return _one


def picked():
    """Our tray menu was just used: finish the spinner it set off, now and as late announcements arrive."""
    from PySide6.QtCore import QTimer
    n = notes()
    if not n.d:
        return
    since = time.monotonic() - 2.0
    for ms in (0, 400, 1500):
        QTimer.singleShot(ms, lambda: n.finish(since))
