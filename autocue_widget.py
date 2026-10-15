"""Continuous, paint-based note autocue. No audio processing or AI changes."""
from bisect import bisect_right
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QFont
from PySide6.QtWidgets import QWidget


class AutocueWidget(QWidget):
    seekRequested = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.events = []
        self.position = 0.0
        self.duration = 0.0
        self.follow = True
        self.manual_offset = 0.0
        self.pixels_per_second = 75.0
        self.setMinimumHeight(175)
        self.setMouseTracking(True)
        self._drag_x = None

    def set_events(self, events, duration=0):
        self.events = sorted((float(t), str(n)) for t, n in events)
        self.duration = max(float(duration), self.events[-1][0] if self.events else 0)
        self.update()

    def set_position(self, seconds):
        self.position = max(0.0, float(seconds))
        self.update()

    def set_follow(self, follow):
        self.follow = bool(follow)
        if not self.follow:
            self.manual_offset = self._offset()
        self.update()

    def _offset(self):
        return max(0.0, self.position * self.pixels_per_second - self.width() * .35) if self.follow else self.manual_offset

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(self.rect(), QColor('#101f2c'))
        if not self.events:
            p.setPen(QColor('#829bad'))
            p.drawText(self.rect(), Qt.AlignCenter, 'Load and analyze a song to see the autocue')
            return
        px = self.pixels_per_second
        offset = self._offset()
        left, right = offset / px, (offset + w) / px
        p.setFont(QFont('Arial', 9))
        first_bar = max(0, int(left / 2))
        for bar in range(first_bar, int(right / 2) + 2):
            x = round(bar * 2 * px - offset)
            p.setPen(QPen(QColor('#354e60'), 1, Qt.DashLine))
            p.drawLine(x, 28, x, h - 16)
            p.setPen(QColor('#829bad'))
            p.drawText(x + 5, 20, str(bar + 1))
        times = [e[0] for e in self.events]
        start_i = max(0, bisect_right(times, left) - 1)
        p.setFont(QFont('Arial', 17, QFont.Bold))
        for i in range(start_i, len(self.events)):
            start, note = self.events[i]
            if start > right:
                break
            end = self.events[i+1][0] if i+1 < len(self.events) else max(self.duration, right)
            if end <= left:
                continue
            x1, x2 = max(0, round(start * px - offset)), min(w, round(end * px - offset))
            if x2 <= x1:
                continue
            active = start <= self.position < end
            past = end <= self.position
            bg = QColor('#285b8a' if active else '#183449' if past else '#214c6a')
            border = QColor('#7bd6ff' if active else '#345f7c')
            p.setPen(QPen(border, 1))
            p.setBrush(bg)
            p.drawRoundedRect(x1 + 1, 62, max(1, x2 - x1 - 3), 74, 5, 5)
            p.setPen(QColor('#f1faff' if not past else '#71899a'))
            if x2-x1 >= 24:
                p.drawText(x1+4, 62, max(1,x2-x1-8), 74, Qt.AlignCenter, note)
        cursor_x = round(self.position * px - offset)
        p.setPen(QPen(QColor('#7bd6ff'), 2))
        p.drawLine(cursor_x, 28, cursor_x, h-10)
        p.setPen(QColor('#7bd6ff'))
        p.drawText(max(0,cursor_x-14), 20, '▼')

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_x = event.position().x()
            self._drag_origin = self._offset()
            self.set_follow(False)

    def mouseMoveEvent(self, event):
        if self._drag_x is not None:
            self.manual_offset = max(0, self._drag_origin + self._drag_x - event.position().x())
            self.update()

    def mouseReleaseEvent(self, event):
        if self._drag_x is not None:
            if abs(event.position().x() - self._drag_x) < 5:
                seconds = (self.manual_offset + event.position().x()) / self.pixels_per_second
                self.seekRequested.emit(int(max(0, min(self.duration, seconds)) * 1000))
            self._drag_x = None
