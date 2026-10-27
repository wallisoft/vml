"""A small branded splash for the designer's start-up, so the first few seconds aren't a black gap.

Opaque (so the compositor paints it at once, Wayland included), shown and forced to screen *before* the
heavy load blocks the event loop, and held for a floor (default 3s, measured from that first paint) so it
reads as a loading screen rather than a flicker. The bar is indeterminate - the load blocks the loop, so
there's no honest percentage; it animates in whatever time the loop is free.
"""
import time

from PySide6.QtCore import Qt, QElapsedTimer, QEventLoop
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import QApplication, QLabel, QProgressBar, QVBoxLayout, QWidget

BG = "#1E3A8A"
BG2 = "#172554"
FG = "#FFFFFF"
SUB = "#BFDBFE"
BAR = "#60A5FA"


class Splash(QWidget):
    def __init__(self, title="Visualised"):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.SplashScreen)
        self.setFixedSize(440, 240)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(40, 36, 40, 32)
        lay.setSpacing(10)

        name = QLabel("Visualised")
        f = QFont(); f.setPointSize(32); f.setBold(True); name.setFont(f)
        name.setStyleSheet(f"color:{FG}; background:transparent")

        sub = QLabel("Design desktop, web and phone apps")
        sub.setStyleSheet(f"color:{SUB}; font-size:13px; background:transparent")

        self.status = QLabel("Starting…")
        self.status.setStyleSheet(f"color:{SUB}; font-size:12px; background:transparent")

        self.bar = QProgressBar()
        self.bar.setRange(0, 0)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(6)
        self.bar.setStyleSheet(
            f"QProgressBar{{background:{BG2}; border:0; border-radius:3px}}"
            f"QProgressBar::chunk{{background:{BAR}; border-radius:3px}}")

        ttl = QLabel(title)
        ttl.setStyleSheet("color:#93C5FD; font-size:11px; background:transparent")

        lay.addStretch(1)
        lay.addWidget(name)
        lay.addWidget(sub)
        lay.addStretch(1)
        lay.addWidget(self.status)
        lay.addWidget(self.bar)
        lay.addWidget(ttl)

        self._clock = QElapsedTimer()
        scr = QApplication.primaryScreen()
        if scr:
            c = scr.availableGeometry().center()
            self.move(c.x() - self.width() // 2, c.y() - self.height() // 2)

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(BG))
        p.end()

    def start(self, status="Starting…"):
        """Put the splash on screen and painted NOW, before the caller's heavy load blocks the event loop."""
        self.status.setText(status)
        self.show()
        self.raise_()
        self._clock.start()
        for _ in range(3):                      # a few passes so the compositor actually maps + paints it
            QApplication.processEvents(QEventLoop.AllEvents, 20)
        self.repaint()

    def say(self, text):
        self.status.setText(text)
        QApplication.processEvents()

    def done(self, window, floor_ms=3000):
        """Hold the splash to the floor (from first paint), letting the bar animate, then show the window."""
        while self._clock.isValid() and self._clock.elapsed() < floor_ms:
            QApplication.processEvents(QEventLoop.AllEvents, 30)
            time.sleep(0.02)
        if window is not None:
            window.show(); window.raise_(); window.activateWindow()
        self.close()
        self.deleteLater()
