import os
import sys
import queue
import threading
import asyncio
import time
from unittest.mock import patch, MagicMock

import pytest

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.live_ws_client import (
    BinancePythonBinanceWsClient,
    create_live_stream_client,
)

class _FakeAsyncClient:
    def __init__(self):
        self.closed = False

    async def close_connection(self):
        self.closed = True

    @classmethod
    async def create(cls):
        return cls()

class _FakeStream:
    def __init__(self):
        pass
    async def recv(self):
        await asyncio.sleep(86400)

class _FakeSocketContext:
    def __init__(self):
        pass
    async def __aenter__(self):
        return _FakeStream()
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

class _FakeBinanceSocketManager:
    instances = []

    def __init__(self, client):
        self.client = client
        self.spot_calls = []
        self.futures_calls = []
        _FakeBinanceSocketManager.instances.append(self)

    def kline_socket(self, symbol, interval="1m"):
        self.spot_calls.append({"symbol": symbol, "interval": interval})
        return _FakeSocketContext()

    def futures_multiplex_socket(self, streams):
        self.futures_calls.append({"streams": streams})
        return _FakeSocketContext()

def _make_client(exchange_type="future"):
    return BinancePythonBinanceWsClient(
        symbol="BTC/USDT",
        timeframe="1m",
        exchange_type=exchange_type,
        data_queue=queue.Queue(),
        stop_event=threading.Event(),
    )

def test_create_live_stream_client_returns_binance_adapter():
    client = create_live_stream_client(
        exchange_name="binance",
        symbol="BTC/USDT",
        timeframe="1m",
        exchange_type="future",
        data_queue=queue.Queue(),
        stop_event=threading.Event(),
    )
    assert isinstance(client, BinancePythonBinanceWsClient)

def test_create_live_stream_client_rejects_unsupported_exchange():
    with pytest.raises(ValueError, match="Unsupported live exchange"):
        create_live_stream_client(
            exchange_name="bybit",
            symbol="BTC/USDT",
            timeframe="1m",
            exchange_type="future",
            data_queue=queue.Queue(),
            stop_event=threading.Event(),
        )

@patch("engine.live_ws_client.AsyncClient", _FakeAsyncClient)
@patch("engine.live_ws_client.BinanceSocketManager", _FakeBinanceSocketManager)
def test_binance_ws_client_uses_futures_socket_for_future_market():
    _FakeBinanceSocketManager.instances.clear()
    client = _make_client(exchange_type="future")

    client.start()
    # give it a moment to run
    import time
    time.sleep(0.1)

    manager = _FakeBinanceSocketManager.instances[-1]
    assert len(manager.futures_calls) == 1
    assert manager.futures_calls[0]["streams"] == ["btcusdt@kline_1m"]
    assert manager.spot_calls == []
    
    client.request_stop()
    client.join(timeout=1.0)

@patch("engine.live_ws_client.AsyncClient", _FakeAsyncClient)
@patch("engine.live_ws_client.BinanceSocketManager", _FakeBinanceSocketManager)
def test_binance_ws_client_uses_spot_socket_for_spot_market():
    _FakeBinanceSocketManager.instances.clear()
    client = _make_client(exchange_type="spot")

    client.start()
    import time
    time.sleep(0.1)

    manager = _FakeBinanceSocketManager.instances[-1]
    assert len(manager.spot_calls) == 1
    assert manager.spot_calls[0]["symbol"] == "BTCUSDT"
    assert manager.spot_calls[0]["interval"] == "1m"
    assert manager.futures_calls == []

    client.request_stop()
    client.join(timeout=1.0)

def test_binance_ws_client_maps_closed_kline_payload_into_queue():
    q = queue.Queue()
    client = BinancePythonBinanceWsClient(
        symbol="BTC/USDT",
        timeframe="1m",
        exchange_type="future",
        data_queue=q,
        stop_event=threading.Event(),
    )

    client._handle_socket_message(
        {
            "data": {
                "e": "kline",
                "k": {
                    "t": 1700000000000,
                    "o": "100.0",
                    "h": "110.0",
                    "l": "90.0",
                    "c": "105.0",
                    "v": "1234.5",
                    "x": True,
                },
            }
        }
    )

    assert q.qsize() == 1
    assert q.get_nowait() == {
        "timestamp": 1700000000000,
        "open": 100.0,
        "high": 110.0,
        "low": 90.0,
        "close": 105.0,
        "volume": 1234.5,
    }

@patch("engine.live_ws_client.AsyncClient", _FakeAsyncClient)
@patch("engine.live_ws_client.BinanceSocketManager", _FakeBinanceSocketManager)
def test_binance_ws_client_request_stop_stops_socket_and_manager():
    _FakeBinanceSocketManager.instances.clear()
    client = _make_client(exchange_type="future")

    client.start()
    import time
    time.sleep(0.1)
    
    manager = _FakeBinanceSocketManager.instances[-1]
    client.request_stop()
    client.join(timeout=1.0)
    
    assert client.stop_event.is_set() is True
    assert getattr(manager.client, "closed", False) is True
    assert client.is_alive() is False


class _BoomAsyncClient:
    @classmethod
    async def create(cls):
        raise RuntimeError("boom")


@patch("engine.live_ws_client.AsyncClient", _BoomAsyncClient)
@patch("engine.live_ws_client.BinanceSocketManager", _FakeBinanceSocketManager)
def test_binance_ws_client_stop_interrupts_retry_backoff():
    client = _make_client(exchange_type="future")

    client.start()
    time.sleep(0.1)
    client.request_stop()
    client.join(timeout=0.3)

    assert client.is_alive() is False
