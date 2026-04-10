# Code Conventions

Python and TypeScript/React conventions for this repo.

For linting config see `pyproject.toml` (Ruff) and `web-dashboard/.eslintrc.cjs` (ESLint).
Do not duplicate rule lists here — cross-link instead.

## Python

### Naming
- Modules and functions: `snake_case`
- Classes: `PascalCase`
- Constants: `UPPER_SNAKE_CASE`
- Private methods: `_leading_underscore`
- Test files: `test_<module>.py` under `tests/`

### Backtrader patterns
- Strategies extend `BaseStrategy` (`strategies/base_strategy.py`), not Backtrader's `Strategy` directly
- Indicator initialization goes in `__init__`, signal reading in `next()`
- Never read `self.data.close[0]` for a "future" value — use `[-N]` for confirmed bars
- Timeframe data: always use `self.data_ltf = self.datas[0]`, `self.data_htf = self.datas[1]` — order is guaranteed by `ordered_timeframes()`
- Magic numbers for thresholds (e.g. pivot span, ATR multiplier) must be strategy params, not inline literals

### General Python
- Prefer explicit `if x is None` over truthiness checks for objects that may be 0 or empty
- No bare `except:` — catch specific exceptions
- Logging: use `engine/logger.py` — do not create new loggers directly
- Config: no config files — strategy config loaded from MongoDB via repositories

### Ruff
Config in `pyproject.toml`. Run: `ruff check . && ruff format .`
Do not add `# noqa` suppressions without a comment explaining why.

## TypeScript / React

### Component structure
- One component per file, named identically to the file (`TradeList.tsx` exports `TradeList`)
- Props interface defined in the same file, named `<Component>Props`
- Keep components small — if a file exceeds ~200 lines, split by responsibility

### MUI v5
- Use MUI `sx` prop for one-off styles; extract to `styled()` only when reused across 2+ files
- Use MUI theme tokens (`theme.spacing`, `theme.palette`) — avoid hardcoded px/hex values
- Import from `@mui/material` not sub-paths unless tree-shaking requires it

### State and data
- API calls via `axios` (`axios` is the only HTTP client in deps)
- Component-local state: `useState`; shared/derived state: lift to parent or context
- Do not fetch data inside deeply nested components — fetch at page/panel level and pass down

### Charts
- Primary: Plotly.js (`react-plotly.js`) for backtest equity curves, trade scatter
- Secondary: Recharts for simpler bar/line charts
- Do not mix both libraries for the same data visualization

### Frontend layers (FSD)

The frontend follows a loose Feature-Sliced Design structure. Use this when placing new files:

| Layer | Path | What belongs here |
|-------|------|-------------------|
| `app/` | `src/app/` | App-level providers and context orchestration (`BacktestProvider`, etc.) |
| `pages/` | `src/pages/` | Top-level page compositions (`DashboardPage.tsx`) |
| `widgets/` | `src/widgets/` | Large self-contained UI blocks (config panel, console, results panel, history) |
| `features/` | `src/features/` | User-facing interactions with own logic (e.g. trade details modal) |
| `entities/` | `src/entities/` | Reusable domain-specific UI (e.g. `TradeAnalysisChart`, `TradeOHLCVChart`) |
| `shared/` | `src/shared/` | API config (`shared/api/config.ts`), shared types, generic utility UI |

Rules:
- Lower layers must not import from higher layers — `shared` cannot import from `widgets`
- New UI features go in `features/`; new reusable domain components in `entities/`; new API/type shared utilities in `shared/`

### Testing (Vitest)
- Test files: `*.test.tsx` or `*.test.ts` in same directory as the component
- Use `@testing-library/react` — prefer `getByRole` / `getByText` over `getByTestId`
- Mock API calls with `vi.mock` — do not let tests hit real HTTP endpoints

## Testing — Python (Pytest)

### Structure
- All tests under `tests/`
- One test file per module: `test_<module_name>.py`
- Group related tests in classes only when shared setup warrants it

### Conventions
- Test names: `test_<what>_<expected_outcome>` (e.g. `test_bos_up_when_close_above_last_sh`)
- Avoid testing implementation details — test observable behavior
- Use `conftest.py` fixtures for shared setup (MongoDB mock, strategy instances)
- MongoDB in tests: always set `USE_MONGOMOCK=true` unless the test is explicitly marked `@pytest.mark.live`

### What must have tests
- All market structure calculations (`market_structure.py`)
- All trade metric calculations (`trade_metrics.py`)
- All state transitions in strategies (entry/exit/filter logic)
- All result mapping in `result_mapper.py`
- All API endpoints (at least happy path + error path)

### TDD discipline
Write the failing test first. Run it to confirm it fails. Then implement. This is not optional.
