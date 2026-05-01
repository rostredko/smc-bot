# Exchange Adapters — Koval

## ExchangeAdapter interface

All exchanges implement `koval/exchanges/base.py::ExchangeAdapter`:

```python
from abc import ABC, abstractmethod
from typing import AsyncIterator

class ExchangeAdapter(ABC):
    @abstractmethod
    def fetch_ohlcv(
        self,
        symbol: str,       # "BTC/USDT"
        timeframe: str,    # "1h", "4h", "1d"
        since: int | None = None,   # unix ms
        limit: int = 500,
    ) -> list[list]:       # [[time_ms, open, high, low, close, volume], ...]
        ...

    @abstractmethod
    def get_live_feed(self, symbol: str, timeframe: str):
        """Returns a Backtrader-compatible live data feed."""
        ...

    @abstractmethod
    async def place_order(
        self, symbol: str, side: str, size: float,
        price: float | None = None, order_type: str = "market",
    ) -> dict:
        ...

    @abstractmethod
    async def get_balance(self) -> float:
        ...

    @abstractmethod
    async def get_open_positions(self) -> list[dict]:
        ...
```

## Binance adapter

**File:** `koval/exchanges/binance.py`

**Source:** Ported and refactored from smc-bot `engine/data_loader.py` + `engine/live_ws_client.py`.

```python
from koval.exchanges.binance import BinanceAdapter

# Testnet (sandbox)
adapter = BinanceAdapter(
    api_key=os.getenv("BINANCE_API_KEY"),
    api_secret=os.getenv("BINANCE_API_SECRET"),
    testnet=True,
)

# Production
adapter = BinanceAdapter(
    api_key=os.getenv("BINANCE_API_KEY"),
    api_secret=os.getenv("BINANCE_API_SECRET"),
    testnet=False,
)

ohlcv = adapter.fetch_ohlcv("BTC/USDT", "1h", limit=500)
```

**Testnet URL:** `https://testnet.binancefuture.com`

## WhiteBIT adapter

**File:** `koval/exchanges/whitebit.py`

**API docs:** https://whitebit.com/api/docs (v4)

```python
from koval.exchanges.whitebit import WhiteBITAdapter

adapter = WhiteBITAdapter(
    api_key=os.getenv("WHITEBIT_API_KEY"),
    api_secret=os.getenv("WHITEBIT_API_SECRET"),
    testnet=True,
)

ohlcv = adapter.fetch_ohlcv("BTC_USDT", "1h", limit=500)
```

**WhiteBIT symbol format:** `BTC_USDT` (underscore, not slash)

**Key endpoints (v4 REST):**
- OHLCV: `GET /api/v4/public/kline` — params: `market`, `interval`, `limit`
- WebSocket: `wss://api.whitebit.com/ws` — subscribe to `candles_subscribe`

**Interval mapping:**

| Koval timeframe | WhiteBIT interval |
|----------------|-------------------|
| `1m` | `1m` |
| `5m` | `5m` |
| `15m` | `15m` |
| `1h` | `1h` |
| `4h` | `4h` |
| `1d` | `1d` |

## How to add a new exchange

1. Create `koval/exchanges/<exchange_name>.py`
2. Implement all `ExchangeAdapter` abstract methods
3. Add to `koval/exchanges/__init__.py` registry
4. Write tests in `tests/exchanges/test_<exchange_name>.py` with mocked HTTP
5. Add env vars to `.env.example`
6. Document here

## Testing adapters

Use `pytest-httpx` or `responses` to mock HTTP calls:

```python
import pytest
import responses
from koval.exchanges.binance import BinanceAdapter

@responses.activate
def test_binance_fetch_ohlcv():
    responses.add(
        responses.GET,
        "https://testnet.binancefuture.com/fapi/v1/klines",
        json=[[1704067200000, "42000", "42500", "41800", "42200", "100", ...]],
    )
    adapter = BinanceAdapter(api_key="test", api_secret="test", testnet=True)
    data = adapter.fetch_ohlcv("BTC/USDT", "1h", limit=1)
    assert len(data) == 1
    assert data[0][4] == 42200.0  # close price
```
