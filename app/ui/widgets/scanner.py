"""
TradeMind AI — Market Scanner Widget
Displays real-time AI-scored trade opportunities ranked by confidence.
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget,
    QTableWidgetItem, QHeaderView, QPushButton, QFrame,
    QSpinBox, QCheckBox, QAbstractItemView, QSizePolicy
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QBrush


# ── Helpers ───────────────────────────────────────────────────────────────────
def _color_for_confidence(conf: int) -> QColor:
    if conf >= 75:  return QColor("#10b981")   # green
    if conf >= 55:  return QColor("#f59e0b")   # amber
    return QColor("#ef4444")                    # red

def _color_for_risk(risk: str) -> QColor:
    return {"LOW": QColor("#10b981"), "MEDIUM": QColor("#f59e0b"),
            "HIGH": QColor("#ef4444")}.get(risk, QColor("#9ca3af"))

def _color_for_action(action: str) -> QColor:
    return {"BUY": QColor("#10b981"), "SELL": QColor("#ef4444"),
            "HOLD": QColor("#6b7280")}.get(action, QColor("#9ca3af"))


COLS = ["Symbol", "Signal", "Strategy", "Price ₹", "AI Conf %", "Risk", "Status", "Reason"]


class ScannerWidget(QWidget):
    """
    Displays the live scan results from StrategyEngine.
    Rows are added via on_scan_result() called by MainWindow.
    """

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self._rows: list[dict] = []        # ring-buffer of results
        self._auto_trade_enabled = False
        self._build_ui()

    # ── UI ────────────────────────────────────────────────────────────────
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # ── Header ────────────────────────────────────────────────────────
        hdr = QHBoxLayout()
        title = QLabel("AI Market Scanner")
        title.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        title.setStyleSheet("color: #f1f5f9;")
        hdr.addWidget(title)
        hdr.addStretch()

        self._status_lbl = QLabel("Waiting for signals…")
        self._status_lbl.setStyleSheet("color: #94a3b8; font-size: 12px;")
        hdr.addWidget(self._status_lbl)
        layout.addLayout(hdr)

        # ── Stats bar ─────────────────────────────────────────────────────
        stats = QHBoxLayout()
        self._card_scanned  = self._stat_card("Scanned",  "0",  "#3b82f6")
        self._card_signals  = self._stat_card("Signals",  "0",  "#10b981")
        self._card_approved = self._stat_card("Approved", "0",  "#f59e0b")
        self._card_executed = self._stat_card("Executed", "0",  "#8b5cf6")
        for card in (self._card_scanned, self._card_signals,
                     self._card_approved, self._card_executed):
            stats.addWidget(card)
        layout.addLayout(stats)

        # ── Controls ──────────────────────────────────────────────────────
        ctrl = QHBoxLayout()

        self._auto_toggle = QCheckBox("  Auto-Trade (AI approved signals only)")
        self._auto_toggle.setStyleSheet("color: #f1f5f9; font-size: 13px;")
        self._auto_toggle.toggled.connect(self._on_auto_toggle)
        ctrl.addWidget(self._auto_toggle)

        ctrl.addStretch()

        ctrl.addWidget(QLabel("Min Confidence:"))
        self._conf_spin = QSpinBox()
        self._conf_spin.setRange(50, 95)
        self._conf_spin.setValue(70)
        self._conf_spin.setSuffix(" %")
        self._conf_spin.setFixedWidth(80)
        ctrl.addWidget(self._conf_spin)

        clear_btn = QPushButton("Clear")
        clear_btn.setFixedWidth(70)
        clear_btn.clicked.connect(self._clear)
        ctrl.addWidget(clear_btn)

        layout.addLayout(ctrl)

        # ── Table ─────────────────────────────────────────────────────────
        self._table = QTableWidget(0, len(COLS))
        self._table.setHorizontalHeaderLabels(COLS)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.setStyleSheet("""
            QTableWidget { background: #1e2330; border: none; gridline-color: #2d3139; }
            QTableWidget::item { padding: 6px 8px; color: #e2e8f0; }
            QTableWidget::item:alternate { background: #252b3b; }
            QHeaderView::section {
                background: #2d3139; color: #94a3b8;
                padding: 6px 8px; border: none; font-weight: bold;
            }
        """)
        hh = self._table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(7, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self._table)

        # ── Footer ────────────────────────────────────────────────────────
        footer = QLabel(
            "⚠  Auto-trade executes paper trades by default. "
            "Enable Live Mode in Settings only when ready."
        )
        footer.setStyleSheet("color: #f59e0b; font-size: 11px;")
        footer.setWordWrap(True)
        layout.addWidget(footer)

        self._n_scanned  = 0
        self._n_signals  = 0
        self._n_approved = 0
        self._n_executed = 0

    def _stat_card(self, label: str, value: str, color: str) -> QFrame:
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{ background: #1e2330; border-radius: 8px;
                      border-left: 3px solid {color}; padding: 4px; }}
        """)
        vl = QVBoxLayout(card)
        vl.setContentsMargins(12, 8, 12, 8)
        val_lbl = QLabel(value)
        val_lbl.setFont(QFont("Segoe UI", 22, QFont.Weight.Bold))
        val_lbl.setStyleSheet(f"color: {color};")
        val_lbl.setObjectName(f"stat_{label.lower()}")
        lbl = QLabel(label)
        lbl.setStyleSheet("color: #94a3b8; font-size: 11px;")
        vl.addWidget(val_lbl)
        vl.addWidget(lbl)
        return card

    def _update_stat(self, card: QFrame, value: int):
        lbl = card.findChild(QLabel)
        if lbl:
            lbl.setText(str(value))

    # ── Public slots ──────────────────────────────────────────────────────
    def on_scan_result(self, result: dict):
        """
        Called by MainWindow when the engine emits a scan_result signal.

        result keys:
            symbol, signal, strategy, price, confidence, risk, status,
            reason, approved, executed
        """
        self._n_scanned += 1
        if result.get("signal") in ("BUY", "SELL"):
            self._n_signals += 1
        if result.get("approved"):
            self._n_approved += 1
        if result.get("executed"):
            self._n_executed += 1

        self._update_stat(self._card_scanned,  self._n_scanned)
        self._update_stat(self._card_signals,  self._n_signals)
        self._update_stat(self._card_approved, self._n_approved)
        self._update_stat(self._card_executed, self._n_executed)

        self._insert_row(result)
        self._status_lbl.setText(
            f"Last scan: {result.get('symbol', '?')} — "
            f"AI {result.get('confidence', 0)}% confidence"
        )

    def get_min_confidence(self) -> int:
        return self._conf_spin.value()

    def is_auto_trade(self) -> bool:
        return self._auto_trade_enabled

    # ── Internal ──────────────────────────────────────────────────────────
    def _on_auto_toggle(self, checked: bool):
        self._auto_trade_enabled = checked
        color = "#10b981" if checked else "#94a3b8"
        self._auto_toggle.setStyleSheet(f"color: {color}; font-size: 13px;")

    def _insert_row(self, r: dict):
        # Keep max 200 rows
        if self._table.rowCount() >= 200:
            self._table.removeRow(self._table.rowCount() - 1)

        self._table.insertRow(0)

        conf    = r.get("confidence", 0)
        action  = r.get("signal", "HOLD")
        risk    = r.get("risk", "HIGH")
        status  = r.get("status", "—")
        approved = r.get("approved", False)

        def cell(text, color=None, bold=False):
            item = QTableWidgetItem(str(text))
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if color:
                item.setForeground(QBrush(color))
            if bold:
                f = QFont()
                f.setBold(True)
                item.setFont(f)
            return item

        self._table.setItem(0, 0, cell(r.get("symbol", ""), bold=True))
        self._table.setItem(0, 1, cell(action, _color_for_action(action), bold=True))
        self._table.setItem(0, 2, cell(r.get("strategy", "")))
        self._table.setItem(0, 3, cell(f"₹{r.get('price', 0):,.2f}"))
        self._table.setItem(0, 4, cell(f"{conf}%", _color_for_confidence(conf), bold=True))
        self._table.setItem(0, 5, cell(risk, _color_for_risk(risk)))
        self._table.setItem(0, 6, cell(status,
            QColor("#10b981") if approved else QColor("#6b7280")))

        reason_item = QTableWidgetItem(r.get("reason", ""))
        reason_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        reason_item.setForeground(QBrush(QColor("#94a3b8")))
        self._table.setItem(0, 7, reason_item)

    def _clear(self):
        self._table.setRowCount(0)
        self._n_scanned = self._n_signals = self._n_approved = self._n_executed = 0
        for card in (self._card_scanned, self._card_signals,
                     self._card_approved, self._card_executed):
            self._update_stat(card, 0)
        self._status_lbl.setText("Cleared")

    def refresh(self):
        pass   # nothing to refresh on demand
