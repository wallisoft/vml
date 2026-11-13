"""
Input commands for VML — the head-tracking SENSOR and the kb/mouse ACTUATOR,
exposed to @Script as Vml() commands. Policy (gain, smoothing, dwell, calibration,
edge-crossing) lives in VML where it can be tuned without a rebuild; this module is
only sensors and actuators.

    Vml("Face")                 -> {"present":0|1,"nx":..,"ny":..,"blinkL":..,"blinkR":..,"jawOpen":..}
    Vml("FaceStop")
    Vml("AllowInput")           -- consent gate; required once before any Mouse*/Key* fires
    Vml("MouseMove", x, y)      -- x,y normalised 0..1 of the virtual desktop
    Vml("MouseClick") / MouseDown / MouseUp
    Vml("KeyText", "hello")     -- unicode
    Vml("KeyPress", "enter")    -- enter/back/space/tab/esc/up/down/left/right

Face is lazy: mediapipe + cv2 are imported only on first use, so this module is free
to import without them. Injection: Windows via SendInput, Linux/Wayland via uinput
(Kato's injector, vendored here as uinput_inject). macOS to follow.
"""
import json
import os
import sys
import threading
import time
import urllib.request

MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/face_landmarker/"
             "face_landmarker/float16/1/face_landmarker.task")


def _model_path():
    cache = os.path.join(os.path.expanduser("~"), ".vml", "models")
    os.makedirs(cache, exist_ok=True)
    path = os.path.join(cache, "face_landmarker.task")
    if not os.path.exists(path):
        urllib.request.urlretrieve(MODEL_URL, path)          # one-time fetch
    return path


class _Head:
    """Runs the camera + FaceLandmarker in a background thread; publishes the latest signals."""
    def __init__(self):
        self.lock = threading.Lock()
        self.last = {"present": 0, "nx": 0.5, "ny": 0.5, "blinkL": 0.0, "blinkR": 0.0, "jawOpen": 0.0}
        self.thread = None
        self.stop = threading.Event()
        self.err = ""

    def start(self, cam_index=0, flip=True):
        if self.thread and self.thread.is_alive():
            return
        self.stop.clear()
        self.thread = threading.Thread(target=self._run, args=(cam_index, flip), daemon=True)
        self.thread.start()

    def _run(self, cam_index, flip):
        try:
            import cv2
            import mediapipe as mp
            from mediapipe.tasks import python as mptask
            from mediapipe.tasks.python import vision
            base = mptask.BaseOptions(model_asset_path=_model_path())
            opts = vision.FaceLandmarkerOptions(base_options=base, running_mode=vision.RunningMode.VIDEO,
                                                num_faces=1, output_face_blendshapes=True)
            lm = vision.FaceLandmarker.create_from_options(opts)
            cap = cv2.VideoCapture(cam_index, cv2.CAP_DSHOW if sys.platform.startswith("win") else 0)
            if not cap.isOpened():
                self.err = "camera %s would not open" % cam_index
                return
            i = 0
            while not self.stop.is_set():
                ok, frame = cap.read()
                if not ok:
                    time.sleep(0.02); continue
                i += 1
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                res = lm.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb),
                                          int(time.time() * 1000) + i)
                if res.face_landmarks:
                    n = res.face_landmarks[0][1]
                    nx = (1.0 - n.x) if flip else n.x
                    bs = {}
                    if res.face_blendshapes:
                        for c in res.face_blendshapes[0]:
                            bs[c.category_name] = c.score
                    with self.lock:
                        self.last = {"present": 1, "nx": round(nx, 4), "ny": round(n.y, 4),
                                     "blinkL": round(bs.get("eyeBlinkLeft", 0.0), 3),
                                     "blinkR": round(bs.get("eyeBlinkRight", 0.0), 3),
                                     "jawOpen": round(bs.get("jawOpen", 0.0), 3)}
                else:
                    with self.lock:
                        self.last = dict(self.last, present=0)
            cap.release()
        except Exception as e:
            self.err = str(e)
            with self.lock:
                self.last = dict(self.last, present=0)


_HEAD = _Head()
_INPUT_OK = False                       # flipped by Vml("AllowInput") — the consent gate


# ---- Windows injection (SendInput), built once on first use -----------------
_WIN = None

