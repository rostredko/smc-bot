# Release Notes v1.0.0 — Live Trading & Dashboard


- Generated at (UTC): 2026-03-16T20:59:06+00:00
- Target branch: `master`
- Commit range: `61a239d908b2..c02d11e778ad`

## Summary
- Commits included: 12
- Contributors: 1
- Files touched (unique): 112
- Cumulative line changes: `+14290 / -3344`

## Change Areas
- **Test Suite**: 34 file(s)
- **Frontend UI**: 26 file(s)
- **Trading Engine**: 15 file(s)
- **Backend API and Dashboard Runtime**: 12 file(s)
- **Repository Root**: 9 file(s)
- **Strategies and Risk**: 6 file(s)
- **Database Layer**: 3 file(s)
- **Documentation**: 2 file(s)
- **tools**: 2 file(s)
- **.githooks**: 1 file(s)
- **CI/CD**: 1 file(s)
- **Dependencies**: 1 file(s)

## Change Types
- **Other Changes**: 12 commit(s)

## Commit-by-Commit Details
### 4ecf53456c86 - Refactor project structure and enhance configuration management
- Author: rostredko <rost.redko@gmail.com>
- Date: 2026-03-05T21:10:22+02:00
- Type: Other Changes
- Scope: .githooks, Backend API and Dashboard Runtime, CI/CD, Database Layer, Documentation, Frontend UI, Repository Root, Strategies and Risk, Test Suite, Trading Engine, tools
- Diff footprint: 69 file(s), `+5942 / -1772`
- Files:
  - `.githooks/pre-push` (`+66 / -0`)
  - `.github/workflows/ci.yml` (`+2 / -0`)
  - `.gitignore` (`+2 / -3`)
  - `Dockerfile.frontend` (`+2 / -0`)
  - `PROJECT_STRUCTURE.md` (`+343 / -328`)
  - `README.md` (`+59 / -170`)
  - `RELEASE_NOTES_WORKFLOW.md` (`+41 / -0`)
  - `VERSION` (`+1 / -0`)
  - `db/connection.py` (`+24 / -0`)
  - `db/repositories/backtest_repository.py` (`+17 / -3`)
  - `db/repositories/user_config_repository.py` (`+39 / -1`)
  - `docker-compose.yml` (`+8 / -2`)
  - `engine/base_engine.py` (`+6 / -0`)
  - `engine/bt_analyzers.py` (`+13 / -24`)
  - `engine/bt_backtest_engine.py` (`+27 / -41`)
  - `engine/bt_live_engine.py` (`+221 / -6`)
  - `engine/bt_oco_patch.py` (`+146 / -0`)
  - `engine/data_loader.py` (`+389 / -123`)
  - `engine/live_data_feed.py` (`+84 / -0`)
  - `engine/live_ws_client.py` (`+154 / -0`)
  - `engine/logger.py` (`+36 / -2`)
  - `engine/trade_narrator.py` (`+123 / -0`)
  - `pytest.ini` (`+1 / -0`)
  - `strategies/base_strategy.py` (`+153 / -45`)
  - `strategies/bt_price_action.py` (`+136 / -189`)
  - `strategies/fast_test_strategy.py` (`+223 / -0`)
  - `strategies/helpers/narrative_generator.py` (`+0 / -106`)
  - `strategies/helpers/risk_manager.py` (`+32 / -47`)
  - `tests/conftest.py` (`+4 / -0`)
  - `tests/test_backtest_repository_live_flag.py` (`+19 / -0`)
  - ... 39 more file(s) omitted

