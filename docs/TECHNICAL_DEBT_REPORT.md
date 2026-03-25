# Technical Debt Report

Current snapshot: 2026-03-25

This document is the current technical debt register and execution roadmap for `smc-bot`. It is intentionally implementation-oriented: it records the main debt items, explains the underlying architectural causes, and lays out a safe five-phase plan to reduce risk without breaking working behavior.

This is not a rewrite proposal. The recommended path is controlled extraction, tighter boundaries, and stronger verification.

## 1. Executive summary

`smc-bot` already has several sound core decisions:
- shared market-structure logic is centralized in [`strategies/market_structure.py`](../strategies/market_structure.py)
- multi-timeframe ordering is centralized in [`engine/timeframe_utils.py`](../engine/timeframe_utils.py)
- runtime strategy discovery and result mapping have already been extracted into [`web-dashboard/services/strategy_runtime.py`](../web-dashboard/services/strategy_runtime.py) and [`web-dashboard/services/result_mapper.py`](../web-dashboard/services/result_mapper.py)
- the system has meaningful backend regression coverage under [`tests/`](../tests)

The main debt is not “bad code” in the abstract. The main debt is that several critical runtime seams are still too implicit:
- HTTP transport, orchestration, lifecycle, and analytics are overly concentrated in [`web-dashboard/server.py`](../web-dashboard/server.py)
- in-process globals are still the runtime source of truth
- config normalization and runtime translation are duplicated across API and CLI paths
- strategy and lifecycle logic are still too embedded in large framework-bound classes
- frontend side effects are concentrated in a few broad providers
- local verification is less reproducible than CI because the toolchain is not pinned tightly enough

The safest program is:
1. Add guardrails and characterization tests first
2. Extract shared translation and runtime seams second
3. Move orchestration out of the HTTP layer third
4. Decompose domain and persistence logic fourth
5. Finish with frontend boundary cleanup and full-stack hardening

## 2. Current baseline

### 2.1 Code hotspots

Current module sizes in the main hotspot areas:

| Module | Current size | Why it matters |
|--------|--------------|----------------|
| [`web-dashboard/server.py`](../web-dashboard/server.py) | 2476 lines | Concentrates routes, orchestration, lifecycle, OHLCV, cache, and chart enrichment |
| [`strategies/bt_price_action.py`](../strategies/bt_price_action.py) | 1287 lines | Concentrates signal logic, filters, SL/TP logic, trigger state, and metadata shaping |
| [`engine/bt_backtest_engine.py`](../engine/bt_backtest_engine.py) | 546 lines | Owns data loading, analyzers, metrics normalization, optimization, and forced close behavior |
| [`web-dashboard/src/app/providers/config/ConfigProvider.tsx`](../web-dashboard/src/app/providers/config/ConfigProvider.tsx) | 541 lines | Concentrates config loading, validation, persistence, and command side effects |
| [`strategies/base_strategy.py`](../strategies/base_strategy.py) | 436 lines | Concentrates order lifecycle, OCO, trailing, funding, and drawdown logic |
| [`engine/bt_live_engine.py`](../engine/bt_live_engine.py) | 232 lines | Lifecycle and threading surface for live-paper execution |
| [`web-dashboard/src/app/providers/BacktestProvider.tsx`](../web-dashboard/src/app/providers/BacktestProvider.tsx) | 193 lines | App-level orchestration and runtime restore/polling |

These sizes do not automatically mean the files are wrong. They do mean they have become the most expensive places to change safely.

### 2.2 Test surface

Current test inventory:

| Area | Count | Notes |
|------|-------|-------|
| Backend test files | 35 | Includes engine, API, lifecycle, mapping, repository, and strategy tests |
| Frontend test files | 11 | Covers providers, config/history/results widgets, and shared utilities |

Verification performed while preparing this report:
- `./.venv/bin/python -m pytest -q tests/test_strategy_runtime_service.py tests/test_result_mapper_service.py tests/test_api.py`
- result: `20 passed`

