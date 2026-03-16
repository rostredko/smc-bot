# Backtrade Machine - Project Structure

## 1. Scope

This document is the detailed technical map of the repository:
- directory layout and responsibilities
- runtime topology
- backend API surface
- data flow for backtest/live modes
- persistence model
- testing matrix

If you need quick onboarding only, use [README.md](README.md).

## 2. Runtime Topology

Primary local/dev runtime is Docker Compose:
- `mongo` (`mongo:7`) on `27017`
- `backend` (`Dockerfile.backend`) on `8000`
- `frontend` (`Dockerfile.frontend`) on `5173`

Files:
- `docker-compose.yml`: base services and named volumes (`mongo_data`, `data_cache`)
- `docker-compose.override.yml`: intentionally no-op; keeps plain `docker compose up` stable and avoids broken Desktop bind-mount behavior
- `docker-compose.dev.yml`: optional Docker watch/hot-reload overlay

## 3. Repository Map

```text
smc-bot/
├── main.py
├── VERSION
├── Dockerfile.backend
├── Dockerfile.frontend
├── docker-compose.yml
├── docker-compose.override.yml
├── deps/
│   └── requirements.txt
├── db/
│   ├── connection.py
│   └── repositories/
│       ├── app_config_repository.py
│       ├── backtest_repository.py
│       └── user_config_repository.py
├── engine/
│   ├── base_engine.py
│   ├── binance_account_client.py
│   ├── bt_oco_patch.py
│   ├── bt_backtest_engine.py
│   ├── bt_live_engine.py
│   ├── bt_analyzers.py
│   ├── data_loader.py
│   ├── execution_settings.py
│   ├── live_ws_client.py
│   ├── live_data_feed.py
│   ├── trade_metrics.py
│   ├── trade_narrator.py
│   └── logger.py
├── strategies/
│   ├── base_strategy.py
│   ├── bt_price_action.py
│   ├── fast_test_strategy.py
│   ├── market_structure.py
│   └── helpers/
│       └── risk_manager.py
├── web-dashboard/
│   ├── server.py
│   ├── api/
│   │   ├── models.py
│   │   ├── state.py
│   │   └── logging_handlers.py
│   ├── services/
│   │   ├── strategy_runtime.py
│   │   └── result_mapper.py
│   ├── src/
│   │   ├── app/providers/
│   │   ├── pages/dashboard/ui/
│   │   ├── widgets/
│   │   ├── features/
│   │   ├── entities/
│   │   └── shared/
│   ├── package.json
│   └── vite.config.ts
├── tests/
└── docs/
```

## 4. Backend Architecture

### 4.1 API and Orchestration (`web-dashboard/server.py`)

`server.py` is the API boundary and imports models, state, and logging utilities from `web-dashboard/api/`. It is responsible for:
- configuration CRUD
- backtest lifecycle
- live paper lifecycle
- runtime snapshot / dashboard reload recovery
- OHLCV + indicators API
- result/history retrieval and deletion
- WebSocket log broadcasting

**API layer (`web-dashboard/api/`):**
- `api/models.py` — Pydantic models: `BacktestConfig`, `BacktestRequest`, `BacktestStatus`
- `api/state.py` — shared state: `running_backtests`, `live_trading_state`, `active_connections`, `active_console_state`; helpers: `_latest_running_backtest_run_id()`, `_has_active_runtime()`
- `api/logging_handlers.py` — `RunLogCollector` (in-memory tail capture), `attach_run_log_handlers()`, `detach_run_log_handlers()`, `attach_run_log_metadata()`

Recent structure changes:
- runtime strategy resolution moved to `web-dashboard/services/strategy_runtime.py`
- result/trade/equity mapping moved to `web-dashboard/services/result_mapper.py`
- noisy OHLCV messages moved to debug and WS-suppressed for cleaner live output
- dashboard market-structure math now reuses the shared `strategies/market_structure.py` BOS helper to stay aligned with the trading strategy

