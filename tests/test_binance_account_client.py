import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from engine.binance_account_client import BinanceCommissionRateClient


class _FakeBinanceClient:
    def __init__(self):
        self.closed = False

    def futures_commission_rate(self, **params):
        assert params["symbol"] == "BTCUSDT"
        return {
            "symbol": "BTCUSDT",
            "makerCommissionRate": "0.0002",
            "takerCommissionRate": "0.0004",
        }

    def v3_get_account_commission(self, **params):
        assert params["symbol"] == "ETHUSDT"
        return {
            "symbol": "ETHUSDT",
            "standardCommission": {
                "maker": "0.00100000",
                "taker": "0.00100000",
            },
        }

    def close_connection(self):
        self.closed = True


def test_fetch_commission_rates_for_futures_converts_to_bps():
    client = BinanceCommissionRateClient(api_key="x", api_secret="y", client=_FakeBinanceClient())

    maker_bps, taker_bps = client.fetch_commission_rates(symbol="BTC/USDT", exchange_type="future")

    assert maker_bps == 2.0
    assert taker_bps == 4.0


def test_fetch_commission_rates_for_spot_reads_standard_commission():
    client = BinanceCommissionRateClient(api_key="x", api_secret="y", client=_FakeBinanceClient())

    maker_bps, taker_bps = client.fetch_commission_rates(symbol="ETH/USDT", exchange_type="spot")

    assert maker_bps == 10.0
    assert taker_bps == 10.0


def test_close_delegates_to_underlying_client():
    fake_client = _FakeBinanceClient()
    client = BinanceCommissionRateClient(api_key="x", api_secret="y", client=fake_client)

    client.close()

    assert fake_client.closed is True
