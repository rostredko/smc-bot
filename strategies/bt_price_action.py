import datetime
import math
import re
import backtrader as bt
from .base_strategy import BaseStrategy
from .market_structure import (
    advance_structure_state,
    is_confirmed_swing_high,
    is_confirmed_swing_low,
)
from engine.logger import get_logger

logger = get_logger(__name__)
_TIMEFRAME_TOKEN_RE = re.compile(r"(\d+[mhdw])", re.IGNORECASE)


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
        left_highs = [float(data.high[-span - offset]) for offset in range(1, span + 1)]
        right_highs = [float(data.high[-span + offset]) for offset in range(1, span + 1)]
        return is_confirmed_swing_high(candidate, left_highs, right_highs)

    @staticmethod
    def _is_pivot_low(data, span: int) -> bool:
        candidate = float(data.low[-span])
        left_lows = [float(data.low[-span - offset]) for offset in range(1, span + 1)]
        right_lows = [float(data.low[-span + offset]) for offset in range(1, span + 1)]
        return is_confirmed_swing_low(candidate, left_lows, right_lows)

    def next(self):
        span = self.params.pivot_span

        if self._is_pivot_high(self.data, span):
            self._last_swing_high = float(self.data.high[-span])

        if self._is_pivot_low(self.data, span):
            self._last_swing_low = float(self.data.low[-span])

        self._structure = advance_structure_state(
            close_value=float(self.data.close[0]),
            last_swing_high=self._last_swing_high,
            last_swing_low=self._last_swing_low,
            current_structure=self._structure,
        )

        self.lines.sh_level[0] = self._last_swing_high if self._last_swing_high is not None else float('nan')
        self.lines.sl_level[0] = self._last_swing_low if self._last_swing_low is not None else float('nan')
        self.lines.structure[0] = self._structure

