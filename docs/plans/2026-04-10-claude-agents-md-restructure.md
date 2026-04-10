# CLAUDE.md + AGENTS.md Restructure — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current lean CLAUDE.md/AGENTS.md with a full 14-section governance structure and create 3 new agent_docs files (system_architecture, code_conventions, troubleshooting_known_issues).

**Architecture:** Pure documentation update — no code changes. 2 existing files rewritten, 3 new files created under `agent_docs/`. All files stay committed to git. No renames of existing dirs.

**Tech Stack:** Markdown. All content is self-contained in this plan — no lookups needed during execution.

---

## File Map

| Action | File |
|--------|------|
| Create | `agent_docs/system_architecture.md` |
| Create | `agent_docs/code_conventions.md` |
| Create | `agent_docs/troubleshooting_known_issues.md` |
| Rewrite | `CLAUDE.md` |
| Rewrite | `AGENTS.md` |

---

## Task 1: Create `agent_docs/system_architecture.md`

**Files:**
- Create: `agent_docs/system_architecture.md`

- [ ] **Step 1: Write the file**

Write `agent_docs/system_architecture.md` with this exact content:

```markdown
# System Architecture

Authoritative detail on module boundaries, data flow, and state management.
For the full directory map see [PROJECT_STRUCTURE.md](../PROJECT_STRUCTURE.md).

## Runtime topology

```
                    ┌─────────────────────────────────────┐
                    │           Docker Compose             │
                    │  mongo:27017   backend:8000          │
                    │  frontend: host 5174 → ctn 5173      │
                    └─────────────────────────────────────┘
```

Three processes in Docker Compose:
- `mongo` — MongoDB 7, port 27017, volumes: `mongo_data`, `data_cache`
- `backend` — FastAPI (uvicorn), port 8000
- `frontend` — Vite dev server, host port 5174 → container 5173

## Data flow (one direction only)

```
  engine/          →   web-dashboard/services/   →   web-dashboard/api/   →   React UI
  bt_backtest_engine    strategy_runtime.py           server.py               src/
  bt_live_engine        result_mapper.py              api/models.py
  strategies/                                         api/state.py
```

**Rule:** engine has no imports from `api/` or `web-dashboard/`. Dependency is strictly left-to-right.

## Module responsibilities

### `engine/`
| File | Responsibility |
|------|----------------|
| `base_engine.py` | Abstract engine interface |
| `bt_backtest_engine.py` | Backtrader backtest runner |
| `bt_live_engine.py` | Backtrader paper-live runner |
| `data_loader.py` | OHLCV load from Binance + `data_cache/` |
| `live_ws_client.py` | Binance WebSocket client |
| `live_data_feed.py` | Backtrader live data feed adapter |
| `bt_analyzers.py` | Custom Backtrader analyzers (trade metrics) |
| `timeframe_utils.py` | LTF-first timeframe ordering (`ordered_timeframes`) |
| `trade_metrics.py` | Trade-level metrics calculations |
| `trade_narrator.py` | Human-readable trade descriptions |
| `execution_settings.py` | Broker/commission config |
| `optimize_context.py` | Logging context for optimize runs |
| `logger.py` | Centralized logging setup |

### `strategies/`
| File | Responsibility |
|------|----------------|
| `base_strategy.py` | `BaseStrategy` — shared Backtrader hooks |
| `bt_price_action.py` | Primary strategy: HTF structure + LTF execution |
| `market_structure.py` | BOS/CHoCH detection, swing high/low tracking |
| `fvg_sweep_choch_strategy.py` | FVG + sweep + CHoCH strategy |
| `fast_test_strategy.py` | Minimal strategy for CI speed |
| `helpers/` | Shared helpers (risk manager, etc.) |

### `web-dashboard/services/`
| File | Responsibility |
|------|----------------|
| `strategy_runtime.py` | Resolves strategy class, builds runtime config, optimize config |
| `result_mapper.py` | Shapes engine results → API/DB response (trades, equity, metrics) |

### `web-dashboard/api/`
| File | Responsibility |
|------|----------------|
| `models.py` | Pydantic request/response models (`BacktestConfig`, `BacktestRequest`, `BacktestStatus`) |
| `state.py` | In-process runtime state: active runs, WS connections, console buffer |
| `logging_handlers.py` | Run log collectors — attach/detach to active runs |

### `web-dashboard/server.py`
FastAPI app entry: all HTTP routes + WebSocket `/ws`.

### `db/`
| File | Responsibility |
|------|----------------|
| `connection.py` | MongoDB connection; `USE_MONGOMOCK=true` → in-memory for tests |
| `repositories/backtest_repository.py` | Backtest run CRUD |
| `repositories/user_config_repository.py` | User strategy configs |
| `repositories/app_config_repository.py` | App-level config |

## State management

| State type | Location | Notes |
|------------|----------|-------|
| Active run handle | `api/state.py` | In-process; lost on restart |
| WS connections | `api/state.py` | In-process |
| Console log buffer | `api/state.py` | In-process ring buffer |
| Backtest results | MongoDB `backtests` | Durable |
| Strategy configs | MongoDB `user_configs` | Durable |
| App config | MongoDB `app_config` | Durable |
| OHLCV cache | `data_cache/` (volume) | File-based |

**Rule:** No hidden singletons. In-process state goes in `api/state.py`; anything durable goes in MongoDB.

## Multi-timeframe data contract

`engine/timeframe_utils.py::ordered_timeframes()` always sorts timeframes by duration ascending so:
- `data0` = LTF (e.g. 1H) — execution timeframe
- `data1` = HTF (e.g. 4H) — structure timeframe

Strategy code must never assume a different order. This is enforced by `ordered_timeframes`, not by config array order.

## Key contracts (do not bypass)

- Strategy config: always flow through `services/strategy_runtime.py::build_runtime_strategy_config`
- Results: always flow through `services/result_mapper.py` before reaching API or DB
- API shapes: defined in `api/models.py` — UI and engine must stay in sync through these
- Log attach/detach: use `api/logging_handlers.py` patterns — do not wire new logging directly into endpoints
```

