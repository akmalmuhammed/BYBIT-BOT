"""
API Routes
REST endpoints for dashboard
"""
from fastapi import APIRouter, HTTPException
from typing import List, Dict, Optional
from pydantic import BaseModel

from ..storage import storage, Trade, TradeStatus
from ..strategy import get_all_strategies, get_strategy, STRATEGIES
from ..paper_trader import paper_trader
from ..scanner import scanner

router = APIRouter(prefix="/api", tags=["trading"])


# ============ RESPONSE MODELS ============

class StrategyInfo(BaseModel):
    id: str
    cooldown_minutes: int
    sl_percent: float
    atr_timeframe: str


class TradeResponse(BaseModel):
    id: str
    symbol: str
    strategy_id: str
    side: str
    entry_price: float
    entry_time: str
    trade_size_usd: float = 100.0
    exit_price: Optional[float]
    exit_time: Optional[str]
    pnl_pct: Optional[float]
    pnl_usd: Optional[float]
    status: str


class PerformanceResponse(BaseModel):
    strategy_id: str
    total_trades: int
    wins: int
    losses: int
    win_rate: float
    total_pnl_pct: float


class PositionResponse(BaseModel):
    symbol: str
    strategy_id: str
    side: str
    entry_price: float
    current_sl: float
    take_profit_1: float
    take_profit_2: float
    take_profit_3: float
    take_profit_4: float
    take_profit_5: float
    take_profit_6: float
    tp1_hit: bool
    tp2_hit: bool
    tp3_hit: bool
    tp4_hit: bool
    tp5_hit: bool
    tp6_hit: bool
    current_price: Optional[float] = None
    unrealized_pnl_pct: Optional[float] = None
    unrealized_pnl_usd: Optional[float] = None
    trade_size_usd: Optional[float] = None


# ============ ENDPOINTS ============

@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}


@router.get("/strategies", response_model=List[StrategyInfo])
async def get_strategies():
    """Get all registered strategies."""
    strategies = get_all_strategies()
    return [
        StrategyInfo(
            id=s.strategy_id,
            cooldown_minutes=s.cooldown_minutes,
            sl_percent=s.sl_percent,
            atr_timeframe=s.atr_timeframe
        )
        for s in strategies
    ]


@router.get("/symbols")
async def get_symbols():
    """Get top 60 futures symbols."""
    symbols = scanner.get_top_futures_symbols()
    return {"symbols": symbols, "count": len(symbols)}


@router.get("/trades", response_model=List[TradeResponse])
async def get_trades(
    strategy_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 100
):
    """Get trade history."""
    trades = storage.get_trades(strategy_id=strategy_id, status=status)
    trades = trades[-limit:]  # Most recent
    
    return [
        TradeResponse(
            id=t.id,
            symbol=t.symbol,
            strategy_id=t.strategy_id,
            side=t.side,
            entry_price=t.entry_price,
            entry_time=t.entry_time,
            trade_size_usd=t.trade_size_usd,
            exit_price=t.exit_price,
            exit_time=t.exit_time,
            pnl_pct=t.pnl_pct,
            pnl_usd=t.pnl_usd,
            status=t.status
        )
        for t in trades
    ]


@router.get("/trades/{trade_id}")
async def get_trade(trade_id: str):
    """Get a specific trade."""
    trade = storage.get_trade_by_id(trade_id)
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")
    return trade.to_dict()


