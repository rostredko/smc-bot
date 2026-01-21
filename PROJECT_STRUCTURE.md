# SMC Trading Bot - Project Structure

## Overview
Trading bot for cryptocurrency spot trading using Smart Money Concepts (SMC) strategy. Supports backtesting and live trading with comprehensive risk management.

---

## ENGINE MODULE

### 1. backtest_engine.py

#### Class: BacktestEngine
Main coordinator for backtesting simulation.

**__init__(self, config: Dict[str, Any])**
- Initializes backtest engine with configuration
- Sets up DataLoader, RiskManager, TradeSimulator, Logger, PerformanceReporter
- Loads strategy module dynamically

**Methods:**
- `_load_strategy()` - Dynamically loads strategy class from strategies module
- `load_data()` - Fetches historical data for all required timeframes
- `run_backtest()` - Main simulation loop that processes each bar
- `_prepare_market_data(current_time: pd.Timestamp) -> Dict[str, pd.DataFrame]` - Prepares market data snapshot up to current time
- `_calculate_risk_reward_ratio(entry_price, stop_loss, take_profit, direction) -> float` - Calculates R:R ratio
- `_execute_signal(signal, current_price, current_time)` - Processes new trade signal, validates risk/reward, creates position
- `_setup_laddered_exits(position)` - Sets up partial TP levels (TP1: 50%, TP2: 30%, Runner: 20%)
- `_update_positions(current_price, current_time)` - Updates all open positions, checks SL/TP hits
- `_is_stop_hit(position, current_price) -> bool` - Checks if stop loss triggered
- `_check_take_profits(position, current_price, current_time) -> bool` - Handles laddered TP exits
- `_partial_exit(position, exit_size, exit_price, current_time, reason)` - Executes partial position exit
- `_update_trailing_stop(position, current_price)` - Updates trailing stop for runner position
- `_close_position(position, exit_price, current_time, reason)` - Closes position completely
- `_close_remaining_positions()` - Closes all positions at end of backtest
- `_update_equity_curve(current_time)` - Updates equity curve with unrealized PnL
- `_generate_final_report() -> Dict` - Generates performance metrics

**Function:**
- `run_backtest(config_file: str)` - Main entry point to run backtest from config file

---

### 2. data_loader.py

#### Class: DataLoader
Fetches and caches historical market data via ccxt.

**__init__(self, exchange_name: str = "binance", cache_dir: str = "data_cache")**
- Initializes exchange connection via ccxt
- Sets up rate limiting

**Methods:**
- `_initialize_exchange() -> ccxt.Exchange` - Creates and tests exchange connection
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

### 3. live_trading.py

#### Class: LiveTradingConfig (dataclass)
Configuration for live trading.

**Fields:**
- exchange_name, api_key, secret, sandbox
- symbol, timeframes, initial_capital, risk_per_trade, max_drawdown, max_positions, leverage
- strategy_config, poll_interval, slippage, commission

#### Class: LiveTradingEngine
Live trading engine for real-time execution.

**__init__(self, config: LiveTradingConfig)**
- Initializes exchange connection
- Sets up RiskManager and Strategy

**Methods:**
- `_init_exchange()` - Initializes exchange connection with API keys
- `start_trading()` - Starts main trading loop
- `stop_trading()` - Stops trading and closes all positions
- `_trading_cycle()` - Executes one trading cycle (update data, generate signals, execute trades)
- `_fetch_market_data() -> Optional[Dict[str, pd.DataFrame]]` - Fetches real-time market data
- `_update_positions(market_data)` - Updates all open positions with current prices
- `_should_close_position(position, current_price) -> bool` - Checks if position should be closed
- `_can_open_position() -> bool` - Checks if new position can be opened
- `_execute_signal(signal, market_data)` - Executes trading signal
- `_execute_trade(position)` - Executes actual trade on exchange (paper trading)
- `_close_position(position, reason)` - Closes position and updates statistics
- `_get_current_price() -> float` - Gets current market price from exchange
- `_log_status()` - Logs current trading status
- `get_performance_stats() -> Dict[str, Any]` - Gets performance statistics

**Function:**
- `create_live_trading_config_from_file(config_file: str) -> LiveTradingConfig` - Creates config from JSON file

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

### 6. position.py

#### Class: Position
Represents a trading position with laddered exits and trailing stops.

**__init__(self, id, entry_price, size, stop_loss, take_profit=None, entry_time=None, reason="", direction="LONG", ladder_exit_enabled=True, trailing_stop_enabled=True, breakeven_move_enabled=True)**
- Initializes spot position with all exit management flags

**Methods:**
- `get_unrealized_pnl(current_price=None) -> float` - Calculates unrealized PnL
- `get_total_pnl(current_price=None) -> float` - Gets total PnL (realized + unrealized)
- `is_profitable(current_price=None) -> bool` - Checks if position is profitable
- `is_stop_hit(current_price) -> bool` - Checks if stop loss hit
- `is_take_profit_hit(current_price) -> bool` - Checks if any TP level hit
- `get_next_take_profit() -> Optional[Dict]` - Gets next un-hit TP level
- `hit_take_profit(tp_price) -> float` - Marks TP as hit, returns exit size
- `partial_exit(exit_size, exit_price, reason)` - Executes partial exit
- `close_position(exit_price, reason)` - Closes entire position
- `update_trailing_stop(current_price, trailing_distance=0.02)` - Updates trailing stop
- `move_stop_to_breakeven()` - Moves stop to entry price
- `move_stop_to_profit(profit_price)` - Moves stop to profitable level
- `check_ladder_exits(current_price) -> List[Dict]` - Checks for ladder exit opportunities
- `activate_trailing_stop()` - Activates trailing stop
- `get_position_summary() -> Dict` - Gets position summary
- `get_performance_metrics() -> Dict` - Gets performance metrics
- `_calculate_exit_efficiency() -> float` - Calculates exit efficiency

