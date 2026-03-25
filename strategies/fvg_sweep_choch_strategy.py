import datetime
import math
import re

import backtrader as bt
import backtrader.indicators as btind

from .base_strategy import BaseStrategy
from .market_structure import is_confirmed_swing_high, is_confirmed_swing_low
from engine.logger import get_logger

logger = get_logger(__name__)
_TIMEFRAME_TOKEN_RE = re.compile(r"(\d+[mhdw])", re.IGNORECASE)


def _iso_utc(dt: datetime.datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    else:
        dt = dt.astimezone(datetime.timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


class FvgSweepChochStrategy(BaseStrategy):
    params = (
        ("pivot_span", 2),
        ("enable_structure_filter", True),
        ("use_ote_filter", False),
        ("ote_min_retracement", 0.62),
        ("ote_max_retracement", 0.79),
        ("use_min_pullback_filter", True),
        ("min_pullback_atr_mult", 1.0),
        ("enable_fvg", True),
        ("fvg_min_atr_mult", 0.2),
        ("fvg_max_age_bars", 40),
        ("use_midpoint", False),
        ("enable_sweep", True),
        ("sweep_min_atr_mult", 0.15),
        ("enable_choch", True),
        ("choch_mode", "fast"),
        ("choch_entry_window_bars", 6),
        ("choch_max_pullaway_mult", 1.5),
        ("displacement_required", True),
        ("enable_displacement", True),
        ("displacement_atr_mult", 1.0),
        ("displacement_close_threshold", 0.7),
        ("entry_type", "market"),
        ("limit_mode", "choch_level"),
        ("sl_buffer_mult", 0.2),
        ("use_breakeven_sl", False),
        ("breakeven_sl", 1.0),
        ("tp_mode", "liquidity"),
        ("risk_reward_ratio", 2.0),
        ("partial_tp", False),
        ("atr_period", 14),
        ("min_rr_filter", 1.5),
        ("risk_per_trade", 1.0),
        ("leverage", 1.0),
        ("dynamic_position_sizing", True),
        ("max_drawdown", 50.0),
        ("trailing_stop_distance", 0.0),
        ("breakeven_trigger_r", 0.0),
        ("position_cap_adverse", 0.5),
        ("detailed_signals", True),
        ("market_analysis", True),
    )

    # backtrader exposes `Strategy.position` as a read-only property.
    # Unit tests in this repo sometimes construct strategies via `__new__`
    # and then manually set `strategy.position = None` to simulate "no position".
    #
    # To keep runtime behavior intact while unblocking unit tests, we shadow
    # the inherited property with a safe, test-oriented setter/getter.
    @property
    def position(self):
        if "_manual_position" in self.__dict__:
            return self.__dict__["_manual_position"]
        try:
            return super().position
        except Exception:
            # Uninitialized strategy instance (e.g. created via `__new__`).
            return None

    @position.setter
    def position(self, value):
        self.__dict__["_manual_position"] = value

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

    @staticmethod
    def _to_valid_float(value):
        try:
            val = float(value)
        except (TypeError, ValueError):
            return None
        if math.isnan(val) or math.isinf(val):
            return None
        return val

    def _bool_param(self, name: str, default: bool) -> bool:
        raw = getattr(self.params, name, default)
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, (int, float)):
            return bool(raw)
        if isinstance(raw, str):
            normalized = raw.strip().lower()
            if normalized in {"1", "true", "yes", "on"}:
                return True
            if normalized in {"0", "false", "no", "off"}:
                return False
        return default

    def _float_param(self, name: str, default: float, min_value: float | None = None) -> float:
        raw = getattr(self.params, name, default)
        try:
            parsed = float(raw)
        except (TypeError, ValueError):
            parsed = default
        if min_value is not None:
            return max(min_value, parsed)
        return parsed

    def _int_param(self, name: str, default: int, min_value: int = 0) -> int:
        raw = getattr(self.params, name, default)
        try:
            parsed = int(raw)
        except (TypeError, ValueError):
            parsed = default
        return max(min_value, parsed)

    def __init__(self):
        super().__init__()
        self.has_secondary = len(self.datas) > 1
        self.data_ltf = self.datas[0]
        self.data_htf = self.datas[1] if self.has_secondary else self.datas[0]
        self.open_line = self.data_ltf.open
        self.high_line = self.data_ltf.high
        self.low_line = self.data_ltf.low
        self.close_line = self.data_ltf.close
        self.atr = btind.ATR(self.data_ltf, period=self.params.atr_period)
        self.atr_htf = btind.ATR(self.data_htf, period=self.params.atr_period)
        self._htf_timeframe_label = self._detect_data_timeframe(self.data_htf, fallback="HTF")
        self._ltf_timeframe_label = self._detect_data_timeframe(self.data_ltf, fallback="LTF")
        self._last_htf_len = 0
        self._htf_swing_highs: list[dict] = []
        self._htf_swing_lows: list[dict] = []
        self._htf_structure = 0
        self._active_htf_fvg_long = None
        self._active_htf_fvg_short = None
        self._last_internal_swing_high = None
        self._last_internal_swing_low = None
        self._active_setup = None
        self._pending_limit_setup = None

    def get_execution_bar_indicators(self):
        atr_val = self._to_valid_float(self.atr[0])
        if atr_val is None:
            return None
        return {
            "ATR": round(atr_val, 4),
            "HTF_Structure": self._htf_structure,
        }

    def next(self):
        if getattr(self, "_close_orphan_position", False):
            self._close_orphan_position = False
            if self.position:
                self.close()
                return

        if self._oco_closed and not self.position:
            self._oco_closed = False

        self._update_equity_peak()
        if not self.position:
            self.initial_sl = None

        if getattr(self, "_dd_limit_hit", False):
            return

        self._update_drawdown_guard()

        if self.position and self.stop_order:
            self._update_dynamic_exit_orders()

        if self.position:
            self._apply_funding_adjustment(self.data_ltf, self.close_line[0])
            return

        self._update_htf_context()
        self._update_internal_swings()
        self._expire_or_cancel_stale_setup()

        if self.order:
            return

        if self.data_ltf.islive() and not self._is_live_bar_fresh():
            return

        self._try_capture_sweep()
        self._try_confirm_choch()
        self._try_place_entry()

    def _update_drawdown_guard(self):
        max_dd = self.params.max_drawdown
        if max_dd is None or max_dd <= 0 or self._equity_peak <= 0:
            return
        current = self.broker.getvalue()
        dd_pct = 100.0 * (self._equity_peak - current) / self._equity_peak
        if dd_pct <= max_dd:
            return
        if getattr(self, "_dd_limit_hit", False):
            return
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

    def _update_dynamic_exit_orders(self):
        entry_bar = getattr(self, "_entry_exec_bar", -1)
        entry_data = getattr(self, "_entry_exec_data", None)
        bar_ok = entry_data is None or len(entry_data) > entry_bar
        stop_accepted = self.stop_order and self.stop_order.status == bt.Order.Accepted
        tp_ok = self.tp_order is None or self.tp_order.status == bt.Order.Accepted
        if not (bar_ok and stop_accepted and tp_ok):
            return

        current_sl = self.stop_order.price
        new_sl = current_sl
        sl_changed = False
        new_reason = self.stop_reason

        if self.params.breakeven_trigger_r > 0 and self.initial_sl is not None:
            risk = abs(self.position.price - self.initial_sl)
            if risk > 0:
                profit = (self.close_line[0] - self.position.price) if self.position.size > 0 else (self.position.price - self.close_line[0])
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
                trail_price = self.close_line[0] - (self.close_line[0] * self.params.trailing_stop_distance)
                if trail_price > new_sl:
                    new_sl = trail_price
                    sl_changed = True
                    new_reason = "Trailing Stop"
            else:
                trail_price = self.close_line[0] + (self.close_line[0] * self.params.trailing_stop_distance)
                if trail_price < new_sl:
                    new_sl = trail_price
                    sl_changed = True
                    new_reason = "Trailing Stop"

        if not sl_changed:
            return

        dt_str = self._get_local_dt_str(self.data_ltf.datetime.datetime(0))
        logger.info(f"[{dt_str}] STOP UPDATE: {new_reason} -> {new_sl:.2f}")
        self.cancel_reason = f"{new_reason} Update"
        tp_price_val = self.tp_order.price if self.tp_order else None
        if self.tp_order:
            self.cancel(self.tp_order)
            self.tp_order = None
        self.cancel(self.stop_order)
        self.stop_reason = new_reason
        self.sl_history.append({
            "time": _iso_utc(self.data_ltf.datetime.datetime(0)),
            "price": new_sl,
            "reason": new_reason,
        })
        size = abs(self.position.size)
        if self.position.size > 0:
            self.stop_order = self.sell(price=new_sl, exectype=bt.Order.Stop, size=size)
            if tp_price_val is not None:
                self.tp_order = self.sell(price=tp_price_val, exectype=bt.Order.Limit, size=size, oco=self.stop_order)
        else:
            self.stop_order = self.buy(price=new_sl, exectype=bt.Order.Stop, size=size)
            if tp_price_val is not None:
                self.tp_order = self.buy(price=tp_price_val, exectype=bt.Order.Limit, size=size, oco=self.stop_order)

    def _is_live_bar_fresh(self) -> bool:
        bar_dt = self.data_ltf.datetime.datetime(0)
        now_dt = datetime.datetime.utcnow()
        if len(self.data_ltf) >= 2:
            prev_dt = self.data_ltf.datetime.datetime(-1)
            bar_period_secs = max(60, (bar_dt - prev_dt).total_seconds())
        else:
            bar_period_secs = 60
        return (now_dt - bar_dt).total_seconds() <= (bar_period_secs * 2)

    def _update_htf_context(self):
        current_len = len(self.data_htf)
        if current_len == self._last_htf_len:
            return
        self._last_htf_len = current_len
        self._detect_confirmed_htf_swing()
        self._refresh_htf_structure()
        self._detect_htf_fvg()
        self._invalidate_setups_on_bias_change()

    def _detect_confirmed_htf_swing(self):
        span = self._int_param("pivot_span", 2, min_value=1)
        if len(self.data_htf) < (span * 2) + 1:
            return

        candidate_high = self._to_valid_float(self.data_htf.high[-span])
        candidate_low = self._to_valid_float(self.data_htf.low[-span])
        if candidate_high is None or candidate_low is None:
            return

        left_highs = [self.data_htf.high[-span - offset] for offset in range(1, span + 1)]
        right_highs = [self.data_htf.high[-span + offset] for offset in range(1, span + 1)]
        left_lows = [self.data_htf.low[-span - offset] for offset in range(1, span + 1)]
        right_lows = [self.data_htf.low[-span + offset] for offset in range(1, span + 1)]
        swing_bar = len(self.data_htf) - span - 1

        if is_confirmed_swing_high(candidate_high, left_highs, right_highs):
            if not self._htf_swing_highs or self._htf_swing_highs[-1]["bar"] != swing_bar:
                self._htf_swing_highs.append({"bar": swing_bar, "price": candidate_high})

        if is_confirmed_swing_low(candidate_low, left_lows, right_lows):
            if not self._htf_swing_lows or self._htf_swing_lows[-1]["bar"] != swing_bar:
                self._htf_swing_lows.append({"bar": swing_bar, "price": candidate_low})

    def _refresh_htf_structure(self):
        bullish = (
            len(self._htf_swing_highs) >= 2
            and len(self._htf_swing_lows) >= 2
            and self._htf_swing_highs[-1]["price"] > self._htf_swing_highs[-2]["price"]
            and self._htf_swing_lows[-1]["price"] >= self._htf_swing_lows[-2]["price"]
        )
        bearish = (
            len(self._htf_swing_highs) >= 2
            and len(self._htf_swing_lows) >= 2
            and self._htf_swing_lows[-1]["price"] < self._htf_swing_lows[-2]["price"]
            and self._htf_swing_highs[-1]["price"] <= self._htf_swing_highs[-2]["price"]
        )
        if bullish:
            self._htf_structure = 1
        elif bearish:
            self._htf_structure = -1
        else:
            self._htf_structure = 0

    def _detect_htf_fvg(self):
        if not self._bool_param("enable_fvg", True):
            return
        if len(self.data_htf) < 3:
            return

        atr_val = self._to_valid_float(self.atr_htf[0])
        if atr_val is None or atr_val <= 0:
            return

        low_0 = self._to_valid_float(self.data_htf.low[0])
        high_0 = self._to_valid_float(self.data_htf.high[0])
        high_m2 = self._to_valid_float(self.data_htf.high[-2])
        low_m2 = self._to_valid_float(self.data_htf.low[-2])
        if None in (low_0, high_0, high_m2, low_m2):
            return

        min_mult = self._float_param("fvg_min_atr_mult", 0.2, min_value=0.0)
        created_bar = len(self.data_htf) - 1

        if low_0 > high_m2:
            top = low_0
            bottom = high_m2
            zone_size = top - bottom
            if zone_size > (atr_val * min_mult):
                self._active_htf_fvg_long = {
                    "direction": "long",
                    "top": top,
                    "bottom": bottom,
                    "midpoint": (top + bottom) / 2.0,
                    "created_bar": created_bar,
                }

        if high_0 < low_m2:
            top = low_m2
            bottom = high_0
            zone_size = top - bottom
            if zone_size > (atr_val * min_mult):
                self._active_htf_fvg_short = {
                    "direction": "short",
                    "top": top,
                    "bottom": bottom,
                    "midpoint": (top + bottom) / 2.0,
                    "created_bar": created_bar,
                }

    def _get_active_fvg(self, direction: str):
        zone = self._active_htf_fvg_long if direction == "long" else self._active_htf_fvg_short
        if not zone:
            return None
        max_age = self._int_param("fvg_max_age_bars", 40, min_value=1)
        if (len(self.data_htf) - 1) - zone["created_bar"] > max_age:
            return None
        return zone

    def _update_internal_swings(self):
        if len(self.data_ltf) < 3:
            return
        swing_high = self._to_valid_float(self.high_line[-1])
        swing_low = self._to_valid_float(self.low_line[-1])
        prev_high = self._to_valid_float(self.high_line[-2])
        next_high = self._to_valid_float(self.high_line[0])
        prev_low = self._to_valid_float(self.low_line[-2])
        next_low = self._to_valid_float(self.low_line[0])
        swing_bar = len(self.data_ltf) - 2

        if None not in (swing_high, prev_high, next_high) and swing_high > prev_high and swing_high > next_high:
            self._last_internal_swing_high = {"bar": swing_bar, "price": swing_high}
            if self._active_setup and self._active_setup["direction"] == "long" and self._active_setup["phase"] == "await_confirmed_swing":
                if swing_bar > self._active_setup["sweep_bar"]:
                    self._active_setup["choch_level"] = swing_high
                    self._active_setup["phase"] = "await_choch_break"

        if None not in (swing_low, prev_low, next_low) and swing_low < prev_low and swing_low < next_low:
            self._last_internal_swing_low = {"bar": swing_bar, "price": swing_low}
            if self._active_setup and self._active_setup["direction"] == "short" and self._active_setup["phase"] == "await_confirmed_swing":
                if swing_bar > self._active_setup["sweep_bar"]:
                    self._active_setup["choch_level"] = swing_low
                    self._active_setup["phase"] = "await_choch_break"

    def _invalidate_setups_on_bias_change(self):
        if not self._active_setup:
            return
        expected_bias = 1 if self._active_setup["direction"] == "long" else -1
        if self._htf_structure != expected_bias:
            self._active_setup = None
            self._pending_limit_setup = None

    def _is_price_in_zone(self, zone) -> bool:
        if zone is None:
            return False
        return not (self.high_line[0] < zone["bottom"] or self.low_line[0] > zone["top"])

    def _try_capture_sweep(self):
        if not self._bool_param("enable_sweep", True):
            return
        if self.order or self.position:
            return

        atr_val = self._to_valid_float(self.atr[0])
        if atr_val is None or atr_val <= 0:
            return
        wick_mult = self._float_param("sweep_min_atr_mult", 0.15, min_value=0.0)

        if self._allows_direction("long"):
            zone = self._get_active_fvg("long")
            if zone and self._is_price_in_zone(zone) and self._last_internal_swing_low and self._last_internal_swing_high:
                swing_level = self._last_internal_swing_low["price"]
                choch_level = self._last_internal_swing_high["price"]
                current_low = self._to_valid_float(self.low_line[0])
                current_close = self._to_valid_float(self.close_line[0])
                if None not in (current_low, current_close) and current_low < swing_level < current_close:
                    if (swing_level - current_low) > (atr_val * wick_mult):
                        self._active_setup = {
                            "direction": "long",
                            "zone": zone,
                            "sweep_bar": len(self.data_ltf),
                            "sweep_level": swing_level,
                            "sweep_extreme": current_low,
                            "choch_level": choch_level if self._choch_mode() == "fast" else None,
                            "phase": "await_choch_break" if self._choch_mode() == "fast" else "await_confirmed_swing",
                            "choch_confirmed_bar": None,
                        }
                        return

        if self._allows_direction("short"):
            zone = self._get_active_fvg("short")
            if zone and self._is_price_in_zone(zone) and self._last_internal_swing_high and self._last_internal_swing_low:
                swing_level = self._last_internal_swing_high["price"]
                choch_level = self._last_internal_swing_low["price"]
                current_high = self._to_valid_float(self.high_line[0])
                current_close = self._to_valid_float(self.close_line[0])
                if None not in (current_high, current_close) and current_high > swing_level > current_close:
                    if (current_high - swing_level) > (atr_val * wick_mult):
                        self._active_setup = {
                            "direction": "short",
                            "zone": zone,
                            "sweep_bar": len(self.data_ltf),
                            "sweep_level": swing_level,
                            "sweep_extreme": current_high,
                            "choch_level": choch_level if self._choch_mode() == "fast" else None,
                            "phase": "await_choch_break" if self._choch_mode() == "fast" else "await_confirmed_swing",
                            "choch_confirmed_bar": None,
                        }

    def _choch_mode(self) -> str:
        mode = str(getattr(self.params, "choch_mode", "fast") or "fast").strip().lower()
        return "confirmed" if mode == "confirmed" else "fast"

    def _allows_direction(self, direction: str) -> bool:
        if not self._bool_param("enable_structure_filter", True):
            return True
        if direction == "long":
            return self._htf_structure == 1
        return self._htf_structure == -1

    def _get_latest_htf_range(self):
        if not self._htf_swing_highs or not self._htf_swing_lows:
            return None
        sh_level = self._htf_swing_highs[-1]["price"]
        sl_level = self._htf_swing_lows[-1]["price"]
        if sh_level is None or sl_level is None or sh_level <= sl_level:
            return None
        return sh_level, sl_level

    def _passes_ote_filter(self, direction: str, entry_price: float) -> bool:
        if not self._bool_param("use_ote_filter", False):
            return True

        htf_range = self._get_latest_htf_range()
        if htf_range is None:
            return False

        sh_level, sl_level = htf_range
        ote_threshold = self._float_param("ote_min_retracement", 0.62, min_value=0.0)
        range_size = sh_level - sl_level

        if direction == "long":
            return entry_price <= (sh_level - range_size * ote_threshold)
        return entry_price >= (sl_level + range_size * ote_threshold)

    def _passes_min_pullback_filter(self, direction: str, entry_price: float) -> bool:
        if not self._bool_param("use_min_pullback_filter", True):
            return True

        htf_range = self._get_latest_htf_range()
        atr_htf = self._to_valid_float(self.atr_htf[0]) if hasattr(self, "atr_htf") else None
        if htf_range is None or atr_htf is None or atr_htf <= 0:
            return False

        sh_level, sl_level = htf_range
        min_pullback = atr_htf * self._float_param("min_pullback_atr_mult", 1.0, min_value=0.0)
        if direction == "long":
            return (sh_level - entry_price) >= min_pullback
        return (entry_price - sl_level) >= min_pullback

    def _displacement_valid(self, direction: str) -> bool:
        if not self._bool_param("enable_displacement", True):
            return True
        atr_val = self._to_valid_float(self.atr[0])
        open_val = self._to_valid_float(self.open_line[0])
        close_val = self._to_valid_float(self.close_line[0])
        high_val = self._to_valid_float(self.high_line[0])
        low_val = self._to_valid_float(self.low_line[0])
        if None in (atr_val, open_val, close_val, high_val, low_val) or atr_val <= 0:
            return False
        candle_range = high_val - low_val
        if candle_range <= 0:
            return False
        body_size = abs(close_val - open_val)
        if body_size <= (atr_val * self._float_param("displacement_atr_mult", 1.0, min_value=0.0)):
            return False
        close_threshold = min(1.0, self._float_param("displacement_close_threshold", 0.7, min_value=0.0))
        if direction == "long":
            return ((close_val - low_val) / candle_range) >= close_threshold
        return ((high_val - close_val) / candle_range) >= close_threshold

    def _try_confirm_choch(self):
        if not self._bool_param("enable_choch", True):
            return
        if not self._active_setup or self._active_setup["phase"] != "await_choch_break":
            return
        if not self._is_price_in_zone(self._active_setup["zone"]):
            return
        choch_level = self._active_setup.get("choch_level")
        if choch_level is None:
            return
        current_close = self._to_valid_float(self.close_line[0])
        atr_val = self._to_valid_float(self.atr[0])
        if current_close is None or atr_val is None or atr_val <= 0:
            return

        direction = self._active_setup["direction"]
        broke_level = current_close > choch_level if direction == "long" else current_close < choch_level
        if not broke_level:
            return
        if self._bool_param("displacement_required", True) and not self._displacement_valid(direction):
            return
        max_pullaway = self._float_param("choch_max_pullaway_mult", 1.5, min_value=0.0)
        if max_pullaway > 0 and abs(current_close - choch_level) > (atr_val * max_pullaway):
            return
        self._active_setup["phase"] = "ready_to_enter"
        self._active_setup["choch_confirmed_bar"] = len(self.data_ltf)

    def _expire_or_cancel_stale_setup(self):
        if not self._active_setup:
            return
        direction = self._active_setup["direction"]
        if not self._allows_direction(direction):
            self._active_setup = None
            self._pending_limit_setup = None
            return
        if not self._get_active_fvg(direction):
            self._active_setup = None
            self._pending_limit_setup = None
            return
        if self._active_setup["phase"] != "ready_to_enter":
            return
        choch_bar = self._active_setup.get("choch_confirmed_bar")
        if not choch_bar:
            return
        entry_window = self._int_param("choch_entry_window_bars", 6, min_value=1)
        if (len(self.data_ltf) - choch_bar) <= entry_window:
            return
        if self.order:
            self.cancel(self.order)
            self.order = None
        self.pending_metadata = None
        self._pending_limit_setup = None
        self._active_setup = None

    def _try_place_entry(self):
        if not self._active_setup or self._active_setup["phase"] != "ready_to_enter":
            return
        if self.position or self.order:
            return

        direction = self._active_setup["direction"]
        zone = self._active_setup["zone"]
        if not self._is_price_in_zone(zone):
            return

        if str(getattr(self.params, "entry_type", "market") or "market").strip().lower() == "limit":
            self._place_limit_entry(direction)
        else:
            self._place_market_entry(direction, self.close_line[0])

    def _place_limit_entry(self, direction: str):
        limit_mode = str(getattr(self.params, "limit_mode", "choch_level") or "choch_level").strip().lower()
        if limit_mode == "fvg_midpoint" and self._bool_param("use_midpoint", False):
            entry_price = self._active_setup["zone"]["midpoint"]
        else:
            entry_price = self._active_setup["choch_level"]
        self._place_entry_order(direction, entry_price, exectype=bt.Order.Limit)

    def _place_market_entry(self, direction: str, entry_price: float):
        self._place_entry_order(direction, entry_price, exectype=bt.Order.Market)

    def _place_entry_order(self, direction: str, entry_price: float, exectype):
        if not self._passes_min_pullback_filter(direction, entry_price):
            if getattr(self.params, "detailed_signals", True):
                dt_str = self._get_local_dt_str(self.data_ltf.datetime.datetime(0))
                logger.info(
                    f"[{dt_str}] Rejected FVG Sweep CHoCH: entry {entry_price:.2f} "
                    f"failed min pullback filter for {direction}"
                )
            return

        if not self._passes_ote_filter(direction, entry_price):
            if getattr(self.params, "detailed_signals", True):
                dt_str = self._get_local_dt_str(self.data_ltf.datetime.datetime(0))
                logger.info(
                    f"[{dt_str}] Rejected FVG Sweep CHoCH: entry {entry_price:.2f} "
                    f"failed OTE filter for {direction}"
                )
            return

        sl_price = self._resolve_stop_price(direction, entry_price)
        if sl_price is None:
            return
        size = self._calculate_position_size(entry_price, sl_price, direction=direction)
        if size <= 0:
            return

        tp_price, tp_calc_expr = self._resolve_take_profit(direction, entry_price, sl_price)
        if tp_price is None:
            return

        sl_distance = abs(entry_price - sl_price)
        tp_distance = abs(tp_price - entry_price)
        if sl_distance <= 0 or tp_distance <= 0:
            return
        min_rr_required = self._float_param("min_rr_filter", 1.5, min_value=0.0)
        available_rr = tp_distance / sl_distance if sl_distance > 0 else 0.0
        if min_rr_required > 0 and available_rr < min_rr_required:
            if getattr(self.params, "detailed_signals", True):
                dt_str = self._get_local_dt_str(self.data_ltf.datetime.datetime(0))
                logger.info(
                    f"[{dt_str}] Rejected FVG Sweep CHoCH: available RR {available_rr:.2f} "
                    f"below minimum filter {min_rr_required:.2f}"
                )
            return

        dt_str = self._get_local_dt_str(self.data_ltf.datetime.datetime(0))
        entry_context = self._build_entry_context(direction, entry_price, sl_price, tp_price)
        logger.info(
            f"[{dt_str}] SIGNAL GENERATED: {direction.upper()} Entry={entry_price:.2f} "
            f"SL={sl_price:.2f} TP={tp_price:.2f} Size={size:.4f} Reason=FVG Sweep CHoCH"
        )
        self._log_signal_thesis(
            dt_str,
            entry_context=entry_context,
            sl_price_ref=sl_price,
            tp_price_ref=tp_price,
            sl_calc_expr=entry_context["sl_calc_expr"],
            tp_calc_expr=tp_calc_expr,
        )

        self.pending_metadata = {
            "reason": "FVG Sweep CHoCH",
            "stop_loss": sl_price,
            "take_profit": tp_price,
            "sl_distance": sl_distance,
            "tp_distance": tp_distance,
            "direction": direction,
            "size": size,
            "sl_calculation": entry_context["sl_calc_text"],
            "tp_calculation": f"Math: {tp_calc_expr}\nResult: {tp_price:.2f}",
            "entry_context": entry_context["entry_context"],
        }
        self.initial_sl = sl_price
        self.stop_reason = "Stop Loss"
        self.sl_history = [{"time": _iso_utc(self.data_ltf.datetime.datetime(0)), "price": sl_price, "reason": "Initial Stop Loss"}]
        self._pending_limit_setup = self._active_setup if exectype == bt.Order.Limit else None

        if direction == "long":
            if exectype == bt.Order.Limit:
                self.order = self.buy(size=size, exectype=bt.Order.Limit, price=entry_price)
            else:
                self.order = self.buy(size=size, exectype=bt.Order.Market)
        else:
            if exectype == bt.Order.Limit:
                self.order = self.sell(size=size, exectype=bt.Order.Limit, price=entry_price)
            else:
                self.order = self.sell(size=size, exectype=bt.Order.Market)

        if exectype == bt.Order.Market:
            self._active_setup = None

    def _resolve_stop_price(self, direction: str, entry_price: float):
        atr_val = self._to_valid_float(self.atr[0])
        if atr_val is None or atr_val <= 0 or not self._active_setup:
            return None
        sl_buffer = atr_val * self._float_param("sl_buffer_mult", 0.2, min_value=0.0)
        if direction == "long":
            sl_price = self._active_setup["sweep_extreme"] - sl_buffer
            return sl_price if sl_price < entry_price else None
        sl_price = self._active_setup["sweep_extreme"] + sl_buffer
        return sl_price if sl_price > entry_price else None

    def _resolve_take_profit(self, direction: str, entry_price: float, sl_price: float):
        risk = abs(entry_price - sl_price)
        if risk <= 0:
            return None, "Invalid risk"

        tp_mode = str(getattr(self.params, "tp_mode", "liquidity") or "liquidity").strip().lower()
        if tp_mode == "liquidity":
            if direction == "long":
                target = next((s["price"] for s in reversed(self._htf_swing_highs) if s["price"] > entry_price), None)
                if target is not None and target > entry_price:
                    return target, f"Next HTF swing high liquidity ({target:.2f})"
            else:
                target = next((s["price"] for s in reversed(self._htf_swing_lows) if s["price"] < entry_price), None)
                if target is not None and target < entry_price:
                    return target, f"Next HTF swing low liquidity ({target:.2f})"

        rr = self._float_param("risk_reward_ratio", 2.0, min_value=0.1)
        if direction == "long":
            return entry_price + (risk * rr), "Entry + (Risk * RR)"
        return entry_price - (risk * rr), "Entry - (Risk * RR)"

    def _build_entry_context(self, direction: str, entry_price: float, sl_price: float, tp_price: float):
        zone = self._active_setup["zone"]
        setup = self._active_setup
        why_parts = [
            "Pattern: FVG Sweep CHoCH",
            f"HTF bias: {'bullish' if direction == 'long' else 'bearish'}",
            f"Active {self._htf_timeframe_label} FVG [{zone['bottom']:.2f}, {zone['top']:.2f}]",
            f"Sweep through internal liquidity {setup['sweep_level']:.2f}",
            f"CHoCH break of {setup['choch_level']:.2f}",
        ]
        if self._bool_param("enable_displacement", True):
            why_parts.append("Displacement candle validated")

        htf_range = self._get_latest_htf_range()
        indicators = {
            "HTF_Structure": "bullish" if self._htf_structure > 0 else "bearish" if self._htf_structure < 0 else "neutral",
            f"{self._htf_timeframe_label}_FVG_Bottom": round(zone["bottom"], 2),
            f"{self._htf_timeframe_label}_FVG_Top": round(zone["top"], 2),
            "Sweep_Level": round(setup["sweep_level"], 2),
            "Sweep_Extreme": round(setup["sweep_extreme"], 2),
            "CHoCH_Level": round(setup["choch_level"], 2),
            "ATR": round(self.atr[0], 4),
            "Available_RR": round(abs(tp_price - entry_price) / abs(entry_price - sl_price), 2) if abs(entry_price - sl_price) > 0 else None,
        }

        if self._bool_param("use_min_pullback_filter", True) and htf_range is not None:
            sh_level, sl_level = htf_range
            atr_htf = self._to_valid_float(self.atr_htf[0]) if hasattr(self, "atr_htf") else None
            if atr_htf is not None and atr_htf > 0:
                min_pullback = atr_htf * self._float_param("min_pullback_atr_mult", 1.0, min_value=0.0)
                pullback_distance = (sh_level - entry_price) if direction == "long" else (entry_price - sl_level)
                why_parts.append(
                    f"Min pullback filter: {pullback_distance:.2f} away from HTF extreme "
                    f"(required >= {min_pullback:.2f}, {self._float_param('min_pullback_atr_mult', 1.0, min_value=0.0):.2f} x HTF ATR)"
                )
                indicators["HTF_ATR"] = round(atr_htf, 4)
                indicators["Min_Pullback_Required"] = round(min_pullback, 2)
                indicators["Pullback_From_HTF_Extreme"] = round(pullback_distance, 2)

        if self._bool_param("use_ote_filter", False) and htf_range is not None:
            sh_level, sl_level = htf_range
            ote_min = self._float_param("ote_min_retracement", 0.62, min_value=0.0)
            ote_max = self._float_param("ote_max_retracement", 0.79, min_value=ote_min)
            range_size = sh_level - sl_level
            equilibrium = (sh_level + sl_level) / 2.0
            if direction == "long":
                ote_low = sh_level - range_size * ote_max
                ote_high = sh_level - range_size * ote_min
                why_parts.append(f"OTE filter: entry {entry_price:.2f} is in discount zone [{ote_low:.2f}, {ote_high:.2f}]")
            else:
                ote_low = sl_level + range_size * ote_min
                ote_high = sl_level + range_size * ote_max
                why_parts.append(f"OTE filter: entry {entry_price:.2f} is in premium zone [{ote_low:.2f}, {ote_high:.2f}]")

            indicators["HTF_Equilibrium_0_5"] = round(equilibrium, 2)
            indicators["OTE_Low"] = round(ote_low, 2)
            indicators["OTE_High"] = round(ote_high, 2)

        sl_calc_expr = f"Sweep extreme {'-' if direction == 'long' else '+'} (ATR * {self.params.sl_buffer_mult})"
        sl_calc_text = f"Math: {sl_calc_expr}\nResult: {sl_price:.2f}"
        return {
            "entry_context": {
                "why_entry": why_parts,
                "indicators_at_entry": indicators,
            },
            "sl_calc_expr": sl_calc_expr,
            "sl_calc_text": sl_calc_text,
        }

    def notify_order(self, order):
        super().notify_order(order)
        if order.status in (order.Canceled, order.Margin, order.Rejected):
            if order == self.order:
                self._pending_limit_setup = None
        if order.status == order.Completed and order == self.order:
            self._active_setup = None
            self._pending_limit_setup = None
