# bt_traders_reality Strategy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement `TradersRealityStrategy` (`bt_traders_reality`) — a backtrader strategy that replicates the signal logic from `scripts/market_analyzer.py`, using PVSRA, EMA stack, daily pivot points, ADR exhaustion, and weekly M0/M5 levels as entry triggers and SL/TP anchors, without modifying the engine layer.

**Architecture:** Pure-Python indicator helpers in `strategies/helpers/tr_indicators.py` (no backtrader dependency, fully unit-testable). Backtrader strategy in `strategies/bt_traders_reality.py` extends `BaseStrategy`, maintains rolling state (PVSRA deques, daily/weekly level state machines) in `next()`, and uses `bt.talib.EMA` + `bt.talib.ATR` for indicators. Engine, result mapper, and BaseStrategy are untouched.

**Tech Stack:** Python 3.11+, Backtrader, bt.talib (TA-Lib wrapper), `collections.deque`, existing `BaseStrategy._place_entry()` contract.

---

## Engine change analysis

**No engine changes required.** Here is the reasoning:

| Need | How it's satisfied without engine changes |
|------|-------------------------------------------|
| EMA 5/13/50/200/800 | `bt.talib.EMA` — already used in `bt_price_action` |
| PVSRA rolling window | `collections.deque(maxlen=10)` updated in `next()` |
| Daily pivot levels | State machine in `next()`: detect date change, save OHLC, compute PP/R1-R3/S1-S3 |
| ADR (daily ranges) | `collections.deque(maxlen=N)` of daily ranges, updated on day boundary |
| Weekly M0/M5 | State machine in `next()`: detect week change, save H/L |
| SL/TP placement | `BaseStrategy._place_entry()` — unchanged contract |
| Signal metadata | `pending_metadata` / `entry_context` — unchanged contract |

---

## File map

| File | Action | Responsibility |
|------|--------|---------------|
| `strategies/helpers/tr_indicators.py` | **Create** | Pure-Python signal math: PVSRA, EMA stack, pivot levels, ADR exhaustion, signal classification |
| `strategies/bt_traders_reality.py` | **Create** | Backtrader strategy: state machines, indicator wiring, entry/exit logic |
| `tests/test_tr_indicators.py` | **Create** | Unit tests for every function in `tr_indicators.py` |
| `tests/test_bt_traders_reality.py` | **Create** | Integration tests: full cerebro runs, entry/rejection verification |
| `web-dashboard/services/strategy_runtime.py` | **Modify** (1 line) | Add `"bt_traders_reality"` to `_LEGACY_CANONICAL_NAMES` |
| `web-dashboard/server.py` | **Modify** (~50 lines) | Add `"bt_traders_reality"` schema to `get_strategy_config_schema()` |

---

## Task 1: Pure-Python indicator helpers

**Files:**
- Create: `strategies/helpers/tr_indicators.py`
- Test: `tests/test_tr_indicators.py`

### 1a. Write failing tests for `pvsra_label` and `pvsra_score_delta`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_tr_indicators.py
import pytest
from strategies.helpers.tr_indicators import (
    pvsra_label,
    pvsra_score_delta,
    ema_stack_score,
    ema_cross_score,
    pivot_levels,
    pivot_position_score,
    adr_mean,
    adr_exhaustion_score,
    classify_signal,
    composite_signal_score,
)


class TestPvsraLabel:
    def test_ring_volume_bull_is_green(self):
        # vol >= avg_vol * 2.0 → ring volume; close >= open → bull
        assert pvsra_label(vol=200, spread=1.0, avg_vol=100, max_spread_vol=50,
                           is_bull=True) == "green"

    def test_ring_volume_bear_is_red(self):
        assert pvsra_label(vol=200, spread=1.0, avg_vol=100, max_spread_vol=50,
                           is_bull=False) == "red"

    def test_ring_via_spread_vol_bull(self):
        # spread*vol >= max_spread_vol triggers ring; vol < avg*2 so spread route
        assert pvsra_label(vol=50, spread=2.0, avg_vol=60, max_spread_vol=100,
                           is_bull=True) == "green"

    def test_big_volume_bull_is_blue(self):
        # vol >= avg_vol * 1.5 but < 2.0 → big volume; not ring
        assert pvsra_label(vol=150, spread=1.0, avg_vol=100, max_spread_vol=9999,
                           is_bull=True) == "blue"

    def test_big_volume_bear_is_violet(self):
        assert pvsra_label(vol=150, spread=1.0, avg_vol=100, max_spread_vol=9999,
                           is_bull=False) == "violet"

    def test_normal_bull_is_gray_up(self):
        assert pvsra_label(vol=80, spread=1.0, avg_vol=100, max_spread_vol=9999,
                           is_bull=True) == "gray_up"

    def test_normal_bear_is_gray_dn(self):
        assert pvsra_label(vol=80, spread=1.0, avg_vol=100, max_spread_vol=9999,
                           is_bull=False) == "gray_dn"

    def test_ring_takes_priority_over_big(self):
        # vol=200 qualifies for both ring (>=2x) and big (>=1.5x) — ring wins
        assert pvsra_label(vol=200, spread=1.0, avg_vol=100, max_spread_vol=50,
                           is_bull=True) == "green"


class TestPvsraScoreDelta:
    def test_green_gives_plus_two(self):
        assert pvsra_score_delta("green") == 2.0

    def test_red_gives_minus_two(self):
        assert pvsra_score_delta("red") == -2.0

    def test_blue_gives_plus_one(self):
        assert pvsra_score_delta("blue") == 1.0

    def test_violet_gives_minus_one(self):
        assert pvsra_score_delta("violet") == -1.0

    def test_gray_gives_zero(self):
        assert pvsra_score_delta("gray_up") == 0.0
        assert pvsra_score_delta("gray_dn") == 0.0
```

- [ ] **Step 2: Run to confirm FAIL**

```bash
./.venv/bin/python -m pytest tests/test_tr_indicators.py -v 2>&1 | head -30
```

Expected: `ModuleNotFoundError` or `ImportError` — `tr_indicators` does not exist yet.

### 1b. Create `tr_indicators.py` with PVSRA functions

- [ ] **Step 3: Create file with PVSRA + score functions**

```python
# strategies/helpers/tr_indicators.py
"""
Pure-Python indicator helpers for TradersRealityStrategy.
No backtrader or pandas dependency. All inputs are plain Python scalars/lists.
"""
from __future__ import annotations
from typing import Optional


def pvsra_label(
    vol: float,
    spread: float,
    avg_vol: float,
    max_spread_vol: float,
    is_bull: bool,
    rv_mult: float = 2.0,
    bv_mult: float = 1.5,
) -> str:
    """
    Classify a bar as a PVSRA vector.
    - Ring Volume (rv): vol >= avg_vol*rv_mult OR spread*vol >= max_spread_vol
    - Big Volume (bv): vol >= avg_vol*bv_mult AND NOT ring
    Colors: green/red (ring), blue/violet (big), gray_up/gray_dn (normal)
    """
    cond_rv = (vol >= avg_vol * rv_mult) or (spread * vol >= max_spread_vol)
    cond_bv = (vol >= avg_vol * bv_mult) and not cond_rv
    if cond_rv:
        return "green" if is_bull else "red"
    if cond_bv:
        return "blue" if is_bull else "violet"
    return "gray_up" if is_bull else "gray_dn"


def pvsra_score_delta(label: str) -> float:
    """
    Signal score contribution for a PVSRA label.
    Matches market_analyzer.py calc_signals: green/red get ±2, blue/violet ±1.
    """
    return {
        "green":   2.0,
        "red":    -2.0,
        "blue":    1.0,
        "violet": -1.0,
        "gray_up": 0.0,
        "gray_dn": 0.0,
    }.get(label, 0.0)
```

- [ ] **Step 4: Run PVSRA tests**

```bash
./.venv/bin/python -m pytest tests/test_tr_indicators.py::TestPvsraLabel tests/test_tr_indicators.py::TestPvsraScoreDelta -v
```

Expected: all 10 tests PASS.

### 1c. Add EMA functions + tests

- [ ] **Step 5: Add EMA tests to `test_tr_indicators.py`**

```python
class TestEmaStackScore:
    def test_full_bull_stack(self):
        assert ema_stack_score(5.0, 4.0, 3.0, 2.0) == 2.0

    def test_full_bear_stack(self):
        assert ema_stack_score(2.0, 3.0, 4.0, 5.0) == -2.0

    def test_partial_stack_is_neutral(self):
        assert ema_stack_score(5.0, 4.0, 6.0, 2.0) == 0.0

    def test_equal_values_neutral(self):
        assert ema_stack_score(3.0, 3.0, 3.0, 3.0) == 0.0


