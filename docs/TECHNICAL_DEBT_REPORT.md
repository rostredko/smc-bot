# Technical Debt Report

Current snapshot: 2026-03-25

This document records the current technical debt in `smc-bot` based on repository docs, code inspection, and a small verification slice. It is intentionally pragmatic: the goal is not to justify a rewrite, but to identify the highest-risk seams, explain why they are risky, and define a safe order for improvement.

## 1. Executive summary

The project is functional and has several good architectural decisions already in place:
- shared market-structure math is centralized in [`strategies/market_structure.py`](../strategies/market_structure.py)
- multi-timeframe feed ordering is centralized in [`engine/timeframe_utils.py`](../engine/timeframe_utils.py)
- API/storage payload shaping was already extracted into [`web-dashboard/services/result_mapper.py`](../web-dashboard/services/result_mapper.py)
- runtime strategy resolution was already extracted into [`web-dashboard/services/strategy_runtime.py`](../web-dashboard/services/strategy_runtime.py)
- backend regression coverage exists in critical areas under [`tests/`](../tests)

The highest current debt is not one specific bug. It is change amplification: a few large modules own too many responsibilities, and several runtime rules are duplicated across layers. That makes the system harder to change safely than it needs to be.

Current top priorities:
1. Reduce backend orchestration concentration in [`web-dashboard/server.py`](../web-dashboard/server.py)
2. Replace process-global runtime state with an explicit runtime registry abstraction
3. Unify configuration normalization and runtime config building across API and CLI paths
4. Decompose oversized trading-strategy logic into smaller pure units
5. Reduce frontend provider concentration and side-effect sprawl

## 2. Assessment method

This report is based on:
- primary onboarding docs: [`../CLAUDE.md`](../CLAUDE.md), [`../PROJECT_STRUCTURE.md`](../PROJECT_STRUCTURE.md)
- architecture and workflow docs under [`../agent_docs/`](../agent_docs)
- direct code inspection of the main runtime files
- targeted backend verification

Verification performed while preparing this report:
- `./.venv/bin/python -m pytest -q tests/test_strategy_runtime_service.py tests/test_result_mapper_service.py tests/test_api.py`
- result: `20 passed`

Frontend verification was attempted but blocked by local toolchain drift:
- repository and CI expect Node 18+
- current local runtime was Node 14
- Vitest failed before app tests ran

That toolchain mismatch is itself listed below as debt.

## 3. Priority scale

- `P1`: should be addressed before or during the next non-trivial architecture work in the affected area
- `P2`: important, but can follow once P1 seams are stabilized
- `P3`: watchlist / developer-experience debt; lower immediate product risk, but still worth fixing

## 4. Debt register

### TD-01. Oversized API and orchestration hub

- Priority: `P1`
- Area: backend architecture
- Primary files:
  - [`web-dashboard/server.py`](../web-dashboard/server.py)
  - [`web-dashboard/api/state.py`](../web-dashboard/api/state.py)
  - [`web-dashboard/services/result_mapper.py`](../web-dashboard/services/result_mapper.py)
  - [`web-dashboard/services/strategy_runtime.py`](../web-dashboard/services/strategy_runtime.py)

### Symptoms

[`web-dashboard/server.py`](../web-dashboard/server.py) is the FastAPI entrypoint, but it also owns:
- app lifespan and startup/shutdown
- config CRUD
- backtest/live lifecycle
- websocket broadcasting
- runtime state restoration
- optimization validation and heartbeat logic
- OHLCV caching
- indicator computation
- chart enrichment for trade details

This is the main backend hotspot. The file is large enough that unrelated changes can easily collide conceptually.

### Why it matters

- Small behavior changes become high-blast-radius edits.
- Route handlers are harder to unit test because they own orchestration details directly.
- Operational code and business logic are coupled in the same file.
- Future changes are more likely to create regressions in cancellation, cleanup, or persistence.

### Recommended remediation

