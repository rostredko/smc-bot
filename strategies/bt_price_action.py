import datetime
import math
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


class MarketStructure(bt.Indicator):
    lines = ('sh_level', 'sl_level', 'structure')
    params = (
        ('pivot_span', 2),
    )

    def __init__(self):
        super().__init__()
        self.addminperiod((self.params.pivot_span * 2) + 1)
        self._last_swing_high = None
        self._last_swing_low = None
        self._structure = 0

    @staticmethod
    def _is_pivot_high(data, span: int) -> bool:
        candidate = float(data.high[-span])
        for offset in range(1, span + 1):
            if candidate <= float(data.high[-span - offset]):
                return False
            if candidate <= float(data.high[-span + offset]):
                return False
        return True

    @staticmethod
    def _is_pivot_low(data, span: int) -> bool:
        candidate = float(data.low[-span])
        for offset in range(1, span + 1):
            if candidate >= float(data.low[-span - offset]):
                return False
            if candidate >= float(data.low[-span + offset]):
                return False
        return True

    def next(self):
        span = self.params.pivot_span

        if self._is_pivot_high(self.data, span):
            self._last_swing_high = float(self.data.high[-span])

        if self._is_pivot_low(self.data, span):
            self._last_swing_low = float(self.data.low[-span])

        close_val = float(self.data.close[0])
        if self._last_swing_high is not None and close_val > self._last_swing_high:
            self._structure = 1
        elif self._last_swing_low is not None and close_val < self._last_swing_low:
            self._structure = -1
        elif self._structure == 0:
            if self._last_swing_high is not None and self._last_swing_low is not None:
                midpoint = (self._last_swing_high + self._last_swing_low) / 2.0
                self._structure = 1 if close_val >= midpoint else -1
            elif self._last_swing_high is not None:
                self._structure = -1 if close_val < self._last_swing_high else 1
            elif self._last_swing_low is not None:
                self._structure = 1 if close_val > self._last_swing_low else -1

        self.lines.sh_level[0] = self._last_swing_high if self._last_swing_high is not None else float('nan')
        self.lines.sl_level[0] = self._last_swing_low if self._last_swing_low is not None else float('nan')
        self.lines.structure[0] = self._structure

