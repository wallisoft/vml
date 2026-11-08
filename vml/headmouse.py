#!/usr/bin/env python3
"""Head-mouse as an engine command.

Webcam + MediaPipe head-tracking, exposed through Vml() so ANY Visualised app
can go hands-free: drive the real OS cursor (and click by dwell/mouth/blink), or
consume cursor+click events and move its own selection (an AAC talker lighting
up tiles, no OS cursor needed).

This is Andy's proven standalone HeadTracker, lifted in verbatim so every bit of
its tuning (gains, smoothing, dwell/blink/jaw, calibration, edge-crossing to a
second screen) carries over. cv2 + mediapipe import lazily - only when it starts
- so the engine loads fine on a box without them; the frozen runtime bundles
them so Face works on a clean machine.

Commands:
    Vml("HeadMouse", "start")            start; drive the real OS cursor + clicks
    Vml("HeadMouse", "start", "events")  start; events only (no OS cursor)
    Vml("HeadMouse", "stop")             stop the camera + tracking
    Vml("HeadMouse", "read")             latest {x,y,click,face,crossed} as JSON
    Vml("HeadMouse", "recentre")         re-centre on the current head pose
    Vml("HeadMouse", "calibrate")        5-second look-around auto-calibration
    Vml("HeadMouse", "running")          "1" while tracking, "" otherwise
    Vml("HeadMouse", "status")           the last status line (text)
    Vml("HeadSet", "gainX", "8")         tune any config key live:
                                         gain/gainX/gainY, dwellMs, dwellR,
                                         clickMethod (dwell|blink|jaw|off),
                                         blinkMs, jawThresh, paused (1/0), recipe
                                         (steady|tremor|minimal), flip, ...
    Vml("Face")                          {nx,ny,present,click} JSON, auto-starting
                                         in events mode - what a talker polls each tick
    Vml("FaceStop")                      alias for HeadMouse stop
"""
import os, sys, json, time, threading

DEFAULTS = {
    "gain":       2.6,
    "gainX":      2.6,
    "gainY":      2.6,
    "deadzone":   0.004,
    "smoothMin":  0.08,
    "smoothMax":  0.9,
    "velSpan":    0.02,
    "clickMethod": "dwell",   # dwell | blink | jaw | off
    "dwellR":     0.03,
    "dwellMs":    900,
    "cooldownMs": 700,
    "blinkThresh": 0.5,
    "blinkMs":    450,
    "jawThresh":  0.4,
    "jawMs":      350,
    "flip":       True,
    "camIndex":   0,
    "camW":       640,
    "camH":       480,
    "phonePos":   "left",
    "crossEdge":  0.015,
    "crossDwellMs": 700,
    "phoneScale": 2.5,
    "comfort":    1.3,
}

RECIPES = {
    "steady":  {"gainX": 7.2,  "gainY": 14.4, "smoothMin": 0.12, "smoothMax": 0.9,  "velSpan": 0.02},
    "tremor":  {"gainX": 6.0,  "gainY": 12.0, "smoothMin": 0.05, "smoothMax": 0.55, "velSpan": 0.05},
    "minimal": {"gainX": 9.0,  "gainY": 18.0, "smoothMin": 0.10, "smoothMax": 0.9,  "velSpan": 0.015},
}


def data_dir():
    """A writable per-user home for the head-mouse config + the face model.
    Not next to this file: in the frozen runtime that lives read-only inside the
    exe, and the model has to be fetchable + the config tunable."""
    if sys.platform.startswith("win"):
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        d = os.path.join(base, "Visualised", "headmouse")
    else:
        d = os.path.join(os.path.expanduser("~"), ".local", "share", "visualised", "headmouse")
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:
        pass
    return d


def cfg_path():
    return os.path.join(data_dir(), "headmouse.json")


