# Engine and bt_price_action Strategy Deep Review (March 2026)

> **Historical:** Analysis of specific run_ids and commits. Code has been updated since (api/, timeframe_utils, utils). Use for drawdown/risk context; line numbers may have changed.

**Goal**: Identify causes of discrepancies between backtests:
- **Good**: `backtest_20260302_180422_53c33285` — profit > 5k, max drawdown ~30%
- **Bad**: `backtest_20260304_145333_b5e98829` — max drawdown > 105%

---

## 1. Max Drawdown > 100% — Mathematical Analysis

### 1.1 Backtrader DrawDown Formula

Backtrader source (`backtrader/analyzers/drawdown.py`):

```python
r.drawdown = drawdown = 100.0 * moneydown / self._maxvalue
# where moneydown = self._maxvalue - self._value (peak - current)
```

So: **drawdown = 100 × (peak − value) / peak**

### 1.2 When Is Drawdown > 100%?

With **negative equity** (value < 0):

- Peak = 10,000
- Value = -5,000 (after a series of losses with leverage)
- moneydown = 10,000 − (−5,000) = 15,000
- **drawdown = 100 × 15,000 / 10,000 = 150%**

**Conclusion**: Max drawdown > 100% means the account went negative. This is possible with:
1. High leverage (10x default)
2. A series of losing trades
3. No margin call / liquidation in Backtrader simulator

---

## 2. Code Changes (git diff)

### 2.1 DataLoader — Date Filter (commit 8a2c883, db2df6b)

**Before**:
```python
end_dt = pd.Timestamp(end_date)  # 2024-12-31 00:00:00
df = df[(df.index >= start_dt) & (df.index <= end_dt)]
```

**After**:
```python
end_dt = pd.Timestamp(end_date) + pd.Timedelta(days=1) - pd.Timedelta(milliseconds=1)
# 2024-12-31 23:59:59.999
df = df[(df.index >= start_dt) & (df.index <= end_dt)]
```

**Impact**:
- Before: bars at 2024-12-31 01:00, 05:00, ... could be **excluded** (if comparison was strict)
- Now: **full last day** included
- For 4h: +6 bars; for 1h: +24 bars

**Risk**: If the last day of the period was strongly losing, this adds losing trades and can worsen results.

### 2.2 DataLoader — Retry on Errors (commit 8a2c883)

**Before**: `continue` without updating `current_ts` on exception → possible infinite loop.

**After**: `current_ts += 3600000` and `retries` with limit 5.

**Impact**: Bug fix. May change volume of loaded data on unstable network.

### 2.3 BaseStrategy — Order Cleanup on Cancel/Margin/Reject (commit db2df6b)

**Before**:
```python
if order == self.stop_order:
    self.stop_order = None
# tp_order and self.order were NOT cleared!
```

**After**:
```python
if order == self.stop_order:
    self.stop_order = None
elif order == self.tp_order:
    self.tp_order = None
elif order == self.order:
    self.order = None
```

**Impact**:
- Before: on Margin/Reject entry order `self.order` stayed as reference to rejected order
- In `next()`: `if self.order: return` — strategy could **hang** and not open new trades
- Now: after rejection `self.order = None` — strategy continues trading

**Risk**: If margin rejections previously prevented overtrading, now the strategy may keep entering and accumulate losses. But logically, cleanup is correct behavior.

### 2.4 RiskManager — Validation (commit 8a2c883)

```python
risk_per_trade_pct = max(0.0, min(100.0, float(risk_per_trade_pct)))
leverage = max(0.1, float(leverage))
```

**Impact**:
- `risk_per_trade > 100` → clamp to 100%. Before, invalid % could be used.
- `leverage = 0` → clamp to 0.1. Before, division by zero or zero size possible.

### 2.5 bt_price_action — size <= 0 Guard (commit db2df6b)

Added check `if size <= 0: return` before entry. Prevents entry with zero size.

### 2.6 bt_price_action — Close on max_drawdown (commit db2df6b)

On exceeding `max_drawdown` added `if self.position: self.close()`. Before, strategy only logged and returned, but position could stay open.

---

## 3. Math and Financial Logic Verification

### 3.1 RiskManager — Position Size

```python
risk_amount = account_value * (risk_per_trade_pct / 100.0)
risk_per_unit = abs(entry_price - stop_loss)
size = risk_amount / risk_per_unit
```

**Check**: With risk 2%, account 10k, risk_per_unit = 500:
- risk_amount = 200
- size = 200 / 500 = 0.4
- At entry 50,000: notional = 20,000
- With leverage 10x: max_notional = 100,000 → 20k < 100k ✓

**Correct**.

### 3.2 SL/TP on Fill (base_strategy)

```python
real_sl = exec_price - sl_dist  # long
real_tp = exec_price + tp_dist  # long
```

`sl_dist` and `tp_dist` are distances from signal bar. On fill at bar N+1 price may differ, but distances are preserved. **Correct**.