class PriceActionStrategy(BaseStrategy):
    params = (
        ('min_range_factor', 1.2),
        ('min_wick_to_range', 0.6),
        ('max_body_to_range', 0.3),
        ('risk_reward_ratio', 2.0),
        ('sl_buffer_atr', 1.5),
        ('structural_sl_buffer_atr', 0.1),
        ('atr_period', 14),
        ('use_trend_filter', True),
        ('use_structure_filter', True),
        ('use_ema_filter', False),
        ('trend_ema_period', 200),
        ('market_structure_pivot_span', 2),
        ('poi_zone_upper_atr_mult', 0.3),
        ('poi_zone_lower_atr_mult', 0.2),
        ('use_ltf_choch_trigger', True),
        ('ltf_choch_entry_window_bars', 6),
        ('ltf_choch_arm_timeout_bars', 24),
        ('use_opposing_level_tp', False),
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

        self.ms_4h = MarketStructure(self.data_htf, pivot_span=self.params.market_structure_pivot_span)
        self.ms_1h = MarketStructure(self.data_ltf, pivot_span=self.params.market_structure_pivot_span)
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
        self._armed_long_choch_level = None
        self._armed_short_choch_level = None
        self._armed_long_bar = -1
        self._armed_short_bar = -1
        self._long_choch_trigger_bar = -1
        self._short_choch_trigger_bar = -1

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

        self._update_ltf_choch_state()

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

        if self.params.use_structure_filter:
            structure = self._get_structure_state()
            sh_level = self._to_valid_float(self.ms_4h.sh_level[0])
            sl_level = self._to_valid_float(self.ms_4h.sl_level[0])
            indicators['Structure'] = structure
            if sh_level is not None:
                indicators['SH_Level_4H'] = round(sh_level, 2)
            if sl_level is not None:
                indicators['SL_Level_4H'] = round(sl_level, 2)

            if direction == 'long':
                zone = self._get_poi_zone_long()
                if zone is not None:
                    zone_low, zone_high = zone
                    indicators['POI_Low'] = round(zone_low, 2)
                    indicators['POI_High'] = round(zone_high, 2)
                    why_parts.append(f"Structure: Bullish (state={structure}), POI [{zone_low:.2f}, {zone_high:.2f}]")
                else:
                    why_parts.append(f"Structure: Bullish (state={structure})")
                if self._bool_param('use_ltf_choch_trigger', True):
                    trigger_age = len(self.data_ltf) - self._long_choch_trigger_bar if self._long_choch_trigger_bar > 0 else None
                    if trigger_age is not None:
                        indicators['LTF_CHOCH_Age_Bars'] = trigger_age
                        why_parts.append(f"1H CHoCH confirmed {trigger_age} bar(s) ago")
            else:
                zone = self._get_poi_zone_short()
                if zone is not None:
                    zone_low, zone_high = zone
                    indicators['POI_Low'] = round(zone_low, 2)
                    indicators['POI_High'] = round(zone_high, 2)
                    why_parts.append(f"Structure: Bearish (state={structure}), POI [{zone_low:.2f}, {zone_high:.2f}]")
                else:
                    why_parts.append(f"Structure: Bearish (state={structure})")
                if self._bool_param('use_ltf_choch_trigger', True):
                    trigger_age = len(self.data_ltf) - self._short_choch_trigger_bar if self._short_choch_trigger_bar > 0 else None
                    if trigger_age is not None:
                        indicators['LTF_CHOCH_Age_Bars'] = trigger_age
                        why_parts.append(f"1H CHoCH confirmed {trigger_age} bar(s) ago")

        if self._is_ema_filter_enabled():
            ema_val = self.ema_htf[0]
            indicators[f'EMA_{self.params.trend_ema_period}'] = round(ema_val, 2)
            if direction == 'long':
                why_parts.append(f"EMA filter: HTF close above EMA{self.params.trend_ema_period} (${ema_val:,.2f})")
            else:
                why_parts.append(f"EMA filter: HTF close below EMA{self.params.trend_ema_period} (${ema_val:,.2f})")

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

        if self.params.use_structure_filter:
            structure = self._get_structure_state()
            indicators['Structure'] = structure
            sh_level = self._to_valid_float(self.ms_4h.sh_level[0])
            sl_level = self._to_valid_float(self.ms_4h.sl_level[0])
            if sh_level is not None:
                indicators['SH_Level_4H'] = round(sh_level, 2)
            if sl_level is not None:
                indicators['SL_Level_4H'] = round(sl_level, 2)
            why_parts.append(f"Structure (HTF): state={structure}")

        if self._is_ema_filter_enabled():
            ema_val = self.ema_htf[0]
            indicators[f'EMA_{self.params.trend_ema_period}'] = round(ema_val, 2)
            why_parts.append(f"EMA (HTF): EMA{self.params.trend_ema_period} at ${ema_val:,.2f}")

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
        entry_price = self.close_line[0]
        sl_price_ref, sl_distance, sl_calc_expr = self._resolve_structural_sl_long(entry_price)
        if sl_price_ref is None or sl_distance <= 0:
            return

        tp_price_ref, tp_distance, tp_calc_expr = self._resolve_tp_price(direction='long', entry_price=entry_price, sl_distance=sl_distance)
        if tp_price_ref is None or tp_distance <= 0:
            return

        self._place_entry(
            reason,
            'long',
            sl_price_ref,
            tp_price_ref,
            sl_distance,
            tp_distance,
            sl_calc_expr,
            tp_calc_expr,
        )

    def _enter_short(self, reason):
        entry_price = self.close_line[0]
        sl_price_ref, sl_distance, sl_calc_expr = self._resolve_structural_sl_short(entry_price)
        if sl_price_ref is None or sl_distance <= 0:
            return

        tp_price_ref, tp_distance, tp_calc_expr = self._resolve_tp_price(direction='short', entry_price=entry_price, sl_distance=sl_distance)
        if tp_price_ref is None or tp_distance <= 0:
            return

        self._place_entry(
            reason,
            'short',
            sl_price_ref,
            tp_price_ref,
            sl_distance,
            tp_distance,
            sl_calc_expr,
            tp_calc_expr,
        )

    @staticmethod
    def _to_valid_float(value):
        try:
            val = float(value)
        except (TypeError, ValueError):
            return None
        if math.isnan(val) or math.isinf(val):
            return None
        return val

    def _get_structure_state(self) -> int:
        structure_val = self._to_valid_float(self.ms_4h.structure[0])
        if structure_val is None:
            return 0
        if structure_val > 0:
            return 1
        if structure_val < 0:
            return -1
        return 0

    def _is_ema_filter_enabled(self) -> bool:
        return self._bool_param('use_trend_filter', False) or self._bool_param('use_ema_filter', False)

    def _bool_param(self, name: str, default: bool) -> bool:
        raw = getattr(self.params, name, default)
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, (int, float)):
            return bool(raw)
        if isinstance(raw, str):
            normalized = raw.strip().lower()
            if normalized in {'1', 'true', 'yes', 'on'}:
                return True
            if normalized in {'0', 'false', 'no', 'off'}:
                return False
            return default
        return default

    def _int_param(self, name: str, default: int, min_value: int = 0) -> int:
        raw = getattr(self.params, name, default)
        try:
            parsed = int(raw)
        except (TypeError, ValueError):
            parsed = default
        return max(min_value, parsed)

    def _reset_long_choch_state(self):
        self._armed_long_choch_level = None
        self._armed_long_bar = -1
        self._long_choch_trigger_bar = -1

    def _reset_short_choch_state(self):
        self._armed_short_choch_level = None
        self._armed_short_bar = -1
        self._short_choch_trigger_bar = -1

    def _consume_ltf_choch_trigger(self, direction: str):
        if direction == 'long':
            self._long_choch_trigger_bar = -1
        elif direction == 'short':
            self._short_choch_trigger_bar = -1

    def _has_valid_ltf_choch_trigger(self, direction: str) -> bool:
        if not self._bool_param('use_ltf_choch_trigger', True):
            return True

        bar_num = len(self.data_ltf)
        entry_window = self._int_param('ltf_choch_entry_window_bars', 6, min_value=1)
        trigger_bar = self._long_choch_trigger_bar if direction == 'long' else self._short_choch_trigger_bar
        return trigger_bar > 0 and (bar_num - trigger_bar) <= entry_window

    def _update_ltf_choch_state(self):
        if not self.params.use_structure_filter:
            self._reset_long_choch_state()
            self._reset_short_choch_state()
            return

        if not self._bool_param('use_ltf_choch_trigger', True):
            self._reset_long_choch_state()
            self._reset_short_choch_state()
            return

        bar_num = len(self.data_ltf)
        if bar_num < 2:
            return

        entry_window = self._int_param('ltf_choch_entry_window_bars', 6, min_value=1)
        arm_timeout = self._int_param('ltf_choch_arm_timeout_bars', 24, min_value=entry_window)

        curr_ltf_sh = self._to_valid_float(self.ms_1h.sh_level[0])
        curr_ltf_sl = self._to_valid_float(self.ms_1h.sl_level[0])
        prev_ltf_sh = self._to_valid_float(self.ms_1h.sh_level[-1])
        prev_ltf_sl = self._to_valid_float(self.ms_1h.sl_level[-1])

        new_ltf_swing_high = (
            curr_ltf_sh is not None and (prev_ltf_sh is None or not math.isclose(curr_ltf_sh, prev_ltf_sh, abs_tol=1e-9))
        )
        new_ltf_swing_low = (
            curr_ltf_sl is not None and (prev_ltf_sl is None or not math.isclose(curr_ltf_sl, prev_ltf_sl, abs_tol=1e-9))
        )

        structure = self._get_structure_state()
        close_price = self.close_line[0]

        if structure != 1:
            self._reset_long_choch_state()
        else:
            if self._is_price_inside_zone(self._get_poi_zone_long()) and new_ltf_swing_low and curr_ltf_sh is not None:
                self._armed_long_choch_level = curr_ltf_sh
                self._armed_long_bar = bar_num

            if self._armed_long_choch_level is not None and self._armed_long_bar > 0:
                if (bar_num - self._armed_long_bar) > arm_timeout:
                    self._armed_long_choch_level = None
                    self._armed_long_bar = -1
                elif close_price > self._armed_long_choch_level and bar_num > self._armed_long_bar:
                    self._long_choch_trigger_bar = bar_num
                    self._armed_long_choch_level = None
                    self._armed_long_bar = -1

        if structure != -1:
            self._reset_short_choch_state()
        else:
            if self._is_price_inside_zone(self._get_poi_zone_short()) and new_ltf_swing_high and curr_ltf_sl is not None:
                self._armed_short_choch_level = curr_ltf_sl
                self._armed_short_bar = bar_num

            if self._armed_short_choch_level is not None and self._armed_short_bar > 0:
                if (bar_num - self._armed_short_bar) > arm_timeout:
                    self._armed_short_choch_level = None
                    self._armed_short_bar = -1
                elif close_price < self._armed_short_choch_level and bar_num > self._armed_short_bar:
                    self._short_choch_trigger_bar = bar_num
                    self._armed_short_choch_level = None
                    self._armed_short_bar = -1

        if self._long_choch_trigger_bar > 0 and (bar_num - self._long_choch_trigger_bar) > entry_window:
            self._long_choch_trigger_bar = -1
        if self._short_choch_trigger_bar > 0 and (bar_num - self._short_choch_trigger_bar) > entry_window:
            self._short_choch_trigger_bar = -1

    def _get_poi_zone_long(self):
        sl_level = self._to_valid_float(self.ms_4h.sl_level[0])
        atr_val = self._to_valid_float(self.atr[0])
        if sl_level is None or atr_val is None or atr_val <= 0:
            return None
        zone_high = sl_level + (atr_val * self.params.poi_zone_upper_atr_mult)
        zone_low = sl_level - (atr_val * self.params.poi_zone_lower_atr_mult)
        return zone_low, zone_high

    def _get_poi_zone_short(self):
        sh_level = self._to_valid_float(self.ms_4h.sh_level[0])
        atr_val = self._to_valid_float(self.atr[0])
        if sh_level is None or atr_val is None or atr_val <= 0:
            return None
        zone_high = sh_level + (atr_val * self.params.poi_zone_upper_atr_mult)
        zone_low = sh_level - (atr_val * self.params.poi_zone_lower_atr_mult)
        return zone_low, zone_high

    def _is_price_inside_zone(self, zone) -> bool:
        if zone is None:
            return False
        close_price = self.close_line[0]
        zone_low, zone_high = zone
        return zone_low <= close_price <= zone_high

    def _resolve_structural_sl_long(self, entry_price: float):
        atr_val = self._to_valid_float(self.atr[0])
        if atr_val is None or atr_val <= 0:
            return None, 0.0, "Invalid ATR"

        sl_level = self._to_valid_float(self.ms_4h.sl_level[0])
        if sl_level is not None:
            sl_price_ref = sl_level - (atr_val * self.params.structural_sl_buffer_atr)
            if sl_price_ref < entry_price:
                sl_distance = entry_price - sl_price_ref
                sl_calc_expr = f"SL_Level_4H ({sl_level:.2f}) - (ATR * {self.params.structural_sl_buffer_atr})"
                return sl_price_ref, sl_distance, sl_calc_expr

        sl_buffer = atr_val * self.params.sl_buffer_atr
        sl_price_ref = self.low_line[0] - sl_buffer
        if sl_price_ref < entry_price:
            sl_distance = entry_price - sl_price_ref
            sl_calc_expr = f"Fallback: Low ({self.low_line[0]:.2f}) - (ATR * {self.params.sl_buffer_atr})"
            return sl_price_ref, sl_distance, sl_calc_expr
        return None, 0.0, "Unable to build valid long SL"

    def _resolve_structural_sl_short(self, entry_price: float):
        atr_val = self._to_valid_float(self.atr[0])
        if atr_val is None or atr_val <= 0:
            return None, 0.0, "Invalid ATR"

        sh_level = self._to_valid_float(self.ms_4h.sh_level[0])
        if sh_level is not None:
            sl_price_ref = sh_level + (atr_val * self.params.structural_sl_buffer_atr)
            if sl_price_ref > entry_price:
                sl_distance = sl_price_ref - entry_price
                sl_calc_expr = f"SH_Level_4H ({sh_level:.2f}) + (ATR * {self.params.structural_sl_buffer_atr})"
                return sl_price_ref, sl_distance, sl_calc_expr

        sl_buffer = atr_val * self.params.sl_buffer_atr
        sl_price_ref = self.high_line[0] + sl_buffer
        if sl_price_ref > entry_price:
            sl_distance = sl_price_ref - entry_price
            sl_calc_expr = f"Fallback: High ({self.high_line[0]:.2f}) + (ATR * {self.params.sl_buffer_atr})"
            return sl_price_ref, sl_distance, sl_calc_expr
        return None, 0.0, "Unable to build valid short SL"

    def _resolve_tp_price(self, direction: str, entry_price: float, sl_distance: float):
        rr_target = self.params.risk_reward_ratio
        if direction == 'long':
            tp_rr = entry_price + (sl_distance * rr_target)
            tp_price_ref = tp_rr
            tp_calc_expr = "Entry + (Risk * RR)"
            if self.params.use_opposing_level_tp:
                opposing_level = self._to_valid_float(self.ms_4h.sh_level[0])
                if opposing_level is not None and opposing_level > entry_price:
                    tp_price_ref = min(tp_rr, opposing_level)
                    tp_calc_expr = f"min(Entry + (Risk * RR), SH_Level_4H {opposing_level:.2f})"
            tp_distance = tp_price_ref - entry_price
        else:
            tp_rr = entry_price - (sl_distance * rr_target)
            tp_price_ref = tp_rr
            tp_calc_expr = "Entry - (Risk * RR)"
            if self.params.use_opposing_level_tp:
                opposing_level = self._to_valid_float(self.ms_4h.sl_level[0])
                if opposing_level is not None and opposing_level < entry_price:
                    tp_price_ref = max(tp_rr, opposing_level)
                    tp_calc_expr = f"max(Entry - (Risk * RR), SL_Level_4H {opposing_level:.2f})"
            tp_distance = entry_price - tp_price_ref
        if tp_distance <= 0:
            return None, 0.0, "Invalid TP distance"
        return tp_price_ref, tp_distance, tp_calc_expr

    def _place_entry(self, reason, direction, sl_price_ref, tp_price_ref, sl_distance, tp_distance, sl_calc_expr, tp_calc_expr):
        self.last_entry_bar = len(self.data_ltf)
        size = self._calculate_position_size(self.close_line[0], sl_price_ref, direction=direction)
        if size <= 0:
            logger.warning(f"[{self._get_local_dt_str(self.data_ltf.datetime.datetime(0))}] {direction.upper()} size is 0, skipping. SL: {sl_price_ref:.2f}")
            return
        dt_str = self._get_local_dt_str(self.data_ltf.datetime.datetime(0))
        logger.info(f"[{dt_str}] SIGNAL GENERATED: {direction.upper()} Entry={self.close_line[0]:.2f} SL={sl_price_ref:.2f} TP={tp_price_ref:.2f} Size={size:.4f} Reason={reason}")
        sl_calc = f"Math: {sl_calc_expr}\nResult: {sl_price_ref:.2f}\n---\nATR Period: {self.params.atr_period}"
        tp_calc = f"Math: {tp_calc_expr}\nResult: {tp_price_ref:.2f}\n---\nAdjusted to actual fill price on execution"
        self.pending_metadata = {
            'reason': reason, 'stop_loss': sl_price_ref, 'take_profit': tp_price_ref,
            'sl_distance': sl_distance, 'tp_distance': tp_distance, 'direction': direction, 'size': size,
            'sl_calculation': sl_calc, 'tp_calculation': tp_calc, 'entry_context': self._build_entry_context(reason, direction)
        }
        self._consume_ltf_choch_trigger(direction)
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

        if self.params.use_structure_filter:
            if self._get_structure_state() != 1:
                return False
            if self._bool_param('use_ltf_choch_trigger', True):
                if not self._has_valid_ltf_choch_trigger('long'):
                    return False
            elif not self._is_price_inside_zone(self._get_poi_zone_long()):
                return False

        if self._is_ema_filter_enabled():
            htf_close = self._to_valid_float(self.data_htf.close[0])
            ema_val = self._to_valid_float(self.ema_htf[0])
            if htf_close is None or ema_val is None or htf_close < ema_val:
                return False

        if self.params.use_rsi_filter:
            if self.rsi[0] > self.params.rsi_overbought:
                return False

        if self.params.use_rsi_momentum:
            if self.rsi[0] < self.params.rsi_momentum_threshold:
                return False

        if self.params.use_adx_filter:
            if self.adx[0] < self.params.adx_threshold:
                return False

        return True

    def _check_filters_short(self):
        if self.position or self.order:
            return False

        if self.params.use_structure_filter:
            if self._get_structure_state() != -1:
                return False
            if self._bool_param('use_ltf_choch_trigger', True):
                if not self._has_valid_ltf_choch_trigger('short'):
                    return False
            elif not self._is_price_inside_zone(self._get_poi_zone_short()):
                return False

        if self._is_ema_filter_enabled():
            htf_close = self._to_valid_float(self.data_htf.close[0])
            ema_val = self._to_valid_float(self.ema_htf[0])
            if htf_close is None or ema_val is None or htf_close > ema_val:
                return False

        if self.params.use_rsi_filter:
            if self.rsi[0] < self.params.rsi_oversold:
                return False

        if self.params.use_rsi_momentum:
            bearish_threshold = 100 - self.params.rsi_momentum_threshold
            if self.rsi[0] > bearish_threshold:
                return False

        if self.params.use_adx_filter:
            if self.adx[0] < self.params.adx_threshold:
                return False

        return True