### b851fcfd6724 - Implement WebSocket logging queue, backtest cancellation, OHLCV cache clearing, and new strategy parameters with corresponding tests.
- Author: rostredko <rost.redko@gmail.com>
- Date: 2026-03-06T18:23:46+02:00
- Type: Other Changes
- Scope: Backend API and Dashboard Runtime, Frontend UI, Repository Root, Strategies and Risk, Test Suite, Trading Engine
- Diff footprint: 32 file(s), `+1265 / -207`
- Files:
  - `RELEASE_NOTES_WORKFLOW.md` (`+0 / -41`)
  - `engine/bt_backtest_engine.py` (`+62 / -1`)
  - `engine/data_loader.py` (`+51 / -10`)
  - `engine/logger.py` (`+15 / -0`)
  - `main.py` (`+16 / -4`)
  - `strategies/base_strategy.py` (`+5 / -4`)
  - `strategies/bt_price_action.py` (`+7 / -8`)
  - `strategies/fast_test_strategy.py` (`+4 / -4`)
  - `strategies/helpers/risk_manager.py` (`+37 / -14`)
  - `tests/conftest.py` (`+1 / -4`)
  - `tests/test_base_strategy_notify_order.py` (`+49 / -0`)
  - `tests/test_bt_backtest_engine.py` (`+39 / -0`)
  - `tests/test_data_loader.py` (`+17 / -5`)
  - `tests/test_engine_logger.py` (`+10 / -0`)
  - `tests/test_full_e2e_price_action.py` (`+0 / -1`)
  - `tests/test_integration_talib.py` (`+5 / -0`)
  - `tests/test_live_api_controls.py` (`+441 / -2`)
  - `tests/test_live_e2e.py` (`+0 / -1`)
  - `tests/test_main_cli_backtest.py` (`+45 / -0`)
  - `tests/test_result_backfill.py` (`+6 / -0`)
  - `tests/test_result_mapper_service.py` (`+21 / -0`)
  - `tests/test_risk_manager.py` (`+24 / -0`)
  - `web-dashboard/server.py` (`+266 / -67`)
  - `web-dashboard/services/result_mapper.py` (`+20 / -3`)
  - `web-dashboard/src/app/providers/config/ConfigProvider.tsx` (`+14 / -2`)
  - `web-dashboard/src/app/providers/console/ConsoleProvider.tsx` (`+11 / -0`)
  - `web-dashboard/src/entities/trade/ui/TradeAnalysisChart.tsx` (`+64 / -32`)
  - `web-dashboard/src/shared/const/tooltips.ts` (`+0 / -1`)
  - `web-dashboard/src/shared/lib/validation.test.ts` (`+5 / -1`)
  - `web-dashboard/src/shared/lib/validation.ts` (`+29 / -0`)
  - ... 2 more file(s) omitted

### 5d2e9992fd13 - Enhance TradeDetailsModal with navigation for multiple trades
- Author: rostredko <rost.redko@gmail.com>
- Date: 2026-03-06T18:35:11+02:00
- Type: Other Changes
- Scope: Frontend UI
- Diff footprint: 3 file(s), `+69 / -6`
- Files:
  - `web-dashboard/src/features/trade-details/ui/TradeDetailsModal.tsx` (`+59 / -3`)
  - `web-dashboard/src/widgets/backtest-history/ui/BacktestHistoryList.tsx` (`+7 / -2`)
  - `web-dashboard/src/widgets/results-panel/ui/ResultsPanel.tsx` (`+3 / -1`)

### 62a433eb5ff1 - Enable sorting for backtest history records by various fields in the UI, API, and database.
- Author: rostredko <rost.redko@gmail.com>
- Date: 2026-03-06T18:55:51+02:00
- Type: Other Changes
- Scope: Backend API and Dashboard Runtime, Database Layer, Frontend UI
- Diff footprint: 4 file(s), `+92 / -15`
- Files:
  - `db/repositories/backtest_repository.py` (`+12 / -2`)
  - `web-dashboard/server.py` (`+12 / -2`)
  - `web-dashboard/src/widgets/backtest-history/api/historyApi.ts` (`+6 / -2`)
  - `web-dashboard/src/widgets/backtest-history/ui/BacktestHistoryList.tsx` (`+62 / -9`)

