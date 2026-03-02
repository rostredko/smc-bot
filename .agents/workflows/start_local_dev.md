---
description: start the local development environment using docker
---

# Starting Local Development Environment

When the user requests to start the local development environment, start the servers, or run the project locally, you MUST strictly follow these steps:

1. **DO NOT** run `python server.py` or `npm run dev` manually. We have migrated to a fully containerized setup for local development.
2. **Preserve Data**: Ensure that you do not overwrite or reset any existing database volumes or caches unless explicitly requested. The data volumes `mongo_data` and `data_cache` must be persisted.

To start the project:

// turbo
1. Run `docker compose up -d` to spin up MongoDB, the Python Backend, and the Vite Frontend in the background.

```shell
docker compose up -d
```

To stop the project, run `docker compose down`. Do not use `-v` unless the user explicitly asks to wipe all database and cache data.
