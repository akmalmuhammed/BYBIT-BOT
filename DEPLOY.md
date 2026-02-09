# Live Bybit Trading Bot - GCP Deployment

## Quick Deploy to GCP VM

### 1. Create VM (Compute Engine)

- Machine: e2-micro (free tier) or e2-small
- OS: Ubuntu 22.04 LTS
- Allow HTTP/HTTPS traffic
- Add your SSH key

### 2. SSH into VM

```bash
gcloud compute ssh YOUR_VM_NAME --zone=YOUR_ZONE
```

### 3. Install Docker

```bash
sudo apt update
sudo apt install -y docker.io docker-compose
sudo usermod -aG docker $USER
# Re-login after this
```

### 4. Clone/Upload Project

```bash
# Option A: Clone from git
git clone YOUR_REPO_URL
cd bybit-paper-trader

# Option B: SCP from local
gcloud compute scp --recurse ./bybit-paper-trader VM_NAME:~/ --zone=ZONE
```

### 5. Configure API Keys

```bash
cd bybit-paper-trader
nano .env
```

Add:

```
BYBIT_API_KEY=your_api_key_here
BYBIT_API_SECRET=your_secret_here
BYBIT_TESTNET=false
```

### 6. Start Bot

```bash
docker-compose up -d --build
```

### 7. Enable Live Trading

```bash
curl -X POST http://localhost:8000/api/live/start
```

### 8. Check Status

```bash
curl http://localhost:8000/api/live/status
```

---

## Monitoring

### View Logs

```bash
docker-compose logs -f bot
```

### Check Health

```bash
curl http://localhost:8000/api/health
```

### Emergency Stop

```bash
curl -X POST http://localhost:8000/api/live/emergency-close
curl -X POST http://localhost:8000/api/live/stop
```

---

## Auto-Start on Reboot

Docker Compose with `restart: always` handles this automatically.