### 4.2 Application Services (`web-dashboard/services/`)

- `strategy_runtime.py`
  - `resolve_strategy_class(strategy_name)`
  - `build_runtime_strategy_config(config)`
  - centralizes runnable strategy discovery and runtime risk param injection

- `result_mapper.py`
  - `map_backtest_trades(...)`
  - `map_live_trades(...)`
  - `build_equity_series(..., max_points)`
  - `build_backtest_metrics_doc(...)`
  - `build_live_metrics_doc(...)`
  - centralizes API/storage payload shaping

### 4.3 Engine Layer (`engine/`)

- `base_engine.py`
  - shared Backtrader setup (`Cerebro`, broker, commission/leverage)
  - stable timeframe ordering helper for MTF strategies (`data0=LTF`, `data1=HTF`)
  - applies OCO patch early (`bt_oco_patch.apply_oco_guard()`)
  - applies exchange-aware paper fee settings

- `bt_oco_patch.py`
  - patches Backtrader broker internals to prevent same-bar OCO double execution
  - also improves cancel behavior for submitted orders (prevents orphan exits)

- `bt_backtest_engine.py`
  - historical data loading via `DataLoader`
  - analyzer registration
  - normalized metrics output
  - forced final close synthesis for open positions at the end of backtests

- `bt_live_engine.py`
  - warm-up from REST (`fetch_recent_bars`)
  - live feed via exchange-selected WS client + queue + Backtrader live feed
  - analyzer output parity with backtest
  - graceful stop and thread join
  - same lower-TF-first feed ordering as backtest

- `data_loader.py`
  - ccxt exchange bootstrap (Binance futures/spot)
  - CSV cache in `data_cache/` with staleness invalidation
  - OHLCV fetch and shaping

- `execution_settings.py`
  - shared execution-mode and fee normalization for backtest/live
  - current Binance paper defaults for spot/futures

- `binance_account_client.py`
  - signed Binance commission lookup groundwork for future real trading

- `live_ws_client.py`
  - live stream transport layer
  - Binance public kline streaming via `python-binance`
  - pushes only closed candles into queue
  - reconnect/backoff and queue overflow handling

- `live_data_feed.py`
  - queue-driven Backtrader live feed adapter

- `bt_analyzers.py`
  - `TradeListAnalyzer` (detailed trade metadata)
  - `EquityCurveAnalyzer`
  - merges funding adjustments into realized trade PnL while keeping gross PnL fields

- `trade_metrics.py`
  - closed-trade-only metrics builder used by backtest/live engines
  - keeps summary metrics aligned with persisted trade list

- `trade_narrator.py`
  - strategy-agnostic trade narrative builder used from strategy base class

- `logger.py`
  - logging setup
  - WS queue handler
  - `suppress_ws_logging()` context manager for noisy internals

### 4.4 Strategy Layer (`strategies/`)

- `base_strategy.py`
  - shared order lifecycle (`notify_order`, `notify_trade`)
  - SL/TP OCO handling
  - trailing/breakeven update flow
  - orphan cleanup and drawdown stop checks
  - funding cashflow application for long/short positions

- `bt_price_action.py` (primary strategy)
  - `HTF` `MarketStructure` indicator with confirmed fractals and BOS-only structure state
  - `LTF` execution logic with TA-Lib patterns: hammer/inverted hammer/shooting star/hanging man/engulfing
  - default structural flow: `HTF structure -> POI -> optional LTF CHoCH -> LTF pattern entry`
  - structural SL from the active `HTF` level + `ATR_<HTF>` buffer
  - TP from RR and optional clamp to the opposing `HTF` structural level
  - dynamic narrative/formula labels derived from the real feed timeframe (`1D`, `4H`, `15M`, etc.)
  - optional EMA/RSI/ADX filters for legacy/backward-compatible configs
  - safe bool parsing for legacy configs that may store `"true"` / `"false"` strings

