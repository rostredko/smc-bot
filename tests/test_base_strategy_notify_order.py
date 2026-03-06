from types import SimpleNamespace

from strategies.base_strategy import BaseStrategy


class DummyOrder:
    Submitted = 1
    Accepted = 2
    Completed = 3
    Canceled = 4
    Margin = 5
    Rejected = 6

    def __init__(self, status: int):
        self.status = status
        self.info = {}


def _make_strategy() -> BaseStrategy:
    strategy = BaseStrategy.__new__(BaseStrategy)
    strategy.order = None
    strategy.stop_order = None
    strategy.tp_order = None
    strategy.cancel_reason = None
    strategy.params = SimpleNamespace(max_drawdown=30.0, stop_on_drawdown=True)
    strategy._dd_limit_hit = False
    strategy._get_local_dt_str = lambda *args, **kwargs: "2026-03-06 00:00:00"
    return strategy


def test_notify_order_canceled_clears_entry_when_order_is_list():
    strategy = _make_strategy()
    entry = DummyOrder(DummyOrder.Canceled)
    strategy.order = [entry]

    BaseStrategy.notify_order(strategy, entry)

    assert strategy.order is None


def test_notify_order_margin_sets_dd_flag_and_clears_entry_when_order_is_list():
    strategy = _make_strategy()
    entry = DummyOrder(DummyOrder.Margin)
    strategy.order = [entry]

    BaseStrategy.notify_order(strategy, entry)

    assert strategy.order is None
    assert strategy._dd_limit_hit is True