Frontend verification was attempted but blocked by local runtime drift:
- repo and CI expect Node 18+
- local runtime was Node 14
- Vitest failed before app tests ran

That mismatch is tracked below as debt because it reduces trust in local validation.

### 2.3 Existing constraints that must remain stable

The following behavior should be preserved during debt reduction:
- paper-live remains the safe default; no silent path to real-money execution
- API contracts remain backward-compatible unless explicitly versioned
- multi-timeframe feed ordering stays LTF-first
- shared market-structure math remains a single source of truth
- old persisted results remain readable
- route URLs and dashboard behavior stay stable during extraction phases

## 3. Refactor guardrails

The debt program should follow these rules:

1. Characterize before refactor.
   Add or tighten tests around current behavior before moving responsibilities.
2. Extract seams before changing semantics.
   Move code behind interfaces or service modules first; behavior changes come later if still needed.
3. Preserve contracts by default.
   HTTP shapes, persistence shapes, and strategy semantics should not drift accidentally.
4. Keep phase scope narrow.
   Each phase should be deployable independently.
5. Avoid “cleanup” edits outside the active seam.
   Large opportunistic rewrites will create more risk than they remove.

## 4. Debt register summary

| ID | Priority | Debt item | Main evidence | Target end state | Planned phase |
|----|----------|-----------|---------------|------------------|---------------|
| `TD-01` | `P1` | Backend orchestration is over-concentrated | [`web-dashboard/server.py`](../web-dashboard/server.py) owns routes, lifecycle, OHLCV, and helpers | `server.py` becomes composition/routing layer, orchestration moves into services/runners | Phase 3 |
| `TD-02` | `P1` | Runtime state is process-global and mutable | [`web-dashboard/api/state.py`](../web-dashboard/api/state.py) globals are runtime truth | explicit runtime registry abstraction with narrow API | Phase 2 |
| `TD-03` | `P1` | Config normalization is duplicated across entrypoints | [`main.py`](../main.py), [`web-dashboard/server.py`](../web-dashboard/server.py), [`engine/execution_settings.py`](../engine/execution_settings.py) | one canonical translation path from request/config -> runtime -> strategy kwargs | Phase 2 |
| `TD-04` | `P1` | Lifecycle ownership is too implicit | background tasks, executor calls, WS handlers, and thread cleanup are spread across modules | explicit runner lifecycle with stable states and cleanup ownership | Phase 3 |
| `TD-05` | `P1` | Trading logic is concentrated in oversized framework-bound classes | [`strategies/bt_price_action.py`](../strategies/bt_price_action.py), [`strategies/base_strategy.py`](../strategies/base_strategy.py) | smaller pure helpers and lifecycle helpers under thin Backtrader adapters | Phase 4 |
| `TD-06` | `P2` | OHLCV, cache, indicators, and chart enrichment are mixed into the HTTP layer | [`web-dashboard/server.py`](../web-dashboard/server.py), [`engine/data_loader.py`](../engine/data_loader.py) | dedicated analytics/query services with no FastAPI dependency | Phase 3 |
| `TD-07` | `P2` | Persistence schema is tightly coupled to response schema | [`db/repositories/backtest_repository.py`](../db/repositories/backtest_repository.py), [`web-dashboard/services/result_mapper.py`](../web-dashboard/services/result_mapper.py) | schema-versioned persistence and explicit storage-to-response mapping | Phase 4 |
| `TD-08` | `P2` | Frontend providers own too much side-effect logic | [`web-dashboard/src/app/providers/config/ConfigProvider.tsx`](../web-dashboard/src/app/providers/config/ConfigProvider.tsx), [`web-dashboard/src/app/providers/BacktestProvider.tsx`](../web-dashboard/src/app/providers/BacktestProvider.tsx) | smaller hooks/modules and narrower provider contracts | Phase 5 |
| `TD-09` | `P2` | Strategy discovery hides import failures | [`web-dashboard/services/strategy_runtime.py`](../web-dashboard/services/strategy_runtime.py) silently skips import errors | structured diagnostics with non-crashing failure visibility | Phase 1 |
| `TD-10` | `P3` | Toolchain and verification are not pinned tightly enough | local Node drift vs CI; Python command ambiguity | reproducible local verification path aligned with CI | Phase 1 and Phase 5 |
| `TD-11` | `P3` | Docs had historical reviews but no current execution register | historical reports existed, but no current roadmap | this file becomes the maintained source for debt status and order of work | Phase 1 |

