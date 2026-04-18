"""
TradeMind AI — Research Report Widget
Displays AI-generated quant research reports in a scrollable article view.
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextBrowser, QFrame, QLineEdit, QSizePolicy, QProgressBar
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QFont

from app.research.report_generator import ReportGenerator
from app.trading.engine import DEFAULT_SYMBOLS


class ResearchWidget(QWidget):
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db        = db
        self._engine   = None
        self._gen      = None
        self._build_ui()

    # ── UI ────────────────────────────────────────────────────────────────
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 10)
        layout.setSpacing(12)

        # ── Header ────────────────────────────────────────────────────────
        hdr = QHBoxLayout()
        title = QLabel("AI Research & Stock Picker")
        title.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        title.setStyleSheet("color: #f1f5f9;")
        hdr.addWidget(title)
        hdr.addStretch()

        self._status_lbl = QLabel("Ready")
        self._status_lbl.setStyleSheet("color: #94a3b8; font-size: 12px;")
        hdr.addWidget(self._status_lbl)
        layout.addLayout(hdr)

        # ── Sub-header ────────────────────────────────────────────────────
        sub = QLabel(
            "Combines live news (ET Markets, Moneycontrol, Google News) "
            "+ technical quant scoring + AI deep analysis"
        )
        sub.setStyleSheet("color: #6b7280; font-size: 12px;")
        sub.setWordWrap(True)
        layout.addWidget(sub)

        # ── Controls ──────────────────────────────────────────────────────
        ctrl = QHBoxLayout()

        ctrl.addWidget(QLabel("Symbols:"))
        self._symbols_edit = QLineEdit(", ".join(DEFAULT_SYMBOLS))
        self._symbols_edit.setPlaceholderText("RELIANCE, INFY, TCS, …")
        self._symbols_edit.setStyleSheet(
            "background:#1e2330;color:#e2e8f0;border:1px solid #2d3139;"
            "border-radius:4px;padding:4px 8px;"
        )
        ctrl.addWidget(self._symbols_edit, stretch=1)

        self._run_btn = QPushButton("▶  Run Research")
        self._run_btn.setFixedWidth(160)
        self._run_btn.setStyleSheet("""
            QPushButton {
                background: #3b82f6; color: #fff;
                border-radius: 6px; padding: 6px 14px; font-weight: bold;
            }
            QPushButton:hover   { background: #2563eb; }
            QPushButton:disabled{ background: #374151; color: #6b7280; }
        """)
        self._run_btn.clicked.connect(self._run_research)
        ctrl.addWidget(self._run_btn)

        layout.addLayout(ctrl)

        # ── Progress bar ──────────────────────────────────────────────────
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)   # indeterminate
        self._progress.setFixedHeight(4)
        self._progress.setTextVisible(False)
        self._progress.setStyleSheet("""
            QProgressBar { background: #1e2330; border: none; border-radius: 2px; }
            QProgressBar::chunk { background: #3b82f6; border-radius: 2px; }
        """)
        self._progress.setVisible(False)
        layout.addWidget(self._progress)

        # ── Report view ───────────────────────────────────────────────────
        self._browser = QTextBrowser()
        self._browser.setOpenExternalLinks(True)
        self._browser.setStyleSheet("""
            QTextBrowser {
                background: #131722; border: none;
                border-radius: 8px;
            }
            QScrollBar:vertical {
                background: #1e2330; width: 8px; border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background: #3b4255; border-radius: 4px; min-height: 30px;
            }
        """)
        self._browser.setHtml(self._placeholder_html())
        layout.addWidget(self._browser, stretch=1)

        # ── Footer ────────────────────────────────────────────────────────
        footer = QLabel(
            "⚠  Educational only — not financial advice. "
            "Always verify before trading. Use stop-losses."
        )
        footer.setStyleSheet("color: #f59e0b; font-size: 11px;")
        layout.addWidget(footer)

    # ── Research execution ────────────────────────────────────────────────
    def set_engine(self, engine):
        self._engine = engine
        if self._gen:
            self._gen.set_engine(engine)

    def _run_research(self):
        if self._gen and self._gen.is_running():
            return

        symbols_raw = self._symbols_edit.text()
        symbols = [s.strip().upper() for s in symbols_raw.split(",") if s.strip()]
        if not symbols:
            return

        self._gen = ReportGenerator(self._engine)
        self._run_btn.setEnabled(False)
        self._run_btn.setText("Researching…")
        self._progress.setVisible(True)
        self._status_lbl.setText("Fetching news & analysing…")

        self._gen.generate(
            symbols     = symbols,
            on_progress = self._on_progress,
            on_done     = self._on_done,
        )

    def _on_progress(self, message: str):
        # Called from background thread — use Qt-safe method
        from PyQt6.QtCore import QMetaObject, Qt
        QMetaObject.invokeMethod(
            self._status_lbl, "setText",
            Qt.ConnectionType.QueuedConnection,
            message,   # type: ignore[arg-type]
        )

    def _on_done(self, html: str):
        from PyQt6.QtCore import QMetaObject, Qt
        # Update UI from main thread
        QTimer.singleShot(0, lambda: self._apply_report(html))

    def _apply_report(self, html: str):
        self._browser.setHtml(html)
        self._run_btn.setEnabled(True)
        self._run_btn.setText("▶  Run Research")
        self._progress.setVisible(False)
        self._status_lbl.setText(
            f"Report ready — {__import__('datetime').datetime.now().strftime('%H:%M')}"
        )

    # ── Placeholder HTML ──────────────────────────────────────────────────
    def _placeholder_html(self) -> str:
        return """
<html><body style="background:#131722;color:#e2e8f0;
                   font-family:Segoe UI,sans-serif;padding:40px;text-align:center;">
  <div style="margin-top:80px;">
    <div style="font-size:48px;">📰</div>
    <h2 style="color:#f1f5f9;margin:16px 0 8px;">AI Research Report</h2>
    <p style="color:#6b7280;max-width:400px;margin:0 auto 24px;">
      Click <strong style="color:#3b82f6;">Run Research</strong> to analyse stocks
      using live news + quant scoring + AI deep analysis.
    </p>
    <div style="background:#1e2330;border-radius:8px;padding:20px;
                max-width:420px;margin:0 auto;text-align:left;">
      <div style="color:#f59e0b;font-size:12px;font-weight:700;margin-bottom:10px;">
        WHAT IT DOES
      </div>
      <div style="color:#94a3b8;font-size:13px;line-height:1.8;">
        📡 Fetches live news from ET Markets, Moneycontrol, Google News<br>
        📊 Computes RSI, momentum, volume ratio via Yahoo Finance<br>
        🤖 AI analyses each stock and rates news sentiment 0–100<br>
        🏆 Ranks stocks by composite quant score<br>
        🎯 Gives target price, stop-loss & clear recommendation
      </div>
    </div>
    <p style="color:#374151;font-size:11px;margin-top:24px;">
      Requires: Groq or Gemini connected in Settings → AI Assistant
    </p>
  </div>
</body></html>"""

    def refresh(self):
        pass
