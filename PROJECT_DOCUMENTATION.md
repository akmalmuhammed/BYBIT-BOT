# 📘 Bybit GCP Trading Bot - Comprehensive Documentation

## 1. Executive Summary

This project is a sophisticated **algorithmic trading system** designed to trade cryptocurrency futures on **Bybit (USDT Perpetual)**. It is essentially a "headless" automated trader that runs 24/7 on a **Google Cloud Platform (GCP)** Virtual Machine.

Key capabilities:

- **Autonomous Operations**: Scans the market, generates signals, and executes trades without human intervention.
- **Robust Architecture**: Built with Python (FastAPI) and Docker, designed for fault tolerance and auto-recovery.
- **Live Monitoring**: Includes a real-time dashboard for tracking performance and health.

---

## 2. System Architecture

The system is deployed as a multi-container **Docker** application orchestrated via `docker-compose`.

### 🏗️ Components

1.  **Bot Container (`backend`)**:
    - **Image**: Python 3.9 Slim
    - **Role**: The brain of the operation. Handles data fetching, strategy logic, and execution.
    - **Framework**: FastAPI (for internal API + dashboard backend).

2.  **Dashboard Container (`nginx`)**:
    - **Image**: Nginx Alpine
    - **Role**: Serves the frontend static files (HTML/JS) and reverse-proxies API requests to the bot.
    - **Port**: Exposed on port 80 (HTTP).

### 🔄 Data Flow

1.  **Scheduler** (inside Bot) triggers a scan every **5 minutes**.
2.  **Scanner** fetches OHLCV market data from **Bybit API**.
3.  **Strategy Engine** analyzes the data using Heikin-Ashi and other indicators.
4.  **Signal Generator** produces BUY/SELL signals based on trend flips.
5.  **Trader Module** validates signals and executes orders via Bybit API.
6.  **Dashboard** polls the Bot API to display live status.

---

## 3. Core Logic & Implementation

### 🕒 The Scheduler (`main.py`)

- Uses `APScheduler` (AsyncIO) to run tasks.
- **Resilience**: Configured with `max_instances=1` (prevents overlaps) and `misfire_grace_time=300s`.
- **Thread Pool**: The actual scan logic (`scanner.py`) is blocking (synchronous), so it runs in a separate thread pool (`asyncio.to_thread`) to prevent freezing the API.
- **Heartbeat**: Updates a global heartbeat dictionary to prove it's alive.

### 📡 Data Scanner (`scanner.py`)

- **Incremental Fetching**:
  - Checks local JSON files for existing data.
  - Fetches _only_ new candles since the last update using the `start` timestamp parameter.
  - drastically reduces bandwidth usage and API calls.
- **Rate Limiting**: Enforces a 150ms delay between calls to respect Bybit's limit (10 req/s).
- **Persistence**: Saves candles to `backend/data/candles/{symbol}_{tf}.json`.

### 🧠 Strategy Engine (`strategy.py`)

The monitoring strategy is **Heikin-Ashi 4H Flip**.

#### Logic:

1.  **Trend Detection**:
    - Calculates Heikin-Ashi (HA) candles for the **4-Hour (4H)** timeframe.
    - **Bullish**: HA Close > HA Open.
    - **Bearish**: HA Close < HA Open.
2.  **Flip Signal**:
    - Checks the **last two completed** 4H candles.
    - **Long Entry**: Candle A was Bearish -> Candle B is Bullish.
    - **Short Entry**: Candle A was Bullish -> Candle B is Bearish.
3.  **Validation**:
    - Ensures the flip is confirmed by a closed candle (never trades on forming candles).
    - Checks for **Cooldown**: Prevents re-entering the same symbol within X minutes of a loss.

### ⚡ Live Trader (`live_trader.py`)

- **Execution**:
  - Opens positions with **Market Orders** for immediate execution.
  - Sets **Leverage** (default 8x) and **Margin Mode** (Cross/Isolated).
- **Risk Management**:
  - **Stop Loss (SL)**: Calculated based on ATR (Average True Range).
  - **Take Profit (TP)**: 10 split TP levels (TP1...TP10) to scale out of positions.
  - **Trailing Stop**: Activates after TP1 is hit to lock in profits.

---

## 4. The Strategy Details

**Name**: `HA_4H_FLIP_V1`

### Parameters

- **Timeframe**: 4 Hours (used for trend direction).
- **Triggers**: 5-minute scan cycle (checks if the 4H candle just closed and flipped).
- **Indicators**:
  - **Heikin-Ashi**: Smoothed price action to detect trends.
  - **ATR (14)**: Used for dynamic Stop Loss calculation.
  - **RSI (14)** / **EMA (20)**: Calculated but currently used for filtering (optional).

### Entry Conditions

- **LONG**: 4H Trend flips from Bearish 🔴 to Bullish 🟢.
- **SHORT**: 4H Trend flips from Bullish 🟢 to Bearish 🔴.

### Exit Conditions

1.  **Stop Loss Hit**: Price moves against us by `X * ATR`.
2.  **Take Profit Hit**: Price reaches target levels.
3.  **Opposite Signal**: If we are Long and a Short signal appears, we close immediately and flip.

---

## 5. GCP Deployment specifics

### VM Configuration

- **Zone**: `europe-west1-b` (or similar).
- **Machine Type**: `e2-micro` (Free tier eligible) or `e2-small`.
- **Clock**: Synchronized to **UTC+3** (Istanbul/Moscow time) via `/etc/timezone` mapping.

### Docker setup

- **Volume Mapping**:
  - `./backend/data` on host maps to `/app/data` in container.
  - This ensures trade history and candle data persist even if containers restart.
- **Network**:
  - Containers share a bridge network.
  - Nginx proxies port 80 -> Bot port 8000.

### Auto-Recovery

- `restart: always` policy in Docker Compose.
- If the bot crashes, Docker automatically restarts it.
- **State Restoration**: On startup, the bot reads `trades.json` and fetches open positions from Bybit to sync its internal state.

---

## 6. Directory Structure

```
bybit-paper-trader/
├── backend/
│   ├── app/
│   │   ├── main.py          # Entry point, Scheduler
│   │   ├── scanner.py       # Data fetching
│   │   ├── strategy.py      # HA Logic
│   │   ├── live_trader.py   # Execution
│   │   ├── indicators.py    # Math (RSI, ATR, HA)
│   │   └── api/routes.py    # Dashboard API
│   └── data/                # Persistent storage (JSON)
├── dashboard/               # Frontend (HTML/JS)
├── docker-compose.yml       # Orchestration
└── config.py                # Settings (Keys, Timezone)
```

## 7. Troubleshooting

If the bot seems "stuck":

1.  **Check Logs**: `docker-compose logs -f bot`
2.  **Check Heartbeat**: `GET /api/heartbeat` (Should return `healthy: true`)
3.  **Check Files**: Verify `backend/data/candles/*.json` are updating timestamps.
