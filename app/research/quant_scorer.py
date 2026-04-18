"""
TradeMind AI — Quant Scorer
Combines technical indicators + news sentiment into a composite 0-100 score.

Score breakdown:
  40%  News sentiment     (AI-rated, 0-100)
  35%  Technical signals  (RSI, trend, volume via yfinance)
  25%  Price momentum     (5-day and 20-day return)
"""
from __future__ import annotations
import time
from dataclasses import dataclass, field
from typing import Optional, Dict, Any

_HAS_YF     = True   # checked lazily inside score()
_HAS_PANDAS = True


@dataclass
class QuantData:
    symbol:       str
    # Price data
    current_price:  float = 0.0
    price_5d_chg:   float = 0.0     # % change over 5 days
    price_20d_chg:  float = 0.0     # % change over 20 days
    high_52w:       float = 0.0
    low_52w:        float = 0.0
    # Technical
    rsi_14:         float = 50.0
    volume_ratio:   float = 1.0     # today vol / 20-day avg vol
    above_sma20:    bool  = False
    above_sma50:    bool  = False
    # Fundamentals (from yfinance info)
    pe_ratio:       Optional[float] = None
    market_cap_cr:  Optional[float] = None   # in crores
    sector:         str = ""
    # Scores
    technical_score: float = 50.0
    momentum_score:  float = 50.0
    news_score:      float = 50.0   # filled by AI
    composite_score: float = 50.0
    # Meta
    error: str = ""
    signals: list = field(default_factory=list)   # human-readable signal list


def _clamp(val: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, val))


def _rsi(prices, period: int = 14) -> float:
    if len(prices) < period + 1:
        return 50.0
    delta  = prices.diff()
    gain   = delta.clip(lower=0).rolling(period).mean()
    loss   = (-delta.clip(upper=0)).rolling(period).mean()
    rs     = gain / loss.replace(0, float("nan"))
    rsi    = 100 - (100 / (1 + rs))
    return float(rsi.iloc[-1]) if not rsi.iloc[-1] != rsi.iloc[-1] else 50.0


def _tech_score(d: QuantData) -> tuple[float, list]:
    """Score 0-100 purely from technicals. Returns (score, signals)."""
    signals = []
    score   = 50.0

    # RSI component (0-40 pts)
    rsi = d.rsi_14
    if rsi < 30:
        score += 25;  signals.append(f"RSI {rsi:.0f} — oversold (bullish reversal zone)")
    elif rsi < 45:
        score += 15;  signals.append(f"RSI {rsi:.0f} — approaching oversold")
    elif rsi < 60:
        score += 5;   signals.append(f"RSI {rsi:.0f} — neutral")
    elif rsi < 70:
        score -= 5;   signals.append(f"RSI {rsi:.0f} — approaching overbought")
    else:
        score -= 20;  signals.append(f"RSI {rsi:.0f} — overbought (caution)")

    # SMA trend (0-20 pts)
    if d.above_sma20 and d.above_sma50:
        score += 15;  signals.append("Price above SMA20 & SMA50 — strong uptrend")
    elif d.above_sma20:
        score += 8;   signals.append("Price above SMA20 — short-term bullish")
    elif d.above_sma50:
        score += 3;   signals.append("Price above SMA50 only — mixed trend")
    else:
        score -= 15;  signals.append("Price below SMA20 & SMA50 — downtrend")

    # Volume (0-10 pts)
    vr = d.volume_ratio
    if vr > 2.0:
        score += 10;  signals.append(f"Volume {vr:.1f}x average — strong interest")
    elif vr > 1.3:
        score += 5;   signals.append(f"Volume {vr:.1f}x average — above average")
    elif vr < 0.5:
        score -= 5;   signals.append(f"Volume {vr:.1f}x average — low activity")

    # 52-week position
    if d.high_52w > d.low_52w and d.current_price > 0:
        pos = (d.current_price - d.low_52w) / (d.high_52w - d.low_52w)
        if pos > 0.8:
            score -= 8;  signals.append(f"Near 52-week high ({pos*100:.0f}% of range) — limited upside")
        elif pos < 0.3:
            score += 8;  signals.append(f"Near 52-week low ({pos*100:.0f}% of range) — potential rebound")

    return _clamp(score), signals


