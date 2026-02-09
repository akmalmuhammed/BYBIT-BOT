"""
JSON Storage Module
Handles persistence of trades, positions, and performance data
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, asdict
from enum import Enum

from .config import TRADES_DIR, POSITIONS_DIR, DATA_DIR, STARTING_CAPITAL, TRADE_SIZE, MAX_CONCURRENT_TRADES


class Side(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"


class TradeStatus(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    STOPPED = "STOPPED"


@dataclass
class Trade:
    """Represents a paper trade."""
    id: str
    symbol: str
    strategy_id: str
    side: str
    entry_price: float
    entry_time: str
    trade_size_usd: float = 100.0  # Position size in USD
    quantity: float = 1.0
    exit_price: Optional[float] = None
    exit_time: Optional[str] = None
    stop_loss: Optional[float] = None
    take_profit_1: Optional[float] = None
    take_profit_2: Optional[float] = None
    take_profit_3: Optional[float] = None
    current_sl: Optional[float] = None
    pnl_pct: Optional[float] = None
    pnl_usd: Optional[float] = None
    status: str = TradeStatus.OPEN.value
    notes: str = ""
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'Trade':
        return cls(**data)


@dataclass
class Position:
    """Represents an open position."""
    symbol: str
    strategy_id: str
    side: str
    entry_price: float
    entry_time: str
    quantity: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    take_profit_3: float
    current_sl: float
    # TP4-10 are optional for backward compatibility
    take_profit_4: Optional[float] = None
    take_profit_5: Optional[float] = None
    take_profit_6: Optional[float] = None
    take_profit_7: Optional[float] = None
    take_profit_8: Optional[float] = None
    take_profit_9: Optional[float] = None
    take_profit_10: Optional[float] = None
    tp1_hit: bool = False
    tp2_hit: bool = False
    tp3_hit: bool = False
    tp4_hit: bool = False
    tp5_hit: bool = False
    tp6_hit: bool = False
    tp7_hit: bool = False
    tp8_hit: bool = False
    tp9_hit: bool = False
    tp10_hit: bool = False
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'Position':
        # Handle old positions without TP4-10
        tp3 = data.get('take_profit_3', data.get('entry_price', 0))
        tp2 = data.get('take_profit_2', tp3)
        entry = data.get('entry_price', tp2)
        
        # Estimate ATR step from existing TPs
        if data.get('side') == 'LONG':
            step = (tp3 - tp2) if tp3 > tp2 else abs(entry * 0.01)
            for i in range(4, 11):
                if f'take_profit_{i}' not in data:
                    data[f'take_profit_{i}'] = tp3 + step * (i - 3)
        else:
            step = (tp2 - tp3) if tp2 > tp3 else abs(entry * 0.01)
            for i in range(4, 11):
                if f'take_profit_{i}' not in data:
                    data[f'take_profit_{i}'] = tp3 - step * (i - 3)
        
        # Ensure all TP hit flags exist
        for i in range(1, 11):
            data.setdefault(f'tp{i}_hit', False)
        
        return cls(**data)


class Storage:
    """JSON-based storage for paper trading data."""
    
    def __init__(self):
        self.trades_file = TRADES_DIR / "all_trades.json"
        self.positions_file = POSITIONS_DIR / "open_positions.json"
        self.performance_file = DATA_DIR / "performance.json"
        self.account_file = DATA_DIR / "account.json"
        
        # Initialize files if they don't exist
        self._init_files()
    
    def _init_files(self):
        """Create initial empty files if they don't exist."""
        if not self.trades_file.exists():
            self._write_json(self.trades_file, {"trades": []})
        
        if not self.positions_file.exists():
            self._write_json(self.positions_file, {"positions": []})
        
        if not self.performance_file.exists():
            self._write_json(self.performance_file, {
                "strategies": {},
                "daily_pnl": []
            })
        
        if not self.account_file.exists():
            self._write_json(self.account_file, {
                "starting_capital": STARTING_CAPITAL,
                "current_balance": STARTING_CAPITAL,
                "total_pnl_usd": 0.0,
                "next_trade_size": TRADE_SIZE,
                "max_trades": MAX_CONCURRENT_TRADES,
                "created_at": datetime.now(timezone.utc).isoformat()
            })
    
    def _read_json(self, filepath: Path) -> Dict:
        """Read JSON file."""
        try:
            with open(filepath, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error reading {filepath}: {e}")
            return {}
    
    def _write_json(self, filepath: Path, data: Dict):
        """Write JSON file."""
        try:
            with open(filepath, 'w') as f:
                json.dump(data, f, indent=2, default=str)
        except Exception as e:
            print(f"Error writing {filepath}: {e}")
    
    # ============ TRADES ============
    
    def save_trade(self, trade: Trade):
        """Save a new trade or update existing."""
        data = self._read_json(self.trades_file)
        trades = data.get("trades", [])
        
        # Check if trade exists (update) or is new (append)
        existing_idx = None
        for i, t in enumerate(trades):
            if t.get("id") == trade.id:
                existing_idx = i
                break
        
        if existing_idx is not None:
            trades[existing_idx] = trade.to_dict()
        else:
            trades.append(trade.to_dict())
        
        data["trades"] = trades
        data["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._write_json(self.trades_file, data)
    
    def get_trades(self, 
                   strategy_id: Optional[str] = None,
                   symbol: Optional[str] = None,
                   status: Optional[str] = None) -> List[Trade]:
        """Get trades with optional filters."""
        data = self._read_json(self.trades_file)
        trades = data.get("trades", [])
        
        result = []
        for t in trades:
            if strategy_id and t.get("strategy_id") != strategy_id:
                continue
            if symbol and t.get("symbol") != symbol:
                continue
            if status and t.get("status") != status:
                continue
            result.append(Trade.from_dict(t))
        
        return result
    
    def get_trade_by_id(self, trade_id: str) -> Optional[Trade]:
        """Get a specific trade by ID."""
        trades = self.get_trades()
        for t in trades:
            if t.id == trade_id:
                return t
        return None
    
    # ============ POSITIONS ============
    
    def save_position(self, position: Position):
        """Save an open position."""
        data = self._read_json(self.positions_file)
        positions = data.get("positions", [])
        
        # Remove existing position for same symbol+strategy
        positions = [
            p for p in positions 
            if not (p.get("symbol") == position.symbol and 
                    p.get("strategy_id") == position.strategy_id)
        ]
        
        positions.append(position.to_dict())
        data["positions"] = positions
        data["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._write_json(self.positions_file, data)
    
    def get_positions(self, strategy_id: Optional[str] = None) -> List[Position]:
        """Get all open positions, optionally filtered by strategy."""
        data = self._read_json(self.positions_file)
        positions = data.get("positions", [])
        
        result = []
        for p in positions:
            if strategy_id and p.get("strategy_id") != strategy_id:
                continue
            result.append(Position.from_dict(p))
        
        return result
    
    def remove_position(self, symbol: str, strategy_id: str):
        """Remove a closed position."""
        data = self._read_json(self.positions_file)
        positions = data.get("positions", [])
        
        positions = [
            p for p in positions 
            if not (p.get("symbol") == symbol and 
                    p.get("strategy_id") == strategy_id)
        ]
        
        data["positions"] = positions
        data["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._write_json(self.positions_file, data)
    
    # ============ PERFORMANCE ============
    
    def update_strategy_performance(self, strategy_id: str):
        """Recalculate performance metrics for a strategy."""
        trades = self.get_trades(strategy_id=strategy_id, status=TradeStatus.CLOSED.value)
        
        if not trades:
            return
        
        wins = [t for t in trades if t.pnl_pct and t.pnl_pct > 0]
        losses = [t for t in trades if t.pnl_pct and t.pnl_pct <= 0]
        
        total_pnl = sum(t.pnl_pct for t in trades if t.pnl_pct)
        win_rate = len(wins) / len(trades) * 100 if trades else 0
        
        avg_win = sum(t.pnl_pct for t in wins) / len(wins) if wins else 0
        avg_loss = sum(t.pnl_pct for t in losses) / len(losses) if losses else 0
        
        data = self._read_json(self.performance_file)
        data["strategies"][strategy_id] = {
            "total_trades": len(trades),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": round(win_rate, 2),
            "total_pnl_pct": round(total_pnl, 2),
            "avg_win_pct": round(avg_win, 2),
            "avg_loss_pct": round(avg_loss, 2),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        
        self._write_json(self.performance_file, data)
    
    def get_performance(self, strategy_id: Optional[str] = None) -> Dict:
        """Get performance metrics."""
        data = self._read_json(self.performance_file)
        
        if strategy_id:
            return data.get("strategies", {}).get(strategy_id, {})
        
        return data.get("strategies", {})
    
    # ============ ACCOUNT ============
    
    def get_account(self) -> Dict:
        """Get account info."""
        return self._read_json(self.account_file)
    
    def get_next_trade_size(self) -> float:
        """Get next trade size with compounding."""
        account = self.get_account()
        return account.get("next_trade_size", TRADE_SIZE)
    
    def get_current_balance(self) -> float:
        """Get current account balance."""
        account = self.get_account()
        return account.get("current_balance", STARTING_CAPITAL)
    
    def can_open_trade(self, strategy_id: str = None) -> bool:
        """Check if we can open more trades (max 10 PER STRATEGY)."""
        if strategy_id:
            # Count positions for this specific strategy
            positions = self.get_positions(strategy_id)
        else:
            positions = self.get_positions()
        account = self.get_account()
        max_trades = account.get("max_trades", MAX_CONCURRENT_TRADES)
        return len(positions) < max_trades
    
    def update_account_after_trade(self, pnl_usd: float, trade_size: float):
        """
        Update account balance after a trade closes.
        Compounding: next trade size = current trade size + pnl
        """
        account = self.get_account()
        
        # Update balance
        account["current_balance"] = account.get("current_balance", STARTING_CAPITAL) + pnl_usd
        account["total_pnl_usd"] = account.get("total_pnl_usd", 0) + pnl_usd
        
        # Compounding: next trade size = trade_size + pnl
        # If you win $5 on a $100 trade, next trade is $105
        # If you lose $5 on a $100 trade, next trade is $95
        new_trade_size = trade_size + pnl_usd
        
        # Don't go below $10 minimum or above balance
        new_trade_size = max(10.0, min(new_trade_size, account["current_balance"]))
        account["next_trade_size"] = round(new_trade_size, 2)
        
        account["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._write_json(self.account_file, account)
        
        print(f"💰 Balance: ${account['current_balance']:.2f} | Next trade: ${account['next_trade_size']:.2f}")


# Singleton instance
storage = Storage()