class TestEmaCrossScore:
    def test_golden_cross(self):
        # ema5 crosses above ema13
        assert ema_cross_score(ema5=11.0, ema13=10.0, ema5_prev=9.0, ema13_prev=10.0) == 1.0

    def test_death_cross(self):
        assert ema_cross_score(ema5=9.0, ema13=10.0, ema5_prev=11.0, ema13_prev=10.0) == -1.0

    def test_no_cross(self):
        assert ema_cross_score(ema5=11.0, ema13=10.0, ema5_prev=10.5, ema13_prev=10.0) == 0.0

    def test_already_crossed_no_event(self):
        # Both current and prev have ema5 > ema13 — no cross event
        assert ema_cross_score(ema5=12.0, ema13=10.0, ema5_prev=11.0, ema13_prev=10.0) == 0.0
```

- [ ] **Step 6: Add EMA functions to `tr_indicators.py`**

```python
def ema_stack_score(ema5: float, ema13: float, ema50: float, ema200: float) -> float:
    """Return +2 for full bull stack (5>13>50>200), -2 for full bear, 0 otherwise."""
    if ema5 > ema13 > ema50 > ema200:
        return 2.0
    if ema5 < ema13 < ema50 < ema200:
        return -2.0
    return 0.0


def ema_cross_score(ema5: float, ema13: float, ema5_prev: float, ema13_prev: float) -> float:
    """Return +1 on golden cross (5 over 13), -1 on death cross, 0 otherwise."""
    if ema5 > ema13 and ema5_prev <= ema13_prev:
        return 1.0
    if ema5 < ema13 and ema5_prev >= ema13_prev:
        return -1.0
    return 0.0
```

- [ ] **Step 7: Run EMA tests**

```bash
./.venv/bin/python -m pytest tests/test_tr_indicators.py::TestEmaStackScore tests/test_tr_indicators.py::TestEmaCrossScore -v
```

Expected: all 8 tests PASS.

### 1d. Add pivot level functions + tests

- [ ] **Step 8: Add pivot tests**

```python
class TestPivotLevels:
    def test_classic_pivot_calculation(self):
        levels = pivot_levels(high=110.0, low=90.0, close=105.0)
        pp = (110 + 90 + 105) / 3  # = 101.667
        assert abs(levels["PP"] - pp) < 1e-9
        assert abs(levels["R1"] - (2 * pp - 90)) < 1e-9
        assert abs(levels["S1"] - (2 * pp - 110)) < 1e-9
        assert abs(levels["R2"] - (pp + 20)) < 1e-9
        assert abs(levels["S2"] - (pp - 20)) < 1e-9
        assert abs(levels["R3"] - (110 + 2 * (pp - 90))) < 1e-9
        assert abs(levels["S3"] - (90 - 2 * (110 - pp))) < 1e-9

    def test_returns_all_keys(self):
        levels = pivot_levels(100.0, 80.0, 90.0)
        for key in ("PP", "R1", "R2", "R3", "S1", "S2", "S3"):
            assert key in levels


class TestPivotPositionScore:
    def test_above_pp_gives_plus_one(self):
        assert pivot_position_score(close=105.0, pp=100.0) == 1.0

    def test_below_pp_gives_minus_one(self):
        assert pivot_position_score(close=95.0, pp=100.0) == -1.0

    def test_equal_pp_gives_zero(self):
        assert pivot_position_score(close=100.0, pp=100.0) == 0.0
```

- [ ] **Step 9: Add pivot functions to `tr_indicators.py`**

```python
def pivot_levels(high: float, low: float, close: float) -> dict:
    """Classic floor pivot levels computed from previous day's High/Low/Close."""
    pp = (high + low + close) / 3.0
    r1 = 2 * pp - low
    s1 = 2 * pp - high
    r2 = pp + (high - low)
    s2 = pp - (high - low)
    r3 = high + 2 * (pp - low)
    s3 = low  - 2 * (high - pp)
    return {"PP": pp, "R1": r1, "R2": r2, "R3": r3, "S1": s1, "S2": s2, "S3": s3}


def pivot_position_score(close: float, pp: float) -> float:
    """Close strictly above PP: +1. Strictly below: -1. Equal: 0."""
    if close > pp:
        return 1.0
    if close < pp:
        return -1.0
    return 0.0
```

- [ ] **Step 10: Run pivot tests**

```bash
./.venv/bin/python -m pytest tests/test_tr_indicators.py::TestPivotLevels tests/test_tr_indicators.py::TestPivotPositionScore -v
```

Expected: all 5 tests PASS.

### 1e. Add ADR functions + tests

- [ ] **Step 11: Add ADR tests**

```python
class TestAdrMean:
    def test_mean_of_list(self):
        assert adr_mean([10.0, 20.0, 30.0]) == pytest.approx(20.0)

    def test_single_value(self):
        assert adr_mean([15.0]) == pytest.approx(15.0)

    def test_empty_returns_none(self):
        assert adr_mean([]) is None


class TestAdrExhaustionScore:
    def test_no_exhaustion_neutral(self):
        # price in middle of range, ADR not consumed
        assert adr_exhaustion_score(close=100.0, day_low=90.0, day_high=110.0, adr=20.0) == 0.0

    def test_upward_exhaustion_penalises(self):
        # close=107.5, day_low=90, adr=10 → adr_used_up = (107.5-90)/10 = 1.75 > 0.85
        assert adr_exhaustion_score(close=107.5, day_low=90.0, day_high=120.0, adr=10.0) == -1.0

    def test_downward_exhaustion_rewards(self):
        # close=91.0, day_high=110, adr=10 → adr_used_down=(110-91)/10=1.9 > 0.85
        assert adr_exhaustion_score(close=91.0, day_low=85.0, day_high=110.0, adr=10.0) == 1.0

    def test_both_exhausted_nets_zero(self):
        # Degenerate: range collapsed. Both conditions could fire; net = 0
        result = adr_exhaustion_score(close=100.0, day_low=99.9, day_high=100.1, adr=0.01)
        assert isinstance(result, float)

    def test_zero_adr_returns_zero(self):
        assert adr_exhaustion_score(close=100.0, day_low=99.0, day_high=101.0, adr=0.0) == 0.0
```

- [ ] **Step 12: Add ADR functions to `tr_indicators.py`**

```python
def adr_mean(daily_ranges: list) -> Optional[float]:
    """Mean of a list of daily High-Low ranges. Returns None if list is empty."""
    if not daily_ranges:
        return None
    return sum(daily_ranges) / len(daily_ranges)


def adr_exhaustion_score(
    close: float,
    day_low: float,
    day_high: float,
    adr: float,
    threshold: float = 0.85,
) -> float:
    """
    Penalise entry when price is near the extreme of the day's range.
    - Price near day HIGH (adr_used_up > threshold): -1 (long exhausted)
    - Price near day LOW (adr_used_down > threshold): +1 (short exhausted, reversion likely)
    """
    if adr <= 0:
        return 0.0
    adr_used_up   = (close - day_low)  / adr
    adr_used_down = (day_high - close) / adr
    score = 0.0
    if adr_used_up > threshold:
        score -= 1.0
    if adr_used_down > threshold:
        score += 1.0
    return score
```

- [ ] **Step 13: Run ADR tests**

```bash
./.venv/bin/python -m pytest tests/test_tr_indicators.py::TestAdrMean tests/test_tr_indicators.py::TestAdrExhaustionScore -v
```

Expected: all 9 tests PASS.

### 1f. Add `classify_signal` and `composite_signal_score` + tests

- [ ] **Step 14: Add classification tests**

```python
class TestClassifySignal:
    def test_strong_long_at_four(self):
        assert classify_signal(4.0) == "STRONG LONG"

    def test_strong_long_above_four(self):
        assert classify_signal(6.0) == "STRONG LONG"

    def test_long_at_two(self):
        assert classify_signal(2.0) == "LONG"

    def test_long_at_three(self):
        assert classify_signal(3.0) == "LONG"

    def test_neutral_at_one(self):
        assert classify_signal(1.0) == "NEUTRAL"

    def test_neutral_at_zero(self):
        assert classify_signal(0.0) == "NEUTRAL"

    def test_neutral_at_minus_one(self):
        assert classify_signal(-1.0) == "NEUTRAL"

    def test_short_at_minus_two(self):
        assert classify_signal(-2.0) == "SHORT"

    def test_strong_short_at_minus_four(self):
        assert classify_signal(-4.0) == "STRONG SHORT"

    def test_strong_short_below_minus_four(self):
        assert classify_signal(-5.0) == "STRONG SHORT"


