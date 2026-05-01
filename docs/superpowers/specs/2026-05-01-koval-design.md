# Koval — Design Spec

> Version: 1.0 — 2026-05-01
> Status: Approved for planning
> Repo: git@gitlab.com:koval-group/koval-ai.git

---

## 1. Vision & Positioning

**Koval** (укр. коваль = blacksmith) is an open-source universal algo-trading platform for traders who don't know programming.

### Core value proposition

The user builds trading strategies by connecting blocks in a visual editor — no code required. The engine executes strategies via backtesting, paper trading, or live trading on connected exchanges.

### Positioning (the Android analogy)

- **Jesse** = Apple — opinionated framework, write code their way
- **Koval** = Android — choose your blocks, data source, library, exchange; everything is pluggable

### Target users

- Primary: Ukrainian crypto traders who want to automate/backtest SMC or any algo strategy
- Secondary: International algo traders wanting a no-code backtesting + live platform

### What "no code" means in Koval

| User action | Interface |
|-------------|-----------|
| Pick an existing strategy | Strategy list |
| Tune its parameters | Sliders + toggles on dashboard |
| Create a new strategy | Block Builder (drag-drop canvas) |
| Run backtest / paper / live | Single button per mode |

SMC/ICT is the first built-in block pack — not the identity of the platform. Any strategy domain can be added as blocks.

---

## 2. Architecture

### System overview

```
┌──────────────────────────────────────────────────────┐
│                   Web Dashboard                      │
│  Strategy List    Block Builder    Live Monitor      │
│  + param sliders  (drag-drop)      (P&L, positions)  │
└─────────────────────────┬────────────────────────────┘
                          │
┌─────────────────────────▼────────────────────────────┐
│                  Koval API (FastAPI)                  │
│  /strategies  /backtest  /live  /blocks  /results    │
└─────────────────────────┬────────────────────────────┘
                          │
         ┌────────────────▼──────────────────┐
         │       Strategy Registry            │
         │  name → class + schema + blocks   │
         └────────────────┬──────────────────┘
                          │
         ┌────────────────▼──────────────────┐
         │      Block Execution Layer         │
         │  signal / filter / exit / risk    │
         │  (pure functions, MIT)            │
         └────────────────┬──────────────────┘
                          │
         ┌────────────────▼──────────────────┐
         │    Declarative Strategy ABC        │
         │  should_long / go_long / filters  │
         │  → TradeSetup (no BT knowledge)   │
         └────────────────┬──────────────────┘
                          │
         ┌────────────────▼──────────────────┐
         │      BTStrategyAdapter (GPL)       │
         │  OCO, orders, notify_* — all BT   │
         └────────────────┬──────────────────┘
                          │
         ┌────────────────▼──────────────────┐
         │           Koval Engine             │
         │  ┌──────────────┐ ┌─────────────┐ │
         │  │  Backtester  │ │ Live Runner │ │
         │  │  (Backtrader)│ │(Backtrader) │ │
         │  └──────────────┘ └─────────────┘ │
         └────────────────┬──────────────────┘
                          │
         ┌────────────────▼──────────────────┐
         │       Exchange Adapter Layer       │
         │  ┌────────────┐ ┌───────────────┐ │
         │  │  Binance   │ │   WhiteBIT    │ │
         │  │  (ported)  │ │   (new)       │ │
         │  └────────────┘ └───────────────┘ │
         └───────────────────────────────────┘
```

### License split

| Layer | License |
|-------|---------|
| Block Execution Layer | MIT |
| Declarative Strategy ABC | MIT |
| Strategy Registry | MIT |
| Koval API + Dashboard | MIT |
| BTStrategyAdapter | GPL-3.0 |
| Backtrader (dependency) | GPL-3.0 |

README clearly documents both licenses.

### Trading modes

| Mode | Status | Data | Capital |
|------|--------|------|---------|
| `backtest` | ✅ v1 | Historical OHLCV | Simulated |
| `paper` | ✅ v1 | Live market feed | Simulated |
| `live` (sandbox) | ✅ v1 | Live market feed | Exchange testnet |
| `live` (real account) | 🔜 future | Live market feed | Real money |

