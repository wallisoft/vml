"""
KVM inject for VML — the full-vocabulary input ACTUATOR, the mirror of the capture sensor. A VML KVM
policy (Kato) drains InputEvents on the controller, sends them to the driven machine, and there replays
each one with Vml("Inject", event). This module performs one event on this machine, the right way for the
OS, and on Windows hops onto the secure desktop (UAC, the lock/login screen) or an administrator's window
through the Kato input service when one is needed.

    Vml("Inject", event_json)     -- perform one event (same shape as an InputEvents item)
    Vml("InjectRelease")          -- let go of everything currently held (coming home, or on exit)
    Vml("InjectServiceReady")     -- "1" if the Windows secure-desktop service is reachable here

Events (JSON), the same vocabulary InputEvents reports:
    {"t":"move","x":0.5,"y":0.5}             absolute, 0..1 of the virtual desktop
    {"t":"button","name":"left","down":true}
    {"t":"scroll","dx":0,"dy":-1}
    {"t":"key","char":"a","down":true}   |   {"name":"enter",...}   |   {"vk":65,...}

Backends: uinput on Linux/Wayland, pynput controllers on Windows/macOS, and the KatoInput named pipe for
Windows' secure desktops. Gated by AllowInput, the same consent as the rest of the actuator. The hard-won
Windows parts - which desktop is showing, when a shortcut must travel as a key code, letting keys up the
way they went down - are lifted straight from the proven Kato.
"""
import ctypes
import json
import os
import platform
import sys
import time

WINDOWS = platform.system() == "Windows"


# ----- Windows desktop-state gates (lifted from Kato) ------------------------
def input_blocked():
    """True when this machine can't take ordinary injected input: the Windows lock, UAC or login screen."""
    if not WINDOWS:
        return False
    u = ctypes.windll.user32
    h = u.OpenInputDesktop(0, False, 0x0100)            # DESKTOP_SWITCHDESKTOP
    if not h:
        return True                                     # a secure desktop is showing
    u.CloseDesktop(h)
    return False


_elevated = {"at": 0.0, "is": False}


def elevated_target():
    """True when the foreground window, or the one under the pointer, belongs to a program running as
    administrator - Windows silently drops ordinary input sent to those, so it must go via the service."""
    if not WINDOWS:
        return False
    now = time.time()
    if now - _elevated["at"] < 0.25:
        return _elevated["is"]
    _elevated["at"], found = now, False
    try:
        from ctypes import wintypes
        u, k, a = ctypes.windll.user32, ctypes.windll.kernel32, ctypes.windll.advapi32
        u.GetForegroundWindow.restype = ctypes.c_void_p
        u.WindowFromPoint.restype = ctypes.c_void_p
        u.WindowFromPoint.argtypes = [wintypes.POINT]
        u.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD)]
        k.OpenProcess.restype = ctypes.c_void_p
        k.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        k.CloseHandle.argtypes = [ctypes.c_void_p]
        a.OpenProcessToken.argtypes = [ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p)]
        a.GetTokenInformation.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
                                          ctypes.POINTER(wintypes.DWORD)]
        pt = wintypes.POINT()
        u.GetCursorPos(ctypes.byref(pt))
        for hwnd in {u.GetForegroundWindow(), u.WindowFromPoint(pt)}:
            if not hwnd or found:
                continue
            pid = wintypes.DWORD(0)
            u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if not pid.value or pid.value == os.getpid():
                continue
            h = k.OpenProcess(0x1000, False, pid.value)             # PROCESS_QUERY_LIMITED_INFORMATION
            if not h:
                found = True                                        # can't even look at it: it is above us
                continue
            try:
                token = ctypes.c_void_p()
                if not a.OpenProcessToken(h, 0x0008, ctypes.byref(token)):      # TOKEN_QUERY
                    found = True
                    continue
                try:
                    elevated, size = wintypes.DWORD(0), wintypes.DWORD(0)
                    if a.GetTokenInformation(token, 20, ctypes.byref(elevated), 4, ctypes.byref(size)) and elevated.value:
                        found = True                                # TokenElevation
                finally:
                    k.CloseHandle(token)
            finally:
                k.CloseHandle(h)
    except Exception:
        found = False
    _elevated["is"] = found
    return found


def needs_service():
    """Input only the Windows service can deliver: the lock screen and security prompts, and any window
    belonging to a program running as administrator."""
    return input_blocked() or elevated_target()


