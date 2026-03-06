class RiskManager:
    """
    Position sizing: raw_size = risk_amount / sl_distance.
    Effective size is capped by: leverage, max_drawdown/10 risk cap, position_cap_adverse.
    position_cap_adverse is clamped to [0.5, 1.0] for risk safety.
    See docs/ENTRY_MECHANISMS_AND_GHOST_TRADE.md for full formula.
    """

    @staticmethod
    def calculate_position_size(account_value, risk_per_trade_pct, entry_price, stop_loss, leverage,
                               dynamic_sizing=True, max_drawdown_pct=None, position_cap_adverse=0.5,
                               direction=None):
        try:
            entry = float(entry_price)
            stop = float(stop_loss)
            equity = float(account_value) if account_value is not None else 0.0
        except (TypeError, ValueError):
            return 0.0

        if entry <= 0 or equity <= 0:
            return 0.0
        try:
            risk_pct_raw = float(risk_per_trade_pct)
        except (TypeError, ValueError):
            risk_pct_raw = 0.0
        risk_pct = max(0.0, min(100.0, risk_pct_raw))

        try:
            lev_raw = float(leverage)
        except (TypeError, ValueError):
            lev_raw = 0.1
        lev = max(0.1, lev_raw)

        side = str(direction).lower() if direction is not None else ""
        if side in ("long", "buy") and stop >= entry:
            return 0.0
        if side in ("short", "sell") and stop <= entry:
            return 0.0

        if dynamic_sizing:
            risk_amount = equity * (risk_pct / 100.0)
            try:
                if max_drawdown_pct is not None and float(max_drawdown_pct) > 0:
                    risk_amount = min(risk_amount, equity * (float(max_drawdown_pct) / 100.0) / 10)
            except (TypeError, ValueError):
                pass
            risk_per_unit = abs(entry - stop)
            if risk_per_unit == 0:
                return 0.0
            size = risk_amount / risk_per_unit
        else:
            size = (equity * (risk_pct / 100.0)) / entry

        pos_value = size * entry
        max_value = equity * lev
        if pos_value > max_value:
            size = max_value / entry
        try:
            if max_drawdown_pct is not None and float(max_drawdown_pct) > 0:
                adverse = max(0.5, min(1.0, float(position_cap_adverse)))
                max_from_dd = equity * (float(max_drawdown_pct) / 100.0) / adverse
                if size * entry > max_from_dd:
                    size = max_from_dd / entry
        except (TypeError, ValueError):
            pass
        return size