- [ ] **Step 2: Verify the file was created**

Run: `head -5 agent_docs/system_architecture.md`
Expected: `# System Architecture`

---

## Task 2: Create `agent_docs/code_conventions.md`

**Files:**
- Create: `agent_docs/code_conventions.md`

- [ ] **Step 1: Write the file**

Write `agent_docs/code_conventions.md` with this exact content:

```markdown
# Code Conventions

Python and TypeScript/React conventions for this repo.

For linting config see `pyproject.toml` (Ruff) and `web-dashboard/.eslintrc.cjs` (ESLint).
Do not duplicate rule lists here — cross-link instead.

## Python

### Naming
- Modules and functions: `snake_case`
- Classes: `PascalCase`
- Constants: `UPPER_SNAKE_CASE`
- Private methods: `_leading_underscore`
- Test files: `test_<module>.py` under `tests/`

### Backtrader patterns
- Strategies extend `BaseStrategy` (`strategies/base_strategy.py`), not Backtrader's `Strategy` directly
- Indicator initialization goes in `__init__`, signal reading in `next()`
- Never read `self.data.close[0]` for a "future" value — use `[-N]` for confirmed bars
- Timeframe data: always use `self.data_ltf = self.datas[0]`, `self.data_htf = self.datas[1]` — order is guaranteed by `ordered_timeframes()`
- Magic numbers for thresholds (e.g. pivot span, ATR multiplier) must be strategy params, not inline literals

### General Python
- Prefer explicit `if x is None` over truthiness checks for objects that may be 0 or empty
- No bare `except:` — catch specific exceptions
- Logging: use `engine/logger.py` — do not create new loggers directly
- Config: no config files — strategy config loaded from MongoDB via repositories

### Ruff
Config in `pyproject.toml`. Run: `ruff check . && ruff format .`
Do not add `# noqa` suppressions without a comment explaining why.

## TypeScript / React

### Component structure
- One component per file, named identically to the file (`TradeList.tsx` exports `TradeList`)
- Props interface defined in the same file, named `<Component>Props`
- Keep components small — if a file exceeds ~200 lines, split by responsibility

### MUI v5
- Use MUI `sx` prop for one-off styles; extract to `styled()` only when reused across 2+ files
- Use MUI theme tokens (`theme.spacing`, `theme.palette`) — avoid hardcoded px/hex values
- Import from `@mui/material` not sub-paths unless tree-shaking requires it

### State and data
- API calls via `axios` (`axios` is the only HTTP client in deps)
- Component-local state: `useState`; shared/derived state: lift to parent or context
- Do not fetch data inside deeply nested components — fetch at page/panel level and pass down

### Charts
- Primary: Plotly.js (`react-plotly.js`) for backtest equity curves, trade scatter
- Secondary: Recharts for simpler bar/line charts
- Do not mix both libraries for the same data visualization

