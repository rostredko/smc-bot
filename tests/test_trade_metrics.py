from engine.trade_metrics import build_closed_trade_metrics


def test_build_closed_trade_metrics_uses_closed_trade_realized_pnl():
    metrics = build_closed_trade_metrics(
        initial_capital=10000.0,
        final_capital=10150.0,
        closed_trades=[
            {"realized_pnl": 120.0},
            {"realized_pnl": -45.0},
            {"realized_pnl": 75.0},
        ],
    )

    assert metrics["total_trades"] == 3
    assert metrics["win_count"] == 2
    assert metrics["loss_count"] == 1
    assert metrics["win_rate"] == (2 / 3) * 100.0
    assert metrics["profit_factor"] == (120.0 + 75.0) / 45.0
    assert metrics["avg_win"] == (120.0 + 75.0) / 2
    assert metrics["avg_loss"] == -45.0
    assert metrics["total_pnl"] == 150.0


def test_build_closed_trade_metrics_handles_all_wins_without_division_error():
    metrics = build_closed_trade_metrics(
        initial_capital=10000.0,
        final_capital=10100.0,
        closed_trades=[
            {"realized_pnl": 40.0},
            {"realized_pnl": 60.0},
        ],
    )

    assert metrics["profit_factor"] == 999.0
    assert metrics["loss_count"] == 0
    assert metrics["avg_loss"] == 0.0
