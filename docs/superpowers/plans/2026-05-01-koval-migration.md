# Koval — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate smc-bot into Koval — a universal open-source algo-trading platform for traders without programming knowledge, with block builder UI, backtesting, paper and sandbox live trading on Binance and WhiteBIT.

**Architecture:** Clean fork (new GitLab repo). Backtrader stays as execution engine but is fully hidden behind `BTStrategyAdapter`. Core is MIT-licensed; the Backtrader adapter layer is GPL-3.0. Strategy logic is expressed as JSON block graphs that the engine assembles into `DeclarativeStrategy` instances at runtime.

**Tech Stack:** Python 3.11+, Backtrader, FastAPI, Pydantic v2, TA-Lib, React 18 + TypeScript + Vite + MUI v5, react-flow (block builder), MongoDB, Docker Compose, Pytest, Vitest, Ruff.

**Design spec:** `docs/superpowers/specs/2026-05-01-koval-design.md` (in smc-bot repo)

**Target repo:** `git@gitlab.com:koval-group/koval-ai.git`

---

## Scope note

This plan has 10 phases. Each phase produces working, testable software independently. For phases 5+, create a dedicated sub-plan at execution time using `writing-plans` skill with the phase spec as input.

---

## Phase 0: Repo Bootstrap

**Goal:** Initialized Koval repo with correct structure, Docker, CI config, and all agent documentation in place. Running `docker compose up` boots an empty but wired-up stack.

**Files to create:**

```
koval/
├── koval/                     # Python package root
│   ├── __init__.py
│   ├── engine/                # (empty, phase 1)
│   ├── adapters/
│   │   └── backtrader/        # (empty, phase 1)
│   ├── strategy/
│   │   └── base/              # (empty, phase 2)
│   ├── blocks/
│   │   ├── signals/           # (empty, phase 3)
│   │   ├── filters/           # (empty, phase 3)
│   │   ├── exits/             # (empty, phase 3)
│   │   └── risk/              # (empty, phase 3)
│   ├── exchanges/             # (empty, phase 5)
│   └── db/                    # (empty, phase 6)
├── api/                       # FastAPI app (empty, phase 6)
├── dashboard/                 # React app (empty, phase 8)
├── tests/
│   └── conftest.py
├── agent_docs/                # (copy from docs/koval-init/agent_docs/)
├── docker-compose.yml
├── docker-compose.dev.yml
├── pyproject.toml
├── .env.example
├── CLAUDE.md                  # (copy from docs/koval-init/CLAUDE.md)
├── AGENTS.md                  # (copy from docs/koval-init/AGENTS.md)
├── PROJECT_STRUCTURE.md       # (copy from docs/koval-init/PROJECT_STRUCTURE.md)
├── LICENSE-MIT
├── LICENSE-GPL
└── README.md
```

### Task 0.1: Initialize repo and copy agent docs

- [ ] **Step 1: Clone / init the repo**

```bash
git clone git@gitlab.com:koval-group/koval-ai.git
cd koval-ai
```

- [ ] **Step 2: Copy init files from smc-bot**

From smc-bot repo, copy everything in `docs/koval-init/` to the root of the new Koval repo:

```bash
# Run from smc-bot repo root
cp docs/koval-init/CLAUDE.md         /path/to/koval/CLAUDE.md
cp docs/koval-init/AGENTS.md         /path/to/koval/AGENTS.md
cp docs/koval-init/PROJECT_STRUCTURE.md /path/to/koval/PROJECT_STRUCTURE.md
cp -r docs/koval-init/agent_docs/    /path/to/koval/agent_docs/
```

- [ ] **Step 3: Create Python package skeleton**

```bash
cd koval
mkdir -p koval/engine
mkdir -p koval/adapters/backtrader
mkdir -p koval/strategy/base
mkdir -p koval/blocks/signals koval/blocks/filters koval/blocks/exits koval/blocks/risk
mkdir -p koval/exchanges
mkdir -p koval/db/repositories
mkdir -p api/routers api/services
mkdir -p tests/engine tests/strategy tests/blocks tests/exchanges tests/api
```

Create `__init__.py` in every package dir:

```bash
find koval api -type d | xargs -I{} touch {}/__init__.py
touch tests/__init__.py
touch tests/engine/__init__.py tests/strategy/__init__.py
touch tests/blocks/__init__.py tests/exchanges/__init__.py tests/api/__init__.py
```

- [ ] **Step 4: Create conftest.py**

`tests/conftest.py`:
```python
import os
import pytest

os.environ.setdefault("USE_MONGOMOCK", "true")
os.environ.setdefault("KOVAL_ENV", "test")
```

- [ ] **Step 5: Create LICENSE files**

`LICENSE-MIT`:
```
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
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
```

`LICENSE-GPL`: Download full GPL-3.0 text from https://www.gnu.org/licenses/gpl-3.0.txt

- [ ] **Step 6: Commit initial structure**

```bash
git add .
git commit -m "chore: initialize Koval repo structure and agent documentation"
git push origin main
```