### Exchange adapter interface

```python
class ExchangeAdapter(ABC):
    def fetch_ohlcv(self, symbol, timeframe, since, limit) -> list
    def get_live_feed(self, symbol, timeframe) -> DataFeed
    def place_order(self, side, size, price, order_type) -> Order
    def get_balance(self) -> float
    def get_open_positions(self) -> list
```

Binance: ported from smc-bot. WhiteBIT: new implementation of same interface.

---

## 3. Block Builder UI

### Block canvas (strategy creation)

```
┌─────────────────────────────────────────────────────┐
│  KOVAL — Strategy Builder                           │
│                                                     │
│  Available Blocks          Canvas                   │
│  ┌──────────────┐          ┌───────────────────┐   │
│  │ 📊 SIGNALS   │          │  [BOS Detected] ──┼─┐ │
│  │  BOS/CHoCH   │          │         AND       │ │ │
│  │  EMA Cross   │          │  [RSI < 30]    ───┼─┤ │
│  │  Engulfing   │          │         AND       │ │ │
│  │  FVG         │          │  [ADX > 25]    ───┼─┤ │
│  ├──────────────┤          │                   │ │ │
│  │ 🔍 FILTERS   │          │         ↓         │ │ │
│  │  RSI         │          │  [Enter LONG]  ←──┘ │ │
│  │  ADX         │          │  entry: limit       │ │
│  │  EMA Trend   │          │  SL: swing low      │ │
│  │  Volume      │          │  TP: 2R             │ │
│  ├──────────────┤          └─────────────────────┘ │
│  │ 🚪 EXITS     │                                   │
│  │  Fixed TP/SL │          Strategy name: _______   │
│  │  Trailing SL │          [💾 Save]  [▶ Backtest]  │
│  │  Breakeven   │                                   │
│  ├──────────────┤                                   │
│  │ ⚖️ RISK      │                                   │
│  │  % per trade │                                   │
│  │  Leverage    │                                   │
│  └──────────────┘                                   │
└─────────────────────────────────────────────────────┘
```

### Block graph JSON (saved strategy format)

```json
{
  "name": "My BOS Strategy",
  "version": "1.0",
  "blocks": [
    {"id": "sig1", "type": "signal.bos_detected", "params": {"pivot_span": 2}},
    {"id": "flt1", "type": "filter.rsi",          "params": {"period": 14, "max": 30}},
    {"id": "flt2", "type": "filter.adx",          "params": {"period": 14, "min": 25}},
    {"id": "ent1", "type": "entry.long",           "params": {"entry_type": "limit"}},
    {"id": "ex1",  "type": "exit.atr_sl",          "params": {"atr_mult": 1.5}},
    {"id": "ex2",  "type": "exit.fixed_tp",        "params": {"rr": 2.0}}
  ],
  "connections": [
    {"from": "sig1", "to": "ent1"},
    {"from": "flt1", "to": "ent1"},
    {"from": "flt2", "to": "ent1"},
    {"from": "ent1", "to": "ex1"},
    {"from": "ent1", "to": "ex2"}
  ]
}
```

Koval engine reads this JSON → dynamically assembles `DeclarativeStrategy` → runs via `BTStrategyAdapter`.

### Parameter sliders (existing strategy config)

```
┌──────────────────────────────────────────┐
│  Price Action SMC                        │
│  ─────────────────────────────────────  │
│  RSI Period        [──●────────] 14      │
│  ADX Threshold     [────●──────] 30      │
│  Risk per trade    [──●────────] 1.0%    │
│  RR Ratio          [────●──────] 2.0     │
│  Trailing Stop     [ OFF / ON  ]         │
│  ─────────────────────────────────────  │
│  [▶ Backtest]  [📄 Paper]  [🔴 Live]     │
└──────────────────────────────────────────┘
```

