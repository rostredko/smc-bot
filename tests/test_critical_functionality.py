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

    def test_reversed_timeframe_ordering(self):
        """Lower TF should be added first (datas[0]) as master clock."""
        config = {
            'symbol': 'BTC/USDT',
            'timeframes': ['4h', '15m'],
            'start_date': '2025-01-01',
            'end_date': '2025-01-31',
            'initial_capital': 10000,
        }
        engine = BTBacktestEngine(config)
        
        # Mock data_loader to avoid actual data fetching
        mock_df = pd.DataFrame({
            'open': [100.0]*300,
            'high': [105.0]*300,
            'low': [95.0]*300,
            'close': [101.0]*300,
            'volume': [1000]*300,
        }, index=pd.date_range('2025-01-01', periods=300, freq='h'))
        
        engine.data_loader = MagicMock()
        engine.data_loader.get_data = MagicMock(return_value=mock_df)
        
        engine.add_data()
        
        # Verify get_data was called with reversed order (lower TF first)
        calls = engine.data_loader.get_data.call_args_list
        self.assertEqual(len(calls), 2)
        # First call should be '15m' (lower TF)
        self.assertEqual(calls[0][0][1], '15m')
        # Second call should be '4h' (higher TF)
        self.assertEqual(calls[1][0][1], '4h')

    def test_single_timeframe_no_reverse(self):
        """Single timeframe should not be reversed."""
        config = {
            'symbol': 'BTC/USDT',
            'timeframes': ['4h'],
            'start_date': '2025-01-01',
            'end_date': '2025-01-31',
            'initial_capital': 10000,
        }
        engine = BTBacktestEngine(config)
        
        mock_df = pd.DataFrame({
            'open': [100.0]*300,
            'high': [105.0]*300,
            'low': [95.0]*300,
            'close': [101.0]*300,
            'volume': [1000]*300,
        }, index=pd.date_range('2025-01-01', periods=300, freq='h'))
        
        engine.data_loader = MagicMock()
        engine.data_loader.get_data = MagicMock(return_value=mock_df)
        
        engine.add_data()
        
        calls = engine.data_loader.get_data.call_args_list
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
        """Dynamic sizing: risk_amount / risk_per_share."""
        self.strategy.params = MagicMock()
        self.strategy.params.dynamic_position_sizing = True
        self.strategy.params.risk_per_trade = 1.0  # 1% of equity
        self.strategy.params.leverage = 10.0
        
        # Mock broker
        self.strategy.broker = MagicMock()
        self.strategy.broker.get_cash.return_value = 10000
        self.strategy.broker.get_value.return_value = 10000
        
        # Entry at 100, SL at 95 → risk_per_share = 5
        # Risk amount = 10000 * 0.01 = 100
        # Size = 100 / 5 = 20
        size = self.strategy._calculate_position_size(100.0, 95.0)
        self.assertAlmostEqual(size, 20.0, places=2)

    def test_leverage_cap(self):
        """Position should be capped at max leverage."""
        self.strategy.params = MagicMock()
        self.strategy.params.dynamic_position_sizing = True
        self.strategy.params.risk_per_trade = 10.0  # 10% — very aggressive
        self.strategy.params.leverage = 2.0  # Low leverage
        
        self.strategy.broker = MagicMock()
        self.strategy.broker.get_cash.return_value = 10000
        self.strategy.broker.get_value.return_value = 10000
        
        # Entry at 100, SL at 99 → risk_per_share = 1
        # Risk amount = 10000 * 0.10 = 1000
        # Uncapped size = 1000 / 1 = 1000 → value = 100000
        # Max value at 2x leverage = 20000 → max size = 200
        size = self.strategy._calculate_position_size(100.0, 99.0)
        self.assertAlmostEqual(size, 200.0, places=2)

    def test_zero_risk_returns_zero(self):
        """Entry == SL should return 0 (no division by zero)."""
        self.strategy.params = MagicMock()
        self.strategy.params.dynamic_position_sizing = True
        self.strategy.params.risk_per_trade = 1.0
        self.strategy.params.leverage = 10.0
        
        self.strategy.broker = MagicMock()
        self.strategy.broker.get_cash.return_value = 10000
        self.strategy.broker.get_value.return_value = 10000
        
        size = self.strategy._calculate_position_size(100.0, 100.0)
        self.assertEqual(size, 0)


class TestPatternDetection(unittest.TestCase):
    """Test pattern detection methods."""

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
        
        self.strategy.params = MagicMock()
        self.strategy.params.min_range_factor = 0.8
        self.strategy.params.min_wick_to_range = 0.6
        self.strategy.params.max_body_to_range = 0.3

    def test_bullish_pinbar_valid(self):
        """Valid hammer: small body, long lower wick, significant range."""
        self.strategy.atr = [10.0]
        # Range = 10, body = 0, lower wick = 8 (80% of range)
        self.strategy.open = [108.0]
        self.strategy.close = [108.0]
        self.strategy.high = [110.0]
        self.strategy.low = [100.0]
        
        self.assertTrue(self.strategy._is_bullish_pinbar())

    def test_bullish_pinbar_too_small(self):
        """Candle too small relative to ATR should be rejected."""
        self.strategy.atr = [20.0]  # ATR big
        # Range = 5 < 20*0.8=16 → too small
        self.strategy.open = [104.0]
        self.strategy.close = [104.0]
        self.strategy.high = [105.0]
        self.strategy.low = [100.0]
        
        self.assertFalse(self.strategy._is_bullish_pinbar())

    def test_zero_range_returns_false(self):
        """Zero range candle (doji with no movement) should not crash."""
        self.strategy.atr = [10.0]
        self.strategy.open = [100.0]
        self.strategy.close = [100.0]
        self.strategy.high = [100.0]
        self.strategy.low = [100.0]
        
        self.assertFalse(self.strategy._is_bullish_pinbar())
        self.assertFalse(self.strategy._is_bearish_pinbar())


class TestEngineColumnValidation(unittest.TestCase):
    """Test that engine validates required columns."""

    def test_missing_columns_skipped(self):
        """Data with missing columns should be skipped with warning."""
        config = {
            'symbol': 'BTC/USDT',
            'timeframes': ['4h'],
            'start_date': '2025-01-01',
            'end_date': '2025-01-31',
            'initial_capital': 10000,
        }
        engine = BTBacktestEngine(config)
        
        # DataFrame missing 'volume' column
        bad_df = pd.DataFrame({
            'open': [100.0]*10,
            'high': [105.0]*10,
            'low': [95.0]*10,
            'close': [101.0]*10,
            # 'volume' missing!
        }, index=pd.date_range('2025-01-01', periods=10, freq='h'))
        
        engine.data_loader = MagicMock()
        engine.data_loader.get_data = MagicMock(return_value=bad_df)
        
        # Should not crash, just print warning and skip
        engine.add_data()
        
        # No data should have been added
        self.assertEqual(len(engine.cerebro.datas), 0)


if __name__ == '__main__':
    unittest.main()
