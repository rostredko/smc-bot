import backtrader as bt
from .helpers.narrative_generator import TradeNarrator
from .helpers.risk_manager import RiskManager
from engine.logger import get_logger

logger = get_logger(__name__)

class BaseStrategy(bt.Strategy):
    """
    Base class for all strategies.
    Handles common functionality:
    - Order management (logging, tracking)
    - Trade reporting (PnL, Narrative generation)
    - Helper initialization
    """
    
    params = (
        ('risk_reward_ratio', 2.0),
        ('risk_per_trade', 1.0),
        ('leverage', 1.0),
        ('dynamic_position_sizing', True),
    )

    def __init__(self):
        super().__init__()
        
        self.order = None
        self.stop_order = None
        self.tp_order = None
        self.trade_map = {}
        self.pending_metadata = None
        self.initial_sl = None
        self.cancel_reason = None
        self.stop_reason = "Stop Loss"
        self.last_exit_reason = "Unknown"
        self.trade_id_map = {}
        self.next_trade_id = 1
        self.sl_history = []
        self.narrator = TradeNarrator(self.params.risk_reward_ratio)

    def _calculate_position_size(self, entry_price, stop_loss):
        """
        Delegate to RiskManager.
        """
        return RiskManager.calculate_position_size(
            account_value=self.broker.get_value(),
            risk_per_trade_pct=self.params.risk_per_trade,
            entry_price=entry_price,
            stop_loss=stop_loss,
            leverage=self.params.leverage,
            dynamic_sizing=self.params.dynamic_position_sizing
        )

    def get_trade_info(self, trade_ref):
        return self.trade_map.get(trade_ref, {})

    def notify_order(self, order):
        if order.status in (order.Submitted, order.Accepted):
            return

        if order.status == order.Completed:
            dt_str = self.data.datetime.date(0).isoformat()
            if order.isbuy():
                logger.info(f"[{dt_str}] BUY EXECUTED, Price: {order.executed.price:.2f}, Cost: {order.executed.value:.2f}, Comm {order.executed.comm:.2f}")
            elif order.issell():
                logger.info(f"[{dt_str}] SELL EXECUTED, Price: {order.executed.price:.2f}, Cost: {order.executed.value:.2f}, Comm {order.executed.comm:.2f}")
            
            if isinstance(self.order, list):
                 self.order = self.order[0]

            if order == self.order:
                 self.order = None

            is_stop_order = (self.stop_order and order.ref == self.stop_order.ref)
            is_tp_order = (self.tp_order and order.ref == self.tp_order.ref)
            
            if is_stop_order:
                self.last_exit_reason = self.stop_reason
                logger.info(f"[{dt_str}] EXIT TRIGGERED by {self.stop_reason} (Price: {order.executed.price:.2f})")
                if self.tp_order:
                    self.cancel(self.tp_order)
                    self.tp_order = None
                self.stop_order = None
                    
            elif is_tp_order:
                self.last_exit_reason = "Take Profit"
                logger.info(f"[{dt_str}] EXIT TRIGGERED by Take Profit (Price: {order.executed.price:.2f})")
                if self.stop_order:
                    self.cancel(self.stop_order)
                    self.stop_order = None
                self.tp_order = None

        elif order.status in (order.Canceled, order.Margin, order.Rejected):
            dt_str = self.data.datetime.date(0).isoformat()
            info_str = f" Info: {order.info}" if order.info else ""
            if order.status == order.Canceled:
                self.cancel_reason = None
            elif order.status == order.Margin:
                logger.warning(f"[{dt_str}] ⛔ ORDER MARGIN ERROR - Insufficient Cash?{info_str}")
            else:
                logger.warning(f"[{dt_str}] ⛔ ORDER REJECTED {info_str}")
            
            if order == self.stop_order:
                self.stop_order = None

    def notify_trade(self, trade):
        if trade.justopened:
            current_size = abs(trade.size)
            if self.pending_metadata:
                self.pending_metadata['size'] = current_size
                if hasattr(self, 'get_execution_bar_indicators') and callable(getattr(self, 'get_execution_bar_indicators')):
                    exec_inds = self.get_execution_bar_indicators()
                    if exec_inds:
                        self.pending_metadata['execution_bar_indicators'] = exec_inds
                self.trade_map[trade.ref] = self.pending_metadata
                self.pending_metadata = None
            else:
                logger.error(f"CRITICAL: Trade {trade.ref} opened WITHOUT metadata! Pending is None.")
                self.trade_map[trade.ref] = {'size': current_size} 
        
        elif trade.isclosed:
            pnl = trade.pnl
            pnl_comm = trade.pnlcomm
            duration = (trade.dtclose - trade.dtopen)
            
            entry_price = trade.price
            pnl_pct = 0.0
            
            stored_info = self.trade_map.get(trade.ref, {})
            size = stored_info.get('size', 0)
            if size == 0 and len(trade.history) > 0:
                 size = trade.history[0].event.size

            if entry_price > 0 and size != 0:
                 raw_move = pnl / size
                 pnl_pct = (raw_move / entry_price) * 100
            
            if trade.ref not in self.trade_id_map:
                self.trade_id_map[trade.ref] = self.next_trade_id
                self.next_trade_id += 1
            
            local_trade_id = self.trade_id_map[trade.ref]
            
            logger.info(f"🔴 TRADE CLOSED [#{local_trade_id}]: PnL: {pnl:.2f} ({pnl_pct:.2f}%) | Net: {pnl_comm:.2f} | Reason: {self.last_exit_reason} | Duration: {duration}")
            narrative = self.narrator.generate_narrative(
                trade=trade,
                exit_reason=self.last_exit_reason,
                stored_info=self.trade_map.get(trade.ref, {}),
                sl_history=self.sl_history
            )
            
            exit_context = None
            if hasattr(self, '_build_exit_context'):
                exit_context = self._build_exit_context(self.last_exit_reason)

            if trade.ref in self.trade_map:
                self.trade_map[trade.ref]['exit_reason'] = self.last_exit_reason
                self.trade_map[trade.ref]['narrative'] = narrative
                self.trade_map[trade.ref]['sl_history'] = self.sl_history[:]
                if exit_context is not None:
                    self.trade_map[trade.ref]['exit_context'] = exit_context
            else:
                rec = {
                    'exit_reason': self.last_exit_reason,
                    'narrative': narrative,
                    'sl_history': self.sl_history[:]
                }
                if exit_context is not None:
                    rec['exit_context'] = exit_context
                self.trade_map[trade.ref] = rec