### 496fdd57b9f0 - Enhance chart data handling and configuration in trading features
- Author: rostredko <rost.redko@gmail.com>
- Date: 2026-03-06T20:20:27+02:00
- Type: Other Changes
- Scope: Backend API and Dashboard Runtime, Frontend UI, Test Suite
- Diff footprint: 4 file(s), `+133 / -19`
- Files:
  - `tests/test_live_api_controls.py` (`+83 / -0`)
  - `web-dashboard/server.py` (`+19 / -5`)
  - `web-dashboard/src/entities/trade/ui/TradeOHLCVChart.tsx` (`+21 / -9`)
  - `web-dashboard/src/features/trade-details/ui/TradeDetailsModal.tsx` (`+10 / -5`)

### 960c9515d145 - Implement MarketStructure indicator and enhance PriceActionStrategy with structural filters
- Author: rostredko <rost.redko@gmail.com>
- Date: 2026-03-07T00:02:47+02:00
- Type: Other Changes
- Scope: Backend API and Dashboard Runtime, Frontend UI, Strategies and Risk, Test Suite
- Diff footprint: 13 file(s), `+1188 / -132`
- Files:
  - `strategies/bt_price_action.py` (`+455 / -34`)
  - `tests/test_base_engine.py` (`+3 / -3`)
  - `tests/test_bt_analyzers.py` (`+5 / -5`)
  - `tests/test_bt_backtest_engine.py` (`+6 / -6`)
  - `tests/test_full_e2e_price_action.py` (`+1 / -0`)
  - `tests/test_integration_talib.py` (`+11 / -15`)
  - `tests/test_live_api_controls.py` (`+112 / -0`)
  - `tests/test_price_action_extended.py` (`+50 / -11`)
  - `tests/test_strategy_integration.py` (`+2 / -4`)
  - `web-dashboard/server.py` (`+279 / -14`)
  - `web-dashboard/src/entities/trade/ui/TradeOHLCVChart.tsx` (`+157 / -18`)
  - `web-dashboard/src/features/trade-details/ui/TradeDetailsModal.tsx` (`+107 / -17`)
  - `web-dashboard/src/widgets/backtest-history/ui/BacktestHistoryList.tsx` (`+0 / -5`)

### f3d75893e836 - Enhance ConfigProvider and ConfigPanel with reset functionality and update TradeOHLCVChart interaction
- Author: rostredko <rost.redko@gmail.com>
- Date: 2026-03-07T14:56:38+02:00
- Type: Other Changes
- Scope: Frontend UI
- Diff footprint: 4 file(s), `+41 / -3`
- Files:
  - `web-dashboard/src/app/providers/config/ConfigProvider.tsx` (`+16 / -1`)
  - `web-dashboard/src/entities/trade/ui/TradeOHLCVChart.tsx` (`+2 / -0`)
  - `web-dashboard/src/widgets/backtest-history/ui/BacktestHistoryList.tsx` (`+21 / -1`)
  - `web-dashboard/src/widgets/config-panel/ui/ConfigPanel.tsx` (`+2 / -1`)