#### Class: SpotTradeSimulator
Simulates spot trade execution and manages position lifecycle.

**__init__(self)**
- Initializes with cash_usdt and asset_qty balances

**Methods:**
- `create_position(entry_price, size, stop_loss, take_profit=None, reason="", ladder_exit_enabled=True, trailing_stop_enabled=True, breakeven_move_enabled=True, take_profit_levels=None) -> Position` - Creates new position
- `update_positions(current_price, current_time)` - Updates positions and handles ladder exits
- `_execute_partial_exit(position, instruction, current_price)` - Executes partial exit
- `close_position(position, exit_price, reason)` - Closes position completely
- `get_open_positions() -> List[Position]` - Gets all open positions
- `get_closed_positions() -> List[Position]` - Gets all closed positions
- `get_position_by_id(position_id) -> Optional[Position]` - Gets position by ID
- `get_total_exposure() -> float` - Gets total exposure
- `get_total_equity(current_price) -> float` - Gets total equity (cash + asset value)
- `get_total_unrealized_pnl(current_price) -> float` - Gets total unrealized PnL
- `get_account_summary(current_price) -> Dict` - Gets account summary

---

### 7. risk_manager.py

#### Class: SpotRiskManager
Risk manager optimized for spot crypto trading.

**__init__(self, initial_capital, risk_per_trade=0.5, max_drawdown=15.0, max_positions=1, max_consecutive_losses=5, daily_loss_limit=3.0)**
- Initializes with risk parameters and exchange constraints

**Methods:**
- `get_equity(current_price) -> float` - Calculates total equity (cash + asset value)
- `can_open_position(entry_price, stop_loss, current_bar_time=None, current_price=None) -> tuple[bool, str]` - Checks if position can be opened (cooldown, drawdown, consecutive losses checks)
- `calculate_position_size(entry_price, stop_loss) -> float` - Calculates position size in BTC based on risk
- `_floor_to_step(qty, step_size) -> float` - Rounds quantity to step size
- `calculate_current_drawdown(current_equity) -> float` - Calculates drawdown from peak
- `update_balance(pnl, position_direction=None, exit_time=None)` - Updates balance after trade close, tracks consecutive losses
- `add_position(position)` - Adds position to tracking, updates balances
- `remove_position(position)` - Removes position from tracking
- `get_risk_metrics(current_price=50000) -> Dict` - Gets risk metrics
- `reset_daily_metrics()` - Resets daily tracking
- `validate_risk_reward_ratio(entry_price, stop_loss, take_profit, min_risk_reward) -> tuple[bool, str]` - Validates R:R ratio
- `update_peak_equity(current_price)` - Updates peak equity with current price
- `_calculate_total_potential_risk() -> float` - Calculates total potential risk from all positions

#### Class: PositionSizer
Position sizing calculator for spot trading.

**__init__(self, cash_usdt, min_qty=0.00001, step_size=0.00001, min_notional=10.0, tick_size=0.01, maker_fee=0.0001, taker_fee=0.0004, slippage_bp=1)**
- Initializes with exchange constraints

**Methods:**
- `calculate_size(entry_price, stop_loss, risk_per_trade_pct=0.5) -> Dict` - Calculates position size with detailed breakdown
- `_floor_to_step(qty, step_size) -> float` - Rounds quantity to step size
- `calculate_exit_fees(qty, exit_price) -> float` - Calculates exit fees
- `calculate_total_fees(qty, entry_price, exit_price) -> float` - Calculates total round-trip fees

---



### STRATEGIES MODULE (`strategies/`)

Contains trading strategies and analysis logic.

- **`base_strategy.py`**: Abstract base class defining the strategy interface.
- **`price_action_strategy.py`**: **(PRIMARY)** Production-ready strategy based on Trend Following, EMA, and RSI logic.
- **`smc_strategy.py`**: Legacy strategy implementing Smart Money Concepts.
- **`smc_analysis.py`**: Library of SMC analysis components (Market Structure, Order Blocks, FVGs).
- **`simple_test_strategy.py`**: Minimal strategy for engine testing.

#### Class: StrategyBase (ABC)
Abstract base class for trading strategies.

**__init__(self, config: Optional[Dict] = None)**
- Initializes strategy with configuration
- Sets up SMC analyzers (MarketStructureAnalyzer, OrderBlockDetector, FairValueGapDetector, LiquidityZoneMapper)

**Methods:**
- `generate_signals(market_data: Dict[str, pd.DataFrame]) -> List[Dict[str, Any]]` - Abstract method to generate signals
- `on_trade_exit(position) -> None` - Callback when trade is closed
- `get_strategy_info() -> Dict[str, Any]` - Gets strategy information
- `reset_state()` - Resets strategy state

---

### 2. simple_test_strategy.py

#### Class: SimpleTestStrategy (extends StrategyBase)
Simple test strategy for engine validation.

**__init__(self, config: Optional[Dict] = None)**
- Initializes with signal_frequency and risk_reward_ratio

**Methods:**
- `generate_signals(market_data) -> List[Dict[str, Any]]` - Generates simple alternating signals every N bars
- `_get_timeframe_minutes(timeframe) -> int` - Converts timeframe to minutes
- `_create_long_signal(df, current_price) -> Dict[str, Any]` - Creates long signal
- `_create_short_signal(df, current_price) -> Dict[str, Any]` - Creates short signal
- `get_strategy_info() -> Dict[str, Any]` - Gets strategy info with bar count

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
