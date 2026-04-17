"""
Reusable MetricCard widget — the small KPI tiles shown on the dashboard.
"""
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame
from PyQt6.QtCore import Qt
from app.config import COLOR_SUCCESS, COLOR_DANGER, COLOR_TEXT_MUTED, COLOR_WARNING


class MetricCard(QWidget):
    """
    A card displaying:
        icon  TITLE
        BIG VALUE
        ▲ change   sub-text
    """

    def __init__(
        self,
        title: str,
        value: str = "—",
        change: str = "",
        sub: str = "",
        icon: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("card")
        self._build_ui(title, value, change, sub, icon)

    def _build_ui(self, title, value, change, sub, icon):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(4)

        # ── Header row ──────────────────────────────
        header = QHBoxLayout()
        header.setSpacing(6)

        if icon:
            icon_lbl = QLabel(icon)
            icon_lbl.setFixedSize(24, 24)
            icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            icon_lbl.setStyleSheet(
                "font-size: 16px; background: rgba(59,130,246,0.15); "
                "border-radius: 6px;"
            )
            header.addWidget(icon_lbl)

        self._title_lbl = QLabel(title.upper())
        self._title_lbl.setObjectName("card-title")
        header.addWidget(self._title_lbl)
        header.addStretch()
        layout.addLayout(header)

        # ── Main value ───────────────────────────────
        self._value_lbl = QLabel(value)
        self._value_lbl.setObjectName("card-value")
        layout.addWidget(self._value_lbl)

        # ── Footer row (change + sub) ────────────────
        footer = QHBoxLayout()
        footer.setSpacing(8)

        self._change_lbl = QLabel(change)
        footer.addWidget(self._change_lbl)

        if sub:
            sub_lbl = QLabel(sub)
            sub_lbl.setObjectName("label-muted")
            sub_lbl.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; font-size: 11px;")
            footer.addWidget(sub_lbl)

        footer.addStretch()
        layout.addLayout(footer)

        self.update_change(change)

    # ── Public update API ──────────────────────────────────────────────────
    def update_value(self, value: str):
        self._value_lbl.setText(value)

    def update_change(self, change: str):
        self._change_lbl.setText(change)
        if change.startswith("+") or change.startswith("▲"):
            self._change_lbl.setObjectName("card-change-positive")
            self._change_lbl.setStyleSheet(f"color: {COLOR_SUCCESS}; font-size: 12px; font-weight: 600;")
        elif change.startswith("-") or change.startswith("▼"):
            self._change_lbl.setObjectName("card-change-negative")
            self._change_lbl.setStyleSheet(f"color: {COLOR_DANGER}; font-size: 12px; font-weight: 600;")
        else:
            self._change_lbl.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; font-size: 12px;")

    def set_all(self, value: str, change: str = ""):
        self.update_value(value)
        if change:
            self.update_change(change)
