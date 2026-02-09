"""
Main FastAPI Application
With APScheduler for 5-minute scans
"""
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Dict
import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .api.routes import router
from .scanner import scanner
from .strategy import get_all_strategies
from .paper_trader import paper_trader
from .indicators import add_all_indicators
from .config import SCAN_INTERVAL_MINUTES


# Scheduler
scheduler_instance = AsyncIOScheduler()


async def run_scan_cycle():
    """
    Main scanning cycle - runs every 5 minutes.
    1. Fetch OHLCV for all symbols
    2. Run all strategies
    3. Execute signals (paper + live if enabled)
    4. Update positions
    """
    from .live_trader import get_live_trader
    from .config import LIVE_STRATEGY
    from .indicators import calculate_heikin_ashi, get_ha_trend
    
    print(f"\n{'='*50}")
    print(f"🔍 Scan cycle started at {datetime.now(timezone.utc).isoformat()}")
    print(f"{'='*50}")
    
    try:
        # Get live trader instance
        live_trader = get_live_trader()
        
        # Get top symbols
        symbols = scanner.get_top_futures_symbols()
        print(f"📊 Scanning {len(symbols)} symbols...")
        
        # Current prices for position updates
        current_prices: Dict[str, float] = {}
        
        # Scan each symbol
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
                
                # Get current 4H HA state for live trading
                df_4h_ha = calculate_heikin_ashi(df_4h.copy())
                current_ha_state = get_ha_trend(df_4h_ha)
                
                # Save candles
                for tf, df in data.items():
                    if df is not None and not df.empty:
                        scanner.save_candles(symbol, tf, df)
                
                # Run all strategies
                for strategy in get_all_strategies():
                    signal = strategy.generate_signal(
                        symbol=symbol,
                        df_4h=df_4h,
                        df_5m=df_5m,
                        df_15m=df_15m,
                        df_1h=df_1h
                    )
                    
                    if signal and signal.direction:
                        # Paper trading - always execute
                        trade = paper_trader.execute_signal(signal)
                        if trade:
                            strategy.set_entry_time(symbol)
                        
                        # LIVE TRADING - only BASE strategy
                        if strategy.strategy_id == LIVE_STRATEGY and live_trader.enabled:
                            live_trader.execute_signal(signal, current_ha_state)
                
            except Exception as e:
                print(f"Error processing {symbol}: {e}")
                continue
        
        # Update all open positions (paper)
        paper_trader.check_all_positions(current_prices)
        
        # Update live positions (trailing SL)
        if live_trader.enabled:
            live_trader.update_positions()
        
        print(f"\n✅ Scan cycle completed. Prices updated for {len(current_prices)} symbols.")
        
    except Exception as e:
        print(f"❌ Error in scan cycle: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - start/stop scheduler."""
    # Startup
    print("🚀 Starting Paper Trading System...")
    
    # Schedule the scan every 5 minutes
    scheduler_instance.add_job(
        run_scan_cycle,
        'interval',
        minutes=SCAN_INTERVAL_MINUTES,
        id='scan_cycle',
        next_run_time=datetime.now(timezone.utc)  # Run immediately on start
    )
    scheduler_instance.start()
    print(f"⏰ Scheduler started - scanning every {SCAN_INTERVAL_MINUTES} minutes")
    
    yield
    
    # Shutdown
    scheduler_instance.shutdown()
    print("👋 Paper Trading System stopped.")


# Create FastAPI app
app = FastAPI(
    title="Bybit Paper Trading System",
    description="4H HA Flip Strategy with Multi-Variation A/B Testing",
    version="1.0.0",
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
        "scan_interval": f"{SCAN_INTERVAL_MINUTES} minutes",
        "strategies": [s.strategy_id for s in get_all_strategies()],
        "docs": "/docs"
    }


# For running directly
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
