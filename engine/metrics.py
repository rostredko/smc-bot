"""
Performance metrics calculation module.
Handles comprehensive performance analysis and reporting.
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Any
from datetime import datetime


class PerformanceReporter:
    """
    Calculates comprehensive performance metrics from trade history.
    """

    def __init__(self, initial_capital: float = 10000):
        """Initialize performance reporter."""
        self.initial_capital = initial_capital

    def compute_metrics(self, closed_trades: List, equity_curve: List[Dict]) -> Dict:
        """
        Compute comprehensive performance metrics.

        Args:
            closed_trades: List of closed Position objects
            equity_curve: List of equity curve data points

        Returns:
            Dictionary of performance metrics
        """
        if not closed_trades:
            return self._empty_metrics()

        # Basic trade statistics
        total_trades = len(closed_trades)
        winning_trades = [t for t in closed_trades if t.realized_pnl > 0]
        losing_trades = [t for t in closed_trades if t.realized_pnl < 0]

        win_count = len(winning_trades)
        loss_count = len(losing_trades)
        win_rate = (win_count / total_trades) * 100 if total_trades > 0 else 0

        # PnL statistics
        total_pnl = sum(t.realized_pnl for t in closed_trades)
        gross_profit = sum(t.realized_pnl for t in winning_trades)
        gross_loss = abs(sum(t.realized_pnl for t in losing_trades))

        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

        # Average win/loss
        avg_win = gross_profit / win_count if win_count > 0 else 0
        avg_loss = gross_loss / loss_count if loss_count > 0 else 0

        # Largest win/loss
        largest_win = max((t.realized_pnl for t in winning_trades), default=0)
        largest_loss = min((t.realized_pnl for t in losing_trades), default=0)

        # Risk metrics
        max_drawdown = self._calculate_max_drawdown(equity_curve)
        sharpe_ratio = self._calculate_sharpe_ratio(closed_trades)

        # Trade duration statistics
        durations = []
        for trade in closed_trades:
            if trade.exit_time and trade.entry_time:
                duration = (trade.exit_time - trade.entry_time).total_seconds() / 3600
                durations.append(duration)

        avg_duration = np.mean(durations) if durations else 0

        # Risk-reward analysis
        risk_rewards = [t.risk_reward_ratio for t in closed_trades if t.risk_reward_ratio > 0]
        avg_risk_reward = np.mean(risk_rewards) if risk_rewards else 0

        # Consecutive wins/losses
        consecutive_wins, consecutive_losses = self._calculate_consecutive_trades(closed_trades)

        # Monthly returns (if enough data)
        monthly_returns = self._calculate_monthly_returns(equity_curve)

        return {
            "total_trades": total_trades,
            "win_count": win_count,
            "loss_count": loss_count,
            "win_rate": win_rate,
            "total_pnl": total_pnl,
            "gross_profit": gross_profit,
            "gross_loss": gross_loss,
            "profit_factor": profit_factor,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "largest_win": largest_win,
            "largest_loss": largest_loss,
            "max_drawdown": max_drawdown,
            "sharpe_ratio": sharpe_ratio,
            "avg_duration_hours": avg_duration,
            "avg_risk_reward": avg_risk_reward,
            "max_consecutive_wins": consecutive_wins,
            "max_consecutive_losses": consecutive_losses,
            "monthly_returns": monthly_returns,
            "expectancy": self._calculate_expectancy(avg_win, avg_loss, win_rate),
            "recovery_factor": self._calculate_recovery_factor(total_pnl, max_drawdown),
            "calmar_ratio": self._calculate_calmar_ratio(total_pnl, max_drawdown),
        }

    def _empty_metrics(self) -> Dict:
        """Return empty metrics when no trades."""
        return {
            "total_trades": 0,
            "win_count": 0,
            "loss_count": 0,
            "win_rate": 0,
            "total_pnl": 0,
            "gross_profit": 0,
            "gross_loss": 0,
            "profit_factor": 0,
            "avg_win": 0,
            "avg_loss": 0,
            "largest_win": 0,
            "largest_loss": 0,
            "max_drawdown": 0,
            "sharpe_ratio": 0,
            "avg_duration_hours": 0,
            "avg_risk_reward": 0,
            "max_consecutive_wins": 0,
            "max_consecutive_losses": 0,
            "monthly_returns": [],
            "expectancy": 0,
            "recovery_factor": 0,
            "calmar_ratio": 0,
        }

    def _calculate_max_drawdown(self, equity_curve: List[Dict]) -> float:
        """Calculate maximum drawdown from equity curve."""
        if not equity_curve:
            return 0

        peak = equity_curve[0]["equity"]
        max_dd = 0

        for point in equity_curve:
            if point["equity"] > peak:
                peak = point["equity"]

            drawdown = (peak - point["equity"]) / peak * 100
            max_dd = max(max_dd, drawdown)

        return max_dd

    def _calculate_sharpe_ratio(self, closed_trades: List) -> float:
        """Calculate Sharpe ratio from trade returns."""
        if len(closed_trades) < 2:
            return 0

        # Calculate returns as percentages
        returns = []
        for trade in closed_trades:
            if trade.risk_amount > 0:
                return_pct = trade.realized_pnl / trade.risk_amount
                returns.append(return_pct)

        if len(returns) < 2:
            return 0

        mean_return = np.mean(returns)
        std_return = np.std(returns)

        if std_return == 0:
            return 0

        # Annualized Sharpe ratio (assuming daily trades)
        sharpe = (mean_return / std_return) * np.sqrt(252)
        return sharpe

    def _calculate_consecutive_trades(self, closed_trades: List) -> tuple[int, int]:
        """Calculate maximum consecutive wins and losses."""
        if not closed_trades:
            return 0, 0

        max_wins = 0
        max_losses = 0
        current_wins = 0
        current_losses = 0

        for trade in closed_trades:
            if trade.realized_pnl > 0:
                current_wins += 1
                current_losses = 0
                max_wins = max(max_wins, current_wins)
            else:
                current_losses += 1
                current_wins = 0
                max_losses = max(max_losses, current_losses)

        return max_wins, max_losses

    def _calculate_monthly_returns(self, equity_curve: List[Dict]) -> List[float]:
        """Calculate monthly returns from equity curve."""
        if len(equity_curve) < 30:  # Need at least a month of data
            return []

        # Group by month and calculate returns
        monthly_data = {}
        for point in equity_curve:
            month_key = point["timestamp"].strftime("%Y-%m")
            if month_key not in monthly_data:
                monthly_data[month_key] = []
            monthly_data[month_key].append(point["equity"])

        monthly_returns = []
        prev_month_equity = None

        for month in sorted(monthly_data.keys()):
            month_equity = monthly_data[month][-1]  # End of month equity

            if prev_month_equity is not None:
                monthly_return = (month_equity - prev_month_equity) / prev_month_equity * 100
                monthly_returns.append(monthly_return)

            prev_month_equity = month_equity

        return monthly_returns

    def _calculate_expectancy(self, avg_win: float, avg_loss: float, win_rate: float) -> float:
        """Calculate expectancy (expected value per trade)."""
        win_prob = win_rate / 100
        loss_prob = 1 - win_prob
        return (avg_win * win_prob) - (avg_loss * loss_prob)

    def _calculate_recovery_factor(self, total_pnl: float, max_drawdown: float) -> float:
        """Calculate recovery factor (total return / max drawdown)."""
        if max_drawdown == 0:
            return float("inf") if total_pnl > 0 else 0
        return total_pnl / max_drawdown

    def _calculate_calmar_ratio(self, total_pnl: float, max_drawdown: float) -> float:
        """Calculate Calmar ratio (annual return / max drawdown)."""
        if max_drawdown == 0:
            return float("inf") if total_pnl > 0 else 0

        # Assuming annual return (would need time period for accurate calculation)
        annual_return = total_pnl  # Simplified
        return annual_return / max_drawdown

    def generate_report(self, metrics: Dict) -> str:
        """Generate a formatted performance report."""
        report = []
        report.append("PERFORMANCE REPORT")
        report.append("=" * 50)

        # Basic Statistics
        report.append(f"Total Trades: {metrics['total_trades']}")
        report.append(f"Win Rate: {metrics['win_rate']:.1f}%")
        report.append(f"Profit Factor: {metrics['profit_factor']:.2f}")
        report.append(f"Total PnL: ${metrics['total_pnl']:,.2f}")

        # Risk Metrics
        report.append(f"Max Drawdown: {metrics['max_drawdown']:.1f}%")
        report.append(f"Sharpe Ratio: {metrics['sharpe_ratio']:.2f}")
        report.append(f"Recovery Factor: {metrics['recovery_factor']:.2f}")

        # Trade Analysis
        report.append(f"Average Win: ${metrics['avg_win']:.2f}")
        report.append(f"Average Loss: ${metrics['avg_loss']:.2f}")
        report.append(f"Largest Win: ${metrics['largest_win']:.2f}")
        report.append(f"Largest Loss: ${metrics['largest_loss']:.2f}")

        # Additional Metrics
        report.append(f"Average Duration: {metrics['avg_duration_hours']:.1f} hours")
        report.append(f"Average Risk/Reward: {metrics['avg_risk_reward']:.2f}")
        report.append(f"Max Consecutive Wins: {metrics['max_consecutive_wins']}")
        report.append(f"Max Consecutive Losses: {metrics['max_consecutive_losses']}")

        return "\n".join(report)


# Example usage
if __name__ == "__main__":
    # Test PerformanceReporter
    reporter = PerformanceReporter()

    # Mock trade data
    class MockTrade:
        def __init__(self, pnl, risk_amount=100, entry_time=None, exit_time=None):
            self.realized_pnl = pnl
            self.risk_amount = risk_amount
            self.risk_reward_ratio = abs(pnl) / risk_amount if risk_amount > 0 else 0
            self.entry_time = entry_time or pd.Timestamp.now()
            self.exit_time = exit_time or pd.Timestamp.now() + pd.Timedelta(hours=1)

    mock_trades = [MockTrade(150, 100), MockTrade(-50, 100), MockTrade(200, 100), MockTrade(-75, 100), MockTrade(100, 100)]

    mock_equity = [
        {"timestamp": pd.Timestamp("2023-01-01"), "equity": 10000},
        {"timestamp": pd.Timestamp("2023-01-02"), "equity": 10150},
        {"timestamp": pd.Timestamp("2023-01-03"), "equity": 10100},
        {"timestamp": pd.Timestamp("2023-01-04"), "equity": 10300},
        {"timestamp": pd.Timestamp("2023-01-05"), "equity": 10225},
        {"timestamp": pd.Timestamp("2023-01-06"), "equity": 10325},
    ]

    metrics = reporter.compute_metrics(mock_trades, mock_equity)
    print("Performance Metrics:")
    for key, value in metrics.items():
        print(f"{key}: {value}")

    report = reporter.generate_report(metrics)
    print("\n" + report)
