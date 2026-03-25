# Backtrade Machine v1.0.0: Backend + Strategy + Dashboard Reference

## 1. What This Document Covers

This document describes:

1. Backend architecture and data flow (backtest/live);
2. Trading engine and order lifecycle;
3. The `bt_price_action` strategy (parameters, signals, SL/TP, trailing, breakeven);
4. All key dashboard fields and their trading/financial meaning;
5. Important limitations of the current v1.0.0 implementation.

The document is based on the actual repository code (`engine/*`, `strategies/*`, `web-dashboard/server.py`, `web-dashboard/api/*`, `web-dashboard/services/*`, `web-dashboard/src/*`, `db/*`).

---

## 2. Backend: Layers and Responsibilities

### 2.1 API Modules (`web-dashboard/api/*`)

As of March 2025, state and models have been extracted into separate modules:

- `api/models.py`: `BacktestConfig`, `BacktestRequest`, `BacktestStatus` (Pydantic).
- `api/state.py`: `running_backtests`, `live_trading_state`, `active_connections`, `active_console_state`, helpers `_latest_running_backtest_run_id()`, `_has_active_runtime()`.
- `api/logging_handlers.py`: `RunLogCollector`, `attach_run_log_handlers`, `detach_run_log_handlers`, `attach_run_log_metadata`.

`server.py` imports from `api/` and re-exports for test backward compatibility.

### 2.2 API/Orchestration (`web-dashboard/server.py`)

`server.py` is the single orchestration point (routes and lifespan):

- Start/stop backtest;
- Start/stop live paper;
- History/results retrieval;
- Configs (general + live);
- WebSocket logs (`/ws`);
- OHLCV + indicators (`/api/ohlcv`).

State is stored in `api/state.py`; run logging in `api/logging_handlers.py`. `_OHLCV_CACHE` remains in `server.py`.

### 2.3 Service Layer (`web-dashboard/services/*`)

- `strategy_runtime.py`:
  - Strategy name to class mapping;
  - Runtime strategy config assembly (inject trailing/breakeven/risk/leverage/max_drawdown).
- `result_mapper.py`:
  - Trade mapping to API/DB format;
  - Equity serialization;
  - Backtest/live aggregate metrics.

### 2.4 Engine Layer (`engine/*`)

- `base_engine.py`:
  - Shared Cerebro, broker setup (cash/commission/leverage);
  - OCO patch applied before engine start.
- `bt_backtest_engine.py`:
  - Historical data loading;
  - Backtest execution;
  - Analyzer metrics collection.
- `bt_live_engine.py`:
  - Warm-up with history;
  - Live feed from WebSocket via queue;
  - Stop and cleanup.
- `data_loader.py`:
  - OHLCV fetch via ccxt;
  - DB cache (`ohlcv_cache`) + CSV fallback;
  - Gap detection and missing-range backfill.
- `live_ws_client.py`:
  - Dedicated thread + event loop;
  - Binance kline stream subscription;
  - Only closed candles (`kline["x"] == True`) written to queue.
- `live_data_feed.py`:
  - Backtrader DataFeed reading from queue.
- `bt_oco_patch.py`:
  - Patch against same-bar OCO double fill and orphan orders.

### 2.5 Strategy Layer (`strategies/*`)

- `base_strategy.py`:
  - Unified order/trade lifecycle;
  - SL/TP placement from actual execution price;
  - Trailing/breakeven updates and OCO reordering;
  - Drawdown stop control.
- `bt_price_action.py`:
  - Primary strategy for v1.0.0.
- `fast_test_strategy.py`:
  - Stress-test strategy for live pipeline verification.
  - Current smoke template `live_test_1m_frequent` uses it on a single `1m` timeframe.
- `helpers/risk_manager.py`:
  - Position sizing with risk/leverage caps.

### 2.6 Persistence Layer (`db/*`)

- `connection.py`: Mongo connection and indexes.
- `repositories/backtest_repository.py`: Run result save/load.
- `repositories/app_config_repository.py`: App config (`default`/`live`).
- `repositories/user_config_repository.py`: User config templates.

---

