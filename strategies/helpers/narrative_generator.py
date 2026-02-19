
class TradeNarrator:
    """
    Generates detailed, human-readable analysis of how a trade unfolded.
    Extracted from PriceActionStrategy to adhere to SRP.
    """
    
    def __init__(self, risk_reward_ratio):
        self.risk_reward_ratio = risk_reward_ratio

    def generate_narrative(self, trade, exit_reason, stored_info, sl_history):
        """
        Generates the narrative string.
        
        Args:
            trade: Backtrader trade object
            exit_reason (str): Reason for exit (e.g., "Take Profit", "Stop Loss")
            stored_info (dict): Metadata stored for the trade (size, reason, sl, tp)
            sl_history (list): History of SL updates
        """
        direction = "Long" if trade.long else "Short"
        pnl = trade.pnl  # Gross PnL
        pnl_comm = trade.pnlcomm  # Net PnL (after commission)
        entry_price = trade.price
        
        size = stored_info.get('size', 0)
        reason = stored_info.get('reason', 'Signal')
        initial_sl = stored_info.get('stop_loss', 0)
        initial_tp = stored_info.get('take_profit', 0)
        
        if size == 0 and len(trade.history) > 0:
            size = trade.history[0].event.size
        
        # Calculate price move %
        price_diff_pct = 0.0
        exit_price = entry_price
        if entry_price > 0 and size != 0:
            raw_move = pnl / size
            price_diff_pct = abs((raw_move / entry_price) * 100)
            exit_price = entry_price + raw_move if trade.long else entry_price - raw_move
        
        # Calculate duration
        duration = trade.dtclose - trade.dtopen
        duration_days = duration
        
        # Calculate initial risk and R:R achieved
        initial_risk = abs(entry_price - initial_sl) if initial_sl else 0
        achieved_r = 0.0
        if initial_risk > 0 and size != 0:
            move_per_unit = pnl / abs(size)
            achieved_r = move_per_unit / initial_risk
        
        # Commission as % of gross PnL
        commission = abs(pnl - pnl_comm)
        comm_pct_of_pnl = (commission / abs(pnl) * 100) if pnl != 0 else 0
        
        # Build narrative parts
        lines = []
        
        # Line 1: Entry context
        lines.append(f"Entry: {direction} position opened on \"{reason}\" pattern at ${entry_price:,.2f}.")
        
        # Line 2: Risk setup
        if initial_sl and initial_tp:
            target_rr = self.risk_reward_ratio
            lines.append(f"Risk Setup: SL at ${initial_sl:,.2f} (risk ${initial_risk:,.2f}/unit), TP at ${initial_tp:,.2f} (target {target_rr}R).")
        
        # Line 3: What happened (exit-specific)
        if exit_reason == "Take Profit":
            lines.append(f"Outcome: Price moved {price_diff_pct:.2f}% in favor and hit the Take Profit target at ${exit_price:,.2f}. Achieved {achieved_r:+.2f}R.")
            
        elif exit_reason == "Stop Loss":
            # Check if it was a fast stop (< 12 hours on 4h = 3 bars) 
            if duration_days < 1:
                lines.append(f"Outcome: Market reversed against the position quickly. Stop Loss hit at ${exit_price:,.2f} within {duration_days:.1f} days ({achieved_r:+.2f}R). The signal lacked follow-through.")
            else:
                lines.append(f"Outcome: Price moved against over {duration_days:.1f} days before hitting the Stop Loss at ${exit_price:,.2f} ({achieved_r:+.2f}R). Controlled loss as designed.")
            
        elif exit_reason == "Trailing Stop":
            num_updates = len(sl_history) - 1 if sl_history else 0
            
            if pnl > 0:
                # Profitable trailing - compare to what TP would have been
                tp_potential = abs(initial_tp - entry_price) if initial_tp else 0
                actual_profit_per_unit = abs(pnl / size) if size != 0 else 0
                captured_pct = (actual_profit_per_unit / tp_potential * 100) if tp_potential > 0 else 0
                
                lines.append(f"Outcome: Price moved {price_diff_pct:.2f}% in favor over {duration_days:.1f} days. Trailing Stop locked in profits after {num_updates} updates, exiting at ${exit_price:,.2f} ({achieved_r:+.2f}R). Captured {captured_pct:.0f}% of the original TP target.")
            else:
                # Loss trailing - show how much was saved
                saved_pct = 0
                if initial_risk > 0 and size != 0:
                    actual_loss_per_unit = abs(pnl / size)
                    saved_val = initial_risk - actual_loss_per_unit
                    saved_pct = (saved_val / initial_risk) * 100
                
                if saved_pct > 0:
                    lines.append(f"Outcome: Price moved briefly in favor but reversed. Trailing Stop ({num_updates} updates) closed at ${exit_price:,.2f} ({achieved_r:+.2f}R), reducing the loss by {saved_pct:.1f}% vs the initial SL.")
                else:
                    lines.append(f"Outcome: Price didn't gain momentum. Trailing Stop closed at ${exit_price:,.2f} ({achieved_r:+.2f}R) with {num_updates} updates.")
                    
        elif exit_reason == "Breakeven":
            lines.append(f"Outcome: Price moved in favor then reversed. Position closed at breakeven (${exit_price:,.2f}) to protect capital. No loss, no gain.")
        else:
            lines.append(f"Outcome: Closed at ${exit_price:,.2f} ({achieved_r:+.2f}R). Exit reason: {exit_reason}.")
        
        # Line 4: Financial summary
        result_word = "Profit" if pnl_comm > 0 else "Loss"
        lines.append(f"P&L: ${pnl_comm:+,.2f} net ({price_diff_pct:.2f}% move). Commission ${commission:,.2f} ({comm_pct_of_pnl:.1f}% of gross).")
        
        return " ".join(lines)
