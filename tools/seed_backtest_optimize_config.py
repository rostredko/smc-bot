#!/usr/bin/env python3
"""
Seed a backtest-optimize config template for quick testing.
Run from project root: python tools/seed_backtest_optimize_config.py
(Requires pymongo. For Docker, use the one-liner from the commit that added this.)
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / "web-dashboard") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "web-dashboard"))

from db.repositories import UserConfigRepository


CONFIG_NAME = "backtest_optimize_quick_test"

# Jan 2026 - today for test trades, optimize mode, 3 params × 3 values = 27 combos
# 1h+15m for more bars; relaxed filters for signals
CONFIG = {
    "initial_capital": 10000,
    "risk_per_trade": 1.5,
    "max_drawdown": 30.0,
    "leverage": 10.0,
    "symbol": "BTC/USDT",
    "timeframes": ["1h", "15m"],
    "exchange": "binance",
    "exchange_type": "future",
    "execution_mode": "paper",
    "start_date": "2026-01-01",
    "end_date": "2026-03-17",
    "strategy": "bt_price_action",
    "strategy_config": {
        "risk_reward_ratio": 2.0,
        "sl_buffer_atr": 1.3,
        "trailing_stop_distance": 0.0,
        "use_trend_filter": False,
        "use_rsi_filter": False,
        "use_adx_filter": False,
        "use_premium_discount_filter": False,
        "use_space_to_target_filter": False,
        "pattern_bearish_engulfing": True,
        "use_structure_filter": True,
        "use_opposing_level_tp": True,
    },
    "trailing_stop_distance": 0.0,
    "breakeven_trigger_r": 0.0,
    "dynamic_position_sizing": True,
    "position_cap_adverse": 0.5,
    "maker_fee_bps": 2.0,
    "taker_fee_bps": 4.0,
    "fee_source": "exchange_default",
    "slippage_bps": 1.5,
    "funding_rate_per_8h": 0.0001,
    "funding_interval_hours": 8,
    "run_mode": "optimize",
    "opt_params": {
        "risk_reward_ratio": [1.5, 2.0, 2.5],
        "sl_buffer_atr": [1.0, 1.3, 1.5],
        "trailing_stop_distance": [0, 0.01, 0.02],
    },
    "opt_target_metric": "sharpe_ratio",
}


def main():
    repo = UserConfigRepository()
    repo.save(CONFIG_NAME, CONFIG)
    print(f"Saved config '{CONFIG_NAME}' to user_configs")
    print(f"  Period: {CONFIG['start_date']} — {CONFIG['end_date']} (Jan–Mar 2026)")
    print(f"  Run mode: {CONFIG['run_mode']}")
    print(f"  Opt params: {list(CONFIG['opt_params'].keys())}")
    print(f"  Timeframes: {CONFIG['timeframes']}")


if __name__ == "__main__":
    main()
