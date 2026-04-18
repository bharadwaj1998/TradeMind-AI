"""
TradeMind AI — Stock Discovery
Finds stocks worth analysing by crawling:
  1. NSE top gainers / losers (public NSE API)
  2. Google News RSS mentions of Nifty symbols
  3. yfinance volume surge / momentum screen

Returns a ranked list of symbols to feed into the report generator.
"""
from __future__ import annotations
import re
import time
import threading
from typing import List, Dict, Tuple
from datetime import datetime

import requests

try:
    import yfinance as yf
    import pandas as pd
    _HAS_YF = True
except ImportError:
    _HAS_YF = False

try:
    import feedparser
    _HAS_FP = True
except ImportError:
    _HAS_FP = False

# ── Nifty 50 + Nifty Next 50 universe ────────────────────────────────────────
NIFTY_50 = [
    "RELIANCE","TCS","HDFCBANK","INFY","ICICIBANK","HINDUNILVR","KOTAKBANK",
    "SBIN","BHARTIARTL","ITC","LT","AXISBANK","BAJFINANCE","HCLTECH","WIPRO",
    "ASIANPAINT","MARUTI","SUNPHARMA","ULTRACEMCO","TITAN","BAJAJFINSV",
    "TATAMOTORS","NESTLEIND","TECHM","ONGC","NTPC","POWERGRID","ADANIENT",
    "JSWSTEEL","GRASIM","TATASTEEL","DIVISLAB","DRREDDY","HEROMOTOCO",
    "EICHERMOT","INDUSINDBK","HINDALCO","COALINDIA","M&M","ADANIPORTS",
    "SBILIFE","LTIM","TRENT","VEDL","CIPLA","BRITANNIA","APOLLOHOSP",
    "BEL","SHRIRAMFIN","BAJAJ-AUTO",
]

NIFTY_NEXT_50 = [
    "ZOMATO","DMART","SIEMENS","PIDILITIND","GODREJCP","AMBUJACEM","GLAND",
    "HAVELLS","LUPIN","MCDOWELL-N","NAUKRI","PERSISTENT","POLYCAB","SRF",
    "TORNTPHARM","TATACONSUM","UPL","VOLTAS","BANDHANBNK","BERGEPAINT",
    "BIOCON","COLPAL","CUMMINSIND","DLF","FEDERALBNK","GAIL","HAL",
    "INDUSTOWER","IRCTC","MARICO","MUTHOOTFIN","OBEROIRLTY","PEL",
    "PIIND","RECLTD","SBICARD","SUNDARMFIN","TATACOMM","TIINDIA",
    "UNITDSPR","WHIRLPOOL","ZYDUSLIFE",
]

FULL_UNIVERSE = NIFTY_50 + NIFTY_NEXT_50

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json,text/html,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}

_FEEDS = [
    ("ET Markets",    "https://economictimes.indiatimes.com/markets/stocks/rss.cms"),
    ("Moneycontrol",  "https://www.moneycontrol.com/rss/MClatestnews.xml"),
    ("ET Markets 2",  "https://economictimes.indiatimes.com/markets/rss.cms"),
]


# ── NSE API helper ─────────────────────────────────────────────────────────────
def _nse_top_movers(n: int = 10) -> Dict[str, List[str]]:
    """
    Fetch NSE top gainers and losers for Nifty 50.
    Returns {"gainers": [...], "losers": [...]}
    """
    try:
        session = requests.Session()
        # NSE requires a session cookie first
        session.get("https://www.nseindia.com", headers=_HEADERS, timeout=8)
        time.sleep(0.5)

        url  = "https://www.nseindia.com/api/equity-stockIndices?index=NIFTY%2050"
        resp = session.get(url, headers=_HEADERS, timeout=10)
        data = resp.json()

        stocks = data.get("data", [])
        # Skip the first row (index itself)
        stocks = [s for s in stocks if s.get("symbol") != "NIFTY 50"]

        sorted_by_chg = sorted(
            stocks,
            key=lambda x: float(x.get("pChange", 0)),
            reverse=True,
        )
        gainers = [s["symbol"] for s in sorted_by_chg[:n] if float(s.get("pChange", 0)) > 0]
        losers  = [s["symbol"] for s in sorted_by_chg[-n:] if float(s.get("pChange", 0)) < 0]
        return {"gainers": gainers, "losers": losers}
    except Exception:
        return {"gainers": [], "losers": []}


