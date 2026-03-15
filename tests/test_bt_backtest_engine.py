"""
Comprehensive tests for engine/bt_backtest_engine.py.
Covers SMCDataFeed, add_data, run_backtest, metrics, and edge cases.
"""
import unittest
from unittest.mock import ANY, MagicMock, patch
import backtrader as bt
import pandas as pd
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.bt_backtest_engine import BTBacktestEngine, SMCDataFeed
from strategies.bt_price_action import PriceActionStrategy


def _mock_ohlcv_df(rows=100):
    return pd.DataFrame({
        "open": [100.0] * rows,
        "high": [105.0] * rows,
        "low": [95.0] * rows,
        "close": [101.0] * rows,
        "volume": [1000] * rows,
    }, index=pd.date_range("2024-01-01", periods=rows, freq="h"))


class _OpenAtEndStrategy(bt.Strategy):
    """Opens once and intentionally leaves the position open into the last bar."""

    def __init__(self):
        self.order = None

    def notify_order(self, order):
        if order.status in (order.Completed, order.Canceled, order.Margin, order.Rejected):
            self.order = None

    def next(self):
        if self.order or self.position:
            return
        if len(self) == 3:
            self.order = self.buy(size=1)


@patch("engine.bt_backtest_engine.DataLoader")
class TestSMCDataFeed(unittest.TestCase):
    """Test SMCDataFeed column mapping."""

    def test_params_explicit_ohlcv_mapping(self, mock_dataloader_cls):
        dummy = pd.DataFrame({"open": [], "high": [], "low": [], "close": [], "volume": []})
        feed = SMCDataFeed(dataname=dummy)
        self.assertIsNone(feed.p.datetime)
        self.assertEqual(feed.p.open, -1)
        self.assertEqual(feed.p.high, -1)
        self.assertEqual(feed.p.low, -1)
        self.assertEqual(feed.p.close, -1)
        self.assertEqual(feed.p.volume, -1)


@patch("engine.bt_backtest_engine.DataLoader")
class TestBTBacktestEngineInit(unittest.TestCase):
    """Test engine initialization."""

    def test_closed_trades_empty_on_init(self, mock_dataloader_cls):
        mock_dataloader_cls.return_value = MagicMock()
        engine = BTBacktestEngine({"symbol": "BTC/USDT", "timeframes": ["1h"]})
        self.assertEqual(engine.closed_trades, [])

    def test_data_loader_uses_config_exchange(self, mock_dataloader_cls):
        engine = BTBacktestEngine({
            "symbol": "ETH/USDT",
            "timeframes": ["4h"],
            "exchange": "bybit",
            "exchange_type": "spot",
        })
        mock_dataloader_cls.assert_called_once_with(
            exchange_name="bybit",
            exchange_type="spot",
            log_level=ANY,
        )


@patch("engine.bt_backtest_engine.DataLoader")
class TestBacktestCancellation(unittest.TestCase):
    """Test cooperative cancellation behavior."""

    def test_cancel_is_idempotent_and_calls_runstop_once(self, mock_dataloader_cls):
        mock_dataloader_cls.return_value = MagicMock()
        engine = BTBacktestEngine({"symbol": "BTC/USDT", "timeframes": ["1h"]})
        engine.cerebro.runstop = MagicMock()

        engine.cancel()
        engine.cancel()

        self.assertTrue(engine.should_cancel)
        engine.cerebro.runstop.assert_called_once()

    def test_run_backtest_returns_cancelled_when_flag_set_before_start(self, mock_dataloader_cls):
        mock_dataloader_cls.return_value = MagicMock()
        engine = BTBacktestEngine({"symbol": "BTC/USDT", "timeframes": ["1h"]})
        engine.should_cancel = True

        with patch.object(engine, "add_data") as add_data_mock:
            metrics = engine.run_backtest()

        self.assertEqual(metrics, {"cancelled": True})
        add_data_mock.assert_not_called()

    def test_run_backtest_returns_cancelled_if_flag_set_after_data_load(self, mock_dataloader_cls):
        mock_dataloader_cls.return_value = MagicMock()
        engine = BTBacktestEngine({"symbol": "BTC/USDT", "timeframes": ["1h"]})

        def _set_cancel():
            engine.should_cancel = True

        with patch.object(engine, "add_data", side_effect=_set_cancel):
            metrics = engine.run_backtest()

        self.assertEqual(metrics, {"cancelled": True})


