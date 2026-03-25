# bt_price_action Audit — 2026-03-07

## Scope

This is the current internal reference for the modified `bt_price_action` strategy and its engine/runtime integration.

Audited areas:
- `strategies/bt_price_action.py`
- `strategies/base_strategy.py`
- `engine/base_engine.py`, `engine/timeframe_utils.py`, `engine/utils.py`
- `engine/bt_backtest_engine.py`
- `engine/bt_live_engine.py`
- `engine/bt_analyzers.py`
- `engine/trade_metrics.py`
- `main.py`
- `web-dashboard/api/` (models, state, logging_handlers)
- `web-dashboard/services/strategy_runtime.py`
- `web-dashboard/server.py`

## Current Strategy Model

`bt_price_action` is now a structural multi-timeframe strategy:
- `4H` defines market structure with confirmed fractals (`2 left / 2 right`) and BOS-only trend state.
- `1H` is the execution timeframe for candle patterns and optional LTF CHoCH confirmation.
- EMA is no longer the default behavior. It remains an optional filter.

Core flow:
1. Build `4H` market structure from confirmed swing highs/lows.
2. Allow only the direction of current `4H` structure when `use_structure_filter=true`.
3. Build POI from `4H` structural levels (`SH` / `SL`) plus `ATR_4H` multipliers.
4. On `1H`, require either:
   - `POI + pattern`, when `use_ltf_choch_trigger=false`
   - `POI -> arm -> LTF CHoCH -> pattern`, when `use_ltf_choch_trigger=true`
5. Build structural SL from `4H` level plus `ATR_4H` buffer.
6. Build TP from RR and optionally clamp it to the opposing `4H` structural level.

## Config Flag Semantics

Important flags:
- `use_structure_filter`
  - `true`: use `4H` structure / POI / structural SL logic.
  - `false`: bypass structural direction and POI gating.
- `use_ltf_choch_trigger`
  - `true`: require valid `1H` CHoCH trigger after POI interaction.
  - `false`: CHoCH is fully bypassed; entry falls back to `POI + pattern`.
- `use_trend_filter`
  - legacy EMA alias; still enables EMA filtering.
- `use_ema_filter`
  - explicit EMA toggle.

EMA note:
- current code treats `use_trend_filter=true` or `use_ema_filter=true` as "EMA filter enabled".
- this is intentional for backward compatibility with older configs and dashboard fields.

## Bugs Fixed In This Audit

### 1. MTF feed order no longer depends on config array order

Previous risk:
- engines used `reversed(timeframes)`.
- for multi-timeframe strategies this implicitly assumed configs always came in `["4h", "1h"]` style.
- if config order changed to `["1h", "4h"]`, the strategy could map `data0/data1` incorrectly.

Current behavior:
- engines now sort timeframes by duration and always add lower timeframe first.
- for MTF strategy instances:
  - `data0 = LTF`
  - `data1 = HTF`

Files:
- `engine/base_engine.py`
- `engine/bt_backtest_engine.py`
- `engine/bt_live_engine.py`

### 2. Strategy bool gates are hardened against string configs

Previous risk:
- some critical gates read raw params directly (`self.params.use_structure_filter`, `self.params.pattern_bearish_engulfing`, etc.).
- if config storage or a legacy payload passed `"false"` / `"true"` strings, Python truthiness could activate filters or patterns incorrectly.

Current behavior:
- critical structure, RSI, ADX, and pattern gates now use `_bool_param(...)`.
- string booleans are normalized consistently.

Files:
- `strategies/bt_price_action.py`

## Validation Run

Regression checks executed after the fixes:

```bash
./.venv/bin/python -m pytest \
  tests/test_base_engine.py \
  tests/test_bt_backtest_engine.py \
  tests/test_bt_live_engine.py \
  tests/test_price_action_extended.py -q
```

Result:
- `55 passed`

Key regression coverage added/updated:
- MTF timeframe ordering normalization in backtest engine
- MTF timeframe ordering normalization in live engine
- bool-string handling for structural filters
- bool-string handling for pattern toggles

## Known Intentional Behavior

These are not bugs:
- `use_trend_filter=false` does not disable CHoCH.
- `use_ltf_choch_trigger` is the dedicated CHoCH on/off switch.
- `start_test_3` is currently tuned for bearish 2026 conditions and is intentionally short-biased.

## Known Limitations

These remain known limitations, not newly introduced bugs:
- backtest realism is research-grade, not exchange-exact:
  - no partial fills
  - no reject/requote model
  - no liquidation engine
  - no latency model
  - funding is fixed-rate, not time-varying exchange series
- live session metrics are session-level and can diverge from realized closed-trade PnL if a session is stopped with an open position.

## Files To Read First

If you need to work on this strategy again, start here:
- `strategies/bt_price_action.py`
- `strategies/base_strategy.py`
- `engine/base_engine.py`
- `engine/bt_backtest_engine.py`
- `engine/bt_live_engine.py`
- `tests/test_price_action_extended.py`
- `tests/test_market_structure_indicator.py`