@router.get("/positions")
async def get_positions(strategy_id: Optional[str] = None):
    """Get open positions with enriched data."""
    from ..config import LEVERAGE
    
    positions = storage.get_positions(strategy_id)
    result = []
    
    for p in positions:
        # Get current price from latest candle
        current_price = None
        df = scanner.load_candles(p.symbol, "5")
        if not df.empty:
            current_price = float(df.iloc[-1]['close'])
        
        # Calculate unrealized PnL
        unrealized_pnl_pct = None
        unrealized_pnl_usd = None
        trade_size_usd = 100.0  # Default
        
        if current_price:
            if p.side == "LONG":
                pnl_pct = ((current_price - p.entry_price) / p.entry_price) * 100
            else:
                pnl_pct = ((p.entry_price - current_price) / p.entry_price) * 100
            
            # Apply leverage
            unrealized_pnl_pct = round(pnl_pct * LEVERAGE, 2)
            
            # Get trade size from open trades
            trades = storage.get_trades(strategy_id=p.strategy_id, symbol=p.symbol, status="OPEN")
            if trades:
                trade_size_usd = trades[0].trade_size_usd
            
            unrealized_pnl_usd = round(trade_size_usd * (unrealized_pnl_pct / 100), 2)
        
        result.append({
            "symbol": p.symbol,
            "strategy_id": p.strategy_id,
            "side": p.side,
            "entry_price": p.entry_price,
            "current_sl": p.current_sl,
            "take_profit_1": p.take_profit_1,
            "take_profit_2": p.take_profit_2,
            "take_profit_3": p.take_profit_3,
            "take_profit_4": p.take_profit_4,
            "take_profit_5": p.take_profit_5,
            "take_profit_6": p.take_profit_6,
            "tp1_hit": p.tp1_hit,
            "tp2_hit": p.tp2_hit,
            "tp3_hit": p.tp3_hit,
            "tp4_hit": p.tp4_hit,
            "tp5_hit": p.tp5_hit,
            "tp6_hit": p.tp6_hit,
            "current_price": current_price,
            "unrealized_pnl_pct": unrealized_pnl_pct,
            "unrealized_pnl_usd": unrealized_pnl_usd,
            "trade_size_usd": trade_size_usd
        })
    
    return result


@router.get("/performance")
async def get_performance(strategy_id: Optional[str] = None):
    """Get performance metrics."""
    if strategy_id:
        perf = storage.get_performance(strategy_id)
        if not perf:
            return {"strategy_id": strategy_id, "total_trades": 0}
        return {"strategy_id": strategy_id, **perf}
    
    all_perf = storage.get_performance()
    result = []
    for sid, data in all_perf.items():
        result.append({"strategy_id": sid, **data})
    
    return {"strategies": result}


@router.get("/comparison")
async def get_strategy_comparison():
    """Get side-by-side strategy comparison."""
    all_perf = storage.get_performance()
    
    comparison = []
    for strategy in get_all_strategies():
        perf = all_perf.get(strategy.strategy_id, {})
        comparison.append({
            "strategy_id": strategy.strategy_id,
            "cooldown": strategy.cooldown_minutes,
            "atr_tf": strategy.atr_timeframe,
            "total_trades": perf.get("total_trades", 0),
            "wins": perf.get("wins", 0),
            "losses": perf.get("losses", 0),
            "win_rate": perf.get("win_rate", 0),
            "total_pnl": perf.get("total_pnl_pct", 0)
        })
    
    # Sort by win rate
    comparison.sort(key=lambda x: x["win_rate"], reverse=True)
    
    return {"comparison": comparison}


@router.get("/candles/{symbol}")
async def get_candles(symbol: str, timeframe: str = "5"):
    """Get cached candles for a symbol."""
    df = scanner.load_candles(symbol, timeframe)
    
    if df.empty:
        # Try to fetch fresh
        df = scanner.fetch_klines(symbol, interval=timeframe)
        if df.empty:
            raise HTTPException(status_code=404, detail="No candles found")
        scanner.save_candles(symbol, timeframe, df)
    
    # Convert to list of dicts
    records = df.tail(100).to_dict(orient='records')
    for r in records:
        if hasattr(r.get('timestamp'), 'isoformat'):
            r['timestamp'] = r['timestamp'].isoformat()
    
    return {"symbol": symbol, "timeframe": timeframe, "candles": records}