## 5. Root-cause analysis by cluster

### 5.1 Boundary erosion around the backend HTTP layer

The backend already has the beginnings of layer separation:
- request/response models in [`web-dashboard/api/models.py`](../web-dashboard/api/models.py)
- runtime strategy logic in [`web-dashboard/services/strategy_runtime.py`](../web-dashboard/services/strategy_runtime.py)
- result mapping in [`web-dashboard/services/result_mapper.py`](../web-dashboard/services/result_mapper.py)

The problem is that these extracted services coexist with a still-overloaded HTTP entrypoint. As a result:
- route handlers still know too much about lifecycle internals
- helper functions stay in the route file because no dedicated seam exists yet
- cleanup paths are distributed instead of being owned by a run coordinator

This is why `server.py` is the first major backend refactor target.

### 5.2 Runtime ownership is implicit instead of explicit

The project currently assumes a single-process in-memory runtime. That is acceptable for local development, but the ownership model is weak:
- state is stored in globals
- mutation happens from multiple route/task call sites
- lifecycle transitions are conventions rather than a dedicated state machine or registry abstraction

This makes the system harder to reason about even before any scaling concerns.

### 5.3 Domain logic is still too embedded in framework objects

Backtrader strategies are the runtime integration point, but too much actual business logic still lives directly inside the strategy classes:
- signal evaluation
- trigger windows
- stop/target calculation
- trailing/breakeven rules
- funding application

That reduces the amount of logic that can be tested as pure functions and increases regression risk for any non-trivial strategy change.

### 5.4 Storage and API concerns are too close together

Persisted result documents are intentionally convenient for the dashboard, but the convenience comes with coupling:
- backfills happen during read paths
- response-facing fields influence persistence shape
- optimization and live/backtest documents reuse broad overlapping structures with flags and special cases

That is manageable now, but it will become expensive once the project needs cleaner migrations or more result types.

### 5.5 Frontend state ownership is too broad

The frontend is not in crisis, but it is drifting toward “provider as application service layer”:
- `ConfigProvider` owns multiple unrelated concerns
- `BacktestProvider` orchestrates restore and polling behavior
- UI state and transport state are co-located

That structure is workable for a single page, but it makes future UI changes more coupled than necessary.

### 5.6 Verification depends too much on local environment luck

The repository already documents the expected runtime, but local validation is still too easy to misconfigure:
- CI is authoritative
- Docker is reliable
- host-level local execution is not pinned tightly enough

That leads to noisy failures and weaker confidence in developer-side checks.

## 6. Phase dependency map

The five phases below are ordered by dependency, not by convenience.

| Phase | Main purpose | Depends on | Unlocks |
|-------|--------------|------------|---------|
| Phase 1 | Guardrails, observability, and baseline stabilization | none | safer refactors in all later phases |
| Phase 2 | Canonical runtime seams for config and state | Phase 1 characterization tests | safe extraction of orchestration out of `server.py` |
| Phase 3 | Backend orchestration extraction | Phases 1-2 | thinner HTTP layer, explicit runners, reusable OHLCV services |
| Phase 4 | Domain decomposition and persistence hardening | Phases 1-3 | lower regression risk in strategy changes and safer storage evolution |
| Phase 5 | Frontend boundary cleanup and full-stack hardening | Phases 1-4 | more maintainable UI state flow and reproducible end-to-end verification |

### Recommended sequencing rule

Do not start Phase 3 before Phase 2 is complete. Without a runtime registry seam and config translation seam, orchestration extraction will simply move complexity around instead of reducing it.

