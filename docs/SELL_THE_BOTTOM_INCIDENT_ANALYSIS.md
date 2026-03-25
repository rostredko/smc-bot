# Sell the Bottom Incident Analysis — Code Verification

**Branch:** `strategy-modification`  
**Date:** March 16, 2025  
**Context:** Incident where the bot entered Short on a strong 4H bullish impulse, ignoring it due to structure filter.

---

## 1. Incident Description

- On 4H chart: strong bullish candle / bullish engulfing.
- Bot opened **Short** on Bearish Engulfing signal on 1H.
- Cause: 4H structure was still bearish (structure = -1), bullish signals ignored.
- Entry occurred in support zone ("sell the bottom").

---

## 2. Code Verification

### 2.1. Timeframe Conflict (1H vs 4H) — ✅ Confirmed

**Claim:** Patterns are detected on 1H, structure on 4H.

**Code:**

- `ordered_timeframes()` sorts by duration: `["4h", "1h"]` → `["1h", "4h"]`.
- `datas[0]` = 1h (LTF), `datas[1]` = 4h (HTF).
- `data_ltf = self.datas[0]`, `data_htf = self.datas[1]`.
- Patterns (CDLENGULFING, pinbar, etc.) on `data_ltf` (1H).
- Structure (`ms_htf`, `structure`) on `data_htf` (4H).

**Conclusion:** A 4H bullish candle is 4× 1H candles. Bearish Engulfing on one of them is valid and can trigger Short when structure = -1.

---

### 2.2. Structure Priority (Bias) — ✅ Confirmed

**Claim:** structure = -1 blocks all Long and allows only Short.

**Code:** `_check_filters_short`: `_get_structure_state() != -1` → return False. Bot ignores bullish signals until structure flips to 1 (close > last SH).

---

### 2.3. Engulfing Definition (TALib) — ✅ Confirmed

**Claim:** CDLENGULFING on candle bodies on 1H.

**Code:** `self.cdl_engulfing = bt.talib.CDLENGULFING(self.data_ltf.open, ...)`. Bearish = -100, Bullish = +100. Micro-engulfing of a doji is technically valid.

---

### 2.4. Recommendation 1: Premium/Discount — ⚠️ Implemented but Disabled

**Recommendation:** Short only in Premium (upper 50% of 4H High–Low range).

**Code:** `use_premium_discount_filter` defaults to **False**. `_passes_premium_discount_filter('short')`: `entry_price > equilibrium`. Enabling would block Short in Discount.

---

### 2.5. Recommendation 2: POI Required for CHoCH — ✅ Already Implemented

**Recommendation:** CHoCH should fire only after touching 4H Supply Zone.

**Code:** Short arm requires `_bar_intersects_zone(self._get_poi_zone_short())`. POI for Short is around `last_sh_level` (4H Supply). Without POI intersection, arm is not set.

**Conclusion:** Claim "CHoCH works in isolation from POI" is **incorrect**. POI is required at arm. Entry can be slightly outside (limited by `ltf_choch_max_pullaway_atr_mult`).

---

### 2.6. Recommendation 3: Engulfing Body Size Filter — ⚠️ Implemented but Disabled

**Recommendation:** Engulfing body should be meaningful (e.g. % of ATR or average body).

**Code:** `use_engulfing_quality_filter` defaults to **False**. When enabled: `engulfing_min_body_to_range` (0.55), `engulfing_min_body_to_atr` (0.35), `engulfing_min_body_engulf_ratio` (1.0). Enabling would filter weak engulfings.

---

### 2.7. Recommendation 4: RSI Divergence — ❌ Not Implemented

**Recommendation:** Check for bullish divergence (price down, RSI up) before Short.

**Code:** Only `use_rsi_filter` (overbought/oversold) and `use_rsi_momentum`. No divergence logic across bars.

---

## 3. Summary Table

| Claim / Recommendation | Status | Details |
|------------------------|--------|---------|
| Patterns on 1H, structure on 4H | ✅ | data_ltf / data_htf, ordered_timeframes |
| structure = -1 → Short only | ✅ | _check_filters_short |
| CDLENGULFING on 1H | ✅ | cdl_engulfing on data_ltf |
| Premium/Discount | ⚠️ | Implemented, use_premium_discount_filter=False |
| CHoCH without POI | ❌ | POI required for arm |
| Engulfing body size filter | ⚠️ | Implemented, use_engulfing_quality_filter=False |
| RSI divergence | ❌ | Not implemented |

---

## 4. Conclusions

1. **Incident description** matches code: 4H structure blocks bullish signals, Bearish Engulfing on 1H can trigger Short.
2. **CHoCH does not work "in isolation" from POI** — POI intersection is required at arm.
3. **Premium/Discount** and **Engulfing Quality** exist but are disabled by default.
4. **RSI divergence** is absent.

---

## 5. Tuning Recommendations

To reduce "sell the bottom" risk without code changes:

| Parameter | Recommendation | Effect |
|-----------|----------------|--------|
| `use_premium_discount_filter` | `true` | Blocks Short in Discount (lower 50%) |
| `use_engulfing_quality_filter` | `true` | Filters weak engulfings |
| `use_rsi_filter` | `true` (default) | Blocks Short when RSI < 30 (oversold) |

RSI divergence would require strategy changes.
