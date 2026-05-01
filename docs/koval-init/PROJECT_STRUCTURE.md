# PROJECT_STRUCTURE.md — Koval

> Module map, API routes, and data flow reference.
> Architecture detail: [agent_docs/system_architecture.md](agent_docs/system_architecture.md)

---

## Directory map

```
koval/                              # Python package (MIT license)
├── engine/
│   ├── backtest_engine.py          # Backtrader backtest runner
│   ├── live_engine.py              # Backtrader live/paper runner
│   ├── trade_metrics.py            # Trade-level metrics calculations
│   ├── trade_narrator.py           # Human-readable trade descriptions
│   ├── timeframe_utils.py          # LTF-first timeframe ordering
│   ├── execution_settings.py       # Broker/commission config
│   └── logger.py                   # Centralized logging setup
│
├── adapters/                       # GPL-3.0 boundary
│   └── backtrader/
│       ├── bt_adapter.py           # BTStrategyAdapter + make_bt_strategy_class factory
│       ├── bt_analyzers.py         # Custom Backtrader analyzers
│       └── oco_patch.py            # OCO ghost-trade fix (critical — do not remove)
│
├── strategy/
│   ├── base/
│   │   ├── declarative.py          # DeclarativeStrategy ABC
│   │   └── trade_setup.py          # TradeSetup, StructureState, ChartAnnotation dataclasses
│   ├── registry.py                 # STRATEGY_REGISTRY, register_strategy, get_all_definitions
│   ├── schemas.py                  # Pydantic schemas → JSON Schema for dashboard forms
│   └── block_assembler.py          # JSON block graph → DeclarativeStrategy instance
│
├── blocks/                         # Pure functions (no BT, no side effects)
│   ├── signals/
│   │   ├── smc.py                  # BOS, CHoCH, FVG, OB detection
│   │   ├── candlesticks.py         # Hammer, Engulfing, Pinbar patterns
│   │   └── technical.py            # EMA cross, price action patterns
│   ├── filters/
│   │   ├── momentum.py             # RSI, Stoch, MACD filters
│   │   ├── trend.py                # ADX, EMA trend filters
│   │   └── volatility.py           # ATR, Bollinger Bands
│   ├── exits/
│   │   ├── fixed.py                # Fixed TP/SL calculation
│   │   ├── trailing.py             # Trailing stop logic
│   │   └── breakeven.py            # Breakeven trigger logic
│   └── risk/
│       └── position_sizer.py       # Position size from risk % and SL distance
│
├── exchanges/
│   ├── base.py                     # ExchangeAdapter ABC
│   ├── binance.py                  # Binance REST + WebSocket adapter
│   └── whitebit.py                 # WhiteBIT REST + WebSocket adapter
│
└── db/
    ├── connection.py               # MongoDB connection; USE_MONGOMOCK=true → in-memory
    └── repositories/
        ├── backtest_repository.py  # Backtest run CRUD
        ├── strategy_repository.py  # User strategy configs (block graphs)
        └── app_config_repository.py # App-level config

api/                                # FastAPI application (MIT license)
├── server.py                       # App factory, startup, CORS (max ~100 lines)
├── routers/
│   ├── strategies.py               # GET /strategies, GET /blocks
│   ├── backtest.py                 # POST /backtest/start, GET /backtest/{id}/*
│   ├── live.py                     # POST /live/start, POST /live/stop
│   └── results.py                  # GET /results, GET /results/{id}/trades
├── services/
│   ├── backtest_service.py         # Orchestrates full backtest run lifecycle
│   ├── live_service.py             # Orchestrates live/paper run lifecycle
│   └── result_mapper.py            # Engine results → API/DB response shapes
├── models.py                       # Pydantic request/response models
├── state.py                        # In-process state: active runs, WS connections
└── ws.py                           # WebSocket /ws — log stream

dashboard/                          # React 18 + TypeScript + Vite
├── src/
│   ├── app/
│   │   ├── providers/              # App-level React context providers
│   │   └── router.tsx              # Route definitions
│   ├── features/
│   │   ├── block-builder/          # react-flow drag-drop strategy canvas
│   │   │   ├── BlockBuilder.tsx
│   │   │   ├── BlockPalette.tsx
│   │   │   ├── BlockNode.tsx
│   │   │   ├── useBlockGraph.ts
│   │   │   └── SaveStrategyModal.tsx
│   │   ├── strategy-config/        # JSON Schema → auto-rendered slider forms
│   │   │   └── SchemaForm.tsx
│   │   ├── backtest/               # Backtest results, trade walkthrough
│   │   └── live-monitor/           # Real-time P&L, positions, kill switch
│   ├── entities/                   # Domain UI components
│   ├── shared/                     # API client, shared components, design tokens
│   └── main.tsx
└── package.json

tests/                              # Pytest tests
├── conftest.py                     # USE_MONGOMOCK=true, shared fixtures
├── engine/                         # Tests for koval/engine/*
├── strategy/                       # Tests for DeclarativeStrategy, BTAdapter, registry
├── blocks/                         # Tests for all block pure functions
├── exchanges/                      # Tests for exchange adapters (mocked HTTP)
└── api/                            # Tests for FastAPI endpoints (httpx + mongomock)
```

---

## API routes

| Method | Path | Description |
|--------|------|-------------|
| GET | `/strategies` | List registered strategies with JSON Schema |
| GET | `/blocks` | List available blocks by category |
| POST | `/strategies` | Save a block-graph strategy |
| GET | `/strategies/{id}` | Get saved strategy |
| POST | `/backtest/start` | Start backtest run |
| GET | `/backtest/{id}/status` | Run status + progress |
| GET | `/backtest/{id}/trades` | Trade list for run |
| GET | `/backtest/{id}/equity` | Equity curve data |
| GET | `/backtest/{id}/metrics` | Aggregate metrics |
| POST | `/live/start` | Start paper/sandbox live session |
| POST | `/live/stop` | Stop active live session |
| GET | `/live/status` | Active session status + positions |
| GET | `/results` | All historical run summaries |
| WS | `/ws` | Real-time log stream |

---

## Data flow

```
Exchange (Binance / WhiteBIT)
    ↓ OHLCV / live feed
koval/exchanges/*.py
    ↓
koval/engine/backtest_engine.py  OR  koval/engine/live_engine.py
    ↓ uses
koval/adapters/backtrader/bt_adapter.py  (BTStrategyAdapter)
    ↓ delegates to
koval/strategy/block_assembler.py  →  DeclarativeStrategy instance
    ↑ built from
koval/blocks/signals/*.py  +  koval/blocks/filters/*.py  +  koval/blocks/exits/*.py
    ↓ results
api/services/result_mapper.py
    ↓
koval/db/repositories/backtest_repository.py  (durable)
api/state.py  (in-process)
    ↓
api/routers/*.py
    ↓
React Dashboard
```

---

## Key contracts (do not bypass)

- Strategy config always flows through `koval/strategy/registry.py`
- Results always flow through `api/services/result_mapper.py` before reaching API or DB
- API shapes defined in `api/models.py` — UI and engine stay in sync through these
- BT code always lives in `koval/adapters/backtrader/` — never in strategy or block files
- Block functions are always pure — no state, no BT imports, no side effects
