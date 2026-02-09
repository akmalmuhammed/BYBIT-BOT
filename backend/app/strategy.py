"""
Strategy Engine
Base strategy class and all variations for 4H HA flip strategy
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple
import pandas as pd

from .indicators import (
    calculate_heikin_ashi, detect_ha_flip, get_ha_trend,
    calculate_rsi, calculate_ema, calculate_atr, calculate_vwap,
    add_all_indicators
)
from .config import DEFAULT_SL_PERCENT, ATR_PERIOD, RSI_PERIOD, EMA_PERIOD


@dataclass
class Signal:
    """Trading signal from strategy."""
    symbol: str
    direction: Optional[str]  # "LONG", "SHORT", or None
    entry_price: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    take_profit_3: float
    take_profit_4: float
    take_profit_5: float
    take_profit_6: float
    take_profit_7: float
    take_profit_8: float
    take_profit_9: float
    take_profit_10: float
    strategy_id: str
    timestamp: str
    confidence: float = 1.0
    reason: str = ""


class BaseStrategy(ABC):
    """
    Base class for all strategy variations.
    Override the `check_entry_filters` method to add custom filters.
    """
    
    def __init__(self, 
                 strategy_id: str,
                 cooldown_minutes: int = 60,
                 sl_percent: float = DEFAULT_SL_PERCENT,
                 atr_timeframe: str = "5",
                 atr_multipliers: Tuple[float, ...] = (1.5, 2.5, 4.0, 5.5, 7.0, 9.0, 11.0, 13.5, 16.0, 19.0)):
        self.strategy_id = strategy_id
        self.cooldown_minutes = cooldown_minutes
        self.sl_percent = sl_percent
        self.atr_timeframe = atr_timeframe
        self.atr_multipliers = atr_multipliers
        
        # Track last entry time per symbol for cooldown
        self._last_entry: Dict[str, datetime] = {}
        
        # Track previous HA state per symbol for flip detection
        self._prev_ha_state: Dict[str, str] = {}
    
    def is_in_cooldown(self, symbol: str) -> bool:
        """Check if symbol is in cooldown period."""
        if symbol not in self._last_entry:
            return False
        
        elapsed = datetime.now(timezone.utc) - self._last_entry[symbol]
        return elapsed.total_seconds() < (self.cooldown_minutes * 60)
    
    def set_entry_time(self, symbol: str):
        """Mark entry time for cooldown tracking."""
        self._last_entry[symbol] = datetime.now(timezone.utc)
    
    def detect_flip(self, symbol: str, df_4h: pd.DataFrame) -> Optional[str]:
        """
        Detect 4H Heikin-Ashi flip.
        
        Returns:
            'bullish', 'bearish', or None
        """
        if len(df_4h) < 2:
            return None
        
        df_ha = calculate_heikin_ashi(df_4h)
        
        prev = df_ha.iloc[-2]
        curr = df_ha.iloc[-1]
        
        prev_bullish = prev['HA_close'] > prev['HA_open']
        curr_bullish = curr['HA_close'] > curr['HA_open']
        
        # Store current state
        current_state = 'bullish' if curr_bullish else 'bearish'
        prev_stored = self._prev_ha_state.get(symbol)
        self._prev_ha_state[symbol] = current_state
        
        # Detect flip
        if prev_stored is None:
            return None  # First candle, no flip possible
        
        if prev_stored == 'bearish' and current_state == 'bullish':
            return 'bullish'
        elif prev_stored == 'bullish' and current_state == 'bearish':
            return 'bearish'
        
        return None
    
    def calculate_targets(self, 
                          entry_price: float, 
                          direction: str, 
                          atr: float) -> Tuple[float, ...]:
        """
        Calculate SL and TP levels (10 take profit levels).
        
        Returns:
            (stop_loss, tp1, tp2, tp3, tp4, tp5, tp6, tp7, tp8, tp9, tp10)
        """
        tps = []
        if direction == "LONG":
            sl = entry_price * (1 - self.sl_percent)
            for mult in self.atr_multipliers:
                tps.append(entry_price + (atr * mult))
        else:  # SHORT
            sl = entry_price * (1 + self.sl_percent)
            for mult in self.atr_multipliers:
                tps.append(entry_price - (atr * mult))
        
        return (sl, *tps)
    
    @abstractmethod
    def check_entry_filters(self, 
                            symbol: str,
                            direction: str,
                            df_5m: pd.DataFrame,
                            df_15m: Optional[pd.DataFrame] = None,
                            df_1h: Optional[pd.DataFrame] = None) -> Tuple[bool, str]:
        """
        Check additional entry filters.
        
        Returns:
            (passes_filter, reason)
        """
        pass
    
    def generate_signal(self,
                        symbol: str,
                        df_4h: pd.DataFrame,
                        df_5m: pd.DataFrame,
                        df_15m: Optional[pd.DataFrame] = None,
                        df_1h: Optional[pd.DataFrame] = None) -> Optional[Signal]:
        """
        Generate trading signal for a symbol.
        
        Args:
            symbol: Trading pair
            df_4h: 4H candles for HA flip detection
            df_5m: 5m candles for execution and indicators
            df_15m: 15m candles (optional, for Var A ATR)
            df_1h: 1H candles (optional, for Var C RSI)
            
        Returns:
            Signal if conditions met, None otherwise
        """
        # Check cooldown
        if self.is_in_cooldown(symbol):
            return None
        
        # Need enough data
        if len(df_4h) < 5 or len(df_5m) < 50:
            return None
        
        # Detect 4H HA flip
        flip = self.detect_flip(symbol, df_4h)
        if not flip:
            return None
        
        direction = "LONG" if flip == "bullish" else "SHORT"
        
        # Add indicators to 5m
        df_5m_ind = add_all_indicators(df_5m)
        
        # Check entry filters
        passes, reason = self.check_entry_filters(
            symbol, direction, df_5m_ind, df_15m, df_1h
        )
        
        if not passes:
            return None
        
        # Get current price and ATR
        current_price = df_5m_ind.iloc[-1]['close']
        
        # Get ATR from appropriate timeframe
        if self.atr_timeframe == "15" and df_15m is not None and len(df_15m) >= ATR_PERIOD:
            atr_df = add_all_indicators(df_15m)
            atr = atr_df.iloc[-1]['ATR']
        else:
            atr = df_5m_ind.iloc[-1]['ATR']
        
        # Calculate targets
        targets = self.calculate_targets(current_price, direction, atr)
        sl = targets[0]
        tps = targets[1:]  # TP1-TP10
        
        return Signal(
            symbol=symbol,
            direction=direction,
            entry_price=current_price,
            stop_loss=sl,
            take_profit_1=tps[0],
            take_profit_2=tps[1],
            take_profit_3=tps[2],
            take_profit_4=tps[3],
            take_profit_5=tps[4],
            take_profit_6=tps[5],
            take_profit_7=tps[6],
            take_profit_8=tps[7],
            take_profit_9=tps[8],
            take_profit_10=tps[9],
            strategy_id=self.strategy_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            reason=f"4H HA flip {flip}. {reason}"
        )


# ============ STRATEGY VARIATIONS ============

class BaseFlipStrategy(BaseStrategy):
    """Base strategy: Just 4H HA flip, no additional filters."""
    
    def __init__(self):
        super().__init__(
            strategy_id="base",
            cooldown_minutes=60,
            atr_timeframe="15"
        )
    
    def check_entry_filters(self, symbol, direction, df_5m, df_15m=None, df_1h=None):
        return True, "No filters"


class VariationA(BaseStrategy):
    """Variation A: 30min cooldown, 15m ATR for targets."""
    
    def __init__(self):
        super().__init__(
            strategy_id="var_a",
            cooldown_minutes=30,
            atr_timeframe="15"
        )
    
    def check_entry_filters(self, symbol, direction, df_5m, df_15m=None, df_1h=None):
        return True, "No filters (15m ATR)"


class VariationB(BaseStrategy):
    """Variation B: RSI + EMA confirmation on 5m."""
    
    def __init__(self):
        super().__init__(
            strategy_id="var_b",
            cooldown_minutes=60,
            atr_timeframe="5"
        )
    
    def check_entry_filters(self, symbol, direction, df_5m, df_15m=None, df_1h=None):
        if len(df_5m) < 2:
            return False, "Not enough data"
        
        last = df_5m.iloc[-1]
        rsi = last.get('RSI', 50)
        ema = last.get('EMA', last['close'])
        price = last['close']
        
        if direction == "LONG":
            if rsi > 50 and price > ema:
                return True, f"RSI={rsi:.1f}>50, Price>{ema:.2f}"
            return False, f"RSI={rsi:.1f}, Price vs EMA failed"
        else:  # SHORT
            if rsi < 50 and price < ema:
                return True, f"RSI={rsi:.1f}<50, Price<{ema:.2f}"
            return False, f"RSI={rsi:.1f}, Price vs EMA failed"


class VariationC(BaseStrategy):
    """Variation C: Advanced multi-confluence."""
    
    def __init__(self):
        super().__init__(
            strategy_id="var_c",
            cooldown_minutes=45,
            atr_timeframe="5"
        )
    
    def check_entry_filters(self, symbol, direction, df_5m, df_15m=None, df_1h=None):
        if len(df_5m) < 20:
            return False, "Not enough 5m data"
        
        last = df_5m.iloc[-1]
        price = last['close']
        rsi_5m = last.get('RSI', 50)
        vwap = last.get('VWAP', price)
        volume = last.get('volume', 0)
        volume_avg = last.get('volume_avg', volume)
        atr = last.get('ATR', 0)
        atr_sma = last.get('ATR_SMA', atr)
        
        # Check 1H RSI if available
        rsi_1h = 50
        if df_1h is not None and len(df_1h) >= RSI_PERIOD:
            df_1h_ind = add_all_indicators(df_1h)
            rsi_1h = df_1h_ind.iloc[-1].get('RSI', 50)
        
        # Volume must be above 1.5x average
        volume_ok = volume > (volume_avg * 1.5)
        
        # ATR must be expanding
        atr_expanding = atr > atr_sma
        
        reasons = []
        
        if direction == "LONG":
            # 1H RSI > 50
            if rsi_1h <= 50:
                return False, f"1H RSI={rsi_1h:.1f} <= 50"
            reasons.append(f"1H RSI={rsi_1h:.1f}>50")
            
            # Price > VWAP
            if price <= vwap:
                return False, f"Price <= VWAP"
            reasons.append("Price>VWAP")
            
            # Volume filter
            if not volume_ok:
                return False, f"Volume too low"
            reasons.append("Vol>1.5x avg")
            
            # ATR expanding
            if not atr_expanding:
                return False, f"ATR not expanding"
            reasons.append("ATR expanding")
            
            return True, ", ".join(reasons)
            
        else:  # SHORT
            if rsi_1h >= 50:
                return False, f"1H RSI={rsi_1h:.1f} >= 50"
            reasons.append(f"1H RSI={rsi_1h:.1f}<50")
            
            if price >= vwap:
                return False, f"Price >= VWAP"
            reasons.append("Price<VWAP")
            
            if not volume_ok:
                return False, f"Volume too low"
            reasons.append("Vol>1.5x avg")
            
            if not atr_expanding:
                return False, f"ATR not expanding"
            reasons.append("ATR expanding")
            
            return True, ", ".join(reasons)


# ============ STRATEGY REGISTRY ============

# Extensible registry for adding more variations
STRATEGIES: Dict[str, BaseStrategy] = {
    "base": BaseFlipStrategy(),
    "var_a": VariationA(),
    "var_b": VariationB(),
    "var_c": VariationC(),
}


def register_strategy(strategy: BaseStrategy):
    """Register a new strategy variation."""
    STRATEGIES[strategy.strategy_id] = strategy


def get_strategy(strategy_id: str) -> Optional[BaseStrategy]:
    """Get strategy by ID."""
    return STRATEGIES.get(strategy_id)


def get_all_strategies() -> List[BaseStrategy]:
    """Get all registered strategies."""
    return list(STRATEGIES.values())
