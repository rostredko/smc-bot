"""
Tests for BaseEngine broker setup and core behavior.
BaseEngine is abstract; we test via BTBacktestEngine with mocked DataLoader.
"""
import unittest
from unittest.mock import MagicMock, patch
import pandas as pd
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.bt_backtest_engine import BTBacktestEngine
from strategies.bt_price_action import PriceActionStrategy


def _mock_df():
    return pd.DataFrame({
        "open": [100.0] * 100,
        "high": [105.0] * 100,
        "low": [95.0] * 100,
        "close": [101.0] * 100,
        "volume": [1000] * 100,
    }, index=pd.date_range("2024-01-01", periods=100, freq="h"))


@patch("engine.bt_backtest_engine.DataLoader")
class TestBaseEngineBrokerSetup(unittest.TestCase):
    """Test broker configuration from config."""

    def test_initial_capital_from_config(self, mock_dataloader_cls):
        mock_dataloader_cls.return_value.get_data.return_value = _mock_df()
        config = {
            "symbol": "BTC/USDT",
            "timeframes": ["1h"],
            "start_date": "2024-01-01",
            "end_date": "2024-01-31",
            "initial_capital": 50000,
        }
        engine = BTBacktestEngine(config)
        self.assertEqual(engine.cerebro.broker.getcash(), 50000)
        self.assertEqual(engine.cerebro.broker.getvalue(), 50000)

    def test_default_initial_capital_when_missing(self, mock_dataloader_cls):
        mock_dataloader_cls.return_value.get_data.return_value = _mock_df()
        config = {
            "symbol": "BTC/USDT",
            "timeframes": ["1h"],
            "start_date": "2024-01-01",
            "end_date": "2024-01-31",
        }
        engine = BTBacktestEngine(config)
        self.assertEqual(engine.cerebro.broker.getcash(), 10000)

    def test_commission_and_leverage_from_config(self, mock_dataloader_cls):
        mock_dataloader_cls.return_value.get_data.return_value = _mock_df()
        config = {
            "symbol": "BTC/USDT",
            "timeframes": ["1h"],
            "start_date": "2024-01-01",
            "end_date": "2024-01-31",
            "initial_capital": 10000,
            "commission": 0.001,
            "leverage": 5.0,
        }
        engine = BTBacktestEngine(config)
        engine.add_strategy(PriceActionStrategy, use_trend_filter=False, use_structure_filter=False, use_adx_filter=False, use_rsi_filter=False)
        engine.add_data()
        results = engine.run()
        self.assertIsNotNone(results)
        self.assertEqual(len(results), 1)

    def test_slippage_bps_configures_broker(self, mock_dataloader_cls):
        mock_dataloader_cls.return_value.get_data.return_value = _mock_df()
        config = {
            "symbol": "BTC/USDT",
            "timeframes": ["1h"],
            "start_date": "2024-01-01",
            "end_date": "2024-01-31",
            "slippage_bps": 2.5,
        }
        engine = BTBacktestEngine(config)
        self.assertAlmostEqual(engine.cerebro.broker.p.slip_perc, 0.00025)


@patch("engine.bt_backtest_engine.DataLoader")
class TestBaseEngineInitialState(unittest.TestCase):
    """Test initial state of engine."""

    def test_strategy_none_before_run(self, mock_dataloader_cls):
        mock_dataloader_cls.return_value.get_data.return_value = _mock_df()
        config = {"symbol": "BTC/USDT", "timeframes": ["1h"], "start_date": "2024-01-01", "end_date": "2024-01-31"}
        engine = BTBacktestEngine(config)
        self.assertIsNone(engine.strategy)

    def test_should_cancel_false_initially(self, mock_dataloader_cls):
        mock_dataloader_cls.return_value.get_data.return_value = _mock_df()
        config = {"symbol": "BTC/USDT", "timeframes": ["1h"], "start_date": "2024-01-01", "end_date": "2024-01-31"}
        engine = BTBacktestEngine(config)
        self.assertFalse(engine.should_cancel)

    def test_logger_exists(self, mock_dataloader_cls):
        mock_dataloader_cls.return_value.get_data.return_value = _mock_df()
        config = {"symbol": "BTC/USDT", "timeframes": ["1h"], "start_date": "2024-01-01", "end_date": "2024-01-31"}
        engine = BTBacktestEngine(config)
        self.assertIsNotNone(engine.logger)
        self.assertTrue(hasattr(engine.logger, "log"))


@patch("engine.bt_backtest_engine.DataLoader")
class TestBaseEngineAddStrategy(unittest.TestCase):
    """Test add_strategy adds strategy to Cerebro."""

    def test_add_strategy_then_run_returns_strategy_in_results(self, mock_dataloader_cls):
        mock_dataloader_cls.return_value.get_data.return_value = _mock_df()
        config = {
            "symbol": "BTC/USDT",
            "timeframes": ["1h"],
            "start_date": "2024-01-01",
            "end_date": "2024-01-31",
        }
        engine = BTBacktestEngine(config)
        engine.add_strategy(PriceActionStrategy, use_trend_filter=False, use_structure_filter=False, use_adx_filter=False, use_rsi_filter=False)
        engine.add_data()
        results = engine.run()
        self.assertIsInstance(results[0], PriceActionStrategy)


@patch("engine.bt_backtest_engine.DataLoader")
class TestBaseEngineTimeframeOrderingHelpers(unittest.TestCase):
    def test_ordered_timeframes_normalizes_mtf_order(self, mock_dataloader_cls):
        mock_dataloader_cls.return_value.get_data.return_value = _mock_df()
        engine = BTBacktestEngine({"symbol": "BTC/USDT", "timeframes": ["4h", "1h", "15m"]})

        self.assertEqual(engine._ordered_timeframes(["4h", "1h", "15m"]), ["15m", "1h", "4h"])
        self.assertEqual(engine._ordered_timeframes(["1h", "4h"]), ["1h", "4h"])


@patch("engine.bt_backtest_engine.DataLoader")
class TestBaseEngineRun(unittest.TestCase):
    """Test run() executes Cerebro."""

    def test_run_returns_list_of_strategies(self, mock_dataloader_cls):
        mock_dataloader_cls.return_value.get_data.return_value = _mock_df()
        config = {
            "symbol": "BTC/USDT",
            "timeframes": ["1h"],
            "start_date": "2024-01-01",
            "end_date": "2024-01-31",
        }
        engine = BTBacktestEngine(config)
        engine.add_strategy(PriceActionStrategy, use_trend_filter=False, use_structure_filter=False, use_adx_filter=False, use_rsi_filter=False)
        engine.add_data()
        results = engine.run()
        self.assertIsInstance(results, list)
        self.assertGreater(len(results), 0)


if __name__ == "__main__":
    unittest.main()