Do not rewrite the backend. Extract responsibilities incrementally:

1. Introduce service modules for:
   - run coordination
   - live runner lifecycle
   - backtest runner lifecycle
   - OHLCV and chart-data computation
2. Keep [`web-dashboard/server.py`](../web-dashboard/server.py) as a composition root and route layer.
3. Move heavyweight helper functions out first, then move route orchestration second.

### Safe first step

Extract OHLCV/chart-data logic from [`web-dashboard/server.py`](../web-dashboard/server.py) into a dedicated service module without changing API contracts.

### TD-02. Process-global runtime state is the source of truth

- Priority: `P1`
- Area: runtime and operability
- Primary files:
  - [`web-dashboard/api/state.py`](../web-dashboard/api/state.py)
  - [`web-dashboard/server.py`](../web-dashboard/server.py)

### Symptoms

Runtime state is stored in module-level mutable globals:
- `running_backtests`
- `live_trading_state`
- `active_connections`
- `active_console_state`

For a single-process local app this is workable, but it bakes in assumptions about process model, startup order, and cleanup semantics.

### Why it matters

- Scaling to multiple workers is unsafe without redesign.
- Hot reload / restart behavior depends on implicit process memory.
- Concurrency bugs become harder to reason about because the state shape is informal and mutable from multiple call sites.
- Runtime coordination is harder to mock in tests.

### Recommended remediation

Create an explicit runtime registry abstraction:
- start with an in-memory implementation
- keep the public operations narrow: create run, update status, request stop, append console line, snapshot runtime
- isolate locking inside that abstraction

If the app ever needs multi-process runtime state, a Redis-backed adapter can be added later without rewriting route handlers.

### Safe first step

Wrap existing globals behind a `RuntimeRegistry` class and update routes/services to call the abstraction first, without changing storage behavior yet.

### TD-03. Configuration normalization is duplicated across entrypoints

- Priority: `P1`
- Area: contracts and runtime consistency
- Primary files:
  - [`web-dashboard/server.py`](../web-dashboard/server.py)
  - [`main.py`](../main.py)
  - [`web-dashboard/api/models.py`](../web-dashboard/api/models.py)
  - [`engine/execution_settings.py`](../engine/execution_settings.py)
  - [`web-dashboard/services/strategy_runtime.py`](../web-dashboard/services/strategy_runtime.py)

### Symptoms

The project currently has multiple places that normalize or rebuild runtime config:
- API-side live/backtest normalization in [`web-dashboard/server.py`](../web-dashboard/server.py)
- CLI-side normalization in [`main.py`](../main.py)
- fee/execution defaults in [`engine/execution_settings.py`](../engine/execution_settings.py)
- runtime strategy merge rules in [`web-dashboard/services/strategy_runtime.py`](../web-dashboard/services/strategy_runtime.py)

Each piece is individually understandable, but together they create drift risk.

### Why it matters

- API and CLI can diverge subtly in defaults or accepted shapes.
- Live and backtest code paths can interpret the same config differently.
- Adding a new config field becomes error-prone because there is no single canonical translation path.
- Regression tests have to defend the same behavior in more than one place.

### Recommended remediation

Create one canonical translator layer:
- external request shape -> normalized app config
- normalized app config -> engine config
- normalized app config -> strategy kwargs

Keep execution-mode and fee logic in [`engine/execution_settings.py`](../engine/execution_settings.py), but move request-shape translation into a single module shared by API and CLI.

### Safe first step

Extract current normalization code into one shared backend module and add characterization tests that assert API and CLI produce the same normalized output for the same input.

### TD-04. Trading logic is concentrated in very large strategy classes

- Priority: `P1`
- Area: domain logic and regression risk
- Primary files:
  - [`strategies/bt_price_action.py`](../strategies/bt_price_action.py)
  - [`strategies/base_strategy.py`](../strategies/base_strategy.py)
  - [`strategies/helpers/risk_manager.py`](../strategies/helpers/risk_manager.py)

