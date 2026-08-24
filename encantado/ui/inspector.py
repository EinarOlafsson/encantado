"""Instrument inspector: every parameter of the selected channel."""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (QComboBox, QFileDialog, QFrame, QGridLayout,
                             QHBoxLayout, QLabel, QMenu, QPushButton,
                             QScrollArea, QVBoxLayout, QWidget)

from ..core.project import Project, instrument_spec
from ..dsp.drums import DRUMS
from ..dsp.effects import EFFECTS
from ..dsp.instruments import INSTRUMENTS
from ..dsp.params import Param, defaults_for
from . import theme as T
from .widgets import Knob

COLS = 5
SC_PARAMS = (
    Param("sc_amount", "Duck", 0.0, 1.0, 0.0, "%", "lin"),
    Param("sc_release", "Release", 0.02, 1.2, 0.28, "ms", "log"),
    Param("sc_shape", "Shape", 0.3, 5.0, 1.8, "", "lin"),
)


def _group_box(title: str) -> tuple[QFrame, QGridLayout]:
    card = QFrame()
    card.setObjectName("Card")
    v = QVBoxLayout(card)
    v.setContentsMargins(8, 6, 8, 8)
    v.setSpacing(4)
    lb = QLabel(title.upper())
    lb.setObjectName("Title")
    v.addWidget(lb)
    grid = QGridLayout()
    grid.setSpacing(1)
    v.addLayout(grid)
    return card, grid