# ----- the named-pipe client to the Kato input service (lifted) --------------
class SecureInput:
    """Talks to the optional Kato Input Service (SYSTEM) to inject onto Windows' secure desktops. Silently
    does nothing if the service isn't installed, so the feature is simply absent unless the user chose it."""
    PIPE = r"\\.\pipe\KatoInput"

    def __init__(self):
        self.handle = None
        self.checked = 0.0

    def _open(self):
        GENERIC, OPEN_EXISTING = 0xC0000000, 3
        h = ctypes.windll.kernel32.CreateFileW(self.PIPE, GENERIC, 0, None, OPEN_EXISTING, 0, None)
        if h in (-1, 0xFFFFFFFFFFFFFFFF):
            return None
        mode = ctypes.c_ulong(0x00000002)                 # PIPE_READMODE_MESSAGE
        ctypes.windll.kernel32.SetNamedPipeHandleState(h, ctypes.byref(mode), None, None)
        return h

    def present(self):
        if not WINDOWS:
            return False
        now = time.time()
        if self.handle is None and now - self.checked > 3:
            self.checked = now
            self.handle = self._open()
        return self.handle is not None

    def send(self, cmd):
        if not self.present():
            return False
        data = (json.dumps(cmd) + "\n").encode("utf-8")
        written = ctypes.c_ulong(0)
        ok = ctypes.windll.kernel32.WriteFile(self.handle, data, len(data), ctypes.byref(written), None)
        if not ok:
            try:
                ctypes.windll.kernel32.CloseHandle(self.handle)
            except Exception:
                pass
            self.handle = None                             # make the next call reconnect
            return False
        return True


_SECURE = SecureInput()

