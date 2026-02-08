# SMC Trading Bot - Project Structure

## Overview
Trading bot for cryptocurrency spot trading using Smart Money Concepts (SMC) strategy. Supports backtesting and live trading with comprehensive risk management.

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
Custom Backtrader analyzer to capture detailed trade history in a format compatible with the web dashboard.

---

### 2. data_loader.py

#### Class: DataLoader
Fetches and caches historical market data via ccxt.

**__init__(self, exchange_name: str = "binance", exchange_type: str = "future", cache_dir: str = "data_cache")**
- Initializes exchange connection via ccxt (supports spot/future/swap)
- Sets up rate limiting

**Methods:**
- `_initialize_exchange() -> ccxt.Exchange` - Creates and tests exchange connection (sets defaultType)
- `fetch_ohlcv(symbol, timeframe, start_date, end_date) -> pd.DataFrame` - Fetches raw OHLCV data with caching
- `get_data(symbol, timeframe, start_date, end_date) -> pd.DataFrame` - High-level method to get formatted data with indicators
- `get_data_multi(symbol, timeframes, start_date, end_date) -> Dict[str, pd.DataFrame]` - Fetches multiple timeframes
- `_ohlcv_to_dataframe(ohlcv) -> pd.DataFrame` - Converts OHLCV list to DataFrame
- `_add_technical_indicators(df) -> pd.DataFrame` - Adds ATR, SMA, EMA, MACD, RSI, volume indicators
- `_calculate_atr(df, period=14) -> pd.Series` - Calculates Average True Range
- `_calculate_rsi(prices, period=14) -> pd.Series` - Calculates Relative Strength Index
- `_rate_limit()` - Implements rate limiting between requests
- `_get_cache_file(symbol, timeframe, start_date, end_date) -> str` - Generates cache file path
- `clear_cache()` - Clears all cached data
- `get_available_symbols() -> List[str]` - Gets list of available trading symbols
- `get_exchange_info() -> Dict` - Gets exchange information

---

### 5. data_loader.py
# (Remains mostly same, adapter logic added in engine)
# ...

---

### 4. logger.py

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

### 5. metrics.py

#### Class: PerformanceReporter
(Similar to logger.py PerformanceReporter - appears to be duplicate)

**Methods:**
- `compute_metrics(closed_trades, equity_curve) -> Dict`
- `_empty_metrics() -> Dict`
- `_calculate_max_drawdown(equity_curve) -> float`
- `_calculate_sharpe_ratio(closed_trades) -> float`
- `_calculate_consecutive_trades(closed_trades) -> tuple[int, int]`
- `_calculate_monthly_returns(equity_curve) -> List[float]`
- `_calculate_expectancy(avg_win, avg_loss, win_rate) -> float`
- `_calculate_recovery_factor(total_pnl, max_drawdown) -> float`
- `_calculate_calmar_ratio(total_pnl, max_drawdown) -> float`
- `generate_report(metrics) -> str`

---

# Removed legacy Position and RiskManager classes (functionality moved to Backtrader internals).

---



### STRATEGIES MODULE (`strategies/`)

Contains trading strategies and analysis logic.

- **`bt_price_action.py`**: **(PRIMARY)** Backtrader implementation of Price Action Strategy.
- **`smc_analysis.py`**: Library of SMC analysis components (Reuse attempted in BT or pending migration).

#### Class: PriceActionStrategy (extends bt.Strategy)
Backtrader strategy using EMA, RSI, and candlestick patterns.

**params:**
- trend_ema_period, rsi_period, etc.

**Methods:**
- `next()`: Main strategy logic executed per bar.
- `_is_bullish_pinbar()`: Pattern detection.
- `_enter_long()`: Executing trades using `buy_bracket`.
---

### 3. smc_strategy.py

#### Class: SMCStrategy (extends StrategyBase)
Smart Money Concepts based trading strategy.

**__init__(self, config: Optional[Dict] = None)**
- Initializes with comprehensive SMC configuration
- Sets up market bias, zones, performance tracking

**Core Methods:**
- `generate_signals(market_data) -> List[Dict[str, Any]]` - Main signal generation method
  - Updates market bias from higher timeframe
  - Checks volatility filter
  - Updates zones and levels
  - Looks for entry opportunities

**Market Analysis Methods:**
- `_calculate_atr(df, period=None) -> float` - Calculates ATR
- `_calculate_minimum_stop_distance(low_df, high_df) -> float` - Calculates min SL distance based on ATR
- `_calculate_adaptive_stop_loss(low_df, high_df, current_price, direction) -> float` - Adaptive SL based on support/resistance
- `_is_volatility_acceptable(high_df) -> bool` - Checks if volatility is in acceptable range
- `_calculate_rsi(df, period=None) -> float` - Calculates RSI
- `_calculate_ema(df, period) -> float` - Calculates EMA
- `_calculate_macd(df, fast=None, slow=None, signal=None)` - Calculates MACD
- `_update_market_bias(high_df)` - Determines market bias using weighted scoring (EMA alignment, RSI, structure, MACD)
- `_analyze_market_structure(high_df)` - Analyzes market structure for bias
- `_update_zones_and_levels(high_df, low_df)` - Updates order blocks, FVGs, liquidity levels
- `_cleanup_old_zones(low_df)` - Removes old zones

