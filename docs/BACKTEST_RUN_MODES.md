# Backtest run modes

Configured via `BacktestConfig.run_mode` in `web-dashboard/api/models.py` and enforced in `web-dashboard/server.py` when starting a backtest.

## `single` (default)

One backtest run with the provided `strategy_config` and timeframes. Uses `BTBacktestEngine` standard path.

## `optimize`

Grid search over whitelisted strategy parameters. Validation: `web-dashboard/server.py` (`_validate_optimize_params`).

- **Required keys in `opt_params`** (each must be an array of **exactly 3** numeric values):

  - `risk_reward_ratio` (each ≥ 0)
  - `sl_buffer_atr` (each > 0)
  - `trailing_stop_distance` (each ≥ 0)

- **Cartesian product** of those three lists defines the search space (default 3×3×3 = **27** combinations).

- **`opt_target_metric`:** `sharpe_ratio` or `profit_factor` (see `BacktestConfig`).

- **Optional `opt_timeframes`:** when set, multi-timeframe optimization runs per primary/secondary pair (see `server.py` backtest task for `opt_timeframes` handling).

Runtime strategy config for optimize is built in `web-dashboard/services/strategy_runtime.py` (`build_opt_strategy_config`).

## Persistence

Optimize results are mapped via `web-dashboard/services/result_mapper.py` (`build_optimization_metrics_doc` and related paths). Tests: `tests/test_optimize_save_single_parity.py`.
