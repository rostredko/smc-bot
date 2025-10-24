"""
Core BacktestEngine class that orchestrates the entire backtesting process.
Coordinates data feeds, runs the backtest loop, executes strategy signals,
simulates trades, and aggregates results.
"""

import json
from typing import Any, Dict, List

import pandas as pd

from .data_loader import DataLoader
from .risk_manager import SpotRiskManager
from .position import Position, SpotTradeSimulator
from .logger import Logger
from .metrics import PerformanceReporter


class BacktestEngine:
    """
    Main coordinator class that ties everything together.
    Handles configuration, data loading, strategy execution, and results reporting.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the backtest engine with configuration parameters.

        Args:
            config: Dictionary containing backtest parameters:
                - initial_capital: Starting account balance
                - risk_per_trade: Risk percentage per trade (e.g., 2.0 for 2%)
                - max_drawdown: Maximum allowed drawdown percentage
                - max_positions: Legacy parameter - positions now managed by risk/reward ratio
                - symbol: Trading pair (e.g., 'BTC/USDT')
                - timeframes: List of timeframes needed
                - start_date: Backtest start date
                - end_date: Backtest end date
                - strategy: Strategy module name
                - leverage: Maximum leverage to use
        """
        self.config = config
        self.initial_capital = config.get("initial_capital", 10000)
        self.current_capital = self.initial_capital
        self.peak_capital = self.initial_capital

        # Initialize components
        self.data_loader = DataLoader(config.get("exchange", "binance"))
        self.risk_manager = SpotRiskManager(
            initial_capital=self.initial_capital,
            risk_per_trade=config.get("risk_per_trade", 0.5),
            max_drawdown=config.get("max_drawdown", 15.0),
            max_positions=config.get("max_positions", 1),
        )
        self.trade_simulator = SpotTradeSimulator()
        self.logger = Logger(config.get("log_level", "INFO"))
        self.reporter = PerformanceReporter(self.initial_capital)

        # Cancellation flag for graceful shutdown
        self.should_cancel = False

        # Strategy and data storage
        self.strategy = None
        self.data = {}
        self.open_positions: List[Position] = []
        self.closed_trades: List[Position] = []
        self.equity_curve = []

        # Load strategy
        self._load_strategy()

    def _load_strategy(self):
        """Load the specified strategy module."""
        strategy_name = self.config.get("strategy", "smc_strategy")
        try:
            # Import strategy module
            strategy_module = __import__(f"strategies.{strategy_name}", fromlist=["Strategy"])

            # Try to find the strategy class (could be 'Strategy', 'SMCStrategy', etc.)
            strategy_class = None
            for class_name in ["Strategy", "SMCStrategy", "SimpleTestStrategy", "SimplifiedSMCStrategy", f"{strategy_name.title()}Strategy"]:
                if hasattr(strategy_module, class_name):
                    strategy_class = getattr(strategy_module, class_name)
                    break

            if strategy_class is None:
                raise AttributeError(f"No strategy class found in {strategy_name}")

            self.strategy = strategy_class()
            self.logger.strategy = self.strategy  # Link strategy to logger for detailed logging
            self.logger.log("INFO", f"Loaded strategy: {strategy_name}")
        except Exception as e:
            raise RuntimeError(f"Failed to load strategy {strategy_name}: {e}")

    def load_data(self):
        """Fetch historical data for all required timeframes."""
        symbol = self.config["symbol"]
        timeframes = self.config.get("timeframes", ["1h"])
        start_date = self.config["start_date"]
        end_date = self.config["end_date"]

        self.logger.log("INFO", f"Loading data for {symbol} from {start_date} to {end_date}")

        for timeframe in timeframes:
            self.logger.log("INFO", f"Fetching {timeframe} data...")
            df = self.data_loader.get_data(symbol, timeframe, start_date, end_date)
            self.data[timeframe] = df
            self.logger.log("INFO", f"Loaded {len(df)} bars for {timeframe}")

        # Use primary timeframe for main loop
        self.primary_timeframe = timeframes[0]
        self.primary_data = self.data[self.primary_timeframe]

    def run_backtest(self):
        """Execute the main backtest simulation loop."""
        self.logger.log("INFO", "Starting backtest simulation...")
        self.logger.log("INFO", f"Initial capital: ${self.initial_capital:,.2f}")

        # Track equity curve
        self.equity_curve.append({"timestamp": self.primary_data.index[0], "equity": self.current_capital, "drawdown": 0.0})

        # Main simulation loop
        for i, (timestamp, row) in enumerate(self.primary_data.iterrows()):
            # Check for cancellation request
            if self.should_cancel:
                self.logger.log("INFO", f"⏹️ Backtest cancelled by user at {timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
                break

            current_price = row["close"]
            current_time = timestamp

            # Prepare market data snapshot for strategy
            market_data = self._prepare_market_data(current_time)

            # Generate signals from strategy
            try:
                signals = self.strategy.generate_signals(market_data)
                if signals is None:
                    signals = []

                # Log signal generation details
                for signal in signals:
                    self.logger.log_signal_generation(signal, market_data, current_time)

            except Exception as e:
                self.logger.log("ERROR", f"Strategy error at {current_time}: {e}")
                signals = []

            # Process new signals
            for signal in signals:
                self._execute_signal(signal, current_price, current_time)

            # Update existing positions
            self._update_positions(current_price, current_time)

            # Update equity curve
            self._update_equity_curve(current_time)

        # Close any remaining positions at end
        self._close_remaining_positions()

        # Generate final report
        metrics = self._generate_final_report()
        return metrics

    def _prepare_market_data(self, current_time: pd.Timestamp) -> Dict[str, pd.DataFrame]:
        """Prepare market data snapshot up to current time for strategy."""
        market_data = {}

        for timeframe, df in self.data.items():
            # Get data up to current time (inclusive)
            mask = df.index <= current_time
            market_data[timeframe] = df[mask].copy()

        return market_data

    def _calculate_risk_reward_ratio(self, entry_price: float, stop_loss: float, take_profit: float, direction: str) -> float:
        """Calculate risk/reward ratio for a trade."""
        risk_distance = abs(entry_price - stop_loss)
        reward_distance = abs(take_profit - entry_price)

        if risk_distance <= 0:
            return 0

        return reward_distance / risk_distance

    def _execute_signal(self, signal: Dict[str, Any], current_price: float, current_time: pd.Timestamp):
        """Process a new trade signal."""
        # Get stop loss and take profit first
        stop_loss = signal.get("stop_loss")
        take_profit = signal.get("take_profit")

        # Determine entry price
        entry_price = signal.get("entry_price", current_price)
        if entry_price is None:
            entry_price = current_price

        if stop_loss is None:
            self.logger.log("WARNING", "No stop loss specified, using default")
            stop_loss = entry_price * 0.98 if signal["direction"] == "LONG" else entry_price * 1.02

        # Check risk/reward ratio using Risk Manager validation
        if take_profit is not None:
            min_risk_reward = self.config.get("min_risk_reward", 3.0)
            rr_valid, rr_reason = self.risk_manager.validate_risk_reward_ratio(entry_price, stop_loss, take_profit, min_risk_reward)

            if not rr_valid:
                rejection_details = {
                    "calculated_rr": self._calculate_risk_reward_ratio(entry_price, stop_loss, take_profit, signal["direction"]),
                    "min_required_rr": min_risk_reward,
                    "entry_price": entry_price,
                    "stop_loss": stop_loss,
                    "take_profit": take_profit,
                    "reason": rr_reason,
                }
                self.logger.log_signal_rejection(signal, "Risk/Reward", rejection_details, current_time)
                return

        # Calculate potential risk for this position
        risk_distance = abs(entry_price - stop_loss)
        temp_position_size = self.risk_manager.calculate_position_size(entry_price, stop_loss)

        # Check if we can open a new position with this risk and projected value
        can_open, reason = self.risk_manager.can_open_position(entry_price, stop_loss, current_time.to_pydatetime(), current_price)
        if not can_open:
            rejection_details = {
                "max_positions": self.risk_manager.max_positions,
                "current_positions": len(self.open_positions),
                "potential_risk": risk_distance * temp_position_size,
                "total_potential_risk": self.risk_manager._calculate_total_potential_risk() + risk_distance * temp_position_size,
                "reason": reason,
            }
            self.logger.log_signal_rejection(signal, "Risk/Reward", rejection_details, current_time)
            return

        # Calculate final position size
        position_size = self.risk_manager.calculate_position_size(entry_price, stop_loss)

        if position_size <= 0:
            rejection_details = {
                "calculated_size": position_size,
                "entry_price": entry_price,
                "stop_loss": stop_loss,
                "risk_amount": abs(entry_price - stop_loss) * position_size,
                "reason": "Position size too small",
            }
            self.logger.log_signal_rejection(signal, "Position size", rejection_details, current_time)
            return

        # Create position
        position = Position(
            id=len(self.open_positions) + len(self.closed_trades) + 1,
            entry_price=entry_price,
            size=position_size,
            stop_loss=stop_loss,
            take_profit=take_profit,
            entry_time=current_time,
            reason=signal.get("reason", "Strategy signal"),
            direction=signal.get("direction", "LONG"),
        )

        # Set up laddered exits if not specified
        if take_profit is None:
            self._setup_laddered_exits(position)

        self.open_positions.append(position)

        # Log trade opening
        self.logger.log_trade_open(position, self.current_capital, self.initial_capital)

        # Update risk manager
        self.risk_manager.add_position(position)

        # Update strategy executed signals counter
        if hasattr(self.strategy, "signals_executed"):
            self.strategy.signals_executed += 1

    def _setup_laddered_exits(self, position: Position):
        """Set up laddered take-profit levels for a spot position."""
        risk_distance = abs(position.entry_price - position.stop_loss)

        # Spot trading is long-only
        tp1_price = position.entry_price + risk_distance  # 1:1 R:R
        tp2_price = position.entry_price + (2 * risk_distance)  # 1:2 R:R
        tp3_price = position.entry_price + (2.5 * risk_distance)  # 1:2.5 R:R (runner)

        position.take_profit_levels = [
            {"price": tp1_price, "percentage": 0.5, "reason": "TP1 - 1R"},
            {"price": tp2_price, "percentage": 0.3, "reason": "TP2 - 2R"},
            {"price": tp3_price, "percentage": 0.2, "reason": "Runner - Trailing"},
        ]

    def _update_positions(self, current_price: float, current_time: pd.Timestamp):
        """Update all open positions and check for exit conditions."""
        positions_to_remove = []

        for position in self.open_positions:

            # Check stop loss
            if self._is_stop_hit(position, current_price):
                self._close_position(position, current_price, current_time, "STOP LOSS")
                positions_to_remove.append(position)
                continue

            # Check take profit levels
            if self._check_take_profits(position, current_price, current_time):
                # Position might be partially or fully closed
                if position.size <= 0:
                    positions_to_remove.append(position)

            # Update trailing stop if active
            if position.trailing_active:
                self._update_trailing_stop(position, current_price)

        # Remove closed positions
        for position in positions_to_remove:
            self.open_positions.remove(position)
            self.closed_trades.append(position)
            self.risk_manager.remove_position(position)

    def _is_stop_hit(self, position: Position, current_price: float) -> bool:
        """Check if stop loss is hit."""
        if position.direction == "LONG":
            return current_price <= position.stop_loss
        else:  # SHORT
            return current_price >= position.stop_loss

    def _check_take_profits(self, position: Position, current_price: float, current_time: pd.Timestamp) -> bool:
        """Check and execute take profit levels. Returns True if position is fully closed."""
        if not hasattr(position, "take_profit_levels") or not position.take_profit_levels:
            return False

        for tp_level in position.take_profit_levels:
            tp_price = tp_level["price"]
            tp_percentage = tp_level["percentage"]

            if position.tp_hit.get(tp_price, False):
                continue  # Already hit this TP

            # Check TP based on direction
            tp_hit = False
            if position.direction == "LONG" and current_price >= tp_price:
                tp_hit = True
            elif position.direction == "SHORT" and current_price <= tp_price:
                tp_hit = True

            if tp_hit:
                # Execute partial exit
                exit_size = position.size * tp_percentage
                self._partial_exit(position, exit_size, tp_price, current_time, tp_level.get("reason", f"TP hit at {tp_price}"))

                # Move stop to breakeven after TP1
                if tp_percentage == 0.5 and not position.breakeven_moved:
                    position.stop_loss = position.entry_price
                    position.breakeven_moved = True
                    self.logger.log("INFO", f"Stop moved to breakeven: {position.entry_price}")

                # Activate trailing stop after TP2
                if tp_percentage == 0.3 and not position.trailing_active:
                    position.trailing_active = True
                    self.logger.log("INFO", "Trailing stop activated")

                position.tp_hit[tp_price] = True
                break

        return position.size <= 0

    def _partial_exit(self, position: Position, exit_size: float, exit_price: float, current_time: pd.Timestamp, reason: str):
        """Execute a partial position exit."""
        # Calculate PnL for this portion based on direction
        if position.direction == "LONG":
            pnl = (exit_price - position.entry_price) * exit_size
        else:  # SHORT
            pnl = (position.entry_price - exit_price) * exit_size

        # Apply fees
        fee = exit_price * exit_size * 0.0004  # 0.04% taker fee
        net_pnl = pnl - fee

        # Update position
        position.size -= exit_size
        position.realized_pnl += net_pnl

        # Update account balance
        self.current_capital += net_pnl

        # Log partial exit
        self.logger.log_partial_exit(position, exit_size, exit_price, net_pnl, reason, current_time, self.current_capital, self.initial_capital)

    def _update_trailing_stop(self, position: Position, current_price: float):
        """Update trailing stop based on price movement."""
        if position.direction == "LONG":
            # For LONG positions: move stop up as price goes up
            if current_price > position.trailing_high:
                position.trailing_high = current_price
                # Move stop to some distance below the high
                atr_distance = current_price * 0.02  # 2% trailing distance
                new_stop = current_price - atr_distance
                if new_stop > position.stop_loss:
                    position.stop_loss = new_stop
        else:  # SHORT
            # For SHORT positions: move stop down as price goes down
            if current_price < position.trailing_low:
                position.trailing_low = current_price
                # Move stop to some distance above the low
                atr_distance = current_price * 0.02  # 2% trailing distance
                new_stop = current_price + atr_distance
                if new_stop < position.stop_loss:
                    position.stop_loss = new_stop

    def _close_position(self, position: Position, exit_price: float, current_time: pd.Timestamp, reason: str):
        """Close a position completely."""
        # Calculate final PnL based on direction
        remaining_size = position.size
        if position.direction == "LONG":
            pnl = (exit_price - position.entry_price) * remaining_size
        else:  # SHORT
            pnl = (position.entry_price - exit_price) * remaining_size

        # Apply fees
        fee = exit_price * remaining_size * 0.0004
        net_pnl = pnl - fee

        # Update position
        position.exit_price = exit_price
        position.exit_time = current_time
        position.exit_reason = reason
        position.realized_pnl += net_pnl
        position.size = 0

        # Update account balance and risk manager
        self.current_capital += net_pnl
        self.risk_manager.update_balance(net_pnl, position_direction=position.direction, exit_time=current_time.to_pydatetime())

        # Update peak equity with current price
        self.risk_manager.update_peak_equity(exit_price)

        # Log final exit
        self.logger.log_trade_close(position, net_pnl, self.current_capital, self.initial_capital)

    def _close_remaining_positions(self):
        """Close any remaining positions at the end of backtest."""
        final_price = self.primary_data["close"].iloc[-1]
        final_time = self.primary_data.index[-1]

        for position in self.open_positions.copy():
            self._close_position(position, final_price, final_time, "End of backtest")
            self.open_positions.remove(position)
            self.closed_trades.append(position)

    def _update_equity_curve(self, current_time: pd.Timestamp):
        """Update equity curve for drawdown calculation with detailed tracking."""
        # Get current price from the primary timeframe data
        primary_tf = self.config.get("timeframes", ["1h"])[0]

        # Find the closest available timestamp
        try:
            current_price = self.data[primary_tf].loc[current_time, "close"]
        except KeyError:
            # If exact timestamp not found, get the last available price
            current_price = self.data[primary_tf]["close"].iloc[-1]

        # Calculate current equity (capital + unrealized PnL)
        unrealized_pnl = 0
        total_position_value = 0
        for position in self.open_positions:
            position_value = position.entry_price * position.size
            total_position_value += position_value

            if position.direction == "LONG":
                unrealized_pnl += (current_price - position.entry_price) * position.size
            else:
                unrealized_pnl += (position.entry_price - current_price) * position.size

        current_equity = self.current_capital + unrealized_pnl

        # Update peak capital
        if current_equity > self.peak_capital:
            self.peak_capital = current_equity

        # Update risk manager peak equity
        self.risk_manager.update_peak_equity(current_price)

        # Calculate drawdown
        drawdown = (self.peak_capital - current_equity) / self.peak_capital * 100

        # Calculate return from initial capital
        total_return = (current_equity - self.initial_capital) / self.initial_capital * 100

        # Calculate daily return (if we have previous equity point)
        daily_return = 0
        if self.equity_curve:
            prev_equity = self.equity_curve[-1]["equity"]
            if prev_equity > 0:
                daily_return = (current_equity - prev_equity) / prev_equity * 100

        self.equity_curve.append(
            {
                "timestamp": current_time,
                "equity": current_equity,
                "capital": self.current_capital,
                "unrealized_pnl": unrealized_pnl,
                "drawdown": drawdown,
                "total_return_pct": total_return,
                "daily_return_pct": daily_return,
                "current_price": current_price,
                "open_positions_count": len(self.open_positions),
                "total_position_value": total_position_value,
                "peak_capital": self.peak_capital,
            }
        )

    def _generate_final_report(self):
        """Generate and display final performance report."""
        self.logger.log("INFO", "Backtest completed. Generating report...")

        # Calculate metrics
        metrics = self.reporter.compute_metrics(self.closed_trades, self.equity_curve)

        # Print summary
        self.logger.print_summary(metrics)

        return metrics


def run_backtest(config_file: str):
    """Main function to run a backtest from a configuration file."""
    with open(config_file, "r") as f:
        config = json.load(f)

    engine = BacktestEngine(config)
    engine.load_data()
    metrics = engine.run_backtest()

    return engine, metrics


if __name__ == "__main__":
    # Example usage
    config = {
        "initial_capital": 10000,
        "risk_per_trade": 2.0,
        "max_drawdown": 15.0,
        "max_positions": 3,
        "symbol": "BTC/USDT",
        "timeframes": ["4h", "15m"],
        "start_date": "2023-01-01",
        "end_date": "2023-12-31",
        "strategy": "smc_strategy",
        "leverage": 10.0,
        "exchange": "binance",
    }

    engine = BacktestEngine(config)
    engine.load_data()
    engine.run_backtest()
