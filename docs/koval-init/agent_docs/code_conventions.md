# Code Conventions — Koval

## Python

### General

- Python 3.11+ — use `match`, `TypeAlias`, `Self`, `X | Y` union syntax
- Type hints everywhere — no untyped public functions
- Pydantic v2 — use `model_validate`, `model_dump`, `model_json_schema`
- Ruff for linting and formatting — `ruff check . && ruff format .`
- Max line length: 100

### Naming

- Files: `snake_case.py`
- Classes: `PascalCase`
- Functions/variables: `snake_case`
- Constants: `UPPER_SNAKE_CASE`
- Private methods: `_single_underscore`

### Block functions — pure function signature

```python
# Good — pure function, no state
def check_rsi(rsi_value: float, config: dict) -> bool:
    return rsi_value < config.get("rsi_oversold", 30)

# Bad — side effects, state mutation
def check_rsi(self) -> bool:  # no self in blocks
    self.state = ...
```

### DeclarativeStrategy subclasses

```python
from koval.strategy.base.declarative import DeclarativeStrategy
from koval.strategy.base.trade_setup import TradeSetup

class MyStrategy(DeclarativeStrategy):
    def should_long(self) -> bool:
        return self.indicator("ema", period=9) > self.indicator("ema", period=21)

    def go_long(self) -> TradeSetup:
        atr = self.indicator("atr")
        return TradeSetup(
            direction='long',
            entry_price=self.close,
            stop_loss=self.close - 2 * atr,
            entry_type='market',
            why_entry=["EMA9 > EMA21"],
        )

    def filters(self) -> list:
        return [
            lambda: self.indicator("adx") > self.config.get("adx_threshold", 25),
        ]
```

### Never import backtrader outside adapters

```python
# NEVER in koval/strategy/, koval/blocks/, koval/engine/, api/
import backtrader as bt  # ← FORBIDDEN outside koval/adapters/backtrader/

# Use the factory instead
from koval.adapters.backtrader.bt_adapter import make_bt_strategy_class
AdaptedClass = make_bt_strategy_class(MyStrategy, risk_per_trade=1.0)
```

### GPL-3.0 file header

Every file in `koval/adapters/backtrader/` must start with:
```python
# SPDX-License-Identifier: GPL-3.0-or-later
```

### Logging

```python
from koval.engine.logger import get_logger
logger = get_logger(__name__)

logger.info("Starting backtest run_id=%s", run_id)
logger.warning("Strategy not found: %s", name)
logger.error("Backtest failed: %s", exc, exc_info=True)
```

### Async patterns

```python
# FastAPI route handlers — async
@router.post("/backtest/start")
async def start_backtest(config: BacktestRequest) -> BacktestStartResponse:
    ...

# CPU-bound work (Backtrader run) — run in thread pool
import asyncio
result = await asyncio.get_event_loop().run_in_executor(None, run_backtest_sync, config)
```

## React / TypeScript

### General

- TypeScript strict mode — no `any` without explicit justification
- MUI v5 component library — never use plain HTML elements where MUI exists
- `sx` prop for one-off styles; `styled()` only for components used in 2+ files
- Functional components + hooks only — no class components

### Feature Slice Design (FSD)

```
src/
├── features/      ← New features go here
├── entities/      ← Domain UI components (TradeCard, StrategyBadge)
├── shared/        ← API client, design tokens, reusable primitives
└── app/           ← Providers, router
```

### Block Builder conventions

- `BlockNode.tsx` renders a single block — receives `data` prop from react-flow
- `useBlockGraph.ts` owns the node/edge state and exposes `toJSON(): BlockGraph`
- Block categories: `signal`, `filter`, `entry`, `exit`, `risk` — each has its own color token

### API client

```typescript
// shared/api/client.ts — single source for all API calls
import axios from 'axios'
const api = axios.create({ baseURL: import.meta.env.VITE_API_URL ?? 'http://localhost:8000' })
export default api
```

### Component naming

- Files: `PascalCase.tsx`
- Hooks: `useCamelCase.ts`
- Types: `PascalCase` (no `I` prefix for interfaces)

### MUI theme tokens (do not hardcode colors)

```tsx
// Good
<Box sx={{ bgcolor: 'background.paper', color: 'text.primary' }} />

// Bad
<Box sx={{ bgcolor: '#1e1e1e', color: '#ffffff' }} />
```