## 7. Five-phase implementation plan

## Phase 1. Guardrails and baseline stabilization

### Objective

Create the safety net that later refactors depend on:
- better diagnostics
- tighter verification expectations
- tests that characterize the current behavior of critical seams

### Debt items addressed

- `TD-09` strategy discovery hides import failures
- `TD-10` toolchain and verification drift
- `TD-11` missing current-state debt governance
- enables safe work on `TD-01` to `TD-08`

### Why this phase comes first

The current code already works. The highest short-term risk is not “bad design”; it is accidental behavior drift during refactoring. That is why Phase 1 focuses on characterization and observability rather than architecture changes.

### In scope

- make strategy import failures visible without crashing the dashboard
- pin and document the local verification toolchain
- add characterization tests for lifecycle, config translation, and key API behavior
- establish this debt report as the maintained source of prioritization

### Explicit non-goals

- no route extraction yet
- no runtime registry yet
- no strategy refactor yet

### Implementation workstreams

#### Workstream A. Strategy discovery diagnostics

Target files:
- [`web-dashboard/services/strategy_runtime.py`](../web-dashboard/services/strategy_runtime.py)
- [`tests/test_strategy_runtime_service.py`](../tests/test_strategy_runtime_service.py)

Planned changes:
1. Replace silent import skipping with structured logging that includes module name and exception summary.
2. Keep discovery resilient: a broken strategy should not take down `/strategies`.
3. Add tests that assert failure visibility and non-crashing behavior.

Expected outcome:
- broken strategy modules become diagnosable immediately
- dashboard resilience is preserved

#### Workstream B. Local toolchain reproducibility

Target files:
- [`README.md`](../README.md)
- [`agent_docs/running_tests.md`](../agent_docs/running_tests.md)
- [`web-dashboard/package.json`](../web-dashboard/package.json)
- optionally `.nvmrc` or equivalent runtime pin

Planned changes:
1. Pin Node runtime expectations explicitly for local development.
2. Document the canonical Python invocation through the project venv.
3. Add a repo-level verification shortcut or documented canonical check sequence.

Expected outcome:
- a developer can reproduce the CI-aligned local validation path with minimal ambiguity

#### Workstream C. Characterization tests

Target tests to add or extend:
- [`tests/test_api.py`](../tests/test_api.py)
- [`tests/test_live_api_controls.py`](../tests/test_live_api_controls.py)
- [`tests/test_strategy_runtime_service.py`](../tests/test_strategy_runtime_service.py)
- new `tests/test_runtime_contracts.py` or similar

Planned coverage:
1. config normalization parity expectations
2. start/stop lifecycle behavior for live and backtest entrypoints
3. runtime state restore payload shape
4. strategy discovery behavior under import failure

### Validation plan

Required:
- backend targeted tests pass
- local frontend test command is runnable under the pinned Node version
- manual smoke: `/strategies`, `/api/runtime/state`, start/stop endpoints still behave as before

### Exit criteria

- strategy discovery import failures are visible in logs or diagnostics
- local verification steps are documented and reproducible
- characterization tests exist for the seams that later phases will move

### Rollback strategy

Phase 1 is low-risk. If it causes noise or instability, revert diagnostics or tooling changes independently; do not block the roadmap on optional DX improvements.

## Phase 2. Canonical runtime seams for config and state

### Objective

Introduce the backend seams that the current architecture is missing:
- one canonical config translation path
- one runtime registry abstraction for mutable process state

### Debt items addressed

- `TD-02` process-global runtime state
- `TD-03` duplicated configuration normalization

### Why this phase comes second

Without these seams, any attempt to decompose [`web-dashboard/server.py`](../web-dashboard/server.py) will keep leaking state and translation logic into the extracted modules.

### In scope

- create a runtime registry abstraction with an in-memory implementation
- create a shared config translation module used by API and CLI
- replace direct mutation patterns with narrow method calls
- preserve all public HTTP and CLI contracts

### Explicit non-goals

- no route decomposition yet
- no storage schema change yet
- no strategy semantics changes

