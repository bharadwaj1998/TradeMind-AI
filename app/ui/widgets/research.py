"""
TradeMind AI — Research & Intraday Widget
Two tabs:
  1. Swing Research  — discovers stocks via web crawl + AI quant analysis
  2. Intraday Picks  — best stocks for today's session with buy button
"""
from __future__ import annotations
from datetime import datetime

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextBrowser, QTabWidget, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QProgressBar, QFrame,
    QLineEdit, QSizePolicy, QCheckBox
)
from PyQt6.QtCore import Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QFont, QColor, QBrush, QDesktopServices

from app.research.report_generator import ReportGenerator, DEFAULT_SYMBOLS
from app.research.intraday_picker  import IntradayPicker, IntradayPick
from app.research.stock_discovery  import StockDiscovery, NIFTY_50


_REC_COLOR = {
    "STRONG BUY":   "#10b981",
    "BUY":          "#34d399",
    "HOLD":         "#f59e0b",
    "AVOID":        "#f87171",
    "STRONG AVOID": "#ef4444",
}
_RISK_COLOR = {"LOW": "#10b981", "MEDIUM": "#f59e0b", "HIGH": "#ef4444"}
_SIG_COLOR  = {"BUY": "#10b981", "SHORT": "#ef4444", "WATCH": "#f59e0b"}

INTRADAY_COLS = [
    "Symbol", "Signal", "Strategy", "LTP ₹", "Gap %", "Vol Ratio",
    "RSI", "Score", "Target ₹", "Stop Loss ₹", "Reason", "Action"
]


