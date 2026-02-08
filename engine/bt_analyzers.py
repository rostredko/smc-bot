import backtrader as bt
from datetime import datetime

class TradeListAnalyzer(bt.Analyzer):
    """
    Analyzer that records all closed trades with details required for the dashboard.
    """
    
    def __init__(self):
        self.trades = []

    def notify_trade(self, trade):
        if trade.isclosed:
            # Calculate PnL
            pnl = trade.pnl
            pnlcomm = trade.pnlcomm
            
            # Get Entry/Exit details 
            # Note: A trade might theoretically have multiple entries/exits if averaged in/out.
            # For simplicity, we assume single entry/exit or take the cached price.
            
            # We need to access the history or just take the main price
            entry_date = bt.num2date(trade.dtopen)
            exit_date = bt.num2date(trade.dtclose)
            
            # Retrieve metadata from the opening order
            reason = "Signal"
            stop_loss = None
            take_profit = None
            
            # Try to get info from the opening order
            # The opening transaction is usually the first in history
            if len(trade.history) > 0:
                # history contains list of [datetime, size, price, value, commission, pnl] 
                # OR is it just text? Only internal backlog.
                # Actually trade objects don't store the order object directly in history list easily accessible.
                # But we can try to find the order ref?
                pass
                
            # Alternative: Since we are in the same cerebro instance, we can try to look up the order?
            # No, easiest way is to rely on customized trade objects if possible, but BT doesn't support that well.
            
            # Let's try to access the order info directly if attached to the trade opener?
            # trade.opener is NOT a standard attribute.
            
            # Strategy 2: If we are running in the same strategy instance, the strategy tracks the trades.
            # But analyzer is separate.
            
            # STRATEGY 3: We added .addinfo() to the order.
            # Does the trade object keep a ref to the order?
            # trade.ref is unique.
            # Using private attribute trade.historyon -> NO.
            
            # Let's look at the open order associated with this trade.
            # We can't easily.
            
            # NEW APPROACH:
            # We will use a shared "trade_metadata" dictionary on the strategy instance.
            # The strategy object is accessible via self.strategy (if added to strategy) or self.datas...
            
            # Analyzer is added to Cerebro. self.strategy might be available if using correct hook?
            # Actually, `notify_trade` is called by the strategy? 
            # In backtrader: `strategy.notify_trade` calls `analyzer.notify_trade`.
            # So `self.strategy` should be available in the analyzer!
            
            # Let's use `self.strategy.trade_metadata` (we need to implement this in strategy first? 
            # Wait, I just implemented .addinfo(). Let's see if we can access it).
            
            # Accessing via self.strategy.closed_trades? No.
            
            # Robust way: 
            # In NotifyTrade, the `trade` object is passed.
            # We can iterate `self.strategy.orders`? No.
            
            # Let's use the .addinfo() we just added. 
            # But where is the order?
            # trade.justopened?
            
            # Let's assume we can't get the order from the trade easily.
            # Let's create a mapping in the strategy.
            # self.strategy.trades_info[trade.ref] = { ... }
            # But we don't know trade.ref when creating the order.
            
            # What if we use `notify_order` in the strategy to map order.ref -> trade.ref?
            # When order is executed, trade is opened/updated.
            
            # Okay, simpler plan for this edit:
            # Just extract what we can.
            # I will assume for now we can't get custom info easily without a shared dict.
            # I will use a placeholder and then fix the mapping in the NEXT step.
            
            # Actually, let's fix the schema first.
            # Get size from history or metadata
            size = abs(trade.size) if trade.size else 0
            
            # Prepare initial record
            trade_record = {
                "id": trade.ref,
                "direction": "LONG" if trade.long else "SHORT",
                "entry_price": trade.price,
                # exit_price calculation needs valid size, so we defer it slightly or calc with 0 safe div
                "entry_time": entry_date.isoformat(),
                "exit_time": exit_date.isoformat(),
                "duration": str(exit_date - entry_date),
                "realized_pnl": pnlcomm,
                # Placeholders to be updated from metadata
                "stop_loss": 0,
                "take_profit": 0,
                "reason": "Signal", 
                "exit_reason": "Take Profit" if pnl > 0 else "Stop Loss",
                "commission": pnl - pnlcomm
            }

            # Attempt to retrieve enriched data from strategy if available
            if hasattr(self.strategy, 'get_trade_info'):
                 info = self.strategy.get_trade_info(trade.ref)
                 if info:
                     trade_record.update(info)
                     # If size was 0 from closed trade object, try to get it from metadata
                     if size == 0 and 'size' in info:
                         size = info['size']
            
            # Finalize exit price calculation with correct size
            if size != 0:
                pnl_per_unit = pnl / size
                if trade.long:
                    trade_record["exit_price"] = trade.price + pnl_per_unit
                else:
                    trade_record["exit_price"] = trade.price - pnl_per_unit
                
                trade_record["size"] = size
            else:
                 trade_record["exit_price"] = trade.price
                 trade_record["size"] = 0

            self.trades.append(trade_record)

    def get_analysis(self):
        return self.trades


class EquityCurveAnalyzer(bt.Analyzer):
    """
    Analyzer that records the portfolio equity value at each step.
    """
    def __init__(self):
        self.equity_curve = []
        
    def next(self):
        # Record timestamp and current equity
        # Use datetime(0) to get python datetime object
        self.equity_curve.append({
            'timestamp': self.datas[0].datetime.datetime(0),
            'equity': self.strategy.broker.getvalue()
        })
        
    def get_analysis(self):
        return self.equity_curve