### Task 0.2: pyproject.toml + dependencies

- [ ] **Step 1: Write pyproject.toml**

`pyproject.toml`:
```toml
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
```

- [ ] **Step 2: Create .env.example**

`.env.example`:
```env
# Koval environment
KOVAL_ENV=development

# MongoDB
MONGO_URI=mongodb://localhost:27017
MONGO_DB=koval

# Binance
BINANCE_API_KEY=
BINANCE_API_SECRET=
BINANCE_TESTNET=true

# WhiteBIT
WHITEBIT_API_KEY=
WHITEBIT_API_SECRET=
WHITEBIT_TESTNET=true

# Test mode
USE_MONGOMOCK=false
```

- [ ] **Step 3: Run test to verify setup**

```bash
pip install -e ".[dev]"
python -m pytest tests/ -q
```

Expected: `no tests ran` (0 errors — structure is valid).

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml .env.example
git commit -m "chore: add pyproject.toml and environment config"
```

### Task 0.3: Docker Compose

- [ ] **Step 1: Write docker-compose.yml**

`docker-compose.yml`:
```yaml
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
```

- [ ] **Step 2: Write docker-compose.dev.yml**

`docker-compose.dev.yml`:
```yaml
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
```

- [ ] **Step 3: Write Dockerfile.backend**

`Dockerfile.backend`:
```dockerfile
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
```

- [ ] **Step 4: Commit**

```bash
git add docker-compose.yml docker-compose.dev.yml Dockerfile.backend
git commit -m "chore: add Docker Compose stack"
```

---

## Phase 1: Core Engine Port

**Goal:** All portable engine utilities running with tests in Koval. OCO patch, analyzers, metrics, narrator, logger — all confirmed working.

**Source (smc-bot → Koval):**

| Source | Destination |
|--------|-------------|
| `engine/logger.py` | `koval/engine/logger.py` |
| `engine/timeframe_utils.py` | `koval/engine/timeframe_utils.py` |
| `engine/trade_metrics.py` | `koval/engine/trade_metrics.py` |
| `engine/trade_narrator.py` | `koval/engine/trade_narrator.py` |
| `engine/execution_settings.py` | `koval/engine/execution_settings.py` |
| `engine/bt_analyzers.py` | `koval/adapters/backtrader/bt_analyzers.py` |
| `engine/bt_oco_patch.py` | `koval/adapters/backtrader/oco_patch.py` |

### Task 1.1: Port logger + timeframe_utils

- [ ] **Step 1: Copy and adapt logger**

`koval/engine/logger.py` — copy from smc-bot `engine/logger.py`. Change any `smc_bot` references to `koval`.

- [ ] **Step 2: Copy timeframe_utils**

`koval/engine/timeframe_utils.py` — copy verbatim from smc-bot. No changes needed.

- [ ] **Step 3: Write test**

`tests/engine/test_timeframe_utils.py`:
```python
from koval.engine.timeframe_utils import ordered_timeframes

def test_ordered_timeframes_sorts_ltf_first():
    result = ordered_timeframes(["4h", "1h"])
    assert result == ["1h", "4h"]

def test_ordered_timeframes_three_frames():
    result = ordered_timeframes(["1d", "15m", "1h"])
    assert result == ["15m", "1h", "1d"]
```

- [ ] **Step 4: Run and verify**

```bash
python -m pytest tests/engine/test_timeframe_utils.py -v
```

Expected: 2 PASSED.

- [ ] **Step 5: Commit**

```bash
git add koval/engine/logger.py koval/engine/timeframe_utils.py tests/engine/test_timeframe_utils.py
git commit -m "feat: port logger and timeframe_utils from smc-bot"
```

### Task 1.2: Port OCO patch (critical)

- [ ] **Step 1: Copy oco_patch.py**

`koval/adapters/backtrader/oco_patch.py` — copy from smc-bot `engine/bt_oco_patch.py` verbatim. This is GPL-3.0 code. Add license header:

```python
# SPDX-License-Identifier: GPL-3.0-or-later
# Koval Backtrader Adapter — OCO guard patch
# Fixes Backtrader ghost-trade bug: same-bar TP+SL double-fill
# Applied before Cerebro instantiation in base_engine.py
```

- [ ] **Step 2: Write smoke test**

`tests/engine/test_oco_patch.py`:
```python
import backtrader as bt
from koval.adapters.backtrader.oco_patch import apply_oco_guard

def test_oco_patch_applies_without_error():
    apply_oco_guard()
    cerebro = bt.Cerebro()
    assert cerebro is not None

def test_oco_patch_idempotent():
    apply_oco_guard()
    apply_oco_guard()  # second call must not raise
    cerebro = bt.Cerebro()
    assert cerebro is not None
