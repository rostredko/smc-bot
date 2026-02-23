import backtrader as bt
from .base_strategy import BaseStrategy
from engine.logger import get_logger

logger = get_logger(__name__)

class PriceActionStrategy(BaseStrategy):
    """
    Backtrader implementation of PriceActionStrategy.
    """
    params = (
        ('min_range_factor', 0.8),
        ('min_wick_to_range', 0.6),
        ('max_body_to_range', 0.3),
        ('risk_reward_ratio', 2.5),
        ('sl_buffer_atr', 0.5),
        ('atr_period', 14),
        ('use_trend_filter', True),
        ('trend_ema_period', 200),
        ('use_rsi_filter', False),
        ('rsi_period', 14),
        ('rsi_overbought', 70),
        ('rsi_oversold', 30),
        ('use_rsi_momentum', False),
        ('rsi_momentum_threshold', 60),
        ('use_adx_filter', False),
        ('adx_period', 14),
        ('adx_threshold', 21),
        ('trailing_stop_distance', 0.0),
        ('breakeven_trigger_r', 0.0),
        ('risk_per_trade', 1.0),
        ('leverage', 1.0),
        ('dynamic_position_sizing', True),
        ('max_drawdown', 50.0),
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
        self.cdl_shootingstar = bt.talib.CDLSHOOTINGSTAR(self.data_ltf.open, self.data_ltf.high, self.data_ltf.low, self.data_ltf.close)
        self.open = self.data_ltf.open
        self.high = self.data_ltf.high
        self.low = self.data_ltf.low
        self.close = self.data_ltf.close
        self.last_entry_bar = -1




    def next(self):
        if self.order:
            return

        if not self.position:
            self.initial_sl = None

        if hasattr(self.stats, 'drawdown'):
             dd = self.stats.drawdown.drawdown[0]
             if dd > self.params.max_drawdown:
                 if not getattr(self, '_dd_limit_hit', False):
                     logger.warning(f"[{self.data_ltf.datetime.date(0).isoformat()}] CRITICAL: Max Drawdown {dd:.2f}% exceeded limit {self.params.max_drawdown}%. Stopping trading.")
                     self._dd_limit_hit = True
                 return

        if self.position and self.stop_order:
             current_sl = self.stop_order.price
             new_sl = current_sl
             sl_changed = False
             new_reason = self.stop_reason

             if self.params.breakeven_trigger_r > 0 and self.initial_sl is not None:
                 risk = abs(self.position.price - self.initial_sl)
                 if risk > 0:
                     profit = 0
                     if self.position.size > 0:
                         profit = self.close[0] - self.position.price
                     else:
                         profit = self.position.price - self.close[0]
                     
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
                    dist = self.close[0] * self.params.trailing_stop_distance
                    trail_price = self.close[0] - dist
                    if trail_price > new_sl:
                        new_sl = trail_price
                        sl_changed = True
                        new_reason = "Trailing Stop"

                 elif self.position.size < 0:
                    dist = self.close[0] * self.params.trailing_stop_distance
                    trail_price = self.close[0] + dist
                    if trail_price < new_sl:
                        new_sl = trail_price
                        sl_changed = True
                        new_reason = "Trailing Stop"

             if sl_changed:
                 logger.info(f"[{self.data_ltf.datetime.date(0).isoformat()}] STOP UPDATE: {new_reason} -> {new_sl:.2f}")
                 self.cancel_reason = f"{new_reason} Update"
                 
                 tp_price_val = None
                 if self.tp_order:
                     tp_price_val = self.tp_order.price
                     self.cancel(self.tp_order)
                     self.tp_order = None
                     
                 self.cancel(self.stop_order)
                 self.stop_reason = new_reason
                 
                 self.sl_history.append({
                     'time': self.data_ltf.datetime.datetime(0).isoformat(),
                     'price': new_sl,
                     'reason': new_reason
                 })
                 
                 # Recreate both orders linked via OCO
                 if self.position.size > 0:
                     self.stop_order = self.sell(price=new_sl, exectype=bt.Order.Stop, size=self.position.size)
                     if tp_price_val is not None:
                         self.tp_order = self.sell(price=tp_price_val, exectype=bt.Order.Limit, size=self.position.size, oco=self.stop_order)
                 else:
                     self.stop_order = self.buy(price=new_sl, exectype=bt.Order.Stop, size=abs(self.position.size))
                     if tp_price_val is not None:
                         self.tp_order = self.buy(price=tp_price_val, exectype=bt.Order.Limit, size=abs(self.position.size), oco=self.stop_order)
                 


        if self.position:
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
        """
        Build entry context: why entry was decided here + indicator values at entry.
        Only includes indicators that are enabled in strategy config.
        """
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
        """
        Build exit context: why exit was decided + indicator values at exit.
        Same structure as entry_context for consistency.
        """
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
        sl_price = self.low[0] - sl_buffer
        risk = self.close[0] - sl_price
        tp_distance = risk * self.params.risk_reward_ratio
        tp_price = self.close[0] + tp_distance
        self.last_entry_bar = len(self.data_ltf)
        size = self._calculate_position_size(self.close[0], sl_price)
        
        dt_str = self.data_ltf.datetime.date(0).isoformat()
        logger.info(f"[{dt_str}] SIGNAL GENERATED: LONG Entry={self.close[0]:.2f} SL={sl_price:.2f} TP={tp_price:.2f} Size={size:.4f} Reason={reason}")
        entry_context = self._build_entry_context(reason, 'long')
        sl_calc = (
            f"Math: Low ({self.low[0]:.2f}) - (ATR ({atr:.2f}) * Buffer ({self.params.sl_buffer_atr}))\n"
            f"Result: {sl_price:.2f}\n"
            f"---\n"
            f"Low: Lowest price of setup candle\n"
            f"ATR: Average True Range (Volatility) (Atr Period: {self.params.atr_period})\n"
            f"Buffer: Safety margin multiplier (Sl Buffer Atr: {self.params.sl_buffer_atr})"
        )
        tp_calc = (
            f"Math: Entry ({self.close[0]:.2f}) + (Risk ({risk:.2f}) * RR ({self.params.risk_reward_ratio}))\n"
            f"Result: {tp_price:.2f}\n"
            f"---\n"
            f"Entry: Close price of setup candle\n"
            f"Risk: Distance to Stop Loss\n"
            f"RR: Risk to Reward Ratio (Risk Reward Ratio: {self.params.risk_reward_ratio})"
        )
        self.pending_metadata = {
            'reason': reason,
            'stop_loss': sl_price, 
            'take_profit': tp_price,
            'sl_calculation': sl_calc,
            'tp_calculation': tp_calc,
            'entry_context': entry_context
        }
        self.initial_sl = sl_price
        self.stop_reason = "Stop Loss" # Reset stop reason for new trade
        
        # Initialize SL history with full ISO datetime for chart visualisation
        self.sl_history = [{
            'time': self.data_ltf.datetime.datetime(0).isoformat(),
            'price': sl_price,
            'reason': 'Initial Stop Loss'
        }]
        orders = self.buy_bracket(
            price=self.close[0], 
            stopprice=sl_price, 
            limitprice=tp_price,
            exectype=bt.Order.Market,
            size=size
        )
        
        # Handle potential nested list return from bracket order
        if len(orders) > 0 and isinstance(orders[0], list):
             orders = orders[0]
        
        # Expecting [Main, Stop, Limit] from bracket
        self.order = orders[0]
        self.stop_order = orders[1]
        self.tp_order = orders[2] if len(orders) > 2 else None
             
        # Add metadata to the main order for the analyzer to pick up
        self.order.addinfo(
            reason=reason,
            stop_loss=sl_price,
            take_profit=tp_price,
            risk_reward=self.params.risk_reward_ratio,
            sl_calculation=sl_calc,
            tp_calculation=tp_calc
        )

    def _enter_short(self, reason):
        atr = self.atr[0]
        sl_buffer = atr * self.params.sl_buffer_atr
        sl_price = self.high[0] + sl_buffer
        risk = sl_price - self.close[0]
        tp_distance = risk * self.params.risk_reward_ratio
        tp_price = self.close[0] - tp_distance
        
        # Churn prevention
        self.last_entry_bar = len(self.data_ltf)
        
        # Calculate Position Size
        size = self._calculate_position_size(self.close[0], sl_price)
        
        dt_str = self.data_ltf.datetime.date(0).isoformat()
        logger.info(f"[{dt_str}] SIGNAL GENERATED: SHORT Entry={self.close[0]:.2f} SL={sl_price:.2f} TP={tp_price:.2f} Size={size:.4f} Reason={reason}")
        
        # Entry context for detailed trade view
        entry_context = self._build_entry_context(reason, 'short')
        
        # Calculation strings for tooltip
        sl_calc = (
            f"Math: High ({self.high[0]:.2f}) + (ATR ({atr:.2f}) * Buffer ({self.params.sl_buffer_atr}))\n"
            f"Result: {sl_price:.2f}\n"
            f"---\n"
            f"High: Highest price of setup candle\n"
            f"ATR: Average True Range (Volatility) (Atr Period: {self.params.atr_period})\n"
            f"Buffer: Safety margin multiplier (Sl Buffer Atr: {self.params.sl_buffer_atr})"
        )
        tp_calc = (
            f"Math: Entry ({self.close[0]:.2f}) - (Risk ({risk:.2f}) * RR ({self.params.risk_reward_ratio}))\n"
            f"Result: {tp_price:.2f}\n"
            f"---\n"
            f"Entry: Close price of setup candle\n"
            f"Risk: Distance to Stop Loss\n"
            f"RR: Risk to Reward Ratio (Risk Reward Ratio: {self.params.risk_reward_ratio})"
        )

        self.pending_metadata = {
            'reason': reason,
            'stop_loss': sl_price, 
            'take_profit': tp_price,
            'sl_calculation': sl_calc,
            'tp_calculation': tp_calc,
            'entry_context': entry_context
        }
        self.initial_sl = sl_price
        self.stop_reason = "Stop Loss" # Reset stop reason for new trade
        
        # Initialize SL history with full ISO datetime for chart visualisation
        self.sl_history = [{
            'time': self.data_ltf.datetime.datetime(0).isoformat(),
            'price': sl_price,
            'reason': 'Initial Stop Loss'
        }]
        
        orders = self.sell_bracket(
            price=self.close[0], 
            stopprice=sl_price, 
            limitprice=tp_price,
            exectype=bt.Order.Market,
            size=size
        )
        
        # Handle potential nested list return from bracket order
        if len(orders) > 0 and isinstance(orders[0], list):
             orders = orders[0]
        
        # Expecting [Main, Stop, Limit] from bracket
        self.order = orders[0]
        self.stop_order = orders[1]
        self.tp_order = orders[2] if len(orders) > 2 else None

        # Add metadata to the main order for the analyzer to pick up
        self.order.addinfo(
            reason=reason,
            stop_loss=sl_price,
            take_profit=tp_price,
            risk_reward=self.params.risk_reward_ratio,
            sl_calculation=sl_calc,
            tp_calculation=tp_calc
        )

    def _has_significant_range(self):
        rng = self.high[0] - self.low[0]
        return rng >= (self.atr[0] * self.params.min_range_factor)

    def _is_bullish_pinbar(self):
        return self.cdl_hammer[0] == 100 and self._has_significant_range()

    def _is_bearish_pinbar(self):
        return self.cdl_shootingstar[0] == -100 and self._has_significant_range()

    def _is_bullish_engulfing(self):
        return self.cdl_engulfing[0] == 100 and self._has_significant_range()

    def _is_bearish_engulfing(self):
        return self.cdl_engulfing[0] == -100 and self._has_significant_range()

    def _check_filters_long(self):
        if self.position: return False
        if self.last_entry_bar == len(self.data_ltf): return False
        
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
        if self.position: return False
        if self.last_entry_bar == len(self.data_ltf): return False

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


