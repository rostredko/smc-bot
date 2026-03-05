"""
Tests for critical engine and strategy functionality that should remain stable.
Tests cover:
1. Engine data feed ordering (dual-TF master clock)
2. Strategy position sizing calculation
3. Strategy pattern detection basics
4. Trailing stop / breakeven logic
"""
import unittest
from unittest.mock import MagicMock, patch
import backtrader as bt
import pandas as pd
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.bt_backtest_engine import BTBacktestEngine
from strategies.bt_price_action import PriceActionStrategy


class TestEngineDataOrdering(unittest.TestCase):
    """Test that the engine correctly orders data feeds for dual-TF."""

    @patch('engine.bt_backtest_engine.DataLoader')
    def test_reversed_timeframe_ordering(self, mock_dataloader_cls):
        """Lower TF should be added first (datas[0]) as master clock."""
        mock_df = pd.DataFrame({
            'open': [100.0]*300,
            'high': [105.0]*300,
            'low': [95.0]*300,
            'close': [101.0]*300,
            'volume': [1000]*300,
        }, index=pd.date_range('2025-01-01', periods=300, freq='h'))
        mock_loader = MagicMock()
        mock_loader.get_data.return_value = mock_df
        mock_dataloader_cls.return_value = mock_loader

        config = {
            'symbol': 'BTC/USDT',
            'timeframes': ['4h', '15m'],
            'start_date': '2025-01-01',
            'end_date': '2025-01-31',
            'initial_capital': 10000,
        }
        engine = BTBacktestEngine(config)
        engine.add_data()
        
        # Verify get_data was called with reversed order (lower TF first)
        calls = mock_loader.get_data.call_args_list
        self.assertEqual(len(calls), 2)
        # First call should be '15m' (lower TF)
        self.assertEqual(calls[0][0][1], '15m')
        # Second call should be '4h' (higher TF)
        self.assertEqual(calls[1][0][1], '4h')

    @patch('engine.bt_backtest_engine.DataLoader')
    def test_single_timeframe_no_reverse(self, mock_dataloader_cls):
        """Single timeframe should not be reversed."""
        mock_df = pd.DataFrame({
            'open': [100.0]*300,
            'high': [105.0]*300,
            'low': [95.0]*300,
            'close': [101.0]*300,
            'volume': [1000]*300,
        }, index=pd.date_range('2025-01-01', periods=300, freq='h'))
        mock_loader = MagicMock()
        mock_loader.get_data.return_value = mock_df
        mock_dataloader_cls.return_value = mock_loader

        config = {
            'symbol': 'BTC/USDT',
            'timeframes': ['4h'],
            'start_date': '2025-01-01',
            'end_date': '2025-01-31',
            'initial_capital': 10000,
        }
        engine = BTBacktestEngine(config)
        engine.add_data()
        
        calls = mock_loader.get_data.call_args_list
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0][1], '4h')


class TestPositionSizing(unittest.TestCase):
    """Test position sizing calculation."""

    def setUp(self):
        self.cerebro = bt.Cerebro()
        self.cerebro.addstrategy(PriceActionStrategy)
        
        dates = pd.date_range(start='2020-01-01', periods=250)
        closes = [100.0 + (i % 2) for i in range(250)]
        df = pd.DataFrame({
            'open': closes,
            'high': [c + 5 for c in closes],
            'low': [c - 5 for c in closes],
            'close': closes,
            'volume': [1000] * 250
        }, index=dates)
        data = bt.feeds.PandasData(dataname=df)
        self.cerebro.adddata(data)
        results = self.cerebro.run()
        self.strategy = results[0]

    def test_dynamic_sizing_basic(self):
        self.strategy.params = MagicMock()
        self.strategy.params.dynamic_position_sizing = True
        self.strategy.params.risk_per_trade = 1.0
        self.strategy.params.leverage = 10.0
        self.strategy.params.max_drawdown = None
        self.strategy.params.position_cap_adverse = 0.5
        self.strategy.broker = MagicMock()
        self.strategy.broker.get_cash.return_value = 10000
        self.strategy.broker.getvalue.return_value = 10000
        
        # Entry at 100, SL at 95 → risk_per_share = 5
        # Risk amount = 10000 * 0.01 = 100
        # Size = 100 / 5 = 20
        size = self.strategy._calculate_position_size(100.0, 95.0)
        self.assertAlmostEqual(size, 20.0, places=2)

    def test_leverage_cap(self):
        self.strategy.params = MagicMock()
        self.strategy.params.dynamic_position_sizing = True
        self.strategy.params.risk_per_trade = 10.0
        self.strategy.params.leverage = 2.0
        self.strategy.params.max_drawdown = None
        self.strategy.params.position_cap_adverse = 0.5
        self.strategy.broker = MagicMock()
        self.strategy.broker.get_cash.return_value = 10000
        self.strategy.broker.getvalue.return_value = 10000

        # Entry at 100, SL at 99 → risk_per_share = 1
        # Risk amount = 10000 * 0.10 = 1000
        # Uncapped size = 1000 / 1 = 1000 → notional = 100000
        # Max allowed = 10000 * 2 = 20000 → max size = 200
        size = self.strategy._calculate_position_size(100.0, 99.0)
        self.assertAlmostEqual(size, 200.0, places=2)

    def test_zero_risk_returns_zero(self):
        self.strategy.params = MagicMock()
        self.strategy.params.dynamic_position_sizing = True
        self.strategy.params.risk_per_trade = 1.0
        self.strategy.params.leverage = 10.0
        self.strategy.params.max_drawdown = None
        self.strategy.broker = MagicMock()
        self.strategy.broker.get_cash.return_value = 10000
        self.strategy.broker.getvalue.return_value = 10000
        
        size = self.strategy._calculate_position_size(100.0, 100.0)
        self.assertEqual(size, 0)