- `market_structure.py`
  - pure shared BOS/fractal helper used by both the Backtrader strategy and the dashboard backend
  - keeps confirmed swing detection and BOS state transitions in one source of truth

- `fast_test_strategy.py`
  - deterministic high-frequency strategy for live pipeline verification
  - time-based forced exits and optional auto-stop after N trades
  - current `live_test_1m_frequent` smoke template uses this strategy on a single `1m` feed

- `helpers/risk_manager.py`
  - position sizing with leverage cap and drawdown-aware cap
  - `position_cap_adverse` protection parameter

### 4.5 Persistence Layer (`db/`)

- `connection.py`
  - Mongo bootstrap (`MONGODB_URI`, `MONGODB_DB`)
  - `USE_MONGOMOCK` support for tests
  - indexes initialization (`backtests`)

- `repositories/backtest_repository.py`
  - save/get/list/delete backtest and live run docs
  - `is_live` persistence
  - paginated history projection

- `repositories/user_config_repository.py`
  - config templates CRUD
  - priority ordering via special doc `_id="__template_order__"`

- `repositories/app_config_repository.py`
  - app-level config docs (`default`, `live`)

## 5. API Surface (`web-dashboard/server.py`)

### 5.1 System
- `GET /` - dashboard index or API fallback payload
- `GET /health` - health/timestamp
- `GET /strategies` - runnable dashboard strategies + schema
- `GET /api/runtime/state` - active backtest/live state + buffered console output
- `WS /ws` - live console stream

### 5.2 Config
- `GET /config`
- `POST /config`
- `GET /config/live`
- `POST /config/live`

### 5.3 User Templates
- `GET /api/user-configs`
- `GET /api/user-configs/{name}`
- `POST /api/user-configs/{name}`
- `DELETE /api/user-configs/{name}`
- `PUT /api/user-configs/reorder`

### 5.4 Backtest Lifecycle
- `POST /backtest/start`
- `GET /backtest/status/{run_id}`
- `GET /backtest/results/{run_id}`
- `DELETE /backtest/{run_id}`

### 5.5 Results and History
- `GET /results`
- `GET /results/{filename}`
- `GET /api/backtest/history`
- `DELETE /api/backtest/history/{filename}` (accepts `run_id` with or without `.json`)

### 5.6 Live Lifecycle
- `POST /api/live/start`
- `POST /api/live/stop`
- `GET /api/live/status`
- `GET /api/runtime/state`

### 5.7 Market Data
- `GET /api/symbols/top`
- `POST /api/ohlcv/cache/clear`
- `GET /api/ohlcv`

`/api/ohlcv` notes:
- supports optional indicator computation (EMA/RSI/ADX/ATR)
- uses DataLoader when `backtest_start` and `backtest_end` are provided
- uses in-memory LRU cache for non-backtest queries

## 6. Frontend Structure (`web-dashboard/src`)

Frontend follows a layered folder split close to Feature-Sliced style.

- `app/`
  - providers and orchestration
  - `BacktestProvider` composes `ConfigProvider`, `ConsoleProvider`, `ResultsProvider`

- `pages/dashboard/ui/DashboardPage.tsx`
  - top-level dashboard composition

- `widgets/`
  - `config-panel`
  - `console-output`
  - `results-panel`
  - `backtest-history`

- `features/`
  - `trade-details` modal and focused feature logic

- `entities/`
  - reusable trade-level UI (`TradeAnalysisChart`, `TradeOHLCVChart`)

- `shared/`
  - API constants (`API_BASE`)
  - validation
  - shared types
  - reusable UI bits

Build/runtime notes:
- `vite.config.ts` injects `__APP_VERSION__` and `__BUILD_NUMBER__` from `VERSION`/env
- production static base is `/static/`
- `config-panel` keeps high-signal strategy controls visible first; for `bt_price_action` this includes a dedicated `Structure & POI` accordion, while low-frequency tuning fields fall under `Advanced Strategy Parameters`
- `backtest-history` avoids repeating top-level exit controls in multiple detail sections; `trailing_stop_distance` and `breakeven_trigger_r` are shown once