### Implementation workstreams

#### Workstream A. Runtime registry abstraction

Target files:
- new backend module, for example `web-dashboard/services/runtime_registry.py`
- [`web-dashboard/api/state.py`](../web-dashboard/api/state.py)
- [`web-dashboard/server.py`](../web-dashboard/server.py)

Planned changes:
1. Define narrow operations:
   - create/update/remove backtest runtime
   - start/update/stop live runtime
   - append/reset console output
   - snapshot active runtime state
2. Move locking and mutation into the registry implementation.
3. Keep initial storage in memory so behavior remains unchanged.
4. Replace direct global writes in route/task code with registry calls.

Expected outcome:
- state ownership becomes explicit
- later orchestration extraction can depend on a stable interface instead of globals

#### Workstream B. Config translation unification

Target files:
- new backend module, for example `web-dashboard/services/runtime_config.py`
- [`main.py`](../main.py)
- [`web-dashboard/server.py`](../web-dashboard/server.py)
- [`engine/execution_settings.py`](../engine/execution_settings.py)
- [`web-dashboard/services/strategy_runtime.py`](../web-dashboard/services/strategy_runtime.py)

Planned changes:
1. Separate three concepts clearly:
   - external request/config shape
   - normalized runtime config
   - strategy kwargs
2. Move request-shape translation into one shared module.
3. Keep exchange/fee normalization in [`engine/execution_settings.py`](../engine/execution_settings.py).
4. Update API and CLI paths to call the same translator.
5. Add parity tests for API-style and CLI-style inputs.

Expected outcome:
- new config fields have one authoritative translation path
- CLI and API stop drifting in defaults and shape handling

### Suggested new tests

- `tests/test_runtime_registry.py`
- `tests/test_runtime_config_translation.py`
- expand [`tests/test_main_cli_backtest.py`](../tests/test_main_cli_backtest.py)
- expand [`tests/test_api.py`](../tests/test_api.py)

### Validation plan

Required:
- existing API tests still pass
- new parity tests prove CLI/API normalization consistency
- runtime snapshot and stop behavior stay unchanged from the client perspective

### Exit criteria

- route/task code no longer needs to mutate runtime globals directly
- API and CLI use the same translation seam for normalization
- lifecycle state can be inspected through one registry abstraction

### Rollback strategy

Keep the first registry implementation in-memory and internal. If problems appear, revert call-site migration while preserving the characterization tests added in Phase 1.

## Phase 3. Backend orchestration extraction

### Objective

Reduce [`web-dashboard/server.py`](../web-dashboard/server.py) from an orchestration hub into a thinner transport/composition layer.

### Debt items addressed

- `TD-01` oversized backend orchestration hub
- `TD-04` implicit lifecycle ownership
- `TD-06` OHLCV/chart-data logic mixed into HTTP layer

### Why this phase comes after Phase 2

Once config translation and runtime state are explicit seams, orchestration can be moved safely without smuggling globals and ad-hoc normalization into each new module.

### In scope

- extract backtest and live runner/coordinator services
- centralize lifecycle transitions
- extract OHLCV/query/chart enrichment services out of the route file
- keep all route paths and response contracts stable

### Explicit non-goals

- no persistence schema versioning yet
- no strategy behavior refactor yet
- no frontend architectural change yet

### Implementation workstreams

#### Workstream A. Backtest and live coordinators

Target files:
- [`web-dashboard/server.py`](../web-dashboard/server.py)
- [`engine/bt_backtest_engine.py`](../engine/bt_backtest_engine.py)
- [`engine/bt_live_engine.py`](../engine/bt_live_engine.py)
- new modules such as:
  - `web-dashboard/services/backtest_runner.py`
  - `web-dashboard/services/live_runner.py`

Planned changes:
1. Define runner ownership for:
   - start
   - progress/status updates
   - stop request handling
   - finalize/save/cleanup
2. Introduce explicit lifecycle statuses and transition rules.
3. Keep route handlers thin: validate input, call service, return response.
4. Centralize log-handler attach/detach ownership in the runner layer.

