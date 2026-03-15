import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from engine.execution_settings import apply_execution_settings, resolve_execution_settings


class _FakeCommissionProvider:
    def fetch_commission_rates(self, *, symbol: str, exchange_type: str) -> tuple[float, float]:
        assert symbol == "BTC/USDT"
        assert exchange_type == "future"
        return 1.5, 3.5


def test_resolve_execution_settings_uses_binance_spot_defaults():
    settings = resolve_execution_settings(
        {
            "exchange": "binance",
            "exchange_type": "spot",
            "execution_mode": "paper",
        }
    )

    assert settings.maker_fee_bps == 10.0
    assert settings.taker_fee_bps == 10.0
    assert settings.broker_commission_bps == 10.0
    assert settings.commission_rate == 0.001
    assert settings.fee_source == "exchange_default"


def test_resolve_execution_settings_converts_legacy_taker_fee_percent():
    settings = resolve_execution_settings(
        {
            "exchange": "binance",
            "exchange_type": "future",
            "taker_fee": 0.04,
        }
    )

    assert settings.taker_fee_bps == 4.0
    assert settings.broker_commission_bps == 4.0
    assert settings.commission_rate == 0.0004
    assert settings.fee_source == "legacy_taker_fee"


def test_resolve_execution_settings_uses_commission_provider_for_real_mode():
    settings = resolve_execution_settings(
        {
            "exchange": "binance",
            "exchange_type": "future",
            "execution_mode": "real",
            "symbol": "BTC/USDT",
        },
        commission_provider=_FakeCommissionProvider(),
    )

    assert settings.maker_fee_bps == 1.5
    assert settings.taker_fee_bps == 3.5
    assert settings.broker_commission_bps == 3.5
    assert settings.fee_source == "binance_api"


def test_apply_execution_settings_merges_fields_into_config():
    config = apply_execution_settings({"exchange": "binance", "exchange_type": "future"})

    assert config["execution_mode"] == "paper"
    assert config["maker_fee_bps"] == 2.0
    assert config["taker_fee_bps"] == 4.0
    assert config["commission"] == 0.0004
    assert config["paper_commission_side"] == "taker"


def test_exchange_default_fee_source_does_not_lock_old_derived_values():
    config = apply_execution_settings(
        {
            "exchange": "binance",
            "exchange_type": "spot",
            "fee_source": "exchange_default",
            "maker_fee_bps": 2.0,
            "taker_fee_bps": 4.0,
            "commission": 0.0004,
        }
    )

    assert config["maker_fee_bps"] == 10.0
    assert config["taker_fee_bps"] == 10.0
    assert config["commission"] == 0.001