## 3. Data Flow: Backtest

1. UI sends `POST /backtest/start`.
2. `run_backtest_task` builds `engine_config`, writes logs to WS.
3. `BTBacktestEngine` is created.
4. Strategy is added via `resolve_strategy_class` + `build_runtime_strategy_config`.
5. `engine.run_backtest()`:
   - Load OHLCV from DataLoader;
   - Run Backtrader;
   - Collect analyzer data.
6. `result_mapper` builds `trades`, `equity_curve`, aggregate metrics.
7. Result is saved to Mongo (`backtests`).
8. UI gets status/result via `/backtest/status/{run_id}`.

Data integrity controls:

- DataLoader has timestamp dedup and sorting;
- Chart data is added only to first N trades (Mongo document size limit);
- Signal counter and trade mapping go through a single pipeline in `result_mapper`.

---

## 4. Data Flow: Live Paper

1. UI sends `POST /api/live/start`.
2. Backend validates live-only fields:
   - `exchange` is required;
   - Current allowlist for live paper: `binance` only;
   - `execution_mode` is `paper` only for now.
3. `BTLiveEngine` is created, strategy added.
4. `BTLiveEngine.add_data()`:
   - Warm-up candles via REST (`fetch_recent_bars`);
   - Start WebSocket client per timeframe;
   - Attach queue to Backtrader live feed.
5. Live market stream for Binance goes through `python-binance`; only closed candles enter the queue.
6. `run_live()` blocks until `engine.stop()`.
7. On stop:
   - stop_event + `cerebro.runstop()` + join ws threads;
   - Collect trades/equity;
   - `build_live_metrics_doc`;
   - Save result to Mongo as `is_live=true`.
8. If the user reloads the page during an active run, the backend keeps runtime state and live console tail; the dashboard restores them via `/api/runtime/state`.

Data integrity controls:

- Live feed uses closed candles only;
- Queue is bounded (memory protection); oldest entries are dropped on overflow;
- On stop, `request_stop()` and active WebSocket closure are used.

---

## 5. Order Lifecycle and OCO

### 5.1 Entry

- Strategy places Market entry (`buy`/`sell`).
- After fill, in `notify_order`, real SL/TP are computed from actual `executed.price`.
- SL and TP are placed as an OCO pair.

### 5.2 Exit

- If stop hits: TP is canceled.
- If TP hits: stop is canceled.
- Ghost/orphan protection:
  - OCO patch (`engine/bt_oco_patch.py`);
  - Hard cleanup `_cancel_all_exit_orders_for_data()` on trade close.

### 5.3 Trailing/Breakeven

- On each bar the strategy may move SL:
  - Breakeven: when target R is reached;
  - Trailing: by distance from current price.
- On SL change:
  - Current SL/TP are canceled;
  - New orders placed with same position size;
  - `sl_history` is updated.

---

## 6. `bt_price_action` Strategy Details

### 6.1 Parameters (actual defaults from code)

- `min_range_factor=0.8`
- `min_wick_to_range=0.6`
- `max_body_to_range=0.3`
- `risk_reward_ratio=2.5`
- `sl_buffer_atr=0.5`
- `atr_period=14`
- `use_trend_filter=True`
- `trend_ema_period=200`
- `use_rsi_filter=False`
- `rsi_period=14`
- `rsi_overbought=70`
- `rsi_oversold=30`
- `use_rsi_momentum=False`
- `rsi_momentum_threshold=60`
- `use_adx_filter=False`
- `adx_period=14`
- `adx_threshold=21`
- `trailing_stop_distance=0.0`
- `breakeven_trigger_r=0.0`
- `risk_per_trade=1.0`
- `leverage=1.0`
- `dynamic_position_sizing=True`
- `max_drawdown=50.0`
- `position_cap_adverse=0.5`
- Pattern flags (`hammer`, `engulfing`, etc.) = `True`
- `force_signal_every_n_bars=0`

### 6.2 Indicators

- HTF EMA: trend filter;
- LTF RSI: overbought/oversold filter, momentum;
- LTF ATR: volatility-based SL;
- LTF ADX: trend strength filter;
- TA-Lib candle patterns: hammer/inverted hammer/shooting star/hanging man/engulfing.

