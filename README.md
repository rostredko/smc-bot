# Backtrade Machine

Production-ready Python backtesting framework for crypto trading strategies. Binance integration, risk management, web dashboard.

**Status**: ✅ Production Ready | **Engine**: Backtrader + TA-Lib

---

## Prerequisites

| Requirement | Version | Purpose |
|-------------|---------|---------|
| Python | 3.8+ | Core runtime |
| MongoDB | 4.0+ | Config, results, dashboard |
| Node.js | 16+ | Web dashboard frontend |
| TA-Lib | 0.6+ | Technical indicators (C library) |

---

## Quick Start (Docker — all-in-one)

```bash
git clone <repo-url>
cd smc-bot

docker compose up -d
```

Starts MongoDB, backend, and frontend (dev mode). Open **http://localhost:5173**.

**Hot-reload (dev):** `docker-compose.override.yml` mounts source code — changes in backend/frontend apply without rebuild. Backend uses `uvicorn --reload`, frontend uses Vite HMR.

---

## Quick Start (Docker for MongoDB only)

```bash
git clone <repo-url>
cd smc-bot

python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

pip install -r deps/requirements.txt
cp .env.example .env

docker compose up -d mongo   # только MongoDB
cd web-dashboard && npm install && npm run build
python server.py             # http://localhost:8000
```

---

## Setup from Scratch (without Docker)

Full guide for running the project when Docker is not available.

### 1. System dependencies

**macOS (Homebrew):**
```bash
brew install python@3.11
brew install mongodb-community    # or: brew tap mongodb/brew && brew install mongodb-community
brew install ta-lib               # TA-Lib C library
brew install node
```

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install python3.11 python3.11-venv python3-pip mongodb build-essential wget nodejs npm

# TA-Lib: wget http://prdownloads.sourceforge.net/ta-lib/ta-lib-0.4.0-src.tar.gz
# tar -xzf ta-lib-0.4.0-src.tar.gz && cd ta-lib && ./configure --prefix=/usr && make && sudo make install
```

**Windows:**
- Install Python 3.11 from python.org
- Install MongoDB from mongodb.com/try/download/community
- Install TA-Lib: download wheel from https://www.lfd.uci.edu/~gohlke/pythonlibs/#ta-lib or use `pip install TA-Lib` (if binary available)
- Install Node.js from nodejs.org

### 2. MongoDB (local or Atlas)

**Option A: Local MongoDB**
```bash
# macOS (Homebrew)
brew services start mongodb-community

# Ubuntu
sudo systemctl start mongod

# Verify
mongosh --eval "db.runCommand({ping:1})"
```

**Option B: MongoDB Atlas (cloud)**
1. Create free cluster at mongodb.com/atlas
2. Get connection string (e.g. `mongodb+srv://user:pass@cluster.mongodb.net/`)
3. Use it in `.env` as `MONGODB_URI`

### 3. Project setup

```bash
cd smc-bot

# Virtual environment
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# Python deps (includes TA-Lib Python bindings)
pip install -r deps/requirements.txt

# Environment
cp .env.example .env
# Edit .env: MONGODB_URI (default mongodb://localhost:27017), MONGODB_DB (default backtrade)
```

### 4. Web dashboard (optional)

```bash
cd web-dashboard
pip install -r requirements.txt   # if not already from project root
npm install
npm run build
```

### 5. Run

**CLI backtest:**
```bash
python main.py backtest   # Config from MongoDB
```

**Web dashboard:**
```bash
cd web-dashboard
python server.py
# Open http://localhost:8000
```

**Tests:**
```bash
python main.py test
```

---

## Usage

### CLI
- `python main.py backtest` — run backtest (config from MongoDB)
- `python main.py live` — live trading (experimental)
- `python main.py test` — run tests

### Web dashboard
- Config, strategies, backtest runs — all in UI
- Results saved to MongoDB
- Edit config via dashboard; CLI uses same config

### Config (MongoDB only)
Stored in `app_config` collection. Edit via dashboard or `POST /config` / `POST /config/live`.

---

## Data & architecture

- **Data**: Binance USD-M Futures (ccxt), cached in `data_cache/`
- **Indicators**: TA-Lib (RSI, ADX, EMA, ATR)
- **Strategy**: PriceActionStrategy — candlestick patterns (Hammer, Engulfing, etc.), trend/RSI/ADX filters
- **Results**: MongoDB (`backtests`, `app_config`, `user_configs`)

---

## Project structure

```
smc-bot/
├── main.py                    # CLI entry
├── docker-compose.yml         # MongoDB + backend + frontend
├── docker-compose.override.yml # Dev: mount source, hot-reload
├── Dockerfile.backend         # Python + TA-Lib
├── Dockerfile.frontend        # Node, Vite dev
├── engine/                    # Backtrader engine, data loader
├── strategies/                # Trading strategies (bt_price_action)
├── db/                        # MongoDB repositories
├── web-dashboard/             # FastAPI + React
├── deps/requirements.txt
└── .env                       # MONGODB_URI, MONGODB_DB
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `ModuleNotFoundError: TA-Lib` | Install TA-Lib C library first, then `pip install TA-Lib` |
| `MongoDB connection failed` | Start MongoDB locally or set `MONGODB_URI` for Atlas |
| Port 8000 in use | `lsof -ti:8000 \| xargs kill -9` (macOS/Linux) |
| No signals from strategy | Check config in dashboard, adjust filters |
| Docker: network ambiguous | `docker network prune` or remove duplicate `smc-bot_default` |

---

## CI (GitHub Actions)

- **Frontend:** npm ci, lint, build
- **Backend:** pip install, pytest (USE_MONGOMOCK=true, no MongoDB required)

---

## Risk disclaimer

Backtesting does not guarantee future results. Live trading is experimental. Use sandbox mode first. Authors accept no responsibility for financial losses.
