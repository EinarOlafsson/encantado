"""Channel rack: the step sequencer, plus per-channel headers."""
from __future__ import annotations

from PyQt6.QtCore import QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import (QAbstractScrollArea, QHBoxLayout, QInputDialog,
                             QLabel, QMenu, QPushButton, QScrollArea,
                             QSizePolicy, QVBoxLayout, QWidget)

from ..core.project import Project
from . import theme as T
from .widgets import ColorDot, LevelMeter

ROW_H = 32
HEADER_W = 236
MIN_STEP_W = 13
MAX_STEP_W = 46


class StepGrid(QWidget):
    """Paints every channel's steps for the current pattern."""

    stepToggled = pyqtSignal(str, int)
    velocityChanged = pyqtSignal(str, int, float)
    channelSelected = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.project: Project | None = None
        self.pattern_id = ""
        self.step_w = 26
        self.playhead = -1
        self.selected = ""
        self._hover = (-1, -1)
        self._paint_mode: bool | None = None
        self._vel_drag = None
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    # -- geometry ------------------------------------------------------------
    def _pattern(self):
        return self.project.pattern(self.pattern_id) if self.project else None

    def n_steps(self) -> int:
        pat = self._pattern()
        return pat.length if pat else 16

    def n_rows(self) -> int:
        return len(self.project.channels) if self.project else 0

    def sizeHint(self) -> QSize:
        return QSize(max(self.n_steps() * self.step_w, 40),
                     max(self.n_rows() * ROW_H, ROW_H))

    def refresh(self) -> None:
        self.setFixedSize(self.sizeHint())
        self.updateGeometry()
        self.update()

    def set_zoom(self, w: int) -> None:
        self.step_w = max(MIN_STEP_W, min(MAX_STEP_W, int(w)))
        self.refresh()

    def _cell(self, pos) -> tuple[int, int]:
        col = int(pos.x() // self.step_w)
        row = int(pos.y() // ROW_H)
        if 0 <= col < self.n_steps() and 0 <= row < self.n_rows():
            return row, col
        return -1, -1

    # -- interaction ---------------------------------------------------------
    def mousePressEvent(self, e):
        row, col = self._cell(e.position())
        if row < 0:
            return
        ch = self.project.channels[row]
        self.channelSelected.emit(ch.id)
        pat = self._pattern()
        if pat is None:
            return
        existing = pat.note_at(ch.id, col)
        if e.button() == Qt.MouseButton.RightButton:
            if existing:
                self._paint_mode = False
                self.stepToggled.emit(ch.id, col)
            return
        if e.modifiers() & Qt.KeyboardModifier.ControlModifier and existing:
            self._vel_drag = (ch.id, col, e.position().y(), existing.velocity)
            return
        self._paint_mode = existing is None
        self.stepToggled.emit(ch.id, col)

    def mouseMoveEvent(self, e):
        row, col = self._cell(e.position())
        if (row, col) != self._hover:
            self._hover = (row, col)
            self.update()
        if self._vel_drag is not None:
            cid, step, y0, v0 = self._vel_drag
            v = max(0.05, min(1.0, v0 + (y0 - e.position().y()) * 0.008))
            self.velocityChanged.emit(cid, step, v)
            return
        if self._paint_mode is None or row < 0:
            return
        ch = self.project.channels[row]
        pat = self._pattern()
        if pat is None:
            return
        has = pat.note_at(ch.id, col) is not None
        if has != self._paint_mode:
            return
        self.stepToggled.emit(ch.id, col)

    def mouseReleaseEvent(self, e):
        self._paint_mode = None
        self._vel_drag = None

    def leaveEvent(self, e):
        self._hover = (-1, -1)
        self.update()

    # -- paint ---------------------------------------------------------------
    def paintEvent(self, _):
        if self.project is None:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pat = self._pattern()
        steps, rows, sw = self.n_steps(), self.n_rows(), self.step_w
        w, h = steps * sw, rows * ROW_H

        p.fillRect(0, 0, w, h, QColor(T.BG_PANEL))
        # alternating bar shading makes long patterns readable at a glance
        for b in range(0, steps, 16):
            if (b // 16) % 2:
                p.fillRect(QRectF(b * sw, 0, min(16, steps - b) * sw, h),
                           QColor(255, 255, 255, 6))

        for r in range(rows + 1):
            p.setPen(QPen(QColor(T.GRID_LINE), 1))
            p.drawLine(0, r * ROW_H, w, r * ROW_H)
        for c in range(steps + 1):
            if c % 16 == 0:
                p.setPen(QPen(QColor(T.GRID_BAR), 1))
            elif c % 4 == 0:
                p.setPen(QPen(QColor(T.GRID_BEAT), 1))
            else:
                continue
            p.drawLine(int(c * sw), 0, int(c * sw), h)

        pad = 2.0
        for r, ch in enumerate(self.project.channels):
            base = QColor(ch.color)
            notes = pat.notes.get(ch.id, ()) if pat else ()
            occupied = {}
            for nt in notes:
                if 0 <= nt.step < steps:
                    occupied[nt.step] = max(occupied.get(nt.step, 0.0), nt.velocity)
            dim = not self.project.audible(ch)
            for c in range(steps):
                x, y = c * sw + pad, r * ROW_H + pad
                cw, chh = sw - pad * 2, ROW_H - pad * 2
                rect = QRectF(x, y, cw, chh)
                vel = occupied.get(c)
                if vel is None:
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(QColor(255, 255, 255, 10 if c % 4 == 0 else 5))
                    p.drawRoundedRect(rect, 3, 3)
                else:
                    col = QColor(base)
                    col.setAlpha(int(90 + 165 * min(vel, 1.0)))
                    if dim:
                        col.setAlpha(int(col.alpha() * 0.32))
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(col)
                    p.drawRoundedRect(rect, 3, 3)
                    if not dim:
                        hi = QColor(base).lighter(150)
                        hi.setAlpha(150)
                        p.setPen(QPen(hi, 1))
                        p.setBrush(Qt.BrushStyle.NoBrush)
                        p.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), 3, 3)

        hr, hc = self._hover
        if hr >= 0:
            p.setPen(QPen(QColor(T.ACCENT), 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(QRectF(hc * sw + 1.5, hr * ROW_H + 1.5,
                                     sw - 3, ROW_H - 3), 3, 3)

        if self.selected:
            i = self.project.channel_index(self.selected)
            if i >= 0:
                p.setPen(QPen(QColor(T.ACCENT_3), 1))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRect(QRectF(0.5, i * ROW_H + 0.5, w - 1, ROW_H - 1))

        if 0 <= self.playhead < steps:
            x = self.playhead * sw
            p.fillRect(QRectF(x, 0, sw, h), QColor(255, 77, 157, 34))
            p.setPen(QPen(QColor(T.PLAYHEAD), 2))
            p.drawLine(int(x), 0, int(x), h)
        p.end()


class StepRuler(QWidget):
    """Bar numbers above the grid."""

    seekRequested = pyqtSignal(int)

    def __init__(self, grid: StepGrid, parent=None):
        super().__init__(parent)
        self.grid = grid
        self.setFixedHeight(20)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def sizeHint(self) -> QSize:
        return QSize(max(self.grid.n_steps() * self.grid.step_w, 40), 20)

    def refresh(self) -> None:
        self.setFixedSize(self.sizeHint())
        self.update()

    def mousePressEvent(self, e):
        self.seekRequested.emit(int(e.position().x() // self.grid.step_w))

    def paintEvent(self, _):
        p = QPainter(self)
        sw, steps = self.grid.step_w, self.grid.n_steps()
        p.fillRect(self.rect(), QColor(T.BG_PANEL_2))
        f = QFont(); f.setPointSizeF(7.6); f.setBold(True)
        p.setFont(f)
        for b in range(0, steps, 4):
            x = b * sw
            is_bar = b % 16 == 0
            p.setPen(QPen(QColor(T.GRID_BAR if is_bar else T.GRID_BEAT), 1))
            p.drawLine(int(x), 12 if is_bar else 15, int(x), 20)
            if is_bar:
                p.setPen(QColor(T.TEXT_DIM))
                p.drawText(int(x) + 4, 11, str(b // 16 + 1))
        if 0 <= self.grid.playhead < steps:
            x = self.grid.playhead * sw
            p.setPen(QPen(QColor(T.PLAYHEAD), 2))
            p.drawLine(int(x), 0, int(x), 20)
        p.end()


class ChannelHeader(QWidget):
    selected = pyqtSignal(str)
    changed = pyqtSignal()
    pianoRollRequested = pyqtSignal(str)
    contextRequested = pyqtSignal(str, object)

    def __init__(self, project: Project, cid: str, parent=None):
        super().__init__(parent)
        self.project = project
        self.cid = cid
        self.setFixedHeight(ROW_H)
        self.setFixedWidth(HEADER_W)
        self.setAutoFillBackground(False)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 0, 6, 0)
        lay.setSpacing(5)

        ch = project.channel(cid)
        self.dot = ColorDot(ch.color if ch else T.ACCENT, 8)
        self.name = QLabel(ch.name if ch else "?")
        self.name.setStyleSheet("font-weight:600;")
        self.name.setMinimumWidth(72)
        self.meter = LevelMeter(Qt.Orientation.Horizontal)
        self.meter.setFixedWidth(30)

        self.btn_pr = QPushButton("⌗")
        self.btn_pr.setFixedSize(19, 19)
        self.btn_pr.setToolTip("Open piano roll")
        self.btn_pr.clicked.connect(lambda: self.pianoRollRequested.emit(self.cid))
        self.btn_m = QPushButton("M")
        self.btn_m.setCheckable(True)
        self.btn_m.setFixedSize(19, 19)
        self.btn_m.setObjectName("Danger")
        self.btn_m.setToolTip("Mute")
        self.btn_s = QPushButton("S")
        self.btn_s.setCheckable(True)
        self.btn_s.setFixedSize(19, 19)
        self.btn_s.setToolTip("Solo")
        self.btn_m.clicked.connect(self._mute)
        self.btn_s.clicked.connect(self._solo)

        lay.addWidget(self.dot)
        lay.addWidget(self.name, 1)
        lay.addWidget(self.meter)
        lay.addWidget(self.btn_pr)
        lay.addWidget(self.btn_m)
        lay.addWidget(self.btn_s)
        self.sync()

    def sync(self) -> None:
        ch = self.project.channel(self.cid)
        if ch is None:
            return
        self.dot.set_color(ch.color)
        self.name.setText(ch.name)
        self.btn_m.setChecked(ch.mute)
        self.btn_s.setChecked(ch.solo)
        self.name.setStyleSheet(
            "font-weight:600;" + ("" if self.project.audible(ch)
                                  else f"color:{T.TEXT_FAINT};"))

    def _mute(self):
        ch = self.project.channel(self.cid)
        if ch:
            ch.mute = self.btn_m.isChecked()
            self.changed.emit()

    def _solo(self):
        ch = self.project.channel(self.cid)
        if ch:
            ch.solo = self.btn_s.isChecked()
            self.changed.emit()

    def mousePressEvent(self, e):
        self.selected.emit(self.cid)
        if e.button() == Qt.MouseButton.RightButton:
            self.contextRequested.emit(self.cid, e.globalPosition().toPoint())

    def mouseDoubleClickEvent(self, e):
        ch = self.project.channel(self.cid)
        if ch is None:
            return
        name, ok = QInputDialog.getText(self, "Rename channel", "Name:", text=ch.name)
        if ok and name.strip():
            ch.name = name.strip()
            self.sync()
            self.changed.emit()

    def paintEvent(self, e):
        p = QPainter(self)
        ch = self.project.channel(self.cid)
        bg = QColor(T.BG_PANEL_2)
        p.fillRect(self.rect(), bg)
        if ch:
            col = QColor(ch.color)
            col.setAlpha(200)
            p.fillRect(0, 0, 3, self.height(), col)
        p.setPen(QPen(QColor(T.GRID_LINE), 1))
        p.drawLine(0, self.height() - 1, self.width(), self.height() - 1)
        p.end()


class ChannelRack(QWidget):
    """Header column + step grid, vertically synchronised."""

    channelSelected = pyqtSignal(str)
    projectChanged = pyqtSignal()
    pianoRollRequested = pyqtSignal(str)
    channelContext = pyqtSignal(str, object)
    seekRequested = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.project: Project | None = None
        self.headers: dict[str, ChannelHeader] = {}

        self.grid = StepGrid()
        self.ruler = StepRuler(self.grid)
        self.ruler.seekRequested.connect(self.seekRequested)
        self.grid.stepToggled.connect(self._toggle)
        self.grid.velocityChanged.connect(self._set_velocity)
        self.grid.channelSelected.connect(self._select)

        self.head_area = QScrollArea()
        self.head_area.setWidgetResizable(True)
        self.head_area.setFixedWidth(HEADER_W)
        self.head_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.head_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.head_host = QWidget()
        self.head_lay = QVBoxLayout(self.head_host)
        self.head_lay.setContentsMargins(0, 0, 0, 0)
        self.head_lay.setSpacing(0)
        self.head_lay.addStretch(1)
        self.head_area.setWidget(self.head_host)

        self.grid_area = QScrollArea()
        self.grid_area.setWidgetResizable(False)
        self.grid_area.setSizeAdjustPolicy(
            QAbstractScrollArea.SizeAdjustPolicy.AdjustIgnored)
        gh = QWidget()
        gl = QVBoxLayout(gh)
        gl.setContentsMargins(0, 0, 0, 0)
        gl.setSpacing(0)
        gl.addWidget(self.ruler)
        gl.addWidget(self.grid)
        gl.addStretch(1)
        self.grid_area.setWidget(gh)
        self.grid_area.verticalScrollBar().valueChanged.connect(
            self.head_area.verticalScrollBar().setValue)

        spacer = QWidget()
        spacer.setFixedHeight(20)
        left = QVBoxLayout()
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(0)
        left.addWidget(spacer)
        left.addWidget(self.head_area, 1)

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        row.addLayout(left)
        row.addWidget(self.grid_area, 1)

    # -- wiring --------------------------------------------------------------
    def set_project(self, project: Project, pattern_id: str) -> None:
        self.project = project
        self.grid.project = project
        self.grid.pattern_id = pattern_id
        self.rebuild()

    def set_pattern(self, pattern_id: str) -> None:
        self.grid.pattern_id = pattern_id
        self.refresh()

    def rebuild(self) -> None:
        for h in self.headers.values():
            h.setParent(None)
            h.deleteLater()
        self.headers.clear()
        if self.project is None:
            return
        for ch in self.project.channels:
            h = ChannelHeader(self.project, ch.id)
            h.selected.connect(self._select)
            h.changed.connect(self._header_changed)
            h.pianoRollRequested.connect(self.pianoRollRequested)
            h.contextRequested.connect(self.channelContext)
            self.head_lay.insertWidget(self.head_lay.count() - 1, h)
            self.headers[ch.id] = h
        self.refresh()

    def refresh(self) -> None:
        self.grid.refresh()
        self.ruler.refresh()
        for h in self.headers.values():
            h.sync()

    def _header_changed(self) -> None:
        self.refresh()
        self.projectChanged.emit()

    def _select(self, cid: str) -> None:
        self.grid.selected = cid
        self.grid.update()
        self.channelSelected.emit(cid)

    def _toggle(self, cid: str, step: int) -> None:
        pat = self.project.pattern(self.grid.pattern_id)
        if pat is None:
            return
        ch = self.project.channel(cid)
        pitch = 48 if (ch and ch.drum) else 60
        pat.toggle_step(cid, step, pitch)
        self.grid.update()
        self.projectChanged.emit()

    def _set_velocity(self, cid: str, step: int, vel: float) -> None:
        pat = self.project.pattern(self.grid.pattern_id)
        if pat is None:
            return
        nt = pat.note_at(cid, step)
        if nt:
            nt.velocity = vel
            self.grid.update()

    def set_playhead(self, step: int) -> None:
        if step != self.grid.playhead:
            self.grid.playhead = step
            self.grid.update()
            self.ruler.update()

    def set_meters(self, meters: dict) -> None:
        for cid, h in self.headers.items():
            h.meter.set_level(meters.get(cid, 0.0))

    def set_zoom(self, w: int) -> None:
        self.grid.set_zoom(w)
        self.ruler.refresh()
