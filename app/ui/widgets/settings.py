"""
TradeMind AI — Settings Screen
Angel One credentials (encrypted), AI model path, trading parameters.
"""
import os
from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFrame, QFormLayout, QTabWidget,
    QDoubleSpinBox, QSpinBox, QFileDialog, QMessageBox,
    QCheckBox, QScrollArea
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont

from app.database.manager import DatabaseManager
from app.config import (
    COLOR_SUCCESS, COLOR_DANGER, COLOR_WARNING, COLOR_TEXT,
    COLOR_TEXT_MUTED, COLOR_BORDER, COLOR_ACCENT,
    DEFAULT_CAPITAL, MAX_RISK_PER_TRADE_PCT, MAX_DAILY_LOSS_PCT,
    DEFAULT_LLAMA_MODEL_PATH
)


class SettingsWidget(QWidget):
    credentials_saved  = pyqtSignal(dict)
    model_path_changed = pyqtSignal(str)

    def __init__(self, db: DatabaseManager, parent=None):
        super().__init__(parent)
        self.db = db
        self._build_ui()
        self._load_settings()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        title = QLabel("Settings")
        title.setObjectName("page-title")
        layout.addWidget(title)

        tabs = QTabWidget()
        tabs.addTab(self._build_broker_tab(),  "Broker — Angel One")
        tabs.addTab(self._build_ai_tab(),      "AI Assistant")
        tabs.addTab(self._build_trading_tab(), "Trading Rules")
        tabs.addTab(self._build_about_tab(),   "About")
        layout.addWidget(tabs)

    # ── Broker tab ────────────────────────────────────────────────────────
    def _build_broker_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # Connection status badge
        self._conn_badge = QLabel("● Not Connected")
        self._conn_badge.setStyleSheet(
            f"background: {COLOR_DANGER}18; color: {COLOR_DANGER}; "
            f"border-radius: 8px; padding: 8px 14px; font-size: 13px; font-weight: 700;"
        )
        layout.addWidget(self._conn_badge)

        info = QLabel(
            "Your credentials are stored encrypted on this device only. "
            "Never shared or sent online."
        )
        info.setWordWrap(True)
        info.setStyleSheet(
            f"background: {COLOR_ACCENT}11; color: {COLOR_TEXT_MUTED}; "
            f"border-radius: 8px; padding: 10px 14px; font-size: 12px;"
        )
        layout.addWidget(info)

        form = QFormLayout()
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._api_key     = self._password_field("Your Angel One API Key")
        self._client_id   = QLineEdit(); self._client_id.setPlaceholderText("e.g. A123456")
        self._client_pwd  = self._password_field("Your Angel One login password")
        self._totp_secret = self._password_field("TOTP secret key from Angel One app")

        form.addRow("API Key:",        self._api_key)
        form.addRow("Client ID:",      self._client_id)
        form.addRow("Password:",       self._client_pwd)
        form.addRow("TOTP Secret:",    self._totp_secret)
        layout.addLayout(form)

        # How to get credentials
        help_btn = QPushButton("How to get Angel One API credentials?")
        help_btn.setObjectName("btn-ghost")
        help_btn.clicked.connect(self._show_api_help)
        layout.addWidget(help_btn)

        btn_row = QHBoxLayout()
        save_btn = QPushButton("Save & Connect")
        save_btn.setObjectName("btn-primary")
        save_btn.setMinimumHeight(40)
        save_btn.clicked.connect(self._save_broker_credentials)
        btn_row.addWidget(save_btn)

        self._broker_status = QLabel("")
        btn_row.addWidget(self._broker_status)
        btn_row.addStretch()
        layout.addLayout(btn_row)
        layout.addStretch()
        return w

    # ── AI tab ────────────────────────────────────────────────────────────
    def _build_ai_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # AI model status badge
        self._ai_badge = QLabel("● Model Not Loaded")
        self._ai_badge.setStyleSheet(
            f"background: {COLOR_WARNING}18; color: {COLOR_WARNING}; "
            f"border-radius: 8px; padding: 8px 14px; font-size: 13px; font-weight: 700;"
        )
        layout.addWidget(self._ai_badge)

        form = QFormLayout()
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # Provider selector
        self._ai_provider = QComboBox()
        self._ai_provider.addItems(["Google Gemini (Recommended — Free)", "Groq (Free)", "Local Llama (Offline)"])
        self._ai_provider.currentIndexChanged.connect(self._on_provider_changed)
        form.addRow("AI Provider:", self._ai_provider)

        # API key (Gemini / Groq)
        self._ai_api_key = QLineEdit()
        self._ai_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self._ai_api_key.setPlaceholderText("Paste your API key here")
        form.addRow("API Key:", self._ai_api_key)

        # API key help label
        self._ai_key_help = QLabel(
            "Get free key: aistudio.google.com/app/apikey"
        )
        self._ai_key_help.setStyleSheet(f"color: {COLOR_ACCENT}; font-size: 11px;")
        form.addRow("", self._ai_key_help)

        # Model ID (optional override)
        self._ai_model_id = QLineEdit()
        self._ai_model_id.setPlaceholderText("gemini-2.0-flash  (leave blank for default)")
        form.addRow("Model (optional):", self._ai_model_id)

        # Local model path (only shown for Llama)
        path_row = QHBoxLayout()
        self._model_path = QLineEdit()
        self._model_path.setPlaceholderText(
            f"e.g. {DEFAULT_LLAMA_MODEL_PATH / 'mistral-7b-instruct-v0.2.Q4_K_M.gguf'}"
        )
        path_row.addWidget(self._model_path)
        browse = QPushButton("Browse…")
        browse.setObjectName("btn-ghost")
        browse.clicked.connect(self._browse_model)
        path_row.addWidget(browse)
        self._model_path_row_label = QLabel("Model File (.gguf):")
        form.addRow(self._model_path_row_label, path_row)

        # Llama options (threads/ctx) — hidden unless Llama selected
        self._ai_threads = QSpinBox()
        self._ai_threads.setRange(1, 32)
        self._ai_threads.setValue(4)
        self._threads_label = QLabel("CPU Threads:")
        form.addRow(self._threads_label, self._ai_threads)

        self._ai_ctx = QSpinBox()
        self._ai_ctx.setRange(512, 16384)
        self._ai_ctx.setSingleStep(512)
        self._ai_ctx.setValue(4096)
        self._ctx_label = QLabel("Context Size:")
        form.addRow(self._ctx_label, self._ai_ctx)

        layout.addLayout(form)

        btn_row = QHBoxLayout()
        load_btn = QPushButton("Connect AI")
        load_btn.setObjectName("btn-primary")
        load_btn.setMinimumHeight(40)
        load_btn.clicked.connect(self._save_ai_settings)
        btn_row.addWidget(load_btn)

        self._ai_status = QLabel("")
        btn_row.addWidget(self._ai_status)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        # Set initial visibility
        self._on_provider_changed(0)

        # Download link
        dl_lbl = QLabel(
            "Don't have a model? Download from Hugging Face:\n"
            "mistralai/Mistral-7B-Instruct-v0.2 (GGUF 4-bit, ~4 GB)"
        )
        dl_lbl.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; font-size: 12px;")
        layout.addWidget(dl_lbl)

        layout.addStretch()
        return w

    # ── Trading rules tab ─────────────────────────────────────────────────
    def _build_trading_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        form = QFormLayout()
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._capital = QDoubleSpinBox()
        self._capital.setRange(1000, 10_000_000)
        self._capital.setDecimals(0)
        self._capital.setValue(DEFAULT_CAPITAL)
        self._capital.setPrefix("₹ ")
        form.addRow("Starting Capital:", self._capital)

        self._max_risk = QDoubleSpinBox()
        self._max_risk.setRange(0.1, 10.0)
        self._max_risk.setDecimals(1)
        self._max_risk.setSuffix(" %")
        self._max_risk.setValue(MAX_RISK_PER_TRADE_PCT)
        form.addRow("Max Risk / Trade:", self._max_risk)

        self._daily_loss_limit = QDoubleSpinBox()
        self._daily_loss_limit.setRange(1.0, 20.0)
        self._daily_loss_limit.setDecimals(1)
        self._daily_loss_limit.setSuffix(" %")
        self._daily_loss_limit.setValue(MAX_DAILY_LOSS_PCT)
        form.addRow("Daily Loss Limit:", self._daily_loss_limit)

        self._max_positions = QSpinBox()
        self._max_positions.setRange(1, 20)
        self._max_positions.setValue(3)
        form.addRow("Max Open Positions:", self._max_positions)

        self._paper_mode = QCheckBox("Paper trading mode (no real orders)")
        self._paper_mode.setChecked(True)
        form.addRow("Mode:", self._paper_mode)

        layout.addLayout(form)

        save_btn = QPushButton("Save Trading Rules")
        save_btn.setObjectName("btn-primary")
        save_btn.setMinimumHeight(40)
        save_btn.setMaximumWidth(220)
        save_btn.clicked.connect(self._save_trading_settings)
        layout.addWidget(save_btn)
        layout.addStretch()
        return w

    # ── About tab ─────────────────────────────────────────────────────────
    def _build_about_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        for text, style in [
            ("TradeMind AI", "font-size:24px; font-weight:700;"),
            ("v1.0.0", f"font-size:13px; color:{COLOR_TEXT_MUTED};"),
            ("", ""),
            ("AI-powered trading assistant for Indian stock markets (NSE/BSE).", "font-size:13px;"),
            ("Runs completely offline. Your data never leaves your computer.", f"color:{COLOR_TEXT_MUTED}; font-size:12px;"),
            ("", ""),
            ("Tech stack: PyQt6 · SQLite · llama-cpp-python · smartapi-python", f"color:{COLOR_TEXT_MUTED}; font-size:11px;"),
            ("Built with Python 3.11 on Windows 11", f"color:{COLOR_TEXT_MUTED}; font-size:11px;"),
        ]:
            lbl = QLabel(text)
            if style:
                lbl.setStyleSheet(style)
            layout.addWidget(lbl)
        return w

    # ── Helpers ───────────────────────────────────────────────────────────
    def _password_field(self, placeholder: str) -> QLineEdit:
        f = QLineEdit()
        f.setEchoMode(QLineEdit.EchoMode.Password)
        f.setPlaceholderText(placeholder)
        return f

    def _browse_model(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select GGUF Model", str(DEFAULT_LLAMA_MODEL_PATH),
            "GGUF Model Files (*.gguf);;All Files (*)"
        )
        if path:
            self._model_path.setText(path)

    def _show_api_help(self):
        QMessageBox.information(
            self, "Getting Angel One API Credentials",
            "1. Log in to smartapi.angelbroking.com\n"
            "2. Click 'Create App' → fill in app details\n"
            "3. Copy your API Key\n"
            "4. Enable TOTP in the Angel One app:\n"
            "   Profile → Security → Enable TOTP\n"
            "   Scan the QR with any Authenticator app\n"
            "   Copy the secret key shown\n\n"
            "Your Client ID is your Angel One login ID (e.g. A123456)\n"
            "Your Password is your Angel One trading password."
        )

    def _save_broker_credentials(self):
        from app.security.vault import Vault
        api_key    = self._api_key.text().strip()
        client_id  = self._client_id.text().strip()
        password   = self._client_pwd.text().strip()
        totp_secret = self._totp_secret.text().strip()

        if not all([api_key, client_id, password]):
            QMessageBox.warning(self, "Missing Fields", "API Key, Client ID, and Password are required.")
            return

        try:
            vault = Vault()
            vault.save("angel_api_key",     api_key)
            vault.save("angel_client_id",   client_id)
            vault.save("angel_password",    password)
            vault.save("angel_totp_secret", totp_secret)

            self._broker_status.setText("✓ Saved")
            self._broker_status.setStyleSheet(f"color: {COLOR_SUCCESS}; font-weight:600;")

            self.credentials_saved.emit({
                "api_key": api_key, "client_id": client_id,
                "password": password, "totp_secret": totp_secret
            })
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not save credentials:\n{e}")

    def _on_provider_changed(self, index: int):
        """Show/hide fields based on selected provider."""
        is_llama = (index == 2)
        is_cloud = (index in (0, 1))

        self._ai_api_key.setVisible(is_cloud)
        self._ai_key_help.setVisible(is_cloud)
        self._ai_model_id.setVisible(is_cloud)
        self._model_path.setVisible(is_llama)
        self._model_path_row_label.setVisible(is_llama)
        self._ai_threads.setVisible(is_llama)
        self._threads_label.setVisible(is_llama)
        self._ai_ctx.setVisible(is_llama)
        self._ctx_label.setVisible(is_llama)

        # Update help text
        if index == 0:
            self._ai_key_help.setText("Get free key: aistudio.google.com/app/apikey")
            self._ai_model_id.setPlaceholderText("gemini-2.0-flash  (leave blank for default)")
        elif index == 1:
            self._ai_key_help.setText("Get free key: console.groq.com/keys")
            self._ai_model_id.setPlaceholderText("llama-3.3-70b-versatile  (leave blank for default)")

    def _save_ai_settings(self):
        provider_map = {0: "gemini", 1: "groq", 2: "llama"}
        provider = provider_map[self._ai_provider.currentIndex()]

        if provider == "llama":
            model_path = self._model_path.text().strip()
            if not model_path or not Path(model_path).exists():
                QMessageBox.warning(self, "File Not Found", "Please select a valid .gguf model file.")
                return
            self.db.set_setting("ai_provider",   "llama")
            self.db.set_setting("ai_model_path", model_path)
            self.db.set_setting("ai_threads",    self._ai_threads.value())
            self.db.set_setting("ai_ctx_size",   self._ai_ctx.value())
        else:
            api_key = self._ai_api_key.text().strip()
            if not api_key:
                QMessageBox.warning(self, "Missing API Key", "Please enter an API key.")
                return
            from app.security.vault import Vault
            Vault().save(f"{provider}_api_key", api_key)
            self.db.set_setting("ai_provider",  provider)
            self.db.set_setting("ai_model_id",  self._ai_model_id.text().strip())

        self._ai_status.setText("Connecting…")
        self._ai_status.setStyleSheet(f"color: {COLOR_WARNING}; font-weight:600; font-size:11px;")
        self.model_path_changed.emit(provider)

    def _save_trading_settings(self):
        self.db.set_setting("capital",          self._capital.value())
        self.db.set_setting("max_risk_pct",     self._max_risk.value())
        self.db.set_setting("daily_loss_limit", self._daily_loss_limit.value())
        self.db.set_setting("max_positions",    self._max_positions.value())
        self.db.set_setting("paper_mode",       self._paper_mode.isChecked())
        QMessageBox.information(self, "Saved", "Trading rules saved successfully.")

    def _load_settings(self):
        # ── Restore credentials from vault ────────────────────────────────
        try:
            from app.security.vault import Vault
            creds = Vault().load_all_broker_creds()
            if creds.get("api_key"):
                self._api_key.setText(creds["api_key"])
            if creds.get("client_id"):
                self._client_id.setText(creds["client_id"])
            if creds.get("password"):
                self._client_pwd.setText(creds["password"])
            if creds.get("totp_secret"):
                self._totp_secret.setText(creds["totp_secret"])
        except Exception:
            pass

        # ── Restore AI provider + key ─────────────────────────────────────
        try:
            from app.security.vault import Vault
            vault = Vault()
            provider = self.db.get_setting("ai_provider", "gemini")
            provider_index = {"gemini": 0, "groq": 1, "llama": 2}.get(provider, 0)
            self._ai_provider.setCurrentIndex(provider_index)
            self._on_provider_changed(provider_index)

            api_key = vault.load(f"{provider}_api_key", "")
            if api_key:
                self._ai_api_key.setText(api_key)

            model_id = self.db.get_setting("ai_model_id", "")
            if model_id:
                self._ai_model_id.setText(model_id)
        except Exception:
            pass

        # ── Restore local Llama settings from DB ──────────────────────────
        self._model_path.setText(self.db.get_setting("ai_model_path", "") or "")
        threads  = self.db.get_setting("ai_threads",       "4")
        ctx      = self.db.get_setting("ai_ctx_size",      "4096")
        capital  = self.db.get_setting("capital",          str(DEFAULT_CAPITAL))
        risk_pct = self.db.get_setting("max_risk_pct",     str(MAX_RISK_PER_TRADE_PCT))
        dl_limit = self.db.get_setting("daily_loss_limit", str(MAX_DAILY_LOSS_PCT))
        max_pos  = self.db.get_setting("max_positions",    "3")
        paper    = self.db.get_setting("paper_mode",       "True")

        try:
            self._ai_threads.setValue(int(threads))
            self._ai_ctx.setValue(int(ctx))
            self._capital.setValue(float(capital))
            self._max_risk.setValue(float(risk_pct))
            self._daily_loss_limit.setValue(float(dl_limit))
            self._max_positions.setValue(int(max_pos))
            self._paper_mode.setChecked(paper == "True")
        except Exception:
            pass

    # ── Public status updaters (called by MainWindow) ─────────────────────
    def set_broker_status(self, connected: bool, label: str = ""):
        if connected:
            self._conn_badge.setText(f"● Connected — {label}")
            self._conn_badge.setStyleSheet(
                f"background: {COLOR_SUCCESS}18; color: {COLOR_SUCCESS}; "
                f"border-radius: 8px; padding: 8px 14px; font-size: 13px; font-weight: 700;"
            )
            self._broker_status.setText("✓ Connected")
            self._broker_status.setStyleSheet(f"color: {COLOR_SUCCESS}; font-weight:600;")
        else:
            self._conn_badge.setText(f"● Not Connected{' — ' + label if label else ''}")
            self._conn_badge.setStyleSheet(
                f"background: {COLOR_DANGER}18; color: {COLOR_DANGER}; "
                f"border-radius: 8px; padding: 8px 14px; font-size: 13px; font-weight: 700;"
            )
            self._broker_status.setText(label or "")
            self._broker_status.setStyleSheet(f"color: {COLOR_DANGER}; font-weight:600;")

    def set_ai_status(self, loaded: bool, model_name: str = "", error: str = ""):
        if loaded:
            self._ai_badge.setText(f"● AI Ready — {model_name}")
            self._ai_badge.setStyleSheet(
                f"background: {COLOR_SUCCESS}18; color: {COLOR_SUCCESS}; "
                f"border-radius: 8px; padding: 8px 14px; font-size: 13px; font-weight: 700;"
            )
            self._ai_status.setText(f"✓ Loaded: {model_name}")
            self._ai_status.setStyleSheet(f"color: {COLOR_SUCCESS}; font-weight:600; font-size:11px;")
        else:
            self._ai_badge.setText(f"● Model Not Loaded{' — ' + error if error else ''}")
            self._ai_badge.setStyleSheet(
                f"background: {COLOR_WARNING}18; color: {COLOR_WARNING}; "
                f"border-radius: 8px; padding: 8px 14px; font-size: 13px; font-weight: 700;"
            )
            if error:
                self._ai_status.setText(error)
                self._ai_status.setStyleSheet(f"color: {COLOR_DANGER}; font-weight:600; font-size:11px;")

    def refresh(self):
        self._load_settings()
