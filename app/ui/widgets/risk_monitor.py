"""
TradeMind AI — Risk Monitor Screen
Shows real-time risk gauges, drawdown meter, position concentration,
daily loss limit, and active alerts.
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QProgressBar, QFrame, QTableWidget, QTableWidgetItem,
    QHeaderView, QGridLayout
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor

from app.database.manager import DatabaseManager
from app.config import (
    COLOR_SUCCESS, COLOR_DANGER, COLOR_WARNING, COLOR_TEXT,
    COLOR_TEXT_MUTED, COLOR_CARD, COLOR_BORDER, COLOR_ACCENT,
    DEFAULT_CAPITAL, MAX_RISK_PER_TRADE_PCT, MAX_DAILY_LOSS_PCT
)


class RiskGauge(QFrame):
    """Labelled progress bar used as a risk gauge."""
    def __init__(self, title: str, max_val: float = 100, suffix: str = "%", parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self._max_val = max_val
        self._suffix  = suffix
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(6)

        hdr = QHBoxLayout()
        self._title_lbl = QLabel(title.upper())
        self._title_lbl.setStyleSheet(
            f"color: {COLOR_TEXT_MUTED}; font-size: 10px; font-weight: 700; letter-spacing:0.5px;"
        )
        hdr.addWidget(self._title_lbl)
        hdr.addStretch()
        self._val_lbl = QLabel(f"0{suffix}")
        self._val_lbl.setStyleSheet("font-size: 18px; font-weight: 700;")
        hdr.addWidget(self._val_lbl)
        layout.addLayout(hdr)

        self._bar = QProgressBar()
        self._bar.setRange(0, int(max_val * 10))
        self._bar.setValue(0)
        self._bar.setFixedHeight(8)
        self._bar.setTextVisible(False)
        layout.addWidget(self._bar)

        self._status = QLabel("Safe")
        self._status.setStyleSheet(f"color: {COLOR_SUCCESS}; font-size: 11px; font-weight:600;")
        layout.addWidget(self._status)

    def update(self, value: float):
        pct = min(value / self._max_val * 100, 100)
        self._bar.setValue(int(pct * 10))
        self._val_lbl.setText(f"{value:.1f}{self._suffix}")

        if pct >= 80:
            self._bar.setObjectName("progress-danger")
            self._status.setText("CRITICAL — consider stopping")
            self._status.setStyleSheet(f"color: {COLOR_DANGER}; font-size: 11px; font-weight:700;")
        elif pct >= 50:
            self._bar.setObjectName("progress-warning")
            self._status.setText("Elevated risk")
            self._status.setStyleSheet(f"color: {COLOR_WARNING}; font-size: 11px; font-weight:600;")
        else:
            self._bar.setObjectName("progress-success")
            self._status.setText("Safe")
            self._status.setStyleSheet(f"color: {COLOR_SUCCESS}; font-size: 11px; font-weight:600;")

        # Re-apply style
        self._bar.style().unpolish(self._bar)
        self._bar.style().polish(self._bar)


class RiskMonitorWidget(QWidget):
    def __init__(self, db: DatabaseManager, parent=None):
        super().__init__(parent)
        self.db = db
        self._build_ui()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh)
        self._timer.start(5000)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        # Header
        hdr = QHBoxLayout()
        title = QLabel("Risk Monitor")
        title.setObjectName("page-title")
        hdr.addWidget(title)
        hdr.addStretch()
        self._halt_lbl = QLabel("")
        self._halt_lbl.setStyleSheet(
            f"background: {COLOR_DANGER}22; color: {COLOR_DANGER}; "
            f"border-radius: 8px; padding: 4px 12px; font-weight: 700;"
        )
        self._halt_lbl.hide()
        hdr.addWidget(self._halt_lbl)
        layout.addLayout(hdr)

        # Gauges grid
        grid = QGridLayout()
        grid.setSpacing(12)

        self._gauge_daily_loss    = RiskGauge("Daily Loss", max_val=MAX_DAILY_LOSS_PCT)
        self._gauge_exposure      = RiskGauge("Capital Exposed", max_val=100)
        self._gauge_open_trades   = RiskGauge("Open Positions", max_val=3, suffix="")
        self._gauge_drawdown      = RiskGauge("Peak Drawdown", max_val=20)

        grid.addWidget(self._gauge_daily_loss,  0, 0)
        grid.addWidget(self._gauge_exposure,    0, 1)
        grid.addWidget(self._gauge_open_trades, 0, 2)
        grid.addWidget(self._gauge_drawdown,    0, 3)
        layout.addLayout(grid)

        # Middle: Positions table + recent alerts
        mid = QHBoxLayout()
        mid.setSpacing(12)
        mid.addWidget(self._build_positions_risk_table(), stretch=3)
        mid.addWidget(self._build_alerts_panel(), stretch=2)
        layout.addLayout(mid)

    def _build_positions_risk_table(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("card")
        v = QVBoxLayout(frame)
        v.setContentsMargins(16, 14, 16, 14)
        v.setSpacing(8)

        lbl = QLabel("Position Risk Breakdown")
        lbl.setStyleSheet("font-size: 14px; font-weight: 700;")
        v.addWidget(lbl)

        self._pos_risk_table = QTableWidget(0, 5)
        self._pos_risk_table.setHorizontalHeaderLabels(
            ["Symbol", "Direction", "Capital %", "Stop Loss", "Max Loss"]
        )
        self._pos_risk_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._pos_risk_table.verticalHeader().setVisible(False)
        self._pos_risk_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._pos_risk_table.setAlternatingRowColors(True)
        v.addWidget(self._pos_risk_table)
        return frame

    def _build_alerts_panel(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("card")
        v = QVBoxLayout(frame)
        v.setContentsMargins(16, 14, 16, 14)
        v.setSpacing(8)

        lbl = QLabel("Risk Alerts")
        lbl.setStyleSheet("font-size: 14px; font-weight: 700;")
        v.addWidget(lbl)

        self._alerts_table = QTableWidget(0, 3)
        self._alerts_table.setHorizontalHeaderLabels(["Level", "Title", "Time"])
        self._alerts_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._alerts_table.verticalHeader().setVisible(False)
        self._alerts_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        v.addWidget(self._alerts_table)
        return frame

    def refresh(self):
        stats    = self.db.get_today_stats()
        trades   = self.db.get_trades(status="OPEN")

        daily_loss_pct = abs(min(stats["total_pnl"], 0)) / DEFAULT_CAPITAL * 100
        exposure_pct   = sum(
            (t.entry_price * t.quantity) for t in trades
        ) / DEFAULT_CAPITAL * 100

        self._gauge_daily_loss.update(daily_loss_pct)
        self._gauge_exposure.update(min(exposure_pct, 100))
        self._gauge_open_trades.update(len(trades))
        self._gauge_drawdown.update(daily_loss_pct)

        # Halt banner
        if daily_loss_pct >= MAX_DAILY_LOSS_PCT:
            self._halt_lbl.setText(
                f"  ⚠ TRADING HALTED — Daily loss limit {MAX_DAILY_LOSS_PCT:.0f}% reached  "
            )
            self._halt_lbl.show()
        else:
            self._halt_lbl.hide()

        # Positions risk table
        self._pos_risk_table.setRowCount(len(trades))
        for row, trade in enumerate(trades):
            cap_pct = trade.entry_price * trade.quantity / DEFAULT_CAPITAL * 100
            sl_dist = abs(trade.entry_price - trade.stop_loss) if trade.stop_loss else 0
            max_loss = sl_dist * trade.quantity if trade.stop_loss else 0
            color = COLOR_DANGER if cap_pct > 20 else COLOR_TEXT

            cells = [
                (trade.symbol, color),
                (trade.direction, COLOR_SUCCESS if trade.direction == "BUY" else COLOR_DANGER),
                (f"{cap_pct:.1f}%", color),
                (f"₹{trade.stop_loss:,.2f}" if trade.stop_loss else "None", COLOR_TEXT_MUTED),
                (f"₹{max_loss:,.0f}" if max_loss else "—", COLOR_DANGER if max_loss > 0 else COLOR_TEXT_MUTED),
            ]
            for col, (text, clr) in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item.setForeground(QColor(clr))
                self._pos_risk_table.setItem(row, col, item)

        # Alerts
        alerts = self.db.get_alerts(limit=20)
        level_colors = {"INFO": COLOR_ACCENT, "WARNING": COLOR_WARNING, "DANGER": COLOR_DANGER}
        self._alerts_table.setRowCount(len(alerts))
        for row, alert in enumerate(alerts):
            color = level_colors.get(alert.level, COLOR_TEXT_MUTED)
            for col, text in enumerate([alert.level, alert.title,
                                         alert.created_at.strftime("%H:%M")]):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item.setForeground(QColor(color if col == 0 else COLOR_TEXT))
                self._alerts_table.setItem(row, col, item)
