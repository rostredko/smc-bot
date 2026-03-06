import backtrader as bt
import pandas as pd
import threading
from typing import Dict, Any
from .base_engine import BaseEngine
from .data_loader import DataLoader
from .logger import get_logger

from .bt_analyzers import TradeListAnalyzer, EquityCurveAnalyzer

logger = get_logger(__name__)

class SMCDataFeed(bt.feeds.PandasData):
    params = (
        ('datetime', None),
        ('open', -1),
        ('high', -1),
        ('low', -1),
        ('close', -1),
        ('volume', -1),
        ('openinterest', -1),
    )

class BTBacktestEngine(BaseEngine):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.data_loader = DataLoader(
            exchange_name=config.get("exchange", "binance"),
            exchange_type=config.get("exchange_type", "future")
        )
        self.data_loader.cancel_check = lambda: self.should_cancel
        self.closed_trades = []
        self._cancel_lock = threading.Lock()
        self._cancel_called = False

    def cancel(self):
        """
        Request cooperative cancellation.
        Safe to call from another thread (API thread while backtest runs in executor).
        """
        with self._cancel_lock:
            if self._cancel_called:
                return
            self._cancel_called = True

        self.should_cancel = True
        try:
            if hasattr(self.cerebro, "runstop"):
                self.cerebro.runstop()
        except Exception as e:
            logger.debug(f"runstop() failed during cancel: {e}")

    def add_data(self):
        """
        Load data using DataLoader and add it to Cerebro.
        """
        if self.should_cancel:
            return

        symbol = self.config.get("symbol", "BTC/USDT")
        timeframes = self.config.get("timeframes", ["1h"])
        start_date = self.config.get("start_date") or "2024-01-01"
        end_date = self.config.get("end_date") or "2024-12-31"

        ordered_timeframes = list(reversed(timeframes)) if len(timeframes) > 1 else timeframes
        
        for tf in ordered_timeframes:
            if self.should_cancel:
                return
            logger.info(f"Loading data for {symbol} {tf}...")
            try:
                df = self.data_loader.get_data(symbol, tf, start_date, end_date)
            except RuntimeError as e:
                if self.should_cancel and "cancel" in str(e).lower():
                    logger.info(f"Data loading cancelled for {symbol} {tf}")
                    return
                raise
            if self.should_cancel:
                return
            
            if df is None or df.empty:
                logger.warning(f"No data found for {symbol} {tf}")
                continue

            if not isinstance(df.index, pd.DatetimeIndex):
                # Try to find a datetime column
                if 'timestamp' in df.columns:
                     df['datetime'] = pd.to_datetime(df['timestamp'])
                     df.set_index('datetime', inplace=True)
                else:
                    logger.error(f"Could not determine datetime index for {tf}")
                    continue

            expected_cols = {'open', 'high', 'low', 'close', 'volume'}
            missing = list(expected_cols - set(df.columns))
            if missing:
                logger.warning(f"Missing columns {missing} for {tf}")
                continue

            data = SMCDataFeed(dataname=df, name=f"{symbol}_{tf}")
            self.cerebro.adddata(data)

    def run_backtest(self):
        """
        Run the backtest and return formatted results.
        """
        if self.should_cancel:
            self.equity_curve = []
            self.closed_trades = []
            return {"cancelled": True}

        self.add_data()
        if self.should_cancel:
            self.equity_curve = []
            self.closed_trades = []
            return {"cancelled": True}
        
        self.cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe', riskfreerate=0.0, timeframe=bt.TimeFrame.Days, compression=1, factor=365)
        self.cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
        self.cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')
        self.cerebro.addanalyzer(bt.analyzers.SQN, _name='sqn')
        self.cerebro.addanalyzer(TradeListAnalyzer, _name='tradelist')
        self.cerebro.addanalyzer(EquityCurveAnalyzer, _name='equity')
        
        self.cerebro.addobserver(bt.observers.DrawDown)

        logger.info("Starting Backtrader backtest...")
        results = self.run()
        
        if not results:
            self.equity_curve = []
            if self.should_cancel:
                self.closed_trades = []
                return {
                    "cancelled": True,
                    "initial_capital": self.cerebro.broker.startingcash,
                    "final_capital": self.cerebro.broker.getvalue(),
                    "total_pnl": self.cerebro.broker.getvalue() - self.cerebro.broker.startingcash,
                    "sharpe_ratio": 0.0,
                    "max_drawdown": 0.0,
                    "total_trades": 0,
                    "win_rate": 0.0,
                    "profit_factor": 0.0,
                    "win_count": 0,
                    "loss_count": 0,
                    "avg_win": 0.0,
                    "avg_loss": 0.0,
                }
            return {}

        strat = results[0]
        self.strategy = strat

        # Capture closed trades
        self.closed_trades = strat.analyzers.tradelist.get_analysis()
        
        # Capture equity curve
        self.equity_curve = strat.analyzers.equity.get_analysis()

        sharpe = strat.analyzers.sharpe.get_analysis().get('sharperatio')
        if sharpe is None: sharpe = 0.0

        drawdown_info = strat.analyzers.drawdown.get_analysis()
        max_dd = self._safe_max_drawdown(drawdown_info)

        trade_analysis = strat.analyzers.trades.get_analysis()
        won = trade_analysis.get('won', {})
        lost = trade_analysis.get('lost', {})

        metrics = {
            "initial_capital": self.cerebro.broker.startingcash,
            "final_capital": self.cerebro.broker.getvalue(),
            "total_pnl": self.cerebro.broker.getvalue() - self.cerebro.broker.startingcash,
            "sharpe_ratio": sharpe,
            "max_drawdown": max_dd,
            "total_trades": trade_analysis.get('total', {}).get('closed', 0),
            "win_rate": self._calculate_win_rate(trade_analysis),
            "profit_factor": self._calculate_profit_factor(trade_analysis),
            "win_count": won.get('total', 0) if isinstance(won, dict) else (won if isinstance(won, int) else 0),
            "loss_count": lost.get('total', 0) if isinstance(lost, dict) else (lost if isinstance(lost, int) else 0),
            "avg_win": won.get('pnl', {}).get('average', 0.0) if isinstance(won, dict) else 0.0,
            "avg_loss": lost.get('pnl', {}).get('average', 0.0) if isinstance(lost, dict) else 0.0,
            "cancelled": bool(self.should_cancel),
        }

        return metrics

    def _calculate_win_rate(self, trade_analysis):
        total = trade_analysis.get('total', {}).get('closed', 0)
        if total == 0:
            return 0.0
        won = trade_analysis.get('won', {})
        won_count = won if isinstance(won, int) else won.get('total', 0)
        return (won_count / total) * 100

    def _calculate_profit_factor(self, trade_analysis):
        won = trade_analysis.get('won', {})
        lost = trade_analysis.get('lost', {})
        won_pnl = won.get('pnl', {}).get('total', 0.0) if isinstance(won, dict) else 0.0
        lost_pnl = abs(lost.get('pnl', {}).get('total', 0.0)) if isinstance(lost, dict) else 0.0
        return 0.0 if lost_pnl == 0 and won_pnl == 0 else (999.0 if lost_pnl == 0 else won_pnl / lost_pnl)

    def _safe_max_drawdown(self, drawdown_info):
        max_block = drawdown_info.get('max')
        if not isinstance(max_block, dict):
            return 0.0
        max_dd = max_block.get('drawdown', 0.0)
        if max_dd is None:
            return 0.0
        try:
            val = float(max_dd)
            val = val if val == val else 0.0
            return min(val, 100.0)
        except (TypeError, ValueError):
            return 0.0
