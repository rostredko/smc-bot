import threading
import queue
import backtrader as bt
from typing import Dict, Any

from .base_engine import BaseEngine
from .logger import get_logger
from .live_ws_client import BinanceWebsocketClient
from .live_data_feed import LiveWebSocketDataFeed
from .bt_analyzers import TradeListAnalyzer, EquityCurveAnalyzer
from .data_loader import DataLoader

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
        exchange_type = self.config.get("exchange_type", "future")
        exchange_name = self.config.get("exchange", "binance")
        queue_maxsize = int(self.config.get("live_queue_maxsize", 3000))
        
        # Consistent with backtest engine: lower timeframe first
        ordered_timeframes = list(reversed(timeframes)) if len(timeframes) > 1 else timeframes
        
        # Initialize DataLoader for history warm-up
        data_loader = DataLoader(exchange_name=exchange_name, exchange_type=exchange_type)
        
        for tf in ordered_timeframes:
            logger.info(f"Initializing Live WebSocket for {symbol} {tf}...")
            
            data_queue = queue.Queue(maxsize=max(100, queue_maxsize))
            
            # Fetch and seed historical warm-up data (e.g. 200 bars to cover SMA/EMA 200 periods)
            recent_bars = data_loader.fetch_recent_bars(symbol, tf, limit=200)
            for bar in recent_bars:
                data_queue.put(bar)
                
            # Start WS Client Thread
            ws_client = BinanceWebsocketClient(
                symbol=symbol,
                timeframe=tf,
                exchange_type=exchange_type,
                data_queue=data_queue,
                stop_event=self.stop_event
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
            # exactsync=True is important for live feeds with multiple datanames
            # It forces Cerebro to advance all feeds together if possible.
            results = self.cerebro.run(exactcells=True)
            
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

        trade_analysis = strat.analyzers.trades.get_analysis()
        won = trade_analysis.get('won', {})
        lost = trade_analysis.get('lost', {})
        
        total_closed = trade_analysis.get('total', {}).get('closed', 0)

        # Win rate logic
        win_rate = 0.0
        if total_closed > 0:
            won_dict = trade_analysis.get('won', {})
            won_count = won_dict if isinstance(won_dict, int) else won_dict.get('total', 0)
            win_rate = (won_count / total_closed) * 100

        # Profit factor logic (won/lost can be int when 0 in some Backtrader versions)
        won_raw = trade_analysis.get('won', {})
        lost_raw = trade_analysis.get('lost', {})
        won_pnl = won_raw.get('pnl', {}).get('total', 0.0) if isinstance(won_raw, dict) else 0.0
        lost_pnl = abs(lost_raw.get('pnl', {}).get('total', 0.0)) if isinstance(lost_raw, dict) else 0.0
        if lost_pnl == 0:
            profit_factor = 0.0 if won_pnl == 0 else 999.0
        else:
            profit_factor = won_pnl / lost_pnl

        return {
            "initial_capital": self.cerebro.broker.startingcash,
            "final_capital": self.cerebro.broker.getvalue(),
            "total_pnl": self.cerebro.broker.getvalue() - self.cerebro.broker.startingcash,
            "sharpe_ratio": sharpe,
            "max_drawdown": max_dd,
            "total_trades": total_closed,
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "win_count": won.get('total', 0) if isinstance(won, dict) else won,
            "loss_count": lost.get('total', 0) if isinstance(lost, dict) else lost,
            "avg_win": won.get('pnl', {}).get('average', 0.0) if isinstance(won, dict) else 0.0,
            "avg_loss": lost.get('pnl', {}).get('average', 0.0) if isinstance(lost, dict) else 0.0,
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
