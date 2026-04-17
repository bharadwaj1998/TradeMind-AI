"""
TradeMind AI — Trade History Screen
Searchable, sortable table of all past trades with P&L breakdown.
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QFrame, QSizePolicy
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

from app.database.manager import DatabaseManager
from app.config import COLOR_SUCCESS, COLOR_DANGER, COLOR_TEXT, COLOR_TEXT_MUTED, COLOR_WARNING


class HistoryWidget(QWidget):
    def __init__(self, db: DatabaseManager, parent=None):
        super().__init__(parent)
        self.db = db
        self._all_trades = []
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        # ── Header ────────────────────────────────────────────────────────
        hdr = QHBoxLayout()
        title = QLabel("Trade History")
        title.setObjectName("page-title")
        hdr.addWidget(title)
        hdr.addStretch()
        layout.addLayout(hdr)

        # ── Summary strip ─────────────────────────────────────────────────
        layout.addWidget(self._build_summary_strip())

        # ── Filters ───────────────────────────────────────────────────────
        filters = QHBoxLayout()
        filters.setSpacing(10)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Search symbol…")
        self._search.setMaximumWidth(220)
        self._search.textChanged.connect(self._apply_filter)
        filters.addWidget(self._search)

        self._status_filter = QComboBox()
        self._status_filter.addItems(["All", "OPEN", "CLOSED", "CANCELLED"])
        self._status_filter.currentTextChanged.connect(self._apply_filter)
        filters.addWidget(self._status_filter)

        self._dir_filter = QComboBox()
        self._dir_filter.addItems(["All Directions", "BUY", "SELL"])
        self._dir_filter.currentTextChanged.connect(self._apply_filter)
        filters.addWidget(self._dir_filter)

        filters.addStretch()

        export_btn = QPushButton("Export CSV")
        export_btn.setObjectName("btn-ghost")
        export_btn.clicked.connect(self._export_csv)
        filters.addWidget(export_btn)

        layout.addLayout(filters)

        # ── Main table ────────────────────────────────────────────────────
        self._table = QTableWidget(0, 9)
        self._table.setHorizontalHeaderLabels([
            "#", "Symbol", "Dir", "Qty", "Entry ₹", "Exit ₹",
            "P&L ₹", "Strategy", "Date"
        ])
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(0, 48)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSortingEnabled(True)
        layout.addWidget(self._table)

    def _build_summary_strip(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("card")
        row = QHBoxLayout(frame)
        row.setContentsMargins(16, 12, 16, 12)
        row.setSpacing(32)

        self._summary_labels = {}
        for key, label in [
            ("total",     "Total Trades"),
            ("wins",      "Wins"),
            ("losses",    "Losses"),
            ("win_rate",  "Win Rate"),
            ("total_pnl", "Total P&L"),
            ("avg_trade", "Avg Trade P&L"),
        ]:
            col = QVBoxLayout()
            col.setSpacing(2)
            lbl = QLabel(label)
            lbl.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; font-size: 10px; font-weight: 700; letter-spacing:0.5px;")
            val = QLabel("—")
            val.setStyleSheet("font-size: 18px; font-weight: 700;")
            col.addWidget(lbl)
            col.addWidget(val)
            row.addLayout(col)
            self._summary_labels[key] = val

        row.addStretch()
        return frame

    # ── Data ──────────────────────────────────────────────────────────────
    def refresh(self):
        self._all_trades = self.db.get_trades(limit=500)
        self._apply_filter()
        self._update_summary()

    def _apply_filter(self):
        search  = self._search.text().upper()
        status  = self._status_filter.currentText()
        dirn    = self._dir_filter.currentText()

        filtered = self._all_trades
        if search:
            filtered = [t for t in filtered if search in t.symbol.upper()]
        if status != "All":
            filtered = [t for t in filtered if t.status == status]
        if dirn != "All Directions":
            filtered = [t for t in filtered if t.direction == dirn]

        self._populate_table(filtered)

    def _populate_table(self, trades):
        self._table.setSortingEnabled(False)
        self._table.setRowCount(len(trades))
        for row, trade in enumerate(trades):
            pnl = trade.pnl or 0
            pnl_color = COLOR_SUCCESS if pnl >= 0 else COLOR_DANGER

            cells = [
                (str(trade.id),                                        COLOR_TEXT_MUTED),
                (trade.symbol,                                         COLOR_TEXT),
                (trade.direction,
                    COLOR_SUCCESS if trade.direction == "BUY" else COLOR_DANGER),
                (str(trade.quantity),                                  COLOR_TEXT),
                (f"{trade.entry_price:,.2f}",                         COLOR_TEXT),
                (f"{trade.exit_price:,.2f}" if trade.exit_price else "—", COLOR_TEXT_MUTED),
                (f"{pnl:+,.2f}",                                      pnl_color),
                (trade.strategy or "Manual",                          COLOR_TEXT_MUTED),
                (trade.entry_time.strftime("%d %b %Y %H:%M")
                    if trade.entry_time else "—",                      COLOR_TEXT_MUTED),
            ]
            for col, (text, color) in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item.setForeground(QColor(color))
                self._table.setItem(row, col, item)

        self._table.setSortingEnabled(True)

    def _update_summary(self):
        trades = [t for t in self._all_trades if t.status == "CLOSED"]
        wins   = [t for t in trades if (t.pnl or 0) > 0]
        losses = [t for t in trades if (t.pnl or 0) <= 0]
        total_pnl = sum(t.pnl or 0 for t in trades)
        avg_pnl   = total_pnl / len(trades) if trades else 0

        self._summary_labels["total"].setText(str(len(trades)))
        self._summary_labels["wins"].setText(str(len(wins)))
        self._summary_labels["losses"].setText(str(len(losses)))
        wr = len(wins) / len(trades) * 100 if trades else 0
        self._summary_labels["win_rate"].setText(f"{wr:.1f}%")
        self._summary_labels["win_rate"].setStyleSheet(
            f"font-size:18px; font-weight:700; color:{COLOR_SUCCESS if wr >= 50 else COLOR_DANGER};"
        )
        c = COLOR_SUCCESS if total_pnl >= 0 else COLOR_DANGER
        self._summary_labels["total_pnl"].setText(f"₹{total_pnl:+,.0f}")
        self._summary_labels["total_pnl"].setStyleSheet(f"font-size:18px; font-weight:700; color:{c};")
        self._summary_labels["avg_trade"].setText(f"₹{avg_pnl:+,.0f}")

    def _export_csv(self):
        from PyQt6.QtWidgets import QFileDialog
        import csv, os
        path, _ = QFileDialog.getSaveFileName(self, "Export CSV", "trades.csv", "CSV Files (*.csv)")
        if not path:
            return
        trades = self._all_trades
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["ID","Symbol","Direction","Qty","Entry","Exit","PnL","Strategy","Date"])
            for t in trades:
                writer.writerow([
                    t.id, t.symbol, t.direction, t.quantity,
                    t.entry_price, t.exit_price or "", t.pnl or "",
                    t.strategy or "", t.entry_time
                ])
