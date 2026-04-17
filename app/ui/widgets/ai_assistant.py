"""
TradeMind AI — AI Assistant Screen
Chat interface backed by local Llama/Mistral model.
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QTextEdit, QLineEdit, QPushButton, QScrollArea,
    QFrame, QSizePolicy, QComboBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QColor, QTextCursor

from app.database.manager import DatabaseManager
from app.config import (
    COLOR_BG, COLOR_CARD, COLOR_BORDER, COLOR_TEXT, COLOR_TEXT_MUTED,
    COLOR_ACCENT, COLOR_SUCCESS, COLOR_DANGER, COLOR_WARNING
)

# ─── Worker thread so AI inference doesn't freeze the UI ─────────────────────
class AIWorker(QThread):
    response_ready   = pyqtSignal(str)
    token_ready      = pyqtSignal(str)     # for streaming (optional)
    error_occurred   = pyqtSignal(str)

    def __init__(self, engine, prompt: str, context: str = ""):
        super().__init__()
        self.engine  = engine
        self.prompt  = prompt
        self.context = context

    def run(self):
        try:
            response = self.engine.chat(self.prompt, context=self.context)
            self.response_ready.emit(response)
        except Exception as e:
            self.error_occurred.emit(str(e))


class ChatBubble(QFrame):
    """Single message bubble (user or assistant)."""
    def __init__(self, text: str, role: str, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)

        bubble = QLabel()
        bubble.setWordWrap(True)
        bubble.setText(text)
        bubble.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        bubble.setMaximumWidth(700)

        if role == "user":
            bubble.setStyleSheet(
                f"background: {COLOR_ACCENT}22; color: {COLOR_TEXT}; "
                f"border-radius: 12px 12px 4px 12px; padding: 10px 14px; font-size: 13px;"
            )
            layout.addStretch()
            layout.addWidget(bubble)
        else:
            bubble.setStyleSheet(
                f"background: {COLOR_CARD}; color: {COLOR_TEXT}; "
                f"border: 1px solid {COLOR_BORDER}; "
                f"border-radius: 12px 12px 12px 4px; padding: 10px 14px; font-size: 13px;"
            )
            layout.addWidget(bubble)
            layout.addStretch()


class AIAssistantWidget(QWidget):
    def __init__(self, db: DatabaseManager, parent=None):
        super().__init__(parent)
        self.db = db
        self._ai_engine = None
        self._worker    = None
        self._build_ui()
        self._load_history()

    def set_engine(self, engine):
        self._ai_engine = engine
        self._model_lbl.setText(f"Model: {engine.model_name()}")
        self._model_lbl.setStyleSheet(f"color: {COLOR_SUCCESS}; font-size: 11px;")

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        # Header
        hdr = QHBoxLayout()
        title = QLabel("AI Assistant")
        title.setObjectName("page-title")
        hdr.addWidget(title)
        hdr.addStretch()
        self._model_lbl = QLabel("Model: Not loaded")
        self._model_lbl.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; font-size: 11px;")
        hdr.addWidget(self._model_lbl)
        layout.addLayout(hdr)

        # Context preset selector
        ctx_row = QHBoxLayout()
        ctx_row.setSpacing(8)
        ctx_lbl = QLabel("Ask about:")
        ctx_lbl.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; font-size: 12px;")
        ctx_row.addWidget(ctx_lbl)
        self._ctx_combo = QComboBox()
        self._ctx_combo.addItems([
            "General Chat",
            "Explain my last trade",
            "Analyse today's P&L",
            "Suggest position sizing",
            "Review current strategy",
            "Risk assessment",
        ])
        self._ctx_combo.setMaximumWidth(220)
        ctx_row.addWidget(self._ctx_combo)

        # Quick prompt buttons
        for label in ["What went wrong today?", "Best trade analysis", "Risk check"]:
            btn = QPushButton(label)
            btn.setObjectName("btn-ghost")
            btn.clicked.connect(lambda _, l=label: self._quick_ask(l))
            ctx_row.addWidget(btn)

        ctx_row.addStretch()

        clear_btn = QPushButton("Clear chat")
        clear_btn.setObjectName("btn-ghost")
        clear_btn.clicked.connect(self._clear_chat)
        ctx_row.addWidget(clear_btn)
        layout.addLayout(ctx_row)

        # Chat scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._chat_container = QWidget()
        self._chat_layout    = QVBoxLayout(self._chat_container)
        self._chat_layout.setContentsMargins(0, 0, 0, 0)
        self._chat_layout.setSpacing(4)
        self._chat_layout.addStretch()
        scroll.setWidget(self._chat_container)
        self._scroll = scroll
        layout.addWidget(scroll, stretch=1)

        # Typing indicator
        self._typing_lbl = QLabel("AI is thinking…")
        self._typing_lbl.setStyleSheet(
            f"color: {COLOR_TEXT_MUTED}; font-size: 12px; padding: 4px 0;"
        )
        self._typing_lbl.hide()
        layout.addWidget(self._typing_lbl)

        # Input row
        input_row = QHBoxLayout()
        input_row.setSpacing(8)

        self._input = QLineEdit()
        self._input.setPlaceholderText("Ask TradeMind AI anything about your trades…")
        self._input.setMinimumHeight(42)
        self._input.returnPressed.connect(self._send_message)
        input_row.addWidget(self._input)

        self._send_btn = QPushButton("Send")
        self._send_btn.setObjectName("btn-primary")
        self._send_btn.setMinimumHeight(42)
        self._send_btn.setMinimumWidth(80)
        self._send_btn.clicked.connect(self._send_message)
        input_row.addWidget(self._send_btn)

        layout.addLayout(input_row)

    # ── Message handling ──────────────────────────────────────────────────
    def _send_message(self):
        text = self._input.text().strip()
        if not text:
            return
        self._input.clear()
        self._append_bubble(text, "user")
        self.db.log_ai_message("user", text)
        self._run_ai(text)

    def _quick_ask(self, prompt: str):
        self._input.setText(prompt)
        self._send_message()

    def _run_ai(self, prompt: str):
        if not self._ai_engine:
            response = (
                "AI model is not loaded yet.\n\n"
                "Go to **Settings → AI Assistant** and set your Mistral model path, "
                "then click **Load Model**."
            )
            self._append_bubble(response, "assistant")
            self.db.log_ai_message("assistant", response)
            return

        # Build context from recent trades
        stats   = self.db.get_today_stats()
        context = (
            f"User's capital: ₹15,000. "
            f"Today's trades: {stats['total_trades']}, "
            f"Win rate: {stats['win_rate']:.1f}%, "
            f"P&L: ₹{stats['total_pnl']:+,.0f}."
        )

        self._typing_lbl.show()
        self._send_btn.setEnabled(False)
        self._input.setEnabled(False)

        self._worker = AIWorker(self._ai_engine, prompt, context)
        self._worker.response_ready.connect(self._on_ai_response)
        self._worker.error_occurred.connect(self._on_ai_error)
        self._worker.start()

    def _on_ai_response(self, response: str):
        self._typing_lbl.hide()
        self._send_btn.setEnabled(True)
        self._input.setEnabled(True)
        self._append_bubble(response, "assistant")
        self.db.log_ai_message("assistant", response)
        self._scroll_to_bottom()

    def _on_ai_error(self, error: str):
        self._typing_lbl.hide()
        self._send_btn.setEnabled(True)
        self._input.setEnabled(True)
        self._append_bubble(f"Error: {error}", "assistant")

    def _append_bubble(self, text: str, role: str):
        bubble = ChatBubble(text, role)
        # Insert before the trailing stretch
        self._chat_layout.insertWidget(self._chat_layout.count() - 1, bubble)
        QTimer.singleShot(50, self._scroll_to_bottom)

    def _scroll_to_bottom(self):
        self._scroll.verticalScrollBar().setValue(
            self._scroll.verticalScrollBar().maximum()
        )

    def _load_history(self):
        history = self.db.get_ai_history(limit=30)
        for msg in history:
            self._append_bubble(msg.content, msg.role)

    def _clear_chat(self):
        while self._chat_layout.count() > 1:
            item = self._chat_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def refresh(self):
        pass   # history loaded once; live updates happen via _append_bubble
