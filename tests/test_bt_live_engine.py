import os
import sys
import time
import queue
import asyncio
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.bt_live_engine import BTLiveEngine
from engine.live_ws_client import BinanceWebsocketClient


class _DummyWSClient:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.started = False
        self.joined = False
        self.join_calls = 0
        self.stop_requested = False
        self.name = "DummyWSClient"
        self._alive = False

    def start(self):
        self.started = True

    def join(self, timeout=None):
        self.joined = True
        self.join_calls += 1

    def is_alive(self):
        return self._alive

    def request_stop(self):
        self.stop_requested = True


class _DummyAnalyzer:
    def __init__(self, analysis):
        self._analysis = analysis

    def get_analysis(self):
        return self._analysis


def _fake_strategy():
    return SimpleNamespace(
        analyzers=SimpleNamespace(
            sharpe=_DummyAnalyzer({"sharperatio": 1.23}),
            drawdown=_DummyAnalyzer({"max": {"drawdown": 12.5}}),
            trades=_DummyAnalyzer(
                {
                    "total": {"closed": 2},
                    "won": {"total": 1, "pnl": {"total": 100.0, "average": 100.0}},
                    "lost": {"total": 1, "pnl": {"total": -50.0, "average": -50.0}},
                }
            ),
            tradelist=_DummyAnalyzer([{"id": 1, "realized_pnl": 25.0}]),
            equity=_DummyAnalyzer([{"timestamp": "2026-03-01T00:00:00Z", "equity": 10025.0}]),
        )
    )


def test_init_no_crash():
    config = {"initial_capital": 10000, "exchange": "binance", "symbol": "BTC/USDT", "timeframes": ["1h"]}
    engine = BTLiveEngine(config)
    assert engine.cerebro is not None
    assert engine.strategy is None


@patch("engine.bt_live_engine.BinanceWebsocketClient", side_effect=lambda **kw: _DummyWSClient(**kw))
@patch("engine.bt_live_engine.DataLoader")
def test_add_data_adds_feeds_without_network(data_loader_cls, _ws_cls):
    data_loader = MagicMock()
    data_loader.fetch_recent_bars.return_value = [
        {"timestamp": 1, "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1.0}
    ]
    data_loader_cls.return_value = data_loader

    config = {"initial_capital": 10000, "symbol": "ETH/USDT", "timeframes": ["4h", "15m"]}
    engine = BTLiveEngine(config)
    engine.add_data()

    assert len(engine.cerebro.datas) == 2
    assert len(engine.ws_clients) == 2
    assert all(ws.started for ws in engine.ws_clients)


def test_stop_sets_event_and_joins_clients():
    engine = BTLiveEngine({"initial_capital": 10000, "symbol": "BTC/USDT"})
    ws1 = _DummyWSClient()
    ws2 = _DummyWSClient()
    engine.ws_clients = [ws1, ws2]

    engine.stop()

    assert engine.stop_event.is_set()
    assert ws1.stop_requested and ws2.stop_requested
    assert ws1.joined and ws2.joined
    assert engine.ws_clients == []


def test_stop_is_idempotent_and_does_not_rejoin():
    engine = BTLiveEngine({"initial_capital": 10000, "symbol": "BTC/USDT"})
    ws = _DummyWSClient()
    engine.ws_clients = [ws]

    engine.stop()
    engine.stop()

    assert ws.join_calls == 1


@patch.object(BTLiveEngine, "add_data", autospec=True)
def test_run_live_returns_metrics(add_data_mock):
    config = {"initial_capital": 10000, "symbol": "ADA/USDT"}
    engine = BTLiveEngine(config)
    engine.cerebro.run = MagicMock(return_value=[_fake_strategy()])

    metrics = engine.run_live()

    add_data_mock.assert_called_once_with(engine)
    assert metrics["total_trades"] == 2
    assert metrics["win_count"] == 1
    assert metrics["loss_count"] == 1
    assert "total_pnl" in metrics
    assert len(engine.closed_trades) == 1


@pytest.mark.asyncio
async def test_ws_backoff_sleep_interrupts_on_stop_event():
    stop_event = threading.Event()
    client = BinanceWebsocketClient(
        symbol="BTC/USDT",
        timeframe="1m",
        exchange_type="future",
        data_queue=queue.Queue(),
        stop_event=stop_event,
    )

    async def trigger_stop():
        await asyncio.sleep(0.02)
        stop_event.set()

    asyncio.create_task(trigger_stop())

    started = time.perf_counter()
    await client._sleep_with_stop(1.0, step=0.01)
    elapsed = time.perf_counter() - started

    assert elapsed < 0.2
