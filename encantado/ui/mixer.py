"""Mixer: one strip per channel plus the master chain."""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPushButton,
                             QScrollArea, QVBoxLayout, QWidget)

from ..core.project import Project
from ..dsp.effects import (Compressor, DJFilter, Delay, EQ3, Limiter, Reverb)
from ..dsp.params import Param
from . import theme as T
from .widgets import Fader, Knob, LevelMeter

PAN_P = Param("pan", "Pan", -1.0, 1.0, 0.0, "", "lin")
REV_P = Param("reverb", "Rev", 0.0, 1.0, 0.0, "%", "lin")
DLY_P = Param("delay", "Dly", 0.0, 1.0, 0.0, "%", "lin")
SC_P = Param("sc", "Duck", 0.0, 1.0, 0.0, "%", "lin")
VOL_P = Param("vol", "Master", 0.0, 1.2, 0.85, "%", "lin")


class ChannelStrip(QFrame):
    changed = pyqtSignal()
    selected = pyqtSignal(str)

    def __init__(self, project: Project, cid: str, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.project = project
        self.cid = cid
        ch = project.channel(cid)
        self.setFixedWidth(84)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(5, 6, 5, 6)
        lay.setSpacing(4)

        self.name = QLabel(ch.name)
        self.name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.name.setWordWrap(True)
        self.name.setFixedHeight(26)
        self.name.setStyleSheet(f"font-weight:700; font-size:10px; color:{ch.color};")
        lay.addWidget(self.name)

        self.k_pan = Knob(PAN_P, ch.pan, ch.color)
        self.k_pan.valueChanged.connect(self._pan)
        lay.addWidget(self.k_pan, 0, Qt.AlignmentFlag.AlignHCenter)

        sends = QHBoxLayout()
        sends.setSpacing(0)
        self.k_rev = Knob(REV_P, ch.sends.reverb, T.ACCENT_3)
        self.k_dly = Knob(DLY_P, ch.sends.delay, T.ACCENT_3)
        self.k_rev.valueChanged.connect(self._rev)
        self.k_dly.valueChanged.connect(self._dly)
        sends.addWidget(self.k_rev)
        sends.addWidget(self.k_dly)
        lay.addLayout(sends)

        self.k_sc = Knob(SC_P, ch.sc_amount, T.ACCENT_2)
        self.k_sc.setToolTip("Sidechain — how hard the kick ducks this channel")
        self.k_sc.valueChanged.connect(self._sc)
        lay.addWidget(self.k_sc, 0, Qt.AlignmentFlag.AlignHCenter)

        row = QHBoxLayout()
        row.setSpacing(3)
        row.setAlignment(Qt.AlignmentFlag.AlignBottom)
        row.addStretch(1)
        self.fader = Fader(ch.volume)
        self.fader.setMaximumHeight(250)
        self.fader.valueChanged.connect(self._vol)
        self.meter = LevelMeter()
        self.meter.setMaximumHeight(250)
        row.addWidget(self.fader)
        row.addWidget(self.meter)
        row.addStretch(1)
        lay.addLayout(row, 1)

        btns = QHBoxLayout()
        btns.setSpacing(3)
        self.btn_m = QPushButton("M")
        self.btn_m.setCheckable(True)
        self.btn_m.setObjectName("MiniDanger")
        self.btn_s = QPushButton("S")
        self.btn_s.setCheckable(True)
        for b in (self.btn_m, self.btn_s):
            b.setFixedHeight(19)
        self.btn_m.clicked.connect(self._mute)
        self.btn_s.clicked.connect(self._solo)
        btns.addWidget(self.btn_m)
        btns.addWidget(self.btn_s)
        lay.addLayout(btns)
        self.sync()

    def _ch(self):
        return self.project.channel(self.cid)

    def _pan(self, v):
        self._ch().pan = v; self.changed.emit()

    def _rev(self, v):
        self._ch().sends.reverb = v; self.changed.emit()

    def _dly(self, v):
        self._ch().sends.delay = v; self.changed.emit()

    def _sc(self, v):
        self._ch().sc_amount = v; self.changed.emit()

    def _vol(self, v):
        self._ch().volume = v; self.changed.emit()

    def _mute(self):
        self._ch().mute = self.btn_m.isChecked(); self.changed.emit()

    def _solo(self):
        self._ch().solo = self.btn_s.isChecked(); self.changed.emit()

    def mousePressEvent(self, e):
        self.selected.emit(self.cid)

    def sync(self):
        ch = self._ch()
        if ch is None:
            return
        self.name.setText(ch.name)
        self.name.setStyleSheet(
            f"font-weight:700; font-size:10px; color:"
            f"{ch.color if self.project.audible(ch) else T.TEXT_FAINT};")
        self.btn_m.setChecked(ch.mute)
        self.btn_s.setChecked(ch.solo)
        for k, v in ((self.k_pan, ch.pan), (self.k_rev, ch.sends.reverb),
                     (self.k_dly, ch.sends.delay), (self.k_sc, ch.sc_amount)):
            k.setValue(v, emit=False)
        self.fader.setValue(ch.volume, emit=False)


class MasterStrip(QFrame):
    changed = pyqtSignal()

    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.project = project
        self.setFixedWidth(268)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(9, 8, 9, 8)
        lay.setSpacing(6)

        head = QLabel("MASTER")
        head.setObjectName("Title")
        head.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(head)

        self.knobs: dict[str, Knob] = {}

        def group(title, section, specs):
            lb = QLabel(title)
            lb.setObjectName("Title")
            lay.addWidget(lb)
            grid = QHBoxLayout()
            grid.setSpacing(0)
            for prm in specs:
                val = project.master.get(section, {}).get(prm.key, prm.default)
                k = Knob(prm, val, T.ACCENT)
                k.valueChanged.connect(
                    lambda v, s=section, key=prm.key: self._set(s, key, v))
                self.knobs[f"{section}.{prm.key}"] = k
                grid.addWidget(k)
            grid.addStretch(1)
            lay.addLayout(grid)

        group("Filter", "djfilter", [p for p in DJFilter.PARAMS])
        group("EQ", "eq", [p for p in EQ3.PARAMS if p.key in ("low", "mid", "high")])
        group("Glue", "comp", [p for p in Compressor.PARAMS
                               if p.key in ("threshold", "ratio", "makeup")])
        group("Reverb", "reverb", [p for p in Reverb.PARAMS
                                   if p.key in ("size", "damp", "hp")])
        group("Delay", "delay", [p for p in Delay.PARAMS
                                 if p.key in ("division", "feedback", "lp")])
        group("Limiter", "limiter", [p for p in Limiter.PARAMS
                                     if p.key in ("ceiling", "drive")])

        lay.addStretch(1)
        row = QHBoxLayout()
        row.setSpacing(6)
        row.setAlignment(Qt.AlignmentFlag.AlignBottom)
        row.addStretch(1)
        self.fader = Fader(project.master.get("volume", 0.85))
        self.fader.setMaximumHeight(250)
        self.fader.valueChanged.connect(self._vol)
        self.meter = LevelMeter()
        self.meter.setFixedWidth(17)
        self.meter.setMaximumHeight(250)
        row.addWidget(self.fader)
        row.addWidget(self.meter)
        row.addStretch(1)
        lay.addLayout(row, 1)

    def _set(self, section, key, value):
        self.project.master.setdefault(section, {})[key] = value
        self.changed.emit()

    def _vol(self, v):
        self.project.master["volume"] = v
        self.changed.emit()

    def sync(self):
        for name, k in self.knobs.items():
            section, key = name.split(".", 1)
            v = self.project.master.get(section, {}).get(key)
            if v is not None:
                k.setValue(v, emit=False)
        self.fader.setValue(self.project.master.get("volume", 0.85), emit=False)


class Mixer(QWidget):
    changed = pyqtSignal()
    channelSelected = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.project: Project | None = None
        self.strips: dict[str, ChannelStrip] = {}
        self.master: MasterStrip | None = None

        self.area = QScrollArea()
        self.area.setWidgetResizable(True)
        self.host = QWidget()
        self.row = QHBoxLayout(self.host)
        self.row.setContentsMargins(8, 8, 8, 8)
        self.row.setSpacing(5)
        self.row.addStretch(1)
        self.area.setWidget(self.host)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self.area)

    def set_project(self, project: Project) -> None:
        self.project = project
        self.rebuild()

    def rebuild(self) -> None:
        for s in list(self.strips.values()):
            s.setParent(None)
            s.deleteLater()
        self.strips.clear()
        if self.master is not None:
            self.master.setParent(None)
            self.master.deleteLater()
            self.master = None
        if self.project is None:
            return
        for i, ch in enumerate(self.project.channels):
            s = ChannelStrip(self.project, ch.id)
            s.changed.connect(self._changed)
            s.selected.connect(self.channelSelected)
            self.row.insertWidget(i, s)
            self.strips[ch.id] = s
        self.master = MasterStrip(self.project)
        self.master.changed.connect(self._changed)
        # insert before the trailing stretch so the master strip is never clipped
        self.row.insertWidget(self.row.count() - 1, self.master)

    def _changed(self) -> None:
        self.sync()
        self.changed.emit()

    def sync(self) -> None:
        for s in self.strips.values():
            s.sync()
        if self.master:
            self.master.sync()

    def set_meters(self, meters: dict, master_peak=None) -> None:
        for cid, s in self.strips.items():
            s.meter.set_level(meters.get(cid, 0.0))
        if self.master is not None and master_peak is not None:
            self.master.meter.set_level(float(master_peak[0]), float(master_peak[1]))
