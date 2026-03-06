"""
Tests for engine/bt_analyzers.py — TradeListAnalyzer and EquityCurveAnalyzer.
Backtrader Analyzers require Cerebro context; tests use integration approach.
"""
import unittest
import pandas as pd
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import backtrader as bt
from engine.bt_analyzers import TradeListAnalyzer, EquityCurveAnalyzer
from strategies.bt_price_action import PriceActionStrategy


def _mock_df(rows=300):
    return pd.DataFrame({
        "open": [100.0] * rows,
        "high": [105.0] * rows,
        "low": [95.0] * rows,
        "close": [101.0] * rows,
        "volume": [1000] * rows,
    }, index=pd.date_range("2024-01-01", periods=rows, freq="h"))


class _OneTradeStrategy(bt.Strategy):
    """Minimal strategy: buy at bar 3, close at bar 10. Produces one LONG trade."""

    def __init__(self):
        self.order = None

    def notify_order(self, order):
        if order.status in (order.Completed, order.Canceled, order.Margin, order.Rejected):
            self.order = None

    def next(self):
        if self.order:
            return
        if len(self) == 3:
            self.order = self.buy(size=10)
        elif len(self) == 10 and self.position:
            self.order = self.close()


class TestTradeListAnalyzer(unittest.TestCase):
    """Integration tests for TradeListAnalyzer."""

    def test_produces_valid_structure(self):
        """TradeListAnalyzer produces records with required fields."""
        cerebro = bt.Cerebro()
        cerebro.addstrategy(PriceActionStrategy, use_trend_filter=False, use_structure_filter=False, use_adx_filter=False, use_rsi_filter=False)
        cerebro.addanalyzer(TradeListAnalyzer, _name="tradelist")

        data = bt.feeds.PandasData(dataname=_mock_df())
        cerebro.adddata(data)

        results = cerebro.run()
        trades = results[0].analyzers.tradelist.get_analysis()

        self.assertIsInstance(trades, list)
        required_fields = {"id", "direction", "entry_price", "exit_price", "entry_time", "exit_time", "realized_pnl", "exit_reason", "size"}
        for t in trades:
            for f in required_fields:
                self.assertIn(f, t, f"Trade record missing field: {f}")

    def test_long_trade_has_correct_direction_and_exit_price(self):
        """LONG trade: direction, entry_price, exit_price, size, realized_pnl present."""
        cerebro = bt.Cerebro()
        cerebro.addstrategy(_OneTradeStrategy)
        cerebro.addanalyzer(TradeListAnalyzer, _name="tradelist")

        df = _mock_df(30)
        data = bt.feeds.PandasData(dataname=df)
        cerebro.adddata(data)

        results = cerebro.run()
        trades = results[0].analyzers.tradelist.get_analysis()

        self.assertGreaterEqual(len(trades), 1)
        t = trades[0]
        self.assertEqual(t["direction"], "LONG")
        self.assertIn("entry_price", t)
        self.assertIn("exit_price", t)
        self.assertIn("size", t)
        self.assertIn("realized_pnl", t)

    def test_ignores_open_trades(self):
        """Only closed trades are recorded."""
        cerebro = bt.Cerebro()
        cerebro.addstrategy(PriceActionStrategy, use_trend_filter=False, use_structure_filter=False, use_adx_filter=False, use_rsi_filter=False)
        cerebro.addanalyzer(TradeListAnalyzer, _name="tradelist")

        data = bt.feeds.PandasData(dataname=_mock_df(20))
        cerebro.adddata(data)

        results = cerebro.run()
        trades = results[0].analyzers.tradelist.get_analysis()
        for t in trades:
            self.assertIn(t["direction"], ("LONG", "SHORT"))
            self.assertIsInstance(t["entry_time"], str)
            self.assertIsInstance(t["exit_time"], str)

    def test_commission_in_record(self):
        """Trade record includes commission (pnl - pnlcomm)."""
        cerebro = bt.Cerebro()
        cerebro.addstrategy(_OneTradeStrategy)
        cerebro.addanalyzer(TradeListAnalyzer, _name="tradelist")

        data = bt.feeds.PandasData(dataname=_mock_df(50))
        cerebro.adddata(data)

        results = cerebro.run()
        trades = results[0].analyzers.tradelist.get_analysis()
        if trades:
            self.assertIn("commission", trades[0])

    def test_get_analysis_returns_list(self):
        """get_analysis returns a list."""
        cerebro = bt.Cerebro()
        cerebro.addstrategy(PriceActionStrategy, use_trend_filter=False, use_structure_filter=False, use_adx_filter=False, use_rsi_filter=False)
        cerebro.addanalyzer(TradeListAnalyzer, _name="tradelist")
        cerebro.adddata(bt.feeds.PandasData(dataname=_mock_df(50)))

        results = cerebro.run()
        analysis = results[0].analyzers.tradelist.get_analysis()
        self.assertIsInstance(analysis, list)


class TestEquityCurveAnalyzer(unittest.TestCase):
    """Tests for EquityCurveAnalyzer."""

    def test_records_during_backtest(self):
        """Equity curve has entries with timestamp and equity."""
        cerebro = bt.Cerebro()
        cerebro.addstrategy(PriceActionStrategy, use_trend_filter=False, use_structure_filter=False, use_adx_filter=False, use_rsi_filter=False)
        cerebro.addanalyzer(EquityCurveAnalyzer, _name="equity")

        data = bt.feeds.PandasData(dataname=_mock_df(50))
        cerebro.adddata(data)

        results = cerebro.run()
        curve = results[0].analyzers.equity.get_analysis()

        self.assertIsInstance(curve, list)
        self.assertGreater(len(curve), 0)
        self.assertIn("timestamp", curve[0])
        self.assertIn("equity", curve[0])

    def test_equity_values_non_negative(self):
        """Equity values are non-negative."""
        cerebro = bt.Cerebro()
        cerebro.addstrategy(PriceActionStrategy, use_trend_filter=False, use_structure_filter=False, use_adx_filter=False, use_rsi_filter=False)
        cerebro.addanalyzer(EquityCurveAnalyzer, _name="equity")

        data = bt.feeds.PandasData(dataname=_mock_df(50))
        cerebro.adddata(data)

        results = cerebro.run()
        curve = results[0].analyzers.equity.get_analysis()

        for point in curve:
            self.assertGreaterEqual(point["equity"], 0)

    def test_curve_length_matches_bars(self):
        """Equity curve has one point per bar."""
        cerebro = bt.Cerebro()
        cerebro.addstrategy(_OneTradeStrategy)
        cerebro.addanalyzer(EquityCurveAnalyzer, _name="equity")

        df = _mock_df(30)
        data = bt.feeds.PandasData(dataname=df)
        cerebro.adddata(data)

        results = cerebro.run()
        curve = results[0].analyzers.equity.get_analysis()

        self.assertEqual(len(curve), len(df))

    def test_get_analysis_returns_list(self):
        """get_analysis returns a list."""
        cerebro = bt.Cerebro()
        cerebro.addstrategy(_OneTradeStrategy)
        cerebro.addanalyzer(EquityCurveAnalyzer, _name="equity")
        cerebro.adddata(bt.feeds.PandasData(dataname=_mock_df(20)))

        results = cerebro.run()
        analysis = results[0].analyzers.equity.get_analysis()
        self.assertIsInstance(analysis, list)


if __name__ == "__main__":
    unittest.main()
