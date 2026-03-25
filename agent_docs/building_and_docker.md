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

Prerequisites: Python 3.10+, Node 18+, MongoDB 7+, TA-Lib C library. See [README.md](../README.md).
