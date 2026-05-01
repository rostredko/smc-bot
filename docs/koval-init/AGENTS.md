# AGENTS.md — Koval

> Universal open-source algo-trading platform for traders without programming knowledge.
> Repo: git@gitlab.com:koval-group/koval-ai.git
> Full agent guide: [CLAUDE.md](CLAUDE.md)

---

## Hard constraints

- Real account live trading (real money) is a future milestone — do not implement without explicit instruction
- `execution_mode` defaults to `paper` or `sandbox` until intentionally promoted
- Never silently delete backtest results, run history, or MongoDB documents
- Destructive operations must be behind explicit API checks and user confirmation
- Do not add features, refactor, or clean up beyond what was asked
- ALL Backtrader code lives in `koval/adapters/backtrader/` — strategies never import `backtrader` directly

## Git safety rule

- Never create commits
- Never push
- Never rebase, merge, or rewrite history
- Only the user commits and performs all final git actions

## Build and test

**Check session state before any task:**
```bash
git status
git log --oneline -10
```

**Run backend tests (from repo root):**
```bash
USE_MONGOMOCK=true python -m pytest -q
```

**Run frontend checks (from `dashboard/`):**
```bash
npm run test -- --run
npm run lint
npm run build
```

**Lint Python:**
```bash
ruff check . && ruff format .
```

**Dev stack with hot reload:**
```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build --watch
```

**Ports:** API `8000` · Dashboard `5174` (host) → `5173` (container) · MongoDB `27017`

**Env vars for tests:** `USE_MONGOMOCK=true`. Copy `.env.example` → `.env` for local dev.

## Architecture rules

Data flows **one direction only**: `koval/` → `api/services/` → `api/routers/` → UI

- `koval/adapters/backtrader/` contains ALL Backtrader-specific code — strategies use `DeclarativeStrategy`, never `bt.Strategy`
- `koval/blocks/` contains pure functions — no BT, no side effects, fully unit-testable
- Strategy config flows through `koval/strategy/registry.py`
- Results flow through `api/services/result_mapper.py`
- In-process runtime state in `api/state.py`; durable history in MongoDB
- `tools/` is never imported by runtime — one-off scripts only

## Key architecture

```
koval/
├── engine/           → Backtest + Live runners (use adapters/backtrader internally)
├── adapters/
│   └── backtrader/   → ALL BT code (GPL-3.0): BTStrategyAdapter, OCO patch, analyzers
├── strategy/
│   ├── base/         → DeclarativeStrategy ABC, TradeSetup dataclasses
│   ├── registry.py   → Strategy registry + Pydantic schemas
│   └── block_assembler.py → JSON block graph → DeclarativeStrategy
├── blocks/           → Pure functions: signals, filters, exits, risk
├── exchanges/        → ExchangeAdapter ABC + Binance + WhiteBIT
└── db/               → MongoDB repositories

api/
├── server.py         → FastAPI app factory (max 100 lines)
├── routers/          → strategies, backtest, live, results
├── services/         → backtest_service, live_service, result_mapper
├── models.py         → Pydantic request/response models
├── state.py          → In-process runtime state
└── ws.py             → WebSocket /ws

dashboard/            → React 18 + TypeScript + Vite + MUI v5
├── src/features/
│   ├── block-builder/   → react-flow drag-drop strategy canvas
│   ├── strategy-config/ → JSON Schema → auto-rendered slider forms
│   ├── backtest/        → backtest results, trade walkthrough
│   └── live-monitor/    → real-time P&L, positions, kill switch
```

## Development workflow

1. **Plan** — write plan to `docs/plans/YYYY-MM-DD-<task>.md` for non-trivial tasks
2. **Tests first** — write failing tests before implementation; no exceptions
3. **Skeleton** — scaffold structure with stubs before logic
4. **Build** — implement; DRY, KISS
5. **Polish** — replace stubs, remove dead code
6. **Verify** — run full test suite before claiming done
7. **Report** — what was built, docs updated, test results, known gaps

**Done checks:**
- [ ] Tests written first, passing now
- [ ] Relevant docs updated in the same work cycle
- [ ] No hidden architecture drift introduced
- [ ] `agent_docs/troubleshooting_known_issues.md` updated if a meaningful issue was found
- [ ] No git commit performed by the agent

## Code conventions (key rules)

- Strategies extend `DeclarativeStrategy`, never `bt.Strategy` or `BTStrategyAdapter` directly
- Block functions: pure — `def check_rsi(value: float, config: dict) -> bool`, no state
- Use `make_bt_strategy_class(MyStrategy)` factory to create BT-compatible class
- No config files — strategy config loaded from MongoDB only
- MUI v5 `sx` prop for one-off styles; `styled()` only when reused across 2+ files
- Full conventions: [agent_docs/code_conventions.md](agent_docs/code_conventions.md)

## Stack

| Layer | Tech |
|-------|------|
| Engine | Python 3.11+, Backtrader (via adapter), FastAPI |
| Blocks | Pure Python functions, TA-Lib |
| Exchanges | CCXT + custom WebSocket adapters |
| UI | React 18 + TypeScript + Vite + MUI v5 + react-flow |
| Charts | Plotly.js (primary), Recharts (secondary) |
| DB | MongoDB via `koval/db/repositories/` |
| Tests | Pytest (backend), Vitest + @testing-library/react (frontend) |
| Lint | Ruff (`pyproject.toml`), ESLint |

## Doc navigation

| Need | Read |
|------|------|
| Full rules, constraints, workflow | [CLAUDE.md](CLAUDE.md) |
| Module map, API routes | [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md) |
| Architecture, boundaries, data flow | [agent_docs/system_architecture.md](agent_docs/system_architecture.md) |
| Test commands, CI, coverage | [agent_docs/running_tests.md](agent_docs/running_tests.md) |
| Docker, dev server, env vars | [agent_docs/building_and_docker.md](agent_docs/building_and_docker.md) |
| Python + React/TS conventions | [agent_docs/code_conventions.md](agent_docs/code_conventions.md) |
| UI/UX design system | [agent_docs/ui_design_system.md](agent_docs/ui_design_system.md) |
| Available blocks, how to add new | [agent_docs/block_library.md](agent_docs/block_library.md) |
| Exchange adapters, WhiteBIT, Binance | [agent_docs/exchange_adapters.md](agent_docs/exchange_adapters.md) |
| Bugs, incidents, known issues | [agent_docs/troubleshooting_known_issues.md](agent_docs/troubleshooting_known_issues.md) |