```

- [ ] **Step 3: Run and verify**

```bash
python -m pytest tests/engine/test_oco_patch.py -v
```

Expected: 2 PASSED.

- [ ] **Step 4: Commit**

```bash
git add koval/adapters/backtrader/oco_patch.py tests/engine/test_oco_patch.py
git commit -m "feat: port OCO guard patch to koval backtrader adapter (GPL-3.0)"
```

### Task 1.3: Port trade_metrics + trade_narrator

- [ ] **Step 1: Copy trade_metrics.py**

`koval/engine/trade_metrics.py` — copy from smc-bot. Update imports if any refer to smc-bot modules.

- [ ] **Step 2: Copy trade_narrator.py**

`koval/engine/trade_narrator.py` — copy from smc-bot. Update imports.

- [ ] **Step 3: Port bt_analyzers.py**

`koval/adapters/backtrader/bt_analyzers.py` — copy from smc-bot `engine/bt_analyzers.py`. Add GPL-3.0 header. Update import paths.

- [ ] **Step 4: Write test**

`tests/engine/test_trade_metrics.py` — copy from smc-bot `tests/test_trade_metrics.py` and update imports:

```python
from koval.engine.trade_metrics import TradeMetrics  # adjust to actual class/function names
```

- [ ] **Step 5: Run and verify**

```bash
python -m pytest tests/engine/ -v
```

Expected: all PASSED.

- [ ] **Step 6: Commit**

```bash
git add koval/engine/ koval/adapters/ tests/engine/
git commit -m "feat: port core engine utilities (metrics, narrator, analyzers)"
```

---

## Phase 2: Declarative Strategy ABC + BTAdapter

**Goal:** `DeclarativeStrategy` ABC and `BTStrategyAdapter` implemented and tested. A minimal test strategy (AlwaysLong) runs through Backtrader cerebro and produces at least one trade.

**New files:**

| File | Responsibility |
|------|----------------|
| `koval/strategy/base/trade_setup.py` | `TradeSetup`, `StructureState`, `ChartAnnotation` dataclasses |
| `koval/strategy/base/declarative.py` | `DeclarativeStrategy` ABC |
| `koval/adapters/backtrader/bt_adapter.py` | `BTStrategyAdapter` — all BT code here |

### Task 2.1: TradeSetup dataclasses

- [ ] **Step 1: Write failing test**

`tests/strategy/test_trade_setup.py`:
```python
from koval.strategy.base.trade_setup import TradeSetup, StructureState

def test_trade_setup_long_defaults():
    setup = TradeSetup(direction='long', entry_price=100.0, stop_loss=95.0)
    assert setup.direction == 'long'
    assert setup.take_profit is None
    assert setup.entry_type == 'limit'
    assert setup.why_entry == []

def test_trade_setup_short():
    setup = TradeSetup(direction='short', entry_price=50000.0, stop_loss=51000.0)
    assert setup.direction == 'short'

def test_structure_state_defaults():
    state = StructureState()
    assert state.bias == 'neutral'
    assert state.bos_confirmed is False
```

- [ ] **Step 2: Run to verify it fails**

```bash
python -m pytest tests/strategy/test_trade_setup.py -v
```

Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement trade_setup.py**

`koval/strategy/base/trade_setup.py`:
```python
from dataclasses import dataclass, field
from typing import Literal, Optional


@dataclass
class StructureState:
    bias: Literal['bullish', 'bearish', 'neutral'] = 'neutral'
    last_swing_high: Optional[float] = None
    last_swing_low: Optional[float] = None
    active_poi: Optional[float] = None
    bos_confirmed: bool = False
    choch_detected: bool = False
    ltf_choch_detected: bool = False
    poi_zone_upper: Optional[float] = None
    poi_zone_lower: Optional[float] = None


@dataclass
class ChartAnnotation:
    type: Literal['level', 'zone', 'marker', 'label']
    time: int
    value: float
    color: str = '#ffffff'
    label: str = ''
    zone_top: Optional[float] = None
    zone_bottom: Optional[float] = None


@dataclass
class TradeSetup:
    direction: Literal['long', 'short']
    entry_price: float
    stop_loss: float
    take_profit: Optional[float] = None
    size: Optional[float] = None
    entry_type: Literal['market', 'limit', 'stop'] = 'limit'
    why_entry: list[str] = field(default_factory=list)
    indicators_at_entry: dict = field(default_factory=dict)
    sl_calc_expr: Optional[str] = None
    tp_calc_expr: Optional[str] = None
    annotations: list[ChartAnnotation] = field(default_factory=list)
```

- [ ] **Step 4: Run and verify**

```bash
python -m pytest tests/strategy/test_trade_setup.py -v
```

Expected: 3 PASSED.

- [ ] **Step 5: Commit**

```bash
git add koval/strategy/base/trade_setup.py tests/strategy/test_trade_setup.py
git commit -m "feat: add TradeSetup, StructureState, ChartAnnotation dataclasses"
```

### Task 2.2: DeclarativeStrategy ABC

- [ ] **Step 1: Write failing test**

`tests/strategy/test_declarative.py`:
```python
from koval.strategy.base.declarative import DeclarativeStrategy
from koval.strategy.base.trade_setup import TradeSetup

