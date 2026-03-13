import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "web-dashboard"))

from services.strategy_runtime import build_runtime_strategy_config, resolve_strategy_class


def test_resolve_strategy_class_aliases():
    cls_main = resolve_strategy_class("bt_price_action")
    cls_alias = resolve_strategy_class("price_action_strategy")
    assert cls_main is cls_alias


def test_build_runtime_strategy_config_overrides_runtime_controls():
    cfg = {
        "risk_per_trade": 2.0,
        "leverage": 7.0,
        "dynamic_position_sizing": False,
        "max_drawdown": 30.0,
        "trailing_stop_distance": 0.02,
        "breakeven_trigger_r": 1.2,
        "position_cap_adverse": 0.8,
        "funding_rate_per_8h": 0.0001,
        "funding_interval_hours": 8,
        "strategy_config": {
            "risk_per_trade": 999,
            "trailing_stop_distance": 999,
            "custom_param": 42,
        },
    }
    st = build_runtime_strategy_config(cfg)
    assert st["risk_per_trade"] == 2.0
    assert st["leverage"] == 7.0
    assert st["dynamic_position_sizing"] is False
    assert st["max_drawdown"] == 30.0
    assert st["trailing_stop_distance"] == 0.02
    assert st["breakeven_trigger_r"] == 1.2
    assert st["position_cap_adverse"] == 0.8
    assert st["funding_rate_per_8h"] == 0.0001
    assert st["funding_interval_hours"] == 8
    assert st["custom_param"] == 42