Expected outcome:
- cleanup paths live in one place per run type
- route handlers stop knowing internal lifecycle mechanics

#### Workstream B. OHLCV and chart-data services

Target files:
- [`web-dashboard/server.py`](../web-dashboard/server.py)
- [`engine/data_loader.py`](../engine/data_loader.py)
- [`strategies/market_structure.py`](../strategies/market_structure.py)
- new modules such as:
  - `web-dashboard/services/ohlcv_service.py`
  - `web-dashboard/services/chart_data_service.py`

Planned changes:
1. Extract cache access into a dedicated adapter or helper module.
2. Extract indicator computation and market-structure shaping into pure service functions.
3. Extract trade chart-data enrichment into a dedicated service that can be tested without FastAPI.
4. Keep shared market-structure math in [`strategies/market_structure.py`](../strategies/market_structure.py).

Expected outcome:
- HTTP layer stops owning analytics-heavy helper logic
- compute and cache boundaries become explicit

### Suggested new tests

- `tests/test_backtest_runner.py`
- `tests/test_live_runner.py`
- `tests/test_ohlcv_service.py`
- expand [`tests/test_live_api_controls.py`](../tests/test_live_api_controls.py)
- expand [`tests/test_result_backfill.py`](../tests/test_result_backfill.py)

### Validation plan

Required:
- lifecycle start/stop/fail/restart behavior remains stable
- OHLCV endpoint returns the same contract as before
- runtime restore still works after page reload

Manual smoke checks:
- start backtest
- cancel active backtest
- start live paper session
- stop live paper session
- fetch OHLCV with indicators
- inspect history/results after completion

### Exit criteria

- [`web-dashboard/server.py`](../web-dashboard/server.py) no longer owns the core execution lifecycle logic directly
- OHLCV/chart-data code is testable outside the route module
- lifecycle cleanup is centralized in runner services

### Rollback strategy

Do not extract all routes at once. Migrate one vertical slice at a time:
1. one backtest path
2. one live path
3. one OHLCV path

If a slice regresses, revert only that slice while preserving the new seam interfaces.

## Phase 4. Domain decomposition and persistence hardening

### Objective

Reduce change risk in the most business-critical logic:
- strategy decision flow
- order lifecycle helpers
- persisted result shape evolution

### Debt items addressed

- `TD-05` oversized domain/framework classes
- `TD-07` persistence tightly coupled to response shape

### Why this phase comes after backend extraction

Domain refactors are safer once orchestration and transport code are already cleaner. Otherwise domain changes and transport changes will overlap in the same diff and become hard to isolate.

### In scope

- extract pure helper modules from strategy logic
- extract lifecycle helpers from base strategy where practical
- introduce persistence schema versioning
- keep old stored documents readable

### Explicit non-goals

- no signal logic redesign
- no strategy performance optimization project
- no real-trading rollout

### Implementation workstreams

#### Workstream A. Strategy logic extraction

Target files:
- [`strategies/bt_price_action.py`](../strategies/bt_price_action.py)
- [`strategies/base_strategy.py`](../strategies/base_strategy.py)
- new helper modules under `strategies/helpers/`

Planned changes:
1. Identify pure decision points that do not require direct Backtrader mutation.
2. Extract them into pure helpers in the following order:
   - structure/POI evaluation helpers
   - signal and filter decision helpers
   - stop/target calculation helpers
   - trailing and breakeven calculation helpers
3. Keep Backtrader strategy classes as adapters that call these helpers.
4. Preserve outputs and semantics through characterization tests.

Expected outcome:
- critical trading behavior becomes more testable
- strategy changes stop requiring giant review surfaces

#### Workstream B. Persistence versioning and mapping

Target files:
- [`db/repositories/backtest_repository.py`](../db/repositories/backtest_repository.py)
- [`web-dashboard/services/result_mapper.py`](../web-dashboard/services/result_mapper.py)
- [`web-dashboard/server.py`](../web-dashboard/server.py)