class AlwaysLongStrategy(DeclarativeStrategy):
    def should_long(self) -> bool:
        return True
    def go_long(self) -> TradeSetup:
        return TradeSetup(direction='long', entry_price=self.close, stop_loss=self.close * 0.95, entry_type='market')

def test_should_long_returns_true():
    s = AlwaysLongStrategy()
    s.close = 100.0
    assert s.should_long() is True

def test_go_long_returns_trade_setup():
    s = AlwaysLongStrategy()
    s.close = 100.0
    setup = s.go_long()
    assert setup.direction == 'long'
    assert setup.entry_price == 100.0
    assert setup.stop_loss == 95.0

def test_default_should_short_false():
    s = AlwaysLongStrategy()
    assert s.should_short() is False

def test_execute_filters_empty_returns_true():
    s = AlwaysLongStrategy()
    assert s._execute_filters() is True

def test_execute_filters_with_false_filter():
    s = AlwaysLongStrategy()
    s._filters_override = [lambda: False]
    # patch filters
    s.__class__.filters = lambda self: [lambda: False]
    assert s._execute_filters() is False
```

- [ ] **Step 2: Run to verify it fails**

```bash
python -m pytest tests/strategy/test_declarative.py -v
```

Expected: FAIL.

- [ ] **Step 3: Implement declarative.py**

`koval/strategy/base/declarative.py`:
```python
from abc import ABC
from typing import Optional
import numpy as np
from .trade_setup import TradeSetup, StructureState


class DeclarativeStrategy(ABC):
    """
    Base class for no-BT-knowledge strategies.
    Engine calls the hooks; strategy returns intents.
    Override should_long/should_short/go_long/go_short.
    Never call self.buy() or self.sell() — return TradeSetup instead.
    """

    close: float = 0.0
    high: float = 0.0
    low: float = 0.0
    open: float = 0.0
    volume: float = 0.0
    bar_index: int = 0
    timestamp: int = 0
    candles: Optional[np.ndarray] = None
    htf_candles: Optional[np.ndarray] = None

    account_value: float = 0.0
    position_size: float = 0.0
    position_direction: Optional[str] = None

    config: dict = {}
    _indicator_cache: dict = {}

    def should_long(self) -> bool:
        return False

    def should_short(self) -> bool:
        return False

    def go_long(self) -> TradeSetup:
        raise NotImplementedError("Override go_long()")

    def go_short(self) -> TradeSetup:
        raise NotImplementedError("Override go_short()")

    def should_cancel_entry(self) -> bool:
        return False

    def on_open_position(self, trade_id: int, setup: TradeSetup) -> None:
        pass

    def on_close_position(self, trade_id: int, result: dict) -> None:
        pass

    def on_sl_update(self, trade_id: int) -> Optional[float]:
        return None

    def on_tp_update(self, trade_id: int) -> Optional[float]:
        return None

    def filters(self) -> list:
        return []

    def _execute_filters(self) -> bool:
        return all(f() for f in self.filters())

    def indicator(self, name: str, **kwargs) -> float:
        key = (name, tuple(sorted(kwargs.items())))
        return self._indicator_cache.get(key, float('nan'))

    def hyperparameters(self) -> list:
        return []
```

- [ ] **Step 4: Run and verify**

```bash
python -m pytest tests/strategy/test_declarative.py -v
```

Expected: PASSED (adjust filter test if needed).

- [ ] **Step 5: Commit**

```bash
git add koval/strategy/base/declarative.py tests/strategy/test_declarative.py
git commit -m "feat: add DeclarativeStrategy ABC"
```

### Task 2.3: BTStrategyAdapter (full BT shim)

- [ ] **Step 1: Write integration test**

`tests/strategy/test_bt_adapter.py`:
```python
import backtrader as bt
import pandas as pd
import numpy as np
from koval.adapters.backtrader.oco_patch import apply_oco_guard
from koval.adapters.backtrader.bt_adapter import make_bt_strategy_class
from koval.strategy.base.declarative import DeclarativeStrategy
from koval.strategy.base.trade_setup import TradeSetup

apply_oco_guard()

class AlwaysLong(DeclarativeStrategy):
    def should_long(self) -> bool:
        return self.position_size == 0
    def go_long(self) -> TradeSetup:
        return TradeSetup(
            direction='long',
            entry_price=self.close,
            stop_loss=self.close * 0.90,
            entry_type='market',
        )

def _make_synthetic_data(n=100) -> bt.feeds.PandasData:
    dates = pd.date_range('2024-01-01', periods=n, freq='1h')
    price = 100 + np.cumsum(np.random.randn(n) * 0.5)
    df = pd.DataFrame({
        'open': price, 'high': price * 1.001,
        'low': price * 0.999, 'close': price,
        'volume': np.ones(n) * 1000,
    }, index=dates)
    return bt.feeds.PandasData(dataname=df)

def test_adapter_executes_at_least_one_trade():
    AdaptedClass = make_bt_strategy_class(AlwaysLong, risk_per_trade=1.0, risk_reward_ratio=2.0)
    cerebro = bt.Cerebro()
    cerebro.adddata(_make_synthetic_data())
    cerebro.addstrategy(AdaptedClass)
    cerebro.broker.setcash(10000)
    results = cerebro.run()
    strat = results[0]
    assert strat._next_trade_id > 1  # at least one trade opened
