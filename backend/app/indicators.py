"""
Technical Indicators Module
Heikin-Ashi, RSI, EMA, ATR, VWAP calculations

FIXES:
- HA first candle open = (open + close) / 2 (matches TradingView)
- RSI uses Wilder's smoothing (alpha=1/period) to match TradingView
- ATR uses Wilder's smoothing to match TradingView
- VWAP resets daily
"""
import pandas as pd
import numpy as np
from typing import Optional


def calculate_heikin_ashi(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate Heikin-Ashi candles from OHLCV data.
    Matches TradingView's HA calculation.
    
    Args:
        df: DataFrame with 'open', 'high', 'low', 'close' columns
        
    Returns:
        DataFrame with HA_open, HA_high, HA_low, HA_close columns added
    """
    ha_df = df.copy()
    
    # HA Close = (Open + High + Low + Close) / 4
    ha_df['HA_close'] = (df['open'] + df['high'] + df['low'] + df['close']) / 4
    
    # HA Open: first candle = (open + close) / 2, then (prev_HA_open + prev_HA_close) / 2
    ha_df['HA_open'] = 0.0
    ha_df.iloc[0, ha_df.columns.get_loc('HA_open')] = (df.iloc[0]['open'] + df.iloc[0]['close']) / 2
    
    for i in range(1, len(ha_df)):
        ha_df.iloc[i, ha_df.columns.get_loc('HA_open')] = (
            ha_df.iloc[i-1]['HA_open'] + ha_df.iloc[i-1]['HA_close']
        ) / 2
    
    # HA High = max(High, HA_Open, HA_Close)
    ha_df['HA_high'] = ha_df[['high', 'HA_open', 'HA_close']].max(axis=1)
    
    # HA Low = min(Low, HA_Open, HA_Close)
    ha_df['HA_low'] = ha_df[['low', 'HA_open', 'HA_close']].min(axis=1)
    
    return ha_df


def get_ha_trend(df: pd.DataFrame) -> str:
    """
    Get current Heikin-Ashi trend state.
    
    Returns:
        'bullish' if HA_close > HA_open, 'bearish' otherwise
    """
    if len(df) == 0:
        return 'neutral'
    
    last = df.iloc[-1]
    if 'HA_close' not in df.columns:
        df = calculate_heikin_ashi(df)
        last = df.iloc[-1]
    
    return 'bullish' if last['HA_close'] > last['HA_open'] else 'bearish'


def detect_ha_flip(df: pd.DataFrame) -> Optional[str]:
    """
    Detect if a Heikin-Ashi trend flip occurred.
    Compares the last two candles in the DataFrame.
    
    Returns:
        'bullish' if flipped to bullish, 'bearish' if flipped to bearish, None if no flip
    """
    if len(df) < 2:
        return None
    
    if 'HA_close' not in df.columns:
        df = calculate_heikin_ashi(df)
    
    prev = df.iloc[-2]
    curr = df.iloc[-1]
    
    prev_bullish = prev['HA_close'] > prev['HA_open']
    curr_bullish = curr['HA_close'] > curr['HA_open']
    
    if not prev_bullish and curr_bullish:
        return 'bullish'
    elif prev_bullish and not curr_bullish:
        return 'bearish'
    
    return None


def calculate_rsi(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Calculate RSI using Wilder's smoothing (matches TradingView)."""
    delta = df['close'].diff()
    
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    
    # Wilder's smoothing: alpha = 1/period
    avg_gain = gain.ewm(alpha=1/period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, adjust=False).mean()
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    
    return rsi


def calculate_ema(df: pd.DataFrame, period: int = 20) -> pd.Series:
    """Calculate Exponential Moving Average."""
    return df['close'].ewm(span=period, adjust=False).mean()


def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Calculate Average True Range using Wilder's smoothing (matches TradingView)."""
    high = df['high']
    low = df['low']
    close = df['close']
    
    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))
    
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    # Wilder's smoothing: alpha = 1/period
    atr = tr.ewm(alpha=1/period, adjust=False).mean()
    
    return atr


def calculate_vwap(df: pd.DataFrame) -> pd.Series:
    """
    Calculate Volume Weighted Average Price.
    Resets daily based on timestamp column.
    """
    typical_price = (df['high'] + df['low'] + df['close']) / 3
    
    # Try to reset VWAP daily
    if 'timestamp' in df.columns:
        try:
            ts = pd.to_datetime(df['timestamp'])
            day = ts.dt.date
            
            tp_vol = typical_price * df['volume']
            cum_tp_vol = tp_vol.groupby(day).cumsum()
            cum_vol = df['volume'].groupby(day).cumsum()
            
            vwap = cum_tp_vol / cum_vol
            return vwap
        except Exception:
            pass
    
    # Fallback: cumulative (no daily reset)
    vwap = (typical_price * df['volume']).cumsum() / df['volume'].cumsum()
    return vwap


def calculate_volume_avg(df: pd.DataFrame, period: int = 20) -> pd.Series:
    """Calculate average volume over period."""
    return df['volume'].rolling(window=period, min_periods=1).mean()


def add_all_indicators(df: pd.DataFrame, 
                       rsi_period: int = 14,
                       ema_period: int = 20,
                       atr_period: int = 14) -> pd.DataFrame:
    """
    Add all indicators to DataFrame.
    """
    result = calculate_heikin_ashi(df)
    result['RSI'] = calculate_rsi(df, rsi_period)
    result['EMA'] = calculate_ema(df, ema_period)
    result['ATR'] = calculate_atr(df, atr_period)
    result['ATR_SMA'] = result['ATR'].rolling(window=20, min_periods=1).mean()
    result['VWAP'] = calculate_vwap(df)
    result['volume_avg'] = calculate_volume_avg(df)
    
    return result