@patch("engine.bt_backtest_engine.DataLoader")
class TestAddData(unittest.TestCase):
    """Test add_data behavior."""

    def test_symbol_and_dates_passed_to_loader(self, mock_dataloader_cls):
        mock_loader = MagicMock()
        mock_loader.get_data.return_value = _mock_ohlcv_df()
        mock_dataloader_cls.return_value = mock_loader

        config = {
            "symbol": "ETH/USDT",
            "timeframes": ["4h"],
            "start_date": "2023-06-01",
            "end_date": "2023-06-30",
        }
        engine = BTBacktestEngine(config)
        engine.add_data()

        mock_loader.get_data.assert_called_once_with("ETH/USDT", "4h", "2023-06-01", "2023-06-30")

    def test_empty_df_skipped_no_crash(self, mock_dataloader_cls):
        mock_loader = MagicMock()
        mock_loader.get_data.return_value = pd.DataFrame()
        mock_dataloader_cls.return_value = mock_loader

        engine = BTBacktestEngine({"symbol": "BTC/USDT", "timeframes": ["1h"]})
        engine.add_data()

        self.assertEqual(len(engine.cerebro.datas), 0)

    def test_none_df_skipped_no_crash(self, mock_dataloader_cls):
        mock_loader = MagicMock()
        mock_loader.get_data.return_value = None
        mock_dataloader_cls.return_value = mock_loader

        engine = BTBacktestEngine({"symbol": "BTC/USDT", "timeframes": ["1h"]})
        engine.add_data()

        self.assertEqual(len(engine.cerebro.datas), 0)

    def test_timestamp_column_fallback_for_datetime_index(self, mock_dataloader_cls):
        dates = pd.date_range("2024-01-01", periods=20, freq="h")
        df = pd.DataFrame({
            "timestamp": dates,
            "open": [100.0] * 20,
            "high": [105.0] * 20,
            "low": [95.0] * 20,
            "close": [101.0] * 20,
            "volume": [1000] * 20,
        })
        mock_loader = MagicMock()
        mock_loader.get_data.return_value = df
        mock_dataloader_cls.return_value = mock_loader

        engine = BTBacktestEngine({"symbol": "BTC/USDT", "timeframes": ["1h"]})
        engine.add_data()

        self.assertEqual(len(engine.cerebro.datas), 1)

    def test_valid_df_added_to_cerebro(self, mock_dataloader_cls):
        mock_loader = MagicMock()
        mock_loader.get_data.return_value = _mock_ohlcv_df()
        mock_dataloader_cls.return_value = mock_loader

        engine = BTBacktestEngine({"symbol": "BTC/USDT", "timeframes": ["1h"]})
        engine.add_data()

        self.assertEqual(len(engine.cerebro.datas), 1)
        self.assertEqual(engine.cerebro.datas[0]._name, "BTC/USDT_1h")


