"""
Capture commands for VML — the global-input SENSOR and screen-edge barriers, the mirror of
the inject actuator in headinput. This watches the real keyboard and mouse system-wide and
reports what happens as an event stream; the POLICY that decides what to do with it — which
edges to arm, when to cross to another machine, which keys mean "come home", sending input
over a link — lives in VML, not here. (That policy is Kato.)

    Vml("AllowCapture")                 -- consent gate; required before capture starts
    Vml("CaptureStart", "left,right")   -- start watching; arm a barrier on each named edge
    Vml("CaptureBarriers","left","left,right")  -- change the armed edges now (sides; every)
    Vml("InputEvents")                  -- drain the queue: a JSON list of what happened
    Vml("CaptureRelease", x, y)         -- give the keyboard/mouse back, pointer at x,y (desktop px)
    Vml("CaptureStop")

Each event in the list InputEvents returns is one dict:
    {"t":"ready","zones":[[w,h,x,y],...]}          screens the desktop reports
    {"t":"armed","sides":["left","right"]}         edges now carrying a barrier
    {"t":"edge","side":"right","x":..,"y":..,"zone":[w,h,x,y]}   pointer crossed: input is ours now
    {"t":"move","dx":..,"dy":..}                   relative pointer motion while captured
    {"t":"button","name":"left","down":true}
    {"t":"scroll","dx":0,"dy":-1}
    {"t":"key","char":"a","down":true}   or   {"t":"key","name":"enter","down":true}
    {"t":"deactivated"} {"t":"disabled"} {"t":"error","msg":".."}

Keys are resolved to finished characters by the OS's own keyboard STATE (libxkbcommon on
Linux), so caps lock, num lock, shift and altgr are tracked by the one thing that is also
being told about the keys — they can't drift out of step (the old caps-lock-reverses bug).
Down and up of the same physical key carry the same char/name, so a policy can forward and
release cleanly. Linux/Wayland only for now (via the desktop's InputCapture portal, run in a
small helper); Windows and macOS to follow.
"""
import collections
import ctypes
import ctypes.util
import glob
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

# kernel keycode -> wire name, for keys that travel by name (the names the machines share)
NAMES = {42: "shift", 54: "shift_r", 29: "ctrl", 97: "ctrl_r", 56: "alt", 100: "alt_gr",
         125: "cmd", 126: "cmd_r", 28: "enter", 96: "enter", 1: "esc", 15: "tab", 57: "space",
         14: "backspace", 111: "delete", 110: "insert", 102: "home", 107: "end",
         104: "page_up", 109: "page_down", 103: "up", 108: "down", 105: "left", 106: "right",
         58: "caps_lock", 87: "f11", 88: "f12", 99: "print_screen", 70: "scroll_lock",
         119: "pause", 69: "num_lock", 127: "menu", 164: "media_play_pause",
         113: "media_volume_mute", 114: "media_volume_down", 115: "media_volume_up",
         165: "media_previous", 163: "media_next",
         **{58 + n: "f%d" % n for n in range(1, 11)}, **{170 + n: "f%d" % n for n in range(13, 21)}}
# the number pad travels as the characters it types
KEYPAD = {82: "0", 79: "1", 80: "2", 81: "3", 75: "4", 76: "5", 77: "6", 71: "7", 72: "8",
          73: "9", 83: ".", 78: "+", 74: "-", 55: "*", 98: "/"}
BUTTONS = {0x110: "left", 0x111: "right", 0x112: "middle"}
SIDE = {"left": "left", "right": "right", "top": "up", "bottom": "down"}

HELPER_PYTHON = os.environ.get("KATO_CAPTURE_PYTHON") or "/usr/bin/python3"
XKB_KEY_UP, XKB_KEY_DOWN = 0, 1
EVDEV_OFFSET = 8                      # an xkb keycode is the kernel keycode + 8


