"""Main window: wires the panels, the engine and the audio backend together."""
from __future__ import annotations

import os

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import (QApplication, QComboBox, QDialog, QDialogButtonBox,
                             QFileDialog, QFormLayout, QHBoxLayout, QLabel,
                             QMainWindow, QMenu, QMessageBox, QProgressDialog,
                             QPushButton, QSplitter, QStackedWidget, QVBoxLayout,
                             QWidget)

from ..audio.backend import AudioBackend
from ..audio.wavio import write_wav
from ..core.project import Project
from ..dsp.engine import Engine
from ..presets.templates import by_key, empty_project
from . import theme as T
from .browser import Browser
from .channel_rack import ChannelRack
from .generate import GenerateDialog
from .inspector import Inspector
from .mixer import Mixer
from .piano_roll import PianoRoll
from .playlist import Playlist
from .transport import Transport

APP_NAME = "Encantado"
FILE_FILTER = "Encantado project (*.ecp);;All files (*)"

# tracker-style keyboard: two rows spanning two octaves
KEY_MAP = {
    Qt.Key.Key_Z: 0, Qt.Key.Key_S: 1, Qt.Key.Key_X: 2, Qt.Key.Key_D: 3,
    Qt.Key.Key_C: 4, Qt.Key.Key_V: 5, Qt.Key.Key_G: 6, Qt.Key.Key_B: 7,
    Qt.Key.Key_H: 8, Qt.Key.Key_N: 9, Qt.Key.Key_J: 10, Qt.Key.Key_M: 11,
    Qt.Key.Key_Q: 12, Qt.Key.Key_2: 13, Qt.Key.Key_W: 14, Qt.Key.Key_3: 15,
    Qt.Key.Key_E: 16, Qt.Key.Key_R: 17, Qt.Key.Key_5: 18, Qt.Key.Key_T: 19,
    Qt.Key.Key_6: 20, Qt.Key.Key_Y: 21, Qt.Key.Key_7: 22, Qt.Key.Key_U: 23,
}


