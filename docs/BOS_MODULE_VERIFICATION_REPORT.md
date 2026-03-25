# BOS Module Verification Report

**Branch:** `strategy-modification`  
**Date:** March 16, 2025  
**Goal:** Verify BOS module implementation against specification and external expert claims.

---

## 1. BOS Module Specification (Reference)

### BOS Logic (Fractal-Based)

| # | Requirement | Description |
|---|-------------|-------------|
| 1 | Extremum detection | "2 left, 2 right" condition for Swing High (SH) and Swing Low (SL) |
| 2 | Level fixation | Once fractal forms (2 candles after peak), price is stored as "Current level" |
| 3 | BOS definition | Close > Last SH → BOS Up; Close < Last SL → BOS Down |
| 4 | POI (Zone of Interest) | Candle or range that formed the breakout fractal — zone for 1H entry search |
| 5 | 4H → 1H bias | structure == 1 → LONG only; structure == -1 → SHORT only |
| 6 | Global levels | last_sl_level (4H) → global support on 1H; last_sh_level → global resistance |

---

## 2. Verification Results vs Specification

### 2.1. Fractals "2 left, 2 right" — ✅ Implemented

**Files:** `strategies/market_structure.py`, `strategies/bt_price_action.py`

- `is_confirmed_swing_high` / `is_confirmed_swing_low` ensure candidate is strictly above (SH) or below (SL) all left and right values.
- In `MarketStructure._is_pivot_high` with `pivot_span=2`:
  - `left_highs` = 2 candles left of peak (offset 1..2)
  - `right_highs` = 2 candles right of peak (offset 1..2)
- In `compute_market_structure_levels`: `highs[c_idx - span:c_idx]` and `highs[c_idx + 1:c_idx + span + 1]` — same 2 left, 2 right.

```37:50:strategies/bt_price_action.py
    @staticmethod
    def _is_pivot_high(data, span: int) -> bool:
        candidate = float(data.high[-span])
        left_highs = [float(data.high[-span - offset]) for offset in range(1, span + 1)]
        right_highs = [float(data.high[-span + offset]) for offset in range(1, span + 1)]
        return is_confirmed_swing_high(candidate, left_highs, right_highs)
```

### 2.2. Level Fixation — ✅ Implemented

**File:** `strategies/bt_price_action.py`

- `MarketStructure` stores `_last_swing_high` and `_last_swing_low`.
- On fractal detection (`_is_pivot_high` / `_is_pivot_low`) values are updated.
- Fractal is confirmed at bar `-span` (i.e. `span` bars after peak). With `pivot_span=2` — 2 candles after peak.

```54:58:strategies/bt_price_action.py
        if self._is_pivot_high(self.data, span):
            self._last_swing_high = float(self.data.high[-span])

        if self._is_pivot_low(self.data, span):
            self._last_swing_low = float(self.data.low[-span])
```

### 2.3. BOS by Close — ✅ Implemented

**File:** `strategies/market_structure.py`

- `advance_structure_state`: `close > last_swing_high` → 1; `close < last_swing_low` → -1.
- State persists across bars (1/-1 carry forward).

```36:50:strategies/market_structure.py
def advance_structure_state(
    close_value: float,
    last_swing_high: float | None,
    last_swing_low: float | None,
    current_structure: int | float = 0,
) -> int:
    if last_swing_high is not None and float(close_value) > float(last_swing_high):
        return 1
    if last_swing_low is not None and float(close_value) < float(last_swing_low):
        return -1
    ...
```

### 2.4. POI as "BOS Candle Fractal Range" — ❌ Not Implemented

**File:** `strategies/bt_price_action.py`

- Current: POI is an **ATR band around last_sl_level / last_sh_level**.
- Params: `poi_zone_upper_atr_mult` (0.3), `poi_zone_lower_atr_mult` (0.2).
- BOS candle range (high/low of breakout candle) is **not stored** or used.