## 7. Data Flow

### 7.1 Backtest Flow
1. UI posts `/backtest/start`.
2. `server.py` builds engine config and starts background task.
3. `BTBacktestEngine` loads historical data via `DataLoader` and normalizes timeframe order low-to-high.
4. Strategy executes in Backtrader; analyzers collect trades/equity/metrics.
5. `result_mapper` shapes payload.
6. Result is saved to Mongo (`backtests`) and exposed in history/results APIs.

### 7.2 Live Paper Flow
1. UI posts `/api/live/start` with config.
2. Backend validates live-only requirements: `exchange` is required, current allowlist is `binance`, and `execution_mode` must still be `paper`.
3. `BTLiveEngine` warms up bars via REST and subscribes to Binance public sockets through `python-binance`.
4. Closed candles stream into queue-driven live data feed.
5. Strategy runs on live feed with the same lower-TF-first ordering used by backtests; stop can be requested via `/api/live/stop`.
6. After stop, trades/equity are mapped and saved as `is_live=true` history record.
7. If the page reloads during an active run, the dashboard restores state and prior logs from `/api/runtime/state`.

### 7.3 Chart Data Enrichment
- Trade records are enriched with contextual candles/indicators for modal charts.
- To avoid Mongo document size issues, chart payload is capped to first N trades (`75`).

## 8. Database Model (Collections)

- `backtests`
  - `_id` (run_id)
  - metrics (`total_pnl`, `win_rate`, etc.)
  - `trades`, `equity_curve`
  - `configuration`
  - `is_live`
  - session metadata for live runs (`session_start`, `session_end`, `session_duration_mins`)

- `user_configs`
  - template docs keyed by config name
  - special order doc: `_id="__template_order__"`

- `app_config`
  - `_id="default"` for backtest config
  - `_id="live"` for live config

## 9. Testing Matrix

Backend tests are under `tests/` and include:
- engine behavior (`test_bt_backtest_engine.py`, `test_bt_live_engine.py`)
- strategy and risk checks (`test_price_action_extended.py`, `test_market_structure_indicator.py`, `test_risk_manager.py`)
- critical regression tests (OCO/orphan/live controls/result backfill)
- repository and API contract tests
- service-layer mapper/runtime tests (`test_result_mapper_service.py`, `test_strategy_runtime_service.py`)
- trade-metric/analyzer consistency checks (`test_trade_metrics.py`, `test_bt_analyzers.py`)

Special test modes:
- Live E2E (`test_live_e2e.py`) is opt-in and internet-dependent:
  - requires `RUN_LIVE_TESTS=1`
  - marked with `@pytest.mark.live`

Frontend checks:
- unit tests via Vitest
- lint via ESLint
- build via Vite/TypeScript

## 10. Docs Folder Map (`docs/`)

Current docs (local, gitignored):
- `BT_PRICE_ACTION_AUDIT_20260307.md` — strategy reference
- `BACKEND_ENGINE_AND_DASHBOARD_REFERENCE_V1_0_0.md` — backend architecture
- `ENGINE_REVIEW.md`, `ENGINE_STRATEGY_REVIEW_2026.md` — engine analysis
- `ENTRY_MECHANISMS_AND_GHOST_TRADE.md` — entry logic (referenced by risk_manager)
- `REAL_LIVE_BINANCE_INTEGRATION_PLAN.md`, `BINANCE_REAL_TRADING_IMPLEMENTATION_PLAN_20260315.md` — Binance plans
- `TA_LIB_ANALYSIS.md` — TA-Lib analysis
- `RELEASE_NOTES_WORKFLOW.md` — release notes workflow
- `plans/` — implementation plans (e.g. refactoring)

Use this file as source-of-truth for code structure; use `docs/` files for topic deep dives and historical decisions.
