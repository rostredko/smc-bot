from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional


def _trade_pnl_sum(trades: Iterable[Dict[str, Any]]) -> float:
    return float(sum(t.get("pnl", t.get("realized_pnl", 0.0)) for t in trades))


def _max_drawdown_from_equity(equity_data: List[Dict[str, Any]]) -> float:
    """
    Compute max drawdown (%) from serialized equity curve [{date, equity}, ...].
    Returns 0.0 when insufficient data.
    """
    if not equity_data:
        return 0.0

    peak: Optional[float] = None
    max_dd = 0.0
    for point in equity_data:
        try:
            equity = float(point.get("equity", 0.0))
        except (TypeError, ValueError):
            continue
        if peak is None or equity > peak:
            peak = equity
        if peak and peak > 0:
            dd = ((peak - equity) / peak) * 100.0
            if dd > max_dd:
                max_dd = dd
    return float(max_dd)


def map_live_trades(closed_trades: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Map TradeListAnalyzer records to repository trade format for live runs.
    Keeps all analyzer fields, only normalizes dashboard fields.
    """
    trades_data: List[Dict[str, Any]] = []
    for i, trade in enumerate(closed_trades):
        realized_pnl = trade.get("realized_pnl", 0)
        entry_price = trade.get("entry_price", 0)
        size = trade.get("size", 0)
        pnl_pct = 0.0
        if entry_price and size:
            pnl_pct = (realized_pnl / size / entry_price) * 100 if size != 0 else 0.0

        full_trade = dict(trade)
        full_trade.update(
            {
                "id": i + 1,
                "pnl": realized_pnl,
                "pnl_percent": round(pnl_pct, 4),
                "status": "CLOSED",
            }
        )
        trades_data.append(full_trade)
    return trades_data


def map_backtest_trades(closed_trades: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Map TradeListAnalyzer records to repository trade format for backtest runs."""
    trades_data: List[Dict[str, Any]] = []
    for i, trade in enumerate(closed_trades):
        entry_time = datetime.fromisoformat(trade["entry_time"]) if trade.get("entry_time") else None
        exit_time = datetime.fromisoformat(trade["exit_time"]) if trade.get("exit_time") else None

        duration_str = None
        if exit_time and entry_time:
            duration_str = str(exit_time - entry_time).replace("0 days ", "")

        trades_data.append(
            {
                "id": i + 1,
                "direction": trade["direction"],
                "entry_price": trade["entry_price"],
                "exit_price": trade["exit_price"],
                "size": trade["size"],
                "pnl": trade["realized_pnl"],
                "pnl_percent": (trade["realized_pnl"] / (trade["entry_price"] * trade["size"])) * 100
                if trade["entry_price"] and trade["size"]
                else 0,
                "entry_time": trade["entry_time"],
                "exit_time": trade["exit_time"],
                "duration": duration_str,
                "status": "CLOSED",
                "stop_loss": trade["stop_loss"],
                "take_profit": trade["take_profit"],
                "realized_pnl": trade["realized_pnl"],
                "exit_reason": trade.get("exit_reason", "Unknown"),
                "commission": trade.get("commission", 0),
                "reason": trade.get("reason", "Unknown"),
                "narrative": trade.get("narrative", None),
                "sl_calculation": trade.get("sl_calculation", None),
                "tp_calculation": trade.get("tp_calculation", None),
                "sl_history": trade.get("sl_history", []),
                "entry_context": trade.get("entry_context", None),
                "execution_bar_indicators": trade.get("execution_bar_indicators", None),
                "exit_context": trade.get("exit_context", None),
                "metadata": trade.get("metadata", {}),
            }
        )
    return trades_data


def build_equity_series(equity_curve: Iterable[Dict[str, Any]], max_points: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Serialize equity curve for repository/doc response.
    If max_points is set, downsample uniformly.
    """
    points = list(equity_curve or [])
    if not points:
        return []

    if max_points is None or len(points) <= max_points:
        selected = points
    elif max_points <= 0:
        selected = []
    elif max_points == 1:
        selected = [points[-1]]
    else:
        # Uniformly sample exactly max_points values and always keep the last point.
        step = (len(points) - 1) / (max_points - 1)
        selected = [points[int(i * step)] for i in range(max_points - 1)]
        selected.append(points[-1])

    out: List[Dict[str, Any]] = []
    for point in selected:
        ts = point["timestamp"]
        out.append(
            {
                "date": ts.isoformat() if hasattr(ts, "isoformat") else str(ts),
                "equity": point["equity"],
            }
        )
    return out


def build_live_metrics_doc(
    config: Dict[str, Any],
    metrics: Dict[str, Any],
    trades_data: List[Dict[str, Any]],
    equity_data: List[Dict[str, Any]],
    session_start: datetime,
    session_end: datetime,
) -> Dict[str, Any]:
    trades_pnl_sum = _trade_pnl_sum(trades_data)
    init_cap = metrics.get("initial_capital", config.get("initial_capital", 10000))

    # Derive trade stats from persisted live trades for consistency.
    pnl_values = [float(t.get("pnl", t.get("realized_pnl", 0.0) or 0.0)) for t in trades_data]
    wins = [p for p in pnl_values if p > 0]
    losses = [p for p in pnl_values if p < 0]
    win_count = len(wins)
    loss_count = len(losses)
    total_trades = len(pnl_values)
    win_rate = (win_count / total_trades) if total_trades > 0 else 0.0
    gross_win = float(sum(wins))
    gross_loss_abs = abs(float(sum(losses)))
    profit_factor = 0.0 if gross_loss_abs == 0 and gross_win == 0 else (999.0 if gross_loss_abs == 0 else gross_win / gross_loss_abs)
    avg_win = (gross_win / win_count) if win_count > 0 else 0.0
    avg_loss = (float(sum(losses)) / loss_count) if loss_count > 0 else 0.0

    metric_max_dd = float(metrics.get("max_drawdown", 0) or 0.0)
    computed_max_dd = _max_drawdown_from_equity(equity_data)
    max_drawdown = metric_max_dd if metric_max_dd > 0 else computed_max_dd

    sharpe_ratio = float(metrics.get("sharpe_ratio", 0) or 0.0)
    raw_signals = metrics.get("signals_generated", 0)
    try:
        metric_signals = int(raw_signals)
    except (TypeError, ValueError):
        try:
            metric_signals = int(float(raw_signals))
        except (TypeError, ValueError):
            metric_signals = 0
    # Live fallback: if signal counter failed, closed trades still imply at least that many signals.
    signals_generated = max(metric_signals, total_trades)

    return {
        "total_pnl": trades_pnl_sum,
        "winning_trades": win_count,
        "losing_trades": loss_count,
        "total_trades": total_trades,
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "max_drawdown": max_drawdown,
        "sharpe_ratio": sharpe_ratio,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "initial_capital": init_cap,
        "final_capital": init_cap + trades_pnl_sum,
        "signals_generated": signals_generated,
        "equity_curve": equity_data,
        "trades": trades_data,
        "strategy": config.get("strategy", "Unknown"),
        "configuration": config,
        "session_start": session_start.isoformat(),
        "session_end": session_end.isoformat(),
        "session_duration_mins": round((session_end - session_start).total_seconds() / 60, 1),
    }


def build_backtest_metrics_doc(
    engine_config: Dict[str, Any],
    metrics: Dict[str, Any],
    trades_data: List[Dict[str, Any]],
    equity_data: List[Dict[str, Any]],
    signals_generated: int,
) -> Dict[str, Any]:
    trades_pnl_sum = _trade_pnl_sum(trades_data)
    init_cap = engine_config.get("initial_capital", 10000)
    return {
        "total_pnl": trades_pnl_sum,
        "winning_trades": metrics.get("win_count", 0),
        "losing_trades": metrics.get("loss_count", 0),
        "total_trades": metrics.get("total_trades", 0),
        "win_rate": metrics.get("win_rate", 0) / 100 if metrics.get("win_rate", 0) > 1 else metrics.get("win_rate", 0),
        "profit_factor": metrics.get("profit_factor", 0),
        "max_drawdown": metrics.get("max_drawdown", 0),
        "sharpe_ratio": metrics.get("sharpe_ratio", 0),
        "avg_win": metrics.get("avg_win", 0),
        "avg_loss": metrics.get("avg_loss", 0),
        "initial_capital": init_cap,
        "final_capital": init_cap + trades_pnl_sum,
        "signals_generated": signals_generated,
        "equity_curve": equity_data,
        "trades": trades_data,
        "strategy": engine_config.get("strategy", "Unknown"),
        "configuration": engine_config,
    }