def _momentum_score(d: QuantData) -> tuple[float, list]:
    """Score 0-100 from price momentum."""
    signals = []
    score   = 50.0

    c5  = d.price_5d_chg
    c20 = d.price_20d_chg

    # 5-day momentum
    if c5 > 4:    score += 25; signals.append(f"Strong 5-day gain: +{c5:.1f}%")
    elif c5 > 2:  score += 15; signals.append(f"Positive 5-day gain: +{c5:.1f}%")
    elif c5 > 0:  score += 5;  signals.append(f"Slight 5-day gain: +{c5:.1f}%")
    elif c5 > -2: score -= 5;  signals.append(f"Slight 5-day decline: {c5:.1f}%")
    elif c5 > -4: score -= 15; signals.append(f"Moderate 5-day decline: {c5:.1f}%")
    else:         score -= 25; signals.append(f"Sharp 5-day decline: {c5:.1f}%")

    # 20-day momentum
    if c20 > 8:   score += 15; signals.append(f"Strong monthly trend: +{c20:.1f}%")
    elif c20 > 3: score += 8;  signals.append(f"Positive monthly trend: +{c20:.1f}%")
    elif c20 < -8:score -= 15; signals.append(f"Weak monthly trend: {c20:.1f}%")

    return _clamp(score), signals


class QuantScorer:
    """
    Fetches yfinance data for a symbol and computes quant scores.
    Call score(symbol) → QuantData.
    """

    _cache: Dict[str, tuple] = {}   # {symbol: (ts, QuantData)}
    _CACHE_TTL = 1800               # 30 minutes — safe for EOD data

    def score(self, symbol: str) -> QuantData:
        # Return cached result if fresh enough
        cached = self._cache.get(symbol)
        if cached and (time.time() - cached[0]) < self._CACHE_TTL:
            return cached[1]

        d = QuantData(symbol=symbol)
        try:
            import yfinance as yf
            import pandas as pd
        except ImportError:
            d.error = "yfinance / pandas not installed"
            return d

        nse_symbol = symbol.upper() + ".NS"
        try:
            ticker = yf.Ticker(nse_symbol)

            # ── Price history ─────────────────────────────────────────────
            hist = ticker.history(period="3mo", interval="1d", auto_adjust=True)
            if hist.empty:
                d.error = f"No price data for {nse_symbol}"
                return d

            close  = hist["Close"]
            volume = hist["Volume"]

            d.current_price = float(close.iloc[-1])
            d.high_52w      = float(close.max())
            d.low_52w       = float(close.min())

            # Returns
            if len(close) > 5:
                d.price_5d_chg  = float((close.iloc[-1] / close.iloc[-6] - 1) * 100)
            if len(close) > 20:
                d.price_20d_chg = float((close.iloc[-1] / close.iloc[-21] - 1) * 100)

            # RSI
            d.rsi_14 = _rsi(close)

            # SMA
            if len(close) >= 20:
                d.above_sma20 = float(close.iloc[-1]) > float(close.rolling(20).mean().iloc[-1])
            if len(close) >= 50:
                d.above_sma50 = float(close.iloc[-1]) > float(close.rolling(50).mean().iloc[-1])

            # Volume ratio (today vs 20-day avg)
            if len(volume) >= 2:
                avg_vol = float(volume.iloc[:-1].tail(20).mean())
                if avg_vol > 0:
                    d.volume_ratio = float(volume.iloc[-1]) / avg_vol

            # ── Fundamentals ──────────────────────────────────────────────
            info = ticker.info
            d.pe_ratio   = info.get("trailingPE") or info.get("forwardPE")
            mkt_cap      = info.get("marketCap")
            if mkt_cap:
                d.market_cap_cr = mkt_cap / 1e7   # to crores
            d.sector = info.get("sector", "")

        except Exception as e:
            d.error = str(e)[:120]
            return d

        # ── Compute scores ────────────────────────────────────────────────
        tech_score, tech_signals = _tech_score(d)
        mom_score,  mom_signals  = _momentum_score(d)

        d.technical_score = tech_score
        d.momentum_score  = mom_score
        d.signals         = tech_signals + mom_signals

        # composite (without news — caller fills news_score then calls finalise)
        d.composite_score = _clamp(
            0.50 * tech_score + 0.50 * mom_score
        )
        # Cache result
        QuantScorer._cache[symbol] = (time.time(), d)
        return d

    def finalise(self, d: QuantData, news_score: float):
        """Call after AI fills news_score to compute final composite."""
        d.news_score      = _clamp(news_score)
        d.composite_score = _clamp(
            0.40 * d.technical_score
            + 0.35 * d.momentum_score
            + 0.25 * news_score
        )
