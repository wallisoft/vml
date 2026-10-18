"""
Visualised's own menus: the bar along a form's top and the drop-downs (and right-click menus) under it, drawn here
in the desktop's colours (vml/theme.py) or the form's MenuTheme, the same on every desktop: cards with rounded
corners and a soft shadow, roomy items, ticks, shortcuts on the right, an arrow for a sub-menu.

What's drawn is ours; the workings underneath are Qt's (QMenu, QMenuBar): the keyboard (arrows, Enter, Escape,
Alt and the underlined letters), sub-menus opening as you hover, keeping a menu on the screen near an edge,
shortcuts that work with the menu shut. Twenty years of getting those right isn't worth throwing away; how a menu
looks and feels is the part worth owning, and this is it.

    VmlMenu      a drop-down or right-click menu       VmlMenuBar   the bar
    menu_theme   a MenuTheme's properties, set on either one (a menu without its own asks its bar)
"""
from PySide6.QtCore import QPoint, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QFontMetrics, QKeySequence, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QMenu, QMenuBar

SHADOW = 12                      # room round a drop-down's card for its shadow
ITEM_H = 30                      # an item's height
SIDE = 6                         # the gap between the card's edge and an item's highlight
TICK_W = 28                      # room on the left for a tick
ARROW_W = 22                     # room on the right for a sub-menu's arrow


def _theme():
    from .theme import theme
    return theme()


def _colours(menu_theme, dark):
    """What a menu is drawn in: the form's MenuTheme where it says, else the desktop's."""
    t = _theme()
    m = menu_theme or {}
    card = QColor(m.get("PopupBackground") or t.surface)
    ink = QColor("#111827") if card.lightnessF() > 0.55 else QColor("#F3F4F6")
    if m.get("Background"):                              # a themed form: its highlight is its bar's colour
        hover, hover_ink = QColor(m["Background"]), QColor(m.get("Foreground") or "#FFFFFF")
    else:
        hover = QColor(ink)
        hover.setAlpha(22 if card.lightnessF() > 0.55 else 34)
        hover_ink = ink
    line = QColor(m.get("PopupBorder") or (QColor(255, 255, 255, 40) if card.lightnessF() <= 0.55 else QColor(0, 0, 0, 38)))
    muted = QColor(ink)
    muted.setAlpha(140)
    return card, ink, hover, hover_ink, line, muted


def _snug(widget):
    """How roomy to make the items: as drawn for Ubuntu's 11pt font, in step with this desktop's own (Windows' 9pt
    Segoe UI is smaller, so the same pixels of room would leave its menus spread out)."""
    return max(0.7, min(1.4, QFontMetrics(widget.font()).height() / 19))


def _plain(text):
    """A menu's words without the & that marks its keyboard letter (&& is a real &)."""
    return str(text or "").replace("&&", "\x00").replace("&", "").replace("\x00", "&")


