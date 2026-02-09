"""
Live Trader
Executes real trades on Bybit using the BASE strategy
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Set
import threading

from .bybit_client import get_client, BybitClient
from .strategy import Signal
from .config import LEVERAGE, DATA_DIR
from .activity_logger import logger


# Track last known HA state per symbol to detect NEW flips only
FLIP_STATE_FILE = DATA_DIR / "live_flip_state.json"


class LiveTrader:
    """Executes live trades on Bybit."""
    
    def __init__(self, 
                 trade_size_usd: float = 10.0,
                 max_positions: int = 8,
                 leverage: int = LEVERAGE):
        self.client = get_client()
        self.trade_size_usd = trade_size_usd
        self.max_positions = max_positions
        self.leverage = leverage
        self.enabled = False
        self._lock = threading.Lock()
        
        # Track positions we've opened
        self.positions: Dict[str, dict] = {}
        
        # Load last known HA states (to only trade NEW flips)
        self.ha_states: Dict[str, str] = self._load_flip_states()
        
        print(f"🔴 LiveTrader initialized | Size: ${trade_size_usd} | Max: {max_positions} | Leverage: {leverage}x")
    
    def _load_flip_states(self) -> Dict[str, str]:
        """Load last known HA states from file."""
        if FLIP_STATE_FILE.exists():
            try:
                with open(FLIP_STATE_FILE, 'r') as f:
                    return json.load(f)
            except:
                pass
        return {}
    
    def _save_flip_states(self):
        """Save current HA states to file."""
        try:
            with open(FLIP_STATE_FILE, 'w') as f:
                json.dump(self.ha_states, f)
        except Exception as e:
            print(f"⚠️ Failed to save flip states: {e}")
    
    def start(self):
        """Enable live trading."""
        self.enabled = True
        logger.live_started()
        print("🟢 LIVE TRADING ENABLED")
    
    def stop(self):
        """Disable live trading."""
        self.enabled = False
        logger.live_stopped()
        print("🔴 LIVE TRADING DISABLED")
    
    def is_new_flip(self, symbol: str, current_state: str) -> bool:
        """
        Check if this is a NEW flip (not the current state when we started).
        
        On first run, we record the current state but DON'T trade.
        Only trade when state CHANGES from recorded state.
        """
        prev_state = self.ha_states.get(symbol)
        
        if prev_state is None:
            # First time seeing this symbol - record state, don't trade
            self.ha_states[symbol] = current_state
            self._save_flip_states()
            logger.flip_recorded(symbol, current_state)
            print(f"📝 Recorded initial state for {symbol}: {current_state} (will trade on NEXT flip)")
            return False
        
        if prev_state != current_state:
            # State changed! This is a new flip
            self.ha_states[symbol] = current_state
            self._save_flip_states()
            return True
        
        return False
    
    def get_open_position_count(self) -> int:
        """Get number of open positions from Bybit."""
        positions = self.client.get_positions()
        return len(positions)
    
    def can_open_position(self) -> bool:
        """Check if we can open a new position."""
        count = self.get_open_position_count()
        return count < self.max_positions
    
    def execute_signal(self, signal: Signal, ha_state: str) -> Optional[str]:
        """
        Execute a live trade signal.
        
        Args:
            signal: Trading signal from strategy
            ha_state: Current HA state ("bullish" or "bearish")
            
        Returns:
            Order ID if successful, None otherwise
        """
        if not self.enabled:
            return None
        
        with self._lock:
            # Check if this is a NEW flip
            if not self.is_new_flip(signal.symbol, ha_state):
                return None
            
            # Check position limit
            if not self.can_open_position():
                print(f"⚠️ Max positions ({self.max_positions}) reached, skipping {signal.symbol}")
                return None
            
            # Check if already in position for this symbol
            positions = self.client.get_positions(signal.symbol)
            if positions:
                print(f"⚠️ Already have position in {signal.symbol}, skipping")
                return None
            
            # Set leverage
            if not self.client.set_leverage(signal.symbol, self.leverage):
                print(f"⚠️ Failed to set leverage for {signal.symbol}")
                # Continue anyway, leverage might already be set
            
            # Calculate quantity
            qty = self.client.calculate_qty(signal.symbol, self.trade_size_usd, self.leverage)
            if not qty:
                print(f"❌ Failed to calculate qty for {signal.symbol}")
                return None
            
            # Place market order
            side = "Buy" if signal.direction == "LONG" else "Sell"
            order_id = self.client.place_market_order(signal.symbol, side, qty)
            
            if not order_id:
                print(f"❌ Failed to place order for {signal.symbol}")
                return None
            
            # Set initial stop loss (just the SL for now, we manage TPs ourselves)
            self.client.set_trading_stop(
                signal.symbol, 
                side,
                stop_loss=signal.stop_loss
            )
            
            # Track position locally
            self.positions[signal.symbol] = {
                "order_id": order_id,
                "symbol": signal.symbol,
                "side": signal.direction,
                "entry_price": signal.entry_price,
                "stop_loss": signal.stop_loss,
                "current_sl": signal.stop_loss,
                "entry_time": datetime.now(timezone.utc).isoformat(),
                "take_profits": [
                    signal.take_profit_1, signal.take_profit_2, signal.take_profit_3,
                    signal.take_profit_4, signal.take_profit_5, signal.take_profit_6,
                    signal.take_profit_7, signal.take_profit_8, signal.take_profit_9,
                    signal.take_profit_10
                ],
                "tp_hit": [False] * 10
            }
            
            # Log the trade
            logger.trade_opened(signal.symbol, signal.direction, signal.entry_price, qty)
            logger.sl_set(signal.symbol, signal.stop_loss)
            logger.tp_set(signal.symbol, {
                1: signal.take_profit_1, 2: signal.take_profit_2, 3: signal.take_profit_3,
                4: signal.take_profit_4, 5: signal.take_profit_5, 6: signal.take_profit_6,
                7: signal.take_profit_7, 8: signal.take_profit_8, 9: signal.take_profit_9,
                10: signal.take_profit_10
            })
            
            print(f"🔴 LIVE TRADE: {signal.direction} {signal.symbol} | Qty: {qty} | Entry: {signal.entry_price:.4f}")
            print(f"   SL: {signal.stop_loss:.4f} | TP10: {signal.take_profit_10:.4f}")
            
            return order_id
    
    def update_positions(self):
        """
        Update all positions - check TPs and adjust trailing SL.
        Called periodically from main loop.
        """
        if not self.enabled:
            return
        
        bybit_positions = self.client.get_positions()
        
        for pos in bybit_positions:
            symbol = pos["symbol"]
            
            if symbol not in self.positions:
                continue
            
            local_pos = self.positions[symbol]
            current_price = float(pos.get("markPrice", 0))
            
            if current_price <= 0:
                continue
            
            is_long = local_pos["side"] == "LONG"
            tps = local_pos["take_profits"]
            tp_hit = local_pos["tp_hit"]
            
            # Check TPs from highest to lowest
            for i in range(9, -1, -1):  # 9 to 0 (TP10 to TP1)
                if tp_hit[i]:
                    continue
                
                tp_price = tps[i]
                hit = (is_long and current_price >= tp_price) or (not is_long and current_price <= tp_price)
                
                if hit:
                    tp_hit[i] = True
                    tp_num = i + 1
                    
                    if tp_num == 10:
                        # TP10 - Close position
                        pnl = ((current_price - local_pos["entry_price"]) / local_pos["entry_price"]) * 100 * self.leverage
                        if not is_long:
                            pnl = -pnl
                        logger.tp10_close(symbol, current_price, pnl)
                        print(f"🎯🎯 TP10 HIT! Closing {symbol} @ {current_price:.4f}")
                        self.client.close_position(symbol, local_pos["side"])
                        del self.positions[symbol]
                        return
                    else:
                        # Update trailing SL to previous TP
                        old_sl = local_pos["current_sl"]
                        new_sl = tps[i - 1] if i > 0 else local_pos["entry_price"]
                        local_pos["current_sl"] = new_sl
                        
                        # Log the TP hit and SL update
                        logger.tp_hit(symbol, tp_num, tp_price, new_sl)
                        logger.sl_updated(symbol, old_sl, new_sl, f"TP{tp_num} hit")
                        
                        # Update on Bybit
                        self.client.set_trading_stop(
                            symbol,
                            "Buy" if is_long else "Sell",
                            stop_loss=new_sl
                        )
                        
                        print(f"🎯 TP{tp_num} hit on {symbol} | SL moved to {new_sl:.4f}")
                    
                    break
    
    def close_all_positions(self):
        """Emergency close all positions."""
        print("🚨 EMERGENCY: Closing all positions...")
        
        positions = self.client.get_positions()
        count = len(positions)
        for pos in positions:
            symbol = pos["symbol"]
            side = "LONG" if pos["side"] == "Buy" else "SHORT"
            self.client.close_position(symbol, side)
        
        self.positions.clear()
        logger.emergency_close(count)
        print("✅ All positions closed")
    
    def get_status(self) -> dict:
        """Get live trading status."""
        return {
            "enabled": self.enabled,
            "trade_size_usd": self.trade_size_usd,
            "max_positions": self.max_positions,
            "leverage": self.leverage,
            "open_positions": self.get_open_position_count(),
            "tracked_symbols": list(self.positions.keys()),
            "recorded_states": len(self.ha_states)
        }


# Singleton instance
_live_trader: Optional[LiveTrader] = None


def get_live_trader(trade_size_usd: float = 10.0, 
                    max_positions: int = 8) -> LiveTrader:
    """Get or create LiveTrader instance."""
    global _live_trader
    if _live_trader is None:
        _live_trader = LiveTrader(trade_size_usd=trade_size_usd, max_positions=max_positions)
    return _live_trader