Planned changes:
1. Introduce `schema_version` for persisted result documents.
2. Separate storage representation from response representation conceptually.
3. Keep legacy backfill behavior, but move it behind version-aware mapping code.
4. Avoid breaking old documents already stored in Mongo.

Expected outcome:
- stored documents can evolve more safely
- API fields stop directly dictating persistence layout

### Suggested new tests

- expand [`tests/test_price_action_extended.py`](../tests/test_price_action_extended.py)
- expand [`tests/test_base_strategy_notify_order.py`](../tests/test_base_strategy_notify_order.py)
- expand [`tests/test_result_mapper_service.py`](../tests/test_result_mapper_service.py)
- expand [`tests/test_optimize_save_single_parity.py`](../tests/test_optimize_save_single_parity.py)
- add `tests/test_persistence_schema_versioning.py`

### Validation plan

Required:
- strategy characterization tests still pass
- optimize/save parity still holds
- old persisted result docs still load correctly
- new persisted docs include schema version

Manual smoke checks:
- load old history item
- save new backtest result
- save live-paper result
- open trade details and verify expected fields still exist

### Exit criteria

- core strategy decisions are testable in smaller pure units
- persisted result format has explicit versioning
- backward-compatible document loading is proven by tests

### Rollback strategy

Keep extracted helper modules additive at first. The first refactor step should route existing code through helpers without changing control flow. Only after tests prove parity should dead inline code be removed.

## Phase 5. Frontend boundary cleanup and full-stack hardening

### Objective

Complete the debt program by making the dashboard easier to change and the full-stack verification path easier to trust.

### Debt items addressed

- `TD-08` oversized frontend provider responsibilities
- completes `TD-10` local verification reproducibility
- reinforces `TD-11` debt-governance discipline

### Why this phase comes last

The frontend consumes the backend contracts. It is safer to clean up frontend boundaries after the backend seams and persistence rules have stabilized.

### In scope

- split broad provider responsibilities into narrower hooks or modules
- isolate API command code from provider state
- tighten frontend verification and runtime pinning
- add full-stack smoke guidance aligned with the new backend boundaries

### Explicit non-goals

- no new state-management library by default
- no redesign of dashboard UX
- no component-library migration

### Implementation workstreams

#### Workstream A. Provider decomposition

Target files:
- [`web-dashboard/src/app/providers/config/ConfigProvider.tsx`](../web-dashboard/src/app/providers/config/ConfigProvider.tsx)
- [`web-dashboard/src/app/providers/BacktestProvider.tsx`](../web-dashboard/src/app/providers/BacktestProvider.tsx)
- [`web-dashboard/src/app/providers/results/ResultsProvider.tsx`](../web-dashboard/src/app/providers/results/ResultsProvider.tsx)
- [`web-dashboard/src/app/providers/console/ConsoleProvider.tsx`](../web-dashboard/src/app/providers/console/ConsoleProvider.tsx)

Planned changes:
1. Extract API commands into focused modules or hooks:
   - config load/save
   - template CRUD/reorder
   - backtest commands
   - live commands
   - runtime restore
2. Keep provider public APIs stable initially.
3. Shrink providers into state containers and orchestration wrappers, not transport layers.

Expected outcome:
- frontend changes affect smaller files and narrower contracts
- provider tests become simpler and more targeted

#### Workstream B. Full-stack verification hardening

Target files:
- [`README.md`](../README.md)
- [`agent_docs/running_tests.md`](../agent_docs/running_tests.md)
- frontend test/build scripts if needed

Planned changes:
1. Finalize local toolchain pinning if not completed in Phase 1.
2. Document a canonical full-stack verification sequence:
   - backend tests
   - frontend tests/lint/build
   - docker/dev runtime smoke path
3. Add or document one repeatable smoke checklist for dashboard runtime behaviors.

Expected outcome:
- frontend verification is reproducible
- full-stack smoke testing is consistent across contributors

### Suggested new tests

