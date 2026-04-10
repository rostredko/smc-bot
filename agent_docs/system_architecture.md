# System Architecture

Authoritative detail on module boundaries, data flow, and state management.
For the full directory map see [PROJECT_STRUCTURE.md](../PROJECT_STRUCTURE.md).

## Runtime topology

```
                    ┌─────────────────────────────────────┐
                    │           Docker Compose             │
                    │  mongo:27017   backend:8000          │
                    │  frontend: host 5174 → ctn 5173      │
                    └─────────────────────────────────────┘
```

Three processes in Docker Compose:
- `mongo` — MongoDB 7, port 27017, volumes: `mongo_data`, `data_cache`
- `backend` — FastAPI (uvicorn), port 8000
- `frontend` — Vite dev server, host port 5174 → container 5173

## Data flow (one direction only)

```
  engine/          →   web-dashboard/services/   →   web-dashboard/api/   →   React UI
  bt_backtest_engine    strategy_runtime.py           server.py               src/
  bt_live_engine        result_mapper.py              api/models.py
  strategies/                                         api/state.py
```

**Rule:** engine has no imports from `api/` or `web-dashboard/`. Dependency is strictly left-to-right.

## Module responsibilities

### `engine/`
| File | Responsibility |
|------|----------------|
| `base_engine.py` | Abstract engine interface |
| `bt_backtest_engine.py` | Backtrader backtest runner |
| `bt_live_engine.py` | Backtrader paper-live runner |
| `data_loader.py` | OHLCV load from Binance + `data_cache/` |
| `live_ws_client.py` | Binance WebSocket client |
| `live_data_feed.py` | Backtrader live data feed adapter |
| `bt_analyzers.py` | Custom Backtrader analyzers (trade metrics) |
| `timeframe_utils.py` | LTF-first timeframe ordering (`ordered_timeframes`) |
| `trade_metrics.py` | Trade-level metrics calculations |
| `trade_narrator.py` | Human-readable trade descriptions |
| `execution_settings.py` | Broker/commission config |
| `optimize_context.py` | Logging context for optimize runs |
| `logger.py` | Centralized logging setup |

### `strategies/`
| File | Responsibility |
|------|----------------|
| `base_strategy.py` | `BaseStrategy` — shared Backtrader hooks |
| `bt_price_action.py` | Primary strategy: HTF structure + LTF execution |
| `market_structure.py` | BOS/CHoCH detection, swing high/low tracking |
| `fvg_sweep_choch_strategy.py` | FVG + sweep + CHoCH strategy |
| `fast_test_strategy.py` | Minimal strategy for CI speed |
| `helpers/` | Shared helpers (risk manager, etc.) |

### `web-dashboard/services/`
| File | Responsibility |
|------|----------------|
| `strategy_runtime.py` | Resolves strategy class, builds runtime config, optimize config |
| `result_mapper.py` | Shapes engine results → API/DB response (trades, equity, metrics) |

### `web-dashboard/api/`
| File | Responsibility |
|------|----------------|
| `models.py` | Pydantic request/response models (`BacktestConfig`, `BacktestRequest`, `BacktestStatus`) |
| `state.py` | In-process runtime state: active runs, WS connections, console buffer |
| `logging_handlers.py` | Run log collectors — attach/detach to active runs |

### `web-dashboard/server.py`
FastAPI app entry: all HTTP routes + WebSocket `/ws`.

### `db/`
| File | Responsibility |
|------|----------------|
| `connection.py` | MongoDB connection; `USE_MONGOMOCK=true` → in-memory for tests |
| `repositories/backtest_repository.py` | Backtest run CRUD |
| `repositories/user_config_repository.py` | User strategy configs |
| `repositories/app_config_repository.py` | App-level config |

## State management

| State type | Location | Notes |
|------------|----------|-------|
| Active run handle | `api/state.py` | In-process; lost on restart |
| WS connections | `api/state.py` | In-process |
| Console log buffer | `api/state.py` | In-process ring buffer |
| Backtest results | MongoDB `backtests` | Durable |
| Strategy configs | MongoDB `user_configs` | Durable |
| App config | MongoDB `app_config` | Durable |
| OHLCV cache | `data_cache/` (volume) | File-based |

**Rule:** No hidden singletons. In-process state goes in `api/state.py`; anything durable goes in MongoDB.

## Multi-timeframe data contract

`engine/timeframe_utils.py::ordered_timeframes()` always sorts timeframes by duration ascending so:
- `data0` = LTF (e.g. 1H) — execution timeframe
- `data1` = HTF (e.g. 4H) — structure timeframe

Strategy code must never assume a different order. This is enforced by `ordered_timeframes`, not by config array order.

## Key contracts (do not bypass)

- Strategy config: always flow through `services/strategy_runtime.py::build_runtime_strategy_config`
- Results: always flow through `services/result_mapper.py` before reaching API or DB
- API shapes: defined in `api/models.py` — UI and engine must stay in sync through these
- Log attach/detach: use `api/logging_handlers.py` patterns — do not wire new logging directly into endpoints

## Critical patches

