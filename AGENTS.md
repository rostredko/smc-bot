# AGENTS.md — Backtrade Machine (`smc-bot`)

> Crypto backtesting and paper live trading research tool. Not a financial product.
> Primary strategy: `bt_price_action` — HTF market structure detection (4H) with LTF execution (1H).
> Full agent guide (Claude Code): [CLAUDE.md](CLAUDE.md)

---

## Hard constraints

- Real-money live trading is a planned future milestone — do not implement, enable, or assume it without explicit instruction; `execution_mode` defaults to `paper` until intentionally promoted
- Never silently delete backtest results, run history, or MongoDB documents
- Destructive operations (drop collection, delete run, reset state) must be behind explicit API checks and user confirmation
- Do not add features, refactor, or clean up beyond what was asked
- Do not create files unless necessary — prefer editing existing ones

## Git safety rule

- Never create commits
- Never push
- Never rebase, merge, or rewrite history
- Only the user commits and performs all final git actions
- Prepare changes, run verification, suggest commit messages — then stop

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

**Run frontend checks (from `web-dashboard/`):**
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

**Env vars for tests:** `USE_MONGOMOCK=true` (in-memory MongoDB). Copy `.env.example` → `.env` for local dev.

## Architecture rules

Data flows **one direction only**: `engine/` → `services/` → `api/` → UI

- `engine/` has no imports from `api/` or `web-dashboard/` — never cross this boundary
- Strategy config flows through `web-dashboard/services/strategy_runtime.py` — do not bypass with direct engine calls
- Results flow through `web-dashboard/services/result_mapper.py` — do not shape API/DB payloads inline
- In-process runtime state lives in `web-dashboard/api/state.py`; durable history in MongoDB — no hidden singletons
- `tools/` is never imported by runtime — one-off scripts only
- **`engine/bt_oco_patch.py` — do not remove or modify.** Patches Backtrader broker to prevent same-bar TP+SL double-fill (ghost trades). Applied in `base_engine.py` before Cerebro creation.

## Development workflow

1. **Plan** — write a plan to `docs/plans/YYYY-MM-DD-<task>.md` for non-trivial tasks
2. **Tests first** — write failing tests before implementation; no exceptions
3. **Skeleton** — scaffold structure with stubs before logic
4. **Build** — implement; DRY, KISS
5. **Polish** — replace stubs, remove dead code and magic numbers
6. **Verify** — run full test suite before claiming done
7. **Report** — what was built, docs updated, test results, known gaps

**Done checks:**
- [ ] Tests written first, passing now
- [ ] Relevant docs updated in the same work cycle
- [ ] No hidden architecture drift introduced
- [ ] `agent_docs/troubleshooting_known_issues.md` updated if a meaningful issue was found
- [ ] No git commit performed by the agent

## Code conventions (key rules)

- Strategies extend `BaseStrategy`, not Backtrader's `Strategy` directly
- Never read `self.data.close[0]` for a "future" value — use `[-N]` for confirmed bars
- LTF/HTF assignment: `self.datas[0]` = LTF, `self.datas[1]` = HTF — always, enforced by `ordered_timeframes()`
- No config files — strategy config loaded from MongoDB only
- MUI v5 `sx` prop for one-off styles; `styled()` only when reused across 2+ files
- Frontend layers (FSD): new features → `features/`; domain UI → `entities/`; API config → `shared/`
- Full conventions: [agent_docs/code_conventions.md](agent_docs/code_conventions.md)

## Stack

| Layer | Tech |
|-------|------|
| Engine | Python 3.11+, Backtrader, FastAPI |
| UI | React 18 + TypeScript + Vite + MUI v5 |
| Charts | Plotly.js (primary), Recharts (secondary) |
| DB | MongoDB via `db/repositories/` |
| Tests | Pytest (backend), Vitest + @testing-library/react (frontend) |
| Lint | Ruff (`pyproject.toml`), ESLint |

## Doc navigation

| Need | Read |
|------|------|
| Full rules, constraints, workflow | [CLAUDE.md](CLAUDE.md) |
| Module map, API routes, data flow | [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md) |
| Architecture, module boundaries, state, strategy params | [agent_docs/system_architecture.md](agent_docs/system_architecture.md) |
| API boundary vs services vs engine | [agent_docs/api_and_architecture.md](agent_docs/api_and_architecture.md) |
| Test commands, CI, coverage expectations | [agent_docs/running_tests.md](agent_docs/running_tests.md) |
| Docker, dev server, env vars | [agent_docs/building_and_docker.md](agent_docs/building_and_docker.md) |
| Development workflow detail | [agent_docs/development_workflow.md](agent_docs/development_workflow.md) |
| Python + React/TS conventions | [agent_docs/code_conventions.md](agent_docs/code_conventions.md) |
| Bugs, incidents, known issues | [agent_docs/troubleshooting_known_issues.md](agent_docs/troubleshooting_known_issues.md) |
| Backtest run modes (single/optimize/live) | [docs/BACKTEST_RUN_MODES.md](docs/BACKTEST_RUN_MODES.md) |
| Technical debt and refactor priorities | [docs/TECHNICAL_DEBT_REPORT.md](docs/TECHNICAL_DEBT_REPORT.md) |