**Entry Methods:**
- `_look_for_entries(low_df, high_df) -> List[Dict[str, Any]]` - Looks for LONG/SHORT entries based on bias
- `_look_for_long_entries(low_df, high_df, current_price) -> List[Dict[str, Any]]` - Finds LONG entries with mandatory SMC factors
- `_look_for_short_entries(low_df, high_df, current_price) -> List[Dict[str, Any]]` - Finds SHORT entries

**Signal Creation Methods:**
- `_create_long_signal(low_df, high_df, current_price, confluence_factors, atr) -> Dict[str, Any]` - Creates LONG signal with partial TPs
- `_create_short_signal(low_df, high_df, current_price, confluence_factors, atr) -> Dict[str, Any]` - Creates SHORT signal
- `_create_exit_signal(current_price, reason) -> Dict[str, Any]` - Creates exit signal

**Filter Methods:**
- `_is_in_discount_zone(price) -> bool` - Checks if price in discount zone
- `_is_in_premium_zone(price) -> bool` - Checks if price in premium zone
- `_has_volume_confirmation(low_df) -> bool` - Checks for volume confirmation
- `_has_strong_volume_confirmation(low_df) -> bool` - Checks for strong volume
- `_has_very_bullish_price_action(low_df) -> bool` - Checks for very bullish PA
- `_has_bearish_price_action(low_df) -> bool` - Checks for bearish PA
- `_is_near_liquidity_level(current_price, direction) -> bool` - Checks proximity to liquidity level
- `_has_liquidity_sweep(low_df, direction) -> bool` - Checks for liquidity sweep
- `_is_in_fibonacci_retracement_zone(low_df, current_price, direction) -> bool` - Checks Fibonacci zones
- `_get_fibonacci_level(low_df, current_price) -> Optional[str]` - Gets closest Fibonacci level
- `_has_bullish_structure_break(low_df) -> bool` - Checks for bullish structure break
- `_has_bearish_structure_break(low_df) -> bool` - Checks for bearish structure break
- `_enhanced_signal_filter(signal, low_df, high_df) -> bool` - Enhanced signal filtering (RSI, trend, volume, time, volatility, confidence, micro-trend)
- `_is_strong_trend_aligned(direction, high_df, low_df) -> bool` - Checks trend alignment on both TFs
- `_is_optimal_volatility(low_df, high_df) -> bool` - Checks optimal volatility range
- `_is_good_trading_time() -> bool` - Checks trading time (avoids low liquidity)
- `_is_aligned_with_lower_tf_trend(direction, low_df) -> bool` - Checks lower TF trend alignment
- `_has_increasing_volume(low_df) -> bool` - Checks for increasing volume

**Management Methods:**
- `on_trade_exit(position)` - Handles trade exit, updates loss counter, invalidates zones
- `get_strategy_config() -> Dict[str, Any]` - Gets strategy configuration for web interface
- `get_strategy_info() -> Dict[str, Any]` - Gets strategy info with market bias, zones, performance
- `manage_open_positions(current_price, current_time)` - Manages open positions with trailing stops
- `_manage_long_position(position, current_price, current_time)` - Manages long position with trailing stop

---

### 4. smc_analysis.py

#### Data Classes:
- `SwingPoint` - Represents swing high/low point (index, price, timestamp, type)
- `OrderBlock` - Order block zone (start_index, end_index, high, low, type, strength, timestamp, zone_id, used)
- `FairValueGap` - FVG/imbalance (start_index, end_index, high, low, type, filled, timestamp, zone_id, used)
- `LiquidityZone` - Liquidity zone (price, type, strength, timestamp, swept)

#### Class: MarketStructureAnalyzer
Analyzes market structure for BOS and CHOCH.

**__init__(self, lookback_period: int = 20)**

**Methods:**
- `identify_trend(df) -> str` - Identifies trend ('Bullish', 'Bearish', 'Sideways')
- `find_swing_points(df) -> List[SwingPoint]` - Finds swing highs and lows
- `detect_structure_breaks(df) -> Dict[str, bool]` - Detects Break of Structure events
- `detect_choch(df) -> Dict[str, bool]` - Detects Change of Character events
- `get_market_bias(df) -> str` - Determines market bias ('Bullish', 'Bearish', 'Neutral')

#### Class: OrderBlockDetector
Detects order blocks (supply/demand zones).

