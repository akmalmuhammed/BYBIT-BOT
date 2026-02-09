# Bybit Live Trading Bot

4H Heikin-Ashi Flip Strategy with 10 Take Profit Levels

## Features

- 📊 Scans Top 20 coins by volume
- 🎯 10 Take Profit levels with trailing SL
- 💰 Auto-close at TP10
- 🔴 Live trading on Bybit Futures
- 📈 Paper trading for backtesting

## Quick Deploy to GCP (Debian 12)

### 1. SSH into your VM

```bash
gcloud compute ssh YOUR_VM --zone=YOUR_ZONE
```

### 2. Install Docker

```bash
sudo apt update && sudo apt install -y docker.io docker-compose
sudo usermod -aG docker $USER
# Log out and back in
```

### 3. Clone Repo

```bash
git clone https://github.com/akmalmuhammed/BYBIT-BOT.git
cd BYBIT-BOT
```

### 4. Configure API Keys

```bash
cp backend/.env.example backend/.env
nano backend/.env
```

Add your Bybit API keys:

```
BYBIT_API_KEY=your_key
BYBIT_API_SECRET=your_secret
BYBIT_TESTNET=false
```

### 5. Start Bot

```bash
docker-compose up -d --build
```

### 6. Enable Live Trading

```bash
curl -X POST http://localhost:8000/api/live/start
```

### 7. Check Status

```bash
curl http://localhost:8000/api/live/status
```

## API Endpoints

| Endpoint                    | Method | Description         |
| --------------------------- | ------ | ------------------- |
| `/api/live/start`           | POST   | Start live trading  |
| `/api/live/stop`            | POST   | Stop live trading   |
| `/api/live/status`          | GET    | Get status          |
| `/api/live/emergency-close` | POST   | Close all positions |

## Settings

- Trade Size: $10
- Max Positions: 8
- Leverage: 8x
- Strategy: BASE (4H HA Flip)
