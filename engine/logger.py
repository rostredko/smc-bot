"""
Logging and Performance Reporting system.
Handles structured logging of trade events and comprehensive performance metrics.
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
import json


class Logger:
    """
    Handles structured logging of trading events.
    Formats trade events into human-readable console output.
    """

    def __init__(self, log_level: str = "INFO"):
        """
        Initialize logger.

        Args:
            log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
        """
        self.log_level = log_level
        self.logs: List[Dict] = []
        self.trade_count = 0

    def log(self, level: str, message: str):
        """
        Log a general message.

        Args:
            level: Log level
            message: Message to log
        """
        if self._should_log(level):
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log_entry = {"timestamp": timestamp, "level": level, "message": message}
            self.logs.append(log_entry)
            print(f"[{timestamp}] {level}: {message}")

    def log_trade_open(self, position, current_capital: float = None, initial_capital: float = None):
        """Log a trade opening event with balance information."""
        self.trade_count += 1
        timestamp = position.entry_time.strftime("%Y-%m-%d %H:%M:%S")

        # Format trade opening log
        log_message = (
            f"OPEN {position.direction} {position.original_size:.4f} @ ${position.entry_price:.2f}, "
            f"SL=${position.stop_loss:.2f}, "
            f"Risk=${position.risk_amount:.2f}"
        )

        if hasattr(position, "take_profit_levels") and position.take_profit_levels:
            tp_levels = [f"TP{i+1}=${tp[0]:.2f}" for i, tp in enumerate(position.take_profit_levels)]
            log_message += f", {', '.join(tp_levels)}"

        if position.reason:
            log_message += f" (Reason: {position.reason})"

        # Add balance information
        balance_info = ""
        if current_capital is not None and initial_capital is not None:
            capital_change = current_capital - initial_capital
            capital_change_pct = (capital_change / initial_capital) * 100
            balance_info = f" | Balance: ${current_capital:,.2f} ({capital_change_pct:+.2f}% from initial ${initial_capital:,.2f})"
            log_message += balance_info

        log_entry = {
            "timestamp": timestamp,
            "type": "TRADE_OPEN",
            "position_id": position.id,
            "direction": position.direction,
            "size": position.original_size,
            "entry_price": position.entry_price,
            "stop_loss": position.stop_loss,
            "reason": position.reason,
            "current_capital": current_capital,
            "initial_capital": initial_capital,
            "capital_change": capital_change if current_capital and initial_capital else None,
            "capital_change_pct": capital_change_pct if current_capital and initial_capital else None,
            "message": log_message,
        }

        self.logs.append(log_entry)
        print(f"[{timestamp}] {log_message}")
        print(f"    📊 Check on TradingView: {timestamp} - Entry at ${position.entry_price:.2f}")

    def log_partial_exit(
        self,
        position,
        exit_size: float,
        exit_price: float,
        pnl: float,
        reason: str,
        current_time: pd.Timestamp = None,
        current_capital: float = None,
        initial_capital: float = None,
    ):
        """Log a partial exit event with balance information."""
        if current_time is None:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        else:
            timestamp = current_time.strftime("%Y-%m-%d %H:%M:%S")

        log_message = (
            f"PARTIAL EXIT {exit_size:.4f} @ ${exit_price:.2f} — {reason}. " f"Realized PnL=${pnl:.2f} ({pnl/position.risk_amount*100:.1f}% of risk)"
        )

        # Add balance information
        if current_capital is not None and initial_capital is not None:
            capital_change = current_capital - initial_capital
            capital_change_pct = (capital_change / initial_capital) * 100
            balance_info = f" | Balance: ${current_capital:,.2f} ({capital_change_pct:+.2f}% from initial)"
            log_message += balance_info

        log_entry = {
            "timestamp": timestamp,
            "type": "PARTIAL_EXIT",
            "position_id": position.id,
            "exit_size": exit_size,
            "exit_price": exit_price,
            "pnl": pnl,
            "reason": reason,
            "current_capital": current_capital,
            "initial_capital": initial_capital,
            "capital_change": capital_change if current_capital and initial_capital else None,
            "capital_change_pct": capital_change_pct if current_capital and initial_capital else None,
            "message": log_message,
        }

        self.logs.append(log_entry)
        print(f"[{timestamp}] {log_message}")
        print(f"    📊 Check on TradingView: {timestamp} - Partial exit at ${exit_price:.2f}")

    def log_trade_close(self, position, final_pnl: float, current_capital: float = None, initial_capital: float = None):
        """Log a trade closing event with balance information."""
        timestamp = position.exit_time.strftime("%Y-%m-%d %H:%M:%S")

        # Calculate total PnL percentage
        total_pnl = position.realized_pnl
        pnl_percentage = (total_pnl / (position.entry_price * position.original_size)) * 100

        log_message = (
            f"CLOSE {position.direction} @ ${position.exit_price:.2f} — {position.exit_reason}. "
            f"Total PnL=${total_pnl:.2f} ({pnl_percentage:+.1f}%)"
        )

        # Add balance information
        if current_capital is not None and initial_capital is not None:
            capital_change = current_capital - initial_capital
            capital_change_pct = (capital_change / initial_capital) * 100
            balance_info = f" | Balance: ${current_capital:,.2f} ({capital_change_pct:+.2f}% from initial ${initial_capital:,.2f})"
            log_message += balance_info

        log_entry = {
            "timestamp": timestamp,
            "type": "TRADE_CLOSE",
            "position_id": position.id,
            "exit_price": position.exit_price,
            "exit_reason": position.exit_reason,
            "total_pnl": total_pnl,
            "pnl_percentage": pnl_percentage,
            "current_capital": current_capital,
            "initial_capital": initial_capital,
            "capital_change": capital_change if current_capital and initial_capital else None,
            "capital_change_pct": capital_change_pct if current_capital and initial_capital else None,
            "message": log_message,
        }

        self.logs.append(log_entry)
        print(f"[{timestamp}] {log_message}")
        print(f"    📊 Check on TradingView: {timestamp} - Close at ${position.exit_price:.2f}")

    def log_risk_event(self, event_type: str, message: str, details: Dict = None):
        """Log risk management events."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        log_entry = {"timestamp": timestamp, "type": "RISK_EVENT", "event_type": event_type, "message": message, "details": details or {}}

        self.logs.append(log_entry)
        print(f"[{timestamp}] RISK: {message}")

    def log_strategy_event(self, event_type: str, message: str, data: Dict = None):
        """Log strategy-specific events."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        log_entry = {"timestamp": timestamp, "type": "STRATEGY_EVENT", "event_type": event_type, "message": message, "data": data or {}}

        self.logs.append(log_entry)
        print(f"[{timestamp}] STRATEGY: {message}")

    def log_signal_generation(self, signal: Dict[str, Any], market_data: Dict[str, pd.DataFrame], current_time: pd.Timestamp = None):
        """Log detailed signal generation information."""
        if current_time is None:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        else:
            timestamp = current_time.strftime("%Y-%m-%d %H:%M:%S")

        # Extract key market context
        current_price = float(signal.get("entry_price", 0))
        direction = signal.get("direction", "UNKNOWN")
        reason = signal.get("reason", "No reason provided")
        confidence = float(signal.get("confidence", 0))

        # Get market bias and zones info
        market_bias = "Unknown"
        zones_info = {}

        if hasattr(self, "strategy") and self.strategy:
            market_bias = getattr(self.strategy, "market_bias", "Unknown")
            zones_info = {
                "order_blocks": len(getattr(self.strategy, "active_order_blocks", [])),
                "fvgs": len(getattr(self.strategy, "active_fvgs", [])),
                "liquidity_levels": len(getattr(self.strategy, "liquidity_levels", [])),
            }

        # Get timeframe info from market data
        timeframe_info = []
        for tf, df in market_data.items():
            if len(df) > 0:
                last_time = df.index[-1].strftime("%Y-%m-%d %H:%M")
                timeframe_info.append(f"{tf}: {last_time}")

        log_message = f"SIGNAL GENERATED: {direction} @ ${current_price:.2f} " f"(Confidence: {confidence:.2f}, Market Bias: {market_bias})"

        log_entry = {
            "timestamp": timestamp,
            "type": "SIGNAL_GENERATION",
            "signal": signal,
            "market_bias": market_bias,
            "zones_info": zones_info,
            "timeframe_info": timeframe_info,
            "message": log_message,
        }

        self.logs.append(log_entry)
        print(f"[{timestamp}] {log_message}")
        print(f"    Reason: {reason}")
        print(f"    Zones: OB={zones_info.get('order_blocks', 0)}, FVG={zones_info.get('fvgs', 0)}, LL={zones_info.get('liquidity_levels', 0)}")
        print(f"    Timeframes: {', '.join(timeframe_info)}")
        print(f"    📊 Check on TradingView: {timestamp} - Price should be around ${current_price:.2f}")

    def log_signal_rejection(self, signal: Dict[str, Any], reason: str, details: Dict = None, current_time: pd.Timestamp = None):
        """Log when a signal is rejected."""
        if current_time is None:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        else:
            timestamp = current_time.strftime("%Y-%m-%d %H:%M:%S")

        direction = signal.get("direction", "UNKNOWN")
        entry_price = float(signal.get("entry_price", 0))

        log_message = f"SIGNAL REJECTED: {direction} @ ${entry_price:.2f} - {reason}"

        log_entry = {
            "timestamp": timestamp,
            "type": "SIGNAL_REJECTION",
            "signal": signal,
            "rejection_reason": reason,
            "details": details or {},
            "message": log_message,
        }

        self.logs.append(log_entry)
        print(f"[{timestamp}] {log_message}")
        print(f"    📊 Check on TradingView: {timestamp} - Price was ${entry_price:.2f}")
        if details:
            for key, value in details.items():
                print(f"    {key}: {value}")

    def log_market_analysis(self, analysis_type: str, data: Dict[str, Any]):
        """Log market analysis results."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        log_entry = {
            "timestamp": timestamp,
            "type": "MARKET_ANALYSIS",
            "analysis_type": analysis_type,
            "data": data,
            "message": f"Market Analysis: {analysis_type}",
        }

        self.logs.append(log_entry)
        print(f"[{timestamp}] MARKET ANALYSIS: {analysis_type}")
        for key, value in data.items():
            print(f"    {key}: {value}")

    def print_summary(self, metrics: Dict):
        """Print the final performance summary."""
        print("\n" + "=" * 60)
        print("BACKTEST SUMMARY")
        print("=" * 60)

        # Basic stats
        print(f"Total Trades: {metrics.get('total_trades', 0)}")
        print(f"Win Rate: {metrics.get('win_rate', 0):.1f}%")
        print(f"Profit Factor: {metrics.get('profit_factor', 0):.2f}")
        print(f"Total PnL: ${metrics.get('total_pnl', 0):,.2f}")
        print(f"Max Drawdown: {metrics.get('max_drawdown', 0):.1f}%")
        print(f"Sharpe Ratio: {metrics.get('sharpe_ratio', 0):.2f}")

        # Additional metrics
        if "avg_win" in metrics:
            print(f"Average Win: ${metrics['avg_win']:.2f}")
        if "avg_loss" in metrics:
            print(f"Average Loss: ${metrics['avg_loss']:.2f}")
        if "largest_win" in metrics:
            print(f"Largest Win: ${metrics['largest_win']:.2f}")
        if "largest_loss" in metrics:
            print(f"Largest Loss: ${metrics['largest_loss']:.2f}")

        print("=" * 60)

    def _should_log(self, level: str) -> bool:
        """Check if message should be logged based on level."""
        levels = {"DEBUG": 0, "INFO": 1, "WARNING": 2, "ERROR": 3}
        return levels.get(level, 1) >= levels.get(self.log_level, 1)

    def get_logs(self, log_type: str = None) -> List[Dict]:
        """Get logs, optionally filtered by type."""
        if log_type:
            return [log for log in self.logs if log.get("type") == log_type]
        return self.logs

    def export_logs(self, filename: str):
        """Export logs to JSON file."""
        with open(filename, "w") as f:
            json.dump(self.logs, f, indent=2, default=str)


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

        # Additional detailed metrics
        total_return = (total_pnl / self.initial_capital) * 100 if hasattr(self, "initial_capital") and self.initial_capital > 0 else 0
        avg_trade_return = (total_pnl / total_trades) if total_trades > 0 else 0
        avg_trade_return_pct = (avg_trade_return / self.initial_capital) * 100 if hasattr(self, "initial_capital") and self.initial_capital > 0 else 0

        # Trade frequency analysis
        if equity_curve and len(equity_curve) > 1:
            start_date = equity_curve[0]["timestamp"]
            end_date = equity_curve[-1]["timestamp"]
            total_days = (end_date - start_date).days
            trades_per_day = total_trades / total_days if total_days > 0 else 0
            trades_per_month = trades_per_day * 30
        else:
            trades_per_day = 0
            trades_per_month = 0

        # Win/Loss streaks analysis
        win_streaks, loss_streaks = self._calculate_win_loss_streaks(closed_trades)
        avg_win_streak = np.mean(win_streaks) if win_streaks else 0
        avg_loss_streak = np.mean(loss_streaks) if loss_streaks else 0

        # Risk-adjusted returns
        sortino_ratio = self._calculate_sortino_ratio(closed_trades)
        max_adverse_excursion = self._calculate_max_adverse_excursion(equity_curve)

        # Performance consistency
        positive_months = len([r for r in monthly_returns if r > 0])
        negative_months = len([r for r in monthly_returns if r < 0])
        monthly_win_rate = (positive_months / len(monthly_returns)) * 100 if monthly_returns else 0

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
            "sortino_ratio": sortino_ratio,
            "avg_duration_hours": avg_duration,
            "avg_risk_reward": avg_risk_reward,
            "max_consecutive_wins": consecutive_wins,
            "max_consecutive_losses": consecutive_losses,
            "monthly_returns": monthly_returns,
            "expectancy": self._calculate_expectancy(avg_win, avg_loss, win_rate),
            "recovery_factor": self._calculate_recovery_factor(total_pnl, max_drawdown),
            "calmar_ratio": self._calculate_calmar_ratio(total_pnl, max_drawdown),
            # New detailed metrics
            "total_return_pct": total_return,
            "avg_trade_return": avg_trade_return,
            "avg_trade_return_pct": avg_trade_return_pct,
            "trades_per_day": trades_per_day,
            "trades_per_month": trades_per_month,
            "avg_win_streak": avg_win_streak,
            "avg_loss_streak": avg_loss_streak,
            "max_adverse_excursion": max_adverse_excursion,
            "monthly_win_rate": monthly_win_rate,
            "positive_months": positive_months,
            "negative_months": negative_months,
            "win_streaks": win_streaks,
            "loss_streaks": loss_streaks,
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
            "sortino_ratio": 0,
            "avg_duration_hours": 0,
            "avg_risk_reward": 0,
            "max_consecutive_wins": 0,
            "max_consecutive_losses": 0,
            "monthly_returns": [],
            "expectancy": 0,
            "recovery_factor": 0,
            "calmar_ratio": 0,
            # New detailed metrics
            "total_return_pct": 0,
            "avg_trade_return": 0,
            "avg_trade_return_pct": 0,
            "trades_per_day": 0,
            "trades_per_month": 0,
            "avg_win_streak": 0,
            "avg_loss_streak": 0,
            "max_adverse_excursion": 0,
            "monthly_win_rate": 0,
            "positive_months": 0,
            "negative_months": 0,
            "win_streaks": [],
            "loss_streaks": [],
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

    def _calculate_consecutive_trades(self, closed_trades: List) -> Tuple[int, int]:
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

    def _calculate_win_loss_streaks(self, closed_trades: List) -> tuple[List[int], List[int]]:
        """Calculate all win and loss streaks."""
        if not closed_trades:
            return [], []

        win_streaks = []
        loss_streaks = []
        current_win_streak = 0
        current_loss_streak = 0

        for trade in closed_trades:
            if trade.realized_pnl > 0:
                current_win_streak += 1
                if current_loss_streak > 0:
                    loss_streaks.append(current_loss_streak)
                    current_loss_streak = 0
            else:
                current_loss_streak += 1
                if current_win_streak > 0:
                    win_streaks.append(current_win_streak)
                    current_win_streak = 0

        # Add final streaks
        if current_win_streak > 0:
            win_streaks.append(current_win_streak)
        if current_loss_streak > 0:
            loss_streaks.append(current_loss_streak)

        return win_streaks, loss_streaks

    def _calculate_sortino_ratio(self, closed_trades: List) -> float:
        """Calculate Sortino ratio (downside deviation)."""
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
        downside_returns = [r for r in returns if r < 0]

        if len(downside_returns) < 2:
            return float("inf") if mean_return > 0 else 0

        downside_std = np.std(downside_returns)
        if downside_std == 0:
            return float("inf") if mean_return > 0 else 0

        # Annualized Sortino ratio
        sortino = (mean_return / downside_std) * np.sqrt(252)
        return sortino

    def _calculate_max_adverse_excursion(self, equity_curve: List[Dict]) -> float:
        """Calculate maximum adverse excursion from equity curve."""
        if not equity_curve:
            return 0

        peak = equity_curve[0]["equity"]
        max_adverse = 0

        for point in equity_curve:
            if point["equity"] > peak:
                peak = point["equity"]

            adverse_excursion = (peak - point["equity"]) / peak * 100
            max_adverse = max(max_adverse, adverse_excursion)

        return max_adverse

    def generate_report(self, metrics: Dict) -> str:
        """Generate a comprehensive formatted performance report."""
        report = []
        report.append("=" * 80)
        report.append("COMPREHENSIVE PERFORMANCE REPORT")
        report.append("=" * 80)

        # Basic Statistics
        report.append("\n📊 BASIC STATISTICS")
        report.append("-" * 40)
        report.append(f"Total Trades: {metrics['total_trades']}")
        report.append(f"Win Rate: {metrics['win_rate']:.1f}%")
        report.append(f"Profit Factor: {metrics['profit_factor']:.2f}")
        report.append(f"Total PnL: ${metrics['total_pnl']:,.2f}")
        report.append(f"Total Return: {metrics.get('total_return_pct', 0):.2f}%")

        # Risk Metrics
        report.append("\n⚠️ RISK METRICS")
        report.append("-" * 40)
        report.append(f"Max Drawdown: {metrics['max_drawdown']:.1f}%")
        report.append(f"Sharpe Ratio: {metrics['sharpe_ratio']:.2f}")
        report.append(f"Sortino Ratio: {metrics.get('sortino_ratio', 0):.2f}")
        report.append(f"Recovery Factor: {metrics['recovery_factor']:.2f}")
        report.append(f"Calmar Ratio: {metrics['calmar_ratio']:.2f}")
        report.append(f"Max Adverse Excursion: {metrics.get('max_adverse_excursion', 0):.1f}%")

        # Trade Analysis
        report.append("\n💰 TRADE ANALYSIS")
        report.append("-" * 40)
        report.append(f"Average Win: ${metrics['avg_win']:.2f}")
        report.append(f"Average Loss: ${metrics['avg_loss']:.2f}")
        report.append(f"Largest Win: ${metrics['largest_win']:.2f}")
        report.append(f"Largest Loss: ${metrics['largest_loss']:.2f}")
        report.append(f"Average Trade Return: ${metrics.get('avg_trade_return', 0):.2f}")
        report.append(f"Average Trade Return %: {metrics.get('avg_trade_return_pct', 0):.2f}%")
        report.append(f"Expectancy: ${metrics['expectancy']:.2f}")

        # Trading Frequency
        report.append("\n📈 TRADING FREQUENCY")
        report.append("-" * 40)
        report.append(f"Trades per Day: {metrics.get('trades_per_day', 0):.2f}")
        report.append(f"Trades per Month: {metrics.get('trades_per_month', 0):.2f}")
        report.append(f"Average Duration: {metrics['avg_duration_hours']:.1f} hours")
        report.append(f"Average Risk/Reward: {metrics['avg_risk_reward']:.2f}")

        # Streak Analysis
        report.append("\n🔥 STREAK ANALYSIS")
        report.append("-" * 40)
        report.append(f"Max Consecutive Wins: {metrics['max_consecutive_wins']}")
        report.append(f"Max Consecutive Losses: {metrics['max_consecutive_losses']}")
        report.append(f"Average Win Streak: {metrics.get('avg_win_streak', 0):.1f}")
        report.append(f"Average Loss Streak: {metrics.get('avg_loss_streak', 0):.1f}")

        # Monthly Performance
        if metrics.get("monthly_returns"):
            report.append("\n📅 MONTHLY PERFORMANCE")
            report.append("-" * 40)
            report.append(f"Monthly Win Rate: {metrics.get('monthly_win_rate', 0):.1f}%")
            report.append(f"Positive Months: {metrics.get('positive_months', 0)}")
            report.append(f"Negative Months: {metrics.get('negative_months', 0)}")

            if len(metrics["monthly_returns"]) > 0:
                best_month = max(metrics["monthly_returns"])
                worst_month = min(metrics["monthly_returns"])
                report.append(f"Best Month: {best_month:+.2f}%")
                report.append(f"Worst Month: {worst_month:+.2f}%")
                report.append(f"Average Monthly Return: {np.mean(metrics['monthly_returns']):.2f}%")

        report.append("\n" + "=" * 80)

        return "\n".join(report)


# Example usage
if __name__ == "__main__":
    # Test Logger
    logger = Logger()
    logger.log("INFO", "Starting backtest")
    logger.log("WARNING", "Risk limit approaching")

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
