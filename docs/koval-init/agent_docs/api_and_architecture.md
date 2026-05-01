# API & Architecture Boundaries — Koval

## The three-layer rule

```
koval/          →    api/services/    →    api/routers/
(domain logic)       (orchestration)       (HTTP/WS)
```

- `koval/` has zero imports from `api/` — ever
- `api/routers/` calls `api/services/` — never calls `koval/engine/` directly
- `api/services/` owns lifecycle orchestration and calls `koval/engine/`

## API ↔ Engine contract

**Request → Engine config:**

```python
# api/services/backtest_service.py
async def start_backtest(request: BacktestRequest) -> str:
    graph = request.strategy  # BlockGraph JSON
    strategy_instance = assemble_from_graph(graph)  # koval/strategy/block_assembler
    adapted_class = make_bt_strategy_class(strategy_instance, **request.risk_params)
    run_id = await asyncio.get_event_loop().run_in_executor(
        None, run_backtest_sync, adapted_class, request
    )
    return run_id
```

**Engine results → API response:**

Always through `api/services/result_mapper.py`. Never shape results inline in routers.

## State: in-process vs durable

| What | Where | Survives restart? |
|------|-------|-------------------|
| Active backtest handle | `api/state.py` | No |
| Active live session | `api/state.py` | No |
| WS connections | `api/state.py` | No |
| Backtest results | MongoDB | Yes |
| Strategy block graphs | MongoDB | Yes |
| OHLCV cache | `data_cache/` volume | Yes |

## WebSocket `/ws` protocol

Client connects → receives log lines as JSON:
```json
{"level": "INFO", "message": "Backtest started", "run_id": "abc123", "ts": 1714567890}
```

Client sends:
```json
{"action": "subscribe", "run_id": "abc123"}
{"action": "unsubscribe", "run_id": "abc123"}
```

## API versioning

No versioning in v1. All routes under `/` directly. Add `/v2/` prefix if breaking changes are needed in the future.
