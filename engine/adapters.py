
import pandas as pd
from backtesting import Strategy
from strategies.base_strategy import StrategyBase

class BacktestingAdapter(Strategy):
    """
    Adapter class to run existing strategies (inheriting from StrategyBase)
    within the backtesting.py engine.
    """
    
    # Class-level variable to pass the strategy class and config
    # This is a requirement of backtesting.py which instantiates the strategy class itself
    target_strategy_class = None 
    target_strategy_config = {}

    def init(self):
        """
        Initialize the adapter.
        Instantiates the actual target strategy (e.g., PriceActionStrategy).
        """
        if self.target_strategy_class is None:
            raise ValueError("target_strategy_class must be set before running backtest")
            
        # Instantiate the real strategy
        self.strategy: StrategyBase = self.target_strategy_class(self.target_strategy_config)
        self.strategy.reset_state()
        
        # Helper for partial exits mapping if needed
        # Helper for partial exits mapping if needed
        self.param_mapping = {}
        
        # Tracking for legacy logging
        self.last_closed_trades = 0
        self.last_open_trades = []
        self._initial_capital = self.target_strategy_config.get('initial_capital', 10000.0)
        
        # scaling detection
        self.scale_factor = 1.0
        try:
            reference_price = self.target_strategy_config.get('reference_price')
            if reference_price and len(self.data.Close) > 0:
                internal_price = self.data.Close[0]
                if internal_price > 0:
                    raw_factor = reference_price / internal_price
                    # Check if factor is significant (power of 10)
                    if raw_factor > 100: # Arbitrary threshold to detect scaling
                        self.scale_factor = raw_factor
        except Exception as e:
            print(f"Failed to calculate scale factor: {e}")
            
        # Reason tracking
        self.trade_reasons = {} # Map (entry_time, entry_price) -> Reason string
        self.last_signal_reason = "Signal" # Default


    @property
    def _current_idx(self):
        """
        Robust accessor for current step index.
        In backtesting.py, self.data grows (or tracks) current step.
        len(self.data) gives the number of bars seen so far.
        The last valid index is len(self.data) - 1.
        """
        return len(self.data) - 1

    def next(self):
        """
        Executed on every bar.
        Constructs the data slice and calls the strategy's generate_signals.
        """
        # 1. Prepare Data Slice
        # We need to construct a robust slice of data ending at current bar
        # backtesting.py's self.data contains all data, but we must only look back
        # from current step
        
        config_lookback = self.target_strategy_config.get('recent_data_lookback_bars', 200)
        lookback = max(200, config_lookback) # Ensure minimum context
        
        config_lookback = self.target_strategy_config.get('recent_data_lookback_bars', 200)
        lookback = max(200, config_lookback) # Ensure minimum context
        
        # Robustly get current index
        current_idx = self._current_idx
        start_idx = max(0, current_idx - lookback + 1)
        
        # Access internal pandas index if possible
        # self.data.index contains the full index
        slice_index = self.data.index[start_idx : current_idx + 1]
        
        # Construct DataFrame slice
        df_slice = pd.DataFrame({
            'open': self.data.Open[start_idx : current_idx + 1],
            'high': self.data.High[start_idx : current_idx + 1],
            'low': self.data.Low[start_idx : current_idx + 1],
            'close': self.data.Close[start_idx : current_idx + 1],
            'volume': self.data.Volume[start_idx : current_idx + 1]
        }, index=slice_index)
    
        # Mock multi-timeframe structure (PoC simplified)
        # In future, we can resample `df_slice` if needed
        primary_tf = self.target_strategy_config.get('primary_timeframe', '1h')
        market_data = {
            primary_tf: df_slice
        }
    
        # --- Legacy Logging Emulation ---
        current_time = self.data.index[current_idx]
        
        # Capture strictly accurate close price from the slice we just built
        # This bypasses potential accessor issues with self.data.Close which is the full array
        try:
            # We can also trust self.data.Close[current_idx]
            self.last_known_close = self.data.Close[current_idx]
        except Exception:
            self.last_known_close = 0.0
            
        display_price = self.last_known_close * self.scale_factor
        
        # 1. Check for CLOSED trades
        if len(self.closed_trades) > self.last_closed_trades:
            for t in self.closed_trades[self.last_closed_trades:]:
                # CLOSE LONG @ $90459.35 ...
                direction = "LONG" if t.size > 0 else "SHORT"
                pnl_pct = t.pl_pct * 100
                equity = self.equity
                cap_change_pct = ((equity - self._initial_capital) / self._initial_capital) * 100
                
                exit_price_display = t.exit_price * self.scale_factor
                
                self._log(f"CLOSE {direction} @ ${exit_price_display:,.2f} — PnL=${t.pl:.2f} ({pnl_pct:.2f}%) | Balance: ${equity:,.2f} ({cap_change_pct:+.2f}% from initial ${self._initial_capital:,.2f})")
                
                # Capture detailed info for dashboard
                if hasattr(self, 'detailed_trades'):
                    exit_reason = "Signal/Manual"
                    # Heuristics for exit reason
                    if t.sl and abs(t.exit_price - t.sl) < (0.0001 * t.exit_price):
                        exit_reason = "Stop Loss"
                    elif t.tp and abs(t.exit_price - t.tp) < (0.0001 * t.exit_price):
                        exit_reason = "Take Profit"
                    
                    # Retrieve Entry Reason
                    reason_key = t.entry_time
                    entry_reason = self.trade_reasons.get(reason_key, "Signal")
                    
                    # DEBUG
                    # print(f"[DEBUG] Closing Trade Key: {reason_key} -> Reason: {entry_reason}")

                    BacktestingAdapter.detailed_trades.append({
                        "entry_time": t.entry_time,
                        "stop_loss": t.sl * self.scale_factor if t.sl else None,
                        "take_profit": t.tp * self.scale_factor if t.tp else None,
                        "exit_reason": exit_reason,
                        "reason": entry_reason # Entry reason from tracking
                    })
                
            self.last_closed_trades = len(self.closed_trades)
    
        # 2. Check for NEW OPEN trades
        # self.trades is a list of active Trade objects
        current_trade_count = len(self.trades)
        
        # Use a more robust key than id(): (entry_time, entry_price, size)
        current_trade_keys = { (t.entry_time, t.entry_price, t.size) for t in self.trades }
        last_trade_keys = { (t.entry_time, t.entry_price, t.size) for t in self.last_open_trades }
        
        new_keys = current_trade_keys - last_trade_keys
        
        if new_keys:
             for t in self.trades:
                 key = (t.entry_time, t.entry_price, t.size)
                 if key in new_keys:
                     # Track reason for this new trade
                     reason_key = t.entry_time
                     self.trade_reasons[reason_key] = self.last_signal_reason
                     
                     # DEBUG
                     # print(f"[DEBUG] New Trade Key: {reason_key} -> Reason: {self.last_signal_reason}")
                     
                     direction = "LONG" if t.size > 0 else "SHORT"
                     
                     # Risk calculation
                     risk_val = 0.0
                     sl_val = 0.0
                     if t.sl and pd.notna(t.sl) and t.sl > 0:
                         sl_val = t.sl
                         dist = abs(t.entry_price - t.sl)
                         risk_val = dist * abs(t.size)
                     
                     equity = self.equity
                     cap_change_pct = ((equity - self._initial_capital) / self._initial_capital) * 100
                     
                     
                     # Debug Info
                     current_price = self.last_known_close
                     if current_price == 0:
                         current_price = self._get_current_price()
                         
                     entry_price = t.entry_price
                     if pd.isna(entry_price) or entry_price == 0:
                         entry_price = current_price
    
                     # Risk calculation
                     risk_val = 0.0
                     sl_val = 0.0
                     if t.sl and pd.notna(t.sl) and t.sl > 0:
                         sl_val = t.sl
                         dist = abs(entry_price - t.sl)
                         risk_val = dist * abs(t.size)
                     
                     equity = self.equity
                     cap_change_pct = ((equity - self._initial_capital) / self._initial_capital) * 100
                     
                     # Format log
                     entry_price_display = entry_price * self.scale_factor
                     sl_display = sl_val * self.scale_factor
                     
                     self._log(f"OPEN {direction} {abs(t.size):.4f} @ ${entry_price_display:,.2f}, SL=${sl_display:,.2f}, Risk=${risk_val:.2f} | Balance: ${equity:,.2f} ({cap_change_pct:+.2f}% from initial ${self._initial_capital:,.2f})")
            
        self.last_open_trades = list(self.trades)
    
        # --------------------------------
    
        # 2. Generate Signals
        signals = self.strategy.generate_signals(market_data)
    
        # 3. Execution Logic
        self._process_signals(signals)
        self._manage_positions()

    def _log(self, message):
        """Helper to log messages with current simulation time."""
        try:
            current_time = self.data.index[self._current_idx]
            print(f"[{current_time}] {message}")
        except Exception:
            print(message)

    def _process_signals(self, signals):
        """Process signals from the strategy."""
        for signal in signals:
            direction = signal['direction']
            
            if direction == 'LONG':
                 if not self.position.is_long:
                     # Log signal for Dashboard
                     reason = signal.get("reason", "Unknown")
                     metadata = signal.get("metadata", {})
                     # Construct confidence from metadata or default
                     confidence = metadata.get("confidence", 0.0)
                     
                     current_price = self.last_known_close
                     if current_price == 0:
                         current_price = self._get_current_price()
                     
                     display_price = current_price * self.scale_factor
                     display_price = current_price * self.scale_factor
                     self._log(f"SIGNAL GENERATED: {direction} @ ${display_price:,.2f} (Confidence: {confidence:.2f}, Reason: {reason})")
                     
                     self.last_signal_reason = reason # Store for trade attribution


                     # Close short if any
                     if self.position.is_short:
                         self.position.close()
                         
                     # Open Long
                     sl = signal.get('stop_loss')
                     tp = signal.get('take_profit')
                     
                     # Dynamic Position Sizing
                     risk_per_trade = self.target_strategy_config.get('risk_per_trade', 2.0)
                     
                     # If SL is present, calculate size based on risk
                     if sl and sl < current_price:
                         risk_percent_decimal = risk_per_trade / 100.0
                         risk_distance = current_price - sl
                         
                         if risk_distance > 0:
                             # Formula: Fraction = (Risk% * Entry) / Dist
                             # Deriv: Risk$ = Equity * Risk%. Units = Risk$ / Dist.
                             # Position$ = Units * Entry. Fraction = Position$ / Equity.
                             # Subst: Fraction = ((Equity * Risk% / Dist) * Entry) / Equity
                             # Fraction = (Risk% * Entry) / Dist
                             raw_fraction = (risk_percent_decimal * current_price) / risk_distance
                             
                             # Clamp to avoid "Units vs Fraction" ambiguity in backtesting.py
                             # backtesting.py treats size >= 1 as units (must be int).
                             # We must stay < 1.0 to ensure percentage sizing.
                             # Cap at 0.99 (Almost max equity) or lower if you want to reserve cash
                             size = min(max(raw_fraction, 0.0001), 0.9999) 
                     
                     self.buy(sl=sl, tp=tp, size=size)
                     
            elif direction == 'SHORT':
                 if not self.position.is_short:
                     # Log signal for Dashboard
                     reason = signal.get("reason", "Unknown")
                     metadata = signal.get("metadata", {})
                     confidence = metadata.get("confidence", 0.0)
                     
                     current_price = self.last_known_close
                     if current_price == 0:
                         current_price = self._get_current_price()
                     
                     display_price = current_price * self.scale_factor
                     display_price = current_price * self.scale_factor
                     self._log(f"SIGNAL GENERATED: {direction} @ ${display_price:,.2f} (Confidence: {confidence:.2f}, Reason: {reason})")
                     
                     self.last_signal_reason = reason # Store for trade attribution

                     # Close long if any
                     if self.position.is_long:
                         self.position.close()
                         
                     # Open Short
                     sl = signal.get('stop_loss')
                     tp = signal.get('take_profit')
                     
                     risk_per_trade = self.target_strategy_config.get('risk_per_trade', 2.0)
                     
                     # If SL is present, calculate size based on risk
                     if sl and sl > current_price:
                         risk_percent_decimal = risk_per_trade / 100.0
                         risk_distance = sl - current_price
                         
                         if risk_distance > 0:
                             raw_fraction = (risk_percent_decimal * current_price) / risk_distance
                             size = min(max(raw_fraction, 0.0001), 0.9999)
                             
                     self.sell(sl=sl, tp=tp, size=size)
                     
            elif direction == 'EXIT':
                self.position.close()

    def _get_current_price(self):
        """Helper to get the last valid non-zero price relative to current step."""
        # Search backwards from self.I
        current_idx = self._current_idx
        for i in range(0, 5):
            idx = current_idx - i
            if idx >= 0 and idx < len(self.data.Close):
                price = self.data.Close[idx]
                if pd.notna(price) and price > 0:
                    return price
        return 0.0

    def _manage_positions(self):
        """
        Manage existing positions (e.g. check for ladder exits if we were doing that manually).
        backtesting.py handles SL/TP automatically if passed to buy/sell.
        This method is a placeholder for complex exit logic not covered by standard SL/TP.
        """
        pass