### Symptoms

[`strategies/bt_price_action.py`](../strategies/bt_price_action.py) owns:
- HTF/LTF market-structure interpretation
- pattern detection
- filter decisions
- SL/TP logic
- entry arming/trigger windows
- narrative and metadata shaping

[`strategies/base_strategy.py`](../strategies/base_strategy.py) owns:
- order lifecycle
- OCO cleanup
- trailing stop and breakeven updates
- funding cashflow handling
- drawdown stop behavior

These are critical files with high behavioral density.

### Why it matters

- A small feature change can impact signal generation, risk, and order lifecycle at once.
- Pure logic is harder to test in isolation because much of it lives inside Backtrader strategy methods.
- Reading and reviewing the strategy requires carrying too much context at once.

### Recommended remediation

Decompose behavior into smaller units while preserving existing strategy behavior:
- pure signal evaluators
- pure structure/POI decision helpers
- pure stop/target builders
- trade lifecycle helpers for funding, trailing, breakeven, orphan cleanup

The Backtrader strategy class should remain the adapter that wires those pieces together, not the place where all rules live directly.

### Safe first step

Extract pure helper functions from [`strategies/bt_price_action.py`](../strategies/bt_price_action.py) first, backed by characterization tests using current known-good behavior.

### TD-05. Async/thread/process lifecycle is more complex than the API surface suggests

- Priority: `P1`
- Area: runtime lifecycle and cleanup
- Primary files:
  - [`web-dashboard/server.py`](../web-dashboard/server.py)
  - [`engine/bt_live_engine.py`](../engine/bt_live_engine.py)
  - [`engine/bt_backtest_engine.py`](../engine/bt_backtest_engine.py)
  - [`engine/logger.py`](../engine/logger.py)

### Symptoms

The runtime uses a combination of:
- FastAPI background tasks
- `asyncio` tasks
- `run_in_executor`
- threads and join/stop flows inside live engine code
- websocket log broadcasting
- manual attach/detach of run log handlers

This is manageable today, but it is easy for cleanup paths to become inconsistent.

### Why it matters

- Cancellation bugs are usually intermittent and hard to reproduce.
- Failure to detach handlers or clear runtime state can create ghost sessions or duplicated logs.
- Live/backtest lifecycle bugs tend to appear only under stop/restart/error paths, not happy paths.

### Recommended remediation

Define an explicit run lifecycle model:
- `created`
- `starting`
- `running`
- `stop_requested`
- `stopping`
- `completed`
- `failed`
- `cancelled`

Move cleanup into reusable runner objects so each run type has one owner for start/stop/finalize logic.

### Safe first step

Add a lifecycle-oriented integration test suite for stop/failure/restart behavior before extracting the runner implementation.

### TD-06. OHLCV API mixes transport, caching, compute, and chart enrichment

- Priority: `P2`
- Area: performance and separation of concerns
- Primary files:
  - [`web-dashboard/server.py`](../web-dashboard/server.py)
  - [`engine/data_loader.py`](../engine/data_loader.py)
  - [`strategies/market_structure.py`](../strategies/market_structure.py)

### Symptoms

The OHLCV area in [`web-dashboard/server.py`](../web-dashboard/server.py) handles:
- request parsing
- in-memory cache
- Mongo cache clearing
- indicator parameter normalization
- TA-Lib computation
- HTF/LTF structure alignment
- per-trade chart-data enrichment

The single-source-of-truth intent is good, but the compute path is too embedded in the HTTP layer.

### Why it matters

- Performance work is harder because the boundary between cache, compute, and response formatting is blurry.
- Large helper functions are difficult to reuse outside the endpoint that created them.
- Future chart or analytics features are likely to duplicate pieces of this logic unless extraction happens first.

### Recommended remediation

Split this area into:
- cache adapter
- OHLCV query service
- indicator/market-structure compute service
- chart-data enrichment service

