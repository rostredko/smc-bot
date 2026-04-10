# Building & Docker

## Production-style Compose

From repo root:

```bash
docker compose up -d --build
```

- API: port **8000**
- Dashboard: host **5174** → container **5173**
- MongoDB: **27017**

`docker-compose.override.yml` is intentionally minimal so plain `docker compose up` stays stable on Docker Desktop.

## Dev with hot reload

**Single command** (watch sync + uvicorn/Vite reload—do not split `up -d` and watch):

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build --watch
```

See also [README.md](../README.md). A local `./scripts/dev.sh` is mentioned there but `scripts/` may be gitignored—use the compose command above if the script is absent.

## Local (no full Docker)

- Backend: `cd web-dashboard && uvicorn server:app --host 0.0.0.0 --port 8000 --reload`
- Frontend: `cd web-dashboard && npm install && npm run dev -- --host 0.0.0.0`

Prerequisites: Python 3.10+, Node 18+, MongoDB 7+, **TA-Lib C library** (must be installed system-wide before `pip install` — see [README.md](../README.md) for platform-specific instructions).

## Environment variables

Copy `.env.example` to `.env` before first run:

```bash
cp .env.example .env
```

| Variable | Default | When needed | Notes |
|----------|---------|-------------|-------|
| `MONGODB_URI` | `mongodb://localhost:27017` | Local dev | Mongo connection string; not needed for Docker Compose |
| `MONGODB_DB` | `backtrade` | Always | Database name |
| `USE_DATABASE` | `true` | Always | Set `false` to disable persistence entirely |
| `USE_MONGOMOCK` | (unset) | Tests only | Set `true` for in-memory MongoDB — required for all test runs without a real Mongo instance |
| `RUN_LIVE_TESTS` | (unset) | Live E2E tests | Set `1` to opt in to internet-dependent live tests (`@pytest.mark.live`) |

For Docker Compose runs, MongoDB starts automatically — no `MONGODB_URI` override needed.
For local (non-Docker) runs, MongoDB must be running on port `27017` or `MONGODB_URI` must point to it.
