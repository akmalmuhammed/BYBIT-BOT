# Troubleshooting Guide: Verify Data Fetching on VM

Since you cannot see the internal logs easily, follow these steps on your GCP VM to verify that data is being fetched and stored correctly.

## 1. Check the Logs

The most direct way to see if the fetcher is working is to check the real-time logs of the bot container.

```bash
cd ~/bybit-paper-trader
docker-compose logs -f bot
```

**What to look for:**

- `📊 Scanning 15 symbols...` (should appear every 5 minutes)
- `✅ Scan complete in X.Xs`
- `💓 System alive` (should appear every 1 minute)

## 2. Check Data Files

The bot saves candle data to JSON files. You can check if these files are being updated.

```bash
# List files in the candles directory, sorted by modification time (newest at bottom)
ls -lt backend/data/candles/ | head -n 10
```

**What to look for:**

- The timestamps on the files should be very recent (within the last 5-10 minutes).
- If files are old (e.g., from hours ago), the fetcher is stuck.

## 3. Use the Debug API

I added a specific debug endpoint to check the internal state. You can call it from the VM itself using `curl`.

```bash
curl -s http://localhost:8000/api/debug/scan-info | python3 -m json.tool
```

**What to look for in the JSON output:**

- `"last_scan_time"`: Should be recent (UTC+3 time).
- `"scanner": { "last_scan_duration_seconds": ... }`: Should be > 0.
- `"heartbeat": { "healthy": true }`: Must be true.

## 4. Check Heartbeat

Simple health check:

```bash
curl -s http://localhost:8000/api/heartbeat | python3 -m json.tool
```

If `"healthy": false`, the scheduler has stalled.

## Summary

- **Logs** show _activity_.
- **Files** show _persistence_.
- **API** shows _internal state_.

If all three look good, the data flow is working perfectly.
