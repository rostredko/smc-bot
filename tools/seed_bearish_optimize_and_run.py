#!/usr/bin/env python3
"""
Create bearish_tactical_preset_2026_q1 optimize config from session backtest_20260317_135044_86f7f57c
(bearish_tactical_preset_2026_q1_hard_sniper) and run optimize to verify at least 1 trade in 27 runs.

Run from project root: python tools/seed_bearish_optimize_and_run.py
Requires: MongoDB, ccxt (for data)
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / "web-dashboard") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "web-dashboard"))

from db.repositories import BacktestRepository, UserConfigRepository
from engine.bt_backtest_engine import BTBacktestEngine
from services.strategy_runtime import build_opt_strategy_config, resolve_strategy_class


SOURCE_RUN_ID = "backtest_20260317_135044_86f7f57c"
SOURCE_TEMPLATE = "bearish_tactical_preset_2026_q1_hard_sniper"
TARGET_CONFIG_NAME = "bearish_tactical_preset_2026_q1_optimize"

OPT_PARAMS = {
    "risk_reward_ratio": [1.5, 2.0, 2.5],
    "sl_buffer_atr": [1.0, 1.3, 1.5],
    "trailing_stop_distance": [0, 0.01, 0.02],
}


def get_base_config() -> dict | None:
    """Get config from backtest run or user template."""
    repo_bt = BacktestRepository()
    doc = repo_bt.get_by_id(SOURCE_RUN_ID)
    if doc:
        cfg = doc.get("configuration", doc)
        if cfg:
            return cfg
    return UserConfigRepository().get(SOURCE_TEMPLATE)


def get_fallback_config() -> dict:
    """Fallback bearish tactical preset when source not found."""
    return {
        "initial_capital": 10000,
        "risk_per_trade": 1.5,
        "max_drawdown": 30.0,
        "leverage": 10.0,
        "symbol": "BTC/USDT",
        "timeframes": ["1h", "15m"],
        "exchange": "binance",
        "exchange_type": "future",
        "execution_mode": "paper",
        "start_date": "2024-01-01",
        "end_date": "2024-03-31",
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
            "pattern_bullish_engulfing": True,
            "pattern_hammer": True,
            "pattern_inverted_hammer": True,
            "pattern_shooting_star": True,
            "pattern_hanging_man": True,
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
    }


def build_optimize_config(base: dict) -> dict:
    """Build optimize config from base, adding opt_params."""
    out = dict(base)
    out["run_mode"] = "optimize"
    out["opt_params"] = OPT_PARAMS
    out["opt_target_metric"] = "sharpe_ratio"
    out["loaded_template_name"] = TARGET_CONFIG_NAME
    return out


def run_optimize_sync(config: dict) -> dict:
    """Run optimization synchronously (no asyncio)."""
    engine_config = {
        "initial_capital": config.get("initial_capital", 10000),
        "risk_per_trade": config.get("risk_per_trade", 2.0),
        "max_drawdown": config.get("max_drawdown", 15.0),
        "leverage": config.get("leverage", 10.0),
        "symbol": config.get("symbol", "BTC/USDT"),
        "timeframes": config.get("timeframes", ["4h", "15m"]),
        "exchange": config.get("exchange", "binance"),
        "exchange_type": config.get("exchange_type", "future"),
        "start_date": config.get("start_date", "2024-01-01"),
        "end_date": config.get("end_date", "2024-12-31"),
        "strategy": config.get("strategy", "bt_price_action"),
        "strategy_config": config.get("strategy_config", {}),
        "trailing_stop_distance": config.get("trailing_stop_distance", 0.0),
        "breakeven_trigger_r": config.get("breakeven_trigger_r", 0.0),
        "dynamic_position_sizing": config.get("dynamic_position_sizing", True),
        "position_cap_adverse": config.get("position_cap_adverse", 0.5),
        "commission": 0.0004,
        "maker_fee_bps": config.get("maker_fee_bps", 2),
        "taker_fee_bps": config.get("taker_fee_bps", 4),
        "broker_commission_bps": 4,
        "fee_source": "exchange_default",
        "slippage_bps": config.get("slippage_bps", 1.5),
        "funding_rate_per_8h": config.get("funding_rate_per_8h", 0.0001),
        "funding_interval_hours": config.get("funding_interval_hours", 8),
        "opt_params": config.get("opt_params", OPT_PARAMS),
        "opt_target_metric": config.get("opt_target_metric", "sharpe_ratio"),
    }
    strategy_class = resolve_strategy_class(engine_config["strategy"])
    opt_kwargs = build_opt_strategy_config(engine_config)
    engine = BTBacktestEngine(engine_config)
    return engine.run_backtest_optimize(strategy_class, opt_kwargs, engine_config["opt_target_metric"])


def main():
    base = get_base_config()
    if not base:
        print(f"⚠️ Source not found (backtest {SOURCE_RUN_ID} or user config '{SOURCE_TEMPLATE}')")
        print("   Using fallback bearish tactical preset (Jan–Mar 2024 for data availability).")
        base = get_fallback_config()

    opt_config = build_optimize_config(base)
    UserConfigRepository().save(TARGET_CONFIG_NAME, opt_config)
    print(f"✅ Saved config '{TARGET_CONFIG_NAME}' to user_configs")
    print(f"   Period: {opt_config.get('start_date')} — {opt_config.get('end_date')}")
    print(f"   Opt params: {list(opt_config.get('opt_params', {}).keys())}")

    print("\n🔄 Running optimize (27 combos)...")
    result = run_optimize_sync(opt_config)
    variants = result.get("variants", [])
    total_trades = sum(v.get("total_trades", 0) for v in variants)
    with_trades = sum(1 for v in variants if v.get("total_trades", 0) > 0)

    print(f"\n📊 Result: {len(variants)} variants, {with_trades} with trades, total {total_trades} trades")
    if with_trades > 0:
        best = variants[0] if variants else {}
        print(f"   Best: Sharpe {best.get('sharpe_ratio', 0):.2f}, PF {best.get('profit_factor', 0):.2f}, "
              f"Trades {best.get('total_trades', 0)}, PnL ${best.get('total_pnl', 0):.2f}")
        print("✅ At least 1 run had trades — OK")
    else:
        print("⚠️ No trades in any run. Check data availability and filters.")
        sys.exit(1)


if __name__ == "__main__":
    save_only = "--save-only" in sys.argv
    if save_only:
        base = get_base_config()
        if not base:
            print("⚠️ Source not found; using fallback preset.")
            base = get_fallback_config()
        opt_config = build_optimize_config(base)
        UserConfigRepository().save(TARGET_CONFIG_NAME, opt_config)
        print(f"✅ Saved '{TARGET_CONFIG_NAME}'. Load in dashboard and run Optimize.")
    else:
        main()
