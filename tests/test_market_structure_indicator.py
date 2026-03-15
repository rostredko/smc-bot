import os
import sys
import unittest
import math

import backtrader as bt
import pandas as pd


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from strategies.bt_price_action import MarketStructure
from strategies.market_structure import compute_market_structure_levels


class _RecorderStrategy(bt.Strategy):
    params = (('pivot_span', 2),)

    def __init__(self):
        self.ms = MarketStructure(self.data, pivot_span=self.params.pivot_span)
        self.structure_values = []
        self.sh_levels = []
        self.sl_levels = []

    def next(self):
        self.structure_values.append(int(self.ms.structure[0]))
        self.sh_levels.append(float(self.ms.sh_level[0]))
        self.sl_levels.append(float(self.ms.sl_level[0]))


def _run_structure(highs, lows, closes):
    opens = closes[:]
    df = pd.DataFrame(
        {
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": [1000.0] * len(closes),
        },
        index=pd.date_range("2024-01-01", periods=len(closes), freq="4h"),
    )
    cerebro = bt.Cerebro()
    cerebro.addstrategy(_RecorderStrategy)
    cerebro.adddata(bt.feeds.PandasData(dataname=df))
    return cerebro.run()[0]


class TestMarketStructureIndicator(unittest.TestCase):
    def test_structure_stays_neutral_without_bos(self):
        strat = _run_structure(
            highs=[10, 11, 15, 12, 11, 12, 13, 12, 11, 10, 9],
            lows=[9, 8, 7, 8, 9, 8, 6, 8, 9, 8, 7],
            closes=[9.5, 10, 11, 10, 10, 10, 7.5, 9, 10, 9, 8],
        )
        self.assertEqual(strat.structure_values[-1], 0)

    def test_structure_turns_bullish_only_after_break_above_swing_high(self):
        strat = _run_structure(
            highs=[10, 11, 15, 12, 11, 12, 13, 12, 11, 10, 16, 17, 18],
            lows=[9, 8, 7, 8, 9, 8, 6, 8, 9, 8, 9, 10, 11],
            closes=[9.5, 10, 11, 10, 10, 10, 7.5, 9, 10, 9, 16.2, 16.8, 17.1],
        )
        self.assertEqual(strat.structure_values[-1], 1)

    def test_structure_turns_bearish_only_after_break_below_swing_low(self):
        strat = _run_structure(
            highs=[10, 11, 14, 12, 11, 12, 13, 12, 11, 10, 9, 8, 7],
            lows=[9, 8, 7, 8, 9, 8, 6, 8, 9, 8, 5.5, 5.0, 4.8],
            closes=[9.5, 10, 11, 10, 10, 10, 7.5, 9, 10, 9, 5.7, 5.1, 4.9],
        )
        self.assertEqual(strat.structure_values[-1], -1)

    def test_indicator_series_matches_shared_market_structure_helper(self):
        highs = [10, 11, 15, 12, 11, 12, 13, 12, 11, 10, 16, 17, 18]
        lows = [9, 8, 7, 8, 9, 8, 6, 8, 9, 8, 9, 10, 11]
        closes = [9.5, 10, 11, 10, 10, 10, 7.5, 9, 10, 9, 16.2, 16.8, 17.1]

        strat = _run_structure(highs=highs, lows=lows, closes=closes)
        exp_sh, exp_sl, exp_st = compute_market_structure_levels(highs, lows, closes, pivot_span=2)

        self.assertEqual(strat.structure_values, [int(v) for v in exp_st[4:]])
        for actual, expected in zip(strat.sh_levels, exp_sh[4:]):
            if math.isnan(expected):
                self.assertTrue(math.isnan(actual))
            else:
                self.assertAlmostEqual(actual, expected, places=9)
        for actual, expected in zip(strat.sl_levels, exp_sl[4:]):
            if math.isnan(expected):
                self.assertTrue(math.isnan(actual))
            else:
                self.assertAlmostEqual(actual, expected, places=9)


if __name__ == "__main__":
    unittest.main()
