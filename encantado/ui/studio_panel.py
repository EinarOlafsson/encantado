"""The generation studio: learn from your audio, then refine by ear.

Deliberately not a render button. You get a population of candidates, you say
which ones are going the right way, and the next population is bred from those.
Locked ones survive untouched, and the macro controls let you steer a direction
the model actually learned from your material.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile

import numpy as np
from PyQt6.QtCore import (QObject, QProcess, QProcessEnvironment, Qt,
                          QThread, pyqtSignal)
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import (QFileDialog, QFrame, QGridLayout, QHBoxLayout,
                             QLabel, QListWidget, QListWidgetItem, QMessageBox,
                             QProgressBar, QPushButton, QScrollArea, QSlider,
                             QSpinBox, QVBoxLayout, QWidget)

from ..audio.wavio import AUDIO_EXTS, write_wav
from . import theme as T

try:
    from ..ai.dataset import build_dataset
    from ..ai.evolve import Studio, Variation
    from ..ai.model import TORCH
    from ..ai.spectral import FEATURE_NAMES
    from ..ai.trainer import GrainModel, TrainConfig
    AI_OK = TORCH
except Exception:                                       # pragma: no cover
    AI_OK = False
    FEATURE_NAMES = ("Brightness", "Length", "Weight", "Noisiness")


class _VocodeWorker(QObject):
    """Phase reconstruction only. Never touches the GPU, so it is safe here."""
    progressed = pyqtSignal(float, str)
    finished = pyqtSignal(str)

    def __init__(self, studio, n_iter=32):
        super().__init__()
        self.studio, self.n_iter = studio, n_iter

    def run(self):
        try:
            self.studio.vocode_all(
                self.n_iter, lambda f, m: (self.progressed.emit(f, m), True)[1])
            self.finished.emit("")
        except Exception as exc:
            self.finished.emit(str(exc))


class WaveView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.audio = None
        self.colour = QColor(T.ACCENT)
        self.setFixedHeight(34)

    def set_audio(self, a):
        self.audio = a
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(T.BG_INPUT))
        if self.audio is None or len(self.audio) < 4:
            p.end(); return
        w, h = self.width(), self.height()
        n = min(w, 400)
        step = max(len(self.audio) // n, 1)
        env = np.abs(self.audio[:step * n].reshape(n, step)).max(axis=1)
        m = float(env.max()) or 1.0
        p.setPen(QPen(self.colour, 1))
        for i in range(n):
            x = i * w / n
            v = env[i] / m * (h / 2 - 2)
            p.drawLine(int(x), int(h / 2 - v), int(x), int(h / 2 + v))
        p.end()


class VariationCard(QFrame):
    play = pyqtSignal(object)
    changed = pyqtSignal()
    add = pyqtSignal(object)

    def __init__(self, var, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.var = var
        v = QVBoxLayout(self)
        v.setContentsMargins(8, 6, 8, 7)
        v.setSpacing(4)
        top = QHBoxLayout()
        self.name = QLabel(var.label)
        self.name.setStyleSheet(f"font-weight:700; color:{T.ACCENT};")
        top.addWidget(self.name)
        top.addStretch(1)
        self.gen = QLabel(f"gen {var.generation}")
        self.gen.setObjectName("Faint")
        top.addWidget(self.gen)
        v.addLayout(top)

        self.wave = WaveView()
        v.addWidget(self.wave)

        row = QHBoxLayout()
        row.setSpacing(4)
        self.b_play = QPushButton("▶")
        self.b_play.setFixedWidth(30)
        self.b_play.clicked.connect(lambda: self.play.emit(self.var))
        self.b_keep = QPushButton("Keep")
        self.b_keep.setCheckable(True)
        self.b_drop = QPushButton("Drop")
        self.b_drop.setCheckable(True)
        self.b_drop.setObjectName("Danger")
        self.b_lock = QPushButton("Lock")
        self.b_lock.setCheckable(True)
        self.b_add = QPushButton("→ Rack")
        self.b_add.setToolTip("Add as a Sampler channel in the project")
        self.b_keep.clicked.connect(self._keep)
        self.b_drop.clicked.connect(self._drop)
        self.b_lock.clicked.connect(self._lock)
        self.b_add.clicked.connect(lambda: self.add.emit(self.var))
        for b in (self.b_play, self.b_keep, self.b_drop, self.b_lock, self.b_add):
            b.setFixedHeight(21)
            row.addWidget(b)
        v.addLayout(row)
        self.sync()

    def _keep(self):
        self.var.rating = 1 if self.b_keep.isChecked() else 0
        self.b_drop.setChecked(False)
        self.sync(); self.changed.emit()

    def _drop(self):
        self.var.rating = -1 if self.b_drop.isChecked() else 0
        self.b_keep.setChecked(False)
        self.sync(); self.changed.emit()

    def _lock(self):
        self.var.locked = self.b_lock.isChecked()
        self.sync(); self.changed.emit()

    def sync(self):
        v = self.var
        self.b_keep.setChecked(v.rating > 0)
        self.b_drop.setChecked(v.rating < 0)
        self.b_lock.setChecked(v.locked)
        col = T.GREEN if v.rating > 0 else (T.ACCENT_2 if v.rating < 0 else T.ACCENT)
        self.name.setStyleSheet(f"font-weight:700; color:{col};")
        self.wave.colour = QColor(col)
        self.wave.set_audio(v.audio)
        self.gen.setText(f"gen {v.generation}")
        self.b_add.setEnabled(v.audio is not None)


class StudioPanel(QWidget):
    previewAudio = pyqtSignal(object)
    addSample = pyqtSignal(object, str)          # (audio, name)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.model = None
        self.studio = None
        self.thread = None
        self.worker = None
        self.proc: QProcess | None = None
        self._model_out = ""
        self._job_file = ""
        self._train_error = ""
        self.cards: list[VariationCard] = []

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        head = QHBoxLayout()
        t = QLabel("Generation studio")
        t.setObjectName("Heading")
        head.addWidget(t)
        head.addStretch(1)
        self.b_load = QPushButton("Load model…")
        self.b_load.clicked.connect(self.load_model)
        self.b_save = QPushButton("Save model…")
        self.b_save.setEnabled(False)
        self.b_save.clicked.connect(self.save_model)
        head.addWidget(self.b_load)
        head.addWidget(self.b_save)
        lay.addLayout(head)

        if not AI_OK:
            warn = QLabel("PyTorch is not available in this environment, so the "
                          "generation studio is disabled. Everything else in "
                          "Encantado works without it.")
            warn.setWordWrap(True)
            warn.setObjectName("Faint")
            lay.addWidget(warn)
            lay.addStretch(1)
            return

        blurb = QLabel(
            "Give it audio and it learns the character of that sound, then "
            "generates new material in the same voice. It learns timbre — hits, "
            "stabs, textures — not arrangements: a handful of files cannot teach "
            "a model to write music. Best results come from a folder of one-shots "
            "or short loops rather than one finished track.")
        blurb.setWordWrap(True)
        blurb.setObjectName("Faint")
        lay.addWidget(blurb)

        src = QHBoxLayout()
        self.files = QListWidget()
        self.files.setMaximumHeight(74)
        src.addWidget(self.files, 1)
        col = QVBoxLayout()
        b_add = QPushButton("Add audio…")
        b_add.clicked.connect(self.choose)
        b_clear = QPushButton("Clear")
        b_clear.clicked.connect(self.files.clear)
        col.addWidget(b_add)
        col.addWidget(b_clear)
        col.addStretch(1)
        src.addLayout(col)
        lay.addLayout(src)

        opts = QHBoxLayout()
        opts.addWidget(QLabel("Training passes"))
        self.epochs = QSpinBox(); self.epochs.setRange(20, 600); self.epochs.setValue(120)
        opts.addWidget(self.epochs)
        opts.addWidget(QLabel("Time limit (s)"))
        self.seconds = QSpinBox(); self.seconds.setRange(20, 1800); self.seconds.setValue(180)
        opts.addWidget(self.seconds)
        self.b_train = QPushButton("Learn from these")
        self.b_train.setObjectName("Primary")
        self.b_train.clicked.connect(self.train)
        opts.addWidget(self.b_train)
        opts.addStretch(1)
        lay.addLayout(opts)

        self.bar = QProgressBar(); self.bar.setVisible(False)
        lay.addWidget(self.bar)
        self.status = QLabel("No model yet.")
        self.status.setObjectName("Faint")
        lay.addWidget(self.status)

        # macro controls
        self.macro_box = QFrame(); self.macro_box.setObjectName("Card")
        mv = QVBoxLayout(self.macro_box)
        mv.setContentsMargins(10, 8, 10, 9); mv.setSpacing(3)
        ml = QLabel("SHAPE  (directions learned from your material)")
        ml.setObjectName("Title"); mv.addWidget(ml)
        self.sliders = []
        for i, name in enumerate(FEATURE_NAMES):
            r = QHBoxLayout()
            lb = QLabel(name); lb.setFixedWidth(78); lb.setObjectName("Dim")
            sl = QSlider(Qt.Orientation.Horizontal)
            sl.setRange(-30, 30); sl.setValue(0)
            val = QLabel("0.0"); val.setFixedWidth(30); val.setObjectName("Faint")
            sl.valueChanged.connect(
                lambda v, k=i, w=val: self._macro(k, v / 10.0, w))
            r.addWidget(lb); r.addWidget(sl, 1); r.addWidget(val)
            mv.addLayout(r)
            self.sliders.append(sl)
        r = QHBoxLayout()
        lb = QLabel("Variation"); lb.setFixedWidth(78); lb.setObjectName("Dim")
        self.mut = QSlider(Qt.Orientation.Horizontal)
        self.mut.setRange(2, 120); self.mut.setValue(35)
        self.mut.valueChanged.connect(
            lambda v: self.studio and setattr(self.studio, "mutation", v / 100.0))
        r.addWidget(lb); r.addWidget(self.mut, 1)
        mv.addLayout(r)
        self.macro_box.setEnabled(False)
        lay.addWidget(self.macro_box)

        acts = QHBoxLayout()
        self.b_gen = QPushButton("Generate")
        self.b_gen.clicked.connect(self.generate)
        self.b_evolve = QPushButton("Evolve from picks")
        self.b_evolve.setObjectName("Primary")
        self.b_evolve.clicked.connect(self.evolve)
        self.b_refresh = QPushButton("Replace unpicked")
        self.b_refresh.clicked.connect(self.refresh_unpicked)
        self.b_export = QPushButton("Export kept…")
        self.b_export.clicked.connect(self.export_kept)
        for b in (self.b_gen, self.b_evolve, self.b_refresh, self.b_export):
            b.setEnabled(False)
            acts.addWidget(b)
        acts.addStretch(1)
        lay.addLayout(acts)

        area = QScrollArea(); area.setWidgetResizable(True)
        host = QWidget()
        self.grid = QGridLayout(host)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(6)
        area.setWidget(host)
        lay.addWidget(area, 1)

    # -- sources -------------------------------------------------------------
    def choose(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Audio to learn from", "",
            "Audio (" + " ".join(f"*{e}" for e in AUDIO_EXTS) + ");;All files (*)")
        self.add_paths(paths)

    def add_paths(self, paths):
        for p in paths:
            if os.path.isdir(p):
                for root, _d, fs in os.walk(p):
                    for f in fs:
                        if f.lower().endswith(AUDIO_EXTS):
                            self._add_one(os.path.join(root, f))
            elif p.lower().endswith(AUDIO_EXTS):
                self._add_one(p)

    def _add_one(self, path):
        it = QListWidgetItem(os.path.basename(path))
        it.setData(Qt.ItemDataRole.UserRole, path)
        it.setToolTip(path)
        self.files.addItem(it)

    def _paths(self):
        return [self.files.item(i).data(Qt.ItemDataRole.UserRole)
                for i in range(self.files.count())]

    # -- training ------------------------------------------------------------
    def train(self):
        paths = self._paths()
        if not paths:
            QMessageBox.information(self, "Nothing to learn from",
                                    "Add some audio files first.")
            return
        if self.proc is not None or self.thread is not None:
            return
        self._model_out = tempfile.mktemp(suffix=".ecm")
        job = {"paths": paths, "epochs": self.epochs.value(),
               "seconds": self.seconds.value(), "out": self._model_out}
        self._job_file = tempfile.mktemp(suffix=".json")
        with open(self._job_file, "w", encoding="utf-8") as fh:
            json.dump(job, fh)
        self.bar.setVisible(True); self.bar.setValue(0)
        self.b_train.setEnabled(False)
        self.status.setText("starting training process…")
        self.proc = QProcess(self)
        self.proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.proc.readyReadStandardOutput.connect(self._proc_output)
        self.proc.finished.connect(self._proc_finished)
        # Put the directory containing the package on PYTHONPATH rather than
        # relying on the working directory. That resolves `-m` both when running
        # from a source checkout and when Encantado is installed as a package.
        env = QProcessEnvironment.systemEnvironment()
        pkg_parent = os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))))
        existing = env.value("PYTHONPATH", "")
        env.insert("PYTHONPATH",
                   pkg_parent + (os.pathsep + existing if existing else ""))
        self.proc.setProcessEnvironment(env)
        self.proc.start(sys.executable,
                        ["-u", "-m", "encantado.ai.train_job", self._job_file])

    def _proc_output(self):
        if self.proc is None:
            return
        text = bytes(self.proc.readAllStandardOutput()).decode("utf-8", "replace")
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("PROGRESS"):
                parts = line.split(" ", 2)
                try:
                    self._progress(float(parts[1]), parts[2] if len(parts) > 2 else "")
                except (ValueError, IndexError):
                    pass
            elif line.startswith("ERROR"):
                self._train_error = line[6:]
            elif line.startswith("DONE"):
                self._train_error = ""

    def _proc_finished(self, code, _status):
        proc = self.proc
        self.proc = None
        self.bar.setVisible(False)
        self.b_train.setEnabled(True)
        for f in (getattr(self, "_job_file", None),):
            if f and os.path.exists(f):
                try:
                    os.unlink(f)
                except OSError:
                    pass
        if code != 0 or not os.path.exists(self._model_out or ""):
            self.status.setText(
                f"Training failed: {getattr(self, '_train_error', '') or 'process exited ' + str(code)}")
            return
        try:
            model = GrainModel.load(self._model_out)
        except Exception as exc:
            self.status.setText(f"Could not load the trained model: {exc}")
            return
        try:
            os.unlink(self._model_out)
        except OSError:
            pass
        self._trained(model, "")

    def _progress(self, f, msg):
        self.bar.setValue(int(f * 100))
        self.status.setText(msg)

    def _end_thread(self):
        if self.thread:
            self.thread.quit(); self.thread.wait(3000)
        self.thread = None; self.worker = None

    def _trained(self, model, err):
        self._end_thread()
        self.bar.setVisible(False)
        self.b_train.setEnabled(True)
        if model is None:
            self.status.setText(f"Training failed: {err}")
            return
        self.model = model
        self.studio = Studio(model, size=8)
        self.studio.seed()
        self.macro_box.setEnabled(True)
        self.b_save.setEnabled(True)
        for b in (self.b_gen, self.b_evolve, self.b_refresh, self.b_export):
            b.setEnabled(True)
        self.status.setText(
            f"Learned from {model.n_grains} grains of {len(model.sources)} file(s). "
            f"{model.active_dims} useful dimensions. Reconstruction "
            f"{model.history[-1]:.0f}.")
        self._render()

    # -- population ----------------------------------------------------------
    def _macro(self, index, value, label):
        label.setText(f"{value:+.1f}")
        if self.studio:
            self.studio.set_macro(index, value)

    def generate(self):
        if not self.studio:
            return
        self.studio.seed()
        self._render()

    def evolve(self):
        if not self.studio:
            return
        self.studio.evolve()
        self._render()

    def refresh_unpicked(self):
        if not self.studio:
            return
        self.studio.refresh()
        self._render()

    def _render(self):
        if not self.studio or self.thread is not None:
            return
        self.bar.setVisible(True); self.bar.setValue(0)
        try:
            # decoding runs here on the main thread: CUDA in a Qt worker thread
            # brings the whole process down
            self.studio.decode_all()
        except Exception as exc:
            self.bar.setVisible(False)
            self.status.setText(f"Decode failed: {exc}")
            return
        self.thread = QThread(self)
        self.worker = _VocodeWorker(self.studio, 32)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.progressed.connect(
            lambda f, m: (self.bar.setValue(int(f * 100)),
                          self.status.setText(f"rendering {m}…")))
        self.worker.finished.connect(self._rendered)
        self.thread.start()

    def _rendered(self, err):
        self._end_thread()
        self.bar.setVisible(False)
        if err:
            self.status.setText(f"Render failed: {err}")
            return
        self.status.setText(
            f"Generation {self.studio.generation}. Keep the ones going the right "
            f"way, drop the ones that aren't, then evolve.")
        self._rebuild_cards()

    def _rebuild_cards(self):
        for c in self.cards:
            c.setParent(None); c.deleteLater()
        self.cards.clear()
        if not self.studio:
            return
        for i, v in enumerate(self.studio.population):
            card = VariationCard(v)
            card.play.connect(lambda var: self.previewAudio.emit(var.audio))
            card.add.connect(self._add_to_rack)
            self.grid.addWidget(card, i // 2, i % 2)
            self.cards.append(card)

    def _add_to_rack(self, var):
        if var.audio is not None:
            self.addSample.emit(var.audio, f"AI {var.label}")

    # -- io ------------------------------------------------------------------
    def export_kept(self):
        if not self.studio:
            return
        kept = [v for v in self.studio.population if v.liked and v.audio is not None]
        if not kept:
            QMessageBox.information(self, "Nothing kept",
                                    "Mark some variations as Keep first.")
            return
        folder = QFileDialog.getExistingDirectory(self, "Export kept variations to")
        if not folder:
            return
        for v in kept:
            write_wav(os.path.join(folder, f"encantado_{v.label}.wav"),
                      np.stack([v.audio] * 2, axis=-1))
        self.status.setText(f"Exported {len(kept)} WAV files.")

    def save_model(self):
        if not self.model:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save model", "model.ecm",
                                              "Encantado model (*.ecm)")
        if path:
            self.model.save(path)
            self.status.setText(f"Saved {os.path.basename(path)}")

    def load_model(self):
        if not AI_OK:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Load model", "",
                                              "Encantado model (*.ecm *.pt)")
        if not path:
            return
        try:
            self.model = GrainModel.load(path)
        except Exception as exc:
            QMessageBox.critical(self, "Could not load", str(exc))
            return
        self.studio = Studio(self.model, size=8)
        self.studio.seed()
        self.macro_box.setEnabled(True)
        self.b_save.setEnabled(True)
        for b in (self.b_gen, self.b_evolve, self.b_refresh, self.b_export):
            b.setEnabled(True)
        self.status.setText(f"Loaded {os.path.basename(path)}")
        self._render()
