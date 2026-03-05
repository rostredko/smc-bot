import unittest

import backtrader as bt
import pandas as pd

from engine.bt_analyzers import TradeListAnalyzer
from strategies.fast_test_strategy import FastTestStrategy


def _make_1m_df(periods: int = 240) -> pd.DataFrame:
    idx = pd.date_range("2026-03-01 00:00:00", periods=periods, freq="1min")
    base = 100.0
    rows = []
    for i, _ in enumerate(idx):
        # Mild oscillation and drift to create both directional moves and pullbacks
        close = base + (i * 0.02) + ((-1) ** i) * 0.06
        open_ = close - 0.03
        high = max(open_, close) + 0.05
        low = min(open_, close) - 0.05
        vol = 10 + (i % 7)
        rows.append((open_, high, low, close, vol))
    return pd.DataFrame(rows, index=idx, columns=["open", "high", "low", "close", "volume"])


def _make_5m_df(df_1m: pd.DataFrame) -> pd.DataFrame:
    return (
        df_1m.resample("5min")
        .agg({
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        })
        .dropna()
    )


class TestFastTestStrategy(unittest.TestCase):
    def _run(self, strategy_kwargs):
        df_1m = _make_1m_df()
        df_5m = _make_5m_df(df_1m)

        cerebro = bt.Cerebro()
        cerebro.broker.setcash(1000.0)
        cerebro.broker.setcommission(commission=0.0004, leverage=5.0)
        cerebro.broker.set_coo(True)

        data_ltf = bt.feeds.PandasData(dataname=df_1m)
        data_htf = bt.feeds.PandasData(dataname=df_5m)
        cerebro.adddata(data_ltf)
        cerebro.adddata(data_htf)

        cerebro.addstrategy(FastTestStrategy, **strategy_kwargs)
        cerebro.addanalyzer(TradeListAnalyzer, _name="tradelist")

        results = cerebro.run(runonce=False)
        strat = results[0]
        trades = strat.analyzers.tradelist.get_analysis()
        return trades

    def test_generates_closed_trades_on_every_bar_cycle(self):
        trades = self._run(
            {
                "fixed_size": 0.01,
                "force_signal_every_n_bars": 1,
                "max_hold_bars": 1,
                "atr_period": 7,
                "sl_mult": 0.35,
                "tp_mult": 0.55,
            }
        )
        self.assertGreater(len(trades), 20, "FastTestStrategy should generate many closed trades for smoke tests")
        self.assertTrue(all(t.get("exit_reason") != "Unknown" for t in trades))

    def test_time_exit_is_applied_when_sl_tp_far_away(self):
        trades = self._run(
            {
                "fixed_size": 0.01,
                "force_signal_every_n_bars": 1,
                "max_hold_bars": 1,
                "atr_period": 7,
                # Far exits: strategy should close by time exit
                "sl_mult": 20.0,
                "tp_mult": 25.0,
            }
        )
        self.assertGreater(len(trades), 10)
        self.assertIn("Time Exit", {t.get("exit_reason") for t in trades})


if __name__ == "__main__":
    unittest.main()
