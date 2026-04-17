"""
TradeMind AI — Mean Reversion Strategy

Logic:
  BUY  when: RSI < oversold threshold (default 30)
             AND price is above its 50-period SMA (uptrend filter)
             AND Bollinger Band %B < 0.1 (price near lower band)

  SELL when: RSI > overbought threshold (default 70)
             AND price is below its 50-period SMA (downtrend filter)
             AND Bollinger Band %B > 0.9 (price near upper band)

Stop-loss: 1× ATR beyond entry
Target:    Middle Bollinger Band (mean reversion target)

Parameters (editable in UI):
  rsi_period  — RSI lookback (default 14)
  oversold    — RSI level for BUY signal (default 30)
  overbought  — RSI level for SELL signal (default 70)
  bb_period   — Bollinger Band period (default 20)
  bb_std      — Bollinger Band standard deviations (default 2)
  trend_ma    — SMA period for trend filter (default 50)
"""
import pandas as pd
import ta

from app.trading.strategies.base import AbstractStrategy
from app.trading.signal import TradeSignal, SignalType
from app.config import EXCHANGE_NSE


class MeanReversion(AbstractStrategy):
    name        = "Mean Reversion"
    description = "Buys oversold stocks (RSI < 30) and sells overbought (RSI > 70)."
    min_bars    = 55

    def generate_signal(
        self,
        df: pd.DataFrame,
        symbol: str,
        exchange: str = EXCHANGE_NSE,
    ) -> TradeSignal:
        if len(df) < self.min_bars:
            return self._hold(symbol, exchange, "Not enough data")

        rsi_period = int(self.get_param("rsi_period", 14))
        oversold   = float(self.get_param("oversold",   30))
        overbought = float(self.get_param("overbought", 70))
        bb_period  = int(self.get_param("bb_period",   20))
        bb_std     = float(self.get_param("bb_std",     2.0))
        trend_ma   = int(self.get_param("trend_ma",    50))

        close = df["close"]

        # ── Indicators ───────────────────────────────────────────────────
        rsi = ta.momentum.RSIIndicator(close, window=rsi_period).rsi()
        bb  = ta.volatility.BollingerBands(close, window=bb_period, window_dev=bb_std)
        sma = close.rolling(trend_ma).mean()

        curr_close  = float(close.iloc[-1])
        curr_rsi    = float(rsi.iloc[-1])
        curr_bb_pct = float(bb.bollinger_pband().iloc[-1])   # 0=lower, 1=upper
        curr_sma    = float(sma.iloc[-1])
        bb_mid      = float(bb.bollinger_mavg().iloc[-1])

        atr = self._atr(df)

        # ── BUY signal ────────────────────────────────────────────────────
        if curr_rsi < oversold and curr_bb_pct < 0.1 and curr_close > curr_sma * 0.97:
            stop_loss = round(curr_close - 1.5 * atr, 2)
            target    = round(bb_mid, 2)
            return TradeSignal(
                strategy   = self.name,
                symbol     = symbol,
                exchange   = exchange,
                signal     = SignalType.BUY,
                price      = curr_close,
                stop_loss  = stop_loss,
                target     = target,
                confidence = round(min(0.9, (oversold - curr_rsi) / oversold + 0.5), 2),
                reason     = (
                    f"RSI oversold {curr_rsi:.0f} | "
                    f"BB %B {curr_bb_pct:.2f} (near lower band) | "
                    f"Target BB mid ₹{bb_mid:.2f}"
                ),
            )

        # ── SELL signal ───────────────────────────────────────────────────
        if curr_rsi > overbought and curr_bb_pct > 0.9 and curr_close < curr_sma * 1.03:
            stop_loss = round(curr_close + 1.5 * atr, 2)
            target    = round(bb_mid, 2)
            return TradeSignal(
                strategy   = self.name,
                symbol     = symbol,
                exchange   = exchange,
                signal     = SignalType.SELL,
                price      = curr_close,
                stop_loss  = stop_loss,
                target     = target,
                confidence = round(min(0.9, (curr_rsi - overbought) / (100 - overbought) + 0.5), 2),
                reason     = (
                    f"RSI overbought {curr_rsi:.0f} | "
                    f"BB %B {curr_bb_pct:.2f} (near upper band) | "
                    f"Target BB mid ₹{bb_mid:.2f}"
                ),
            )

        return self._hold(
            symbol, exchange,
            f"RSI {curr_rsi:.0f} (neutral) | BB %B {curr_bb_pct:.2f}"
        )
