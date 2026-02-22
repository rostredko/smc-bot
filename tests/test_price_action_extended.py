
import unittest
from unittest.mock import MagicMock
import backtrader as bt
import sys
import os
import pandas as pd

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strategies.bt_price_action import PriceActionStrategy

class TestPriceActionExtended(unittest.TestCase):
    def setUp(self):
        # We must instantiate via Cerebro to avoid metabase errors
        self.cerebro = bt.Cerebro()
        self.cerebro.addstrategy(PriceActionStrategy)
        
        # Create dummy data via Pandas to allow strategy instantiation
        # Need enough bars for indicators (EMA 200)
        dates = pd.date_range(start='2020-01-01', periods=250)
        # Add slight oscillation to avoid ZeroDivisionError in RSI (if updates are 0)
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
        
        # Run to get the strategy instance
        results = self.cerebro.run()
        self.strategy = results[0]
        
        # Now Mock attributes for testing
        self.strategy.params = MagicMock()
        # Default mock params
        self.strategy.params.min_range_factor = 0.8
        self.strategy.params.min_wick_to_range = 0.6
        self.strategy.params.max_body_to_range = 0.3
        self.strategy.params.rsi_overbought = 70
        self.strategy.params.rsi_oversold = 30
        self.strategy.params.rsi_momentum_threshold = 60
        self.strategy.params.adx_threshold = 21
        self.strategy.params.use_trend_filter = True
        self.strategy.params.use_rsi_filter = True
        self.strategy.params.use_rsi_momentum = True
        self.strategy.params.use_adx_filter = True
        self.strategy.params.risk_reward_ratio = 2.5

        # Mock indicators as simple lists/arrays that support [0]
        self.strategy.close = [100.0]
        self.strategy.open = [100.0]
        self.strategy.high = [100.0]
        self.strategy.low = [100.0]
        self.strategy.atr = [10.0]
        self.strategy.rsi = [55.0] 
        self.strategy.adx = [25.0] 
        
        # Mock dual-timeframe attributes
        htf_mock = MagicMock()
        htf_mock.close = [90.0]  # Default: close < ema → bearish
        self.strategy.data_htf = htf_mock
        self.strategy.ema_htf = [100.0]  # EMA above close → bearish
        
        ltf_mock = MagicMock()
        ltf_mock.__len__ = MagicMock(return_value=300)
        self.strategy.data_ltf = ltf_mock
        
        # Prevent churn filter from blocking
        self.strategy.last_entry_bar = -1

        # Mock trade map
        self.strategy.trade_map = {}

    def test_filter_rsi_momentum_long(self):
        """Test RSI Momentum Logic for Long entries"""
        # For long: data_htf.close > ema_htf (bullish trend)
        self.strategy.data_htf.close = [110.0]
        self.strategy.ema_htf = [100.0]
        
        # Case 1: RSI = 55 (Too weak, threshold is 60)
        self.strategy.rsi = [55.0]
        self.assertFalse(self.strategy._check_filters_long(), "Should fail: RSI 55 < Threshold 60")

        # Case 2: RSI = 65 (Strong, threshold is 60)
        self.strategy.rsi = [65.0]
        self.assertTrue(self.strategy._check_filters_long(), "Should pass: RSI 65 > Threshold 60")

    def test_filter_rsi_momentum_short(self):
        """Test RSI Momentum Logic for Short entries"""
        # Threshold 60 means short threshold is 100-60 = 40.
        # For short: data_htf.close < ema_htf (bearish trend)
        self.strategy.data_htf.close = [80.0]
        self.strategy.ema_htf = [90.0]
        
        # Case 1: RSI = 45 (Too weak, must be < 40)
        self.strategy.rsi = [45.0]
        self.assertFalse(self.strategy._check_filters_short(), "Should fail: RSI 45 > bearish_threshold 40")

        # Case 2: RSI = 35 (Strong bearish, < 40)
        self.strategy.rsi = [35.0]
        self.assertTrue(self.strategy._check_filters_short(), "Should pass: RSI 35 < bearish_threshold 40")

    @unittest.skip("TA-Lib requires data feeds, not static arrays")
    def test_min_range_factor_validity(self):
        """Test if small candles are rejected by min_range_factor"""
        # ATR = 10, min_range_factor = 0.8 => Min Range = 8.0
        
        # Valid pinbar shape but small size
        self.strategy.open = [104.0]
        self.strategy.close = [104.0]
        self.strategy.high = [105.0]
        self.strategy.low = [100.0]
        self.strategy.atr = [10.0]
        
        self.assertFalse(self.strategy._is_bullish_pinbar(), "Should fail: Range 5.0 < MinRange 8.0")

        # Valid Size: Range 10.0
        self.strategy.open = [108.0]
        self.strategy.close = [108.0]
        self.strategy.high = [110.0]
        self.strategy.low = [100.0]
        # Range 10 >= 8. Shape OK.
        self.assertTrue(self.strategy._is_bullish_pinbar(), "Should pass: Range 10.0 > MinRange 8.0")

    @unittest.skip("TA-Lib requires data feeds, not static arrays")
    def test_narrative_generation(self):
        """Test narrative string generation"""
        # Mock a closed trade with proper numeric values
        trade = MagicMock()
        trade.ref = 1
        trade.long = True
        trade.pnl = 100.0
        trade.pnlcomm = 95.0  # Net PnL after commission
        trade.price = 1000.0
        trade.dtclose = 5.0
        trade.dtopen = 0.0
        trade.history = []
        
        self.strategy.trade_map = {1: {'size': 1.0, 'reason': 'Bullish Engulfing', 'stop_loss': 950.0, 'take_profit': 1100.0}}
        self.strategy.sl_history = []
        
        # Test Take Profit
        stored_info = self.strategy.trade_map.get(trade.ref, {})
        narrative = self.strategy.narrator.generate_narrative(trade, "Take Profit", stored_info, self.strategy.sl_history)
        self.assertIn("hit the Take Profit target", narrative)
        self.assertIn("10.00%", narrative)  # 100/1000 = 10%

        # Test Stop Loss
        trade.pnl = -50.0
        trade.pnlcomm = -55.0
        narrative = self.strategy.narrator.generate_narrative(trade, "Stop Loss", stored_info, self.strategy.sl_history)
        self.assertIn("Stop Loss", narrative)

        # Test Breakeven
        trade.pnl = 0.0
        trade.pnlcomm = -5.0
        narrative = self.strategy.narrator.generate_narrative(trade, "Breakeven", stored_info, self.strategy.sl_history)
        self.assertIn("breakeven", narrative.lower())

if __name__ == '__main__':
    unittest.main()
