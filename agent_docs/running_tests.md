# Running tests & quality checks

## Backend (pytest)

From **repository root**:

```bash
python -m pytest -q
```

If imports fail, ensure `PYTHONPATH` includes the repo root (CI sets `PYTHONPATH=.:$PYTHONPATH`).

### Optional markers

- Live E2E (internet, opt-in): `RUN_LIVE_TESTS=1 python -m pytest -m live -q`

### Mongo in tests

`USE_MONGOMOCK=true` uses in-memory Mongo for tests—see [README.md](../README.md) and `db/connection.py`.

## Frontend

```bash
cd web-dashboard
npm run test -- --run
npm run lint
npm run build
```

## CI

GitHub Actions: [.github/workflows/ci.yml](../.github/workflows/ci.yml) — frontend lint+build (Node 18), backend pytest (Python 3.10).

## Ruff (Python)

Config: [pyproject.toml](../pyproject.toml). Run `ruff check .` / `ruff format .` if installed—do not duplicate rule lists in prose.
