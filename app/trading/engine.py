"""
TradeMind AI — Strategy Engine
Runs all active strategies on a timer during market hours.

Flow every tick:
  1. For each active strategy × watched symbol:
     a. Fetch recent OHLCV candles from Angel One (or simulated data)
     b. Run strategy.generate_signal(df)
     c. Pass signal through RiskManager
     d. If approved: place order (paper or live) → log to DB
  2. Emit signals to UI via Qt signals

Also handles:
  - Watchlist LTP refresh (every 5 s)
  - Auto-stop-loss monitoring (every 30 s)
  - Market open / close detection
"""
import time
from datetime import datetime
from typing import List, Dict, Optional

import pandas as pd
from PyQt6.QtCore import QThread, pyqtSignal, QTimer, QObject

from app.database.manager import DatabaseManager, Strategy
from app.trading.signal import TradeSignal, SignalType
from app.trading.risk import RiskManager
from app.config import EXCHANGE_NSE

# Strategy registry — maps DB name → class
from app.trading.strategies.momentum      import MomentumBreakout
from app.trading.strategies.mean_reversion import MeanReversion
from app.trading.strategies.vwap          import VWAPPullback

STRATEGY_REGISTRY = {
    "Momentum Breakout": MomentumBreakout,
    "Mean Reversion":    MeanReversion,
    "VWAP Pullback":     VWAPPullback,
}

# Default symbols to scan (can be extended via watchlist)
DEFAULT_SYMBOLS = [
    "RELIANCE", "INFY", "TCS", "HDFCBANK", "WIPRO",
    "ICICIBANK", "SBIN", "TATAMOTORS", "BAJFINANCE",
]


# ── Demo OHLCV generator (used when API is not connected) ─────────────────────
def _generate_demo_ohlcv(symbol: str, n: int = 60) -> pd.DataFrame:
    """
    Produce synthetic intraday OHLCV data for paper-trading / demo mode.
    Simulates a realistic price series using a random walk.
    """
    import numpy as np
    rng = np.random.default_rng(seed=hash(symbol) % 10000)

    # Seed price by symbol hash so each symbol feels different
    base = 500 + (hash(symbol) % 3000)
    returns = rng.normal(0.0002, 0.003, n)
    closes  = base * (1 + returns).cumprod()

    opens   = closes * rng.uniform(0.998, 1.002, n)
    highs   = closes * rng.uniform(1.001, 1.008, n)
    lows    = closes * rng.uniform(0.992, 0.999, n)
    volumes = rng.integers(50_000, 500_000, n).astype(float)

    # Inject a realistic momentum breakout near the end ~30% of the time
    if rng.random() < 0.3:
        closes[-3:] *= 1.015
        highs[-3:]  *= 1.018
        volumes[-3:] *= 2.5

    now = datetime.now()
    timestamps = pd.date_range(end=now, periods=n, freq="1min")

    return pd.DataFrame({
        "timestamp": timestamps,
        "open":      opens,
        "high":      highs,
        "low":       lows,
        "close":     closes,
        "volume":    volumes,
    })


def _angel_ohlcv_to_df(raw: list) -> Optional[pd.DataFrame]:
    """Convert Angel One getCandleData response list to a DataFrame."""
    if not raw:
        return None
    try:
        df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.dropna().sort_values("timestamp").reset_index(drop=True)
        return df if len(df) >= 10 else None
    except Exception:
        return None


