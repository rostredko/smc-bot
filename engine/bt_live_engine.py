import threading
import queue
import logging
import backtrader as bt
from typing import Dict, Any

from .base_engine import BaseEngine
from .logger import get_logger
from .live_ws_client import (
    create_live_stream_client,
    normalize_live_exchange_name,
    normalize_live_exchange_type,
)
from .live_data_feed import LiveWebSocketDataFeed
from .bt_analyzers import TradeListAnalyzer, EquityCurveAnalyzer
from .data_loader import DataLoader
from .trade_metrics import build_closed_trade_metrics

logger = get_logger(__name__)


class _StopEventInjector(bt.Observer):
    """
    Cerebro observer that injects engine.stop_event into the strategy's
    _stop_event attribute on the very first bar. This allows strategies
    like FastTestStrategy to call stop_event.set() from notify_trade.
    """
    _stop_event = None  # set by BTLiveEngine before adding to cerebro

    lines = ('dummy',)  # observers must declare at least one line
    plotinfo = dict(plot=False)

    def next(self):
        strat = self._owner
        if hasattr(strat, '_stop_event') and strat._stop_event is None:
            strat._stop_event = self._stop_event


class BTLiveEngine(BaseEngine):
    """
    Concrete implementation of LiveEngine using Backtrader.
    Uses WebSocket data feed and built-in BackBroker to simulate paper trading.
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.stop_event = threading.Event()
        self.ws_clients = []
        self.closed_trades = []
        self.equity_curve = []
        self._stop_lock = threading.Lock()
        self._stop_called = False

    def add_data(self):
        """
        Initialize WS clients and Backtrader feeds for each timeframe.
        """
        symbol = self.config.get("symbol", "BTC/USDT")
        timeframes = self.config.get("timeframes", ["1h"])
        exchange_type = normalize_live_exchange_type(self.config.get("exchange_type", "future"))
        exchange_name = normalize_live_exchange_name(self.config.get("exchange", "binance"))
        queue_maxsize = int(self.config.get("live_queue_maxsize", 3000))
        
        # Keep data0=LTF and data1=HTF regardless of config array order.
        ordered_timeframes = self._ordered_timeframes(timeframes)
        
        # Initialize DataLoader for history warm-up
        data_loader = DataLoader(
            exchange_name=exchange_name,
            exchange_type=exchange_type,
            log_level=self.config.get("log_level", logging.INFO),
        )
        
        for tf in ordered_timeframes:
            logger.info("Initializing %s live market stream for %s %s...", exchange_name, symbol, tf)
            
            data_queue = queue.Queue(maxsize=max(100, queue_maxsize))
            
            # Fetch and seed historical warm-up data (e.g. 200 bars to cover SMA/EMA 200 periods)
            recent_bars = data_loader.fetch_recent_bars(symbol, tf, limit=200)
            for bar in recent_bars:
                data_queue.put(bar)
                
            ws_client = create_live_stream_client(
                exchange_name=exchange_name,
                symbol=symbol,
                timeframe=tf,
                exchange_type=exchange_type,
                data_queue=data_queue,
                stop_event=self.stop_event,
            )
            ws_client.start()
            self.ws_clients.append(ws_client)
            
            # Create Data Feed matching the WS Client's queue
            data_feed = LiveWebSocketDataFeed(
                dataname=f"{symbol}_{tf}",
                name=f"{symbol}_{tf}",
                q=data_queue,
                stop_event=self.stop_event,
                timeout=0.5
            )
            
            # Add to Cerebro
            self.cerebro.adddata(data_feed)

    def run_live(self):
        """
        Run the live trading session. 
        Will block until self.stop_event is set elsewhere (e.g. via API).
        """
        self.add_data()
        
        # Add Analyzers (same as backtest)
        self.cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe', riskfreerate=0.0, timeframe=bt.TimeFrame.Days, compression=1, factor=365)
        self.cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
        self.cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')
        self.cerebro.addanalyzer(bt.analyzers.SQN, _name='sqn')
        self.cerebro.addanalyzer(TradeListAnalyzer, _name='tradelist')
        self.cerebro.addanalyzer(EquityCurveAnalyzer, _name='equity')
        
        # Observer for live equity updates
        self.cerebro.addobserver(bt.observers.DrawDown)

        # Inject stop_event into FastTestStrategy (or any strategy with _stop_event)
        injector = _StopEventInjector
        injector._stop_event = self.stop_event
        self.cerebro.addobserver(injector)

        logger.info("Starting Backtrader Live (Paper) Trading engine...")
        try:
            # Use supported live-mode kwargs only; keep new multi-feed sync behavior.
            results = self.cerebro.run(live=True, oldsync=False)
            
            if not results:
                self.equity_curve = []
                return {}

            strat = results[0]
            self.strategy = strat

            # Capture closed trades and equity curve
            self.closed_trades = strat.analyzers.tradelist.get_analysis()
            self.equity_curve = strat.analyzers.equity.get_analysis()

            return self._format_metrics(strat)

        except Exception as e:
            logger.error(f"Live engine error: {e}", exc_info=True)
            return {}
        finally:
            self.stop() # Ensure resources are cleaned up

    def stop(self):
        """
        Signal the engine and all WS clients to stop gracefully.
        """
        with self._stop_lock:
            if self._stop_called:
                return
            self._stop_called = True

        logger.debug("Stopping BTLiveEngine...")
        try:
            if hasattr(self.cerebro, "runstop"):
                self.cerebro.runstop()
        except Exception as e:
            logger.debug(f"runstop() failed or unavailable: {e}")
        self.stop_event.set()

        ws_clients = list(self.ws_clients)
        self.ws_clients.clear()

        # Join WS Threads
        for ws in ws_clients:
            try:
                if hasattr(ws, "request_stop"):
                    ws.request_stop()
                # Use a small timeout to not block indefinitely in case of thread lock
                ws.join(timeout=2.0)
                if hasattr(ws, "is_alive") and ws.is_alive():
                    ws.join(timeout=1.0)
                if hasattr(ws, "is_alive") and ws.is_alive():
                    logger.debug(f"WS thread still alive after stop timeout: {getattr(ws, 'name', 'unknown')}")
            except Exception as e:
                logger.error(f"Error joining WS thread {ws.name}: {e}")

    def _format_metrics(self, strat) -> Dict[str, Any]:
        """Format analyzer results precisely like the backtest engine."""
        sharpe = strat.analyzers.sharpe.get_analysis().get('sharperatio')
        if sharpe is None: sharpe = 0.0

        drawdown_info = strat.analyzers.drawdown.get_analysis()
        max_dd = self._safe_max_drawdown(drawdown_info)

        trade_metrics = build_closed_trade_metrics(
            initial_capital=self.cerebro.broker.startingcash,
            final_capital=self.cerebro.broker.getvalue(),
            closed_trades=self.closed_trades,
        )

        return {
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
        }

    def _safe_max_drawdown(self, drawdown_info):
        """Extract max drawdown safely; handle None, NaN, missing keys.
        Cap at 100% — values >100% indicate negative equity (leverage/slippage)."""
        max_block = drawdown_info.get('max')
        if not isinstance(max_block, dict):
            return 0.0
        max_dd = max_block.get('drawdown', 0.0)
        if max_dd is None:
            return 0.0
        try:
            val = float(max_dd)
            val = val if val == val else 0.0  # NaN -> 0
            return min(val, 100.0)  # >100% = negative equity, cap for display
        except (TypeError, ValueError):
            return 0.0
