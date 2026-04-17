"""
TradeMind AI — Angel One WebSocket Feed
Streams live LTP ticks via SmartWebSocketV2 (no REST polling).

Token map: {angel_token_str: symbol_str}  e.g. {"2885": "RELIANCE"}
Prices arrive in paise — divided by 100 before calling on_tick.
"""
import threading
import logging
from typing import Callable, Dict, List, Optional

log = logging.getLogger(__name__)

# Angel One exchange type codes
_NSE_CM = 1   # NSE Cash Market
_BSE_CM = 3   # BSE Cash Market

# Subscription mode
_MODE_LTP = 1


class AngelOneFeed:
    """
    Real-time price feed via Angel One SmartWebSocketV2.

    Usage:
        feed = AngelOneFeed(on_tick=lambda sym, ltp: print(sym, ltp))
        feed.start(jwt_token, api_key, client_id, feed_token, token_map)
        ...
        feed.stop()

    on_tick(symbol: str, ltp: float) is called from the feed thread each tick.
    Falls back gracefully when SmartAPI is not installed.
    """

    def __init__(self, on_tick: Callable[[str, float], None]):
        self._on_tick  = on_tick
        self._sws      = None
        self._thread: Optional[threading.Thread] = None
        self._running  = False
        self._lock     = threading.Lock()
        self._token_map: Dict[str, str] = {}   # "2885" → "RELIANCE"

    # ── Public API ────────────────────────────────────────────────────────────
    def start(
        self,
        jwt_token:  str,
        api_key:    str,
        client_id:  str,
        feed_token: str,
        token_map:  Dict[str, str],   # {token: symbol}
    ) -> bool:
        """
        Connect to the WebSocket and begin streaming.
        Returns True if the thread was started; False if SmartAPI is missing.
        """
        try:
            from SmartApi.smartWebSocketV2 import SmartWebSocketV2
        except ImportError:
            log.warning("SmartWebSocketV2 not available — using REST fallback")
            return False

        if self._running:
            self.stop()

        with self._lock:
            self._token_map = dict(token_map)
            self._running   = True

        self._sws = SmartWebSocketV2(jwt_token, api_key, client_id, feed_token)
        self._sws.on_open  = self._on_open
        self._sws.on_data  = self._on_data
        self._sws.on_error = self._on_error
        self._sws.on_close = self._on_close

        self._thread = threading.Thread(
            target=self._sws.connect,
            daemon=True,
            name="angel-ws-feed",
        )
        self._thread.start()
        log.info(f"WebSocket feed started for {len(token_map)} symbols")
        return True

    def stop(self):
        """Disconnect and clean up."""
        self._running = False
        if self._sws:
            try:
                self._sws.close_connection()
            except Exception:
                pass
            self._sws = None
        log.info("WebSocket feed stopped")

    def is_running(self) -> bool:
        return (
            self._running
            and self._thread is not None
            and self._thread.is_alive()
        )

    def update_symbols(self, token_map: Dict[str, str]):
        """Hot-swap the symbol list while connected."""
        with self._lock:
            self._token_map = dict(token_map)
        if self._sws and self._running:
            tokens = list(token_map.keys())
            if tokens:
                try:
                    token_list = [{"exchangeType": _NSE_CM, "tokens": tokens}]
                    self._sws.subscribe("trademind_ltp", _MODE_LTP, token_list)
                except Exception as e:
                    log.warning(f"Resubscribe error: {e}")

    # ── WebSocket callbacks ───────────────────────────────────────────────────
    def _on_open(self, wsapp, message):
        with self._lock:
            tokens = list(self._token_map.keys())
        if not tokens:
            return
        token_list = [{"exchangeType": _NSE_CM, "tokens": tokens}]
        try:
            self._sws.subscribe("trademind_ltp", _MODE_LTP, token_list)
            log.info(f"Subscribed to {len(tokens)} tokens")
        except Exception as e:
            log.error(f"Subscribe failed: {e}")

    def _on_data(self, wsapp, message):
        try:
            token     = str(message.get("token", ""))
            ltp_paise = message.get("last_traded_price", 0)
            if token and ltp_paise:
                ltp = ltp_paise / 100.0          # paise → rupees
                with self._lock:
                    symbol = self._token_map.get(token)
                if symbol:
                    self._on_tick(symbol, ltp)
        except Exception as e:
            log.debug(f"on_data parse error: {e}")

    def _on_error(self, wsapp, message):
        log.warning(f"WebSocket error: {message}")

    def _on_close(self, wsapp, message):
        log.info(f"WebSocket closed: {message}")
        self._running = False