# Windows virtual-key codes for the non-character keys (lifted from Kato)
_VK = {"enter": 0x0D, "return": 0x0D, "tab": 0x09, "space": 0x20, "backspace": 0x08, "delete": 0x2E,
       "esc": 0x1B, "escape": 0x1B, "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
       "home": 0x24, "end": 0x23, "page_up": 0x21, "page_down": 0x22, "insert": 0x2D,
       "shift": 0x10, "shift_r": 0x10, "ctrl": 0x11, "ctrl_l": 0x11, "ctrl_r": 0x11,
       "alt": 0x12, "alt_l": 0x12, "alt_r": 0x12, "alt_gr": 0x12, "cmd": 0x5B, "cmd_r": 0x5C,
       "caps_lock": 0x14, "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73, "f5": 0x74, "f6": 0x75,
       "f7": 0x76, "f8": 0x77, "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B}
_SHORTCUT_KEYS = (0x11, 0x12, 0x5B, 0x5C)                  # Ctrl, Alt, either Windows key


def _wire(event):
    """The on-the-wire key dict from a key event: {"name":..} | {"char":..} | {"vk":..}."""
    return {k: event[k] for k in ("name", "char", "vk") if k in event}


class KvmInjectCommands:
    """Mixed into Engine. The full-vocabulary actuator for a VML KVM; the mirror of CaptureCommands."""

    # per-engine state, created lazily
    def _kvm(self):
        s = getattr(self, "_kvm_state", None)
        if s is None:
            s = self._kvm_state = {"ready": False, "kb": None, "ms": None, "pk": None, "pm": None,
                                   "u": None, "held": {}, "sec_down": {}, "sec_mods": set()}
        return s

    def _kvm_lazy(self):
        s = self._kvm()
        if s["ready"]:
            return s
        if WINDOWS or sys.platform == "darwin":
            from pynput import keyboard, mouse
            s["kb"], s["ms"], s["pk"], s["pm"] = keyboard.Controller(), mouse.Controller(), keyboard, mouse
        else:
            from .uinput_inject import available, UinputInjector
            if not available():
                raise RuntimeError("/dev/uinput is not writable - add the udev rule (as Kato's installer does)")
            s["u"] = UinputInjector(log=lambda *a: None)
        s["ready"] = True
        return s

    @staticmethod
    def _vmetrics():
        u = ctypes.windll.user32
        return [u.GetSystemMetrics(i) for i in (76, 77, 78, 79)]    # vx, vy, vw, vh

    # ---- the one command a KVM policy calls per event ----
    def cmd_Inject(self, event=""):
        """Perform one input event on this machine - move, button, scroll or key - the same shape InputEvents
        reports. On Windows it hops onto the secure desktop or an admin window through the Kato input service
        when one is needed, else injects directly. Needs AllowInput first."""
        from . import headinput
        headinput._need_input()
        try:
            e = json.loads(event) if isinstance(event, str) else event
        except Exception:
            return ""
        if not isinstance(e, dict):
            return ""
        s = self._kvm_lazy()
        t = e.get("t")
        if t == "move":
            self._inj_move(s, float(e.get("x", 0.5)), float(e.get("y", 0.5)))
        elif t == "button":
            self._inj_button(s, str(e.get("name", "left")), bool(e.get("down")))
        elif t == "scroll":
            self._inj_scroll(s, int(e.get("dx", 0)), int(e.get("dy", 0)))
        elif t == "key":
            self._inj_key(s, _wire(e), bool(e.get("down")))
        return ""

    def _inj_move(self, s, x01, y01):
        x01, y01 = min(max(x01, 0.0), 1.0), min(max(y01, 0.0), 1.0)
        if s["u"]:
            s["u"].move(round(x01 * 65535), round(y01 * 65535), 65536, 65536)
            return
        vx, vy, vw, vh = self._vmetrics()
        px, py = int(vx + x01 * max(vw - 1, 1)), int(vy + y01 * max(vh - 1, 1))
        if WINDOWS and needs_service() and _SECURE.send({"t": "move", "x": px, "y": py}):
            return
        s["ms"].position = (px, py)

    def _inj_button(self, s, name, down):
        if s["u"]:
            s["u"].button(name, down)
            return
        if WINDOWS and needs_service() and _SECURE.send({"t": "btn", "button": name, "down": down}):
            return
        btn = getattr(s["pm"].Button, name, None)
        if btn:
            (s["ms"].press if down else s["ms"].release)(btn)

    def _inj_scroll(self, s, dx, dy):
        if s["u"]:
            s["u"].scroll(dx, dy)
            return
        if WINDOWS and needs_service() and _SECURE.send({"t": "scroll", "dx": dx, "dy": dy}):
            return
        s["ms"].scroll(dx, dy)

    def _inj_key(self, s, wire, down):
        if not wire:
            return
        if s["u"]:
            try:
                s["u"].key(wire, down)
            except Exception:
                pass
            return
        ident = json.dumps(wire, sort_keys=True)
        if WINDOWS and ((needs_service() and ident not in s["held"]) or ident in s["sec_down"]) \
                and self._secure_key(s, wire, down, ident):
            return
        k = self._wire_to_pk(s, wire)
        if k is None:
            return
        try:
            if down:
                s["kb"].press(k)
                s["held"][ident] = k
            else:
                s["kb"].release(k)
                s["held"].pop(ident, None)
        except Exception:
            pass

    @staticmethod
    def _wire_to_pk(s, wire):
        kb = s["pk"]
        if "name" in wire:
            return getattr(kb.Key, str(wire["name"]), None)
        if wire.get("char"):
            return wire["char"]
        if "vk" in wire:
            return kb.KeyCode.from_vk(int(wire["vk"]))
        return None

    def _secure_key(self, s, wire, down, ident=""):
        """Relay one key to the input service. A character types as itself whatever the layout, except while
        Ctrl/Alt/Win is held, when Windows only knows a shortcut from the real key code; a key goes up the same
        way it went down. Lifted from Kato."""
        if not down and ident in s["sec_down"]:
            return _SECURE.send(dict(s["sec_down"].pop(ident), down=False))
        cmd = None
        if "name" in wire:
            name = str(wire["name"]).lower()
            vk = _VK.get(name)
            if name.startswith(("ctrl", "alt", "cmd")) and name != "alt_gr":
                (s["sec_mods"].add if down else s["sec_mods"].discard)(name)
            cmd = {"t": "key", "vk": vk} if vk else None
        elif wire.get("char"):
            ch = str(wire["char"])[0]
            cmd = {"t": "key", "char": ord(ch)}
            try:
                u = ctypes.windll.user32
                held = {vk for vk in _SHORTCUT_KEYS if u.GetAsyncKeyState(vk) & 0x8000}
                alt_gr = 0x11 in held and 0x12 in held                # AltGr is Ctrl+Alt: typing, not a shortcut
                if (held or s["sec_mods"]) and not alt_gr:
                    found = u.VkKeyScanW(ord(ch)) & 0xFFFF
                    if found != 0xFFFF and found & 0xFF:
                        cmd = {"t": "key", "vk": found & 0xFF}
            except Exception:
                pass
        elif "vk" in wire:
            cmd = {"t": "key", "vk": int(wire["vk"])}
        if cmd is None:
            return False
        if down and ident:
            s["sec_down"][ident] = cmd
        return _SECURE.send(dict(cmd, down=down))

    def cmd_InjectRelease(self):
        """Let go of every key and button currently held - on the way home, or when a driven session ends."""
        s = self._kvm()
        if s.get("u"):
            try:
                s["u"].release_all()
            except Exception:
                pass
        for k in list(s["held"].values()):
            try:
                s["kb"].release(k)
            except Exception:
                pass
        s["held"].clear()
        for cmd in list(s["sec_down"].values()):
            _SECURE.send(dict(cmd, down=False))
        s["sec_down"].clear()
        s["sec_mods"].clear()
        return ""

    def cmd_InjectServiceReady(self):
        """\"1\" if the Windows secure-desktop input service is installed and reachable here, else \"0\"."""
        return "1" if _SECURE.present() else "0"
