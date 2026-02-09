"""
Main FastAPI Application
With APScheduler for 5-minute scans

FIXES:
- HA state calculated from COMPLETED candles only (excludes current forming candle)
- Live trading uses forced_direction to bypass strategy's internal flip detection
- Paper trading uses strategy's detect_flip (DataFrame-based, no internal state)
- Better error logging and scan diagnostics
"""
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Dict
import asyncio
import traceback

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .api.routes import router
from .scanner import scanner
from .strategy import get_all_strategies
from .paper_trader import paper_trader
from .indicators import add_all_indicators, calculate_heikin_ashi, get_ha_trend
from .config import SCAN_INTERVAL_MINUTES


# Scheduler
scheduler_instance = AsyncIOScheduler()


async def run_scan_cycle():
    """
    Main scanning cycle - runs every 5 minutes.
    1. Fetch OHLCV for all symbols
    2. Determine HA state from COMPLETED candles only
    3. Check for flips (live) or run strategy detection (paper)
    4. Execute signals
    5. Update positions
    """
    from .live_trader import get_live_trader
    from .config import LIVE_STRATEGY
    
    print(f"\n{'='*50}")
    print(f"🔍 Scan cycle started at {datetime.now(timezone.utc).isoformat()}")
    print(f"{'='*50}")
    
    try:
        live_trader = get_live_trader()
        symbols = scanner.get_top_futures_symbols()
        print(f"📊 Scanning {len(symbols)} symbols... (Live: {'ON' if live_trader.enabled else 'OFF'})")
        
        current_prices: Dict[str, float] = {}
        flip_count = 0
        signal_count = 0
        
        for symbol in symbols:
            try:
                # Fetch all needed timeframes
                data = scanner.fetch_multi_timeframe(
                    symbol, 
                    timeframes=["5", "15", "60", "240"]
                )
                
                df_5m = data.get("5")
                df_15m = data.get("15")
                df_1h = data.get("60")
                df_4h = data.get("240")
                
                if df_5m is None or df_5m.empty or df_4h is None or df_4h.empty:
                    continue
                
                # Store current price
                current_prices[symbol] = df_5m.iloc[-1]['close']
                
                # ==============================
                # CRITICAL: Use COMPLETED candles only for HA state
                # df_4h[-1] is the CURRENT (forming) candle - exclude it
                # df_4h[-2] is the LAST COMPLETED candle - use this for state
                # ==============================
                if len(df_4h) < 3:
                    continue
                
                # Calculate HA on all candles
                df_4h_ha = calculate_heikin_ashi(df_4h.copy())
                
                # Get state from LAST COMPLETED candle ([-2], not [-1])
                last_completed = df_4h_ha.iloc[-2]
                current_ha_state = 'bullish' if last_completed['HA_close'] > last_completed['HA_open'] else 'bearish'
                
                # ==============================
                # LIVE TRADING: Use live_trader's flip detection + forced_direction
                # This avoids the double flip detection bug
                # ==============================
                if live_trader.enabled:
                    is_flip = live_trader.is_new_flip(symbol, current_ha_state)
                    
                    if is_flip:
                        flip_count += 1
                        direction = "LONG" if current_ha_state == "bullish" else "SHORT"
                        print(f"🔄 FLIP detected: {symbol} → {current_ha_state} (direction: {direction})")
                        
                        # Find the live strategy and generate signal with forced_direction
                        for strategy in get_all_strategies():
                            if strategy.strategy_id == LIVE_STRATEGY:
                                signal = strategy.generate_signal(
                                    symbol=symbol,
                                    df_4h=df_4h,
                                    df_5m=df_5m,
                                    df_15m=df_15m,
                                    df_1h=df_1h,
                                    forced_direction=direction  # <-- BYPASS internal flip detection
                                )
                                if signal and signal.direction:
                                    signal_count += 1
                                    print(f"📈 Signal generated: {signal.direction} {symbol} @ {signal.entry_price}")
                                    live_trader.execute_trade(signal)
                                else:
                                    print(f"⚠️ Signal filtered out for {symbol} (cooldown or filters)")
                
                # Save candles
                for tf, df in data.items():
                    if df is not None and not df.empty:
                        scanner.save_candles(symbol, tf, df)
                
                # ==============================
                # PAPER TRADING: Uses strategy's own detect_flip (DataFrame-based)
                # This is independent of live trading state
                # ==============================
                for strategy in get_all_strategies():
                    signal = strategy.generate_signal(
                        symbol=symbol,
                        df_4h=df_4h,
                        df_5m=df_5m,
                        df_15m=df_15m,
                        df_1h=df_1h
                        # No forced_direction → uses strategy's detect_flip
                    )
                    
                    if signal and signal.direction:
                        trade = paper_trader.execute_signal(signal)
                        if trade:
                            strategy.set_entry_time(symbol)
                
            except Exception as e:
                print(f"❌ Error processing {symbol}: {e}")
                traceback.print_exc()
                continue
        
        # Update positions
        paper_trader.check_all_positions(current_prices)
        
        if live_trader.enabled:
            live_trader.update_positions()
        
        print(f"\n✅ Scan complete | {len(current_prices)} symbols | {flip_count} flips | {signal_count} signals")
        
    except Exception as e:
        print(f"❌ Error in scan cycle: {e}")
        traceback.print_exc()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - start/stop scheduler."""
    print("🚀 Starting Paper Trading System...")
    
    scheduler_instance.add_job(
        run_scan_cycle,
        'interval',
        minutes=SCAN_INTERVAL_MINUTES,
        id='scan_cycle',
        next_run_time=datetime.now(timezone.utc)
    )
    scheduler_instance.start()
    print(f"⏰ Scheduler started - scanning every {SCAN_INTERVAL_MINUTES} minutes")
    
    yield
    
    scheduler_instance.shutdown()
    print("👋 Paper Trading System stopped.")


# Create FastAPI app
app = FastAPI(
    title="Bybit Paper Trading System",
    description="4H HA Flip Strategy with Multi-Variation A/B Testing",
    version="1.1.0",
    lifespan=lifespan
)

# CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routes
app.include_router(router)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "Bybit Paper Trading System",
        "status": "running",
        "version": "1.1.0",
        "scan_interval": f"{SCAN_INTERVAL_MINUTES} minutes",
        "strategies": [s.strategy_id for s in get_all_strategies()],
        "docs": "/docs"
    }


# For running directly
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
