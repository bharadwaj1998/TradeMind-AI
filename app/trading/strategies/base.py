"""
TradeMind AI — Abstract Strategy Base Class
All strategies inherit from this and implement generate_signal().
"""
from abc import ABC, abstractmethod
from typing import Optional

import pandas as pd

from app.trading.signal import TradeSignal, SignalType
from app.config import EXCHANGE_NSE


class AbstractStrategy(ABC):
    """
    Base class for all TradeMind strategies.

    Subclasses must implement:
        name        — display name (matches DB Strategy.name)
        description — short description
        generate_signal(df, symbol, exchange) → TradeSignal

    The engine feeds OHLCV DataFrames with columns:
        timestamp, open, high, low, close, volume
    All prices are in INR. Timestamps are IST.
    """

    name: str        = "AbstractStrategy"
    description: str = ""
    min_bars: int    = 30      # minimum candles required before generating signals

    def __init__(self, parameters: dict = None):
        self.params = parameters or {}

    def get_param(self, key: str, default=None):
        """Safe parameter lookup with fallback."""
        return self.params.get(key, default)

    @abstractmethod
    def generate_signal(
        self,
        df: pd.DataFrame,
        symbol: str,
        exchange: str = EXCHANGE_NSE,
    ) -> TradeSignal:
        """
        Analyse the OHLCV DataFrame and return a TradeSignal.
        Must always return a signal — use SignalType.HOLD when no edge exists.

        Args:
            df       — OHLCV DataFrame, newest row last
            symbol   — ticker (e.g. "RELIANCE")
            exchange — "NSE" or "BSE"
        """
        ...

    # ── Shared helpers ────────────────────────────────────────────────────
    @staticmethod
    def _last_close(df: pd.DataFrame) -> float:
        return float(df["close"].iloc[-1])

    @staticmethod
    def _last_volume(df: pd.DataFrame) -> float:
        return float(df["volume"].iloc[-1])

    @staticmethod
    def _avg_volume(df: pd.DataFrame, period: int = 20) -> float:
        return float(df["volume"].tail(period).mean())

    @staticmethod
    def _atr(df: pd.DataFrame, period: int = 14) -> float:
        """Average True Range — used for dynamic stop placement."""
        high  = df["high"]
        low   = df["low"]
        close = df["close"].shift(1)
        tr = pd.concat([
            high - low,
            (high - close).abs(),
            (low  - close).abs(),
        ], axis=1).max(axis=1)
        return float(tr.rolling(period).mean().iloc[-1])

    def _hold(self, symbol: str, exchange: str, reason: str = "") -> TradeSignal:
        """Convenience: return a HOLD signal."""
        return TradeSignal(
            strategy=self.name,
            symbol=symbol,
            exchange=exchange,
            signal=SignalType.HOLD,
            reason=reason or "No signal",
        )
