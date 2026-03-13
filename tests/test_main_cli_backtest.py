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
    kwargs = engine.add_strategy.call_args.kwargs
    assert kwargs["risk_per_trade"] == 1.0
    assert kwargs["position_cap_adverse"] == 0.5


@patch("main.BTBacktestEngine")
def test_run_backtest_from_config_falls_back_to_price_action_for_unknown_strategy(engine_cls):
    engine = MagicMock()
    engine.run_backtest.return_value = {}
    engine_cls.return_value = engine

    main.run_backtest_from_config(_minimal_config("unknown_strategy"))

    strategy_cls = engine.add_strategy.call_args.args[0]
    assert strategy_cls is PriceActionStrategy


@patch("main.BTBacktestEngine")
def test_run_backtest_from_config_injects_runtime_controls(engine_cls):
    engine = MagicMock()
    engine.run_backtest.return_value = {}
    engine_cls.return_value = engine

    config = _minimal_config("bt_price_action")
    config.update({
        "risk_per_trade": 1.5,
        "leverage": 7.0,
        "trailing_stop_distance": 0.03,
        "breakeven_trigger_r": 1.1,
        "dynamic_position_sizing": False,
        "max_drawdown": 25.0,
        "position_cap_adverse": 0.7,
        "funding_rate_per_8h": 0.0001,
    })

    main.run_backtest_from_config(config)

    kwargs = engine.add_strategy.call_args.kwargs
    assert kwargs["risk_per_trade"] == 1.5
    assert kwargs["leverage"] == 7.0
    assert kwargs["trailing_stop_distance"] == 0.03
    assert kwargs["breakeven_trigger_r"] == 1.1
    assert kwargs["dynamic_position_sizing"] is False
    assert kwargs["max_drawdown"] == 25.0
    assert kwargs["position_cap_adverse"] == 0.7
    assert kwargs["funding_rate_per_8h"] == 0.0001
