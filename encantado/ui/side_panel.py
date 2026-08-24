"""Left-hand dock: Create, Library and Packs in one tabbed panel."""
from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (QHBoxLayout, QPushButton, QStackedWidget,
                             QVBoxLayout, QWidget)

from ..core.library import SampleLibrary
from .browser import Browser
from .library_panel import LibraryPanel
from .packs_panel import PacksPanel


class SidePanel(QWidget):
    templateChosen = pyqtSignal(str)
    instrumentChosen = pyqtSignal(str)
    newProject = pyqtSignal()
    previewRequested = pyqtSignal(str)
    sampleActivated = pyqtSignal(str)
    packFolderLocated = pyqtSignal(str, str)
    buildKit = pyqtSignal(str)

    def __init__(self, library: SampleLibrary, parent=None):
        super().__init__(parent)
        self.library = library

        self.browser = Browser()
        self.library_panel = LibraryPanel(library)
        self.packs = PacksPanel(library)

        self.browser.templateChosen.connect(self.templateChosen)
        self.browser.instrumentChosen.connect(self.instrumentChosen)
        self.browser.newProject.connect(self.newProject)
        self.library_panel.previewRequested.connect(self.previewRequested)
        self.library_panel.sampleActivated.connect(self.sampleActivated)
        self.packs.folderLocated.connect(self.packFolderLocated)
        self.packs.buildKit.connect(self.buildKit)

        self.stack = QStackedWidget()
        for w in (self.browser, self.library_panel, self.packs):
            self.stack.addWidget(w)

        bar = QHBoxLayout()
        bar.setContentsMargins(4, 4, 4, 0)
        bar.setSpacing(2)
        self.buttons = []
        for i, name in enumerate(("Create", "Library", "Packs")):
            b = QPushButton(name)
            b.setObjectName("Tab")
            b.setCheckable(True)
            b.clicked.connect(lambda _, k=i: self.show_tab(k))
            bar.addWidget(b)
            self.buttons.append(b)
        bar.addStretch(1)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        lay.addLayout(bar)
        lay.addWidget(self.stack, 1)
        self.show_tab(0)

    def show_tab(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        for i, b in enumerate(self.buttons):
            b.setChecked(i == index)

    def refresh_library(self) -> None:
        self.library_panel.refresh()
        self.packs.rebuild()