@patch("engine.bt_backtest_engine.DataLoader")
class TestRunBacktest(unittest.TestCase):
    """Test run_backtest flow and output."""

    def test_returns_metrics_dict_with_expected_keys(self, mock_dataloader_cls):
        mock_loader = MagicMock()
        mock_loader.get_data.return_value = _mock_ohlcv_df(100)
        mock_dataloader_cls.return_value = mock_loader

        engine = BTBacktestEngine({
            "symbol": "BTC/USDT",
            "timeframes": ["1h"],
            "start_date": "2024-01-01",
            "end_date": "2024-01-31",
        })
        engine.add_strategy(PriceActionStrategy, use_trend_filter=False, use_structure_filter=False, use_adx_filter=False, use_rsi_filter=False)
        metrics = engine.run_backtest()

        expected_keys = {
            "initial_capital", "final_capital", "total_pnl", "sharpe_ratio",
            "max_drawdown", "total_trades", "win_rate", "profit_factor",
            "win_count", "loss_count", "avg_win", "avg_loss",
        }
        for k in expected_keys:
            self.assertIn(k, metrics, f"Missing metric key: {k}")

    def test_strategy_assigned_after_run(self, mock_dataloader_cls):
        mock_loader = MagicMock()
        mock_loader.get_data.return_value = _mock_ohlcv_df(50)
        mock_dataloader_cls.return_value = mock_loader

        engine = BTBacktestEngine({"symbol": "BTC/USDT", "timeframes": ["1h"], "start_date": "2024-01-01", "end_date": "2024-01-31"})
        engine.add_strategy(PriceActionStrategy, use_trend_filter=False, use_structure_filter=False, use_adx_filter=False, use_rsi_filter=False)
        engine.run_backtest()

        self.assertIsNotNone(engine.strategy)
        self.assertIsInstance(engine.strategy, PriceActionStrategy)

    def test_closed_trades_populated_after_run(self, mock_dataloader_cls):
        mock_loader = MagicMock()
        mock_loader.get_data.return_value = _mock_ohlcv_df(200)
        mock_dataloader_cls.return_value = mock_loader

        engine = BTBacktestEngine({"symbol": "BTC/USDT", "timeframes": ["1h"], "start_date": "2024-01-01", "end_date": "2024-01-31"})
        engine.add_strategy(PriceActionStrategy, use_trend_filter=False, use_structure_filter=False, use_adx_filter=False, use_rsi_filter=False)
        engine.run_backtest()

        self.assertIsInstance(engine.closed_trades, list)

    def test_equity_curve_populated_after_run(self, mock_dataloader_cls):
        mock_loader = MagicMock()
        mock_loader.get_data.return_value = _mock_ohlcv_df(50)
        mock_dataloader_cls.return_value = mock_loader

        engine = BTBacktestEngine({"symbol": "BTC/USDT", "timeframes": ["1h"], "start_date": "2024-01-01", "end_date": "2024-01-31"})
        engine.add_strategy(PriceActionStrategy, use_trend_filter=False, use_structure_filter=False, use_adx_filter=False, use_rsi_filter=False)
        engine.run_backtest()

        self.assertIsInstance(engine.equity_curve, list)
        self.assertGreater(len(engine.equity_curve), 0)
        self.assertIn("timestamp", engine.equity_curve[0])
        self.assertIn("equity", engine.equity_curve[0])

    def test_initial_capital_preserved_in_metrics(self, mock_dataloader_cls):
        mock_loader = MagicMock()
        mock_loader.get_data.return_value = _mock_ohlcv_df(50)
        mock_dataloader_cls.return_value = mock_loader

        engine = BTBacktestEngine({
            "symbol": "BTC/USDT",
            "timeframes": ["1h"],
            "start_date": "2024-01-01",
            "end_date": "2024-01-31",
            "initial_capital": 25000,
        })
        engine.add_strategy(PriceActionStrategy, use_trend_filter=False, use_structure_filter=False, use_adx_filter=False, use_rsi_filter=False)
        metrics = engine.run_backtest()

        self.assertEqual(metrics["initial_capital"], 25000)

    def test_empty_results_returns_empty_dict(self, mock_dataloader_cls):
        mock_loader = MagicMock()
        mock_loader.get_data.return_value = _mock_ohlcv_df(10)
        mock_dataloader_cls.return_value = mock_loader

        engine = BTBacktestEngine({"symbol": "BTC/USDT", "timeframes": ["1h"], "start_date": "2024-01-01", "end_date": "2024-01-31"})
        engine.add_strategy(PriceActionStrategy, use_trend_filter=False, use_structure_filter=False, use_adx_filter=False, use_rsi_filter=False)

        with patch.object(engine, "run", return_value=[]):
            metrics = engine.run_backtest()

        self.assertEqual(metrics, {})
        self.assertEqual(engine.equity_curve, [])

    def test_open_trade_is_force_closed_on_last_bar(self, mock_dataloader_cls):
        mock_loader = MagicMock()
        df = _mock_ohlcv_df(8).copy()
        df["close"] = [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0]
        df["open"] = df["close"]
        df["high"] = df["close"] + 1.0
        df["low"] = df["close"] - 1.0
        mock_loader.get_data.return_value = df
        mock_dataloader_cls.return_value = mock_loader

        engine = BTBacktestEngine({
            "symbol": "BTC/USDT",
            "timeframes": ["1h"],
            "start_date": "2024-01-01",
            "end_date": "2024-01-31",
            "commission": 0.0,
            "slippage_bps": 0.0,
        })
        engine.add_strategy(_OpenAtEndStrategy)
        metrics = engine.run_backtest()

        self.assertEqual(metrics["forced_final_close_count"], 1)
        self.assertEqual(metrics["total_trades"], 1)
        self.assertEqual(engine.closed_trades[-1]["exit_reason"], "Forced Final Close")
        self.assertAlmostEqual(
            metrics["final_capital"] - metrics["initial_capital"],
            engine.closed_trades[-1]["realized_pnl"],
        )
        self.assertGreater(engine.equity_curve[-1]["equity"], engine.equity_curve[0]["equity"])


