"""
TradeMind AI — Research Report Generator
Orchestrates: news fetch → quant score → AI analysis → HTML report.

Output: a full HTML string ready for QTextBrowser.
"""
from __future__ import annotations
import threading
from datetime import datetime
from typing import List, Dict, Optional, Callable, Tuple

from app.research.news_fetcher  import NewsFetcher, Article
from app.research.quant_scorer  import QuantScorer, QuantData

# Default watchlist (same as engine DEFAULT_SYMBOLS)
DEFAULT_SYMBOLS = [
    "RELIANCE", "INFY", "TCS", "HDFCBANK",
    "ICICIBANK", "SBIN", "TATAMOTORS", "BAJFINANCE", "WIPRO",
]


# ── Prompt builder ────────────────────────────────────────────────────────────
def _build_ai_prompt(symbol: str, articles: List[Article], qd: QuantData) -> str:
    news_block = ""
    for i, a in enumerate(articles[:6], 1):
        age = f"{a.age_hours():.0f}h ago"
        news_block += f"{i}. [{age}] {a.title}\n   {a.summary[:200]}\n\n"

    if not news_block:
        news_block = "No recent news found for this symbol.\n"

    pe_str  = f"{qd.pe_ratio:.1f}" if qd.pe_ratio else "N/A"
    cap_str = f"₹{qd.market_cap_cr:,.0f} Cr" if qd.market_cap_cr else "N/A"

    return f"""You are a senior quantitative analyst at an Indian equity research firm.
Write a concise research note for {symbol} (NSE) for a retail trader with ₹15,000 capital.

=== QUANTITATIVE DATA ===
Price       : ₹{qd.current_price:,.2f}
5-day chg   : {qd.price_5d_chg:+.2f}%
20-day chg  : {qd.price_20d_chg:+.2f}%
RSI (14)    : {qd.rsi_14:.1f}
Volume ratio: {qd.volume_ratio:.2f}x avg
SMA20 trend : {"Above (bullish)" if qd.above_sma20 else "Below (bearish)"}
SMA50 trend : {"Above (bullish)" if qd.above_sma50 else "Below (bearish)"}
P/E ratio   : {pe_str}
Market cap  : {cap_str}
Sector      : {qd.sector or "N/A"}
52w High    : ₹{qd.high_52w:,.2f}
52w Low     : ₹{qd.low_52w:,.2f}

=== RECENT NEWS (last 48h) ===
{news_block}
=== RESPOND IN EXACTLY THIS FORMAT ===

NEWS_SCORE: [0-100 integer — overall news sentiment]
RECOMMENDATION: [STRONG BUY / BUY / HOLD / AVOID / STRONG AVOID]
TARGET_PRICE: [realistic 4-week target in ₹, or NONE]
STOP_LOSS: [suggested stop-loss ₹, or NONE]
RISK_LEVEL: [LOW / MEDIUM / HIGH]

SUMMARY:
[2-3 sentences covering what the news means for this stock and whether technicals support it]

KEY_CATALYSTS:
- [bullet 1]
- [bullet 2]
- [bullet 3 max]

RISKS:
- [bullet 1]
- [bullet 2 max]

VERDICT:
[1 sentence final verdict for a retail trader]

Rules: Be conservative. Small capital = tight risk. Never recommend a stock with HIGH risk unless STRONG AVOID."""