class _Xkb:
    """Resolve a kernel keycode to the character it types, using libxkbcommon's own keyboard
    STATE. Because the same state object is fed every key, the locks (caps, num) and modifiers
    (shift, altgr) it tracks are always in step with the keys we're resolving — which is the
    whole point: a separate caps flag counted by hand is what used to drift and reverse letters."""

    def __init__(self, layout, variant):
        from .uinput_inject import _RuleNames          # lazy: only needed where capture runs
        path = ctypes.util.find_library("xkbcommon")
        if not path:
            raise RuntimeError("libxkbcommon is not installed")
        x = ctypes.CDLL(path)
        x.xkb_context_new.restype = ctypes.c_void_p
        x.xkb_keymap_new_from_names.restype = ctypes.c_void_p
        x.xkb_keymap_new_from_names.argtypes = [ctypes.c_void_p, ctypes.POINTER(_RuleNames), ctypes.c_int]
        x.xkb_state_new.restype = ctypes.c_void_p
        x.xkb_state_new.argtypes = [ctypes.c_void_p]
        x.xkb_state_unref.argtypes = [ctypes.c_void_p]
        x.xkb_keymap_unref.argtypes = [ctypes.c_void_p]
        x.xkb_context_unref.argtypes = [ctypes.c_void_p]
        x.xkb_state_update_key.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int]
        x.xkb_state_update_key.restype = ctypes.c_uint32
        x.xkb_state_key_get_utf8.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_char_p, ctypes.c_size_t]
        x.xkb_state_key_get_utf8.restype = ctypes.c_int
        x.xkb_keymap_mod_get_index.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        x.xkb_keymap_mod_get_index.restype = ctypes.c_uint32
        x.xkb_state_update_mask.argtypes = [ctypes.c_void_p] + [ctypes.c_uint32] * 6
        x.xkb_state_update_mask.restype = ctypes.c_uint32
        x.xkb_state_mod_name_is_active.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
        x.xkb_state_mod_name_is_active.restype = ctypes.c_int
        self._x = x
        ctx = x.xkb_context_new(0)
        if not ctx:
            raise RuntimeError("xkbcommon: no context")
        names = _RuleNames(None, None, (layout or "us").encode(), (variant or "").encode(), None)
        keymap = x.xkb_keymap_new_from_names(ctx, ctypes.byref(names), 0)
        if not keymap:
            x.xkb_context_unref(ctx)
            raise RuntimeError("xkbcommon doesn't know the layout '%s'" % layout)
        self._ctx, self._keymap = ctx, keymap
        self._state = x.xkb_state_new(keymap)
        # the real xkb modifier names: caps is "Lock", num lock is "Mod2"
        INVALID = 0xFFFFFFFF
        self._caps_idx = x.xkb_keymap_mod_get_index(keymap, b"Lock")
        self._num_idx = x.xkb_keymap_mod_get_index(keymap, b"Mod2")
        if self._caps_idx == INVALID:
            self._caps_idx = None
        if self._num_idx == INVALID:
            self._num_idx = None

    def feed(self, code, down):
        """Tell the state about a key; on press, return the character it now types, or None."""
        self._x.xkb_state_update_key(self._state, code + EVDEV_OFFSET, XKB_KEY_DOWN if down else XKB_KEY_UP)
        if not down:
            return None
        buf = ctypes.create_string_buffer(8)
        n = self._x.xkb_state_key_get_utf8(self._state, code + EVDEV_OFFSET, buf, 8)
        if n <= 0:
            return None
        try:
            ch = buf.value.decode("utf-8")
        except Exception:
            return None
        return ch if ch and ch.isprintable() else None

    def set_locks(self, caps, num):
        """Seed the locked modifiers to match the real keyboard. The helper forwards raw keycodes
        and never the lock state, so at the moment of a grab we read the actual Caps/Num Lock from
        the system and tell the state here - otherwise the first letters come out inverted."""
        mask = 0
        if caps and self._caps_idx is not None:
            mask |= 1 << self._caps_idx
        if num and self._num_idx is not None:
            mask |= 1 << self._num_idx
        self._x.xkb_state_update_mask(self._state, 0, 0, mask, 0, 0, 0)

    def caps_active(self):
        """True if the state currently has Caps Lock on (for diagnostics)."""
        XKB_STATE_MODS_LOCKED = 1 << 2
        return bool(self._x.xkb_state_mod_name_is_active(self._state, b"Lock", XKB_STATE_MODS_LOCKED))

    def reset(self):
        """Forget every held key and modifier — used when the pointer comes home, so a key still
        down at hand-off can't leave a stuck modifier behind."""
        try:
            self._x.xkb_state_unref(self._state)
            self._state = self._x.xkb_state_new(self._keymap)
        except Exception:
            pass