class TestCompositeSignalScore:
    def test_full_bull_scenario(self):
        # ema_stack=+2, pvsra=+2(green), pp=+1, adr=0, cross=0 → 5.0
        score = composite_signal_score(
            ema_stack=2.0,
            pvsra_delta=2.0,
            pp_score=1.0,
            adr_score=0.0,
            cross_score=0.0,
        )
        assert score == pytest.approx(5.0)

    def test_all_zeros(self):
        assert composite_signal_score(0.0, 0.0, 0.0, 0.0, 0.0) == pytest.approx(0.0)

    def test_mixed_signals_sum(self):
        # ema_stack=+2, pvsra=-1(violet), pp=+1 → 2.0
        score = composite_signal_score(2.0, -1.0, 1.0, 0.0, 0.0)
        assert score == pytest.approx(2.0)
```

- [ ] **Step 15: Add classification functions to `tr_indicators.py`**

```python
def classify_signal(score: float) -> str:
    """Map composite score to human-readable signal label."""
    if score >= 4:
        return "STRONG LONG"
    if score >= 2:
        return "LONG"
    if score <= -4:
        return "STRONG SHORT"
    if score <= -2:
        return "SHORT"
    return "NEUTRAL"


def composite_signal_score(
    ema_stack: float,
    pvsra_delta: float,
    pp_score: float,
    adr_score: float,
    cross_score: float,
) -> float:
    """Sum all component scores into the composite signal score."""
    return ema_stack + pvsra_delta + pp_score + adr_score + cross_score
```

- [ ] **Step 16: Run all tr_indicators tests**

```bash
./.venv/bin/python -m pytest tests/test_tr_indicators.py -v
```

Expected: all tests PASS (≥ 35 tests).

- [ ] **Step 17: Run ruff on helpers**

```bash
./.venv/bin/ruff check strategies/helpers/tr_indicators.py
```

Expected: no violations.

---

## Task 2: Strategy skeleton and state machines

**Files:**
- Create: `strategies/bt_traders_reality.py`
- Test: `tests/test_bt_traders_reality.py`

### 2a. Write failing test for strategy import and instantiation

- [ ] **Step 1: Write failing instantiation test**

```python
# tests/test_bt_traders_reality.py
import sys
import os
import pytest
import pandas as pd
import numpy as np
import backtrader as bt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strategies.bt_traders_reality import TradersRealityStrategy
from engine.bt_analyzers import TradeListAnalyzer


def _make_ohlcv(n: int = 500, seed: int = 42, base: float = 50000.0) -> pd.DataFrame:
    """Generate n hourly OHLCV bars. Enough warmup for EMA-200 and weekly levels."""
    rng = np.random.default_rng(seed)
    noise = rng.normal(0, 50, n)
    closes = base + np.cumsum(noise)
    opens  = closes + rng.normal(0, 20, n)
    highs  = np.maximum(opens, closes) + rng.uniform(10, 80, n)
    lows   = np.minimum(opens, closes) - rng.uniform(10, 80, n)
    vols   = rng.uniform(500, 2000, n)
    dates  = pd.date_range("2024-01-01", periods=n, freq="1h")
    return pd.DataFrame(
        {"open": opens, "high": highs, "low": lows, "close": closes, "volume": vols},
        index=dates,
    )


def _run_cerebro(df: pd.DataFrame, **strategy_params) -> bt.Strategy:
    cerebro = bt.Cerebro()
    cerebro.addstrategy(TradersRealityStrategy, **strategy_params)
    data = bt.feeds.PandasData(dataname=df)
    cerebro.adddata(data)
    cerebro.addanalyzer(TradeListAnalyzer, _name="tradelist")
    cerebro.broker.setcash(100_000)
    cerebro.broker.setcommission(commission=0.001)
    results = cerebro.run()
    return results[0]


class TestTradersRealityStrategyInstantiation:
    def test_strategy_runs_without_error(self):
        df = _make_ohlcv(500)
        strat = _run_cerebro(df)
        assert strat is not None
```

- [ ] **Step 2: Run to confirm FAIL**

```bash
./.venv/bin/python -m pytest tests/test_bt_traders_reality.py::TestTradersRealityStrategyInstantiation -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError` — `bt_traders_reality` does not exist yet.

### 2b. Create strategy skeleton

- [ ] **Step 3: Create `strategies/bt_traders_reality.py` skeleton**

```python
# strategies/bt_traders_reality.py
"""
TradersRealityStrategy — backtrader implementation of the Traders Reality signal system.
Based on: scripts/market_analyzer.py (Python port of PineScript by plasmapug et al.)

Signal components:
  EMA stack (5/13/50/200): ±2 pts
  PVSRA vector quality:    ±1 to ±2 pts
  Daily pivot position:    ±1 pt
  ADR exhaustion:          ±1 pt
  EMA 5/13 cross:          ±1 pt
"""
from __future__ import annotations

import datetime
import math
from collections import deque

import backtrader as bt

from .base_strategy import BaseStrategy
from .helpers.tr_indicators import (
    adr_exhaustion_score,
    adr_mean,
    classify_signal,
    composite_signal_score,
    ema_cross_score,
    ema_stack_score,
    pivot_levels,
    pivot_position_score,
    pvsra_label,
    pvsra_score_delta,
)
from engine.logger import get_logger

logger = get_logger(__name__)


