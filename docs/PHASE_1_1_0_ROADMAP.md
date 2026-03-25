# Phase 1.1.0 Roadmap — Deep Review & Development Plan

**Project:** smc-bot — Crypto Futures Algo Trading (Binance)  
**Current Version:** 1.0.0  
**Target Version:** 1.1.0  
**Date:** March 16, 2026

---

## Executive Summary

smc-bot is a crypto futures algo trading system on Binance, built on Backtrader. Core: MTF price-action strategy (HTF structure + LTF patterns), paper trading via WebSocket, backtest with ccxt/Mongo cache. Phase 1.1.0 goal: strengthen the system for reliable backtesting, paper live, and preparation for real trading with focus on practical profitability.

---

## 1. Dashboard UI/UX — Recommendations

### 1.1 Critical Improvements

**Already implemented:** Trade-by-Trade Walkthrough — step-by-step trade review (TradeDetailsModal, keyboard/UI navigation, TradeOHLCVChart with entry/exit/SL/TP, indicators, narrative). Config Diff — in BacktestHistoryList when expanding a run, parameters changed vs previous run are shown (bold). Reconnect & Resume — Binance kline WS reconnects with exponential backoff (live_ws_client), dashboard WS reconnects after 3s (ConsoleProvider), /api/runtime/state restores active live run and console on page reload. (REST backfill for missed bars on long disconnect — optional improvement.)


| #   | Feature                         | Description                                                                                                                                                                                                                                                                                                           | Priority |
| --- | ------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------- |
| 1   | **Regime / Drawdown Timeline**  | Equity curve visualization with drawdown zones, trade markers, regime color coding (bull/bear/sideways)                                                                                                                                                                                                     | P0        |
| 2   | **Signals vs Trades**           | "Signals Generated" metric exists; add filter "show only trades where signal was not filled" (slippage/margin)                                                                                                                                                                                       | P1        |
| 3   | **Live Session Status Panel**   | Live panel: (1) connection health, last bar time, open position, unrealized PnL, funding paid; (2) **live chart** — chart below console, drawn in real time: bars, indicators (EMA, RSI, ADX, ATR, fractals), filters, current position. Not just logs, but price and strategy visualization in live. | P0        |
| 4   | **Backtest vs Live Comparison** | Compare same config: backtest vs paper live for the same period (if data available)                                                                                                                                                                                                                 | P1        |


### 1.2 Analytics and Reports


| #   | Feature                         | Description                                                                   |
| --- | ---------------------------- | -------------------------------------------------------------------------- |
| 6   | **Monthly/Weekly Breakdown** | PnL by month/week, heatmap by day of week                             |
| 7   | **Exit Reason Distribution** | Pie chart: TP / SL / Trailing / Breakeven / Forced Close                   |
| 8   | **R-Multiple Distribution**  | R histogram (realized PnL in risk units)                         |
| 9   | **Pattern Performance**      | Win rate and PF per pattern (Hammer, Engulfing, etc.)                |
| 10  | **Structure State at Entry** | Stats: trades at structure=1 vs -1, correlation with outcome |


### 1.3 UX and Navigation


| #   | Feature              | Description                                                                                  |
| --- | ----------------- | ----------------------------------------------------------------------------------------- |
| 11  | **Quick Presets** | Buttons: "Conservative", "Aggressive", "Paper Smoke" — risk/leverage/filter presets |
| 12  | **Export Report** | PDF/HTML report: equity curve, metrics, trade table, narrative                          |


---

## 2. Engine — Recommendations

### 2.1 Backtest Engine


| #   | Improvement                         | Description                                                                                                    |
| --- | --------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| 1   | **Walk-Forward / Rolling Window** | Walk-forward mode: train on N months, test on M, window shift. Critical for strategy stability validation |
| 1a  | **Parameter Optimization (optstrategy)** | Grid search over params via Backtrader `optstrategy` — see section 2.4 below |
| 2   | **Monte Carlo Shuffle**           | Shuffle trade order to assess equity curve robustness                                           |
| 3   | **Regime-Segment Analysis**       | Split backtest by volatility (ATR percentile) or trend (EMA slope) — metrics per segment           |
| 4   | **Slippage Models**               | Realistic models: fixed bps, ATR-based, volume-based. Currently only `slippage_perc`/`slippage_bps`       |
| 5   | **Funding Simulation**            | Use historical funding rates (Binance API) instead of fixed `funding_rate_per_8h`           |
| 6   | **Partial Fill Simulation**       | Optional: simulate partial fills at low liquidity                                       |
| 7   | **Out-of-Sample Holdout**         | Automatic holdout of last N% of data, report only on OOS                                             |


