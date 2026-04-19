"""Characterization tests for Phase 1 guardrails.

These tests freeze the externally observable shape of seams that Phase 2 will
move. They do not pin internal implementation details — they pin the contract
that callers (CLI, API consumers, dashboard providers) already depend on.

Covered:
- Config normalization parity: runtime controls supplied at the top level of a
  config dict win over same-key values embedded in `strategy_config`, and the
  resulting dict always carries a fixed set of runtime-control keys regardless
  of whether the caller supplied them.
- Runtime state restore payload shape: `GET /api/runtime/state` returns a
  stable `{ backtest, live, console }` envelope when no run is active; the
  dashboard's `BacktestProvider` / `RuntimeStateProvider` depend on this
  shape.
"""

import os
import sys

from fastapi.testclient import TestClient

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "web-dashboard"))
sys.path.insert(0, PROJECT_ROOT)

from server import (  # noqa: E402
    app,
    active_console_lock,
    active_console_state,
    live_trading_state,
    running_backtests,
)
from services.strategy_runtime import build_runtime_strategy_config  # noqa: E402


client = TestClient(app)


RUNTIME_CONTROL_KEYS = {
    "trailing_stop_distance",
    "breakeven_trigger_r",
    "risk_per_trade",
    "leverage",
    "dynamic_position_sizing",
    "max_drawdown",
    "position_cap_adverse",
    "funding_rate_per_8h",
    "funding_interval_hours",
    "detailed_signals",
    "market_analysis",
}


# ---------------------------------------------------------------------------
# Config normalization parity
# ---------------------------------------------------------------------------


def test_runtime_config_always_emits_runtime_control_keys():
    """An empty config still produces every runtime-control key with defaults."""

    result = build_runtime_strategy_config({})

    missing = RUNTIME_CONTROL_KEYS - set(result.keys())
    assert not missing, f"missing runtime-control keys: {sorted(missing)}"


def test_runtime_config_top_level_overrides_strategy_config_for_runtime_keys():
    """Top-level runtime controls must override same keys inside strategy_config.

    This is the contract both the API path (server.py start_backtest) and the
    CLI path (main.py → engine) rely on: users set runtime controls at the top
    level and expect them to win over any stale value inside strategy_config.
    """

    config = {
        "risk_per_trade": 2.5,
        "leverage": 5.0,
        "trailing_stop_distance": 0.03,
        "max_drawdown": 25.0,
        "position_cap_adverse": 0.7,
        "funding_rate_per_8h": 0.0002,
        "funding_interval_hours": 4,
        "dynamic_position_sizing": False,
        "detailed_signals": False,
        "market_analysis": False,
        "strategy_config": {
            "risk_per_trade": 99,
            "leverage": 99,
            "trailing_stop_distance": 99,
            "max_drawdown": 99,
            "position_cap_adverse": 99,
            "funding_rate_per_8h": 99,
            "funding_interval_hours": 99,
            "dynamic_position_sizing": True,
            "detailed_signals": True,
            "market_analysis": True,
            "custom_strategy_param": "keep",
        },
    }

    result = build_runtime_strategy_config(config)

    assert result["risk_per_trade"] == 2.5
    assert result["leverage"] == 5.0
    assert result["trailing_stop_distance"] == 0.03
    assert result["max_drawdown"] == 25.0
    assert result["position_cap_adverse"] == 0.7
    assert result["funding_rate_per_8h"] == 0.0002
    assert result["funding_interval_hours"] == 4
    assert result["dynamic_position_sizing"] is False
    assert result["detailed_signals"] is False
    assert result["market_analysis"] is False
    assert result["custom_strategy_param"] == "keep"


def test_runtime_config_breakeven_flag_respected_when_set_in_strategy_config():
    """`use_breakeven_sl` inside strategy_config steers breakeven_trigger_r.

    Flag on + `breakeven_sl` value → that value becomes `breakeven_trigger_r`.
    Flag off → `breakeven_trigger_r` forced to 0.0 regardless of top level.
    """

    on_config = {
        "breakeven_trigger_r": 0.0,
        "strategy_config": {"use_breakeven_sl": True, "breakeven_sl": 1.75},
    }
    off_config = {
        "breakeven_trigger_r": 2.0,
        "strategy_config": {"use_breakeven_sl": False, "breakeven_sl": 1.75},
    }

    assert build_runtime_strategy_config(on_config)["breakeven_trigger_r"] == 1.75
    assert build_runtime_strategy_config(off_config)["breakeven_trigger_r"] == 0.0


# ---------------------------------------------------------------------------
# Runtime state restore payload shape
# ---------------------------------------------------------------------------


def _reset_runtime_state():
    live_trading_state["is_running"] = False
    live_trading_state["engine"] = None
    live_trading_state["run_id"] = None
    live_trading_state["config"] = None
    live_trading_state["start_time"] = None
    live_trading_state["stop_requested"] = False
    running_backtests.clear()
    with active_console_lock:
        active_console_state["run_id"] = None
        active_console_state["run_type"] = None
        active_console_state["lines"].clear()


def test_runtime_state_envelope_is_stable_when_idle():
    """`GET /api/runtime/state` must always return backtest/live/console keys."""

    _reset_runtime_state()
    try:
        response = client.get("/api/runtime/state")
        assert response.status_code == 200
        payload = response.json()

        assert set(payload.keys()) == {"backtest", "live", "console"}

        # Idle backtest -> None
        assert payload["backtest"] is None

        # Idle live payload is always an object with the documented fields.
        live = payload["live"]
        assert isinstance(live, dict)
        assert set(live.keys()) == {
            "is_running",
            "run_id",
            "start_time",
            "stop_requested",
            "config",
        }
        assert live["is_running"] is False
        assert live["run_id"] is None
        assert live["start_time"] is None
        assert live["stop_requested"] is False
        assert live["config"] is None

        # Idle console always exposes run_id/run_type/lines keys, lines empty.
        console = payload["console"]
        assert isinstance(console, dict)
        assert set(console.keys()) == {"run_id", "run_type", "lines"}
        assert console["run_id"] is None
        assert console["run_type"] is None
        assert console["lines"] == []
    finally:
        _reset_runtime_state()