```

- [ ] **Step 2: Run to verify it fails**

```bash
python -m pytest tests/strategy/test_bt_adapter.py -v
```

Expected: FAIL — `make_bt_strategy_class` not found.

- [ ] **Step 3: Implement bt_adapter.py**

`koval/adapters/backtrader/bt_adapter.py` — base this on `engine_universal_spec.md` section 4.3 from smc-bot. Key structure:

```python
# SPDX-License-Identifier: GPL-3.0-or-later
import backtrader as bt
import numpy as np
from typing import Optional, Type
from koval.engine.logger import get_logger
from koval.strategy.base.declarative import DeclarativeStrategy
from koval.strategy.base.trade_setup import TradeSetup
from koval.blocks.risk.position_sizer import calculate_position_size

logger = get_logger(__name__)


class BTStrategyAdapter(bt.Strategy):
    """
    Backtrader shim that delegates to a DeclarativeStrategy instance.
    ALL Backtrader-specific code lives here. User strategies never touch BT.
    """
    params = (
        ('risk_reward_ratio', 2.0),
        ('risk_per_trade', 1.0),
        ('leverage', 1.0),
        ('max_drawdown', None),
        ('trailing_stop_distance', 0.0),
        ('breakeven_trigger_r', 0.0),
        ('sl_buffer_atr', 1.5),
        ('strategy_config', {}),
    )

    def __init__(self):
        super().__init__()
        self._strategy = self._create_strategy_instance()
        self._strategy.config = dict(self.params.strategy_config or {})
        self._entry_order = None
        self._stop_order = None
        self._tp_order = None
        self._pending_setup: Optional[TradeSetup] = None
        self._trade_map = {}
        self._next_trade_id = 1
        self._equity_peak = self.broker.startingcash
        self._dd_limit_hit = False
        self._entry_exec_bar = -1

    def _create_strategy_instance(self) -> DeclarativeStrategy:
        raise NotImplementedError

    def _inject_state(self):
        s = self._strategy
        s.close = float(self.data.close[0])
        s.high = float(self.data.high[0])
        s.low = float(self.data.low[0])
        s.open = float(self.data.open[0])
        s.volume = float(self.data.volume[0]) if hasattr(self.data, 'volume') else 0.0
        s.bar_index = len(self.data)
        s.account_value = self.broker.getvalue()
        s.position_size = abs(float(self.position.size)) if self.position else 0.0
        s.position_direction = (
            'long' if self.position.size > 0
            else 'short' if self.position.size < 0
            else None
        )
        n = min(300, len(self.data))
        if n > 0:
            s.candles = np.array([
                [float(self.data.open[-n + 1 + i]),
                 float(self.data.high[-n + 1 + i]),
                 float(self.data.low[-n + 1 + i]),
                 float(self.data.close[-n + 1 + i]),
                 float(self.data.volume[-n + 1 + i]) if hasattr(self.data, 'volume') else 0.0]
                for i in range(n)
            ])

    def next(self):
        if self._dd_limit_hit:
            return
        self._inject_state()
        self._equity_peak = max(self._equity_peak, self.broker.getvalue())

        if not self.position:
            setup = None
            if self._strategy.should_long() and self._strategy._execute_filters():
                setup = self._strategy.go_long()
            elif self._strategy.should_short() and self._strategy._execute_filters():
                setup = self._strategy.go_short()
            if setup is not None:
                self._submit_entry(setup)
            return

        self._update_exits()

    def _submit_entry(self, setup: TradeSetup):
        size = setup.size
        if size is None:
            size = calculate_position_size(
                account_value=self.broker.getvalue(),
                risk_per_trade_pct=self.params.risk_per_trade,
                entry_price=setup.entry_price,
                stop_loss=setup.stop_loss,
                leverage=self.params.leverage,
            )
        if size <= 0:
            return
        self._pending_setup = setup
        is_long = setup.direction == 'long'
        order_fn = self.buy if is_long else self.sell
        if setup.entry_type == 'market':
            self._entry_order = order_fn(size=size)
        elif setup.entry_type == 'limit':
            self._entry_order = order_fn(price=setup.entry_price, exectype=bt.Order.Limit, size=size)
        else:
            self._entry_order = order_fn(price=setup.entry_price, exectype=bt.Order.Stop, size=size)

    def _place_bracket(self, exec_price: float, size: float, setup: TradeSetup):
        sl = setup.stop_loss
        tp = setup.take_profit
        if tp is None:
            dist = abs(exec_price - sl)
            tp = (exec_price + dist * self.params.risk_reward_ratio
                  if setup.direction == 'long'
                  else exec_price - dist * self.params.risk_reward_ratio)
        if setup.direction == 'long':
            self._stop_order = self.sell(price=sl, exectype=bt.Order.Stop, size=size)
            self._tp_order = self.sell(price=tp, exectype=bt.Order.Limit, size=size, oco=self._stop_order)
        else:
            self._stop_order = self.buy(price=sl, exectype=bt.Order.Stop, size=size)
            self._tp_order = self.buy(price=tp, exectype=bt.Order.Limit, size=size, oco=self._stop_order)

    def _update_exits(self):
        if self._stop_order is None or not self._stop_order.alive():
            return
        if self._entry_exec_bar < 0 or len(self.data) == self._entry_exec_bar:
            return
        new_sl = self._strategy.on_sl_update(0)
        if new_sl is not None and new_sl != self._stop_order.price:
            self.cancel(self._stop_order)
            size = abs(self.position.size)
            is_long = self.position.size > 0
            order_fn = self.sell if is_long else self.buy
            self._stop_order = order_fn(price=new_sl, exectype=bt.Order.Stop, size=size)
            if self._tp_order and self._tp_order.alive():
                self._tp_order = order_fn(
                    price=self._tp_order.price, exectype=bt.Order.Limit,
                    size=size, oco=self._stop_order
                )

    def notify_order(self, order):
        if order.status in (order.Submitted, order.Accepted):
            return
        if order.status == order.Completed:
            if order == self._entry_order:
                self._entry_order = None
                size = abs(order.executed.size)
                self._place_bracket(order.executed.price, size, self._pending_setup)
                self._entry_exec_bar = len(self.data)
                return
            if self._stop_order and order.ref == self._stop_order.ref:
                if self._tp_order:
                    self.cancel(self._tp_order)
                    self._tp_order = None
                self._stop_order = None
            elif self._tp_order and order.ref == self._tp_order.ref:
                if self._stop_order:
                    self.cancel(self._stop_order)
                    self._stop_order = None
                self._tp_order = None
        elif order.status in (order.Canceled, order.Margin, order.Rejected):
            if order == self._entry_order:
                self._entry_order = None

    def notify_trade(self, trade):
        if trade.justopened:
            if self._pending_setup:
                self._trade_map[trade.ref] = {'setup': self._pending_setup}
                self._strategy.on_open_position(self._next_trade_id, self._pending_setup)
                self._pending_setup = None
        elif trade.isclosed:
            stored = self._trade_map.get(trade.ref, {})
            self._strategy.on_close_position(self._next_trade_id, {
                'pnl': trade.pnl, 'pnl_comm': trade.pnlcomm,
                'setup': stored.get('setup'),
            })
            self._next_trade_id += 1
            self._check_drawdown()

    def _check_drawdown(self):
        max_dd = self.params.max_drawdown
        if not max_dd or max_dd <= 0 or self._equity_peak <= 0:
            return
        dd_pct = 100.0 * (self._equity_peak - self.broker.getvalue()) / self._equity_peak
        if dd_pct > max_dd:
            self._dd_limit_hit = True
            try:
                self.cerebro.runstop()
            except Exception:
                pass


