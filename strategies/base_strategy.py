import datetime
import backtrader as bt
from .helpers.risk_manager import RiskManager
from engine.logger import get_logger
from engine.trade_narrator import TradeNarrator
from engine.optimize_context import (
    should_log_opt_progress,
    next_opt_combo,
    get_opt_total,
    get_current_combo,
    set_current_combo,
    clear_current_combo,
)

logger = get_logger(__name__)


class BaseStrategy(bt.Strategy):
    params = (
        ('risk_reward_ratio', 2.0),
        ('risk_per_trade', 1.0),
        ('leverage', 1.0),
        ('dynamic_position_sizing', True),
        ('max_drawdown', None),
        ('stop_on_drawdown', True),
        ('position_cap_adverse', 0.5),
        ('funding_rate_per_8h', 0.0),
        ('funding_interval_hours', 8),
    )

    def __init__(self):
        super().__init__()
        if should_log_opt_progress():
            n = next_opt_combo()
            total = get_opt_total()
            suffix = f"/{total}" if total else ""
            rr = getattr(self.params, "risk_reward_ratio", None)
            sl = getattr(self.params, "sl_buffer_atr", None)
            trail = getattr(self.params, "trailing_stop_distance", None)
            set_current_combo(n)
            logger.info(f"Opt combo {n}{suffix}: RR={rr} SLbuf={sl} Trail={trail}")
        self._equity_peak = self.broker.startingcash
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
        self._close_orphan_position = False
        self._oco_closed = False  # Set on first exit; reset in next() when no position
        self._entry_exec_bar = -1  # Bar index when entry filled; no trailing/breakeven on this bar
        self._entry_exec_data = None
        self._open_trade_funding_adjustment = 0.0
        self._next_funding_dt = None

    def stop(self):
        if should_log_opt_progress():
            n = get_current_combo() or 0
            total = get_opt_total()
            n_trades = len(self.trade_map)
            pnl = self.broker.getvalue() - self.broker.startingcash
            logger.info(f"Combo {n}/{total} done: {n_trades} trades, PnL: ${pnl:,.2f}")
            clear_current_combo()
        super().stop()

    def _cancel_all_exit_orders_for_data(self, data):
        """Hard cleanup: cancel all live exit orders for this data to prevent orphan orders."""
        orders = getattr(self.broker, "orders", None)
        if not orders:
            return
        for o in list(orders):
            if (
                o.owner == self
                and o.data == data
                and o.status in (o.Submitted, o.Accepted)
                and o.alive()
            ):
                try:
                    self.cancel(o)
                except Exception:
                    pass

    def _get_local_dt_str(self, dt=None):
        if dt is None:
            dt = self.data.datetime.datetime(0)
        return dt.replace(tzinfo=datetime.timezone.utc).astimezone().strftime('%Y-%m-%d %H:%M:%S')

    def _calculate_position_size(self, entry_price, stop_loss, direction=None):
        return RiskManager.calculate_position_size(
            account_value=self.broker.getvalue(),
            risk_per_trade_pct=self.params.risk_per_trade,
            entry_price=entry_price,
            stop_loss=stop_loss,
            leverage=self.params.leverage,
            dynamic_sizing=self.params.dynamic_position_sizing,
            max_drawdown_pct=self.params.max_drawdown,
            position_cap_adverse=getattr(self.params, 'position_cap_adverse', 0.5),
            direction=direction,
        )

    @staticmethod
    def _as_utc(dt):
        if dt.tzinfo is None:
            return dt.replace(tzinfo=datetime.timezone.utc)
        return dt.astimezone(datetime.timezone.utc)

    def _funding_interval_hours(self) -> int:
        try:
            hours = int(getattr(self.params, 'funding_interval_hours', 8))
        except (TypeError, ValueError):
            hours = 8
        return max(1, hours)

    def _next_funding_boundary(self, after_dt):
        dt_utc = self._as_utc(after_dt)
        interval_hours = self._funding_interval_hours()
        total_seconds = int(dt_utc.timestamp())
        interval_seconds = interval_hours * 60 * 60
        next_boundary = ((total_seconds // interval_seconds) + 1) * interval_seconds
        return datetime.datetime.fromtimestamp(next_boundary, tz=datetime.timezone.utc)

    def _apply_funding_adjustment(self, data, mark_price):
        try:
            funding_rate = float(getattr(self.params, 'funding_rate_per_8h', 0.0) or 0.0)
        except (TypeError, ValueError):
            funding_rate = 0.0

        if funding_rate == 0.0 or not self.position:
            return

        try:
            price = float(mark_price)
        except (TypeError, ValueError):
            return
        if price <= 0:
            return

        current_dt = self._as_utc(data.datetime.datetime(0))
        if self._next_funding_dt is None:
            self._next_funding_dt = self._next_funding_boundary(current_dt)
            return

        while current_dt >= self._next_funding_dt and self.position:
            notional = abs(float(self.position.size)) * price
            if notional <= 0:
                break
            side_sign = 1.0 if self.position.size > 0 else -1.0
            funding_cashflow = -(side_sign * funding_rate * notional)
            if funding_cashflow != 0.0:
                self.broker.add_cash(funding_cashflow)
                self._open_trade_funding_adjustment += funding_cashflow
                dt_str = self._get_local_dt_str(self._next_funding_dt)
                logger.info(
                    f"[{dt_str}] FUNDING {'CREDIT' if funding_cashflow > 0 else 'DEBIT'}: "
                    f"{funding_cashflow:.2f} on notional {notional:.2f} at rate {funding_rate:.6f}"
                )
            self._next_funding_dt += datetime.timedelta(hours=self._funding_interval_hours())

    @staticmethod
    def _format_signal_indicator_value(key, value):
        if value is None:
            return None
        if key == 'Structure':
            try:
                structure_value = float(value)
            except (TypeError, ValueError):
                return str(value)
            if structure_value > 0:
                return 'bullish'
            if structure_value < 0:
                return 'bearish'
            return 'neutral'
        return str(value)

    def _log_signal_thesis(
        self,
        dt_str,
        *,
        entry_context=None,
        sl_price_ref=None,
        tp_price_ref=None,
        sl_calc_expr=None,
        tp_calc_expr=None,
    ):
        context = entry_context or {}
        thought_lines = []

        why_parts = [part for part in (context.get('why_entry') or []) if part]
        if why_parts:
            trigger = why_parts[0]
            if trigger.startswith("Pattern: "):
                trigger = trigger[len("Pattern: "):]
            thought_lines.append(f"Trigger: {trigger}")
            if len(why_parts) > 1:
                thought_lines.append(f"Filters: {' | '.join(why_parts[1:])}")

        indicator_parts = []
        indicators = context.get('indicators_at_entry') or {}
        for key, value in indicators.items():
            formatted_value = self._format_signal_indicator_value(key, value)
            if formatted_value is None:
                continue
            indicator_parts.append(f"{key}={formatted_value}")
        if indicator_parts:
            thought_lines.append(f"Context: {' | '.join(indicator_parts)}")

        risk_parts = []
        if sl_price_ref is not None and sl_calc_expr:
            risk_parts.append(f"SL {sl_price_ref:.2f} via {sl_calc_expr}")
        if tp_price_ref is not None and tp_calc_expr:
            risk_parts.append(f"TP {tp_price_ref:.2f} via {tp_calc_expr}")
        if risk_parts:
            thought_lines.append(f"Risk plan: {' | '.join(risk_parts)}")

        for thought_line in thought_lines[:4]:
            logger.info(f"[{dt_str}] SIGNAL THESIS: {thought_line}")

    def _update_equity_peak(self):
        self._equity_peak = max(self._equity_peak, self.broker.getvalue())

    def _dd_stop_runstop(self):
        """Stop backtest early when drawdown limit hit (avoids iterating remaining bars)."""
        try:
            cerebro = getattr(self, 'cerebro', None)
            if cerebro and hasattr(cerebro, 'runstop'):
                cerebro.runstop()
                logger.info("Backtest stopped early (drawdown limit). Results will be saved.")
        except Exception:
            pass

    def _check_drawdown_after_trade(self):
        max_dd = self.params.max_drawdown
        if max_dd is None or max_dd <= 0:
            return
        current = self.broker.getvalue()
        self._equity_peak = max(self._equity_peak, current)
        if self._equity_peak <= 0:
            return
        dd_pct = 100.0 * (self._equity_peak - current) / self._equity_peak
        if dd_pct > max_dd:
            if not getattr(self, '_dd_limit_hit', False):
                dt_str = self._get_local_dt_str()
                if self.params.stop_on_drawdown:
                    logger.warning(
                        f"[{dt_str}] CRITICAL: Drawdown {dd_pct:.2f}% exceeded limit {max_dd}% "
                        "(detected on trade close). Stopping trading."
                    )
                    self._dd_limit_hit = True
                    self._dd_stop_runstop()
                else:
                    logger.warning(
                        f"[{dt_str}] Drawdown {dd_pct:.2f}% exceeded limit {max_dd}% "
                        "(stop_on_drawdown=False, continuing)."
                    )

    def get_trade_info(self, trade_ref):
        return self.trade_map.get(trade_ref, {})

    def notify_order(self, order):
        if isinstance(self.order, list):
            self.order = self.order[0] if self.order else None

        if order.status in (order.Submitted, order.Accepted):
            return

        if order.status == order.Completed:
            dt_str = self._get_local_dt_str()
            exec_price = order.executed.price

            if order.isbuy():
                logger.info(f"[{dt_str}] BUY EXECUTED, Price: {exec_price:.2f}, Cost: {order.executed.value:.2f}, Comm {order.executed.comm:.2f}")
            elif order.issell():
                logger.info(f"[{dt_str}] SELL EXECUTED, Price: {exec_price:.2f}, Cost: {order.executed.value:.2f}, Comm {order.executed.comm:.2f}")

            if order == self.order:
                self.order = None
                meta = self.pending_metadata or {}
                if self.stop_order and self.tp_order:
                    sl_p = getattr(self.stop_order, 'price', None) or meta.get('stop_loss', 0)
                    tp_p = getattr(self.tp_order, 'price', None) or meta.get('take_profit', 0)
                    logger.info(f"[{dt_str}] SL/TP SET (bracket): SL={sl_p:.2f} TP={tp_p:.2f}")
                    if self.pending_metadata:
                        self.pending_metadata['stop_loss'] = sl_p
                        self.pending_metadata['take_profit'] = tp_p
                        self.initial_sl = sl_p
                    self._entry_exec_bar = len(order.data)
                    self._entry_exec_data = order.data
                else:
                    sl_dist = meta.get('sl_distance')
                    tp_dist = meta.get('tp_distance')
                    direction = meta.get('direction')
                    size = abs(order.executed.size)
                    if sl_dist is not None and tp_dist is not None and direction and size > 0:
                        # Stop first, TP with oco=Stop — ambiguous bar: Stop has priority
                        if direction == 'long':
                            real_sl = exec_price - sl_dist
                            real_tp = exec_price + tp_dist
                            self.stop_order = self.sell(price=real_sl, exectype=bt.Order.Stop, size=size)
                            self.tp_order = self.sell(price=real_tp, exectype=bt.Order.Limit, size=size, oco=self.stop_order)
                        else:
                            real_sl = exec_price + sl_dist
                            real_tp = exec_price - tp_dist
                            self.stop_order = self.buy(price=real_sl, exectype=bt.Order.Stop, size=size)
                            self.tp_order = self.buy(price=real_tp, exectype=bt.Order.Limit, size=size, oco=self.stop_order)
                        dt_str = self._get_local_dt_str()
                        logger.info(f"[{dt_str}] SL/TP SET at fill price: SL={real_sl:.2f} TP={real_tp:.2f}")
                        if self.pending_metadata:
                            self.pending_metadata['stop_loss'] = real_sl
                            self.pending_metadata['take_profit'] = real_tp
                            self.initial_sl = real_sl
                        self._entry_exec_bar = len(order.data)
                        self._entry_exec_data = order.data
                return

            is_stop_order = (self.stop_order and order.ref == self.stop_order.ref)
            is_tp_order = (self.tp_order and order.ref == self.tp_order.ref)

            if is_stop_order:
                self.last_exit_reason = self.stop_reason
                logger.info(f"[{dt_str}] EXIT TRIGGERED by {self.stop_reason} (Price: {exec_price:.2f})")
                if self.tp_order:
                    self.cancel(self.tp_order)
                    self.tp_order = None
                self.stop_order = None
                self._oco_closed = True

            elif is_tp_order:
                self.last_exit_reason = "Take Profit"
                logger.info(f"[{dt_str}] EXIT TRIGGERED by Take Profit (Price: {exec_price:.2f})")
                if self.stop_order:
                    self.cancel(self.stop_order)
                    self.stop_order = None
                self.tp_order = None
                self._oco_closed = True

            dd_close = getattr(self, '_dd_close_order', None)
            if dd_close is not None and order.ref == dd_close.ref:
                self._dd_close_order = None
                self._dd_stop_runstop()

        elif order.status in (order.Canceled, order.Margin, order.Rejected):
            dt_str = self._get_local_dt_str()
            info_str = f" Info: {order.info}" if order.info else ""
            if order.status == order.Canceled:
                self.cancel_reason = None
            elif order.status == order.Margin:
                logger.warning(f"[{dt_str}] ⛔ ORDER MARGIN ERROR - Insufficient Cash?{info_str}")
                if order == self.order and self.params.max_drawdown and self.params.stop_on_drawdown:
                    self._dd_limit_hit = True
            else:
                logger.warning(f"[{dt_str}] ⛔ ORDER REJECTED {info_str}")

            if order == self.stop_order:
                self.stop_order = None
            elif order == self.tp_order:
                self.tp_order = None
            elif order == self.order:
                self.order = None


    def notify_trade(self, trade):
        if trade.justopened:
            current_size = abs(trade.size)
            self._open_trade_funding_adjustment = 0.0
            self._next_funding_dt = self._next_funding_boundary(bt.num2date(trade.dtopen))
            if self.pending_metadata:
                self.pending_metadata['size'] = current_size
                if hasattr(self, 'get_execution_bar_indicators') and callable(getattr(self, 'get_execution_bar_indicators')):
                    exec_inds = self.get_execution_bar_indicators()
                    if exec_inds:
                        self.pending_metadata['execution_bar_indicators'] = exec_inds
                self.trade_map[trade.ref] = self.pending_metadata
                self.pending_metadata = None
            else:
                logger.error(f"CRITICAL: Trade {trade.ref} opened WITHOUT metadata! Pending is None. Closing orphan position.")
                self.trade_map[trade.ref] = {'size': current_size}
                self._close_orphan_position = True 
        
        elif trade.isclosed:
            self._cancel_all_exit_orders_for_data(trade.data)
            self._check_drawdown_after_trade()

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
            
            dt_str = self._get_local_dt_str()
            logger.info(f"[{dt_str}] 🔴 TRADE CLOSED [#{local_trade_id}]: PnL: {pnl:.2f} ({pnl_pct:.2f}%) | Net: {pnl_comm:.2f} | Reason: {self.last_exit_reason} | Duration: {duration}")
            narrative = self.narrator.generate_narrative(
                trade=trade,
                exit_reason=self.last_exit_reason,
                stored_info=self.trade_map.get(trade.ref, {}),
                sl_history=self.sl_history
            )
            
            exit_context = None
            if hasattr(self, '_build_exit_context'):
                exit_context = self._build_exit_context(self.last_exit_reason)

            rec = self.trade_map.get(trade.ref, {})
            rec.update({
                'exit_reason': self.last_exit_reason,
                'narrative': narrative,
                'sl_history': self.sl_history[:],
                'funding_adjustment': self._open_trade_funding_adjustment,
            })
            if exit_context is not None:
                rec['exit_context'] = exit_context
            self.trade_map[trade.ref] = rec
            self._open_trade_funding_adjustment = 0.0
            self._next_funding_dt = None
