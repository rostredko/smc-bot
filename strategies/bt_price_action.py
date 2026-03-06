import datetime
import backtrader as bt
from .base_strategy import BaseStrategy
from engine.logger import get_logger

logger = get_logger(__name__)


def _iso_utc(dt: datetime.datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    else:
        dt = dt.astimezone(datetime.timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")

class PriceActionStrategy(BaseStrategy):
    params = (
        ('min_range_factor', 1.2),
        ('min_wick_to_range', 0.6),
        ('max_body_to_range', 0.3),
        ('risk_reward_ratio', 2.0),
        ('sl_buffer_atr', 1.5),
        ('atr_period', 14),
        ('use_trend_filter', True),
        ('trend_ema_period', 200),
        ('use_rsi_filter', True),
        ('rsi_period', 14),
        ('rsi_overbought', 70),
        ('rsi_oversold', 30),
        ('use_rsi_momentum', False),
        ('rsi_momentum_threshold', 60),
        ('use_adx_filter', True),
        ('adx_period', 14),
        ('adx_threshold', 30),
        ('trailing_stop_distance', 0.0),
        ('breakeven_trigger_r', 0.0),
        ('risk_per_trade', 1.0),
        ('leverage', 1.0),
        ('dynamic_position_sizing', True),
        ('max_drawdown', 50.0),
        ('position_cap_adverse', 0.5),
        ('pattern_hammer', True),
        ('pattern_inverted_hammer', True),
        ('pattern_shooting_star', True),
        ('pattern_hanging_man', True),
        ('pattern_bullish_engulfing', True),
        ('pattern_bearish_engulfing', True),
        ('force_signal_every_n_bars', 0),
    )

    def __init__(self):
        super().__init__()
        self.has_secondary = len(self.datas) > 1

        if self.has_secondary:
            self.data_ltf = self.datas[0]
            self.data_htf = self.datas[1]
        else:
            self.data_htf = self.datas[0]
            self.data_ltf = self.datas[0]

        self.ema_htf = bt.talib.EMA(self.data_htf.close, timeperiod=self.params.trend_ema_period)
        self.rsi = bt.talib.RSI(self.data_ltf.close, timeperiod=self.params.rsi_period)
        self.atr = bt.talib.ATR(self.data_ltf.high, self.data_ltf.low, self.data_ltf.close, timeperiod=self.params.atr_period)
        self.adx = bt.talib.ADX(self.data_ltf.high, self.data_ltf.low, self.data_ltf.close, timeperiod=self.params.adx_period)
        self.cdl_engulfing = bt.talib.CDLENGULFING(self.data_ltf.open, self.data_ltf.high, self.data_ltf.low, self.data_ltf.close)
        self.cdl_hammer = bt.talib.CDLHAMMER(self.data_ltf.open, self.data_ltf.high, self.data_ltf.low, self.data_ltf.close)
        self.cdl_invertedhammer = bt.talib.CDLINVERTEDHAMMER(self.data_ltf.open, self.data_ltf.high, self.data_ltf.low, self.data_ltf.close)
        self.cdl_shootingstar = bt.talib.CDLSHOOTINGSTAR(self.data_ltf.open, self.data_ltf.high, self.data_ltf.low, self.data_ltf.close)
        self.cdl_hangingman = bt.talib.CDLHANGINGMAN(self.data_ltf.open, self.data_ltf.high, self.data_ltf.low, self.data_ltf.close)
        self.open_line = self.data_ltf.open
        self.high_line = self.data_ltf.high
        self.low_line = self.data_ltf.low
        self.close_line = self.data_ltf.close
        self.last_entry_bar = -1

    def get_execution_bar_indicators(self):
        ind = {}
        if self.params.use_rsi_filter or self.params.use_rsi_momentum:
            ind['RSI'] = round(self.rsi[0], 1)
        if self.params.use_adx_filter:
            ind['ADX'] = round(self.adx[0], 1)
        return ind if ind else None

    def next(self):
        if getattr(self, '_close_orphan_position', False):
            self._close_orphan_position = False
            if self.position:
                self.close()
                return
        if self._oco_closed and not self.position:
            self._oco_closed = False
        if self.order:
            return

        self._update_equity_peak()

        if not self.position:
            self.initial_sl = None

        if getattr(self, '_dd_limit_hit', False):
            return

        max_dd = self.params.max_drawdown
        if max_dd is not None and max_dd > 0 and self._equity_peak > 0:
            current = self.broker.getvalue()
            dd_pct = 100.0 * (self._equity_peak - current) / self._equity_peak
            if dd_pct > max_dd:
                if not getattr(self, '_dd_limit_hit', False):
                    dt_str = self._get_local_dt_str(self.data_ltf.datetime.datetime(0))
                    if self.params.stop_on_drawdown:
                        logger.warning(f"[{dt_str}] CRITICAL: Drawdown {dd_pct:.2f}% exceeded limit {max_dd}%. Stopping trading.")
                        self._dd_limit_hit = True
                        if self.position:
                            self._dd_close_order = self.close()
                        else:
                            self._dd_stop_runstop()
                    else:
                        logger.warning(f"[{dt_str}] Drawdown {dd_pct:.2f}% exceeded limit {max_dd}% (stop_on_drawdown=False).")
                if self.params.stop_on_drawdown:
                    return

        entry_bar = getattr(self, '_entry_exec_bar', -1)
        entry_data = getattr(self, '_entry_exec_data', None)
        bar_ok = entry_data is None or len(entry_data) > entry_bar
        stop_accepted = self.stop_order and self.stop_order.status == bt.Order.Accepted
        tp_ok = self.tp_order is None or self.tp_order.status == bt.Order.Accepted

        if self.position and self.stop_order and bar_ok and stop_accepted and tp_ok:
             current_sl = self.stop_order.price
             new_sl = current_sl
             sl_changed = False
             new_reason = self.stop_reason

             if self.params.breakeven_trigger_r > 0 and self.initial_sl is not None:
                 risk = abs(self.position.price - self.initial_sl)
                 if risk > 0:
                     profit = 0
                     if self.position.size > 0:
                         profit = self.close_line[0] - self.position.price
                     else:
                         profit = self.position.price - self.close_line[0]
                     
                     if profit >= (risk * self.params.breakeven_trigger_r):
                         be_price = self.position.price
                         if self.position.size > 0 and be_price > new_sl:
                             new_sl = be_price
                             sl_changed = True
                             new_reason = "Breakeven"
                             self.initial_sl = None
                         elif self.position.size < 0 and be_price < new_sl:
                             new_sl = be_price
                             sl_changed = True
                             new_reason = "Breakeven"
                             self.initial_sl = None

             if self.params.trailing_stop_distance > 0:
                 if self.position.size > 0:
                    dist = self.close_line[0] * self.params.trailing_stop_distance
                    trail_price = self.close_line[0] - dist
                    if trail_price > new_sl:
                        new_sl = trail_price
                        sl_changed = True
                        new_reason = "Trailing Stop"

                 elif self.position.size < 0:
                    dist = self.close_line[0] * self.params.trailing_stop_distance
                    trail_price = self.close_line[0] + dist
                    if trail_price < new_sl:
                        new_sl = trail_price
                        sl_changed = True
                        new_reason = "Trailing Stop"

             if sl_changed:
                 dt_str = self._get_local_dt_str(self.data_ltf.datetime.datetime(0))
                 logger.info(f"[{dt_str}] STOP UPDATE: {new_reason} -> {new_sl:.2f}")
                 self.cancel_reason = f"{new_reason} Update"
                 
                 tp_price_val = None
                 if self.tp_order:
                     tp_price_val = self.tp_order.price
                     self.cancel(self.tp_order)
                     self.tp_order = None
                     
                 self.cancel(self.stop_order)
                 self.stop_reason = new_reason
                 
                 self.sl_history.append({
                     'time': _iso_utc(self.data_ltf.datetime.datetime(0)),
                     'price': new_sl,
                     'reason': new_reason
                 })

                 if self.position.size > 0:
                     if tp_price_val is not None:
                         self.stop_order = self.sell(price=new_sl, exectype=bt.Order.Stop, size=self.position.size)
                         self.tp_order = self.sell(price=tp_price_val, exectype=bt.Order.Limit, size=self.position.size, oco=self.stop_order)
                     else:
                         self.stop_order = self.sell(price=new_sl, exectype=bt.Order.Stop, size=self.position.size)
                 else:
                     if tp_price_val is not None:
                         self.stop_order = self.buy(price=new_sl, exectype=bt.Order.Stop, size=abs(self.position.size))
                         self.tp_order = self.buy(price=tp_price_val, exectype=bt.Order.Limit, size=abs(self.position.size), oco=self.stop_order)
                     else:
                         self.stop_order = self.buy(price=new_sl, exectype=bt.Order.Stop, size=abs(self.position.size))

        if self.position:
            return

        if self.data_ltf.islive():
            import datetime
            bar_dt = self.data_ltf.datetime.datetime(0)
            now_dt = datetime.datetime.utcnow()

            if len(self.data_ltf) >= 2:
                prev_dt = self.data_ltf.datetime.datetime(-1)
                bar_period_secs = max(60, (bar_dt - prev_dt).total_seconds())
            else:
                bar_period_secs = 60
            max_age_secs = bar_period_secs * 2
            age_secs = (now_dt - bar_dt).total_seconds()
            if age_secs > max_age_secs:
                return

            if not getattr(self, '_warmup_finished', False):
                self._warmup_finished = True
                dt_str = self._get_local_dt_str(bar_dt)
                logger.info(f"[{dt_str}] 🚀 WARM-UP COMPLETE. NOW RUNNING LIVE PAPER TRADING...")

        if self.params.force_signal_every_n_bars > 0:
            bar_num = len(self.data_ltf)
            if bar_num % self.params.force_signal_every_n_bars == 0:
                if not self.position and not self.order:
                    if bar_num % (self.params.force_signal_every_n_bars * 2) == 0:
                        self._enter_long("Force-Test LONG")
                    else:
                        self._enter_short("Force-Test SHORT")
            return

        if self._is_bullish_pinbar():
            if self._check_filters_long():
                self._enter_long("Bullish Pinbar")
        elif self._is_bearish_pinbar():
            if self._check_filters_short():
                self._enter_short("Bearish Pinbar")
        elif self._is_bullish_engulfing():
            if self._check_filters_long():
                self._enter_long("Bullish Engulfing")
        elif self._is_bearish_engulfing():
            if self._check_filters_short():
                self._enter_short("Bearish Engulfing")

    def _build_entry_context(self, reason, direction):
        why_parts = [f"Pattern: {reason}"]
        indicators = {}
        indicators['ATR'] = round(self.atr[0], 4)

        if self.params.use_trend_filter:
            ema_val = self.ema_htf[0]
            indicators[f'EMA_{self.params.trend_ema_period}'] = round(ema_val, 2)
            if direction == 'long':
                why_parts.append(f"Trend: price above EMA{self.params.trend_ema_period} (${ema_val:,.2f})")
            else:
                why_parts.append(f"Trend: price below EMA{self.params.trend_ema_period} (${ema_val:,.2f})")

        if self.params.use_rsi_filter:
            rsi_val = self.rsi[0]
            indicators['RSI'] = round(rsi_val, 1)
            if direction == 'long':
                why_parts.append(f"RSI filter: {rsi_val:.1f} < overbought ({self.params.rsi_overbought})")
            else:
                why_parts.append(f"RSI filter: {rsi_val:.1f} > oversold ({self.params.rsi_oversold})")

        if self.params.use_rsi_momentum:
            rsi_val = self.rsi[0]
            if 'RSI' not in indicators:
                indicators['RSI'] = round(rsi_val, 1)
            if direction == 'long':
                why_parts.append(f"RSI momentum: {rsi_val:.1f} ≥ {self.params.rsi_momentum_threshold}")
            else:
                bearish_thresh = 100 - self.params.rsi_momentum_threshold
                why_parts.append(f"RSI momentum: {rsi_val:.1f} ≤ {bearish_thresh}")

        if self.params.use_adx_filter:
            adx_val = self.adx[0]
            indicators['ADX'] = round(adx_val, 1)
            why_parts.append(f"ADX: {adx_val:.1f} ≥ {self.params.adx_threshold} (trend strength)")

        return {
            'why_entry': why_parts,
            'indicators_at_entry': indicators
        }

    def _build_exit_context(self, exit_reason):
        if exit_reason == "Take Profit":
            why_parts = ["Exit: Take Profit — price reached the target level."]
        elif exit_reason == "Stop Loss":
            why_parts = ["Exit: Stop Loss — price hit the initial stop level."]
        elif exit_reason == "Trailing Stop":
            why_parts = ["Exit: Trailing Stop — price reversed and hit the trailing stop level."]
        elif exit_reason == "Breakeven":
            why_parts = ["Exit: Breakeven — price moved to breakeven, SL was moved to entry."]
        else:
            why_parts = [f"Exit: {exit_reason}"]

        indicators = {}
        indicators['ATR'] = round(self.atr[0], 4)

        if self.params.use_trend_filter:
            ema_val = self.ema_htf[0]
            indicators[f'EMA_{self.params.trend_ema_period}'] = round(ema_val, 2)
            why_parts.append(f"Trend (HTF): EMA{self.params.trend_ema_period} at ${ema_val:,.2f}")

        if self.params.use_rsi_filter or self.params.use_rsi_momentum:
            indicators['RSI'] = round(self.rsi[0], 1)
            why_parts.append(f"RSI at exit: {self.rsi[0]:.1f}")

        if self.params.use_adx_filter:
            indicators['ADX'] = round(self.adx[0], 1)
            why_parts.append(f"ADX at exit: {self.adx[0]:.1f}")

        return {
            'why_exit': why_parts,
            'indicators_at_exit': indicators
        }

    def _enter_long(self, reason):
        atr = self.atr[0]
        sl_buffer = atr * self.params.sl_buffer_atr
        sl_distance = self.close_line[0] - (self.low_line[0] - sl_buffer)
        sl_price_ref = self.close_line[0] - sl_distance
        tp_price_ref = self.close_line[0] + sl_distance * self.params.risk_reward_ratio
        self._place_entry(reason, 'long', sl_price_ref, tp_price_ref, sl_distance, sl_distance * self.params.risk_reward_ratio,
                         f"Low ({self.low_line[0]:.2f}) - (ATR * Buffer)", f"Entry + (Risk * RR)")

    def _enter_short(self, reason):
        atr = self.atr[0]
        sl_buffer = atr * self.params.sl_buffer_atr
        sl_distance = (self.high_line[0] + sl_buffer) - self.close_line[0]
        sl_price_ref = self.close_line[0] + sl_distance
        tp_price_ref = self.close_line[0] - sl_distance * self.params.risk_reward_ratio
        self._place_entry(reason, 'short', sl_price_ref, tp_price_ref, sl_distance, sl_distance * self.params.risk_reward_ratio,
                         f"High ({self.high_line[0]:.2f}) + (ATR * Buffer)", f"Entry - (Risk * RR)")

    def _place_entry(self, reason, direction, sl_price_ref, tp_price_ref, sl_distance, tp_distance, sl_calc_expr, tp_calc_expr):
        self.last_entry_bar = len(self.data_ltf)
        size = self._calculate_position_size(self.close_line[0], sl_price_ref, direction=direction)
        if size <= 0:
            logger.warning(f"[{self._get_local_dt_str(self.data_ltf.datetime.datetime(0))}] {direction.upper()} size is 0, skipping. SL: {sl_price_ref:.2f}")
            return
        dt_str = self._get_local_dt_str(self.data_ltf.datetime.datetime(0))
        logger.info(f"[{dt_str}] SIGNAL GENERATED: {direction.upper()} Entry={self.close_line[0]:.2f} SL={sl_price_ref:.2f} TP={tp_price_ref:.2f} Size={size:.4f} Reason={reason}")
        atr = self.atr[0]
        sl_calc = f"Math: {sl_calc_expr}\nResult: {sl_price_ref:.2f}\n---\nATR Period: {self.params.atr_period}"
        tp_calc = f"Math: {tp_calc_expr}\nResult: {tp_price_ref:.2f}\n---\nAdjusted to actual fill price on execution"
        self.pending_metadata = {
            'reason': reason, 'stop_loss': sl_price_ref, 'take_profit': tp_price_ref,
            'sl_distance': sl_distance, 'tp_distance': tp_distance, 'direction': direction, 'size': size,
            'sl_calculation': sl_calc, 'tp_calculation': tp_calc, 'entry_context': self._build_entry_context(reason, direction)
        }
        self.initial_sl = sl_price_ref
        self.stop_reason = "Stop Loss"
        self.sl_history = [{'time': _iso_utc(self.data_ltf.datetime.datetime(0)), 'price': sl_price_ref, 'reason': 'Initial Stop Loss'}]

        # Market order; SL/TP from exec_price in notify_order (OCO guard, Stop priority)
        if direction == 'long':
            self.order = self.buy(size=size, exectype=bt.Order.Market)
        else:
            self.order = self.sell(size=size, exectype=bt.Order.Market)


    def _has_significant_range(self):
        rng = self.high_line[0] - self.low_line[0]
        return rng >= (self.atr[0] * self.params.min_range_factor)

    def _meets_pinbar_wick_body_ratio(self, check_lower_wick: bool) -> bool:
        rng = self.high_line[0] - self.low_line[0]
        if rng <= 0:
            return False
        body = abs(self.close_line[0] - self.open_line[0])
        if body / rng > self.params.max_body_to_range:
            return False
        if check_lower_wick:
            lower_wick = min(self.open_line[0], self.close_line[0]) - self.low_line[0]
            return lower_wick / rng >= self.params.min_wick_to_range
        else:
            upper_wick = self.high_line[0] - max(self.open_line[0], self.close_line[0])
            return upper_wick / rng >= self.params.min_wick_to_range

    def _is_bullish_pinbar(self):
        if not self._has_significant_range():
            return False
        if self.params.pattern_hammer and self.cdl_hammer[0] == 100 and self._meets_pinbar_wick_body_ratio(check_lower_wick=True):
            return True
        if self.params.pattern_inverted_hammer and self.cdl_invertedhammer[0] == 100 and self._meets_pinbar_wick_body_ratio(check_lower_wick=False):
            return True
        return False

    def _is_bearish_pinbar(self):
        if not self._has_significant_range():
            return False
        if self.params.pattern_shooting_star and self.cdl_shootingstar[0] == -100 and self._meets_pinbar_wick_body_ratio(check_lower_wick=False):
            return True
        if self.params.pattern_hanging_man and self.cdl_hangingman[0] == -100 and self._meets_pinbar_wick_body_ratio(check_lower_wick=True):
            return True
        return False

    def _is_bullish_engulfing(self):
        return self.params.pattern_bullish_engulfing and self.cdl_engulfing[0] == 100 and self._has_significant_range()

    def _is_bearish_engulfing(self):
        return self.params.pattern_bearish_engulfing and self.cdl_engulfing[0] == -100 and self._has_significant_range()

    def _check_filters_long(self):
        if self.position or self.order:
            return False
        
        if self.params.use_trend_filter:
            if self.data_htf.close[0] < self.ema_htf[0]: return False
            
        if self.params.use_rsi_filter:
            if self.rsi[0] > self.params.rsi_overbought: return False

        if self.params.use_rsi_momentum:
            if self.rsi[0] < self.params.rsi_momentum_threshold: return False

        if self.params.use_adx_filter:
            if self.adx[0] < self.params.adx_threshold: return False
            
        return True

    def _check_filters_short(self):
        if self.position or self.order:
            return False
        if self.params.use_trend_filter:
             if self.data_htf.close[0] > self.ema_htf[0]: return False

        if self.params.use_rsi_filter:
            if self.rsi[0] < self.params.rsi_oversold: return False

        if self.params.use_rsi_momentum:
            bearish_threshold = 100 - self.params.rsi_momentum_threshold
            if self.rsi[0] > bearish_threshold: return False

        if self.params.use_adx_filter:
            if self.adx[0] < self.params.adx_threshold: return False
            
        return True