### `engine/bt_oco_patch.py` — OCO guard (do not remove or modify)

Patches Backtrader's `BackBroker` to fix the ghost-trade bug: when both TP and SL are eligible in the same bar, Backtrader's internal `_ococheck` runs after `_try_exec`, so both orders can fill before cancellations propagate. Result: phantom double-fills, incorrect PnL, and ghost trades.

Applied in `base_engine.py` via `bt_oco_patch.apply_oco_guard()` before Cerebro is created — must run before any `Cerebro()` instantiation.

The patch also fixes a second bug: Backtrader's `cancel()` only removed from `pending`, not `submitted`, leaving "hanging" orders when trailing/breakeven fires same-bar as entry fill.

**Removing this patch silently re-enables both bugs in all backtest and live runs.**

## Primary strategy params (`bt_price_action`)

Full source: `strategies/bt_price_action.py:73`. Grouped by category:

| Category | Param | Default | Notes |
|----------|-------|---------|-------|
| **Structure** | `market_structure_pivot_span` | `2` | Fractal span for BOS/CHoCH swing detection |
| **Risk / sizing** | `risk_reward_ratio` | `2.0` | TP = entry ± SL × RR |
| | `sl_buffer_atr` | `1.5` | ATR multiplier for SL buffer from structural level |
| | `structural_sl_buffer_atr` | `0.1` | Additional ATR buffer on structural SL |
| | `atr_period` | `14` | ATR lookback period |
| | `risk_per_trade` | `1.0` | % of capital risked per trade |
| | `leverage` | `1.0` | Leverage multiplier |
| | `dynamic_position_sizing` | `True` | Size by risk%, not fixed lot |
| | `max_drawdown` | `50.0` | % drawdown circuit-breaker |
| | `position_cap_adverse` | `0.5` | Max position size cap in adverse conditions |
| | `trailing_stop_distance` | `0.0` | ATR multiplier for trailing stop (0 = disabled) |
| | `breakeven_trigger_r` | `0.0` | Move SL to breakeven at N×R profit (0 = disabled) |
| **Execution filters** | `use_structure_filter` | `True` | Only trade in HTF bias direction |
| | `use_trend_filter` | `True` | Trend confirmation filter |
| | `use_ema_filter` | `False` | EMA trend filter |
| | `trend_ema_period` | `200` | EMA period when filter enabled |
| | `use_ltf_choch_trigger` | `True` | Require LTF CHoCH before entry |
| | `ltf_choch_entry_window_bars` | `6` | Bars to wait for entry after CHoCH |
| | `ltf_choch_arm_timeout_bars` | `24` | Bars before CHoCH trigger expires |
| | `ltf_choch_max_pullaway_atr_mult` | `1.5` | Max ATR price can move away before CHoCH invalidated |
| | `use_ote_filter` | `False` | OTE (0.62–0.79 fib) retracement filter |
| | `use_opposing_level_tp` | `False` | Clamp TP to opposing HTF structural level |
| | `use_space_to_target_filter` | `False` | Reject if space to TP is too small |
| | `space_to_target_min_rr` | `1.0` | Minimum RR for space filter |
| | `use_choch_displacement_filter` | `False` | Require displacement candle for CHoCH |
| | `choch_displacement_atr_mult` | `1.5` | Displacement threshold in ATR |
| | `require_choch_fvg` | `False` | Require FVG present at CHoCH |
| **RSI / ADX** | `use_rsi_filter` | `True` | RSI overbought/oversold filter |
| | `rsi_period` | `14` | RSI lookback |
| | `rsi_overbought` | `70` | RSI threshold for Short block |
| | `rsi_oversold` | `30` | RSI threshold for Long block |
| | `use_rsi_momentum` | `False` | Require RSI momentum confirmation |
| | `use_adx_filter` | `True` | ADX trend strength filter |
| | `adx_period` | `14` | ADX lookback |
| | `adx_threshold` | `30` | Minimum ADX for trade entry |
| **POI zone** | `poi_zone_upper_atr_mult` | `0.3` | Upper ATR buffer around POI |
| | `poi_zone_lower_atr_mult` | `0.2` | Lower ATR buffer around POI |
| **Pattern quality** | `use_pinbar_quality_filter` | `False` | Extra quality checks for pinbars |
| | `use_engulfing_quality_filter` | `False` | Extra quality checks for engulfing |
| **Pattern toggles** | `pattern_hammer` | `True` | Enable hammer pattern |
| | `pattern_inverted_hammer` | `True` | Enable inverted hammer |
| | `pattern_shooting_star` | `True` | Enable shooting star |
| | `pattern_hanging_man` | `True` | Enable hanging man |
| | `pattern_bullish_engulfing` | `True` | Enable bullish engulfing |
| | `pattern_bearish_engulfing` | `True` | Enable bearish engulfing |
| **Debug** | `force_signal_every_n_bars` | `0` | Force signal every N bars (0 = off, testing only) |
| | `detailed_signals` | `True` | Include signal metadata in trade narrative |
| | `market_analysis` | `True` | Include market analysis in trade narrative |
