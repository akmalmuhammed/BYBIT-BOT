# Update Live Dashboard on GCP (v2)

## Changes Made

1. **Manual Scan Button** - Trigger a scan instantly from the dashboard
2. **Scan Endpoint** - Added `/api/scan/start` to force a scan cycle
3. **HA Status Table** - Shows real-time Heikin Ashi trends (from previous update)
4. **Fetch Logs Filter** - See scan activity (from previous update)

## Files Modified

1. `backend/app/api/routes.py` - Added `/api/scan/start` endpoint and fixed HA logic
2. `dashboard/index.html` - Added "Run Scan" button and handler

## Deployment Steps

### Step 1: Push Changes to GitHub

Run this on your LOCAL machine:

```bash
cd C:\Users\akmal\.gemini\antigravity\scratch\bybit-paper-trader
git add .
git commit -m "Add manual scan button and fix HA status"
git push origin main
```

### Step 2: Update GCP Bot

Run this on your GCP terminal (SSH):

```bash
# 1. SSH into VM
gcloud compute ssh YOUR_VM --zone=YOUR_ZONE

# 2. Update code
cd BYBIT-BOT
git pull origin main

# 3. Restart services
docker-compose down
docker-compose up -d --build
```

### Step 3: Use the New Features

1. Go to http://34.177.84.234/
2. Hard refresh (Ctrl+F5)
3. Click the **"🔍 Run Scan"** button in blue
4. Wait ~30 seconds and check the **"Fetch"** logs or **HA Status** table

## Troubleshooting Empty HA Status

If the HA Status table is still empty:

1. Click **"Run Scan"**
2. Click **"Fetch"** in Activity Log to see if it says "Scanning 15 symbols..."
3. If logs show errors, check container logs on GCP:
   ```bash
   docker logs bybit-live-trader --tail 50
   ```
