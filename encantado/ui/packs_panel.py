"""Sound packs: where to buy them, and how to point Encantado at ones you own."""
from __future__ import annotations

import os

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QDesktopServices, QGuiApplication
from PyQt6.QtCore import QUrl
from PyQt6.QtWidgets import (QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel,
                             QPushButton, QScrollArea, QVBoxLayout, QWidget)

from ..core.packs import (ARTISTS, CATEGORIES, DISCLAIMER, Artist, PackGuide,
                          all_guides, vendor)
from . import theme as T


def _open(url: str) -> None:
    QDesktopServices.openUrl(QUrl(url))


class PackDialog(QDialog):
    """Shown when you click a pack. Explains what it is, where to buy it
    legitimately, and lets you point Encantado at it if you already own it."""

    located = pyqtSignal(str, str)          # (key, folder)

    def __init__(self, title: str, blurb: str, vendor_keys, search_terms,
                 owned_path: str = "", key: str = "", parent=None):
        super().__init__(parent)
        self.key = key
        self.setWindowTitle(title)
        self.setStyleSheet(T.STYLESHEET)
        self.setMinimumWidth(560)

        outer = QVBoxLayout(self)
        outer.setSpacing(9)

        head = QLabel(title)
        head.setObjectName("Heading")
        outer.addWidget(head)
        sub = QLabel(blurb)
        sub.setWordWrap(True)
        sub.setObjectName("Dim")
        outer.addWidget(sub)

        # --- do you already have it -----------------------------------------
        own = QFrame()
        own.setObjectName("Card")
        ov = QVBoxLayout(own)
        ov.setContentsMargins(10, 9, 10, 10)
        ov.setSpacing(6)
        lb = QLabel("ALREADY OWN IT?")
        lb.setObjectName("Title")
        ov.addWidget(lb)
        self.owned_label = QLabel()
        self.owned_label.setWordWrap(True)
        self.owned_label.setObjectName("Faint")
        ov.addWidget(self.owned_label)
        row = QHBoxLayout()
        locate = QPushButton("Locate folder on disk…")
        locate.setObjectName("Primary")
        locate.clicked.connect(self._locate)
        row.addWidget(locate)
        row.addStretch(1)
        ov.addLayout(row)
        outer.addWidget(own)
        self._set_owned(owned_path)

        # --- where to buy ----------------------------------------------------
        buy = QFrame()
        buy.setObjectName("Card")
        bv = QVBoxLayout(buy)
        bv.setContentsMargins(10, 9, 10, 10)
        bv.setSpacing(7)
        lb2 = QLabel("WHERE TO GET IT")
        lb2.setObjectName("Title")
        bv.addWidget(lb2)
        for vk in vendor_keys:
            v = vendor(vk)
            if v is None:
                continue
            r = QHBoxLayout()
            r.setSpacing(8)
            col = QVBoxLayout()
            col.setSpacing(1)
            n = QLabel(v.name)
            n.setStyleSheet(f"font-weight:600; color:{T.ACCENT};")
            note = QLabel(v.note)
            note.setWordWrap(True)
            note.setObjectName("Faint")
            col.addWidget(n)
            col.addWidget(note)
            r.addLayout(col, 1)
            term = search_terms[0] if search_terms else ""
            btn = QPushButton("Open")
            btn.setFixedWidth(64)
            btn.clicked.connect(lambda _, vv=v, t=term: _open(vv.search(t)))
            r.addWidget(btn, 0, Qt.AlignmentFlag.AlignTop)
            bv.addLayout(r)
        outer.addWidget(buy)

        # --- search terms ----------------------------------------------------
        if search_terms:
            sc = QFrame()
            sc.setObjectName("Card")
            sv = QVBoxLayout(sc)
            sv.setContentsMargins(10, 9, 10, 10)
            sv.setSpacing(5)
            lb3 = QLabel("SEARCH FOR")
            lb3.setObjectName("Title")
            sv.addWidget(lb3)
            for term in search_terms:
                r = QHBoxLayout()
                t = QLabel(f"“{term}”")
                t.setStyleSheet("font-family:monospace;")
                r.addWidget(t, 1)
                cp = QPushButton("Copy")
                cp.setFixedWidth(58)
                cp.clicked.connect(
                    lambda _, x=term: QGuiApplication.clipboard().setText(x))
                r.addWidget(cp)
                sv.addLayout(r)
            outer.addWidget(sc)

        disc = QLabel(DISCLAIMER)
        disc.setWordWrap(True)
        disc.setObjectName("Faint")
        outer.addWidget(disc)

        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        r = QHBoxLayout()
        r.addStretch(1)
        r.addWidget(close)
        outer.addLayout(r)

    def _set_owned(self, path: str) -> None:
        if path and os.path.isdir(path):
            self.owned_label.setText(
                f"Indexed from <b>{path}</b> — it is in your Library tab.")
        else:
            self.owned_label.setText(
                "If you already have this on disk, point Encantado at the folder "
                "and every sample in it is indexed and ready to drop onto a "
                "channel. Nothing is copied — only the paths are remembered.")

    def _locate(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Select the folder containing your samples")
        if folder:
            self._set_owned(folder)
            self.located.emit(self.key, folder)


class _Card(QFrame):
    clicked = pyqtSignal()

    def __init__(self, title: str, subtitle: str, color: str, badge: str = "",
                 parent=None):
        super().__init__(parent)
        self.setObjectName("BrowserRow")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(9, 6, 9, 6)
        lay.setSpacing(2)
        top = QHBoxLayout()
        top.setSpacing(6)
        t = QLabel(title)
        t.setStyleSheet(f"font-weight:600; color:{color}; background:transparent;")
        top.addWidget(t, 1)
        if badge:
            b = QLabel(badge)
            b.setStyleSheet(
                f"color:{T.GREEN}; font-size:10px; font-weight:700;"
                f" background:transparent;")
            top.addWidget(b)
        lay.addLayout(top)
        s = QLabel(subtitle)
        s.setWordWrap(True)
        s.setStyleSheet(f"color:{T.TEXT_FAINT}; font-size:11px; background:transparent;")
        lay.addWidget(s)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()


class PacksPanel(QWidget):
    """Browse pack guides and artist searches."""

    folderLocated = pyqtSignal(str, str)     # (guide key, folder)

    def __init__(self, library, parent=None):
        super().__init__(parent)
        self.library = library
        self.area = QScrollArea()
        self.area.setWidgetResizable(True)
        self.host = QWidget()
        self.lay = QVBoxLayout(self.host)
        self.lay.setContentsMargins(8, 8, 8, 8)
        self.lay.setSpacing(5)
        self.area.setWidget(self.host)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.area)
        self.rebuild()

    def rebuild(self) -> None:
        while self.lay.count():
            item = self.lay.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
                w.deleteLater()

        intro = QLabel(
            "Encantado ships no third-party audio. These are pointers to the "
            "rights holders' own sites — and a place to plug in packs you "
            "already own. Everything under Free is a legitimate free download; "
            "check each one's licence before releasing commercially.")
        intro.setWordWrap(True)
        intro.setObjectName("Faint")
        self.lay.addWidget(intro)

        def header(text):
            lb = QLabel(text)
            lb.setObjectName("Title")
            self.lay.addSpacing(5)
            self.lay.addWidget(lb)

        header("By Artist")
        for a in ARTISTS:
            card = _Card(a.name, a.note, T.ACCENT_3)
            card.clicked.connect(lambda x=a: self._artist(x))
            self.lay.addWidget(card)

        for cat in CATEGORIES:
            guides = [g for g in all_guides() if g.category == cat]
            if not guides:
                continue
            header(cat)
            for g in guides:
                owned = self.library.owned_packs.get(g.key, "")
                badge = ("OWNED" if owned and os.path.isdir(owned)
                         else ("FREE" if g.category == "Free" else ""))
                colour = T.GREEN if g.category == "Free" else T.ACCENT
                card = _Card(g.title, g.blurb, colour, badge)
                card.clicked.connect(lambda x=g: self._guide(x))
                self.lay.addWidget(card)

        self.lay.addStretch(1)

    def _guide(self, g: PackGuide) -> None:
        dlg = PackDialog(g.title, g.blurb, g.vendors, g.search_terms,
                         self.library.owned_packs.get(g.key, ""), g.key, self)
        dlg.located.connect(self.folderLocated)
        dlg.exec()
        self.rebuild()

    def _artist(self, a: Artist) -> None:
        blurb = (f"{a.note}\n\nNo verified public list exists of the packs this "
                 f"artist actually used, so Encantado does not invent one. "
                 f"These buttons search each store directly — if an official "
                 f"pack exists, it shows up there.")
        dlg = PackDialog(a.name, blurb, a.vendors, (a.name,), "", "", self)
        dlg.exec()
