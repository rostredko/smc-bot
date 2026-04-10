# Design: CLAUDE.md + AGENTS.md Restructure

**Date:** 2026-04-10  
**Status:** Approved for implementation

## Goal

Replace the current lean CLAUDE.md/AGENTS.md with a full governance structure for iterative, stable development. Establish strict TDD discipline, explicit documentation triggers, and clear agent constraints — while keeping all changes grounded in the actual project state.

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| New docs scope | Selective (3 new files) | Only create docs with real content now; avoid empty stubs |
| Doc storage | Committed to git | Existing pattern; all agent docs are public and versioned |
| TDD discipline | Strict — tests first, always | Research tool where calculation bugs are the most expensive |
| Doc discipline | Explicit per-doc triggers | Prevents drift; each change maps to a specific file to update |
| Onion direction | Inside-out | Aligns with TDD; core value is in engine/strategies, not UI |
| agent_docs naming | Keep `agent_docs/` | No migration pain; no broken references |

## CLAUDE.md — Target Section Structure

1. `## Project` — one-liner
2. `## Purpose` — WHY, what it does
3. `## Hard constraints` — what the agent must never do
4. `## Git safety rule` — commit/push/rebase rules
5. `## Stack and technologies` — Backend/Engine, UI, Data/storage, Tooling
6. `## Architecture rules` — key boundaries and data flow
7. `## Implementation principle: build like an onion` — inside-out layered approach
8. `## Engineering rules` — TDD, no magic numbers, explicit over clever
9. `## 12-factor agent rules for this repo` — adapted for this stack
10. `## Documentation discipline` — per-doc update trigger table
11. `## Development workflow` — Plan → Tests → Skeleton → Build → Polish → Verify → Report
12. `## Authoritative docs` — index table
13. `## Done checks` — checklist before claiming done
14. `## Troubleshooting memory` — pointer + format

## AGENTS.md — Target Structure

Navigation index pointing to CLAUDE.md as primary, then listing all agent docs with one-line descriptions of what each covers.

## New Files to Create

### `agent_docs/system_architecture.md`
- Engine/API/dashboard boundaries
- Data flow: engine → services → API → UI
- Key modules and their responsibilities
- State management: in-process (`state.py`) vs durable (MongoDB)

### `agent_docs/code_conventions.md`
- Python: Ruff rules, Backtrader patterns, naming conventions
- TypeScript/React: MUI v5 patterns, component structure
- Testing conventions: Pytest patterns, Vitest patterns

### `agent_docs/troubleshooting_known_issues.md`
- Seeded from existing incident docs (SELL_THE_BOTTOM_INCIDENT_ANALYSIS.md, BOS_MODULE_VERIFICATION_REPORT.md, MTF_SYNC_VERIFICATION_REPORT.md)
- Format: date, title, context, symptoms, root cause, resolution, prevention

## Key Adaptations from Template

- No `product_requirements.md` — research tool, not a product with stakeholders
- No `ci_cd_deployment.md` — Docker Compose dev is covered in `building_and_docker.md`
- No `data_integrity_source_of_truth.md` — not a financial ledger with strict backup policy
- No TypeScript/MUI/FSD dedicated conventions file — covered in `code_conventions.md` alongside Python
- No gitignored docs — all committed
- `agents_docs/` → `agent_docs/` throughout
- Real-money trading constraint: planned future milestone, not a permanent prohibition

## Hard Constraints (final)

- Real-money live trading is a planned future milestone — do not implement, enable, or assume it without explicit instruction; `execution_mode` defaults to `paper` until intentionally promoted
- Never silently delete backtest results, run history, or MongoDB documents
- Destructive operations must be behind explicit API checks and user confirmation
- Do not add features, refactor, or clean up beyond what was asked
- Do not create files unless necessary — prefer editing existing ones

## Onion Principle (inside-out)

1. Core domain model and data structures
2. Pure business logic (strategies, calculations, analyzers)
3. Data access and persistence (repositories, DB schema)
4. Service layer and shared contracts
5. API layer
6. UI shell and integration
7. Hardening, verification, and refinement

## Documentation Discipline Triggers

| If a change affects... | Update... |
|------------------------|-----------|
| Global rules, workflow, stack, agent discipline | `CLAUDE.md` |
| Architecture, module boundaries, data flow | `agent_docs/system_architecture.md` |
| API routes, request/response shapes | `PROJECT_STRUCTURE.md` |
| Engine or strategy behavior | `docs/` (relevant doc) + `PROJECT_STRUCTURE.md` |
| Testing expectations or commands | `agent_docs/running_tests.md` |
| Docker, dev server, compose setup | `agent_docs/building_and_docker.md` |
| Code style, conventions, linting rules | `agent_docs/code_conventions.md` |
| A meaningful bug, incident, or fix | `agent_docs/troubleshooting_known_issues.md` |
| Run modes (single/optimize/live) | `docs/BACKTEST_RUN_MODES.md` |
| Technical debt or refactor priorities | `docs/TECHNICAL_DEBT_REPORT.md` |
