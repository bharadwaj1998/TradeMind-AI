"""
TradeMind AI — Intraday Stock Picker
Selects the best NSE stocks for the current trading day.

Scoring criteria (time-aware):
  Pre-market  (< 9:15):  Previous close momentum + overnight news
  Morning     (9:15-11): Gap-up/down + volume surge + RSI extremes
  Midday      (11-13):   VWAP trend + momentum continuation
  Afternoon   (13-15:30): Strong trend continuation + high volume
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict

try:
    import yfinance as yf
    import pandas as pd
    import numpy as np
    _HAS_YF = True
except ImportError:
    _HAS_YF = False

from app.research.stock_discovery import NIFTY_50, FULL_UNIVERSE


@dataclass
class IntradayPick:
    symbol:      str
    ltp:         float = 0.0
    prev_close:  float = 0.0
    gap_pct:     float = 0.0       # today's open vs yesterday's close
    day_chg_pct: float = 0.0       # today's % change so far
    volume_ratio: float = 1.0
    rsi:         float = 50.0
    signal:      str = "WATCH"     # BUY / SHORT / WATCH
    entry:       float = 0.0
    target:      float = 0.0
    stop_loss:   float = 0.0
    score:       int = 50
    reason:      str = ""
    strategy:    str = ""          # "Gap & Go" | "VWAP Pullback" | "Momentum" etc.
    risk:        str = "MEDIUM"


def _session_phase() -> str:
    now = datetime.now()
    h, m = now.hour, now.minute
    if (h, m) < (9, 15):  return "pre"
    if (h, m) < (11, 0):  return "morning"
    if (h, m) < (13, 0):  return "midday"
    if (h, m) < (15, 30): return "afternoon"
    return "closed"


def _rsi_series(close, period=14) -> float:
    if len(close) < period + 1:
        return 50.0
    delta = close.diff()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    rs    = gain / loss.replace(0, float("nan"))
    rsi   = 100 - (100 / (1 + rs))
    v = float(rsi.iloc[-1])
    return v if v == v else 50.0


def _intraday_score(pick: IntradayPick, phase: str) -> IntradayPick:
    """Score and set entry/target/SL for an intraday pick."""
    score = 50
    reasons = []

    # Gap analysis
    gap = pick.gap_pct
    if phase in ("morning", "pre"):
        if gap > 1.5:
            score += 20
            pick.signal   = "BUY"
            pick.strategy = "Gap & Go"
            reasons.append(f"Gap-up {gap:+.1f}% — strong morning momentum")
        elif gap < -1.5:
            score += 15
            pick.signal   = "SHORT"
            pick.strategy = "Gap & Go Short"
            reasons.append(f"Gap-down {gap:+.1f}% — short opportunity")
        elif abs(gap) < 0.3:
            score += 8
            pick.strategy = "VWAP Pullback"
            reasons.append("Flat open — wait for VWAP direction")

    # Volume surge
    vr = pick.volume_ratio
    if vr > 2.5:
        score += 20
        reasons.append(f"Volume {vr:.1f}x avg — institutional activity")
    elif vr > 1.5:
        score += 10
        reasons.append(f"Volume {vr:.1f}x avg — above average")
    elif vr < 0.7:
        score -= 10
        reasons.append(f"Low volume {vr:.1f}x — avoid")

    # RSI
    rsi = pick.rsi
    if rsi < 35:
        score += 15
        if pick.signal != "SHORT":
            pick.signal = "BUY"
        reasons.append(f"RSI {rsi:.0f} — oversold bounce setup")
    elif rsi > 65:
        score += 10
        if phase == "morning" and gap > 0:
            reasons.append(f"RSI {rsi:.0f} — momentum continuation")
        else:
            score -= 5
            reasons.append(f"RSI {rsi:.0f} — overbought, caution")

    # Day change
    chg = pick.day_chg_pct
    if phase in ("midday", "afternoon"):
        if chg > 2:
            score += 15
            pick.signal   = "BUY"
            pick.strategy = pick.strategy or "Momentum"
            reasons.append(f"Up {chg:+.1f}% today — strong trend")
        elif chg < -2:
            score += 10
            pick.signal   = "SHORT"
            reasons.append(f"Down {chg:+.1f}% today — downtrend continuation")

    # Set entry/target/SL
    price = pick.ltp or pick.prev_close
    if pick.signal == "BUY":
        pick.entry     = price
        pick.target    = round(price * 1.018, 2)   # 1.8% target (intraday)
        pick.stop_loss = round(price * 0.990, 2)   # 1.0% stop
    elif pick.signal == "SHORT":
        pick.entry     = price
        pick.target    = round(price * 0.982, 2)   # 1.8% target
        pick.stop_loss = round(price * 1.010, 2)   # 1.0% stop

    pick.score  = max(0, min(100, score))
    pick.reason = " • ".join(reasons) if reasons else "No clear setup"
    pick.risk   = "LOW" if score >= 75 else ("MEDIUM" if score >= 55 else "HIGH")

    if not pick.strategy:
        pick.strategy = "Momentum" if pick.signal != "WATCH" else "Watch"

    return pick


class IntradayPicker:
    """
    Picks the best intraday stocks for the current session.

    Usage:
        picker = IntradayPicker(ai_engine)
        picks  = picker.pick(on_progress=cb)
    """

    def __init__(self, ai_engine=None):
        self._engine = ai_engine

    def set_engine(self, engine):
        self._engine = engine

    def pick(
        self,
        symbols: List[str] = None,
        api=None,                  # AngelOneAPI instance for live LTP
        top_n: int = 8,
        on_progress=None,
    ) -> List[IntradayPick]:
        """Run the intraday screen. Returns ranked picks."""
        def progress(msg):
            if on_progress: on_progress(msg)

        symbols = symbols or NIFTY_50
        phase   = _session_phase()
        picks: List[IntradayPick] = []

        progress(f"Market phase: {phase.upper()} — fetching intraday data…")

        if not _HAS_YF:
            return []

        batch = [s + ".NS" for s in symbols]

        # ── Fetch 5-day 1-min data for gap + volume ───────────────────────
        try:
            raw = yf.download(
                batch, period="5d", interval="1d",
                auto_adjust=True, progress=False, threads=True,
            )
            if raw.empty:
                return []

            # Handle both single and multi-ticker column structure
            if isinstance(raw.columns, pd.MultiIndex):
                close_df  = raw["Close"]
                volume_df = raw["Volume"]
                open_df   = raw["Open"]
            else:
                close_df  = raw[["Close"]].rename(columns={"Close": batch[0]})
                volume_df = raw[["Volume"]].rename(columns={"Volume": batch[0]})
                open_df   = raw[["Open"]].rename(columns={"Open": batch[0]})

        except Exception as e:
            progress(f"Data fetch error: {e}")
            return []

        for sym_ns in close_df.columns:
            sym = sym_ns.replace(".NS", "")
            try:
                c = close_df[sym_ns].dropna()
                v = volume_df[sym_ns].dropna()
                o = open_df[sym_ns].dropna()
                if len(c) < 2:
                    continue

                prev_close  = float(c.iloc[-2])
                today_open  = float(o.iloc[-1])
                today_close = float(c.iloc[-1])

                gap_pct     = (today_open  - prev_close) / prev_close * 100
                day_chg_pct = (today_close - prev_close) / prev_close * 100

                avg_vol     = float(v.iloc[:-1].tail(10).mean()) or 1
                vol_ratio   = float(v.iloc[-1]) / avg_vol

                rsi = _rsi_series(c)

                # Live LTP from Angel One if connected
                ltp = today_close
                if api and api.is_connected():
                    from app.api.angel_one import get_token
                    live = api.get_ltp("NSE", sym)
                    if live:
                        ltp = live

                pick = IntradayPick(
                    symbol       = sym,
                    ltp          = ltp,
                    prev_close   = prev_close,
                    gap_pct      = gap_pct,
                    day_chg_pct  = day_chg_pct,
                    volume_ratio = vol_ratio,
                    rsi          = rsi,
                )
                pick = _intraday_score(pick, phase)

                if pick.score >= 50:   # filter weak signals
                    picks.append(pick)

            except Exception:
                continue

        # Sort by score
        picks.sort(key=lambda p: p.score, reverse=True)
        top_picks = picks[:top_n]

        # ── AI commentary on top picks ────────────────────────────────────
        if self._engine and self._engine.is_loaded() and top_picks:
            progress("AI analysing top intraday picks…")
            self._ai_enrich(top_picks, phase)

        progress(f"Found {len(top_picks)} intraday picks")
        return top_picks

    def _ai_enrich(self, picks: List[IntradayPick], phase: str):
        """Ask AI for a brief commentary on the top picks batch."""
        rows = ""
        for p in picks[:5]:
            rows += (
                f"  {p.symbol}: {p.signal} | Gap {p.gap_pct:+.1f}% | "
                f"Vol {p.volume_ratio:.1f}x | RSI {p.rsi:.0f} | "
                f"Score {p.score}\n"
            )

        prompt = f"""Session: {phase.upper()} | {datetime.now().strftime('%d %b %Y %H:%M IST')}

Top intraday candidates (NSE):
{rows}
For each stock, give ONE short sentence (max 12 words) with the most important intraday reason.
Format: SYMBOL: reason

Be direct. Focus on what a day trader needs to act."""

        try:
            response = self._engine.chat(prompt)
            # Parse and attach AI reasons
            sym_map = {p.symbol: p for p in picks}
            for line in response.splitlines():
                if ":" in line:
                    sym, _, reason = line.partition(":")
                    sym = sym.strip().upper()
                    if sym in sym_map and reason.strip():
                        sym_map[sym].reason = reason.strip()
        except Exception:
            pass
