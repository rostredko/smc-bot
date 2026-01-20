"""
Position/Trade object representing an open trading position (Futures/Spot).
Handles size, partial exits, break-even moves, and trailing stops.
"""

from typing import Dict, List, Optional, Tuple
from datetime import datetime
import pandas as pd


class Position:
    """
    Represents a trading position with support for laddered exits and trailing stops.
    Manages the complete lifecycle from entry to exit.
    """

    def __init__(
        self,
        id: int,
        entry_price: float,
        size: float,
        stop_loss: float,
        take_profit: Optional[float] = None,
        entry_time: Optional[pd.Timestamp] = None,
        reason: str = "",
        direction: str = "LONG",
        ladder_exit_enabled: bool = True,
        trailing_stop_enabled: bool = True,
        breakeven_move_enabled: bool = True,
    ):
        """
        Initialize a position.

        Args:
            id: Unique position identifier
            entry_price: Price at which position was opened
            size: Position size (asset units)
            stop_loss: Stop loss price
            take_profit: Take profit price (optional)
            entry_time: Timestamp when position was opened
            reason: Reason for opening the position
            direction: 'LONG' or 'SHORT' (default: 'LONG')
            ladder_exit_enabled: Enable laddered exits
            trailing_stop_enabled: Enable trailing stops
            breakeven_move_enabled: Enable breakeven move after TP1
        """
        self.id = id
        self.direction = direction.upper()
        self.entry_price = entry_price
        self.size = size
        self.original_size = size
        self.stop_loss = stop_loss
        self.take_profit = take_profit
        self.entry_time = entry_time or pd.Timestamp.now()
        self.reason = reason

        # Exit management flags
        self.ladder_exit_enabled = ladder_exit_enabled
        self.trailing_stop_enabled = trailing_stop_enabled
        self.breakeven_move_enabled = breakeven_move_enabled

        # Exit tracking
        self.exit_price: Optional[float] = None
        self.exit_time: Optional[pd.Timestamp] = None
        self.exit_reason: Optional[str] = None
        self.is_closed = False

        # PnL tracking
        self.realized_pnl = 0.0
        self.unrealized_pnl = 0.0

        # Partial exit system
        self.take_profit_levels: List[Dict] = []
        self.tp_hit: Dict[float, bool] = {}
        self.trailing_active = False
        self.trailing_high = entry_price
        self.trailing_low = entry_price

        # Risk metrics
        self.risk_amount = abs(entry_price - stop_loss) * size
        self.risk_reward_ratio = 0.0

        # Enhanced tracking
        self.breakeven_moved = False
        self.tp1_hit = False
        self.tp2_hit = False
        self.runner_exit_price = None

        # Fees tracking
        self.entry_fee = 0.0
        self.exit_fees = 0.0
        self.total_fees = 0.0

        # Metadata
        self.metadata: Dict = {}

    def get_unrealized_pnl(self, current_price: Optional[float] = None) -> float:
        """
        Calculate unrealized PnL for the position.

        Args:
            current_price: Current market price (uses entry_price if None)

        Returns:
            Unrealized PnL in Quote Currency (e.g. USDT)
        """
        if current_price is None:
            current_price = self.entry_price

        # For LONG position: (current_price - entry_price) * size
        # For SHORT position: (entry_price - current_price) * size
        if self.direction == "LONG":
            pnl = (current_price - self.entry_price) * self.size
        else:  # SHORT
            pnl = (self.entry_price - current_price) * self.size
        return pnl

    def get_total_pnl(self, current_price: Optional[float] = None) -> float:
        """
        Get total PnL (realized + unrealized).

        Args:
            current_price: Current market price

        Returns:
            Total PnL
        """
        unrealized = self.get_unrealized_pnl(current_price) if not self.is_closed else 0
        return self.realized_pnl + unrealized

    def is_profitable(self, current_price: Optional[float] = None) -> bool:
        """Check if position is currently profitable."""
        return self.get_unrealized_pnl(current_price) > 0

    def is_stop_hit(self, current_price: float) -> bool:
        """Check if stop loss is hit at current price."""
        if self.direction == "LONG":
            return current_price <= self.stop_loss
        else:  # SHORT
            return current_price >= self.stop_loss

    def is_take_profit_hit(self, current_price: float) -> bool:
        """Check if any take profit level is hit."""
        if not self.take_profit_levels:
            return False

        for tp_level in self.take_profit_levels:
            tp_price = tp_level["price"]
            if tp_price in self.tp_hit and self.tp_hit[tp_price]:
                continue

            if self.direction == "LONG" and current_price >= tp_price:
                return True
            elif self.direction == "SHORT" and current_price <= tp_price:
                return True

        return False

    def get_next_take_profit(self) -> Optional[Dict]:
        """Get the next take profit level that hasn't been hit."""
        for tp_level in self.take_profit_levels:
            tp_price = tp_level["price"]
            if tp_price not in self.tp_hit or not self.tp_hit[tp_price]:
                return tp_level
        return None

    def hit_take_profit(self, tp_price: float) -> float:
        """
        Mark a take profit level as hit and return the exit size.

        Args:
            tp_price: The take profit price that was hit

        Returns:
            Size to exit at this level
        """
        for tp_level in self.take_profit_levels:
            if tp_level["price"] == tp_price:
                self.tp_hit[tp_price] = True
                exit_size = self.original_size * tp_level["percentage"]
                return exit_size
        return 0

    def partial_exit(self, exit_size: float, exit_price: float, reason: str = ""):
        """
        Execute a partial exit from the position.

        Args:
            exit_size: Quantity to close
            exit_price: Price at which to close
            reason: Reason for the exit
        """
        if exit_size >= self.size:
            # Full exit
            self.close_position(exit_price, reason)
            return

        # Calculate PnL for this portion
        if self.direction == "LONG":
            pnl = (exit_price - self.entry_price) * exit_size
        else:  # SHORT
            pnl = (self.entry_price - exit_price) * exit_size

        # Apply exit fees (0.04% taker fee)
        exit_fee = exit_price * exit_size * 0.0004
        net_pnl = pnl - exit_fee

        # Update position
        self.size -= exit_size
        self.realized_pnl += net_pnl
        self.exit_fees += exit_fee
        self.total_fees += exit_fee

        # Log the partial exit
        self.metadata[f"partial_exit_{len(self.metadata)}"] = {
            "size": exit_size,
            "price": exit_price,
            "pnl": net_pnl,
            "fee": exit_fee,
            "reason": reason,
            "timestamp": pd.Timestamp.now(),
        }

    def close_position(self, exit_price: float, reason: str = ""):
        """
        Close the entire position.

        Args:
            exit_price: Price at which to close
            reason: Reason for closing
        """
        if self.is_closed:
            return

        # Calculate final PnL
        remaining_size = self.size
        if self.direction == "LONG":
            pnl = (exit_price - self.entry_price) * remaining_size
        else:  # SHORT
            pnl = (self.entry_price - exit_price) * remaining_size

        # Apply exit fees
        exit_fee = exit_price * remaining_size * 0.0004
        net_pnl = pnl - exit_fee

        # Update position
        self.exit_price = exit_price
        self.exit_time = pd.Timestamp.now()
        self.exit_reason = reason
        self.size = 0
        self.realized_pnl += net_pnl
        self.exit_fees += exit_fee
        self.total_fees += exit_fee
        self.is_closed = True

        # Calculate total risk-reward ratio
        if self.risk_amount > 0:
            self.risk_reward_ratio = self.realized_pnl / self.risk_amount

    def update_trailing_stop(self, current_price: float, trailing_distance: float = 0.02):
        """
        Update trailing stop based on price movement.

        Args:
            current_price: Current market price
            trailing_distance: Distance to trail behind price (as percentage)
        """
        if not self.trailing_active:
            return

        if self.direction == "LONG":
            if current_price > self.trailing_high:
                self.trailing_high = current_price
                new_stop = current_price * (1 - trailing_distance)
                if new_stop > self.stop_loss:
                    self.stop_loss = new_stop
        else:  # SHORT
            if current_price < self.trailing_low:
                self.trailing_low = current_price
                new_stop = current_price * (1 + trailing_distance)
                if new_stop < self.stop_loss:
                    self.stop_loss = new_stop

    def move_stop_to_breakeven(self):
        """Move stop loss to entry price (breakeven)."""
        self.stop_loss = self.entry_price
        self.breakeven_moved = True

    def move_stop_to_profit(self, profit_price: float):
        """Move stop loss to a profitable level."""
        if self.direction == "LONG":
            self.stop_loss = max(self.stop_loss, profit_price)
        else:  # SHORT
            self.stop_loss = min(self.stop_loss, profit_price)

    def check_ladder_exits(self, current_price: float) -> List[Dict]:
        """
        Check for ladder exit opportunities and return exit instructions.

        Args:
            current_price: Current market price

        Returns:
            List of exit instructions
        """
        if not self.ladder_exit_enabled or self.is_closed:
            return []

        exits = []

        # Check each TP level
        for tp_level in self.take_profit_levels:
            tp_price = tp_level["price"]

            # Skip if already hit
            if tp_price in self.tp_hit and self.tp_hit[tp_price]:
                continue

            # Check if TP level is hit
            if self.direction == "LONG" and current_price >= tp_price:
                exit_size = self.original_size * tp_level["percentage"]
                exits.append(
                    {"action": "partial_exit", "size": exit_size, "price": tp_price, "reason": tp_level.get("reason", f"TP hit at {tp_price}")}
                )
            elif self.direction == "SHORT" and current_price <= tp_price:
                exit_size = self.original_size * tp_level["percentage"]
                exits.append(
                    {"action": "partial_exit", "size": exit_size, "price": tp_price, "reason": tp_level.get("reason", f"TP hit at {tp_price}")}
                )

                # Mark as hit
                self.tp_hit[tp_price] = True

                # Move to breakeven after TP1 if enabled
                if tp_level["percentage"] == 0.5 and self.breakeven_move_enabled and not self.breakeven_moved:
                    exits.append({"action": "move_stop", "new_stop": self.entry_price, "reason": "Move to breakeven after TP1"})

                # Activate trailing stop after TP2 if enabled
                if tp_level["percentage"] == 0.3 and self.trailing_stop_enabled and not self.trailing_active:
                    exits.append({"action": "activate_trailing", "reason": "Activate trailing stop after TP2"})

        return exits

    def activate_trailing_stop(self):
        """Activate trailing stop functionality."""
        self.trailing_active = True
        self.trailing_stop_enabled = True

    def get_position_summary(self) -> Dict:
        """Get a summary of the position."""
        return {
            "id": self.id,
            "direction": self.direction,
            "entry_price": self.entry_price,
            "current_size": self.size,
            "original_size": self.original_size,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "entry_time": self.entry_time,
            "exit_price": self.exit_price,
            "exit_time": self.exit_time,
            "exit_reason": self.exit_reason,
            "is_closed": self.is_closed,
            "realized_pnl": self.realized_pnl,
            "risk_amount": self.risk_amount,
            "risk_reward_ratio": self.risk_reward_ratio,
            "reason": self.reason,
            "trailing_active": self.trailing_active,
            "breakeven_moved": self.breakeven_moved,
            "tp_levels_hit": len([tp for tp in self.tp_hit.values() if tp]),
            "ladder_exit_enabled": self.ladder_exit_enabled,
            "trailing_stop_enabled": self.trailing_stop_enabled,
            "breakeven_move_enabled": self.breakeven_move_enabled,
            "take_profit_levels": self.take_profit_levels,
            "entry_fee": self.entry_fee,
            "exit_fees": self.exit_fees,
            "total_fees": self.total_fees,
        }

    def get_performance_metrics(self) -> Dict:
        """Get performance metrics for the position."""
        if not self.is_closed:
            return {}

        duration = (self.exit_time - self.entry_time).total_seconds() / 3600  # hours

        return {
            "duration_hours": duration,
            "total_pnl": self.realized_pnl,
            "pnl_percentage": (self.realized_pnl / (self.entry_price * self.original_size)) * 100,
            "risk_reward_ratio": self.risk_reward_ratio,
            "total_fees": self.total_fees,
            "net_pnl": self.realized_pnl - self.total_fees,
            "exit_efficiency": self._calculate_exit_efficiency(),
        }

    def _calculate_exit_efficiency(self) -> float:
        """Calculate exit efficiency (placeholder)."""
        # This would compare actual exit to optimal exit
        return 1.0

    def __str__(self) -> str:
        """String representation of the position."""
        status = "CLOSED" if self.is_closed else "OPEN"
        return f"Position {self.id}: {self.direction} {self.size} BTC @ {self.entry_price} " f"[{status}] PnL: {self.realized_pnl:.2f} USDT"

    def __repr__(self) -> str:
        """Detailed representation of the position."""
        return (
            f"Position(id={self.id}, size={self.size}, entry_price={self.entry_price}, "
            f"realized_pnl={self.realized_pnl}, is_closed={self.is_closed})"
        )


