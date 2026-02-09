"""
Main FastAPI Application
With APScheduler for 5-minute scans

FIXES:
- Blocking pybit calls run in thread pool (asyncio.to_thread) to not freeze the event loop
- Scheduler: max_instances=1, coalesce=True, misfire_grace_time=300
- Added heartbeat tracking so dashboard can detect stale scans
- Added scan duration tracking and timeout protection
- Wrapped entire scan in try/except so scheduler NEVER dies
"""
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Dict
import asyncio
import time
import traceback

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .api.routes import router
from .scanner import scanner
from .strategy import get_all_strategies
from .paper_trader import paper_trader
from .indicators import add_all_indicators, calculate_heikin_ashi, get_ha_trend
from .config import SCAN_INTERVAL_MINUTES, get_current_time


# Scheduler
scheduler_instance = AsyncIOScheduler()

# Heartbeat tracking (accessible from routes for dashboard health)
scan_heartbeat = {
    "last_scan_start": None,
    "last_scan_end": None,
    "last_scan_duration": 0,
    "scan_count": 0,
    "last_error": None,
    "is_scanning": False,
    "symbols_scanned": 0,
    "flips_detected": 0,
}


def _blocking_scan_cycle():
    """
    The actual scan logic - runs in a thread pool.
    All pybit calls are synchronous/blocking, so this MUST NOT run on the asyncio event loop.
    
    Returns scan stats dict.
    """
    from .live_trader import get_live_trader
    from .config import LIVE_STRATEGY
    
    stats = {"symbols": 0, "flips": 0, "signals": 0, "errors": 0}
    
    live_trader = get_live_trader()
    symbols = scanner.get_top_futures_symbols()
    print(f"📊 Scanning {len(symbols)} symbols... (Live: {'ON' if live_trader.enabled else 'OFF'})")
    
    if not symbols:
        print("⚠️ No symbols returned! Check API connection.")
        return stats
    
    current_prices: Dict[str, float] = {}
    
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
            
            stats["symbols"] += 1
            current_prices[symbol] = df_5m.iloc[-1]['close']
            
            # ==============================
            # CRITICAL: Use COMPLETED candles only for HA state
            # ==============================
            if len(df_4h) < 3:
                continue
            
            df_4h_ha = calculate_heikin_ashi(df_4h.copy())
            
            # [-2] = last COMPLETED candle, [-1] = current FORMING candle (skip)
            last_completed = df_4h_ha.iloc[-2]
            current_ha_state = 'bullish' if last_completed['HA_close'] > last_completed['HA_open'] else 'bearish'
            
            # ==============================
            # LIVE TRADING
            # ==============================
            if live_trader.enabled:
                is_flip = live_trader.is_new_flip(symbol, current_ha_state)
                
                if is_flip:
                    stats["flips"] += 1
                    direction = "LONG" if current_ha_state == "bullish" else "SHORT"
                    print(f"🔄 FLIP: {symbol} → {current_ha_state} ({direction})")
                    
                    for strategy in get_all_strategies():
                        if strategy.strategy_id == LIVE_STRATEGY:
                            signal = strategy.generate_signal(
                                symbol=symbol,
                                df_4h=df_4h,
                                df_5m=df_5m,
                                df_15m=df_15m,
                                df_1h=df_1h,
                                forced_direction=direction
                            )
                            if signal and signal.direction:
                                stats["signals"] += 1
                                print(f"📈 Signal: {signal.direction} {symbol} @ {signal.entry_price}")
                                live_trader.execute_trade(signal)
                            else:
                                print(f"⚠️ Signal filtered for {symbol} (cooldown/data)")
            
            # Save candles
            for tf, df in data.items():
                if df is not None and not df.empty:
                    scanner.save_candles(symbol, tf, df)
            
            # ==============================
            # PAPER TRADING
            # ==============================
            for strategy in get_all_strategies():
                signal = strategy.generate_signal(
                    symbol=symbol,
                    df_4h=df_4h,
                    df_5m=df_5m,
                    df_15m=df_15m,
                    df_1h=df_1h
                )
                
                if signal and signal.direction:
                    trade = paper_trader.execute_signal(signal)
                    if trade:
                        strategy.set_entry_time(symbol)
            
        except Exception as e:
            stats["errors"] += 1
            print(f"❌ Error processing {symbol}: {e}")
            traceback.print_exc()
            continue
    
    # Update positions
    try:
        paper_trader.check_all_positions(current_prices)
    except Exception as e:
        print(f"⚠️ Error updating paper positions: {e}")
    
    try:
        if live_trader.enabled:
            live_trader.update_positions()
    except Exception as e:
        print(f"⚠️ Error updating live positions: {e}")
    
    # Update scanner diagnostics
    scanner._last_scan_time = get_current_time().isoformat()
    
    return stats


