# Development Workflow — Koval

## Session start checklist

```bash
git status
git log --oneline -10
```

Always understand the current branch and recent work before starting.

## Workflow for every non-trivial task

1. **Plan** — write to `docs/plans/YYYY-MM-DD-<task>.md`
2. **Tests first** — write failing tests before any implementation
3. **Skeleton** — scaffold file structure with stubs
4. **Build** — implement; DRY, KISS
5. **Polish** — remove dead code, magic numbers, stubs
6. **Verify** — run full test suite
7. **Report** — what was built, docs updated, test results, known gaps

## Phase execution

Koval is built in 10 phases. See: `docs/superpowers/plans/2026-05-01-koval-migration.md`

For phases 3+, create a detailed sub-plan before executing:
```
docs/plans/YYYY-MM-DD-koval-phase-N-<name>.md
```

## Branching

- `main` — stable, deployable
- `feature/<name>` — feature work
- Never force-push to `main`

## Commit convention

```
feat: add BTStrategyAdapter factory function
fix: correct OCO order cancellation on same-bar fill
chore: add pyproject.toml and Docker config
docs: update block_library.md with MACD block
test: add integration test for full backtest pipeline
```

## Before claiming a task done

```bash
USE_MONGOMOCK=true python -m pytest -q    # must pass
ruff check .                              # must pass
cd dashboard && npm run build             # must pass (0 TS errors)
```
