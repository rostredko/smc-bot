# Backtrade Machine

Backtrade Machine is a crypto trading platform with:
- Backtrader-based backtesting engine
- Live paper-trading engine (Binance market data)
- FastAPI backend for orchestration and API
- React dashboard for config, runs, history, and trade analysis
- MongoDB persistence for configs and results
- Default primary strategy: `bt_price_action` (`HTF` structure / `LTF` execution with dynamic timeframe labels)

Current live paper behavior:
- live start requires `exchange`, and the dashboard defaults it to `binance`
- Binance live candles are streamed through `python-binance`
- page reload does not kill an active backtest/live run; runtime state and console history are restored from the backend
- the saved smoke template `live_test_1m_frequent` is a `fast_test_strategy` 1m live-paper template intended for quick dashboard run checks

`README` is intentionally compact.
Detailed architecture, module map, API breakdown, and data flow are in [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md).

## Quick Start (Docker, recommended)

```bash
git clone <repo-url>
cd smc-bot
docker compose up -d --build
```

Services:
- Dashboard (Vite): `http://localhost:5173`
- API (FastAPI): `http://localhost:8000`
- MongoDB: `mongodb://localhost:27017`

Notes:
- `docker-compose.override.yml` is intentionally a no-op so plain `docker compose up` stays stable on Docker Desktop.
- To apply code changes in Docker, rebuild the affected services: `docker compose up -d --build --force-recreate backend frontend`.
- Do not run `docker compose down -v` unless you want to wipe DB/cache volumes.

## Docker Dev Hot Reload

Optional Docker-based dev mode without bind mounts:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
docker compose -f docker-compose.yml -f docker-compose.dev.yml watch backend frontend
```

What it does:
- backend runs `uvicorn --reload`
- `docker compose watch` syncs changed source files into containers
- dependency changes still trigger a rebuild

This is the safest Docker hot-reload path for this repo because direct bind mounts under `/Users` were unstable on this Docker Desktop setup.

## Local Development (without full Docker)

Prerequisites:
- Python `3.10+` (project images use 3.11)
- Node.js `18+` (Docker frontend uses Node 20)
- MongoDB `7+` (or compatible)
- TA-Lib C library (required for indicators)

Setup:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r deps/requirements.txt
cp .env.example .env
```

Run backend:

```bash
cd web-dashboard
uvicorn server:app --host 0.0.0.0 --port 8000 --reload
```

Run frontend (new terminal):

```bash
cd web-dashboard
npm install
npm run dev -- --host 0.0.0.0
```

## Main Commands

CLI:

```bash
python main.py backtest
python main.py live
python main.py test
```

Backend tests:

```bash
./.venv/bin/python -m pytest -q
```

Frontend checks:

```bash
cd web-dashboard
npm run test -- --run
npm run lint
npm run build
```

If local frontend tooling is using an older Node runtime, prefer running the same checks inside the Docker `frontend` container, which uses Node 20.

Live E2E test (internet-dependent, opt-in):

```bash
RUN_LIVE_TESTS=1 ./.venv/bin/python -m pytest -m live -q
```

## Environment Variables

From `.env`:
- `MONGODB_URI` (default `mongodb://localhost:27017`)
- `MONGODB_DB` (default `backtrade`)
- `USE_DATABASE` (`true`/`false`)

Testing helper:
- `USE_MONGOMOCK=true` for in-memory DB in tests.

## Documentation

- Full technical map: [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md)
- Current `bt_price_action` audit: `docs/BT_PRICE_ACTION_AUDIT_20260307.md`
- Deep-dive docs: `docs/`
  - `ENGINE_REVIEW.md`
  - `ENTRY_MECHANISMS_AND_GHOST_TRADE.md`
  - `REAL_LIVE_BINANCE_INTEGRATION_PLAN.md`
  - and other analysis/planning docs

## Disclaimer

Backtesting and paper trading do not guarantee future results. Use risk controls and validate strategies before any real-money deployment.
