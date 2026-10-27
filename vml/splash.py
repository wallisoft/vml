"""A small branded splash for the designer's start-up, so the first few seconds aren't a black gap.

Shown the moment the app exists, closed when the designer window is ready - but kept up for a short floor
(default 3s) so it reads as a loading screen rather than a flicker. The progress bar is indeterminate (the
heavy load blocks the event loop, so there's no honest percentage); it animates in whatever time the loop
is free, and the floor gives it room to breathe.
"""
import time

from PySide6.QtCore import Qt, QElapsedTimer, QEventLoop
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath
from PySide6.QtWidgets import QApplication, QLabel, QProgressBar, QVBoxLayout, QWidget

BG = "#1E3A8A"          # the designer's blue
BG2 = "#172554"
FG = "#FFFFFF"
SUB = "#BFDBFE"
BAR = "#60A5FA"


class Splash(QWidget):
    def __init__(self, title="Visualised"):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.SplashScreen)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
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
        self.bar.setRange(0, 0)                 # indeterminate
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

        self._clock = QElapsedTimer(); self._clock.start()
        screen = QApplication.primaryScreen()
        if screen:
            c = screen.availableGeometry().center()
            self.move(c.x() - self.width() // 2, c.y() - self.height() // 2)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width(), self.height(), 16, 16)
        p.fillPath(path, QColor(BG))
        p.end()

    def say(self, text):
        self.status.setText(text)
        QApplication.processEvents()

    def done(self, window, floor_ms=3000):
        """Keep the splash up until the floor, letting the bar animate in any free event-loop time, then show
        the window and go. Never less than a brief tail so the finish feels smooth even if load ate the floor."""
        while self._clock.elapsed() < floor_ms:
            QApplication.processEvents(QEventLoop.AllEvents, 30)
            time.sleep(0.02)
        tail = QElapsedTimer(); tail.start()
        while tail.elapsed() < 350:                     # a short animated breath at the end
            QApplication.processEvents(QEventLoop.AllEvents, 30)
            time.sleep(0.02)
        if window is not None:
            window.show(); window.raise_(); window.activateWindow()
        self.close()
        self.deleteLater()
