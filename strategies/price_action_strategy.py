"""
Price Action Strategy Implementation.
Implements a pure price action trading strategy based on specific candlestick patterns:
- Pin Bar
- Engulfing
- Inside Bar
- Outside Bar
"""

from typing import Dict, List, Any, Optional
import pandas as pd
import numpy as np
from .base_strategy import StrategyBase


class PriceActionStrategy(StrategyBase):
    """
    Pure Price Action Strategy.
    Detects specific candlestick patterns and generates signals based on them.
    Includes optional trend filtering using EMA.
    """

    def __init__(self, config: Dict = None):
        """
        Initialize the strategy with configuration thresholds.
        
        Args:
            config: Strategy configuration dictionary with pattern thresholds
        """
        super().__init__(config)
        
        # Pattern Thresholds
        self.min_range_factor = self.config.get('min_range_factor', 0.8)
        self.max_body_to_range = self.config.get('max_body_to_range', 0.3)
        self.min_wick_to_range = self.config.get('min_wick_to_range', 0.6)
        
        # Engulfing/Inside/Outside specific
        self.min_range_factor_mother = self.config.get('min_range_factor_mother', 1.0)
        self.max_child_to_mother = self.config.get('max_child_to_mother', 0.6)
        self.min_expand_factor = self.config.get('min_expand_factor', 1.1)
        
        # Trend Filter
        self.use_trend_filter = self.config.get('use_trend_filter', True)
        self.trend_ema_period = self.config.get('trend_ema_period', 50)

        # RSI Filter
        self.use_rsi_filter = self.config.get('use_rsi_filter', True)
        self.rsi_period = self.config.get('rsi_period', 14)
        self.rsi_overbought = self.config.get('rsi_overbought', 70)
        self.rsi_oversold = self.config.get('rsi_oversold', 30)
        
        # Risk Management
        self.risk_reward_ratio = self.config.get('risk_reward_ratio', 2.5)
        self.sl_buffer_atr = self.config.get('sl_buffer_atr', 0.5)

        # ADX Filter
        self.use_adx_filter = self.config.get('use_adx_filter', False)
        self.adx_period = self.config.get('adx_period', 14)
        self.adx_period = self.config.get('adx_period', 14)
        self.adx_threshold = self.config.get('adx_threshold', 25)

        # RSI Momentum Filter (New)
        self.use_rsi_momentum = self.config.get('use_rsi_momentum', False)
        self.rsi_momentum_threshold = self.config.get('rsi_momentum_threshold', 50)

    def generate_signals(self, market_data: Dict[str, pd.DataFrame]) -> List[Dict[str, Any]]:
        """
        Generate signals based on price action patterns.
        Currently uses the lowest timeframe available or a specific configured one.
        """
        signals = []
        
        # Use the primary timeframe (e.g., '15m' or '1h')
        # If 'primary_timeframe' is in config, use it, else use the first key
        tf = self.config.get('primary_timeframe')
        if not tf:
             # Fallback to the first available timeframe
            tf = list(market_data.keys())[0] if market_data else None
            
        if not tf or tf not in market_data:
            return signals

        df = market_data[tf].copy()
        
        # Ensure we have enough data
        if len(df) < 50:
            return signals

        # 1. Prepare Data & Helpers
        df = self._add_candle_helpers(df)
        
        # 2. Add Trend Filter (EMA)
        if self.use_trend_filter:
            df['trend_ema'] = df['close'].ewm(span=self.trend_ema_period).mean()

        # 3. Add RSI Filter
        if self.use_rsi_filter:
            df = self._add_rsi(df, self.rsi_period)

        # 4. Add ADX Filter (Calculate ADX even if filter is off, useful for debugging/future)
        df = self._add_adx(df, self.adx_period)

        # 4. Detect Patterns
        df = self._detect_pin_bar(df)
        df = self._detect_engulfing(df)
        df = self._detect_inside_bar(df)
        df = self._detect_outside_bar(df)

        # 5. Generate Signal for the latest closed candle (iloc[-1])
        current_idx = df.index[-1]
        row = df.iloc[-1]
        
        signal = None
        pattern_name = ""
        stop_loss = 0.0
        
        # --- BULLISH SIGNAL LOGIC ---
        is_bullish = False
        
        if row['bullish_pinbar']:
            is_bullish = True
            pattern_name = "Bullish Pin Bar"
            stop_loss = row['low']
            
        elif row['bullish_engulfing']:
            is_bullish = True
            pattern_name = "Bullish Engulfing"
            stop_loss = min(row['low'], df.iloc[-2]['low']) # Low of both candles
            
        elif row['inside_bar_bullish_break']: 
            pass 

        elif row['bullish_outside_bar']:
            is_bullish = True
            pattern_name = "Bullish Outside Bar"
            stop_loss = row['low']

        # Filters Check
        if is_bullish:
            # Trend Filter
            if self.use_trend_filter and row['close'] < row['trend_ema']:
                is_bullish = False
            
            if self.use_rsi_filter and row['rsi'] > self.rsi_overbought:
                is_bullish = False

            # RSI Momentum Filter (Must be above 50 to confirm trend)
            if self.use_rsi_momentum and row['rsi'] < self.rsi_momentum_threshold:
                is_bullish = False

            # ADX Filter (Trend Strength)
            if self.use_adx_filter and 'adx' in row and row['adx'] < self.adx_threshold:
                is_bullish = False

        if is_bullish:
            atr = row.get('atr', row['range']) # Fallback if ATR not computed
            sl_price = stop_loss - (atr * self.sl_buffer_atr)
            risk = row['close'] - sl_price
            tp_price = row['close'] + (risk * self.risk_reward_ratio)
            
            signals.append({
                "direction": "LONG",
                "entry_price": row['close'],
                "stop_loss": sl_price,
                "take_profit": tp_price,
                "reason": f"{pattern_name} (Filters: EMA={self.use_trend_filter}, RSI={self.use_rsi_filter})",
                "metadata": {
                    "pattern": pattern_name,
                    "rsi": round(row['rsi'], 2) if 'rsi' in row else None,
                    "ema_trend": "BULLISH" if self.use_trend_filter and row['close'] > row['trend_ema'] else "N/A",
                    "adx": round(row['adx'], 2) if 'adx' in row else None,
                    "close_price": row['close'],
                    "trend_ema": round(row['trend_ema'], 2) if 'trend_ema' in row else None
                }
            })


        # --- BEARISH SIGNAL LOGIC ---
        is_bearish = False
        
        if row['bearish_pinbar']:
            is_bearish = True
            pattern_name = "Bearish Pin Bar"
            stop_loss = row['high']
            
        elif row['bearish_engulfing']:
            is_bearish = True
            pattern_name = "Bearish Engulfing"
            stop_loss = max(row['high'], df.iloc[-2]['high'])
            
        elif row['bearish_outside_bar']:
            is_bearish = True
            pattern_name = "Bearish Outside Bar"
            stop_loss = row['high']

        # Filters Check
        if is_bearish:
            # Trend Filter
            if self.use_trend_filter and row['close'] > row['trend_ema']:
                is_bearish = False
            
            if self.use_rsi_filter and row['rsi'] < self.rsi_oversold:
                is_bearish = False

            # RSI Momentum Filter (Must be below 50 to confirm trend)
            if self.use_rsi_momentum and row['rsi'] > (100 - self.rsi_momentum_threshold):
                is_bearish = False

            # ADX Filter (Trend Strength)
            if self.use_adx_filter and 'adx' in row and row['adx'] < self.adx_threshold:
                is_bearish = False

        if is_bearish:
            atr = row.get('atr', row['range'])
            sl_price = stop_loss + (atr * self.sl_buffer_atr)
            risk = sl_price - row['close']
            tp_price = row['close'] - (risk * self.risk_reward_ratio)
            
            signals.append({
                "direction": "SHORT",
                "entry_price": row['close'],
                "stop_loss": sl_price,
                "take_profit": tp_price,
                "reason": f"{pattern_name} (Filters: EMA={self.use_trend_filter}, RSI={self.use_rsi_filter})",
                "metadata": {
                    "pattern": pattern_name,
                    "rsi": round(row['rsi'], 2) if 'rsi' in row else None,
                    "ema_trend": "BEARISH" if self.use_trend_filter and row['close'] < row['trend_ema'] else "N/A",
                    "adx": round(row['adx'], 2) if 'adx' in row else None,
                    "close_price": row['close'],
                    "trend_ema": round(row['trend_ema'], 2) if 'trend_ema' in row else None
                }
            })

        return signals

    def _add_rsi(self, df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
        """Calculate RSI manually if ta lib not available."""
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean() # Simple RSI for speed/compat
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        
        # Wilder's Smoothing (More accurate standard RSI)
        # However, for simplicity and std library dep, let's use exponential moving average for smoothing logic similar to TA-Lib
        # gain = delta.where(delta > 0, 0).ewm(alpha=1/period, adjust=False).mean()
        # loss = -delta.where(delta < 0, 0).ewm(alpha=1/period, adjust=False).mean()
        # The above EWM method is standard for RSI.
        
        gain = delta.where(delta > 0, 0).ewm(alpha=1/period, adjust=False).mean()
        loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/period, adjust=False).mean()

        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
        return df

    def _add_candle_helpers(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add helper columns for price action analysis."""
        df = df.copy()
        
        # Calculate Body
        df["body"] = (df["close"] - df["open"]).abs()
        
        # Calculate Range (High - Low)
        df["range"] = df["high"] - df["low"]
        
        # Calculate Wicks
        # Upper Wick = High - Max(Open, Close)
        df["upper_wick"] = df["high"] - df[["open", "close"]].max(axis=1)
        
        # Lower Wick = Min(Open, Close) - Low
        df["lower_wick"] = df[["open", "close"]].min(axis=1) - df["low"]
        
        # Average Range (N=20)
        df["avg_range"] = df["range"].rolling(20).mean()
        
        # ATR if not present (DataLoader usually adds it, but just in case)
        if "atr" not in df.columns:
            # Simple ATR approx if real ATR missing
            df["atr"] = df["avg_range"]
            
        return df

    def _detect_pin_bar(self, df: pd.DataFrame) -> pd.DataFrame:
        """Detect Bullish and Bearish Pin Bars."""
        
        # Safe range to avoid division by zero
        range_safe = df["range"].replace(0, np.nan)
        
        # 1. Candle Size
        big_enough = df["range"] >= self.min_range_factor * df["avg_range"]
        
        # 2. Small Body
        small_body = df["body"] <= self.max_body_to_range * range_safe
        
        # --- Bullish Pin Bar ---
        # Long lower wick, small upper wick, close up (or near top)
        long_lower = df["lower_wick"] >= self.min_wick_to_range * range_safe
        short_upper = df["upper_wick"] <= (1 - self.min_wick_to_range) * range_safe
        # Prefer green close for bullish pinbar, though some definitions allow red if close is high
        close_up = df["close"] > df["open"] 
        
        df["bullish_pinbar"] = big_enough & small_body & long_lower & short_upper & close_up
        
        # --- Bearish Pin Bar ---
        # Long upper wick, small lower wick, close down
        long_upper = df["upper_wick"] >= self.min_wick_to_range * range_safe
        short_lower = df["lower_wick"] <= (1 - self.min_wick_to_range) * range_safe
        close_down = df["close"] < df["open"]
        
        df["bearish_pinbar"] = big_enough & small_body & long_upper & short_lower & close_down
        
        return df

    def _detect_engulfing(self, df: pd.DataFrame) -> pd.DataFrame:
        """Detect Bullish and Bearish Engulfing patterns."""
        o = df["open"]
        c = df["close"]
        body = df["body"]
        
        # Previous candle values
        o_prev = o.shift(1)
        c_prev = c.shift(1)
        body_prev = body.shift(1)
        
        # --- Bullish Engulfing ---
        # 1. Previous Red, Current Green
        cond_dir_bull = (c_prev < o_prev) & (c > o)
        # 2. Current Body Engulfs Previous Body completely
        cond_body_bull = (o <= c_prev) & (c >= o_prev)
        # 3. Non-zero bodies
        cond_nonzero = (body > 0) & (body_prev > 0)
        
        df["bullish_engulfing"] = cond_dir_bull & cond_body_bull & cond_nonzero
        
        # --- Bearish Engulfing ---
        # 1. Previous Green, Current Red
        cond_dir_bear = (c_prev > o_prev) & (c < o)
        # 2. Current Body Engulfs Previous Body
        cond_body_bear = (o >= c_prev) & (c <= o_prev)
        
        df["bearish_engulfing"] = cond_dir_bear & cond_body_bear & cond_nonzero
        
        return df

    def _detect_inside_bar(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Detect Inside Bars.
        Note: Inside Bar itself is neutral until broken.
        We mark 'inside_bar' and potential breakout direction?
        For now, just detection as requested.
        """
        h = df["high"]
        l = df["low"]
        r = df["range"]
        r_prev = r.shift(1)
        
        # Inside definition: High <= PrevHigh AND Low >= PrevLow
        cond_inside = (h <= h.shift(1)) & (l >= l.shift(1))
        
        # Mother bar filter (big enough)
        cond_big_mother = r_prev >= self.min_range_factor_mother * df["avg_range"]
        
        # Child bar filter (small enough relative to mother)
        cond_small_child = r <= self.max_child_to_mother * r_prev
        
        df["inside_bar"] = cond_inside & cond_big_mother & cond_small_child
        
        # A simple breakout logic helper (not strictly part of pattern detection but useful for signals)
        # Check if PREVIOUS was inside bar, and CURRENT breaks it?
        # For simplicity in this implementation, we won't trade Inside Bar directly 
        # unless user defined a breakout rule. 
        # I'll enable a placeholder for 'inside_bar_bullish_break' if needed later.
        df["inside_bar_bullish_break"] = False 
        
        return df

    def _detect_outside_bar(self, df: pd.DataFrame) -> pd.DataFrame:
        """Detect Outside Bars."""
        h = df["high"]
        l = df["low"]
        c = df["close"]
        o = df["open"]
        r = df["range"]
        r_prev = r.shift(1)
        
        # Outside definition: High >= PrevHigh AND Low <= PrevLow
        cond_outside_range = (h >= h.shift(1)) & (l <= l.shift(1))
        
        # Volatility filters
        cond_big = r >= self.min_range_factor * df["avg_range"]
        cond_expand = r >= self.min_expand_factor * r_prev
        
        # Close location fraction
        range_safe = r.replace(0, np.nan)
        frac_close = (c - l) / range_safe
        
        # --- Bullish Outside Bar ---
        # Close > Open (Green) AND Close near top
        cond_dir_bull = c > o
        cond_frac_bull = frac_close >= 0.6
        
        df["bullish_outside_bar"] = cond_outside_range & cond_big & cond_expand & cond_dir_bull & cond_frac_bull
        
        # --- Bearish Outside Bar ---
        # Close < Open (Red) AND Close near bottom
        cond_dir_bear = c < o
        cond_frac_bear = frac_close <= 0.4
        
        df["bearish_outside_bar"] = cond_outside_range & cond_big & cond_expand & cond_dir_bear & cond_frac_bear
        
        return df

    def _add_adx(self, df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
        """
        Calculate ADX (Average Directional Index).
        
        Args:
            df: DataFrame with high, low, close
            period: Period for ADX calculation
            
        Returns:
            DataFrame with 'adx' column added
        """
        if len(df) < period * 2:
            return df
            
        # 1. Calculate TR (True Range)
        df['tr1'] = df['high'] - df['low']
        df['tr2'] = abs(df['high'] - df['close'].shift(1))
        df['tr3'] = abs(df['low'] - df['close'].shift(1))
        df['tr'] = df[['tr1', 'tr2', 'tr3']].max(axis=1)
        
        # 2. Calculate DM (Directional Movement)
        df['up_move'] = df['high'] - df['high'].shift(1)
        df['down_move'] = df['low'].shift(1) - df['low']
        
        df['plus_dm'] = np.where((df['up_move'] > df['down_move']) & (df['up_move'] > 0), df['up_move'], 0)
        df['minus_dm'] = np.where((df['down_move'] > df['up_move']) & (df['down_move'] > 0), df['down_move'], 0)
        
        # 3. Smooth TR and DM (Wilder's Smoothing)
        # First value is SMA, subsequent are (prev * (n-1) + current) / n
        # Pandas ewm(alpha=1/n, adjust=False) is equivalent to Wilder's Smoothing
        
        df['tr_smooth'] = df['tr'].ewm(alpha=1/period, adjust=False).mean()
        df['plus_dm_smooth'] = df['plus_dm'].ewm(alpha=1/period, adjust=False).mean()
        df['minus_dm_smooth'] = df['minus_dm'].ewm(alpha=1/period, adjust=False).mean()
        
        # 4. Calculate DI
        df['plus_di'] = 100 * (df['plus_dm_smooth'] / df['tr_smooth'])
        df['minus_di'] = 100 * (df['minus_dm_smooth'] / df['tr_smooth'])
        
        # 5. Calculate DX
        df['dx'] = 100 * abs(df['plus_di'] - df['minus_di']) / (df['plus_di'] + df['minus_di'])
        
        # 6. Calculate ADX (Smoothed DX)
        df['adx'] = df['dx'].ewm(alpha=1/period, adjust=False).mean()
        
        # Cleanup temporary columns
        cols_to_drop = ['tr1', 'tr2', 'tr3', 'tr', 'up_move', 'down_move', 
                        'plus_dm', 'minus_dm', 'tr_smooth', 'plus_dm_smooth', 
                        'minus_dm_smooth', 'plus_di', 'minus_di', 'dx']
        df.drop(columns=cols_to_drop, inplace=True, errors='ignore')
        
        return df