### 7f03f10e9a31 - Implement funding adjustments and enhance trade metrics in backtesting and live trading engines
- Author: rostredko <rost.redko@gmail.com>
- Date: 2026-03-13T18:22:46+02:00
- Type: Other Changes
- Scope: Backend API and Dashboard Runtime, Documentation, Frontend UI, Repository Root, Strategies and Risk, Test Suite, Trading Engine
- Diff footprint: 33 file(s), `+1514 / -297`
- Files:
  - `PROJECT_STRUCTURE.md` (`+22 / -7`)
  - `README.md` (`+2 / -0`)
  - `engine/base_engine.py` (`+47 / -0`)
  - `engine/bt_analyzers.py` (`+12 / -0`)
  - `engine/bt_backtest_engine.py` (`+159 / -15`)
  - `engine/bt_live_engine.py` (`+26 / -38`)
  - `engine/data_loader.py` (`+26 / -19`)
  - `engine/logger.py` (`+40 / -30`)
  - `engine/trade_metrics.py` (`+47 / -0`)
  - `main.py` (`+15 / -1`)
  - `strategies/base_strategy.py` (`+127 / -1`)
  - `strategies/bt_price_action.py` (`+100 / -45`)
  - `strategies/fast_test_strategy.py` (`+1 / -0`)
  - `tests/test_base_engine.py` (`+22 / -0`)
  - `tests/test_base_strategy_signal_thesis.py` (`+47 / -0`)
  - `tests/test_bt_analyzers.py` (`+37 / -0`)
  - `tests/test_bt_backtest_engine.py` (`+66 / -1`)
  - `tests/test_bt_live_engine.py` (`+25 / -2`)
  - `tests/test_data_loader.py` (`+6 / -0`)
  - `tests/test_engine_logger.py` (`+38 / -2`)
  - `tests/test_live_api_controls.py` (`+39 / -0`)
  - `tests/test_main_cli_backtest.py` (`+34 / -0`)
  - `tests/test_market_structure_indicator.py` (`+71 / -0`)
  - `tests/test_price_action_extended.py` (`+38 / -0`)
  - `tests/test_strategy_runtime_service.py` (`+4 / -1`)
  - `tests/test_trade_metrics.py` (`+37 / -0`)
  - `web-dashboard/server.py` (`+152 / -85`)
  - `web-dashboard/services/strategy_runtime.py` (`+2 / -1`)
  - `web-dashboard/src/widgets/backtest-history/ui/BacktestHistoryList.test.tsx` (`+94 / -0`)
  - `web-dashboard/src/widgets/backtest-history/ui/BacktestHistoryList.tsx` (`+35 / -2`)
  - ... 3 more file(s) omitted

### 80bda0491cfa - Add new filters and parameters to PriceActionStrategy for enhanced trading conditions
- Author: rostredko <rost.redko@gmail.com>
- Date: 2026-03-13T19:20:28+02:00
- Type: Other Changes
- Scope: Backend API and Dashboard Runtime, Frontend UI, Strategies and Risk, Test Suite
- Diff footprint: 5 file(s), `+247 / -0`
- Files:
  - `strategies/bt_price_action.py` (`+170 / -0`)
  - `tests/test_live_api_controls.py` (`+6 / -0`)
  - `tests/test_price_action_extended.py` (`+59 / -0`)
  - `web-dashboard/server.py` (`+6 / -0`)
  - `web-dashboard/src/shared/const/tooltips.ts` (`+6 / -0`)

### 3d8955c495df - Refactor docker-compose.override.yml for stability and update main.py with execution settings
- Author: rostredko <rost.redko@gmail.com>
- Date: 2026-03-15T19:28:17+02:00
- Type: Other Changes
- Scope: Backend API and Dashboard Runtime, Dependencies, Documentation, Frontend UI, Repository Root, Strategies and Risk, Test Suite, Trading Engine
- Diff footprint: 44 file(s), `+3183 / -517`
- Files:
  - `PROJECT_STRUCTURE.md` (`+39 / -14`)
  - `README.md` (`+27 / -2`)
  - `deps/requirements.txt` (`+2 / -1`)
  - `docker-compose.dev.yml` (`+61 / -0`)
  - `docker-compose.override.yml` (`+11 / -18`)
  - `engine/base_engine.py` (`+3 / -2`)
  - `engine/binance_account_client.py` (`+69 / -0`)
  - `engine/bt_live_engine.py` (`+11 / -7`)
  - `engine/execution_settings.py` (`+170 / -0`)
  - `engine/live_ws_client.py` (`+187 / -122`)
  - `main.py` (`+27 / -10`)
  - `strategies/bt_price_action.py` (`+259 / -66`)
  - `strategies/market_structure.py` (`+140 / -0`)
  - `tests/test_api.py` (`+53 / -1`)
  - `tests/test_base_engine.py` (`+13 / -0`)
  - `tests/test_base_strategy_signal_thesis.py` (`+3 / -3`)
  - `tests/test_binance_account_client.py` (`+60 / -0`)
  - `tests/test_bt_backtest_engine.py` (`+2 / -1`)
  - `tests/test_bt_live_engine.py` (`+6 / -35`)
  - `tests/test_execution_settings.py` (`+89 / -0`)
  - `tests/test_live_api_controls.py` (`+174 / -2`)
  - `tests/test_live_e2e.py` (`+1 / -0`)
  - `tests/test_live_ws_client.py` (`+201 / -0`)
  - `tests/test_main_cli_backtest.py` (`+29 / -0`)
  - `tests/test_market_structure_indicator.py` (`+26 / -0`)
  - `tests/test_price_action_extended.py` (`+103 / -26`)
  - `tests/test_strategy_runtime_service.py` (`+56 / -1`)
  - `web-dashboard/requirements.txt` (`+1 / -0`)
  - `web-dashboard/server.py` (`+374 / -144`)
  - `web-dashboard/services/strategy_runtime.py` (`+121 / -7`)
  - ... 14 more file(s) omitted