Parameters auto-rendered from Pydantic JSON Schema — no manual form code per strategy.

---

## 4. Repository Structure

New repo: `git@gitlab.com:koval-group/koval-ai.git`

```
koval/
├── koval/                          # Core Python package (MIT)
│   ├── engine/
│   │   ├── base_engine.py          # Abstract engine interface
│   │   ├── backtest_engine.py      # Backtrader backtest runner
│   │   ├── live_engine.py          # Backtrader live/paper runner
│   │   ├── trade_metrics.py        # ← ported from smc-bot
│   │   ├── trade_narrator.py       # ← ported from smc-bot
│   │   ├── timeframe_utils.py      # ← ported from smc-bot
│   │   └── logger.py               # ← ported from smc-bot
│   │
│   ├── adapters/
│   │   └── backtrader/             # GPL-3.0 boundary
│   │       ├── bt_adapter.py       # BTStrategyAdapter (BT shim)
│   │       ├── bt_analyzers.py     # ← ported from smc-bot
│   │       └── oco_patch.py        # ← ported from smc-bot (critical)
│   │
│   ├── strategy/
│   │   ├── base/
│   │   │   ├── declarative.py      # DeclarativeStrategy ABC
│   │   │   └── trade_setup.py      # TradeSetup, StructureState dataclasses
│   │   ├── registry.py             # Strategy registry + resolver
│   │   ├── schemas.py              # Pydantic schemas → JSON Schema → UI forms
│   │   └── block_assembler.py      # JSON graph → DeclarativeStrategy instance
│   │
│   ├── blocks/                     # Block library (pure functions, MIT)
│   │   ├── signals/
│   │   │   ├── smc.py              # BOS, CHoCH, FVG, OB ← from market_structure.py
│   │   │   ├── candlesticks.py     # Hammer, Engulfing, etc. ← from bt_price_action
│   │   │   └── technical.py        # EMA cross, RSI cross, etc.
│   │   ├── filters/
│   │   │   ├── momentum.py         # RSI, Stoch, MACD
│   │   │   ├── trend.py            # ADX, EMA trend
│   │   │   └── volatility.py       # ATR, BB
│   │   ├── exits/
│   │   │   ├── fixed.py            # Fixed TP/SL
│   │   │   ├── trailing.py         # Trailing stop
│   │   │   └── breakeven.py        # Breakeven logic
│   │   └── risk/
│   │       └── position_sizer.py   # ← ported from risk_manager.py
│   │
│   ├── exchanges/
│   │   ├── base.py                 # ExchangeAdapter ABC
│   │   ├── binance.py              # ← ported from smc-bot data_loader + live_ws
│   │   └── whitebit.py             # New — WhiteBIT implementation
│   │
│   └── db/
│       ├── connection.py           # ← ported from smc-bot
│       └── repositories/           # ← ported from smc-bot
│
├── api/                            # FastAPI app (MIT) — rewritten clean
│   ├── server.py                   # Clean entry (NOT 2538-line god object)
│   ├── routers/
│   │   ├── strategies.py           # GET /strategies, GET /blocks
│   │   ├── backtest.py             # POST /backtest/start, GET /backtest/{id}
│   │   ├── live.py                 # POST /live/start, POST /live/stop
│   │   └── results.py             # GET /results, GET /results/{id}/trades
│   ├── models.py                   # Pydantic request/response models
│   ├── state.py                    # In-process runtime state
│   └── ws.py                       # WebSocket /ws handler
│
├── dashboard/                      # React + TypeScript + Vite + MUI v5
│   ├── src/
│   │   ├── features/
│   │   │   ├── block-builder/      # NEW — drag-drop strategy canvas
│   │   │   ├── strategy-config/    # Slider/toggle forms (JSON Schema driven)
│   │   │   ├── backtest/           # ← ported from smc-bot
│   │   │   └── live-monitor/       # ← ported from smc-bot
│   │   └── ...
│   └── package.json
│
├── tests/                          # Pytest + Vitest
├── docker-compose.yml
├── docker-compose.dev.yml
├── LICENSE-MIT                     # Core Koval license
├── LICENSE-GPL                     # BTStrategyAdapter adapter license
├── README.md                       # EN + UA
└── CONTRIBUTING.md
```