### 6.3 Signal Generation Logic

Order:

1. If there is an active entry order — no new actions;
2. If there is an open position — only management (trailing/breakeven);
3. If live and bar is stale — skip signal;
4. If `force_signal_every_n_bars` is enabled — scheduled test entry;
5. Otherwise search for pattern:
   - Bullish pinbar / bearish pinbar;
   - Bullish engulfing / bearish engulfing;
6. After pattern, apply filters:
   - Trend filter;
   - RSI filter;
   - RSI momentum;
   - ADX filter.

### 6.4 SL/TP Placement (financial math)

For Long:

- `sl_long = low - ATR * sl_buffer_atr`
- `risk_per_unit = entry - sl_long`
- `tp_long = entry + risk_per_unit * risk_reward_ratio`

For Short:

- `sl_short = high + ATR * sl_buffer_atr`
- `risk_per_unit = sl_short - entry`
- `tp_short = entry - risk_per_unit * risk_reward_ratio`

### 6.5 Position Size (`RiskManager`)

Base:

- `risk_amount = account_value * (risk_per_trade_pct / 100)`
- `risk_per_unit = |entry - stop|`
- `size = risk_amount / risk_per_unit`

Caps:

1. Leverage cap:
   - `size * entry <= account_value * leverage`
2. DD-based cap:
   - `adverse = clamp(position_cap_adverse, 0.5, 1.0)`
   - `max_from_dd = account_value * (max_drawdown_pct/100) / adverse`
   - `size * entry <= max_from_dd`

### 6.6 Breakeven and Trailing

Breakeven:

- When profit reaches `breakeven_trigger_r * initial_risk`, SL is moved to entry price.

Trailing:

- Long: `new_sl = max(current_sl, close - close * trailing_stop_distance)`
- Short: `new_sl = min(current_sl, close + close * trailing_stop_distance)`

On each SL move:

- Entry is added to `sl_history`;
- SL/TP are reordered as OCO.

### 6.7 Drawdown Circuit

- Strategy tracks equity peak;
- When `max_drawdown` is exceeded:
  - If `stop_on_drawdown=True`, stops trading and (if in position) closes it.

---

## 7. Dashboard: Fields and Impact on Results

Fields visible and configurable in `ConfigPanel`.

### 7.1 General Settings

1. `Initial Capital`
   - Starting capital (base for all metrics and sizing).
   - Impact: PnL scale, position size, DD profile.
2. `Risk Per Trade (%)`
   - Share of capital at risk per trade.
   - Impact: margin-limit hit frequency, equity volatility, drawdown depth.
3. `Max Drawdown (%)`
   - Drawdown limit for emergency stop + part of risk manager cap formula.
   - Impact: strategy aggressiveness and early stop-run probability.
4. `Leverage`
   - Leverage for notional cap.
   - Impact: maximum allowed position size.
5. `Symbol`
   - Trading pair.
   - Impact: volatility regime, liquidity, profit factor.
6. `Trend TF` (`timeframes[0]`)
   - Timeframe for higher context (EMA trend filter).
   - Impact: trend filter sensitivity.
7. `Entry TF` (`timeframes[1]`)
   - Timeframe for entry generation.
   - Impact: signal frequency and noise.
   - Note: Required for backtest and MTF strategies. Single-timeframe smoke configs are supported in live paper, e.g. `live_test_1m_frequent` with `fast_test_strategy`.
8. `Start Date` / `End Date`
   - Backtest period.
   - Impact: market regime and statistical reliability.
   - In live paper these dates do not affect start and must not block `Start Live Run`.
9. `Trailing Stop Distance`
   - Percentage distance of trailing stop from current price.
   - Impact: balance between holding trend and profit capture speed.
10. `Breakeven Trigger (R)`
    - R multiplier for moving stop to breakeven.
    - Impact: reduces tail losses and risk of premature stop-outs.
11. `Dynamic Position Sizing`
    - Enable position size calculation from current capital.
    - Impact: compounding/anti-compounding dynamics.
