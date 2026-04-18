"""
TradeMind AI — Quick Order Dialog
Opened from Research / Intraday cards to place orders via Angel One.
"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QComboBox, QSpinBox, QDoubleSpinBox, QPushButton,
    QFrame, QMessageBox, QFormLayout
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont


class OrderDialog(QDialog):
    """
    Modal dialog for placing a BUY or SELL order.

    Signals:
        order_placed(dict)  — emitted after successful placement
    """
    order_placed = pyqtSignal(dict)

    def __init__(
        self,
        symbol:    str,
        direction: str   = "BUY",      # "BUY" or "SELL"
        price:     float = 0.0,
        stop_loss: float = 0.0,
        target:    float = 0.0,
        api=None,                       # AngelOneAPI instance
        parent=None,
    ):
        super().__init__(parent)
        self._api       = api
        self._symbol    = symbol
        self._direction = direction.upper()

        self.setWindowTitle(f"Place Order — {symbol}")
        self.setModal(True)
        self.setMinimumWidth(400)
        self.setStyleSheet("""
            QDialog   { background: #131722; color: #e2e8f0; }
            QLabel    { color: #e2e8f0; }
            QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
                background: #1e2330; color: #e2e8f0;
                border: 1px solid #374151; border-radius: 4px;
                padding: 6px 8px;
            }
            QPushButton {
                border-radius: 6px; padding: 8px 16px;
                font-weight: bold;
            }
        """)

        self._build_ui(price, stop_loss, target)

    # ── UI ────────────────────────────────────────────────────────────────
    def _build_ui(self, price, stop_loss, target):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        # ── Header ────────────────────────────────────────────────────────
        dir_color = "#10b981" if self._direction == "BUY" else "#ef4444"
        hdr = QLabel(f"{self._direction}  {self._symbol}")
        hdr.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        hdr.setStyleSheet(f"color: {dir_color};")
        layout.addWidget(hdr)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background: #2d3139;")
        layout.addWidget(sep)

        # ── Connection status ─────────────────────────────────────────────
        connected = self._api and self._api.is_connected()
        conn_lbl  = QLabel(
            "● Angel One connected" if connected else
            "⚠ Angel One not connected — this will be a PAPER trade"
        )
        conn_lbl.setStyleSheet(
            f"color: {'#10b981' if connected else '#f59e0b'}; font-size: 12px;"
        )
        layout.addWidget(conn_lbl)

        # ── Form ──────────────────────────────────────────────────────────
        form = QFormLayout()
        form.setSpacing(10)

        self._product = QComboBox()
        self._product.addItems(["INTRADAY", "DELIVERY"])
        form.addRow("Product:", self._product)

        self._order_type = QComboBox()
        self._order_type.addItems(["MARKET", "LIMIT"])
        self._order_type.currentTextChanged.connect(self._on_order_type_changed)
        form.addRow("Order Type:", self._order_type)

        self._price_spin = QDoubleSpinBox()
        self._price_spin.setRange(0, 1_000_000)
        self._price_spin.setDecimals(2)
        self._price_spin.setValue(price)
        self._price_spin.setPrefix("₹ ")
        self._price_spin.setEnabled(False)   # disabled for MARKET
        form.addRow("Limit Price:", self._price_spin)

        self._qty_spin = QSpinBox()
        self._qty_spin.setRange(1, 10_000)
        # Suggest qty based on ₹15K capital
        suggested = max(1, int(15_000 / price)) if price > 0 else 1
        self._qty_spin.setValue(min(suggested, 50))
        form.addRow("Quantity:", self._qty_spin)

        self._sl_spin = QDoubleSpinBox()
        self._sl_spin.setRange(0, 1_000_000)
        self._sl_spin.setDecimals(2)
        self._sl_spin.setValue(stop_loss)
        self._sl_spin.setPrefix("₹ ")
        form.addRow("Stop Loss:", self._sl_spin)

        self._tgt_spin = QDoubleSpinBox()
        self._tgt_spin.setRange(0, 1_000_000)
        self._tgt_spin.setDecimals(2)
        self._tgt_spin.setValue(target)
        self._tgt_spin.setPrefix("₹ ")
        form.addRow("Target:", self._tgt_spin)

        layout.addLayout(form)

        # ── Risk summary ──────────────────────────────────────────────────
        self._risk_lbl = QLabel()
        self._risk_lbl.setStyleSheet(
            "background: #1e2330; border-radius: 6px; "
            "padding: 8px; color: #94a3b8; font-size: 12px;"
        )
        self._risk_lbl.setWordWrap(True)
        layout.addWidget(self._risk_lbl)
        self._update_risk(price, stop_loss, target)

        self._qty_spin.valueChanged.connect(lambda: self._update_risk(price, stop_loss, target))

        # ── Buttons ───────────────────────────────────────────────────────
        btns = QHBoxLayout()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet(
            "background: #374151; color: #e2e8f0;"
        )
        cancel_btn.clicked.connect(self.reject)
        btns.addWidget(cancel_btn)

        self._confirm_btn = QPushButton(
            f"{'BUY' if self._direction == 'BUY' else 'SELL'} — Confirm"
        )
        self._confirm_btn.setStyleSheet(
            f"background: {dir_color}; color: #fff;"
        )
        self._confirm_btn.clicked.connect(self._on_confirm)
        btns.addWidget(self._confirm_btn)

        layout.addLayout(btns)

    def _on_order_type_changed(self, text: str):
        self._price_spin.setEnabled(text == "LIMIT")

    def _update_risk(self, price, stop_loss, target):
        qty   = self._qty_spin.value()
        value = qty * price
        risk  = abs(price - stop_loss) * qty if stop_loss else 0
        gain  = abs(target - price) * qty    if target    else 0
        rr    = gain / risk if risk > 0 else 0
        self._risk_lbl.setText(
            f"Trade value: ₹{value:,.0f}   |   "
            f"Max risk: ₹{risk:,.0f}   |   "
            f"Target gain: ₹{gain:,.0f}   |   "
            f"R:R {rr:.1f}"
        )

    # ── Order placement ───────────────────────────────────────────────────
    def _on_confirm(self):
        qty   = self._qty_spin.value()
        price = self._price_spin.value() if self._order_type.currentText() == "LIMIT" else 0.0
        sl    = self._sl_spin.value()
        tgt   = self._tgt_spin.value()
        prod  = self._product.currentText()

        if self._api and self._api.is_connected():
            self._confirm_btn.setEnabled(False)
            self._confirm_btn.setText("Placing…")
            try:
                result = self._api.place_order(
                    symbol      = self._symbol,
                    exchange    = "NSE",
                    direction   = self._direction,
                    quantity    = qty,
                    price       = price,
                    stop_loss   = sl or None,
                    target      = tgt or None,
                    product_type= prod,
                )
                if result["status"]:
                    QMessageBox.information(
                        self, "Order Placed",
                        f"✓ Order placed successfully\n"
                        f"Order ID: {result.get('orderid', 'N/A')}"
                    )
                    self.order_placed.emit({
                        "symbol": self._symbol, "direction": self._direction,
                        "qty": qty, "price": price, "orderid": result.get("orderid"),
                        "paper": False,
                    })
                    self.accept()
                else:
                    QMessageBox.warning(self, "Order Failed", result.get("message", "Unknown error"))
                    self._confirm_btn.setEnabled(True)
                    self._confirm_btn.setText(f"{self._direction} — Confirm")
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))
                self._confirm_btn.setEnabled(True)
                self._confirm_btn.setText(f"{self._direction} — Confirm")
        else:
            # Paper trade
            QMessageBox.information(
                self, "Paper Trade Logged",
                f"[PAPER] {self._direction} {qty}× {self._symbol}\n"
                f"Price: ₹{price or 'MARKET'}  SL: ₹{sl}  Target: ₹{tgt}"
            )
            self.order_placed.emit({
                "symbol": self._symbol, "direction": self._direction,
                "qty": qty, "price": price, "orderid": None, "paper": True,
            })
            self.accept()
