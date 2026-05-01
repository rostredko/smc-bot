# Building and Docker — Koval

## Dev stack (hot reload)

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build --watch
```

Services:
- `mongo` — MongoDB 7, port 27017
- `backend` — FastAPI with uvicorn reload, port 8000
- `frontend` — Vite dev server, host 5174 → container 5173

## Ports

| Service | Host port | Container port |
|---------|-----------|----------------|
| API | 8000 | 8000 |
| Dashboard | 5174 | 5173 |
| MongoDB | 27017 | 27017 |

## Environment setup

```bash
cp .env.example .env
# Edit .env — add API keys for Binance testnet / WhiteBIT sandbox
```

## Local dev without Docker

```bash
# Python backend
pip install -e ".[dev]"
USE_MONGOMOCK=true uvicorn api.server:app --reload --port 8000

# Frontend
cd dashboard
nvm use  # uses .nvmrc (Node 18)
npm install
npm run dev
```

## Build production images

```bash
docker compose build
docker compose up
```

## Node version

Node version is pinned in `.nvmrc`. Always use `nvm use` before frontend work:
```bash
cd dashboard
nvm use
```

## TA-Lib in Docker

TA-Lib C library is installed in `Dockerfile.backend` via:
```dockerfile
RUN apt-get install -y libta-lib-dev
```

For local dev on macOS: `brew install ta-lib`

## data_cache volume

OHLCV data is cached in the `data_cache` Docker volume, mounted at `/app/data_cache` in the backend container and at `/data/cache` in the mongo container. This persists between container restarts.