class AudioSettings(QDialog):
    def __init__(self, backend: AudioBackend, parent=None):
        super().__init__(parent)
        self.backend = backend
        self.setWindowTitle("Audio settings")
        self.setStyleSheet(T.STYLESHEET)
        self.setMinimumWidth(400)
        form = QFormLayout()
        self.device = QComboBox()
        devices = AudioBackend.output_devices()
        for d in devices:
            self.device.addItem(d.description(), d)
        form.addRow("Output", self.device)
        self.buffer = QComboBox()
        for frames in (256, 512, 1024, 2048, 4096):
            self.buffer.addItem(f"{frames} frames  ({frames / 44.1:.0f} ms)", frames)
        i = self.buffer.findData(backend.buffer_frames)
        self.buffer.setCurrentIndex(i if i >= 0 else 3)
        form.addRow("Buffer", self.buffer)
        note = QLabel("A smaller buffer responds faster but can crackle if the "
                      "machine is busy.")
        note.setObjectName("Faint")
        note.setWordWrap(True)
        form.addRow("", note)
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                               QDialogButtonBox.StandardButton.Cancel)
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(box)

    def apply(self) -> bool:
        return self.backend.start(self.device.currentData(),
                                  self.buffer.currentData())


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1620, 960)
        self.setMinimumSize(1120, 700)

        self.project = by_key("melodic").build()
        self.engine = Engine(self.project)
        self.engine.current_pattern = self.project.patterns[0].id
        self.backend = AudioBackend(self.engine)
        self.path: str | None = None
        self.dirty = False
        self._undo: list[dict] = []
        self._held: dict[int, int] = {}
        self.key_octave = 4

        self._build_ui()
        self._build_menu()
        self._connect()
        self.load_project(self.project, reset_path=True)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(33)

        QTimer.singleShot(120, self._start_audio)

    # -- construction --------------------------------------------------------
    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("Root")
        outer = QVBoxLayout(root)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(8)

        self.transport = Transport()
        outer.addWidget(self.transport)

        self.tabs_bar = QHBoxLayout()
        self.tabs_bar.setContentsMargins(0, 0, 0, 0)
        self.tabs_bar.setSpacing(2)
        self.tab_buttons: list[QPushButton] = []
        for i, name in enumerate(("Channel Rack", "Piano Roll", "Playlist", "Mixer")):
            b = QPushButton(name)
            b.setObjectName("Tab")
            b.setCheckable(True)
            b.clicked.connect(lambda _, k=i: self.show_tab(k))
            self.tabs_bar.addWidget(b)
            self.tab_buttons.append(b)
        self.tabs_bar.addStretch(1)
        self.gen_btn = QPushButton("Generate…")
        self.gen_btn.setToolTip("Write chords, arps, basslines or grooves (Ctrl+G)")
        self.gen_btn.clicked.connect(self.open_generate)
        self.tabs_bar.addWidget(self.gen_btn)

        self.rack = ChannelRack()
        self.roll = PianoRoll()
        self.playlist = Playlist()
        self.mixer = Mixer()
        self.stack = QStackedWidget()
        for w in (self.rack, self.roll, self.playlist, self.mixer):
            holder = QWidget()
            holder.setObjectName("Panel")
            hl = QVBoxLayout(holder)
            hl.setContentsMargins(1, 1, 1, 1)
            hl.addWidget(w)
            self.stack.addWidget(holder)

        centre = QWidget()
        cl = QVBoxLayout(centre)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(4)
        cl.addLayout(self.tabs_bar)
        cl.addWidget(self.stack, 1)

        self.browser = Browser()
        bwrap = QWidget()
        bwrap.setObjectName("Panel")
        bl = QVBoxLayout(bwrap)
        bl.setContentsMargins(1, 1, 1, 1)
        bl.addWidget(self.browser)

        self.inspector = Inspector()
        iwrap = QWidget()
        iwrap.setObjectName("Panel")
        il = QVBoxLayout(iwrap)
        il.setContentsMargins(1, 1, 1, 1)
        il.addWidget(self.inspector)

        split = QSplitter(Qt.Orientation.Horizontal)
        split.addWidget(bwrap)
        split.addWidget(centre)
        split.addWidget(iwrap)
        split.setSizes([248, 1040, 330])
        split.setStretchFactor(1, 1)
        outer.addWidget(split, 1)

        self.setCentralWidget(root)
        self.status = self.statusBar()
        self.status.showMessage("Ready")
        self.show_tab(0)

    def _build_menu(self) -> None:
        m = self.menuBar()
        f = m.addMenu("&File")
        self._act(f, "&New", "Ctrl+N", self.new_project)
        self._act(f, "&Open…", "Ctrl+O", self.open_project)
        f.addSeparator()
        self._act(f, "&Save", "Ctrl+S", self.save_project)
        self._act(f, "Save &As…", "Ctrl+Shift+S", lambda: self.save_project(True))
        f.addSeparator()
        self._act(f, "&Export WAV…", "Ctrl+E", self.export_wav)
        f.addSeparator()
        self._act(f, "&Quit", "Ctrl+Q", self.close)

        e = m.addMenu("&Edit")
        self._act(e, "&Undo", "Ctrl+Z", self.undo)
        e.addSeparator()
        self._act(e, "&Generate…", "Ctrl+G", self.open_generate)
        self._act(e, "Clear pattern", "", self.clear_pattern)

        v = m.addMenu("&View")
        for i, name in enumerate(("Channel Rack", "Piano Roll", "Playlist", "Mixer")):
            self._act(v, name, f"F{i + 1}", lambda k=i: self.show_tab(k))

        a = m.addMenu("&Audio")
        self._act(a, "Settings…", "", self.audio_settings)
        self._act(a, "Restart engine", "", self._start_audio)
        self._act(a, "Panic — all notes off", "Esc", self.panic)

        h = m.addMenu("&Help")
        self._act(h, "Shortcuts", "", self.show_help)

    def _act(self, menu: QMenu, text: str, shortcut: str, slot) -> None:
        act = QAction(text, self)
        if shortcut:
            act.setShortcut(QKeySequence(shortcut))
        act.triggered.connect(lambda: slot())
        menu.addAction(act)

    def _connect(self) -> None:
        t = self.transport
        t.playPressed.connect(self.toggle_play)
        t.stopPressed.connect(self.stop)
        t.modeChanged.connect(self.set_mode)
        t.tempoChanged.connect(lambda _: self.engine.sync_master())
        t.keyChanged.connect(self._key_changed)
        t.patternChanged.connect(self.set_pattern)
        t.patternAdd.connect(self.add_pattern)
        t.patternDuplicate.connect(self.duplicate_pattern)
        t.patternRemove.connect(self.remove_pattern)
        t.patternLengthChanged.connect(self.set_pattern_length)

        self.rack.channelSelected.connect(self.select_channel)
        self.rack.projectChanged.connect(self._touch)
        self.rack.pianoRollRequested.connect(self.open_piano_roll)
        self.rack.channelContext.connect(self.channel_menu)
        self.rack.seekRequested.connect(self.engine.seek_step)

        self.roll.notesChanged.connect(self._touch)
        self.roll.previewNote.connect(self.engine.preview_note)
        self.roll.seekRequested.connect(self.engine.seek_step)

        self.playlist.changed.connect(self._touch)
        self.playlist.seekRequested.connect(self.engine.seek_step)

        self.mixer.changed.connect(self._mixer_changed)
        self.mixer.channelSelected.connect(self.select_channel)

        self.inspector.changed.connect(self._touch)
        self.inspector.structureChanged.connect(self._rebuild_views)

        self.browser.templateChosen.connect(self.load_template)
        self.browser.instrumentChosen.connect(self.add_channel)
        self.browser.newProject.connect(self.new_project)

    # -- project lifecycle ---------------------------------------------------
    def load_project(self, project: Project, reset_path: bool = False) -> None:
        self.project = project
        self.engine.load_project(project)
        pid = project.patterns[0].id if project.patterns else ""
        self.engine.current_pattern = pid
        self.transport.set_project(project)
        self.transport.sync(pid)
        self.rack.set_project(project, pid)
        self.playlist.set_project(project)
        self.mixer.set_project(project)
        self.inspector.set_project(project)
        cid = project.channels[0].id if project.channels else ""
        self.select_channel(cid)
        self.roll.set_context(project, pid, cid)
        if reset_path:
            self.path = None
        self.dirty = False
        self._undo.clear()
        self._update_title()
        self.transport.set_playing(self.engine.playing)

    def new_project(self) -> None:
        if not self._confirm_discard():
            return
        self.load_project(empty_project(), reset_path=True)
        self.status.showMessage("New project", 2500)

    def load_template(self, key: str) -> None:
        if not self._confirm_discard():
            return
        tpl = by_key(key)
        if tpl is None:
            return
        was_playing = self.engine.playing
        self.load_project(tpl.build(), reset_path=True)
        self.set_mode("song")
        if was_playing:
            self.engine.play()
            self.transport.set_playing(True)
        self.status.showMessage(f"Loaded template: {tpl.name}", 3500)

    def _confirm_discard(self) -> bool:
        if not self.dirty:
            return True
        r = QMessageBox.question(
            self, APP_NAME, "This project has unsaved changes. Discard them?",
            QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel)
        return r == QMessageBox.StandardButton.Discard

    def open_project(self) -> None:
        if not self._confirm_discard():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Open project", "", FILE_FILTER)
        if not path:
            return
        try:
            pr = Project.load(path)
        except Exception as exc:
            QMessageBox.critical(self, APP_NAME, f"Could not open:\n{exc}")
            return
        self.load_project(pr)
        self.path = path
        self._update_title()
        self.status.showMessage(f"Opened {os.path.basename(path)}", 3000)

    def save_project(self, save_as: bool = False) -> None:
        path = self.path
        if save_as or not path:
            path, _ = QFileDialog.getSaveFileName(
                self, "Save project", self.project.name + ".ecp", FILE_FILTER)
            if not path:
                return
            if not path.lower().endswith(".ecp"):
                path += ".ecp"
        try:
            self.project.save(path)
        except Exception as exc:
            QMessageBox.critical(self, APP_NAME, f"Could not save:\n{exc}")
            return
        self.path = path
        self.dirty = False
        self._update_title()
        self.status.showMessage(f"Saved {os.path.basename(path)}", 3000)

    def export_wav(self) -> None:
        steps = (self.project.arrangement_length if self.engine.mode == "song"
                 else self.engine.loop_length_steps() * 4)
        if steps <= 0:
            QMessageBox.information(self, APP_NAME,
                                    "Nothing to export — the playlist is empty.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export WAV", self.project.name + ".wav", "WAV audio (*.wav)")
        if not path:
            return
        if not path.lower().endswith(".wav"):
            path += ".wav"
        was_running = self.backend.running
        self.backend.stop()
        dlg = QProgressDialog("Rendering…", "Cancel", 0, 100, self)
        dlg.setWindowTitle("Export")
        dlg.setWindowModality(Qt.WindowModality.WindowModal)
        dlg.setMinimumDuration(0)
        dlg.setValue(0)

        def progress(frac: float) -> bool:
            dlg.setValue(int(frac * 100))
            QApplication.processEvents()
            return not dlg.wasCanceled()

        try:
            audio = self.engine.render_span(steps, 4.0, progress)
            if not dlg.wasCanceled():
                write_wav(path, audio)
                self.status.showMessage(
                    f"Exported {len(audio) / self.engine.sr:.1f}s to "
                    f"{os.path.basename(path)}", 5000)
        except Exception as exc:
            QMessageBox.critical(self, APP_NAME, f"Export failed:\n{exc}")
        finally:
            dlg.close()
            if was_running:
                self._start_audio()

    # -- transport -----------------------------------------------------------
    def _start_audio(self) -> None:
        if self.backend.start():
            self.status.showMessage(
                f"Audio running — {self.backend.latency_ms():.0f} ms buffer", 4000)
        else:
            self.status.showMessage(
                f"No audio output: {self.backend.last_error} "
                f"(you can still edit and export)", 9000)

    def audio_settings(self) -> None:
        dlg = AudioSettings(self.backend, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            if dlg.apply():
                self.status.showMessage(
                    f"Audio restarted — {self.backend.latency_ms():.0f} ms", 4000)
            else:
                self.status.showMessage(f"Audio failed: {self.backend.last_error}",
                                        8000)

    def toggle_play(self) -> None:
        if self.engine.playing:
            self.engine.pause()
        else:
            self.engine.play()
        self.transport.set_playing(self.engine.playing)

    def stop(self) -> None:
        self.engine.stop()
        self.transport.set_playing(False)

    def panic(self) -> None:
        self.engine.reset_audio_state()
        self.status.showMessage("All notes off", 2000)

    def set_mode(self, mode: str) -> None:
        self.engine.set_mode(mode)
        self.transport.btn_pattern.setChecked(mode == "pattern")
        self.transport.btn_song.setChecked(mode == "song")
        if mode == "song":
            self.show_tab(2)

    # -- patterns ------------------------------------------------------------
    def set_pattern(self, pid: str) -> None:
        self.engine.current_pattern = pid
        # keep the transport's selector in step when the change came from
        # somewhere other than the selector itself
        if self.transport.pattern.currentData() != pid:
            self.transport.blockSignals(True)
            i = self.transport.pattern.findData(pid)
            if i >= 0:
                self.transport.pattern.setCurrentIndex(i)
            self.transport.blockSignals(False)
        self.rack.set_pattern(pid)
        self.roll.set_context(self.project, pid, self.roll.grid.channel_id)
        pat = self.project.pattern(pid)
        if pat:
            i = self.transport.length.findData(pat.length)
            if i >= 0:
                self.transport.length.blockSignals(True)
                self.transport.length.setCurrentIndex(i)
                self.transport.length.blockSignals(False)

    def add_pattern(self) -> None:
        self._snapshot()
        pat = self.project.add_pattern(length=self.rack.grid.n_steps())
        self.transport.sync(pat.id)
        self.playlist.sync_patterns()
        self.set_pattern(pat.id)
        self._touch()

    def duplicate_pattern(self) -> None:
        self._snapshot()
        pat = self.project.duplicate_pattern(self.engine.current_pattern)
        if pat:
            self.transport.sync(pat.id)
            self.playlist.sync_patterns()
            self.set_pattern(pat.id)
            self._touch()

    def remove_pattern(self) -> None:
        if len(self.project.patterns) <= 1:
            self.status.showMessage("A project needs at least one pattern", 2500)
            return
        self._snapshot()
        self.project.remove_pattern(self.engine.current_pattern)
        pid = self.project.patterns[0].id
        self.transport.sync(pid)
        self.playlist.sync_patterns()
        self.playlist.refresh()
        self.set_pattern(pid)
        self._touch()

    def set_pattern_length(self, steps: int) -> None:
        pat = self.project.pattern(self.engine.current_pattern)
        if pat is None or pat.length == steps:
            return
        self._snapshot()
        pat.length = steps
        for cid in list(pat.notes):
            pat.notes[cid] = [n for n in pat.notes[cid] if n.step < steps]
        self.rack.refresh()
        self.roll.refresh()
        self._touch()

    def clear_pattern(self) -> None:
        pat = self.project.pattern(self.engine.current_pattern)
        if pat is None:
            return
        self._snapshot()
        pat.notes = {}
        self.rack.refresh()
        self.roll.refresh()
        self._touch()

    # -- channels ------------------------------------------------------------
    def add_channel(self, instrument: str) -> None:
        self._snapshot()
        ch = self.project.add_channel(instrument)
        self._rebuild_views()
        self.select_channel(ch.id)
        self.status.showMessage(f"Added {ch.name}", 2500)

    def select_channel(self, cid: str) -> None:
        self.rack.grid.selected = cid
        self.rack.grid.update()
        self.inspector.set_channel(cid)
        if self.roll.grid.channel_id != cid:
            self.roll.set_context(self.project, self.engine.current_pattern, cid)

    def open_piano_roll(self, cid: str) -> None:
        self.select_channel(cid)
        self.roll.set_context(self.project, self.engine.current_pattern, cid)
        self.show_tab(1)

    def channel_menu(self, cid: str, global_pos) -> None:
        ch = self.project.channel(cid)
        if ch is None:
            return
        menu = QMenu(self)
        menu.addAction("Piano roll", lambda: self.open_piano_roll(cid))
        menu.addAction("Generate…", lambda: self.open_generate(cid))
        menu.addSeparator()
        menu.addAction("Clear steps", lambda: self._clear_channel(cid))
        menu.addAction("Duplicate", lambda: self._duplicate_channel(cid))
        menu.addSeparator()
        menu.addAction("Move up", lambda: self._move_channel(cid, -1))
        menu.addAction("Move down", lambda: self._move_channel(cid, 1))
        menu.addSeparator()
        menu.addAction("Delete", lambda: self._delete_channel(cid))
        menu.exec(global_pos)

    def _clear_channel(self, cid: str) -> None:
        pat = self.project.pattern(self.engine.current_pattern)
        if pat:
            self._snapshot()
            pat.clear_channel(cid)
            self.rack.refresh()
            self.roll.refresh()
            self._touch()

    def _duplicate_channel(self, cid: str) -> None:
        src = self.project.channel(cid)
        if src is None:
            return
        self._snapshot()
        ch = self.project.add_channel(src.instrument, f"{src.name} copy",
                                      dict(src.params))
        ch.volume, ch.pan, ch.sc_amount = src.volume, src.pan, src.sc_amount
        ch.sends.reverb, ch.sends.delay = src.sends.reverb, src.sends.delay
        self._rebuild_views()
        self.select_channel(ch.id)

    def _move_channel(self, cid: str, delta: int) -> None:
        self._snapshot()
        self.project.move_channel(cid, delta)
        self._rebuild_views()
        self.select_channel(cid)

    def _delete_channel(self, cid: str) -> None:
        if len(self.project.channels) <= 1:
            return
        self._snapshot()
        self.project.remove_channel(cid)
        self._rebuild_views()
        if self.project.channels:
            self.select_channel(self.project.channels[0].id)

    def _rebuild_views(self) -> None:
        self.rack.rebuild()
        self.mixer.rebuild()
        self.roll.refresh()
        self._touch()

    def _mixer_changed(self) -> None:
        self.engine.sync_master()
        self.rack.refresh()
        self._touch()

    def _key_changed(self) -> None:
        self.engine.sync_master()
        self.roll.grid.update()
        self._touch()

    # -- generate ------------------------------------------------------------
    def open_generate(self, cid: str | None = None) -> None:
        pat = self.project.pattern(self.engine.current_pattern)
        if pat is None:
            return
        target = cid if isinstance(cid, str) and cid else \
            (self.rack.grid.selected or (self.project.channels[0].id
                                         if self.project.channels else ""))
        if not target:
            return
        dlg = GenerateDialog(self.project, pat, target, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._snapshot()
            dlg.apply()
            self.rack.refresh()
            self.roll.refresh()
            self._touch()
            self.status.showMessage("Generated into "
                                    f"{pat.name}", 2500)

    # -- undo / dirty --------------------------------------------------------
    def _snapshot(self) -> None:
        self._undo.append(self.project.to_dict())
        if len(self._undo) > 40:
            self._undo.pop(0)

    def undo(self) -> None:
        if not self._undo:
            self.status.showMessage("Nothing to undo", 2000)
            return
        state = self._undo.pop()
        pid = self.engine.current_pattern
        pr = Project.from_dict(state)
        self.project = pr
        self.engine.load_project(pr)
        if pr.pattern(pid):
            self.engine.current_pattern = pid
        self.transport.set_project(pr)
        self.transport.sync(self.engine.current_pattern)
        self.rack.set_project(pr, self.engine.current_pattern)
        self.playlist.set_project(pr)
        self.mixer.set_project(pr)
        self.inspector.set_project(pr)
        cid = pr.channels[0].id if pr.channels else ""
        self.select_channel(cid)
        self.status.showMessage("Undo", 1800)

    def _touch(self) -> None:
        self.dirty = True
        self._update_title()

    def _update_title(self) -> None:
        name = os.path.basename(self.path) if self.path else self.project.name
        self.setWindowTitle(f"{APP_NAME} — {name}{' *' if self.dirty else ''}")

    # -- view ----------------------------------------------------------------
    def show_tab(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        for i, b in enumerate(self.tab_buttons):
            b.setChecked(i == index)

    def show_help(self) -> None:
        QMessageBox.information(self, "Shortcuts", (
            "Space — play / pause\n"
            "Esc — all notes off\n"
            "F1..F4 — Channel Rack, Piano Roll, Playlist, Mixer\n"
            "Ctrl+G — generate chords, arps, basslines, grooves\n"
            "Ctrl+S / Ctrl+O / Ctrl+N — save, open, new\n"
            "Ctrl+E — export WAV\n"
            "Ctrl+Z — undo\n\n"
            "Step grid: click or drag to draw, right-click to erase,\n"
            "ctrl-drag up/down to set velocity.\n\n"
            "Piano roll: drag to draw, drag the right edge to resize,\n"
            "right-click to erase, alt to snap to the key.\n\n"
            "Play notes from the keyboard: Z S X D C V G B H N J M\n"
            "and Q 2 W 3 E R 5 T 6 Y 7 U for the octave above.\n"
            "[ and ] shift the octave."))

    # -- timer ---------------------------------------------------------------
    def _tick(self) -> None:
        eng = self.engine
        step = eng.current_step
        if eng.mode == "song":
            self.playlist.set_playhead(step if eng.playing else -1)
            pat = self.project.pattern(eng.current_pattern)
            local = step % pat.length if pat and pat.length else 0
        else:
            pat = self.project.pattern(eng.current_pattern)
            local = step % pat.length if pat and pat.length else 0
            self.playlist.set_playhead(-1)
        self.rack.set_playhead(local if eng.playing else -1)
        self.roll.set_playhead(local if eng.playing else -1)
        self.transport.set_position(step, eng.mode)
        meters = dict(eng.meters)
        self.rack.set_meters(meters)
        if self.stack.currentIndex() == 3:
            self.mixer.set_meters(meters, eng.master_peak)
        self.transport.set_meters(eng.master_peak, eng.cpu)

    # -- keyboard ------------------------------------------------------------
    def keyPressEvent(self, e):
        if e.isAutoRepeat():
            return
        key = e.key()
        if key == Qt.Key.Key_Space:
            self.toggle_play()
            return
        if key == Qt.Key.Key_BracketLeft:
            self.key_octave = max(0, self.key_octave - 1)
            self.status.showMessage(f"Keyboard octave {self.key_octave}", 1500)
            return
        if key == Qt.Key.Key_BracketRight:
            self.key_octave = min(8, self.key_octave + 1)
            self.status.showMessage(f"Keyboard octave {self.key_octave}", 1500)
            return
        if key in KEY_MAP and not (e.modifiers() & (
                Qt.KeyboardModifier.ControlModifier |
                Qt.KeyboardModifier.AltModifier)):
            cid = self.rack.grid.selected
            if cid:
                pitch = 12 * (self.key_octave + 1) + KEY_MAP[key]
                self._held[key] = pitch
                self.engine.preview_note(cid, pitch, 0.9)
            return
        super().keyPressEvent(e)

    def keyReleaseEvent(self, e):
        if e.isAutoRepeat():
            return
        pitch = self._held.pop(e.key(), None)
        if pitch is not None:
            cid = self.rack.grid.selected
            if cid:
                self.engine.preview_off(cid, pitch)
            return
        super().keyReleaseEvent(e)

    def closeEvent(self, e):
        if not self._confirm_discard():
            e.ignore()
            return
        self.timer.stop()
        self.backend.stop()
        e.accept()
