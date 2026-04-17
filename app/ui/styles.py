"""
TradeMind AI — Bloomberg Dark Theme
QSS stylesheet for the entire application.
"""
from app.config import (
    COLOR_BG, COLOR_CARD, COLOR_SIDEBAR, COLOR_BORDER,
    COLOR_TEXT, COLOR_TEXT_MUTED, COLOR_ACCENT, COLOR_SUCCESS,
    COLOR_DANGER, COLOR_WARNING, COLOR_PURPLE, COLOR_CYAN
)

MAIN_STYLESHEET = f"""
/* ─── Global ─────────────────────────────────────────────────────────── */
* {{
    font-family: "Segoe UI", "Arial", sans-serif;
    font-size: 13px;
    color: {COLOR_TEXT};
    outline: none;
}}

QMainWindow, QWidget {{
    background-color: {COLOR_BG};
    border: none;
}}

QFrame {{
    background-color: transparent;
    border: none;
}}

/* ─── Scrollbars ─────────────────────────────────────────────────────── */
QScrollBar:vertical {{
    background: {COLOR_BG};
    width: 8px;
    border-radius: 4px;
}}
QScrollBar::handle:vertical {{
    background: {COLOR_BORDER};
    border-radius: 4px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: {COLOR_TEXT_MUTED};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar:horizontal {{
    background: {COLOR_BG};
    height: 8px;
    border-radius: 4px;
}}
QScrollBar::handle:horizontal {{
    background: {COLOR_BORDER};
    border-radius: 4px;
    min-width: 30px;
}}

/* ─── Sidebar ────────────────────────────────────────────────────────── */
#sidebar {{
    background-color: {COLOR_SIDEBAR};
    border-right: 1px solid {COLOR_BORDER};
    min-width: 220px;
    max-width: 220px;
}}
#sidebar-logo {{
    padding: 20px 16px 12px 16px;
    font-size: 18px;
    font-weight: 700;
    color: {COLOR_ACCENT};
    letter-spacing: 1px;
}}
#sidebar-version {{
    font-size: 10px;
    color: {COLOR_TEXT_MUTED};
    padding: 0 16px 16px 16px;
}}

/* Sidebar nav buttons */
#nav-btn {{
    background: transparent;
    border: none;
    border-radius: 8px;
    padding: 10px 16px;
    text-align: left;
    font-size: 13px;
    color: {COLOR_TEXT_MUTED};
    margin: 2px 8px;
}}
#nav-btn:hover {{
    background: rgba(59, 130, 246, 0.12);
    color: {COLOR_TEXT};
}}
#nav-btn[active="true"] {{
    background: rgba(59, 130, 246, 0.20);
    color: {COLOR_ACCENT};
    font-weight: 600;
    border-left: 3px solid {COLOR_ACCENT};
    padding-left: 13px;
}}

/* Sidebar section labels */
#nav-section {{
    font-size: 10px;
    font-weight: 700;
    color: {COLOR_TEXT_MUTED};
    letter-spacing: 1.5px;
    padding: 16px 16px 4px 16px;
    text-transform: uppercase;
}}

/* ─── Content Area ───────────────────────────────────────────────────── */
#content-area {{
    background: {COLOR_BG};
}}

/* ─── Page Header ────────────────────────────────────────────────────── */
#page-title {{
    font-size: 22px;
    font-weight: 700;
    color: {COLOR_TEXT};
}}
#page-subtitle {{
    font-size: 12px;
    color: {COLOR_TEXT_MUTED};
}}

/* ─── Cards ──────────────────────────────────────────────────────────── */
#card {{
    background: {COLOR_CARD};
    border: 1px solid {COLOR_BORDER};
    border-radius: 12px;
    padding: 16px;
}}
#card-title {{
    font-size: 11px;
    font-weight: 600;
    color: {COLOR_TEXT_MUTED};
    letter-spacing: 0.5px;
    text-transform: uppercase;
}}
#card-value {{
    font-size: 26px;
    font-weight: 700;
    color: {COLOR_TEXT};
}}
#card-change-positive {{
    font-size: 12px;
    color: {COLOR_SUCCESS};
    font-weight: 600;
}}
#card-change-negative {{
    font-size: 12px;
    color: {COLOR_DANGER};
    font-weight: 600;
}}

/* ─── Buttons ────────────────────────────────────────────────────────── */
QPushButton {{
    border-radius: 8px;
    padding: 8px 18px;
    font-weight: 600;
    font-size: 13px;
    border: none;
}}
QPushButton#btn-primary {{
    background: {COLOR_ACCENT};
    color: white;
}}
QPushButton#btn-primary:hover {{
    background: #2563eb;
}}
QPushButton#btn-primary:pressed {{
    background: #1d4ed8;
}}
QPushButton#btn-success {{
    background: {COLOR_SUCCESS};
    color: white;
}}
QPushButton#btn-success:hover {{
    background: #059669;
}}
QPushButton#btn-danger {{
    background: {COLOR_DANGER};
    color: white;
}}
QPushButton#btn-danger:hover {{
    background: #dc2626;
}}
QPushButton#btn-ghost {{
    background: transparent;
    border: 1px solid {COLOR_BORDER};
    color: {COLOR_TEXT_MUTED};
}}
QPushButton#btn-ghost:hover {{
    background: {COLOR_CARD};
    color: {COLOR_TEXT};
    border-color: {COLOR_TEXT_MUTED};
}}

/* ─── Inputs ─────────────────────────────────────────────────────────── */
QLineEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background: {COLOR_BG};
    border: 1px solid {COLOR_BORDER};
    border-radius: 8px;
    padding: 8px 12px;
    color: {COLOR_TEXT};
    selection-background-color: {COLOR_ACCENT};
}}
QLineEdit:focus, QTextEdit:focus, QSpinBox:focus,
QDoubleSpinBox:focus, QComboBox:focus {{
    border-color: {COLOR_ACCENT};
}}
QComboBox::drop-down {{
    border: none;
    padding-right: 8px;
}}
QComboBox QAbstractItemView {{
    background: {COLOR_CARD};
    border: 1px solid {COLOR_BORDER};
    border-radius: 8px;
    selection-background-color: rgba(59, 130, 246, 0.3);
    color: {COLOR_TEXT};
}}

/* ─── Tables ─────────────────────────────────────────────────────────── */
QTableWidget, QTableView {{
    background: {COLOR_CARD};
    border: 1px solid {COLOR_BORDER};
    border-radius: 8px;
    gridline-color: {COLOR_BORDER};
    selection-background-color: rgba(59, 130, 246, 0.2);
    alternate-background-color: rgba(255,255,255,0.02);
}}
QTableWidget::item, QTableView::item {{
    padding: 8px 12px;
    border: none;
}}
QHeaderView::section {{
    background: {COLOR_SIDEBAR};
    color: {COLOR_TEXT_MUTED};
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.5px;
    text-transform: uppercase;
    padding: 8px 12px;
    border: none;
    border-right: 1px solid {COLOR_BORDER};
    border-bottom: 1px solid {COLOR_BORDER};
}}

/* ─── Tab Widget ─────────────────────────────────────────────────────── */
QTabWidget::pane {{
    border: 1px solid {COLOR_BORDER};
    border-radius: 8px;
    background: {COLOR_CARD};
}}
QTabBar::tab {{
    background: transparent;
    color: {COLOR_TEXT_MUTED};
    padding: 8px 20px;
    border: none;
    border-bottom: 2px solid transparent;
    font-size: 13px;
}}
QTabBar::tab:selected {{
    color: {COLOR_ACCENT};
    border-bottom: 2px solid {COLOR_ACCENT};
    font-weight: 600;
}}
QTabBar::tab:hover {{
    color: {COLOR_TEXT};
}}

/* ─── Labels ─────────────────────────────────────────────────────────── */
QLabel#label-success {{ color: {COLOR_SUCCESS}; font-weight: 600; }}
QLabel#label-danger  {{ color: {COLOR_DANGER};  font-weight: 600; }}
QLabel#label-warning {{ color: {COLOR_WARNING}; font-weight: 600; }}
QLabel#label-muted   {{ color: {COLOR_TEXT_MUTED}; }}
QLabel#label-accent  {{ color: {COLOR_ACCENT}; font-weight: 600; }}

/* ─── Progress Bar ───────────────────────────────────────────────────── */
QProgressBar {{
    background: {COLOR_BG};
    border: 1px solid {COLOR_BORDER};
    border-radius: 6px;
    height: 8px;
    text-align: center;
    color: transparent;
}}
QProgressBar::chunk {{
    background: {COLOR_ACCENT};
    border-radius: 6px;
}}
QProgressBar#progress-danger::chunk  {{ background: {COLOR_DANGER}; }}
QProgressBar#progress-warning::chunk {{ background: {COLOR_WARNING}; }}
QProgressBar#progress-success::chunk {{ background: {COLOR_SUCCESS}; }}

/* ─── Tooltips ───────────────────────────────────────────────────────── */
QToolTip {{
    background: {COLOR_CARD};
    color: {COLOR_TEXT};
    border: 1px solid {COLOR_BORDER};
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 12px;
}}

/* ─── Status Bar ─────────────────────────────────────────────────────── */
QStatusBar {{
    background: {COLOR_SIDEBAR};
    border-top: 1px solid {COLOR_BORDER};
    color: {COLOR_TEXT_MUTED};
    font-size: 11px;
}}

/* ─── Separator ──────────────────────────────────────────────────────── */
QFrame[frameShape="4"], QFrame[frameShape="5"] {{
    background: {COLOR_BORDER};
    border: none;
    max-height: 1px;
}}

/* ─── CheckBox / Radio ───────────────────────────────────────────────── */
QCheckBox, QRadioButton {{
    color: {COLOR_TEXT};
    spacing: 8px;
}}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 16px;
    height: 16px;
    border: 2px solid {COLOR_BORDER};
    border-radius: 4px;
    background: {COLOR_BG};
}}
QCheckBox::indicator:checked {{
    background: {COLOR_ACCENT};
    border-color: {COLOR_ACCENT};
}}

/* ─── Slider ─────────────────────────────────────────────────────────── */
QSlider::groove:horizontal {{
    background: {COLOR_BORDER};
    height: 4px;
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {COLOR_ACCENT};
    width: 16px;
    height: 16px;
    margin: -6px 0;
    border-radius: 8px;
}}
QSlider::sub-page:horizontal {{
    background: {COLOR_ACCENT};
    border-radius: 2px;
}}
"""


def apply_badge_style(widget, color: str):
    """Helper: apply a coloured pill/badge style to a QLabel."""
    widget.setStyleSheet(
        f"background: {color}22; color: {color}; border-radius: 6px; "
        f"padding: 2px 8px; font-size: 11px; font-weight: 700;"
    )
