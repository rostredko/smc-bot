class RiskManager:
    """
    Position sizing: raw_size = risk_amount / sl_distance.
    Effective size is capped by: leverage, max_drawdown/10 risk cap, position_cap_adverse.
    position_cap_adverse is clamped to [0.5, 1.0] for risk safety.
    See docs/ENTRY_MECHANISMS_AND_GHOST_TRADE.md for full formula.
    """

    @staticmethod
    def calculate_position_size(account_value, risk_per_trade_pct, entry_price, stop_loss, leverage,
                               dynamic_sizing=True, max_drawdown_pct=None, position_cap_adverse=0.5):
        if entry_price <= 0 or not account_value or account_value <= 0:
            return 0.0
        risk_pct = max(0.0, min(100.0, float(risk_per_trade_pct)))
        lev = max(0.1, float(leverage))

        if dynamic_sizing:
            risk_amount = account_value * (risk_pct / 100.0)
            try:
                if max_drawdown_pct is not None and float(max_drawdown_pct) > 0:
                    risk_amount = min(risk_amount, account_value * (float(max_drawdown_pct) / 100.0) / 10)
            except (TypeError, ValueError):
                pass
            risk_per_unit = abs(entry_price - stop_loss)
            if risk_per_unit == 0:
                return 0.0
            size = risk_amount / risk_per_unit
        else:
            size = (account_value * (risk_pct / 100.0)) / entry_price

        pos_value = size * entry_price
        max_value = account_value * lev
        if pos_value > max_value:
            size = max_value / entry_price
        try:
            if max_drawdown_pct is not None and float(max_drawdown_pct) > 0:
                adverse = max(0.5, min(1.0, float(position_cap_adverse)))
                max_from_dd = account_value * (float(max_drawdown_pct) / 100.0) / adverse
                if size * entry_price > max_from_dd:
                    size = max_from_dd / entry_price
        except (TypeError, ValueError):
            pass
        return size