@router.get("/account")
async def get_account():
    """Get account balance and trading info."""
    account = storage.get_account()
    positions = storage.get_positions()
    
    return {
        "starting_capital": account.get("starting_capital", 1000),
        "current_balance": round(account.get("current_balance", 1000), 2),
        "total_pnl_usd": round(account.get("total_pnl_usd", 0), 2),
        "next_trade_size": round(account.get("next_trade_size", 100), 2),
        "max_trades": account.get("max_trades", 10),
        "open_positions": len(positions)
    }


@router.get("/ha-candles/{symbol}")
async def get_ha_candles(symbol: str, timeframe: str = "240"):
    """Get Heikin-Ashi candles with flip signals."""
    from ..indicators import heikin_ashi
    
    df = scanner.load_candles(symbol, timeframe)
    
    if df.empty:
        df = scanner.fetch_klines(symbol, interval=timeframe, limit=200)
        if df.empty:
            raise HTTPException(status_code=404, detail="No candles found")
        scanner.save_candles(symbol, timeframe, df)
    
    # Calculate Heikin-Ashi
    ha_df = heikin_ashi(df)
    
    # Detect bullish/bearish and flips
    ha_candles = []
    prev_trend = None
    
    for i, row in ha_df.iterrows():
        is_bullish = row['ha_close'] > row['ha_open']
        trend = "bullish" if is_bullish else "bearish"
        
        # Detect flip
        flip = None
        if prev_trend is not None and prev_trend != trend:
            flip = trend  # "bullish" or "bearish" flip
        
        ha_candles.append({
            "timestamp": row['timestamp'].isoformat() if hasattr(row['timestamp'], 'isoformat') else str(row['timestamp']),
            "open": round(row['ha_open'], 6),
            "high": round(row['ha_high'], 6),
            "low": round(row['ha_low'], 6),
            "close": round(row['ha_close'], 6),
            "trend": trend,
            "flip": flip
        })
        
        prev_trend = trend
    
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "candles": ha_candles[-100:]  # Last 100 candles
    }


# ============ LIVE TRADING ENDPOINTS ============

@router.post("/live/start")
async def start_live_trading():
    """Start live trading on Bybit."""
    from ..live_trader import get_live_trader
    from ..config import LIVE_TRADE_SIZE_USD, LIVE_MAX_POSITIONS
    
    trader = get_live_trader(
        trade_size_usd=LIVE_TRADE_SIZE_USD,
        max_positions=LIVE_MAX_POSITIONS
    )
    trader.start()
    
    return {
        "status": "started",
        "message": "🔴 LIVE TRADING ENABLED",
        "settings": trader.get_status()
    }


@router.post("/live/stop")
async def stop_live_trading():
    """Stop live trading."""
    from ..live_trader import get_live_trader
    
    trader = get_live_trader()
    trader.stop()
    
    return {
        "status": "stopped",
        "message": "Live trading disabled"
    }


@router.get("/live/status")
async def get_live_status():
    """Get live trading status."""
    from ..live_trader import get_live_trader
    from ..bybit_client import get_client
    
    try:
        trader = get_live_trader()
        client = get_client()
        
        # Get wallet balance
        balance = client.get_wallet_balance("USDT")
        
        # Get positions from Bybit
        positions = client.get_positions()
        
        return {
            "trading": trader.get_status(),
            "wallet": {
                "balance_usdt": balance
            },
            "bybit_positions": len(positions)
        }
    except Exception as e:
        return {
            "error": str(e),
            "trading": {"enabled": False}
        }


@router.post("/live/emergency-close")
async def emergency_close_all():
    """Emergency close all live positions."""
    from ..live_trader import get_live_trader
    
    trader = get_live_trader()
    trader.close_all_positions()
    
    return {
        "status": "closed",
        "message": "🚨 All positions closed"
    }


@router.get("/live/balance")
async def get_live_balance():
    """Get Bybit wallet balance."""
    from ..bybit_client import get_client
    
    try:
        client = get_client()
        balance = client.get_wallet_balance("USDT")
        
        return {
            "balance_usdt": balance,
            "status": "ok"
        }
    except Exception as e:
        return {
            "error": str(e),
            "status": "error"
        }
