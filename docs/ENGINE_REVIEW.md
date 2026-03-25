# SMC-Bot Engine Deep Review

> **Historical:** Feb 2025. Some issues may have been fixed since. Use for risk-awareness context.

**Goal**: Minimize the risk of financial losses due to code bugs.

**Date**: 2025-02-26

---

## 1. Component Overview

| Component | Purpose | Risk |
|-----------|---------|------|
| `engine/base_engine.py` | Broker, commission, leverage | High |
| `engine/bt_backtest_engine.py` | Backtest, metrics, data | High |
| `engine/data_loader.py` | Exchange data loading | Medium |
| `engine/bt_analyzers.py` | Trade analysis, equity curve | Medium |
| `strategies/base_strategy.py` | Order management, lifecycle | High |
| `strategies/bt_price_action.py` | Patterns, entries/exits | High |
| `strategies/helpers/risk_manager.py` | Position sizing | **Critical** |

---

## 2. Bugs and Risks Found

### 2.1 Critical (may cause losses)

#### A. `float('inf')` in profit_factor → JSON/API
- **File**: `engine/bt_backtest_engine.py:159`
- **Problem**: At 100% win rate `profit_factor` = `float('inf')`. MongoDB BSON supports inf, but REST API may return JSON — `json.dumps` does not serialize inf by default.
- **Risk**: Error when saving/displaying results.
- **Fix**: Replace inf with a large number (e.g. 999.0) or string "∞" for UI.

#### B. RiskManager: no validation of risk_per_trade and leverage
- **File**: `strategies/helpers/risk_manager.py`
- **Problem**: `risk_per_trade_pct` can be negative or > 100; `leverage` can be 0 or negative.
- **Risk**: Incorrect position size → overtrading or zero trades.
- **Fix**: Clamp/validate on input.

#### C. RiskManager: stop_loss > entry for long (or vice versa)
- **File**: `strategies/helpers/risk_manager.py`
- **Problem**: For long: entry > sl. If sl > entry is passed (strategy error), `risk_per_unit` becomes negative; `abs()` fixes it but size may be incorrect.
- **Risk**: Strategy may pass swapped prices.
- **Fix**: Explicit direction check and return 0 for invalid entry/sl pair.

### 2.2 High (stability, crashes)

#### D. DataLoader: infinite loop on empty responses
- **File**: `engine/data_loader.py:136-157`
- **Problem**: `while current_ts < end_ts` + `if not ohlcv: break` — if exchange returns empty list, we exit. But on `continue` after exception `current_ts` is not updated → possible infinite loop.
- **Fix**: Update `current_ts` even on error (e.g. +1 bar) or add max retries.

#### E. DataLoader: date filter with string
- **File**: `engine/data_loader.py:166`
- **Problem**: `df.index >= start_date` — with DatetimeIndex and string "2024-01-01" pandas usually converts, but invalid format causes error.
- **Fix**: Explicitly convert to `pd.Timestamp` before comparison.

#### F. main.py: engine.strategy when results empty
- **File**: `main.py:255-256`
- **Problem**: `getattr(engine.strategy, "signals_generated", 0)` — but `engine.strategy` is not set. In `run_backtest` `results[0]` is returned as strat, but engine.strategy is never assigned.
- **Risk**: AttributeError on access.
- **Check**: In `run_backtest` engine does not save strategy — `strat = results[0]` is local only. `engine.strategy` = None → getattr returns 0. No crash, but logic may be wrong.

#### G. BaseStrategy: order == self.order when list
- **File**: `strategies/base_strategy.py:68-72`
- **Problem**: `if isinstance(self.order, list): self.order = self.order[0]` — then `if order == self.order`. After unpacking comparison is ok. But when TP is canceled before main order fill — edge cases possible.
- **Status**: Requires manual scenario verification.

### 2.3 Medium (data quality)

#### H. TradeListAnalyzer: exit_price when size=0
- **File**: `engine/bt_analyzers.py:60-70`
- **Problem**: When size=0 `pnl_per_unit` is not computed, `exit_price = trade.price` (entry). For closed trade with size=0 this is incorrect.
- **Risk**: Inaccurate dashboard data.
- **Fix**: Use `trade.history` to get exit price if available.

#### I. DataLoader: dropna removes all rows
- **File**: `engine/data_loader.py:224`
- **Problem**: `df.dropna(inplace=True)` — if data has many NaN (exchange issue), empty df possible.
- **Risk**: RuntimeError "No data fetched" or empty backtest.
- **Fix**: Check after dropna and log warning.

---

## 3. Fix Plan

1. **profit_factor**: Replace inf with 999.0 (or constant) for serialization.
2. **RiskManager**: Add validation and clamp for risk_per_trade_pct, leverage; entry/sl check.
3. **DataLoader**: Improve error handling in fetch loop; explicit date conversion; check after dropna.
4. **TradeListAnalyzer**: Improve exit_price calculation when size=0.
5. **Tests**: Add unit tests for all edge cases above.

---

## 4. Current Test Coverage (2025-02-26)

| Module | Tests | Coverage |
|--------|-------|----------|
| base_engine.py | test_base_engine.py | broker, add_strategy, run |
| bt_backtest_engine.py | test_bt_backtest_engine.py, test_critical_functionality.py | SMCDataFeed, add_data, run_backtest, metrics, win_rate, profit_factor |
| bt_analyzers.py | test_bt_analyzers.py | TradeListAnalyzer, EquityCurveAnalyzer |
| data_loader.py | test_data_loader.py | init, fetch, cache, validation, _ohlcv_to_dataframe |
| logger.py | test_engine_logger.py | get_logger, setup_logging, QueueHandler |
| bt_live_engine.py | test_bt_live_engine.py | init, add_data, run_live (placeholder) |

**Integration**: test_full_e2e_price_action.py, test_strategy_integration.py

**Gaps** (non-engine):
- base_strategy.py notify_order/notify_trade — only indirectly
- PatternDetection (3 skipped) — TA-Lib/strategy mocking

---

## 5. Recommended Work Order

1. ~~Bug fixes (section 3)~~ ✅ Done
2. ~~New unit tests for fixed components~~ ✅ Done
3. Integration tests for run_backtest → save → load
4. Optional: property-based tests for RiskManager

---

## 6. Completed Fixes (2025-02-26)

- **profit_factor**: `float('inf')` replaced with `999.0` for JSON serialization
- **RiskManager**: Validation of `risk_per_trade_pct` (0–100%) and `leverage` (min 0.1)
- **DataLoader**: Explicit date conversion to `pd.Timestamp` for filter; retry limit (5) on fetch errors; warning on empty df after dropna
- **Tests**: test_metrics_serializable_to_json, test_ohlcv_to_dataframe_handles_all_nan, test_negative_risk_clamped, test_risk_over_100_clamped, test_zero_leverage_clamped

### Additional Fixes (second pass)

- **F. main.py / engine.strategy**: `engine.strategy` is now assigned in `run_backtest()`; in `main.py` — safe access via `getattr(strat, ..., 0) if strat else 0`
- **H. TradeListAnalyzer exit_price when size=0**: When `size == 0` use `trade.history[-1].event.price` (close price) if history available; else fallback to `trade.price`

### Not Fixed (requires manual check or API change)

- **C. RiskManager entry/sl**: Direction check requires `is_long` parameter — API change
- **G. BaseStrategy order**: Edge cases on TP cancel — require manual verification
