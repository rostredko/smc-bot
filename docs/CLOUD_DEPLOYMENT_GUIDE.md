# Cloud Deployment Guide for smc-bot

This document describes how to prepare the project for deployment to a cloud server, set up CI/CD from GitHub, and run a shared test environment for a few users (e.g., you and a friend running strategies in parallel). It includes provider research, cost estimates, and step-by-step instructions.

---

## 1. Pre-Commit Checklist (Code Ready for Deploy)

Before pushing changes and deploying, ensure:

```bash
# 1. Run all tests
./.venv/bin/python -m pytest tests/ -q

# 2. Build frontend
cd web-dashboard && npm run build

# 3. (Optional) Verify Docker stack locally
docker compose up -d --build
# Manual check: backtest start, live start, results, history
docker compose down
```

**Expected:** 273 passed, 1 skipped; frontend builds without errors; Docker stack starts and core flows work.

---

## 2. Cloud Provider Comparison

| Provider | Tier | Cost | Specs | Docker | Notes |
|----------|------|------|-------|--------|-------|
| **Oracle Cloud** | Always Free | **$0** | 4 OCPU, 24 GB RAM (ARM) or 1 OCPU, 1 GB (AMD) | Yes | Best value; ARM needs multi-arch images |
| **Hetzner Cloud** | CX22 | ~€3.79/mo | 2 vCPU, 4 GB RAM, 40 GB NVMe | Yes | Cheapest paid; EU-centric |
| **DigitalOcean** | Basic | $6–24/mo | 1–2 vCPU, 1–4 GB RAM | Yes | Good DX, managed options |
| **AWS** | Free tier / EC2 | $0–70+/mo | 1 vCPU, 1 GB (t2.micro) | Yes | Complex; free tier limited |
| **Railway** | Hobby | $5/mo | Shared | Yes | Simple; good for quick tests |
| **Fly.io** | Free tier | $0 (limits) | Shared | Yes | Good for small apps |

### Recommendation for smc-bot

- **Minimal cost (weeks–months trial):** **Oracle Cloud Always Free** — 4 OCPU, 24 GB RAM on ARM. Enough for backend + frontend + MongoDB + 2 users.
- **Paid, simple:** **Hetzner CX22** (~€4/mo) — straightforward VPS, Docker-friendly.
- **Paid, managed:** **DigitalOcean** — if you prefer managed DB and nicer tooling.

---

## 3. Oracle Cloud Always Free Tier (Detailed)

### 3.1 Resources

- **VM.Standard.A1.Flex (ARM):** Up to 4 OCPUs, 24 GB RAM (flexible split, e.g. 2 OCPU + 12 GB)
- **VM.Standard.E2.1.Micro (AMD):** 1 OCPU, 1 GB RAM — too small for full stack
- **Storage:** 200 GB block, 20 GB object
- **Network:** 10 Mbps load balancer, VCN included

### 3.2 ARM Compatibility

- **Python 3.11-slim:** ARM images available
- **Node 20-alpine:** ARM images available
- **MongoDB 7:** ARM images available
- **TA-Lib:** Build from source (already in Dockerfile; works on ARM)

Use multi-arch builds if you develop on x86 and deploy on ARM:

```bash
docker buildx create --use
docker buildx build --platform linux/amd64,linux/arm64 -t myimage:latest .
```

### 3.3 Limitations

- ARM instances can have availability constraints in some regions
- Credit card required (no charges for Always Free resources)
- Account setup can be stricter than other providers

---

## 4. Deployment Architecture

### 4.1 Local vs Cloud

| Aspect | Local | Cloud (Test/Prod) |
|--------|-------|-------------------|
| Frontend | Vite dev server (5174) or built dist | Built dist served by FastAPI or Nginx |
| Backend | localhost:8000 | Behind Nginx, port 80/443 |
| MongoDB | localhost:27017 | Same host or managed DB |
| SSL | None | Let's Encrypt (Certbot) |
| API base | localhost:8000 | Same origin (relative URLs) |

### 4.2 Production Docker Stack

```
[Internet] → [Nginx :80/:443] → [Backend :8000]
                    ↓
            [Frontend static / dist]
                    ↓
            [MongoDB :27017]
```

- Nginx: reverse proxy, SSL termination, static files (or proxy to FastAPI serving dist)
- Backend: FastAPI + uvicorn
- MongoDB: in Docker or external

### 4.3 Frontend API Base for Production

The frontend uses `API_BASE` in `web-dashboard/src/shared/api/config.ts`. For production:

- **Option A:** Use relative URLs (`""` or `"/"`) so API calls go to the same origin.
- **Option B:** Use build-time env: `VITE_API_BASE=https://your-domain.com` and wire it in `config.ts`.

Recommended: relative URLs so one domain serves both UI and API.

---

## 5. GitHub Actions CI/CD

### 5.1 Workflow: Deploy on Push to `main`

1. **Build & test** on every push/PR
2. **Deploy** only on push to `main` (or a `deploy` branch)

### 5.2 Required Secrets

| Secret | Description |
|--------|-------------|
| `DEPLOY_HOST` | VPS IP or hostname |
| `DEPLOY_USER` | SSH user (e.g. `ubuntu`, `deployer`) |
| `DEPLOY_SSH_KEY` | Private SSH key for deployment |

