"""Smoke-test ``bt_traders_reality`` strategy with a real 2025 BTC backtest.

This is a one-off script intended to be run manually during development. It
runs the strategy end-to-end via ``BTBacktestEngine`` so we exercise the same
code-path the dashboard does (strategy resolution, data loader, analyzers) and
prints a compact summary of signals/trades/PnL so the implementer can confirm
the strategy does something non-trivial on real data.
"""
from __future__ import annotations

import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _REPO_ROOT)
sys.path.insert(0, os.path.join(_REPO_ROOT, "web-dashboard"))

from engine.bt_backtest_engine import BTBacktestEngine  # noqa: E402
from services.strategy_runtime import (  # noqa: E402
    build_runtime_strategy_config,
    resolve_strategy_class,
)
from strategies.bt_traders_reality import TradersRealityStrategy  # noqa: E402


def main() -> None:
    cls = resolve_strategy_class("bt_traders_reality")
    assert cls is TradersRealityStrategy, f"Strategy resolution failed: {cls}"

    config = {
        "strategy": "bt_traders_reality",
        "symbol": "BTC/USDT",
        "exchange": "binance",
        "exchange_type": "future",
        "timeframes": ["1h", "4h"],
        "start_date": "2025-01-01",
        "end_date": "2025-06-30",
        "initial_capital": 10_000.0,
        "commission": 0.0004,
        "leverage": 1.0,
        "risk_per_trade": 1.0,
        "dynamic_position_sizing": True,
        "max_drawdown": 50.0,
        "trailing_stop_distance": 0.0,
        "breakeven_trigger_r": 0.0,
        "detailed_signals": False,
        "market_analysis": True,
        "strategy_config": {
            "use_htf_ema_filter": True,
            "signal_long_min_score": 2.0,
            "signal_short_max_score": -2.0,
            "risk_reward_ratio": 2.0,
        },
    }

    engine = BTBacktestEngine(config)
    runtime_config = build_runtime_strategy_config(config)
    engine.add_strategy(cls, **runtime_config)

    print(f"Running {cls.__name__} on {config['symbol']} "
          f"{config['timeframes']} from {config['start_date']} to {config['end_date']} ...")

    metrics = engine.run_backtest()
    print("\n=== Backtest metrics ===")
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
            print(f"  {key}: {metrics[key]}")

    trades = engine.closed_trades or []
    print(f"\n=== First 5 trades of {len(trades)} ===")
    for t in trades[:5]:
        print(
            f"  #{t.get('id')} {t.get('direction')} entry={t.get('entry_price')} "
            f"exit={t.get('exit_price')} pnl={t.get('realized_pnl')} "
            f"reason={t.get('exit_reason')}"
        )


if __name__ == "__main__":
    main()
