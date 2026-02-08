# Backtrader Library Usage Documentation

This document describes exactly how the **Backtrader** library is utilized within the `smc-bot` project. It distinguishes between native Backtrader features and custom helper code.

## 1. Data Management

### Downloading Data (Custom)
**File:** `engine/data_loader.py`
*   **Method:** We do **NOT** use Backtrader to download data. Backtrader does not support downloading historical crypto data out-of-the-box.
*   **Implementation:** We use the **CCXT** library (`ccxt.binance`) to fetch OHLCV (Open, High, Low, Close, Volume) data from Binance (Spot or Futures).
*   **Process:** 
    1.  `DataLoader` fetches data via CCXT.
    2.  Data is saved to local CSV files (caching).
    3.  Data is loaded into a Pandas DataFrame.

### Feeding Data (Native Backtrader)
**File:** `engine/bt_backtest_engine.py`
*   **Method:** We use `bt.feeds.PandasData` to feed the downloaded DataFrame into the Backtrader engine.
*   **Usage:**
    ```python
    data = bt.feeds.PandasData(dataname=df, timeframe=tf, ...)
    cerebro.adddata(data)
    ```
*   **Why:** This is the standard way to bridge custom data sources (like CCXT) with Backtrader.

## 2. Trading Strategy

### Strategy Logic (Native Backtrader)
**File:** `strategies/bt_price_action.py`
*   **Inheritance:** Our strategy class `PriceActionStrategy` inherits directly from `bt.Strategy`.
*   **Indicators:** We use native Backtrader indicators for performance and standard calculations:
    *   `bt.indicators.EMA` (Exponential Moving Average)
    *   `bt.indicators.RSI` (Relative Strength Index)
    *   `bt.indicators.ATR` (Average True Range)
    *   `bt.indicators.ADX` (Average Directional Index)
*   **Signal Loop:** We use the standard `next(self)` method which Backtrader calls for every new candle.
*   **Position Sizing:** We access `self.position.size` to check current holdings.

### Order Execution (Native Backtrader)
**File:** `strategies/bt_price_action.py`
*   **Entry:** We use `self.buy_bracket()` and `self.sell_bracket()` to create entry orders with attached Stop Loss and Take Profit orders automatically.
*   **Exits:** The bracket orders handle exits natively (OZO - One Cancels Other).
*   **Trailing Stop:** We implement custom logic inside `next()` that calls `self.cancel(order)` and places a new `self.buy()` or `self.sell()` stop order to move the stop loss.

## 3. Backtest Engine

### Core Engine (Native Backtrader)
**File:** `engine/base_engine.py`, `engine/bt_backtest_engine.py`
*   **Cerebro:** We use `bt.Cerebro()` as the central controller.
*   **Broker:** We configure the native broker:
    *   `cerebro.broker.setcash(initial_capital)`
    *   `cerebro.broker.setcommission(commission=0.0004)` (for crypto fees)
*   **Sizers:** We use `bt.sizers.PercentSizer` (or similar) to calculate trade size based on % risk.

### Integration Wrapper (Custom)
**File:** `engine/bt_backtest_engine.py`
*   **Wrapper:** The `BTBacktestEngine` class wraps `bt.Cerebro`.
*   **Purpose:** 
    1.  Accepts JSON configuration from the Web Dashboard.
    2.  Calls `DataLoader` to get the DataFrame.
    3.  Feeds DataFrame to Cerebro.
    4.  Runs Cerebro (`cerebro.run()`).
    5.  Extracts results from Analyzers.

## 4. Analysis & Reporting

### Analyzers (Native Backtrader)
**File:** `engine/bt_backtest_engine.py`
We attach native analyzers to Cerebro to calculate performance metrics:
1.  `bt.analyzers.TradeAnalyzer` (Wins, losses, PnL per trade)
2.  `bt.analyzers.DrawDown` (Max drawdown)
3.  `bt.analyzers.SharpeRatio` (Risk-adjusted return)
4.  `bt.analyzers.TimeReturn` (Equity curve for plotting)

### Report Generation (Custom)
**File:** `web-dashboard/server.py`
*   **Extraction:** We write custom code to pull data *out* of the Backtrader analyzers objects (e.g., `strat.analyzers.trades.get_analysis()`).
*   **Formatting:** We format this raw data into a JSON structure compliant with our React Frontend.
*   **Logging:** We construct a text-based summary log (PnL, Win Rate, Balance) and broadcast it via WebSocket.

## Summary table

| Component | Implementation Source | Notes |
| :--- | :--- | :--- |
| **Data Downloading** | **Custom (CCXT)** | Backtrader has no native crypto downloader. |
| **Data Feed** | **Native (`bt.feeds`)** | Standard standard Pandas feed. |
| **Strategy Logic** | **Native (`bt.Strategy`)** | 100% Backtrader logic. |
| **Indicators** | **Native (`bt.indicators`)** | EMA, RSI, ATR, ADX. |
| **Order Management** | **Native (`bt.Order`)** | Bracket orders, OCO connections. |
| **Backtest Loop** | **Native (`bt.Cerebro`)** | The core engine. |
| **Metrics Math** | **Native (`bt.analyzers`)** | We trust Backtrader's math. |
| **Report Formatting** | **Custom (`server.py`)** | Required for JSON/Web API output. |
