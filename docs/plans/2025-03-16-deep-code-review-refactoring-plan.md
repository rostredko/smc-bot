# smc-bot Deep Code Review and Refactoring Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

## Implementation Summary

Refactoring completed across all phases: conftest fixtures fixed and strategy default unified (Phase 1); API layer extracted into `web-dashboard/api/` with models, state, and logging handlers (Phase 2); engine utilities moved to `timeframe_utils.py` and `utils.py` (Phase 3); configuration consolidation via `strategy_runtime` (Phase 4); test coverage added for engine and services (Phase 5); documentation updated in PROJECT_STRUCTURE.md, README.md, and this plan (Phase 6).

---

**Goal:** Improve code maintainability through refactoring per SOLID, Clean Code, and best practices; increase test coverage; update documentation without breaking current functionality.

**Architecture:** Incremental refactoring with backward compatibility. Single Responsibility (SRP), layer isolation, duplication removal.

**Tech Stack:** Python 3.10+, Backtrader, FastAPI, React, MongoDB, pytest.

---

## 1. Executive Summary

smc-bot is a trading platform with backtest/live engines, FastAPI backend, and React dashboard. The code is generally working (259 tests pass), but there is technical debt:

- **server.py** ~2400 lines — SRP violation, multiple responsibilities
- **conftest.py** — broken fixtures (import non-existent modules)
- **Duplication** — config logic in main.py and server.py
- **Global state** — `running_backtests`, `live_trading_state`, `active_connections`
- **Inconsistency** — `BacktestConfig.strategy = "smc_strategy"` vs `resolve_strategy_class` default `"bt_price_action"`
- **Documentation** — docs/ in .gitignore, PROJECT_STRUCTURE.md outdated

---

## 2. Scope and Constraints

| Constraint | Description |
|------------|-------------|
| **Do not break functionality** | All 259 tests must pass after each phase |
| **Backward compatibility** | API endpoints, configs, strategies — no breaking changes |
| **Incremental** | Small commits, verification after each step |
| **No new bugs** | Regression tests before merge |

---

## 3. Current State Analysis

### 3.1 Engine Layer (`engine/`)

| Problem | File | Priority |
|---------|------|----------|
| Side-effect on import | `base_engine.py` — `apply_oco_guard()` on import | Medium |
| MockLogger in BaseEngine | `base_engine.py` — built-in MockLogger instead of DI | Low |
| _safe_float duplication | `bt_backtest_engine.py` — can extract to utils | Low |
| Long methods | `bt_backtest_engine.py` — `_build_forced_final_close_record` ~70 lines | Medium |

### 3.2 Strategy Layer (`strategies/`)

| Problem | File | Priority |
|---------|------|----------|
| God class | `base_strategy.py` — ~400 lines, many responsibilities | High |
| Long params | `bt_price_action.py` — 40+ params in one class | Medium |
| Mixed logic | `base_strategy.py` — funding, OCO, drawdown, narrative in one place | High |

### 3.3 API Layer (`web-dashboard/server.py`)

| Problem | Description | Priority |
|---------|-------------|----------|
| Fat server | ~2400 lines, all endpoints in one file | High |
| Global state | `running_backtests`, `live_trading_state`, `active_connections` | High |
| Duplication | `_normalize_json_config` in main.py vs `build_runtime_strategy_config` in server | Medium |
| Inline helpers | `_RunLogCollector`, `_strip_sensitive_live_config_fields`, etc. — can extract | Medium |

### 3.4 Tests (`tests/conftest.py`)

| Problem | Description | Priority |
|---------|-------------|----------|
| Broken fixtures | `risk_manager`, `logger`, `performance_reporter`, `mock_position`, `simple_test_strategy`, `smc_strategy`, `order_block_detector`, `fvg_detector`, `liquidity_mapper` — import non-existent modules | High |
| Unused fixtures | `backtest_config` uses `simple_test_strategy`; `spot_config` — `smc_strategy` | Medium |

### 3.5 Configuration

| Problem | File | Description |
|---------|------|-------------|
| Inconsistency | `backend/server.py` | `BacktestConfig.strategy = "smc_strategy"` vs `resolve_strategy_class` default `"bt_price_action"` |
| Duplication | `main.py` vs `server.py` | `_normalize_json_config`, `_build_cli_runtime_strategy_config` vs `build_runtime_strategy_config` |

---

## 4. SOLID / Clean Code Violations

### 4.1 Single Responsibility Principle (SRP)

- **server.py** — config, backtest lifecycle, live lifecycle, WebSocket, OHLCV API, market structure, result mapping, logging
- **BaseStrategy** — order lifecycle, OCO, funding, drawdown, narrative, signal thesis

### 4.2 Open/Closed Principle (OCP)

- Adding a new strategy requires changing `strategy_runtime.py` (LEGACY_ALIASES)
- Adding a new endpoint — edit server.py

### 4.3 Dependency Inversion (DIP)

- `BaseEngine` creates `MockLogger` internally — hard dependency
- `BaseStrategy` directly uses `RiskManager.calculate_position_size` (static call)
- `server.py` directly imports engine, strategies, db

### 4.4 Clean Code

- Long functions: `notify_order` ~100 lines, `_build_forced_final_close_record` ~70 lines
- Magic numbers: `10**9` in `_timeframe_to_minutes`, `RUN_LOG_CAPTURE_MAX_LINES = 12000`
- Unclear names: `_oco_closed`, `_dd_stop_runstop`

---

## 5. Refactoring Phases

### Phase 1: Critical Fixes (low risk) — Completed

| Task | Files | Description |
|------|-------|-------------|
| 1.1 | `tests/conftest.py` | Remove or fix broken fixtures |
| 1.2 | `web-dashboard/server.py` | Unify `BacktestConfig.strategy` default to `"bt_price_action"` |
| 1.3 | `tests/` | Add tests for conftest fixtures if used |