class TradeSimulator:
    """
    Simulates trade execution and manages position lifecycle.
    Acts as the "exchange" in the backtest environment.
    """

    def __init__(self):
        """Initialize the trade simulator."""
        self.positions: List[Position] = []
        self.next_position_id = 1
        self.balance = 10000  # Starting USDT balance
        self.asset_qty = 0.0  # BTC quantity held (mostly for spot, but can track net exposure)

    def create_position(
        self,
        entry_price: float,
        size: float,
        stop_loss: float,
        take_profit: Optional[float] = None,
        reason: str = "",
        ladder_exit_enabled: bool = True,
        trailing_stop_enabled: bool = True,
        breakeven_move_enabled: bool = True,
        take_profit_levels: Optional[List[Dict]] = None,
    ) -> Position:
        """
        Create a new position.

        Args:
            entry_price: Entry price
            size: Asset quantity
            stop_loss: Stop loss price
            take_profit: Take profit price
            reason: Reason for the trade
            ladder_exit_enabled: Enable laddered exits
            trailing_stop_enabled: Enable trailing stops
            breakeven_move_enabled: Enable breakeven move after TP1
            take_profit_levels: List of TP levels with percentages

        Returns:
            New Position object
        """
        position = Position(
            id=self.next_position_id,
            entry_price=entry_price,
            size=size,
            stop_loss=stop_loss,
            take_profit=take_profit,
            reason=reason,
            ladder_exit_enabled=ladder_exit_enabled,
            trailing_stop_enabled=trailing_stop_enabled,
            breakeven_move_enabled=breakeven_move_enabled,
        )

        # Set take profit levels if provided
        if take_profit_levels:
            position.take_profit_levels = take_profit_levels

        # Calculate entry fee
        entry_fee = entry_price * size * 0.0004  # 0.04% taker fee
        position.entry_fee = entry_fee

        # Update balances (Futures: Pay fee only, margin is handled by RiskManager)
        self.balance -= entry_fee
        # self.asset_qty += size # Not tracking net exposure in balance here for now, kept simpler

        self.positions.append(position)
        self.next_position_id += 1

        return position

    def update_positions(self, current_price: float, current_time: pd.Timestamp):
        """
        Update all positions with current market conditions and handle ladder exits.

        Args:
            current_price: Current market price
            current_time: Current timestamp
        """
        for position in self.positions:
            if position.is_closed:
                continue

            # Update unrealized PnL
            position.unrealized_pnl = position.get_unrealized_pnl(current_price)

            # Update trailing stops
            position.update_trailing_stop(current_price)

            # Check for ladder exits
            exit_instructions = position.check_ladder_exits(current_price)
            for instruction in exit_instructions:
                if instruction["action"] == "partial_exit":
                    self._execute_partial_exit(position, instruction, current_price)
                elif instruction["action"] == "move_stop":
                    position.stop_loss = instruction["new_stop"]
                elif instruction["action"] == "activate_trailing":
                    position.activate_trailing_stop()

    def _execute_partial_exit(self, position: Position, instruction: Dict, current_price: float):
        """Execute a partial exit."""
        exit_size = instruction["size"]
        exit_price = instruction["price"]
        reason = instruction["reason"]

        # Calculate PnL
        if position.direction == "LONG":
            pnl = (exit_price - position.entry_price) * exit_size
        else:  # SHORT
            pnl = (position.entry_price - exit_price) * exit_size

        # Calculate exit fee
        exit_fee = exit_price * exit_size * 0.0004

        # Update balances (Futures: Add PnL, subtract fee)
        self.balance += pnl - exit_fee
        
        # Update position
        position.partial_exit(exit_size, exit_price, reason)

    def close_position(self, position: Position, exit_price: float, reason: str = ""):
        """Close a position completely."""
        if position.is_closed:
            return

        # Calculate PnL
        if position.direction == "LONG":
            pnl = (exit_price - position.entry_price) * position.size
        else:  # SHORT
            pnl = (position.entry_price - exit_price) * position.size

        # Calculate exit fee
        exit_fee = exit_price * position.size * 0.0004

        # Update balances (Futures: Add PnL, subtract fee)
        self.balance += pnl - exit_fee

        # Close position
        position.close_position(exit_price, reason)

    def get_open_positions(self) -> List[Position]:
        """Get all open positions."""
        return [p for p in self.positions if not p.is_closed]

    def get_closed_positions(self) -> List[Position]:
        """Get all closed positions."""
        return [p for p in self.positions if p.is_closed]

    def get_position_by_id(self, position_id: int) -> Optional[Position]:
        """Get a position by its ID."""
        for position in self.positions:
            if position.id == position_id:
                return position
        return None

    def get_total_exposure(self) -> float:
        """Get total exposure across all open positions."""
        total = 0
        for position in self.get_open_positions():
            total += position.size * position.entry_price
        return total

    def get_total_equity(self, current_price: float) -> float:
        """Get total equity (Balance + Unrealized PnL)."""
        unrealized_pnl = self.get_total_unrealized_pnl(current_price)
        return self.balance + unrealized_pnl

    def get_total_unrealized_pnl(self, current_price: float) -> float:
        """Get total unrealized PnL across all open positions."""
        total = 0
        for position in self.get_open_positions():
            total += position.get_unrealized_pnl(current_price)
        return total

    def get_account_summary(self, current_price: float) -> Dict:
        """Get account summary."""
        return {
            "balance": self.balance,
            "total_equity": self.get_total_equity(current_price),
            "unrealized_pnl": self.get_total_unrealized_pnl(current_price),
            "open_positions": len(self.get_open_positions()),
            "closed_positions": len(self.get_closed_positions()),
        }


# Example usage
if __name__ == "__main__":
    # Test Position
    position = Position(id=1, entry_price=50000, size=0.1, stop_loss=48000, take_profit=52000, reason="Test spot trade")

    print(f"Position created: {position}")
    print(f"Unrealized PnL at 51000: {position.get_unrealized_pnl(51000)}")
    print(f"Is profitable at 51000: {position.is_profitable(51000)}")

    # Test partial exit
    position.partial_exit(0.05, 51000, "TP1 hit")
    print(f"After partial exit: {position}")

    # Test TradeSimulator
    simulator = TradeSimulator()
    pos = simulator.create_position(50000, 0.1, 48000, reason="Simulator test")
    print(f"Created position: {pos}")
    print(f"Account summary: {simulator.get_account_summary(50000)}")

    simulator.update_positions(51000, pd.Timestamp.now())
    print(f"Account summary after update: {simulator.get_account_summary(51000)}")
