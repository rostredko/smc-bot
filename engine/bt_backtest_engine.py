import backtrader as bt
import pandas as pd
import logging
import threading
from datetime import timezone
from typing import Dict, Any
from .base_engine import BaseEngine
from .data_loader import DataLoader
from .logger import get_logger

from .bt_analyzers import TradeListAnalyzer, EquityCurveAnalyzer
from .trade_metrics import build_closed_trade_metrics

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
            exchange_type=config.get("exchange_type", "future"),
            log_level=config.get("log_level", logging.INFO),
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

        ordered_timeframes = self._ordered_timeframes(timeframes)
        
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

        forced_final_close_count = self._append_forced_final_closes(strat)
        realized_final_capital = self._compute_realized_final_capital()
        if forced_final_close_count and self.equity_curve:
            self.equity_curve[-1]["equity"] = realized_final_capital

        sharpe = strat.analyzers.sharpe.get_analysis().get('sharperatio')
        if sharpe is None: sharpe = 0.0

        drawdown_info = strat.analyzers.drawdown.get_analysis()
        max_dd = self._safe_max_drawdown(drawdown_info)

        trade_metrics = build_closed_trade_metrics(
            initial_capital=self.cerebro.broker.startingcash,
            final_capital=realized_final_capital,
            closed_trades=self.closed_trades,
        )

        metrics = {
            "initial_capital": trade_metrics["initial_capital"],
            "final_capital": trade_metrics["final_capital"],
            "total_pnl": trade_metrics["total_pnl"],
            "sharpe_ratio": sharpe,
            "max_drawdown": max_dd,
            "total_trades": trade_metrics["total_trades"],
            "win_rate": trade_metrics["win_rate"],
            "profit_factor": trade_metrics["profit_factor"],
            "win_count": trade_metrics["win_count"],
            "loss_count": trade_metrics["loss_count"],
            "avg_win": trade_metrics["avg_win"],
            "avg_loss": trade_metrics["avg_loss"],
            "cancelled": bool(self.should_cancel),
            "forced_final_close_count": forced_final_close_count,
        }

        return metrics

    def _compute_realized_final_capital(self) -> float:
        return self.cerebro.broker.startingcash + sum(
            self._safe_float(trade.get("realized_pnl", 0.0))
            for trade in (self.closed_trades or [])
        )

    def _append_forced_final_closes(self, strat) -> int:
        appended = 0
        seen_refs = {trade.get("id") for trade in self.closed_trades if trade.get("id") is not None}

        for trades_by_id in getattr(strat, "_trades", {}).values():
            for trade_list in trades_by_id.values():
                if not trade_list:
                    continue
                trade = trade_list[-1]
                if getattr(trade, "ref", None) in seen_refs:
                    continue
                if not getattr(trade, "isopen", False) or getattr(trade, "isclosed", False):
                    continue

                forced_trade = self._build_forced_final_close_record(strat, trade)
                if forced_trade is None:
                    continue

                logger.warning(
                    "Backtest ended with open %s trade ref=%s. "
                    "Synthesizing forced final close at %.2f.",
                    forced_trade["direction"],
                    forced_trade["id"],
                    forced_trade["exit_price"],
                )
                self.closed_trades.append(forced_trade)
                seen_refs.add(forced_trade["id"])
                appended += 1

        return appended

    def _build_forced_final_close_record(self, strat, trade) -> Dict[str, Any] | None:
        data = getattr(trade, "data", None)
        if data is None and self.cerebro.datas:
            data = self.cerebro.datas[0]
        if data is None:
            return None

        try:
            last_close = float(data.close[0])
            entry_price = float(trade.price)
            raw_size = float(trade.size)
        except (TypeError, ValueError):
            return None
        if last_close <= 0 or entry_price <= 0 or raw_size == 0:
            return None

        size = abs(raw_size)
        direction = "LONG" if raw_size > 0 else "SHORT"
        slippage = self._resolve_slippage_perc()
        if direction == "LONG":
            exit_price = last_close * (1.0 - slippage)
            gross_pnl = (exit_price - entry_price) * size
        else:
            exit_price = last_close * (1.0 + slippage)
            gross_pnl = (entry_price - exit_price) * size

        commission_rate = self._safe_float(self.config.get("commission", 0.0004))
        close_commission = size * exit_price * commission_rate
        open_commission = max(0.0, self._safe_float(getattr(trade, "pnl", 0.0)) - self._safe_float(getattr(trade, "pnlcomm", 0.0)))
        gross_realized_pnl = gross_pnl - open_commission - close_commission

        funding_adjustment = self._safe_float(getattr(strat, "_open_trade_funding_adjustment", 0.0))
        realized_pnl = gross_realized_pnl + funding_adjustment

        entry_dt = bt.num2date(trade.dtopen)
        if entry_dt.tzinfo is None:
            entry_dt = entry_dt.replace(tzinfo=timezone.utc)
        else:
            entry_dt = entry_dt.astimezone(timezone.utc)

        exit_dt = data.datetime.datetime(0)
        if exit_dt.tzinfo is None:
            exit_dt = exit_dt.replace(tzinfo=timezone.utc)
        else:
            exit_dt = exit_dt.astimezone(timezone.utc)

        info = dict(getattr(strat, "trade_map", {}).get(trade.ref, {}) or {})
        exit_reason = "Forced Final Close"
        exit_context = None
        if hasattr(strat, "_build_exit_context"):
            exit_context = strat._build_exit_context(exit_reason)

        record = {
            "id": trade.ref,
            "direction": direction,
            "entry_price": entry_price,
            "entry_time": entry_dt.isoformat().replace("+00:00", "Z"),
            "exit_time": exit_dt.isoformat().replace("+00:00", "Z"),
            "duration": str(exit_dt - entry_dt),
            "exit_price": exit_price,
            "size": size,
            "realized_pnl": realized_pnl,
            "gross_realized_pnl": gross_realized_pnl,
            "funding_adjustment": funding_adjustment,
            "commission": open_commission + close_commission,
            "reason": info.get("reason", "Signal"),
            "exit_reason": exit_reason,
            "narrative": (
                f"Backtest reached the final bar with an open {direction} position. "
                f"The position was force-closed at {exit_price:.2f} to keep results fully realized."
            ),
            "stop_loss": info.get("stop_loss", 0.0),
            "take_profit": info.get("take_profit", 0.0),
            "sl_calculation": info.get("sl_calculation"),
            "tp_calculation": info.get("tp_calculation"),
            "entry_context": info.get("entry_context"),
            "sl_history": list(getattr(strat, "sl_history", []) or info.get("sl_history", [])),
        }
        if exit_context is not None:
            record["exit_context"] = exit_context
        return record

    def _resolve_slippage_perc(self) -> float:
        slip_perc = self._safe_float(self.config.get("slippage_perc", 0.0))
        if slip_perc > 0:
            return slip_perc
        return self._safe_float(self.config.get("slippage_bps", 0.0)) / 10000.0

    @staticmethod
    def _safe_float(value):
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

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