### 5.3 Example Workflow

```yaml
# .github/workflows/deploy.yml
name: Deploy

on:
  push:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install -r deps/requirements.txt
      - run: python -m pytest tests/ -q
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
      - run: cd web-dashboard && npm ci && npm run build

  deploy:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Deploy via SSH
        uses: appleboy/ssh-action@v1
        with:
          host: ${{ secrets.DEPLOY_HOST }}
          username: ${{ secrets.DEPLOY_USER }}
          key: ${{ secrets.DEPLOY_SSH_KEY }}
          script: |
            cd /opt/smc-bot
            git pull origin main
            docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

### 5.4 Skip Deploy

Add `[skip ci]` or `[ci skip]` to a commit message to skip the workflow.

---

## 6. Server Setup (VPS)

### 6.1 Initial Setup

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# Install Docker Compose plugin
sudo apt install docker-compose-plugin -y

# Clone repo
sudo mkdir -p /opt/smc-bot
sudo chown $USER:$USER /opt/smc-bot
cd /opt/smc-bot
git clone <your-repo-url> .
```

### 6.2 Production Compose Override

Create `docker-compose.prod.yml`:

```yaml
# docker-compose.prod.yml
services:
  backend:
    environment:
      MONGODB_URI: mongodb://mongo:27017
      MONGODB_DB: backtrade
      TZ: UTC
    # Add production-specific env if needed

  frontend:
    # For production: serve built static from backend or nginx
    # Option: remove frontend service, build dist and mount into backend
    profiles:
      - dev  # Only run in dev
```

For production, you can either:
- Build frontend in CI and copy `dist/` into the backend image, or
- Serve `dist/` via Nginx.

### 6.3 Nginx + SSL (Let's Encrypt)

```bash
# Install Certbot
sudo apt install certbot python3-certbot-nginx -y

# Get certificate (replace with your domain)
sudo certbot certonly --standalone -d smc.yourdomain.com

# Nginx config
# /etc/nginx/sites-available/smc-bot
server {
    listen 80;
    server_name smc.yourdomain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl;
    server_name smc.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/smc.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/smc.yourdomain.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

---

## 7. Environment Differences

| Variable | Local | Test (Cloud) | Prod |
|----------|-------|--------------|------|
| `MONGODB_URI` | mongodb://localhost:27017 | mongodb://mongo:27017 | mongodb://mongo:27017 |
| `MONGODB_DB` | backtrade | backtrade | backtrade |
| `USE_DATABASE` | true | true | true |
| `TZ` | Europe/Kyiv | UTC | UTC |

Keep sensitive config (API keys, etc.) in GitHub Secrets or a `.env` file on the server (never committed).

---

## 8. Multi-User Considerations

- **Shared instance:** One backend and MongoDB instance; multiple users use the same dashboard.
- **Configs:** User configs are stored per name; ensure naming is unique per user (e.g. `user1_bt_1m`, `user2_bt_4h`).
- **Concurrent runs:** Backend supports concurrent backtests and live runs; each run has a unique ID.
- **Resource limits:** For 2 users, 4 GB RAM is usually enough; 2–4 OCPU on Oracle ARM is fine.

---

## 9. Step-by-Step Deployment (Oracle Cloud Example)

1. **Create Oracle Cloud account** (Always Free)
2. **Create VM:** Ubuntu 22.04, VM.Standard.A1.Flex (e.g. 2 OCPU, 12 GB RAM)
3. **Open ports:** 22 (SSH), 80, 443 in security list
4. **SSH:** `ssh ubuntu@<public-ip>`
5. **Install Docker + Docker Compose** (see 6.1)
6. **Clone repo** to `/opt/smc-bot`
7. **Create `.env`** with `MONGODB_URI`, `MONGODB_DB`, etc.
8. **Build and run:** `docker compose up -d --build`
9. **Configure Nginx + Certbot** (see 6.3)
10. **Add GitHub Secrets** and workflow (see 5)

---

## 10. Rollback

If a deploy breaks:

```bash
cd /opt/smc-bot
git log -1
git checkout <previous-commit>
docker compose up -d --build
```

Or use `git revert` and push to trigger a new deploy.

---

## 11. Future Improvements

- [ ] Add `docker-compose.prod.yml` with production-specific config
- [ ] Add `VITE_API_BASE` env or relative URLs for production frontend
- [ ] Multi-stage Dockerfile for frontend (build + serve via nginx)
- [ ] Health checks in compose for backend and mongo
- [ ] Optional: managed MongoDB (e.g. Atlas) for production
- [ ] Optional: GitHub Actions build and push images to registry, then pull on server

---

## References

- [Oracle Always Free Resources](https://docs.oracle.com/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm)
- [Docker on Oracle Cloud Free Tier](https://medium.com/@dsouzasunny1436/setting-up-docker-and-docker-compose-on-oracle-clouds-always-free-tier-instance-1e22dc976f12)
- [GitHub Actions SSH deploy](https://github.com/appleboy/ssh-action)
- [Nginx + Let's Encrypt](https://certbot.eff.org/instructions)
