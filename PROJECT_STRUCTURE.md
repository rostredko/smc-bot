# Backtrade Machine - Project Structure

## Overview
Trading bot for cryptocurrency spot trading using custom strategies. Supports backtesting and live trading with comprehensive risk management.

---

## DOCKER

### docker-compose.yml
- **mongo**: MongoDB 7, port 27017, volume `mongo_data`
- **backend**: FastAPI (Dockerfile.backend), port 8000, volume `data_cache`, depends on mongo health
- **frontend**: Vite dev (Dockerfile.frontend), port 5173

### docker-compose.override.yml (dev)
Loaded automatically. Mounts source for hot-reload:
- Backend: `engine/`, `strategies/`, `db/`, `web-dashboard/` + `uvicorn --reload`
- Frontend: `src/`, config files (Vite HMR)

### Dockerfile.backend
Python 3.11, TA-Lib from source, deps from `deps/requirements.txt`. CMD: `python server.py` (override: `uvicorn --reload`).

### Dockerfile.frontend
Node 20, `npm run dev -- --host 0.0.0.0`. Serves on 5173.

---

## ENGINE MODULE

### 1. base_engine.py
#### Class: BaseEngine (ABC)
Abstract base class for Backtrader-based engines.

**__init__(self, config: Dict[str, Any])**
- Initializes Cerebro, Broker, and Sizers.

**Methods:**
- `add_data()`: Abstract method to add data feeds.
- `run()`: Runs Cerebro.
- `_setup_broker()`: Configures broker (cash, commission).
- `_setup_sizers()`: Configures position sizing.

### 2. bt_backtest_engine.py
#### Class: BTBacktestEngine (extends BaseEngine)
Concrete implementation for backtesting.

**Methods:**
- `run_backtest()`: Main entry point. Loads data, adds analyzers, runs strategy, returns metrics.
- `add_data()`: Uses DataLoader to fetch and add feeds to Cerebro.

### 3. bt_live_engine.py
#### Class: BTLiveEngine (extends BaseEngine)
Concrete implementation for live trading (Stage 2 placeholder/skeleton).

### 4. bt_analyzers.py
#### Class: TradeListAnalyzer
Custom Backtrader analyzer to capture detailed trade history (narrative, entry/exit context, sl_history) in a format compatible with the web dashboard.

#### Class: EquityCurveAnalyzer
Captures equity curve data for chart visualization.

---

### 5. data_loader.py

#### Class: DataLoader
Fetches and caches historical market data via ccxt.

**__init__(self, exchange_name: str = "binance", exchange_type: str = "future", cache_dir: str = "data_cache")**
- Initializes exchange connection via ccxt (supports spot/future/swap)
- Sets up rate limiting

**Methods:**
- `_initialize_exchange() -> ccxt.Exchange` - Creates and tests exchange connection (sets defaultType)
- `fetch_ohlcv(symbol, timeframe, start_date, end_date) -> pd.DataFrame` - Fetches raw OHLCV data with caching
- `get_data(symbol, timeframe, start_date, end_date) -> pd.DataFrame` - High-level method to get formatted data (indicators via TA-Lib in strategy)
- `get_data_multi(symbol, timeframes, start_date, end_date) -> Dict[str, pd.DataFrame]` - Fetches multiple timeframes
- `_ohlcv_to_dataframe(ohlcv) -> pd.DataFrame` - Converts OHLCV list to DataFrame
- `_rate_limit()` - Implements rate limiting between requests
- `_get_cache_file(symbol, timeframe, start_date, end_date) -> str` - Generates cache file path
- `clear_cache()` - Clears all cached data
- `get_available_symbols() -> List[str]` - Gets list of available trading symbols
- `get_exchange_info() -> Dict` - Gets exchange information

---

### 6. logger.py

#### Class: Logger
Handles structured logging of trading events.

**__init__(self, log_level: str = "INFO")**
- Initializes logger with log level

**Methods:**
- `log(level: str, message: str)` - Logs general message
- `log_trade_open(position, current_capital, initial_capital)` - Logs trade opening with balance info
- `log_partial_exit(position, exit_size, exit_price, pnl, reason, current_time, current_capital, initial_capital)` - Logs partial exit
- `log_trade_close(position, final_pnl, current_capital, initial_capital)` - Logs trade closing
- `log_risk_event(event_type, message, details)` - Logs risk management events
- `log_strategy_event(event_type, message, data)` - Logs strategy-specific events
- `log_signal_generation(signal, market_data, current_time)` - Logs detailed signal generation info
- `log_signal_rejection(signal, reason, details, current_time)` - Logs when signal is rejected
- `log_market_analysis(analysis_type, data)` - Logs market analysis results
- `print_summary(metrics)` - Prints final performance summary
- `_should_log(level: str) -> bool` - Checks if message should be logged
- `get_logs(log_type: str = None) -> List[Dict]` - Gets logs, optionally filtered
- `export_logs(filename: str)` - Exports logs to JSON file