# ── Engine ────────────────────────────────────────────────────────────────────
class StrategyEngine(QObject):
    """
    Lives on a background QThread.
    Use .start() / .stop() from the main thread.

    Signals:
        signal_generated(TradeSignal)   — new strategy signal
        order_executed(dict)            — order was placed
        ltp_updated(dict)               — {symbol: float} LTP refresh
        engine_status(str)              — status message for status bar
        trading_halted(str)             — emitted when daily loss limit hit
    """
    signal_generated = pyqtSignal(object)   # TradeSignal
    order_executed   = pyqtSignal(dict)
    ltp_updated      = pyqtSignal(dict)
    engine_status    = pyqtSignal(str)
    trading_halted   = pyqtSignal(str)

    def __init__(self, db: DatabaseManager, api=None):
        super().__init__()
        self.db   = db
        self.api  = api                        # AngelOneAPI or None
        self._risk = RiskManager(db)
        self._running  = False
        self._paper_mode = True
        self._watchlist: List[str] = list(DEFAULT_SYMBOLS)

        # Timers (created in start() so they belong to the right thread)
        self._strategy_timer: Optional[QTimer] = None
        self._ltp_timer:      Optional[QTimer] = None
        self._sl_timer:       Optional[QTimer] = None

    # ── Lifecycle ─────────────────────────────────────────────────────────
    def start(self):
        """Call this after moving to a QThread."""
        self._running    = True
        self._paper_mode = self.db.get_setting("paper_mode", "True") == "True"

        # Strategy scan every 60 seconds
        self._strategy_timer = QTimer()
        self._strategy_timer.timeout.connect(self._run_strategies)
        self._strategy_timer.start(60_000)

        # LTP refresh every 5 seconds
        self._ltp_timer = QTimer()
        self._ltp_timer.timeout.connect(self._refresh_ltps)
        self._ltp_timer.start(5_000)

        # Stop-loss monitor every 30 seconds
        self._sl_timer = QTimer()
        self._sl_timer.timeout.connect(self._monitor_stop_losses)
        self._sl_timer.start(30_000)

        self.engine_status.emit("Strategy engine started")

        # Run once immediately
        self._refresh_ltps()
        self._run_strategies()

    def stop(self):
        self._running = False
        for t in (self._strategy_timer, self._ltp_timer, self._sl_timer):
            if t:
                t.stop()
        self.engine_status.emit("Strategy engine stopped")

    def set_api(self, api):
        self.api = api

    def set_watchlist(self, symbols: List[str]):
        self._watchlist = symbols

    def add_symbol(self, symbol: str):
        if symbol not in self._watchlist:
            self._watchlist.append(symbol)

    # ── Strategy scan ─────────────────────────────────────────────────────
    def _run_strategies(self):
        if not self._running:
            return

        if self._risk.is_trading_halted():
            self.trading_halted.emit("Daily loss limit reached — trading halted")
            return

        if not self._is_market_hours():
            return

        active_strategies = self._get_active_strategies()
        if not active_strategies:
            return

        for strat_obj in active_strategies:
            for symbol in self._watchlist:
                try:
                    df = self._fetch_ohlcv(symbol)
                    if df is None or len(df) < strat_obj.min_bars:
                        continue

                    signal = strat_obj.generate_signal(df, symbol, EXCHANGE_NSE)

                    # Always emit to UI (even HOLDs, so the signal log stays active)
                    self.signal_generated.emit(signal)

                    if signal.is_actionable:
                        self._process_signal(signal)

                except Exception as e:
                    self.engine_status.emit(f"Strategy error [{strat_obj.name}]: {e}")

    def _process_signal(self, signal: TradeSignal):
        """Run risk checks then place order (paper or live)."""
        approved, reason, qty = self._risk.evaluate(signal)
        if not approved:
            self.db.add_alert(
                title=f"Signal rejected: {signal.symbol}",
                message=f"{signal.strategy}: {reason}",
                level="INFO",
            )
            return

        # Determine entry price
        entry_price = signal.price if signal.price > 0 else self._get_ltp(signal.symbol)
        if not entry_price:
            return

        # Paper trade or live
        order_id = None
        if not self._paper_mode and self.api and self.api.is_connected():
            try:
                result = self.api.place_order(
                    symbol    = signal.symbol,
                    exchange  = signal.exchange,
                    direction = signal.signal.value,
                    quantity  = qty,
                    price     = signal.price,
                    stop_loss = signal.stop_loss,
                    target    = signal.target,
                )
                if result["status"]:
                    order_id = result["orderid"]
                else:
                    self.db.add_alert(
                        title=f"Order failed: {signal.symbol}",
                        message=result["message"],
                        level="WARNING",
                    )
                    return
            except Exception as e:
                self.db.add_alert(title="Order error", message=str(e), level="DANGER")
                return

        # Log trade to DB
        trade = self.db.add_trade(
            symbol     = signal.symbol,
            exchange   = signal.exchange,
            direction  = signal.signal.value,
            quantity   = qty,
            entry_price = entry_price,
            stop_loss  = signal.stop_loss,
            target     = signal.target,
            strategy   = signal.strategy,
            ai_reason  = signal.reason,
            order_id   = order_id,
        )

        mode_tag = "PAPER" if (self._paper_mode or not order_id) else "LIVE"
        self.db.add_alert(
            title=f"[{mode_tag}] {signal.signal.value} {qty}× {signal.symbol}",
            message=signal.reason,
            level="INFO",
        )
        self.order_executed.emit({
            "trade_id": trade.id,
            "symbol":   signal.symbol,
            "signal":   signal.signal.value,
            "qty":      qty,
            "price":    entry_price,
            "strategy": signal.strategy,
            "paper":    self._paper_mode or not order_id,
        })

    # ── LTP refresh ───────────────────────────────────────────────────────
    def _refresh_ltps(self):
        if not self._running:
            return
        result: Dict[str, float] = {}
        if self.api and self.api.is_connected():
            result = self.api.refresh_watchlist(self._watchlist)
        else:
            # Demo mode: synthesise LTPs from demo OHLCV
            for sym in self._watchlist:
                df = _generate_demo_ohlcv(sym, 5)
                result[sym] = float(df["close"].iloc[-1])
        if result:
            self.ltp_updated.emit(result)

    def _get_ltp(self, symbol: str) -> Optional[float]:
        if self.api and self.api.is_connected():
            return self.api.get_ltp(EXCHANGE_NSE, symbol)
        df = _generate_demo_ohlcv(symbol, 2)
        return float(df["close"].iloc[-1])

    # ── Stop-loss monitor ─────────────────────────────────────────────────
    def _monitor_stop_losses(self):
        if not self._running:
            return
        open_trades = self.db.get_trades(status="OPEN")
        for trade in open_trades:
            if not trade.stop_loss:
                continue
            ltp = self._get_ltp(trade.symbol)
            if ltp is None:
                continue
            triggered = (
                (trade.direction == "BUY"  and ltp <= trade.stop_loss) or
                (trade.direction == "SELL" and ltp >= trade.stop_loss)
            )
            if triggered:
                self.db.close_trade(trade.id, exit_price=ltp)
                self.db.add_alert(
                    title=f"Stop-loss hit: {trade.symbol}",
                    message=f"Closed at ₹{ltp:,.2f} (SL ₹{trade.stop_loss:,.2f})",
                    level="WARNING",
                )
                self.engine_status.emit(
                    f"SL triggered: {trade.symbol} closed @ ₹{ltp:,.2f}"
                )

    # ── Helpers ───────────────────────────────────────────────────────────
    def _fetch_ohlcv(self, symbol: str) -> Optional[pd.DataFrame]:
        """Fetch 1-min candles. Returns demo data when API is not connected."""
        if self.api and self.api.is_connected():
            raw = self.api.get_quote(EXCHANGE_NSE, symbol, interval="ONE_MINUTE")
            df  = _angel_ohlcv_to_df(raw)
            if df is not None:
                return df
        return _generate_demo_ohlcv(symbol, 80)

    def _get_active_strategies(self) -> List:
        """Load active strategies from DB and instantiate them."""
        instances = []
        with self.db.session() as s:
            rows = s.query(Strategy).filter(Strategy.is_active == True).all()
            for row in rows:
                cls = STRATEGY_REGISTRY.get(row.name)
                if cls:
                    instances.append(cls(parameters=row.get_parameters()))
        return instances

    @staticmethod
    def _is_market_hours() -> bool:
        now = datetime.now()
        h, m = now.hour, now.minute
        return (9, 15) <= (h, m) <= (15, 30) and now.weekday() < 5
