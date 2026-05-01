# CLAUDE.md — Koval

## Project

**Koval** (укр. коваль = blacksmith) — universal open-source algo-trading platform for traders without programming knowledge.

Repo: git@gitlab.com:koval-group/koval-ai.git

## Purpose

Traders build strategies by connecting blocks in a visual editor — no code required. The engine executes strategies via backtesting, paper trading, or sandbox live trading on Binance and WhiteBIT.

Positioning: Android-like open platform. Choose your blocks, exchange, data source — everything is pluggable.

## Hard constraints

- Real account live trading (real money) is a future milestone — do not implement, enable, or assume it; only `paper` and `sandbox` modes are in scope
- Never silently delete backtest results, run history, or MongoDB documents
- Destructive operations must be behind explicit API checks and user confirmation
- Do not add features, refactor, or clean up beyond what was asked
- Do not create files unless necessary — prefer editing existing ones

## Git safety rule

- The agent must never create commits
- The agent must never push
- The agent must never rebase, merge, or rewrite history
- Only the user commits and performs all final git actions
- The agent prepares changes, runs verification, and suggests commit messages — then stops

## License split

- Core Koval (engine, blocks, strategy, API, dashboard) → **MIT**
- `koval/adapters/backtrader/` → **GPL-3.0** (Backtrader dependency)
- Every file in `koval/adapters/backtrader/` must have: `# SPDX-License-Identifier: GPL-3.0-or-later`

## Stack

### Backend / Engine
- Python 3.11+, Backtrader (execution engine), FastAPI (API)
- Strategies: `DeclarativeStrategy` subclasses in `koval/strategy/`
- Blocks: pure functions in `koval/blocks/` (signals, filters, exits, risk)
- Block assembler: `koval/strategy/block_assembler.py` — JSON graph → `DeclarativeStrategy` at runtime
- Exchange adapters: `koval/exchanges/` (Binance, WhiteBIT)
- Data: OHLCV via exchange adapters; cached in `data_cache/`

### UI
- React 18 + TypeScript + Vite
- MUI v5 (`@mui/material`) + Emotion for styling
- Charts: Plotly.js (main), Recharts (secondary)
- Block Builder canvas: react-flow (`@xyflow/react`)
- Tests: Vitest + `@testing-library/react`
- Dashboard served via Docker Compose: host `5174` → container `5173`
- Real-time log stream via WebSocket `/ws`

### Data / storage
- MongoDB (Compose service `mongo`, port `27017`)
- Repositories in `koval/db/`; in-process runtime state in `api/state.py`
- No config files — strategy/runtime config lives in MongoDB only

### Tooling
- Linting: Ruff (`pyproject.toml`) for Python, ESLint for frontend
- Tests: Pytest (`USE_MONGOMOCK=true python -m pytest -q`), Vitest (`npm run test -- --run`)
- Docker dev: `docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build --watch`

## Architecture rules

- Engine (`koval/engine/`, `koval/adapters/`) has no knowledge of API or dashboard — data flows one way: engine → services → API → UI
- ALL Backtrader-specific code lives in `koval/adapters/backtrader/` — strategies never import `backtrader` directly
- Blocks (`koval/blocks/`) are pure functions — no BT, no side effects, fully unit-testable
- Strategy config flows through `koval/strategy/registry.py` and `api/services/` — do not bypass with direct engine calls
- In-process runtime state lives in `api/state.py`; durable history in MongoDB — no hidden singletons
- API shapes defined in `api/models.py` — UI and engine stay in sync through these contracts
- `tools/` is never imported by runtime — one-off seed/utility scripts only

## Implementation principle: build like an onion

1. Core data structures (TradeSetup, StructureState dataclasses)
2. Pure business logic (blocks, DeclarativeStrategy)
3. BT adapter (BTStrategyAdapter — all BT code here)
4. Exchange adapters
5. Data access and persistence (repositories)
6. Service layer (backtest_service, live_service, result_mapper)
7. API layer (routers)
8. UI shell and integration
9. Hardening, verification, refinement

## Engineering rules

- **Strict TDD** — write tests before implementation, always; no exceptions for "simple" logic
- Critical calculation and state-transition logic must not be written without tests
- No schema changes without updating `agent_docs/system_architecture.md`
- No critical business-rule changes without updating docs and tests in the same work cycle
- Avoid hidden magic numbers — one source of truth per formula/threshold
- Optimize for a stable MVP, maintainable code, and minimal bugs
- Prefer explicitness and predictability over clever abstractions
- Do not add features, refactor, or clean up beyond what was asked
- No error handling for scenarios that cannot happen — trust internal guarantees

## Development workflow

For every non-trivial task:

1. **Plan** — write a clear plan, save to `docs/plans/YYYY-MM-DD-<task>.md`
2. **Tests first** — write tests before implementation; no exceptions
3. **Skeleton** — scaffold file/module/class structure with stubs before logic
4. **Build** — implement; DRY, KISS
5. **Polish** — replace stubs, remove dead code and magic numbers
6. **Verify** — run full test suite before claiming done
7. **Report** — what was built, what was documented, test results, known gaps

## Documentation discipline

| If a change affects... | Update... |
|------------------------|-----------|
| Global rules, workflow, stack, or agent discipline | `CLAUDE.md` |
| Architecture, module boundaries, data flow | `agent_docs/system_architecture.md` |
| API routes, request/response shapes | `PROJECT_STRUCTURE.md` |
| Engine or strategy behavior | relevant doc under `docs/` + `PROJECT_STRUCTURE.md` |
| Testing expectations or commands | `agent_docs/running_tests.md` |
| Docker, dev server, compose setup | `agent_docs/building_and_docker.md` |
| Code style, conventions, linting rules | `agent_docs/code_conventions.md` |
| UI/UX, design tokens, MUI/component patterns | `agent_docs/ui_design_system.md` |
| A meaningful bug, incident, or fix | `agent_docs/troubleshooting_known_issues.md` |
| Block library additions | `agent_docs/block_library.md` |
| Exchange adapter additions | `agent_docs/exchange_adapters.md` |

## Done checks

Before claiming a non-trivial task is done:
- [ ] Tests written first, passing now
- [ ] Relevant docs updated in the same work cycle
- [ ] No hidden architecture drift introduced
- [ ] `agent_docs/troubleshooting_known_issues.md` updated if a meaningful issue was found
- [ ] No git commit performed by the agent

## Authoritative docs

| Doc | Covers |
|-----|--------|
| `CLAUDE.md` | Root rules and constraints |
| `AGENTS.md` | Navigation index for all agent docs |
| `PROJECT_STRUCTURE.md` | Module map, API routes, data flow |
| `agent_docs/system_architecture.md` | Architecture, module boundaries, data flow |
| `agent_docs/running_tests.md` | Testing expectations and commands |
| `agent_docs/building_and_docker.md` | Docker, dev server, compose setup |
| `agent_docs/code_conventions.md` | Python + React/TS style and conventions |
| `agent_docs/ui_design_system.md` | UI/UX design system — tokens, layout, components |
| `agent_docs/block_library.md` | Available blocks, types, params, how to add new blocks |
| `agent_docs/exchange_adapters.md` | Exchange adapter interface, Binance, WhiteBIT |
| `agent_docs/troubleshooting_known_issues.md` | Failure memory, incidents, root causes |
| `docs/plans/` | Per-task execution plans |
