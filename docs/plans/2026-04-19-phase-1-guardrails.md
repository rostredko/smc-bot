# Phase 1 — Guardrails and baseline stabilization

Date: 2026-04-19
Scope: implement Phase 1 of `docs/TECHNICAL_DEBT_REPORT.md` (section 7). Covers
`TD-09` (strategy discovery diagnostics), `TD-10` (local toolchain
reproducibility), and the characterization-test portion of the Phase 1
guardrail work. `TD-11` (debt governance) is already satisfied by the
2026-04-19 refresh of the debt report itself.

This phase is deliberately non-structural: no route extraction, no runtime
registry, no strategy refactor. Goal is diagnostic clarity + verification
reproducibility + tests that freeze current behavior of the seams that later
phases will move.

## Constraints from `CLAUDE.md`

- Strict TDD: write tests before implementation
- No git operations performed by the agent
- Do not create files beyond what is necessary
- Update relevant docs in the same work cycle as code changes
- No schema changes without `agent_docs/system_architecture.md` updates
  (this phase makes none)

## Workstreams

### A. Strategy discovery diagnostics (`TD-09`)

**Problem.** `web-dashboard/services/strategy_runtime.py` lines 95–98 silently
swallow every `Exception` during strategy module import. A syntax error or
missing dependency in a strategy module causes it to disappear from
`/strategies` with no log trail.

**Plan.**

1. Add failing test in `tests/test_strategy_runtime_service.py` that:
   - writes a temporary `strategies/broken_probe_strategy.py` whose import
     raises at module load time
   - calls `discover_strategy_definitions()` under `caplog`
   - asserts discovery does not raise
   - asserts the broken module name + exception class appear in a `WARNING`
     record on the `backtrade.services.strategy_runtime` logger
2. Add module-level logger to `strategy_runtime.py`
   (`from engine.logger import get_logger; logger = get_logger(__name__)`).
3. Replace the silent `except Exception: continue` with a structured warning
   that records the module name plus exception class and message, then
   continues. Discovery must remain resilient.

**Outcome.** Broken strategy modules become diagnosable without destabilizing
the dashboard.

### B. Local toolchain reproducibility (`TD-10`)

**Problem.** Node runtime is named in prose only ("Node.js 18+") and not
pinned via a repo-level mechanism. Python invocation is inconsistent across
docs (`python -m pytest` vs. venv-local interpreter).

**Plan.**

1. Create `.nvmrc` at repo root with the single line `18` (matches CI Node 18
   in `.github/workflows/ci.yml`).
2. Add `"engines": { "node": ">=18" }` to `web-dashboard/package.json` so
   `npm install` warns on mismatch.
3. Update `README.md` local-dev section to reference `.nvmrc` and the
   canonical Python invocation via `./.venv/bin/python`.
4. Update `agent_docs/running_tests.md` with the canonical test invocation
   and a Node toolchain pointer.

**Outcome.** A developer checking out the repo can reproduce the CI-aligned
verification path without ambiguity.

### C. Characterization tests

**Problem.** The seams that Phase 2+ must move (config normalization, runtime
state restore payload shape) have coverage of individual units but not of the
contract they present to their callers. Refactor risk today is behavioral
drift nobody notices.

**Plan.**

1. New file `tests/test_runtime_contracts.py` covering:
   - **Config normalization parity** — assert that
     `build_runtime_strategy_config` applied to a representative config
     produces the same runtime-controls keys (`risk_per_trade`, `leverage`,
     `max_drawdown`, `trailing_stop_distance`, `breakeven_trigger_r`,
     `position_cap_adverse`, `funding_rate_per_8h`, `funding_interval_hours`,
     `detailed_signals`, `market_analysis`) regardless of whether the user
     supplies them at the top level or inside `strategy_config`.
   - **Runtime state restore payload shape** — assert that
     `GET /api/runtime/state` returns a stable envelope
     (`backtest`, `live`, `console` top-level keys with the documented
     sub-fields) when no run is active, because `BacktestProvider.tsx` and
     `RuntimeStateProvider.tsx` depend on this envelope.
   - **Strategy discovery under import failure** — already covered by
     Workstream A; the single-file location in this new test file would
     duplicate it, so it stays in `tests/test_strategy_runtime_service.py`.

Lifecycle start/stop coverage already exists in
`tests/test_live_api_controls.py` and `tests/test_api.py`; Phase 1 does not
rewrite it.

**Outcome.** Any Phase 2+ change that silently alters these contracts will
fail a targeted test.

## Target files

| File | Action |
|------|--------|
| `docs/plans/2026-04-19-phase-1-guardrails.md` | new (this file) |
| `tests/test_strategy_runtime_service.py` | extend with broken-module test |
| `web-dashboard/services/strategy_runtime.py` | add logger, replace silent except |
| `.nvmrc` | new, content `18` |
| `web-dashboard/package.json` | add `engines` field |
| `README.md` | update local-dev section |
| `agent_docs/running_tests.md` | add canonical invocation + Node pin note |
| `tests/test_runtime_contracts.py` | new characterization tests |

## Verification

- `./.venv/bin/python -m pytest -q` — full backend suite green
- targeted runs during development:
  - `./.venv/bin/python -m pytest tests/test_strategy_runtime_service.py -q`
  - `./.venv/bin/python -m pytest tests/test_runtime_contracts.py -q`
- no git actions performed by the agent

## Known non-goals for Phase 1

- no engine or strategy refactor
- no extraction from `server.py`
- no frontend change
- no new API routes
- no schema changes
