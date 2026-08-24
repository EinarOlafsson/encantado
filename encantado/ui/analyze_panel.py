"""Drop tracks in, get a song recipe out."""
from __future__ import annotations

import os

import numpy as np
from PyQt6.QtCore import QObject, Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import (QFileDialog, QFrame, QHBoxLayout, QLabel,
                             QListWidget, QListWidgetItem, QProgressBar,
                             QPushButton, QScrollArea, QSizePolicy, QVBoxLayout,
                             QWidget)

from ..analysis.recipe import SongRecipe, analyse, recipe_to_project
from ..analysis.separate import ROLE_BANDS
from ..audio.wavio import AUDIO_EXTS
from . import theme as T

ROLE_ORDER = ("Kick", "Tom", "Perc", "Snare", "Hat")


class _Worker(QObject):
    progressed = pyqtSignal(float, str)
    finished = pyqtSignal(object, str)

    def __init__(self, path: str):
        super().__init__()
        self.path = path
        self.cancelled = False

    def run(self):
        try:
            rec = analyse(self.path,
                          progress=lambda f, m: (self.progressed.emit(f, m),
                                                 not self.cancelled)[1])
            self.finished.emit(rec, "")
        except Exception as exc:
            self.finished.emit(None, str(exc))


class GrooveView(QWidget):
    """16-step heat map of transient energy per band."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.groove: dict[str, np.ndarray] = {}
        self.threshold = 0.8
        self.setMinimumHeight(len(ROLE_ORDER) * 22 + 26)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_groove(self, groove: dict) -> None:
        self.groove = groove or {}
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        left = 54
        cw = max((w - left - 6) / 16.0, 4.0)
        p.setPen(QColor(T.TEXT_DIM))
        f = p.font(); f.setPointSizeF(7.4); p.setFont(f)
        for c in range(16):
            if c % 4 == 0:
                p.drawText(int(left + c * cw) + 2, 11, str(c // 4 + 1))
        for r, role in enumerate(ROLE_ORDER):
            y = 16 + r * 22
            p.setPen(QColor(T.TEXT_DIM))
            p.drawText(2, y + 14, role)
            prof = self.groove.get(role)
            for c in range(16):
                x = left + c * cw
                v = float(prof[c]) if prof is not None and c < len(prof) else 0.0
                m = float(prof.max()) if prof is not None and prof.max() > 0 else 1.0
                rel = v / m
                col = QColor(T.ACCENT)
                col.setAlpha(int(28 + 210 * rel ** 2))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(col)
                p.drawRoundedRect(int(x) + 1, y + 2, int(cw) - 2, 17, 3, 3)
                if rel >= self.threshold:
                    p.setPen(QColor(T.TEXT))
                    p.setBrush(Qt.BrushStyle.NoBrush)
                    p.drawRoundedRect(int(x) + 1, y + 2, int(cw) - 2, 17, 3, 3)
        p.end()


class AnalyzePanel(QWidget):
    recipeReady = pyqtSignal(object)
    createProject = pyqtSignal(object)
    sendHits = pyqtSignal(object)
    previewAudio = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.recipe: SongRecipe | None = None
        self.thread: QThread | None = None
        self.worker: _Worker | None = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        head = QHBoxLayout()
        title = QLabel("Analyse a track")
        title.setObjectName("Heading")
        head.addWidget(title)
        head.addStretch(1)
        self.add_btn = QPushButton("Choose audio…")
        self.add_btn.setObjectName("Primary")
        self.add_btn.clicked.connect(self.choose)
        head.addWidget(self.add_btn)
        lay.addLayout(head)

        blurb = QLabel(
            "Drop one or more audio files here. Encantado finds the tempo, key, "
            "chords and arrangement, splits the mix into drums / bass / melodic "
            "layers, cuts out the individual drum hits, and builds an editable "
            "project from what it heard.")
        blurb.setWordWrap(True)
        blurb.setObjectName("Faint")
        lay.addWidget(blurb)

        self.files = QListWidget()
        self.files.setMaximumHeight(84)
        self.files.itemDoubleClicked.connect(lambda i: self.analyse_path(
            i.data(Qt.ItemDataRole.UserRole)))
        lay.addWidget(self.files)

        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setVisible(False)
        lay.addWidget(self.bar)
        self.status = QLabel("")
        self.status.setObjectName("Faint")
        lay.addWidget(self.status)

        area = QScrollArea()
        area.setWidgetResizable(True)
        host = QWidget()
        self.res = QVBoxLayout(host)
        self.res.setContentsMargins(0, 0, 0, 0)
        self.res.setSpacing(8)
        self.res.addStretch(1)
        area.setWidget(host)
        lay.addWidget(area, 1)

        row = QHBoxLayout()
        self.btn_project = QPushButton("Build project from this")
        self.btn_project.setObjectName("Primary")
        self.btn_project.setEnabled(False)
        self.btn_project.clicked.connect(
            lambda: self.recipe and self.createProject.emit(self.recipe))
        self.btn_hits = QPushButton("Send one-shots to Library")
        self.btn_hits.setEnabled(False)
        self.btn_hits.clicked.connect(
            lambda: self.recipe and self.sendHits.emit(self.recipe))
        row.addWidget(self.btn_project)
        row.addWidget(self.btn_hits)
        row.addStretch(1)
        lay.addLayout(row)

    # -- files ---------------------------------------------------------------
    def choose(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Choose audio to analyse", "",
            "Audio (" + " ".join(f"*{e}" for e in AUDIO_EXTS) + ");;All files (*)")
        self.add_paths(paths)

    def add_paths(self, paths: list[str]) -> None:
        added = None
        for p in paths:
            if not p.lower().endswith(AUDIO_EXTS):
                continue
            it = QListWidgetItem(os.path.basename(p))
            it.setData(Qt.ItemDataRole.UserRole, p)
            it.setToolTip(p)
            self.files.addItem(it)
            added = added or p
        if added and self.thread is None:
            self.analyse_path(added)

    # -- run -----------------------------------------------------------------
    def analyse_path(self, path: str) -> None:
        if self.thread is not None or not path:
            return
        self.bar.setVisible(True)
        self.bar.setValue(0)
        self.add_btn.setEnabled(False)
        self.status.setText(f"Analysing {os.path.basename(path)}…")
        self.thread = QThread(self)
        self.worker = _Worker(path)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.progressed.connect(self._progress)
        self.worker.finished.connect(self._done)
        self.thread.start()

    def _progress(self, frac: float, msg: str) -> None:
        self.bar.setValue(int(frac * 100))
        self.status.setText(msg)

    def _done(self, rec, err: str) -> None:
        if self.thread:
            self.thread.quit()
            self.thread.wait(2000)
        self.thread = None
        self.worker = None
        self.bar.setVisible(False)
        self.add_btn.setEnabled(True)
        if rec is None:
            self.status.setText(f"Could not analyse that: {err}")
            return
        self.recipe = rec
        self.status.setText("Done.")
        self.btn_project.setEnabled(True)
        self.btn_hits.setEnabled(bool(rec.hits))
        self.show_recipe(rec)
        self.recipeReady.emit(rec)

    # -- results -------------------------------------------------------------
    def _clear(self):
        while self.res.count():
            it = self.res.takeAt(0)
            w = it.widget()
            if w:
                w.setParent(None)
                w.deleteLater()

    def show_recipe(self, rec: SongRecipe) -> None:
        self._clear()

        card = QFrame(); card.setObjectName("Card")
        v = QVBoxLayout(card); v.setContentsMargins(10, 8, 10, 10); v.setSpacing(4)
        lb = QLabel("WHAT IT HEARD"); lb.setObjectName("Title"); v.addWidget(lb)
        for k, val in rec.summary():
            row = QHBoxLayout()
            a = QLabel(k); a.setObjectName("Dim"); a.setFixedWidth(96)
            b = QLabel(str(val)); b.setWordWrap(True)
            b.setStyleSheet(f"color:{T.ACCENT}; font-weight:600;")
            row.addWidget(a); row.addWidget(b, 1)
            v.addLayout(row)
        self.res.addWidget(card)

        gcard = QFrame(); gcard.setObjectName("Card")
        gv = QVBoxLayout(gcard); gv.setContentsMargins(10, 8, 10, 10); gv.setSpacing(4)
        gl = QLabel("GROOVE  (transient energy per band, 16ths)")
        gl.setObjectName("Title"); gv.addWidget(gl)
        gview = GrooveView(); gview.set_groove(rec.groove); gv.addWidget(gview)
        conf = QLabel(f"Groove confidence {rec.groove_confidence * 100:.0f}%. "
                      "Outlined cells are what gets written into the pattern.")
        conf.setObjectName("Faint"); conf.setWordWrap(True); gv.addWidget(conf)
        self.res.addWidget(gcard)

        if rec.notes:
            ncard = QFrame(); ncard.setObjectName("Card")
            nv = QVBoxLayout(ncard); nv.setContentsMargins(10, 8, 10, 10); nv.setSpacing(3)
            nl = QLabel("NOTES"); nl.setObjectName("Title"); nv.addWidget(nl)
            for n in rec.notes:
                t = QLabel("• " + n); t.setWordWrap(True); t.setObjectName("Faint")
                nv.addWidget(t)
            self.res.addWidget(ncard)

        if rec.hits:
            hcard = QFrame(); hcard.setObjectName("Card")
            hv = QVBoxLayout(hcard); hv.setContentsMargins(10, 8, 10, 10); hv.setSpacing(4)
            hl = QLabel("ONE-SHOTS FOUND"); hl.setObjectName("Title"); hv.addWidget(hl)
            for role, shots in rec.hits.items():
                row = QHBoxLayout(); row.setSpacing(5)
                nm = QLabel(f"{role} ×{len(shots)}"); nm.setFixedWidth(96)
                row.addWidget(nm)
                for i, h in enumerate(shots[:4]):
                    b = QPushButton(f"▶ {i + 1}")
                    b.setObjectName("Mini"); b.setFixedSize(34, 20)
                    b.clicked.connect(lambda _, a=h.audio: self.previewAudio.emit(a))
                    row.addWidget(b)
                row.addStretch(1)
                hv.addLayout(row)
            self.res.addWidget(hcard)

        if rec.stems:
            scard = QFrame(); scard.setObjectName("Card")
            sv = QVBoxLayout(scard); sv.setContentsMargins(10, 8, 10, 10); sv.setSpacing(4)
            sl = QLabel("STEMS"); sl.setObjectName("Title"); sv.addWidget(sl)
            row = QHBoxLayout()
            for nm, audio in rec.stems.as_dict().items():
                b = QPushButton(f"▶ {nm}")
                b.clicked.connect(lambda _, a=audio: self.previewAudio.emit(a))
                row.addWidget(b)
            row.addStretch(1)
            sv.addLayout(row)
            note = QLabel("Split by harmonic/percussive median filtering, not a "
                          "trained separator — expect bleed between layers.")
            note.setObjectName("Faint"); note.setWordWrap(True); sv.addWidget(note)
            self.res.addWidget(scard)

        self.res.addStretch(1)
