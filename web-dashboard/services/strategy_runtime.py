from typing import Any, Dict, Type

from strategies.bt_price_action import PriceActionStrategy
from strategies.fast_test_strategy import FastTestStrategy


_STRATEGY_CLASS_MAP: Dict[str, Type] = {
    "bt_price_action": PriceActionStrategy,
    "price_action_strategy": PriceActionStrategy,
    "fast_test_strategy": FastTestStrategy,
}


def resolve_strategy_class(strategy_name: str):
    """Resolve strategy key from config to concrete strategy class."""
    key = (strategy_name or "bt_price_action").strip().lower()
    return _STRATEGY_CLASS_MAP.get(key, PriceActionStrategy)


def build_runtime_strategy_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge strategy-specific params with runtime risk/exit controls.
    Runtime controls intentionally override same keys from strategy_config.
    """
    st_config = dict(config.get("strategy_config", {}) or {})
    st_config["trailing_stop_distance"] = config.get("trailing_stop_distance", 0.0)
    st_config["breakeven_trigger_r"] = config.get("breakeven_trigger_r", 0.0)
    st_config["risk_per_trade"] = config.get("risk_per_trade", 1.0)
    st_config["leverage"] = config.get("leverage", 1.0)
    st_config["dynamic_position_sizing"] = config.get("dynamic_position_sizing", True)
    st_config["max_drawdown"] = config.get("max_drawdown", 50.0)
    st_config["position_cap_adverse"] = config.get("position_cap_adverse", 0.5)
    return st_config

