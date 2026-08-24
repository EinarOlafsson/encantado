"""Generator dialog: write chords, arps, basslines, grooves and melodies
into the current pattern from the project's key and a chosen progression."""
from __future__ import annotations

import random

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                             QFormLayout, QHBoxLayout, QLabel, QSpinBox,
                             QVBoxLayout)

from ..core.project import Pattern, Project
from ..core.theory import PROGRESSIONS, note_name
from ..presets import builder as B
from . import theme as T

MODES = ("Chords", "Arpeggio", "Bassline", "Drum Groove", "Melody")
BASS_RHYTHMS = ("offbeat", "eighths", "rolling", "octave", "sustain", "downbeat")


class GenerateDialog(QDialog):
    def __init__(self, project: Project, pattern: Pattern, channel_id: str,
                 parent=None):
        super().__init__(parent)
        self.project = project
        self.pattern = pattern
        self.setWindowTitle("Generate")
        self.setMinimumWidth(430)
        self.setStyleSheet(T.STYLESHEET)

        form = QFormLayout()
        form.setSpacing(8)

        self.mode = QComboBox()
        self.mode.addItems(MODES)
        self.mode.currentIndexChanged.connect(self._sync)
        form.addRow("What", self.mode)

        self.channel = QComboBox()
        for ch in project.channels:
            self.channel.addItem(f"{ch.name}  ·  {ch.instrument}", ch.id)
        i = self.channel.findData(channel_id)
        self.channel.setCurrentIndex(max(i, 0))
        form.addRow("Channel", self.channel)

        self.prog = QComboBox()
        for p in PROGRESSIONS:
            self.prog.addItem(f"{p.name}   ({p.scale.split(' ')[0]})", p.name)
        form.addRow("Progression", self.prog)

        self.bars = QSpinBox()
        self.bars.setRange(1, 16)
        self.bars.setValue(max(1, pattern.length // 16))
        form.addRow("Bars", self.bars)

        self.octave = QSpinBox()
        self.octave.setRange(0, 7)
        self.octave.setValue(3)
        form.addRow("Octave", self.octave)

        self.shape = QComboBox()
        self.shape.addItems(sorted(B.ARP_SHAPES.keys()))
        self.shape.setCurrentText("cascade")
        form.addRow("Arp shape", self.shape)

        self.rate = QComboBox()
        for lbl, v in (("1/16", 1), ("1/8", 2), ("1/4", 4)):
            self.rate.addItem(lbl, v)
        form.addRow("Arp rate", self.rate)

        self.span = QSpinBox()
        self.span.setRange(1, 4)
        self.span.setValue(2)
        form.addRow("Arp octaves", self.span)

        self.rhythm = QComboBox()
        self.rhythm.addItems(BASS_RHYTHMS)
        form.addRow("Bass rhythm", self.rhythm)

        self.seventh = QCheckBox("Add 7ths")
        self.extended = QCheckBox("Add 9ths")
        ext = QHBoxLayout()
        ext.addWidget(self.seventh)
        ext.addWidget(self.extended)
        ext.addStretch(1)
        form.addRow("Colour", ext)

        self.replace = QCheckBox("Replace what is already on the channel")
        self.replace.setChecked(True)
        form.addRow("", self.replace)

        self.key_note = QLabel()
        self.key_note.setObjectName("Faint")
        self.key_note.setWordWrap(True)
        form.addRow("", self.key_note)

        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                               QDialogButtonBox.StandardButton.Cancel)
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)

        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(box)
        self._sync()

    def _sync(self) -> None:
        mode = self.mode.currentText()
        is_arp = mode == "Arpeggio"
        is_bass = mode == "Bassline"
        is_drum = mode == "Drum Groove"
        harmonic = mode in ("Chords", "Arpeggio", "Bassline", "Melody")
        for w in (self.shape, self.rate, self.span):
            w.setEnabled(is_arp)
        self.rhythm.setEnabled(is_bass)
        self.prog.setEnabled(harmonic)
        self.seventh.setEnabled(harmonic and not is_drum)
        self.extended.setEnabled(harmonic and not is_drum)
        self.octave.setEnabled(not is_drum)
        prog = PROGRESSIONS[max(self.prog.currentIndex(), 0)]
        self.key_note.setText(
            f"Key: {note_name(self.project.root + 60)[:-1]} "
            f"{self.project.scale}. {prog.note}")

    # -- apply ---------------------------------------------------------------
    def apply(self) -> None:
        cid = self.channel.currentData()
        if not cid:
            return
        pat, pr = self.pattern, self.project
        bars = min(self.bars.value(), max(1, pat.length // 16))
        if self.replace.isChecked():
            pat.clear_channel(cid)

        mode = self.mode.currentText()
        prog_name = self.prog.currentData()
        chords = B.resolve_progression(prog_name, pr.root, pr.scale, bars,
                                       self.octave.value(),
                                       self.seventh.isChecked(),
                                       self.extended.isChecked())
        if mode == "Chords":
            B.chord_track(pat, cid, chords, 0.75)
        elif mode == "Arpeggio":
            B.arp_track(pat, cid, chords, self.shape.currentText(),
                        self.span.value(), self.rate.currentData(), 0.8)
        elif mode == "Bassline":
            B.bass_track(pat, cid, chords, self.rhythm.currentText(), -24)
        elif mode == "Melody":
            rng = random.Random(pr.root * 97 + bars)
            contour = [0, 2, 4, 3, 5, 4, 2, 1]
            events, step = [], 0
            while step < bars * 16:
                deg = contour[(step // 4) % len(contour)]
                ln = rng.choice((4, 4, 8, 6))
                events.append((step, deg, ln))
                step += ln
            B.melody_track(pat, cid, pr.root, pr.scale, events,
                           self.octave.value() + 2, 0.85)
        else:
            ch = pr.channel(cid)
            inst = ch.instrument if ch else ""
            rng = random.Random(7)
            if inst == "kick":
                B.four_on_floor(pat, cid, bars)
            elif inst in ("clap", "snare"):
                B.backbeat(pat, cid, bars, 0.9)
            elif inst == "hat":
                B.offbeat(pat, cid, bars, 0.6)
            elif inst == "cymbal":
                B.steps_at(pat, cid, (0,), 1, 48, 0.5)
            else:
                B.euclid(pat, cid, bars, 5, 16, 48, 0.55, 2)
        pat.notes[cid] = sorted(pat.notes.get(cid, []),
                                key=lambda n: (n.step, n.pitch))