# ── Report parser ─────────────────────────────────────────────────────────────
def _parse_ai_response(text: str) -> dict:
    result = {
        "news_score":    50,
        "recommendation":"HOLD",
        "target_price":  None,
        "stop_loss":     None,
        "risk_level":    "MEDIUM",
        "summary":       "",
        "catalysts":     [],
        "risks":         [],
        "verdict":       "",
        "raw":           text,
    }
    if not text:
        return result

    section = None
    for line in text.splitlines():
        stripped = line.strip()
        upper    = stripped.upper()

        if upper.startswith("NEWS_SCORE:"):
            try:
                result["news_score"] = int(''.join(filter(str.isdigit, stripped.split(":", 1)[1])))
            except Exception:
                pass
        elif upper.startswith("RECOMMENDATION:"):
            val = stripped.split(":", 1)[1].strip().upper()
            for r in ["STRONG BUY", "STRONG AVOID", "BUY", "HOLD", "AVOID"]:
                if r in val:
                    result["recommendation"] = r
                    break
        elif upper.startswith("TARGET_PRICE:"):
            val = stripped.split(":", 1)[1].strip()
            if "NONE" not in val.upper():
                import re
                m = re.search(r"[\d,]+\.?\d*", val.replace(",", ""))
                if m:
                    try: result["target_price"] = float(m.group())
                    except: pass
        elif upper.startswith("STOP_LOSS:"):
            val = stripped.split(":", 1)[1].strip()
            if "NONE" not in val.upper():
                import re
                m = re.search(r"[\d,]+\.?\d*", val.replace(",", ""))
                if m:
                    try: result["stop_loss"] = float(m.group())
                    except: pass
        elif upper.startswith("RISK_LEVEL:"):
            val = stripped.split(":", 1)[1].strip().upper()
            if val in ("LOW", "MEDIUM", "HIGH"):
                result["risk_level"] = val
        elif upper.startswith("SUMMARY:"):
            section = "summary"
        elif upper.startswith("KEY_CATALYSTS:"):
            section = "catalysts"
        elif upper.startswith("RISKS:"):
            section = "risks"
        elif upper.startswith("VERDICT:"):
            section = "verdict"
        elif stripped.startswith("-") and section in ("catalysts", "risks"):
            result[section].append(stripped.lstrip("- ").strip())
        elif section == "summary" and stripped and not upper.startswith(("KEY_", "RISK", "VERDICT")):
            result["summary"] += " " + stripped
        elif section == "verdict" and stripped:
            result["verdict"] += " " + stripped

    result["summary"] = result["summary"].strip()
    result["verdict"] = result["verdict"].strip()
    return result


# ── HTML renderer ─────────────────────────────────────────────────────────────
_REC_COLOR = {
    "STRONG BUY":   ("#10b981", "▲▲"),
    "BUY":          ("#34d399", "▲"),
    "HOLD":         ("#f59e0b", "→"),
    "AVOID":        ("#f87171", "▼"),
    "STRONG AVOID": ("#ef4444", "▼▼"),
}
_RISK_COLOR = {
    "LOW": "#10b981", "MEDIUM": "#f59e0b", "HIGH": "#ef4444"
}
_SCORE_COLOR = {
    range(75, 101): "#10b981",
    range(55,  75): "#f59e0b",
    range(0,   55): "#ef4444",
}

def _score_color(score: int) -> str:
    for r, c in _SCORE_COLOR.items():
        if score in r: return c
    return "#9ca3af"

def _bar(value: float, color: str, width: int = 200) -> str:
    pct = max(0, min(100, value))
    return (
        f'<div style="background:#2d3139;border-radius:4px;width:{width}px;height:8px;display:inline-block;">'
        f'<div style="background:{color};width:{pct}%;height:100%;border-radius:4px;"></div>'
        f'</div>'
    )