def make_bt_strategy_class(
    declarative_cls: Type[DeclarativeStrategy],
    **default_params,
) -> Type[BTStrategyAdapter]:
    """
    Factory: wraps a DeclarativeStrategy class into a BTStrategyAdapter subclass.
    
    Usage:
        AdaptedClass = make_bt_strategy_class(MyStrategy, risk_per_trade=1.0)
        cerebro.addstrategy(AdaptedClass)
    """
    param_tuple = tuple((k, v) for k, v in default_params.items())

    class _Adapter(BTStrategyAdapter):
        params = BTStrategyAdapter.params + param_tuple

        def _create_strategy_instance(self):
            return declarative_cls()

    _Adapter.__name__ = f"{declarative_cls.__name__}Adapter"
    return _Adapter
```

- [ ] **Step 4: Add placeholder position_sizer (needed for adapter)**

`koval/blocks/risk/position_sizer.py`:
```python
def calculate_position_size(
    account_value: float,
    risk_per_trade_pct: float,
    entry_price: float,
    stop_loss: float,
    leverage: float = 1.0,
) -> float:
    """Calculate position size based on risk percentage."""
    if entry_price <= 0 or stop_loss <= 0:
        return 0.0
    risk_amount = account_value * (risk_per_trade_pct / 100.0)
    sl_distance = abs(entry_price - stop_loss)
    if sl_distance == 0:
        return 0.0
    size = (risk_amount / sl_distance) * leverage
    return round(size, 8)
