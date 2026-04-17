"""
TradeMind AI — AI Research Gate
Before any auto-trade, the AI analyses the signal and returns a confidence score.
Only signals with confidence >= threshold are executed.

Output format (parsed from AI response):
  {
    "confidence": 0-100,
    "approved":   bool,
    "action":     "BUY" | "SELL" | "HOLD",
    "risk":       "LOW" | "MEDIUM" | "HIGH",
    "reason":     str,
  }
"""
import re
import pandas as pd
from typing import Optional


def _summarise_df(df: pd.DataFrame, n: int = 5) -> str:
    """Build a compact candle summary for the AI prompt."""
    tail = df.tail(n)
    lines = []
    for _, row in tail.iterrows():
        lines.append(
            f"  O:{row['open']:.1f} H:{row['high']:.1f} "
            f"L:{row['low']:.1f} C:{row['close']:.1f} V:{int(row['volume']):,}"
        )
    return "\n".join(lines)


def _parse_response(text: str, fallback_action: str) -> dict:
    """
    Parse structured AI response. Falls back to safe defaults on parse failure.
    """
    result = {
        "confidence": 0,
        "approved":   False,
        "action":     "HOLD",
        "risk":       "HIGH",
        "reason":     text[:200] if text else "No response",
    }

    for line in text.splitlines():
        line = line.strip()
        if line.upper().startswith("CONFIDENCE:"):
            m = re.search(r"\d+", line)
            if m:
                result["confidence"] = min(100, max(0, int(m.group())))
        elif line.upper().startswith("ACTION:"):
            val = line.split(":", 1)[-1].strip().upper()
            if val in ("BUY", "SELL", "HOLD"):
                result["action"] = val
        elif line.upper().startswith("RISK:"):
            val = line.split(":", 1)[-1].strip().upper()
            if val in ("LOW", "MEDIUM", "HIGH"):
                result["risk"] = val
        elif line.upper().startswith("REASON:"):
            result["reason"] = line.split(":", 1)[-1].strip()

    result["approved"] = (
        result["confidence"] >= 60
        and result["action"] == fallback_action
        and result["risk"] != "HIGH"
    )
    return result


class AIResearcher:
    """
    Uses the active AI engine to vet each trade signal before execution.

    Usage:
        researcher = AIResearcher(engine, confidence_threshold=70)
        result = researcher.research(signal, df)
        if result["approved"]:
            place_order(...)
    """

    def __init__(self, engine, confidence_threshold: int = 70):
        self._engine    = engine
        self._threshold = confidence_threshold

    def is_available(self) -> bool:
        return self._engine is not None and self._engine.is_loaded()

    def set_engine(self, engine):
        self._engine = engine

    def set_threshold(self, threshold: int):
        self._threshold = max(50, min(95, threshold))

    def research(self, signal, df: Optional[pd.DataFrame] = None) -> dict:
        """
        Analyse a TradeSignal with the AI engine.
        Returns research dict (see module docstring).
        Falls back to approved=False when AI is unavailable.
        """
        if not self.is_available():
            return {
                "confidence": 0,
                "approved":   False,
                "action":     "HOLD",
                "risk":       "HIGH",
                "reason":     "AI not connected — skipping research gate",
            }

        rr = signal.risk_reward
        sl_pct = (
            abs(signal.price - signal.stop_loss) / signal.price * 100
            if signal.price and signal.stop_loss
            else 0
        )
        tgt_pct = (
            abs(signal.target - signal.price) / signal.price * 100
            if signal.price and signal.target
            else 0
        )

        candles_text = _summarise_df(df) if df is not None and len(df) >= 5 else "N/A"

        prompt = f"""You are a disciplined intraday trader for Indian stocks (NSE).
Evaluate this trade signal and respond ONLY in the exact format below.

=== SIGNAL ===
Action   : {signal.signal.value}
Symbol   : {signal.symbol}
Strategy : {signal.strategy}
Entry    : ₹{signal.price:.2f}
Stop Loss: ₹{signal.stop_loss:.2f}  ({sl_pct:.1f}% risk)
Target   : ₹{signal.target:.2f}  ({tgt_pct:.1f}% gain)
R:R Ratio: {rr:.2f}
Confidence from strategy: {int(signal.confidence * 100)}%

=== LAST 5 CANDLES (1-min OHLCV) ===
{candles_text}

=== RESPOND IN THIS EXACT FORMAT ===
CONFIDENCE: [integer 0-100]
ACTION: [BUY or SELL or HOLD]
RISK: [LOW or MEDIUM or HIGH]
REASON: [one sentence max]

Rules: confidence>=70 only if trend is clear, volume confirms, SL is tight.
Capital is small (₹15,000) — be conservative."""

        try:
            response = self._engine.chat(prompt)
            result   = _parse_response(response, signal.signal.value)
            # Apply user-configured threshold
            result["approved"] = (
                result["confidence"] >= self._threshold
                and result["action"] == signal.signal.value
                and result["risk"] != "HIGH"
            )
            return result
        except Exception as e:
            return {
                "confidence": 0,
                "approved":   False,
                "action":     "HOLD",
                "risk":       "HIGH",
                "reason":     f"Research error: {e}",
            }
