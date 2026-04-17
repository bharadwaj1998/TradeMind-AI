"""
TradeMind AI — Strategies Screen
Displays strategy cards with toggle on/off, parameter editor, and live signal log.
"""
import json
from datetime import datetime
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QGridLayout, QScrollArea, QDialog, QFormLayout,
    QLineEdit, QTextEdit, QDialogButtonBox, QMessageBox,
    QSplitter, QTableWidget, QTableWidgetItem, QHeaderView
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QColor

from app.database.manager import DatabaseManager, Strategy
from app.config import (
    COLOR_SUCCESS, COLOR_DANGER, COLOR_ACCENT, COLOR_TEXT,
    COLOR_TEXT_MUTED, COLOR_CARD, COLOR_BORDER, COLOR_WARNING
)


class StrategyCard(QFrame):
    def __init__(self, strategy: Strategy, on_toggle, on_edit, parent=None):
        super().__init__(parent)
        self.strategy = strategy
        self.on_toggle = on_toggle
        self.on_edit   = on_edit
        self.setObjectName("card")
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)

        # Header
        hdr = QHBoxLayout()
        name_lbl = QLabel(self.strategy.name)
        name_lbl.setStyleSheet("font-size: 15px; font-weight: 700;")
        hdr.addWidget(name_lbl)
        hdr.addStretch()

        self._status_badge = QLabel("ACTIVE" if self.strategy.is_active else "INACTIVE")
        color = COLOR_SUCCESS if self.strategy.is_active else COLOR_TEXT_MUTED
        self._status_badge.setStyleSheet(
            f"background: {color}22; color: {color}; border-radius:6px; "
            f"padding: 2px 8px; font-size: 11px; font-weight: 700;"
        )
        hdr.addWidget(self._status_badge)
        layout.addLayout(hdr)

        # Description
        desc = QLabel(self.strategy.description or "No description")
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; font-size: 12px;")
        layout.addWidget(desc)

        # Stats row
        stats = QHBoxLayout()
        stats.setSpacing(20)
        for label, value in [
            ("Win Rate", f"{self.strategy.win_rate:.0f}%"),
            ("Trades",   str(self.strategy.total_trades)),
            ("Total P&L", f"₹{self.strategy.total_pnl:+,.0f}"),
        ]:
            col = QVBoxLayout()
            lbl = QLabel(label)
            lbl.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; font-size: 10px; font-weight:700; letter-spacing:0.5px;")
            val = QLabel(value)
            val.setStyleSheet(f"font-size: 16px; font-weight: 700;")
            col.addWidget(lbl)
            col.addWidget(val)
            stats.addLayout(col)
        stats.addStretch()
        layout.addLayout(stats)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        toggle_text = "Deactivate" if self.strategy.is_active else "Activate"
        toggle_obj  = "btn-danger" if self.strategy.is_active else "btn-success"
        toggle_btn  = QPushButton(toggle_text)
        toggle_btn.setObjectName(toggle_obj)
        toggle_btn.clicked.connect(lambda: self.on_toggle(self.strategy))
        btn_row.addWidget(toggle_btn)

        edit_btn = QPushButton("Edit Parameters")
        edit_btn.setObjectName("btn-ghost")
        edit_btn.clicked.connect(lambda: self.on_edit(self.strategy))
        btn_row.addWidget(edit_btn)

        btn_row.addStretch()
        layout.addLayout(btn_row)

    def update_status(self, is_active: bool):
        self.strategy.is_active = is_active
        color = COLOR_SUCCESS if is_active else COLOR_TEXT_MUTED
        text  = "ACTIVE" if is_active else "INACTIVE"
        self._status_badge.setText(text)
        self._status_badge.setStyleSheet(
            f"background: {color}22; color: {color}; border-radius:6px; "
            f"padding: 2px 8px; font-size: 11px; font-weight: 700;"
        )


class ParamEditorDialog(QDialog):
    def __init__(self, strategy: Strategy, parent=None):
        super().__init__(parent)
        self.strategy = strategy
        self.setWindowTitle(f"Edit — {strategy.name}")
        self.setMinimumWidth(400)
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        form = QFormLayout()
        params = self.strategy.get_parameters()
        self._param_inputs = {}
        for k, v in params.items():
            inp = QLineEdit(str(v))
            form.addRow(k + ":", inp)
            self._param_inputs[k] = inp
        layout.addLayout(form)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save |
            QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._save)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _save(self):
        new_params = {}
        for k, inp in self._param_inputs.items():
            val = inp.text()
            try:
                val = float(val) if "." in val else int(val)
            except ValueError:
                pass
            new_params[k] = val
        self.strategy.set_parameters(new_params)
        self.accept()