class VmlMenu(QMenu):
    """A drop-down or right-click menu, drawn as a card."""

    def __init__(self, *args):
        super().__init__(*args)
        self.menu_theme = None
        self.setWindowFlags(self.windowFlags() | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setContentsMargins(SHADOW, SHADOW - 4, SHADOW, SHADOW + 2)
        # the sizes the items are laid out at (Qt places them; paintEvent below draws them)
        k = _snug(self)
        pad = max(3, round((ITEM_H - 18) // 2 * k))
        self.setStyleSheet(f"QMenu {{ background: transparent; border: none; padding: {round(6 * k)}px {SIDE}px; }}"
                           f" QMenu::item {{ padding: {pad}px {round((ARROW_W + 30) * k)}px {pad}px {TICK_W}px; }}"
                           f" QMenu::separator {{ height: {max(7, round(9 * k))}px; }}")

    def theme_of(self):
        """This menu's MenuTheme, else the one of the menu or bar it hangs from."""
        w = self
        while w is not None:
            t = getattr(w, "menu_theme", None)
            if t:
                return t
            w = w.parent() if hasattr(w, "parent") else None
        return None

    def addMenu(self, *args):                            # (a sub-menu made by addMenu("words") is ours too)
        if args and isinstance(args[0], str):
            sub = VmlMenu(args[0], self)
            super().addMenu(sub)
            return sub
        return super().addMenu(*args)

    # (Where Qt puts the menu is left alone: the card hangs a little below and to the right of the item it opens
    # from, a natural cascade. Moving it back after it shows only works on some desktops (not Wayland), and on
    # Windows it lifted every sub-menu over the one before and the drop-downs over the bar.)

    def paintEvent(self, e):
        t = _theme()
        card_c, ink, hover, hover_ink, line, muted = _colours(self.theme_of(), t.dark)
        g = QPainter(self)
        g.setRenderHint(QPainter.Antialiasing)
        card = QRectF(self.rect()).adjusted(SHADOW, SHADOW - 4, -SHADOW, -(SHADOW + 2))
        r = float(t.popup_radius)
        for k in range(SHADOW, 0, -2):                   # a soft shadow, a little below
            spread = QRectF(card).adjusted(-k * 0.5, -k * 0.25 + 2, k * 0.5, k * 0.6 + 2)
            g.setPen(Qt.NoPen)
            g.setBrush(QColor(0, 0, 0, max(1, int(6 * (1 - k / SHADOW))) + 1))
            g.drawRoundedRect(spread, r + k * 0.5, r + k * 0.5)
        path = QPainterPath()
        path.addRoundedRect(card, r, r)
        g.fillPath(path, card_c)
        g.setPen(QPen(line, 1))
        g.setBrush(Qt.NoBrush)
        g.drawPath(path)

        fm = QFontMetrics(self.font())
        active = self.activeAction()
        for act in self.actions():
            if not act.isVisible():
                continue
            rect = self.actionGeometry(act)
            if rect.isEmpty():
                continue
            if act.isSeparator():
                y = rect.center().y()
                rule = QColor(ink)
                rule.setAlpha(36)                        # (quieter than the edge: it only divides)
                g.setPen(QPen(rule, 1))
                g.drawLine(int(card.left()) + 12, y, int(card.right()) - 12, y)
                continue
            box = QRectF(rect).adjusted(SIDE, 1, -SIDE, -1)
            on = act is active and act.isEnabled()
            if on:
                g.setPen(Qt.NoPen)
                g.setBrush(hover)
                g.drawRoundedRect(box, 6, 6)
            words = hover_ink if on else (ink if act.isEnabled() else muted)
            g.setPen(words)
            if act.isCheckable() and act.isChecked():    # a tick
                cx, cy = rect.left() + SIDE + TICK_W // 2, rect.center().y()
                pen = QPen(words, 1.8)
                pen.setCapStyle(Qt.RoundCap)
                pen.setJoinStyle(Qt.RoundJoin)
                g.setPen(pen)
                g.drawPolyline([QPoint(cx - 5, cy), QPoint(cx - 1, cy + 4), QPoint(cx + 6, cy - 4)])
                g.setPen(words)
            text_rect = QRect(rect.left() + SIDE + TICK_W, rect.top(), rect.width() - SIDE * 2 - TICK_W - ARROW_W, rect.height())
            g.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, _plain(act.text()))
            keys = act.shortcut().toString(QKeySequence.NativeText) if not act.shortcut().isEmpty() else ""
            if keys:
                quiet = QColor(words)
                quiet.setAlpha(150)
                g.setPen(quiet)
                g.drawText(text_rect.adjusted(0, 0, ARROW_W - 8, 0), Qt.AlignVCenter | Qt.AlignRight, keys)
                g.setPen(words)
            if act.menu() is not None:                   # a sub-menu: an arrow
                ax, ay = rect.right() - SIDE - 12, rect.center().y()
                pen = QPen(words, 1.6)
                pen.setCapStyle(Qt.RoundCap)
                g.setPen(pen)
                g.drawPolyline([QPoint(ax - 2, ay - 4), QPoint(ax + 2, ay), QPoint(ax - 2, ay + 4)])
        g.end()


class VmlMenuBar(QMenuBar):
    """The bar: its items with a rounded highlight under the pointer, in its MenuTheme's colours or the window's."""

    def __init__(self, *args):
        super().__init__(*args)
        self.menu_theme = None
        self.setNativeMenuBar(False)
        k = _snug(self)
        self.setStyleSheet("QMenuBar { background: transparent; border: none; padding: 2px 4px; }"
                           f" QMenuBar::item {{ padding: {round(6 * k)}px {round(12 * k)}px; margin: 2px 1px; }}")

    def addMenu(self, *args):                            # (menus made by addMenu("File") are ours too)
        if args and isinstance(args[0], str):
            sub = VmlMenu(args[0], self)
            super().addMenu(sub)
            return sub
        return super().addMenu(*args)

    def set_height(self, h):
        self.setMinimumHeight(int(h) if h else 0)

    def paintEvent(self, e):
        m = self.menu_theme or {}
        g = QPainter(self)
        g.setRenderHint(QPainter.Antialiasing)
        from .theme import theme
        t = theme()
        bg = QColor(m["Background"]) if m.get("Background") else QColor(t.surface)   # no theme: the desktop's surface,
        g.fillRect(self.rect(), bg)                                                  # with a line under it
        if not m.get("Background"):
            g.setPen(QColor(t.line))
            g.drawLine(0, self.height() - 1, self.width(), self.height() - 1)
        ink = QColor(m.get("Foreground") or ("#111827" if bg.lightnessF() > 0.55 else "#F3F4F6"))
        if m.get("HoverBackground"):
            hover, hover_ink = QColor(m["HoverBackground"]), QColor(m.get("HoverForeground") or ink)
        else:
            hover = QColor(ink)
            hover.setAlpha(30 if bg.lightnessF() > 0.55 else 40)
            hover_ink = ink
        active = self.activeAction()
        for act in self.actions():
            if not act.isVisible():
                continue
            rect = self.actionGeometry(act)
            on = act is active
            if on:
                g.setPen(Qt.NoPen)
                g.setBrush(hover)
                g.drawRoundedRect(QRectF(rect).adjusted(1, 3, -1, -3), 6, 6)
            g.setPen(hover_ink if on else (ink if act.isEnabled() else QColor(ink.red(), ink.green(), ink.blue(), 120)))
            g.drawText(rect, Qt.AlignCenter, _plain(act.text()))
        g.end()
