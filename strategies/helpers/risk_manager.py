
class RiskManager:
    """
    Calculates position sizes based on risk parameters.
    Extracted from PriceActionStrategy to adhere to SRP.
    """

    @staticmethod
    def calculate_position_size(account_value, risk_per_trade_pct, entry_price, stop_loss, leverage, dynamic_sizing=True):
        """
        Calculate the position size.
        
        Args:
            account_value (float): Current account equity.
            risk_per_trade_pct (float): Risk per trade in percent (e.g. 1.0 for 1%).
            entry_price (float): Entry price.
            stop_loss (float): Stop loss price.
            leverage (float): Max leverage allowed.
            dynamic_sizing (bool): If True, size based on risk distance. If False, fixed % of equity.
            
        Returns:
            float: Position size (units).
        """
        if not dynamic_sizing:
             # Fixed % of equity
             target_value = account_value * (risk_per_trade_pct / 100.0)
             size = target_value / entry_price
        else:
            # Dynamic Risk-Based Sizing
            risk_amount = account_value * (risk_per_trade_pct / 100.0)
            risk_per_share = abs(entry_price - stop_loss)
            
            if risk_per_share == 0:
                return 0.0
                
            size = risk_amount / risk_per_share
            
        # Apply Leverage Limit
        max_pos_value = account_value * leverage
        current_pos_value = size * entry_price
        
        if current_pos_value > max_pos_value:
            # Scale down to max leverage
            size = max_pos_value / entry_price

        return size
