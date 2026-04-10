# Troubleshooting & Known Issues

Record of meaningful bugs, incidents, and root causes.
Update this file whenever a meaningful issue is found or solved.

## Entry format

For each issue:
- **Date** — when the issue was found/resolved
- **Title** — short descriptive name
- **Context** — what was being worked on
- **Symptoms / error** — what was observed
- **Root cause** — why it happened
- **Resolution** — what fixed it
- **Prevention / guardrail** — what prevents recurrence

---

## Issues

### 2025-03-16 — Sell-the-Bottom: Short entry on bullish 4H impulse

**Context:** Strategy backtesting with 1H/4H multi-timeframe setup.

**Symptoms:** Bot opened Short on a 1H Bearish Engulfing candle during a strong 4H bullish impulse. Visually looked like a bad "sell the bottom" entry.

**Root cause:** HTF structure (`structure = -1`) was still bearish at the time of the 1H signal. The 4H bullish candle was in progress (not yet confirmed as a BOS); structure only flips when `close > last_sh_level`. A technically valid 1H Bearish Engulfing triggered within the bearish bias window.

**Resolution:** Confirmed this is correct behavior, not a bug. The `use_premium_discount_filter` param (disabled by default) can reject Short entries when price is in the lower 50% of the HTF range.

**Prevention / guardrail:**
- Enable `use_premium_discount_filter` if you want to avoid counter-trend lows
- Do not interpret "visually bad" entries as bugs without verifying the structure state at bar time
- Reference: `docs/SELL_THE_BOTTOM_INCIDENT_ANALYSIS.md`

---

### 2025-03-16 — MTF data order: LTF/HTF assignment depends on sort, not config order

**Context:** Multi-timeframe strategy config where timeframes could be passed in any order.

**Symptoms:** Concern that `data0`/`data1` assignment might depend on config array order, causing HTF to be used as LTF.

**Root cause:** `ordered_timeframes()` in `engine/timeframe_utils.py` uses `sorted()` by duration (minutes). Order of config array is irrelevant — LTF always becomes `data0`, HTF always becomes `data1`.

**Resolution:** Verified by code inspection. `sorted(["4h", "1h"])` → `["1h", "4h"]` → `data0=1H`, `data1=4H`. No bug.

**Prevention / guardrail:**
- Strategy code must always use `self.datas[0]` = LTF, `self.datas[1]` = HTF — never hardcode by name
- Any new multi-timeframe strategy must use `ordered_timeframes()` from `engine/timeframe_utils.py`
- Reference: `docs/MTF_SYNC_VERIFICATION_REPORT.md`

---

### 2025-03-16 — BOS fractal "2 left, 2 right" requires 2-bar confirmation delay

**Context:** Market structure module; BOS/CHoCH detection with fractal pivots.

**Symptoms:** Confusion about when a swing high/low is "confirmed" and available to strategy logic.

**Root cause:** The fractal confirmation rule requires 2 candles to the right of the candidate pivot. This means a swing high/low is only confirmed 2 bars after it forms. Accessing it on the same bar as formation is lookahead.

**Resolution:** `is_confirmed_swing_high` / `is_confirmed_swing_low` in `market_structure.py` enforce the 2-bar delay. `_is_pivot_high` with `pivot_span=2` accesses `data.high[-span]` (2 bars ago), not `data.high[0]`.

**Prevention / guardrail:**
- Never read `data.high[0]` or `data.close[0]` for fractal detection — always use confirmed bars (`[-N]`)
- Add a test when changing pivot detection logic to confirm no lookahead
- Reference: `docs/BOS_MODULE_VERIFICATION_REPORT.md`
