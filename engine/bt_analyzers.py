import backtrader as bt


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
            entry_date = bt.num2date(trade.dtopen)
            exit_date = bt.num2date(trade.dtclose)
            
            # Get size from trade or rely on metadata

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
                "exit_reason": "Unknown", # Will be updated from metadata
                "commission": pnl - pnlcomm
            }

            info = self.strategy.get_trade_info(trade.ref) if hasattr(self.strategy, 'get_trade_info') else {}
            if info:
                trade_record.update(info)
                if size == 0 and 'size' in info:
                    size = info['size']
                if 'exit_reason' in info:
                    trade_record['exit_reason'] = info['exit_reason']
                elif trade_record['realized_pnl'] > 0:
                    trade_record['exit_reason'] = "Take Profit (Approx)"
                else:
                    trade_record['exit_reason'] = "Stop Loss (Approx)"
                if 'sl_calculation' in info:
                    trade_record['sl_calculation'] = info['sl_calculation']
                if 'tp_calculation' in info:
                    trade_record['tp_calculation'] = info['tp_calculation']

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