### bdb63da22fbd - Refactor strategy config panel UI to group parameters into 'Structure & POI' and 'Advanced Strategy Parameters' sections, update documentation, and refine chart data fetching dependencies.
- Author: rostredko <rost.redko@gmail.com>
- Date: 2026-03-15T20:26:04+02:00
- Type: Other Changes
- Scope: Documentation, Frontend UI
- Diff footprint: 8 file(s), `+217 / -22`
- Files:
  - `PROJECT_STRUCTURE.md` (`+2 / -0`)
  - `README.md` (`+1 / -0`)
  - `web-dashboard/src/entities/trade/ui/TradeOHLCVChart.tsx` (`+27 / -5`)
  - `web-dashboard/src/shared/const/tooltips.ts` (`+2 / -2`)
  - `web-dashboard/src/widgets/backtest-history/ui/BacktestHistoryList.test.tsx` (`+56 / -1`)
  - `web-dashboard/src/widgets/backtest-history/ui/BacktestHistoryList.tsx` (`+0 / -1`)
  - `web-dashboard/src/widgets/config-panel/ui/ConfigPanel.test.tsx` (`+79 / -1`)
  - `web-dashboard/src/widgets/config-panel/ui/ConfigPanel.tsx` (`+50 / -12`)

### c02d11e778ad - Update docker-compose configuration and enhance main.py with project structure adjustments
- Author: rostredko <rost.redko@gmail.com>
- Date: 2026-03-16T22:55:18+02:00
- Type: Other Changes
- Scope: Backend API and Dashboard Runtime, Documentation, Repository Root, Test Suite, Trading Engine
- Diff footprint: 16 file(s), `+399 / -354`
- Files:
  - `PROJECT_STRUCTURE.md` (`+19 / -10`)
  - `README.md` (`+11 / -8`)
  - `docker-compose.yml` (`+1 / -1`)
  - `engine/base_engine.py` (`+2 / -21`)
  - `engine/bt_backtest_engine.py` (`+7 / -13`)
  - `engine/timeframe_utils.py` (`+29 / -0`)
  - `engine/utils.py` (`+8 / -0`)
  - `main.py` (`+4 / -16`)
  - `tests/conftest.py` (`+2 / -93`)
  - `tests/test_engine_utils.py` (`+21 / -0`)
  - `tests/test_timeframe_utils.py` (`+43 / -0`)
  - `web-dashboard/api/__init__.py` (`+1 / -0`)
  - `web-dashboard/api/logging_handlers.py` (`+111 / -0`)
  - `web-dashboard/api/models.py` (`+57 / -0`)
  - `web-dashboard/api/state.py` (`+47 / -0`)
  - `web-dashboard/server.py` (`+36 / -192`)