### Testing (Vitest)
- Test files: `*.test.tsx` or `*.test.ts` in same directory as the component
- Use `@testing-library/react` — prefer `getByRole` / `getByText` over `getByTestId`
- Mock API calls with `vi.mock` — do not let tests hit real HTTP endpoints

## Testing — Python (Pytest)

### Structure
- All tests under `tests/`
- One test file per module: `test_<module_name>.py`
- Group related tests in classes only when shared setup warrants it

### Conventions
- Test names: `test_<what>_<expected_outcome>` (e.g. `test_bos_up_when_close_above_last_sh`)
- Avoid testing implementation details — test observable behavior
- Use `conftest.py` fixtures for shared setup (MongoDB mock, strategy instances)
- MongoDB in tests: always set `USE_MONGOMOCK=true` unless the test is explicitly marked `@pytest.mark.live`

### What must have tests
- All market structure calculations (`market_structure.py`)
- All trade metric calculations (`trade_metrics.py`)
- All state transitions in strategies (entry/exit/filter logic)
- All result mapping in `result_mapper.py`
- All API endpoints (at least happy path + error path)

### TDD discipline
Write the failing test first. Run it to confirm it fails. Then implement. This is not optional.
```

- [ ] **Step 2: Verify the file was created**

Run: `head -5 agent_docs/code_conventions.md`
Expected: `# Code Conventions`

---

## Task 3: Create `agent_docs/troubleshooting_known_issues.md`

**Files:**
- Create: `agent_docs/troubleshooting_known_issues.md`

- [ ] **Step 1: Write the file**

Write `agent_docs/troubleshooting_known_issues.md` with this exact content:

```markdown
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
```

- [ ] **Step 2: Verify the file was created**

Run: `head -5 agent_docs/troubleshooting_known_issues.md`
Expected: `# Troubleshooting & Known Issues`

---

## Task 4: Rewrite `CLAUDE.md`

**Files:**
- Modify: `CLAUDE.md` (full rewrite)

- [ ] **Step 1: Replace the entire file content**

Write `CLAUDE.md` with this exact content:

```markdown
# CLAUDE.md — Backtrade Machine (`smc-bot`)

## Project

Crypto backtesting and paper live trading research tool. Not a financial product.

## Purpose

Backtrader execution engine + FastAPI API + React/TypeScript dashboard + MongoDB persistence.
Primary strategy: `bt_price_action` — HTF market structure detection (4H) with LTF execution (1H).

This is research tooling — not trading advice.

## Hard constraints

- Real-money live trading is a planned future milestone, not the current scope — do not implement, enable, or assume it without explicit instruction; `execution_mode` defaults to `paper` until intentionally promoted
- Never silently delete backtest results, run history, or MongoDB documents
- Destructive operations (drop collection, delete run, reset state) must be behind explicit API checks and user confirmation
- Do not add features, refactor, or clean up beyond what was asked
- Do not create files unless necessary — prefer editing existing ones

## Git safety rule

- The agent must never create commits
- The agent must never push
- The agent must never rebase, merge, or rewrite history
- Only the user commits and performs all final git actions
- The agent prepares changes, runs verification, and suggests commit messages — then stops

## Stack and technologies

### Backend / Engine
- Python 3.11+, Backtrader (execution engine), FastAPI (API server)
- Strategies: `BaseStrategy` subclasses in `strategies/`; shared `market_structure.py`
- Data: OHLCV from Binance via `engine/data_loader.py`; cached in `data_cache/`
- Fees, analyzers, WS feed: `engine/`

### UI
- React 18 + TypeScript + Vite
- MUI v5 (`@mui/material`) + Emotion for styling
- Charts: Plotly.js (main), Recharts (secondary)
- Drag-and-drop: dnd-kit
- Tests: Vitest + `@testing-library/react`
- Dashboard served via Docker Compose: host `5174` → container `5173`
- Real-time log stream via WebSocket `/ws`

### Data / storage
- MongoDB (Compose service `mongo`, port `27017`)
- Repositories in `db/`; in-process runtime state in `web-dashboard/api/state.py`
- No config files — strategy/runtime config lives in MongoDB only

### Tooling
- Linting: Ruff (`pyproject.toml`) for Python, ESLint for frontend
- Tests: Pytest (`python -m pytest -q`), Vitest (`npm run test -- --run`)
- Docker dev with hot reload: `docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build --watch`

## Architecture rules

- Engine (`engine/`) has no knowledge of API or dashboard — data flows one way: engine → services → API → UI
- Strategy config and runtime state flow through `web-dashboard/services/strategy_runtime.py` and `result_mapper.py` — do not bypass these with direct engine calls
- In-process runtime state lives in `web-dashboard/api/state.py`; durable history in MongoDB — no hidden singletons
- Request/response shapes are versioned in `web-dashboard/api/models.py` — keep engine config and UI in sync through these contracts
- Logging: `engine/logger.py`; dashboard log stream via `api/logging_handlers.py` + WS `/ws` — preserve attach/detach patterns when changing runs
- `tools/` is never imported by runtime — one-off seed/utility scripts only

## Implementation principle: build like an onion

Implement step by step from core business depth outward:

1. Core domain model and data structures
2. Pure business logic (strategies, calculations, analyzers)
3. Data access and persistence (repositories, DB schema)
4. Service layer and shared contracts
5. API layer
6. UI shell and integration
7. Hardening, verification, and refinement

Do not build outer layers on top of unstable or untested core logic.

## Engineering rules

- **Strict TDD** — write tests before implementation, always; no exceptions for "simple" logic
- Critical calculation and state-transition logic must not be written without tests
- Avoid hidden magic numbers and duplicated rules — one source of truth per formula/threshold
- No schema changes without updating `agent_docs/system_architecture.md`
- No critical business-rule changes without updating docs and tests in the same work cycle
- Optimize for a stable MVP, maintainable code, and minimal bugs
- Prefer explicitness and predictability over clever abstractions
- Do not add features, refactor, or clean up beyond what was asked
- No error handling for scenarios that cannot happen — trust internal guarantees, validate only at system boundaries

Testing expectations: `agent_docs/running_tests.md`
Code conventions: `agent_docs/code_conventions.md`

## 12-factor agent rules for this repo

- **Own prompts:** keep important project rules explicit in `CLAUDE.md` and `agent_docs/`
- **Own context:** use `CLAUDE.md` (committed) + `agent_docs/` as durable memory; use `docs/plans/` for per-task execution plans
- **Tools as structured outputs:** create plans, schemas, and specs as real artifacts under `docs/`
- **Unify execution and business state:** avoid scattered critical logic — engine config flows through `strategy_runtime.py`, results through `result_mapper.py`
- **Launch/pause/resume with simple artifacts:** plans and docs must support safe continuation across sessions
- **Own control flow:** plan first, scaffold second, implement third
- **Compact errors into context:** record failures and assumptions in `agent_docs/troubleshooting_known_issues.md`
- **Use small focused phases:** do not solve the whole trading system at once
- **Prefer deterministic transformations:** backtest calculations and results must be reproducible

## Documentation discipline

Documentation and code together are the source of truth for behavior and implementation.
Update relevant docs in the same work cycle as the code change.

| If a change affects... | Update... |
|------------------------|-----------|
| Global rules, workflow, stack, or agent discipline | `CLAUDE.md` |
| Architecture, module boundaries, data flow | `agent_docs/system_architecture.md` |
| API routes, request/response shapes | `PROJECT_STRUCTURE.md` |
| Engine or strategy behavior | relevant doc under `docs/` + `PROJECT_STRUCTURE.md` |
| Testing expectations or commands | `agent_docs/running_tests.md` |
| Docker, dev server, compose setup | `agent_docs/building_and_docker.md` |
| Code style, conventions, linting rules | `agent_docs/code_conventions.md` |
| A meaningful bug, incident, or fix | `agent_docs/troubleshooting_known_issues.md` |
| Run modes (single/optimize/live) | `docs/BACKTEST_RUN_MODES.md` |
| Technical debt or refactor priorities | `docs/TECHNICAL_DEBT_REPORT.md` |

Do not leave documentation stale after code changes. Prefer cross-links over duplicating explanations.

## Development workflow

For every non-trivial task:

1. **Plan** — write a clear plan, save to `docs/plans/YYYY-MM-DD-<task>.md` when non-trivial
2. **Tests first** — write tests before implementation; no exceptions
3. **Skeleton** — scaffold file/module/class structure with stubs before logic
4. **Build** — implement; DRY, KISS; stubs where integrations aren't proven yet
5. **Polish** — replace stubs, remove dead code and magic numbers, cover real failure modes only
6. **Verify** — run full test suite before claiming done (see `agent_docs/running_tests.md`)
7. **Report** — what was built, what was documented, test results, known gaps

## Authoritative docs

| Doc | Covers |
|-----|--------|
| `CLAUDE.md` | Root rules and constraints |
| `AGENTS.md` | Navigation index for all agent docs |
| `PROJECT_STRUCTURE.md` | Module map, API routes, data flow |
| `agent_docs/system_architecture.md` | Architecture, module boundaries, data flow detail |
| `agent_docs/running_tests.md` | Testing expectations and commands |
| `agent_docs/building_and_docker.md` | Docker, dev server, compose setup |
| `agent_docs/api_and_architecture.md` | API boundary vs services vs engine (pointers) |
| `agent_docs/development_workflow.md` | Development workflow detail |
| `agent_docs/code_conventions.md` | Python + React/TS style and conventions |
| `agent_docs/troubleshooting_known_issues.md` | Failure memory, incidents, root causes |
| `docs/plans/` | Per-task execution plans |
| `docs/BACKTEST_RUN_MODES.md` | `single` vs `optimize` vs `live` run modes |
| `docs/TECHNICAL_DEBT_REPORT.md` | Debt register and safe refactor order |

## Done checks

Before claiming a non-trivial task is done:
- [ ] Tests written first, passing now
- [ ] Relevant docs updated in the same work cycle
- [ ] No hidden architecture drift introduced
- [ ] `agent_docs/troubleshooting_known_issues.md` updated if a meaningful issue was found or solved
- [ ] No git commit performed by the agent

## Troubleshooting memory

Maintain `agent_docs/troubleshooting_known_issues.md`. For each meaningful issue record:
- Date, title, context
- Symptoms / error
- Root cause (if known)
- Resolution
- Prevention / future guardrail
```

