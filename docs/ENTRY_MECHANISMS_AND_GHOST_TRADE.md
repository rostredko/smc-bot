# Entry Mechanisms and Ghost Trade Bug

**Goal**: Backtest and Live must show identical results. A strategy tested in backtest should behave the same in live trading.

---

## Two Entry Approaches

### Approach A: buy_bracket / sell_bracket (Master)

**How it works**:
```python
bracket = self.buy_bracket(
    price=self.close[0],       # entry price (not used for Market)
    stopprice=sl_price_ref,   # SL from signal bar: low - buffer
    limitprice=tp_price_ref,   # TP from signal bar: close + tp_distance
    exectype=bt.Order.Market,
    size=size
)
# bracket = [main_order, stop_order, limit_order]
```

**Sequence**:
1. Signal on bar N (close, low, high known)
2. Three orders created: market buy + sell stop (SL) + sell limit (TP)
3. Main fills on bar N+1 at open (market fill)
4. SL and TP are **fixed prices** from bar N, independent of exec_price
5. Backtrader broker creates them as bracket — built-in OCO (One-Cancels-Other)

**Pros**:
- Native OCO — ghost trade impossible (broker manages group)
- Simple code — everything in one call
- SL/TP known before fill

**Cons**:
- SL/TP tied to **signal bar**, not actual fill
- Real risk: `|exec_price - sl_price|`, not `close - sl_price`
- Gap between close and next_bar_open can change risk vs expected
- **Live**: buy_bracket supported only on Interactive Brokers. Binance, Bybit, most crypto exchanges — **no**. For live would need emulation (market → fill → place stop/limit separately)

---

### Approach B: Market buy + notify_order (Feature / exec_price) — **used**

**How it works**:
```python
# 1. In _enter_long:
self.order = self.buy(size=size, exectype=bt.Order.Market)
# pending_metadata stores sl_distance, tp_distance, direction

# 2. In notify_order on entry fill:
exec_price = order.executed.price
real_sl = exec_price - sl_dist   # SL tied to fill
real_tp = exec_price + tp_dist   # TP tied to fill
# Stop first, TP with oco=Stop — on ambiguous bar Stop has priority
self.stop_order = self.sell(price=real_sl, exectype=bt.Order.Stop, size=size)
self.tp_order = self.sell(price=real_tp, exectype=bt.Order.Limit, size=size, oco=self.stop_order)
```

**Sequence**:
1. Signal on bar N
2. Market buy — fills on bar N+1 at open (exec_price)
3. In notify_order: create SL and TP **relative to exec_price**
4. Risk is fixed: at SL we lose exactly `risk_amount = size × sl_distance`

**Pros**:
- Risk per trade is **predictable** (see formula below)
- SL/TP always relative to actual fill — correct for live
- **Live**: universal — market → fill → place stop/limit on exchange
- Backtest and live use the same logic

**Cons**:
- SL and TP are two separate orders. OCO required, otherwise **ghost trade** (see below)

---

## Ghost Trade Bug

### What Happens

With approach B (market + notify_order) we create two orders: SL (Stop) and TP (Limit). Both are sell for long.

**Problem**: when in **one bar** price hits both TP and SL (e.g. high ≥ TP and low ≤ SL), both orders can fill:

1. TP fills → closes long, position = 0
2. SL fills → sells, but position already 0 → **opens short** (ghost)

### Symptoms in Logs

```
[2024-03-12 16:00:00] SELL EXECUTED, Price: 73271.77  ← TP (profit)
[2024-03-12 16:00:00] 🔴 TRADE CLOSED [#6]: PnL: 58.30 | Reason: Stop Loss  ← wrong reason
CRITICAL: Trade 7 opened WITHOUT metadata! Pending is None. Closing orphan position.
[2024-03-12 17:00:00] SELL EXECUTED, Price: 71103.51, Cost: -5907.59  ← SL opened short
```

- `Cost: -5907` — negative cost = short position
- `Trade 7 opened WITHOUT metadata` — trade opened not via _enter_long, no pending_metadata
- Max Drawdown 58–100% — ghost short loses money

### Why OCO Did Not Work

We tried linking orders via `oco=`:

```python
self.tp_order = self.sell(price=real_tp, exectype=bt.Order.Limit, size=size)
self.stop_order = self.sell(price=real_sl, exectype=bt.Order.Stop, size=size, oco=self.tp_order)
```

**Expected**: when one fills the other is auto-canceled (Backtrader OCO).

**Actual**: ghost trade remained. Possible causes:
1. Order processing order in BackBroker — both may fill before `_ococheck` runs
2. Intra-bar simulation: high/low in one bar — both triggers fire in same iteration
3. OCO in Backtrader implemented for backtest only, edge cases possible

### What We Tried

