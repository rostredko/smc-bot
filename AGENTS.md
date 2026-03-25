# AGENTS.md

Use **[CLAUDE.md](CLAUDE.md)** as the primary onboarding file for coding agents (project purpose, stack, workflow, verification). It follows progressive disclosure: deep detail lives in linked docs, not duplicated inline.

| Need | Read |
|------|------|
| Directory map, API list, DB model, test matrix | [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md) |
| Docker / dev server / compose | [agent_docs/building_and_docker.md](agent_docs/building_and_docker.md) |
| Pytest / npm checks / CI expectations | [agent_docs/running_tests.md](agent_docs/running_tests.md) |
| API boundary vs services vs engine | [agent_docs/api_and_architecture.md](agent_docs/api_and_architecture.md) |
| Backtest `run_mode` | [docs/BACKTEST_RUN_MODES.md](docs/BACKTEST_RUN_MODES.md) |
| Current technical debt and refactor priorities | [docs/TECHNICAL_DEBT_REPORT.md](docs/TECHNICAL_DEBT_REPORT.md) |

**Rules of engagement:** match existing patterns in the touched layer; run linters/tests rather than hand-auditing style; keep diffs minimal and scoped to the request. Editor-specific rules may appear under `.cursor/rules` in your environment—follow them when present.
