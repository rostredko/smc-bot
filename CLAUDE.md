# CLAUDE.md — Backtrade Machine (`smc-bot`)

## Purpose (WHY)

Crypto **backtesting** and **paper live** trading: Backtrader execution engine, FastAPI API, React (Vite) dashboard, MongoDB persistence. Primary strategy: `bt_price_action` (HTF market structure / LTF execution). This is research tooling—not trading advice.

## Stack & layout (WHAT)


| Area             | Role                                                       |
| ---------------- | ---------------------------------------------------------- |
| `engine/`        | Backtest/live engines, data load, analyzers, fees, WS feed |
| `strategies/`    | `BaseStrategy` subclasses; shared `market_structure.py`    |
| `web-dashboard/` | FastAPI `server.py`, `api/`, `services/`, React `src/`     |
| `db/`            | Mongo connection + repositories                            |
| `tests/`         | Pytest suite                                               |
| `main.py`        | CLI entry (backtest/live/test)                             |
| `tools/`         | One-off seed/utility scripts (not imported by runtime)     |


**Full module map, routes, and data flow:** [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md) (source of truth—prefer `file:line` pointers there over copying code here).

## How to work (HOW)

1. **Onboard by reading** [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md) when touching architecture, API, or persistence.
2. **Follow the development workflow** — [agent_docs/development_workflow.md](agent_docs/development_workflow.md).
3. **Progressive disclosure**—open only what matches the task under [agent_docs/](agent_docs/):
  - [agent_docs/building_and_docker.md](agent_docs/building_and_docker.md)
  - [agent_docs/running_tests.md](agent_docs/running_tests.md)
  - [agent_docs/api_and_architecture.md](agent_docs/api_and_architecture.md)
4. **Do not restate linter policy**—use **Ruff** (`pyproject.toml`) and **ESLint** in `web-dashboard/`. Fix issues with tools, not prose.
5. **Commit policy:** agents must not create, amend, or rewrite commits. Prepare changes and verification, but leave every commit to the user.

## Runtime & ports (local)

- API: `http://localhost:8000`
- Dashboard (Docker Compose): host `**5174`** → container `5173` (see `docker-compose.yml`)
- MongoDB: `27017` (Compose service `mongo`)

**Docker dev with hot reload (required for watch sync):**  
`docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build --watch`  
(or `./scripts/dev.sh` if you maintain it locally—`scripts/` may be gitignored).

## Reliability habits (12-factor-inspired)

- **Explicit state:** in-process state lives in `web-dashboard/api/state.py`; durable history in Mongo—avoid hidden singletons for “truth.”
- **Versioned contracts:** request/response shapes in `web-dashboard/api/models.py`; keep engine config and UI in sync via `web-dashboard/services/strategy_runtime.py` / `result_mapper.py`.
- **Observability:** logging via `engine/logger.py`; dashboard log stream uses `api/logging_handlers.py` and `WS /ws`—preserve attach/detach patterns when changing runs.
- **Safe defaults:** live path is **paper** (`execution_mode`); do not assume real-money execution exists.
- **Human gates:** destructive deletes and long optimize runs should stay behind existing API checks and user intent—not silent automation.

## Related docs

- [README.md](README.md) — install & commands
- [docs/BACKTEST_RUN_MODES.md](docs/BACKTEST_RUN_MODES.md) — `single` vs `optimize`
- [docs/TECHNICAL_DEBT_REPORT.md](docs/TECHNICAL_DEBT_REPORT.md) — current debt register and safe refactor order
- [AGENTS.md](AGENTS.md) — Cursor-oriented index
