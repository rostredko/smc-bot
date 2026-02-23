
class RiskManager:
    """
    Calculates position sizes based on risk parameters.
    Extracted from PriceActionStrategy to adhere to SRP.
    """

    @staticmethod
    def calculate_position_size(account_value, risk_per_trade_pct, entry_price, stop_loss, leverage, dynamic_sizing=True):
        """
        Calculate the position size.

        Dynamic mode (recommended):
            Risk exactly risk_per_trade_pct% of equity per trade.
            Size = (account_value * risk%) / |entry - SL|
            This means a 1% risk trade would lose exactly 1% if SL is hit.

        Fixed mode:
            Allocate risk_per_trade_pct% of account value as position value.

        Both modes are capped at (account_value * leverage) to prevent
        exceeding the allowed notional exposure.

        Args:
            account_value (float): Current account equity.
            risk_per_trade_pct (float): Risk per trade as percent (e.g. 1.0 = 1%).
            entry_price (float): Entry price.
            stop_loss (float): Stop loss price.
            leverage (float): Maximum allowed leverage multiplier.
            dynamic_sizing (bool): If True, size based on risk distance. If False, fixed % of equity.

        Returns:
            float: Position size in units (e.g. BTC).
        """
        if entry_price <= 0 or account_value is None or account_value <= 0:
            return 0.0

        if not dynamic_sizing:
            # Fixed: allocate risk_per_trade_pct% of account as position value
            target_value = account_value * (risk_per_trade_pct / 100.0)
            size = target_value / entry_price
        else:
            # Dynamic: risk exactly risk_per_trade_pct% of account on this trade
            risk_amount = account_value * (risk_per_trade_pct / 100.0)
            risk_per_unit = abs(entry_price - stop_loss)

            if risk_per_unit == 0:
                return 0.0

            size = risk_amount / risk_per_unit

        # Cap at maximum allowable notional position (account equity * leverage)
        max_pos_value = account_value * leverage
        current_pos_value = size * entry_price

        if current_pos_value > max_pos_value:
            size = max_pos_value / entry_price

        return size
