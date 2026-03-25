# Development Workflow

Follow these steps for every non-trivial task.

## 1. Plan

Write a clear, detailed implementation plan before touching code.
- Break the task into discrete steps.
- If the plan is non-trivial, save it to `docs/plans/` with a dated name (e.g. `2026-03-26-feature-name.md`).

## 2. Skeleton

Architect first, implement second.
- Create the file/module/class structure.
- Write function signatures with `pass` or minimal stubs.
- No real logic yet — just the shape.

## 3. Build Fast (Ugly Phase)

> Premature complexity is ego disguised as architecture.

- DRY, KISS. No over-engineering.
- Fake it till you make it: use stubs, hardcoded values, mocks where real integrations aren't proven yet.
- Get it working end-to-end before making it pretty.

## 4. Polish

Iterate until the MVP is solid and clean:
- Replace stubs with real logic.
- Remove dead code and magic numbers.
- Ensure error handling covers actual failure modes (not hypothetical ones).

## 5. Document

Every non-trivial step goes in `docs/`:
- Design rationale, trade-offs, formulas, math — deep dive.
- `file:line` pointers to authoritative code (no inline code copies that go stale).
- Update or create files under `docs/` — do not leave decisions undocumented.

## 6. Test

Coverage target: **≥ 95%**.

| Type        | Command                                                        |
|-------------|----------------------------------------------------------------|
| Backend     | `PYTHONPATH=. python -m pytest -q`                             |
| Frontend    | `cd web-dashboard && npm run test -- --run && npm run lint && npm run build` |
| E2E / live  | `RUN_LIVE_TESTS=1 python -m pytest -m live -q` (opt-in)       |

Run all three before claiming done. See [running_tests.md](running_tests.md) for details.

## 7. Report

Write a concise summary to the user in chat:
- What was built.
- What was documented and where.
- Test results (coverage, pass/fail count).
- Any known gaps or follow-up items.
