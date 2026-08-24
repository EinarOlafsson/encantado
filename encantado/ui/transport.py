"""Top transport bar: play controls, tempo, key, pattern selection, meters."""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (QComboBox, QDoubleSpinBox, QFrame, QHBoxLayout,
                             QLabel, QPushButton, QSlider, QVBoxLayout, QWidget)

from ..core.project import Project
from ..core.theory import NOTE_NAMES, SCALES
from . import theme as T
from .widgets import LevelMeter


class Transport(QFrame):
    playPressed = pyqtSignal()
    stopPressed = pyqtSignal()
    modeChanged = pyqtSignal(str)
    tempoChanged = pyqtSignal(float)
    keyChanged = pyqtSignal()
    patternChanged = pyqtSignal(str)
    patternAdd = pyqtSignal()
    patternDuplicate = pyqtSignal()
    patternRemove = pyqtSignal()
    patternLengthChanged = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Panel")
        self.project: Project | None = None
        self._sync_guard = False
        self.setFixedHeight(56)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.setSpacing(9)

        self.btn_play = QPushButton("▶")
        self.btn_play.setObjectName("Primary")
        self.btn_play.setFixedSize(42, 32)
        self.btn_play.setToolTip("Play / pause  (Space)")
        self.btn_play.clicked.connect(self.playPressed)
        self.btn_stop = QPushButton("■")
        self.btn_stop.setFixedSize(34, 32)
        self.btn_stop.setToolTip("Stop and rewind")
        self.btn_stop.clicked.connect(self.stopPressed)
        lay.addWidget(self.btn_play)
        lay.addWidget(self.btn_stop)

        self.btn_pattern = QPushButton("Pattern")
        self.btn_pattern.setMinimumWidth(84)
        self.btn_song = QPushButton("Song")
        self.btn_song.setMinimumWidth(62)
        for b, m in ((self.btn_pattern, "pattern"), (self.btn_song, "song")):
            b.setCheckable(True)
            b.setFixedHeight(32)
            b.clicked.connect(lambda _, mm=m: self._set_mode(mm))
        self.btn_pattern.setChecked(True)
        lay.addWidget(self.btn_pattern)
        lay.addWidget(self.btn_song)
        lay.addWidget(self._sep())

        self.pos = QLabel("1 . 1")
        self.pos.setStyleSheet(
            f"font-family:monospace; font-size:17px; font-weight:700;"
            f" color:{T.ACCENT}; min-width:74px;")
        lay.addWidget(self.pos)
        lay.addWidget(self._sep())

        lay.addWidget(self._cap("BPM"))
        self.bpm = QDoubleSpinBox()
        self.bpm.setRange(40.0, 220.0)
        self.bpm.setDecimals(1)
        self.bpm.setSingleStep(0.5)
        self.bpm.setValue(124.0)
        self.bpm.setFixedWidth(74)
        self.bpm.valueChanged.connect(self._bpm)
        lay.addWidget(self.bpm)

        lay.addWidget(self._cap("Key"))
        self.root = QComboBox()
        self.root.addItems(NOTE_NAMES)
        self.root.setFixedWidth(56)
        self.root.currentIndexChanged.connect(self._key)
        lay.addWidget(self.root)
        self.scale = QComboBox()
        self.scale.addItems(list(SCALES.keys()))
        self.scale.setFixedWidth(116)
        self.scale.currentIndexChanged.connect(self._key)
        lay.addWidget(self.scale)

        lay.addWidget(self._cap("Swing"))
        self.swing = QSlider(Qt.Orientation.Horizontal)
        self.swing.setRange(0, 100)
        self.swing.setFixedWidth(58)
        self.swing.valueChanged.connect(self._key)
        lay.addWidget(self.swing)
        lay.addWidget(self._sep())

        lay.addWidget(self._cap("Pattern"))
        self.pattern = QComboBox()
        self.pattern.setMinimumWidth(112)
        self.pattern.currentIndexChanged.connect(self._pattern)
        lay.addWidget(self.pattern)
        for label, sig, tip in (("+", self.patternAdd, "New pattern"),
                                ("◧", self.patternDuplicate, "Duplicate"),
                                ("✕", self.patternRemove, "Delete")):
            b = QPushButton(label)
            b.setObjectName("Mini")
            b.setFixedSize(24, 24)
            b.setToolTip(tip)
            b.clicked.connect(sig)
            lay.addWidget(b)

        lay.addWidget(self._cap("Bars"))
        self.length = QComboBox()
        for bars in (1, 2, 4, 8, 16):
            self.length.addItem(str(bars), bars * 16)
        self.length.setFixedWidth(58)
        self.length.currentIndexChanged.connect(
            lambda: self.patternLengthChanged.emit(self.length.currentData()))
        lay.addWidget(self.length)

        lay.addStretch(1)
        self.cpu = QLabel("CPU 0%")
        self.cpu.setObjectName("Faint")
        lay.addWidget(self.cpu)
        col = QVBoxLayout()
        col.setSpacing(1)
        cap = QLabel("MASTER")
        cap.setObjectName("Title")
        self.meter = LevelMeter(Qt.Orientation.Horizontal)
        self.meter.setFixedWidth(96)
        col.addWidget(cap)
        col.addWidget(self.meter)
        lay.addLayout(col)

    @staticmethod
    def _sep() -> QWidget:
        w = QFrame()
        w.setFixedWidth(1)
        w.setStyleSheet(f"background:{T.BORDER};")
        return w

    @staticmethod
    def _cap(text: str) -> QLabel:
        lb = QLabel(text)
        lb.setObjectName("Title")
        return lb

    # -- events --------------------------------------------------------------
    def _set_mode(self, mode: str) -> None:
        self.btn_pattern.setChecked(mode == "pattern")
        self.btn_song.setChecked(mode == "song")
        self.modeChanged.emit(mode)

    def _bpm(self, v):
        if not self._sync_guard and self.project:
            self.project.bpm = float(v)
            self.tempoChanged.emit(float(v))

    def _key(self):
        if self._sync_guard or not self.project:
            return
        self.project.root = self.root.currentIndex()
        self.project.scale = self.scale.currentText()
        self.project.swing = self.swing.value() / 100.0
        self.keyChanged.emit()

    def _pattern(self):
        if not self._sync_guard:
            pid = self.pattern.currentData()
            if pid:
                self.patternChanged.emit(pid)

    # -- state ---------------------------------------------------------------
    def set_project(self, project: Project) -> None:
        self.project = project
        self.sync()

    def sync(self, current_pattern: str = "") -> None:
        if self.project is None:
            return
        self._sync_guard = True
        self.bpm.setValue(self.project.bpm)
        self.root.setCurrentIndex(self.project.root)
        i = self.scale.findText(self.project.scale)
        if i >= 0:
            self.scale.setCurrentIndex(i)
        self.swing.setValue(int(self.project.swing * 100))
        cur = current_pattern or self.pattern.currentData()
        self.pattern.clear()
        for pat in self.project.patterns:
            self.pattern.addItem(pat.name, pat.id)
        idx = self.pattern.findData(cur)
        self.pattern.setCurrentIndex(idx if idx >= 0 else 0)
        pat = self.project.pattern(self.pattern.currentData())
        if pat:
            li = self.length.findData(pat.length)
            if li >= 0:
                self.length.setCurrentIndex(li)
        self._sync_guard = False

    def set_playing(self, playing: bool) -> None:
        self.btn_play.setText("❚❚" if playing else "▶")

    def set_position(self, step: int, mode: str) -> None:
        bar, beat = step // 16 + 1, (step % 16) // 4 + 1
        self.pos.setText(f"{bar} . {beat}")

    def set_meters(self, peak, cpu: float) -> None:
        self.meter.set_level(float(peak[0]), float(peak[1]))
        self.cpu.setText(f"CPU {cpu:.0f}%")
