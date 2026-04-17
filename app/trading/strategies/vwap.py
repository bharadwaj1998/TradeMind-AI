"""
TradeMind AI — VWAP Pullback Strategy

Logic:
  VWAP is reset at market open (09:15 IST) each day.
  BUY when:
    - Price pulls back to within `deviation_pct` % of VWAP
    - The overall trend is up (price > VWAP for most of the session)
    - RSI is not oversold (<45) — we want a healthy pullback, not a breakdown
    - Volume on the pullback candle is below average (healthy retracement)

Stop-loss: Below the pullback candle low, rounded by 0.5× ATR
Target:    Previous session high or 1.5× ATR above entry

Parameters (editable in UI):
  deviation_pct — how close to VWAP counts as a "pullback" (default 0.5%)
  rsi_min       — minimum RSI to confirm trend health (default 40)
  vol_factor    — pullback volume must be < this × avg vol (default 0.8)
"""
import pandas as pd
import ta

from app.trading.strategies.base import AbstractStrategy
from app.trading.signal import TradeSignal, SignalType
from app.config import EXCHANGE_NSE


def _compute_vwap(df: pd.DataFrame) -> pd.Series:
    """
    Intraday VWAP from the start of the DataFrame.
    VWAP = cumsum(typical_price × volume) / cumsum(volume)
    """
    typical = (df["high"] + df["low"] + df["close"]) / 3
    cum_vol  = df["volume"].cumsum()
    cum_tpv  = (typical * df["volume"]).cumsum()
    return cum_tpv / cum_vol


class VWAPPullback(AbstractStrategy):
    name        = "VWAP Pullback"
    description = "Enters long when price pulls back to VWAP in an uptrend."
    min_bars    = 20

    def generate_signal(
        self,
        df: pd.DataFrame,
        symbol: str,
        exchange: str = EXCHANGE_NSE,
    ) -> TradeSignal:
        if len(df) < self.min_bars:
            return self._hold(symbol, exchange, "Not enough data")

        dev_pct    = float(self.get_param("deviation_pct", 0.5))
        rsi_min    = float(self.get_param("rsi_min",       40))
        vol_factor = float(self.get_param("vol_factor",    0.8))

        close  = df["close"]
        volume = df["volume"]

        # ── Indicators ───────────────────────────────────────────────────
        vwap_series  = _compute_vwap(df)
        curr_vwap    = float(vwap_series.iloc[-1])
        curr_close   = float(close.iloc[-1])
        curr_vol     = float(volume.iloc[-1])
        avg_vol      = float(volume.mean())

        rsi_series   = ta.momentum.RSIIndicator(close, window=14).rsi()
        curr_rsi     = float(rsi_series.iloc[-1])

        atr = self._atr(df)

        # ── Uptrend check: close was above VWAP > 60% of candles ─────────
        above_vwap_pct = float((close > vwap_series).mean()) * 100

        # Distance from VWAP as a percentage
        dist_pct = abs(curr_close - curr_vwap) / curr_vwap * 100

        # ── Conditions ────────────────────────────────────────────────────
        near_vwap    = dist_pct <= dev_pct
        price_below  = curr_close <= curr_vwap          # in pullback
        uptrend      = above_vwap_pct >= 60             # bullish session
        rsi_ok       = curr_rsi >= rsi_min              # not breaking down
        low_vol_pb   = avg_vol > 0 and (curr_vol / avg_vol) <= vol_factor

        if uptrend and near_vwap and price_below and rsi_ok and low_vol_pb:
            stop_loss = round(float(df["low"].iloc[-1]) - 0.5 * atr, 2)
            target    = round(float(df["high"].iloc[-5:].max()), 2)
            if target <= curr_close:
                target = round(curr_close + 1.5 * atr, 2)

            return TradeSignal(
                strategy   = self.name,
                symbol     = symbol,
                exchange   = exchange,
                signal     = SignalType.BUY,
                price      = curr_close,
                stop_loss  = stop_loss,
                target     = target,
                confidence = round(min(0.85, 0.5 + above_vwap_pct / 200), 2),
                reason     = (
                    f"Pullback to VWAP ₹{curr_vwap:.2f} ({dist_pct:.2f}%) | "
                    f"Session {above_vwap_pct:.0f}% above VWAP | RSI {curr_rsi:.0f}"
                ),
            )

        # Diagnose why no signal
        reasons = []
        if not uptrend:
            reasons.append(f"no uptrend ({above_vwap_pct:.0f}% above VWAP)")
        if not near_vwap:
            reasons.append(f"not near VWAP (dist {dist_pct:.1f}% > {dev_pct}%)")
        if not rsi_ok:
            reasons.append(f"RSI too low ({curr_rsi:.0f})")
        if not low_vol_pb:
            mult = curr_vol / avg_vol if avg_vol > 0 else 0
            reasons.append(f"high pullback vol ({mult:.1f}x)")

        return self._hold(symbol, exchange, "; ".join(reasons) or "No pullback")