class FXCard(QFrame):
    changed = pyqtSignal()
    removeRequested = pyqtSignal(int)

    def __init__(self, spec: dict, index: int, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.spec = spec
        self.index = index
        cls = EFFECTS.get(spec.get("type", ""))
        v = QVBoxLayout(self)
        v.setContentsMargins(8, 6, 8, 8)
        v.setSpacing(4)

        head = QHBoxLayout()
        head.setSpacing(5)
        lb = QLabel((cls.NAME if cls else spec.get("type", "?")).upper())
        lb.setObjectName("Title")
        self.btn_on = QPushButton("On")
        self.btn_on.setCheckable(True)
        self.btn_on.setChecked(bool(spec.get("enabled", True)))
        self.btn_on.setFixedSize(34, 18)
        self.btn_on.toggled.connect(self._toggle)
        btn_x = QPushButton("✕")
        btn_x.setFixedSize(18, 18)
        btn_x.setObjectName("Ghost")
        btn_x.clicked.connect(lambda: self.removeRequested.emit(self.index))
        head.addWidget(lb)
        head.addStretch(1)
        head.addWidget(self.btn_on)
        head.addWidget(btn_x)
        v.addLayout(head)

        grid = QGridLayout()
        grid.setSpacing(1)
        v.addLayout(grid)
        params = spec.setdefault("params", {})
        if cls:
            for i, prm in enumerate(cls.PARAMS):
                val = params.get(prm.key, prm.default)
                params.setdefault(prm.key, val)
                k = Knob(prm, val, T.ACCENT_4)
                k.valueChanged.connect(lambda vv, key=prm.key: self._set(key, vv))
                grid.addWidget(k, i // COLS, i % COLS)

    def _set(self, key, value):
        self.spec["params"][key] = value
        self.changed.emit()

    def _toggle(self, on):
        self.spec["enabled"] = bool(on)
        self.changed.emit()


class Inspector(QWidget):
    changed = pyqtSignal()
    structureChanged = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.project: Project | None = None
        self.cid = ""
        self._building = False

        self.area = QScrollArea()
        self.area.setWidgetResizable(True)
        self.host = QWidget()
        self.lay = QVBoxLayout(self.host)
        self.lay.setContentsMargins(8, 8, 8, 8)
        self.lay.setSpacing(6)
        self.lay.addStretch(1)
        self.area.setWidget(self.host)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self.area)

    def set_project(self, project: Project) -> None:
        self.project = project
        self.cid = ""
        self.build()

    def set_channel(self, cid: str) -> None:
        if cid != self.cid:
            self.cid = cid
            self.build()

    def _clear(self) -> None:
        while self.lay.count():
            item = self.lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

    def build(self) -> None:
        self._building = True
        self._clear()
        ch = self.project.channel(self.cid) if self.project else None
        if ch is None:
            lb = QLabel("Select a channel")
            lb.setObjectName("Dim")
            lb.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.lay.addWidget(lb)
            self.lay.addStretch(1)
            self._building = False
            return

        spec = instrument_spec(ch.instrument)

        head = QFrame()
        head.setObjectName("Card")
        hv = QVBoxLayout(head)
        hv.setContentsMargins(8, 7, 8, 8)
        hv.setSpacing(5)
        name = QLabel(ch.name)
        name.setObjectName("Heading")
        name.setStyleSheet(f"color:{ch.color}; font-weight:800;")
        hv.addWidget(name)

        row = QHBoxLayout()
        row.setSpacing(6)
        self.inst_box = QComboBox()
        for key, sp in list(INSTRUMENTS.items()) + list(DRUMS.items()):
            self.inst_box.addItem(f"{sp['name']}  ·  {sp['category']}", key)
        i = self.inst_box.findData(ch.instrument)
        self.inst_box.setCurrentIndex(max(i, 0))
        self.inst_box.currentIndexChanged.connect(self._change_instrument)
        row.addWidget(self.inst_box, 1)
        hv.addLayout(row)

        if spec:
            blurb = QLabel(spec.get("blurb", ""))
            blurb.setObjectName("Faint")
            blurb.setWordWrap(True)
            hv.addWidget(blurb)

        if ch.instrument == "sampler":
            btn = QPushButton(ch.sample_path.rsplit("/", 1)[-1] or "Load WAV…")
            btn.clicked.connect(self._load_sample)
            hv.addWidget(btn)
        self.lay.addWidget(head)

        # instrument parameters, grouped as the synth defines them
        if spec:
            groups: dict[str, list[Param]] = {}
            for prm in spec["params"]:
                groups.setdefault(prm.group, []).append(prm)
            for title, prms in groups.items():
                card, grid = _group_box(title)
                for i, prm in enumerate(prms):
                    val = ch.params.get(prm.key, prm.default)
                    k = Knob(prm, val, ch.color)
                    k.valueChanged.connect(
                        lambda v, key=prm.key: self._set_param(key, v))
                    grid.addWidget(k, i // COLS, i % COLS)
                self.lay.addWidget(card)

        # sidechain
        card, grid = _group_box("Sidechain")
        for i, prm in enumerate(SC_PARAMS):
            k = Knob(prm, getattr(ch, prm.key, prm.default), T.ACCENT_2)
            k.valueChanged.connect(lambda v, key=prm.key: self._set_attr(key, v))
            grid.addWidget(k, 0, i)
        kick_btn = QPushButton("Trigger source")
        kick_btn.setCheckable(True)
        kick_btn.setChecked(ch.is_kick_source)
        kick_btn.setToolTip("Notes on this channel fire the sidechain ducking")
        kick_btn.toggled.connect(self._set_kick)
        grid.addWidget(kick_btn, 1, 0, 1, COLS)
        self.lay.addWidget(card)

        # insert effects
        fx_card = QFrame()
        fx_card.setObjectName("Card")
        fv = QVBoxLayout(fx_card)
        fv.setContentsMargins(8, 6, 8, 8)
        fv.setSpacing(4)
        fh = QHBoxLayout()
        lb = QLabel("INSERT FX")
        lb.setObjectName("Title")
        add = QPushButton("+ Add")
        add.setFixedHeight(20)
        add.clicked.connect(self._add_fx_menu)
        fh.addWidget(lb)
        fh.addStretch(1)
        fh.addWidget(add)
        fv.addLayout(fh)
        self.lay.addWidget(fx_card)

        for i, fx_spec in enumerate(ch.fx):
            card = FXCard(fx_spec, i)
            card.changed.connect(self.changed)
            card.removeRequested.connect(self._remove_fx)
            self.lay.addWidget(card)

        self.lay.addStretch(1)
        self._building = False

    # -- edits ---------------------------------------------------------------
    def _ch(self):
        return self.project.channel(self.cid) if self.project else None

    def _set_param(self, key: str, value: float) -> None:
        ch = self._ch()
        if ch is not None and not self._building:
            ch.params[key] = value
            self.changed.emit()

    def _set_attr(self, key: str, value: float) -> None:
        ch = self._ch()
        if ch is not None and not self._building:
            setattr(ch, key, value)
            self.changed.emit()

    def _set_kick(self, on: bool) -> None:
        ch = self._ch()
        if ch is not None and not self._building:
            ch.is_kick_source = bool(on)
            self.changed.emit()

    def _change_instrument(self) -> None:
        if self._building:
            return
        ch = self._ch()
        key = self.inst_box.currentData()
        if ch is None or key == ch.instrument:
            return
        spec = instrument_spec(key)
        ch.instrument = key
        ch.params = defaults_for(spec["params"])
        self.build()
        self.structureChanged.emit()

    def _add_fx_menu(self) -> None:
        menu = QMenu(self)
        for key, cls in EFFECTS.items():
            menu.addAction(cls.NAME, lambda k=key: self._add_fx(k))
        menu.exec(self.cursor().pos())

    def _add_fx(self, key: str) -> None:
        ch = self._ch()
        if ch is None:
            return
        cls = EFFECTS[key]
        ch.fx.append({"type": key, "enabled": True,
                      "params": {p.key: p.default for p in cls.PARAMS}})
        self.build()
        self.changed.emit()

    def _remove_fx(self, index: int) -> None:
        ch = self._ch()
        if ch is None or not (0 <= index < len(ch.fx)):
            return
        ch.fx.pop(index)
        self.build()
        self.changed.emit()

    def _load_sample(self) -> None:
        ch = self._ch()
        if ch is None:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Load sample", "",
                                              "WAV files (*.wav);;All files (*)")
        if not path:
            return
        from ..audio.wavio import read_wav
        try:
            buf, _sr = read_wav(path)
        except Exception as exc:
            QLabel(f"Could not read: {exc}")
            return
        ch.sample_path = path
        ch.params["_buffer"] = buf
        self.build()
        self.changed.emit()
