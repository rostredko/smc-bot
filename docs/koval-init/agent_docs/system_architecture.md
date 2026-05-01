# System Architecture — Koval

Authoritative detail on module boundaries, data flow, and state management.
For the full directory map see [PROJECT_STRUCTURE.md](../PROJECT_STRUCTURE.md).

## Runtime topology

```
┌──────────────────────────────────────────┐
│             Docker Compose               │
│  mongo:27017   backend:8000             │
│  frontend: host 5174 → ctn 5173         │
└──────────────────────────────────────────┘
```

Three processes: `mongo`, `backend` (FastAPI/uvicorn), `frontend` (Vite dev server).

## Data flow (one direction only)

```
koval/exchanges/      →  koval/engine/       →  api/services/   →  api/routers/  →  React UI
(data source)            (backtest/live)         (result_mapper)    (HTTP/WS)
                              ↓
                    koval/adapters/backtrader/
                    (BTStrategyAdapter)
                              ↓
                    koval/strategy/ + koval/blocks/
                    (DeclarativeStrategy + pure block functions)
```

**Rule:** `koval/engine/` and `koval/adapters/` have no imports from `api/` or `dashboard/`. Dependency is strictly left-to-right.

## The GPL-3.0 boundary

```
MIT territory                     │  GPL-3.0 territory
──────────────────────────────────┼──────────────────────────
koval/strategy/base/declarative   │  koval/adapters/backtrader/
koval/blocks/**                   │  (bt_adapter.py, oco_patch.py,
koval/engine/                     │   bt_analyzers.py)
koval/exchanges/                  │
api/**                            │
dashboard/**                      │
```

No MIT file may import from `koval/adapters/backtrader/`. Only `koval/engine/` is allowed to use the adapter via `make_bt_strategy_class`.

## Module responsibilities

### `koval/engine/`
| File | Responsibility |
|------|----------------|
| `backtest_engine.py` | Cerebro setup, run backtest, return normalized results |
| `live_engine.py` | Live/paper run lifecycle, WebSocket feed integration |
| `trade_metrics.py` | Trade-level metric calculations |
| `trade_narrator.py` | Human-readable trade descriptions |
| `timeframe_utils.py` | LTF-first timeframe ordering (`ordered_timeframes`) |
| `execution_settings.py` | Broker/commission config |
| `logger.py` | Centralized logging setup |

### `koval/adapters/backtrader/` (GPL-3.0)
| File | Responsibility |
|------|----------------|
| `bt_adapter.py` | `BTStrategyAdapter` — all BT hooks; `make_bt_strategy_class` factory |
| `bt_analyzers.py` | Custom Backtrader analyzers (trade metrics, drawdown) |
| `oco_patch.py` | OCO ghost-trade fix — **do not remove or modify** |

### `koval/strategy/`
| File | Responsibility |
|------|----------------|
| `base/declarative.py` | `DeclarativeStrategy` ABC — `should_long`, `go_long`, `filters`, hooks |
| `base/trade_setup.py` | `TradeSetup`, `StructureState`, `ChartAnnotation` dataclasses |
| `registry.py` | `STRATEGY_REGISTRY` — name → class + Pydantic schema + metadata |
| `schemas.py` | Pydantic schemas → JSON Schema for auto-rendered dashboard forms |
| `block_assembler.py` | JSON block graph → `DeclarativeStrategy` instance at runtime |

### `koval/blocks/` (pure functions)
| Directory | Responsibility |
|-----------|----------------|
| `signals/smc.py` | BOS, CHoCH, FVG, OB detection |
| `signals/candlesticks.py` | Hammer, Engulfing, Shooting Star, etc. |
| `signals/technical.py` | EMA cross, RSI cross |
| `filters/momentum.py` | RSI, Stoch, MACD entry filters |
| `filters/trend.py` | ADX, EMA trend filters |
| `filters/volatility.py` | ATR-based, BB filters |
| `exits/fixed.py` | Fixed TP/SL calculation |
| `exits/trailing.py` | Trailing stop logic |
| `exits/breakeven.py` | Breakeven trigger |
| `risk/position_sizer.py` | Size from risk% + SL distance |