#### Class: PerformanceReporter
Calculates comprehensive performance metrics.

**__init__(self, initial_capital: float = 10000)**
- Initializes with starting capital

**Methods:**
- `compute_metrics(closed_trades, equity_curve) -> Dict` - Computes all performance metrics
- `_empty_metrics() -> Dict` - Returns empty metrics when no trades
- `_calculate_max_drawdown(equity_curve) -> float` - Calculates maximum drawdown
- `_calculate_sharpe_ratio(closed_trades) -> float` - Calculates Sharpe ratio
- `_calculate_consecutive_trades(closed_trades) -> Tuple[int, int]` - Max consecutive wins/losses
- `_calculate_monthly_returns(equity_curve) -> List[float]` - Calculates monthly returns
- `_calculate_expectancy(avg_win, avg_loss, win_rate) -> float` - Calculates expectancy
- `_calculate_recovery_factor(total_pnl, max_drawdown) -> float` - Recovery factor
- `_calculate_calmar_ratio(total_pnl, max_drawdown) -> float` - Calmar ratio
- `_calculate_win_loss_streaks(closed_trades) -> tuple[List[int], List[int]]` - All win/loss streaks
- `_calculate_sortino_ratio(closed_trades) -> float` - Sortino ratio (downside deviation)
- `_calculate_max_adverse_excursion(equity_curve) -> float` - Maximum adverse excursion
- `generate_report(metrics) -> str` - Generates formatted performance report

---

**Removed:** `engine/metrics.py`, `engine/position.py`, `engine/risk_manager.py` — functionality moved to Backtrader analyzers and `strategies/helpers/risk_manager.py`.

---



### STRATEGIES MODULE (`strategies/`)

Contains trading strategies and helpers.

- **`bt_price_action.py`**: **(PRIMARY)** Backtrader implementation of Price Action Strategy.
- **`base_strategy.py`**: Base class for Backtrader strategies (extends `bt.Strategy`).
- **`helpers/risk_manager.py`**: Dynamic position sizing based on risk_per_trade and ATR.
- **`helpers/narrative_generator.py`**: Trade outcome narrative generation.

#### Class: PriceActionStrategy (extends BaseStrategy → bt.Strategy)
Backtrader strategy using TA-Lib for high-performance indicator calculations and candlestick patterns.

**params:**
- trend_ema_period, rsi_period, adx_threshold, min_range_factor, min_wick_to_range, max_body_to_range
- `pattern_hammer`, `pattern_inverted_hammer`, `pattern_shooting_star`, `pattern_hanging_man`, `pattern_bullish_engulfing`, `pattern_bearish_engulfing` — enable/disable each pattern (default: true)

**Methods:**
- `next()`: Main strategy logic executed per bar.
- `_is_bullish_pinbar()`, `_is_bearish_pinbar()`, `_is_bullish_engulfing()`, `_is_bearish_engulfing()`: Pattern detection via TA-Lib (CDLHAMMER, CDLINVERTEDHAMMER, CDLSHOOTINGSTAR, CDLHANGINGMAN, CDLENGULFING), filtered by `_meets_pinbar_wick_body_ratio()` and pattern toggles.
- `_enter_long()`, `_enter_short()`: Execute trades using OCO-linked Bracket Orders.
- `_build_entry_context(reason, direction)`: Returns why_entry + indicators_at_entry (ATR, EMA, RSI, ADX).
- `_build_exit_context(exit_reason)`: Returns why_exit + indicators_at_exit.

**Removed:** `smc_strategy.py`, `smc_analysis.py` — SMC strategy not supported in current Backtrader branch.

---

## KEY CONCEPTS

### Trading Flow:
1. BTBacktestEngine loads data via DataLoader and adds strategy to Cerebro
2. For each bar: PriceActionStrategy `next()` runs (pattern detection, filters, entry/exit)
3. RiskManager (strategies/helpers) calculates position size from risk_per_trade and ATR
4. OCO-linked bracket orders (SL + TP) for atomic execution
5. Breakeven and trailing stop updates via order cancel/replace
6. TradeListAnalyzer captures trades; metrics from Backtrader analyzers

