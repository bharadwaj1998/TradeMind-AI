"""
TradeMind AI — Live Trading Screen
Manual order entry + live watchlist + real-time P&L ticker.
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QSpinBox, QDoubleSpinBox,
    QFrame, QTableWidget, QTableWidgetItem, QHeaderView,
    QGroupBox, QFormLayout, QSplitter, QMessageBox
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont

from app.database.manager import DatabaseManager
from app.config import (
    COLOR_SUCCESS, COLOR_DANGER, COLOR_ACCENT, COLOR_TEXT,
    COLOR_TEXT_MUTED, COLOR_CARD, COLOR_BORDER, COLOR_WARNING,
    DEFAULT_CAPITAL, MAX_RISK_PER_TRADE_PCT
)


class LiveTradingWidget(QWidget):
    order_placed = pyqtSignal(dict)   # emitted when an order is submitted

    def __init__(self, db: DatabaseManager, parent=None):
        super().__init__(parent)
        self.db = db
        self._angel_api = None     # set later via set_api()
        self._build_ui()

        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self.refresh)
        self._refresh_timer.start(3000)

    def set_api(self, api):
        self._angel_api = api

    # ── Build UI ──────────────────────────────────────────────────────────
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        # Page header
        hdr = QHBoxLayout()
        title = QLabel("Live Trading")
        title.setObjectName("page-title")
        hdr.addWidget(title)
        hdr.addStretch()

        self._conn_badge = QLabel("● Not Connected")
        self._conn_badge.setStyleSheet(
            f"color: {COLOR_DANGER}; font-size: 12px; font-weight: 600;"
        )
        hdr.addWidget(self._conn_badge)
        layout.addLayout(hdr)

        # ── Main splitter: order panel | watchlist ──────────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)

        splitter.addWidget(self._build_order_panel())
        splitter.addWidget(self._build_watchlist_panel())
        splitter.setSizes([420, 700])
        layout.addWidget(splitter, stretch=1)

        # ── Open positions strip ────────────────────────────────────────
        layout.addWidget(self._build_positions_strip())

    def _build_order_panel(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("card")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(12)

        lbl = QLabel("Place Order")
        lbl.setStyleSheet("font-size: 16px; font-weight: 700;")
        layout.addWidget(lbl)

        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # Symbol
        self._sym_input = QLineEdit()
        self._sym_input.setPlaceholderText("e.g. RELIANCE, INFY")
        self._sym_input.textChanged.connect(self._update_risk_calc)
        form.addRow("Symbol:", self._sym_input)

        # Exchange
        self._exchange_combo = QComboBox()
        self._exchange_combo.addItems(["NSE", "BSE"])
        form.addRow("Exchange:", self._exchange_combo)

        # Direction
        dir_layout = QHBoxLayout()
        self._buy_btn = QPushButton("BUY")
        self._buy_btn.setObjectName("btn-success")
        self._buy_btn.setCheckable(True)
        self._buy_btn.setChecked(True)
        self._buy_btn.setMinimumHeight(36)

        self._sell_btn = QPushButton("SELL")
        self._sell_btn.setObjectName("btn-danger")
        self._sell_btn.setCheckable(True)
        self._sell_btn.setMinimumHeight(36)

        self._buy_btn.clicked.connect(lambda: self._set_direction("BUY"))
        self._sell_btn.clicked.connect(lambda: self._set_direction("SELL"))

        dir_layout.addWidget(self._buy_btn)
        dir_layout.addWidget(self._sell_btn)
        form.addRow("Direction:", dir_layout)

        # Quantity
        self._qty_spin = QSpinBox()
        self._qty_spin.setRange(1, 10000)
        self._qty_spin.setValue(1)
        self._qty_spin.valueChanged.connect(self._update_risk_calc)
        form.addRow("Quantity:", self._qty_spin)

        # Price (0 = market order)
        self._price_spin = QDoubleSpinBox()
        self._price_spin.setRange(0, 999999)
        self._price_spin.setDecimals(2)
        self._price_spin.setSpecialValueText("MARKET")
        self._price_spin.valueChanged.connect(self._update_risk_calc)
        form.addRow("Price (₹):", self._price_spin)

        # Stop Loss
        self._sl_spin = QDoubleSpinBox()
        self._sl_spin.setRange(0, 999999)
        self._sl_spin.setDecimals(2)
        self._sl_spin.setSpecialValueText("None")
        self._sl_spin.valueChanged.connect(self._update_risk_calc)
        form.addRow("Stop Loss (₹):", self._sl_spin)

        # Target
        self._target_spin = QDoubleSpinBox()
        self._target_spin.setRange(0, 999999)
        self._target_spin.setDecimals(2)
        self._target_spin.setSpecialValueText("None")
        form.addRow("Target (₹):", self._target_spin)

        layout.addLayout(form)

        # ── Risk calculator ─────────────────────────────────────────────
        risk_frame = QFrame()
        risk_frame.setStyleSheet(
            f"background: rgba(239,68,68,0.08); border: 1px solid {COLOR_BORDER}; "
            f"border-radius: 8px; padding: 8px;"
        )
        risk_layout = QVBoxLayout(risk_frame)
        risk_layout.setContentsMargins(8, 6, 8, 6)
        risk_layout.setSpacing(4)

        risk_title = QLabel("Risk Calculator")
        risk_title.setStyleSheet("font-size: 11px; font-weight: 700; color: #f59e0b;")
        risk_layout.addWidget(risk_title)

        self._risk_labels = {}
        for key, label in [("capital_risk", "Capital at Risk"), ("rr_ratio", "R:R Ratio"),
                            ("position_size", "Suggested Qty")]:
            row = QHBoxLayout()
            lbl_key = QLabel(label + ":")
            lbl_key.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; font-size: 11px;")
            val = QLabel("—")
            val.setStyleSheet("font-size: 11px; font-weight: 600;")
            row.addWidget(lbl_key)
            row.addStretch()
            row.addWidget(val)
            self._risk_labels[key] = val
            risk_layout.addLayout(row)

        layout.addWidget(risk_frame)

        # ── Submit button ───────────────────────────────────────────────
        self._submit_btn = QPushButton("PLACE ORDER")
        self._submit_btn.setObjectName("btn-primary")
        self._submit_btn.setMinimumHeight(42)
        self._submit_btn.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        self._submit_btn.clicked.connect(self._place_order)
        layout.addWidget(self._submit_btn)

        layout.addStretch()
        return frame

    def _build_watchlist_panel(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("card")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)

        hdr = QHBoxLayout()
        lbl = QLabel("Watchlist")
        lbl.setStyleSheet("font-size: 16px; font-weight: 700;")
        hdr.addWidget(lbl)
        hdr.addStretch()

        add_sym = QLineEdit()
        add_sym.setPlaceholderText("Add symbol…")
        add_sym.setMaximumWidth(140)
        add_sym.returnPressed.connect(lambda: self._add_to_watchlist(add_sym.text()))
        hdr.addWidget(add_sym)

        layout.addLayout(hdr)

        self._watchlist_table = QTableWidget(0, 5)
        self._watchlist_table.setHorizontalHeaderLabels(
            ["Symbol", "LTP", "Change", "Volume", "Action"]
        )
        self._watchlist_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._watchlist_table.verticalHeader().setVisible(False)
        self._watchlist_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._watchlist_table.setAlternatingRowColors(True)
        layout.addWidget(self._watchlist_table)

        # Seed default watchlist symbols
        for sym in ["NIFTY 50", "RELIANCE", "INFY", "HDFCBANK", "TCS", "WIPRO"]:
            self._add_to_watchlist(sym, refresh=False)

        return frame

    def _build_positions_strip(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("card")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(8)
        frame.setMaximumHeight(220)

        hdr = QHBoxLayout()
        lbl = QLabel("Open Positions")
        lbl.setStyleSheet("font-size: 14px; font-weight: 700;")
        hdr.addWidget(lbl)
        hdr.addStretch()
        layout.addLayout(hdr)

        self._open_pos_table = QTableWidget(0, 7)
        self._open_pos_table.setHorizontalHeaderLabels(
            ["Symbol", "Direction", "Qty", "Entry", "LTP", "P&L", "Action"]
        )
        self._open_pos_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._open_pos_table.verticalHeader().setVisible(False)
        self._open_pos_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self._open_pos_table)

        return frame

    # ── Logic ─────────────────────────────────────────────────────────────
    def _set_direction(self, direction: str):
        self._buy_btn.setChecked(direction == "BUY")
        self._sell_btn.setChecked(direction == "SELL")

    def _get_direction(self) -> str:
        return "BUY" if self._buy_btn.isChecked() else "SELL"

    def _update_risk_calc(self):
        try:
            price = self._price_spin.value()
            sl    = self._sl_spin.value()
            qty   = self._qty_spin.value()

            if price > 0 and sl > 0 and price != sl:
                risk_per_share = abs(price - sl)
                total_risk     = risk_per_share * qty
                cap_risk_pct   = (total_risk / DEFAULT_CAPITAL) * 100
                target         = self._target_spin.value()
                rr = abs(target - price) / risk_per_share if target > 0 else 0
                suggested_qty  = int((DEFAULT_CAPITAL * MAX_RISK_PER_TRADE_PCT / 100) / risk_per_share)

                color = COLOR_DANGER if cap_risk_pct > MAX_RISK_PER_TRADE_PCT else COLOR_SUCCESS
                self._risk_labels["capital_risk"].setText(f"₹{total_risk:,.0f}  ({cap_risk_pct:.1f}%)")
                self._risk_labels["capital_risk"].setStyleSheet(f"font-size:11px; font-weight:600; color:{color};")
                self._risk_labels["rr_ratio"].setText(f"1 : {rr:.1f}" if rr > 0 else "—")
                self._risk_labels["position_size"].setText(str(suggested_qty))
            else:
                for lbl in self._risk_labels.values():
                    lbl.setText("—")
        except Exception:
            pass

    def _place_order(self):
        symbol = self._sym_input.text().strip().upper()
        if not symbol:
            QMessageBox.warning(self, "Missing Symbol", "Please enter a stock symbol.")
            return

        price     = self._price_spin.value()
        sl        = self._sl_spin.value()
        target    = self._target_spin.value()
        qty       = self._qty_spin.value()
        direction = self._get_direction()
        exchange  = self._exchange_combo.currentText()

        order_data = {
            "symbol":    symbol,
            "exchange":  exchange,
            "direction": direction,
            "quantity":  qty,
            "price":     price,
            "stop_loss": sl if sl > 0 else None,
            "target":    target if target > 0 else None,
        }

        # Try live API first; fall back to paper trade
        if self._angel_api and self._angel_api.is_connected():
            try:
                result = self._angel_api.place_order(**order_data)
                order_data["order_id"] = result.get("orderid")
            except Exception as e:
                QMessageBox.warning(self, "Order Failed", str(e))
                return
        else:
            # Paper trading: use current price as entry
            order_data["entry_price"] = price if price > 0 else 0.0
            QMessageBox.information(
                self, "Paper Trade",
                f"API not connected — trade recorded as paper trade.\n\n"
                f"{direction} {qty}x {symbol}"
            )

        self.db.add_trade(
            symbol=symbol,
            exchange=exchange,
            direction=direction,
            quantity=qty,
            entry_price=price,
            stop_loss=sl if sl > 0 else None,
            target=target if target > 0 else None,
            strategy="Manual",
        )
        self.db.add_alert(
            title=f"Order placed: {direction} {qty}x {symbol}",
            level="INFO"
        )
        self.order_placed.emit(order_data)
        self.refresh()

    def _add_to_watchlist(self, symbol: str, refresh: bool = True):
        symbol = symbol.strip().upper()
        if not symbol:
            return
        row = self._watchlist_table.rowCount()
        self._watchlist_table.insertRow(row)
        cells = [symbol, "—", "—", "—"]
        for col, text in enumerate(cells):
            item = QTableWidgetItem(text)
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._watchlist_table.setItem(row, col, item)
        # Remove button
        remove_btn = QPushButton("✕")
        remove_btn.setObjectName("btn-ghost")
        remove_btn.setFixedSize(28, 28)
        remove_btn.clicked.connect(lambda _, r=row: self._watchlist_table.removeRow(r))
        self._watchlist_table.setCellWidget(row, 4, remove_btn)

    def refresh(self):
        trades = self.db.get_trades(status="OPEN")
        self._open_pos_table.setRowCount(len(trades))
        for row, trade in enumerate(trades):
            pnl = trade.pnl or 0
            cells = [
                (trade.symbol, COLOR_TEXT),
                (trade.direction, COLOR_SUCCESS if trade.direction == "BUY" else COLOR_DANGER),
                (str(trade.quantity), COLOR_TEXT),
                (f"₹{trade.entry_price:,.2f}", COLOR_TEXT),
                ("—", COLOR_TEXT_MUTED),
                (f"₹{pnl:+,.2f}", COLOR_SUCCESS if pnl >= 0 else COLOR_DANGER),
            ]
            for col, (text, color) in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item.setForeground(QColor(color))
                self._open_pos_table.setItem(row, col, item)

            # Close button
            close_btn = QPushButton("Close")
            close_btn.setObjectName("btn-danger")
            close_btn.setFixedHeight(26)
            tid = trade.id
            close_btn.clicked.connect(lambda _, t=tid: self._close_trade(t))
            self._open_pos_table.setCellWidget(row, 6, close_btn)

    def update_ltps(self, ltps: dict):
        """Update watchlist LTP column from engine's price feed."""
        for row in range(self._watchlist_table.rowCount()):
            sym_item = self._watchlist_table.item(row, 0)
            if not sym_item:
                continue
            symbol = sym_item.text()
            ltp = ltps.get(symbol)
            if ltp is None:
                continue

            # LTP column (col 1)
            ltp_item = QTableWidgetItem(f"₹{ltp:,.2f}")
            ltp_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._watchlist_table.setItem(row, 1, ltp_item)

            # Change column (col 2) — store prev price in item data
            prev_item = self._watchlist_table.item(row, 1)
            try:
                prev = float(prev_item.text().replace("₹", "").replace(",", "")) if prev_item else ltp
            except (ValueError, AttributeError):
                prev = ltp
            chg_pct = (ltp - prev) / prev * 100 if prev > 0 else 0
            chg_text = f"{chg_pct:+.2f}%"
            chg_item = QTableWidgetItem(chg_text)
            chg_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            clr = COLOR_SUCCESS if chg_pct >= 0 else COLOR_DANGER
            chg_item.setForeground(QColor(clr))
            self._watchlist_table.setItem(row, 2, chg_item)

    def _close_trade(self, trade_id: int):
        reply = QMessageBox.question(
            self, "Close Trade",
            "Close this trade at market price?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.db.close_trade(trade_id, exit_price=0.0)   # 0 = market close placeholder
            self.refresh()
