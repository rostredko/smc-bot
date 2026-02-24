"""Test legacy result backfill: GET /results/{filename} adds config when missing."""
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'web-dashboard'))
sys.path.insert(0, PROJECT_ROOT)

from fastapi.testclient import TestClient

from server import app
from db.repositories import BacktestRepository

client = TestClient(app)


def test_legacy_result_backfill_adds_configuration():
    """Legacy result (no config) returns backfilled config and persists."""
    filename = "test_legacy_backfill_me.json"
    run_id = "test_legacy_backfill_me"
    legacy_data = {
        "total_pnl": 100,
        "total_trades": 5,
        "win_rate": 60,
        "trades": [
            {"id": 1, "entry_time": "2025-01-01T12:00:00", "exit_time": "2025-01-02T12:00:00"}
        ],
    }
    BacktestRepository().save(run_id, legacy_data)

    response = client.get(f"/results/{filename}")
    assert response.status_code == 200
    data = response.json()

    assert "configuration" in data
    cfg = data["configuration"]
    assert cfg.get("symbol") == "BTC/USDT"
    assert cfg.get("timeframes") == ["1h"]
    assert cfg.get("strategy") == "bt_price_action"
    assert cfg.get("_legacy_default") is True
    assert "strategy_config" in cfg
    sc = cfg["strategy_config"]
    assert sc.get("trend_ema_period") == 200
    assert sc.get("rsi_period") == 14
    assert sc.get("adx_period") == 14

    persisted = BacktestRepository().get_by_id(run_id)
    assert "configuration" in persisted


def test_result_with_existing_configuration_unchanged():
    """Loading a result that already has configuration returns it unchanged."""
    filename = "test_has_config_backfill.json"
    run_id = "test_has_config_backfill"
    data_with_config = {
        "total_pnl": 50,
        "configuration": {
            "symbol": "ETH/USDT",
            "timeframes": ["4h", "1h"],
            "strategy_config": {"trend_ema_period": 100, "rsi_period": 7},
        },
    }
    BacktestRepository().save(run_id, data_with_config)

    response = client.get(f"/results/{filename}")
    assert response.status_code == 200
    data = response.json()
    assert data["configuration"]["symbol"] == "ETH/USDT"
    sc = data["configuration"]["strategy_config"]
    assert sc["trend_ema_period"] == 100
