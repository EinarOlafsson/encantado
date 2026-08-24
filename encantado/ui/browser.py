"""Left-hand browser: templates, instruments, patterns."""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (QFrame, QLabel, QScrollArea, QVBoxLayout, QWidget)

from ..dsp.drums import DRUMS
from ..dsp.instruments import INSTRUMENTS
from ..presets.templates import TEMPLATES
from . import theme as T


class _Row(QFrame):
    """A clickable card. A QFrame rather than a button so the wrapped
    subtitle actually drives the row's height."""

    clicked = pyqtSignal()

    def __init__(self, title: str, subtitle: str = "", color: str = T.ACCENT,
                 parent=None):
        super().__init__(parent)
        self.setObjectName("BrowserRow")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(9, 6, 9, 6)
        lay.setSpacing(2)
        t = QLabel(title)
        t.setStyleSheet(f"font-weight:600; color:{color}; background:transparent;")
        lay.addWidget(t)
        if subtitle:
            sub = QLabel(subtitle)
            sub.setWordWrap(True)
            sub.setStyleSheet(
                f"color:{T.TEXT_FAINT}; font-size:11px; background:transparent;")
            lay.addWidget(sub)
            self.setToolTip(subtitle)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()


class Browser(QWidget):
    templateChosen = pyqtSignal(str)
    instrumentChosen = pyqtSignal(str)
    newProject = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        area = QScrollArea()
        area.setWidgetResizable(True)
        host = QWidget()
        lay = QVBoxLayout(host)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(5)

        def section(title):
            lb = QLabel(title)
            lb.setObjectName("Title")
            lay.addSpacing(4)
            lay.addWidget(lb)

        section("Start")
        blank = _Row("Blank Project", "Six empty channels, 124 BPM")
        blank.clicked.connect(self.newProject)
        lay.addWidget(blank)

        section("Styles")
        for t in TEMPLATES:
            row = _Row(t.name, f"{t.bpm} BPM · {t.blurb}", T.ACCENT)
            row.clicked.connect(lambda k=t.key: self.templateChosen.emit(k))
            lay.addWidget(row)

        section("Add Instrument")
        cats: dict[str, list] = {}
        for key, spec in list(INSTRUMENTS.items()) + list(DRUMS.items()):
            cats.setdefault(spec["category"], []).append((key, spec))
        for cat, items in cats.items():
            cl = QLabel(cat)
            cl.setStyleSheet(f"color:{T.TEXT_FAINT}; font-size:11px; "
                             f"font-weight:600; padding-top:4px;")
            lay.addWidget(cl)
            for key, spec in items:
                row = _Row(spec["name"], spec.get("blurb", ""), T.ACCENT_3)
                row.clicked.connect(lambda k=key: self.instrumentChosen.emit(k))
                lay.addWidget(row)

        lay.addStretch(1)
        area.setWidget(host)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(area)