### 2.2 Live Engine


| #   | Improvement                  | Description                                                                                                                                  |
| --- | -------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| 8   | **Bar Staleness Alert**    | If last bar older than 2× period — warning to console and UI                                                                      |
| 9   | **Live Equity Streaming**  | Real-time equity curve streaming in dashboard (WebSocket)                                                                          |
| 10  | **Live Chart Data Stream** | Real-time bar and indicator streaming (WebSocket): OHLCV, EMA, RSI, ADX, ATR, fractals, structure — for live chart below console |
| 11  | **Session Snapshot**       | Periodic state save (position, orders, equity) to Mongo for crash recovery                                       |


### 2.3 Data Layer


| #   | Improvement                 | Description                                                                                  |
| --- | ------------------------- | ----------------------------------------------------------------------------------------- |
| 12  | **Data Quality Report**   | On load: gaps, duplicates, timezone drift, contract roll — report before run      |
| 13  | **Multi-Symbol Backtest** | Parallel backtest on multiple symbols (BTC, ETH, etc.) with aggregated stats |
| 14  | **Funding Rate Cache**    | Historical funding rates cache for Binance futures in Mongo/CSV                            |


### 2.4 Parameter Optimization (Backtrader optstrategy) — **IMPLEMENTED**

**Summary:** Backtrader supports `cerebro.optstrategy()` instead of `addstrategy()` — passing parameter ranges runs grid search over all combinations.

**Current implementation (March 2026):**
- Run Mode "Optimize" in ConfigPanel; 3 params: risk_reward_ratio, sl_buffer_atr, trailing_stop_distance (3 values each → 27 combos)
- `opt_target_metric`: sharpe_ratio or profit_factor
- Cartesian product by index (fallback for Backtrader optreturn)
- ResultsPanel: Variants table, Best row highlighted green, Win Rate, Profit Factor
- BacktestHistoryList: variants table on expand, Save, Copy to JSON (icon)
- See `docs/BACKTEST_RUN_MODES.md` — internal reference

**How it works:**

1. **Parameter definition** — strategy already has `params` (risk_reward_ratio, sl_buffer_atr, rsi_period, etc.).

2. **optstrategy instead of addstrategy:**
   ```python
   # Current:
   cerebro.addstrategy(PriceActionStrategy, risk_reward_ratio=2.0, sl_buffer_atr=1.5, ...)

   # With optstrategy:
   cerebro.optstrategy(
       PriceActionStrategy,
       risk_reward_ratio=[1.5, 2.0, 2.5, 3.0],
       sl_buffer_atr=[1.0, 1.25, 1.5, 1.75, 2.0],
       adx_threshold=range(20, 41, 5),
       ...
   )
   ```
   Backtrader runs all combinations (e.g. 4×5×5 = 100 runs).

3. **Result** — `cerebro.run()` returns a list of results. Each element: `(strategy_instance, params, analyzers)`. Extract Sharpe, PF, max_dd and sort by target metric.

4. **Backtrader optimizations (v1.8.12.99+):**
   - `optdatas=True` (default): data loaded once in main process, passed to subprocess — memory and time savings.
   - `optreturn=True` (default): returns lightweight objects (params + analyzers only), not full strategy instances.
   - **Multiprocessing**: uses all CPUs by default. ~3× speedup on 4-core (184s → 57s in Backtrader benchmarks).

**Relevance for smc-bot:**

- bt_price_action has ~40+ params. Optimizing all — combinatorial explosion. Pick 3–5 key ones: `risk_reward_ratio`, `sl_buffer_atr`, `adx_threshold`, `rsi_overbought`/`rsi_oversold`, `poi_zone_upper_atr_mult`.
- **Overfitting risk**: grid search on full history without holdout leads to curve fitting. Must combine with Walk-Forward: optimize on train window, evaluate on test window.
- **Dashboard integration**: new "Optimize" mode in ConfigPanel — set ranges, target metric (Sharpe / PF / custom), run, show top-N combinations table and ability to load best config.

**Implementation order (done):**