def update_cfg(path, **kw):
    """Merge keys into the json config the tracker live-reloads."""
    cfg = {}
    try:
        with open(path, encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        pass
    cfg.update(kw)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        pass
    return cfg


def load_cfg(path):
    cfg = dict(DEFAULTS)
    try:
        with open(path, encoding="utf-8") as f:
            cfg.update(json.load(f))
    except FileNotFoundError:
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(DEFAULTS, f, indent=2)
        except Exception:
            pass
    except Exception as e:
        print("headmouse: config read error (using last good):", e)
    rec = cfg.get("recipe")
    if rec in RECIPES:
        cfg.update(RECIPES[rec])
    return cfg


def _key_down(vk):
    try:
        import ctypes
        return bool(ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000)
    except Exception:
        return False


def _at_edge(x, y, pos, m):
    if pos == "left":   return x <= m
    if pos == "right":  return x >= 1 - m
    if pos == "top":    return y <= m
    if pos == "bottom": return y >= 1 - m
    return False


def _opposite(pos):
    return {"left": "right", "right": "left", "top": "bottom", "bottom": "top"}.get(pos, "right")


def _scrolllock_on():
    """Scroll Lock as a hard pause toggle (its LED shows the state)."""
    try:
        import ctypes
        return bool(ctypes.windll.user32.GetKeyState(0x91) & 1)  # VK_SCROLL
    except Exception:
        return False


class HeadTracker:
    """The embeddable engine. injector drives the OS cursor (optional);
    on_event gets every frame's {x,y,click,face}. Both independent."""

    def __init__(self, config_path=None, model_path=None, injector=None,
                 on_event=None, on_status=None):
        self.config_path = config_path or cfg_path()
        self.model_path = model_path or os.path.join(data_dir(), "face_landmarker.task")
        self.injector = injector
        self.on_event = on_event or (lambda e: None)
        self.on_status = on_status or (lambda s: None)
        self._stop = threading.Event()
        self._thread = None
        self.last = {"x": 0.5, "y": 0.5, "face": 0, "click": False, "crossed": False}
        self._yield_until = 0.0

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)

    def running(self):
        return bool(self._thread and self._thread.is_alive())

    def _emit(self, x, y, click, face, crossed=False):
        self.last = {"x": x, "y": y, "click": click, "face": face, "crossed": crossed}
        try:
            self.on_event(self.last)
        except Exception:
            pass

    def _ensure_model(self):
        if not os.path.exists(self.model_path):
            import urllib.request
            self.on_status("fetching face model (once)...")
            urllib.request.urlretrieve(
                "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
                "face_landmarker/float16/1/face_landmarker.task", self.model_path)

    def _run(self):
        try:
            import cv2
            import mediapipe as mp
            from mediapipe.tasks import python as mptask
            from mediapipe.tasks.python import vision
        except Exception as e:
            self.on_status("ERROR: head-mouse needs the camera libraries (%s)" % e)
            return

        try:
            self._ensure_model()
        except Exception as e:
            self.on_status("ERROR: could not get the face model (%s)" % e); return
        base = mptask.BaseOptions(model_asset_path=self.model_path)
        opts = vision.FaceLandmarkerOptions(
            base_options=base, running_mode=vision.RunningMode.VIDEO,
            num_faces=1, output_face_blendshapes=True)
        lm = vision.FaceLandmarker.create_from_options(opts)

        cfg = load_cfg(self.config_path)
        self._recenter_seen = cfg.get("recenter")
        self._cal_seen = cfg.get("calibrate")
        cap = cv2.VideoCapture(cfg["camIndex"], cv2.CAP_DSHOW if sys.platform.startswith("win") else 0)
        if not cap.isOpened():
            self.on_status("ERROR: camera %s would not open" % cfg["camIndex"]); return
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, cfg["camW"])
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cfg["camH"])

        centre = None
        if cfg.get("centerX") is not None and cfg.get("centerY") is not None:
            try: centre = (float(cfg["centerX"]), float(cfg["centerY"]))
            except Exception: centre = None
        sm_x = sm_y = 0.5
        prev_nose = None
        anchor = None; anchor_t = 0.0
        blink_t = None
        jaw_t = None
        crossed = False; edge_since = None
        phone_centre = None
        f9_down = False
        calibrating = False; cal_end = 0.0; cal_min = [1.0, 1.0]; cal_max = [0.0, 0.0]
        last_click = 0.0
        last_seen = time.time()
        last_cfg = time.time()
        i = 0
        try:
            while not self._stop.is_set():
                ok, frame = cap.read()
                if not ok:
                    time.sleep(0.02); continue
                i += 1
                now = time.time()
                if now - last_cfg > 1.0:
                    cfg = load_cfg(self.config_path); last_cfg = now
                    if cfg.get("recenter") != self._recenter_seen:
                        self._recenter_seen = cfg.get("recenter")
                        centre = None; crossed = False; edge_since = None; sm_x = sm_y = 0.5; anchor = None
                    if cfg.get("calibrate") != self._cal_seen:
                        self._cal_seen = cfg.get("calibrate")
                        calibrating = True; cal_end = now + 5.0
                        cal_min = [1.0, 1.0]; cal_max = [0.0, 0.0]
                        self.on_status("calibrating - look slowly round all four edges")
                dn = _key_down(0x78)                      # F9 = manual re-centre
                if dn and not f9_down:
                    centre = None; crossed = False; edge_since = None; sm_x = sm_y = 0.5; anchor = None
                f9_down = dn

                if cfg.get("paused"):
                    self._emit(sm_x, sm_y, False, 0, crossed)
                    continue

                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                res = lm.detect_for_video(
                    mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb),
                    int(now * 1000) + i)

                if not res.face_landmarks:
                    self._emit(sm_x, sm_y, False, 0, crossed)
                    continue
                last_seen = now
                n = res.face_landmarks[0][1]
                nx = (1.0 - n.x) if cfg["flip"] else n.x
                ny = n.y
                if prev_nose is None:
                    prev_nose = (nx, ny)

                if calibrating:
                    cal_min[0] = min(cal_min[0], nx); cal_max[0] = max(cal_max[0], nx)
                    cal_min[1] = min(cal_min[1], ny); cal_max[1] = max(cal_max[1], ny)
                    if now >= cal_end:
                        midx = (cal_min[0] + cal_max[0]) / 2.0; midy = (cal_min[1] + cal_max[1]) / 2.0
                        hx = max(0.015, (cal_max[0] - cal_min[0]) / 2.0)
                        hy = max(0.015, (cal_max[1] - cal_min[1]) / 2.0)
                        cmf = cfg.get("comfort", 1.3)
                        gx = min(40.0, max(2.0, round(0.5 / hx * cmf, 2)))
                        gy = min(40.0, max(2.0, round(0.5 / hy * cmf, 2)))
                        centre = (midx, midy); prev_nose = (midx, midy)
                        try: update_cfg(self.config_path, gainX=gx, gainY=gy, centerX=round(midx, 4), centerY=round(midy, 4), recipe=None)
                        except Exception: pass
                        calibrating = False
                        self.on_status("calibrated: sideways %.1f, up/down %.1f" % (gx, gy))
                    self._emit(sm_x, sm_y, False, 1, crossed)
                    continue

                if centre is None:
                    centre = (nx, ny); prev_nose = (nx, ny)
                    try: update_cfg(self.config_path, centerX=round(nx, 4), centerY=round(ny, 4))
                    except Exception: pass
                    self.on_status("centred")
                    self._emit(sm_x, sm_y, False, 1)
                    continue

                vel = ((nx - prev_nose[0])**2 + (ny - prev_nose[1])**2) ** 0.5
                prev_nose = (nx, ny)
                t = min(1.0, vel / max(1e-6, cfg["velSpan"]))
                alpha = cfg["smoothMin"] + (cfg["smoothMax"] - cfg["smoothMin"]) * t

                on_phone = crossed and phone_centre is not None
                anchor_base = phone_centre if on_phone else centre
                gmul = cfg.get("phoneScale", 2.5) if on_phone else 1.0
                dx, dy = nx - anchor_base[0], ny - anchor_base[1]
                if abs(dx) < cfg["deadzone"]: dx = 0.0
                if abs(dy) < cfg["deadzone"]: dy = 0.0
                tx = 0.5 + dx * cfg.get("gainX", cfg["gain"]) * gmul
                ty = 0.5 + dy * cfg.get("gainY", cfg["gain"]) * gmul
                tx = 0.0 if tx < 0 else (1.0 if tx > 1 else tx)
                ty = 0.0 if ty < 0 else (1.0 if ty > 1 else ty)
                sm_x += alpha * (tx - sm_x)
                sm_y += alpha * (ty - sm_y)
                paused = _scrolllock_on()
                if self.injector and getattr(self.injector, "user_moved", None) and self.injector.user_moved():
                    self._yield_until = now + 3.0          # real mouse touched -> step aside
                yielding = now < self._yield_until

                pos = cfg.get("phonePos", "left")
                want_edge = _at_edge(sm_x, sm_y, pos if not crossed else _opposite(pos), cfg.get("crossEdge", 0.015))
                if want_edge:
                    if edge_since is None:
                        edge_since = now
                    elif (now - edge_since) * 1000 >= cfg.get("crossDwellMs", 700):
                        crossed = not crossed; edge_since = None; anchor = None
                        phone_centre = (nx, ny) if crossed else None
                else:
                    edge_since = None

                drive_pc = (not crossed) and (not paused) and (not yielding)
                if not drive_pc:
                    anchor = None; blink_t = None; jaw_t = None
                if drive_pc and self.injector:
                    self.injector.move_abs(sm_x, sm_y)
                elif self.injector and getattr(self.injector, "sync", None):
                    self.injector.sync()

                clicked = False
                method = cfg["clickMethod"] if (drive_pc and not want_edge) else None
                if method == "dwell":
                    if anchor is None or ((sm_x-anchor[0])**2 + (sm_y-anchor[1])**2) ** 0.5 > cfg["dwellR"]:
                        anchor = (sm_x, sm_y); anchor_t = now
                    elif (now-anchor_t)*1000 >= cfg["dwellMs"] and (now-last_click)*1000 >= cfg["cooldownMs"]:
                        clicked = True; anchor_t = now
                elif method == "blink":
                    if self._both_eyes_shut(res, cfg["blinkThresh"]):
                        if blink_t is None:
                            blink_t = now
                        elif (now-blink_t)*1000 >= cfg["blinkMs"] and (now-last_click)*1000 >= cfg["cooldownMs"]:
                            clicked = True; blink_t = None
                    else:
                        blink_t = None
                elif method == "jaw":
                    if self._mouth_open(res, cfg["jawThresh"]):
                        if jaw_t is None:
                            jaw_t = now
                        elif (now-jaw_t)*1000 >= cfg["jawMs"] and (now-last_click)*1000 >= cfg["cooldownMs"]:
                            clicked = True; jaw_t = None
                    else:
                        jaw_t = None

                if clicked:
                    last_click = now
                    if self.injector:
                        self.injector.click()
                    self.on_status("click")
                self._emit(sm_x, sm_y, clicked, 1, crossed)
        finally:
            try: cap.release()
            except Exception: pass
            self.on_status("stopped")

    @staticmethod
    def _both_eyes_shut(res, thresh):
        if not res.face_blendshapes:
            return False
        s = {c.category_name: c.score for c in res.face_blendshapes[0]}
        return min(s.get("eyeBlinkLeft", 0.0), s.get("eyeBlinkRight", 0.0)) >= thresh

    @staticmethod
    def _mouth_open(res, thresh):
        if not res.face_blendshapes:
            return False
        s = {c.category_name: c.score for c in res.face_blendshapes[0]}
        return s.get("jawOpen", 0.0) >= thresh


