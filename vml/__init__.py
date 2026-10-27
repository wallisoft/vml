"""VML engine for Qt: VML -> (Lua parser) -> SQLite -> Qt widgets, scripted in Lua, Bash and PowerShell."""
__version__ = "1.12.0"

import os as _os2
import sys as _sys2
if _sys2.platform.startswith("win") and not _os2.environ.get("QT_QPA_PLATFORM"):
    # (Windows: ClearType text) Qt draws text with DirectWrite's greyscale smoothing, thin beside every other Windows
    # app; its GDI engine draws it with ClearType, as Explorer and Notepad do. QT_QPA_PLATFORM set already wins.
    _os2.environ["QT_QPA_PLATFORM"] = "windows:fontengine=gdi"
elif _sys2.platform.startswith("linux") and _os2.environ.get("WAYLAND_DISPLAY") and not _os2.environ.get("QT_QPA_PLATFORM"):
    # (Linux/Wayland: shortcuts) Under Qt's native Wayland plugin, menu-accelerator shortcuts (Ctrl+S, Ctrl+X, ...)
    # do not fire; XWayland (xcb) behaves like X11 and Windows, where they always have. An explicit override wins.
    _os2.environ["QT_QPA_PLATFORM"] = "xcb"

import os as _os
import sys as _sys
if ("__compiled__" in globals() or getattr(_sys, "frozen", False)) and not _os.path.isfile(_sys.executable):
    # (compiled: the real program, not Nuitka's stand-in) Newer Nuitka sets sys.executable to a "python" that
    # doesn't exist, so a program can't start itself by accident; Visualised starts itself on purpose (a folder or
    # RAM drive's server, a form in a window of its own), so it gets the real program back.
    for _exe in ("/proc/self/exe", _sys.argv[0] if _sys.argv else ""):
        _exe = _os.path.realpath(_exe) if _exe else ""
        if _exe and _os.path.isfile(_exe) and "python" not in _os.path.basename(_exe).lower():
            _sys.executable = _exe
            break