12. `Position Cap Adverse`
    - Worst-case adverse move in cap formula.
    - Impact: upper bound on notional for tail-risk management.

### 7.2 Strategy Filters

1. `use_trend_filter`
   - Trade only in EMA trend direction.
2. `trend_ema_period`
   - EMA trend filter period.
3. `use_rsi_filter`
   - Filter out trades at RSI extremes.
4. `rsi_period`
   - RSI period.
5. `rsi_overbought` / `rsi_oversold`
   - Overbought/oversold zone thresholds.
6. `use_rsi_momentum`
   - RSI momentum direction filter.
7. `rsi_momentum_threshold`
   - Momentum mode threshold.
8. `use_adx_filter`
   - Allow trades only when trend strength is sufficient.
9. `adx_period`
   - ADX period.
10. `adx_threshold`
    - Minimum ADX level for entry.

### 7.3 Entry & Risk / Pattern Fields

1. `risk_reward_ratio`
   - Target RR for TP.
2. `sl_buffer_atr`
   - ATR multiplier for SL buffer.
3. `atr_period`
   - ATR period.
4. `min_range_factor`
   - Minimum candle size vs ATR.
5. `min_wick_to_range`
   - Minimum wick share for pinbar.
6. `max_body_to_range`
   - Maximum body share for pinbar.
7. `pattern_hammer`
8. `pattern_inverted_hammer`
9. `pattern_shooting_star`
10. `pattern_hanging_man`
11. `pattern_bullish_engulfing`
12. `pattern_bearish_engulfing`
    - Enable/disable specific patterns.
    - Impact: signal frequency and quality, typical trade duration.

### 7.4 Backtest / Live Controls

1. `Start Backtest` / `Stop`
   - Start/stop backtest session.
2. `Start Live Run` / `Stop`
   - Start/stop live paper session.
   - `Exchange` is required for live; UI defaults to `Binance`.
3. `Load Template`, `Reset Settings`
   - Load saved preset, reset to defaults.
4. Reload behavior
   - Page reload must not clear active run; backend keeps runtime snapshot and log buffer; dashboard restores status/buttons/console after reload.

### 7.5 ResultsPanel Metrics (trading meaning)

1. `Total PnL`: Total absolute profit/loss.
2. `Win Rate`: Share of winning trades.
3. `Profit Factor`: gross win / gross loss.
4. `Max Drawdown`: Maximum equity drawdown.
5. `Sharpe Ratio`: Return per unit of risk.
6. `Total Trades`: Number of closed trades.
7. `Signals Generated`: Number of generated signals.

---

## 8. Stability / Data-Integrity Notes for v1.0.0

### 8.1 What Is Done Well

- OCO patch against same-bar ghost trade;
- Orphan exit order cleanup;
- DB OHLCV cache with missing-range backfill only;
- Single mapper layer for output normalization;
- Live stop path with thread join and active WebSocket closure.

### 8.2 Current Implementation Limitations

1. Unused risk/execution fields removed from runtime/API/frontend (`max_positions`, `min_risk_reward`, `max_total_risk_percent`, `slippage_bp`) to avoid false expectations from the UI.
2. Real backtest cancellation during execution is limited (flag is set, but there is no cooperative check in the backtest core during `run_backtest`).
3. Timezone consistency of input dates and timestamp conversions must be controlled.
4. Frontend lint currently has 1 error (`TradeAnalysisChart.tsx`, regex escape).

---

## 9. Recommendations Before v1.0.0 Release

1. Make timezone handling strictly UTC end-to-end (dates -> timestamps -> filters -> charts).
2. Implement cooperative cancel in backtest engine (periodic checkpoints + correct final status).
3. Synchronize defaults between:
   - Runtime strategy defaults,
   - API schema defaults,
   - Legacy backfill defaults.
4. Enable real execution-model parameters:
   - Slippage modeling,
   - Max positions gating,
   - Portfolio-level risk cap.
5. Add tests for:
   - Cancel in-progress;
   - Timezone-deterministic date windows;
   - Cache-key correctness with `ema_timeframe`;
   - `final_capital` parity (broker vs trade-sum).