### Risk Management:
- Position sizing via `strategies/helpers/risk_manager.py` (risk_per_trade %, ATR-based SL)
- Maximum drawdown protection inside strategy (`max_drawdown` param)
- Leverage cap applied in RiskManager

### Price Action Strategy Features:
- Multi-timeframe analysis (e.g. 4h for trend, 1h/15m for entries)
- TA-Lib candlestick patterns: Hammer, Inverted Hammer, Shooting Star, Hanging Man, Engulfing
- Configurable pattern toggles and geometry filters (min_wick_to_range, max_body_to_range)
- Trend filter (EMA), RSI filter, ADX filter
- Breakeven trigger (breakeven_trigger_r) and trailing stop (trailing_stop_distance)

---

## DATA STRUCTURES

### Signal Dictionary:
```python
{
    "direction": "LONG" | "SHORT",
    "entry_price": float,
    "stop_loss": float,
    "take_profit": float,
    "position_size": float,
    "reason": str,
    "confidence": float,
    "strategy": str,
    "take_profit_levels": [
        {"price": float, "percentage": float, "reason": str},
        ...
    ],
    "trailing_stop_enabled": bool,
    "breakeven_move_enabled": bool
}
```

### Trade Object (from analyzer):
- id, direction, entry_price, exit_price, size, stop_loss, take_profit
- entry_time, exit_time, exit_reason, realized_pnl
- reason, narrative, sl_calculation, tp_calculation, sl_history
- entry_context: { why_entry, indicators_at_entry }
- exit_context: { why_exit, indicators_at_exit }
- take_profit_levels, tp_hit, trailing_active, breakeven_moved
- Various flags for exit management

---

## DATABASE MODULE (`db/`)

MongoDB stores backtest results, user configs, and app config. Required for web dashboard.

### db/connection.py
- `get_database()` — MongoDB database instance (uses mongomock when `USE_MONGOMOCK=true`)
- `is_database_available()` — Checks MongoDB reachability
- `init_db()` — Creates indexes

### db/repositories/
- **BacktestRepository**: `save()`, `get_by_id()`, `get_by_filename()`, `list_ids()`, `list_paginated()`, `delete()`
- **UserConfigRepository**: `list_names()`, `get()`, `save()`, `delete()`
- **AppConfigRepository**: `get()`, `save()`, `get_backtest_config()`, `get_live_config()`, `save_live_config()` — backtest and live configs

### Collections
- `backtests` — backtest results with metrics, trades, equity_curve, configuration
- `user_configs` — saved config templates
- `app_config` — backtest config (id: `default`), live config (id: `live`)

### Environment
- `MONGODB_URI` (default: `mongodb://localhost:27017`)
- `MONGODB_DB` (default: `backtrade`)
- `USE_MONGOMOCK=true` — for tests (in-memory mock)

---

## CONFIGURATION

**CLI & Web dashboard:** Config from MongoDB only. No config files.
**Live trading:** Stored in MongoDB `app_config` (id: `live`). API: `GET/POST /config/live`

### Backtest Config:
- initial_capital, risk_per_trade, max_drawdown, max_positions
- symbol, timeframes, start_date, end_date, strategy (e.g. `bt_price_action`)
- leverage, exchange, exchange_type

### Strategy Config (bt_price_action):
- filters: use_trend_filter, trend_ema_period, use_rsi_filter, rsi_period, rsi_overbought, rsi_oversold, use_adx_filter, adx_threshold
- entry & risk: min_range_factor, min_wick_to_range, max_body_to_range, risk_reward_ratio, sl_buffer_atr, atr_period
- patterns: pattern_hammer, pattern_inverted_hammer, pattern_shooting_star, pattern_hanging_man, pattern_bullish_engulfing, pattern_bearish_engulfing (boolean toggles)
- exit: trailing_stop_distance, breakeven_trigger_r



---

## WEB DASHBOARD MODULE

### 1. server.py
FastAPI backend that bridges the Python trading engine with the React frontend.