### `koval/exchanges/`
| File | Responsibility |
|------|----------------|
| `base.py` | `ExchangeAdapter` ABC — fetch_ohlcv, get_live_feed, place_order, get_balance |
| `binance.py` | Binance Spot/Futures REST + WebSocket |
| `whitebit.py` | WhiteBIT v4 REST + WebSocket |

### `api/`
| File | Responsibility |
|------|----------------|
| `server.py` | FastAPI app factory — CORS, startup, router mounting (max ~100 lines) |
| `routers/strategies.py` | `GET /strategies`, `GET /blocks`, `POST /strategies` |
| `routers/backtest.py` | `POST /backtest/start`, `GET /backtest/{id}/*` |
| `routers/live.py` | `POST /live/start`, `POST /live/stop`, `GET /live/status` |
| `routers/results.py` | `GET /results`, `GET /results/{id}/trades` |
| `services/backtest_service.py` | Full backtest lifecycle orchestration |
| `services/live_service.py` | Full live run lifecycle orchestration |
| `services/result_mapper.py` | Engine results → API/DB response shapes |
| `models.py` | Pydantic request/response models |
| `state.py` | In-process state: active runs, WS connections, log buffer |
| `ws.py` | WebSocket `/ws` handler |

## State management

| State type | Location | Notes |
|------------|----------|-------|
| Active run handle | `api/state.py` | In-process; lost on restart |
| WS connections | `api/state.py` | In-process |
| Console log buffer | `api/state.py` | In-process ring buffer |
| Backtest results | MongoDB `backtests` | Durable |
| Strategy configs (block graphs) | MongoDB `strategies` | Durable |
| App config | MongoDB `app_config` | Durable |
| OHLCV cache | `data_cache/` (volume) | File-based |

**Rule:** No hidden singletons. In-process state → `api/state.py`; anything durable → MongoDB.

## Multi-timeframe data contract

`koval/engine/timeframe_utils.py::ordered_timeframes()` sorts timeframes ascending so:
- `data0` = LTF (e.g. 1H) — execution timeframe
- `data1` = HTF (e.g. 4H) — structure timeframe

Strategy code must never assume a different order.

## Block graph runtime assembly

```
POST /backtest/start
  body: { strategy: { blocks: [...], connections: [...] } }
        ↓
api/services/backtest_service.py
        ↓
koval/strategy/block_assembler.py
  assemble_from_graph(graph_json) → DeclarativeStrategy instance
        ↓
koval/adapters/backtrader/bt_adapter.py
  make_bt_strategy_class(declarative_instance) → BTStrategyAdapter subclass
        ↓
koval/engine/backtest_engine.py
  cerebro.addstrategy(AdaptedClass)
  cerebro.run()
```

## Critical patches

### `koval/adapters/backtrader/oco_patch.py` — OCO guard (do not remove or modify)

Patches Backtrader's `BackBroker` to fix the ghost-trade bug: when both TP and SL are eligible in the same bar, Backtrader's internal `_ococheck` runs after `_try_exec`, so both orders can fill before cancellations propagate. Result: phantom double-fills, incorrect PnL.

Applied in `backtest_engine.py` via `oco_patch.apply_oco_guard()` before any `Cerebro()` instantiation.

**Removing this patch silently re-enables both bugs in all backtest and live runs.**

## Trading modes

| Mode | Capital | Data | Account |
|------|---------|------|---------|
| `backtest` | Simulated | Historical OHLCV | None |
| `paper` | Simulated | Live market feed | None |
| `sandbox` | Simulated | Live market feed | Exchange testnet |
| `live` | Real | Live market feed | Real exchange account (future) |
