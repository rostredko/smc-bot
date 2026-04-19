# Running tests & quality checks

## Backend (pytest)

From **repository root**, using the project venv explicitly:

```bash
./.venv/bin/python -m pytest -q
```

Plain `python -m pytest -q` also works when the venv is activated; the explicit
`./.venv/bin/python` form is the canonical invocation and avoids ambiguity
about which interpreter is in scope.

If imports fail, ensure `PYTHONPATH` includes the repo root (CI sets `PYTHONPATH=.:$PYTHONPATH`).

### Optional markers

- Live E2E (internet, opt-in): `RUN_LIVE_TESTS=1 python -m pytest -m live -q`

### Mongo in tests

`USE_MONGOMOCK=true` uses in-memory Mongo for tests—see [README.md](../README.md) and `db/connection.py`.

## Frontend

Node runtime is pinned to major version `18` via [`.nvmrc`](../.nvmrc). Use
`nvm use` before running the frontend checks to match CI:

```bash
cd web-dashboard
nvm use
npm run test -- --run
npm run lint
npm run build
```

`web-dashboard/package.json` also declares `"engines": { "node": ">=18" }`;
`npm install` warns on mismatch.

## CI

GitHub Actions: [.github/workflows/ci.yml](../.github/workflows/ci.yml) — frontend lint+build (Node 18), backend Ruff + pytest (Python 3.10).

## Ruff (Python)

Install into the project venv so local and CI checks match:

```bash
./.venv/bin/pip install -r deps/requirements-dev.txt
```

Config: [pyproject.toml](../pyproject.toml). Canonical invocations from repo root:

```bash
./.venv/bin/ruff check .
./.venv/bin/ruff format .
```

Run `ruff check .` before pushing — CI fails the backend job on any ruff violation. Do not duplicate rule lists in prose.

## Canonical local verification

Full CI-aligned check sequence, executed from repo root:

```bash
./.venv/bin/ruff check .
./.venv/bin/python -m pytest -q
cd web-dashboard && nvm use && npm run lint && npm run test -- --run && npm run build
```