### Phase 2: Server Decomposition (medium risk) — Completed

| Task | Files | Description |
|------|-------|-------------|
| 2.1 | `web-dashboard/api/` | Create `api/routes/` — backtest, live, config, ohlcv, results |
| 2.2 | `web-dashboard/api/` | Create `api/state.py` — encapsulate `running_backtests`, `live_trading_state`, `active_connections` |
| 2.3 | `web-dashboard/api/` | Create `api/logging_handlers.py` — `_RunLogCollector`, `_attach_run_log_handlers` |
| 2.4 | `web-dashboard/server.py` | Import routes from api/, keep only app setup and lifespan |
| 2.5 | `tests/` | Add tests for new API modules |

### Phase 3: Engine & Strategy Refactoring (medium risk) — Completed

| Task | Files | Description |
|------|-------|-------------|
| 3.1 | `engine/base_engine.py` | Extract `_timeframe_to_minutes`, `_ordered_timeframes` to `engine/timeframe_utils.py` |
| 3.2 | `strategies/base_strategy.py` | Extract funding logic to `strategies/helpers/funding.py` |
| 3.3 | `strategies/base_strategy.py` | Extract drawdown check to `strategies/helpers/drawdown_guard.py` |
| 3.4 | `engine/bt_backtest_engine.py` | Extract `_build_forced_final_close_record` to separate builder |
| 3.5 | `engine/` | Create `engine/utils.py` — `_safe_float`, common helpers |

### Phase 4: Configuration Consolidation (low risk) — Completed

| Task | Files | Description |
|------|-------|-------------|
| 4.1 | `web-dashboard/services/strategy_runtime.py` | Add `normalize_config_for_runtime()` — single normalization point |
| 4.2 | `main.py` | Use `build_runtime_strategy_config` from strategy_runtime instead of duplicating |
| 4.3 | `web-dashboard/server.py` | Unify normalization calls |

### Phase 5: Test Coverage (low risk) — Completed

| Task | Files | Description |
|------|-------|-------------|
| 5.1 | `tests/test_base_engine.py` | Add tests for `_timeframe_to_minutes`, `_ordered_timeframes` |
| 5.2 | `tests/test_bt_backtest_engine.py` | Tests for `_build_forced_final_close_record` edge cases |
| 5.3 | `tests/test_server.py` | New module — tests for isolated API endpoints |
| 5.4 | `tests/test_risk_manager.py` | Already covered; add edge cases for `position_cap_adverse` |
| 5.5 | `tests/test_data_loader.py` | Cover DB cache fallback |
| 5.6 | Coverage report | `pytest --cov=engine --cov=strategies --cov=web-dashboard --cov-report=html` |

### Phase 6: Documentation (low risk) — Completed

| Task | Files | Description |
|------|-------|-------------|
| 6.1 | `PROJECT_STRUCTURE.md` | Update after server refactor |
| 6.2 | `docs/` | Remove docs from .gitignore or create `docs/` in repo (README references docs/) |
| 6.3 | `README.md` | Add "Architecture" section with layer diagram |
| 6.4 | Docstrings | Add/update docstrings in key modules (base_engine, base_strategy, strategy_runtime) |

---

## 6. Implementation Order

1. **Phase 1** — critical fixes (conftest, strategy default)
2. **Phase 5.1–5.2** — engine tests (before engine refactor)
3. **Phase 3** — engine/strategy refactoring
4. **Phase 4** — configuration consolidation
5. **Phase 2** — server decomposition
6. **Phase 5.3–5.6** — API tests
7. **Phase 6** — documentation

---

## 7. Verification Checklist

After each phase:

- [ ] `./.venv/bin/python -m pytest tests/ -q` — all tests pass
- [ ] `cd web-dashboard && npm run build` — frontend builds
- [ ] `docker compose up -d --build` — app starts
- [ ] Manual check: backtest start, live start, results, history

---

## 8. Rollback Strategy

- Each phase — separate branch or commit sequence
- Before merge — `git diff main --stat` for review
- On regression — revert last phase commit

---

## 9. Task Breakdown (Phase 1 — detailed)

### Task 1.1: Fix conftest broken fixtures

**Files:** `tests/conftest.py`

**Step 1:** Remove fixtures that import non-existent modules:
- `risk_manager` (engine.risk_manager) → `strategies.helpers.risk_manager.RiskManager` — static class, fixture not needed
- `logger` (engine.Logger) → does not exist
- `performance_reporter` (engine.metrics.PerformanceReporter) → does not exist
- `mock_position` (engine.position.Position) → does not exist
- `simple_test_strategy` (strategies.simple_test_strategy) → does not exist
- `smc_strategy` (strategies.smc_strategy) → does not exist
- `order_block_detector`, `fvg_detector`, `liquidity_mapper` (engine.smc_analysis) → does not exist

**Step 2:** Verified: no test uses these fixtures as parameters — dead code. Safe to remove.

**Step 3:** Update `backtest_config` and `spot_config` — `strategy: "bt_price_action"` or `"fast_test_strategy"`.

### Task 1.2: Unify strategy default

**Files:** `web-dashboard/server.py`

**Change:** `BacktestConfig.strategy: str = "smc_strategy"` → `"bt_price_action"`

**Reason:** `resolve_strategy_class` default is `"bt_price_action"`; `smc_strategy` does not exist.

---

## 10. References

- [PROJECT_STRUCTURE.md](../../PROJECT_STRUCTURE.md)
- [README.md](../../README.md)
- [superpowers:verification-before-completion]
- [superpowers:requesting-code-review]
