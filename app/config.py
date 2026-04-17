"""
TradeMind AI — Application Configuration
All constants, paths, and runtime settings live here.
"""
import os
from pathlib import Path

# ─── App Identity ────────────────────────────────────────────────────────────
APP_NAME = "TradeMind AI"
APP_VERSION = "1.0.0"
APP_ORG = "TradeMind"

# ─── Paths ───────────────────────────────────────────────────────────────────
# Everything stored in user's AppData so the .exe installer has write access
APP_DATA_DIR = Path(os.getenv("APPDATA", "~")) / "TradeMind-AI"
DB_PATH      = APP_DATA_DIR / "trademind.db"
LOG_DIR      = APP_DATA_DIR / "logs"
CACHE_DIR    = APP_DATA_DIR / "cache"

# User-configurable model path (saved in settings; this is the default)
DEFAULT_LLAMA_MODEL_PATH = Path.home() / "llama.cpp" / "models"

# ─── UI Theme Colors (Bloomberg Dark) ────────────────────────────────────────
COLOR_BG           = "#1a1d23"
COLOR_CARD         = "#252830"
COLOR_SIDEBAR      = "#13151a"
COLOR_BORDER       = "#2d3139"
COLOR_TEXT         = "#e8eaed"
COLOR_TEXT_MUTED   = "#8b949e"
COLOR_ACCENT       = "#3b82f6"
COLOR_SUCCESS      = "#10b981"
COLOR_DANGER       = "#ef4444"
COLOR_WARNING      = "#f59e0b"
COLOR_PURPLE       = "#8b5cf6"
COLOR_CYAN         = "#06b6d4"

# ─── Trading Defaults ────────────────────────────────────────────────────────
DEFAULT_CAPITAL         = 15_000          # INR
MAX_RISK_PER_TRADE_PCT  = 2.0             # % of capital risked per trade
MAX_DAILY_LOSS_PCT      = 5.0             # Halt trading if daily loss exceeds this %
MAX_OPEN_POSITIONS      = 3
BROKERAGE_PCT           = 0.03           # 0.03% per leg (Angel One typical)

# ─── Angel One API ───────────────────────────────────────────────────────────
ANGEL_ONE_BASE_URL = "https://apiconnect.angelbroking.com"
ANGEL_ONE_WS_URL   = "wss://smartapisocket.angelone.in/smart/websocket"
MARKET_OPEN_TIME   = "09:15"
MARKET_CLOSE_TIME  = "15:30"
EXCHANGE_NSE       = "NSE"
EXCHANGE_BSE       = "BSE"

# ─── AI Settings ─────────────────────────────────────────────────────────────
AI_MAX_TOKENS     = 512
AI_TEMPERATURE    = 0.7
AI_CONTEXT_SIZE   = 4096
AI_THREADS        = 4          # CPU threads for llama inference

# ─── Chart Settings ──────────────────────────────────────────────────────────
CHART_UPDATE_INTERVAL_MS = 1000          # Live chart refresh rate
CHART_HISTORY_CANDLES    = 200

# ─── Create directories on import ────────────────────────────────────────────
for _d in (APP_DATA_DIR, LOG_DIR, CACHE_DIR):
    _d.mkdir(parents=True, exist_ok=True)
