#!/bin/bash
# Koval repo bootstrap script
# Run from INSIDE the already-cloned koval-ai directory
# Example: cd ~/Projects/koval-ai && bash ~/Projects/smc-bot/docs/koval-init/bootstrap.sh

set -e

SMC_BOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"

# Verify we're inside a git repo pointing at koval-ai
REMOTE_URL="$(git remote get-url origin 2>/dev/null || echo '')"
if [[ "$REMOTE_URL" != *"koval-ai"* ]]; then
  echo "ERROR: Run this script from inside the koval-ai repo directory."
  echo "       Current remote: $REMOTE_URL"
  exit 1
fi

echo "=== Koval Bootstrap ==="
echo "smc-bot source : $SMC_BOT_DIR"
echo "koval-ai target: $(pwd)"
echo ""

# ── 2. Copy agent documentation ───────────────────────────────────────────────
echo "→ Copying agent docs from smc-bot..."
cp "$SMC_BOT_DIR/docs/koval-init/CLAUDE.md"            ./CLAUDE.md
cp "$SMC_BOT_DIR/docs/koval-init/AGENTS.md"            ./AGENTS.md
cp "$SMC_BOT_DIR/docs/koval-init/PROJECT_STRUCTURE.md" ./PROJECT_STRUCTURE.md
cp -r "$SMC_BOT_DIR/docs/koval-init/agent_docs/"       ./agent_docs/

# ── 3. Python package structure ───────────────────────────────────────────────
echo "→ Creating Python package structure..."
mkdir -p koval/engine
mkdir -p koval/adapters/backtrader
mkdir -p koval/strategy/base
mkdir -p koval/blocks/signals
mkdir -p koval/blocks/filters
mkdir -p koval/blocks/exits
mkdir -p koval/blocks/risk
mkdir -p koval/exchanges
mkdir -p koval/db/repositories

# ── 4. API structure ──────────────────────────────────────────────────────────
mkdir -p api/routers
mkdir -p api/services

# ── 5. Dashboard structure ────────────────────────────────────────────────────
mkdir -p dashboard/src/features/block-builder
mkdir -p dashboard/src/features/strategy-config
mkdir -p dashboard/src/features/backtest
mkdir -p dashboard/src/features/live-monitor
mkdir -p dashboard/src/app/providers
mkdir -p dashboard/src/entities
mkdir -p dashboard/src/shared/api

# ── 6. Tests ──────────────────────────────────────────────────────────────────
mkdir -p tests/engine
mkdir -p tests/strategy
mkdir -p tests/blocks
mkdir -p tests/exchanges
mkdir -p tests/api

# ── 7. Docs ───────────────────────────────────────────────────────────────────
mkdir -p docs/plans
mkdir -p docs/superpowers/specs
mkdir -p docs/superpowers/plans
mkdir -p tools

# ── 8. __init__.py files ──────────────────────────────────────────────────────
echo "→ Creating __init__.py files..."
find koval api -type d | xargs -I{} touch {}/__init__.py
touch tests/__init__.py
for d in tests/engine tests/strategy tests/blocks tests/exchanges tests/api; do
  touch "$d/__init__.py"
done

# ── 9. conftest.py ────────────────────────────────────────────────────────────
cat > tests/conftest.py << 'CONFEOF'
import os
import pytest

os.environ.setdefault("USE_MONGOMOCK", "true")
os.environ.setdefault("KOVAL_ENV", "test")
CONFEOF

# ── 10. pyproject.toml ────────────────────────────────────────────────────────
echo "→ Creating pyproject.toml..."
cat > pyproject.toml << 'PYEOF'
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.backends.legacy:build"

[project]
name = "koval"
version = "0.1.0"
description = "Universal algo-trading platform for traders without programming knowledge"
requires-python = ">=3.11"
dependencies = [
    "backtrader>=1.9.78",
    "fastapi>=0.111",
    "uvicorn[standard]>=0.29",
    "pydantic>=2.7",
    "motor>=3.4",
    "pymongo>=4.7",
    "mongomock>=4.1",
    "python-dotenv>=1.0",
    "ccxt>=4.3",
    "websockets>=12.0",
    "numpy>=1.26",
    "pandas>=2.2",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.1",
    "pytest-asyncio>=0.23",
    "pytest-cov>=5.0",
    "httpx>=0.27",
    "ruff>=0.4",
    "responses>=0.25",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]
ignore = ["E501"]
PYEOF

# ── 11. .env.example ──────────────────────────────────────────────────────────
cat > .env.example << 'ENVEOF'
# Koval environment
KOVAL_ENV=development

