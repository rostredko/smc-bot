"""Parameter sweep: find timeframe combos that maximise signal frequency.

For each of the 5 presets, we re-run the backtest on Q1 2026 across a grid of
``(trend_tf, entry_tf)`` combinations. The script prints a sorted table per
preset so the operator can pick the combo that balances trade count vs PnL.

Usage:  ./.venv/bin/python tools/tr_tf_sweep.py
"""
from __future__ import annotations

import copy
import json
import os
import sys
from typing import Any, Dict, List, Tuple

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _REPO_ROOT)
sys.path.insert(0, os.path.join(_REPO_ROOT, "web-dashboard"))

from engine.bt_backtest_engine import BTBacktestEngine  # noqa: E402
from services.strategy_runtime import (  # noqa: E402
    build_runtime_strategy_config,
    resolve_strategy_class,
)
from tools.tr_strategy_presets import PRESETS  # noqa: E402


# Grid of (trend_tf, entry_tf). Primary must be >= secondary for dashboard
# parity — all entries satisfy this constraint.
TF_GRID: List[Tuple[str, str]] = [
    ("15m", "5m"),
    ("30m", "5m"),
    ("30m", "15m"),
    ("1h", "5m"),
    ("1h", "15m"),
    ("1h", "30m"),
    ("2h", "15m"),
    ("2h", "30m"),
    ("2h", "1h"),
    ("4h", "15m"),
    ("4h", "30m"),
    ("4h", "1h"),
    ("4h", "2h"),
]


def _run_backtest(preset: Dict[str, Any]) -> tuple[Dict[str, Any], list]:
    cfg = copy.deepcopy(preset)
    cls = resolve_strategy_class(cfg.get("strategy", "bt_traders_reality"))
    engine = BTBacktestEngine(cfg)
    runtime_cfg = build_runtime_strategy_config(cfg)
    engine.add_strategy(cls, **runtime_cfg)
    metrics = engine.run_backtest()
    trades = engine.closed_trades or []
    return metrics, trades


def sweep_preset(name: str, preset: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for trend_tf, entry_tf in TF_GRID:
        cfg = copy.deepcopy(preset)
        cfg["timeframes"] = [trend_tf, entry_tf]
        try:
            metrics, trades = _run_backtest(cfg)
        except Exception as exc:
            rows.append(
                {
                    "trend_tf": trend_tf,
                    "entry_tf": entry_tf,
                    "trades": 0,
                    "pnl": 0.0,
                    "wr": 0.0,
                    "pf": 0.0,
                    "dd": 0.0,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            continue
        rows.append(
            {
                "trend_tf": trend_tf,
                "entry_tf": entry_tf,
                "trades": int(metrics.get("total_trades", 0) or 0),
                "pnl": float(metrics.get("total_pnl", 0.0) or 0.0),
                "wr": float(metrics.get("win_rate", 0.0) or 0.0),
                "pf": float(metrics.get("profit_factor", 0.0) or 0.0),
                "dd": float(metrics.get("max_drawdown", 0.0) or 0.0),
            }
        )
    return rows


def _print_table(name: str, rows: List[Dict[str, Any]]) -> None:
    print(f"\n=== {name} (sorted by trades, pnl>=0 first) ===")
    # Positive PnL first, then by trade count desc
    rows_sorted = sorted(
        rows,
        key=lambda r: (r.get("pnl", 0.0) < 0, -r.get("trades", 0), -r.get("pnl", 0.0)),
    )
    header = f"  {'TF':<13} {'trades':>7}  {'PnL':>8}  {'WR%':>5}  {'PF':>6}  {'DD%':>5}"
    print(header)
    print("  " + "-" * (len(header) - 2))
    for r in rows_sorted:
        tf = f"{r['trend_tf']}/{r['entry_tf']}"
        if "error" in r:
            print(f"  {tf:<13}  ERROR: {r['error']}")
            continue
        print(
            f"  {tf:<13} {r['trades']:>7}  {r['pnl']:>8.2f}  "
            f"{r['wr']:>5.1f}  {r['pf']:>6.2f}  {r['dd']:>5.1f}"
        )


def main() -> None:
    all_results: Dict[str, List[Dict[str, Any]]] = {}
    best_per_preset: Dict[str, Dict[str, Any]] = {}

    for name, preset in PRESETS.items():
        print(f"\n## Sweeping '{name}' across {len(TF_GRID)} TF combos ...")
        rows = sweep_preset(name, preset)
        all_results[name] = rows
        _print_table(name, rows)

        # Pick best: trades>=threshold AND PnL>0 AND highest trade count (tie-break by pnl)
        winners = [r for r in rows if r.get("pnl", 0.0) > 0 and "error" not in r]
        if winners:
            best = max(winners, key=lambda r: (r["trades"], r["pnl"]))
            best_per_preset[name] = best
            print(
                f"  >>> BEST: {best['trend_tf']}/{best['entry_tf']} — "
                f"trades={best['trades']}, PnL={best['pnl']:.2f}, WR={best['wr']:.1f}%"
            )

    print("\n\n=== Summary: best TF per preset ===")
    print(f"  {'preset':<22} {'TF':<13} {'trades':>7}  {'PnL':>8}  {'WR%':>5}  {'PF':>6}")
    for name, best in best_per_preset.items():
        tf = f"{best['trend_tf']}/{best['entry_tf']}"
        print(
            f"  {name:<22} {tf:<13} {best['trades']:>7}  {best['pnl']:>8.2f}  "
            f"{best['wr']:>5.1f}  {best['pf']:>6.2f}"
        )

    out_path = os.path.join(_REPO_ROOT, "tools", "tr_tf_sweep_results.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(
            {"results": all_results, "best_per_preset": best_per_preset}, f, indent=2
        )
    print(f"\nFull results -> {out_path}")


if __name__ == "__main__":
    main()
