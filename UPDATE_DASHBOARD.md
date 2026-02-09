# Update Live Dashboard on GCP

## 🚀 Deployment Steps (Git Workflow)

Since all changes are now pushed to GitHub, deployment is simple:

1.  **SSH into your GCP VM**:

    ```bash
    gcloud compute ssh instance-20250123-181534 --zone=us-central1-a
    ```

2.  **Pull the latest code**:

    ```bash
    cd BYBIT-BOT
    git pull origin main
    ```

3.  **Clean up old state (CRITICAL)**:
    Delete the old flip state file to ensure the new logic starts fresh:

    ```bash
    rm backend/app/data/live_flip_state.json
    ```

4.  **Rebuild and Restart**:

    ```bash
    docker-compose down
    docker-compose up -d --build
    ```

5.  **Verify**:
    - **Dashboard**: http://34.177.84.234/
    - **Debug Endpoint**: http://34.177.84.234/api/debug/scan-info
    - **Fetch Status**: http://34.177.84.234/api/fetch/status

## 📝 Changes Deployed

- **Critical Bug Fixes**:
  - Fixed Double Flip Detection (Strategy vs LiveTrader desync)
  - Fixed 4H Candle Fetching (Now uses only COMPLETED candles)
  - Fixed Testnet/Mainnet config
  - Fixed VWAP reset and Indicator calculations
- **Dashboard Enhancements**:
  - **Fetch Report**: Shows last scan time, duration, and errors.
  - **HA Status**: Shows real-time Heikin Ashi trends and flip readiness.
  - **Logs**: Added "Fetch" filter to monitoring scanning.
