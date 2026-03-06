import os
import sys
from unittest.mock import MagicMock, patch

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

import main
from strategies.bt_price_action import PriceActionStrategy
from strategies.fast_test_strategy import FastTestStrategy


def _minimal_config(strategy_name: str):
    return {
        "initial_capital": 10000,
        "symbol": "BTC/USDT",
        "start_date": "2024-01-01",
        "end_date": "2024-01-31",
        "strategy": strategy_name,
        "strategy_config": {},
    }


@patch("main.BTBacktestEngine")
def test_run_backtest_from_config_uses_fast_test_strategy(engine_cls):
    engine = MagicMock()
    engine.run_backtest.return_value = {}
    engine_cls.return_value = engine

    main.run_backtest_from_config(_minimal_config("fast_test_strategy"))

    strategy_cls = engine.add_strategy.call_args.args[0]
    assert strategy_cls is FastTestStrategy


@patch("main.BTBacktestEngine")
def test_run_backtest_from_config_falls_back_to_price_action_for_unknown_strategy(engine_cls):
    engine = MagicMock()
    engine.run_backtest.return_value = {}
    engine_cls.return_value = engine

    main.run_backtest_from_config(_minimal_config("unknown_strategy"))

    strategy_cls = engine.add_strategy.call_args.args[0]
    assert strategy_cls is PriceActionStrategy
