import backtrader as bt
from .base_strategy import BaseStrategy
from engine.logger import get_logger

logger = get_logger(__name__)

class PriceActionStrategy(BaseStrategy):
    """
    Backtrader implementation of PriceActionStrategy.
    """
    params = (
        # Pattern Settings
        ('min_range_factor', 0.8),
        ('min_wick_to_range', 0.6),
        ('max_body_to_range', 0.3),
        
        # Risk / Targets
        ('risk_reward_ratio', 2.5),
        ('sl_buffer_atr', 0.5),
        ('atr_period', 14),

        # Trend Filter
        ('use_trend_filter', True),
        ('trend_ema_period', 200),

        # RSI Filter
        ('use_rsi_filter', False),
        ('rsi_period', 14),
        ('rsi_overbought', 70),
        ('rsi_oversold', 30),

        # RSI Momentum
        ('use_rsi_momentum', False),
        ('rsi_momentum_threshold', 60),

        # ADX Filter
        ('use_adx_filter', False),
        ('adx_period', 14),
        ('adx_threshold', 21),
        
        # Trailing Stop
        ('trailing_stop_distance', 0.0), # 0.0 = Disabled
        ('breakeven_trigger_r', 0.0), # 0.0 = Disabled
        
        # Risk Management
        ('risk_per_trade', 1.0), # Percent of equity
        ('leverage', 1.0),
        ('dynamic_position_sizing', True),
        ('max_drawdown', 50.0), # Percent
    )

    def __init__(self):
        super().__init__()
        
        # Dual Timeframe Setup:
        # Engine adds lower TF first → datas[0] = Lower TF (e.g. 15m)
        # Engine adds higher TF second → datas[1] = Higher TF (e.g. 4h)
        self.has_secondary = len(self.datas) > 1
        
        if self.has_secondary:
            self.data_ltf = self.datas[0]  # Lower timeframe (execution/patterns)
            self.data_htf = self.datas[1]  # Higher timeframe (trend/EMA)
        else:
            # Fallback: single data feed for everything
            self.data_htf = self.datas[0]
            self.data_ltf = self.datas[0]
        
        # Higher TF indicators (trend direction)
        self.ema_htf = bt.talib.EMA(self.data_htf.close, timeperiod=self.params.trend_ema_period)
        
        # Lower TF indicators (execution)
        self.rsi = bt.talib.RSI(self.data_ltf.close, timeperiod=self.params.rsi_period)
        self.atr = bt.talib.ATR(self.data_ltf.high, self.data_ltf.low, self.data_ltf.close, timeperiod=self.params.atr_period)
        self.adx = bt.talib.ADX(self.data_ltf.high, self.data_ltf.low, self.data_ltf.close, timeperiod=self.params.adx_period)
        
        # TA-Lib Pattern Indicators
        self.cdl_engulfing = bt.talib.CDLENGULFING(self.data_ltf.open, self.data_ltf.high, self.data_ltf.low, self.data_ltf.close)
        self.cdl_hammer = bt.talib.CDLHAMMER(self.data_ltf.open, self.data_ltf.high, self.data_ltf.low, self.data_ltf.close)
        self.cdl_shootingstar = bt.talib.CDLSHOOTINGSTAR(self.data_ltf.open, self.data_ltf.high, self.data_ltf.low, self.data_ltf.close)
        
        # Helper for patterns — always on lower TF
        self.open = self.data_ltf.open
        self.high = self.data_ltf.high
        self.low = self.data_ltf.low
        self.close = self.data_ltf.close
        
        # Churn prevention
        self.last_entry_bar = -1




    def next(self):
        # Check if an order is pending
        if self.order:
            return
            
        # Reset tracking if not in position
        if not self.position:
            self.initial_sl = None
            
        # 0. Check Max Drawdown
        if hasattr(self.stats, 'drawdown'):
             # Use [0] to get current value from the LineIterator (Observer)
             # 'drawdown' line contains the current drawdown percentage
             dd = self.stats.drawdown.drawdown[0]
             if dd > self.params.max_drawdown:
                 if not getattr(self, '_dd_limit_hit', False):
                     logger.warning(f"[{self.data_ltf.datetime.date(0).isoformat()}] CRITICAL: Max Drawdown {dd:.2f}% exceeded limit {self.params.max_drawdown}%. Stopping trading.")
                     self._dd_limit_hit = True
                 return 
                 
        # Trailing Stop & Breakeven Logic
        if self.position and self.stop_order:
             current_sl = self.stop_order.price
             new_sl = current_sl
             sl_changed = False
             new_reason = self.stop_reason

             # 1. Breakeven Check
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
                         # Update if BE price is better than current SL
                         if self.position.size > 0 and be_price > new_sl:
                             new_sl = be_price
                             sl_changed = True
                             new_reason = "Breakeven"
                             self.initial_sl = None # Mark BE as done
                         elif self.position.size < 0 and be_price < new_sl:
                             new_sl = be_price
                             sl_changed = True
                             new_reason = "Breakeven"
                             self.initial_sl = None # Mark BE as done

             # 2. Trailing Stop Check (Can overwrite BE if stricter)
             if self.params.trailing_stop_distance > 0:
                 if self.position.size > 0: # Long
                    dist = self.close[0] * self.params.trailing_stop_distance
                    trail_price = self.close[0] - dist
                    if trail_price > new_sl:
                        new_sl = trail_price
                        sl_changed = True
                        new_reason = "Trailing Stop"

                 elif self.position.size < 0: # Short
                    dist = self.close[0] * self.params.trailing_stop_distance
                    trail_price = self.close[0] + dist
                    if trail_price < new_sl:
                        new_sl = trail_price
                        sl_changed = True
                        new_reason = "Trailing Stop"

             # 3. Execute Single Update if needed
             if sl_changed:
                 logger.info(f"[{self.data_ltf.datetime.date(0).isoformat()}] STOP UPDATE: {new_reason} -> {new_sl:.2f}")
                 self.cancel_reason = f"{new_reason} Update"
                 
                 # Capture existing TP price before cancellation breaks the bracket
                 tp_price_val = None
                 if self.tp_order:
                     tp_price_val = self.tp_order.price
                     self.cancel(self.tp_order)
                     self.tp_order = None
                     
                 self.cancel(self.stop_order)
                 self.stop_reason = new_reason
                 
                 # Record SL update with full ISO datetime for chart visualisation
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
                 


        # Pattern Detection
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

    # ... (helper mehtods)

    def _enter_long(self, reason):
        atr = self.atr[0]
        sl_buffer = atr * self.params.sl_buffer_atr
        sl_price = self.low[0] - sl_buffer
        risk = self.close[0] - sl_price
        tp_distance = risk * self.params.risk_reward_ratio
        tp_price = self.close[0] + tp_distance
        
        # Churn prevention
        self.last_entry_bar = len(self.data_ltf)
        
        # Calculate Position Size
        size = self._calculate_position_size(self.close[0], sl_price)
        
        dt_str = self.data_ltf.datetime.date(0).isoformat()
        logger.info(f"[{dt_str}] SIGNAL GENERATED: LONG Entry={self.close[0]:.2f} SL={sl_price:.2f} TP={tp_price:.2f} Size={size:.4f} Reason={reason}")
        
        # Calculation strings for tooltip
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

        # Prepare metadata for the trade
        self.pending_metadata = {
            'reason': reason,
            'stop_loss': sl_price, 
            'take_profit': tp_price,
            'sl_calculation': sl_calc,
            'tp_calculation': tp_calc
        }
        self.initial_sl = sl_price
        self.stop_reason = "Stop Loss" # Reset stop reason for new trade
        
        # Initialize SL history with full ISO datetime for chart visualisation
        self.sl_history = [{
            'time': self.data_ltf.datetime.datetime(0).isoformat(),
            'price': sl_price,
            'reason': 'Initial Stop Loss'
        }]

        # Use bracket order for atomic execution assurance
        orders = self.buy_bracket(
            price=self.close[0], 
            stopprice=sl_price, 
            limitprice=tp_price,
            exectype=bt.Order.Market, # Entry at Market
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
            'tp_calculation': tp_calc
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
        if self.position: return False # Already in position
        if self.last_entry_bar == len(self.data_ltf): return False # Already attempted entry on this bar
        
        if self.params.use_trend_filter:
            if self.data_htf.close[0] < self.ema_htf[0]: return False
            
        if self.params.use_rsi_filter:
            if self.rsi[0] > self.params.rsi_overbought: return False

        if self.params.use_rsi_momentum:
            # RSI should be above threshold for bullish momentum
            # Default threshold 60 means we want strong momentum > 60
            if self.rsi[0] < self.params.rsi_momentum_threshold: return False

        if self.params.use_adx_filter:
            if self.adx[0] < self.params.adx_threshold: return False
            
        return True

    def _check_filters_short(self):
        if self.position: return False
        if self.last_entry_bar == len(self.data_ltf): return False # Already attempted entry on this bar

        if self.params.use_trend_filter:
             if self.data_htf.close[0] > self.ema_htf[0]: return False

        if self.params.use_rsi_filter:
            if self.rsi[0] < self.params.rsi_oversold: return False

        if self.params.use_rsi_momentum:
            # RSI should be below (100 - threshold) for bearish momentum
            # e.g. if threshold is 60, we want RSI < 40 for strong bearish momentum
            # detailed logic: 100 - 60 = 40.
            bearish_threshold = 100 - self.params.rsi_momentum_threshold
            if self.rsi[0] > bearish_threshold: return False

        if self.params.use_adx_filter:
            if self.adx[0] < self.params.adx_threshold: return False
            
        return True