1. ✅ `add_opt_strategy()` in BaseEngine / BTBacktestEngine.
2. ✅ `run_mode: "optimize"` in config with `opt_params` (3 whitelist params) and `opt_target_metric`.
3. ✅ Result — list `{params, sharpe_ratio, profit_factor, max_drawdown, total_trades, win_rate, ...}`; Cartesian product fallback for params.
4. Later — integrate with Walk-Forward: optimize on train, validate on test.


---

## 3. bt_price_action Strategy — Recommendations

### 3.1 Filters and "Sell the Bottom" Protection


| #   | Improvement                          | Description                                                                                                                 |
| --- | ---------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| 1   | **Premium/Discount by default**  | Enable `use_premium_discount_filter=True` in defaults — blocks Short in Discount                                      |
| 2   | **Engulfing Quality by default** | Enable `use_engulfing_quality_filter=True` — filters weak engulfing                                                 |
| 3   | **RSI Divergence**                 | Add optional filter: bullish divergence (price down, RSI up) blocks Short; bearish divergence blocks Long |
| 4   | **HTF Candle Momentum**            | Before Short: ensure last closed 4H candle is not strong bullish (body > 0.5× ATR, close > open)               |
| 5   | **Structure Confirmation Bars**    | Don't enter on first bar after BOS — wait 1–2 confirmation bars (reduces false entries on reversal)                |


### 3.2 Patterns and Triggers


| #   | Improvement                    | Description                                                                                                          |
| --- | ---------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| 6   | **FVG (Fair Value Gap)**     | `_detect_ltf_fvg` exists for CHoCH; extend: optional entry on FVG retest as separate trigger            |
| 7   | **Order Block**              | Optional filter: enter only if price in order block zone (last bull/bear impulse before reversal) |
| 8   | **Liquidity Sweep**          | Detect sweep of lows/highs before CHoCH — improves setup quality                                                |
| 9   | **Multi-Pattern Confluence** | Require 2+ patterns (e.g. Pinbar + Engulfing on adjacent bars) for entry                                  |
| 10  | **Pattern Strength Score**   | Pattern score (0–1) by body/range, wick ratio, ATR — enter only when score > threshold                         |


### 3.3 Exit Management


| #   | Improvement                | Description                                                                            |
| --- | ------------------------ | ----------------------------------------------------------------------------------- |
| 11  | **Partial TP**           | Optional: close 50% at 1R, remainder at full TP with trailing                  |
| 12  | **Time-Based Exit**      | Exit on timeout (e.g. 24h without movement to TP) — reduces position "stuck" time |
| 13  | **Structure Break Exit** | Early exit on HTF structure change (BOS against position)                           |
| 14  | **Dynamic RR**           | Adaptive RR: higher in trending (ADX high), lower in ranging                 |


### 3.4 Risk & Sizing


| #   | Improvement                    | Description                                                                                      |
| --- | ---------------------------- | --------------------------------------------------------------------------------------------- |
| 15  | **Volatility Scaling**       | Reduce size at high ATR (volatility) — `size *= (baseline_atr / current_atr)` with cap |
| 16  | **Consecutive Loss Scaling** | After N consecutive losses — reduce risk_per_trade (e.g. 1% → 0.5%)                       |
| 17  | **Correlation Filter**       | MTF: don't enter if LTF and HTF structure conflict (rare, but possible with lag)      |


---

## 4. Architectural Improvements

### 4.1 Execution Boundary (Real Trading Preparation)

See `docs/BINANCE_REAL_TRADING_IMPLEMENTATION_PLAN_20260315.md`. Key steps:

1. **ExecutionService interface** — paper vs real abstraction
2. **OrderIntent** — strategy emits intent, execution service converts to orders
3. **Refactor strategy** — from `self.buy()`/`self.sell()` to `emit_intent()`

### 4.2 Domain Layer


| #   | Improvement                      | Description                                                                                                  |
| --- | ------------------------------ | --------------------------------------------------------------------------------------------------------- |
| 1   | **Signal vs Trade Separation** | Explicitly separate: Signal (intent) and Trade (executed trade). Currently mixed in `trade_map`             |
| 2   | **Strategy Config Schema**     | Validatable config schema (Pydantic/JSON Schema) — prevents typos and invalid values          |
| 3   | **Event Sourcing for trades**  | Store event chain (signal → order_placed → fill → exit) for audit and replay                         |
| 4   | **Modular Filters**            | Extract filters into separate classes (StructureFilter, RSIFilter, etc.) — easier to test and combine |


### 4.3 Testing