| Attempt | Result |
|---------|--------|
| `oco=self.stop_order` (SL leader) | Ghost remained |
| `oco=self.tp_order` (TP leader, SL with oco=TP) | Ghost remained |
| Swapped creation order (TP first, SL second) | Ghost remained |
| `self.close()` in notify_trade on orphan | Too late — damage already done in bar |
| Flag `_close_orphan_position` + close in next() | Closes on next bar — 1 bar loss |

### Solution: OCO Guard + Stop Priority

Ghost trade is fixed by broker patch (`bt_oco_patch.py`). Only Feature path (market + exec_price) is used.

---

## Backtest ↔ Live: Requirements

For results to match:

1. **Same entry logic** — same approach (bracket or market+notify) in both modes
2. **Same SL/TP** — tied to same price (signal bar or exec_price)
3. **Same size calculation** — see formula below
4. **No ghost trade** — only one of SL/TP can fill

### Effective Position Size Formula

Base formula: `raw_size = risk_amount / sl_distance`, where `risk_amount = account × risk_per_trade_pct`.

Actual size is capped by:
- **leverage_cap**: `size × entry_price ≤ account × leverage`
- **dd_cap** (when `max_drawdown`): `risk_amount ≤ account × (max_dd / 100) / 10` and `size × entry_price ≤ account × (max_dd / 100) / position_cap_adverse`

Total: `effective_size = min(raw_size, leverage_cap_size, dd_cap_size)`.

### Summary

- **Feature path** (market + exec_price) — only mode. Backtest and live use the same logic.
- **OCO guard** — broker patch prevents ghost trade on same-bar double fill.

---

## Technical Details (for investigation)

### Specific Bug (Trade 6, 2024-03-12)

- Entry: 72570, SL: 71103, TP: 73271
- Bar 16:00: high ≥ 73271 (TP hit), low ≤ 71103 (SL hit) — both in bar range
- Bar 17:00: SL again (if not canceled)

### Backtrader Broker Flow (bbroker.py)

```
# Bar processing:
while True:
    order = self.pending.popleft()
    self._try_exec(order)   # checks high/low, fills if needed
    if order.status == Completed:
        self.notify(order)
        self._ococheck(order)   # cancels others in OCO group
```

Question: if both TP and SL are in pending and both trigger in one bar — in what order are they processed? By popleft — first added. We create TP first, then SL — so TP should be processed first. If TP fills, _ococheck should cancel SL. Why doesn't it?

### Hypotheses

- **A**: Limit and Stop processed in different loops? (e.g. Limit by close, Stop by low?)
- **B**: `_ococheck` runs after `_execute`, but second order already filled in same iteration?
- **C**: Bracket orders create parent-child link, not OCO — different cancel logic?

---

## Solution (exec_price + OCO guard)

**Final policy**:
- **Default**: exec_price — only mode. Market entry, SL/TP from `order.executed.price` in `notify_order`.
- **OCO guard**: broker patch prevents ghost trade.
- **Ambiguous bar** (high ≥ tp and low ≤ sl): Stop has priority over TP. Create Stop first, TP with `oco=Stop`.

### Broker Patch (`engine/bt_oco_patch.py`)

- `apply_oco_guard()` — monkey-patch for `BackBroker`:
  - In `next()` on each bar introduces set `_oco_done`.
  - Before `_try_exec(order)`: if order's OCO group is already in `_oco_done`, order is canceled immediately.
  - In `_ococheck`: after computing `ocoref` it is added to `_oco_done` before iterating pending.
  - **cancel()**: also removes order from `submitted` (not just `pending`) — otherwise on trailing/breakeven in entry fill bar cancel silently fails, old orders remain and fire later.
- Patch is applied by early import in `engine/base_engine.py` (before Cerebro creation).

### Regression Tests

- `tests/test_oco_same_bar.py`: one bar with `high >= tp` and `low <= sl` — same-bar OCO.
- `tests/test_exit_replace_submitted_no_orphan.py`: entry fill → TP hit — no orphan on cancel/replace in entry bar.
- Run: `pytest tests/test_oco_same_bar.py tests/test_exit_replace_submitted_no_orphan.py -v`

### Strategy

- `base_strategy.notify_order`: on first exit fill cancels sibling, clears `stop_order`/`tp_order`. On entry fill saves `_entry_exec_bar`.
- `base_strategy.notify_trade`: on trade close — hard cleanup: cancel all live exit orders for the instrument.
- `bt_price_action`: trailing/breakeven only if `len(data) > _entry_exec_bar` and `stop_order.status == Accepted`. Stop first, TP with `oco=Stop`.

---

## Files

- `strategies/base_strategy.py` — notify_order, SL/TP from exec_price
- `strategies/bt_price_action.py` — _enter_long, _enter_short, _place_entry
- `engine/bt_oco_patch.py` — OCO guard patch