class _Capture:
    """Owns the Wayland helper subprocess and turns its raw report into the engine's event queue."""

    def __init__(self, log=None):
        self.log = log or (lambda *a: None)
        self.proc = None
        self.q = collections.deque(maxlen=4000)
        self.lock = threading.Lock()
        self.running = False
        self.error = ""
        self.every = []
        self._down = {}                  # physical code -> the wire we emitted on its press
        self.xkb = None
        try:
            from .uinput_inject import detect_layout
            lay = detect_layout()
            self.layout = (lay[0], lay[1] if len(lay) > 1 else "")
            self.xkb = _Xkb(self.layout[0], self.layout[1])
        except Exception as exc:
            self.log("capture: key resolution unavailable (%s); character keys travel raw" % exc)
            self.layout = ("us", "")

    # ---- lifecycle ----
    def start(self, every):
        if self.running:
            self.barriers(every, every)
            return True
        helper = os.environ.get("KATO_CAPTURE_HELPER") or str(Path(__file__).with_name("capture_helper.py"))
        if not os.path.exists(helper):
            self.error = "the Wayland capture helper is missing from this installation"
            return False
        if not os.path.exists(HELPER_PYTHON):
            self.error = "the system Python (%s) was not found" % HELPER_PYTHON
            return False
        env = {k: v for k, v in os.environ.items()
               if k not in ("LD_LIBRARY_PATH", "PYTHONPATH", "PYTHONHOME", "QT_PLUGIN_PATH")}
        try:
            # a session of its own: Ctrl+C in a terminal would otherwise stop the helper and leave
            # the app holding nothing.
            self.proc = subprocess.Popen([HELPER_PYTHON, "-I", helper], stdin=subprocess.PIPE,
                                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                         bufsize=1, env=env, start_new_session=True)
        except Exception as exc:
            self.error = "couldn't start the Wayland capture helper: %s" % exc
            return False
        self.running = True
        self.error = ""
        threading.Thread(target=self._read, daemon=True).start()
        threading.Thread(target=self._read_err, daemon=True).start()
        threading.Thread(target=self._keepalive, daemon=True).start()
        self.barriers(every, every)
        return True

    def _say(self, **cmd):
        try:
            with self.lock:
                if self.proc and self.proc.poll() is None:
                    self.proc.stdin.write(json.dumps(cmd) + "\n")
                    self.proc.stdin.flush()
        except Exception:
            pass

    def barriers(self, sides, every):
        self.every = list(every)
        self._say(c="barriers", sides=list(sides), every=list(every))

    def release(self, x, y):
        self._down.clear()
        if self.xkb:
            self.xkb.reset()
        self._say(c="release", x=float(x), y=float(y))

    @staticmethod
    def _read_locks():
        """The real Caps/Num Lock state from the keyboard LEDs. Any keyboard reporting a lock on
        counts it on. Returns (caps_on, num_on); (False, False) if nothing can be read."""
        def any_on(pattern):
            for p in glob.glob(pattern):
                try:
                    if int(open(p).read().strip() or "0") > 0:
                        return True
                except Exception:
                    pass
            return False
        try:
            caps = any_on("/sys/class/leds/*capslock*/brightness")
            num = any_on("/sys/class/leds/*numlock*/brightness")
            return caps, num
        except Exception:
            return False, False

    def _keepalive(self):
        # the helper hands the keyboard/mouse back if it doesn't hear this every few seconds
        while self.running:
            self._say(c="alive")
            time.sleep(1.0)

    def _read_err(self):
        try:
            for line in self.proc.stderr:
                line = line.strip()
                if line:
                    self.error = line[:300]
        except Exception:
            pass

    def _read(self):
        try:
            for line in self.proc.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except Exception:
                    continue
                self._translate(ev)
        except Exception as exc:
            self.error = str(exc)
        self.running = False
        self.q.append({"t": "disabled"})

    def _translate(self, ev):
        e = ev.get("e")
        if e == "ready":
            self.q.append({"t": "ready", "zones": ev.get("zones", [])})
        elif e == "armed":
            self.q.append({"t": "armed", "sides": [SIDE.get(s, s) for s in ev.get("sides", [])]})
        elif e == "activated":
            self._down.clear()
            caps, num = self._read_locks()
            if self.xkb:
                self.xkb.reset()
                self.xkb.set_locks(caps, num)        # match the real keyboard before any key resolves
            self.q.append({"t": "edge", "side": SIDE.get(ev.get("side"), ev.get("side")),
                           "x": ev.get("x"), "y": ev.get("y"), "zone": ev.get("zone"),
                           "caps": caps, "num": num})
        elif e == "m":
            self.q.append({"t": "move", "dx": ev.get("dx", 0), "dy": ev.get("dy", 0)})
        elif e == "b":
            self.q.append({"t": "button", "name": BUTTONS.get(ev.get("code"), ev.get("code")),
                           "down": bool(ev.get("down"))})
        elif e == "s":
            self.q.append({"t": "scroll", "dx": ev.get("dx", 0), "dy": ev.get("dy", 0)})
        elif e == "k":
            self.q.append(self._key(ev.get("code"), bool(ev.get("down"))))
        elif e == "deactivated":
            self._down.clear()
            if self.xkb:
                self.xkb.reset()
            self.q.append({"t": "deactivated"})
        elif e == "disabled":
            self.q.append({"t": "disabled"})
        elif e == "error":
            self.q.append({"t": "error", "msg": ev.get("msg", "")})

    def _key(self, code, down):
        out = {"t": "key", "down": down}
        if code in NAMES:                                # named keys: travel by name, keep the state in step
            out["name"] = NAMES[code]
            if self.xkb:
                self.xkb.feed(code, down)
            (self._down.__setitem__(code, {"name": NAMES[code]}) if down else self._down.pop(code, None))
        elif code in KEYPAD:
            out["char"] = KEYPAD[code]
            (self._down.__setitem__(code, {"char": KEYPAD[code]}) if down else self._down.pop(code, None))
        elif down:
            ch = self.xkb.feed(code, down) if self.xkb else None
            if ch:
                out["char"] = ch
                self._down[code] = {"char": ch}
            else:
                out["code"] = code
        else:                                            # up of a character key: same wire we sent on down
            if self.xkb:
                self.xkb.feed(code, down)
            was = self._down.pop(code, None)
            if was and "char" in was:
                out["char"] = was["char"]
            else:
                out["code"] = code
        return out

    def drain(self):
        out = []
        while self.q:
            out.append(self.q.popleft())
        return out

    def stop(self):
        self.running = False
        self._say(c="quit")
        try:
            if self.proc:
                self.proc.stdin.close()
                self.proc.wait(timeout=2)
        except Exception:
            try:
                self.proc.kill()
            except Exception:
                pass
        self.proc = None


