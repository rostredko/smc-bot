"""Five parameter presets for `bt_traders_reality` mapped to trading setups.

Each preset is a complete flat config compatible with the dashboard
`BacktestConfig` model + `POST /api/user-configs/{name}` endpoint.
"""
from __future__ import annotations

from typing import Any, Dict


def _common(**overrides: Any) -> Dict[str, Any]:
    base: Dict[str, Any] = {
        "initial_capital": 10_000.0,
        "risk_per_trade": 1.5,
        "max_drawdown": 25.0,
        "leverage": 5.0,
        "symbol": "BTC/USDT",
        "timeframes": ["1h", "4h"],
        "start_date": "2026-01-01",
        "end_date": "2026-03-31",
        "exchange": "binance",
        "exchange_type": "future",
        "execution_mode": "paper",
        "strategy": "bt_traders_reality",
        "dynamic_position_sizing": True,
        "trailing_stop_distance": 0.0,
        "breakeven_trigger_r": 0.0,
        "position_cap_adverse": 0.5,
        "taker_fee_bps": 4.0,
        "maker_fee_bps": 2.0,
        "slippage_bps": 1.0,
        "funding_rate_per_8h": 0.0,
        "funding_interval_hours": 8,
        "detailed_signals": False,
        "market_analysis": True,
        "run_mode": "single",
        "strategy_config": {},
    }
    base.update(overrides)
    return base


PRESETS: Dict[str, Dict[str, Any]] = {
    # ──────────────────────────────────────────────────────────────────────
    # 1) Weekly Reversal — counter-trend at weekly M0/M5 exhaustion
    # ──────────────────────────────────────────────────────────────────────
    "TR Weekly Reversal": _common(
        timeframes=["1h", "5m"],
        risk_per_trade=1.0,
        strategy_config={
            "ema_fast": 5,
            "ema_medium": 13,
            "ema_slow": 50,
            "ema_trend": 200,
            "pvsra_avg_period": 10,
            "pvsra_rv_mult": 1.3,
            "pvsra_bv_mult": 1.02,
            "adr_period": 14,
            "adr_exhaustion_threshold": 0.55,
            "signal_long_min_score": 1.0,
            "signal_short_max_score": -1.0,
            "pvsra_long_labels": ["green", "blue"],
            "pvsra_short_labels": ["red", "violet"],
            "use_htf_ema_filter": False,
            "use_weekly_sl": True,
            "use_pivot_tp": True,
            "atr_period": 14,
            "sl_buffer_atr": 1.0,
            "sl_weekly_buffer_atr": 0.15,
            "risk_reward_ratio": 1.5,
        },
    ),

    # ──────────────────────────────────────────────────────────────────────
    # 2) Trend Pullback Continuation — only strong signals, HTF aligned
    # ──────────────────────────────────────────────────────────────────────
    "TR Trend Pullback": _common(
        timeframes=["1h", "5m"],
        risk_per_trade=1.5,
        breakeven_trigger_r=1.0,
        strategy_config={
            "ema_fast": 5,
            "ema_medium": 13,
            "ema_slow": 50,
            "ema_trend": 200,
            "pvsra_avg_period": 10,
            "pvsra_rv_mult": 1.3,
            "pvsra_bv_mult": 1.02,
            "adr_period": 14,
            "adr_exhaustion_threshold": 0.9,
            "signal_long_min_score": 2.0,
            "signal_short_max_score": -2.0,
            "pvsra_long_labels": ["green", "blue"],
            "pvsra_short_labels": ["red", "violet"],
            "use_htf_ema_filter": True,
            "use_weekly_sl": True,
            "use_pivot_tp": True,
            "atr_period": 14,
            "sl_buffer_atr": 1.5,
            "sl_weekly_buffer_atr": 0.2,
            "risk_reward_ratio": 2.0,
        },
    ),

    # ──────────────────────────────────────────────────────────────────────
    # 3) Mean Reversion After Exhaustion — fade intraday exhaustion
    # ──────────────────────────────────────────────────────────────────────
    "TR Mean Reversion": _common(
        timeframes=["1h", "5m"],
        risk_per_trade=1.0,
        max_drawdown=20.0,
        strategy_config={
            "ema_fast": 5,
            "ema_medium": 13,
            "ema_slow": 50,
            "ema_trend": 200,
            "pvsra_avg_period": 10,
            "pvsra_rv_mult": 1.7,
            "pvsra_bv_mult": 1.3,
            "adr_period": 14,
            "adr_exhaustion_threshold": 0.55,
            "signal_long_min_score": 1.0,
            "signal_short_max_score": -1.0,
            "use_htf_ema_filter": False,
            "use_weekly_sl": False,
            "use_pivot_tp": True,
            "atr_period": 14,
            "sl_buffer_atr": 1.5,
            "sl_weekly_buffer_atr": 0.1,
            "risk_reward_ratio": 1.2,
        },
    ),

    # ──────────────────────────────────────────────────────────────────────
    # 4) Rotation Scanner — aggressive, broad PVSRA gates
    # ──────────────────────────────────────────────────────────────────────
    "TR Rotation Scanner": _common(
        timeframes=["1h", "5m"],
        risk_per_trade=1.0,
        strategy_config={
            "ema_fast": 5,
            "ema_medium": 13,
            "ema_slow": 50,
            "ema_trend": 200,
            "pvsra_avg_period": 10,
            "pvsra_rv_mult": 1.3,
            "pvsra_bv_mult": 1.02,
            "adr_period": 14,
            "adr_exhaustion_threshold": 0.8,
            "signal_long_min_score": 1.5,
            "signal_short_max_score": -1.5,
            "pvsra_long_labels": ["green", "blue"],
            "pvsra_short_labels": ["red", "violet"],
            "use_htf_ema_filter": False,
            "use_weekly_sl": True,
            "use_pivot_tp": True,
            "atr_period": 14,
            "sl_buffer_atr": 1.2,
            "sl_weekly_buffer_atr": 0.15,
            "risk_reward_ratio": 2.0,
        },
    ),

    # ──────────────────────────────────────────────────────────────────────
    # 5) Top-Down Execution — 4h HTF bias, 15m entry
    # ──────────────────────────────────────────────────────────────────────
    "TR Top-Down": _common(
        timeframes=["1h", "5m"],
        risk_per_trade=1.0,
        breakeven_trigger_r=1.0,
        strategy_config={
            "ema_fast": 5,
            "ema_medium": 13,
            "ema_slow": 50,
            "ema_trend": 200,
            "pvsra_avg_period": 10,
            "pvsra_rv_mult": 1.3,
            "pvsra_bv_mult": 1.02,
            "adr_period": 14,
            "adr_exhaustion_threshold": 0.85,
            "signal_long_min_score": 2.0,
            "signal_short_max_score": -2.0,
            "pvsra_long_labels": ["green", "blue"],
            "pvsra_short_labels": ["red", "violet"],
            "use_htf_ema_filter": True,
            "use_weekly_sl": True,
            "use_pivot_tp": True,
            "atr_period": 14,
            "sl_buffer_atr": 1.5,
            "sl_weekly_buffer_atr": 0.15,
            "risk_reward_ratio": 2.0,
        },
    ),
}