```664:679:strategies/bt_price_action.py
    def _get_poi_zone_long(self):
        sl_level = self._to_valid_float(self.ms_htf.sl_level[0])
        atr_val = self._to_valid_float(self.atr_htf[0])
        ...
        zone_high = sl_level + (atr_val * self.params.poi_zone_upper_atr_mult)
        zone_low = sl_level - (atr_val * self.params.poi_zone_lower_atr_mult)
        return zone_low, zone_high
```

### 2.5. 4H → 1H Bias (LONG / SHORT only) — ✅ Implemented

**File:** `strategies/bt_price_action.py`

- `_check_filters_long`: `_get_structure_state() != 1` → entry blocked.
- `_check_filters_short`: `_get_structure_state() != -1` → entry blocked.
- `_get_structure_state()` reads from `ms_htf.structure[0]` (HTF = 4H in typical config).

### 2.6. last_sl_level / last_sh_level as Global Levels on 1H — ✅ Implemented

**File:** `strategies/bt_price_action.py`

- `_resolve_structural_sl_long`: SL built from `ms_htf.sl_level[0]` (global support).
- `_resolve_structural_sl_short`: SL from `ms_htf.sh_level[0]` (global resistance).
- `_get_poi_zone_long` / `_get_poi_zone_short` use the same HTF levels.

---

## 3. External Expert Claims Verification

### 3.1. Matches — All Confirmed

| Expert claim | Status | Code reference |
|--------------|--------|----------------|
| Fractals 2 left / 2 right | ✅ | `market_structure.py`, `bt_price_action.py` |
| Last SH/SL stored in memory | ✅ | `MarketStructure._last_swing_high`, `_last_swing_low` |
| BOS by close: close > last SH → 1, close < last SL → -1 | ✅ | `advance_structure_state()` |
| structure == 1 → long only; -1 → short only | ✅ | `_check_filters_long` / `_check_filters_short` |
| last_sl_level / last_sh_level as reference on 1H | ✅ | `_resolve_structural_sl_*`, `_get_poi_zone_*` |

### 3.2. Mismatches — All Confirmed

| Expert claim | Status | Details |
|--------------|--------|---------|
| POI is not "BOS candle fractal range" | ✅ | POI = ATR band around level |
| Only level stored; BOS candle range not stored | ✅ | No structure for BOS candle high/low |
| No separate "BOS zone object" | ✅ | No object capturing breakout fractal zone |
| POI is dynamic — shifts with new SL/SH | ✅ | POI built from current `sl_level[0]` / `sh_level[0]` |

### 3.3. CHoCH and POI — Confirmed

**Claim:** With CHoCH enabled, price must enter POI at arm/setup, but entry can occur slightly outside POI.

**Verification:** Arm requires `_bar_intersects_zone(self._get_poi_zone_long())`. Trigger checks `trigger_zone_ref == current_zone_ref` and `ltf_choch_max_pullaway_atr_mult`, but does **not** require entry strictly inside POI.

---

## 4. Summary Table

| Component | Specification | Implementation | Status |
|-----------|---------------|----------------|--------|
| Fractals 2/2 | Yes | Yes | ✅ |
| Level fixation | Yes | Yes | ✅ |
| BOS by Close | Yes | Yes | ✅ |
| POI | BOS candle fractal range | ATR band around level | ⚠️ Different |
| 4H → 1H bias | Yes | Yes | ✅ |
| Global levels (SL/SH) | Yes | Yes | ✅ |

---

## 5. Conclusions

1. **BOS on fractals** is implemented per specification.
2. **4H → 1H bias bridge** and use of `last_sl_level` / `last_sh_level` as global levels are correct.
3. **POI** differs from spec: instead of BOS candle range, an ATR band around the current level is used.
4. External expert claims are **confirmed** by code review.

---

## 6. Recommendations (if aligning POI to spec)

To move to a "true BOS POI zone":

1. Store high/low of the breakout candle when BOS is confirmed.
2. Introduce a "BOS zone" object with: level, breakout candle range (low–high), direction (1/-1).
3. Use this range as POI instead of the ATR band.
4. Decide whether POI stays fixed (last BOS zone) or updates on each BOS — spec implies fixing the zone of the specific BOS.
