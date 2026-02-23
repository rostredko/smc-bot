"""
Tests for TradeListAnalyzer (integration with Cerebro).
"""
import unittest
from unittest.mock import MagicMock
import pandas as pd
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import backtrader as bt
from engine.bt_analyzers import TradeListAnalyzer
from strategies.bt_price_action import PriceActionStrategy


class TestTradeListAnalyzer(unittest.TestCase):
    """Integration tests: run minimal backtest and verify analyzer output."""

    def test_tradelist_analyzer_produces_valid_structure(self):
        """TradeListAnalyzer produces records with required fields."""
        cerebro = bt.Cerebro()
        cerebro.addstrategy(PriceActionStrategy, use_trend_filter=False, use_adx_filter=False, use_rsi_filter=False)
        cerebro.addanalyzer(TradeListAnalyzer, _name="tradelist")

        df = pd.DataFrame({
            "open": [100.0] * 300,
            "high": [105.0] * 300,
            "low": [95.0] * 300,
            "close": [101.0] * 300,
            "volume": [1000] * 300,
        }, index=pd.date_range("2024-01-01", periods=300, freq="h"))
        data = bt.feeds.PandasData(dataname=df)
        cerebro.adddata(data)

        results = cerebro.run()
        strat = results[0]
        trades = strat.analyzers.tradelist.get_analysis()

        self.assertIsInstance(trades, list)
        required_fields = {"id", "direction", "entry_price", "exit_price", "entry_time", "exit_time", "realized_pnl", "exit_reason", "size"}
        for t in trades:
            for f in required_fields:
                self.assertIn(f, t, f"Trade record missing field: {f}")


if __name__ == "__main__":
    unittest.main()
