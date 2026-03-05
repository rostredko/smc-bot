"""
FastTestStrategy
================
Deterministic stress/smoke strategy for live paper tests.

Goals:
- Generate frequent entries on real Binance candles (LTF feed, typically 1m).
- Guarantee closed trades via time-based forced flatten (even in flat markets).
- Keep all production execution mechanics (entry fill -> SL/TP placement in notify_order).
"""

import datetime
import backtrader as bt
import backtrader.indicators as btind
from .base_strategy import BaseStrategy
from engine.logger import get_logger

logger = get_logger(__name__)


def _iso_utc(dt: datetime.datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    else:
        dt = dt.astimezone(datetime.timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


class FastTestStrategy(BaseStrategy):
    """High-frequency deterministic strategy for live pipeline verification."""

    params = (
        ('sl_mult', 0.35),
        ('tp_mult', 0.55),
        ('atr_period', 7),
        ('max_drawdown', 50.0),
        ('risk_per_trade', 1.0),
        ('leverage', 5.0),
        ('dynamic_position_sizing', True),
        # Compatibility with common server-injected strategy kwargs
        ('trailing_stop_distance', 0.0),
        ('breakeven_trigger_r', 0.0),
        ('position_cap_adverse', 0.5),
        # Deterministic and margin-safe for BTCUSDT live paper tests.
        ('fixed_size', 0.001),
        # Used when dynamic size unexpectedly returns zero/negative.
        ('min_fallback_size', 0.001),
        # Entry cadence: 1 = signal every LTF bar, 2 = every 2 bars, etc.
        ('force_signal_every_n_bars', 1),
        # Guarantees closure in stagnant market: force market close after N bars in position.
        ('max_hold_bars', 1),
        # Stop the engine automatically after this many closed trades (0 = never).
        ('stop_after_n_trades', 0),
    )

    def __init__(self):
        super().__init__()
        self.has_secondary = len(self.datas) > 1
        self.data_ltf = self.datas[0]
        self.data_htf = self.datas[1] if self.has_secondary else self.datas[0]
        self.atr = btind.ATR(self.data_ltf, period=self.params.atr_period)
        self._signal_count = 0
        self._closed_count = 0
        self._last_signal_bar = -1
        self._time_exit_order = None
        # Injected by BTLiveEngine tests
        self._stop_event = None

    def _pick_size(self, entry: float, sl_ref: float) -> float:
        if self.params.fixed_size > 0:
            return float(self.params.fixed_size)
        size = float(self._calculate_position_size(entry, sl_ref))
        if size > 0:
            return size
        if self.params.min_fallback_size > 0:
            return float(self.params.min_fallback_size)
        return 0.0

    def _is_live_bar_fresh(self) -> bool:
        if not self.data_ltf.islive():
            return True
        bar_dt = self.data_ltf.datetime.datetime(0)
        now_dt = datetime.datetime.utcnow()
        if len(self.data_ltf) >= 2:
            prev_dt = self.data_ltf.datetime.datetime(-1)
            bar_period_secs = max(60, (bar_dt - prev_dt).total_seconds())
        else:
            bar_period_secs = 60
        age_secs = (now_dt - bar_dt).total_seconds()
        return age_secs <= bar_period_secs * 2

    def _force_time_exit_if_needed(self) -> bool:
        max_hold = int(self.params.max_hold_bars or 0)
        if max_hold <= 0:
            return False
        if not self.position:
            return False
        if self._entry_exec_data is None or self._entry_exec_bar < 0:
            return False
        if self._time_exit_order and self._time_exit_order.alive():
            return True

        bars_since_entry = len(self._entry_exec_data) - self._entry_exec_bar
        if bars_since_entry < max_hold:
            return False

        if self.tp_order:
            self.cancel(self.tp_order)
            self.tp_order = None
        if self.stop_order:
            self.cancel(self.stop_order)
            self.stop_order = None

        self.last_exit_reason = "Time Exit"
        self._time_exit_order = self.close(data=self._entry_exec_data)
        dt_str = self._get_local_dt_str(self.data_ltf.datetime.datetime(0))
        logger.info(f"[{dt_str}] [FastTest] Time Exit triggered after {bars_since_entry} bars.")
        return True

    def notify_order(self, order):
        super().notify_order(order)
        if self._time_exit_order and order.ref == self._time_exit_order.ref:
            if order.status not in (order.Submitted, order.Accepted):
                self._time_exit_order = None

    def notify_trade(self, trade):
        super().notify_trade(trade)
        if trade.isclosed:
            self._closed_count += 1
            n = int(self.params.stop_after_n_trades or 0)
            if n > 0 and self._closed_count >= n:
                logger.info(f"🏁 [FastTestStrategy] {self._closed_count} trades closed — stopping.")
                if self._stop_event is not None:
                    self._stop_event.set()

    def next(self):
        if self.order:
            return
        if self._time_exit_order and self._time_exit_order.alive():
            return

        if hasattr(self.stats, 'drawdown'):
            dd = self.stats.drawdown.drawdown[0]
            if dd > self.params.max_drawdown:
                return

        if self.position:
            if self._force_time_exit_if_needed():
                return
            return

        if not self._is_live_bar_fresh():
            return
        if self.data_ltf.islive() and not getattr(self, '_warmup_finished', False):
            self._warmup_finished = True
            logger.info("🚀 [FastTestStrategy] WARM-UP COMPLETE. FIRING TEST TRADES...")

        bar_num = len(self.data_ltf)
        n = max(1, int(self.params.force_signal_every_n_bars or 1))
        if bar_num == self._last_signal_bar:
            return
        if bar_num % n != 0:
            return

        close = float(self.data_ltf.close[0])
        atr = float(self.atr[0]) if self.atr[0] == self.atr[0] else 0.0
        if atr <= 0:
            # Keep strategy deterministic even during initial ATR warm-up edge cases.
            atr = max(close * 0.0005, 1.0)

        sl_dist = atr * float(self.params.sl_mult)
        tp_dist = atr * float(self.params.tp_mult)
        go_long = (self._signal_count % 2 == 0)
        self._signal_count += 1
        self._last_signal_bar = bar_num

        if go_long:
            sl_ref = close - sl_dist
            tp_ref = close + tp_dist
            size = self._pick_size(close, sl_ref)
            if size <= 0:
                return
            self.pending_metadata = {
                'reason': 'Fast-Test LONG',
                'stop_loss': sl_ref,
                'take_profit': tp_ref,
                'sl_distance': sl_dist,
                'tp_distance': tp_dist,
                'direction': 'long',
                'size': size,
                'sl_calculation': f'ATR({self.params.atr_period}) * {self.params.sl_mult}',
                'tp_calculation': f'ATR({self.params.atr_period}) * {self.params.tp_mult}',
                'entry_context': None,
            }
            self.initial_sl = sl_ref
            self.stop_reason = 'Stop Loss'
            self.sl_history = [{'time': _iso_utc(self.data_ltf.datetime.datetime(0)), 'price': sl_ref, 'reason': 'Initial Stop Loss'}]
            logger.info(f"SIGNAL GENERATED: LONG Entry={close:.2f} SL={sl_ref:.2f} TP={tp_ref:.2f} Size={size:.4f}")
            self.order = self.buy(size=size, exectype=bt.Order.Market)
            return

        sl_ref = close + sl_dist
        tp_ref = close - tp_dist
        size = self._pick_size(close, sl_ref)
        if size <= 0:
            return
        self.pending_metadata = {
            'reason': 'Fast-Test SHORT',
            'stop_loss': sl_ref,
            'take_profit': tp_ref,
            'sl_distance': sl_dist,
            'tp_distance': tp_dist,
            'direction': 'short',
            'size': size,
            'sl_calculation': f'ATR({self.params.atr_period}) * {self.params.sl_mult}',
            'tp_calculation': f'ATR({self.params.atr_period}) * {self.params.tp_mult}',
            'entry_context': None,
        }
        self.initial_sl = sl_ref
        self.stop_reason = 'Stop Loss'
        self.sl_history = [{'time': _iso_utc(self.data_ltf.datetime.datetime(0)), 'price': sl_ref, 'reason': 'Initial Stop Loss'}]
        logger.info(f"SIGNAL GENERATED: SHORT Entry={close:.2f} SL={sl_ref:.2f} TP={tp_ref:.2f} Size={size:.4f}")
        self.order = self.sell(size=size, exectype=bt.Order.Market)
