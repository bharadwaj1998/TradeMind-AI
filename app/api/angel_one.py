"""
TradeMind AI — Angel One SmartAPI Wrapper
Handles login (with TOTP), live quotes, order placement, and positions.

Usage:
    api = AngelOneAPI()
    ok, msg = api.login(api_key, client_id, password, totp_secret)
    if ok:
        ltp = api.get_ltp("NSE", "RELIANCE", "2885")
        api.place_order(...)
"""
import time
import threading
from datetime import datetime
from typing import Optional, Dict, List, Tuple

try:
    import pyotp
    _HAS_PYOTP = True
except ImportError:
    _HAS_PYOTP = False

try:
    from SmartApi import SmartConnect
    _HAS_SMARTAPI = True
except ImportError:
    _HAS_SMARTAPI = False

from app.config import EXCHANGE_NSE


# ── Symbol Token Lookup ───────────────────────────────────────────────────────
# Common NSE symbols and their Angel One token IDs.
# This covers most large-cap stocks. For others, use lookup_token().
_SYMBOL_TOKENS: Dict[str, str] = {
    "RELIANCE":   "2885",
    "INFY":       "1594",
    "TCS":        "11536",
    "HDFCBANK":   "1333",
    "WIPRO":      "3787",
    "ICICIBANK":  "4963",
    "AXISBANK":   "5900",
    "SBIN":       "3045",
    "TATAMOTORS": "3456",
    "TATASTEEL":  "3499",
    "BAJFINANCE": "317",
    "BAJAJFINSV": "16675",
    "KOTAKBANK":  "1922",
    "HINDUNILVR": "1394",
    "LTIM":       "17818",
    "HCLTECH":    "7229",
    "MARUTI":     "10999",
    "SUNPHARMA":  "3351",
    "TITAN":      "3506",
    "ULTRACEMCO": "11532",
    "ADANIENT":   "25",
    "ADANIPORTS": "15083",
    "ASIANPAINT": "236",
    "BHARTIARTL": "10604",
    "COALINDIA":  "20374",
    "DIVISLAB":   "10940",
    "DRREDDY":    "881",
    "EICHERMOT":  "910",
    "GRASIM":     "1232",
    "HEROMOTOCO": "1348",
    "HINDALCO":   "1363",
    "INDUSINDBK": "5258",
    "ITC":        "1660",
    "JSWSTEEL":   "11723",
    "LT":         "11483",
    "M&M":        "2031",
    "NESTLEIND":  "17963",
    "NTPC":       "11630",
    "ONGC":       "2475",
    "POWERGRID":  "14977",
    "SBILIFE":    "21808",
    "TECHM":      "13538",
    "TRENT":      "1964",
    "VEDL":       "3063",
    "WIPRO":      "3787",
    # Indices (for reference / watchlist display only)
    "NIFTY 50":   "99926000",
    "BANKNIFTY":  "99926009",
    "SENSEX":     "1",
}


def get_token(symbol: str) -> str:
    """Return the Angel One symbol token. Falls back to empty string if unknown."""
    return _SYMBOL_TOKENS.get(symbol.upper().strip(), "")


