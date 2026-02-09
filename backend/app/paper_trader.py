"""
Paper Trading Engine
Executes and manages paper trades with position tracking
"""
from datetime import datetime, timezone
from typing import Dict, List, Optional
import uuid
import pandas as pd

from .storage import storage, Trade, Position, TradeStatus, Side
from .strategy import Signal, get_all_strategies, BaseStrategy
from .scanner import scanner
from .indicators import add_all_indicators
from .config import LEVERAGE


class PaperTrader:
    """
    Paper trading execution engine.
    Manages positions, executes signals, and tracks PnL.
    """
    
    def __init__(self):
        self.storage = storage
    
    def execute_signal(self, signal: Signal) -> Optional[Trade]:
        """
        Execute a trading signal.
        Opens a new paper position and creates trade record.
        """
        if signal.direction is None:
            return None
        
        # Check if we can open more trades (max 10 per strategy)
        if not self.storage.can_open_trade(signal.strategy_id):
            return None
        
        # Check if we already have a position for this symbol+strategy
        existing = self.get_position(signal.symbol, signal.strategy_id)
        if existing:
            return None  # Already in a trade
        
        # Get trade size from account (with compounding)
        trade_size_usd = self.storage.get_next_trade_size()
        
        # Create trade record
        trade_id = str(uuid.uuid4())[:8]
        now = datetime.now(timezone.utc).isoformat()
        
        trade = Trade(
            id=trade_id,
            symbol=signal.symbol,
            strategy_id=signal.strategy_id,
            side=signal.direction,
            entry_price=signal.entry_price,
            entry_time=now,
            trade_size_usd=trade_size_usd,
            stop_loss=signal.stop_loss,
            take_profit_1=signal.take_profit_1,
            take_profit_2=signal.take_profit_2,
            take_profit_3=signal.take_profit_3,
            current_sl=signal.stop_loss,
            status=TradeStatus.OPEN.value,
            notes=signal.reason
        )
        
        # Create position
        position = Position(
            symbol=signal.symbol,
            strategy_id=signal.strategy_id,
            side=signal.direction,
            entry_price=signal.entry_price,
            entry_time=now,
            quantity=1.0,
            stop_loss=signal.stop_loss,
            take_profit_1=signal.take_profit_1,
            take_profit_2=signal.take_profit_2,
            take_profit_3=signal.take_profit_3,
            take_profit_4=signal.take_profit_4,
            take_profit_5=signal.take_profit_5,
            take_profit_6=signal.take_profit_6,
            take_profit_7=signal.take_profit_7,
            take_profit_8=signal.take_profit_8,
            take_profit_9=signal.take_profit_9,
            take_profit_10=signal.take_profit_10,
            current_sl=signal.stop_loss,
        )
        
        # Save
        self.storage.save_trade(trade)
        self.storage.save_position(position)
        
        print(f"📈 Opened {signal.direction} on {signal.symbol} @ {signal.entry_price:.4f} | Size: ${trade_size_usd:.2f} [{signal.strategy_id}]")
        
        return trade
    
    def get_position(self, symbol: str, strategy_id: str) -> Optional[Position]:
        """Get open position for symbol+strategy."""
        positions = self.storage.get_positions(strategy_id)
        for p in positions:
            if p.symbol == symbol:
                return p
        return None
    
    def update_position(self, symbol: str, strategy_id: str, current_price: float) -> Optional[str]:
        """
        Update position state based on current price.
        Checks SL/TP hits and updates trailing stop.
        At TP10, closes the position.
        
        Returns:
            'sl_hit', 'tp1_hit' through 'tp10_hit', 'tp10_close', or None
        """
        position = self.get_position(symbol, strategy_id)
        if not position:
            return None
        
        is_long = position.side == "LONG"
        
        # Check stop loss
        if is_long and current_price <= position.current_sl:
            self._close_position(position, current_price, "Stop Loss Hit")
            return "sl_hit"
        elif not is_long and current_price >= position.current_sl:
            self._close_position(position, current_price, "Stop Loss Hit")
            return "sl_hit"
        
        # Check take profits (highest first) - close at TP10
        result = None
        
        # TP levels with their previous TP for trailing SL
        tp_levels = [
            ('tp10', 'take_profit_10', 'take_profit_9', True),   # Close at TP10
            ('tp9', 'take_profit_9', 'take_profit_8', False),
            ('tp8', 'take_profit_8', 'take_profit_7', False),
            ('tp7', 'take_profit_7', 'take_profit_6', False),
            ('tp6', 'take_profit_6', 'take_profit_5', False),
            ('tp5', 'take_profit_5', 'take_profit_4', False),
            ('tp4', 'take_profit_4', 'take_profit_3', False),
            ('tp3', 'take_profit_3', 'take_profit_2', False),
            ('tp2', 'take_profit_2', 'take_profit_1', False),
            ('tp1', 'take_profit_1', None, False),
        ]
        
        for tp_name, tp_attr, sl_attr, close_position in tp_levels:
            hit_attr = f"{tp_name}_hit"
            is_hit = getattr(position, hit_attr, False)
            tp_price = getattr(position, tp_attr, None)
            
            if tp_price is None:
                continue
                
            if not is_hit:
                if (is_long and current_price >= tp_price) or (not is_long and current_price <= tp_price):
                    setattr(position, hit_attr, True)
                    
                    if close_position:
                        # TP10 hit - close the position
                        self._close_position(position, current_price, "TP10 Target Hit")
                        print(f"🎯🎯 TP10 HIT! Closed {symbol} [{strategy_id}] @ {current_price:.4f}")
                        return "tp10_close"
                    
                    # Update trailing SL
                    if sl_attr:
                        new_sl = getattr(position, sl_attr)
                        position.current_sl = new_sl
                    
                    result = f"{tp_name}_hit"
                    break
        
        if result:
            self.storage.save_position(position)
            print(f"🎯 {result.upper()} on {symbol} [{strategy_id}] - SL moved to {position.current_sl:.4f}")
        
        return result
    
    def _close_position(self, position: Position, exit_price: float, reason: str):
        """Close a position and calculate PnL."""
        # Calculate PnL percentage
        if position.side == "LONG":
            pnl_pct = ((exit_price - position.entry_price) / position.entry_price) * 100
        else:
            pnl_pct = ((position.entry_price - exit_price) / position.entry_price) * 100
        
        # Update trade record
        trades = self.storage.get_trades(
            strategy_id=position.strategy_id,
            symbol=position.symbol,
            status=TradeStatus.OPEN.value
        )
        
        trade_size_usd = 100.0  # Default
        pnl_usd = 0.0
        
        if trades:
            trade = trades[0]
            trade_size_usd = trade.trade_size_usd
            
            # Calculate USD PnL with leverage (8x)
            # With leverage: PnL is amplified
            leveraged_pnl_pct = pnl_pct * LEVERAGE
            pnl_usd = trade_size_usd * (leveraged_pnl_pct / 100)
            
            trade.exit_price = exit_price
            trade.exit_time = datetime.now(timezone.utc).isoformat()
            trade.pnl_pct = round(leveraged_pnl_pct, 2)  # Store leveraged PnL
            trade.pnl_usd = round(pnl_usd, 2)
            trade.status = TradeStatus.CLOSED.value
            trade.notes += f" | {reason}"
            
            self.storage.save_trade(trade)
        
        # Remove position
        self.storage.remove_position(position.symbol, position.strategy_id)
        
        # Update account balance with compounding
        self.storage.update_account_after_trade(pnl_usd, trade_size_usd)
        
        # Update performance
        self.storage.update_strategy_performance(position.strategy_id)
        
        emoji = "✅" if pnl_pct > 0 else "❌"
        print(f"{emoji} Closed {position.side} on {position.symbol} @ {exit_price:.4f} | PnL: {pnl_pct:+.2f}% (${pnl_usd:+.2f}) [{position.strategy_id}]")
    
    def check_all_positions(self, prices: Dict[str, float]):
        """
        Check all open positions against current prices.
        
        Args:
            prices: Dict mapping symbol to current price
        """
        for strategy in get_all_strategies():
            positions = self.storage.get_positions(strategy.strategy_id)
            for pos in positions:
                if pos.symbol in prices:
                    self.update_position(pos.symbol, pos.strategy_id, prices[pos.symbol])
    
    def get_all_open_trades(self) -> List[Trade]:
        """Get all open trades across all strategies."""
        return self.storage.get_trades(status=TradeStatus.OPEN.value)
    
    def get_strategy_performance(self, strategy_id: str) -> Dict:
        """Get performance metrics for a strategy."""
        return self.storage.get_performance(strategy_id)
    
    def get_all_performance(self) -> Dict:
        """Get performance for all strategies."""
        return self.storage.get_performance()


# Singleton
paper_trader = PaperTrader()
