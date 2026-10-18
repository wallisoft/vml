"""
How Visualised looks, in one place: the colours, corners and type that its own title bars, dialogs and menus are
drawn with, worked out from the desktop it's running on, so an app looks at home there.

    from .theme import theme
    t = theme()            t.surface, t.ink, t.accent ...  (worked out once, again when the desktop changes)

What it reads from the desktop:
    light or dark      Qt's colour scheme (GNOME's Appearance setting; Windows' app mode; a Mac's)
    accent             Windows' accent colour; GNOME's accent colour (47 and later); a Mac's; else blue
    corners            how round the desktop draws its own windows: Windows 11 8px all round, Windows 10 square,
                       GNOME 12px across the top, a Mac 10px all round
    title bar          its colour (Windows' accent if "Show accent colour on title bars" is on), and where the
                       title goes (left on Windows, centred elsewhere)

A form can still say otherwise for itself (TitleBackground, BorderBrush, MenuTheme, CornerRadius); this is what's
used when it doesn't.
"""
import os
import sys
from dataclasses import dataclass

GNOME_ACCENTS = {"blue": "#3584E4", "teal": "#2190A4", "green": "#3A944A", "yellow": "#C88800", "orange": "#ED5B00",
                 "red": "#E62D42", "pink": "#D56199", "purple": "#9141AC", "slate": "#6F8396"}


@dataclass
class Theme:
    dark: bool
    host: str            # win11, win10, mac, gnome, linux
    accent: str          # the desktop's highlight colour
    accent_ink: str      # words on the accent
    surface: str         # a dialog's or a menu's card
    band: str            # the pale band under a dialog's buttons; a hovered menu item
    line: str            # thin lines round things
    ink: str             # words
    muted: str           # quieter words
    title_bg: str        # a title bar
    title_ink: str
    title_align: str     # "left" or "center"
    corners: tuple       # (top, bottom) radius of a window
    edge: str            # a form's edge when it doesn't choose one: a quiet mid grey
    popup_radius: int    # a menu's corners

    def corner(self):
        return max(self.corners)


def _host():
    if sys.platform == "win32":
        return "win11" if sys.getwindowsversion().build >= 22000 else "win10"
    if sys.platform == "darwin":
        return "mac"
    desk = (os.environ.get("XDG_CURRENT_DESKTOP") or os.environ.get("DESKTOP_SESSION") or "").lower()
    return "gnome" if any(k in desk for k in ("gnome", "ubuntu", "unity", "budgie", "pantheon")) else "linux"


def _dark():
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication
        return QApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark
    except Exception:
        return False


def _windows_dwm():
    """Windows' accent colour, and whether title bars wear it."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\DWM") as k:
            abgr = winreg.QueryValueEx(k, "AccentColor")[0]
            try:
                prevalence = winreg.QueryValueEx(k, "ColorPrevalence")[0] == 1
            except OSError:
                prevalence = False
        return "#%02X%02X%02X" % (abgr & 0xFF, (abgr >> 8) & 0xFF, (abgr >> 16) & 0xFF), prevalence
    except Exception:
        return None, False


def _gnome_accent():
    try:
        import subprocess
        out = subprocess.run(["gsettings", "get", "org.gnome.desktop.interface", "accent-color"],
                             capture_output=True, text=True, timeout=2).stdout.strip().strip("'")
        return GNOME_ACCENTS.get(out)
    except Exception:
        return None


def _ink_on(colour):
    from PySide6.QtGui import QColor
    c = QColor(colour)
    return "#111827" if (0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()) > 150 else "#FFFFFF"


def _work_out():
    host, dark = _host(), _dark()
    title_on_accent = False
    if host.startswith("win"):
        accent, title_on_accent = _windows_dwm()
        accent = accent or "#0078D4"
    elif host == "gnome":
        accent = _gnome_accent() or "#3584E4"
    else:
        accent = "#3584E4" if host != "mac" else "#007AFF"
    if dark:
        surface, band, line, ink, muted = "#2B2B2B", "#242424", "#3D3D3D", "#F3F4F6", "#A1A1AA"
        title = {"win11": "#202020", "win10": "#202020", "mac": "#2D2D2D"}.get(host, "#303030")
    else:
        surface, band, line, ink, muted = "#FFFFFF", "#F7F8FA", "#E5E7EB", "#111827", "#6B7280"
        title = {"win11": "#F3F3F3", "win10": "#FFFFFF", "mac": "#E8E8E8"}.get(host, "#EBEBEB")
    if title_on_accent:
        title = accent
    corners = {"win11": (8, 8), "win10": (0, 0), "mac": (10, 10), "gnome": (12, 0)}.get(host, (8, 8))
    return Theme(dark=dark, host=host, edge="#6B6B6B" if dark else "#9CA3AF", accent=accent, accent_ink=_ink_on(accent),
                 surface=surface, band=band,
                 line=line, ink=ink, muted=muted, title_bg=title, title_ink=_ink_on(title),
                 title_align="left" if host.startswith("win") else "center", corners=corners,
                 popup_radius={"win11": 8, "win10": 0, "mac": 6}.get(host, 10))


_current = None


def theme():
    """The desktop's look, worked out the first time it's asked for (and again after refresh())."""
    global _current
    if _current is None:
        _current = _work_out()
        try:                                                    # the desktop switched light/dark: work it out again
            from PySide6.QtWidgets import QApplication
            hints = QApplication.styleHints()
            if not getattr(hints, "_vml_theme_hooked", False):
                hints.colorSchemeChanged.connect(lambda *a: refresh())
                hints._vml_theme_hooked = True
        except Exception:
            pass
    return _current


def refresh():
    global _current
    _current = None
    return theme()