### 3.3 TradeListAnalyzer — exit_price

```python
pnl_per_unit = pnl / size  # GROSS pnl (without commission)
if trade.long:
    exit_price = trade.price + pnl_per_unit
else:
    exit_price = trade.price - pnl_per_unit
```

For long: `exit = entry + pnl/size` → `pnl = (exit - entry) * size` ✓

**Note**: Uses `pnl` (gross), not `pnlcomm`. Commission is already in `realized_pnl` for dashboard. For exit price from PnL — gross is logical.

### 3.4 Win Rate / Profit Factor

- `_calculate_win_rate`: handles `won` as int (Backtrader when 0 wins) — **fixed**.
- `profit_factor`: `inf` replaced with 999.0 for JSON — **fixed**.

---

## 4. Possible Causes of Result Degradation

### 4.1 Data

1. **Extended end_date** — more bars at end of period.
2. **Cache** — on cache reset or `max_cache_age_days` expiry data is refetched; may differ from exchange.
3. **Different dates** — if configs for 02.03 and 04.03 differed (start_date, end_date), results will differ.

### 4.2 Configuration

Check in MongoDB for both run_ids:
- `initial_capital`, `leverage`, `risk_per_trade`
- `start_date`, `end_date`, `timeframes`
- `strategy_config` (trend_ema_period, risk_reward_ratio, etc.)

### 4.3 Strategy Behavior

- **Order cleanup** — after Margin/Reject strategy can enter again; with insufficient margin this can cause a cascade of losses.
- **Close on max_drawdown** — position is now force-closed; before it could stay open and add more loss.

---

## 5. Recommendations

### 5.1 Urgent

1. **Cap drawdown in display**: Cap at 100% for UI, since >100% means negative equity.
2. **Add equity check**: When `broker.getvalue() <= 0` stop backtest and log.
3. **Compare configs** of both backtests in MongoDB — `configuration` for `backtest_20260302_180422_53c33285` and `backtest_20260304_145333_b5e98829`.

### 5.2 Medium-term

1. **Margin call / liquidation**: Consider simulating margin call on negative equity.
2. **end_date mode**: Add option "include full last day" (default yes for backward compatibility).
3. **Logging**: On Margin/Reject log `broker.getvalue()`, `broker.getcash()` for debugging.

### 5.3 Tests

1. Unit test: when equity is negative drawdown > 100%.
2. Integration test: same config + fixed data → same result on repeated runs.

---

## 6. Reproduction Checklist

```bash
# 1. Get config of good backtest from MongoDB
# db.backtests.findOne({_id: "backtest_20260302_180422_53c33285"}, {configuration: 1})

# 2. Run with same config
# python main.py backtest  # with config from DB

# 3. Clear cache and rerun (if suspecting data)
# rm -rf data_cache/BTC*
# python main.py backtest

# 4. Temporarily revert data_loader end_dt for A/B test
```

---

## 7. Summary

| Component | Status | Comment |
|-----------|--------|---------|
| Drawdown > 100% | Expected | Reflects negative equity with leverage |
| DataLoader end_date | Change | Includes full last day |
| BaseStrategy order cleanup | Fix | Correct cleanup on Cancel/Margin/Reject |
| RiskManager validation | Fix | Clamp risk and leverage |
| bt_price_action size guard | Fix | Skip entry when size=0 |
| bt_price_action dd close | Fix | Close position when max_drawdown exceeded |

**Likely cause of degradation**: Combination of (1) extended end_date, (2) possible config/data differences, and (3) fixed order cleanup logic, so strategy keeps trading after margin rejections. For precise conclusion, compare configs and equity curves of both backtests.

---

## 8. Fixes (After Review)

### Problem: max_drawdown=30% did not trigger, drawdown reached 105%

**Cause**: Drawdown check ran in `next()` at bar start, but trade close (and equity update) happens in the same bar. By the next `next()` we already see the result — drawdown could exceed limit in one bar.

**Fixes**:

1. **Check in notify_trade** — right after trade close `_check_drawdown_after_trade()` is called. Equity is already updated, drawdown computed from peak and current. On limit exceed, `_dd_limit_hit` is set.

2. **Peak tracking** — `_equity_peak` updated in `_update_equity_peak()` (at start of `next()`) and in `_check_drawdown_after_trade()` (on trade close).

3. **Cap in RiskManager** — `max_drawdown_pct` limits `risk_amount`: one trade cannot lose more than `max_drawdown_pct`% of account. Protects from slippage and gaps.

4. **Early return on _dd_limit_hit** — at start of `next()` `_dd_limit_hit` is checked; when set, further logic is skipped.

5. **Slippage buffer in RiskManager** — risk cap per trade = max_drawdown/10, so with gap (up to 10× worse than stop) limit is not exceeded.

6. **Safe metric extraction** — `_safe_max_drawdown()` handles None, NaN, missing keys; won/lost handled as int or dict (Backtrader may return int when 0).