- expand [`web-dashboard/src/app/providers/BacktestProvider.test.tsx`](../web-dashboard/src/app/providers/BacktestProvider.test.tsx)
- expand [`web-dashboard/src/app/providers/config/ConfigProvider.test.tsx`](../web-dashboard/src/app/providers/config/ConfigProvider.test.tsx)
- expand [`web-dashboard/src/widgets/results-panel/ui/ResultsPanel.test.tsx`](../web-dashboard/src/widgets/results-panel/ui/ResultsPanel.test.tsx)
- expand [`web-dashboard/src/widgets/backtest-history/ui/BacktestHistoryList.test.tsx`](../web-dashboard/src/widgets/backtest-history/ui/BacktestHistoryList.test.tsx)

### Validation plan

Required:
- frontend unit tests pass under the pinned Node version
- `npm run lint` passes
- `npm run build` passes
- dashboard still restores runtime state, logs, and results as before

Manual smoke checks:
- load dashboard
- switch between backtest/live tabs
- restore active runtime after page reload
- open history and result details
- verify console reconnect behavior

### Exit criteria

- provider modules have narrower responsibilities
- frontend verification is reproducible on the documented runtime
- dashboard behavior remains stable under the post-refactor backend contracts

### Rollback strategy

Keep provider API contracts stable while extracting hooks/modules. If a frontend refactor regresses behavior, revert the hook extraction without undoing earlier backend debt reduction phases.

## 8. Cross-phase verification matrix

Each phase should finish with both targeted and regression checks.

| Layer | Minimum verification after phase work |
|-------|--------------------------------------|
| Backend services | targeted pytest modules for the changed seam |
| API contracts | existing API regression tests plus new characterization tests |
| Engine/strategy logic | strategy and metrics parity tests where relevant |
| Frontend | targeted Vitest tests for touched providers/widgets |
| Build integrity | frontend build and backend import sanity |
| Runtime smoke | start/stop/reload behavior for backtest and live-paper |

Recommended recurring commands:
- backend targeted tests via `./.venv/bin/python -m pytest -q ...`
- full backend suite from repo root
- frontend tests/lint/build from [`web-dashboard/`](../web-dashboard)
- Docker smoke path when host toolchains are questionable

## 9. Suggested execution model

### If one engineer is doing the work

Follow the phases strictly in order. Do not overlap Phase 3 and Phase 4.

### If a small team is doing the work

Allowed parallelism:
- during Phase 1: toolchain pinning can run in parallel with characterization tests
- during Phase 2: runtime registry and config translation can be developed in parallel if they converge before route migration
- during Phase 5: frontend provider decomposition and documentation hardening can run in parallel

Not recommended in parallel:
- Phase 3 orchestration extraction and Phase 4 domain decomposition
- backend contract changes and frontend provider changes without a stable contract checkpoint

## 10. Definition of success

This debt program is successful when all of the following are true:
- `server.py` is no longer the primary home of orchestration logic
- runtime state has an explicit ownership abstraction
- API and CLI use the same config translation seam
- trading logic is more testable as pure units than it is today
- persistence format can evolve without coupling every change to API response shape
- frontend provider changes no longer require editing one or two giant modules
- local validation is aligned with CI and reproducible

## 11. What should not be rewritten

The following decisions are currently valuable and should be preserved unless there is a strong, tested reason to change them:
- shared market-structure logic in [`strategies/market_structure.py`](../strategies/market_structure.py)
- LTF-first timeframe ordering in [`engine/timeframe_utils.py`](../engine/timeframe_utils.py)
- service extraction already done in [`web-dashboard/services/result_mapper.py`](../web-dashboard/services/result_mapper.py) and [`web-dashboard/services/strategy_runtime.py`](../web-dashboard/services/strategy_runtime.py)
- the current regression-heavy backend test surface in [`tests/`](../tests)
- the safety posture that live mode remains paper-only by default

The right strategy for this codebase is not “rewrite the platform”. The right strategy is to keep the working core, tighten the seams, and make the next change cheaper and safer than the last one.
