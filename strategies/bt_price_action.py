import backtrader as bt

class PriceActionStrategy(bt.Strategy):
    """
    Backtrader implementation of PriceActionStrategy.
    """
    params = (
        # Pattern Settings
        ('min_range_factor', 0.8),
        ('min_wick_to_range', 0.6),
        ('max_body_to_range', 0.3),
        
        # Risk / Targets
        ('risk_reward_ratio', 2.0),
        ('sl_buffer_atr', 0.5),

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
        
    )

    def __init__(self):
        self.ema = bt.indicators.EMA(period=self.params.trend_ema_period)
        self.rsi = bt.indicators.RSI(period=self.params.rsi_period)
        self.atr = bt.indicators.ATR(period=14)
        
        # ADX (New addition to match config)
        self.adx = bt.indicators.ADX(period=self.params.adx_period)
        
        # Helper for patterns
        self.open = self.data.open
        self.high = self.data.high
        self.low = self.data.low
        self.close = self.data.close
        
        # Order management
        self.order = None
        self.stop_order = None
        
        # Metadata tracking
        self.trade_map = {}
        self.pending_metadata = None

    def get_trade_info(self, trade_ref):
        info = self.trade_map.get(trade_ref, {})
        # print(f"DEBUG: Strategy.get_trade_info({trade_ref}) returning: {info}")
        return info

    def notify_trade(self, trade):
        if trade.justopened:
            # print(f"DEBUG: Trade OPENED ref={trade.ref}. Pending: {self.pending_metadata}")
            # Capture size here as it is available when trade opens
            current_size = abs(trade.size)
            
            if self.pending_metadata:
                self.pending_metadata['size'] = current_size # Add size to metadata
                self.trade_map[trade.ref] = self.pending_metadata
                # self.pending_metadata = None 
            else:
                # If no pending metadata (shouldn't happen), at least store size
                self.trade_map[trade.ref] = {'size': current_size} 
                
    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            # Buy/Sell order submitted/accepted to/by broker - Nothing to do
            return

        # Check if an order has been completed
        # Attention: broker could reject order if not enough cash
        if order.status in [order.Completed]:
            dt_str = self.data.datetime.date(0).isoformat()
            if order.isbuy():
                print(f"[{dt_str}] BUY EXECUTED, Price: {order.executed.price:.2f}, Cost: {order.executed.value:.2f}, Comm {order.executed.comm:.2f}")
            elif order.issell():
                print(f"[{dt_str}] SELL EXECUTED, Price: {order.executed.price:.2f}, Cost: {order.executed.value:.2f}, Comm {order.executed.comm:.2f}")
            
            self.bar_executed = len(self)
            
            # If the main order is completed, we might want to reset stop_order tracking if we were strictly tracking the main order
            # But bracket orders handle themselves mostly. We only need stop_order for trailing.
            
            # Defensive check (just in case)
            if isinstance(self.order, list):
                 self.order = self.order[0]

            if order == self.order:
                 self.order = None # Main order completed

        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            dt_str = self.data.datetime.date(0).isoformat()
            print(f"[{dt_str}] Order Canceled/Margin/Rejected")
            
            # Reset tracking if orders are canceled
            if order == self.stop_order:
                self.stop_order = None

        # Write down: no pending order
        # self.order = None # Don't reset here blindly as we might be tracking position

    def next(self):
        # Check if an order is pending - if so, we cannot send a 2nd one
        if self.order:
            return
            
        # Trailing Stop Logic
        if self.position and self.params.trailing_stop_distance > 0 and self.stop_order:
            if self.position.size > 0: # Long
                # Calculate new stop price
                # If trailing_stop_distance is < 1, assume percentage (e.g. 0.02 for 2%)
                # If > 1, assume absolute price distance? Usually safe to assume percentage for crypto
                # Let's support both: < 1 is percent, >= 1 is absolute? Or just assume percent as per previous context?
                # User config had 0.02 default, so it's likely percent.
                
                dist = self.close[0] * self.params.trailing_stop_distance
                new_stop_price = self.close[0] - dist
                
                if new_stop_price > self.stop_order.price:
                    # Move stop up
                    self.cancel(self.stop_order)
                    self.stop_order = self.sell(price=new_stop_price, exectype=bt.Order.Stop, size=self.position.size)
                    dt_str = self.data.datetime.date(0).isoformat()
                    # print(f"[{dt_str}] Trailing Stop Moved Up to {new_stop_price:.2f}")

            elif self.position.size < 0: # Short
                dist = self.close[0] * self.params.trailing_stop_distance
                new_stop_price = self.close[0] + dist
                
                if new_stop_price < self.stop_order.price:
                    # Move stop down
                    self.cancel(self.stop_order)
                    self.stop_order = self.buy(price=new_stop_price, exectype=bt.Order.Stop, size=abs(self.position.size))
                    dt_str = self.data.datetime.date(0).isoformat()
                    # print(f"[{dt_str}] Trailing Stop Moved Down to {new_stop_price:.2f}")


        # 1. Pattern Detection
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
        sl_price = self.low[0] - (atr * self.params.sl_buffer_atr)
        risk = self.close[0] - sl_price
        tp_price = self.close[0] + (risk * self.params.risk_reward_ratio)
        
        dt_str = self.data.datetime.date(0).isoformat()
        print(f"[{dt_str}] SIGNAL GENERATED: LONG Entry={self.close[0]:.2f} SL={sl_price:.2f} TP={tp_price:.2f} Reason={reason}")
        
        # Prepare metadata for the trade
        self.pending_metadata = {
            'reason': reason,
            'stop_loss': sl_price, 
            'take_profit': tp_price
        }

        # Use bracket order for atomic execution assurance
        orders = self.buy_bracket(
            price=self.close[0], 
            stopprice=sl_price, 
            limitprice=tp_price,
            exectype=bt.Order.Market # Entry at Market
        )
        
        # Handle potential nested list return from bracket order
        if len(orders) > 0 and isinstance(orders[0], list):
             self.order = orders[0][0]
             self.stop_order = orders[0][1]
        else:
             self.order = orders[0]
             self.stop_order = orders[1]
             
        # Add metadata to the main order for the analyzer to pick up
        self.order.addinfo(
            reason=reason,
            stop_loss=sl_price,
            take_profit=tp_price,
            risk_reward=self.params.risk_reward_ratio
        )

    def _enter_short(self, reason):
        atr = self.atr[0]
        sl_price = self.high[0] + (atr * self.params.sl_buffer_atr)
        risk = sl_price - self.close[0]
        tp_price = self.close[0] - (risk * self.params.risk_reward_ratio)
        
        dt_str = self.data.datetime.date(0).isoformat()
        print(f"[{dt_str}] SIGNAL GENERATED: SHORT Entry={self.close[0]:.2f} SL={sl_price:.2f} TP={tp_price:.2f} Reason={reason}")
        
        self.pending_metadata = {
            'reason': reason,
            'stop_loss': sl_price, 
            'take_profit': tp_price
        }
        
        orders = self.sell_bracket(
            price=self.close[0], 
            stopprice=sl_price, 
            limitprice=tp_price,
            exectype=bt.Order.Market
        )
        
        # Handle potential nested list return from bracket order
        if len(orders) > 0 and isinstance(orders[0], list):
             self.order = orders[0][0]
             self.stop_order = orders[0][1]
        else:
             self.order = orders[0]
             self.stop_order = orders[1]

        # Add metadata to the main order for the analyzer to pick up
        self.order.addinfo(
            reason=reason,
            stop_loss=sl_price,
            take_profit=tp_price,
            risk_reward=self.params.risk_reward_ratio
        )

    def _is_bullish_pinbar(self):
        # Logic: Small body, long lower wick
        body = abs(self.close[0] - self.open[0])
        rng = self.high[0] - self.low[0]
        if rng == 0: return False
        
        lower_wick = min(self.open[0], self.close[0]) - self.low[0]
        
        return (
            body < self.params.max_body_to_range * rng and 
            lower_wick > self.params.min_wick_to_range * rng
        )

    def _is_bearish_pinbar(self):
        body = abs(self.close[0] - self.open[0])
        rng = self.high[0] - self.low[0]
        if rng == 0: return False
        
        upper_wick = self.high[0] - max(self.open[0], self.close[0])
        
        return (
            body < self.params.max_body_to_range * rng and 
            upper_wick > self.params.min_wick_to_range * rng
        )

    def _is_bullish_engulfing(self):
        # Prev red, curr green, curr body covers prev body
        if self.close[-1] < self.open[-1] and self.close[0] > self.open[0]:
            return (
                self.close[0] >= self.open[-1] and 
                self.open[0] <= self.close[-1]
            )
        return False

    def _is_bearish_engulfing(self):
        # Prev green, curr red, curr body covers prev body
        if self.close[-1] > self.open[-1] and self.close[0] < self.open[0]:
             return (
                self.close[0] <= self.open[-1] and 
                self.open[0] >= self.close[-1]
            )
        return False

    def _check_filters_long(self):
        if self.position: return False # Already in position
        
        if self.params.use_trend_filter:
            if self.close[0] < self.ema[0]: return False
            
        if self.params.use_rsi_filter:
            if self.rsi[0] > self.params.rsi_overbought: return False
            
        return True

    def _check_filters_short(self):
        if self.position: return False

        if self.params.use_trend_filter:
            if self.close[0] > self.ema[0]: return False

        if self.params.use_rsi_filter:
            if self.rsi[0] < self.params.rsi_oversold: return False
            
        return True