# ---------- Windows SendInput injector (drives the real OS cursor) ----------
def win_injector():
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                    ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                    ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG))]
    class _U(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT)]
    class INPUT(ctypes.Structure):
        _fields_ = [("type", wintypes.DWORD), ("u", _U)]
    MOVE, ABS, VDESK, LDOWN, LUP = 0x0001, 0x8000, 0x4000, 0x0002, 0x0004

    def send(flags, dx=0, dy=0):
        extra = ctypes.c_ulong(0)
        mi = MOUSEINPUT(dx, dy, 0, flags, 0, ctypes.pointer(extra))
        inp = INPUT(0, _U(mi))
        user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))

    class WinInjector:
        def __init__(self):
            self._last = None
        def _pos(self):
            pt = wintypes.POINT()
            user32.GetCursorPos(ctypes.byref(pt))
            return (pt.x, pt.y)
        def move_abs(self, nx, ny):
            nx = 0.0 if nx < 0 else 1.0 if nx > 1 else nx
            ny = 0.0 if ny < 0 else 1.0 if ny > 1 else ny
            send(MOVE | ABS | VDESK, int(nx*65535), int(ny*65535))
            self._last = self._pos()
        def user_moved(self, thresh=4):
            if self._last is None:
                return False
            p = self._pos()
            return ((p[0]-self._last[0])**2 + (p[1]-self._last[1])**2) ** 0.5 > thresh
        def sync(self):
            self._last = self._pos()
        def click(self):
            send(LDOWN); send(LUP)
    try:
        ctypes.windll.winmm.timeBeginPeriod(1)
    except Exception:
        pass
    return WinInjector()