class StrategiesWidget(QWidget):
    def __init__(self, db: DatabaseManager, parent=None):
        super().__init__(parent)
        self.db = db
        self._cards: list[StrategyCard] = []
        self._signal_rows: list[dict] = []     # ring buffer of last 100 signals
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        hdr = QHBoxLayout()
        title = QLabel("Strategies")
        title.setObjectName("page-title")
        hdr.addWidget(title)
        hdr.addStretch()
        subtitle = QLabel("Activate strategies to enable automated signal generation")
        subtitle.setObjectName("page-subtitle")
        hdr.addWidget(subtitle)
        layout.addLayout(hdr)

        # ── Splitter: strategy cards (top) | signal log (bottom) ──────────
        splitter = QSplitter(Qt.Orientation.Vertical)

        # Strategy cards in a scroll area
        cards_scroll = QScrollArea()
        cards_scroll.setWidgetResizable(True)
        cards_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._cards_container = QWidget()
        self._cards_layout    = QGridLayout(self._cards_container)
        self._cards_layout.setSpacing(12)
        cards_scroll.setWidget(self._cards_container)
        splitter.addWidget(cards_scroll)

        # Signal log panel
        splitter.addWidget(self._build_signal_log())
        splitter.setSizes([500, 280])

        layout.addWidget(splitter)

    def _build_signal_log(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("card")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        hdr = QHBoxLayout()
        lbl = QLabel("Live Signal Log")
        lbl.setStyleSheet("font-size: 14px; font-weight: 700;")
        hdr.addWidget(lbl)
        hdr.addStretch()

        self._signal_count_lbl = QLabel("0 signals")
        self._signal_count_lbl.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; font-size: 11px;")
        hdr.addWidget(self._signal_count_lbl)

        clear_btn = QPushButton("Clear")
        clear_btn.setObjectName("btn-ghost")
        clear_btn.clicked.connect(self._clear_signals)
        hdr.addWidget(clear_btn)
        layout.addLayout(hdr)

        self._signal_table = QTableWidget(0, 6)
        self._signal_table.setHorizontalHeaderLabels(
            ["Time", "Strategy", "Symbol", "Signal", "Price", "Reason"]
        )
        self._signal_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._signal_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self._signal_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self._signal_table.verticalHeader().setVisible(False)
        self._signal_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._signal_table.setAlternatingRowColors(True)
        self._signal_table.setMaximumHeight(220)
        layout.addWidget(self._signal_table)
        return frame

    def refresh(self):
        # Clear old cards
        for card in self._cards:
            card.deleteLater()
        self._cards.clear()

        with self.db.session() as s:
            strategies = s.query(Strategy).all()

        for i, strat in enumerate(strategies):
            card = StrategyCard(strat, self._toggle_strategy, self._edit_strategy)
            self._cards_layout.addWidget(card, i // 2, i % 2)
            self._cards.append(card)

    # ── Live signal receiver ──────────────────────────────────────────────
    def on_signal(self, signal):
        """Called by MainWindow when StrategyEngine emits a new signal."""
        from app.trading.signal import SignalType

        # Keep a ring buffer of last 100
        self._signal_rows.insert(0, signal)
        if len(self._signal_rows) > 100:
            self._signal_rows.pop()

        self._signal_count_lbl.setText(f"{len(self._signal_rows)} signals")

        # Insert at top of table
        self._signal_table.insertRow(0)
        color = (
            COLOR_SUCCESS if signal.signal == SignalType.BUY
            else COLOR_DANGER if signal.signal == SignalType.SELL
            else COLOR_TEXT_MUTED
        )

        cells = [
            (signal.timestamp.strftime("%H:%M:%S"), COLOR_TEXT_MUTED),
            (signal.strategy,                        COLOR_TEXT),
            (signal.symbol,                          COLOR_TEXT),
            (signal.signal.value,                    color),
            (f"₹{signal.price:,.2f}" if signal.price else "—", COLOR_TEXT),
            (signal.reason[:80],                     COLOR_TEXT_MUTED),
        ]
        for col, (text, clr) in enumerate(cells):
            item = QTableWidgetItem(text)
            item.setForeground(QColor(clr))
            if col == 3:
                item.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
            self._signal_table.setItem(0, col, item)

        # Cap table rows at 100
        while self._signal_table.rowCount() > 100:
            self._signal_table.removeRow(self._signal_table.rowCount() - 1)

    def _clear_signals(self):
        self._signal_rows.clear()
        self._signal_table.setRowCount(0)
        self._signal_count_lbl.setText("0 signals")

    def _toggle_strategy(self, strategy: Strategy):
        with self.db.session() as s:
            strat = s.get(Strategy, strategy.id)
            strat.is_active = not strat.is_active
            s.commit()
            new_state = strat.is_active

        for card in self._cards:
            if card.strategy.id == strategy.id:
                card.update_status(new_state)
                self.db.add_alert(
                    title=f"Strategy {'activated' if new_state else 'deactivated'}: {strategy.name}",
                    level="INFO"
                )
                break

    def _edit_strategy(self, strategy: Strategy):
        dialog = ParamEditorDialog(strategy, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            with self.db.session() as s:
                strat = s.get(Strategy, strategy.id)
                strat.parameters = strategy.parameters
                s.commit()
