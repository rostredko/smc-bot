import os
import sys
from pathlib import Path

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "web-dashboard"))

from services.strategy_runtime import (
    build_runtime_strategy_config,
    build_opt_strategy_config,
    discover_strategy_definitions,
    list_dashboard_strategies,
    resolve_strategy_class,
)


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


def test_build_opt_strategy_config_replaces_whitelisted_params_with_lists():
    cfg = {
        "strategy_config": {"risk_reward_ratio": 2.0, "sl_buffer_atr": 1.3, "trailing_stop_distance": 0.0},
        "opt_params": {
            "risk_reward_ratio": [1.5, 2.0, 2.5],
            "sl_buffer_atr": [1.0, 1.3, 1.5],
            "trailing_stop_distance": [0, 0.01, 0.02],
        },
        "risk_per_trade": 1.5,
        "leverage": 10.0,
    }
    out = build_opt_strategy_config(cfg)
    assert out["risk_reward_ratio"] == [1.5, 2.0, 2.5]
    assert out["sl_buffer_atr"] == [1.0, 1.3, 1.5]
    assert out["trailing_stop_distance"] == [0, 0.01, 0.02]
    assert out["risk_per_trade"] == 1.5


def test_build_opt_strategy_config_ignores_non_whitelisted_opt_params():
    cfg = {
        "strategy_config": {"risk_reward_ratio": 2.0},
        "opt_params": {"risk_reward_ratio": [1.5, 2.0], "atr_period": [7, 14]},
    }
    out = build_opt_strategy_config(cfg)
    assert out["risk_reward_ratio"] == [1.5, 2.0]
    assert "atr_period" not in out or out.get("atr_period") != [7, 14]


def test_list_dashboard_strategies_returns_only_public_runtime_strategies():
    strategies = list_dashboard_strategies()
    names = [strategy["name"] for strategy in strategies]

    assert names == ["bt_price_action", "fast_test_strategy", "fvg_sweep_choch_strategy"]
    assert "price_action_strategy" not in names
    assert "market_structure" not in names


def test_discover_strategy_definitions_picks_new_strategy_classes_from_modules():
    strategies_dir = Path(PROJECT_ROOT) / "strategies"
    module_path = strategies_dir / "temporary_breakout.py"
    module_name = "strategies.temporary_breakout"

    module_path.write_text(
        "\n".join(
            [
                "from strategies.base_strategy import BaseStrategy",
                "",
                "class TemporaryBreakoutStrategy(BaseStrategy):",
                "    params = ()",
                "",
                "    def next(self):",
                "        return None",
                "",
                "class HelperThing:",
                "    pass",
            ]
        ),
        encoding="utf-8",
    )

    try:
        sys.modules.pop(module_name, None)
        definitions = discover_strategy_definitions()
        names = [definition["name"] for definition in definitions]

        assert "temporary_breakout_strategy" in names

        breakout_definition = next(
            definition for definition in definitions if definition["name"] == "temporary_breakout_strategy"
        )
        assert breakout_definition["class_name"] == "TemporaryBreakoutStrategy"
        assert "temporary_breakout" in breakout_definition["aliases"]
    finally:
        module_path.unlink(missing_ok=True)
        sys.modules.pop(module_name, None)
