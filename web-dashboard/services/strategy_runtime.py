import importlib
import inspect
import re
from pathlib import Path
from typing import Any, Dict, List, Type

from strategies.base_strategy import BaseStrategy
from strategies.bt_price_action import PriceActionStrategy


_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_STRATEGIES_DIR = _PROJECT_ROOT / "strategies"
_EXCLUDED_MODULE_STEMS = frozenset({"__init__", "base_strategy"})
_LEGACY_CANONICAL_NAMES = {
    "bt_price_action": "bt_price_action",
}
_LEGACY_ALIASES = {
    "bt_price_action": ("price_action_strategy",),
}
_CAMEL_TO_SNAKE_RE_1 = re.compile(r"(.)([A-Z][a-z]+)")
_CAMEL_TO_SNAKE_RE_2 = re.compile(r"([a-z0-9])([A-Z])")


def _camel_to_snake(value: str) -> str:
    step_1 = _CAMEL_TO_SNAKE_RE_1.sub(r"\1_\2", value)
    return _CAMEL_TO_SNAKE_RE_2.sub(r"\1_\2", step_1).lower()


def _display_name_from_key(strategy_key: str) -> str:
    return strategy_key.replace("_", " ").title()


def _iter_strategy_module_stems(strategies_dir: Path) -> List[str]:
    if not strategies_dir.exists():
        return []
    return sorted(
        file.stem
        for file in strategies_dir.glob("*.py")
        if file.stem not in _EXCLUDED_MODULE_STEMS and not file.stem.startswith("_")
    )


def _is_public_strategy_class(module_name: str, strategy_class: Type[Any]) -> bool:
    return (
        inspect.isclass(strategy_class)
        and strategy_class.__module__ == module_name
        and strategy_class is not BaseStrategy
        and issubclass(strategy_class, BaseStrategy)
        and strategy_class.__name__.endswith("Strategy")
    )


def _build_strategy_name(module_stem: str, strategy_class: Type[Any]) -> str:
    if module_stem in _LEGACY_CANONICAL_NAMES:
        return _LEGACY_CANONICAL_NAMES[module_stem]
    if module_stem.endswith("_strategy"):
        return module_stem
    class_key = _camel_to_snake(strategy_class.__name__)
    return class_key if class_key.endswith("_strategy") else f"{class_key}_strategy"


def _build_strategy_aliases(module_stem: str, strategy_name: str, strategy_class: Type[Any]) -> tuple[str, ...]:
    aliases: List[str] = [strategy_name, module_stem, _camel_to_snake(strategy_class.__name__)]
    aliases.extend(_LEGACY_ALIASES.get(module_stem, ()))
    deduped: List[str] = []
    for alias in aliases:
        normalized = (alias or "").strip().lower()
        if normalized and normalized not in deduped:
            deduped.append(normalized)
    return tuple(deduped)


def discover_strategy_definitions(
    *,
    strategies_dir: Path | None = None,
    package_name: str = "strategies",
) -> List[Dict[str, Any]]:
    """
    Discover runnable strategies from modules in the strategies package.

    A module contributes to the dashboard only if it defines a concrete BaseStrategy
    subclass whose class name ends with `Strategy`.
    """
    strategies_path = strategies_dir or _STRATEGIES_DIR
    importlib.invalidate_caches()
    definitions: List[Dict[str, Any]] = []

    for module_stem in _iter_strategy_module_stems(strategies_path):
        module_name = f"{package_name}.{module_stem}"
        try:
            module = importlib.import_module(module_name)
        except Exception:
            continue

        for _, strategy_class in inspect.getmembers(module, inspect.isclass):
            if not _is_public_strategy_class(module_name, strategy_class):
                continue

            strategy_name = _build_strategy_name(module_stem, strategy_class)
            definitions.append(
                {
                    "name": strategy_name,
                    "display_name": _display_name_from_key(strategy_name),
                    "module_name": module_stem,
                    "class_name": strategy_class.__name__,
                    "aliases": _build_strategy_aliases(module_stem, strategy_name, strategy_class),
                    "strategy_class": strategy_class,
                }
            )

    return definitions


def list_dashboard_strategies() -> List[Dict[str, str]]:
    """Return strategies that should appear in the dashboard dropdown."""
    return [
        {
            "name": definition["name"],
            "display_name": definition["display_name"],
        }
        for definition in discover_strategy_definitions()
    ]


def resolve_strategy_class(strategy_name: str):
    """Resolve strategy key from config to concrete strategy class."""
    key = (strategy_name or "bt_price_action").strip().lower()
    for definition in discover_strategy_definitions():
        if key in definition["aliases"]:
            return definition["strategy_class"]
    return PriceActionStrategy


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
    st_config["funding_rate_per_8h"] = config.get("funding_rate_per_8h", 0.0)
    st_config["funding_interval_hours"] = config.get("funding_interval_hours", 8)
    return st_config


OPT_WHITELIST = frozenset({"risk_reward_ratio", "sl_buffer_atr", "trailing_stop_distance"})


def build_opt_strategy_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build kwargs for optstrategy: merge base config with opt_params.
    opt_params values (lists/ranges) override base config for whitelisted keys only.
    """
    base = build_runtime_strategy_config(config)
    opt_params = config.get("opt_params") or {}
    if not opt_params:
        return base
    result = dict(base)
    for key, values in opt_params.items():
        if key not in OPT_WHITELIST:
            continue
        if values is not None and hasattr(values, "__iter__") and not isinstance(values, (str, bytes)):
            result[key] = list(values) if not isinstance(values, list) else values
    return result
