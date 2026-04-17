"""
TradeMind AI — Momentum Breakout Strategy

Logic:
  BUY  when: close breaks above the highest close of the last N candles
             AND current volume > avg_volume * volume_multiplier
             AND RSI is not overbought (< 75)

Stop-loss: 1× ATR below the breakout candle's low
Target:    2× ATR above entry (minimum 1:2 R:R)

Parameters (editable in UI):
  period       — lookback window for breakout level (default 20)
  volume_mult  — volume confirmation multiplier (default 1.5)
  rsi_period   — RSI period to filter overbought entries (default 14)
"""
import pandas as pd
import ta

from app.trading.strategies.base import AbstractStrategy
from app.trading.signal import TradeSignal, SignalType
from app.config import EXCHANGE_NSE


class MomentumBreakout(AbstractStrategy):
    name        = "Momentum Breakout"
    description = "Buys when price breaks above 20-period high with volume confirmation."
    min_bars    = 25

    def generate_signal(
        self,
        df: pd.DataFrame,
        symbol: str,
        exchange: str = EXCHANGE_NSE,
    ) -> TradeSignal:
        if len(df) < self.min_bars:
            return self._hold(symbol, exchange, "Not enough data")

        period      = int(self.get_param("period", 20))
        vol_mult    = float(self.get_param("volume_mult", 1.5))
        rsi_period  = int(self.get_param("rsi_period", 14))

        close  = df["close"]
        volume = df["volume"]

        # Highest close over the last `period` candles (excluding current)
        prev_high = float(close.iloc[-(period + 1):-1].max())
        curr_close = float(close.iloc[-1])
        curr_vol   = float(volume.iloc[-1])
        avg_vol    = float(volume.iloc[-(period + 1):-1].mean())

        # RSI filter
        rsi_series = ta.momentum.RSIIndicator(close, window=rsi_period).rsi()
        curr_rsi   = float(rsi_series.iloc[-1])

        # ── Conditions ────────────────────────────────────────────────────
        breakout     = curr_close > prev_high
        vol_confirm  = avg_vol > 0 and (curr_vol / avg_vol) >= vol_mult
        not_overbought = curr_rsi < 75

        if not (breakout and vol_confirm and not_overbought):
            reasons = []
            if not breakout:
                reasons.append(f"no breakout (close {curr_close:.1f} ≤ high {prev_high:.1f})")
            if not vol_confirm:
                mult = curr_vol / avg_vol if avg_vol > 0 else 0
                reasons.append(f"weak volume ({mult:.1f}x < {vol_mult}x)")
            if not not_overbought:
                reasons.append(f"RSI overbought ({curr_rsi:.0f})")
            return self._hold(symbol, exchange, "; ".join(reasons))

        # ── Entry pricing ─────────────────────────────────────────────────
        atr        = self._atr(df)
        entry      = curr_close
        stop_loss  = round(float(df["low"].iloc[-1]) - atr, 2)
        target     = round(entry + 2 * atr, 2)

        reason = (
            f"Breakout above ₹{prev_high:.2f} | "
            f"Vol {curr_vol / avg_vol:.1f}x avg | RSI {curr_rsi:.0f}"
        )

        return TradeSignal(
            strategy   = self.name,
            symbol     = symbol,
            exchange   = exchange,
            signal     = SignalType.BUY,
            price      = entry,
            stop_loss  = stop_loss,
            target     = target,
            confidence = min(0.9, 0.5 + (curr_vol / avg_vol - vol_mult) * 0.1),
            reason     = reason,
        )