def _render_card(symbol: str, qd: QuantData, ai: dict) -> str:
    rec     = ai["recommendation"]
    rc, ri  = _REC_COLOR.get(rec, ("#9ca3af", "→"))
    risk_c  = _RISK_COLOR.get(ai["risk_level"], "#9ca3af")
    comp    = int(qd.composite_score)
    comp_c  = _score_color(comp)

    catalysts_html = "".join(
        f'<li style="color:#e2e8f0;margin:4px 0;">{c}</li>'
        for c in ai["catalysts"]
    ) or '<li style="color:#6b7280;">No specific catalysts identified</li>'

    risks_html = "".join(
        f'<li style="color:#fca5a5;margin:4px 0;">{r}</li>'
        for r in ai["risks"]
    ) or '<li style="color:#6b7280;">Standard market risks apply</li>'

    tp_str = f"₹{ai['target_price']:,.2f}" if ai["target_price"] else "—"
    sl_str = f"₹{ai['stop_loss']:,.2f}"    if ai["stop_loss"]    else "—"
    pe_str = f"{qd.pe_ratio:.1f}x"         if qd.pe_ratio        else "—"

    signals_html = "".join(
        f'<div style="color:#94a3b8;font-size:12px;margin:2px 0;">• {s}</div>'
        for s in qd.signals
    ) or '<div style="color:#6b7280;font-size:12px;">No technical signals computed</div>'

    return f"""
<div style="background:#1e2330;border-radius:12px;border-left:4px solid {rc};
            margin:0 0 20px 0;padding:20px;font-family:Segoe UI,sans-serif;">

  <!-- Header -->
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
    <div>
      <span style="font-size:22px;font-weight:700;color:#f1f5f9;">{symbol}</span>
      &nbsp;
      <span style="font-size:14px;color:#94a3b8;">NSE  •  ₹{qd.current_price:,.2f}</span>
      &nbsp;
      <span style="color:{'#10b981' if qd.price_5d_chg >= 0 else '#ef4444'};font-weight:600;">
        {qd.price_5d_chg:+.2f}% (5d)
      </span>
    </div>
    <div style="text-align:right;">
      <span style="background:{rc};color:#fff;padding:4px 14px;border-radius:20px;
                   font-weight:700;font-size:14px;">{ri} {rec}</span>
      &nbsp;&nbsp;
      <span style="background:{risk_c}22;color:{risk_c};padding:4px 10px;
                   border-radius:20px;font-size:12px;">Risk: {ai['risk_level']}</span>
    </div>
  </div>

  <!-- Composite score bar -->
  <div style="margin-bottom:16px;">
    <span style="color:#94a3b8;font-size:12px;">Composite Score&nbsp;</span>
    <span style="color:{comp_c};font-weight:700;font-size:18px;">{comp}/100</span>
    &nbsp;&nbsp;{_bar(comp, comp_c, 180)}
    <div style="display:inline-block;margin-left:16px;font-size:11px;color:#6b7280;">
      Tech {int(qd.technical_score)} &nbsp;|&nbsp;
      Momentum {int(qd.momentum_score)} &nbsp;|&nbsp;
      News {int(qd.news_score)}
    </div>
  </div>

  <!-- Key numbers -->
  <table style="width:100%;border-collapse:collapse;margin-bottom:14px;">
    <tr>
      <td style="color:#94a3b8;font-size:12px;padding:3px 8px 3px 0;">RSI (14)</td>
      <td style="color:#e2e8f0;font-size:12px;padding:3px 12px 3px 0;font-weight:600;">{qd.rsi_14:.1f}</td>
      <td style="color:#94a3b8;font-size:12px;padding:3px 8px 3px 0;">Volume</td>
      <td style="color:#e2e8f0;font-size:12px;padding:3px 12px 3px 0;font-weight:600;">{qd.volume_ratio:.2f}x avg</td>
      <td style="color:#94a3b8;font-size:12px;padding:3px 8px 3px 0;">Target</td>
      <td style="color:#10b981;font-size:12px;font-weight:600;">{tp_str}</td>
    </tr>
    <tr>
      <td style="color:#94a3b8;font-size:12px;padding:3px 8px 3px 0;">20-day chg</td>
      <td style="color:#e2e8f0;font-size:12px;font-weight:600;">{qd.price_20d_chg:+.2f}%</td>
      <td style="color:#94a3b8;font-size:12px;padding:3px 8px 3px 0;">P/E</td>
      <td style="color:#e2e8f0;font-size:12px;font-weight:600;">{pe_str}</td>
      <td style="color:#94a3b8;font-size:12px;padding:3px 8px 3px 0;">Stop Loss</td>
      <td style="color:#ef4444;font-size:12px;font-weight:600;">{sl_str}</td>
    </tr>
  </table>

  <!-- Summary -->
  <div style="background:#252b3b;border-radius:8px;padding:12px;margin-bottom:12px;">
    <div style="color:#f59e0b;font-size:11px;font-weight:700;margin-bottom:6px;">AI ANALYSIS</div>
    <div style="color:#e2e8f0;font-size:13px;line-height:1.6;">{ai['summary'] or 'Analysis not available.'}</div>
  </div>

  <!-- Catalysts + Risks side by side -->
  <div style="display:flex;gap:12px;margin-bottom:12px;">
    <div style="flex:1;background:#252b3b;border-radius:8px;padding:12px;">
      <div style="color:#10b981;font-size:11px;font-weight:700;margin-bottom:6px;">KEY CATALYSTS</div>
      <ul style="margin:0;padding-left:16px;">{catalysts_html}</ul>
    </div>
    <div style="flex:1;background:#252b3b;border-radius:8px;padding:12px;">
      <div style="color:#ef4444;font-size:11px;font-weight:700;margin-bottom:6px;">RISK FACTORS</div>
      <ul style="margin:0;padding-left:16px;">{risks_html}</ul>
    </div>
  </div>

  <!-- Technical signals -->
  <div style="background:#252b3b;border-radius:8px;padding:12px;margin-bottom:12px;">
    <div style="color:#3b82f6;font-size:11px;font-weight:700;margin-bottom:6px;">TECHNICAL SIGNALS</div>
    {signals_html}
  </div>

  <!-- Verdict -->
  <div style="border-top:1px solid #2d3139;padding-top:10px;">
    <span style="color:#f59e0b;font-size:11px;font-weight:700;">VERDICT: </span>
    <span style="color:#f1f5f9;font-size:13px;">{ai['verdict'] or '—'}</span>
  </div>
</div>
"""