**__init__(self, min_strength: float = 0.6)**

**Methods:**
- `find_order_blocks(df) -> List[OrderBlock]` - Finds order blocks in price data
- `_is_strong_bullish_move(df, index) -> bool` - Checks for strong bullish move
- `_is_strong_bearish_move(df, index) -> bool` - Checks for strong bearish move
- `_create_demand_block(df, index) -> Optional[OrderBlock]` - Creates demand order block
- `_create_supply_block(df, index) -> Optional[OrderBlock]` - Creates supply order block
- `_calculate_volume_strength(df, index) -> float` - Calculates volume strength
- `_calculate_price_strength(df, index, block_type) -> float` - Calculates price action strength
- `find_premium_discount_zones(df) -> Dict[str, Dict]` - Finds premium/discount zones
- `is_price_in_zone(price, zone) -> bool` - Checks if price is in zone

#### Class: FairValueGapDetector
Detects Fair Value Gaps (FVGs).

**__init__(self, min_gap_size: float = 0.001)**

**Methods:**
- `scan_for_gaps(df) -> List[FairValueGap]` - Scans for FVGs in price data
- `_detect_bullish_gap(df, index) -> Optional[FairValueGap]` - Detects bullish FVG
- `_detect_bearish_gap(df, index) -> Optional[FairValueGap]` - Detects bearish FVG
- `check_gap_fill(df, gap) -> bool` - Checks if FVG has been filled
- `get_active_gaps(df) -> List[FairValueGap]` - Gets all unfilled FVGs

#### Class: LiquidityZoneMapper
Maps liquidity zones and detects liquidity sweeps.

**__init__(self, sweep_threshold: float = 0.002)**

**Methods:**
- `identify_liquidity_sweeps(df) -> List[LiquidityZone]` - Identifies liquidity sweeps
- `find_liquidity_levels(df, lookback=50) -> List[LiquidityZone]` - Finds potential liquidity levels

---

## KEY CONCEPTS

### Trading Flow:
1. BacktestEngine loads data and strategy
2. For each bar: strategy generates signals based on market data
3. Engine validates signals (risk/reward, position limits)
4. Positions are created with laddered exits (TP1: 50%, TP2: 30%, Runner: 20%)
5. Positions are updated each bar (check SL/TP, trailing stops)
6. Performance metrics calculated at end

### Risk Management:
- Position sizing based on risk_per_trade percentage
- Maximum drawdown protection
- Cooldown after stop loss
- Consecutive loss tracking with risk reduction
- Maximum concurrent positions limit

### SMC Strategy Features:
- Multi-timeframe analysis (4h for bias, 15m for entries)
- Order blocks, Fair Value Gaps, Liquidity zones
- Premium/Discount zone filtering
- Fibonacci retracement levels
- Market structure analysis (BOS, CHOCH)
- Volatility filtering
- Multiple confluence factors required for entry
- Enhanced signal filtering (RSI, trend, volume, time filters)

### Position Management:
- Laddered exits with partial take profits
- Breakeven move after TP1
- Trailing stop for runner position
- Adaptive stop loss based on ATR and support/resistance

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

### Position Object:
- id, direction, entry_price, size, stop_loss, take_profit
- entry_time, exit_time, exit_price, exit_reason
- realized_pnl, unrealized_pnl, risk_amount, risk_reward_ratio
- take_profit_levels, tp_hit, trailing_active, breakeven_moved
- Various flags for exit management

---

## CONFIGURATION

### Backtest Config:
- initial_capital, risk_per_trade, max_drawdown, max_positions
- symbol, timeframes, start_date, end_date, strategy
- min_risk_reward, leverage, exchange

### Strategy Config:
- timeframes: high_timeframe, low_timeframe
- risk_management: risk_per_trade_pct, max_concurrent_positions, min_required_rr, max_stop_distance_pct
- volatility_filter: volatility_filter_enabled, atr_period, atr_percentile_min/max
- partial_take_profits: tp1_r, tp1_pct, tp2_r, tp2_pct, runner_pct
- exit_management: trailing_stop_enabled, breakeven_move_enabled
- filters: volume_threshold, rsi_period, ema_filter_period, min_signal_confidence



---

## WEB DASHBOARD MODULE

### 1. server.py
FastAPI backend that bridges the Python trading engine with the React frontend.

**Endpoints:**
- `/config`: Read/Write JSON configuration
- `/backtest/start`: Triggers `BacktestEngine` in a background thread
- `/ws`: WebSocket for real-time log streaming from `Logger`

### 2. src/App.tsx
Main React component handling strategy selection, configuration forms, and simulation control.

### 3. src/components/BacktestHistoryList.tsx
Displays historical backtest runs with:
- Dedicated columns for Strategy and Period
- Expandable rows showing full configuration diffs
- PnL and other performance metrics