Keep shared market-structure math in [`strategies/market_structure.py`](../strategies/market_structure.py); that part should remain the shared source of truth.

### Safe first step

Extract read-only compute helpers to a service module with no FastAPI imports.

### TD-07. Strategy discovery hides import failures

- Priority: `P2`
- Area: extensibility and diagnostics
- Primary file:
  - [`web-dashboard/services/strategy_runtime.py`](../web-dashboard/services/strategy_runtime.py)

### Symptoms

Strategy discovery catches `Exception` and silently skips modules that fail to import.

That keeps the dashboard resilient, but it also hides a class of breakages: a strategy can disappear from the UI without any obvious signal to the developer.

### Why it matters

- New strategy development becomes harder to debug.
- Broken imports can ship unnoticed if no one checks logs or strategy lists carefully.
- Silent failure is the wrong default for developer-facing discovery logic.

### Recommended remediation

Keep the dashboard from crashing, but surface the failure:
- log import errors with module name and traceback
- expose diagnostic metadata in a debug-only endpoint or admin log
- optionally show a partial warning when a configured strategy cannot be resolved cleanly

### Safe first step

Replace silent `continue` behavior with structured logging and test that import failures are visible.

### TD-08. Frontend provider layer concentrates too much state and side-effect logic

- Priority: `P2`
- Area: frontend maintainability
- Primary files:
  - [`web-dashboard/src/app/providers/config/ConfigProvider.tsx`](../web-dashboard/src/app/providers/config/ConfigProvider.tsx)
  - [`web-dashboard/src/app/providers/BacktestProvider.tsx`](../web-dashboard/src/app/providers/BacktestProvider.tsx)
  - [`web-dashboard/src/app/providers/results/ResultsProvider.tsx`](../web-dashboard/src/app/providers/results/ResultsProvider.tsx)
  - [`web-dashboard/src/app/providers/console/ConsoleProvider.tsx`](../web-dashboard/src/app/providers/console/ConsoleProvider.tsx)

### Symptoms

The provider split is better than a single global context, but `ConfigProvider` still owns many responsibilities:
- config loading
- strategy loading
- validation
- template CRUD and reorder
- run start/stop actions
- live status actions
- active tab and selected optimization variant

`BacktestProvider` also contains app-level orchestration for runtime restoration and polling.

### Why it matters

- The provider layer mixes domain intent, side effects, and UI state.
- UI behavior becomes harder to test because components depend on broad provider contracts.
- New dashboard features are likely to add more code to the same providers instead of to focused hooks/services.

### Recommended remediation

Refactor toward smaller focused hooks and command-style modules:
- config loading hook
- template management hook
- backtest command hook
- live command hook
- runtime restoration hook

This does not require a new state library immediately. The first goal is narrower responsibility boundaries.

### Safe first step

Extract API-calling logic from `ConfigProvider` into dedicated modules/hooks while keeping the current public provider API stable.

### TD-09. Persistence schema is tightly coupled to API response shape

- Priority: `P2`
- Area: storage evolution and backward compatibility
- Primary files:
  - [`db/repositories/backtest_repository.py`](../db/repositories/backtest_repository.py)
  - [`web-dashboard/services/result_mapper.py`](../web-dashboard/services/result_mapper.py)
  - [`web-dashboard/server.py`](../web-dashboard/server.py)

### Symptoms

Saved documents look very close to what the API returns to the frontend. This is simple and convenient, but it couples storage shape to presentation needs.

Examples:
- list/history projections depend on fields that are also display-facing
- normalization/backfill logic is performed during result retrieval
- optimization and live/backtest payloads share broad document structure with special-case flags

### Why it matters

- Evolving stored data safely becomes harder over time.
- Adding API fields can accidentally become a storage concern.
- Backfills and migration logic can spread into route handlers and repositories.

### Recommended remediation

Move toward explicit persistence versioning:
- add a document version field
- define stored-result schema separately from response schema
- serialize API responses from stored documents through dedicated mappers

### Safe first step

