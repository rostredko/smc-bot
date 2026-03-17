import os
import sys
from datetime import datetime, timedelta, timezone
import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "web-dashboard"))

from services.result_mapper import (
    map_live_trades,
    build_equity_series,
    build_backtest_metrics_doc,
    build_live_metrics_doc,
    build_optimization_metrics_doc,
)


def test_map_live_trades_normalizes_dashboard_fields():
    trades = [
        {"entry_price": 100.0, "size": 2.0, "realized_pnl": 10.0, "direction": "LONG"},
    ]
    out = map_live_trades(trades)
    assert len(out) == 1
    assert out[0]["id"] == 1
    assert out[0]["pnl"] == 10.0
    assert out[0]["status"] == "CLOSED"
    assert out[0]["pnl_percent"] == 5.0


def test_build_equity_series_downsamples_and_serializes():
    curve = [
        {"timestamp": datetime(2026, 3, 1, tzinfo=timezone.utc) + timedelta(minutes=i), "equity": 10000 + i}
        for i in range(120)
    ]
    out = build_equity_series(curve, max_points=100)
    assert len(out) <= 100
    assert "date" in out[0] and "equity" in out[0]
    assert out[-1]["equity"] == 10000 + 119


def test_build_backtest_metrics_doc_uses_trade_sum_for_final_capital():
    metrics = {"win_count": 1, "loss_count": 1, "total_trades": 2}
    trades = [{"pnl": 50.0}, {"pnl": -20.0}]
    equity = [{"date": "2026-03-01T00:00:00Z", "equity": 10030.0}]
    doc = build_backtest_metrics_doc(
        engine_config={"initial_capital": 10000, "strategy": "bt_price_action"},
        metrics=metrics,
        trades_data=trades,
        equity_data=equity,
        signals_generated=4,
    )
    assert doc["total_pnl"] == 30.0
    assert doc["final_capital"] == 10030.0
    assert doc["signals_generated"] == 4


def test_build_backtest_metrics_doc_prefers_broker_values_when_available():
    metrics = {
        "win_count": 1,
        "loss_count": 1,
        "total_trades": 2,
        "total_pnl": 55.0,
        "final_capital": 10055.0,
    }
    trades = [{"pnl": 50.0}, {"pnl": -20.0}]  # sum=30, intentionally different from broker
    equity = [{"date": "2026-03-01T00:00:00Z", "equity": 10055.0}]
    doc = build_backtest_metrics_doc(
        engine_config={"initial_capital": 10000, "strategy": "bt_price_action"},
        metrics=metrics,
        trades_data=trades,
        equity_data=equity,
        signals_generated=4,
    )
    assert doc["total_pnl"] == 55.0
    assert doc["final_capital"] == 10055.0


def test_build_live_metrics_doc_includes_signals_generated():
    start = datetime(2026, 3, 5, 19, 0, tzinfo=timezone.utc)
    end = start + timedelta(minutes=5)
    doc = build_live_metrics_doc(
        config={"initial_capital": 10000, "strategy": "fast_test_strategy"},
        metrics={"signals_generated": 3, "win_count": 1, "loss_count": 1, "total_trades": 2},
        trades_data=[{"pnl": 1.0}, {"pnl": -0.5}],
        equity_data=[],
        session_start=start,
        session_end=end,
    )
    assert doc["signals_generated"] == 3


def test_build_live_metrics_doc_derives_stats_from_trades_and_equity_fallback():
    start = datetime(2026, 3, 5, 19, 0, tzinfo=timezone.utc)
    end = start + timedelta(minutes=15)
    doc = build_live_metrics_doc(
        config={"initial_capital": 10000, "strategy": "fast_test_strategy"},
        metrics={"signals_generated": 0, "max_drawdown": 0.0, "sharpe_ratio": 0.42},
        trades_data=[{"pnl": 2.0}, {"pnl": -1.0}, {"pnl": -3.0}],
        equity_data=[
            {"date": "2026-03-05T19:00:00+00:00", "equity": 10000.0},
            {"date": "2026-03-05T19:05:00+00:00", "equity": 10100.0},
            {"date": "2026-03-05T19:10:00+00:00", "equity": 10000.0},
            {"date": "2026-03-05T19:15:00+00:00", "equity": 9800.0},
        ],
        session_start=start,
        session_end=end,
    )

    assert doc["total_pnl"] == -2.0
    assert doc["total_trades"] == 3
    assert doc["winning_trades"] == 1
    assert doc["losing_trades"] == 2
    assert doc["win_rate"] == pytest.approx(1 / 3)
    assert doc["profit_factor"] == pytest.approx(0.5)
    assert doc["avg_win"] == pytest.approx(2.0)
    assert doc["avg_loss"] == pytest.approx(-2.0)
    assert doc["max_drawdown"] == pytest.approx((300.0 / 10100.0) * 100.0)
    # Fallback keeps signals non-zero when counter misses but trades were executed.
    assert doc["signals_generated"] == 3


def test_build_optimization_metrics_doc_uses_best_variant():
    variants = [
        {
            "params": {"risk_reward_ratio": 2.5, "sl_buffer_atr": 1, "trailing_stop_distance": 0.02},
            "sharpe_ratio": 0.11,
            "profit_factor": 28.57,
            "total_pnl": 116.27,
            "total_trades": 2,
            "win_rate": 50,
            "win_count": 1,
            "loss_count": 1,
            "max_drawdown": 0.6,
            "final_capital": 10116.27,
        },
        {"params": {}, "sharpe_ratio": 0.05, "total_pnl": 50},
    ]
    doc = build_optimization_metrics_doc(
        engine_config={"initial_capital": 10000, "strategy": "bt_price_action"},
        metrics={"variants": variants, "signals_generated": 10},
        signals_generated=10,
    )
    assert doc["run_mode"] == "optimize"
    assert doc["is_optimization_batch"] is True
    assert doc["variants_count"] == 2
    assert doc["variants"] == variants
    assert doc["total_pnl"] == 116.27
    assert doc["sharpe_ratio"] == 0.11
    assert doc["profit_factor"] == 28.57
    assert doc["total_trades"] == 2
    assert doc["win_rate"] == 0.5
    assert doc["final_capital"] == 10116.27
