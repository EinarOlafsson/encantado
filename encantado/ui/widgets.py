"""Custom controls: rotary knob, level meter, fader, small helpers."""
from __future__ import annotations

import math

from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import (QBrush, QColor, QFont, QLinearGradient, QPainter, QPen)
from PyQt6.QtWidgets import QLabel, QSizePolicy, QWidget

from ..dsp.params import Param
from . import theme as T


class Knob(QWidget):
    """Rotary control. Drag vertically, Shift for fine, double-click resets."""

    valueChanged = pyqtSignal(float)

    ARC_START = 225.0
    ARC_SPAN = -270.0

    def __init__(self, param: Param, value: float | None = None,
                 accent: str | None = None, parent=None):
        super().__init__(parent)
        self.param = param
        self._value = param.default if value is None else float(value)
        self.accent = QColor(accent or T.ACCENT)
        self._drag_y = None
        self._drag_v = 0.0
        self._hover = False
        self.setFixedSize(52, 62)
        self.setCursor(Qt.CursorShape.SizeVerCursor)
        self.setMouseTracking(True)
        self.setToolTip(f"{param.label} — {param.format(self._value)}")

    # -- value ---------------------------------------------------------------
    def value(self) -> float:
        return self._value

    def setValue(self, v: float, emit: bool = True) -> None:
        v = max(self.param.lo, min(self.param.hi, float(v)))
        if abs(v - self._value) < 1e-9:
            return
        self._value = v
        self.setToolTip(f"{self.param.label} — {self.param.format(v)}")
        self.update()
        if emit:
            self.valueChanged.emit(v)

    def _norm(self) -> float:
        return self.param.to_norm(self._value)

    # -- interaction ---------------------------------------------------------
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_y = e.position().y()
            self._drag_v = self._norm()

    def mouseMoveEvent(self, e):
        if self._drag_y is None:
            return
        dy = self._drag_y - e.position().y()
        scale = 0.0016 if e.modifiers() & Qt.KeyboardModifier.ShiftModifier else 0.007
        self.setValue(self.param.from_norm(self._drag_v + dy * scale))

    def mouseReleaseEvent(self, e):
        self._drag_y = None

    def mouseDoubleClickEvent(self, e):
        self.setValue(self.param.default)

    def wheelEvent(self, e):
        step = 0.01 if e.modifiers() & Qt.KeyboardModifier.ShiftModifier else 0.04
        d = step * (1 if e.angleDelta().y() > 0 else -1)
        self.setValue(self.param.from_norm(self._norm() + d))
        e.accept()

    def enterEvent(self, e):
        self._hover = True
        self.update()

    def leaveEvent(self, e):
        self._hover = False
        self.update()

    # -- paint ---------------------------------------------------------------
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        r = 17.0
        cx, cy = w / 2.0, 22.0
        box = QRectF(cx - r, cy - r, r * 2, r * 2)

        p.setPen(QPen(QColor(T.BG_INPUT), 6, cap=Qt.PenCapStyle.RoundCap))
        p.drawArc(box, int(self.ARC_START * 16), int(self.ARC_SPAN * 16))

        n = self._norm()
        if self.param.lo < 0 < self.param.hi:          # bipolar: fill from centre
            centre = self.param.to_norm(0.0)
            start = self.ARC_START + self.ARC_SPAN * centre
            span = self.ARC_SPAN * (n - centre)
        else:
            start, span = self.ARC_START, self.ARC_SPAN * n
        col = QColor(self.accent)
        if self._hover:
            col = col.lighter(118)
        p.setPen(QPen(col, 6, cap=Qt.PenCapStyle.RoundCap))
        if abs(span) > 0.4:
            p.drawArc(box, int(start * 16), int(span * 16))

        p.setBrush(QBrush(QColor(T.BG_PANEL_2)))
        p.setPen(QPen(QColor(T.BORDER), 1))
        p.drawEllipse(QPointF(cx, cy), r - 5.5, r - 5.5)

        ang = math.radians(self.ARC_START + self.ARC_SPAN * n)
        p.setPen(QPen(col, 2.2, cap=Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(cx + math.cos(ang) * 4.5, cy - math.sin(ang) * 4.5),
                   QPointF(cx + math.cos(ang) * (r - 7), cy - math.sin(ang) * (r - 7)))

        f = QFont(); f.setPointSizeF(7.4)
        p.setFont(f)
        p.setPen(QColor(T.TEXT_DIM))
        p.drawText(QRectF(0, 41, w, 10), Qt.AlignmentFlag.AlignCenter, self.param.label)
        f.setPointSizeF(7.2); f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(T.TEXT if self._hover else T.TEXT_FAINT))
        p.drawText(QRectF(0, 51, w, 10), Qt.AlignmentFlag.AlignCenter,
                   self.param.format(self._value))
        p.end()