def _injector():
    """The OS-cursor injector for this platform, or None (events-only).
    Windows: SendInput. Linux/mac cursor-drive is a follow-up (uinput / CGEvent);
    until then those platforms run events-only and the app moves its own focus."""
    if sys.platform.startswith("win"):
        try:
            return win_injector()
        except Exception:
            return None
    return None


# ---------- the engine command surface ----------
class HeadMouseCommands:
    """Mixed into Engine: Vml("HeadMouse"/"HeadSet"/"Face"/"FaceStop", ...)."""

    def _hm(self):
        return getattr(self, "_headtracker", None)

    def _hm_set_status(self, s):
        # called from the tracker thread: only touch a plain attribute (GIL-safe),
        # never Qt, so there's no cross-thread UI crash.
        self._hm_status_text = s

    def cmd_HeadMouse(self, action="start", mode="cursor"):
        action = (action or "start").strip().lower()
        if action == "start":
            try:
                from . import packs
                if packs.available("headmouse") == "missing":
                    return "needs-pack:headmouse"   # app prompts to unlock/install the pack
            except Exception:
                pass
            ht = self._hm()
            if ht and ht.running():
                return "1"
            inj = None if (mode or "").strip().lower() == "events" else _injector()
            ht = HeadTracker(injector=inj, on_status=self._hm_set_status)
            self._headtracker = ht
            self._hm_status_text = "starting"
            ht.start()
            return "1"
        if action in ("stop", "facestop"):
            ht = self._hm()
            if ht:
                ht.stop()
            return ""
        if action == "read":
            ht = self._hm()
            last = ht.last if ht else {"x": 0.5, "y": 0.5, "click": False, "face": 0, "crossed": False}
            return json.dumps(last)
        if action in ("recentre", "recenter"):
            update_cfg(cfg_path(), recenter=int(load_cfg(cfg_path()).get("recenter", 0)) + 1)
            return ""
        if action == "calibrate":
            update_cfg(cfg_path(), calibrate=int(load_cfg(cfg_path()).get("calibrate", 0)) + 1)
            return ""
        if action == "running":
            ht = self._hm()
            return "1" if (ht and ht.running()) else ""
        if action == "status":
            return getattr(self, "_hm_status_text", "")
        return ""

    def cmd_HeadSet(self, key="", value=""):
        key = (key or "").strip()
        if not key:
            return ""
        v = value
        if key in ("flip", "paused"):
            v = 1 if str(value).strip().lower() in ("1", "true", "on", "yes") else 0
        elif key in ("clickMethod", "recipe", "phonePos"):
            v = str(value).strip()
        else:
            try:
                sv = str(value).strip()
                v = float(sv) if ("." in sv or "e" in sv.lower()) else int(sv)
            except Exception:
                v = value
        update_cfg(cfg_path(), **{key: v})
        return ""

    def cmd_Face(self):
        """Latest head state as {nx,ny,present,click} JSON, auto-starting in
        events mode. What an AAC talker polls each tick to move its own highlight."""
        ht = self._hm()
        if not (ht and ht.running()):
            self.cmd_HeadMouse("start", "events")
            ht = self._hm()
        last = ht.last if ht else {"x": 0.5, "y": 0.5, "click": False, "face": 0}
        return json.dumps({"nx": last.get("x", 0.5), "ny": last.get("y", 0.5),
                           "present": last.get("face", 0), "click": last.get("click", False)})

    def cmd_FaceStop(self):
        return self.cmd_HeadMouse("stop")
