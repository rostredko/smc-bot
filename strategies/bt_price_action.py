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
        self.tp_order = None # Track TP limit order separate from STOP
        
        # Metadata tracking
        self.trade_map = {}
        self.pending_metadata = None
        self.initial_sl = None
        
        # Churn prevention
        self.last_entry_bar = -1
        
        # Track cancellation reason
        self.cancel_reason = None
        
        # Track active stop reason (e.g. "Stop Loss", "Trailing Stop", "Breakeven")
        self.stop_reason = "Stop Loss"
        self.last_exit_reason = "Unknown"

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
        # print(f"📖 get_trade_info({trade_ref}) called. Result: {info}")
        # print(f"📋 Full trade_map: {self.trade_map}")
        return info

    def notify_trade(self, trade):
        if trade.justopened:
            current_size = abs(trade.size)
            # print(f"🔵 TRADE OPENED: ref={trade.ref}, size={current_size}, pending_metadata={self.pending_metadata}")
            
            if self.pending_metadata:
                # print(f"DEBUG: Mapping Trade {trade.ref} to metadata: {self.pending_metadata}")
                self.pending_metadata['size'] = current_size
                self.trade_map[trade.ref] = self.pending_metadata
                # print(f"🟢 STORED in trade_map[{trade.ref}]: {self.trade_map[trade.ref]}")
                self.pending_metadata = None 
            else:
                print(f"CRITICAL: Trade {trade.ref} opened WITHOUT metadata! Pending is None.")
                self.trade_map[trade.ref] = {'size': current_size} 
        
        elif trade.isclosed:
            # Calculate metrics for logging
            pnl = trade.pnl
            pnl_comm = trade.pnlcomm
            duration = (trade.dtclose - trade.dtopen)
            
            # Get size and calculating percentage
            entry_price = trade.price
            stored_info = self.trade_map.get(trade.ref, {})
            size = stored_info.get('size', 0)
            if size == 0 and len(trade.history) > 0:
                 size = trade.history[0].event.size
            
            pnl_pct = 0.0
            if entry_price > 0 and size != 0:
                 raw_move = pnl / size
                 pnl_pct = (raw_move / entry_price) * 100
            
            print(f"🔴 TRADE CLOSED [#{trade.ref}]: PnL: {pnl:.2f} ({pnl_pct:.2f}%) | Net: {pnl_comm:.2f} | Reason: {self.last_exit_reason} | Duration: {duration}")

            # Generate Narrative
            narrative = self._generate_trade_narrative(trade, self.last_exit_reason)
            
            if trade.ref in self.trade_map:
                self.trade_map[trade.ref]['exit_reason'] = self.last_exit_reason
                self.trade_map[trade.ref]['narrative'] = narrative
            else:
                self.trade_map[trade.ref] = {
                    'exit_reason': self.last_exit_reason,
                    'narrative': narrative
                }

    def _generate_trade_narrative(self, trade, exit_reason):
        """
        Generates a human-readable description of how the trade unfolded.
        """
        # Safer direction check using trade attribute
        direction = "Long" if trade.long else "Short"
        pnl = trade.pnl # Gross PnL
        result = "profit" if pnl > 0 else "loss"
        
        entry_price = trade.price
        price_diff_pct = 0.0
        
        # Get executed size from our own tracker (most reliable)
        # Fallback to history if missing (e.g. restart)
        stored_info = self.trade_map.get(trade.ref, {})
        size = stored_info.get('size', 0)
        
        if size == 0 and len(trade.history) > 0:
             size = trade.history[0].event.size
            
        if entry_price > 0 and size != 0:
             # PnL = (Exit - Entry) * Size
             # Price Move = PnL / Size
             # % Move = (Price Move / Entry) * 100
             raw_move = pnl / size
             price_diff_pct = abs((raw_move / entry_price) * 100)

        narrative = ""
        
        if exit_reason == "Take Profit":
            narrative = f"{direction} trade hit the Take Profit target perfectly. Price moved {price_diff_pct:.2f}% in favor, securing a solid win."
        elif exit_reason == "Stop Loss":
            narrative = f"{direction} trade hit the Stop Loss. Market moved against confidence immediately, resulting in a controlled loss."
        elif exit_reason == "Trailing Stop":
            if pnl > 0:
                narrative = f"{direction} trade followed the trend successfully. Price moved significantly in favor ({price_diff_pct:.2f}%), and the Trailing Stop locked in profits as the trend reversed."
            else:
                narrative = f"{direction} trade was closed by Trailing Stop. Price didn't gain enough momentum, closing with a slight result."
        elif exit_reason == "Breakeven":
            narrative = f"{direction} trade moved in favor but then reversed. The position was closed at Breakeven to protect capital."
        else:
             narrative = f"{direction} trade closed with {result}. Exit triggered by {exit_reason}."
             
        return narrative 
                
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
            
            # Check Exit Orders
            is_stop_order = (self.stop_order and order.ref == self.stop_order.ref)
            is_tp_order = (self.tp_order and order.ref == self.tp_order.ref)
            
            if is_stop_order:
                self.last_exit_reason = self.stop_reason
                print(f"[{dt_str}] EXIT TRIGGERED by {self.stop_reason} (Price: {order.executed.price:.2f})")
                
                # Cleanup sibling TP order if it exists
                if self.tp_order:
                    # check status to avoid double cancel?
                    # print(f"🧹 Cleanup: Cancelling sibling TP order {self.tp_order.ref}")
                    self.cancel(self.tp_order)
                    self.tp_order = None
                self.stop_order = None
                    
            elif is_tp_order:
                self.last_exit_reason = "Take Profit"
                print(f"[{dt_str}] EXIT TRIGGERED by Take Profit (Price: {order.executed.price:.2f})")
                
                # Cleanup sibling Stop order if it exists
                if self.stop_order:
                    # print(f"🧹 Cleanup: Cancelling sibling Stop order {self.stop_order.ref}")
                    self.cancel(self.stop_order)
                    self.stop_order = None
                self.tp_order = None
                
            elif self.order is None and not is_stop_order and not is_tp_order:
                # Fallback detection
                if self.stop_order and order.ref != self.stop_order.ref:
                     # Could be an untracked TP order from before
                     pass 
                # print(f"[{dt_str}] Order Completed. Ref: {order.ref}")

        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            dt_str = self.data.datetime.date(0).isoformat()
            info_str = f" Info: {order.info}" if order.info else ""
            if order.status == order.Canceled:
                reason = self.cancel_reason if self.cancel_reason else "OCO / Broker Internal"
                # print(f"[{dt_str}] ℹ️ Order Canceled (id={order.ref}) - Reason: {reason}{info_str}")
                self.cancel_reason = None # Reset
            elif order.status == order.Margin:
                print(f"[{dt_str}] ⛔ ORDER MARGIN ERROR - Insufficient Cash?{info_str}")
            else:
                print(f"[{dt_str}] ⛔ ORDER REJECTED {info_str}")
            
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
                             # print(f"[{self.data.datetime.date(0).isoformat()}] Breakeven condition met. Proposed SL: {new_sl:.2f}")
                             self.initial_sl = None # Mark BE as done
                         elif self.position.size < 0 and be_price < new_sl:
                             new_sl = be_price
                             sl_changed = True
                             new_reason = "Breakeven"
                             # print(f"[{self.data.datetime.date(0).isoformat()}] Breakeven condition met. Proposed SL: {new_sl:.2f}")
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
                        # print(f"[{self.data.datetime.date(0).isoformat()}] Trailing condition met. Proposed SL: {new_sl:.2f}")

                 elif self.position.size < 0: # Short
                    dist = self.close[0] * self.params.trailing_stop_distance
                    trail_price = self.close[0] + dist
                    if trail_price < new_sl:
                        new_sl = trail_price
                        sl_changed = True
                        new_reason = "Trailing Stop"
                        # print(f"[{self.data.datetime.date(0).isoformat()}] Trailing condition met. Proposed SL: {new_sl:.2f}")

             # 3. Execute Single Update if needed
             if sl_changed:
                 print(f"[{self.data.datetime.date(0).isoformat()}] STOP UPDATE: {new_reason} -> {new_sl:.2f}")
                 self.cancel_reason = f"{new_reason} Update"
                 self.cancel(self.stop_order)
                 self.stop_reason = new_reason
                 
                 if self.position.size > 0:
                     self.stop_order = self.sell(price=new_sl, exectype=bt.Order.Stop, size=self.position.size)
                 else:
                     self.stop_order = self.buy(price=new_sl, exectype=bt.Order.Stop, size=abs(self.position.size))
                 
                 # print(f"    -> New Stop Created. Ref (approx): {self.stop_order.ref}")


        # 1. Pattern Detection
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
        self.stop_reason = "Stop Loss" # Reset stop reason for new trade

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
        self.stop_reason = "Stop Loss" # Reset stop reason for new trade
        
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
            risk_reward=self.params.risk_reward_ratio
        )

    def _is_bullish_pinbar(self):
        # Logic: Small body, long lower wick
        body = abs(self.close[0] - self.open[0])
        rng = self.high[0] - self.low[0]
        if rng == 0: return False
        
        # Check if bar size is significant enough
        if rng < (self.atr[0] * self.params.min_range_factor): return False
        
        lower_wick = min(self.open[0], self.close[0]) - self.low[0]
        
        return (
            body < self.params.max_body_to_range * rng and 
            lower_wick > self.params.min_wick_to_range * rng
        )

    def _is_bearish_pinbar(self):
        body = abs(self.close[0] - self.open[0])
        rng = self.high[0] - self.low[0]
        if rng == 0: return False
        
        # Check if bar size is significant enough
        if rng < (self.atr[0] * self.params.min_range_factor): return False
        
        upper_wick = self.high[0] - max(self.open[0], self.close[0])
        
        return (
            body < self.params.max_body_to_range * rng and 
            upper_wick > self.params.min_wick_to_range * rng
        )

    def _is_bullish_engulfing(self):
        # Prev red, curr green, curr body covers prev body
        rng = self.high[0] - self.low[0]
        # Check if bar size is significant enough
        if rng < (self.atr[0] * self.params.min_range_factor): return False
        
        if self.close[-1] < self.open[-1] and self.close[0] > self.open[0]:
            return (
                self.close[0] >= self.open[-1] and 
                self.open[0] <= self.close[-1]
            )
        return False

    def _is_bearish_engulfing(self):
        # Prev green, curr red, curr body covers prev body
        rng = self.high[0] - self.low[0]
        # Check if bar size is significant enough
        if rng < (self.atr[0] * self.params.min_range_factor): return False
        
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
            # RSI should be above threshold for bullish momentum
            # Default threshold 60 means we want strong momentum > 60
            if self.rsi[0] < self.params.rsi_momentum_threshold: return False

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
            # RSI should be below (100 - threshold) for bearish momentum
            # e.g. if threshold is 60, we want RSI < 40 for strong bearish momentum
            # detailed logic: 100 - 60 = 40.
            bearish_threshold = 100 - self.params.rsi_momentum_threshold
            if self.rsi[0] > bearish_threshold: return False

        if self.params.use_adx_filter:
            if self.adx[0] < self.params.adx_threshold: return False
            
        return True


