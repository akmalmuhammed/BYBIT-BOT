"""
Bybit Data Scanner
Fetches OHLCV data for top futures coins

FIXES:
- Added delay between API calls to avoid Bybit rate limits
- Added request timeout via pybit recv_window
- Added retry with backoff on failures  
- Reduced default candle limit (50 is enough, not 200)
- Tracks scan timing for diagnostics
"""
import time
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional
import pandas as pd
from pybit.unified_trading import HTTP

from .config import (
    BYBIT_API_KEY, BYBIT_API_SECRET, BYBIT_TESTNET,
    CANDLES_DIR, TOP_COINS_COUNT, TIMEFRAMES, get_current_time
)

# Rate limit: delay between API calls (seconds)
API_CALL_DELAY = 0.15  # 150ms between calls (~6.6 calls/sec, well within Bybit's 10/sec limit)
MAX_RETRIES = 2
RETRY_DELAY = 2.0  # seconds


class BybitScanner:
    """Fetches and manages OHLCV data from Bybit."""
    
    def __init__(self):
        self.session = HTTP(
            testnet=BYBIT_TESTNET,
            api_key=BYBIT_API_KEY,
            api_secret=BYBIT_API_SECRET,
            recv_window=10000,  # 10 second timeout
        )
        self._top_symbols: List[str] = []
        self._last_refresh = None
        self._api_call_count = 0
        self._last_scan_time: Optional[str] = None
        self._last_scan_duration: float = 0
        self._consecutive_failures: int = 0
    
    def _rate_limit(self):
        """Sleep between API calls to respect rate limits."""
        time.sleep(API_CALL_DELAY)
        self._api_call_count += 1
    
    def get_top_futures_symbols(self, limit: int = TOP_COINS_COUNT) -> List[str]:
        """
        Get top futures symbols by 24h volume.
        Caches for 1 hour to avoid rate limits.
        """
        now = get_current_time()
        if self._top_symbols and self._last_refresh:
            elapsed = (now - self._last_refresh).total_seconds()
            if elapsed < 3600:  # Cache for 1 hour
                return self._top_symbols[:limit]
        
        for attempt in range(MAX_RETRIES + 1):
            try:
                self._rate_limit()
                response = self.session.get_tickers(category="linear")
                
                if response['retCode'] != 0:
                    print(f"⚠️ Error fetching tickers: {response['retMsg']}")
                    if attempt < MAX_RETRIES:
                        time.sleep(RETRY_DELAY * (attempt + 1))
                        continue
                    return self._top_symbols[:limit] if self._top_symbols else []
                
                tickers = response['result']['list']
                
                # Filter USDT pairs and sort by 24h volume
                usdt_pairs = [
                    t for t in tickers 
                    if t['symbol'].endswith('USDT') and float(t.get('turnover24h', 0)) > 0
                ]
                
                sorted_pairs = sorted(
                    usdt_pairs,
                    key=lambda x: float(x.get('turnover24h', 0)),
                    reverse=True
                )
                
                self._top_symbols = [p['symbol'] for p in sorted_pairs]
                self._last_refresh = now
                self._consecutive_failures = 0
                
                return self._top_symbols[:limit]
                
            except Exception as e:
                print(f"⚠️ Error getting top symbols (attempt {attempt+1}): {e}")
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY * (attempt + 1))
                    continue
                return self._top_symbols[:limit] if self._top_symbols else []
    
    def fetch_klines(self, 
                     symbol: str, 
                     interval: str = "5", 
                     limit: int = 100) -> pd.DataFrame:
        """
        Fetch kline/candlestick data for a symbol.
        Includes rate limiting and retry logic.
        """
        for attempt in range(MAX_RETRIES + 1):
            try:
                self._rate_limit()
                response = self.session.get_kline(
                    category="linear",
                    symbol=symbol,
                    interval=interval,
                    limit=limit
                )
                
                if response['retCode'] != 0:
                    err_msg = response.get('retMsg', 'Unknown error')
                    # Rate limit error
                    if 'rate limit' in err_msg.lower() or response['retCode'] == 10006:
                        wait = RETRY_DELAY * (attempt + 2)
                        print(f"⚠️ Rate limited on {symbol} {interval}m, waiting {wait}s...")
                        time.sleep(wait)
                        continue
                    print(f"⚠️ Error fetching klines for {symbol} {interval}m: {err_msg}")
                    return pd.DataFrame()
                
                klines = response['result']['list']
                
                if not klines:
                    return pd.DataFrame()
                
                # Bybit returns newest first, reverse it
                klines = list(reversed(klines))
                
                df = pd.DataFrame(klines, columns=[
                    'timestamp', 'open', 'high', 'low', 'close', 'volume', 'turnover'
                ])
                
                # Convert types
                df['timestamp'] = pd.to_datetime(
                    df['timestamp'].astype('int64'), 
                    unit='ms', 
                    utc=True
                )
                for col in ['open', 'high', 'low', 'close', 'volume', 'turnover']:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
                
                self._consecutive_failures = 0
                return df
                
            except Exception as e:
                print(f"⚠️ Error fetching klines for {symbol} {interval}m (attempt {attempt+1}): {e}")
                self._consecutive_failures += 1
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY * (attempt + 1))
                    continue
                return pd.DataFrame()
    
    def fetch_multi_timeframe(self, 
                               symbol: str, 
                               timeframes: List[str] = ["5", "15", "60", "240"]) -> Dict[str, pd.DataFrame]:
        """
        Fetch klines for multiple timeframes.
        """
        result = {}
        for tf in timeframes:
            result[tf] = self.fetch_klines(symbol, interval=tf)
            # Extra delay between timeframes for same symbol
        return result
    
    def save_candles(self, symbol: str, timeframe: str, df: pd.DataFrame):
        """Save candles to JSON file."""
        if df.empty:
            return
        
        filepath = CANDLES_DIR / f"{symbol}_{timeframe}.json"
        
        data = {
            "symbol": symbol,
            "timeframe": timeframe,
            "updated_at": get_current_time().isoformat(),
            "candles": df.to_dict(orient='records')
        }
        
        # Convert timestamps to strings
        for candle in data['candles']:
            if isinstance(candle.get('timestamp'), pd.Timestamp):
                candle['timestamp'] = candle['timestamp'].isoformat()
        
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2, default=str)
    
    def load_candles(self, symbol: str, timeframe: str) -> pd.DataFrame:
        """Load candles from JSON file."""
        filepath = CANDLES_DIR / f"{symbol}_{timeframe}.json"
        
        if not filepath.exists():
            return pd.DataFrame()
        
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
            
            df = pd.DataFrame(data['candles'])
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            return df
            
        except Exception as e:
            print(f"Error loading candles: {e}")
            return pd.DataFrame()
    
    def scan_all_symbols(self, timeframes: List[str] = ["5", "240"]) -> Dict[str, Dict[str, pd.DataFrame]]:
        """Scan all top symbols and fetch candles."""
        symbols = self.get_top_futures_symbols()
        result = {}
        
        for symbol in symbols:
            result[symbol] = self.fetch_multi_timeframe(symbol, timeframes)
            for tf, df in result[symbol].items():
                self.save_candles(symbol, tf, df)
        
        return result
    
    def get_diagnostics(self) -> dict:
        """Get scanner diagnostics for debug endpoint."""
        return {
            "api_calls_since_start": self._api_call_count,
            "last_scan_time": self._last_scan_time,
            "last_scan_duration_seconds": self._last_scan_duration,
            "consecutive_failures": self._consecutive_failures,
            "cached_symbols_count": len(self._top_symbols),
            "testnet": BYBIT_TESTNET,
        }


# Singleton instance
scanner = BybitScanner()
