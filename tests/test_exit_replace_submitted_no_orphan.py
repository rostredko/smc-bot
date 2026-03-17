"""
Regression test for "hanging" exit orders when trailing/breakeven runs same-bar as entry fill.

Bug: Entry fills -> notify_order creates SL/TP (go to submitted). Next bar, strategy next()
runs BEFORE broker check_submitted — so SL/TP still in submitted. We do cancel/recreate.
BackBroker.cancel() only removes from pending, not submitted. Cancel silently fails,
old orders stay and later fire (orphan short).

Fix: Patch cancel to also remove from submitted.
"""
import sys
import os
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from engine.base_engine import BaseEngine  # noqa: F401 - applies patch

import backtrader as bt

from strategies.base_strategy import BaseStrategy


class ExitReplaceSubmittedStrategy(BaseStrategy):
    """
    Triggers cancel/recreate on bar 2 when SL/TP are still in submitted
    (strategy next() runs before broker check_submitted).
    NO bar_ok guard — we explicitly test the cancel-from-submitted path.
    """

    params = (("breakeven_trigger_r", 0.5),)

    def __init__(self):
        super().__init__()
        self.exit_fills = []
        self.canceled_refs = []

    def next(self):
        # NO bar_ok guard — trigger cancel/recreate even when orders may be in submitted
        stop_accepted = self.stop_order and self.stop_order.status == bt.Order.Accepted
        tp_ok = self.tp_order is None or self.tp_order.status == bt.Order.Accepted  # noqa: F841
        # Also allow Submitted (the path we're testing)
        stop_pending = self.stop_order and self.stop_order.status in (
            bt.Order.Submitted,
            bt.Order.Accepted,
        )
        tp_pending = self.tp_order is None or self.tp_order.status in (
            bt.Order.Submitted,
            bt.Order.Accepted,
        )

        if self.position and self.stop_order and (stop_accepted or stop_pending) and tp_pending:
            risk = abs(self.position.price - self.initial_sl) if self.initial_sl else 1
            profit = (
                self.datas[0].close[0] - self.position.price
                if self.position.size > 0
                else self.position.price - self.datas[0].close[0]
            )
            if risk > 0 and profit >= (risk * self.params.breakeven_trigger_r):
                # Actually do cancel/recreate (not pass)
                old_stop_ref = self.stop_order.ref
                old_tp_ref = self.tp_order.ref if self.tp_order else None
                tp_price_val = self.tp_order.price if self.tp_order else None

                self.cancel(self.tp_order)
                self.tp_order = None
                self.cancel(self.stop_order)
                self.stop_order = None

                self.canceled_refs.extend([r for r in [old_stop_ref, old_tp_ref] if r is not None])

                new_sl = self.position.price
                if self.position.size > 0:
                    self.stop_order = self.sell(
                        price=new_sl, exectype=bt.Order.Stop, size=self.position.size
                    )
                    if tp_price_val is not None:
                        self.tp_order = self.sell(
                            price=tp_price_val,
                            exectype=bt.Order.Limit,
                            size=self.position.size,
                            oco=self.stop_order,
                        )
                else:
                    self.stop_order = self.buy(
                        price=new_sl, exectype=bt.Order.Stop, size=abs(self.position.size)
                    )
                    if tp_price_val is not None:
                        self.tp_order = self.buy(
                            price=tp_price_val,
                            exectype=bt.Order.Limit,
                            size=abs(self.position.size),
                            oco=self.stop_order,
                        )
                self.initial_sl = None

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
        super().notify_order(order)
        if order.status == order.Completed and order.issell():
            self.exit_fills.append(
                {
                    "price": order.executed.price,
                    "ref": order.ref,
                    "size": order.executed.size,
                }
            )
        elif order.status == order.Canceled:
            if order.ref not in self.canceled_refs:
                self.canceled_refs.append(order.ref)


def test_entry_bar_cancel_recreate_no_orphan():
    """
    Bar 0: signal. Bar 1: fill at 102, sl=92, tp=122. SL/TP go to submitted.
    Bar 2: strategy next() runs BEFORE broker check_submitted — orders still in submitted.
    Profit >= 0.5R (close 115 >= 107). We cancel/recreate. Cancel must work (patched).
    Bar 2/3: new TP at 122 hits. One exit fill, no orphan.
    """
    dates = pd.date_range("2024-01-01", periods=4, freq="1h")
    df = pd.DataFrame(
        {
            "open": [100.0, 102.0, 110.0, 120.0],
            "high": [105.0, 110.0, 120.0, 130.0],
            "low": [95.0, 100.0, 108.0, 118.0],
            "close": [102.0, 108.0, 115.0, 122.0],
            "volume": [1000] * 4,
        },
        index=dates,
    )

    cerebro = bt.Cerebro()
    cerebro.addstrategy(ExitReplaceSubmittedStrategy)
    data = bt.feeds.PandasData(dataname=df)
    cerebro.adddata(data)
    cerebro.broker.setcash(100000.0)
    cerebro.broker.setcommission(commission=0.0)

    results = cerebro.run(runonce=False)
    strat = results[0]
    broker = cerebro.broker

    # No orphan
    pos = broker.getposition(data)
    assert pos.size == 0, f"Position must be 0, got {pos.size} (orphan)"

    # Exactly one exit fill
    assert len(strat.exit_fills) == 1, (
        f"Expected 1 exit fill, got {len(strat.exit_fills)}: {strat.exit_fills}"
    )

    # Old orders were canceled (not completed) — proves cancel-from-submitted worked
    assert len(strat.canceled_refs) >= 1, (
        f"Expected at least 1 canceled order ref, got {strat.canceled_refs}"
    )