# ── News-based symbol extraction ──────────────────────────────────────────────
def _extract_symbols_from_feeds(universe: List[str]) -> Dict[str, int]:
    """
    Parse RSS feeds and count how many times each symbol is mentioned.
    Returns {symbol: mention_count}.
    """
    counts: Dict[str, int] = {s: 0 for s in universe}
    sym_set = set(universe)

    def _worker(feed_url: str):
        if not _HAS_FP:
            return
        try:
            feed = feedparser.parse(feed_url, request_headers={"User-Agent": _HEADERS["User-Agent"]})
            for entry in feed.entries[:30]:
                text = (entry.get("title", "") + " " + entry.get("summary", "")).upper()
                for sym in sym_set:
                    if re.search(rf"\b{re.escape(sym)}\b", text):
                        counts[sym] += 1
        except Exception:
            pass

    threads = [threading.Thread(target=_worker, args=(url,), daemon=True)
               for _, url in _FEEDS]
    for t in threads: t.start()
    for t in threads: t.join(timeout=12)

    return counts


# ── yfinance momentum screen ──────────────────────────────────────────────────
def _yf_screen(symbols: List[str], top_n: int = 15) -> List[Tuple[str, float]]:
    """
    Download recent price data and score each symbol by:
      momentum (5d) * 0.4 + volume_ratio * 0.3 + rsi_score * 0.3
    Returns list of (symbol, score) sorted descending.
    """
    if not _HAS_YF:
        return []

    results = []
    batch = [s + ".NS" for s in symbols]

    try:
        raw = yf.download(batch, period="1mo", interval="1d",
                          auto_adjust=True, progress=False, threads=True)
        if raw.empty:
            return []

        close  = raw["Close"]  if "Close"  in raw.columns else raw.xs("Close",  axis=1, level=0)
        volume = raw["Volume"] if "Volume" in raw.columns else raw.xs("Volume", axis=1, level=0)

        for sym_ns in close.columns:
            sym   = sym_ns.replace(".NS", "")
            c     = close[sym_ns].dropna()
            v     = volume[sym_ns].dropna()
            if len(c) < 10:
                continue

            # 5-day momentum
            mom5 = float((c.iloc[-1] / c.iloc[-6] - 1) * 100) if len(c) >= 6 else 0

            # Volume ratio (last day vs 20-day avg)
            avg_vol = float(v.iloc[:-1].tail(20).mean()) if len(v) > 1 else 1
            vol_r   = float(v.iloc[-1]) / avg_vol if avg_vol > 0 else 1

            # Simple RSI score (30=buy, 70=sell)
            delta = c.diff()
            gain  = delta.clip(lower=0).rolling(14).mean()
            loss  = (-delta.clip(upper=0)).rolling(14).mean()
            rsi   = float(100 - 100 / (1 + gain.iloc[-1] / (loss.iloc[-1] or 1e-9)))
            rsi_score = max(0, min(100, (70 - rsi) + 50))   # 50 at RSI=70, 100 at RSI=20

            score = mom5 * 0.4 + min(vol_r, 3) * 10 * 0.3 + rsi_score * 0.3
            results.append((sym, score))

    except Exception:
        pass

    results.sort(key=lambda x: x[1], reverse=True)
    return results[:top_n]


# ── Public API ────────────────────────────────────────────────────────────────
class StockDiscovery:
    """
    Discovers investment candidates by combining:
      - NSE top movers (gainers / losers)
      - News mention frequency (RSS)
      - yfinance momentum + volume screen
    """

    def discover(
        self,
        mode: str = "swing",      # "swing" or "intraday"
        top_n: int = 10,
        on_progress=None,
    ) -> Dict[str, List[str]]:
        """
        Returns:
          {
            "trending":  [sym, ...],   # news + movers
            "momentum":  [sym, ...],   # technical screen
            "gainers":   [sym, ...],   # NSE top gainers today
            "losers":    [sym, ...],   # NSE top losers today
            "combined":  [sym, ...],   # final ranked picks
          }
        """
        def progress(msg):
            if on_progress:
                on_progress(msg)

        progress("Scanning NSE top movers…")
        movers = _nse_top_movers(n=top_n)

        progress("Reading market news for trending stocks…")
        news_counts = _extract_symbols_from_feeds(NIFTY_50)

        # Top news mentions
        trending = sorted(news_counts, key=news_counts.get, reverse=True)
        trending = [s for s in trending if news_counts[s] > 0][:top_n]

        # Combine gainers + trending into candidate pool
        candidate_pool = list(dict.fromkeys(
            movers["gainers"] + trending + NIFTY_50[:20]
        ))[:30]

        progress("Running quant screen (momentum + volume + RSI)…")
        screened = _yf_screen(candidate_pool, top_n=top_n)
        momentum = [s for s, _ in screened]

        # Final combined: symbols that appear in ≥2 lists get priority
        from collections import Counter
        vote = Counter()
        for s in movers["gainers"]: vote[s] += 3
        for s in trending:          vote[s] += 2
        for s in momentum:          vote[s] += 2
        for _, s in enumerate(movers["losers"][:5]): vote[s] += 1  # losers = reversal opp

        combined = [s for s, _ in vote.most_common(top_n)]

        return {
            "trending": trending,
            "momentum": momentum,
            "gainers":  movers["gainers"],
            "losers":   movers["losers"],
            "combined": combined or momentum or NIFTY_50[:top_n],
        }