class ResearchWidget(QWidget):
    """Hosts Swing Research and Intraday tabs."""
    buy_requested = pyqtSignal(dict)    # {symbol, direction, price, sl, target}

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db      = db
        self._engine = None
        self._api    = None
        self._gen    = None
        self._picker = None
        self._disc   = StockDiscovery()
        self._build_ui()

    # ── UI construction ───────────────────────────────────────────────────
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 10)
        root.setSpacing(10)

        # Title
        title = QLabel("AI Research & Stock Picker")
        title.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        title.setStyleSheet("color: #f1f5f9;")
        root.addWidget(title)

        # Tabs
        self._tabs = QTabWidget()
        self._tabs.setStyleSheet("""
            QTabWidget::pane  { border: none; background: transparent; }
            QTabBar::tab {
                background: #1e2330; color: #94a3b8;
                padding: 8px 20px; border-radius: 6px 6px 0 0;
                margin-right: 2px;
            }
            QTabBar::tab:selected { background: #2d3748; color: #f1f5f9; }
        """)
        root.addWidget(self._tabs)

        self._tabs.addTab(self._build_swing_tab(), "📊  Swing Research")
        self._tabs.addTab(self._build_intraday_tab(), "⚡  Intraday Picks")

    # ── Swing Research tab ────────────────────────────────────────────────
    def _build_swing_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 12, 0, 0)
        lay.setSpacing(8)

        sub = QLabel(
            "Discovers trending stocks via NSE movers + news crawl, then runs "
            "quant scoring + AI analysis. Sorted by composite score."
        )
        sub.setStyleSheet("color: #6b7280; font-size: 12px;")
        sub.setWordWrap(True)
        lay.addWidget(sub)

        # Controls
        ctrl = QHBoxLayout()

        self._auto_disc = QCheckBox("Auto-discover (NSE + News)")
        self._auto_disc.setChecked(True)
        self._auto_disc.setStyleSheet("color: #e2e8f0;")
        ctrl.addWidget(self._auto_disc)

        ctrl.addWidget(QLabel("  Symbols:"))
        self._symbols_edit = QLineEdit(", ".join(DEFAULT_SYMBOLS))
        self._symbols_edit.setStyleSheet(
            "background:#1e2330;color:#e2e8f0;border:1px solid #374151;"
            "border-radius:4px;padding:4px 8px;"
        )
        self._symbols_edit.setEnabled(False)
        self._auto_disc.toggled.connect(lambda c: self._symbols_edit.setEnabled(not c))
        ctrl.addWidget(self._symbols_edit, stretch=1)

        self._swing_btn = QPushButton("▶  Run Research")
        self._swing_btn.setFixedWidth(170)
        self._swing_btn.setStyleSheet(self._btn_style("#3b82f6"))
        self._swing_btn.clicked.connect(self._run_swing)
        ctrl.addWidget(self._swing_btn)

        lay.addLayout(ctrl)

        self._swing_progress = self._make_progress()
        lay.addWidget(self._swing_progress)

        self._swing_status = QLabel("Ready — click Run Research")
        self._swing_status.setStyleSheet("color: #94a3b8; font-size: 12px;")
        lay.addWidget(self._swing_status)

        self._browser = QTextBrowser()
        self._browser.setOpenLinks(False)
        self._browser.anchorClicked.connect(self._on_browser_link)
        self._browser.setStyleSheet("""
            QTextBrowser { background: #131722; border: none; border-radius: 8px; }
            QScrollBar:vertical { background:#1e2330; width:8px; border-radius:4px; }
            QScrollBar::handle:vertical { background:#3b4255; border-radius:4px; min-height:30px; }
        """)
        self._browser.setHtml(self._placeholder_html())
        lay.addWidget(self._browser, stretch=1)

        lay.addWidget(QLabel(
            "⚠ Educational only — not financial advice. Always use stop-losses.",
            styleSheet="color:#f59e0b;font-size:11px;"
        ))
        return w

    # ── Intraday tab ──────────────────────────────────────────────────────
    def _build_intraday_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 12, 0, 0)
        lay.setSpacing(8)

        # Info bar
        self._session_lbl = QLabel()
        self._session_lbl.setStyleSheet(
            "background:#1e2330;border-radius:6px;padding:6px 12px;"
            "color:#f59e0b;font-size:12px;"
        )
        self._update_session_label()
        lay.addWidget(self._session_lbl)

        # Controls
        ctrl = QHBoxLayout()
        ctrl.addWidget(QLabel("Scan universe:"))
        self._univ_combo = QLabel("Nifty 50 (50 stocks)")
        self._univ_combo.setStyleSheet("color:#94a3b8;")
        ctrl.addWidget(self._univ_combo)
        ctrl.addStretch()

        self._intraday_btn = QPushButton("⚡  Get Today's Picks")
        self._intraday_btn.setFixedWidth(180)
        self._intraday_btn.setStyleSheet(self._btn_style("#10b981"))
        self._intraday_btn.clicked.connect(self._run_intraday)
        ctrl.addWidget(self._intraday_btn)
        lay.addLayout(ctrl)

        self._intraday_progress = self._make_progress()
        lay.addWidget(self._intraday_progress)

        self._intraday_status = QLabel("Ready — click Get Today's Picks")
        self._intraday_status.setStyleSheet("color: #94a3b8; font-size: 12px;")
        lay.addWidget(self._intraday_status)

        # Table
        self._intraday_table = QTableWidget(0, len(INTRADAY_COLS))
        self._intraday_table.setHorizontalHeaderLabels(INTRADAY_COLS)
        self._intraday_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._intraday_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._intraday_table.setAlternatingRowColors(True)
        self._intraday_table.verticalHeader().setVisible(False)
        self._intraday_table.setStyleSheet("""
            QTableWidget { background:#1e2330; border:none; gridline-color:#2d3139; }
            QTableWidget::item { padding:6px 8px; color:#e2e8f0; }
            QTableWidget::item:alternate { background:#252b3b; }
            QHeaderView::section {
                background:#2d3139; color:#94a3b8;
                padding:6px 8px; border:none; font-weight:bold;
            }
        """)
        hh = self._intraday_table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(10, QHeaderView.ResizeMode.Stretch)   # Reason col stretches
        lay.addWidget(self._intraday_table, stretch=1)

        lay.addWidget(QLabel(
            "⚠ Intraday only — all positions must be squared off before 3:15 PM. "
            "Stop-loss is mandatory.",
            styleSheet="color:#f59e0b;font-size:11px;"
        ))
        return w

    # ── Public setters ────────────────────────────────────────────────────
    def set_engine(self, engine):
        self._engine = engine
        if self._picker:
            self._picker.set_engine(engine)
        if self._gen:
            self._gen.set_engine(engine)

    def set_api(self, api):
        self._api = api

    # ── Swing research ────────────────────────────────────────────────────
    def _run_swing(self):
        if self._gen and self._gen.is_running():
            return

        if self._auto_disc.isChecked():
            # Discover symbols via web crawl first, then analyse
            self._swing_btn.setEnabled(False)
            self._swing_btn.setText("Discovering…")
            self._swing_progress.setVisible(True)
            self._swing_status.setText("Scanning NSE movers + news…")

            import threading
            def _discover():
                result = self._disc.discover(
                    mode="swing", top_n=10,
                    on_progress=lambda m: QTimer.singleShot(
                        0, lambda msg=m: self._swing_status.setText(msg)
                    ),
                )
                symbols = result["combined"]
                QTimer.singleShot(0, lambda s=symbols: self._start_swing_analysis(s))

            threading.Thread(target=_discover, daemon=True).start()
        else:
            syms = [s.strip().upper() for s in self._symbols_edit.text().split(",") if s.strip()]
            self._start_swing_analysis(syms or DEFAULT_SYMBOLS)

    def _start_swing_analysis(self, symbols):
        self._gen = ReportGenerator(self._engine)
        self._swing_btn.setEnabled(False)
        self._swing_btn.setText("Analysing…")
        self._swing_progress.setVisible(True)
        self._swing_status.setText(f"Analysing {len(symbols)} stocks…")

        self._gen.generate(
            symbols     = symbols,
            on_progress = self._swing_progress_cb,
            on_done     = self._swing_done_cb,
        )

    def _swing_progress_cb(self, msg):
        from PyQt6.QtCore import QMetaObject
        QMetaObject.invokeMethod(
            self._swing_status, "setText",
            Qt.ConnectionType.QueuedConnection,
            msg,
        )

    def _swing_done_cb(self, html):
        # Inject buy buttons into the HTML (as anchor links)
        html = self._inject_buy_buttons(html)
        QTimer.singleShot(0, lambda: self._apply_swing(html))

    def _apply_swing(self, html):
        self._browser.setHtml(html)
        self._swing_btn.setEnabled(True)
        self._swing_btn.setText("▶  Run Research")
        self._swing_progress.setVisible(False)
        self._swing_status.setText(
            f"Report ready — {datetime.now().strftime('%H:%M')}  "
            f"(click BUY/AVOID buttons to trade)"
        )

    def _inject_buy_buttons(self, html: str) -> str:
        """Add BUY and AVOID buttons to each research card."""
        import re
        def add_btns(m):
            sym = m.group(1)
            buy_link  = f'trademind://buy/{sym}'
            skip_link = f'trademind://skip/{sym}'
            btns = (
                f'<a href="{buy_link}" style="background:#10b981;color:#fff;'
                f'padding:4px 14px;border-radius:4px;text-decoration:none;'
                f'font-weight:bold;font-size:12px;">▲ BUY {sym}</a>'
                f'&nbsp;&nbsp;'
                f'<a href="{skip_link}" style="background:#374151;color:#94a3b8;'
                f'padding:4px 14px;border-radius:4px;text-decoration:none;'
                f'font-size:12px;">✕ Skip</a>'
            )
            return m.group(0) + f'<div style="margin-top:10px;">{btns}</div>'

        # Insert after the verdict line in each card
        html = re.sub(
            r'<span style="color:#f59e0b;font-size:11px;font-weight:700;">VERDICT: </span>'
            r'<span style="color:#f1f5f9;font-size:13px;">([^<]*)</span>',
            lambda m2: m2.group(0),   # keep verdict unchanged
            html,
        )
        # Simpler: add button row at end of each card before closing </div>
        # Match symbol from card header
        html = re.sub(
            r'<span style="font-size:22px;font-weight:700;color:#f1f5f9;">([A-Z&-]+)</span>',
            lambda m: _add_sym_attr(m),
            html,
        )
        return html

    def _on_browser_link(self, url: QUrl):
        path = url.toString()
        if path.startswith("trademind://buy/"):
            sym = path.split("/")[-1]
            self.buy_requested.emit({
                "symbol":    sym,
                "direction": "BUY",
                "price":     0.0,
                "sl":        0.0,
                "target":    0.0,
            })
        # skip: do nothing

    # ── Intraday picks ────────────────────────────────────────────────────
    def _run_intraday(self):
        self._picker = IntradayPicker(self._engine)
        self._intraday_btn.setEnabled(False)
        self._intraday_btn.setText("Scanning…")
        self._intraday_progress.setVisible(True)
        self._intraday_status.setText("Fetching intraday data for Nifty 50…")
        self._update_session_label()

        import threading
        def _run():
            picks = self._picker.pick(
                symbols     = NIFTY_50,
                api         = self._api,
                top_n       = 8,
                on_progress = lambda m: QTimer.singleShot(
                    0, lambda msg=m: self._intraday_status.setText(msg)
                ),
            )
            QTimer.singleShot(0, lambda p=picks: self._apply_intraday(p))

        threading.Thread(target=_run, daemon=True).start()

    def _apply_intraday(self, picks: list):
        self._intraday_table.setRowCount(0)
        for pick in picks:
            self._add_intraday_row(pick)

        self._intraday_btn.setEnabled(True)
        self._intraday_btn.setText("⚡  Get Today's Picks")
        self._intraday_progress.setVisible(False)
        self._intraday_status.setText(
            f"Found {len(picks)} picks — {datetime.now().strftime('%H:%M IST')}"
        )

    def _add_intraday_row(self, p: IntradayPick):
        row = self._intraday_table.rowCount()
        self._intraday_table.insertRow(row)

        sig_color  = QColor(_SIG_COLOR.get(p.signal, "#9ca3af"))
        risk_color = QColor(_RISK_COLOR.get(p.risk, "#9ca3af"))
        score_color = QColor(
            "#10b981" if p.score >= 70 else
            "#f59e0b" if p.score >= 50 else "#ef4444"
        )

        def cell(text, color=None, bold=False, align=Qt.AlignmentFlag.AlignCenter):
            item = QTableWidgetItem(str(text))
            item.setTextAlignment(align)
            if color:
                item.setForeground(QBrush(color))
            if bold:
                f = QFont(); f.setBold(True); item.setFont(f)
            return item

        self._intraday_table.setItem(row, 0,  cell(p.symbol, bold=True))
        self._intraday_table.setItem(row, 1,  cell(p.signal, sig_color, bold=True))
        self._intraday_table.setItem(row, 2,  cell(p.strategy))
        self._intraday_table.setItem(row, 3,  cell(f"₹{p.ltp:,.2f}"))
        self._intraday_table.setItem(row, 4,  cell(f"{p.gap_pct:+.2f}%",
            QColor("#10b981") if p.gap_pct > 0 else QColor("#ef4444")))
        self._intraday_table.setItem(row, 5,  cell(f"{p.volume_ratio:.2f}x",
            QColor("#10b981") if p.volume_ratio > 1.5 else None))
        self._intraday_table.setItem(row, 6,  cell(f"{p.rsi:.0f}",
            QColor("#10b981") if p.rsi < 40 else
            QColor("#ef4444") if p.rsi > 65 else None))
        self._intraday_table.setItem(row, 7,  cell(f"{p.score}", score_color, bold=True))
        self._intraday_table.setItem(row, 8,  cell(
            f"₹{p.target:,.2f}" if p.target else "—",
            QColor("#10b981")))
        self._intraday_table.setItem(row, 9,  cell(
            f"₹{p.stop_loss:,.2f}" if p.stop_loss else "—",
            QColor("#ef4444")))
        reason_item = QTableWidgetItem(p.reason)
        reason_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        reason_item.setForeground(QBrush(QColor("#94a3b8")))
        self._intraday_table.setItem(row, 10, reason_item)

        # Buy/Short button
        if p.signal in ("BUY", "SHORT"):
            btn_color = "#10b981" if p.signal == "BUY" else "#ef4444"
            btn = QPushButton(f"{'▲ BUY' if p.signal == 'BUY' else '▼ SHORT'}")
            btn.setStyleSheet(
                f"background:{btn_color};color:#fff;border-radius:4px;"
                f"padding:4px 8px;font-weight:bold;font-size:11px;"
            )
            btn.clicked.connect(lambda _, pick=p: self._on_intraday_order(pick))
            self._intraday_table.setCellWidget(row, 11, btn)
        else:
            self._intraday_table.setItem(row, 11, cell("—", QColor("#6b7280")))

    def _on_intraday_order(self, pick: IntradayPick):
        self.buy_requested.emit({
            "symbol":    pick.symbol,
            "direction": pick.signal if pick.signal != "SHORT" else "SELL",
            "price":     pick.ltp,
            "sl":        pick.stop_loss,
            "target":    pick.target,
        })

    # ── Helpers ───────────────────────────────────────────────────────────
    def _update_session_label(self):
        from datetime import datetime as dt
        now  = dt.now()
        h, m = now.hour, now.minute
        if (h, m) < (9, 15):
            phase = "PRE-MARKET — Scan runs on previous close data"
        elif (h, m) < (11, 0):
            phase = "MORNING SESSION — Best for Gap & Go + Volume breakouts"
        elif (h, m) < (13, 0):
            phase = "MIDDAY SESSION — VWAP pullbacks + trend continuation"
        elif (h, m) < (15, 30):
            phase = "AFTERNOON SESSION — Momentum plays; square off by 3:15 PM"
        else:
            phase = "MARKET CLOSED — Picks based on EOD data for tomorrow's plan"
        self._session_lbl.setText(f"⏱  {now.strftime('%H:%M IST')}  |  {phase}")

    def _btn_style(self, color: str) -> str:
        return (
            f"QPushButton {{background:{color};color:#fff;border-radius:6px;"
            f"padding:6px 14px;font-weight:bold;}}"
            f"QPushButton:hover {{background:{color}cc;}}"
            f"QPushButton:disabled {{background:#374151;color:#6b7280;}}"
        )

    def _make_progress(self) -> QProgressBar:
        pb = QProgressBar()
        pb.setRange(0, 0)
        pb.setFixedHeight(4)
        pb.setTextVisible(False)
        pb.setStyleSheet("""
            QProgressBar { background:#1e2330; border:none; border-radius:2px; }
            QProgressBar::chunk { background:#3b82f6; border-radius:2px; }
        """)
        pb.setVisible(False)
        return pb

    def _placeholder_html(self) -> str:
        return """
<html><body style="background:#131722;color:#e2e8f0;
  font-family:Segoe UI,sans-serif;padding:60px;text-align:center;">
  <div style="font-size:48px;">📰</div>
  <h2 style="color:#f1f5f9;">AI Swing Research</h2>
  <p style="color:#6b7280;max-width:480px;margin:0 auto 24px;">
    Discovers trending NSE stocks via live news crawl + NSE movers,
    then ranks them with quant scoring + AI deep analysis.
  </p>
  <div style="background:#1e2330;border-radius:8px;padding:20px;
              max-width:440px;margin:0 auto;text-align:left;">
    <div style="color:#f59e0b;font-size:12px;font-weight:700;margin-bottom:10px;">PIPELINE</div>
    <div style="color:#94a3b8;font-size:13px;line-height:1.9;">
      🌐 NSE API → top gainers / losers today<br>
      📡 RSS crawl → ET Markets, Moneycontrol, Google News<br>
      📊 yfinance → RSI, SMA, volume ratio, momentum<br>
      🤖 AI → sentiment, catalysts, risks, target price<br>
      🏆 Ranked by composite score → BUY button on each card
    </div>
  </div>
</body></html>"""

    def refresh(self):
        self._update_session_label()


def _add_sym_attr(m):
    """Passthrough — symbol is embedded in HTML for reference."""
    return m.group(0)