def _win():
    global _WIN
    if _WIN is not None:
        return _WIN
    if not sys.platform.startswith("win"):
        raise RuntimeError("input injection is Windows-only for now")
    import ctypes
    from ctypes import wintypes

    MOUSEEVENTF_MOVE, MOUSEEVENTF_ABSOLUTE, MOUSEEVENTF_VIRTUALDESK = 0x0001, 0x8000, 0x4000
    MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP = 0x0002, 0x0004
    KEYEVENTF_KEYUP, KEYEVENTF_UNICODE = 0x0002, 0x0004
    INPUT_MOUSE, INPUT_KEYBOARD = 0, 1
    VK = {"back": 0x08, "tab": 0x09, "enter": 0x0D, "esc": 0x1B, "space": 0x20,
          "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28, "delete": 0x2E}

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                    ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                    ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG))]

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                    ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG))]

    class _U(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT)]

    class INPUT(ctypes.Structure):
        _fields_ = [("type", wintypes.DWORD), ("u", _U)]

    user32 = ctypes.windll.user32
    SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN = 78, 79

    def _send(inp):
        user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))

    class Win:
        def move_abs(self, x01, y01):
            ax = int(max(0.0, min(1.0, x01)) * 65535)
            ay = int(max(0.0, min(1.0, y01)) * 65535)
            mi = MOUSEINPUT(ax, ay, 0, MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK, 0, None)
            _send(INPUT(INPUT_MOUSE, _U(mi=mi)))

        def _btn(self, flag):
            _send(INPUT(INPUT_MOUSE, _U(mi=MOUSEINPUT(0, 0, 0, flag, 0, None))))

        def click(self):
            self._btn(MOUSEEVENTF_LEFTDOWN); self._btn(MOUSEEVENTF_LEFTUP)

        def down(self):
            self._btn(MOUSEEVENTF_LEFTDOWN)

        def up(self):
            self._btn(MOUSEEVENTF_LEFTUP)

        def type_text(self, s):
            for ch in s:
                code = ord(ch)
                _send(INPUT(INPUT_KEYBOARD, _U(ki=KEYBDINPUT(0, code, KEYEVENTF_UNICODE, 0, None))))
                _send(INPUT(INPUT_KEYBOARD, _U(ki=KEYBDINPUT(0, code, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0, None))))

        def press(self, name):
            vk = VK.get(str(name).lower())
            if vk is None:
                return
            _send(INPUT(INPUT_KEYBOARD, _U(ki=KEYBDINPUT(vk, 0, 0, 0, None))))
            _send(INPUT(INPUT_KEYBOARD, _U(ki=KEYBDINPUT(vk, 0, KEYEVENTF_KEYUP, 0, None))))

    _WIN = Win()
    return _WIN


# ---- Linux / Wayland injection via uinput (Kato's injector, vendored) --------
_LINUX = None

class _LinuxInj:
    def __init__(self):
        from .uinput_inject import available, UinputInjector
        if not available():
            raise RuntimeError("/dev/uinput is not writable - add the udev rule (as Kato's installer does)")
        self._u = UinputInjector(log=lambda *a: None)

    def move_abs(self, x01, y01):
        x = max(0.0, min(1.0, x01)); y = max(0.0, min(1.0, y01))
        self._u.move(round(x * 65535), round(y * 65535), 65536, 65536)

    def click(self):
        self._u.button("left", True); self._u.button("left", False)

    def down(self):
        self._u.button("left", True)

    def up(self):
        self._u.button("left", False)

    def type_text(self, s):
        for ch in s:
            self._u.key({"char": ch}, True); self._u.key({"char": ch}, False)

    def press(self, name):
        wire = {"name": {"back": "backspace"}.get(str(name).lower(), str(name).lower())}
        self._u.key(wire, True); self._u.key(wire, False)


def _injector():
    """The input injector for this OS: Windows SendInput, or Linux/Wayland uinput."""
    global _LINUX
    if sys.platform.startswith("win"):
        return _win()
    if _LINUX is None:
        _LINUX = _LinuxInj()
    return _LINUX


def _need_input():
    if not _INPUT_OK:
        raise RuntimeError("input not permitted: call Vml(\"AllowInput\") first (declare the app's Inject capability)")


class InputCommands:
    """Mixed into Engine. Face = read-only sensor; Mouse*/Key* = gated actuator."""

    # --- sensor ---------------------------------------------------------------
    def cmd_Face(self, cam="0", flip="1"):
        """The head right now, from the camera, as JSON: present (0/1), nx and ny (the nose, 0..1 across the frame),
        blinkL, blinkR and jawOpen (0..1). Starts the camera on the first call. The pointer policy - gain, smoothing,
        dwell, calibration - belongs in your script; this only reports what the camera sees."""
        _HEAD.start(int(cam or "0"), str(flip) != "0")
        with _HEAD.lock:
            return json.dumps(_HEAD.last)

    def cmd_FaceStop(self):
        """Stop the camera that Face started."""
        _HEAD.stop.set()
        return ""

    def cmd_FaceError(self):
        """The last trouble the face camera hit (\"\" if none): no camera, or the vision libraries not installed."""
        return _HEAD.err

    # --- consent gate ---------------------------------------------------------
    def cmd_AllowInput(self, on="1"):
        """Let this app move the mouse and type (MouseMove, MouseClick, KeyText, KeyPress). Call it once the user has
        agreed; nothing is injected until you do. AllowInput \"0\" turns it off again."""
        global _INPUT_OK
        _INPUT_OK = str(on) != "0"
        return "1" if _INPUT_OK else "0"

    # --- actuator (gated) -----------------------------------------------------
    def cmd_MouseMove(self, x="0.5", y="0.5"):
        """Move the mouse to x,y - each 0..1 across the whole desktop (0.5, 0.5 is the centre). Needs AllowInput first."""
        _need_input(); _injector().move_abs(float(x), float(y)); return ""

    def cmd_MouseClick(self):
        """Click the left mouse button where the pointer is. Needs AllowInput first."""
        _need_input(); _injector().click(); return ""

    def cmd_MouseDown(self):
        """Press and hold the left mouse button (with MouseUp, that makes a drag). Needs AllowInput first."""
        _need_input(); _injector().down(); return ""

    def cmd_MouseUp(self):
        """Let go of the left mouse button. Needs AllowInput first."""
        _need_input(); _injector().up(); return ""

    def cmd_KeyText(self, text=""):
        """Type text into whatever has keyboard focus, as if from the keyboard. Needs AllowInput first."""
        _need_input(); _injector().type_text(str(text)); return ""

    def cmd_KeyPress(self, key=""):
        """Press a named key: enter, back, space, tab, esc, up, down, left, right, delete. Needs AllowInput first."""
        _need_input(); _injector().press(str(key)); return ""