@patch("engine.bt_backtest_engine.DataLoader")
class TestCalculateWinRate(unittest.TestCase):
    """Test _calculate_win_rate."""

    def test_zero_trades_returns_zero(self, mock_dataloader_cls):
        mock_dataloader_cls.return_value = MagicMock()
        engine = BTBacktestEngine({"symbol": "BTC/USDT", "timeframes": ["1h"]})
        analysis = {"total": {"closed": 0}, "won": {"total": 0}, "lost": {"total": 0}}
        self.assertEqual(engine._calculate_win_rate(analysis), 0.0)

    def test_all_won_returns_100(self, mock_dataloader_cls):
        mock_dataloader_cls.return_value = MagicMock()
        engine = BTBacktestEngine({"symbol": "BTC/USDT", "timeframes": ["1h"]})
        analysis = {"total": {"closed": 10}, "won": {"total": 10}, "lost": {"total": 0}}
        self.assertEqual(engine._calculate_win_rate(analysis), 100.0)

    def test_half_won_returns_50(self, mock_dataloader_cls):
        mock_dataloader_cls.return_value = MagicMock()
        engine = BTBacktestEngine({"symbol": "BTC/USDT", "timeframes": ["1h"]})
        analysis = {"total": {"closed": 10}, "won": {"total": 5}, "lost": {"total": 5}}
        self.assertEqual(engine._calculate_win_rate(analysis), 50.0)


@patch("engine.bt_backtest_engine.DataLoader")
class TestCalculateProfitFactor(unittest.TestCase):
    """Test _calculate_profit_factor."""

    def test_zero_loss_won_positive_returns_999(self, mock_dataloader_cls):
        mock_dataloader_cls.return_value = MagicMock()
        engine = BTBacktestEngine({"symbol": "BTC/USDT", "timeframes": ["1h"]})
        analysis = {"won": {"pnl": {"total": 100.0}}, "lost": {"pnl": {"total": 0.0}}}
        self.assertEqual(engine._calculate_profit_factor(analysis), 999.0)

    def test_zero_won_zero_loss_returns_zero(self, mock_dataloader_cls):
        mock_dataloader_cls.return_value = MagicMock()
        engine = BTBacktestEngine({"symbol": "BTC/USDT", "timeframes": ["1h"]})
        analysis = {"won": {"pnl": {"total": 0.0}}, "lost": {"pnl": {"total": 0.0}}}
        self.assertEqual(engine._calculate_profit_factor(analysis), 0.0)

    def test_normal_case_won_over_lost(self, mock_dataloader_cls):
        mock_dataloader_cls.return_value = MagicMock()
        engine = BTBacktestEngine({"symbol": "BTC/USDT", "timeframes": ["1h"]})
        analysis = {"won": {"pnl": {"total": 200.0}}, "lost": {"pnl": {"total": 50.0}}}
        self.assertAlmostEqual(engine._calculate_profit_factor(analysis), 4.0, places=2)

    def test_negative_lost_uses_abs(self, mock_dataloader_cls):
        mock_dataloader_cls.return_value = MagicMock()
        engine = BTBacktestEngine({"symbol": "BTC/USDT", "timeframes": ["1h"]})
        analysis = {"won": {"pnl": {"total": 100.0}}, "lost": {"pnl": {"total": -25.0}}}
        self.assertAlmostEqual(engine._calculate_profit_factor(analysis), 4.0, places=2)