async def run_scan_cycle():
    """
    Async wrapper that runs the blocking scan in a thread pool.
    This ensures the FastAPI event loop and scheduler stay responsive.
    
    CRITICAL: This function NEVER raises an exception.
    If it did, APScheduler would log it but the job continues.
    The triple try/except ensures the scheduler is bulletproof.
    """
    global scan_heartbeat
    from .activity_logger import logger
    
    scan_heartbeat["is_scanning"] = True
    scan_heartbeat["last_scan_start"] = get_current_time().isoformat()
    
    print(f"\n{'='*50}")
    print(f"🔍 Scan #{scan_heartbeat['scan_count'] + 1} at {scan_heartbeat['last_scan_start']}")
    print(f"{'='*50}")
    
    # Log to dashboard
    logger.scan_started(15)  # Approx number
    
    start_time = time.time()
    
    try:
        # Run the blocking scan in a thread pool so it doesn't freeze the event loop
        stats = await asyncio.wait_for(
            asyncio.to_thread(_blocking_scan_cycle),
            timeout=240  # 4 minute timeout (scan interval is 5 min)
        )
        
        duration = time.time() - start_time
        
        scan_heartbeat["last_scan_end"] = get_current_time().isoformat()
        scan_heartbeat["last_scan_duration"] = round(duration, 1)
        scan_heartbeat["scan_count"] += 1
        scan_heartbeat["symbols_scanned"] = stats.get("symbols", 0)
        scan_heartbeat["flips_detected"] = stats.get("flips", 0)
        scan_heartbeat["last_error"] = None
        scan_heartbeat["is_scanning"] = False
        
        scanner._last_scan_duration = duration
        
        print(f"\n✅ Scan complete in {duration:.1f}s | {stats['symbols']} symbols | {stats['flips']} flips | {stats['signals']} signals | {stats['errors']} errors")
        
        # Log completion
        logger._add("SCAN", "SYSTEM", f"✅ Scan complete in {duration:.1f}s", stats)
        
    except asyncio.TimeoutError:
        duration = time.time() - start_time
        scan_heartbeat["last_error"] = f"Scan timed out after {duration:.0f}s"
        scan_heartbeat["is_scanning"] = False
        print(f"⏰ SCAN TIMED OUT after {duration:.0f}s! Will retry next cycle.")
        
    except Exception as e:
        duration = time.time() - start_time
        scan_heartbeat["last_error"] = f"{type(e).__name__}: {str(e)[:200]}"
        scan_heartbeat["is_scanning"] = False
        print(f"❌ Scan failed after {duration:.1f}s: {e}")
        traceback.print_exc()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - start/stop scheduler."""
    print("🚀 Starting Bybit Trading System...")
    print(f"   Scan interval: {SCAN_INTERVAL_MINUTES} minutes")
    
    scheduler_instance.add_job(
        run_scan_cycle,
        'interval',
        minutes=SCAN_INTERVAL_MINUTES,
        id='scan_cycle',
        next_run_time=get_current_time(),
        max_instances=1,       # Never run 2 scans at once
        coalesce=True,         # If missed, run once (not multiple catchups)
        misfire_grace_time=300, # Allow 5 min grace for misfired jobs
    )
    scheduler_instance.start()
    print(f"⏰ Scheduler started")
    
    yield
    
    scheduler_instance.shutdown()
    print("👋 Trading System stopped.")


# Create FastAPI app
app = FastAPI(
    title="Bybit Trading System",
    description="4H HA Flip Strategy with Multi-Variation A/B Testing",
    version="1.2.0",
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
        "name": "Bybit Trading System",
        "status": "running",
        "version": "1.2.0",
        "scan_interval": f"{SCAN_INTERVAL_MINUTES} minutes",
        "strategies": [s.strategy_id for s in get_all_strategies()],
        "heartbeat": scan_heartbeat,
        "docs": "/docs"
    }


# For running directly
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