class _PynputCapture:
    """Capture backend for Windows, macOS and X11 - pynput suppressing listeners, the same way the current
    Kato takes the keyboard and mouse. (Wayland can't be grabbed like this and uses the portal helper above.)
    It emits exactly the same event stream as the Wayland backend, so the VML policy on top is identical.
    pynput resolves each key to its character through the OS, with caps/num lock already applied, so there is
    no lock state to seed here."""

    def __init__(self, log=None):
        self.log = log or (lambda *a: None)
        self.q = collections.deque(maxlen=4000)
        self.running = False
        self.error = ""
        self.armed = []
        self.bounds = (0, 0, 1, 1)
        self.zones = []
        self.grabbed = False
        self._centre = (0, 0)
        self._watch = None                 # non-suppressing mouse listener: edge detection
        self._grabs = []                   # suppressing listeners while driving
        self._is_windows = sys.platform.startswith("win")
        try:
            from pynput import keyboard, mouse
            self._kb, self._ms = keyboard, mouse
            self._mctl = mouse.Controller()
        except Exception as exc:
            self._kb = self._ms = self._mctl = None
            self.error = "pynput is not installed (needed to capture on Windows/macOS/X11): %s" % exc

    def _screens(self):
        """Virtual-desktop bounds and per-monitor zones [w,h,x,y], from Qt if the app is up, else one screen."""
        try:
            from PySide6.QtGui import QGuiApplication
            if QGuiApplication.instance():
                zones, vx0, vy0, vx1, vy1 = [], 10 ** 9, 10 ** 9, -10 ** 9, -10 ** 9
                for s in QGuiApplication.screens():
                    g = s.geometry()
                    zones.append([g.width(), g.height(), g.x(), g.y()])
                    vx0, vy0 = min(vx0, g.x()), min(vy0, g.y())
                    vx1, vy1 = max(vx1, g.x() + g.width()), max(vy1, g.y() + g.height())
                if zones:
                    return (vx0, vy0, vx1 - vx0, vy1 - vy0), zones
        except Exception:
            pass
        try:
            u = ctypes.windll.user32            # Windows virtual-screen metrics
            SM = (76, 77, 78, 79)
            x, y, w, h = (u.GetSystemMetrics(m) for m in SM)
            return (x, y, w, h), [[w, h, x, y]]
        except Exception:
            return (0, 0, 1920, 1080), [[1920, 1080, 0, 0]]

    def start(self, every):
        if self._kb is None:
            return False
        if self.running:
            self.barriers(every, every)
            return True
        self.bounds, self.zones = self._screens()
        self.armed = list(every)
        self.running = True
        self.error = ""
        self.q.append({"t": "ready", "zones": self.zones})
        self.q.append({"t": "armed", "sides": list(self.armed)})
        self._watch = self._ms.Listener(on_move=self._on_watch_move)
        self._watch.start()
        return True

    def barriers(self, sides, every):
        if set(sides) != set(self.armed):
            self.armed = list(sides)
            self.q.append({"t": "armed", "sides": list(self.armed)})
        else:
            self.armed = list(sides)

    def _on_watch_move(self, x, y):
        if self.grabbed or not self.running:
            return
        bx, by, bw, bh = self.bounds
        side = ratio = None
        if "right" in self.armed and x >= bx + bw - 1:
            side, ratio = "right", (y - by) / max(bh, 1)
        elif "left" in self.armed and x <= bx:
            side, ratio = "left", (y - by) / max(bh, 1)
        elif "up" in self.armed and y <= by:
            side, ratio = "up", (x - bx) / max(bw, 1)
        elif "down" in self.armed and y >= by + bh - 1:
            side, ratio = "down", (x - bx) / max(bw, 1)
        if side:
            self._grab(side, max(0.0, min(1.0, ratio)))

    def _grab(self, side, ratio):
        if self.grabbed:
            return
        bx, by, bw, bh = self.bounds
        self._centre = (bx + bw // 2, by + bh // 2)
        try:
            self._mctl.position = self._centre
        except Exception:
            pass
        self.grabbed = True
        self.q.append({"t": "edge", "side": side, "ratio": ratio,
                       "x": self._centre[0], "y": self._centre[1], "zone": None})
        self._grabs = [
            self._ms.Listener(on_move=self._g_move, on_click=self._g_click, on_scroll=self._g_scroll, suppress=True),
            self._kb.Listener(on_press=lambda k: self._g_key(k, True),
                              on_release=lambda k: self._g_key(k, False), suppress=True),
        ]
        for g in self._grabs:
            g.start()
        threading.Thread(target=self._watchdog, daemon=True).start()

    def _g_move(self, x, y):
        if not self.grabbed:
            return True
        cx, cy = self._centre
        dx, dy = x - cx, y - cy
        if dx or dy:
            self.q.append({"t": "move", "dx": dx, "dy": dy})
            if not self._is_windows:                    # X11/mac: re-park the real pointer (Windows pins it for us)
                try:
                    self._mctl.position = self._centre
                except Exception:
                    pass
        return True

    def _g_click(self, x, y, button, pressed):
        self.q.append({"t": "button", "name": getattr(button, "name", str(button)), "down": bool(pressed)})
        return True

    def _g_scroll(self, x, y, dx, dy):
        self.q.append({"t": "scroll", "dx": dx, "dy": dy})
        return True

    def _g_key(self, key, down):
        wire = self._key_to_wire(key)
        if wire is None:
            return True
        ev = {"t": "key", "down": down}
        ev.update(wire)
        self.q.append(ev)
        return True

    def _key_to_wire(self, key):
        """Mirror of Kato's key_to_wire: a named key travels by name, otherwise the character it typed
        (with Windows' Ctrl+letter control codes turned back into the letter), otherwise the raw vk."""
        if isinstance(key, self._kb.Key):
            return {"name": key.name}
        char = getattr(key, "char", None)
        vk = getattr(key, "vk", None)
        if char and ord(char[0]) < 32 and vk is not None and (48 <= vk <= 57 or 65 <= vk <= 90):
            char = chr(vk).lower()
        if char:
            return {"char": char}
        if vk is not None:
            return {"vk": vk}
        return None

    def _watchdog(self):
        """Windows can silently drop a slow input hook while pynput still says the listener runs, freezing the
        pointer mid-drive. The real pointer is suppressed and pinned at centre, so if it escapes, capture is
        gone: release and tell the policy to come home. (Lifted from Kato's _suppress_watchdog.)"""
        strikes = 0
        while self.grabbed and self.running:
            try:
                px, py = self._mctl.position
                cx, cy = self._centre
                if abs(px - cx) > 12 or abs(py - cy) > 12:
                    strikes += 1
                    if strikes >= 3:
                        self.log("capture: pointer escaped its park - input lost, releasing")
                        self.release(cx, cy)
                        self.q.append({"t": "disabled"})
                        return
                else:
                    strikes = 0
            except Exception:
                pass
            time.sleep(0.15)

    def release(self, x, y):
        self.grabbed = False
        for g in self._grabs:
            try:
                g.stop()
            except Exception:
                pass
        self._grabs = []
        try:
            self._mctl.position = (int(float(x)), int(float(y)))
        except Exception:
            pass
        self.q.append({"t": "deactivated"})

    def drain(self):
        out = []
        while self.q:
            out.append(self.q.popleft())
        return out

    def stop(self):
        self.running = False
        if self.grabbed:
            self.release(*self._centre)
        try:
            if self._watch:
                self._watch.stop()
        except Exception:
            pass
        self._watch = None


def _is_wayland():
    return bool(os.environ.get("WAYLAND_DISPLAY")) or os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"


_CAP = None
_CAPTURE_OK = False                       # flipped by Vml("AllowCapture") — the consent gate


def _cap():
    """The capture backend for this machine: the portal helper on Wayland, pynput everywhere else."""
    global _CAP
    if _CAP is None:
        _CAP = _Capture() if _is_wayland() else _PynputCapture()
    return _CAP


class CaptureCommands:
    """Mixed into Engine. The global-input sensor + screen-edge barriers: the mirror of the inject
    actuator. Gated by AllowCapture (separate from AllowInput — watching everything typed is graver
    than injecting). The helper keeps its own dead-man safety whatever a script does."""

    def cmd_AllowCapture(self, on="1"):
        """Let this app watch the real keyboard and mouse system-wide (CaptureStart and the rest).
        Watching everything someone types is serious, so capture does nothing until you call this,
        once the user has agreed. AllowCapture \"0\" turns it off again."""
        global _CAPTURE_OK
        _CAPTURE_OK = str(on) != "0"
        return "1" if _CAPTURE_OK else "0"

    def cmd_CaptureStart(self, edges=""):
        """Start watching the keyboard and mouse, arming a barrier on each named screen edge
        (comma-separated, from left, right, up, down). When the pointer is pushed against an armed
        edge the desktop hands this program the keyboard and mouse and an \"edge\" event appears in
        InputEvents. Needs AllowCapture first. Linux/Wayland for now."""
        if not _CAPTURE_OK:
            raise RuntimeError("capture not permitted: call Vml(\"AllowCapture\") first")
        sides = [s.strip() for s in str(edges).replace(";", ",").split(",") if s.strip()]
        if not _cap().start(sides):
            raise RuntimeError(_cap().error or "capture could not start")
        return ""

    def cmd_CaptureBarriers(self, sides="", every=""):
        """Change which screen edges carry a barrier right now (sides), out of the ones the desktop
        was first told about (every). Policy uses this to stop watching an edge while the pointer is
        away on another machine, then arm it again on the way back. Both are comma-separated."""
        s = [x.strip() for x in str(sides).replace(";", ",").split(",") if x.strip()]
        ev = [x.strip() for x in str(every).replace(";", ",").split(",") if x.strip()] or s
        _cap().barriers(s, ev)
        return ""

    def cmd_CaptureRelease(self, x="0", y="0"):
        """Give the keyboard and mouse back to this machine, putting the pointer at x,y (desktop
        pixels). Call it when policy decides the crossing is over - coming home, or undoing a
        crossing that shouldn't have happened."""
        _cap().release(x, y)
        return ""

    def cmd_InputEvents(self):
        """Drain and return everything captured since the last call, as a JSON list: key, move,
        button, scroll, edge and status events (see the module header). Call it on a timer; it
        never blocks and returns [] when nothing happened. What to do with it - crossing,
        home-keys, sending over a link - is policy, and it's yours to write."""
        return json.dumps(_cap().drain())

    def cmd_CaptureStop(self):
        """Stop watching; the keyboard and mouse go back to this machine as normal."""
        _cap().stop()
        return ""

    def cmd_CaptureError(self):
        """The last trouble capture hit (\"\" if none)."""
        return _cap().error if _CAP else ""
