# Backtrade Machine

Backtrade Machine is a crypto trading platform with:
- Backtrader-based backtesting engine
- Live paper-trading engine (Binance market data)
- FastAPI backend for orchestration and API
- React dashboard for config, runs, history, and trade analysis
- MongoDB persistence for configs and results

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
- `docker-compose.override.yml` enables hot-reload for local development.
- Do not run `docker compose down -v` unless you want to wipe DB/cache volumes.

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
- Deep-dive docs: `docs/`
  - `ENGINE_REVIEW.md`
  - `ENTRY_MECHANISMS_AND_GHOST_TRADE.md`
  - `REAL_LIVE_BINANCE_INTEGRATION_PLAN.md`
  - and other analysis/planning docs

## Disclaimer

Backtesting and paper trading do not guarantee future results. Use risk controls and validate strategies before any real-money deployment.
