"""Library panel: browse, audition and use samples you own."""
from __future__ import annotations

import os

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (QApplication, QComboBox, QFileDialog, QHBoxLayout,
                             QLabel, QLineEdit, QListWidget, QListWidgetItem,
                             QMenu, QMessageBox, QProgressDialog, QPushButton,
                             QVBoxLayout, QWidget)

from ..core.library import CATEGORIES, Sample, SampleLibrary
from . import theme as T

CATEGORY_COLOR = {
    "Kick": "#ff5c7a", "Snare": "#ff9f45", "Clap": "#ffc94d", "Hat": "#7ee787",
    "Cymbal": "#5ddb8a", "Tom": "#ff9f45", "Perc": "#4dd4c1", "Bass": "#4db8ff",
    "Lead": "#8b7cff", "Chord": "#d47cff", "Pad": "#ff7cc4", "Vocal": "#ffd93d",
    "FX": "#a0a8b8", "Loop": "#2fe0cf", "Other": "#78849a",
}


class LibraryPanel(QWidget):
    previewRequested = pyqtSignal(str)
    sampleActivated = pyqtSignal(str)          # add as a channel
    libraryChanged = pyqtSignal()

    def __init__(self, library: SampleLibrary, parent=None):
        super().__init__(parent)
        self.library = library

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        top = QHBoxLayout()
        top.setSpacing(5)
        self.add_btn = QPushButton("Add folder…")
        self.add_btn.setObjectName("Primary")
        self.add_btn.clicked.connect(self.add_folder)
        self.rescan_btn = QPushButton("↺")
        self.rescan_btn.setObjectName("Mini")
        self.rescan_btn.setFixedSize(26, 26)
        self.rescan_btn.setToolTip("Rescan every indexed folder")
        self.rescan_btn.clicked.connect(self.rescan)
        top.addWidget(self.add_btn, 1)
        top.addWidget(self.rescan_btn)
        lay.addLayout(top)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search samples…")
        self.search.textChanged.connect(self.refresh)
        lay.addWidget(self.search)

        self.cat = QComboBox()
        self.cat.addItem("All categories", "")
        for c in CATEGORIES:
            self.cat.addItem(c, c)
        self.cat.currentIndexChanged.connect(self.refresh)
        lay.addWidget(self.cat)

        self.list = QListWidget()
        self.list.setAlternatingRowColors(False)
        self.list.setStyleSheet(
            f"QListWidget {{ background:{T.BG_INPUT}; border:1px solid {T.BORDER};"
            f" border-radius:5px; }}"
            f"QListWidget::item {{ padding:4px 6px; border-radius:4px; }}"
            f"QListWidget::item:selected {{ background:{T.ACCENT_3}; }}")
        self.list.itemClicked.connect(self._clicked)
        self.list.itemDoubleClicked.connect(self._activated)
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._menu)
        lay.addWidget(self.list, 1)

        self.status = QLabel()
        self.status.setObjectName("Faint")
        self.status.setWordWrap(True)
        lay.addWidget(self.status)

        hint = QLabel("click to audition · double-click to add as a channel · "
                      "or drag files and folders straight onto the window")
        hint.setObjectName("Faint")
        hint.setWordWrap(True)
        lay.addWidget(hint)

        self.refresh()

    # -- data ----------------------------------------------------------------
    def refresh(self) -> None:
        self.list.clear()
        results = self.library.search(self.search.text(), self.cat.currentData())
        for s in results:
            bits = [s.category]
            if s.duration:
                bits.append(f"{s.duration:.2f}s")
            if s.bpm:
                bits.append(f"{s.bpm:.0f} BPM")
            if s.loop:
                bits.append("loop")
            if s.pack:
                bits.append(s.pack)
            item = QListWidgetItem(f"{s.name}\n{'  ·  '.join(bits)}")
            item.setData(Qt.ItemDataRole.UserRole, s.path)
            item.setForeground(QColor(CATEGORY_COLOR.get(s.category, T.TEXT)))
            item.setToolTip(s.path)
            self.list.addItem(item)
        total = len(self.library.samples)
        shown = len(results)
        if total:
            self.status.setText(
                f"{shown} of {total} samples · {len(self.library.roots)} folder"
                f"{'s' if len(self.library.roots) != 1 else ''} indexed")
        else:
            self.status.setText(
                "No samples indexed yet. Add a folder, or drag one onto the "
                "window. Encantado only stores the paths — your files stay "
                "where they are.")

    # -- actions -------------------------------------------------------------
    def add_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Add a sample folder")
        if folder:
            self.scan_folder(folder)

    def scan_folder(self, folder: str) -> int:
        dlg = QProgressDialog(f"Scanning {os.path.basename(folder)}…", "Stop",
                              0, 0, self)
        dlg.setWindowModality(Qt.WindowModality.WindowModal)
        dlg.setMinimumDuration(300)

        def progress(n, path):
            dlg.setLabelText(f"Found {n} samples…\n{os.path.basename(path)}")
            QApplication.processEvents()
            return not dlg.wasCanceled()

        try:
            found = self.library.scan(folder, progress)
        finally:
            dlg.close()
        self.library.save()
        self.refresh()
        self.libraryChanged.emit()
        if found == 0:
            QMessageBox.information(
                self, "Nothing found",
                f"No audio files were found under:\n{folder}\n\n"
                "Encantado reads WAV directly, and AIFF, FLAC, MP3 and OGG "
                "through ffmpeg.")
        return found

    def rescan(self) -> None:
        missing = self.library.forget_missing()
        dlg = QProgressDialog("Rescanning…", "Stop", 0, 0, self)
        dlg.setWindowModality(Qt.WindowModality.WindowModal)
        dlg.setMinimumDuration(300)

        def progress(n, path):
            dlg.setLabelText(f"Found {n} new samples…")
            QApplication.processEvents()
            return not dlg.wasCanceled()

        try:
            found = self.library.rescan(progress)
        finally:
            dlg.close()
        self.library.save()
        self.refresh()
        self.libraryChanged.emit()
        self.status.setText(f"Rescan: {found} added, {missing} missing removed")

    def _clicked(self, item: QListWidgetItem) -> None:
        self.previewRequested.emit(item.data(Qt.ItemDataRole.UserRole))

    def _activated(self, item: QListWidgetItem) -> None:
        self.sampleActivated.emit(item.data(Qt.ItemDataRole.UserRole))

    def _menu(self, pos) -> None:
        item = self.list.itemAt(pos)
        if item is None:
            return
        path = item.data(Qt.ItemDataRole.UserRole)
        menu = QMenu(self)
        menu.addAction("Add as channel", lambda: self.sampleActivated.emit(path))
        menu.addAction("Audition", lambda: self.previewRequested.emit(path))
        menu.addSeparator()
        menu.addAction("Copy path",
                       lambda: QApplication.clipboard().setText(path))
        menu.addAction("Show folder", lambda: self._reveal(path))
        menu.addSeparator()
        menu.addAction("Remove from index", lambda: self._forget(path))
        menu.exec(self.list.mapToGlobal(pos))

    def _reveal(self, path: str) -> None:
        from PyQt6.QtCore import QUrl
        from PyQt6.QtGui import QDesktopServices
        QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(path)))

    def _forget(self, path: str) -> None:
        self.library.samples = [s for s in self.library.samples
                                if s.path != path]
        self.library.save()
        self.refresh()
