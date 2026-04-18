"""
TradeMind AI — News Fetcher
Pulls articles from free RSS feeds: ET Markets, Moneycontrol, Google News.
No API key required.
"""
import time
import threading
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from dataclasses import dataclass, field

import requests

try:
    import feedparser
    _HAS_FEEDPARSER = True
except ImportError:
    _HAS_FEEDPARSER = False

try:
    from bs4 import BeautifulSoup
    _HAS_BS4 = True
except ImportError:
    _HAS_BS4 = False

# ── RSS feed sources (all free, no key needed) ────────────────────────────────
_MARKET_FEEDS = [
    ("Economic Times Markets",
     "https://economictimes.indiatimes.com/markets/stocks/rss.cms"),
    ("Economic Times News",
     "https://economictimes.indiatimes.com/markets/rss.cms"),
    ("Moneycontrol",
     "https://www.moneycontrol.com/rss/MClatestnews.xml"),
]

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    )
}


@dataclass
class Article:
    title:     str
    summary:   str
    url:       str
    source:    str
    published: datetime = field(default_factory=datetime.now)

    def age_hours(self) -> float:
        return (datetime.now() - self.published).total_seconds() / 3600

    def is_recent(self, max_hours: int = 24) -> bool:
        return self.age_hours() <= max_hours


def _strip_html(text: str) -> str:
    if _HAS_BS4 and text:
        return BeautifulSoup(text, "lxml").get_text(separator=" ").strip()
    return text or ""


def _parse_date(entry) -> datetime:
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        try:
            return datetime(*entry.published_parsed[:6])
        except Exception:
            pass
    return datetime.now()


def _parse_feed(url: str, source: str, max_items: int = 20,
                timeout: int = 10) -> List[Article]:
    if not _HAS_FEEDPARSER:
        return []
    try:
        feed = feedparser.parse(url, request_headers=_HEADERS)
        articles = []
        for entry in feed.entries[:max_items]:
            title   = _strip_html(entry.get("title", ""))
            summary = _strip_html(entry.get("summary", "") or entry.get("description", ""))
            url_    = entry.get("link", "")
            pub     = _parse_date(entry)
            if title:
                articles.append(Article(title, summary[:600], url_, source, pub))
        return articles
    except Exception:
        return []


# ── Public API ────────────────────────────────────────────────────────────────
class NewsFetcher:
    """
    Fetches market news articles from multiple RSS feeds in parallel.
    Results cached for 15 minutes to avoid hammering sources.
    """
    _CACHE_TTL = 900   # 15 minutes

    def __init__(self):
        self._cache: Dict[str, tuple] = {}   # key → (timestamp, articles)
        self._lock = threading.Lock()

    # ── Market-wide news ──────────────────────────────────────────────────
    def fetch_market_news(self, max_per_feed: int = 15,
                          max_hours: int = 24) -> List[Article]:
        """Fetch general Indian market news from all configured feeds."""
        cache_key = "market"
        cached = self._get_cache(cache_key)
        if cached is not None:
            return cached

        articles: List[Article] = []
        threads  = []

        def _worker(feed_url, source):
            result = _parse_feed(feed_url, source, max_per_feed)
            with self._lock:
                articles.extend(result)

        for source, url in _MARKET_FEEDS:
            t = threading.Thread(target=_worker, args=(url, source), daemon=True)
            t.start()
            threads.append(t)

        for t in threads:
            t.join(timeout=12)

        recent = [a for a in articles if a.is_recent(max_hours)]
        recent.sort(key=lambda a: a.published, reverse=True)

        self._set_cache(cache_key, recent)
        return recent

    # ── Stock-specific news via Google News RSS ───────────────────────────
    def fetch_stock_news(self, symbol: str,
                         max_articles: int = 8,
                         max_hours: int = 48) -> List[Article]:
        """Fetch news specifically about one NSE symbol."""
        cache_key = f"stock_{symbol}"
        cached = self._get_cache(cache_key)
        if cached is not None:
            return cached

        query = f"{symbol}+NSE+India+stock"
        url   = (
            f"https://news.google.com/rss/search"
            f"?q={query}&hl=en-IN&gl=IN&ceid=IN:en"
        )
        articles = _parse_feed(url, "Google News", max_articles)
        recent   = [a for a in articles if a.is_recent(max_hours)]

        self._set_cache(cache_key, recent)
        return recent

    # ── Batch: news for multiple symbols ─────────────────────────────────
    def fetch_batch(self, symbols: List[str],
                    max_per_symbol: int = 5) -> Dict[str, List[Article]]:
        """Fetch stock-specific news for a list of symbols in parallel."""
        results: Dict[str, List[Article]] = {s: [] for s in symbols}
        threads = []

        def _worker(sym):
            results[sym] = self.fetch_stock_news(sym, max_per_symbol)

        for sym in symbols:
            t = threading.Thread(target=_worker, args=(sym,), daemon=True)
            t.start()
            threads.append(t)

        for t in threads:
            t.join(timeout=15)

        return results

    # ── Cache helpers ─────────────────────────────────────────────────────
    def _get_cache(self, key: str) -> Optional[List[Article]]:
        with self._lock:
            entry = self._cache.get(key)
        if entry and (time.time() - entry[0]) < self._CACHE_TTL:
            return entry[1]
        return None

    def _set_cache(self, key: str, data: list):
        with self._lock:
            self._cache[key] = (time.time(), data)
