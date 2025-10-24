"""
Risk Management and Position Sizing module.
Handles risk calculations, position sizing, and enforcement of risk rules.
"""

from typing import Dict, List, Optional
from datetime import datetime, timedelta
from .position import Position


class SpotRiskManager:
    """
    Risk Manager optimized for spot crypto trading.
    Handles cash-based position sizing and risk management.
    """

    def __init__(
        self,
        initial_capital: float,
        risk_per_trade: float = 0.5,
        max_drawdown: float = 15.0,
        max_positions: int = 1,
        max_consecutive_losses: int = 5,
        daily_loss_limit: float = 3.0,
    ):
        """
        Initialize spot risk manager.

        Args:
            initial_capital: Starting USDT balance
            risk_per_trade: Risk percentage per trade (e.g., 0.5 for 0.5%)
            max_drawdown: Maximum allowed drawdown percentage
            max_positions: Maximum simultaneous positions (1 for spot)
            max_consecutive_losses: Max consecutive losses before cooldown
            daily_loss_limit: Daily loss limit percentage
        """
        self.initial_capital = initial_capital
        self.cash_usdt = initial_capital
        self.asset_qty = 0.0  # BTC quantity held
        self.peak_equity = initial_capital
        self.risk_per_trade = risk_per_trade
        self.max_drawdown = max_drawdown
        self.max_positions = max_positions
        self.max_consecutive_losses = max_consecutive_losses
        self.daily_loss_limit = daily_loss_limit

        # Track positions and risk metrics
        self.open_positions: List[Position] = []
        self.daily_pnl = 0.0
        self.consecutive_losses = 0

        # Risk state management
        self.trading_halted = False
        self.halt_reason = None
        self.soft_halt = False
        self.halt_start_time = None
        self.halt_duration_hours = 24

        # Risk adaptation
        self.risk_reduction_factor = 1.0
        self.last_loss_time = None

        # Cooldown tracking
        self.last_stop_times = {"LONG": None}
        self.cooldown_bars = 16  # 4h cooldown for 15m timeframe

        # Exchange constraints
        self.min_qty = 0.00001
        self.step_size = 0.00001
        self.min_notional = 10.0
        self.tick_size = 0.01
        self.maker_fee = 0.0001
        self.taker_fee = 0.0004
        self.slippage_bp = 1  # 0.01%

    def get_equity(self, current_price: float) -> float:
        """Calculate total equity (cash + asset value)."""
        return self.cash_usdt + (self.asset_qty * current_price)

    def can_open_position(
        self, entry_price: float, stop_loss: float, current_bar_time: datetime = None, current_price: float = None
    ) -> tuple[bool, str]:
        """
        Check if a LONG position can be opened (spot trading only).

        Args:
            entry_price: Entry price for the position
            stop_loss: Stop loss price
            current_bar_time: Current bar timestamp for cooldown check

        Returns:
            Tuple of (can_open, reason)
        """
        # Check cooldown after stop loss
        if current_bar_time and self.last_stop_times.get("LONG"):
            time_since_stop = current_bar_time - self.last_stop_times["LONG"]
            cooldown_duration = timedelta(minutes=15 * self.cooldown_bars)  # 15m bars
            if time_since_stop < cooldown_duration:
                return False, "COOLDOWN_ACTIVE"

        # Check for hard halt
        if self.trading_halted:
            return False, f"Trading halted: {self.halt_reason}"

        # Check drawdown limit
        price_for_equity = current_price if current_price is not None else entry_price
        current_equity = self.get_equity(price_for_equity)
        current_drawdown = self.calculate_current_drawdown(current_equity)

        # Update peak equity if current equity is higher
        if current_equity > self.peak_equity:
            self.peak_equity = current_equity

        # Always update peak equity to current equity if we're below initial capital
        # This prevents false drawdown calculations
        if current_equity < self.initial_capital:
            self.peak_equity = current_equity

        if current_drawdown >= self.max_drawdown:
            self.trading_halted = True
            self.halt_reason = f"Critical drawdown exceeded: {current_drawdown:.2f}%"
            return False, self.halt_reason

        # Check consecutive losses
        if self.consecutive_losses >= self.max_consecutive_losses:
            if self.soft_halt and self.halt_start_time:
                if datetime.now() - self.halt_start_time > timedelta(hours=self.halt_duration_hours):
                    self.soft_halt = False
                    self.halt_start_time = None
                    self.risk_reduction_factor = 0.5
                else:
                    return False, f"Soft halt active: {self.consecutive_losses} consecutive losses"
            else:
                self.soft_halt = True
                self.halt_start_time = datetime.now()
                self.risk_reduction_factor = 0.3
                return False, f"Soft halt initiated: {self.consecutive_losses} consecutive losses"

        # Position limit check
        if len(self.open_positions) >= self.max_positions:
            return False, f"Maximum positions ({self.max_positions}) reached"

        # Check if we have enough cash
        position_value = self.calculate_position_size(entry_price, stop_loss) * entry_price
        if position_value > self.cash_usdt * 0.95:  # Leave 5% buffer
            return False, "INSUFFICIENT_CASH"

        return True, "OK"

    def calculate_position_size(self, entry_price: float, stop_loss: float) -> float:
        """
        Calculate position size for spot trading.

        Args:
            entry_price: Entry price
            stop_loss: Stop loss price

        Returns:
            Position size in BTC
        """
        # Calculate risk amount
        risk_amount = self.cash_usdt * (self.risk_per_trade / 100) * self.risk_reduction_factor

        # Calculate risk distance
        risk_distance = max(entry_price - stop_loss, entry_price * 0.01)  # Min 1% stop

        if risk_distance <= 0:
            return 0

        # Calculate position size from risk
        qty_from_risk = risk_amount / risk_distance

        # Calculate position size from available cash (leave 5% buffer for fees)
        qty_from_cash = (self.cash_usdt * 0.95) / entry_price

        # Use the smaller of the two
        qty = min(qty_from_risk, qty_from_cash)

        # Round to step size
        qty = self._floor_to_step(qty, self.step_size)

        return qty

    def _floor_to_step(self, qty: float, step_size: float) -> float:
        """Round quantity down to step size."""
        return (qty // step_size) * step_size

    def calculate_current_drawdown(self, current_equity: float) -> float:
        """Calculate current drawdown percentage from peak equity."""
        if self.peak_equity <= 0:
            return 0

        drawdown = (self.peak_equity - current_equity) / self.peak_equity * 100
        return max(0, drawdown)

    def update_balance(self, pnl: float, position_direction: str = None, exit_time: datetime = None):
        """
        Update balance after position close.

        Args:
            pnl: Profit or loss from the trade
            position_direction: Direction of the closed position ('LONG')
            exit_time: Time when position was closed
        """
        self.cash_usdt += pnl

        # Update peak equity - use current cash + asset value
        # Note: This method doesn't have current_price, so we'll update peak in the main loop
        # where current_price is available

        # Track consecutive losses
        if pnl < 0:
            self.consecutive_losses += 1
            self.last_loss_time = datetime.now()

            # Record stop loss time for cooldown
            if position_direction and exit_time:
                self.last_stop_times[position_direction] = exit_time

            # Adjust risk reduction factor
            if self.consecutive_losses >= 3:
                self.risk_reduction_factor = max(0.3, 1.0 - (self.consecutive_losses * 0.1))
        else:
            # Reset consecutive losses
            if self.consecutive_losses > 0:
                self.consecutive_losses = 0
                self.risk_reduction_factor = min(1.0, self.risk_reduction_factor + 0.2)

        # Update daily PnL
        self.daily_pnl += pnl

    def add_position(self, position: Position):
        """Add a new position to tracking."""
        self.open_positions.append(position)
        # Update balances
        self.cash_usdt -= position.size * position.entry_price
        self.asset_qty += position.size

    def remove_position(self, position: Position):
        """Remove a position from tracking."""
        if position in self.open_positions:
            self.open_positions.remove(position)
            # Update balances
            self.cash_usdt += position.size * position.exit_price
            self.asset_qty -= position.size

    def get_risk_metrics(self, current_price: float = 50000) -> Dict:
        """Get risk metrics."""
        current_equity = self.get_equity(current_price)
        return {
            "cash_usdt": self.cash_usdt,
            "asset_qty": self.asset_qty,
            "peak_equity": self.peak_equity,
            "current_drawdown": self.calculate_current_drawdown(current_equity),
            "open_positions": len(self.open_positions),
            "consecutive_losses": self.consecutive_losses,
            "trading_halted": self.trading_halted,
            "soft_halt": self.soft_halt,
            "halt_reason": self.halt_reason,
            "daily_pnl": self.daily_pnl,
            "risk_reduction_factor": self.risk_reduction_factor,
            "last_loss_time": self.last_loss_time,
            "last_stop_times": self.last_stop_times,
        }

    def reset_daily_metrics(self):
        """Reset daily tracking metrics."""
        self.daily_pnl = 0

    def validate_risk_reward_ratio(self, entry_price: float, stop_loss: float, take_profit: float, min_risk_reward: float) -> tuple[bool, str]:
        """
        Validate risk/reward ratio for a trade.

        Args:
            entry_price: Entry price
            stop_loss: Stop loss price
            take_profit: Take profit price
            min_risk_reward: Minimum required risk/reward ratio

        Returns:
            Tuple of (is_valid, reason)
        """
        if entry_price <= 0 or stop_loss <= 0 or take_profit <= 0:
            return False, "Invalid price values"

        # Calculate risk and reward distances
        if entry_price > stop_loss:  # Long position
            risk_distance = entry_price - stop_loss
            reward_distance = take_profit - entry_price
        else:  # Short position
            risk_distance = stop_loss - entry_price
            reward_distance = entry_price - take_profit

        if risk_distance <= 0:
            return False, "Invalid risk distance"

        if reward_distance <= 0:
            return False, "Invalid reward distance"

        # Calculate risk/reward ratio
        rr_ratio = reward_distance / risk_distance

        if rr_ratio < min_risk_reward:
            return False, f"RR ratio {rr_ratio:.2f} below minimum {min_risk_reward:.2f}"

        return True, f"RR ratio {rr_ratio:.2f} acceptable"

    def update_peak_equity(self, current_price: float):
        """Update peak equity with current market price."""
        current_equity = self.get_equity(current_price)

        # Only update peak equity if current equity is higher than current peak
        if current_equity > self.peak_equity:
            self.peak_equity = current_equity
            self.risk_reduction_factor = 1.0

        # If we're below initial capital, peak should remain at initial capital
        # This ensures proper drawdown calculation
        if current_equity < self.initial_capital and self.peak_equity < self.initial_capital:
            self.peak_equity = self.initial_capital

    def _calculate_total_potential_risk(self) -> float:
        """Calculate total potential risk from all open positions."""
        total_risk = 0.0
        for position in self.open_positions:
            if hasattr(position, "risk_amount"):
                total_risk += position.risk_amount
        return total_risk


class PositionSizer:
    """
    Position sizing calculator for spot trading.
    Calculates optimal position size based on risk and available cash.
    """

    def __init__(
        self,
        cash_usdt: float,
        min_qty: float = 0.00001,
        step_size: float = 0.00001,
        min_notional: float = 10.0,
        tick_size: float = 0.01,
        maker_fee: float = 0.0001,
        taker_fee: float = 0.0004,
        slippage_bp: int = 1,
    ):
        """
        Initialize spot position sizer.

        Args:
            cash_usdt: Available USDT balance
            min_qty: Minimum order quantity
            step_size: Order quantity step size
            min_notional: Minimum order value
            tick_size: Price tick size
            maker_fee: Maker fee percentage
            taker_fee: Taker fee percentage
            slippage_bp: Slippage in basis points
        """
        self.cash_usdt = cash_usdt
        self.min_qty = min_qty
        self.step_size = step_size
        self.min_notional = min_notional
        self.tick_size = tick_size
        self.maker_fee = maker_fee
        self.taker_fee = taker_fee
        self.slippage_bp = slippage_bp

    def calculate_size(self, entry_price: float, stop_loss: float, risk_per_trade_pct: float = 0.5) -> Dict:
        """
        Calculate position size for spot trading.

        Args:
            entry_price: Entry price
            stop_loss: Stop loss price
            risk_per_trade_pct: Risk percentage per trade

        Returns:
            Dictionary with position sizing details
        """
        # Calculate risk amount
        risk_amount = self.cash_usdt * (risk_per_trade_pct / 100)

        # Calculate risk distance
        risk_distance = max(entry_price - stop_loss, entry_price * 0.01)

        if risk_distance <= 0:
            return {"qty": 0, "min_notional_met": False, "reason": "Invalid risk distance"}

        # Calculate position size from risk
        qty_from_risk = risk_amount / risk_distance

        # Calculate position size from available cash (leave 5% buffer for fees)
        qty_from_cash = (self.cash_usdt * 0.95) / entry_price

        # Use the smaller of the two
        qty = min(qty_from_risk, qty_from_cash)

        # Round to step size
        qty = self._floor_to_step(qty, self.step_size)

        # Check minimum quantity
        if qty < self.min_qty:
            return {"qty": 0, "min_notional_met": False, "reason": "Below minimum quantity"}

        # Check minimum notional
        order_value = qty * entry_price
        min_notional_met = order_value >= self.min_notional

        if not min_notional_met:
            return {"qty": 0, "min_notional_met": False, "reason": "Below minimum notional"}

        # Calculate fees
        entry_fee = order_value * self.taker_fee
        exit_fee = order_value * self.taker_fee
        total_fees = entry_fee + exit_fee

        # Calculate target price for 1:2 R:R
        target_price = entry_price + (2 * risk_distance)

        return {
            "qty": qty,
            "order_value": order_value,
            "risk_amount": risk_amount,
            "risk_distance": risk_distance,
            "entry_fee": entry_fee,
            "exit_fee": exit_fee,
            "total_fees": total_fees,
            "target_price": target_price,
            "min_notional_met": min_notional_met,
            "reason": "OK",
        }

    def _floor_to_step(self, qty: float, step_size: float) -> float:
        """Round quantity down to step size."""
        return (qty // step_size) * step_size

    def calculate_exit_fees(self, qty: float, exit_price: float) -> float:
        """Calculate fees for position exit."""
        exit_value = qty * exit_price
        return exit_value * self.taker_fee

    def calculate_total_fees(self, qty: float, entry_price: float, exit_price: float) -> float:
        """Calculate total fees for round trip."""
        entry_fee = qty * entry_price * self.taker_fee
        exit_fee = qty * exit_price * self.taker_fee
        return entry_fee + exit_fee


# Example usage
if __name__ == "__main__":
    # Test SpotRiskManager
    risk_manager = SpotRiskManager(initial_capital=10000, risk_per_trade=0.5, max_drawdown=15.0, max_positions=1)

    print(f"Spot Risk Manager initialized:")
    print(f"  Cash USDT: {risk_manager.cash_usdt}")
    print(f"  Asset Qty: {risk_manager.asset_qty}")
    print(f"  Risk per trade: {risk_manager.risk_per_trade}%")

    # Test position sizing
    position_size = risk_manager.calculate_position_size(50000, 48000)
    print(f"  Position size for 50000/48000: {position_size:.6f} BTC")

    # Test PositionSizer
    sizer = PositionSizer(cash_usdt=10000)
    sizing_result = sizer.calculate_size(50000, 48000, 0.5)
    print(f"\nSpot Position Sizer result:")
    print(f"  Quantity: {sizing_result['qty']:.6f} BTC")
    print(f"  Order value: ${sizing_result['order_value']:.2f}")
    print(f"  Total fees: ${sizing_result['total_fees']:.2f}")
    print(f"  Target price: ${sizing_result['target_price']:.2f}")
