"""
TradeMind AI — Dashboard Screen
Displays: portfolio summary cards, equity curve chart, open positions table, recent trades.
"""
from datetime import date, timedelta
import random  # used only for demo sparklines until live data connects

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QScrollArea, QFrame, QTableWidget, QTableWidgetItem,
    QHeaderView, QSizePolicy, QGridLayout
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor

try:
    import pyqtgraph as pg
    HAS_PYQTGRAPH = True
except ImportError:
    HAS_PYQTGRAPH = False

from app.database.manager import DatabaseManager
from app.ui.components.metric_card import MetricCard
from app.config import (
    COLOR_BG, COLOR_CARD, COLOR_BORDER, COLOR_TEXT, COLOR_TEXT_MUTED,
    COLOR_SUCCESS, COLOR_DANGER, COLOR_ACCENT, COLOR_WARNING,
    DEFAULT_CAPITAL
)


class DashboardWidget(QWidget):
    def __init__(self, db: DatabaseManager, parent=None):
        super().__init__(parent)
        self.db = db
        self._build_ui()
        # Auto-refresh every 5 seconds
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh)
        self._timer.start(5000)

    # ── Build UI ──────────────────────────────────────────────────────────
    def _build_ui(self):
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        container = QWidget()
        scroll.setWidget(container)

        main = QVBoxLayout(self)
        main.setContentsMargins(0, 0, 0, 0)
        main.addWidget(scroll)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        # ── Page header ───────────────────────────────────────────────────
        header = QHBoxLayout()
        title = QLabel("Dashboard")
        title.setObjectName("page-title")
        subtitle = QLabel("Portfolio overview  •  Today's performance")
        subtitle.setObjectName("page-subtitle")
        header.addWidget(title)
        header.addSpacing(12)
        header.addWidget(subtitle)
        header.addStretch()

        self._last_updated = QLabel("Last updated: —")
        self._last_updated.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; font-size: 11px;")
        header.addWidget(self._last_updated)
        layout.addLayout(header)

        # ── Metric cards row ──────────────────────────────────────────────
        cards_grid = QGridLayout()
        cards_grid.setSpacing(12)

        self._card_portfolio = MetricCard("Portfolio Value", "₹0", "", "Total", "▦")
        self._card_pnl       = MetricCard("Today's P&L",    "₹0", "", "Realised", "⚡")
        self._card_trades    = MetricCard("Trades Today",   "0",  "", "Executed", "📋")
        self._card_winrate   = MetricCard("Win Rate",        "0%", "", "Today",    "🎯")
        self._card_drawdown  = MetricCard("Max Drawdown",   "0%", "", "Today",    "📉")
        self._card_positions = MetricCard("Open Positions", "0",  "", "Active",   "🔓")

        for i, card in enumerate([
            self._card_portfolio, self._card_pnl, self._card_trades,
            self._card_winrate, self._card_drawdown, self._card_positions
        ]):
            cards_grid.addWidget(card, 0, i)

        layout.addLayout(cards_grid)

        # ── Middle row: equity curve + positions ──────────────────────────
        mid = QHBoxLayout()
        mid.setSpacing(12)

        mid.addWidget(self._build_equity_chart(), stretch=3)
        mid.addWidget(self._build_positions_panel(), stretch=2)
        layout.addLayout(mid)

        # ── Recent trades table ───────────────────────────────────────────
        layout.addWidget(self._build_recent_trades())

    def _build_equity_chart(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("card")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)

        hdr = QHBoxLayout()
        lbl = QLabel("Equity Curve")
        lbl.setStyleSheet("font-size: 14px; font-weight: 700;")
        hdr.addWidget(lbl)
        hdr.addStretch()
        self._equity_period = QLabel("30 days")
        self._equity_period.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; font-size: 11px;")
        hdr.addWidget(self._equity_period)
        layout.addLayout(hdr)

        if HAS_PYQTGRAPH:
            pg.setConfigOption("background", COLOR_CARD)
            pg.setConfigOption("foreground", COLOR_TEXT_MUTED)
            self._equity_plot = pg.PlotWidget()
            self._equity_plot.setMinimumHeight(220)
            self._equity_plot.showGrid(x=False, y=True, alpha=0.2)
            self._equity_plot.getAxis("bottom").setStyle(showValues=True)
            self._equity_plot.getAxis("left").setStyle(showValues=True)
            # Remove borders
            self._equity_plot.getViewBox().setBorder(None)
            layout.addWidget(self._equity_plot)
        else:
            placeholder = QLabel("Install pyqtgraph for live charts\n(pip install pyqtgraph)")
            placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            placeholder.setMinimumHeight(220)
            placeholder.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; font-size: 12px;")
            layout.addWidget(placeholder)
            self._equity_plot = None

        return frame

    def _build_positions_panel(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("card")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)

        hdr = QLabel("Open Positions")
        hdr.setStyleSheet("font-size: 14px; font-weight: 700;")
        layout.addWidget(hdr)

        self._pos_table = QTableWidget(0, 4)
        self._pos_table.setHorizontalHeaderLabels(["Symbol", "Qty", "Avg Price", "P&L"])
        self._pos_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._pos_table.verticalHeader().setVisible(False)
        self._pos_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._pos_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._pos_table.setAlternatingRowColors(True)
        layout.addWidget(self._pos_table)

        self._no_positions = QLabel("No open positions")
        self._no_positions.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._no_positions.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; font-size: 12px; padding: 20px;")
        layout.addWidget(self._no_positions)

        return frame

    def _build_recent_trades(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("card")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)

        hdr = QHBoxLayout()
        lbl = QLabel("Recent Trades")
        lbl.setStyleSheet("font-size: 14px; font-weight: 700;")
        hdr.addWidget(lbl)
        hdr.addStretch()
        layout.addLayout(hdr)

        self._trades_table = QTableWidget(0, 7)
        self._trades_table.setHorizontalHeaderLabels(
            ["Symbol", "Direction", "Qty", "Entry", "Exit", "P&L", "Strategy"]
        )
        self._trades_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._trades_table.verticalHeader().setVisible(False)
        self._trades_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._trades_table.setAlternatingRowColors(True)
        self._trades_table.setMaximumHeight(220)
        layout.addWidget(self._trades_table)

        return frame

    # ── Data refresh ──────────────────────────────────────────────────────
    def refresh(self):
        from datetime import datetime
        self._last_updated.setText(f"Updated: {datetime.now().strftime('%H:%M:%S')}")
        self._refresh_cards()
        self._refresh_equity_chart()
        self._refresh_positions()
        self._refresh_recent_trades()

    def _refresh_cards(self):
        stats = self.db.get_today_stats()
        history = self.db.get_portfolio_history(1)
        portfolio_val = history[0].total_value if history else DEFAULT_CAPITAL

        pnl = stats["total_pnl"]
        pnl_str = f"₹{pnl:+,.0f}" if pnl != 0 else "₹0"
        pnl_change = (f"▲ +₹{pnl:,.0f}" if pnl > 0
                      else f"▼ ₹{pnl:,.0f}" if pnl < 0 else "—")

        self._card_portfolio.set_all(f"₹{portfolio_val:,.0f}")
        self._card_pnl.set_all(pnl_str, pnl_change)
        self._card_trades.set_all(str(stats["total_trades"]))
        self._card_winrate.set_all(f"{stats['win_rate']:.1f}%")

    def _refresh_equity_chart(self):
        if not HAS_PYQTGRAPH or self._equity_plot is None:
            return
        history = self.db.get_portfolio_history(30)
        if not history:
            # Show flat line at starting capital
            y = [DEFAULT_CAPITAL] * 5
            x = list(range(5))
        else:
            history = list(reversed(history))
            y = [h.total_value for h in history]
            x = list(range(len(y)))

        self._equity_plot.clear()
        pen = pg.mkPen(color=COLOR_ACCENT, width=2)
        fill = pg.FillBetweenItem(
            pg.PlotDataItem(x, y, pen=pen),
            pg.PlotDataItem(x, [min(y)] * len(y), pen=pg.mkPen(None)),
            brush=pg.mkBrush(color=(59, 130, 246, 30)),
        )
        self._equity_plot.addItem(fill)
        self._equity_plot.plot(x, y, pen=pen)

    def _refresh_positions(self):
        from app.database.manager import Position
        positions = self.db.session().query(Position).all()
        self._pos_table.setRowCount(len(positions))
        self._no_positions.setVisible(len(positions) == 0)

        for row, pos in enumerate(positions):
            items = [
                pos.symbol,
                str(pos.quantity),
                f"₹{pos.avg_price:,.2f}",
                f"₹{pos.pnl:+,.2f}",
            ]
            for col, text in enumerate(items):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if col == 3:
                    item.setForeground(
                        QColor(COLOR_SUCCESS) if pos.pnl >= 0 else QColor(COLOR_DANGER)
                    )
                self._pos_table.setItem(row, col, item)

    def _refresh_recent_trades(self):
        trades = self.db.get_trades(limit=10)
        self._trades_table.setRowCount(len(trades))
        for row, trade in enumerate(trades):
            direction_color = COLOR_SUCCESS if trade.direction == "BUY" else COLOR_DANGER
            pnl_color = COLOR_SUCCESS if (trade.pnl or 0) >= 0 else COLOR_DANGER

            cells = [
                (trade.symbol, COLOR_TEXT),
                (trade.direction, direction_color),
                (str(trade.quantity), COLOR_TEXT),
                (f"₹{trade.entry_price:,.2f}", COLOR_TEXT),
                (f"₹{trade.exit_price:,.2f}" if trade.exit_price else "—", COLOR_TEXT_MUTED),
                (f"₹{trade.pnl:+,.2f}" if trade.pnl else "—", pnl_color),
                (trade.strategy or "Manual", COLOR_TEXT_MUTED),
            ]
            for col, (text, color) in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item.setForeground(QColor(color))
                self._trades_table.setItem(row, col, item)