# ── Main API class ────────────────────────────────────────────────────────────
class AngelOneAPI:
    """
    Thread-safe wrapper around Angel One SmartAPI.

    State machine:
        DISCONNECTED → login() → CONNECTED
        CONNECTED    → any error → DISCONNECTED (auto-reconnect attempted)
    """

    def __init__(self):
        self._obj: Optional[object] = None   # SmartConnect instance
        self._lock   = threading.Lock()
        self._connected  = False
        self._client_id  = ""
        self._api_key    = ""
        self._jwt_token  = ""
        self._feed_token = ""
        self._profile: Dict = {}

    # ── Connection ────────────────────────────────────────────────────────
    def login(
        self,
        api_key: str,
        client_id: str,
        password: str,
        totp_secret: str = "",
    ) -> Tuple[bool, str]:
        """
        Authenticate with Angel One.
        Returns (success: bool, message: str).
        """
        if not _HAS_SMARTAPI:
            return False, (
                "SmartAPI library not installed.\n"
                "Run: pip install smartapi-python"
            )

        try:
            totp_code = ""
            if totp_secret:
                if not _HAS_PYOTP:
                    return False, "pyotp not installed: pip install pyotp"
                totp_code = pyotp.TOTP(totp_secret).now()

            with self._lock:
                self._obj = SmartConnect(api_key=api_key)
                data = self._obj.generateSession(client_id, password, totp_code)

            if data.get("status"):
                self._connected  = True
                self._api_key    = api_key
                self._client_id  = client_id
                self._jwt_token  = data["data"]["jwtToken"]
                self._feed_token = data["data"]["feedToken"]
                # Fetch profile
                try:
                    prof = self._obj.getProfile(self._feed_token)
                    self._profile = prof.get("data", {})
                except Exception:
                    pass
                name = self._profile.get("name", client_id)
                return True, f"Connected as {name}"
            else:
                msg = data.get("message", "Login failed")
                return False, msg

        except Exception as e:
            self._connected = False
            return False, str(e)

    def logout(self) -> None:
        with self._lock:
            if self._obj and self._connected:
                try:
                    self._obj.terminateSession(self._client_id)
                except Exception:
                    pass
            self._connected = False
            self._obj = None

    def is_connected(self) -> bool:
        return self._connected and self._obj is not None

    def get_profile(self) -> Dict:
        return self._profile

    # ── Market Data ───────────────────────────────────────────────────────
    def get_ltp(self, exchange: str, symbol: str, token: str = "") -> Optional[float]:
        """
        Fetch Last Traded Price for a symbol.
        If token is empty, looks it up from the built-in map.
        Returns None on failure.
        """
        if not self.is_connected():
            return None
        tok = token or get_token(symbol)
        if not tok:
            return None
        try:
            with self._lock:
                resp = self._obj.ltpData(exchange, symbol, tok)
            if resp and resp.get("status"):
                return float(resp["data"]["ltp"])
        except Exception:
            pass
        return None

    def get_quote(
        self,
        exchange: str,
        symbol: str,
        token: str = "",
        interval: str = "ONE_MINUTE",
        from_date: str = "",
        to_date: str = "",
    ) -> Optional[Dict]:
        """
        Fetch OHLCV candle data.
        Returns the raw API response data dict or None on failure.
        """
        if not self.is_connected():
            return None
        tok = token or get_token(symbol)
        if not tok:
            return None
        now = datetime.now()
        from_date = from_date or now.strftime("%Y-%m-%d 09:00")
        to_date   = to_date   or now.strftime("%Y-%m-%d %H:%M")
        try:
            with self._lock:
                resp = self._obj.getCandleData({
                    "exchange":    exchange,
                    "symboltoken": tok,
                    "interval":    interval,
                    "fromdate":    from_date,
                    "todate":      to_date,
                })
            return resp.get("data") if resp and resp.get("status") else None
        except Exception:
            return None

    def get_positions(self) -> List[Dict]:
        """Fetch all open positions from the broker."""
        if not self.is_connected():
            return []
        try:
            with self._lock:
                resp = self._obj.position()
            if resp and resp.get("status"):
                return resp.get("data") or []
        except Exception:
            pass
        return []

    def get_holdings(self) -> List[Dict]:
        """Fetch long-term holdings."""
        if not self.is_connected():
            return []
        try:
            with self._lock:
                resp = self._obj.holding()
            if resp and resp.get("status"):
                return resp.get("data") or []
        except Exception:
            pass
        return []

    def get_funds(self) -> Optional[Dict]:
        """Fetch available margin / funds."""
        if not self.is_connected():
            return None
        try:
            with self._lock:
                resp = self._obj.rmsLimit()
            if resp and resp.get("status"):
                return resp.get("data")
        except Exception:
            pass
        return None

    # ── Order Management ──────────────────────────────────────────────────
    def place_order(
        self,
        symbol: str,
        exchange: str = "NSE",
        direction: str = "BUY",         # "BUY" or "SELL"
        quantity: int = 1,
        price: float = 0.0,             # 0 = MARKET order
        stop_loss: Optional[float] = None,
        target: Optional[float] = None,
        product_type: str = "INTRADAY", # INTRADAY / DELIVERY / CARRYFORWARD
        token: str = "",
    ) -> Dict:
        """
        Place a live order via Angel One.
        Returns {"orderid": "...", "status": True/False, "message": "..."}.
        Raises RuntimeError if not connected.
        """
        if not self.is_connected():
            raise RuntimeError("Not connected to Angel One. Please login first.")

        tok       = token or get_token(symbol)
        ordertype = "MARKET" if price == 0 else "LIMIT"

        params = {
            "variety":         "NORMAL",
            "tradingsymbol":   symbol.upper(),
            "symboltoken":     tok,
            "transactiontype": direction.upper(),
            "exchange":        exchange.upper(),
            "ordertype":       ordertype,
            "producttype":     product_type,
            "duration":        "DAY",
            "price":           str(price) if price > 0 else "0",
            "squareoff":       str(target)    if target    else "0",
            "stoploss":        str(stop_loss) if stop_loss else "0",
            "quantity":        str(quantity),
        }

        with self._lock:
            resp = self._obj.placeOrder(params)

        if resp and resp.get("status"):
            return {"status": True, "orderid": resp.get("data", ""), "message": "Order placed"}
        else:
            msg = resp.get("message", "Order placement failed") if resp else "No response"
            return {"status": False, "orderid": "", "message": msg}

    def cancel_order(self, order_id: str, variety: str = "NORMAL") -> bool:
        """Cancel a pending order. Returns True on success."""
        if not self.is_connected():
            return False
        try:
            with self._lock:
                resp = self._obj.cancelOrder(order_id, variety)
            return bool(resp and resp.get("status"))
        except Exception:
            return False

    def get_order_book(self) -> List[Dict]:
        """Fetch today's order book."""
        if not self.is_connected():
            return []
        try:
            with self._lock:
                resp = self._obj.orderBook()
            return resp.get("data") or [] if resp and resp.get("status") else []
        except Exception:
            return []

    # ── Watchlist helpers ─────────────────────────────────────────────────
    def refresh_watchlist(self, symbols: List[str], exchange: str = "NSE") -> Dict[str, float]:
        """
        Bulk fetch LTPs for a list of symbols.
        Returns {symbol: ltp} dict. Missing symbols get None.
        """
        result = {}
        for sym in symbols:
            ltp = self.get_ltp(exchange, sym)
            result[sym] = ltp
            time.sleep(0.05)   # gentle rate limit
        return result