@patch("engine.bt_backtest_engine.DataLoader")
class TestAddDataTimeframeOrdering(unittest.TestCase):
    """Test dual-TF ordering (lower TF first)."""

    def test_dual_tf_is_sorted_low_to_high_even_if_config_is_reversed(self, mock_dataloader_cls):
        mock_loader = MagicMock()
        mock_loader.get_data.return_value = _mock_ohlcv_df()
        mock_dataloader_cls.return_value = mock_loader

        config = {
            "symbol": "BTC/USDT",
            "timeframes": ["4h", "15m"],
            "start_date": "2024-01-01",
            "end_date": "2024-01-31",
        }
        engine = BTBacktestEngine(config)
        engine.add_data()

        calls = mock_loader.get_data.call_args_list
        self.assertEqual(calls[0][0][1], "15m")
        self.assertEqual(calls[1][0][1], "4h")

    def test_dual_tf_is_sorted_low_to_high_even_if_config_is_already_low_first(self, mock_dataloader_cls):
        mock_loader = MagicMock()
        mock_loader.get_data.return_value = _mock_ohlcv_df()
        mock_dataloader_cls.return_value = mock_loader

        engine = BTBacktestEngine({
            "symbol": "BTC/USDT",
            "timeframes": ["1h", "4h"],
            "start_date": "2024-01-01",
            "end_date": "2024-01-31",
        })
        engine.add_data()

        calls = mock_loader.get_data.call_args_list
        self.assertEqual(calls[0][0][1], "1h")
        self.assertEqual(calls[1][0][1], "4h")

    def test_single_tf_no_reverse(self, mock_dataloader_cls):
        mock_loader = MagicMock()
        mock_loader.get_data.return_value = _mock_ohlcv_df()
        mock_dataloader_cls.return_value = mock_loader

        engine = BTBacktestEngine({"symbol": "BTC/USDT", "timeframes": ["4h"], "start_date": "2024-01-01", "end_date": "2024-01-31"})
        engine.add_data()

        self.assertEqual(mock_loader.get_data.call_args[0][1], "4h")


@patch("engine.bt_backtest_engine.DataLoader")
class TestAddDataDateDefaults(unittest.TestCase):
    """Test default dates when missing from config."""

    def test_missing_dates_use_defaults(self, mock_dataloader_cls):
        mock_loader = MagicMock()
        mock_loader.get_data.return_value = _mock_ohlcv_df()
        mock_dataloader_cls.return_value = mock_loader

        engine = BTBacktestEngine({"symbol": "BTC/USDT", "timeframes": ["1h"]})
        engine.add_data()

        self.assertEqual(mock_loader.get_data.call_args[0][2], "2024-01-01")
        self.assertEqual(mock_loader.get_data.call_args[0][3], "2024-12-31")


@patch("engine.bt_backtest_engine.DataLoader")
class TestAddDataColumnValidation(unittest.TestCase):
    """Test column validation."""

    def test_missing_columns_skipped(self, mock_dataloader_cls):
        bad_df = pd.DataFrame({
            "open": [100.0] * 10,
            "high": [105.0] * 10,
            "low": [95.0] * 10,
            "close": [101.0] * 10,
        }, index=pd.date_range("2025-01-01", periods=10, freq="h"))
        mock_loader = MagicMock()
        mock_loader.get_data.return_value = bad_df
        mock_dataloader_cls.return_value = mock_loader

        engine = BTBacktestEngine({"symbol": "BTC/USDT", "timeframes": ["1h"]})
        engine.add_data()

        self.assertEqual(len(engine.cerebro.datas), 0)


if __name__ == "__main__":
    unittest.main()
