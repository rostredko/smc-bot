import os
import sys
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "web-dashboard"))
sys.path.insert(0, PROJECT_ROOT)

from server import app, live_trading_state, run_live_trading_task
from db.repositories import UserConfigRepository


client = TestClient(app)


def _reset_live_state():
    live_trading_state["is_running"] = False
    live_trading_state["engine"] = None
    live_trading_state["start_time"] = None
    live_trading_state["stop_requested"] = False


def test_stop_live_accepts_request_before_engine_is_attached():
    _reset_live_state()
    live_trading_state["is_running"] = True

    resp = client.post("/api/live/stop")
    assert resp.status_code == 200
    assert live_trading_state["stop_requested"] is True

    _reset_live_state()


def test_nested_user_config_flatten_includes_position_cap_adverse():
    repo = UserConfigRepository()
    name = f"tmp_cfg_{uuid4().hex[:8]}"
    nested = {
        "account": {
            "initial_capital": 15000,
            "risk_per_trade": 1.2,
            "max_drawdown": 25,
            "max_positions": 2,
            "leverage": 5,
        },
        "trading": {"symbol": "ETH/USDT", "timeframes": ["4h", "1h"]},
        "period": {"start_date": "2025-01-01", "end_date": "2025-03-01"},
        "strategy": {"name": "bt_price_action", "config": {"use_trend_filter": True}},
        "position_cap_adverse": 0.7,
    }
    repo.save(name, nested)

    try:
        resp = client.get(f"/api/user-configs/{name}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["position_cap_adverse"] == 0.7
        assert data["symbol"] == "ETH/USDT"
        assert data["strategy"] == "bt_price_action"
    finally:
        repo.delete(name)


@pytest.mark.asyncio
@patch("server.setup_logging")
@patch("server.DataLoader")
@patch("server.BacktestRepository")
@patch("server.BTLiveEngine")
async def test_live_task_saves_history_even_with_empty_metrics(
    engine_cls,
    repo_cls,
    loader_cls,
    _setup_logging,
):
    _reset_live_state()

    engine = MagicMock()
    engine.closed_trades = []
    engine.equity_curve = []
    engine.run_live.return_value = {}
    engine_cls.return_value = engine

    repo = MagicMock()
    repo_cls.return_value = repo

    with patch("server.broadcast_message", new=AsyncMock()):
        await run_live_trading_task(
            {
                "symbol": "BTC/USDT",
                "timeframes": ["1m"],
                "strategy": "fast_test_strategy",
                "initial_capital": 10000,
            }
        )

    assert repo.save.called
    assert repo.save.call_args.kwargs.get("is_live") is True
    saved_doc = repo.save.call_args.args[1]
    assert saved_doc.get("total_trades") == 0
    assert saved_doc.get("trades") == []
    assert saved_doc.get("signals_generated") == 0
    loader_cls.assert_not_called()