```

- [ ] **Step 5: Run integration test**

```bash
python -m pytest tests/strategy/test_bt_adapter.py -v
```

Expected: PASSED.

- [ ] **Step 6: Commit**

```bash
git add koval/adapters/backtrader/bt_adapter.py koval/blocks/risk/position_sizer.py tests/strategy/test_bt_adapter.py
git commit -m "feat: add BTStrategyAdapter and make_bt_strategy_class factory"
```

---

## Phase 3: Block Library

**Goal:** All signal, filter, exit, and risk blocks implemented as pure functions with tests. Port market_structure from smc-bot. Blocks are importable and independently testable without BT.

**Files:**

| File | Source |
|------|--------|
| `koval/blocks/signals/smc.py` | Port from `strategies/market_structure.py` |
| `koval/blocks/signals/candlesticks.py` | Extract from `strategies/bt_price_action.py` |
| `koval/blocks/signals/technical.py` | New (EMA cross, etc.) |
| `koval/blocks/filters/momentum.py` | New (RSI, MACD) |
| `koval/blocks/filters/trend.py` | New (ADX, EMA trend) |
| `koval/blocks/filters/volatility.py` | New (ATR, BB) |
| `koval/blocks/exits/fixed.py` | New |
| `koval/blocks/exits/trailing.py` | Extract from `strategies/base_strategy.py` |
| `koval/blocks/exits/breakeven.py` | Extract from `strategies/base_strategy.py` |
| `koval/blocks/risk/position_sizer.py` | Port from `strategies/helpers/risk_manager.py` |

**Key rule:** All block functions are pure — input data in, result out. No BT, no side effects.

> **Create detailed sub-plan for this phase** using `writing-plans` with `docs/superpowers/specs/2026-05-01-koval-design.md` section 2 (Block Execution Layer) as input before executing.

---

## Phase 4: Strategy Registry + Schemas + Block Assembler

**Goal:** `STRATEGY_REGISTRY`, Pydantic schemas for built-in strategies, and `BlockAssembler` that converts JSON block graph → `DeclarativeStrategy` instance at runtime.

**Files:**

| File | Responsibility |
|------|----------------|
| `koval/strategy/registry.py` | `StrategyDefinition`, `STRATEGY_REGISTRY`, `register_strategy`, `get_all_definitions` |
| `koval/strategy/schemas.py` | Pydantic schemas per strategy type (auto-generates JSON Schema for UI) |
| `koval/strategy/block_assembler.py` | `assemble_from_graph(graph_json) -> DeclarativeStrategy` |

**Key test (defines Phase 4 done):**

```python
def test_registry_returns_json_schema():
    from koval.strategy.registry import get_all_definitions
    defs = get_all_definitions()
    assert len(defs) > 0
    assert "schema" in defs[0]

def test_block_assembler_runs_backtest():
    graph = {
        "blocks": [
            {"id": "sig1", "type": "signal.ema_cross", "params": {"fast": 9, "slow": 21}},
            {"id": "ent1", "type": "entry.long", "params": {"entry_type": "market"}},
            {"id": "ex1", "type": "exit.atr_sl", "params": {"atr_mult": 1.5}},
        ],
        "connections": [
            {"from": "sig1", "to": "ent1"},
            {"from": "ent1", "to": "ex1"},
        ]
    }
    strategy = assemble_from_graph(graph)
    assert isinstance(strategy, DeclarativeStrategy)
```

> **Create detailed sub-plan for this phase** using `writing-plans` before executing.

---

## Phase 5: Exchange Adapters

**Goal:** `ExchangeAdapter` ABC, Binance adapter (ported from smc-bot), WhiteBIT adapter (new) — both supporting OHLCV fetch and live feed. Tests run with mocked HTTP.

**Files:**

| File | Source |
|------|--------|
| `koval/exchanges/base.py` | New — `ExchangeAdapter` ABC |
| `koval/exchanges/binance.py` | Port from `engine/data_loader.py` + `engine/live_ws_client.py` |
| `koval/exchanges/whitebit.py` | New — WhiteBIT REST API v4 + WebSocket |

**WhiteBIT API:** https://whitebit.com/api/docs — use v4 REST for OHLCV, WebSocket for live feed.

**Key test:**
```python
def test_binance_adapter_fetch_ohlcv_mocked(requests_mock):
    adapter = BinanceAdapter(testnet=True)
    requests_mock.get(..., json=[...])
    data = adapter.fetch_ohlcv("BTC/USDT", "1h", limit=10)
    assert len(data) == 10
    assert len(data[0]) == 6  # [time, open, high, low, close, volume]
```

> **Create detailed sub-plan for this phase** (WhiteBIT API integration is the most complex part).

---

## Phase 6: Database + Clean API

**Goal:** MongoDB repositories ported, clean FastAPI with split routers (not a 2538-line god object), all endpoints tested with mongomock + httpx.

**Files (api/):**

```
api/
├── server.py              # App factory, startup, CORS — max 100 lines
├── routers/
│   ├── strategies.py      # GET /strategies, GET /blocks
│   ├── backtest.py        # POST /backtest/start, GET /backtest/{id}, GET /backtest/{id}/status
│   ├── live.py            # POST /live/start, POST /live/stop, GET /live/status
│   └── results.py         # GET /results, GET /results/{id}/trades
├── models.py              # Pydantic request/response models
├── state.py               # In-process runtime state (active runs, WS connections)
├── ws.py                  # WebSocket /ws handler
└── services/
    ├── backtest_service.py # Orchestrates backtest run (extracted from old server.py)
    ├── live_service.py     # Orchestrates live run
    └── result_mapper.py    # Port from smc-bot
