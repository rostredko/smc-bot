"""Run 5 `bt_traders_reality` presets on Q1 2026 and save them to Mongo.

The backtest is executed in-process via ``BTBacktestEngine`` (fast and shares
the data cache with the dashboard). Configs are persisted to Mongo via the
running dashboard API so they appear in the UI immediately.
"""
from __future__ import annotations

import copy
import json
import os
import sys
from typing import Any, Dict

import requests

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _REPO_ROOT)
sys.path.insert(0, os.path.join(_REPO_ROOT, "web-dashboard"))

from engine.bt_backtest_engine import BTBacktestEngine  # noqa: E402
from services.strategy_runtime import (  # noqa: E402
    build_runtime_strategy_config,
    resolve_strategy_class,
)
from tools.tr_strategy_presets import PRESETS  # noqa: E402

API_BASE = os.environ.get("DASHBOARD_API", "http://localhost:8000")


def _print_summary(name: str, metrics: Dict[str, Any], trades: list) -> None:
    print(f"\n=== {name} ===")
    for key in (
        "initial_capital",
        "final_capital",
        "total_pnl",
        "sharpe_ratio",
        "max_drawdown",
        "total_trades",
        "win_rate",
        "profit_factor",
        "win_count",
        "loss_count",
    ):
        if key in metrics:
            value = metrics[key]
            if isinstance(value, float):
                print(f"  {key:<18} {value:>12.2f}")
            else:
                print(f"  {key:<18} {value!s:>12}")
    longs = sum(1 for t in trades if (t.get("signal_direction") or "").lower() == "long")
    shorts = sum(1 for t in trades if (t.get("signal_direction") or "").lower() == "short")
    wins_long = sum(
        1
        for t in trades
        if (t.get("signal_direction") or "").lower() == "long"
        and float(t.get("realized_pnl", 0) or 0) > 0
    )
    wins_short = sum(
        1
        for t in trades
        if (t.get("signal_direction") or "").lower() == "short"
        and float(t.get("realized_pnl", 0) or 0) > 0
    )
    print(f"  longs/shorts        {longs} ({wins_long} w) / {shorts} ({wins_short} w)")


def _run_backtest(preset: Dict[str, Any]) -> tuple[Dict[str, Any], list]:
    """Execute one preset in-process and return (metrics, trades)."""
    config = copy.deepcopy(preset)
    cls = resolve_strategy_class(config.get("strategy", "bt_traders_reality"))
    engine = BTBacktestEngine(config)
    runtime_cfg = build_runtime_strategy_config(config)
    engine.add_strategy(cls, **runtime_cfg)
    metrics = engine.run_backtest()
    trades = engine.closed_trades or []
    return metrics, trades


def _save_config(name: str, preset: Dict[str, Any]) -> None:
    """Persist preset into Mongo via the dashboard API."""
    url = f"{API_BASE}/api/user-configs/{name}"
    response = requests.post(url, json=preset, timeout=15)
    response.raise_for_status()
    print(f"  saved '{name}' -> {response.json().get('message')}")


def main() -> None:
    print(f"Running {len(PRESETS)} presets on "
          f"{next(iter(PRESETS.values()))['start_date']} -> "
          f"{next(iter(PRESETS.values()))['end_date']} via API {API_BASE} ...")

    all_metrics: Dict[str, Dict[str, Any]] = {}
    for name, preset in PRESETS.items():
        try:
            metrics, trades = _run_backtest(preset)
        except Exception as exc:
            print(f"\n=== {name} ===\n  ERROR: {type(exc).__name__}: {exc}")
            continue
        _print_summary(name, metrics, trades)
        all_metrics[name] = metrics

        try:
            _save_config(name, preset)
        except Exception as exc:
            print(f"  save failed: {type(exc).__name__}: {exc}")

    print("\n=== Summary (sorted by total_pnl desc) ===")
    sorted_items = sorted(
        all_metrics.items(),
        key=lambda item: item[1].get("total_pnl", 0.0),
        reverse=True,
    )
    for name, metrics in sorted_items:
        pnl = metrics.get("total_pnl", 0.0)
        trades = int(metrics.get("total_trades", 0) or 0)
        wr = metrics.get("win_rate", 0.0)
        pf = metrics.get("profit_factor", 0.0) or 0.0
        dd = metrics.get("max_drawdown", 0.0)
        print(
            f"  {name:<24}  PnL={pnl:>8.2f}  trades={trades:>3}  "
            f"WR={wr:>5.1f}%  PF={pf:>4.2f}  DD={dd:>4.1f}%"
        )

    summary_path = os.path.join(_REPO_ROOT, "tools", "tr_presets_q1_2026_results.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(all_metrics, f, indent=2)
    print(f"\nMetrics saved to {summary_path}")


if __name__ == "__main__":
    main()
