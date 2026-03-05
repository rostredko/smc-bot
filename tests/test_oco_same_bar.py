"""
Regression test for OCO same-bar ghost-trade fix.

When both TP and SL are eligible in one bar (high >= tp and low <= sl),
only one must execute. Without the OCO guard patch, both can fill and
the second creates an orphan short (ghost trade).
"""
import sys
import os
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Apply OCO patch before Cerebro (via base_engine import)
from engine.base_engine import BaseEngine  # noqa: F401 - applies patch

import backtrader as bt


class OCOMinimalStrategy(bt.Strategy):
    """Minimal strategy: bar 0 buy, notify_order sets SL/TP via OCO (exec_price-based)."""

    def __init__(self):
        self.order = None
        self.stop_order = None
        self.tp_order = None
        self.pending_metadata = None
        self.exit_fills = []
        self.entry_fill_price = None

    def next(self):
        if self.order:
            return
        if self.position:
            return
        # Bar 0: enter long
        self.pending_metadata = {
            "sl_distance": 10.0,
            "tp_distance": 20.0,
            "direction": "long",
        }
        self.order = self.buy(size=1.0, exectype=bt.Order.Market)

    def notify_order(self, order):
        if order.status in (order.Submitted, order.Accepted):
            return

        if order.status == order.Completed:
            exec_price = order.executed.price
            if order == self.order:
                self.order = None
                self.entry_fill_price = exec_price
                meta = self.pending_metadata or {}
                sl_dist = meta.get("sl_distance", 10.0)
                tp_dist = meta.get("tp_distance", 20.0)
                direction = meta.get("direction", "long")
                size = abs(order.executed.size)
                # Stop first, TP with oco=Stop — ambiguous bar: Stop priority
                if direction == "long":
                    real_sl = exec_price - sl_dist
                    real_tp = exec_price + tp_dist
                    self.stop_order = self.sell(
                        price=real_sl, exectype=bt.Order.Stop, size=size
                    )
                    self.tp_order = self.sell(
                        price=real_tp,
                        exectype=bt.Order.Limit,
                        size=size,
                        oco=self.stop_order,
                    )
                else:
                    real_sl = exec_price + sl_dist
                    real_tp = exec_price - tp_dist
                    self.stop_order = self.buy(
                        price=real_sl, exectype=bt.Order.Stop, size=size
                    )
                    self.tp_order = self.buy(
                        price=real_tp,
                        exectype=bt.Order.Limit,
                        size=size,
                        oco=self.stop_order,
                    )
                self.pending_metadata = None
                return

            self.exit_fills.append(
                {"price": exec_price, "ref": order.ref, "size": order.executed.size}
            )
            if self.stop_order and order.ref == self.stop_order.ref:
                self.stop_order = None
                if self.tp_order:
                    self.cancel(self.tp_order)
                    self.tp_order = None
            elif self.tp_order and order.ref == self.tp_order.ref:
                self.tp_order = None
                if self.stop_order:
                    self.cancel(self.stop_order)
                    self.stop_order = None

        elif order.status in (order.Canceled, order.Margin, order.Rejected):
            if order == self.stop_order:
                self.stop_order = None
            elif order == self.tp_order:
                self.tp_order = None
            elif order == self.order:
                self.order = None


def test_oco_same_bar_only_one_fill():
    """Pathological bar: high >= tp and low <= sl. Only one exit must execute."""
    # Bar 0: normal, entry will fill on bar 1 open
    # Bar 1: open=102 (exec_price), sl=92, tp=122; high=125, low=90 -> both hit
    dates = pd.date_range("2024-01-01", periods=3, freq="1h")
    df = pd.DataFrame(
        {
            "open": [100.0, 102.0, 102.0],
            "high": [105.0, 125.0, 125.0],  # bar 1: high >= tp (122)
            "low": [95.0, 90.0, 90.0],      # bar 1: low <= sl (92)
            "close": [102.0, 102.0, 102.0],
            "volume": [1000] * 3,
        },
        index=dates,
    )

    cerebro = bt.Cerebro()
    cerebro.addstrategy(OCOMinimalStrategy)
    data = bt.feeds.PandasData(dataname=df)
    cerebro.adddata(data)
    cerebro.broker.setcash(100000.0)
    cerebro.broker.setcommission(commission=0.0)

    results = cerebro.run()
    strat = results[0]
    broker = cerebro.broker

    # Position must be flat (no ghost short)
    pos = broker.getposition(data)
    assert pos.size == 0, f"Position must be 0, got {pos.size} (ghost trade)"

    # Exactly one exit fill (TP or SL)
    assert len(strat.exit_fills) == 1, (
        f"Expected 1 exit fill, got {len(strat.exit_fills)}: {strat.exit_fills}"
    )

    # Exit order must be sell (closing long) — size is negative for sell
    exit_fill = strat.exit_fills[0]
    assert abs(exit_fill["size"]) == 1.0, "Exit must close 1 unit"

    # No open short
    assert broker.getvalue() > 0, "Account value must be positive after close"


def test_oco_same_bar_second_order_cancelled():
    """Same setup: verify the second OCO order is cancelled, not executed."""
    dates = pd.date_range("2024-01-01", periods=3, freq="1h")
    df = pd.DataFrame(
        {
            "open": [100.0, 102.0, 102.0],
            "high": [105.0, 125.0, 125.0],
            "low": [95.0, 90.0, 90.0],
            "close": [102.0, 102.0, 102.0],
            "volume": [1000] * 3,
        },
        index=dates,
    )

    cerebro = bt.Cerebro()
    cerebro.addstrategy(OCOMinimalStrategy)
    data = bt.feeds.PandasData(dataname=df)
    cerebro.adddata(data)
    cerebro.broker.setcash(100000.0)
    cerebro.broker.setcommission(commission=0.0)

    results = cerebro.run()
    strat = results[0]

    # One exit filled
    assert len(strat.exit_fills) == 1
    # The other order was cancelled (not in exit_fills)
    # Both TP and SL were in same OCO group; only one executed
    assert strat.entry_fill_price is not None
    sl_price = strat.entry_fill_price - 10
    tp_price = strat.entry_fill_price + 20
    exit_price = strat.exit_fills[0]["price"]
    # Exit must be either TP or SL
    assert exit_price in (sl_price, tp_price), (
        f"Exit price {exit_price} must be SL={sl_price} or TP={tp_price}"
    )
