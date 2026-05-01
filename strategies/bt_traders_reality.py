"""TradersRealityStrategy — backtrader implementation of the Traders Reality signal system.

Based on: ``scripts/market_analyzer.py`` (Python port of PineScript by plasmapug et al.).

Signal components:
  - EMA stack (5/13/50/200): ±2 pts
  - PVSRA vector quality:    ±1 to ±2 pts
  - Daily pivot position:    ±1 pt
  - ADR exhaustion:          ±1 pt
  - EMA 5/13 cross:          ±1 pt
"""
from __future__ import annotations

import datetime
import math
from collections import deque

import backtrader as bt

from engine.logger import get_logger

from .base_strategy import BaseStrategy
from .helpers.tr_indicators import (
    adr_exhaustion_score,
    adr_mean,
    classify_signal,
    composite_signal_score,
    ema_cross_score,
    ema_stack_score,
    pivot_levels,
    pivot_position_score,
    pvsra_label,
    pvsra_score_delta,
)

logger = get_logger(__name__)


def _iso_utc(dt: datetime.datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    else:
        dt = dt.astimezone(datetime.timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


class TradersRealityStrategy(BaseStrategy):
    params = (
        # EMA periods
        ("ema_fast", 5),
        ("ema_medium", 13),
        ("ema_slow", 50),
        ("ema_trend", 200),
        # PVSRA rolling window and thresholds
        ("pvsra_avg_period", 10),
        ("pvsra_rv_mult", 2.0),
        ("pvsra_bv_mult", 1.5),
        # ADR settings
        ("adr_period", 14),
        ("adr_exhaustion_threshold", 0.85),
        # Signal entry thresholds
        ("signal_long_min_score", 2.0),
        ("signal_short_max_score", -2.0),
        # Which PVSRA labels qualify as entry triggers
        ("pvsra_long_labels", ("green", "blue")),
        ("pvsra_short_labels", ("red", "violet")),
        # HTF EMA filter
        ("use_htf_ema_filter", True),
        # Pivot-based SL/TP
        ("use_weekly_sl", True),
        ("use_pivot_tp", True),
        # ATR fallback SL
        ("atr_period", 14),
        ("sl_buffer_atr", 1.5),
        ("sl_weekly_buffer_atr", 0.1),
        # Trailing / breakeven (inherited from BaseStrategy pattern)
        ("trailing_stop_distance", 0.0),
        ("breakeven_trigger_r", 0.0),
        # Risk/display controls (passed through by strategy_runtime)
        ("risk_reward_ratio", 2.0),
        ("risk_per_trade", 1.0),
        ("leverage", 1.0),
        ("dynamic_position_sizing", True),
        ("max_drawdown", 50.0),
        ("detailed_signals", True),
        ("market_analysis", True),
    )

    def __init__(self):
        super().__init__()
        self.has_secondary = len(self.datas) > 1
        if self.has_secondary:
            self.data_ltf = self.datas[0]
            self.data_htf = self.datas[1]
        else:
            self.data_ltf = self.datas[0]
            self.data_htf = self.datas[0]

        self.ema_fast = bt.talib.EMA(self.data_ltf.close, timeperiod=self.p.ema_fast)
        self.ema_medium = bt.talib.EMA(self.data_ltf.close, timeperiod=self.p.ema_medium)
        self.ema_slow = bt.talib.EMA(self.data_ltf.close, timeperiod=self.p.ema_slow)
        self.ema_trend_ltf = bt.talib.EMA(self.data_ltf.close, timeperiod=self.p.ema_trend)
        self.ema_trend_htf = bt.talib.EMA(self.data_htf.close, timeperiod=self.p.ema_trend)
        self.atr_ltf = bt.talib.ATR(
            self.data_ltf.high,
            self.data_ltf.low,
            self.data_ltf.close,
            timeperiod=self.p.atr_period,
        )

        period = max(1, int(self.p.pvsra_avg_period))
        self._pvsra_period: int = period
        self._pvsra_vol_buf: deque[float] = deque(maxlen=period)
        self._pvsra_spread_vol_buf: deque[float] = deque(maxlen=period)
        self._last_pvsra_label: str = "gray_up"

        # Normalize PVSRA label gates to frozensets for cheap + robust
        # membership checks regardless of whether the user supplied tuple/list.
        self._pvsra_long_set: frozenset[str] = frozenset(self.p.pvsra_long_labels or ())
        self._pvsra_short_set: frozenset[str] = frozenset(
            self.p.pvsra_short_labels or ()
        )

        self._current_day: datetime.date | None = None
        self._day_high: float = float("-inf")
        self._day_low: float = float("inf")
        self._day_close: float | None = None
        self._pivots: dict | None = None
        self._adr_buf: deque[float] = deque(maxlen=int(self.p.adr_period))
        self._current_adr: float | None = None
        self._current_day_low: float | None = None
        self._current_day_high: float | None = None

        self._current_week: tuple | None = None
        self._week_high: float = float("-inf")
        self._week_low: float = float("inf")
        self._m5: float | None = None  # prev week HIGH (resistance)
        self._m0: float | None = None  # prev week LOW (support)

    # ── State machines ────────────────────────────────────────────────────────

    def _update_pvsra(self, vol: float, spread: float) -> None:
        self._pvsra_vol_buf.append(vol)
        self._pvsra_spread_vol_buf.append(spread * vol)
        # Require a full warmup window before labeling: with a tiny buffer the
        # rolling average is meaningless and ring-volume triggers trivially.
        if len(self._pvsra_vol_buf) < self._pvsra_period:
            self._last_pvsra_label = (
                "gray_up"
                if float(self.data_ltf.close[0]) >= float(self.data_ltf.open[0])
                else "gray_dn"
            )
            return
        avg_vol = sum(self._pvsra_vol_buf) / len(self._pvsra_vol_buf)
        max_sv = max(self._pvsra_spread_vol_buf)
        is_bull = float(self.data_ltf.close[0]) >= float(self.data_ltf.open[0])
        self._last_pvsra_label = pvsra_label(
            vol=vol,
            spread=spread,
            avg_vol=avg_vol,
            max_spread_vol=max_sv,
            is_bull=is_bull,
            rv_mult=self.p.pvsra_rv_mult,
            bv_mult=self.p.pvsra_bv_mult,
        )

    def _update_daily_state(
        self,
        dt: datetime.date,
        high: float,
        low: float,
        close: float,
    ) -> None:
        if self._current_day is None:
            self._current_day = dt
            self._day_high = high
            self._day_low = low
            self._day_close = close
            self._current_day_high = high
            self._current_day_low = low
            return

        if dt != self._current_day:
            if (
                self._day_high > float("-inf")
                and self._day_low < float("inf")
                and self._day_close is not None
            ):
                day_range = self._day_high - self._day_low
                self._adr_buf.append(day_range)
                self._pivots = pivot_levels(
                    self._day_high, self._day_low, self._day_close
                )
            self._current_adr = adr_mean(list(self._adr_buf))
            self._current_day = dt
            self._day_high = high
            self._day_low = low
            self._day_close = close
        else:
            self._day_high = max(self._day_high, high)
            self._day_low = min(self._day_low, low)
            self._day_close = close

        self._current_day_high = self._day_high
        self._current_day_low = self._day_low

    def _update_weekly_state(
        self, dt: datetime.date, high: float, low: float
    ) -> None:
        iso = dt.isocalendar()
        week_key = (iso[0], iso[1])

        if self._current_week is None:
            self._current_week = week_key
            self._week_high = high
            self._week_low = low
            return

        if week_key != self._current_week:
            if self._week_high > float("-inf") and self._week_low < float("inf"):
                self._m5 = self._week_high
                self._m0 = self._week_low
            self._current_week = week_key
            self._week_high = high
            self._week_low = low
        else:
            self._week_high = max(self._week_high, high)
            self._week_low = min(self._week_low, low)

    # ── Score computation ─────────────────────────────────────────────────────

    def _compute_signal_score(self) -> tuple[float, str]:
        e5 = self._safe_float(self.ema_fast[0])
        e13 = self._safe_float(self.ema_medium[0])
        e50 = self._safe_float(self.ema_slow[0])
        e200 = self._safe_float(self.ema_trend_ltf[0])
        e5_prev = self._safe_float(self.ema_fast[-1]) if len(self.ema_fast) > 1 else None
        e13_prev = (
            self._safe_float(self.ema_medium[-1]) if len(self.ema_medium) > 1 else None
        )

        if any(v is None for v in (e5, e13, e50, e200, e5_prev, e13_prev)):
            return 0.0, self._last_pvsra_label

        stack = ema_stack_score(e5, e13, e50, e200)
        cross = ema_cross_score(e5, e13, e5_prev, e13_prev)
        pvsra = pvsra_score_delta(self._last_pvsra_label)

        pp_score = 0.0
        if self._pivots is not None:
            pp_score = pivot_position_score(
                float(self.data_ltf.close[0]), self._pivots["PP"]
            )

        adr_score = 0.0
        if (
            self._current_adr is not None
            and self._current_adr > 0
            and self._current_day_low is not None
            and self._current_day_high is not None
        ):
            adr_score = adr_exhaustion_score(
                close=float(self.data_ltf.close[0]),
                day_low=self._current_day_low,
                day_high=self._current_day_high,
                adr=self._current_adr,
                threshold=self.p.adr_exhaustion_threshold,
            )

        score = composite_signal_score(stack, pvsra, pp_score, adr_score, cross)
        return score, self._last_pvsra_label

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _safe_float(value) -> float | None:
        try:
            v = float(value)
        except (TypeError, ValueError):
            return None
        if math.isnan(v) or math.isinf(v):
            return None
        return v

    def _get_local_dt_str(self, dt=None):
        if dt is None:
            dt = self.data_ltf.datetime.datetime(0)
        return (
            dt.replace(tzinfo=datetime.timezone.utc)
            .astimezone()
            .strftime("%Y-%m-%d %H:%M:%S")
        )

    # ── Entry resolution ──────────────────────────────────────────────────────

    def _resolve_sl_long(self, entry_price: float):
        atr = self._safe_float(self.atr_ltf[0])
        if atr is None or atr <= 0:
            return None, 0.0, "Invalid ATR"

        if self.p.use_weekly_sl and self._m0 is not None:
            sl_price = self._m0 - atr * self.p.sl_weekly_buffer_atr
            if sl_price < entry_price:
                dist = entry_price - sl_price
                return (
                    sl_price,
                    dist,
                    f"Weekly M0 ({self._m0:.2f}) - ATR*{self.p.sl_weekly_buffer_atr}",
                )

        if self._pivots is not None:
            s1 = self._pivots["S1"]
            if s1 < entry_price:
                dist = entry_price - s1
                return s1, dist, f"Daily S1 ({s1:.2f})"

        sl_price = float(self.data_ltf.low[0]) - atr * self.p.sl_buffer_atr
        if sl_price < entry_price:
            dist = entry_price - sl_price
            return sl_price, dist, f"Low - ATR*{self.p.sl_buffer_atr}"

        return None, 0.0, "Cannot build valid long SL"

    def _resolve_sl_short(self, entry_price: float):
        atr = self._safe_float(self.atr_ltf[0])
        if atr is None or atr <= 0:
            return None, 0.0, "Invalid ATR"

        if self.p.use_weekly_sl and self._m5 is not None:
            sl_price = self._m5 + atr * self.p.sl_weekly_buffer_atr
            if sl_price > entry_price:
                dist = sl_price - entry_price
                return (
                    sl_price,
                    dist,
                    f"Weekly M5 ({self._m5:.2f}) + ATR*{self.p.sl_weekly_buffer_atr}",
                )

        if self._pivots is not None:
            r1 = self._pivots["R1"]
            if r1 > entry_price:
                dist = r1 - entry_price
                return r1, dist, f"Daily R1 ({r1:.2f})"

        sl_price = float(self.data_ltf.high[0]) + atr * self.p.sl_buffer_atr
        if sl_price > entry_price:
            dist = sl_price - entry_price
            return sl_price, dist, f"High + ATR*{self.p.sl_buffer_atr}"

        return None, 0.0, "Cannot build valid short SL"

    def _resolve_tp_long(self, entry_price: float, sl_distance: float):
        if self.p.use_pivot_tp and self._pivots is not None:
            r1 = self._pivots["R1"]
            if r1 > entry_price:
                dist = r1 - entry_price
                return r1, dist, f"Daily R1 ({r1:.2f})"
        rr_tp = entry_price + sl_distance * self.p.risk_reward_ratio
        dist = rr_tp - entry_price
        return rr_tp, dist, f"Entry + Risk*RR({self.p.risk_reward_ratio})"

    def _resolve_tp_short(self, entry_price: float, sl_distance: float):
        if self.p.use_pivot_tp and self._pivots is not None:
            s1 = self._pivots["S1"]
            if s1 < entry_price:
                dist = entry_price - s1
                return s1, dist, f"Daily S1 ({s1:.2f})"
        rr_tp = entry_price - sl_distance * self.p.risk_reward_ratio
        dist = entry_price - rr_tp
        return rr_tp, dist, f"Entry - Risk*RR({self.p.risk_reward_ratio})"

    # ── HTF filter ────────────────────────────────────────────────────────────

    def _htf_is_bullish(self) -> bool:
        if not self.p.use_htf_ema_filter:
            return True
        htf_close = self._safe_float(self.data_htf.close[0])
        htf_ema = self._safe_float(self.ema_trend_htf[0])
        if htf_close is None or htf_ema is None:
            return False
        return htf_close > htf_ema

    def _htf_is_bearish(self) -> bool:
        if not self.p.use_htf_ema_filter:
            return True
        htf_close = self._safe_float(self.data_htf.close[0])
        htf_ema = self._safe_float(self.ema_trend_htf[0])
        if htf_close is None or htf_ema is None:
            return False
        return htf_close < htf_ema

    # ── Entry / exit context ──────────────────────────────────────────────────

    def _build_entry_context(
        self, reason: str, direction: str, score: float, pvsra: str
    ) -> dict:
        indicators = {
            "SignalScore": round(score, 1),
            "Signal": classify_signal(score),
            "PVSRA": pvsra,
        }
        atr = self._safe_float(self.atr_ltf[0])
        if atr is not None:
            indicators["ATR"] = round(atr, 4)
        e5 = self._safe_float(self.ema_fast[0])
        e200 = self._safe_float(self.ema_trend_ltf[0])
        if e5 is not None and e200 is not None:
            indicators["EMA5_vs_EMA200"] = "bull" if e5 > e200 else "bear"
        if self._m5 is not None:
            indicators["M5_Weekly"] = round(self._m5, 4)
        if self._m0 is not None:
            indicators["M0_Weekly"] = round(self._m0, 4)
        if self._pivots is not None:
            indicators["DailyPP"] = round(self._pivots["PP"], 4)

        why_parts = [
            f"TR Signal: {reason}",
            f"Score: {score:.1f} → {classify_signal(score)}",
            f"PVSRA: {pvsra}",
        ]
        if self.p.use_htf_ema_filter:
            htf_trend = "bullish" if self._htf_is_bullish() else "bearish"
            why_parts.append(f"HTF EMA{self.p.ema_trend}: {htf_trend}")

        return {"why_entry": why_parts, "indicators_at_entry": indicators}

    def _build_exit_context(self, exit_reason: str) -> dict:
        score, pvsra = self._compute_signal_score()
        return {
            "why_exit": [
                f"Exit: {exit_reason}",
                f"PVSRA: {pvsra}",
                f"Score: {score:.1f}",
            ],
            "indicators_at_exit": {
                "SignalScore": round(score, 1),
                "PVSRA": pvsra,
            },
        }

    def _place_entry(self, direction: str, score: float, pvsra: str) -> None:
        """Resolve SL/TP/size first, and only mutate state if the entry is viable.

        This avoids leaking ``pending_metadata``/``sl_history`` and false
        ``SIGNAL GENERATED`` logs on aborted entries (zero size, invalid SL,
        non-positive TP distance).
        """
        entry_price = float(self.data_ltf.close[0])

        if direction == "long":
            sl_price, sl_dist, sl_expr = self._resolve_sl_long(entry_price)
        else:
            sl_price, sl_dist, sl_expr = self._resolve_sl_short(entry_price)
        if sl_price is None or sl_dist <= 0:
            return

        if direction == "long":
            tp_price, tp_dist, tp_expr = self._resolve_tp_long(entry_price, sl_dist)
        else:
            tp_price, tp_dist, tp_expr = self._resolve_tp_short(entry_price, sl_dist)
        if tp_dist <= 0:
            return

        size = self._calculate_position_size(entry_price, sl_price, direction=direction)
        if size <= 0:
            if bool(getattr(self.p, "detailed_signals", True)):
                dt_str = self._get_local_dt_str()
                logger.warning(
                    f"[{dt_str}] {direction.upper()} size=0, skipping. "
                    f"SL={sl_price:.4f}"
                )
            return

        dt_str = self._get_local_dt_str()
        reason_label = "LONG entry" if direction == "long" else "SHORT entry"
        entry_context = self._build_entry_context(reason_label, direction, score, pvsra)
        reason = f"TR {direction.upper()} (score={score:.1f}, pvsra={pvsra})"
        logger.info(
            f"[{dt_str}] SIGNAL GENERATED: {direction.upper()} "
            f"Entry={entry_price:.4f} SL={sl_price:.4f} TP={tp_price:.4f} "
            f"Size={size:.6f} Score={score:.1f} PVSRA={pvsra}"
        )
        self._log_signal_thesis(
            dt_str,
            entry_context=entry_context,
            sl_price_ref=sl_price,
            tp_price_ref=tp_price,
            sl_calc_expr=sl_expr,
            tp_calc_expr=tp_expr,
        )

        self.pending_metadata = {
            "reason": reason,
            "stop_loss": sl_price,
            "take_profit": tp_price,
            "sl_distance": sl_dist,
            "tp_distance": tp_dist,
            "direction": direction,
            "size": size,
            "sl_calculation": f"Math: {sl_expr}\nResult: {sl_price:.4f}",
            "tp_calculation": f"Math: {tp_expr}\nResult: {tp_price:.4f}",
            "entry_context": entry_context,
        }
        self.initial_sl = sl_price
        self.stop_reason = "Stop Loss"
        self.sl_history = [
            {
                "time": _iso_utc(self.data_ltf.datetime.datetime(0)),
                "price": sl_price,
                "reason": "Initial Stop Loss",
            }
        ]
        if direction == "long":
            self.order = self.buy(size=size, exectype=bt.Order.Market)
        else:
            self.order = self.sell(size=size, exectype=bt.Order.Market)

    def _enter_long(self, score: float, pvsra: str) -> None:
        self._place_entry("long", score, pvsra)

    def _enter_short(self, score: float, pvsra: str) -> None:
        self._place_entry("short", score, pvsra)

    # ── Main loop ─────────────────────────────────────────────────────────────

    def next(self):
        if getattr(self, "_close_orphan_position", False):
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
        if getattr(self, "_dd_limit_hit", False):
            return

        max_dd = self.p.max_drawdown
        if max_dd is not None and max_dd > 0 and self._equity_peak > 0:
            current = self.broker.getvalue()
            dd_pct = 100.0 * (self._equity_peak - current) / self._equity_peak
            if dd_pct > max_dd:
                if not getattr(self, "_dd_limit_hit", False):
                    dt_str = self._get_local_dt_str()
                    if self.p.stop_on_drawdown:
                        logger.warning(
                            f"[{dt_str}] CRITICAL: Drawdown {dd_pct:.2f}% > {max_dd}%. Stopping."
                        )
                        self._dd_limit_hit = True
                        if self.position:
                            self._dd_close_order = self.close()
                        else:
                            self._dd_stop_runstop()
                if self.p.stop_on_drawdown:
                    return

        entry_bar = getattr(self, "_entry_exec_bar", -1)
        entry_data = getattr(self, "_entry_exec_data", None)
        bar_ok = entry_data is None or len(entry_data) > entry_bar
        stop_acc = self.stop_order and self.stop_order.status == bt.Order.Accepted
        tp_ok = self.tp_order is None or self.tp_order.status == bt.Order.Accepted

        if self.position and self.stop_order and bar_ok and stop_acc and tp_ok:
            cur_sl = self.stop_order.price
            new_sl = cur_sl
            sl_changed = False
            new_reason = self.stop_reason

            if self.p.breakeven_trigger_r > 0 and self.initial_sl is not None:
                risk = abs(self.position.price - self.initial_sl)
                if risk > 0:
                    profit = (
                        float(self.data_ltf.close[0]) - self.position.price
                        if self.position.size > 0
                        else self.position.price - float(self.data_ltf.close[0])
                    )
                    if profit >= risk * self.p.breakeven_trigger_r:
                        be_price = self.position.price
                        if self.position.size > 0 and be_price > new_sl:
                            new_sl, sl_changed, new_reason = (
                                be_price,
                                True,
                                "Breakeven",
                            )
                            self.initial_sl = None
                        elif self.position.size < 0 and be_price < new_sl:
                            new_sl, sl_changed, new_reason = (
                                be_price,
                                True,
                                "Breakeven",
                            )
                            self.initial_sl = None

            if self.p.trailing_stop_distance > 0:
                if self.position.size > 0:
                    trail = float(self.data_ltf.close[0]) * (
                        1 - self.p.trailing_stop_distance
                    )
                    if trail > new_sl:
                        new_sl, sl_changed, new_reason = (
                            trail,
                            True,
                            "Trailing Stop",
                        )
                elif self.position.size < 0:
                    trail = float(self.data_ltf.close[0]) * (
                        1 + self.p.trailing_stop_distance
                    )
                    if trail < new_sl:
                        new_sl, sl_changed, new_reason = (
                            trail,
                            True,
                            "Trailing Stop",
                        )

            if sl_changed:
                dt_str = self._get_local_dt_str()
                logger.info(f"[{dt_str}] STOP UPDATE: {new_reason} -> {new_sl:.4f}")
                self.cancel_reason = f"{new_reason} Update"
                tp_val = self.tp_order.price if self.tp_order else None
                if self.tp_order:
                    self.cancel(self.tp_order)
                    self.tp_order = None
                self.cancel(self.stop_order)
                self.stop_reason = new_reason
                self.sl_history.append(
                    {
                        "time": _iso_utc(self.data_ltf.datetime.datetime(0)),
                        "price": new_sl,
                        "reason": new_reason,
                    }
                )
                if self.position.size > 0:
                    self.stop_order = self.sell(
                        price=new_sl, exectype=bt.Order.Stop, size=self.position.size
                    )
                    if tp_val:
                        self.tp_order = self.sell(
                            price=tp_val,
                            exectype=bt.Order.Limit,
                            size=self.position.size,
                            oco=self.stop_order,
                        )
                else:
                    self.stop_order = self.buy(
                        price=new_sl,
                        exectype=bt.Order.Stop,
                        size=abs(self.position.size),
                    )
                    if tp_val:
                        self.tp_order = self.buy(
                            price=tp_val,
                            exectype=bt.Order.Limit,
                            size=abs(self.position.size),
                            oco=self.stop_order,
                        )

        if self.position:
            self._apply_funding_adjustment(
                self.data_ltf, float(self.data_ltf.close[0])
            )

        bar_dt = self.data_ltf.datetime.datetime(0)
        self._update_pvsra(
            vol=float(self.data_ltf.volume[0]),
            spread=float(self.data_ltf.high[0]) - float(self.data_ltf.low[0]),
        )
        self._update_daily_state(
            dt=bar_dt.date(),
            high=float(self.data_ltf.high[0]),
            low=float(self.data_ltf.low[0]),
            close=float(self.data_ltf.close[0]),
        )
        self._update_weekly_state(
            dt=bar_dt.date(),
            high=float(self.data_ltf.high[0]),
            low=float(self.data_ltf.low[0]),
        )

        if self.position:
            return

        score, pvsra = self._compute_signal_score()
        verbose = bool(getattr(self.p, "detailed_signals", True))

        if score >= self.p.signal_long_min_score:
            if pvsra not in self._pvsra_long_set:
                if verbose:
                    logger.info(
                        f"Rejected LONG: PVSRA={pvsra} not in "
                        f"{sorted(self._pvsra_long_set)}"
                    )
            elif not self._htf_is_bullish():
                if verbose:
                    logger.info("Rejected LONG: HTF not bullish")
            else:
                self._enter_long(score, pvsra)

        elif score <= self.p.signal_short_max_score:
            if pvsra not in self._pvsra_short_set:
                if verbose:
                    logger.info(
                        f"Rejected SHORT: PVSRA={pvsra} not in "
                        f"{sorted(self._pvsra_short_set)}"
                    )
            elif not self._htf_is_bearish():
                if verbose:
                    logger.info("Rejected SHORT: HTF not bearish")
            else:
                self._enter_short(score, pvsra)
