"""
TradeMind AI — TradeSignal
A signal emitted by a strategy when it detects a trade opportunity.
"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class SignalType(str, Enum):
    BUY  = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"    # no action — returned when no edge is detected


@dataclass
class TradeSignal:
    """
    Immutable output from a strategy's generate_signal() method.

    Fields:
        strategy    — which strategy produced this signal
        symbol      — NSE/BSE ticker
        exchange    — "NSE" or "BSE"
        signal      — BUY / SELL / HOLD
        price       — suggested entry price (0 = use market price)
        stop_loss   — suggested stop-loss level
        target      — suggested profit target
        confidence  — 0.0–1.0 (1.0 = highest conviction)
        reason      — human-readable explanation for the AI log
        timestamp   — when the signal was generated
    """
    strategy:   str
    symbol:     str
    exchange:   str
    signal:     SignalType
    price:      float          = 0.0
    stop_loss:  Optional[float] = None
    target:     Optional[float] = None
    confidence: float          = 0.5
    reason:     str            = ""
    timestamp:  datetime       = field(default_factory=datetime.now)

    @property
    def is_actionable(self) -> bool:
        """True if the signal is BUY or SELL (not HOLD)."""
        return self.signal in (SignalType.BUY, SignalType.SELL)

    @property
    def risk_reward(self) -> Optional[float]:
        """R:R ratio if stop_loss and target are both set."""
        if self.stop_loss and self.target and self.price > 0:
            risk   = abs(self.price - self.stop_loss)
            reward = abs(self.target - self.price)
            return round(reward / risk, 2) if risk > 0 else None
        return None

    def summary(self) -> str:
        rr = f"  R:R {self.risk_reward:.1f}" if self.risk_reward else ""
        sl = f"  SL ₹{self.stop_loss:,.2f}" if self.stop_loss else ""
        tgt = f"  Target ₹{self.target:,.2f}" if self.target else ""
        return (
            f"[{self.strategy}] {self.signal.value} {self.symbol} "
            f"@ ₹{self.price:,.2f}{sl}{tgt}{rr}  — {self.reason}"
        )
