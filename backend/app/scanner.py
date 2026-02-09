"""
Bybit Data Scanner
Fetches OHLCV data for top 60 futures coins
"""
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional
import httpx
import pandas as pd
from pybit.unified_trading import HTTP

from .config import (
    BYBIT_API_KEY, BYBIT_API_SECRET, BYBIT_TESTNET,
    CANDLES_DIR, TOP_COINS_COUNT, TIMEFRAMES
)


class BybitScanner:
    """Fetches and manages OHLCV data from Bybit."""
    
    def __init__(self):
        self.session = HTTP(
            testnet=BYBIT_TESTNET,
            api_key=BYBIT_API_KEY,
            api_secret=BYBIT_API_SECRET,
        )
        self._top_symbols: List[str] = []
        self._last_refresh = None
    
    def get_top_futures_symbols(self, limit: int = TOP_COINS_COUNT) -> List[str]:
        """
        Get top futures symbols by 24h volume.
        Caches for 1 hour to avoid rate limits.
        """
        now = datetime.now(timezone.utc)
        if self._top_symbols and self._last_refresh:
            elapsed = (now - self._last_refresh).total_seconds()
            if elapsed < 3600:  # Cache for 1 hour
                return self._top_symbols[:limit]
        
        try:
            # Get all USDT perpetual tickers
            response = self.session.get_tickers(category="linear")
            
            if response['retCode'] != 0:
                print(f"Error fetching tickers: {response['retMsg']}")
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
            
            return self._top_symbols[:limit]
            
        except Exception as e:
            print(f"Error getting top symbols: {e}")
            return self._top_symbols[:limit] if self._top_symbols else []
    
    def fetch_klines(self, 
                     symbol: str, 
                     interval: str = "5", 
                     limit: int = 200) -> pd.DataFrame:
        """
        Fetch kline/candlestick data for a symbol.
        
        Args:
            symbol: Trading pair (e.g., BTCUSDT)
            interval: Timeframe (1, 3, 5, 15, 30, 60, 120, 240, 360, 720, D, W, M)
            limit: Number of candles (max 200)
            
        Returns:
            DataFrame with columns: timestamp, open, high, low, close, volume
        """
        try:
            response = self.session.get_kline(
                category="linear",
                symbol=symbol,
                interval=interval,
                limit=limit
            )
            
            if response['retCode'] != 0:
                print(f"Error fetching klines for {symbol}: {response['retMsg']}")
                return pd.DataFrame()
            
            klines = response['result']['list']
            
            if not klines:
                return pd.DataFrame()
            
            # Bybit returns newest first, reverse it
            klines = list(reversed(klines))
            
            df = pd.DataFrame(klines, columns=[
                'timestamp', 'open', 'high', 'low', 'close', 'volume', 'turnover'
            ])
            
            # Convert types safely (Windows compatible)
            df['timestamp'] = pd.to_datetime(
                df['timestamp'].astype('int64'), 
                unit='ms', 
                utc=True
            )
            for col in ['open', 'high', 'low', 'close', 'volume', 'turnover']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            
            return df
            
        except Exception as e:
            print(f"Error fetching klines for {symbol}: {e}")
            return pd.DataFrame()
    
    def fetch_multi_timeframe(self, 
                               symbol: str, 
                               timeframes: List[str] = ["5", "15", "60", "240"]) -> Dict[str, pd.DataFrame]:
        """
        Fetch klines for multiple timeframes.
        
        Returns:
            Dict mapping timeframe to DataFrame
        """
        result = {}
        for tf in timeframes:
            result[tf] = self.fetch_klines(symbol, interval=tf)
        return result
    
    def save_candles(self, symbol: str, timeframe: str, df: pd.DataFrame):
        """Save candles to JSON file."""
        if df.empty:
            return
        
        filepath = CANDLES_DIR / f"{symbol}_{timeframe}.json"
        
        # Convert to serializable format
        data = {
            "symbol": symbol,
            "timeframe": timeframe,
            "updated_at": datetime.now(timezone.utc).isoformat(),
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
        """
        Scan all top symbols and fetch candles for specified timeframes.
        
        Returns:
            Dict[symbol, Dict[timeframe, DataFrame]]
        """
        symbols = self.get_top_futures_symbols()
        result = {}
        
        for symbol in symbols:
            result[symbol] = self.fetch_multi_timeframe(symbol, timeframes)
            
            # Save to disk
            for tf, df in result[symbol].items():
                self.save_candles(symbol, tf, df)
        
        return result


# Singleton instance
scanner = BybitScanner()