**Endpoints:**
- `/config`: Read/Write configuration (from MongoDB)
- `/backtest/start`: Triggers `BacktestEngine` in a background thread
- `/backtest/status/{run_id}`, `/backtest/results/{run_id}`, `DELETE /backtest/{run_id}`
- `/api/ohlcv`: OHLCV candles + indicators (EMA, RSI, ADX, ATR). Params: symbol, timeframe, start, end, backtest_start, backtest_end, exchange_type, ema_period, rsi_period, adx_period, atr_period. When backtest_start/end provided, uses DataLoader cache.
- `/api/backtest/history`: Paginated backtest history
- `/ws`: WebSocket for real-time log streaming

### 2. src/App.tsx
Main React component handling strategy selection, configuration forms, and simulation control.

### 3. Trade Details Modal (`features/trade-details/ui/TradeDetailsModal.tsx`)
Modal showing full trade analysis:
- Price chart with entry/exit markers, SL/TP, trailing stop history
- PnL calculation breakdown
- **TRADE ANALYSIS**: Narrative + entry summary (reason, why_entry, indicators_at_entry) + exit summary (reason, why_exit, indicators_at_exit)
- For old backtests without `exit_context`, indicators at exit are fetched from `/api/ohlcv`

### 4. BacktestHistoryList
Displays historical backtest runs with expandable rows, config diffs (Filters, Entry & Risk, Patterns, Exit Management), PnL. Passes symbol, timeframes, strategyConfig, exchangeType, backtestStart, backtestEnd to TradeDetailsModal.

---

## BACKTRADER & TA-LIB ENGINE ARCHITECTURE

This section details how the **Backtrader** library and **TA-Lib** C-bindings are orchestrated alongside custom helper code to form the Backtrade Machine engine.

### 1. Data Management
- **Downloading Data (Custom):** Backtrader does not support downloading historical crypto data out-of-the-box. We use `ccxt.binance` inside `engine/data_loader.py` to fetch pure OHLCV data.
- **Feeding Data (Custom Wrapper):** We use a custom `SMCDataFeed` (inheriting from `bt.feeds.PandasData`) inside `engine/bt_backtest_engine.py` to strictly map and feed the pandas DataFrame into the Backtrader `Cerebro` engine.

### 2. Trading Strategy
- **Strategy Logic (Native Backtrader):** Our `PriceActionStrategy` inherits directly from `bt.Strategy` and hooks into the standard `next(self)` event loop.
- **Indicators (TA-Lib):** We **bypass** native Backtrader indicators (like `bt.indicators.EMA`) and instead use standard **TA-Lib** (`bt.talib.EMA`, `bt.talib.RSI`, `bt.talib.ATR`, `bt.talib.ADX`). This guarantees maximum mathematical parity with industry standards (like TradingView) and extreme C-level execution speed.
- **Order Execution (Native Backtrader OCO):**
  - **Entry:** We execute Limit and Stop orders. 
  - **Exits & Trailing Stops:** We manually link Stop Loss and Take Profit orders using the `oco=` (One-Cancels-Other) parameter. When trailing a stop, we gracefully cancel the existing bracket and recreate *both* the Stop and TP to preserve the OCO constraint natively.

### 3. Backtest Engine & Reporting
- **Core Engine (Native):** We use `bt.Cerebro()` as the central controller, configuring the broker (`cerebro.broker.setcash()`) and a custom position sizing logic inside the strategy via `RiskManager`.
- **Metrics Math (Native):** We attach native analyzers (`TradeAnalyzer`, `DrawDown`, `SharpeRatio`, `TimeReturn`) to calculate performance metrics.
- **Report Generation (Custom):** `web-dashboard/server.py` extracts raw analyzer Python objects and maps them into rigid JSON structures needed for the React frontend, broadcasting live status via WebSocket.

### Engine Components Summary Table

| Component | Implementation Source | Notes |
| :--- | :--- | :--- |
| **Data Downloading** | **Custom (`ccxt`)** | Backtrader has no native crypto downloader. |
| **Data Feed** | **Custom (`SMCDataFeed`)** | Inherits `PandasData` for strict column safety. |
| **Strategy Logic** | **Native (`bt.Strategy`)** | 100% Backtrader event loop. |
| **Indicators** | **TA-Lib (`bt.talib`)** | Bypasses BT native math for C-speed and accuracy. |
| **Order Management** | **Native (`bt.Order`)** | Strict OCO links via `buy/sell(oco=...)`. |
| **Backtest Loop** | **Native (`bt.Cerebro`)** | The core orchestrator. |
| **Metrics Math** | **Native (`bt.analyzers`)** | We trust Backtrader's math. |
| **Report Formatting** | **Custom (`server.py`)** | Pydantic JSON/Web API mapping. |

