# Running Tests — Koval

## Backend (Pytest)

```bash
# From repo root — always use mongomock for tests
USE_MONGOMOCK=true python -m pytest -q

# Specific test file
USE_MONGOMOCK=true python -m pytest tests/strategy/test_bt_adapter.py -v

# With coverage
USE_MONGOMOCK=true python -m pytest --cov=koval --cov=api -q
```

## Frontend (Vitest)

```bash
cd dashboard
npm run test -- --run       # single run, no watch
npm run test                # watch mode
npm run lint                # ESLint
npm run build               # TypeScript compile check
```

## Linting (Python)

```bash
ruff check .
ruff format .
```

## Test architecture expectations

- **Unit tests** for all block functions (`koval/blocks/**`) — pure functions, no fixtures needed
- **Unit tests** for `DeclarativeStrategy` subclasses — no BT, inject state manually
- **Integration tests** for `BTStrategyAdapter` — run with synthetic BT data via Pandas feed
- **Integration tests** for API endpoints — use `httpx.AsyncClient` + `mongomock`
- **Exchange adapter tests** — mock HTTP with `responses` or `pytest-httpx`

## Test file conventions

| What you're testing | Where |
|--------------------|-------|
| `koval/engine/` | `tests/engine/` |
| `koval/strategy/base/` | `tests/strategy/` |
| `koval/blocks/` | `tests/blocks/` |
| `koval/exchanges/` | `tests/exchanges/` |
| `api/routers/` | `tests/api/` |

## Mandatory passing before claiming done

```bash
USE_MONGOMOCK=true python -m pytest -q    # 0 failures
ruff check .                              # 0 errors
cd dashboard && npm run build             # 0 TypeScript errors
```

## TA-Lib note

TA-Lib requires the C library installed. In Docker it's installed via `apt-get install libta-lib-dev`. Locally: `brew install ta-lib` (macOS) or `apt install libta-lib-dev` (Linux).

Tests that require TA-Lib should import defensively:
```python
try:
    import talib
    HAS_TALIB = True
except ImportError:
    HAS_TALIB = False

@pytest.mark.skipif(not HAS_TALIB, reason="TA-Lib not installed")
def test_rsi_block():
    ...
```