```

**API contract (core endpoints):**

```
GET  /strategies                → [{name, display_name, schema, tags}]
GET  /blocks                    → [{type, category, params_schema}]
POST /backtest/start            → {run_id}
GET  /backtest/{id}/status      → {status, progress, metrics}
GET  /backtest/{id}/trades      → [{trade details}]
POST /live/start                → {session_id}
POST /live/stop                 → {ok}
GET  /results                   → [{run summary}]
WS   /ws                        → log stream
```

> **Create detailed sub-plan for this phase** — especially the clean server.py split.

---

## Phase 7: Backtest Engine Integration

**Goal:** Full end-to-end: POST /backtest/start with block graph JSON → engine runs → results stored → GET /backtest/{id}/trades returns trades.

**Key integration test:**
```python
async def test_full_backtest_run(client: AsyncClient):
    payload = {
        "symbol": "BTC/USDT",
        "timeframes": ["1h"],
        "start_date": "2024-01-01",
        "end_date": "2024-03-01",
        "initial_capital": 10000,
        "strategy": {
            "blocks": [...],
            "connections": [...]
        }
    }
    r = await client.post("/backtest/start", json=payload)
    run_id = r.json()["run_id"]
    # poll status
    for _ in range(30):
        status = await client.get(f"/backtest/{run_id}/status")
        if status.json()["status"] == "completed":
            break
        await asyncio.sleep(0.5)
    trades = await client.get(f"/backtest/{run_id}/trades")
    assert trades.status_code == 200
```

---

## Phase 8: Dashboard Port + Parameter Sliders

**Goal:** React dashboard running, connects to clean API, renders strategy list, parameter slider form auto-generated from JSON Schema, runs backtest and shows results.

**Key new component:**

`dashboard/src/features/strategy-config/SchemaForm.tsx` — renders MUI form from JSON Schema:
- `type: integer` + `minimum/maximum` → MUI Slider
- `type: boolean` → MUI Switch
- `type: string`, `enum` → MUI Select
- Groups → MUI Accordion sections

**Port from smc-bot (with updated API calls):**
- Trade walkthrough chart (Plotly)
- Backtest history panel
- Live log stream (WebSocket)
- Results table

> **Create detailed sub-plan for this phase** — SchemaForm is the critical new component.

---

## Phase 9: Block Builder UI

**Goal:** Drag-drop strategy canvas using react-flow. User drags blocks from palette, connects them, saves as JSON graph, runs backtest.

**Library:** `react-flow` (MIT) — `npm install @xyflow/react`

**Components:**

```
dashboard/src/features/block-builder/
├── BlockBuilder.tsx           # Main canvas (ReactFlow)
├── BlockPalette.tsx           # Left sidebar — grouped blocks
├── BlockNode.tsx              # Custom node renderer per block type
├── BlockEdge.tsx              # Custom edge (connection line)
├── useBlockGraph.ts           # State: nodes, edges → JSON graph
├── BlockParamEditor.tsx       # Right panel — edit selected block params
└── SaveStrategyModal.tsx      # Name + save
```

**Block node types** registered in ReactFlow:
- `signal` — green header
- `filter` — blue header
- `entry` — yellow header
- `exit` — red header
- `risk` — purple header

> **Create detailed sub-plan for this phase** — react-flow integration requires careful state management.

---

## Phase 10: Live Trading Integration

**Goal:** Paper trading and sandbox live trading work end-to-end. WebSocket streams real-time prices to dashboard. Live monitor panel shows open positions, P&L.

**Modes:**
- `paper` — live market data + simulated execution (Backtrader live runner)
- `live_sandbox` — exchange testnet (Binance testnet / WhiteBIT sandbox)
- `live_real` — 🔜 future, not in this plan

**Key new components:**
- `api/routers/live.py` — start/stop/status endpoints
- `koval/engine/live_engine.py` — port from smc-bot `bt_live_engine.py`
- `dashboard/src/features/live-monitor/` — P&L panel, open positions, kill switch

> **Create detailed sub-plan for this phase** before executing.

---

## Phase 0 Execution Order Summary

Start with Phase 0 immediately after this plan is reviewed. Then execute phases in order — each phase's tests must pass before moving to the next.

```
Phase 0: Repo bootstrap          ← Execute now (init files ready in docs/koval-init/)
Phase 1: Core engine port        ← ~2 days
Phase 2: Declarative ABC + BT    ← ~3 days  
Phase 3: Block library           ← ~4 days (write sub-plan first)
Phase 4: Registry + assembler    ← ~3 days (write sub-plan first)
Phase 5: Exchange adapters       ← ~4 days (write sub-plan first)
Phase 6: DB + clean API          ← ~4 days (write sub-plan first)
Phase 7: Backtest integration    ← ~3 days
Phase 8: Dashboard port          ← ~4 days (write sub-plan first)
Phase 9: Block Builder UI        ← ~6 days (write sub-plan first)
Phase 10: Live trading           ← ~4 days (write sub-plan first)
```

**Total estimate:** ~8-10 weeks of focused development.