Introduce a `schema_version` field in persisted result documents and keep the current schema otherwise unchanged.

### TD-10. Local developer toolchain is not pinned tightly enough

- Priority: `P3`
- Area: developer experience and verification reliability
- Primary files:
  - [`README.md`](../README.md)
  - [`agent_docs/running_tests.md`](../agent_docs/running_tests.md)
  - [`.github/workflows/ci.yml`](../.github/workflows/ci.yml)
  - [`web-dashboard/package.json`](../web-dashboard/package.json)

### Symptoms

The repository docs and CI clearly expect modern runtimes, but local execution can still drift:
- frontend expects Node 18+
- CI uses Node 18
- local Node 14 caused Vitest to fail before app tests executed
- backend verification is documented with `python -m pytest`, but local environments may not expose `python` without using the project venv

### Why it matters

- Developers can get false-negative failures caused by tooling, not code.
- Verification becomes less trustworthy.
- Onboarding friction increases.

### Recommended remediation

Pin or automate the local toolchain:
- add `.nvmrc` or Volta config for Node
- document the canonical Python entrypoint more explicitly
- prefer one repo-level verification script for common checks
- keep Docker verification as the fallback path when local host tooling drifts

### Safe first step

Add explicit local runtime pins for Node and document the project venv as the default Python command path for local verification.

### TD-11. Documentation set contains historical analyses but no single current debt register

- Priority: `P3`
- Area: architecture communication
- Primary files:
  - [`docs/ENGINE_REVIEW.md`](ENGINE_REVIEW.md)
  - [`docs/ENGINE_STRATEGY_REVIEW_2026.md`](ENGINE_STRATEGY_REVIEW_2026.md)
  - [`docs/BT_PRICE_ACTION_AUDIT_20260307.md`](BT_PRICE_ACTION_AUDIT_20260307.md)

### Symptoms

The repository already has useful historical reviews and incident reports, but before this document there was no single current-state debt register that answered:
- what is still debt now
- what is already fixed
- what should be prioritized first

### Why it matters

- Historical docs are useful context, but they are not the same thing as a current execution plan.
- Future contributors can misread old issues as still-open issues.

### Recommended remediation

Keep historical docs for incident context, but use this file as the current debt register and update it when major debt items are resolved or reprioritized.

### Safe first step

Link this report from onboarding docs and update it after any non-trivial refactor affecting the listed areas.

## 5. Recommended execution order

The safest order is incremental:

### Phase 1. Guardrails and observability

- make strategy import failures visible
- pin local toolchain expectations
- keep this report current
- add lifecycle regression tests for stop/failure/restart paths

### Phase 2. Backend boundary cleanup

- extract config translation into one shared module
- wrap runtime globals in a registry abstraction
- move OHLCV/chart services out of [`web-dashboard/server.py`](../web-dashboard/server.py)

### Phase 3. Runtime orchestration extraction

- introduce dedicated runner/coordinator services for backtest and live flows
- keep route signatures and HTTP contracts stable
- reduce [`web-dashboard/server.py`](../web-dashboard/server.py) to routing/composition

### Phase 4. Domain and frontend decomposition

- extract pure helpers from strategy code
- split frontend provider responsibilities into smaller hooks/modules
- add storage versioning once service boundaries are cleaner

## 6. What should not be rewritten

The following decisions are currently useful and should be preserved unless there is a strong reason to change them:
- shared market-structure logic in [`strategies/market_structure.py`](../strategies/market_structure.py)
- LTF-first feed ordering in [`engine/timeframe_utils.py`](../engine/timeframe_utils.py)
- service extraction already done in [`web-dashboard/services/result_mapper.py`](../web-dashboard/services/result_mapper.py) and [`web-dashboard/services/strategy_runtime.py`](../web-dashboard/services/strategy_runtime.py)
- the existing regression-heavy backend test surface in [`tests/`](../tests)

The right path here is controlled extraction, not a full rewrite.
