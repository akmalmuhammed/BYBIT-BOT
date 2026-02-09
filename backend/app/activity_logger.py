"""
Activity Logger
Stores all trading events for the dashboard
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict
from .config import DATA_DIR

LOGS_FILE = DATA_DIR / "activity_logs.json"
MAX_LOGS = 500


class ActivityLogger:
    """Logs all trading activity for dashboard display."""
    
    def __init__(self):
        self.logs: List[Dict] = self._load_logs()
    
    def _load_logs(self) -> List[Dict]:
        """Load existing logs from file."""
        if LOGS_FILE.exists():
            try:
                with open(LOGS_FILE, 'r') as f:
                    return json.load(f)
            except:
                pass
        return []
    
    def _save_logs(self):
        """Save logs to file."""
        # Keep only latest MAX_LOGS
        self.logs = self.logs[-MAX_LOGS:]
        try:
            with open(LOGS_FILE, 'w') as f:
                json.dump(self.logs, f, indent=2)
        except Exception as e:
            print(f"Failed to save logs: {e}")
    
    def _add(self, event_type: str, symbol: str, message: str, data: Dict = None):
        """Add a log entry."""
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": event_type,
            "symbol": symbol,
            "message": message,
            "data": data or {}
        }
        self.logs.append(entry)
        self._save_logs()
        print(f"📝 [{event_type}] {symbol}: {message}")
    
    # ===== TRADE EVENTS =====
    
    def trade_opened(self, symbol: str, side: str, entry_price: float, qty: float):
        """Log new trade opened."""
        self._add("TRADE_OPEN", symbol, f"{side} opened @ {entry_price:.4f}", {
            "side": side,
            "entry_price": entry_price,
            "qty": qty
        })
    
    def trade_closed(self, symbol: str, side: str, exit_price: float, pnl: float, reason: str):
        """Log trade closed."""
        self._add("TRADE_CLOSE", symbol, f"{side} closed @ {exit_price:.4f} | {reason} | PnL: {pnl:+.2f}%", {
            "side": side,
            "exit_price": exit_price,
            "pnl": pnl,
            "reason": reason
        })
    
    # ===== SL EVENTS =====
    
    def sl_set(self, symbol: str, sl_price: float):
        """Log stop loss set."""
        self._add("SL_SET", symbol, f"Stop Loss set @ {sl_price:.4f}", {
            "sl_price": sl_price
        })
    
    def sl_updated(self, symbol: str, old_sl: float, new_sl: float, reason: str):
        """Log stop loss updated (trailing)."""
        self._add("SL_UPDATED", symbol, f"SL moved: {old_sl:.4f} → {new_sl:.4f} ({reason})", {
            "old_sl": old_sl,
            "new_sl": new_sl,
            "reason": reason
        })
    
    def sl_hit(self, symbol: str, sl_price: float, pnl: float):
        """Log stop loss hit."""
        self._add("SL_HIT", symbol, f"🛑 Stop Loss HIT @ {sl_price:.4f} | PnL: {pnl:+.2f}%", {
            "sl_price": sl_price,
            "pnl": pnl
        })
    
    # ===== TP EVENTS =====
    
    def tp_set(self, symbol: str, tp_levels: Dict[int, float]):
        """Log take profit levels set."""
        tp_str = ", ".join([f"TP{k}={v:.4f}" for k, v in tp_levels.items()])
        self._add("TP_SET", symbol, f"Take Profits set: {tp_str}", tp_levels)
    
    def tp_hit(self, symbol: str, tp_num: int, tp_price: float, new_sl: float = None):
        """Log take profit hit."""
        msg = f"🎯 TP{tp_num} HIT @ {tp_price:.4f}"
        if new_sl:
            msg += f" | SL moved to {new_sl:.4f}"
        self._add("TP_HIT", symbol, msg, {
            "tp_num": tp_num,
            "tp_price": tp_price,
            "new_sl": new_sl
        })
    
    def tp10_close(self, symbol: str, exit_price: float, pnl: float):
        """Log TP10 hit - position closed."""
        self._add("TP10_CLOSE", symbol, f"🎯🎯 TP10 FINAL TARGET! Closed @ {exit_price:.4f} | PnL: {pnl:+.2f}%", {
            "exit_price": exit_price,
            "pnl": pnl
        })
    
    # ===== SYSTEM EVENTS =====
    
    def scan_started(self, num_symbols: int):
        """Log scan cycle started."""
        self._add("SCAN", "SYSTEM", f"Scanning {num_symbols} symbols...", {
            "num_symbols": num_symbols
        })
    
    def signal_detected(self, symbol: str, side: str, ha_state: str):
        """Log signal detected."""
        self._add("SIGNAL", symbol, f"📊 {side} signal detected (HA: {ha_state})", {
            "side": side,
            "ha_state": ha_state
        })
    
    def flip_recorded(self, symbol: str, state: str):
        """Log initial HA state recorded."""
        self._add("FLIP_RECORD", symbol, f"Initial state recorded: {state}", {
            "state": state
        })
    
    def live_started(self):
        """Log live trading started."""
        self._add("SYSTEM", "SYSTEM", "🟢 LIVE TRADING ENABLED", {})
    
    def live_stopped(self):
        """Log live trading stopped."""
        self._add("SYSTEM", "SYSTEM", "🔴 LIVE TRADING STOPPED", {})
    
    def emergency_close(self, num_positions: int):
        """Log emergency close."""
        self._add("EMERGENCY", "SYSTEM", f"🚨 EMERGENCY CLOSE - {num_positions} positions closed", {
            "num_positions": num_positions
        })
    
    def get_logs(self, limit: int = 100, event_type: str = None) -> List[Dict]:
        """Get recent logs, optionally filtered by type."""
        logs = self.logs
        if event_type:
            logs = [l for l in logs if l.get("type") == event_type]
        return logs[-limit:][::-1]  # Most recent first


# Singleton instance
logger = ActivityLogger()
