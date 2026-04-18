"""
TradeMind AI — Main Application Window
Provides the sidebar navigation shell and hosts all screen widgets.
Also owns the AngelOneAPI and LlamaEngine singletons and wires them to widgets.
"""
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QPushButton, QLabel, QFrame, QStackedWidget, QStatusBar,
    QSizePolicy, QSpacerItem, QMessageBox
)
from PyQt6.QtCore import Qt, QTimer, QTime, QThread, pyqtSignal
from PyQt6.QtGui import QFont

from app.config import APP_NAME, APP_VERSION
from app.ui.styles import MAIN_STYLESHEET
from app.database.manager import DatabaseManager
from app.trading.engine import StrategyEngine


# ── Per-screen lazy loader — import + create only on first visit ─────────────
_SCREEN_FACTORIES = {
    0: lambda db: __import__('app.ui.widgets.dashboard',    fromlist=['DashboardWidget']).DashboardWidget(db),
    1: lambda db: __import__('app.ui.widgets.live_trading', fromlist=['LiveTradingWidget']).LiveTradingWidget(db),
    2: lambda db: __import__('app.ui.widgets.history',      fromlist=['HistoryWidget']).HistoryWidget(db),
    3: lambda db: __import__('app.ui.widgets.strategies',   fromlist=['StrategiesWidget']).StrategiesWidget(db),
    4: lambda db: __import__('app.ui.widgets.scanner',      fromlist=['ScannerWidget']).ScannerWidget(db),
    5: lambda db: __import__('app.ui.widgets.research',     fromlist=['ResearchWidget']).ResearchWidget(db),
    6: lambda db: __import__('app.ui.widgets.risk_monitor', fromlist=['RiskMonitorWidget']).RiskMonitorWidget(db),
    7: lambda db: __import__('app.ui.widgets.ai_assistant', fromlist=['AIAssistantWidget']).AIAssistantWidget(db),
    8: lambda db: __import__('app.ui.widgets.settings',     fromlist=['SettingsWidget']).SettingsWidget(db),
}


NAV_ITEMS = [
    # (label, icon, screen_index)
    ("MAIN",   None,  None),
    ("Dashboard",     "▦",  0),
    ("Live Trading",  "⚡", 1),
    ("Trade History", "📋", 2),
    ("ANALYSIS", None, None),
    ("Strategies",    "♟",  3),
    ("AI Scanner",    "🔍", 4),
    ("Research",      "📰", 5),
    ("Risk Monitor",  "🛡",  6),
    ("AI ASSISTANT", None, None),
    ("AI Assistant",  "🤖", 7),
    ("SYSTEM",  None, None),
    ("Settings",      "⚙",  8),
]


# ── Background login worker ────────────────────────────────────────────────────
class _LoginWorker(QThread):
    done = pyqtSignal(bool, str)

    def __init__(self, api, creds: dict):
        super().__init__()
        self.api   = api
        self.creds = creds

    def run(self):
        ok, msg = self.api.login(
            self.creds["api_key"],
            self.creds["client_id"],
            self.creds["password"],
            self.creds.get("totp_secret", ""),
        )
        self.done.emit(ok, msg)


# ── Background AI loader ───────────────────────────────────────────────────────
class _AILoadWorker(QThread):
    done = pyqtSignal(object, str)   # engine, error

    def __init__(self, db):
        super().__init__()
        self.db = db

    def run(self):
        from app.ai.engine import create_engine
        from app.security.vault import Vault
        vault    = Vault()
        provider = self.db.get_setting("ai_provider", "gemini")
        api_key  = vault.load(f"{provider}_api_key", "")
        model_id = self.db.get_setting("ai_model_id", "")
        model_path = self.db.get_setting("ai_model_path", "")
        n_threads  = int(self.db.get_setting("ai_threads", "4"))
        n_ctx      = int(self.db.get_setting("ai_ctx_size", "4096"))
        engine = create_engine(provider, api_key=api_key, model_path=model_path,
                               model_id=model_id)
        self.done.emit(engine, engine.get_error())


class _LoadingPlaceholder(QWidget):
    """Shown while a screen is being lazy-loaded."""
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lbl = QLabel("Loading…")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet("color: #6b7280; font-size: 14px;")
        lay.addWidget(lbl)