| #   | Improvement                     | Description                                                                                                     |
| --- | ----------------------------- | ------------------------------------------------------------------------------------------------------------ |
| 5   | **Strategy Unit Tests**       | Tests for `_check_filters_long/short`, `_resolve_structural_sl_`*, `_get_poi_zone_`* with fixed data |
| 6   | **Engine Integration Tests**  | Run backtest on fixed CSV, compare metrics with baseline                                            |
| 7   | **OCO/Order Lifecycle Tests** | Tests for partial fill, same-bar SL+TP, restart reconciliation                                                |
| 8   | **Property-Based Tests**      | Hypothesis: random configs and data — verify invariants (size > 0, SL < entry for long, etc.)          |


### 4.4 Observability


| #   | Improvement              | Description                                                                    |
| --- | ---------------------- | --------------------------------------------------------------------------- |
| 9   | **Structured Logging** | JSON logs with trade_id, bar_time, signal_reason — for parsing and alerts      |
| 10  | **Metrics Export**     | Prometheus/StatsD: trades_per_hour, open_position_duration, equity_snapshot |
| 11  | **Health Endpoint**    | `/health` with DB check, exchange connectivity, last bar age               |


---

## 5. Phase 1.1.0 Prioritization

### Must Have (MVP 1.1.0)

1. **Dashboard:** Live Session Status Panel (status + live chart below console: bars, indicators, filters in real time), Exit Reason Distribution
2. **Engine:** Walk-Forward / Rolling Window backtest, Data Quality Report
3. **Strategy:** Premium/Discount and Engulfing Quality by default, RSI Divergence (optional)
4. **Architecture:** ExecutionService boundary, OrderIntent — no real orders, paper path refactor only

### Should Have

1. **Dashboard:** Regime/Drawdown Timeline, Monthly Breakdown
2. **Engine:** Funding simulation with historical rates, Bar Staleness Alert, **Parameter Optimization (optstrategy)** — grid search over key params, Optimize mode in UI
3. **Strategy:** HTF Candle Momentum filter, Structure Confirmation Bars
4. **Architecture:** Strategy Config Schema, Modular Filters

### Nice to Have

1. **Dashboard:** Backtest vs Live Comparison, Export Report
2. **Engine:** Monte Carlo, Regime-Segment Analysis, Walk-Forward + optstrategy (optimize on train, validate on test)
3. **Strategy:** FVG retest, Partial TP, Volatility Scaling

---

## 6. Concrete Steps for Profitability

### 6.1 Backtest

- Run **walk-forward** on 2023–2025: train 6 months, test 1 month, step 1 month
- Compare **in-sample vs out-of-sample** — if OOS worse, strategy is overfit
- Test on **multiple symbols** (BTC, ETH, SOL) — edge must be robust
- Enable **realistic fees** (4 bps taker) and **slippage** (5–10 bps)
- Use **historical funding** — significant on futures

### 6.2 Paper Live

- Run **at least 2–4 weeks** before any real
- Compare **expected fills** (backtest logic) with **actual** (paper) — drift analysis
- Monitor **latency** — delay between bar close and signal
- Enable **all filters** (premium/discount, engulfing quality) — don't relax for paper

### 6.3 Real Trading Preparation

- Start with **Binance Testnet** (if available for futures)
- **$100 account:** max_position_notional $10–20, max_daily_loss $3–5, 1 position max
- **Kill switch** and **flatten** — required before first real run
- **Startup reconciliation** — refuse startup on unknown positions/orders

---

## 7. Links to Existing Documents

- `BINANCE_REAL_TRADING_IMPLEMENTATION_PLAN_20260315.md` — real trading plan
- `SELL_THE_BOTTOM_INCIDENT_ANALYSIS.md` — incident analysis, filter recommendations
- `MTF_SYNC_VERIFICATION_REPORT.md` — MTF and lookahead verification
- `BOS_MODULE_VERIFICATION_REPORT.md` — BOS/POI verification
- `ENTRY_MECHANISMS_AND_GHOST_TRADE.md` — order lifecycle, OCO

---

## 8. Pre-Release 1.1.0 Checklist

- Walk-forward backtest implemented and tested (or Parameter Optimization via optstrategy)
- Premium/Discount and Engulfing Quality enabled by default
- Live Session Status Panel in dashboard (status + live chart: bars, indicators in real time)
- Data Quality Report on data load
- ExecutionService boundary (paper path through it)
- Strategy unit tests for key filters
- Documentation updated

