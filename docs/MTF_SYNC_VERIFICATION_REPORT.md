# MTF Sync Verification Report

**Branch:** `strategy-modification`  
**Date:** March 16, 2025  
**Goal:** Verify claims about multi-timeframe (1H / 4H) data sync and absence of lookahead.

---

## 1. Theory (Reference)

### Rules

1. **data0 = 1H** (execution), **data1 = 4H** (structure).
2. On current 1H bar, only **already closed** 4H candles may be used.
3. **Bridge:** Trend State, Last SH, Last SL passed from 4H to 1H.
4. **Lookahead:** Using future data inflates backtest and causes losses in live.

---

## 2. Implementation

### 2.1. Data Order (data0 / data1)

**Uses `sorted()`, not `reversed()`.**

```23:29:engine/timeframe_utils.py
def ordered_timeframes(timeframes):
    """
    Always add lower timeframe first so multi-timeframe strategies receive:
    data0 = LTF, data1 = HTF, regardless of config array order.
    """
    items = list(timeframes or ["1h"])
    return sorted(items, key=timeframe_to_minutes)
```

- `timeframe_to_minutes("1h")` = 60, `timeframe_to_minutes("4h")` = 240.
- `sorted(["4h", "1h"])` → `["1h", "4h"]`.
- `sorted(["1h", "4h"])` → `["1h", "4h"]`.

**Result:** `data0 = LTF`, `data1 = HTF` always, regardless of config order.

**Expert correction:** Claim "reversed(timeframes)" and "["1h", "4h"] breaks mapping" is **wrong**. Both config orders yield the same result.

---

### 2.2. Strategy Mapping

```194:206:strategies/bt_price_action.py
        if self.has_secondary:
            self.data_ltf = self.datas[0]
            self.data_htf = self.datas[1]
        ...
        self.ms_htf = MarketStructure(self.data_htf, ...)
```

- `data_ltf` = 1H, `data_htf` = 4H.
- `MarketStructure` runs on `data_htf` (4H).

---

### 2.3. 4H → 1H Bridge

```637:639:strategies/bt_price_action.py
    def _get_structure_state(self) -> int:
        structure_val = self._to_valid_float(self.ms_htf.structure[0])
        ...
```

- `self.ms_htf.structure[0]` — Trend State (1 / -1 / 0).
- `self.ms_htf.sh_level[0]` — Last Swing High.
- `self.ms_htf.sl_level[0]` — Last Swing Low.

Used directly, no intermediate variables.

---

### 2.4. Live: Closed Candles Only

```117:119:engine/live_ws_client.py
        kline = payload.get("k")
        if not isinstance(kline, dict) or not kline.get("x"):
            return
```

- Only candles with `kline["x"] == True` (closed) are pushed.
- Unclosed 4H candles are not used.

---

### 2.5. Fractals: No Lookahead

```37:42:strategies/bt_price_action.py
    @staticmethod
    def _is_pivot_high(data, span: int) -> bool:
        candidate = float(data.high[-span])
        left_highs = [float(data.high[-span - offset]) for offset in range(1, span + 1)]
        right_highs = [float(data.high[-span + offset]) for offset in range(1, span + 1)]
        return is_confirmed_swing_high(candidate, left_highs, right_highs)
```

- `pivot_span=2` → 2 candles left and right.
- Fractal confirmed only after 2 candles to the right.

---

## 3. Summary Table

| Claim | Status | Details |
|-------|--------|---------|
| data0 = 1H, data1 = 4H | ✅ | `ordered_timeframes` → `sorted`, LTF first |
| Config order | ✅ | `["1h","4h"]` and `["4h","1h"]` give same result |
| 4H — closed candles only (live) | ✅ | `kline.get("x")` in live_ws_client |
| Fractal lookahead | ✅ | None. Confirmation via `span=2` |
| Bridge (structure, SH, SL) | ✅ | `ms_htf.structure[0]`, `sh_level[0]`, `sl_level[0]` |

---

## 4. Expert Claim Correction

Expert claimed: "engine uses reversed(timeframes)" and "["1h", "4h"] breaks mapping".

- Code uses `sorted(timeframes, key=timeframe_to_minutes)`, not `reversed`.
- Config order does not affect `data0`/`data1` — mapping is always the same.

---

## 5. LTF/HTF Robustness

Expert suggested: "Make LTF/HTF self-determined and independent of config order."

- **Current implementation** already does this: `ordered_timeframes` sorts by duration, LTF always first.
- Optional hardening: add `timeframe_to_minutes(datas[0]) < timeframe_to_minutes(datas[1])` check in strategy and log `data_ltf = X, data_htf = Y` at startup.

---

## 6. Summary

- MTF sync is implemented correctly.
- Config order does not affect `data0`/`data1` — sorting is used.
- 4H data in live comes only from closed candles.
- Fractals are confirmed with 2-candle delay and no lookahead.
