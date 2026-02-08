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
        
        # Risk Management
        ('risk_per_trade', 1.0), # Percent of equity
        ('leverage', 1.0),
        ('dynamic_position_sizing', True),
        ('max_drawdown', 50.0), # Percent
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
        self.initial_sl = None
        
        # Churn prevention
        self.last_entry_bar = -1

    def _calculate_position_size(self, entry_price, stop_loss):
        """
        Calculate position size based on risk per trade and account balance.
        """
        cash = self.broker.get_cash()
        value = self.broker.get_value()
        
        if not self.params.dynamic_position_sizing:
             # Fixed % of equity
             # Example: 10% of equity
             # Native BT Sizer would be better here but we want consistent interface
             # Let's say we use 'risk_per_trade' as the fixed % size of equity
             target_value = value * (self.params.risk_per_trade / 100.0)
             size = target_value / entry_price
        else:
            # Dynamic Risk-Based Sizing
            # Risk Amount = Equity * (Risk% / 100)
            risk_amount = value * (self.params.risk_per_trade / 100.0)
            
            risk_per_share = abs(entry_price - stop_loss)
            
            if risk_per_share == 0:
                return 0 # Should not happen
                
            size = risk_amount / risk_per_share
            
        # Apply Leverage Limit
        # Max Position Value = Equity * Leverage
        max_pos_value = value * self.params.leverage
        current_pos_value = size * entry_price
        
        if current_pos_value > max_pos_value:
            # Scale down to max leverage
            size = max_pos_value / entry_price
            # print(f"DEBUG: Position sized capped by leverage {self.params.leverage}x")

        return size

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
            info_str = f" Info: {order.info}" if order.info else ""
            if order.status == order.Canceled:
                print(f"[{dt_str}] ℹ️ Order Canceled (id={order.ref}){info_str}")
            elif order.status == order.Margin:
                print(f"[{dt_str}] ⛔ ORDER MARGIN ERROR (id={order.ref}) - Insufficient Cash?{info_str}")
            else:
                print(f"[{dt_str}] ⛔ ORDER REJECTED (id={order.ref}){info_str}")
            
            # Reset tracking if orders are canceled
            if order == self.stop_order:
                self.stop_order = None

        # Write down: no pending order
        # self.order = None # Don't reset here blindly as we might be tracking position

    # ... (helper mehtods)

    def next(self):
        # Check if an order is pending
        if self.order:
            return
            
        # Reset tracking if not in position
        if not self.position:
            self.initial_sl = None
            
        # 0. Check Max Drawdown
        if hasattr(self.stats, 'drawdown'):
             dd = self.stats.drawdown.max.drawdown
             if dd > self.params.max_drawdown:
                 if not getattr(self, '_dd_limit_hit', False):
                     print(f"[{self.data.datetime.date(0).isoformat()}] CRITICAL: Max Drawdown {dd:.2f}% exceeded limit {self.params.max_drawdown}%. Stopping trading.")
                     self._dd_limit_hit = True
                 return 
                 
        # Trailing Stop & Breakeven
        if self.position and self.stop_order:
             # Breakeven Logic
             if self.params.breakeven_trigger_r > 0 and self.initial_sl is not None:
                 risk = abs(self.position.price - self.initial_sl)
                 if risk > 0:
                     profit = 0
                     if self.position.size > 0:
                         profit = self.close[0] - self.position.price
                     else:
                         profit = self.position.price - self.close[0]
                     
                     if profit >= (risk * self.params.breakeven_trigger_r):
                         # Move to Breakeven
                         # Add a small buffer for commissions? Let's stick to pure entry price for now as per 'Breakeven'
                         new_sl = self.position.price
                         
                         # Check if we need to update
                         update_needed = False
                         if self.position.size > 0 and new_sl > self.stop_order.price:
                             update_needed = True
                         elif self.position.size < 0 and new_sl < self.stop_order.price:
                             update_needed = True
                             
                         if update_needed:
                             print(f"[{self.data.datetime.date(0).isoformat()}] BREAKEVEN TRIGGERED: Moving SL to {new_sl:.2f}")
                             self.cancel(self.stop_order)
                             if self.position.size > 0:
                                 self.stop_order = self.sell(price=new_sl, exectype=bt.Order.Stop, size=self.position.size)
                             else:
                                 self.stop_order = self.buy(price=new_sl, exectype=bt.Order.Stop, size=abs(self.position.size))
                             
                             self.initial_sl = None # Done
                             
        # Trailing Stop Logic (runs after or independent of BE)
        if self.position and self.params.trailing_stop_distance > 0 and self.stop_order:
             # ... existing trailing logic ...
             pass
             
             if self.position.size > 0: # Long
                dist = self.close[0] * self.params.trailing_stop_distance
                new_stop_price = self.close[0] - dist
                if new_stop_price > self.stop_order.price:
                    self.cancel(self.stop_order)
                    self.stop_order = self.sell(price=new_stop_price, exectype=bt.Order.Stop, size=self.position.size)
                    # print(f"[{self.data.datetime.date(0).isoformat()}] Trailing Stop Moved Up to {new_stop_price:.2f}")

             elif self.position.size < 0: # Short
                dist = self.close[0] * self.params.trailing_stop_distance
                new_stop_price = self.close[0] + dist
                if new_stop_price < self.stop_order.price:
                    self.cancel(self.stop_order)
                    self.stop_order = self.buy(price=new_stop_price, exectype=bt.Order.Stop, size=abs(self.position.size))
                    # print(f"[{self.data.datetime.date(0).isoformat()}] Trailing Stop Moved Down to {new_stop_price:.2f}")


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
        
        # Churn prevention
        self.last_entry_bar = len(self.data)
        
        # Calculate Position Size
        size = self._calculate_position_size(self.close[0], sl_price)
        
        dt_str = self.data.datetime.date(0).isoformat()
        print(f"[{dt_str}] SIGNAL GENERATED: LONG Entry={self.close[0]:.2f} SL={sl_price:.2f} TP={tp_price:.2f} Size={size:.4f} Reason={reason}")
        
        # Prepare metadata for the trade
        self.pending_metadata = {
            'reason': reason,
            'stop_loss': sl_price, 
            'take_profit': tp_price
        }
        self.initial_sl = sl_price

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
        
        # Churn prevention
        self.last_entry_bar = len(self.data)
        
        # Calculate Position Size
        size = self._calculate_position_size(self.close[0], sl_price)
        
        dt_str = self.data.datetime.date(0).isoformat()
        print(f"[{dt_str}] SIGNAL GENERATED: SHORT Entry={self.close[0]:.2f} SL={sl_price:.2f} TP={tp_price:.2f} Size={size:.4f} Reason={reason}")
        
        self.pending_metadata = {
            'reason': reason,
            'stop_loss': sl_price, 
            'take_profit': tp_price
        }
        self.initial_sl = sl_price
        
        orders = self.sell_bracket(
            price=self.close[0], 
            stopprice=sl_price, 
            limitprice=tp_price,
            exectype=bt.Order.Market,
            size=size
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
        if self.last_entry_bar == len(self.data): return False # Already attempted entry on this bar
        
        if self.params.use_trend_filter:
            if self.close[0] < self.ema[0]: return False
            
        if self.params.use_rsi_filter:
            if self.rsi[0] > self.params.rsi_overbought: return False

        if self.params.use_rsi_momentum:
            # RSI should be above 50 for bullish momentum
            if self.rsi[0] < 50: return False

        if self.params.use_adx_filter:
            if self.adx[0] < self.params.adx_threshold: return False
            
        return True

    def _check_filters_short(self):
        if self.position: return False
        if self.last_entry_bar == len(self.data): return False # Already attempted entry on this bar

        if self.params.use_trend_filter:
             if self.close[0] > self.ema[0]: return False

        if self.params.use_rsi_filter:
            if self.rsi[0] < self.params.rsi_oversold: return False

        if self.params.use_rsi_momentum:
            # RSI should be below 50 for bearish momentum
            if self.rsi[0] > 50: return False

        if self.params.use_adx_filter:
            if self.adx[0] < self.params.adx_threshold: return False
            
        return True