# MongoDB
MONGO_URI=mongodb://localhost:27017
MONGO_DB=koval

# Binance (testnet)
BINANCE_API_KEY=
BINANCE_API_SECRET=
BINANCE_TESTNET=true

# WhiteBIT (sandbox)
WHITEBIT_API_KEY=
WHITEBIT_API_SECRET=
WHITEBIT_TESTNET=true

# Test mode (in-memory MongoDB)
USE_MONGOMOCK=false
ENVEOF

# ── 12. .gitignore ────────────────────────────────────────────────────────────
cat > .gitignore << 'GITEOF'
__pycache__/
*.py[cod]
*.so
.env
.venv/
venv/
dist/
build/
*.egg-info/
.pytest_cache/
.ruff_cache/
.mypy_cache/
node_modules/
dashboard/dist/
data_cache/
*.log
.DS_Store
.idea/
.vscode/
GITEOF

# ── 13. .nvmrc (Node 18 for dashboard) ───────────────────────────────────────
echo "18" > .nvmrc

# ── 14. README.md skeleton ────────────────────────────────────────────────────
cat > README.md << 'READMEEOF'
# Koval

> Universal algo-trading platform for traders without programming knowledge.

**Koval** (укр. коваль = blacksmith) lets you build trading strategies by connecting blocks in a visual editor — no code required.

## Features

- 🔧 **Block Builder** — drag-drop strategy canvas (signals + filters + exits)
- 📊 **Backtesting** — historical OHLCV simulation
- 📄 **Paper Trading** — live market data, simulated execution
- 🔴 **Sandbox Live** — exchange testnet trading (Binance, WhiteBIT)
- 🇺🇦 **WhiteBIT support** — Ukrainian exchange

## Quick start

```bash
cp .env.example .env
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build --watch
```

Dashboard: http://localhost:5174
API: http://localhost:8000

## License

Core: MIT · Backtrader adapter: GPL-3.0
READMEEOF

# ── 15. LICENSE files ─────────────────────────────────────────────────────────
cat > LICENSE-MIT << 'MITEOF'
MIT License

Copyright (c) 2026 Koval Contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
MITEOF

# ── 16. .gitkeep for tracked empty dirs ───────────────────────────────────────
find . -type d -empty -not -path "./.git/*" | xargs -I{} touch {}/.gitkeep

# ── 17. Docker files ──────────────────────────────────────────────────────────
echo "→ Creating Docker files..."
cat > docker-compose.yml << 'DCEOF'
services:
  mongo:
    image: mongo:7
    ports:
      - "27017:27017"
    volumes:
      - mongo_data:/data/db
      - data_cache:/data/cache

  backend:
    build:
      context: .
      dockerfile: Dockerfile.backend
    ports:
      - "8000:8000"
    environment:
      - MONGO_URI=mongodb://mongo:27017
      - MONGO_DB=koval
      - KOVAL_ENV=development
    env_file:
      - .env
    volumes:
      - data_cache:/app/data_cache
    depends_on:
      - mongo

  frontend:
    build:
      context: ./dashboard
      dockerfile: Dockerfile
    ports:
      - "5174:5173"
    depends_on:
      - backend

volumes:
  mongo_data:
  data_cache:
DCEOF

cat > docker-compose.dev.yml << 'DEVEOF'
services:
  backend:
    build:
      context: .
      dockerfile: Dockerfile.backend
      target: dev
    volumes:
      - ./koval:/app/koval
      - ./api:/app/api
    command: uvicorn api.server:app --host 0.0.0.0 --port 8000 --reload

  frontend:
    volumes:
      - ./dashboard/src:/app/src
DEVEOF

cat > Dockerfile.backend << 'DFEOF'
FROM python:3.11-slim AS base

RUN apt-get update && apt-get install -y \
    build-essential \
    libta-lib-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml .
RUN pip install -e .

FROM base AS dev
RUN pip install -e ".[dev]"
COPY . .

FROM base AS prod
COPY . .
CMD ["uvicorn", "api.server:app", "--host", "0.0.0.0", "--port", "8000"]
DFEOF

# ── 18. Done ─────────────────────────────────────────────────────────────────
echo ""
echo "=== Structure created successfully! ==="
echo ""
echo "Next steps (run manually from koval-ai/):"
echo ""
echo "  git add ."
echo "  git commit -m 'chore: initialize Koval repo structure and agent documentation'"
echo "  git push origin main"
echo ""
echo "Then start Phase 1 from the implementation plan:"
echo "  (in smc-bot) docs/superpowers/plans/2026-05-01-koval-migration.md"
