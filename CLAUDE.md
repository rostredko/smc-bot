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
- **Check session state on start:** run `git status` and `git log --oneline -10` before any task to understand current branch and recent work context

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
