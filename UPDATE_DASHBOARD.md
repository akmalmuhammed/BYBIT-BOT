# Update Live Dashboard on GCP

## Changes Made

Added two new features to the live dashboard:

1. **HA Status Table** - Shows real-time Heikin Ashi trends for all symbols
2. **Fetch Logs Filter** - Filter activity logs to see data fetching events

## Files Modified

1. `backend/app/api/routes.py` - Added `/api/ha-status` endpoint
2. `dashboard/index.html` - Added HA status section and fetch logs filter

## Deployment Steps

### Option 1: Git Push & Pull (Recommended)

```bash
# On your local machine
cd C:\Users\akmal\.gemini\antigravity\scratch\bybit-paper-trader
git add .
git commit -m "Add HA status and fetch logs to dashboard"
git push origin main

# SSH into GCP VM
gcloud compute ssh YOUR_VM --zone=YOUR_ZONE

# Pull updates
cd BYBIT-BOT
git pull origin main

# Restart containers
docker-compose down
docker-compose up -d --build
```

### Option 2: Manual File Upload

**Upload these 2 files to your GCP VM:**

1. `backend/app/api/routes.py`
2. `dashboard/index.html`

```bash
# From your local machine
gcloud compute scp backend/app/api/routes.py YOUR_VM:~/BYBIT-BOT/backend/app/api/routes.py --zone=YOUR_ZONE
gcloud compute scp dashboard/index.html YOUR_VM:~/BYBIT-BOT/dashboard/index.html --zone=YOUR_ZONE

# SSH into VM
gcloud compute ssh YOUR_VM --zone=YOUR_ZONE

# Restart containers
cd BYBIT-BOT
docker-compose down
docker-compose up -d --build
```

### Option 3: Direct Edit on VM

```bash
# SSH into GCP VM
gcloud compute ssh YOUR_VM --zone=YOUR_ZONE

# Edit routes.py
cd BYBIT-BOT/backend/app/api
nano routes.py
# Add the /ha-status endpoint at the end (see below)

# Edit dashboard
cd ~/BYBIT-BOT/dashboard
nano index.html
# Add HA status section and update JavaScript (see below)

# Restart
cd ~/BYBIT-BOT
docker-compose down
docker-compose up -d --build
```

## New Endpoint Code

Add this to `backend/app/api/routes.py` at the end (after the `/logs` endpoint):

```python
@router.get("/ha-status")
async def get_ha_status():
    """Get current HA status for all monitored symbols."""
    from ..live_trader import get_live_trader
    from ..indicators import calculate_heikin_ashi, get_ha_trend
    from datetime import datetime, timezone

    trader = get_live_trader()
    symbols = scanner.get_top_futures_symbols()

    ha_status = []

    for symbol in symbols[:20]:  # Top 20 symbols
        try:
            # Get 4H candles
            df = scanner.load_candles(symbol, "240")
            if df.empty:
                continue

            # Calculate HA
            df_ha = calculate_heikin_ashi(df.copy())
            current_trend = get_ha_trend(df_ha)

            # Get last candle time
            last_candle_time = df.iloc[-1]['timestamp']
            if hasattr(last_candle_time, 'isoformat'):
                last_candle_time = last_candle_time.isoformat()

            # Get recorded state from live trader
            recorded_state = trader.ha_states.get(symbol, {}).get("state", "unknown")

            ha_status.append({
                "symbol": symbol,
                "current_trend": current_trend,
                "recorded_state": recorded_state,
                "last_update": last_candle_time,
                "is_flip_ready": current_trend != recorded_state if recorded_state != "unknown" else False
            })
        except Exception as e:
            continue

    return {"ha_status": ha_status, "count": len(ha_status)}
```

## Dashboard Changes

### 1. Add "Fetch" filter button (line ~251)

Change:

```html
<button class="filter-btn" data-filter="SL">SL Events</button>
<button class="filter-btn" data-filter="SYSTEM">System</button>
```

To:

```html
<button class="filter-btn" data-filter="SL">SL Events</button>
<button class="filter-btn" data-filter="SCAN">Fetch</button>
<button class="filter-btn" data-filter="SYSTEM">System</button>
```

### 2. Add HA Status section (after line ~257, after the grid-2col closing div)

```html
<!-- HA Status Section -->
<div class="section">
  <div class="section-title">📊 Heikin Ashi Status (4H)</div>
  <div id="ha-status-table">
    <p class="empty">Loading HA status...</p>
  </div>
</div>
```

### 3. Add fetchHAStatus function (before refreshData function, around line ~437)

```javascript
// Fetch HA Status
async function fetchHAStatus() {
  try {
    const res = await fetch(`${API_BASE}/ha-status`);
    const data = await res.json();

    const container = document.getElementById("ha-status-table");
    const haList = data.ha_status || [];

    if (haList.length === 0) {
      container.innerHTML = '<p class="empty">No HA data available</p>';
      return;
    }

    let html = `<table>
            <tr>
                <th>Symbol</th>
                <th>Current Trend</th>
                <th>Recorded State</th>
                <th>Status</th>
                <th>Last Update</th>
            </tr>`;

    haList.forEach((ha) => {
      const trendClass = ha.current_trend === "bullish" ? "long" : "short";
      const recordedClass = ha.recorded_state === "bullish" ? "long" : "short";
      const statusText = ha.is_flip_ready ? "🔄 FLIP READY" : "✓ Tracking";
      const statusClass = ha.is_flip_ready ? "pnl-positive" : "";

      html += `<tr>
                <td><strong>${ha.symbol}</strong></td>
                <td class="${trendClass}">${ha.current_trend.toUpperCase()}</td>
                <td class="${recordedClass}">${ha.recorded_state.toUpperCase()}</td>
                <td class="${statusClass}">${statusText}</td>
                <td>${formatTime(ha.last_update)}</td>
            </tr>`;
    });

    html += "</table>";
    container.innerHTML = html;
  } catch (e) {
    console.error("HA status fetch failed:", e);
  }
}
```

### 4. Update refreshData function (around line ~438)

Change:

```javascript
function refreshData() {
  fetchStatus();
  fetchPositions();
  fetchLogs();
}
```

To:

```javascript
function refreshData() {
  fetchStatus();
  fetchPositions();
  fetchLogs();
  fetchHAStatus();
}
```

## Verify Deployment

After deployment, visit http://34.177.84.234/ and you should see:

- ✅ New "Fetch" filter button in Activity Log
- ✅ New "Heikin Ashi Status (4H)" section at the bottom
- ✅ Table showing all symbols with their HA trends
- ✅ "FLIP READY" indicator when trends change

## Troubleshooting

If the dashboard doesn't update:

```bash
# Check container logs
docker-compose logs -f

# Hard refresh browser (Ctrl+Shift+R)

# Verify files were updated
docker exec bybit-live-trader cat /app/app/api/routes.py | grep "ha-status"
docker exec bybit-dashboard cat /usr/share/nginx/html/index.html | grep "HA Status"
```
