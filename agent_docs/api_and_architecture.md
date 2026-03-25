# API & architecture pointers

Authoritative detail is in [PROJECT_STRUCTURE.md](../PROJECT_STRUCTURE.md). This file only lists **where to look**.

## HTTP entry

- **FastAPI app:** `web-dashboard/server.py` — all routes, backtest/live tasks, WebSocket `/ws`.

## Layers

| Layer | Path | Notes |
|--------|------|--------|
| Pydantic models | `web-dashboard/api/models.py` | `BacktestConfig`, `BacktestRequest`, `BacktestStatus` |
| Shared runtime state | `web-dashboard/api/state.py` | Active runs, connections, console buffer |
| Log capture | `web-dashboard/api/logging_handlers.py` | Run log collectors, attach/detach |
| Strategy resolution | `web-dashboard/services/strategy_runtime.py` | `resolve_strategy_class`, `build_runtime_strategy_config`, optimize config |
| Result shaping | `web-dashboard/services/result_mapper.py` | Trades, equity, metrics for API/DB |

## Engine & strategies

- **Engines:** `engine/bt_backtest_engine.py`, `engine/bt_live_engine.py`, `engine/base_engine.py`
- **Data:** `engine/data_loader.py`, `engine/live_ws_client.py`, `engine/live_data_feed.py`
- **Helpers:** `engine/timeframe_utils.py` (LTF-first ordering), `engine/utils.py`, `engine/optimize_context.py` (optimize logging context)
- **Strategies:** `strategies/base_strategy.py`, `strategies/bt_price_action.py`, `strategies/market_structure.py`

## Persistence

- `db/connection.py`, `db/repositories/*.py` — `backtests`, `user_configs`, `app_config`

When adding endpoints, keep models and repositories consistent and extend tests under `tests/`.