- [ ] **Step 2: Verify the section count**

Run: `grep "^## " CLAUDE.md | wc -l`
Expected: `14`

---

## Task 5: Update `AGENTS.md`

**Files:**
- Modify: `AGENTS.md` (full rewrite)

- [ ] **Step 1: Replace the entire file content**

Write `AGENTS.md` with this exact content:

```markdown
# AGENTS.md

Use **[CLAUDE.md](CLAUDE.md)** as the primary onboarding file for coding agents — project purpose, stack, architecture rules, workflow, and verification.

## Doc navigation

| Need | Read |
|------|------|
| Root rules, constraints, workflow | [CLAUDE.md](CLAUDE.md) |
| Module map, API routes, data flow | [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md) |
| Architecture, module boundaries, state management | [agent_docs/system_architecture.md](agent_docs/system_architecture.md) |
| API boundary vs services vs engine | [agent_docs/api_and_architecture.md](agent_docs/api_and_architecture.md) |
| Pytest / Vitest / CI expectations | [agent_docs/running_tests.md](agent_docs/running_tests.md) |
| Docker / dev server / compose | [agent_docs/building_and_docker.md](agent_docs/building_and_docker.md) |
| Development workflow detail | [agent_docs/development_workflow.md](agent_docs/development_workflow.md) |
| Python + React/TS conventions | [agent_docs/code_conventions.md](agent_docs/code_conventions.md) |
| Bugs, incidents, known issues | [agent_docs/troubleshooting_known_issues.md](agent_docs/troubleshooting_known_issues.md) |
| Backtest run modes | [docs/BACKTEST_RUN_MODES.md](docs/BACKTEST_RUN_MODES.md) |
| Technical debt and refactor priorities | [docs/TECHNICAL_DEBT_REPORT.md](docs/TECHNICAL_DEBT_REPORT.md) |

## Rules of engagement

- Match existing patterns in the touched layer
- Run linters/tests rather than hand-auditing style
- Keep diffs minimal and scoped to the request
- Never create commits, push, or rewrite history — prepare changes and leave git actions to the user
```

- [ ] **Step 2: Verify the file**

Run: `grep "^## " AGENTS.md`
Expected output:
```
## Doc navigation
## Rules of engagement
```

---

## Self-review notes

- All 5 files have complete content — no TBDs or placeholders
- `system_architecture.md` data flow matches actual code (`strategy_runtime.py`, `result_mapper.py`, `api/state.py`)
- `code_conventions.md` references `pyproject.toml` and `.eslintrc.cjs` rather than duplicating rules
- `troubleshooting_known_issues.md` seeded with 3 verified incidents from `docs/`
- `CLAUDE.md` has exactly 14 `##` sections
- `AGENTS.md` lookup table includes all 3 new files
- No circular references; cross-links go one direction (AGENTS.md → CLAUDE.md → agent_docs/)
- `agent_docs/development_workflow.md` is not replaced — existing file covers workflow detail; CLAUDE.md now summarizes it inline