class LevelMeter(QWidget):
    """Peak meter with a slow-falling hold line."""

    def __init__(self, orientation=Qt.Orientation.Vertical, parent=None):
        super().__init__(parent)
        self.orientation = orientation
        self.level = [0.0, 0.0]
        self.peak_hold = [0.0, 0.0]
        self._decay = 0.86
        if orientation == Qt.Orientation.Vertical:
            self.setFixedWidth(13)
            self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        else:
            self.setFixedHeight(9)
            self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_level(self, left: float, right: float | None = None) -> None:
        vals = [float(left), float(right if right is not None else left)]
        for i, v in enumerate(vals):
            self.level[i] = max(v, self.level[i] * self._decay)
            self.peak_hold[i] = max(v, self.peak_hold[i] * 0.985)
        self.update()

    @staticmethod
    def _norm_db(v: float) -> float:
        if v <= 1e-5:
            return 0.0
        db = 20.0 * math.log10(min(v, 1.6))
        return max(0.0, min(1.0, (db + 54.0) / 54.0))

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(T.BG_INPUT))
        p.drawRoundedRect(QRectF(0, 0, w, h), 3, 3)

        vertical = self.orientation == Qt.Orientation.Vertical
        n = 2
        for i in range(n):
            frac = self._norm_db(self.level[i])
            hold = self._norm_db(self.peak_hold[i])
            if vertical:
                cw = (w - 3) / n
                x = 1.5 + i * cw
                grad = QLinearGradient(0, h, 0, 0)
                grad.setColorAt(0.0, QColor(T.GREEN))
                grad.setColorAt(0.72, QColor(T.ACCENT))
                grad.setColorAt(0.9, QColor(T.ACCENT_4))
                grad.setColorAt(1.0, QColor(T.ACCENT_2))
                p.setBrush(QBrush(grad))
                bh = frac * (h - 3)
                p.drawRoundedRect(QRectF(x, h - 1.5 - bh, cw - 1, bh), 1.5, 1.5)
                if hold > 0.01:
                    p.setBrush(QColor(T.TEXT))
                    p.drawRect(QRectF(x, h - 1.5 - hold * (h - 3), cw - 1, 1.3))
            else:
                ch = (h - 3) / n
                y = 1.5 + i * ch
                grad = QLinearGradient(0, 0, w, 0)
                grad.setColorAt(0.0, QColor(T.GREEN))
                grad.setColorAt(0.72, QColor(T.ACCENT))
                grad.setColorAt(0.9, QColor(T.ACCENT_4))
                grad.setColorAt(1.0, QColor(T.ACCENT_2))
                p.setBrush(QBrush(grad))
                p.drawRoundedRect(QRectF(1.5, y, frac * (w - 3), ch - 1), 1.5, 1.5)
        p.end()


class Fader(QWidget):
    """Vertical mixer fader in dB."""

    valueChanged = pyqtSignal(float)

    def __init__(self, value: float = 0.8, parent=None):
        super().__init__(parent)
        self._value = float(value)
        self.setFixedWidth(26)
        self.setMinimumHeight(110)
        self.setCursor(Qt.CursorShape.SizeVerCursor)
        self._drag = None

    def value(self) -> float:
        return self._value

    def setValue(self, v: float, emit: bool = True) -> None:
        v = max(0.0, min(1.5, float(v)))
        if abs(v - self._value) < 1e-9:
            return
        self._value = v
        self.update()
        if emit:
            self.valueChanged.emit(v)

    def _frac(self) -> float:
        return (self._value / 1.5) ** 0.5

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag = (e.position().y(), self._frac())

    def mouseMoveEvent(self, e):
        if self._drag is None:
            return
        y0, f0 = self._drag
        scale = 1.0 / max(self.height() - 22, 1)
        fine = 0.25 if e.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1.0
        f = max(0.0, min(1.0, f0 + (y0 - e.position().y()) * scale * fine))
        self.setValue((f ** 2) * 1.5)

    def mouseReleaseEvent(self, e):
        self._drag = None

    def mouseDoubleClickEvent(self, e):
        self.setValue(0.8)

    def wheelEvent(self, e):
        d = 0.02 * (1 if e.angleDelta().y() > 0 else -1)
        self.setValue(((max(0.0, min(1.0, self._frac() + d))) ** 2) * 1.5)
        e.accept()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        cx = w / 2
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(T.BG_INPUT))
        p.drawRoundedRect(QRectF(cx - 2.5, 8, 5, h - 16), 2.5, 2.5)
        f = self._frac()
        y = 8 + (1 - f) * (h - 16)
        p.setBrush(QColor(T.ACCENT))
        p.drawRoundedRect(QRectF(cx - 2.5, y, 5, h - 8 - y), 2.5, 2.5)
        # cap
        p.setBrush(QColor("#2a3446"))
        p.setPen(QPen(QColor(T.BORDER_LIT), 1))
        p.drawRoundedRect(QRectF(cx - 10, y - 6, 20, 12), 3, 3)
        p.setPen(QPen(QColor(T.ACCENT), 1.6))
        p.drawLine(QPointF(cx - 6, y), QPointF(cx + 6, y))
        p.end()


class ColorDot(QLabel):
    def __init__(self, color: str, size: int = 9, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.set_color(color)

    def set_color(self, color: str) -> None:
        self.setStyleSheet(f"background:{color}; border-radius:{self.width()//2}px;")


def title_label(text: str) -> QLabel:
    lb = QLabel(text)
    lb.setObjectName("Title")
    return lb
