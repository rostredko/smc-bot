from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from engine.execution_settings import is_futures_exchange_type

try:
    from binance.client import Client
except ImportError:  # pragma: no cover - runtime dependency
    Client = None


@dataclass(frozen=True)
class CommissionRates:
    maker_fee_bps: float
    taker_fee_bps: float
    source: str = "binance_api"


class BinanceCommissionRateClient:
    """
    Thin signed-endpoint adapter for future real-exchange trading.

    It is intentionally not used by paper mode. Real mode should fetch
    per-account commission rates instead of relying on static defaults.
    """

    def __init__(
        self,
        *,
        api_key: str,
        api_secret: str,
        testnet: bool = False,
        client: Any | None = None,
    ):
        if client is None and Client is None:
            raise RuntimeError("python-binance is not installed. Install python-binance to query Binance fees.")

        self._client = client or Client(api_key, api_secret, testnet=testnet)

    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        return str(symbol or "").replace("/", "").upper()

    @staticmethod
    def _to_bps(rate: Any) -> float:
        return float(rate) * 10000.0

    def fetch_commission_rates(self, *, symbol: str, exchange_type: str) -> tuple[float, float]:
        normalized_symbol = self._normalize_symbol(symbol)
        if is_futures_exchange_type(exchange_type):
            payload = self._client.futures_commission_rate(symbol=normalized_symbol)
            return (
                self._to_bps(payload["makerCommissionRate"]),
                self._to_bps(payload["takerCommissionRate"]),
            )

        payload = self._client.v3_get_account_commission(symbol=normalized_symbol)
        standard = payload.get("standardCommission", {}) if isinstance(payload, dict) else {}
        return (
            self._to_bps(standard["maker"]),
            self._to_bps(standard["taker"]),
        )

    def close(self) -> None:
        close_connection = getattr(self._client, "close_connection", None)
        if callable(close_connection):
            close_connection()
