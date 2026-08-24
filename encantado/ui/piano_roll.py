"""Piano roll editor with scale highlighting and ghost notes."""
from __future__ import annotations

from PyQt6.QtCore import QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import (QComboBox, QHBoxLayout, QLabel, QPushButton,
                             QScrollArea, QSizePolicy, QVBoxLayout, QWidget)

from ..core.project import Note, Project
from ..core.theory import is_black_key, note_name, scale_pitches, snap_to_scale
from . import theme as T

NOTE_H = 12
LOW_PITCH = 21
HIGH_PITCH = 108
KEY_W = 58
EDGE = 5


class PianoKeys(QWidget):
    notePressed = pyqtSignal(int)
    noteReleased = pyqtSignal(int)

    def __init__(self, roll, parent=None):
        super().__init__(parent)
        self.roll = roll
        self.setFixedWidth(KEY_W)
        self._down = -1
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def sizeHint(self) -> QSize:
        return QSize(KEY_W, (HIGH_PITCH - LOW_PITCH + 1) * NOTE_H)

    def _pitch(self, y) -> int:
        return HIGH_PITCH - int(y // NOTE_H)

    def mousePressEvent(self, e):
        self._down = self._pitch(e.position().y())
        self.notePressed.emit(self._down)
        self.update()

    def mouseReleaseEvent(self, e):
        if self._down >= 0:
            self.noteReleased.emit(self._down)
        self._down = -1
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        h = self.height()
        p.fillRect(self.rect(), QColor(T.BG_PANEL_2))
        f = QFont(); f.setPointSizeF(7.0)
        p.setFont(f)
        allowed = self.roll.scale_set()
        for pitch in range(LOW_PITCH, HIGH_PITCH + 1):
            y = (HIGH_PITCH - pitch) * NOTE_H
            if y > h:
                continue
            black = is_black_key(pitch)
            if pitch == self._down:
                col = QColor(T.ACCENT)
            elif black:
                col = QColor("#0f131a")
            else:
                col = QColor("#c9d2e0")
            width = (KEY_W - 24) if black else (KEY_W - 8)
            p.fillRect(QRectF(0, y, KEY_W - 8, NOTE_H - 1),
                       QColor("#aab4c4") if black else col)
            p.fillRect(QRectF(0, y, width, NOTE_H - 1), col)
            if allowed and (pitch % 12) in allowed:
                p.fillRect(QRectF(KEY_W - 7, y, 4, NOTE_H - 1),
                           QColor(T.ACCENT_3))
            if pitch % 12 == 0:
                p.setPen(QColor("#33404f") if not black else QColor(T.TEXT_DIM))
                p.drawText(QRectF(3, y, KEY_W - 14, NOTE_H),
                           Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                           note_name(pitch))
        p.setPen(QPen(QColor(T.BORDER), 1))
        p.drawLine(KEY_W - 1, 0, KEY_W - 1, h)
        p.end()


class RollGrid(QWidget):
    notesChanged = pyqtSignal()
    previewNote = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.project: Project | None = None
        self.pattern_id = ""
        self.channel_id = ""
        self.step_w = 24
        self.playhead = -1
        self.snap = 1
        self.default_len = 4
        self.show_ghosts = True
        self._drag = None
        self._erase = False
        self._hover = None
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    # -- helpers -------------------------------------------------------------
    def pattern(self):
        return self.project.pattern(self.pattern_id) if self.project else None

    def channel(self):
        return self.project.channel(self.channel_id) if self.project else None

    def n_steps(self) -> int:
        pat = self.pattern()
        return pat.length if pat else 16

    def scale_set(self):
        if not self.project:
            return set()
        return scale_pitches(self.project.root, self.project.scale)

    def sizeHint(self) -> QSize:
        return QSize(max(self.n_steps() * self.step_w, 60),
                     (HIGH_PITCH - LOW_PITCH + 1) * NOTE_H)

    def refresh(self) -> None:
        self.setFixedSize(self.sizeHint())
        self.update()

    def _pitch(self, y) -> int:
        return max(LOW_PITCH, min(HIGH_PITCH, HIGH_PITCH - int(y // NOTE_H)))

    def _step(self, x) -> int:
        return max(0, int(x // self.step_w))

    def _notes(self):
        pat = self.pattern()
        if pat is None or not self.channel_id:
            return []
        return pat.notes.get(self.channel_id, [])

    def _note_at(self, pos):
        st, pitch = self._step(pos.x()), self._pitch(pos.y())
        for nt in reversed(self._notes()):
            if nt.pitch == pitch and nt.step <= st < nt.step + max(nt.length, 1):
                right = (nt.step + nt.length) * self.step_w
                return nt, abs(pos.x() - right) <= EDGE
        return None, False

    def _snap(self, step: int) -> int:
        return (step // self.snap) * self.snap if self.snap > 1 else step

    # -- interaction ---------------------------------------------------------
    def mousePressEvent(self, e):
        if self.project is None or not self.channel_id:
            return
        pat = self.pattern()
        if pat is None:
            return
        nt, on_edge = self._note_at(e.position())

        if e.button() == Qt.MouseButton.RightButton:
            self._erase = True
            if nt:
                pat.remove_note(self.channel_id, nt)
                self.update()
                self.notesChanged.emit()
            return

        if nt is None:
            pitch = self._pitch(e.position().y())
            if e.modifiers() & Qt.KeyboardModifier.AltModifier:
                pitch = snap_to_scale(pitch, self.project.root, self.project.scale)
            step = self._snap(self._step(e.position().x()))
            nt = Note(step, pitch, self.default_len, 0.9)
            pat.add_note(self.channel_id, nt)
            self.previewNote.emit(pitch)
            self._drag = ("resize", nt, e.position(), nt.step, nt.pitch, nt.length)
        elif e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self._drag = ("vel", nt, e.position(), nt.step, nt.pitch, nt.velocity)
        elif on_edge:
            self._drag = ("resize", nt, e.position(), nt.step, nt.pitch, nt.length)
        else:
            self.previewNote.emit(nt.pitch)
            self._drag = ("move", nt, e.position(), nt.step, nt.pitch, nt.length)
        self.update()
        self.notesChanged.emit()

    def mouseMoveEvent(self, e):
        pos = e.position()
        if self._erase:
            nt, _ = self._note_at(pos)
            pat = self.pattern()
            if nt and pat:
                pat.remove_note(self.channel_id, nt)
                self.update()
                self.notesChanged.emit()
            return
        if self._drag is None:
            nt, on_edge = self._note_at(pos)
            self.setCursor(Qt.CursorShape.SizeHorCursor if on_edge
                           else Qt.CursorShape.ArrowCursor)
            h = (self._step(pos.x()), self._pitch(pos.y()))
            if h != self._hover:
                self._hover = h
                self.update()
            return

        kind, nt, origin, s0, p0, v0 = self._drag
        dx = pos.x() - origin.x()
        if kind == "move":
            dsteps = self._snap(int(round(dx / self.step_w)) + s0) - s0 \
                if self.snap > 1 else int(round(dx / self.step_w))
            dpitch = int(round((origin.y() - pos.y()) / NOTE_H))
            nt.step = max(0, min(self.n_steps() - 1, s0 + dsteps))
            new_pitch = max(LOW_PITCH, min(HIGH_PITCH, p0 + dpitch))
            if e.modifiers() & Qt.KeyboardModifier.AltModifier:
                new_pitch = snap_to_scale(new_pitch, self.project.root,
                                          self.project.scale)
            if new_pitch != nt.pitch:
                self.previewNote.emit(new_pitch)
            nt.pitch = new_pitch
        elif kind == "resize":
            end = self._step(pos.x()) + 1
            if self.snap > 1:
                end = max(self.snap, ((end + self.snap - 1) // self.snap) * self.snap)
            nt.length = max(1, min(self.n_steps() - nt.step, end - nt.step))
            self.default_len = nt.length
        else:
            nt.velocity = max(0.05, min(1.0, v0 + (origin.y() - pos.y()) * 0.008))
        self.update()
        self.notesChanged.emit()

    def mouseReleaseEvent(self, e):
        if self._drag is not None:
            pat = self.pattern()
            if pat and self.channel_id:
                pat.notes[self.channel_id].sort(key=lambda n: (n.step, n.pitch))
        self._drag = None
        self._erase = False

    def leaveEvent(self, e):
        self._hover = None
        self.update()

    # -- paint ---------------------------------------------------------------
    def paintEvent(self, _):
        if self.project is None:
            return
        p = QPainter(self)
        steps, sw = self.n_steps(), self.step_w
        w, h = steps * sw, (HIGH_PITCH - LOW_PITCH + 1) * NOTE_H
        p.fillRect(0, 0, w, h, QColor(T.BG_PANEL))

        allowed = self.scale_set()
        for pitch in range(LOW_PITCH, HIGH_PITCH + 1):
            y = (HIGH_PITCH - pitch) * NOTE_H
            if is_black_key(pitch):
                p.fillRect(QRectF(0, y, w, NOTE_H), QColor(0, 0, 0, 58))
            if allowed and (pitch % 12) not in allowed:
                p.fillRect(QRectF(0, y, w, NOTE_H), QColor(0, 0, 0, 42))
            if pitch % 12 == self.project.root:
                p.fillRect(QRectF(0, y, w, NOTE_H), QColor(139, 124, 255, 22))

        for b in range(0, steps, 16):
            if (b // 16) % 2:
                p.fillRect(QRectF(b * sw, 0, min(16, steps - b) * sw, h),
                           QColor(255, 255, 255, 5))
        for pitch in range(LOW_PITCH, HIGH_PITCH + 2):
            y = (HIGH_PITCH - pitch + 1) * NOTE_H
            p.setPen(QPen(QColor(T.GRID_LINE), 1))
            p.drawLine(0, int(y), w, int(y))
        for c in range(steps + 1):
            if c % 16 == 0:
                p.setPen(QPen(QColor(T.GRID_BAR), 1))
            elif c % 4 == 0:
                p.setPen(QPen(QColor(T.GRID_BEAT), 1))
            else:
                continue
            p.drawLine(int(c * sw), 0, int(c * sw), h)

        pat = self.pattern()
        if pat is None:
            p.end()
            return

        if self.show_ghosts:
            for cid, notes in pat.notes.items():
                if cid == self.channel_id:
                    continue
                ch = self.project.channel(cid)
                if ch is None or ch.drum:
                    continue
                col = QColor(ch.color)
                col.setAlpha(46)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(col)
                for nt in notes:
                    y = (HIGH_PITCH - nt.pitch) * NOTE_H
                    p.drawRoundedRect(
                        QRectF(nt.step * sw + 1, y + 1.5,
                               max(nt.length, 1) * sw - 2, NOTE_H - 3), 2, 2)

        ch = self.channel()
        base = QColor(ch.color) if ch else QColor(T.ACCENT)
        for nt in self._notes():
            y = (HIGH_PITCH - nt.pitch) * NOTE_H
            rect = QRectF(nt.step * sw + 1, y + 1.5,
                          max(nt.length, 1) * sw - 2, NOTE_H - 3)
            col = QColor(base)
            col.setAlpha(int(110 + 145 * min(nt.velocity, 1.0)))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(col)
            p.drawRoundedRect(rect, 2.5, 2.5)
            edge = QColor(base).lighter(160)
            edge.setAlpha(190)
            p.setPen(QPen(edge, 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), 2.5, 2.5)

        if self._hover and self._drag is None:
            st, pitch = self._hover
            if 0 <= st < steps:
                y = (HIGH_PITCH - pitch) * NOTE_H
                p.setPen(QPen(QColor(T.ACCENT), 1, Qt.PenStyle.DotLine))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRect(QRectF(st * sw + 1, y + 1.5, sw - 2, NOTE_H - 3))

        if 0 <= self.playhead < steps:
            x = self.playhead * sw
            p.setPen(QPen(QColor(T.PLAYHEAD), 2))
            p.drawLine(int(x), 0, int(x), h)
        p.end()


class RollRuler(QWidget):
    seekRequested = pyqtSignal(int)

    def __init__(self, grid: RollGrid, parent=None):
        super().__init__(parent)
        self.grid = grid
        self.setFixedHeight(20)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def sizeHint(self) -> QSize:
        return QSize(max(self.grid.n_steps() * self.grid.step_w, 60), 20)

    def refresh(self) -> None:
        self.setFixedSize(self.sizeHint())
        self.update()

    def mousePressEvent(self, e):
        self.seekRequested.emit(int(e.position().x() // self.grid.step_w))

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(T.BG_PANEL_2))
        sw, steps = self.grid.step_w, self.grid.n_steps()
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


class PianoRoll(QWidget):
    notesChanged = pyqtSignal()
    previewNote = pyqtSignal(str, int)
    seekRequested = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.project: Project | None = None
        self.grid = RollGrid()
        self.keys = PianoKeys(self.grid)
        self.ruler = RollRuler(self.grid)

        bar = QHBoxLayout()
        bar.setContentsMargins(8, 6, 8, 6)
        bar.setSpacing(8)
        self.title = QLabel("Piano Roll")
        self.title.setObjectName("Heading")
        bar.addWidget(self.title)
        bar.addSpacing(12)

        bar.addWidget(QLabel("Snap"))
        self.snap_box = QComboBox()
        for lbl, v in (("1/16", 1), ("1/8", 2), ("1/4", 4), ("1/2", 8), ("Bar", 16)):
            self.snap_box.addItem(lbl, v)
        self.snap_box.currentIndexChanged.connect(
            lambda: setattr(self.grid, "snap", self.snap_box.currentData()))
        bar.addWidget(self.snap_box)

        bar.addWidget(QLabel("Length"))
        self.len_box = QComboBox()
        for lbl, v in (("1/16", 1), ("1/8", 2), ("1/4", 4), ("1/2", 8), ("Bar", 16)):
            self.len_box.addItem(lbl, v)
        self.len_box.setCurrentIndex(2)
        self.len_box.currentIndexChanged.connect(
            lambda: setattr(self.grid, "default_len", self.len_box.currentData()))
        bar.addWidget(self.len_box)

        self.ghost_btn = QPushButton("Ghosts")
        self.ghost_btn.setCheckable(True)
        self.ghost_btn.setChecked(True)
        self.ghost_btn.setToolTip("Show notes from other channels behind these")
        self.ghost_btn.toggled.connect(self._set_ghosts)
        bar.addWidget(self.ghost_btn)

        hint = QLabel("drag to draw · right-click erase · ctrl-drag velocity · alt snap to key")
        hint.setObjectName("Faint")
        bar.addStretch(1)
        bar.addWidget(hint)

        self.area = QScrollArea()
        self.area.setWidgetResizable(False)
        host = QWidget()
        self.host = host
        hl = QHBoxLayout(host)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(0)
        kcol = QVBoxLayout()
        kcol.setContentsMargins(0, 0, 0, 0)
        kcol.setSpacing(0)
        spacer = QWidget(); spacer.setFixedSize(KEY_W, 20)
        kcol.addWidget(spacer)
        kcol.addWidget(self.keys)
        gcol = QVBoxLayout()
        gcol.setContentsMargins(0, 0, 0, 0)
        gcol.setSpacing(0)
        gcol.addWidget(self.ruler)
        gcol.addWidget(self.grid)
        hl.addLayout(kcol)
        hl.addLayout(gcol)
        hl.addStretch(1)
        self.area.setWidget(host)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addLayout(bar)
        lay.addWidget(self.area, 1)

        self.grid.notesChanged.connect(self.notesChanged)
        self.grid.previewNote.connect(self._preview)
        self.keys.notePressed.connect(self._preview)
        self.ruler.seekRequested.connect(self.seekRequested)

    def _set_ghosts(self, on: bool) -> None:
        self.grid.show_ghosts = on
        self.grid.update()

    def _preview(self, pitch: int) -> None:
        if self.grid.channel_id:
            self.previewNote.emit(self.grid.channel_id, pitch)

    def set_context(self, project: Project, pattern_id: str, channel_id: str) -> None:
        self.project = project
        self.grid.project = project
        self.grid.pattern_id = pattern_id
        self.grid.channel_id = channel_id
        ch = project.channel(channel_id)
        self.title.setText(f"Piano Roll — {ch.name}" if ch else "Piano Roll")
        self.refresh()
        if ch is not None:
            self._scroll_to_content()

    def _scroll_to_content(self) -> None:
        notes = self.grid._notes()
        centre = (sum(n.pitch for n in notes) / len(notes)) if notes else 60
        y = (HIGH_PITCH - centre) * NOTE_H - self.area.height() / 2
        self.area.verticalScrollBar().setValue(int(max(0, y)))

    def refresh(self) -> None:
        self.grid.refresh()
        self.ruler.refresh()
        self.keys.setFixedSize(self.keys.sizeHint())
        self.keys.update()
        self.host.adjustSize()

    def set_playhead(self, step: int) -> None:
        if step != self.grid.playhead:
            self.grid.playhead = step
            self.grid.update()
            self.ruler.update()