class TestEngineMetrics(unittest.TestCase):
    """Test engine metric calculations for edge cases."""

    @patch('engine.bt_backtest_engine.DataLoader')
    def test_win_rate_zero_trades(self, mock_dataloader_cls):
        """Win rate should be 0 when no trades closed."""
        mock_dataloader_cls.return_value = MagicMock()
        config = {'symbol': 'BTC/USDT', 'timeframes': ['1h'], 'start_date': '2024-01-01', 'end_date': '2024-01-31'}
        engine = BTBacktestEngine(config)
        analysis = {'total': {'closed': 0}, 'won': {'total': 0}, 'lost': {'total': 0}}
        self.assertEqual(engine._calculate_win_rate(analysis), 0.0)

    @patch('engine.bt_backtest_engine.DataLoader')
    def test_profit_factor_zero_loss(self, mock_dataloader_cls):
        """Profit factor should be 999 when won > 0 and lost == 0 (serializable)."""
        mock_dataloader_cls.return_value = MagicMock()
        config = {'symbol': 'BTC/USDT', 'timeframes': ['1h'], 'start_date': '2024-01-01', 'end_date': '2024-01-31'}
        engine = BTBacktestEngine(config)
        analysis = {'won': {'pnl': {'total': 100.0}}, 'lost': {'pnl': {'total': 0.0}}}
        self.assertEqual(engine._calculate_profit_factor(analysis), 999.0)

    @patch('engine.bt_backtest_engine.DataLoader')
    def test_profit_factor_zero_won_zero_loss(self, mock_dataloader_cls):
        """Profit factor should be 0 when both won and lost are 0."""
        mock_dataloader_cls.return_value = MagicMock()
        config = {'symbol': 'BTC/USDT', 'timeframes': ['1h'], 'start_date': '2024-01-01', 'end_date': '2024-01-31'}
        engine = BTBacktestEngine(config)
        analysis = {'won': {'pnl': {'total': 0.0}}, 'lost': {'pnl': {'total': 0.0}}}
        self.assertEqual(engine._calculate_profit_factor(analysis), 0.0)

    @patch('engine.bt_backtest_engine.DataLoader')
    def test_metrics_serializable_to_json(self, mock_dataloader_cls):
        """Metrics with max profit_factor must be JSON-serializable (no inf)."""
        import json
        mock_dataloader_cls.return_value = MagicMock()
        config = {'symbol': 'BTC/USDT', 'timeframes': ['1h'], 'start_date': '2024-01-01', 'end_date': '2024-01-31'}
        engine = BTBacktestEngine(config)
        analysis = {'won': {'pnl': {'total': 100.0}}, 'lost': {'pnl': {'total': 0.0}}}
        pf = engine._calculate_profit_factor(analysis)
        metrics = {'profit_factor': pf, 'total_pnl': 100.0}
        json_str = json.dumps(metrics)
        self.assertIn('999', json_str)


class TestEngineDateValidation(unittest.TestCase):
    """Test engine handles missing start/end dates."""

    @patch('engine.bt_backtest_engine.DataLoader')
    def test_missing_dates_use_defaults(self, mock_dataloader_cls):
        mock_df = pd.DataFrame({
            "open": [100.0] * 100,
            "high": [105.0] * 100,
            "low": [95.0] * 100,
            "close": [101.0] * 100,
            "volume": [1000] * 100,
        }, index=pd.date_range("2024-01-01", periods=100, freq="h"))
        mock_loader = MagicMock()
        mock_loader.get_data.return_value = mock_df
        mock_dataloader_cls.return_value = mock_loader

        config = {
            "symbol": "BTC/USDT",
            "timeframes": ["1h"],
            "initial_capital": 10000,
        }
        engine = BTBacktestEngine(config)
        engine.add_data()
        calls = mock_loader.get_data.call_args_list
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0][2], "2024-01-01")
        self.assertEqual(calls[0][0][3], "2024-12-31")


class TestEngineColumnValidation(unittest.TestCase):
    """Test that engine validates required columns."""

    @patch('engine.bt_backtest_engine.DataLoader')
    def test_missing_columns_skipped(self, mock_dataloader_cls):
        """Data with missing columns should be skipped with warning."""
        # DataFrame missing 'volume' column
        bad_df = pd.DataFrame({
            'open': [100.0]*10,
            'high': [105.0]*10,
            'low': [95.0]*10,
            'close': [101.0]*10,
            # 'volume' missing!
        }, index=pd.date_range('2025-01-01', periods=10, freq='h'))
        mock_loader = MagicMock()
        mock_loader.get_data.return_value = bad_df
        mock_dataloader_cls.return_value = mock_loader

        config = {
            'symbol': 'BTC/USDT',
            'timeframes': ['4h'],
            'start_date': '2025-01-01',
            'end_date': '2025-01-31',
            'initial_capital': 10000,
        }
        engine = BTBacktestEngine(config)
        # Should not crash, just print warning and skip
        engine.add_data()
        
        # No data should have been added
        self.assertEqual(len(engine.cerebro.datas), 0)


if __name__ == '__main__':
    unittest.main()