---

## 5. Migration from smc-bot

### What gets ported (unchanged or minimal changes)

| smc-bot source | Koval destination | Change |
|----------------|-------------------|--------|
| `engine/trade_metrics.py` | `koval/engine/trade_metrics.py` | None |
| `engine/trade_narrator.py` | `koval/engine/trade_narrator.py` | None |
| `engine/timeframe_utils.py` | `koval/engine/timeframe_utils.py` | None |
| `engine/logger.py` | `koval/engine/logger.py` | None |
| `engine/bt_analyzers.py` | `koval/adapters/backtrader/bt_analyzers.py` | None |
| `engine/bt_oco_patch.py` | `koval/adapters/backtrader/oco_patch.py` | None |
| `strategies/market_structure.py` | `koval/blocks/signals/smc.py` | Rename + restructure |
| `strategies/helpers/risk_manager.py` | `koval/blocks/risk/position_sizer.py` | Rename |
| `engine/data_loader.py` (Binance) | `koval/exchanges/binance.py` | Refactor to adapter interface |
| `engine/live_ws_client.py` | `koval/exchanges/binance.py` | Merged into adapter |
| `web-dashboard/services/result_mapper.py` | `api/services/result_mapper.py` | None |
| `db/` | `koval/db/` | None |
| Dashboard React shell | `dashboard/src/` | Port + extend |

### What gets rewritten clean

| smc-bot source | Reason | Koval replacement |
|----------------|--------|-------------------|
| `web-dashboard/server.py` (2538 lines) | God object | `api/routers/` split by domain |
| `strategies/bt_price_action.py` (1342 lines) | BT-coupled monolith | Block functions in `koval/blocks/` |
| `strategies/base_strategy.py` (436 lines) | Mixed concerns | `DeclarativeStrategy` ABC + `BTStrategyAdapter` |
| `web-dashboard/services/strategy_runtime.py` | Registry doesn't exist | `koval/strategy/registry.py` |

### What is new in Koval

| Component | Description |
|-----------|-------------|
| `block_assembler.py` | JSON block graph → DeclarativeStrategy at runtime |
| `koval/exchanges/whitebit.py` | WhiteBIT exchange adapter |
| Block Builder UI | React drag-drop canvas (react-flow library) |
| `api/routers/` | Clean split: strategies, backtest, live, results |

---

## 6. Future Phases (out of scope for v1)

| Phase | Description |
|-------|-------------|
| Cloud + self-hosted | Multi-tenant SaaS, user auth, data isolation |
| Real account connection | Live trading with real exchange credentials |
| Strategy marketplace | Community block packs, shared strategies |
| Optuna optimization | Replace grid search with Bayesian optimization |
| Walk-forward validation | Out-of-sample testing |
| Additional exchanges | Bybit, OKX, etc. |
| pip install | Lite mode without Docker |
| Notifications | Telegram alerts for live signals |

---

## 7. Key decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| New repo vs evolve in place | New repo (Approach B) | Clean open-source entry point, no legacy noise |
| Engine | Backtrader (ported) | Proven, battle-tested; abstracted behind BTStrategyAdapter |
| License | MIT core + GPL-3.0 adapter | Backtrader is GPL-3.0; core stays permissive |
| Block Builder UI library | react-flow | Production-grade node editor, MIT license |
| Strategy format | JSON block graph | Human-readable, version-controllable, engine-agnostic |
| Exchange support v1 | Binance + WhiteBIT | Binance: existing; WhiteBIT: Ukrainian market differentiator |
| Trading modes v1 | backtest + paper + live (sandbox) | Real account connection deferred |
| Primary market | Ukraine | Unoccupied SMC niche, WhiteBIT differentiator |
| Name | Koval | Ukrainian for "blacksmith/forger"; zero trading SEO competition |
