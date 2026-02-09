"""
Configuration for Paper Trading System

FIXES:
- BYBIT_TESTNET defaults to false (was true, causing data mismatch)
"""
import os
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

"""
Configuration for Paper Trading System

FIXES:
- BYBIT_TESTNET defaults to false (was true, causing data mismatch)
"""
import os
from dotenv import load_dotenv
from pathlib import Path
from datetime import timezone, timedelta, datetime

load_dotenv()

# Bybit API
BYBIT_API_KEY = os.getenv("BYBIT_API_KEY", "")
BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET", "")
# IMPORTANT: Set to "false" for mainnet data. "true" uses testnet which has different prices!
BYBIT_TESTNET = os.getenv("BYBIT_TESTNET", "false").lower() == "true"

# Timezone Configuration (UTC+3)
TIMEZONE = timezone(timedelta(hours=3))

def get_current_time() -> datetime:
    """Get current time in project timezone."""
    return datetime.now(TIMEZONE)

# Data paths
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
CANDLES_DIR = DATA_DIR / "candles"
TRADES_DIR = DATA_DIR / "trades"
POSITIONS_DIR = DATA_DIR / "positions"

# Ensure directories exist
for d in [CANDLES_DIR, TRADES_DIR, POSITIONS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# Trading settings
TOP_COINS_COUNT = 15  # Top 15 trending by volume
SCAN_INTERVAL_MINUTES = 5

# Timeframes
TIMEFRAMES = {
    "5m": "5",
    "15m": "15",
    "1h": "60",
    "4h": "240",
}

# Strategy defaults
DEFAULT_SL_PERCENT = 0.025  # 2.5%
DEFAULT_COOLDOWN_MINUTES = 60
ATR_PERIOD = 14
RSI_PERIOD = 14
EMA_PERIOD = 20
VWAP_ENABLED = True

# Money Management
STARTING_CAPITAL = 1000.0  # $1000 total
TRADE_SIZE = 100.0         # $100 per trade
MAX_CONCURRENT_TRADES = 10 # Max 10 open trades per strategy
LEVERAGE = 8               # 8x leverage
COMPOUNDING = True         # Reinvest profits/losses

# Live Trading Settings
LIVE_TRADING_ENABLED = False       # Safety switch - must be enabled explicitly
LIVE_TRADE_SIZE_USD = 10.0         # $10 per trade for live
LIVE_MAX_POSITIONS = 8             # Max 8 concurrent live positions
LIVE_STRATEGY = "base"             # Only use BASE strategy for live