def _render_full_report(
    cards: list[str],
    generated_at: str,
    market_news_count: int,
    symbol_count: int,
) -> str:
    return f"""
<html><body style="background:#131722;color:#e2e8f0;
                   font-family:Segoe UI,sans-serif;padding:20px;margin:0;">

<div style="margin-bottom:24px;">
  <h1 style="color:#f1f5f9;margin:0 0 4px 0;font-size:24px;">
    TradeMind AI — Research Report
  </h1>
  <div style="color:#6b7280;font-size:12px;">
    Generated: {generated_at} &nbsp;|&nbsp;
    {symbol_count} stocks analysed &nbsp;|&nbsp;
    {market_news_count} market news articles processed
  </div>
  <div style="color:#f59e0b;font-size:11px;margin-top:6px;">
    ⚠ For educational purposes only. Not financial advice. Always use stop-losses.
  </div>
</div>

{"".join(cards) if cards else '<div style="color:#6b7280;padding:40px;text-align:center;">No data available — check your internet connection and try again.</div>'}

</body></html>
"""


# ── Main orchestrator ─────────────────────────────────────────────────────────
class ReportGenerator:
    """
    Orchestrates the full research pipeline:
      fetch news → quant score → AI analysis → HTML report

    Usage:
        gen = ReportGenerator(ai_engine)
        gen.generate(symbols, on_progress=cb, on_done=cb)
    """

    def __init__(self, ai_engine=None):
        self._engine  = ai_engine
        self._fetcher = NewsFetcher()
        self._scorer  = QuantScorer()
        self._running = False

    def set_engine(self, engine):
        self._engine = engine

    def is_running(self) -> bool:
        return self._running

    def generate(
        self,
        symbols: List[str] = None,
        on_progress: Callable[[str], None] = None,
        on_done: Callable[[str], None] = None,
    ):
        """Run the full pipeline in a background thread."""
        if self._running:
            return
        symbols = symbols or DEFAULT_SYMBOLS

        def _run():
            self._running = True
            try:
                html = self._pipeline(symbols, on_progress or (lambda m: None))
            except Exception as e:
                html = f"<html><body style='color:#ef4444;padding:20px;'>Report error: {e}</body></html>"
            self._running = False
            if on_done:
                on_done(html)

        threading.Thread(target=_run, daemon=True, name="research-gen").start()

    def _pipeline(self, symbols: List[str], progress) -> str:
        from concurrent.futures import ThreadPoolExecutor, as_completed

        # ── Step 1: Fetch news + quant data IN PARALLEL ───────────────────
        progress("Fetching news & price data in parallel…")

        quant_data: Dict[str, QuantData] = {}
        stock_news: Dict[str, list] = {}
        market_articles = []

        def _fetch_market():
            return self._fetcher.fetch_market_news(max_per_feed=15, max_hours=24)

        def _fetch_stock_news(sym):
            return sym, self._fetcher.fetch_stock_news(sym, max_articles=5)

        def _fetch_quant(sym):
            return sym, self._scorer.score(sym)

        with ThreadPoolExecutor(max_workers=6) as pool:
            # Submit all tasks simultaneously
            mkt_future   = pool.submit(_fetch_market)
            news_futures = {pool.submit(_fetch_stock_news, s): s for s in symbols}
            quant_futures= {pool.submit(_fetch_quant,      s): s for s in symbols}

            market_articles = mkt_future.result(timeout=20)

            for f in as_completed(news_futures, timeout=25):
                sym, articles = f.result()
                stock_news[sym] = articles

            for f in as_completed(quant_futures, timeout=30):
                sym, qd = f.result()
                quant_data[sym] = qd

        progress(f"Price data fetched. Running AI on top stocks…")

        # ── Step 2: Merge news, do a quick pre-sort by technical score ────
        all_news_map: Dict[str, list] = {}
        for sym in symbols:
            news = list(stock_news.get(sym, []))
            sym_lower = sym.lower()
            for a in market_articles:
                if sym_lower in a.title.lower() or sym_lower in a.summary.lower():
                    if a not in news:
                        news.insert(0, a)
            all_news_map[sym] = news

        # Sort by technical score — only call AI on top 5
        sorted_syms = sorted(
            symbols,
            key=lambda s: quant_data.get(s, QuantData(s)).composite_score,
            reverse=True,
        )
        ai_top_n   = 5
        ai_symbols = set(sorted_syms[:ai_top_n])

        # ── Step 3: Parallel AI calls for top stocks only ─────────────────
        ai_results: Dict[str, dict] = {}

        def _run_ai(sym):
            qd = quant_data.get(sym, QuantData(sym))
            return sym, self._ai_analyse(sym, all_news_map.get(sym, []), qd)

        if self._engine and self._engine.is_loaded():
            with ThreadPoolExecutor(max_workers=3) as pool:
                futures = {pool.submit(_run_ai, s): s for s in ai_symbols}
                done = 0
                for f in as_completed(futures, timeout=60):
                    sym, result = f.result()
                    ai_results[sym] = result
                    done += 1
                    progress(f"AI done {done}/{len(ai_symbols)}: {sym}")

        # ── Step 4: Build cards ───────────────────────────────────────────
        results: list[tuple[float, str]] = []
        for sym in symbols:
            qd      = quant_data.get(sym, QuantData(sym))
            ai      = ai_results.get(sym, {
                "news_score": 50, "recommendation": "HOLD",
                "target_price": None, "stop_loss": None,
                "risk_level": "MEDIUM", "summary": "",
                "catalysts": [], "risks": [],
                "verdict": "Quant data only — AI analysis for top stocks.",
            })
            self._scorer.finalise(qd, ai["news_score"])
            card = _render_card(sym, qd, ai)
            results.append((qd.composite_score, card))

        results.sort(key=lambda x: x[0], reverse=True)

        return _render_full_report(
            [c for _, c in results],
            generated_at=datetime.now().strftime("%d %b %Y  %H:%M IST"),
            market_news_count=len(market_articles),
            symbol_count=len(symbols),
        )

    def _ai_analyse(self, symbol: str, articles: list, qd: QuantData) -> dict:
        """Ask AI to analyse the stock. Returns parsed dict."""
        default = {
            "news_score": 50, "recommendation": "HOLD",
            "target_price": None, "stop_loss": None,
            "risk_level": "MEDIUM", "summary": "",
            "catalysts": [], "risks": [], "verdict": "",
        }

        if not (self._engine and self._engine.is_loaded()):
            default["summary"] = "AI engine not connected — connect Groq/Gemini in Settings."
            return default

        if qd.error:
            default["summary"] = f"Price data error: {qd.error}"
            return default

        prompt = _build_ai_prompt(symbol, articles, qd)
        try:
            response = self._engine.chat(prompt)
            return _parse_ai_response(response)
        except Exception as e:
            default["summary"] = f"AI error: {e}"
            return default
