"""Arrangement playlist: patterns laid out as clips on a timeline."""
from __future__ import annotations

from PyQt6.QtCore import QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import (QComboBox, QHBoxLayout, QLabel, QPushButton,
                             QScrollArea, QSizePolicy, QVBoxLayout, QWidget)

from ..core.project import STEPS_PER_BAR, Clip, Project
from . import theme as T

LANE_H = 30
EDGE = 6
PATTERN_COLORS = ["#4db8ff", "#8b7cff", "#2fe0cf", "#ffc94d", "#ff5c7a",
                  "#5ddb8a", "#ff9f45", "#d47cff"]


class ArrangeGrid(QWidget):
    changed = pyqtSignal()
    seekRequested = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.project: Project | None = None
        self.px_per_bar = 46.0
        self.playhead = -1
        self.paint_pattern = ""
        self.min_bars = 96
        self._drag = None
        self._erase = False
        self._hover = None
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    # -- geometry ------------------------------------------------------------
    @property
    def px_per_step(self) -> float:
        return self.px_per_bar / STEPS_PER_BAR

    def n_bars(self) -> int:
        if self.project is None:
            return self.min_bars
        used = self.project.arrangement_length // STEPS_PER_BAR
        return max(self.min_bars, used + 16)

    def n_lanes(self) -> int:
        return self.project.n_lanes if self.project else 8

    def sizeHint(self) -> QSize:
        return QSize(int(self.n_bars() * self.px_per_bar),
                     self.n_lanes() * LANE_H)

    def refresh(self) -> None:
        self.setFixedSize(self.sizeHint())
        self.update()

    def _lane(self, y) -> int:
        return max(0, min(self.n_lanes() - 1, int(y // LANE_H)))

    def _step(self, x) -> int:
        return max(0, int(x / self.px_per_step))

    def _snap_bar(self, step: int) -> int:
        return (step // STEPS_PER_BAR) * STEPS_PER_BAR

    def _clip_at(self, pos):
        if self.project is None:
            return None, False
        lane, step = self._lane(pos.y()), self._step(pos.x())
        for clip in reversed(self.project.arrangement):
            if clip.lane == lane and clip.start <= step < clip.end:
                right = clip.end * self.px_per_step
                return clip, abs(pos.x() - right) <= EDGE
        return None, False

    # -- interaction ---------------------------------------------------------
    def mousePressEvent(self, e):
        if self.project is None:
            return
        clip, on_edge = self._clip_at(e.position())
        if e.button() == Qt.MouseButton.RightButton:
            self._erase = True
            if clip:
                self.project.arrangement.remove(clip)
                self.refresh()
                self.changed.emit()
            return
        if clip is None:
            pid = self.paint_pattern or (self.project.patterns[0].id
                                         if self.project.patterns else "")
            pat = self.project.pattern(pid)
            if pat is None:
                return
            start = self._snap_bar(self._step(e.position().x()))
            clip = Clip(pid, start, max(pat.length, STEPS_PER_BAR),
                        self._lane(e.position().y()))
            self.project.arrangement.append(clip)
            self._drag = ("move", clip, e.position(), clip.start, clip.lane, clip.length)
        elif on_edge:
            self._drag = ("resize", clip, e.position(), clip.start, clip.lane, clip.length)
        else:
            self._drag = ("move", clip, e.position(), clip.start, clip.lane, clip.length)
        self.refresh()
        self.changed.emit()

    def mouseMoveEvent(self, e):
        if self._erase:
            clip, _ = self._clip_at(e.position())
            if clip and self.project:
                self.project.arrangement.remove(clip)
                self.refresh()
                self.changed.emit()
            return
        if self._drag is None:
            clip, on_edge = self._clip_at(e.position())
            self.setCursor(Qt.CursorShape.SizeHorCursor if on_edge
                           else Qt.CursorShape.ArrowCursor)
            h = (self._lane(e.position().y()),
                 self._snap_bar(self._step(e.position().x())))
            if h != self._hover:
                self._hover = h
                self.update()
            return
        kind, clip, origin, s0, l0, len0 = self._drag
        if kind == "move":
            dsteps = int(round((e.position().x() - origin.x()) / self.px_per_step))
            clip.start = max(0, self._snap_bar(s0 + dsteps))
            clip.lane = self._lane(e.position().y())
        else:
            end = self._step(e.position().x())
            end = max(clip.start + STEPS_PER_BAR,
                      ((end + STEPS_PER_BAR - 1) // STEPS_PER_BAR) * STEPS_PER_BAR)
            clip.length = end - clip.start
        self.refresh()
        self.changed.emit()

    def mouseReleaseEvent(self, e):
        self._drag = None
        self._erase = False

    def leaveEvent(self, e):
        self._hover = None
        self.update()

    # -- paint ---------------------------------------------------------------
    def paintEvent(self, _):
        p = QPainter(self)
        w, h = self.width(), self.height()
        p.fillRect(0, 0, w, h, QColor(T.BG_PANEL))
        ppb = self.px_per_bar
        bars = self.n_bars()

        for b in range(bars):
            if (b // 4) % 2:
                p.fillRect(QRectF(b * ppb, 0, ppb, h), QColor(255, 255, 255, 5))
        for lane in range(self.n_lanes() + 1):
            p.setPen(QPen(QColor(T.GRID_LINE), 1))
            p.drawLine(0, lane * LANE_H, w, lane * LANE_H)
        for b in range(bars + 1):
            if b % 4 == 0:
                p.setPen(QPen(QColor(T.GRID_BAR), 1))
            else:
                p.setPen(QPen(QColor(T.GRID_LINE), 1))
            p.drawLine(int(b * ppb), 0, int(b * ppb), h)

        if self.project:
            order = {pt.id: i for i, pt in enumerate(self.project.patterns)}
            f = QFont(); f.setPointSizeF(7.6); f.setBold(True)
            p.setFont(f)
            for clip in self.project.arrangement:
                pat = self.project.pattern(clip.pattern_id)
                if pat is None:
                    continue
                col = QColor(PATTERN_COLORS[order.get(clip.pattern_id, 0)
                                            % len(PATTERN_COLORS)])
                x = clip.start * self.px_per_step
                cw = clip.length * self.px_per_step
                rect = QRectF(x + 1, clip.lane * LANE_H + 2, cw - 2, LANE_H - 4)
                body = QColor(col); body.setAlpha(120)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(body)
                p.drawRoundedRect(rect, 3, 3)
                p.setPen(QPen(col, 1.2))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRoundedRect(rect, 3, 3)
                # repeat markers where the pattern loops inside a longer clip
                if pat.length and clip.length > pat.length:
                    p.setPen(QPen(QColor(255, 255, 255, 70), 1, Qt.PenStyle.DashLine))
                    r = pat.length
                    while r < clip.length:
                        rx = (clip.start + r) * self.px_per_step
                        p.drawLine(QRectF(rx, rect.top(), 0, rect.height()).topLeft(),
                                   QRectF(rx, rect.top(), 0, rect.height()).bottomLeft())
                        r += pat.length
                if cw > 26:
                    p.setPen(QColor(T.TEXT))
                    p.drawText(rect.adjusted(5, 0, -3, 0),
                               Qt.AlignmentFlag.AlignVCenter, pat.name)

        if self._hover and self._drag is None:
            lane, step = self._hover
            pat = self.project.pattern(self.paint_pattern) if self.project else None
            ln = max(pat.length, STEPS_PER_BAR) if pat else STEPS_PER_BAR
            p.setPen(QPen(QColor(T.ACCENT), 1, Qt.PenStyle.DotLine))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(QRectF(step * self.px_per_step + 1, lane * LANE_H + 2,
                                     ln * self.px_per_step - 2, LANE_H - 4), 3, 3)

        if self.playhead >= 0:
            x = self.playhead * self.px_per_step
            p.setPen(QPen(QColor(T.PLAYHEAD), 2))
            p.drawLine(int(x), 0, int(x), h)
        p.end()


class ArrangeRuler(QWidget):
    seekRequested = pyqtSignal(int)

    def __init__(self, grid: ArrangeGrid, parent=None):
        super().__init__(parent)
        self.grid = grid
        self.setFixedHeight(20)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def sizeHint(self) -> QSize:
        return QSize(int(self.grid.n_bars() * self.grid.px_per_bar), 20)

    def refresh(self) -> None:
        self.setFixedSize(self.sizeHint())
        self.update()

    def mousePressEvent(self, e):
        self.seekRequested.emit(int(e.position().x() / self.grid.px_per_step))

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(T.BG_PANEL_2))
        ppb = self.grid.px_per_bar
        f = QFont(); f.setPointSizeF(7.6); f.setBold(True)
        p.setFont(f)
        every = 4 if ppb < 30 else 1
        for b in range(self.grid.n_bars()):
            x = b * ppb
            if b % 4 == 0:
                p.setPen(QPen(QColor(T.GRID_BAR), 1))
                p.drawLine(int(x), 11, int(x), 20)
                if b % every == 0:
                    p.setPen(QColor(T.TEXT_DIM))
                    p.drawText(int(x) + 3, 10, str(b + 1))
        if self.grid.playhead >= 0:
            x = self.grid.playhead * self.grid.px_per_step
            p.setPen(QPen(QColor(T.PLAYHEAD), 2))
            p.drawLine(int(x), 0, int(x), 20)
        p.end()


class Playlist(QWidget):
    changed = pyqtSignal()
    seekRequested = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.project: Project | None = None
        self.grid = ArrangeGrid()
        self.ruler = ArrangeRuler(self.grid)
        self.grid.changed.connect(self.changed)
        self.ruler.seekRequested.connect(self.seekRequested)

        bar = QHBoxLayout()
        bar.setContentsMargins(8, 6, 8, 6)
        bar.setSpacing(8)
        title = QLabel("Playlist")
        title.setObjectName("Heading")
        bar.addWidget(title)
        bar.addSpacing(12)
        bar.addWidget(QLabel("Paint"))
        self.pat_box = QComboBox()
        self.pat_box.setMinimumWidth(140)
        self.pat_box.currentIndexChanged.connect(self._pick)
        bar.addWidget(self.pat_box)

        self.zoom_out = QPushButton("−")
        self.zoom_in = QPushButton("+")
        for b in (self.zoom_out, self.zoom_in):
            b.setObjectName("Mini")
            b.setFixedSize(26, 24)
        self.zoom_out.clicked.connect(lambda: self.set_zoom(self.grid.px_per_bar / 1.3))
        self.zoom_in.clicked.connect(lambda: self.set_zoom(self.grid.px_per_bar * 1.3))
        bar.addWidget(self.zoom_out)
        bar.addWidget(self.zoom_in)

        hint = QLabel("click to place · drag to move · edge to repeat · right-click erase")
        hint.setObjectName("Faint")
        bar.addStretch(1)
        bar.addWidget(hint)

        self.area = QScrollArea()
        self.area.setWidgetResizable(False)
        host = QWidget()
        self.host = host
        vl = QVBoxLayout(host)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(0)
        vl.addWidget(self.ruler)
        vl.addWidget(self.grid)
        vl.addStretch(1)
        self.area.setWidget(host)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addLayout(bar)
        lay.addWidget(self.area, 1)

    def set_zoom(self, ppb: float) -> None:
        self.grid.px_per_bar = max(14.0, min(220.0, float(ppb)))
        self.refresh()

    def _pick(self) -> None:
        self.grid.paint_pattern = self.pat_box.currentData() or ""

    def set_project(self, project: Project) -> None:
        self.project = project
        self.grid.project = project
        self.sync_patterns()
        self.refresh()

    def sync_patterns(self) -> None:
        if self.project is None:
            return
        cur = self.grid.paint_pattern
        self.pat_box.blockSignals(True)
        self.pat_box.clear()
        for pat in self.project.patterns:
            self.pat_box.addItem(pat.name, pat.id)
        idx = self.pat_box.findData(cur)
        self.pat_box.setCurrentIndex(idx if idx >= 0 else 0)
        self.pat_box.blockSignals(False)
        self._pick()

    def refresh(self) -> None:
        self.grid.refresh()
        self.ruler.refresh()
        self.host.adjustSize()

    def set_playhead(self, step: int) -> None:
        if step != self.grid.playhead:
            self.grid.playhead = step
            self.grid.update()
            self.ruler.update()
