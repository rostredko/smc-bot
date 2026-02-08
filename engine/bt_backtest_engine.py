import backtrader as bt
import pandas as pd
from typing import Dict, Any
from .base_engine import BaseEngine
from .data_loader import DataLoader

from .bt_analyzers import TradeListAnalyzer, EquityCurveAnalyzer

class BTBacktestEngine(BaseEngine):
    """
    Concrete implementation of BacktestEngine using Backtrader.
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.data_loader = DataLoader(
            exchange_name=config.get("exchange", "binance"),
            exchange_type=config.get("exchange_type", "future")
        )
        self.closed_trades = []

    def add_data(self):
        """
        Load data using DataLoader and add it to Cerebro.
        """
        symbol = self.config.get("symbol", "BTC/USDT")
        timeframes = self.config.get("timeframes", ["1h"])
        start_date = self.config.get("start_date")
        end_date = self.config.get("end_date")

        # Backtrader requires data feeds. We'll use PandasData.
        # We need to ensure the DataFrame has the correct index and columns.
        
        for tf in timeframes:
            print(f"Loading data for {symbol} {tf}...")
            df = self.data_loader.get_data(symbol, tf, start_date, end_date)
            
            if df is None or df.empty:
                print(f"Warning: No data found for {symbol} {tf}")
                continue

            # Prepare DataFrame for Backtrader
            # Ensure 'datetime' index
            if not isinstance(df.index, pd.DatetimeIndex):
                # Try to find a datetime column
                if 'timestamp' in df.columns:
                     df['datetime'] = pd.to_datetime(df['timestamp'])
                     df.set_index('datetime', inplace=True)
                else:
                    print(f"Error: Could not determine datetime index for {tf}")
                    continue

            # Rename columns to match Backtrader requirements if necessary
            # BT expects: open, high, low, close, volume, openinterest
            # Our DataLoader likely returns lowercase options.
            df = df.rename(columns={
                "open": "open",
                "high": "high",
                "low": "low",
                "close": "close",
                "volume": "volume"
            })

            # Create Data Feed
            data = bt.feeds.PandasData(dataname=df, name=f"{symbol}_{tf}")
            self.cerebro.adddata(data)

    def run_backtest(self):
        """
        Run the backtest and return formatted results.
        """
        self.add_data()
        
        # Add Analyzers
        self.cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe', riskfreerate=0.0, timeframe=bt.TimeFrame.Days, compression=1, factor=365)
        self.cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
        self.cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')
        self.cerebro.addanalyzer(bt.analyzers.SQN, _name='sqn')
        self.cerebro.addanalyzer(TradeListAnalyzer, _name='tradelist')
        self.cerebro.addanalyzer(EquityCurveAnalyzer, _name='equity')

        print("Starting Backtrader backtest...")
        results = self.run()
        
        if not results:
            self.equity_curve = []
            return {}

        strat = results[0]
        
        # Capture closed trades
        self.closed_trades = strat.analyzers.tradelist.get_analysis()
        
        # Capture equity curve
        self.equity_curve = strat.analyzers.equity.get_analysis()

        # Format metrics
        sharpe = strat.analyzers.sharpe.get_analysis().get('sharperatio')
        if sharpe is None: sharpe = 0.0

        drawdown_info = strat.analyzers.drawdown.get_analysis()
        max_dd = drawdown_info.get('max', {}).get('drawdown', 0.0)
        if max_dd is None: max_dd = 0.0

        metrics = {
            "initial_capital": self.cerebro.broker.startingcash,
            "final_capital": self.cerebro.broker.getvalue(),
            "total_pnl": self.cerebro.broker.getvalue() - self.cerebro.broker.startingcash,
            "sharpe_ratio": sharpe,
            "max_drawdown": max_dd,
            "total_trades": strat.analyzers.trades.get_analysis().get('total', {}).get('closed', 0),
            "win_rate": self._calculate_win_rate(strat.analyzers.trades.get_analysis()),
            "profit_factor": self._calculate_profit_factor(strat.analyzers.trades.get_analysis()),
            "win_count": strat.analyzers.trades.get_analysis().get('won', {}).get('total', 0),
            "loss_count": strat.analyzers.trades.get_analysis().get('lost', {}).get('total', 0),
            "avg_win": strat.analyzers.trades.get_analysis().get('won', {}).get('pnl', {}).get('average', 0.0),
            "avg_loss": strat.analyzers.trades.get_analysis().get('lost', {}).get('pnl', {}).get('average', 0.0),
        }
        
        return metrics

    def _calculate_win_rate(self, trade_analysis):
        total = trade_analysis.get('total', {}).get('closed', 0)
        if total == 0:
            return 0.0
        won = trade_analysis.get('won', {}).get('total', 0)
        return (won / total) * 100

    def _calculate_profit_factor(self, trade_analysis):
        won_pnl = trade_analysis.get('won', {}).get('pnl', {}).get('total', 0.0)
        lost_pnl = abs(trade_analysis.get('lost', {}).get('pnl', {}).get('total', 0.0))
        
        if lost_pnl == 0:
            return 0.0 if won_pnl == 0 else float('inf')
            
        return won_pnl / lost_pnl
