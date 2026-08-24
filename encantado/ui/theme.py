"""Dark neon visual language for Encantado."""
from __future__ import annotations

from PyQt6.QtGui import QColor

# -- palette ---------------------------------------------------------------
BG          = "#0b0d12"
BG_PANEL    = "#12161f"
BG_PANEL_2  = "#181d28"
BG_INPUT    = "#0e1218"
BORDER      = "#252c3a"
BORDER_LIT  = "#39445a"
TEXT        = "#d9e0ec"
TEXT_DIM    = "#78849a"
TEXT_FAINT  = "#4d586b"

ACCENT      = "#2fe0cf"      # cyan   — primary
ACCENT_2    = "#ff4d9d"      # magenta — record / danger
ACCENT_3    = "#8b7cff"      # violet — selection
ACCENT_4    = "#ffc94d"      # amber  — solo / warning
GREEN       = "#5ddb8a"

GRID_LINE   = "#1c2230"
GRID_BEAT   = "#28303f"
GRID_BAR    = "#3a4459"
PLAYHEAD    = "#ff4d9d"


def qc(hex_str: str, alpha: int = 255) -> QColor:
    c = QColor(hex_str)
    c.setAlpha(alpha)
    return c


STYLESHEET = f"""
* {{
    font-family: "Inter", "Segoe UI", "DejaVu Sans", sans-serif;
    font-size: 12px;
    color: {TEXT};
}}
QWidget#Root, QMainWindow {{ background: {BG}; }}

QFrame#Panel, QWidget#Panel {{
    background: {BG_PANEL};
    border: 1px solid {BORDER};
    border-radius: 8px;
}}
QFrame#Card {{
    background: {BG_PANEL_2};
    border: 1px solid {BORDER};
    border-radius: 6px;
}}
QLabel#Title {{
    font-size: 11px; font-weight: 700; color: {TEXT_DIM};
    letter-spacing: 1.2px; text-transform: uppercase;
}}
QLabel#Heading {{ font-size: 15px; font-weight: 700; color: {TEXT}; }}
QLabel#Dim {{ color: {TEXT_DIM}; }}
QLabel#Faint {{ color: {TEXT_FAINT}; font-size: 11px; }}

/* ---- buttons ---- */
QPushButton {{
    background: {BG_PANEL_2};
    border: 1px solid {BORDER};
    border-radius: 5px;
    padding: 5px 11px;
    color: {TEXT};
}}
QPushButton:hover {{ background: #1f2632; border-color: {BORDER_LIT}; }}
QPushButton:pressed {{ background: #0f131b; }}
QPushButton:checked {{
    background: {ACCENT}; border-color: {ACCENT}; color: #04231f;
    font-weight: 600;
}}
QPushButton:disabled {{ color: {TEXT_FAINT}; border-color: #1c222d; }}

QPushButton#Primary {{
    background: {ACCENT}; color: #04231f; border: none; font-weight: 700;
}}
QPushButton#Primary:hover {{ background: #45efdd; }}
QPushButton#Danger:checked {{ background: {ACCENT_2}; border-color: {ACCENT_2}; color: #2a0413; }}
QPushButton#Ghost {{ background: transparent; border: 1px solid {BORDER}; }}
QPushButton#Ghost:hover {{ background: {BG_PANEL_2}; }}
QPushButton#Tab {{
    background: transparent; border: none; border-bottom: 2px solid transparent;
    border-radius: 0; padding: 7px 15px; color: {TEXT_DIM}; font-weight: 600;
}}
QPushButton#Tab:hover {{ color: {TEXT}; }}
QPushButton#Tab:checked {{
    color: {ACCENT}; border-bottom: 2px solid {ACCENT}; background: transparent;
}}

/* ---- inputs ---- */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background: {BG_INPUT};
    border: 1px solid {BORDER};
    border-radius: 5px;
    padding: 4px 8px;
    selection-background-color: {ACCENT_3};
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border-color: {ACCENT};
}}
QComboBox::drop-down {{ border: none; width: 18px; }}
QComboBox::down-arrow {{
    image: none; border-left: 4px solid transparent;
    border-right: 4px solid transparent; border-top: 5px solid {TEXT_DIM};
    margin-right: 6px;
}}
QComboBox QAbstractItemView {{
    background: {BG_PANEL_2}; border: 1px solid {BORDER_LIT};
    selection-background-color: {ACCENT_3}; outline: none; padding: 3px;
}}
QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{ width: 14px; border: none; }}

/* ---- scrollbars ---- */
QScrollBar:vertical {{ background: transparent; width: 11px; margin: 0; }}
QScrollBar::handle:vertical {{
    background: #2b3444; border-radius: 5px; min-height: 28px;
}}
QScrollBar::handle:vertical:hover {{ background: #3c485c; }}
QScrollBar:horizontal {{ background: transparent; height: 11px; margin: 0; }}
QScrollBar::handle:horizontal {{
    background: #2b3444; border-radius: 5px; min-width: 28px;
}}
QScrollBar::handle:horizontal:hover {{ background: #3c485c; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

/* ---- misc ---- */
QSplitter::handle {{ background: {BORDER}; }}
QSplitter::handle:hover {{ background: {ACCENT}; }}
QToolTip {{
    background: {BG_PANEL_2}; color: {TEXT};
    border: 1px solid {BORDER_LIT}; padding: 5px 7px; border-radius: 4px;
}}
QMenu {{
    background: {BG_PANEL_2}; border: 1px solid {BORDER_LIT};
    padding: 5px; border-radius: 6px;
}}
QMenu::item {{ padding: 6px 24px 6px 14px; border-radius: 4px; }}
QMenu::item:selected {{ background: {ACCENT_3}; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 5px 8px; }}
QMenuBar {{ background: {BG_PANEL}; border-bottom: 1px solid {BORDER}; }}
QMenuBar::item {{ padding: 6px 11px; background: transparent; }}
QMenuBar::item:selected {{ background: {BG_PANEL_2}; }}
QScrollArea {{ border: none; background: transparent; }}
QSlider::groove:horizontal {{ height: 4px; background: {BG_INPUT}; border-radius: 2px; }}
QSlider::handle:horizontal {{
    background: {ACCENT}; width: 12px; margin: -5px 0; border-radius: 6px;
}}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 2px; }}
QProgressBar {{
    background: {BG_INPUT}; border: 1px solid {BORDER};
    border-radius: 4px; text-align: center; height: 16px;
}}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 3px; }}
QStatusBar {{ background: {BG_PANEL}; border-top: 1px solid {BORDER}; }}
QStatusBar::item {{ border: none; }}
"""