class NavButton(QPushButton):
    def __init__(self, label: str, icon: str, parent=None):
        super().__init__(parent)
        self.setObjectName("nav-btn")
        self.setText(f"  {icon}  {label}")
        self.setCheckable(False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(38)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._active = False

    def set_active(self, active: bool):
        self._active = active
        self.setProperty("active", "true" if active else "false")
        self.style().unpolish(self)
        self.style().polish(self)


class MainWindow(QMainWindow):
    def __init__(self, db: DatabaseManager):
        super().__init__()
        self.db = db
        self._nav_buttons: list = []
        self._current_index = 0
        self._api    = None   # AngelOneAPI instance (created on first login)
        self._engine = None   # LlamaEngine instance (created when model loads)
        self._login_worker   = None
        self._ai_load_worker = None

        # Strategy engine (lives on its own QThread)
        self._strategy_engine  = None
        self._strategy_thread  = None

        self.setWindowTitle(f"{APP_NAME}  v{APP_VERSION}")
        self.setMinimumSize(1280, 800)
        self.resize(1440, 900)

        self.setStyleSheet(MAIN_STYLESHEET)

        self._build_ui()
        self._build_status_bar()
        self._start_clock()
        self._navigate(0)

        # Defer heavy startup tasks — let window paint first
        QTimer.singleShot(1_500, self._try_auto_login)
        QTimer.singleShot(3_000, self._try_auto_load_ai)

    # ── UI construction ────────────────────────────────────────────────────
    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        root_layout.addWidget(self._build_sidebar())
        root_layout.addWidget(self._build_content())

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(220)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 0, 0, 12)
        layout.setSpacing(0)

        logo = QLabel(APP_NAME)
        logo.setObjectName("sidebar-logo")
        logo.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        layout.addWidget(logo)

        ver = QLabel(f"v{APP_VERSION}  •  NSE/BSE")
        ver.setObjectName("sidebar-version")
        layout.addWidget(ver)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: #2d3139; margin: 0 12px 8px 12px;")
        layout.addWidget(sep)

        for label, icon, idx in NAV_ITEMS:
            if icon is None:
                sec = QLabel(label)
                sec.setObjectName("nav-section")
                layout.addWidget(sec)
            else:
                btn = NavButton(label, icon)
                btn.clicked.connect(lambda checked, i=idx: self._navigate(i))
                layout.addWidget(btn)
                self._nav_buttons.append((idx, btn))

        layout.addStretch()

        self._market_status = QLabel("● Market Closed")
        self._market_status.setStyleSheet(
            "color: #ef4444; font-size: 11px; padding: 8px 16px;"
        )
        layout.addWidget(self._market_status)
        return sidebar

    def _build_content(self) -> QWidget:
        content = QWidget()
        content.setObjectName("content-area")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._stack = QStackedWidget()
        layout.addWidget(self._stack)

        # Screens are None until first visited — lazy loaded per _SCREEN_FACTORIES
        n_screens = len(_SCREEN_FACTORIES)
        self._screens = [None] * n_screens
        self._dashboard    = None
        self._live_trading = None
        self._history      = None
        self._strategies   = None
        self._scanner      = None
        self._research     = None
        self._risk_monitor = None
        self._ai_assistant = None
        self._settings     = None

        # Add placeholder widgets so QStackedWidget has the right indices
        for _ in range(n_screens):
            ph = _LoadingPlaceholder()
            self._stack.addWidget(ph)

        # Load dashboard and settings immediately (needed at startup)
        self._ensure_screen(0)   # dashboard always visible first
        self._ensure_screen(8)   # settings needed for credential wiring

        # ── Wire Settings signals ────────────────────────────────────────
        self._settings.credentials_saved.connect(self._on_credentials_saved)
        self._settings.model_path_changed.connect(self._on_model_path_changed)

        # ── Start strategy engine ─────────────────────────────────────────
        self._start_strategy_engine()

        return content

    def _build_status_bar(self):
        bar = QStatusBar()
        self.setStatusBar(bar)

        self._clock_lbl = QLabel("00:00:00")
        self._clock_lbl.setStyleSheet("padding: 0 12px; font-size: 11px;")

        self._conn_lbl = QLabel("● Not connected")
        self._conn_lbl.setStyleSheet("color: #ef4444; padding: 0 12px; font-size: 11px;")

        bar.addWidget(self._clock_lbl)
        bar.addPermanentWidget(self._conn_lbl)
        bar.showMessage("  Welcome to TradeMind AI  •  Configure Angel One credentials in Settings to begin")

    # ── Lazy screen loader ─────────────────────────────────────────────────
    def _ensure_screen(self, index: int):
        """Create and wire a screen on first visit, replace the placeholder."""
        if self._screens[index] is not None:
            return
        widget = _SCREEN_FACTORIES[index](self.db)
        self._screens[index] = widget
        self._stack.insertWidget(index, widget)
        old = self._stack.widget(index + 1)   # old placeholder shifted right
        self._stack.removeWidget(old)

        # Store named references
        _names = ['_dashboard','_live_trading','_history','_strategies',
                  '_scanner','_research','_risk_monitor','_ai_assistant','_settings']
        setattr(self, _names[index], widget)

        # Post-load wiring
        self._wire_screen(index, widget)

    def _wire_screen(self, index: int, widget):
        """Wire signals after lazy creation."""
        if index == 4:   # Scanner
            widget._auto_toggle.toggled.connect(self._on_auto_trade_toggled)
            widget._conf_spin.valueChanged.connect(self._on_conf_threshold_changed)
            if self._strategy_engine:
                self._strategy_engine.scan_result.connect(widget.on_scan_result)
        elif index == 5:   # Research
            widget.buy_requested.connect(self._on_buy_requested)
            if self._engine:
                widget.set_engine(self._engine)
            if self._api:
                widget.set_api(self._api)
        elif index == 7:   # AI Assistant
            if self._engine:
                widget.set_engine(self._engine)
        elif index == 1:   # Live Trading
            if self._api:
                widget.set_api(self._api)
            if self._strategy_engine:
                self._strategy_engine.ltp_updated.connect(
                    lambda ltps, w=widget: hasattr(w, 'update_ltps') and w.update_ltps(ltps)
                )

    # ── Navigation ─────────────────────────────────────────────────────────
    def _navigate(self, index: int):
        self._current_index = index
        self._ensure_screen(index)          # lazy load if first visit
        self._stack.setCurrentIndex(index)
        for idx, btn in self._nav_buttons:
            btn.set_active(idx == index)
        screen = self._screens[index]
        if screen and hasattr(screen, "refresh"):
            screen.refresh()

    # ── Clock / Market status ──────────────────────────────────────────────
    def _start_clock(self):
        timer = QTimer(self)
        timer.timeout.connect(self._tick)
        timer.start(1000)
        self._tick()

    def _tick(self):
        now = QTime.currentTime()
        self._clock_lbl.setText(f"IST  {now.toString('hh:mm:ss')}")
        h, m = now.hour(), now.minute()
        is_open = (9, 15) <= (h, m) <= (15, 30)
        if is_open:
            self._market_status.setText("● Market Open")
            self._market_status.setStyleSheet(
                "color: #10b981; font-size: 11px; padding: 8px 16px;"
            )
        else:
            self._market_status.setText("● Market Closed")
            self._market_status.setStyleSheet(
                "color: #ef4444; font-size: 11px; padding: 8px 16px;"
            )

    def set_connection_status(self, connected: bool, label: str = ""):
        if connected:
            self._conn_lbl.setText(f"● {label or 'Connected'}")
            self._conn_lbl.setStyleSheet("color: #10b981; padding: 0 12px; font-size: 11px;")
        else:
            self._conn_lbl.setText(f"● {label or 'Not connected'}")
            self._conn_lbl.setStyleSheet("color: #ef4444; padding: 0 12px; font-size: 11px;")

    # ── Angel One API ─────────────────────────────────────────────────────
    def _try_auto_login(self):
        """On startup, auto-login if saved credentials exist."""
        try:
            from app.security.vault import Vault
            creds = Vault().load_all_broker_creds()
            if creds.get("api_key") and creds.get("client_id") and creds.get("password"):
                self._start_login(creds)
        except Exception:
            pass

    def _on_credentials_saved(self, creds: dict):
        """Called when the user clicks Save & Connect in Settings."""
        self._start_login(creds)

    def _start_login(self, creds: dict):
        from app.api.angel_one import AngelOneAPI
        if self._api is None:
            self._api = AngelOneAPI()
        self.set_connection_status(False, "Connecting…")
        self.statusBar().showMessage("  Connecting to Angel One…")

        self._login_worker = _LoginWorker(self._api, creds)
        self._login_worker.done.connect(self._on_login_done)
        self._login_worker.start()

    def _on_login_done(self, ok: bool, msg: str):
        if ok:
            self.set_connection_status(True, msg)
            self.statusBar().showMessage(f"  Angel One connected — {msg}")
            self.db.add_alert("Angel One connected", msg, "INFO")
            if self._live_trading: self._live_trading.set_api(self._api)
            if self._research:     self._research.set_api(self._api)
            if self._strategy_engine:
                self._strategy_engine.set_api(self._api)
            self._settings.set_broker_status(True, msg)
        else:
            self.set_connection_status(False, "Login failed")
            self.statusBar().showMessage(f"  Angel One login failed: {msg}")
            self.db.add_alert("Login failed", msg, "WARNING")
            self._settings.set_broker_status(False, msg)

    # ── AI Engine ─────────────────────────────────────────────────────────
    def _try_auto_load_ai(self):
        """On startup, auto-load AI if a provider is configured."""
        provider = self.db.get_setting("ai_provider", "")
        if provider:
            self._load_ai_model()

    def _on_model_path_changed(self, _=None):
        """Called when user clicks Connect AI in Settings."""
        self._load_ai_model()

    def _load_ai_model(self):
        self.statusBar().showMessage("  Connecting to AI…")
        self._settings.set_ai_status(False, error="Connecting…")
        self._ai_load_worker = _AILoadWorker(self.db)
        self._ai_load_worker.done.connect(self._on_ai_loaded)
        self._ai_load_worker.start()

    # ── Strategy Engine ───────────────────────────────────────────────────
    def _start_strategy_engine(self):
        self._strategy_thread = QThread(self)
        self._strategy_engine = StrategyEngine(self.db, self._api)
        self._strategy_engine.moveToThread(self._strategy_thread)

        # Wire engine signals to UI
        # Scanner/LiveTrading wired lazily in _wire_screen when first visited
        self._strategy_engine.signal_generated.connect(self._on_signal)
        self._strategy_engine.order_executed.connect(self._on_order_executed)
        self._strategy_engine.ltp_updated.connect(self._on_ltp_updated)
        self._strategy_engine.engine_status.connect(
            lambda msg: self.statusBar().showMessage(f"  {msg}")
        )
        self._strategy_engine.trading_halted.connect(self._on_trading_halted)

        self._strategy_thread.started.connect(self._strategy_engine.start)
        self._strategy_thread.start()

    def _on_signal(self, signal):
        if self._strategies and hasattr(self._strategies, "on_signal"):
            self._strategies.on_signal(signal)

    def _on_order_executed(self, order: dict):
        if self._dashboard:  self._dashboard.refresh()
        if self._live_trading: self._live_trading.refresh()

    def _on_ltp_updated(self, ltps: dict):
        if self._live_trading and hasattr(self._live_trading, "update_ltps"):
            self._live_trading.update_ltps(ltps)

    def _on_trading_halted(self, msg: str):
        self.set_connection_status(False, "TRADING HALTED")
        self.statusBar().showMessage(f"  ⚠ {msg}")
        self.db.add_alert("Trading Halted", msg, "DANGER")

    def _on_ai_loaded(self, engine, error: str):
        if engine.is_loaded():
            self._engine = engine
            # Wire to already-created screens; lazy screens get it via _wire_screen
            if self._ai_assistant: self._ai_assistant.set_engine(engine)
            if self._research:     self._research.set_engine(engine)
            if self._strategy_engine:
                self._strategy_engine.set_ai_engine(engine)
            self._settings.set_ai_status(True, engine.model_name())
            self.statusBar().showMessage(f"  AI ready — {engine.model_name()}")
            self.db.add_alert("AI model loaded", engine.model_name(), "INFO")
        else:
            self.statusBar().showMessage(f"  AI model failed to load: {error}")
            self.db.add_alert("AI model failed", error, "WARNING")
            self._settings.set_ai_status(False, error=error)

    def _on_auto_trade_toggled(self, enabled: bool):
        threshold = self._scanner.get_min_confidence()
        if self._strategy_engine:
            self._strategy_engine.set_auto_trade(enabled, threshold)
        state = "ENABLED" if enabled else "DISABLED"
        self.statusBar().showMessage(
            f"  Auto-Trade {state} — min AI confidence {threshold}%"
        )
        self.db.add_alert(
            f"Auto-Trade {state}",
            f"Min confidence: {threshold}%",
            "WARNING" if enabled else "INFO",
        )

    def _on_conf_threshold_changed(self, value: int):
        if self._strategy_engine:
            self._strategy_engine.set_auto_trade(
                self._scanner.is_auto_trade(), value
            )

    def _on_buy_requested(self, order: dict):
        """Open the order dialog when user clicks BUY from research/intraday."""
        from app.ui.dialogs.order_dialog import OrderDialog
        dlg = OrderDialog(
            symbol    = order["symbol"],
            direction = order.get("direction", "BUY"),
            price     = order.get("price", 0.0),
            stop_loss = order.get("sl", 0.0),
            target    = order.get("target", 0.0),
            api       = self._api,
            parent    = self,
        )
        dlg.order_placed.connect(lambda r: self.db.add_alert(
            f"{'[LIVE]' if not r.get('paper') else '[PAPER]'} "
            f"{r['direction']} {r['qty']}× {r['symbol']}",
            f"Order ID: {r.get('orderid') or 'paper'}",
            "INFO",
        ))
        dlg.exec()
