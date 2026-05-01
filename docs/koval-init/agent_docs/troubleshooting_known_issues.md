# Troubleshooting & Known Issues — Koval

## Format

Each entry:
- **Date** — when discovered
- **Title** — short identifier
- **Symptoms** — what you observe
- **Root cause** — why it happens
- **Resolution** — how it was fixed
- **Prevention** — guardrail for the future

---

## 2026-05-01 — Backtrader OCO same-bar double-fill

**Symptoms:** Two trades close on the same bar (one TP, one SL). PnL is incorrect. Ghost trade appears in results.

**Root cause:** Backtrader's `_ococheck` runs after `_try_exec` internally. When both TP and SL prices are hit within the same bar, both orders can fill before cancellation propagates.

**Resolution:** `koval/adapters/backtrader/oco_patch.py` patches `BackBroker` to add a fill guard. Must be applied before any `Cerebro()` instantiation via `apply_oco_guard()`.

**Prevention:** `oco_patch.py` is called in `backtest_engine.py` and `live_engine.py` before Cerebro creation. Never remove this call. Never modify `oco_patch.py` without running the full test suite.

---

*Add new issues here as they are discovered.*
