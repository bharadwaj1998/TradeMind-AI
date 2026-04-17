"""
TradeMind AI — Risk Manager
Validates every signal before it becomes an order.
Enforces: daily loss limit, max open positions, max capital exposure,
and calculates proper position size using fixed-fractional risk.
"""
from typing import Optional, Tuple

from app.database.manager import DatabaseManager
from app.trading.signal import TradeSignal, SignalType
from app.config import (
    DEFAULT_CAPITAL,
    MAX_RISK_PER_TRADE_PCT,
    MAX_DAILY_LOSS_PCT,
    MAX_OPEN_POSITIONS,
)


class RiskManager:
    """
    All risk checks run synchronously before order submission.
    Returns (approved: bool, reason: str, qty: int).
    """

    def __init__(self, db: DatabaseManager):
        self.db = db

    # ── Public API ────────────────────────────────────────────────────────
    def evaluate(
        self, signal: TradeSignal
    ) -> Tuple[bool, str, int]:
        """
        Run all risk checks for a signal.

        Returns:
            approved  — True if the signal may be traded
            reason    — explanation if rejected, or empty string if approved
            quantity  — recommended lot size (0 if rejected)
        """
        capital = self._get_capital()

        # 1. Only act on BUY / SELL signals
        if not signal.is_actionable:
            return False, "HOLD signal — no action", 0

        # 2. Daily loss limit
        ok, msg = self._check_daily_loss(capital)
        if not ok:
            return False, msg, 0

        # 3. Max open positions
        ok, msg = self._check_max_positions(signal)
        if not ok:
            return False, msg, 0

        # 4. Signal must have a stop-loss for auto-trading
        if signal.stop_loss is None or signal.stop_loss <= 0:
            return False, "No stop-loss set — cannot size position safely", 0

        # 5. Minimum R:R ratio (must be at least 1:1.5)
        rr = signal.risk_reward
        if rr is not None and rr < 1.5:
            return False, f"R:R {rr:.1f} below minimum 1:1.5 — skipped", 0

        # 6. Calculate position size
        qty = self._position_size(capital, signal)
        if qty < 1:
            return False, "Capital too small for this stop distance", 0

        return True, "", qty

    def is_trading_halted(self) -> bool:
        """True when daily loss limit is breached."""
        capital = self._get_capital()
        ok, _ = self._check_daily_loss(capital)
        return not ok

    def get_suggested_qty(
        self,
        capital: float,
        price: float,
        stop_loss: float,
        risk_pct: Optional[float] = None,
    ) -> int:
        """
        Public helper for the UI's risk calculator.
        Returns the suggested quantity for the given price & stop distance.
        """
        rp = risk_pct or MAX_RISK_PER_TRADE_PCT
        risk_amount    = capital * rp / 100
        risk_per_share = abs(price - stop_loss)
        if risk_per_share <= 0:
            return 0
        return max(1, int(risk_amount / risk_per_share))

    # ── Internal checks ───────────────────────────────────────────────────
    def _get_capital(self) -> float:
        val = self.db.get_setting("capital", str(DEFAULT_CAPITAL))
        try:
            return float(val)
        except (ValueError, TypeError):
            return DEFAULT_CAPITAL

    def _check_daily_loss(self, capital: float) -> Tuple[bool, str]:
        stats      = self.db.get_today_stats()
        daily_loss = min(stats["total_pnl"], 0)        # negative number or 0
        loss_pct   = abs(daily_loss) / capital * 100

        limit = float(self.db.get_setting("daily_loss_limit", str(MAX_DAILY_LOSS_PCT)))
        if loss_pct >= limit:
            return False, (
                f"Daily loss limit {limit:.0f}% reached "
                f"(current: {loss_pct:.1f}%) — trading halted"
            )
        return True, ""

    def _check_max_positions(self, signal: TradeSignal) -> Tuple[bool, str]:
        open_trades = self.db.get_trades(status="OPEN")
        max_pos = int(self.db.get_setting("max_positions", str(MAX_OPEN_POSITIONS)))

        # Check if we already have a position in this symbol
        existing = [t for t in open_trades if t.symbol == signal.symbol]
        if existing:
            return False, f"Already have an open position in {signal.symbol}"

        if len(open_trades) >= max_pos:
            return False, f"Max open positions ({max_pos}) reached"

        return True, ""

    def _position_size(self, capital: float, signal: TradeSignal) -> int:
        risk_pct   = float(self.db.get_setting("max_risk_pct", str(MAX_RISK_PER_TRADE_PCT)))
        risk_amount    = capital * risk_pct / 100
        price          = signal.price if signal.price > 0 else 1
        risk_per_share = abs(price - signal.stop_loss)
        if risk_per_share <= 0:
            return 0
        return max(1, int(risk_amount / risk_per_share))