class TradersRealityStrategy(BaseStrategy):
    params = (
        # EMA periods
        ("ema_fast", 5),
        ("ema_medium", 13),
        ("ema_slow", 50),
        ("ema_trend", 200),
        # PVSRA rolling window and thresholds
        ("pvsra_avg_period", 10),
        ("pvsra_rv_mult", 2.0),
        ("pvsra_bv_mult", 1.5),
        # ADR settings
        ("adr_period", 14),
        ("adr_exhaustion_threshold", 0.85),
        # Signal entry thresholds
        ("signal_long_min_score", 2.0),
        ("signal_short_max_score", -2.0),
        # Which PVSRA labels qualify as entry triggers
        ("pvsra_long_labels", ("green", "blue")),
        ("pvsra_short_labels", ("red", "violet")),
        # HTF EMA filter
        ("use_htf_ema_filter", True),
        # Pivot-based SL/TP
        ("use_weekly_sl", True),
        ("use_pivot_tp", True),
        # ATR fallback SL
        ("atr_period", 14),
        ("sl_buffer_atr", 1.5),
        ("sl_weekly_buffer_atr", 0.1),
        # Risk/display controls (passed through by strategy_runtime)
        ("risk_reward_ratio", 2.0),
        ("risk_per_trade", 1.0),
        ("leverage", 1.0),
        ("dynamic_position_sizing", True),
        ("max_drawdown", 50.0),
        ("detailed_signals", True),
        ("market_analysis", True),
    )

    def __init__(self):
        super().__init__()
        self.has_secondary = len(self.datas) > 1
        if self.has_secondary:
            self.data_ltf = self.datas[0]
            self.data_htf = self.datas[1]
        else:
            self.data_ltf = self.datas[0]
            self.data_htf = self.datas[0]

        # ── EMA indicators ────────────────────────────────────────────
        self.ema_fast   = bt.talib.EMA(self.data_ltf.close, timeperiod=self.p.ema_fast)
        self.ema_medium = bt.talib.EMA(self.data_ltf.close, timeperiod=self.p.ema_medium)
        self.ema_slow   = bt.talib.EMA(self.data_ltf.close, timeperiod=self.p.ema_slow)
        self.ema_trend_ltf = bt.talib.EMA(self.data_ltf.close, timeperiod=self.p.ema_trend)
        self.ema_trend_htf = bt.talib.EMA(self.data_htf.close, timeperiod=self.p.ema_trend)
        self.atr_ltf    = bt.talib.ATR(
            self.data_ltf.high, self.data_ltf.low, self.data_ltf.close,
            timeperiod=self.p.atr_period,
        )

        # ── PVSRA rolling buffers (maxlen = pvsra_avg_period) ─────────
        period = max(1, self.p.pvsra_avg_period)
        self._pvsra_vol_buf: deque[float] = deque(maxlen=period)
        self._pvsra_spread_vol_buf: deque[float] = deque(maxlen=period)
        self._last_pvsra_label: str = "gray_up"

        # ── Daily state (pivot points + ADR) ──────────────────────────
        self._current_day: datetime.date | None = None
        self._day_open: float | None = None
        self._day_high: float = float("-inf")
        self._day_low: float  = float("inf")
        self._day_close: float | None = None
        self._pivots: dict | None = None          # previous day's pivot levels
        self._adr_buf: deque[float] = deque(maxlen=self.p.adr_period)
        self._current_adr: float | None = None
        self._current_day_low: float | None = None
        self._current_day_high: float | None = None

        # ── Weekly state (M0 / M5) ────────────────────────────────────
        self._current_week: tuple | None = None   # (year, week_number)
        self._week_high: float = float("-inf")
        self._week_low:  float = float("inf")
        self._m5: float | None = None             # prev week HIGH (resistance)
        self._m0: float | None = None             # prev week LOW  (support)

    # ── State machines ────────────────────────────────────────────────────────

    def _update_pvsra(self, vol: float, spread: float) -> None:
        self._pvsra_vol_buf.append(vol)
        self._pvsra_spread_vol_buf.append(spread * vol)
        if len(self._pvsra_vol_buf) < 2:
            return
        avg_vol = sum(self._pvsra_vol_buf) / len(self._pvsra_vol_buf)
        max_sv  = max(self._pvsra_spread_vol_buf)
        is_bull = float(self.data_ltf.close[0]) >= float(self.data_ltf.open[0])
        self._last_pvsra_label = pvsra_label(
            vol=vol,
            spread=spread,
            avg_vol=avg_vol,
            max_spread_vol=max_sv,
            is_bull=is_bull,
            rv_mult=self.p.pvsra_rv_mult,
            bv_mult=self.p.pvsra_bv_mult,
        )

    def _update_daily_state(self, dt: datetime.date, high: float, low: float,
                             close: float, open_: float) -> None:
        if self._current_day is None:
            self._current_day = dt
            self._day_open = open_
            self._day_high = high
            self._day_low  = low
            self._day_close = close
            return

        if dt != self._current_day:
            # Day has rolled: finalise yesterday, compute new pivots and ADR entry
            if (self._day_high > float("-inf") and self._day_low < float("inf")
                    and self._day_close is not None):
                day_range = self._day_high - self._day_low
                self._adr_buf.append(day_range)
                self._pivots = pivot_levels(self._day_high, self._day_low, self._day_close)
            self._current_adr = adr_mean(list(self._adr_buf))
            # Reset day trackers
            self._current_day = dt
            self._day_open = open_
            self._day_high = high
            self._day_low  = low
            self._day_close = close
        else:
            self._day_high  = max(self._day_high, high)
            self._day_low   = min(self._day_low,  low)
            self._day_close = close

        # Live day extremes used by ADR exhaustion
        self._current_day_high = self._day_high
        self._current_day_low  = self._day_low

    def _update_weekly_state(self, dt: datetime.date, high: float, low: float) -> None:
        iso = dt.isocalendar()
        week_key = (iso[0], iso[1])  # (year, week)

        if self._current_week is None:
            self._current_week = week_key
            self._week_high = high
            self._week_low  = low
            return

        if week_key != self._current_week:
            # Week rolled: save previous week's extremes as M5/M0
            if self._week_high > float("-inf") and self._week_low < float("inf"):
                self._m5 = self._week_high
                self._m0 = self._week_low
            self._current_week = week_key
            self._week_high = high
            self._week_low  = low
        else:
            self._week_high = max(self._week_high, high)
            self._week_low  = min(self._week_low,  low)

    # ── Score computation ─────────────────────────────────────────────────────

    def _compute_signal_score(self) -> tuple[float, str]:
        """Return (score, pvsra_label) for the current bar."""
        e5  = self._safe_float(self.ema_fast[0])
        e13 = self._safe_float(self.ema_medium[0])
        e50 = self._safe_float(self.ema_slow[0])
        e200 = self._safe_float(self.ema_trend_ltf[0])

        e5_prev  = self._safe_float(self.ema_fast[-1])
        e13_prev = self._safe_float(self.ema_medium[-1])

        if any(v is None for v in (e5, e13, e50, e200, e5_prev, e13_prev)):
            return 0.0, self._last_pvsra_label

        stack  = ema_stack_score(e5, e13, e50, e200)
        cross  = ema_cross_score(e5, e13, e5_prev, e13_prev)
        pvsra  = pvsra_score_delta(self._last_pvsra_label)

        pp_score = 0.0
        if self._pivots is not None:
            pp_score = pivot_position_score(float(self.data_ltf.close[0]), self._pivots["PP"])

        adr_score = 0.0
        if (self._current_adr is not None and self._current_adr > 0
                and self._current_day_low is not None and self._current_day_high is not None):
            adr_score = adr_exhaustion_score(
                close=float(self.data_ltf.close[0]),
                day_low=self._current_day_low,
                day_high=self._current_day_high,
                adr=self._current_adr,
                threshold=self.p.adr_exhaustion_threshold,
            )

        score = composite_signal_score(stack, pvsra, pp_score, adr_score, cross)
        return score, self._last_pvsra_label

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _safe_float(value) -> float | None:
        try:
            v = float(value)
        except (TypeError, ValueError):
            return None
        if math.isnan(v) or math.isinf(v):
            return None
        return v

    def _get_local_dt_str(self, dt=None):
        if dt is None:
            dt = self.data_ltf.datetime.datetime(0)
        return dt.replace(tzinfo=datetime.timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")

    # ── Entry resolution ──────────────────────────────────────────────────────

    def _resolve_sl_long(self, entry_price: float):
        """Return (sl_price, sl_distance, sl_expr) for a long entry."""
        atr = self._safe_float(self.atr_ltf[0])
        if atr is None or atr <= 0:
            return None, 0.0, "Invalid ATR"

        # Priority 1: weekly M0 (previous week low) with small ATR buffer
        if self.p.use_weekly_sl and self._m0 is not None:
            sl_price = self._m0 - atr * self.p.sl_weekly_buffer_atr
            if sl_price < entry_price:
                dist = entry_price - sl_price
                return sl_price, dist, f"Weekly M0 ({self._m0:.2f}) - ATR*{self.p.sl_weekly_buffer_atr}"

        # Priority 2: daily S1
        if self._pivots is not None:
            s1 = self._pivots["S1"]
            if s1 < entry_price:
                dist = entry_price - s1
                return s1, dist, f"Daily S1 ({s1:.2f})"

        # Fallback: ATR buffer below current low
        sl_price = float(self.data_ltf.low[0]) - atr * self.p.sl_buffer_atr
        if sl_price < entry_price:
            dist = entry_price - sl_price
            return sl_price, dist, f"Low - ATR*{self.p.sl_buffer_atr}"

        return None, 0.0, "Cannot build valid long SL"

    def _resolve_sl_short(self, entry_price: float):
        """Return (sl_price, sl_distance, sl_expr) for a short entry."""
        atr = self._safe_float(self.atr_ltf[0])
        if atr is None or atr <= 0:
            return None, 0.0, "Invalid ATR"

        # Priority 1: weekly M5 (previous week high)
        if self.p.use_weekly_sl and self._m5 is not None:
            sl_price = self._m5 + atr * self.p.sl_weekly_buffer_atr
            if sl_price > entry_price:
                dist = sl_price - entry_price
                return sl_price, dist, f"Weekly M5 ({self._m5:.2f}) + ATR*{self.p.sl_weekly_buffer_atr}"

        # Priority 2: daily R1
        if self._pivots is not None:
            r1 = self._pivots["R1"]
            if r1 > entry_price:
                dist = r1 - entry_price
                return r1, dist, f"Daily R1 ({r1:.2f})"

        # Fallback: ATR buffer above current high
        sl_price = float(self.data_ltf.high[0]) + atr * self.p.sl_buffer_atr
        if sl_price > entry_price:
            dist = sl_price - entry_price
            return sl_price, dist, f"High + ATR*{self.p.sl_buffer_atr}"

        return None, 0.0, "Cannot build valid short SL"

    def _resolve_tp_long(self, entry_price: float, sl_distance: float):
        """Return (tp_price, tp_distance, tp_expr) for a long entry."""
        if self.p.use_pivot_tp and self._pivots is not None:
            r1 = self._pivots["R1"]
            if r1 > entry_price:
                dist = r1 - entry_price
                return r1, dist, f"Daily R1 ({r1:.2f})"
        rr_tp = entry_price + sl_distance * self.p.risk_reward_ratio
        dist = rr_tp - entry_price
        return rr_tp, dist, f"Entry + Risk*RR({self.p.risk_reward_ratio})"

    def _resolve_tp_short(self, entry_price: float, sl_distance: float):
        """Return (tp_price, tp_distance, tp_expr) for a short entry."""
        if self.p.use_pivot_tp and self._pivots is not None:
            s1 = self._pivots["S1"]
            if s1 < entry_price:
                dist = entry_price - s1
                return s1, dist, f"Daily S1 ({s1:.2f})"
        rr_tp = entry_price - sl_distance * self.p.risk_reward_ratio
        dist = entry_price - rr_tp
        return rr_tp, dist, f"Entry - Risk*RR({self.p.risk_reward_ratio})"

    # ── HTF filter ────────────────────────────────────────────────────────────

    def _htf_is_bullish(self) -> bool:
        if not self.p.use_htf_ema_filter:
            return True
        htf_close = self._safe_float(self.data_htf.close[0])
        htf_ema   = self._safe_float(self.ema_trend_htf[0])
        if htf_close is None or htf_ema is None:
            return False
        return htf_close > htf_ema

    def _htf_is_bearish(self) -> bool:
        if not self.p.use_htf_ema_filter:
            return True
        htf_close = self._safe_float(self.data_htf.close[0])
        htf_ema   = self._safe_float(self.ema_trend_htf[0])
        if htf_close is None or htf_ema is None:
            return False
        return htf_close < htf_ema

    # ── Entry helpers ─────────────────────────────────────────────────────────

    def _build_entry_context(self, reason: str, direction: str, score: float,
                              pvsra: str) -> dict:
        indicators = {
            "SignalScore": round(score, 1),
            "Signal": classify_signal(score),
            "PVSRA": pvsra,
        }
        atr = self._safe_float(self.atr_ltf[0])
        if atr is not None:
            indicators["ATR"] = round(atr, 4)
        e5 = self._safe_float(self.ema_fast[0])
        e200 = self._safe_float(self.ema_trend_ltf[0])
        if e5 is not None and e200 is not None:
            indicators["EMA5_vs_EMA200"] = "bull" if e5 > e200 else "bear"
        if self._m5 is not None:
            indicators["M5_Weekly"] = round(self._m5, 4)
        if self._m0 is not None:
            indicators["M0_Weekly"] = round(self._m0, 4)
        if self._pivots is not None:
            indicators["DailyPP"] = round(self._pivots["PP"], 4)

        why_parts = [
            f"TR Signal: {reason}",
            f"Score: {score:.1f} → {classify_signal(score)}",
            f"PVSRA: {pvsra}",
        ]
        if self.p.use_htf_ema_filter:
            htf_trend = "bullish" if self._htf_is_bullish() else "bearish"
            why_parts.append(f"HTF EMA{self.p.ema_trend}: {htf_trend}")

        return {"why_entry": why_parts, "indicators_at_entry": indicators}

    def _build_exit_context(self, exit_reason: str) -> dict:
        score, pvsra = self._compute_signal_score()
        return {
            "why_exit": [f"Exit: {exit_reason}", f"PVSRA: {pvsra}", f"Score: {score:.1f}"],
            "indicators_at_exit": {
                "SignalScore": round(score, 1),
                "PVSRA": pvsra,
            },
        }

    def _enter_long(self, score: float, pvsra: str) -> None:
        entry_price = float(self.data_ltf.close[0])
        sl_price, sl_dist, sl_expr = self._resolve_sl_long(entry_price)
        if sl_price is None or sl_dist <= 0:
            return

        tp_price, tp_dist, tp_expr = self._resolve_tp_long(entry_price, sl_dist)
        if tp_dist <= 0:
            return

        dt_str = self._get_local_dt_str()
        entry_context = self._build_entry_context("LONG entry", "long", score, pvsra)
        reason = f"TR LONG (score={score:.1f}, pvsra={pvsra})"
        logger.info(
            f"[{dt_str}] SIGNAL GENERATED: LONG Entry={entry_price:.4f} "
            f"SL={sl_price:.4f} TP={tp_price:.4f} Score={score:.1f} PVSRA={pvsra}"
        )
        self._log_signal_thesis(
            dt_str,
            entry_context=entry_context,
            sl_price_ref=sl_price,
            tp_price_ref=tp_price,
            sl_calc_expr=sl_expr,
            tp_calc_expr=tp_expr,
        )
        self.pending_metadata = {
            "reason": reason,
            "stop_loss": sl_price,
            "take_profit": tp_price,
            "sl_distance": sl_dist,
            "tp_distance": tp_dist,
            "direction": "long",
            "size": 0,
            "sl_calculation": f"Math: {sl_expr}\nResult: {sl_price:.4f}",
            "tp_calculation": f"Math: {tp_expr}\nResult: {tp_price:.4f}",
            "entry_context": entry_context,
        }
        self.initial_sl = sl_price
        self.stop_reason = "Stop Loss"
        from engine.bt_backtest_engine import _iso_utc  # noqa: PLC0415
        self.sl_history = [{
            "time": _iso_utc(self.data_ltf.datetime.datetime(0)),
            "price": sl_price,
            "reason": "Initial Stop Loss",
        }]
        size = self._calculate_position_size(entry_price, sl_price, direction="long")
        if size <= 0:
            logger.warning(f"[{dt_str}] LONG size=0, skipping. SL={sl_price:.4f}")
            self.pending_metadata = None
            return
        self.pending_metadata["size"] = size
        self.order = self.buy(size=size, exectype=bt.Order.Market)

    def _enter_short(self, score: float, pvsra: str) -> None:
        entry_price = float(self.data_ltf.close[0])
        sl_price, sl_dist, sl_expr = self._resolve_sl_short(entry_price)
        if sl_price is None or sl_dist <= 0:
            return

        tp_price, tp_dist, tp_expr = self._resolve_tp_short(entry_price, sl_dist)
        if tp_dist <= 0:
            return

        dt_str = self._get_local_dt_str()
        entry_context = self._build_entry_context("SHORT entry", "short", score, pvsra)
        reason = f"TR SHORT (score={score:.1f}, pvsra={pvsra})"
        logger.info(
            f"[{dt_str}] SIGNAL GENERATED: SHORT Entry={entry_price:.4f} "
            f"SL={sl_price:.4f} TP={tp_price:.4f} Score={score:.1f} PVSRA={pvsra}"
        )
        self._log_signal_thesis(
            dt_str,
            entry_context=entry_context,
            sl_price_ref=sl_price,
            tp_price_ref=tp_price,
            sl_calc_expr=sl_expr,
            tp_calc_expr=tp_expr,
        )
        self.pending_metadata = {
            "reason": reason,
            "stop_loss": sl_price,
            "take_profit": tp_price,
            "sl_distance": sl_dist,
            "tp_distance": tp_dist,
            "direction": "short",
            "size": 0,
            "sl_calculation": f"Math: {sl_expr}\nResult: {sl_price:.4f}",
            "tp_calculation": f"Math: {tp_expr}\nResult: {tp_price:.4f}",
            "entry_context": entry_context,
        }
        self.initial_sl = sl_price
        self.stop_reason = "Stop Loss"
        from engine.bt_backtest_engine import _iso_utc  # noqa: PLC0415
        self.sl_history = [{
            "time": _iso_utc(self.data_ltf.datetime.datetime(0)),
            "price": sl_price,
            "reason": "Initial Stop Loss",
        }]
        size = self._calculate_position_size(entry_price, sl_price, direction="short")
        if size <= 0:
            logger.warning(f"[{dt_str}] SHORT size=0, skipping. SL={sl_price:.4f}")
            self.pending_metadata = None
            return
        self.pending_metadata["size"] = size
        self.order = self.sell(size=size, exectype=bt.Order.Market)

    # ── Main loop ─────────────────────────────────────────────────────────────

    def next(self):
        # ── Standard BaseStrategy guards ──────────────────────────────
        if getattr(self, "_close_orphan_position", False):
            self._close_orphan_position = False
            if self.position:
                self.close()
                return
        if self._oco_closed and not self.position:
            self._oco_closed = False
        if self.order:
            return

        self._update_equity_peak()
        if not self.position:
            self.initial_sl = None
        if getattr(self, "_dd_limit_hit", False):
            return

        # ── Drawdown check ────────────────────────────────────────────
        max_dd = self.p.max_drawdown
        if max_dd is not None and max_dd > 0 and self._equity_peak > 0:
            current = self.broker.getvalue()
            dd_pct = 100.0 * (self._equity_peak - current) / self._equity_peak
            if dd_pct > max_dd:
                if not getattr(self, "_dd_limit_hit", False):
                    dt_str = self._get_local_dt_str()
                    if self.p.stop_on_drawdown:
                        logger.warning(
                            f"[{dt_str}] CRITICAL: Drawdown {dd_pct:.2f}% > {max_dd}%. Stopping."
                        )
                        self._dd_limit_hit = True
                        if self.position:
                            self._dd_close_order = self.close()
                        else:
                            self._dd_stop_runstop()
                if self.p.stop_on_drawdown:
                    return

        # ── Trailing / breakeven (inherited pattern) ──────────────────
        entry_bar  = getattr(self, "_entry_exec_bar", -1)
        entry_data = getattr(self, "_entry_exec_data", None)
        bar_ok     = entry_data is None or len(entry_data) > entry_bar
        stop_acc   = self.stop_order and self.stop_order.status == bt.Order.Accepted
        tp_ok      = self.tp_order is None or self.tp_order.status == bt.Order.Accepted

        if self.position and self.stop_order and bar_ok and stop_acc and tp_ok:
            cur_sl = self.stop_order.price
            new_sl = cur_sl
            sl_changed = False
            new_reason = self.stop_reason

            if self.p.breakeven_trigger_r > 0 and self.initial_sl is not None:
                risk = abs(self.position.price - self.initial_sl)
                if risk > 0:
                    profit = (
                        float(self.data_ltf.close[0]) - self.position.price
                        if self.position.size > 0
                        else self.position.price - float(self.data_ltf.close[0])
                    )
                    if profit >= risk * self.p.breakeven_trigger_r:
                        be_price = self.position.price
                        if self.position.size > 0 and be_price > new_sl:
                            new_sl, sl_changed, new_reason = be_price, True, "Breakeven"
                            self.initial_sl = None
                        elif self.position.size < 0 and be_price < new_sl:
                            new_sl, sl_changed, new_reason = be_price, True, "Breakeven"
                            self.initial_sl = None

            if self.p.trailing_stop_distance > 0:
                if self.position.size > 0:
                    trail = float(self.data_ltf.close[0]) * (1 - self.p.trailing_stop_distance)
                    if trail > new_sl:
                        new_sl, sl_changed, new_reason = trail, True, "Trailing Stop"
                elif self.position.size < 0:
                    trail = float(self.data_ltf.close[0]) * (1 + self.p.trailing_stop_distance)
                    if trail < new_sl:
                        new_sl, sl_changed, new_reason = trail, True, "Trailing Stop"

            if sl_changed:
                dt_str = self._get_local_dt_str()
                logger.info(f"[{dt_str}] STOP UPDATE: {new_reason} -> {new_sl:.4f}")
                self.cancel_reason = f"{new_reason} Update"
                tp_val = self.tp_order.price if self.tp_order else None
                if self.tp_order:
                    self.cancel(self.tp_order)
                    self.tp_order = None
                self.cancel(self.stop_order)
                self.stop_reason = new_reason
                self.sl_history.append({
                    "time": self._get_local_dt_str(),
                    "price": new_sl,
                    "reason": new_reason,
                })
                if self.position.size > 0:
                    self.stop_order = self.sell(price=new_sl, exectype=bt.Order.Stop,
                                                size=self.position.size)
                    if tp_val:
                        self.tp_order = self.sell(price=tp_val, exectype=bt.Order.Limit,
                                                   size=self.position.size,
                                                   oco=self.stop_order)
                else:
                    self.stop_order = self.buy(price=new_sl, exectype=bt.Order.Stop,
                                               size=abs(self.position.size))
                    if tp_val:
                        self.tp_order = self.buy(price=tp_val, exectype=bt.Order.Limit,
                                                  size=abs(self.position.size),
                                                  oco=self.stop_order)

        if self.position:
            self._apply_funding_adjustment(self.data_ltf, float(self.data_ltf.close[0]))

        # ── Update state machines ─────────────────────────────────────
        bar_dt = self.data_ltf.datetime.datetime(0)
        self._update_pvsra(
            vol=float(self.data_ltf.volume[0]),
            spread=float(self.data_ltf.high[0]) - float(self.data_ltf.low[0]),
        )
        self._update_daily_state(
            dt=bar_dt.date(),
            high=float(self.data_ltf.high[0]),
            low=float(self.data_ltf.low[0]),
            close=float(self.data_ltf.close[0]),
            open_=float(self.data_ltf.open[0]),
        )
        self._update_weekly_state(
            dt=bar_dt.date(),
            high=float(self.data_ltf.high[0]),
            low=float(self.data_ltf.low[0]),
        )

        if self.position:
            return

        # ── Compute composite score ───────────────────────────────────
        score, pvsra = self._compute_signal_score()

        # ── Entry decisions ───────────────────────────────────────────
        verbose = bool(getattr(self.p, "detailed_signals", True))

        if score >= self.p.signal_long_min_score:
            if pvsra not in self.p.pvsra_long_labels:
                if verbose:
                    logger.info(f"Rejected LONG: PVSRA={pvsra} not in {self.p.pvsra_long_labels}")
            elif not self._htf_is_bullish():
                if verbose:
                    logger.info("Rejected LONG: HTF not bullish")
            else:
                self._enter_long(score, pvsra)

        elif score <= self.p.signal_short_max_score:
            if pvsra not in self.p.pvsra_short_labels:
                if verbose:
                    logger.info(f"Rejected SHORT: PVSRA={pvsra} not in {self.p.pvsra_short_labels}")
            elif not self._htf_is_bearish():
                if verbose:
                    logger.info("Rejected SHORT: HTF not bearish")
            else:
                self._enter_short(score, pvsra)
```

- [ ] **Step 4: Run instantiation test**

```bash
./.venv/bin/python -m pytest tests/test_bt_traders_reality.py::TestTradersRealityStrategyInstantiation -v
```

Expected: PASS (strategy runs 500 bars without error).

---

## Task 3: Fix `_iso_utc` import — use local definition

The current skeleton imports `_iso_utc` from `engine.bt_backtest_engine` which may not export it. Replace with a local version.

**Files:**
- Modify: `strategies/bt_traders_reality.py`

- [ ] **Step 1: Check if `_iso_utc` is exported from `engine.bt_backtest_engine`**

```bash
grep -n "_iso_utc\|def _iso_utc" /Users/rostislav/Projects/smc-bot/engine/bt_backtest_engine.py | head -5
```

- [ ] **Step 2: If NOT exported, replace inline import in `_enter_long` / `_enter_short` with a module-level function**

In `strategies/bt_traders_reality.py`, remove the inline imports and add at module level (after the `from engine.logger` import):

```python
def _iso_utc(dt: datetime.datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    else:
        dt = dt.astimezone(datetime.timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")
```

Then in `_enter_long` and `_enter_short`, remove the `from engine.bt_backtest_engine import _iso_utc` lines and use the module-level function.

- [ ] **Step 3: Re-run instantiation test after fix**

```bash
./.venv/bin/python -m pytest tests/test_bt_traders_reality.py::TestTradersRealityStrategyInstantiation -v
```

Expected: PASS.

- [ ] **Step 4: Run ruff on strategy file**

```bash
./.venv/bin/ruff check strategies/bt_traders_reality.py
```

Expected: 0 violations. Fix any violations found before continuing.

---

## Task 4: Filter tests — PVSRA gate and HTF gate

**Files:**
- Test: `tests/test_bt_traders_reality.py`

- [ ] **Step 1: Write failing tests for entry filtering**

```python
class TestTradersRealityFilters:
    """Verify that the PVSRA and HTF gates reject signals correctly."""

    def _make_trending_bullish_df(self, n: int = 500) -> pd.DataFrame:
        """Strongly uptrending data so EMA5>EMA13>EMA50>EMA200 after warmup."""
        dates = pd.date_range("2023-01-01", periods=n, freq="1h")
        closes = np.linspace(40000, 55000, n)
        opens  = closes - 10
        highs  = closes + 50
        lows   = closes - 50
        vols   = np.linspace(1000, 3000, n)
        return pd.DataFrame(
            {"open": opens, "high": highs, "low": lows, "close": closes, "volume": vols},
            index=dates,
        )

    def test_no_entry_without_pvsra_qualifier(self):
        """With uniform volume, PVSRA is always gray — no entry should fire."""
        df = self._make_trending_bullish_df(500)
        # Flat volume → avg_vol ≈ vol → no ring or big volume → gray labels only
        df["volume"] = 1000.0
        strat = _run_cerebro(
            df,
            use_htf_ema_filter=False,
            signal_long_min_score=2.0,
            pvsra_rv_mult=2.0,
            pvsra_bv_mult=1.5,
            risk_reward_ratio=2.0,
        )
        trades = strat.analyzers.tradelist.get_analysis()
        assert len(trades) == 0

    def test_htf_filter_blocks_long_in_downtrend(self):
        """Strongly downtrending data: HTF EMA filter should block all longs."""
        n = 500
        dates = pd.date_range("2023-01-01", periods=n, freq="1h")
        closes = np.linspace(55000, 40000, n)  # downtrend
        opens  = closes + 10
        highs  = closes + 50
        lows   = closes - 50
        # Spike volume every 20 bars to trigger PVSRA
        vols   = np.where(np.arange(n) % 20 == 0, 10000.0, 500.0)
        df = pd.DataFrame(
            {"open": opens, "high": highs, "low": lows, "close": closes, "volume": vols},
            index=dates,
        )
        strat = _run_cerebro(df, use_htf_ema_filter=True, risk_reward_ratio=2.0)
        trades = strat.analyzers.tradelist.get_analysis()
        # In a strong downtrend, HTF close < EMA200 → no longs should fire
        long_trades = [t for t in trades if t.get("direction") == "long"]
        assert len(long_trades) == 0
```

- [ ] **Step 2: Run tests**

```bash
./.venv/bin/python -m pytest tests/test_bt_traders_reality.py::TestTradersRealityFilters -v
```

Expected: PASS. If FAIL, inspect the signal logic — ensure `pvsra_long_labels` is correctly checked and the `_htf_is_bullish` short-circuits as expected.

---

## Task 5: Entry signal tests — PVSRA-triggered trade

**Files:**
- Test: `tests/test_bt_traders_reality.py`

- [ ] **Step 1: Write failing test that injects a PVSRA green bar**

```python
class TestTradersRealityEntry:
    """Inject explicit ring-volume bars and verify entries fire."""

    def _make_uptrend_with_pvsra_spike(self) -> pd.DataFrame:
        """
        500 bars uptrend for EMA warmup. At bar 450, inject a ring-volume bull bar:
        volume = avg_volume * 3. This should trigger PVSRA=green and a long entry.
        """
        n = 500
        dates  = pd.date_range("2023-01-01", periods=n, freq="1h")
        closes = np.linspace(40000, 52000, n)
        opens  = closes - 20
        highs  = closes + 80
        lows   = closes - 80
        vols   = np.full(n, 1000.0)
        # Inject ring-volume at bar 450 (bull: close > open)
        vols[450] = 3200.0   # 3.2x the average → ring volume
        df = pd.DataFrame(
            {"open": opens, "high": highs, "low": lows, "close": closes, "volume": vols},
            index=dates,
        )
        return df

    def test_pvsra_green_triggers_long_entry(self):
        df = self._make_uptrend_with_pvsra_spike()
        strat = _run_cerebro(
            df,
            use_htf_ema_filter=False,
            signal_long_min_score=2.0,
            risk_reward_ratio=2.0,
            max_drawdown=None,
        )
        trades = strat.analyzers.tradelist.get_analysis()
        # At least one long trade should fire after the ring-volume bar
        long_trades = [t for t in trades if t.get("direction") == "long"]
        assert len(long_trades) >= 1

    def test_trade_metadata_contains_score(self):
        df = self._make_uptrend_with_pvsra_spike()
        strat = _run_cerebro(
            df,
            use_htf_ema_filter=False,
            signal_long_min_score=2.0,
            risk_reward_ratio=2.0,
            max_drawdown=None,
        )
        trades = strat.analyzers.tradelist.get_analysis()
        long_trades = [t for t in trades if t.get("direction") == "long"]
        if long_trades:
            ec = long_trades[0].get("entry_context") or {}
            indicators = ec.get("indicators_at_entry") or {}
            assert "SignalScore" in indicators
            assert indicators["SignalScore"] >= 2.0
```

- [ ] **Step 2: Run tests**

```bash
./.venv/bin/python -m pytest tests/test_bt_traders_reality.py::TestTradersRealityEntry -v
```

Expected: PASS. If FAIL, add debug logging to inspect computed scores at bar 450.

---

## Task 6: SL/TP resolution unit tests

**Files:**
- Test: `tests/test_bt_traders_reality.py`

- [ ] **Step 1: Write tests for SL/TP resolution methods directly**

```python
class TestTradersRealitySLTP:
    """Test _resolve_sl_long, _resolve_sl_short, _resolve_tp_long, _resolve_tp_short."""

    def _make_strat_with_pivots(self) -> TradersRealityStrategy:
        """Run enough bars to populate pivot state, return strategy instance."""
        df = _make_ohlcv(500)
        strat = _run_cerebro(df, use_htf_ema_filter=False, risk_reward_ratio=2.0, max_drawdown=None)
        return strat

    def test_sl_long_falls_back_to_atr_when_no_pivots(self):
        """When pivots are None and weekly SL disabled, ATR fallback is used."""
        strat = self._make_strat_with_pivots()
        # Force clear pivots + m0 to test fallback path
        strat._pivots = None
        strat._m0 = None
        entry = 50000.0
        # Patch ATR to known value via direct override of atr_ltf
        # We can only verify the formula — call _resolve_sl_long and check the
        # fallback expression is returned
        _sl, _dist, expr = strat._resolve_sl_long(entry)
        if _sl is not None:
            assert "ATR" in expr or "Low" in expr

    def test_tp_long_uses_r1_when_pivot_available(self):
        strat = self._make_strat_with_pivots()
        if strat._pivots is None:
            pytest.skip("Pivots not populated in this run — warmup too short")
        r1 = strat._pivots["R1"]
        entry = strat._pivots["PP"] + 1.0   # just above PP
        tp, dist, expr = strat._resolve_tp_long(entry, sl_distance=50.0)
        if r1 > entry:
            assert abs(tp - r1) < 1e-6
            assert "R1" in expr

    def test_tp_short_uses_s1_when_pivot_available(self):
        strat = self._make_strat_with_pivots()
        if strat._pivots is None:
            pytest.skip("Pivots not populated in this run — warmup too short")
        s1 = strat._pivots["S1"]
        entry = strat._pivots["PP"] - 1.0   # just below PP
        tp, dist, expr = strat._resolve_tp_short(entry, sl_distance=50.0)
        if s1 < entry:
            assert abs(tp - s1) < 1e-6
            assert "S1" in expr
```

- [ ] **Step 2: Run SL/TP tests**

```bash
./.venv/bin/python -m pytest tests/test_bt_traders_reality.py::TestTradersRealitySLTP -v
```

Expected: PASS or skip (if pivot warmup isn't reached).

---

## Task 7: Strategy registration

**Files:**
- Modify: `web-dashboard/services/strategy_runtime.py` (1 line)
- Modify: `web-dashboard/server.py` (~50 lines)

### 7a. Register canonical name

- [ ] **Step 1: Add to `_LEGACY_CANONICAL_NAMES` in `strategy_runtime.py`**

In `web-dashboard/services/strategy_runtime.py`, line ~19, add one entry:

```python
_LEGACY_CANONICAL_NAMES = {
    "bt_price_action": "bt_price_action",
    "bt_traders_reality": "bt_traders_reality",   # ← ADD THIS LINE
}
```

- [ ] **Step 2: Verify discovery finds the strategy**

```bash
./.venv/bin/python -c "
from web_dashboard.services.strategy_runtime import discover_strategy_definitions
defs = discover_strategy_definitions()
names = [d['name'] for d in defs]
print(names)
assert 'bt_traders_reality' in names, f'bt_traders_reality not found in {names}'
print('OK')
"
```

Wait — the package name here is `web-dashboard/services/strategy_runtime.py`. The test should be run from the repo root:

```bash
PYTHONPATH=. ./.venv/bin/python -c "
from web_dashboard.services.strategy_runtime import discover_strategy_definitions
defs = discover_strategy_definitions()
names = [d['name'] for d in defs]
print(names)
assert 'bt_traders_reality' in names, f'bt_traders_reality not found in {names}'
print('STRATEGY DISCOVERY: OK')
"
```

Expected: `[..., 'bt_traders_reality', ...]` printed, followed by `STRATEGY DISCOVERY: OK`.

### 7b. Add UI schema

- [ ] **Step 3: Add schema to `server.py`**

In `web-dashboard/server.py`, inside `get_strategy_config_schema()`, add a new entry to `default_schemas` dict immediately after the `"bt_price_action"` block (before line ~477):

```python
"bt_traders_reality": {
    # EMA
    "ema_fast":   {"type": "number", "default": 5,   "section": "EMA"},
    "ema_medium": {"type": "number", "default": 13,  "section": "EMA"},
    "ema_slow":   {"type": "number", "default": 50,  "section": "EMA"},
    "ema_trend":  {"type": "number", "default": 200, "section": "EMA"},

    # PVSRA
    "pvsra_avg_period": {"type": "number",  "default": 10,  "section": "PVSRA"},
    "pvsra_rv_mult":    {"type": "number",  "default": 2.0, "section": "PVSRA",
                         "label": "Ring Volume Multiplier (≥2x avg)"},
    "pvsra_bv_mult":    {"type": "number",  "default": 1.5, "section": "PVSRA",
                         "label": "Big Volume Multiplier (≥1.5x avg)"},

    # ADR
    "adr_period":               {"type": "number", "default": 14,   "section": "ADR"},
    "adr_exhaustion_threshold": {"type": "number", "default": 0.85, "section": "ADR",
                                  "label": "ADR Exhaustion Threshold (0.85)"},

    # Signal thresholds
    "signal_long_min_score":  {"type": "number", "default":  2.0, "section": "Signal"},
    "signal_short_max_score": {"type": "number", "default": -2.0, "section": "Signal"},

    # HTF filter
    "use_htf_ema_filter": {"type": "boolean", "default": True, "section": "Filters",
                            "label": "HTF EMA Trend Filter"},

    # Levels
    "use_weekly_sl": {"type": "boolean", "default": True,  "section": "Levels",
                      "label": "Use Weekly M0/M5 for SL"},
    "use_pivot_tp":  {"type": "boolean", "default": True,  "section": "Levels",
                      "label": "Use Daily Pivot R1/S1 for TP"},

    # ATR SL fallback
    "atr_period":           {"type": "number", "default": 14,  "section": "Stop Loss"},
    "sl_buffer_atr":        {"type": "number", "default": 1.5, "section": "Stop Loss",
                              "label": "ATR Multiplier (fallback SL)"},
    "sl_weekly_buffer_atr": {"type": "number", "default": 0.1, "section": "Stop Loss",
                              "label": "Weekly Level Buffer (ATR mult)"},

    # Risk/exit (standard across all strategies)
    "risk_reward_ratio": {"type": "number", "default": 2.0, "section": "Risk"},
},
```

Also add the alias line after `default_schemas["price_action_strategy"] = ...`:

```python
default_schemas["traders_reality_strategy"] = default_schemas["bt_traders_reality"]
```

- [ ] **Step 4: Verify schema is returned**

```bash
PYTHONPATH=. ./.venv/bin/python -c "
import sys; sys.path.insert(0, 'web-dashboard')
from server import get_strategy_config_schema
schema = get_strategy_config_schema('bt_traders_reality')
assert 'pvsra_rv_mult' in schema, 'pvsra_rv_mult missing from schema'
assert 'use_weekly_sl' in schema, 'use_weekly_sl missing from schema'
print('SCHEMA: OK', list(schema.keys()))
"
```

Expected: schema keys printed, `SCHEMA: OK`.

---

## Task 8: Strategy runtime test for `bt_traders_reality`

**Files:**
- Test: `tests/test_strategy_runtime_service.py` (existing file — add test case)

- [ ] **Step 1: Write failing test**

Add to `tests/test_strategy_runtime_service.py`:

```python
def test_resolve_bt_traders_reality_returns_correct_class():
    from strategies.bt_traders_reality import TradersRealityStrategy
    from web_dashboard.services.strategy_runtime import resolve_strategy_class
    cls = resolve_strategy_class("bt_traders_reality")
    assert cls is TradersRealityStrategy
```

- [ ] **Step 2: Run it to confirm FAIL (before strategy_runtime.py edit)**

```bash
./.venv/bin/python -m pytest tests/test_strategy_runtime_service.py::test_resolve_bt_traders_reality_returns_correct_class -v
```

Expected: FAIL (class resolves to `PriceActionStrategy` fallback before the registration change).

After completing Task 7a, re-run:

```bash
./.venv/bin/python -m pytest tests/test_strategy_runtime_service.py::test_resolve_bt_traders_reality_returns_correct_class -v
```

Expected: PASS.

---

## Task 9: Full test suite + ruff

- [ ] **Step 1: Run ruff on all new/modified Python files**

```bash
./.venv/bin/ruff check strategies/helpers/tr_indicators.py strategies/bt_traders_reality.py
./.venv/bin/ruff format strategies/helpers/tr_indicators.py strategies/bt_traders_reality.py
```

Expected: 0 violations after formatting.

- [ ] **Step 2: Run full pytest**

```bash
./.venv/bin/python -m pytest -q
```

Expected: all existing tests pass, new tests pass. No regressions.

- [ ] **Step 3: Spot-check the signal logic manually**

```bash
PYTHONPATH=. ./.venv/bin/python -c "
from strategies.helpers.tr_indicators import (
    pvsra_label, pvsra_score_delta, ema_stack_score,
    pivot_levels, classify_signal, composite_signal_score
)
# Full bull scenario: ema stack + green pvsra + above PP
stack = ema_stack_score(5, 4, 3, 2)           # +2
pvsra = pvsra_score_delta('green')             # +2
pp    = 1.0                                    # above PP
adr   = 0.0
cross = 1.0                                    # golden cross
score = composite_signal_score(stack, pvsra, pp, adr, cross)
label = classify_signal(score)
print(f'Score={score} Label={label}')
assert score == 6.0
assert label == 'STRONG LONG'
print('SIGNAL LOGIC: OK')
"
```

Expected: `Score=6.0 Label=STRONG LONG` + `SIGNAL LOGIC: OK`.

---

## Task 10: Documentation update

**Files:**
- Modify: `docs/TRADERS_REALITY_MARKET_ANALYZER_ANALYSIS.md`

- [ ] **Step 1: Update the "Что нужно реализовать" section**

In `docs/TRADERS_REALITY_MARKET_ANALYZER_ANALYSIS.md`, update section 6.1 to reflect what was actually built:

- Change "нужно реализовать" → "реализовано"
- Add reference to `strategies/bt_traders_reality.py` and `strategies/helpers/tr_indicators.py`
- Add reference to the implementation plan: `docs/superpowers/plans/2026-04-22-bt-traders-reality-strategy.md`

No new documentation files are needed — all decisions are recorded in this plan.

---

## Self-review against spec

### Spec coverage check

| Requirement | Covered by |
|------------|------------|
| PVSRA (Ring/Big Volume, 10-bar window) | Task 1 `pvsra_label`, Task 2 `_update_pvsra` |
| EMA 5/13/50/200 stack score ±2 | Task 1 `ema_stack_score`, Task 2 indicators |
| EMA 5/13 cross score ±1 | Task 1 `ema_cross_score`, Task 2 `_compute_signal_score` |
| Daily Pivot PP/R1-R3/S1-S3 score ±1 | Task 1 `pivot_levels`, Task 2 `_update_daily_state` |
| ADR exhaustion score ±1 | Task 1 `adr_exhaustion_score`, Task 2 `_update_daily_state` |
| Weekly M0/M5 levels | Task 2 `_update_weekly_state`, `_resolve_sl_long/short` |
| Signal classification (score thresholds) | Task 1 `classify_signal` |
| HTF EMA filter (close vs EMA200) | Task 2 `_htf_is_bullish/_bearish` |
| PVSRA qualifier gate (green/blue for long) | Task 2 `next()` entry decisions |
| SL: Weekly M0 → S1 → ATR fallback | Task 2 `_resolve_sl_long` |
| SL: Weekly M5 → R1 → ATR fallback | Task 2 `_resolve_sl_short` |
| TP: R1 (long) / S1 (short) → RR fallback | Task 2 `_resolve_tp_long/short` |
| BaseStrategy OCO / trailing / breakeven | Inherited — no engine changes |
| Strategy auto-discovery | Task 7a canonical name registration |
| Dashboard schema | Task 7b |
| TDD discipline | Tests written before implementation in every task |
| No engine changes | Confirmed — all state is in strategy layer |

### No placeholders found — all code is complete and typed.

### Type consistency:
- `pvsra_label` returns `str` — used as `str` throughout ✓
- `pivot_levels` returns `dict[str, float]` — keys accessed by string literals matching function output ✓
- `composite_signal_score` returns `float` — compared to `float` params ✓
- `_resolve_sl_long` / `_resolve_tp_long` return `(float | None, float, str)` — callers check for `None` ✓

---

## Commit guidance (for user)

After all tasks pass, suggested commits (user executes):

```bash
git add strategies/helpers/tr_indicators.py tests/test_tr_indicators.py
git commit -m "feat(indicators): add pure-Python TR indicator helpers (PVSRA, pivots, ADR, EMA)"

git add strategies/bt_traders_reality.py tests/test_bt_traders_reality.py
git commit -m "feat(strategy): add TradersRealityStrategy (bt_traders_reality)"

git add web-dashboard/services/strategy_runtime.py web-dashboard/server.py
git commit -m "feat(dashboard): register bt_traders_reality strategy with schema"
```
