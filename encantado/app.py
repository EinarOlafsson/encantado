"""Application entry point."""
from __future__ import annotations

import sys

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from .ui import theme as T
from .ui.main_window import MainWindow


def main() -> int:
    QApplication.setAttribute(
        Qt.ApplicationAttribute.AA_DontCreateNativeWidgetSiblings, True)
    app = QApplication(sys.argv)
    app.setApplicationName("Encantado")
    app.setOrganizationName("Encantado")
    app.setStyleSheet(T.STYLESHEET)
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