class PriceActionStrategy(BaseStrategy):
    params = (
        ('min_range_factor', 1.2),
        ('min_wick_to_range', 0.6),
        ('max_body_to_range', 0.3),
        ('use_pinbar_quality_filter', False),
        ('pinbar_min_wick_to_body_ratio', 2.5),
        ('pinbar_max_opposite_wick_to_range', 0.2),
        ('pinbar_close_near_extreme_threshold', 0.65),
        ('use_engulfing_quality_filter', False),
        ('engulfing_min_body_to_range', 0.55),
        ('engulfing_min_body_to_atr', 0.35),
        ('engulfing_min_body_engulf_ratio', 1.0),
        ('engulfing_max_opposite_wick_to_range', 0.2),
        ('engulfing_require_close_through_prev_extreme', False),
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
        ('ltf_choch_max_pullaway_atr_mult', 1.5),
        ('use_premium_discount_filter', False),
        ('use_space_to_target_filter', False),
        ('space_to_target_min_rr', 1.0),
        ('use_choch_displacement_filter', False),
        ('choch_displacement_atr_mult', 1.5),
        ('require_choch_fvg', False),
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

    @staticmethod
    def _extract_timeframe_token(value) -> str | None:
        if not isinstance(value, str):
            return None
        matches = _TIMEFRAME_TOKEN_RE.findall(value)
        if not matches:
            return None
        return matches[-1].lower()

    @staticmethod
    def _seconds_to_timeframe_token(seconds: float) -> str | None:
        try:
            total_seconds = int(round(float(seconds)))
        except (TypeError, ValueError):
            return None
        if total_seconds <= 0:
            return None
        for unit, unit_seconds in (("w", 604800), ("d", 86400), ("h", 3600), ("m", 60)):
            if total_seconds % unit_seconds == 0:
                return f"{total_seconds // unit_seconds}{unit}"
        return None

    @classmethod
    def _detect_data_timeframe(cls, data, fallback: str) -> str:
        candidates = [
            getattr(data, "_name", None),
            getattr(getattr(data, "p", None), "name", None),
        ]
        dataname = getattr(getattr(data, "p", None), "dataname", None)
        if isinstance(dataname, str):
            candidates.append(dataname)

        for candidate in candidates:
            token = cls._extract_timeframe_token(candidate)
            if token:
                return token.upper()

        index = getattr(dataname, "index", None)
        if index is not None and len(index) >= 2:
            prev_dt = index[0]
            for curr_dt in index[1:]:
                try:
                    delta_seconds = (curr_dt - prev_dt).total_seconds()
                except Exception:
                    prev_dt = curr_dt
                    continue
                token = cls._seconds_to_timeframe_token(delta_seconds)
                if token:
                    return token.upper()
                prev_dt = curr_dt

        return fallback.upper()

    def _scoped_indicator_key(self, base: str, scope: str = "htf") -> str:
        label = self._htf_timeframe_label if scope == "htf" else self._ltf_timeframe_label
        return f"{base}_{label}"

    def __init__(self):
        super().__init__()
        self.has_secondary = len(self.datas) > 1

        if self.has_secondary:
            self.data_ltf = self.datas[0]
            self.data_htf = self.datas[1]
        else:
            self.data_htf = self.datas[0]
            self.data_ltf = self.datas[0]

        self._htf_timeframe_label = self._detect_data_timeframe(self.data_htf, fallback="HTF")
        self._ltf_timeframe_label = self._detect_data_timeframe(self.data_ltf, fallback="LTF")

        self.ms_htf = MarketStructure(self.data_htf, pivot_span=self.params.market_structure_pivot_span)
        self.ms_ltf = MarketStructure(self.data_ltf, pivot_span=self.params.market_structure_pivot_span)
        self.ema_htf = bt.talib.EMA(self.data_htf.close, timeperiod=self.params.trend_ema_period)
        self.rsi = bt.talib.RSI(self.data_ltf.close, timeperiod=self.params.rsi_period)
        self.atr = bt.talib.ATR(self.data_ltf.high, self.data_ltf.low, self.data_ltf.close, timeperiod=self.params.atr_period)
        self.atr_htf = bt.talib.ATR(self.data_htf.high, self.data_htf.low, self.data_htf.close, timeperiod=self.params.atr_period)
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
        self._long_choch_trigger_price = None
        self._short_choch_trigger_price = None
        self._long_choch_trigger_zone_ref = None
        self._short_choch_trigger_zone_ref = None
        self._long_choch_trigger_body_atr_ratio = None
        self._short_choch_trigger_body_atr_ratio = None
        self._long_choch_trigger_has_fvg = None
        self._short_choch_trigger_has_fvg = None

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
            self._apply_funding_adjustment(self.data_ltf, self.close_line[0])

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
        atr_htf_val = self._to_valid_float(self.atr_htf[0])
        if atr_htf_val is not None:
            indicators[self._scoped_indicator_key('ATR', scope='htf')] = round(atr_htf_val, 4)

        if self._bool_param('use_structure_filter', True):
            structure = self._get_structure_state()
            sh_level = self._to_valid_float(self.ms_htf.sh_level[0])
            sl_level = self._to_valid_float(self.ms_htf.sl_level[0])
            equilibrium = self._get_htf_equilibrium()
            space_metrics = self._get_space_to_target_metrics(direction, self.close_line[0])
            indicators['Structure'] = structure
            if sh_level is not None:
                indicators[self._scoped_indicator_key('SH_Level', scope='htf')] = round(sh_level, 2)
            if sl_level is not None:
                indicators[self._scoped_indicator_key('SL_Level', scope='htf')] = round(sl_level, 2)
            if equilibrium is not None:
                indicators['HTF_Equilibrium_0_5'] = round(equilibrium, 2)
            if space_metrics is not None:
                indicators['HTF_Space_R'] = round(space_metrics['available_rr'], 2)

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
                        body_atr_ratio, has_fvg = self._get_choch_trigger_quality('long')
                        indicators['LTF_CHOCH_Age_Bars'] = trigger_age
                        indicators['LTF_CHOCH_Trigger_Price'] = round(self._long_choch_trigger_price, 2) if self._long_choch_trigger_price is not None else None
                        if body_atr_ratio is not None:
                            indicators['LTF_CHOCH_Body_ATR'] = round(body_atr_ratio, 2)
                        if has_fvg is not None:
                            indicators['LTF_CHOCH_FVG'] = has_fvg
                        why_parts.append(f"{self._ltf_timeframe_label} CHoCH confirmed {trigger_age} bar(s) ago")
                        if body_atr_ratio is not None:
                            why_parts.append(f"{self._ltf_timeframe_label} CHoCH displacement: body {body_atr_ratio:.2f}x ATR")
                        if has_fvg is True:
                            why_parts.append(f"{self._ltf_timeframe_label} CHoCH left a bullish FVG")
                if self._bool_param('use_premium_discount_filter', False) and equilibrium is not None:
                    why_parts.append(f"Premium/Discount: entry {self.close_line[0]:.2f} is below EQ {equilibrium:.2f} (discount)")
                if self._bool_param('use_space_to_target_filter', False) and space_metrics is not None:
                    why_parts.append(
                        f"Space to target: {space_metrics['available_rr']:.2f}R available before "
                        f"{self._scoped_indicator_key('SH_Level', scope='htf')}"
                    )
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
                        body_atr_ratio, has_fvg = self._get_choch_trigger_quality('short')
                        indicators['LTF_CHOCH_Age_Bars'] = trigger_age
                        indicators['LTF_CHOCH_Trigger_Price'] = round(self._short_choch_trigger_price, 2) if self._short_choch_trigger_price is not None else None
                        if body_atr_ratio is not None:
                            indicators['LTF_CHOCH_Body_ATR'] = round(body_atr_ratio, 2)
                        if has_fvg is not None:
                            indicators['LTF_CHOCH_FVG'] = has_fvg
                        why_parts.append(f"{self._ltf_timeframe_label} CHoCH confirmed {trigger_age} bar(s) ago")
                        if body_atr_ratio is not None:
                            why_parts.append(f"{self._ltf_timeframe_label} CHoCH displacement: body {body_atr_ratio:.2f}x ATR")
                        if has_fvg is True:
                            why_parts.append(f"{self._ltf_timeframe_label} CHoCH left a bearish FVG")
                if self._bool_param('use_premium_discount_filter', False) and equilibrium is not None:
                    why_parts.append(f"Premium/Discount: entry {self.close_line[0]:.2f} is above EQ {equilibrium:.2f} (premium)")
                if self._bool_param('use_space_to_target_filter', False) and space_metrics is not None:
                    why_parts.append(
                        f"Space to target: {space_metrics['available_rr']:.2f}R available before "
                        f"{self._scoped_indicator_key('SL_Level', scope='htf')}"
                    )

        if self._is_ema_filter_enabled():
            ema_val = self.ema_htf[0]
            indicators[f'EMA_{self.params.trend_ema_period}'] = round(ema_val, 2)
            if direction == 'long':
                why_parts.append(f"EMA filter: HTF close above EMA{self.params.trend_ema_period} (${ema_val:,.2f})")
            else:
                why_parts.append(f"EMA filter: HTF close below EMA{self.params.trend_ema_period} (${ema_val:,.2f})")

        if self._bool_param('use_rsi_filter', False):
            rsi_val = self.rsi[0]
            indicators['RSI'] = round(rsi_val, 1)
            if direction == 'long':
                why_parts.append(f"RSI filter: {rsi_val:.1f} < overbought ({self.params.rsi_overbought})")
            else:
                why_parts.append(f"RSI filter: {rsi_val:.1f} > oversold ({self.params.rsi_oversold})")

        if self._bool_param('use_rsi_momentum', False):
            rsi_val = self.rsi[0]
            if 'RSI' not in indicators:
                indicators['RSI'] = round(rsi_val, 1)
            if direction == 'long':
                why_parts.append(f"RSI momentum: {rsi_val:.1f} ≥ {self.params.rsi_momentum_threshold}")
            else:
                bearish_thresh = 100 - self.params.rsi_momentum_threshold
                why_parts.append(f"RSI momentum: {rsi_val:.1f} ≤ {bearish_thresh}")

        if self._bool_param('use_adx_filter', False):
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

        if self._bool_param('use_structure_filter', True):
            structure = self._get_structure_state()
            indicators['Structure'] = structure
            sh_level = self._to_valid_float(self.ms_htf.sh_level[0])
            sl_level = self._to_valid_float(self.ms_htf.sl_level[0])
            if sh_level is not None:
                indicators[self._scoped_indicator_key('SH_Level', scope='htf')] = round(sh_level, 2)
            if sl_level is not None:
                indicators[self._scoped_indicator_key('SL_Level', scope='htf')] = round(sl_level, 2)
            why_parts.append(f"Structure (HTF): state={structure}")

        if self._is_ema_filter_enabled():
            ema_val = self.ema_htf[0]
            indicators[f'EMA_{self.params.trend_ema_period}'] = round(ema_val, 2)
            why_parts.append(f"EMA (HTF): EMA{self.params.trend_ema_period} at ${ema_val:,.2f}")

        if self._bool_param('use_rsi_filter', False) or self._bool_param('use_rsi_momentum', False):
            indicators['RSI'] = round(self.rsi[0], 1)
            why_parts.append(f"RSI at exit: {self.rsi[0]:.1f}")

        if self._bool_param('use_adx_filter', False):
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
        structure_val = self._to_valid_float(self.ms_htf.structure[0])
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

    def _float_param(self, name: str, default: float, min_value: float | None = None) -> float:
        raw = getattr(self.params, name, default)
        try:
            parsed = float(raw)
        except (TypeError, ValueError):
            parsed = default
        if min_value is not None:
            return max(min_value, parsed)
        return parsed

    def _reset_long_choch_state(self):
        self._armed_long_choch_level = None
        self._armed_long_bar = -1
        self._long_choch_trigger_bar = -1
        self._long_choch_trigger_price = None
        self._long_choch_trigger_zone_ref = None
        self._long_choch_trigger_body_atr_ratio = None
        self._long_choch_trigger_has_fvg = None

    def _reset_short_choch_state(self):
        self._armed_short_choch_level = None
        self._armed_short_bar = -1
        self._short_choch_trigger_bar = -1
        self._short_choch_trigger_price = None
        self._short_choch_trigger_zone_ref = None
        self._short_choch_trigger_body_atr_ratio = None
        self._short_choch_trigger_has_fvg = None

    def _consume_ltf_choch_trigger(self, direction: str):
        if direction == 'long':
            self._long_choch_trigger_bar = -1
            self._long_choch_trigger_price = None
            self._long_choch_trigger_zone_ref = None
            self._long_choch_trigger_body_atr_ratio = None
            self._long_choch_trigger_has_fvg = None
        elif direction == 'short':
            self._short_choch_trigger_bar = -1
            self._short_choch_trigger_price = None
            self._short_choch_trigger_zone_ref = None
            self._short_choch_trigger_body_atr_ratio = None
            self._short_choch_trigger_has_fvg = None

    def _get_choch_trigger_quality(self, direction: str):
        if direction == 'long':
            return self._long_choch_trigger_body_atr_ratio, self._long_choch_trigger_has_fvg
        return self._short_choch_trigger_body_atr_ratio, self._short_choch_trigger_has_fvg

    def _capture_choch_trigger_quality(self, direction: str):
        atr_val = self._to_valid_float(self.atr[0])
        body_size = abs(self.close_line[0] - self.open_line[0])
        body_atr_ratio = None
        if atr_val is not None and atr_val > 0:
            body_atr_ratio = body_size / atr_val
        has_fvg = self._detect_ltf_fvg(direction)
        if direction == 'long':
            self._long_choch_trigger_body_atr_ratio = body_atr_ratio
            self._long_choch_trigger_has_fvg = has_fvg
        else:
            self._short_choch_trigger_body_atr_ratio = body_atr_ratio
            self._short_choch_trigger_has_fvg = has_fvg

    def _detect_ltf_fvg(self, direction: str) -> bool:
        if len(self.data_ltf) < 3:
            return False

        if direction == 'long':
            prior_high = self._to_valid_float(self.high_line[-2])
            current_low = self._to_valid_float(self.low_line[0])
            if prior_high is None or current_low is None:
                return False
            return current_low > prior_high

        prior_low = self._to_valid_float(self.low_line[-2])
        current_high = self._to_valid_float(self.high_line[0])
        if prior_low is None or current_high is None:
            return False
        return current_high < prior_low

    def _get_htf_equilibrium(self):
        sh_level = self._to_valid_float(self.ms_htf.sh_level[0])
        sl_level = self._to_valid_float(self.ms_htf.sl_level[0])
        if sh_level is None or sl_level is None or sh_level <= sl_level:
            return None
        return (sh_level + sl_level) / 2.0

    def _passes_premium_discount_filter(self, direction: str) -> bool:
        if not self._bool_param('use_structure_filter', True):
            return True
        if not self._bool_param('use_premium_discount_filter', False):
            return True

        equilibrium = self._get_htf_equilibrium()
        if equilibrium is None:
            return False

        entry_price = self.close_line[0]
        if direction == 'long':
            return entry_price < equilibrium
        return entry_price > equilibrium

    def _get_space_to_target_metrics(self, direction: str, entry_price: float):
        if direction == 'long':
            opposing_level = self._to_valid_float(self.ms_htf.sh_level[0])
            _, risk, _ = self._resolve_structural_sl_long(entry_price)
            if opposing_level is None or opposing_level <= entry_price or risk <= 0:
                return None
            available_space = opposing_level - entry_price
        else:
            opposing_level = self._to_valid_float(self.ms_htf.sl_level[0])
            _, risk, _ = self._resolve_structural_sl_short(entry_price)
            if opposing_level is None or opposing_level >= entry_price or risk <= 0:
                return None
            available_space = entry_price - opposing_level

        return {
            'opposing_level': opposing_level,
            'risk': risk,
            'available_space': available_space,
            'available_rr': available_space / risk if risk > 0 else 0.0,
        }

    def _passes_space_to_target_filter(self, direction: str) -> bool:
        if not self._bool_param('use_structure_filter', True):
            return True
        if not self._bool_param('use_space_to_target_filter', False):
            return True

        min_rr = self._float_param('space_to_target_min_rr', 1.0, min_value=0.0)
        metrics = self._get_space_to_target_metrics(direction, self.close_line[0])
        if metrics is None:
            return False
        return metrics['available_rr'] >= min_rr

    def _has_valid_ltf_choch_trigger(self, direction: str) -> bool:
        if not self._bool_param('use_ltf_choch_trigger', True):
            return True

        bar_num = len(self.data_ltf)
        entry_window = self._int_param('ltf_choch_entry_window_bars', 6, min_value=1)
        trigger_bar = self._long_choch_trigger_bar if direction == 'long' else self._short_choch_trigger_bar
        if trigger_bar <= 0 or (bar_num - trigger_bar) > entry_window:
            return False

        trigger_price = self._long_choch_trigger_price if direction == 'long' else self._short_choch_trigger_price
        if trigger_price is None:
            return False

        current_zone_ref = self._to_valid_float(self.ms_htf.sl_level[0]) if direction == 'long' else self._to_valid_float(self.ms_htf.sh_level[0])
        trigger_zone_ref = self._long_choch_trigger_zone_ref if direction == 'long' else self._short_choch_trigger_zone_ref
        if trigger_zone_ref is None or current_zone_ref is None:
            return False
        if not math.isclose(current_zone_ref, trigger_zone_ref, rel_tol=1e-9, abs_tol=1e-6):
            return False

        max_pullaway_mult = self._to_valid_float(getattr(self.params, 'ltf_choch_max_pullaway_atr_mult', 0.0))
        atr_val = self._to_valid_float(self.atr[0])
        if max_pullaway_mult is not None and max_pullaway_mult > 0 and atr_val is not None and atr_val > 0:
            if abs(self.close_line[0] - trigger_price) > (atr_val * max_pullaway_mult):
                return False

        body_atr_ratio, has_fvg = self._get_choch_trigger_quality(direction)
        if self._bool_param('use_choch_displacement_filter', False):
            min_body_mult = self._float_param('choch_displacement_atr_mult', 1.5, min_value=0.0)
            if body_atr_ratio is None or body_atr_ratio < min_body_mult:
                return False

        if self._bool_param('require_choch_fvg', False) and has_fvg is not True:
            return False

        return True

    def _update_ltf_choch_state(self):
        if not self._bool_param('use_structure_filter', True):
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

        curr_ltf_sh = self._to_valid_float(self.ms_ltf.sh_level[0])
        curr_ltf_sl = self._to_valid_float(self.ms_ltf.sl_level[0])
        prev_ltf_sh = self._to_valid_float(self.ms_ltf.sh_level[-1])
        prev_ltf_sl = self._to_valid_float(self.ms_ltf.sl_level[-1])

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
            if self._bar_intersects_zone(self._get_poi_zone_long()) and new_ltf_swing_low and curr_ltf_sh is not None:
                self._armed_long_choch_level = curr_ltf_sh
                self._armed_long_bar = bar_num

            if self._armed_long_choch_level is not None and self._armed_long_bar > 0:
                if (bar_num - self._armed_long_bar) > arm_timeout:
                    self._armed_long_choch_level = None
                    self._armed_long_bar = -1
                elif close_price > self._armed_long_choch_level and bar_num > self._armed_long_bar:
                    self._long_choch_trigger_bar = bar_num
                    self._long_choch_trigger_price = close_price
                    self._long_choch_trigger_zone_ref = self._to_valid_float(self.ms_htf.sl_level[0])
                    self._capture_choch_trigger_quality('long')
                    self._armed_long_choch_level = None
                    self._armed_long_bar = -1

        if structure != -1:
            self._reset_short_choch_state()
        else:
            if self._bar_intersects_zone(self._get_poi_zone_short()) and new_ltf_swing_high and curr_ltf_sl is not None:
                self._armed_short_choch_level = curr_ltf_sl
                self._armed_short_bar = bar_num

            if self._armed_short_choch_level is not None and self._armed_short_bar > 0:
                if (bar_num - self._armed_short_bar) > arm_timeout:
                    self._armed_short_choch_level = None
                    self._armed_short_bar = -1
                elif close_price < self._armed_short_choch_level and bar_num > self._armed_short_bar:
                    self._short_choch_trigger_bar = bar_num
                    self._short_choch_trigger_price = close_price
                    self._short_choch_trigger_zone_ref = self._to_valid_float(self.ms_htf.sh_level[0])
                    self._capture_choch_trigger_quality('short')
                    self._armed_short_choch_level = None
                    self._armed_short_bar = -1

        if self._long_choch_trigger_bar > 0 and (bar_num - self._long_choch_trigger_bar) > entry_window:
            self._reset_long_choch_state()
        if self._short_choch_trigger_bar > 0 and (bar_num - self._short_choch_trigger_bar) > entry_window:
            self._reset_short_choch_state()

    def _get_poi_zone_long(self):
        sl_level = self._to_valid_float(self.ms_htf.sl_level[0])
        atr_val = self._to_valid_float(self.atr_htf[0])
        if sl_level is None or atr_val is None or atr_val <= 0:
            return None
        zone_high = sl_level + (atr_val * self.params.poi_zone_upper_atr_mult)
        zone_low = sl_level - (atr_val * self.params.poi_zone_lower_atr_mult)
        return zone_low, zone_high

    def _get_poi_zone_short(self):
        sh_level = self._to_valid_float(self.ms_htf.sh_level[0])
        atr_val = self._to_valid_float(self.atr_htf[0])
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

    def _bar_intersects_zone(self, zone) -> bool:
        if zone is None:
            return False
        zone_low, zone_high = zone
        bar_low = self.low_line[0]
        bar_high = self.high_line[0]
        return not (bar_high < zone_low or bar_low > zone_high)

    def _resolve_structural_sl_long(self, entry_price: float):
        atr_val = self._to_valid_float(self.atr_htf[0])
        if atr_val is None or atr_val <= 0:
            return None, 0.0, "Invalid ATR"

        sl_level = self._to_valid_float(self.ms_htf.sl_level[0])
        if sl_level is not None:
            sl_price_ref = sl_level - (atr_val * self.params.structural_sl_buffer_atr)
            if sl_price_ref < entry_price:
                sl_distance = entry_price - sl_price_ref
                sl_calc_expr = (
                    f"{self._scoped_indicator_key('SL_Level', scope='htf')} ({sl_level:.2f}) - "
                    f"({self._scoped_indicator_key('ATR', scope='htf')} * {self.params.structural_sl_buffer_atr})"
                )
                return sl_price_ref, sl_distance, sl_calc_expr

        sl_buffer = atr_val * self.params.sl_buffer_atr
        sl_price_ref = self.low_line[0] - sl_buffer
        if sl_price_ref < entry_price:
            sl_distance = entry_price - sl_price_ref
            sl_calc_expr = f"Fallback: Low ({self.low_line[0]:.2f}) - (ATR * {self.params.sl_buffer_atr})"
            return sl_price_ref, sl_distance, sl_calc_expr
        return None, 0.0, "Unable to build valid long SL"

    def _resolve_structural_sl_short(self, entry_price: float):
        atr_val = self._to_valid_float(self.atr_htf[0])
        if atr_val is None or atr_val <= 0:
            return None, 0.0, "Invalid ATR"

        sh_level = self._to_valid_float(self.ms_htf.sh_level[0])
        if sh_level is not None:
            sl_price_ref = sh_level + (atr_val * self.params.structural_sl_buffer_atr)
            if sl_price_ref > entry_price:
                sl_distance = sl_price_ref - entry_price
                sl_calc_expr = (
                    f"{self._scoped_indicator_key('SH_Level', scope='htf')} ({sh_level:.2f}) + "
                    f"({self._scoped_indicator_key('ATR', scope='htf')} * {self.params.structural_sl_buffer_atr})"
                )
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
                opposing_level = self._to_valid_float(self.ms_htf.sh_level[0])
                if opposing_level is not None and opposing_level > entry_price:
                    tp_price_ref = min(tp_rr, opposing_level)
                    tp_calc_expr = (
                        f"min(Entry + (Risk * RR), "
                        f"{self._scoped_indicator_key('SH_Level', scope='htf')} {opposing_level:.2f})"
                    )
            tp_distance = tp_price_ref - entry_price
        else:
            tp_rr = entry_price - (sl_distance * rr_target)
            tp_price_ref = tp_rr
            tp_calc_expr = "Entry - (Risk * RR)"
            if self.params.use_opposing_level_tp:
                opposing_level = self._to_valid_float(self.ms_htf.sl_level[0])
                if opposing_level is not None and opposing_level < entry_price:
                    tp_price_ref = max(tp_rr, opposing_level)
                    tp_calc_expr = (
                        f"max(Entry - (Risk * RR), "
                        f"{self._scoped_indicator_key('SL_Level', scope='htf')} {opposing_level:.2f})"
                    )
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
        entry_context = self._build_entry_context(reason, direction)
        logger.info(f"[{dt_str}] SIGNAL GENERATED: {direction.upper()} Entry={self.close_line[0]:.2f} SL={sl_price_ref:.2f} TP={tp_price_ref:.2f} Size={size:.4f} Reason={reason}")
        self._log_signal_thesis(
            dt_str,
            entry_context=entry_context,
            sl_price_ref=sl_price_ref,
            tp_price_ref=tp_price_ref,
            sl_calc_expr=sl_calc_expr,
            tp_calc_expr=tp_calc_expr,
        )
        sl_calc = f"Math: {sl_calc_expr}\nResult: {sl_price_ref:.2f}\n---\nATR Period: {self.params.atr_period}"
        tp_calc = f"Math: {tp_calc_expr}\nResult: {tp_price_ref:.2f}\n---\nAdjusted to actual fill price on execution"
        self.pending_metadata = {
            'reason': reason, 'stop_loss': sl_price_ref, 'take_profit': tp_price_ref,
            'sl_distance': sl_distance, 'tp_distance': tp_distance, 'direction': direction, 'size': size,
            'sl_calculation': sl_calc, 'tp_calculation': tp_calc, 'entry_context': entry_context
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

    def _get_bar_shape_metrics(self, offset: int = 0):
        open_val = self._to_valid_float(self.open_line[offset])
        high_val = self._to_valid_float(self.high_line[offset])
        low_val = self._to_valid_float(self.low_line[offset])
        close_val = self._to_valid_float(self.close_line[offset])
        atr_val = self._to_valid_float(self.atr[offset]) if len(self.atr) else None
        if None in (open_val, high_val, low_val, close_val):
            return None

        rng = high_val - low_val
        if rng <= 0:
            return None

        body = abs(close_val - open_val)
        upper_wick = max(0.0, high_val - max(open_val, close_val))
        lower_wick = max(0.0, min(open_val, close_val) - low_val)
        close_location = (close_val - low_val) / rng

        return {
            'open': open_val,
            'high': high_val,
            'low': low_val,
            'close': close_val,
            'range': rng,
            'body': body,
            'upper_wick': upper_wick,
            'lower_wick': lower_wick,
            'upper_wick_to_range': upper_wick / rng,
            'lower_wick_to_range': lower_wick / rng,
            'body_to_range': body / rng,
            'body_to_atr': (body / atr_val) if atr_val is not None and atr_val > 0 else None,
            'close_location': close_location,
        }

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

    def _passes_pinbar_quality(self, check_lower_wick: bool) -> bool:
        if not self._bool_param('use_pinbar_quality_filter', False):
            return True

        stats = self._get_bar_shape_metrics(0)
        if stats is None:
            return False

        dominant_wick = stats['lower_wick'] if check_lower_wick else stats['upper_wick']
        opposite_wick_to_range = stats['upper_wick_to_range'] if check_lower_wick else stats['lower_wick_to_range']
        body_floor = max(stats['body'], stats['range'] * 0.01)
        min_wick_to_body = self._float_param('pinbar_min_wick_to_body_ratio', 2.5, min_value=0.0)
        max_opposite_wick = self._float_param('pinbar_max_opposite_wick_to_range', 0.2, min_value=0.0)
        close_threshold = self._float_param('pinbar_close_near_extreme_threshold', 0.65, min_value=0.0)
        close_threshold = min(close_threshold, 1.0)

        if (dominant_wick / body_floor) < min_wick_to_body:
            return False
        if opposite_wick_to_range > max_opposite_wick:
            return False
        if check_lower_wick and stats['close_location'] < close_threshold:
            return False
        if not check_lower_wick and stats['close_location'] > (1.0 - close_threshold):
            return False
        return True

    def _passes_engulfing_quality(self, direction: str) -> bool:
        if not self._bool_param('use_engulfing_quality_filter', False):
            return True

        current = self._get_bar_shape_metrics(0)
        previous = self._get_bar_shape_metrics(-1)
        if current is None or previous is None:
            return False

        min_body_to_range = self._float_param('engulfing_min_body_to_range', 0.55, min_value=0.0)
        min_body_to_atr = self._float_param('engulfing_min_body_to_atr', 0.35, min_value=0.0)
        min_body_engulf_ratio = self._float_param('engulfing_min_body_engulf_ratio', 1.0, min_value=0.0)
        max_opposite_wick = self._float_param('engulfing_max_opposite_wick_to_range', 0.2, min_value=0.0)
        require_close_through_prev_extreme = self._bool_param('engulfing_require_close_through_prev_extreme', False)

        if current['body_to_range'] < min_body_to_range:
            return False
        if current['body_to_atr'] is None or current['body_to_atr'] < min_body_to_atr:
            return False
        if previous['body'] <= 0 or current['body'] < (previous['body'] * min_body_engulf_ratio):
            return False

        if direction == 'long':
            if not (current['close'] > current['open'] and previous['close'] < previous['open']):
                return False
            if current['open'] > previous['close'] or current['close'] < previous['open']:
                return False
            if current['upper_wick_to_range'] > max_opposite_wick:
                return False
            if require_close_through_prev_extreme and current['close'] <= previous['high']:
                return False
            return True

        if not (current['close'] < current['open'] and previous['close'] > previous['open']):
            return False
        if current['open'] < previous['close'] or current['close'] > previous['open']:
            return False
        if current['lower_wick_to_range'] > max_opposite_wick:
            return False
        if require_close_through_prev_extreme and current['close'] >= previous['low']:
            return False
        return True

    def _is_bullish_pinbar(self):
        if not self._has_significant_range():
            return False
        if self._bool_param('pattern_hammer', True) and self.cdl_hammer[0] == 100 and self._meets_pinbar_wick_body_ratio(check_lower_wick=True) and self._passes_pinbar_quality(check_lower_wick=True):
            return True
        if self._bool_param('pattern_inverted_hammer', True) and self.cdl_invertedhammer[0] == 100 and self._meets_pinbar_wick_body_ratio(check_lower_wick=False) and self._passes_pinbar_quality(check_lower_wick=False):
            return True
        return False

    def _is_bearish_pinbar(self):
        if not self._has_significant_range():
            return False
        if self._bool_param('pattern_shooting_star', True) and self.cdl_shootingstar[0] == -100 and self._meets_pinbar_wick_body_ratio(check_lower_wick=False) and self._passes_pinbar_quality(check_lower_wick=False):
            return True
        if self._bool_param('pattern_hanging_man', True) and self.cdl_hangingman[0] == -100 and self._meets_pinbar_wick_body_ratio(check_lower_wick=True) and self._passes_pinbar_quality(check_lower_wick=True):
            return True
        return False

    def _is_bullish_engulfing(self):
        return self._bool_param('pattern_bullish_engulfing', True) and self.cdl_engulfing[0] == 100 and self._has_significant_range() and self._passes_engulfing_quality('long')

    def _is_bearish_engulfing(self):
        return self._bool_param('pattern_bearish_engulfing', True) and self.cdl_engulfing[0] == -100 and self._has_significant_range() and self._passes_engulfing_quality('short')

    def _check_filters_long(self):
        if self.position or self.order:
            return False

        if self._bool_param('use_structure_filter', True):
            if self._get_structure_state() != 1:
                return False
            if self._bool_param('use_ltf_choch_trigger', True):
                if not self._has_valid_ltf_choch_trigger('long'):
                    return False
            elif not self._bar_intersects_zone(self._get_poi_zone_long()):
                return False
            if not self._passes_premium_discount_filter('long'):
                return False
            if not self._passes_space_to_target_filter('long'):
                return False

        if self._is_ema_filter_enabled():
            htf_close = self._to_valid_float(self.data_htf.close[0])
            ema_val = self._to_valid_float(self.ema_htf[0])
            if htf_close is None or ema_val is None or htf_close < ema_val:
                return False

        if self._bool_param('use_rsi_filter', False):
            if self.rsi[0] > self.params.rsi_overbought:
                return False

        if self._bool_param('use_rsi_momentum', False):
            if self.rsi[0] < self.params.rsi_momentum_threshold:
                return False

        if self._bool_param('use_adx_filter', False):
            if self.adx[0] < self.params.adx_threshold:
                return False

        return True

    def _check_filters_short(self):
        if self.position or self.order:
            return False

        if self._bool_param('use_structure_filter', True):
            if self._get_structure_state() != -1:
                return False
            if self._bool_param('use_ltf_choch_trigger', True):
                if not self._has_valid_ltf_choch_trigger('short'):
                    return False
            elif not self._bar_intersects_zone(self._get_poi_zone_short()):
                return False
            if not self._passes_premium_discount_filter('short'):
                return False
            if not self._passes_space_to_target_filter('short'):
                return False

        if self._is_ema_filter_enabled():
            htf_close = self._to_valid_float(self.data_htf.close[0])
            ema_val = self._to_valid_float(self.ema_htf[0])
            if htf_close is None or ema_val is None or htf_close > ema_val:
                return False

        if self._bool_param('use_rsi_filter', False):
            if self.rsi[0] < self.params.rsi_oversold:
                return False

        if self._bool_param('use_rsi_momentum', False):
            bearish_threshold = 100 - self.params.rsi_momentum_threshold
            if self.rsi[0] > bearish_threshold:
                return False

        if self._bool_param('use_adx_filter', False):
            if self.adx[0] < self.params.adx_threshold:
                return False

        return True
