
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
        self.strategy.params.use_trend_filter = False
        self.strategy.params.use_structure_filter = True
        self.strategy.params.use_ema_filter = False
        self.strategy.params.use_rsi_filter = True
        self.strategy.params.use_rsi_momentum = True
        self.strategy.params.use_adx_filter = True
        self.strategy.params.risk_reward_ratio = 2.5
        self.strategy.params.structural_sl_buffer_atr = 0.1
        self.strategy.params.sl_buffer_atr = 1.5
        self.strategy.params.use_opposing_level_tp = False
        self.strategy.params.poi_zone_upper_atr_mult = 0.3
        self.strategy.params.poi_zone_lower_atr_mult = 0.2
        self.strategy.params.use_ltf_choch_trigger = True
        self.strategy.params.ltf_choch_entry_window_bars = 6
        self.strategy.params.ltf_choch_arm_timeout_bars = 24
        self.strategy.params.ltf_choch_max_pullaway_atr_mult = 1.5

        # Mock indicators as simple lists/arrays that support [0]
        self.strategy.close_line = [101.0]
        self.strategy.open_line = [100.0]
        self.strategy.high_line = [102.0]
        self.strategy.low_line = [99.0]
        self.strategy.atr = [10.0]
        self.strategy.atr_htf = [10.0]
        self.strategy.rsi = [55.0] 
        self.strategy.adx = [25.0] 
        
        # Mock dual-timeframe attributes
        htf_mock = MagicMock()
        htf_mock.close = [90.0]  # Default: close < ema → bearish
        self.strategy.data_htf = htf_mock
        self.strategy.ema_htf = [100.0]  # EMA above close → bearish

        ms_mock = MagicMock()
        ms_mock.structure = [1.0]
        ms_mock.sl_level = [100.0]
        ms_mock.sh_level = [120.0]
        self.strategy.ms_4h = ms_mock
        
        ltf_mock = MagicMock()
        ltf_mock.__len__ = MagicMock(return_value=300)
        self.strategy.data_ltf = ltf_mock
        
        # Prevent churn filter from blocking
        self.strategy.last_entry_bar = -1

        # Mock trade map
        self.strategy.trade_map = {}
        self.strategy._long_choch_trigger_bar = 300
        self.strategy._short_choch_trigger_bar = 300
        self.strategy._long_choch_trigger_price = 101.0
        self.strategy._short_choch_trigger_price = 101.0
        self.strategy._long_choch_trigger_zone_ref = 100.0
        self.strategy._short_choch_trigger_zone_ref = 100.0

    def test_filter_rsi_momentum_long(self):
        """Test RSI Momentum Logic for Long entries"""
        # For long: bullish structure + price in POI zone around 4H SL
        self.strategy.ms_4h.structure = [1.0]
        self.strategy.ms_4h.sl_level = [100.0]
        self.strategy.close_line = [101.0]
        
        # Case 1: RSI = 55 (Too weak, threshold is 60)
        self.strategy.rsi = [55.0]
        self.assertFalse(self.strategy._check_filters_long(), "Should fail: RSI 55 < Threshold 60")

        # Case 2: RSI = 65 (Strong, threshold is 60)
        self.strategy.rsi = [65.0]
        self.assertTrue(self.strategy._check_filters_long(), "Should pass: RSI 65 > Threshold 60")

    def test_filter_rsi_momentum_short(self):
        """Test RSI Momentum Logic for Short entries"""
        # Threshold 60 means short threshold is 100-60 = 40.
        # For short: bearish structure + price in POI zone around 4H SH
        self.strategy.ms_4h.structure = [-1.0]
        self.strategy.ms_4h.sh_level = [100.0]
        self.strategy.close_line = [101.0]
        
        # Case 1: RSI = 45 (Too weak, must be < 40)
        self.strategy.rsi = [45.0]
        self.assertFalse(self.strategy._check_filters_short(), "Should fail: RSI 45 > bearish_threshold 40")

        # Case 2: RSI = 35 (Strong bearish, < 40)
        self.strategy.rsi = [35.0]
        self.assertTrue(self.strategy._check_filters_short(), "Should pass: RSI 35 < bearish_threshold 40")

    def test_long_requires_recent_ltf_choch_trigger(self):
        """Bullish setup requires a recent LTF CHoCH trigger when enabled."""
        self.strategy.ms_4h.structure = [1.0]
        self.strategy.ms_4h.sl_level = [100.0]
        self.strategy.close_line = [104.0]  # Outside [98, 103] for ATR=10
        self.strategy.rsi = [65.0]
        self.strategy._long_choch_trigger_bar = -1
        self.assertFalse(self.strategy._check_filters_long(), "Should fail: no CHoCH trigger")

        self.strategy._long_choch_trigger_bar = 300
        self.assertTrue(self.strategy._check_filters_long(), "Should pass: recent CHoCH trigger is present")

    def test_long_choch_invalid_when_zone_reference_changes(self):
        self.strategy.ms_4h.structure = [1.0]
        self.strategy.ms_4h.sl_level = [101.0]
        self.strategy.rsi = [65.0]
        self.assertFalse(self.strategy._check_filters_long(), "Should fail: CHoCH came from stale HTF zone")

    def test_poi_zone_uses_htf_atr(self):
        self.strategy.ms_4h.sl_level = [100.0]
        self.strategy.atr = [1.0]
        self.strategy.atr_htf = [10.0]
        zone_low, zone_high = self.strategy._get_poi_zone_long()
        self.assertAlmostEqual(zone_low, 98.0, places=6)
        self.assertAlmostEqual(zone_high, 103.0, places=6)

    def test_structural_long_sl_uses_4h_level(self):
        """SL should be anchored to HTF structural level when available."""
        self.strategy.atr = [1.0]
        self.strategy.atr_htf = [10.0]
        sl_price, sl_distance, sl_expr = self.strategy._resolve_structural_sl_long(entry_price=101.0)
        self.assertAlmostEqual(sl_price, 99.0, places=6)
        self.assertAlmostEqual(sl_distance, 2.0, places=6)
        self.assertIn("SL_Level_4H", sl_expr)

    def test_structure_filter_accepts_string_false(self):
        self.strategy.params.use_structure_filter = "false"
        self.strategy.params.use_rsi_filter = False
        self.strategy.params.use_rsi_momentum = False
        self.strategy.params.use_adx_filter = False
        self.strategy.ms_4h.structure = [-1.0]
        self.assertTrue(self.strategy._check_filters_long())

    def test_pattern_flags_accept_string_false(self):
        self.strategy.params.pattern_bearish_engulfing = "false"
        self.strategy.cdl_engulfing = [-100]
        self.strategy.atr = [1.0]
        self.strategy.high_line = [110.0]
        self.strategy.low_line = [100.0]
        self.assertFalse(self.strategy._is_bearish_engulfing())

if __name__ == '__main__':
    unittest.main()
