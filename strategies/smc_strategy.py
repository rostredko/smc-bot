"""
SMC Strategy Implementation.
Smart Money Concepts based trading strategy.
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Any
from datetime import datetime

from strategies.base_strategy import StrategyBase


class SMCStrategy(StrategyBase):
    """
    Smart Money Concepts based trading strategy.
    Implements a comprehensive SMC approach with multi-timeframe analysis.
    """

    def __init__(self, config: Optional[Dict] = None):
        """
        Initialize SMC strategy.

        Args:
            config: Strategy configuration
        """
        default_config = {
            # Core Settings
            "mode": "spot",
            "allow_short": False,  # No shorting in spot
            
            # Timeframes
            "high_timeframe": "4h",
            "low_timeframe": "15m",
            
            # Risk Management
            "risk_per_trade_pct": 0.3,
            "max_concurrent_positions": 3,
            "min_required_rr": 2.0,
            "max_stop_distance_pct": 0.04,  # Max 4% SL
            
            # Volatility Filters
            "volatility_filter_enabled": True,
            "atr_period": 14,
            "atr_percentile_min": 30,
            "atr_percentile_max": 70,
            "sl_atr_multiplier": 2.0,
            
            # Technical Entry Filters
            "ema_filter_period": 50,
            "rsi_period": 14,
            "min_rsi_long": 35,
            "max_rsi_long": 70,  # For mean reversion exits
            "volume_threshold": 1.3,
            
            # Partial Take Profits
            "use_partial_tp": True,
            "tp1_r": 1.0,
            "tp1_pct": 0.5,
            "tp2_r": 2.0, 
            "tp2_pct": 0.3,
            "runner_pct": 0.2,
            
            # Exit Management
            "trailing_stop_enabled": True,
            "trail_start": 1.5,
            "trail_step": 0.3,
            "breakeven_move_enabled": True,
            
            # Market Structure
            "require_structure_confirmation": True,
            "support_level_lookback_bars": 20,
            
            # Cooldown & Psychology
            "cooldown_after_loss_bars": 10,
            "reduce_risk_after_loss": True,
            "risk_reduction_after_loss": 0.6,
            
            # Exchange Settings
            "min_notional": 10.0,
            "taker_fee": 0.0004,
            "slippage_bp": 2,
            
            # Дополнительные параметры для работы стратегии (не в новом конфиге, но нужны для функционала)
            "min_zone_strength": 0.9,
            "max_zones": 5,
            "confluence_required": True,
            "max_rsi_short": 70,
            "min_confluence_factors": 3,
            "require_mandatory_smc": True,
            "mandatory_smc_factors": ["OB", "FVG", "Liquidity"],
            "min_mandatory_factors": 1,
            "min_additional_factors": 2,
            "premium_discount_filter": True,
            "fibonacci_levels": [0.618, 0.786],
            "trend_filter_enabled": True,
            "ladder_exit_enabled": True,
            "use_adaptive_sl": True,
            "use_trailing_stop": True,
            "adaptive_rr_enabled": True,
            "min_qty": 0.00001,
            "step_size": 0.00001,
            "tick_size": 0.01,
            "maker_fee": 0.0001,
            "recent_data_lookback_bars": 20,
            "swing_point_lookback_bars": 3,
            "structure_analysis_lookback": 20,
            "volume_lookback_bars": 20,
            "liquidity_sweep_lookback": 10,
            "fibonacci_retracement_lookback": 50,
            "price_action_lookback": 3,
            "bullish_engulfing_body_ratio": 0.7,
            "bearish_engulfing_body_ratio": 0.5,
            "shooting_star_upper_shadow_ratio": 2.0,
            "shooting_star_lower_shadow_ratio": 0.5,
            "liquidity_level_tolerance_pct": 0.005,
            "neutral_rsi": 50.0,
            "volatility_percentile_lookback": 100,
            "volatility_percentile_calc_period": 50,
            "macd_fast_period": 12,
            "macd_slow_period": 26,
            "macd_signal_period": 9,
            "atr_percentile_lookback": 14,
            "order_block_strength_threshold": 0.9,
            "rr_target_primary": 2.0,
            "atr_multiplier": 1.2,
            "min_sl_atr_multiplier_15m": 1.8,
            "min_sl_atr_multiplier_4h": 2.2,
            "dynamic_risk_management": True,
            "neutral_bias_allowed": True,
            "use_support_resistance_sl": True,
        }

        super().__init__(config)
        self.config = {**default_config, **self.config}

        # Strategy-specific state
        self.market_bias = None
        self.premium_discount_zones = None
        self.active_order_blocks = []
        self.active_fvgs = []
        self.liquidity_levels = []

        # Performance tracking
        self.signals_generated = 0
        self.signals_executed = 0
        self.consecutive_losses = 0  # Track for dynamic risk management

        # Spot trading balances
        self.cash_usdt = 10000  # Available USDT cash
        self.asset_qty = 0.0  # BTC quantity held
        self.equity = 10000  # Total equity (cash + asset value)

    def generate_signals(self, market_data: Dict[str, pd.DataFrame]) -> List[Dict[str, Any]]:
        """
        Generate SMC-based trading signals.

        Args:
            market_data: Dictionary with high and low timeframe data

        Returns:
            List of signal dictionaries
        """
        signals = []

        # Get required timeframes
        high_tf = self.config["high_timeframe"]
        low_tf = self.config["low_timeframe"]

        if high_tf not in market_data or low_tf not in market_data:
            return signals

        high_df = market_data[high_tf]
        low_df = market_data[low_tf]

        if len(high_df) < 50 or len(low_df) < 20:
            return signals

        # Step 1: Determine market bias from higher timeframe
        self._update_market_bias(high_df)

        # Step 2: Check volatility filter
        volatility_ok = self._is_volatility_acceptable(high_df)
        if not volatility_ok:
            return signals

        # Step 3: Identify key zones and levels
        self._update_zones_and_levels(high_df, low_df)

        # Step 4: Look for entry opportunities (both LONG and SHORT for spot trading)
        signals = self._look_for_entries(low_df, high_df)

        self.signals_generated += len(signals)
        return signals

    def _calculate_atr(self, df: pd.DataFrame, period: int = None) -> float:
        """Calculate Average True Range (ATR) for volatility-based stops."""
        if period is None:
            period = self.config["atr_period"]

        if len(df) < period + 1:
            return 0.0

        high = df["high"]
        low = df["low"]
        close = df["close"]

        # Calculate True Range
        tr1 = high - low
        tr2 = (high - close.shift(1)).abs()
        tr3 = (low - close.shift(1)).abs()

        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(period).mean().iloc[-1]

        return float(atr) if not pd.isna(atr) else 0.0

    def _calculate_minimum_stop_distance(self, low_df: pd.DataFrame, high_df: pd.DataFrame) -> float:
        """
        Calculate minimum stop loss distance based on ATR from both timeframes.

        Args:
            low_df: Low timeframe data (15m)
            high_df: High timeframe data (4h)

        Returns:
            Minimum stop distance in price units
        """
        atr_15m = self._calculate_atr(low_df)
        atr_4h = self._calculate_atr(high_df)

        # Minimum SL distance uses a single ATR multiplier from config
        sl_mult = self.config.get("sl_atr_multiplier", 2.0)
        min_distance = max(atr_15m * sl_mult, (atr_4h * sl_mult) / 4)

        return min_distance

    def _calculate_adaptive_stop_loss(self, low_df: pd.DataFrame, high_df: pd.DataFrame, current_price: float, direction: str) -> float:
        """Adaptive stop loss based on support/resistance and volatility.

        Args:
            low_df: Low timeframe data (15m)
            high_df: High timeframe data (4h)
            current_price: Current price
            direction: Position direction ('LONG' or 'SHORT')

        Returns:
            Adaptive stop loss
        """
        # Base ATR stop
        atr_15m = self._calculate_atr(low_df)
        atr_4h = self._calculate_atr(high_df)
        sl_mult = self.config.get("sl_atr_multiplier", 2.0)
        atr_stop = max(atr_15m * sl_mult, atr_4h * sl_mult)

        if direction == "LONG":
            # Find nearest support level
            recent_lows = low_df["low"].tail(self.config["support_level_lookback_bars"])
            support_level = recent_lows.min()

            # Use maximum of ATR and support
            stop_distance = max(atr_stop, (current_price - support_level) * 0.95)
            stop_loss = current_price - stop_distance

            # Check that stop is not too far (max 3.5%)
            max_stop_distance = current_price * self.config["max_stop_distance_pct"]
            if stop_distance > max_stop_distance:
                stop_loss = current_price - max_stop_distance

        else:  # SHORT
            recent_highs = low_df["high"].tail(self.config["support_level_lookback_bars"])
            resistance_level = recent_highs.max()

            stop_distance = max(atr_stop, (resistance_level - current_price) * 0.95)
            stop_loss = current_price + stop_distance

            max_stop_distance = current_price * self.config["max_stop_distance_pct"]  # Increased from 3% to 3.5%
            if stop_distance > max_stop_distance:
                stop_loss = current_price + max_stop_distance

        return stop_loss

    def _is_volatility_acceptable(self, high_df: pd.DataFrame) -> bool:
        """
        Check if current volatility is within acceptable range for trading.

        Args:
            high_df: High timeframe data (4h)

        Returns:
            True if volatility is acceptable for trading
        """
        if not self.config.get("volatility_filter_enabled", True):
            return True

        if len(high_df) < self.config["volatility_percentile_lookback"]:  # Need enough data for percentile calculation
            return True

        # Calculate current ATR
        current_atr = self._calculate_atr(high_df)

        # Calculate ATR percentiles over last 100 bars
        atr_values = []
        for i in range(self.config["volatility_percentile_lookback"], len(high_df)):
            period_data = high_df.iloc[i - self.config["atr_period"] : i + 1]  # 14-period ATR
            atr_val = self._calculate_atr(period_data)
            if atr_val > 0:
                atr_values.append(atr_val)

        if len(atr_values) < self.config["volatility_percentile_calc_period"]:  # Not enough data
            return True

        # Calculate percentiles
        atr_percentile = (sum(1 for x in atr_values if x <= current_atr) / len(atr_values)) * 100

        min_percentile = self.config.get("atr_percentile_min", 30)
        max_percentile = self.config.get("atr_percentile_max", 70)

        return min_percentile <= atr_percentile <= max_percentile

    def _calculate_rsi(self, df: pd.DataFrame, period: int = None) -> float:
        """Calculate RSI for momentum confirmation."""
        if period is None:
            period = self.config["rsi_period"]

        if len(df) < period + 1:
            return self.config["neutral_rsi"]  # Neutral RSI

        delta = df["close"].diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)

        avg_gain = gain.rolling(window=period).mean()
        avg_loss = loss.rolling(window=period).mean()

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        return float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else self.config["neutral_rsi"]

    def _calculate_ema(self, df: pd.DataFrame, period: int) -> float:
        """Calculate Exponential Moving Average."""
        if len(df) < period:
            return df["close"].iloc[-1]

        ema = df["close"].ewm(span=period, adjust=False).mean()
        return float(ema.iloc[-1]) if not pd.isna(ema.iloc[-1]) else df["close"].iloc[-1]

    def _calculate_macd(self, df: pd.DataFrame, fast: int = None, slow: int = None, signal: int = None):
        """Calculate MACD indicator."""
        if fast is None:
            fast = self.config["macd_fast_period"]
        if slow is None:
            slow = self.config["macd_slow_period"]
        if signal is None:
            signal = self.config["macd_signal_period"]

        if len(df) < slow + signal:
            return 0.0, 0.0, 0.0

        ema_fast = df["close"].ewm(span=fast).mean()
        ema_slow = df["close"].ewm(span=slow).mean()

        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal).mean()
        macd_histogram = macd_line - signal_line

        return (float(macd_line.iloc[-1]), float(signal_line.iloc[-1]), float(macd_histogram.iloc[-1]))

    def _update_market_bias(self, high_df: pd.DataFrame):
        """Улучшенное определение рыночного bias с weighted scoring."""
        # Multi-timeframe EMA analysis
        ema_9_4h = self._calculate_ema(high_df, 9)
        ema_21_4h = self._calculate_ema(high_df, 21)
        ema_50_4h = self._calculate_ema(high_df, 50)

        current_price = high_df["close"].iloc[-1]

        # Weighted scoring system
        bull_score = 0
        bear_score = 0

        # EMA alignment (most important)
        if current_price > ema_9_4h > ema_21_4h > ema_50_4h:
            bull_score += 3
        elif current_price < ema_9_4h < ema_21_4h < ema_50_4h:
            bear_score += 3

        # RSI momentum
        rsi_4h = self._calculate_rsi(high_df)
        if rsi_4h > 55 and rsi_4h < 80:
            bull_score += 1
        elif rsi_4h < 45 and rsi_4h > 20:
            bear_score += 1

        # Market structure
        structure = self._analyze_market_structure(high_df)
        if structure == "bullish":
            bull_score += 2
        elif structure == "bearish":
            bear_score += 2

        # MACD confirmation
        macd_line, signal_line, macd_histogram = self._calculate_macd(high_df)
        if macd_line > signal_line and macd_histogram > 0:
            bull_score += 1
        elif macd_line < signal_line and macd_histogram < 0:
            bear_score += 1

        # Determine bias with clear thresholds
        if bull_score >= 4 and bull_score > bear_score + 1:
            self.market_bias = "BULLISH"
        elif bear_score >= 4 and bear_score > bull_score + 1:
            self.market_bias = "BEARISH"
        else:
            self.market_bias = "NEUTRAL"

    def _analyze_market_structure(self, high_df: pd.DataFrame):
        """Analyze market structure for bias determination."""
        if len(high_df) < 20:
            return "neutral"

        # Look for recent structure breaks
        recent_data = high_df.tail(self.config["structure_analysis_lookback"])

        # Find swing points
        highs = recent_data["high"].rolling(self.config["swing_point_lookback_bars"], center=True).max()
        lows = recent_data["low"].rolling(self.config["swing_point_lookback_bars"], center=True).min()

        # Check for higher highs and higher lows (bullish)
        recent_highs = highs.dropna().tail(self.config["swing_point_lookback_bars"])
        recent_lows = lows.dropna().tail(self.config["swing_point_lookback_bars"])

        bullish_structure = False
        bearish_structure = False

        if len(recent_highs) >= 2 and len(recent_lows) >= 2:
            if recent_highs.iloc[-1] > recent_highs.iloc[-2]:
                bullish_structure = True
            if recent_lows.iloc[-1] < recent_lows.iloc[-2]:
                bearish_structure = True

        if bullish_structure and not bearish_structure:
            return "bullish"
        elif bearish_structure and not bullish_structure:
            return "bearish"
        else:
            return "neutral"

    def _update_zones_and_levels(self, high_df: pd.DataFrame, low_df: pd.DataFrame):
        """Update order blocks, FVGs, and liquidity levels."""
        # Update premium/discount zones
        self.premium_discount_zones = self.order_block_detector.find_premium_discount_zones(high_df)

        # Update order blocks
        self.active_order_blocks = self.order_block_detector.find_order_blocks(low_df)

        # Update fair value gaps
        self.active_fvgs = self.fvg_detector.scan_for_gaps(low_df)

        # Update liquidity levels
        self.liquidity_levels = self.liquidity_mapper.find_liquidity_levels(low_df)

        # Clean up old zones (keep only recent ones)
        self._cleanup_old_zones(low_df)

    def _cleanup_old_zones(self, low_df: pd.DataFrame):
        """Remove old zones that are no longer relevant."""
        current_time = low_df.index[-1]

        # Keep only zones from last 100 bars
        cutoff_time = current_time - pd.Timedelta(hours=100)

        self.active_order_blocks = [ob for ob in self.active_order_blocks if ob.timestamp > cutoff_time]

        self.active_fvgs = [fvg for fvg in self.active_fvgs if fvg.timestamp > cutoff_time and not fvg.filled]

    def _look_for_entries(self, low_df: pd.DataFrame, high_df: pd.DataFrame) -> List[Dict[str, Any]]:
        """Look for both LONG and SHORT entry opportunities (spot trading)."""
        signals = []
        current_price = low_df["close"].iloc[-1]

        # Look for LONG entries in BULLISH bias
        if self.market_bias == "BULLISH":
            signals.extend(self._look_for_long_entries(low_df, high_df, current_price))
        # Look for SHORT entries in BEARISH bias
        elif self.market_bias == "BEARISH" and self.config.get("allow_short", False):
            signals.extend(self._look_for_short_entries(low_df, high_df, current_price))
        # In NEUTRAL bias, allow longs and optionally shorts based on allow_short
        elif self.market_bias == "NEUTRAL" and self.config.get("neutral_bias_allowed", False):
            signals.extend(self._look_for_long_entries(low_df, high_df, current_price))
            if self.config.get("allow_short", False):
                signals.extend(self._look_for_short_entries(low_df, high_df, current_price))

        return signals

    def _look_for_long_entries(self, low_df: pd.DataFrame, high_df: pd.DataFrame, current_price: float) -> List[Dict[str, Any]]:
        """Улучшенный поиск LONG входов с обязательными SMC элементами."""
        signals = []

        # Volatility-based position sizing
        atr = self._calculate_atr(low_df)

        # Check Fibonacci retracement levels for better entries
        if not self._is_in_fibonacci_retracement_zone(low_df, current_price, "long"):
            return signals

        # Check if price is in discount zone (if enabled)
        if self.config["premium_discount_filter"] and not self._is_in_discount_zone(current_price):
            return signals

        confluence_factors = []
        mandatory_factors = []
        used_ob_ids = []
        used_fvg_ids = []

        # MANDATORY factors (minimum 1)

        # 1. Сильные Order Blocks
        strong_obs = [ob for ob in self.active_order_blocks if ob.type == "demand" and ob.strength >= self.config["order_block_strength_threshold"]]
        for ob in strong_obs:
            if ob.low <= current_price <= ob.high:
                confluence_factors.append(f"Strong Demand OB ({ob.strength:.2f})")
                mandatory_factors.append("OB")
                used_ob_ids.append(ob.zone_id)

        # 2. Fair Value Gaps
        for fvg in self.active_fvgs:
            if fvg.type == "bullish" and fvg.low <= current_price <= fvg.high:
                confluence_factors.append("Bullish FVG")
                mandatory_factors.append("FVG")
                used_fvg_ids.append(fvg.zone_id)

        # 3. Liquidity уровни
        if self._is_near_liquidity_level(current_price, "buy"):
            confluence_factors.append("Liquidity Level")
            mandatory_factors.append("Liquidity")

        # ADDITIONAL factors

        # Volume confirmation
        if self._has_strong_volume_confirmation(low_df):
            confluence_factors.append("Strong Volume")

        # Price action
        if self._has_very_bullish_price_action(low_df):
            confluence_factors.append("Very Bullish PA")

        # RSI momentum
        rsi = self._calculate_rsi(low_df)
        if 40 <= rsi <= 65:  # Optimal entry zone
            confluence_factors.append("Optimal RSI")

        # Trend filter (EMA)
        ema50 = self._calculate_ema(low_df, self.config["ema_filter_period"])
        if current_price > ema50:
            confluence_factors.append("Above EMA50")

        # Fibonacci level confirmation
        fib_level = self._get_fibonacci_level(low_df, current_price)
        if fib_level:
            confluence_factors.append(f"Fibonacci {fib_level}")

        # Market structure confirmation
        if self._has_bullish_structure_break(low_df):
            confluence_factors.append("Structure break")

        # Require minimum 1 mandatory + 2 additional factors
        has_mandatory = len(set(mandatory_factors)) >= 1
        has_additional = len(confluence_factors) - len(mandatory_factors) >= 2

        if has_mandatory and has_additional:
            signal = self._create_long_signal(low_df, high_df, current_price, confluence_factors, atr)

            # Apply enhanced signal filtering
            if self._enhanced_signal_filter(signal, low_df, high_df):
                signals.append(signal)
                print(f"LONG Signal created with {len(confluence_factors)} confluence factors")

                # Mark used zones to prevent re-entry
                for ob_id in used_ob_ids:
                    for ob in self.active_order_blocks:
                        if ob.zone_id == ob_id:
                            ob.used = True
                for fvg_id in used_fvg_ids:
                    for fvg in self.active_fvgs:
                        if fvg.zone_id == fvg_id:
                            fvg.used = True
            else:
                print(f"LONG Signal filtered out by enhanced filters")

        return signals

    def _look_for_short_entries(self, low_df: pd.DataFrame, high_df: pd.DataFrame, current_price: float) -> List[Dict[str, Any]]:
        """Enhanced short entry for spot trading (sell BTC, buy back cheaper)."""
        if not self.config.get("allow_short", False):
            return []
        signals = []

        # Volatility-based position sizing
        atr = self._calculate_atr(low_df)

        # Check Fibonacci retracement levels for better entries
        if not self._is_in_fibonacci_retracement_zone(low_df, current_price, "short"):
            return signals

        # Check if price is in premium zone (if enabled)
        if self.config["premium_discount_filter"] and not self._is_in_premium_zone(current_price):
            return signals

        confluence_factors = []
        used_ob_ids = []
        used_fvg_ids = []

        # Factor 1: Strong supply order blocks only
        for ob in self.active_order_blocks:
            if not ob.used and ob.type == "supply" and ob.low <= current_price <= ob.high and ob.strength >= self.config["min_zone_strength"]:
                confluence_factors.append(f"Strong Supply OB ({ob.strength:.2f})")
                used_ob_ids.append(ob.zone_id)

        # Factor 2: Fair value gap confluence
        for fvg in self.active_fvgs:
            if not fvg.used and fvg.type == "bearish" and fvg.low <= current_price <= fvg.high:
                confluence_factors.append("Bearish FVG")
                used_fvg_ids.append(fvg.zone_id)

        # Factor 3: Volume confirmation
        if self._has_volume_confirmation(low_df):
            confluence_factors.append("Volume confirmation")

        # Factor 4: Price action confirmation
        if self._has_bearish_price_action(low_df):
            confluence_factors.append("Bearish price action")

        # Factor 5: Liquidity sweep confirmation
        if self._has_liquidity_sweep(low_df, "sell"):
            confluence_factors.append("Liquidity sweep")

        # Factor 6: Momentum confirmation (RSI)
        rsi = self._calculate_rsi(low_df)
        if rsi < 55:  # Not overbought
            confluence_factors.append("Negative Momentum")

        # Factor 7: Trend filter (EMA)
        ema50 = self._calculate_ema(low_df, self.config["ema_filter_period"])
        if current_price < ema50:
            confluence_factors.append("Below EMA50")

        # Factor 8: Fibonacci level confirmation
        fib_level = self._get_fibonacci_level(low_df, current_price)
        if fib_level:
            confluence_factors.append(f"Fibonacci {fib_level}")

        # Factor 9: Market structure confirmation
        if self._has_bearish_structure_break(low_df):
            confluence_factors.append("Structure break")

        # Generate signal if enough confluence
        min_confluence = self.config["min_confluence_factors"]
        print(f"Short confluence factors: {confluence_factors}")
        print(f"Required confluence: {min_confluence}, Found: {len(confluence_factors)}")
        if len(confluence_factors) >= min_confluence:
            signal = self._create_short_signal(low_df, high_df, current_price, confluence_factors, atr)
            signals.append(signal)
            print(f"Short signal created with {len(confluence_factors)} confluence factors")

            # Mark used zones to prevent re-entry
            for ob_id in used_ob_ids:
                for ob in self.active_order_blocks:
                    if ob.zone_id == ob_id:
                        ob.used = True
            for fvg_id in used_fvg_ids:
                for fvg in self.active_fvgs:
                    if fvg.zone_id == fvg_id:
                        fvg.used = True

        return signals

    def _create_exit_signal(self, current_price: float, reason: str) -> Dict[str, Any]:
        """Create an exit signal to sell all BTC and move to cash."""
        return {
            "direction": "EXIT",
            "entry_price": float(current_price),
            "stop_loss": None,
            "take_profit": None,
            "position_size": self.asset_qty,  # Sell all BTC
            "reason": reason,
            "confidence": 1.0,
            "strategy": "SMC_SPOT",
            "action": "SELL_ALL",
        }

    def _is_in_discount_zone(self, price: float) -> bool:
        """Check if price is in discount zone."""
        if not self.premium_discount_zones or not self.premium_discount_zones["discount"]:
            return False

        discount_zone = self.premium_discount_zones["discount"]
        return discount_zone["low"] <= price <= discount_zone["high"]

    def _is_in_premium_zone(self, price: float) -> bool:
        """Check if price is in premium zone."""
        if not self.premium_discount_zones or not self.premium_discount_zones["premium"]:
            return False

        premium_zone = self.premium_discount_zones["premium"]
        return premium_zone["low"] <= price <= premium_zone["high"]

    def _has_volume_confirmation(self, low_df: pd.DataFrame) -> bool:
        """Check for volume confirmation."""
        if "volume" not in low_df.columns or len(low_df) < 20:
            return False

        current_volume = low_df["volume"].iloc[-1]
        avg_volume = low_df["volume"].rolling(self.config["volume_lookback_bars"]).mean().iloc[-1]

        return current_volume > avg_volume * self.config["volume_threshold"]

    def _has_very_bullish_price_action(self, low_df: pd.DataFrame) -> bool:
        """Проверка очень бычьего price action."""
        if len(low_df) < 3:
            return False

        current = low_df.iloc[-1]
        previous = low_df.iloc[-2]

        # Very bullish engulfing with large body
        if (
            previous["close"] < previous["open"]  # Previous was bearish
            and current["close"] > current["open"]  # Current is bullish
            and current["close"] > previous["open"]  # Current close > previous open
            and current["open"] < previous["close"]
        ):  # Current open < previous close

            # Additional check for large bullish body
            body_size = current["close"] - current["open"]
            candle_range = current["high"] - current["low"]

            if body_size > candle_range * self.config["bullish_engulfing_body_ratio"]:  # Body составляет >70% от range
                return True

        return False

    def _is_near_liquidity_level(self, current_price: float, direction: str) -> bool:
        """Проверка близости к liquidity уровню.

        Args:
            current_price: Текущая цена
            direction: Направление ('buy' или 'sell')

        Returns:
            True если цена близко к liquidity уровню
        """
        if not self.liquidity_levels:
            return False

        for level in self.liquidity_levels:
            # LiquidityZone - это объект с атрибутом price, а не словарь
            price_diff = abs(current_price - level.price) / current_price
            if price_diff < self.config["liquidity_level_tolerance_pct"]:  # Within 0.5%
                return True

        return False

    def _has_bearish_price_action(self, low_df: pd.DataFrame) -> bool:
        """Check for bearish price action patterns."""
        if len(low_df) < 3:
            return False

        # Check for bearish engulfing
        current = low_df.iloc[-1]
        previous = low_df.iloc[-2]

        # Bearish engulfing: current candle engulfs previous bullish candle
        if (
            previous["close"] > previous["open"]  # Previous was bullish
            and current["close"] < current["open"]  # Current is bearish
            and current["close"] < previous["open"]  # Current close < previous open
            and current["open"] > previous["close"]
        ):  # Current open > previous close
            return True

        # Check for shooting star pattern
        body_size = abs(current["close"] - current["open"])
        lower_shadow = min(current["open"], current["close"]) - current["low"]
        upper_shadow = current["high"] - max(current["open"], current["close"])

        if upper_shadow > body_size * self.config["shooting_star_upper_shadow_ratio"] and lower_shadow < body_size * self.config["shooting_star_lower_shadow_ratio"]:  # Long upper shadow  # Short lower shadow
            return True

        return False

    def _has_liquidity_sweep(self, low_df: pd.DataFrame, direction: str) -> bool:
        """Check for liquidity sweep in the specified direction - FIXED LOGIC."""
        if len(low_df) < 10:
            return False

        # Look for recent liquidity sweeps
        recent = low_df.tail(self.config["liquidity_sweep_lookback"])

        if direction == "buy":
            # Buy-side sweep: swept below previous range low and returned above it
            prev_range_low = recent["low"].iloc[:-1].min()
            last = recent.iloc[-1]

            # Check if last candle swept below previous range and closed above it
            swept = last["low"] < prev_range_low and last["close"] > prev_range_low
            return swept

        elif direction == "sell":
            # Sell-side sweep: swept above previous range high and returned below it
            prev_range_high = recent["high"].iloc[:-1].max()
            last = recent.iloc[-1]

            # Check if last candle swept above previous range and closed below it
            swept_up = last["high"] > prev_range_high and last["close"] < prev_range_high
            return swept_up

        return False

    def _is_in_fibonacci_retracement_zone(self, low_df: pd.DataFrame, current_price: float, direction: str) -> bool:
        """Check if price is in a Fibonacci retracement zone."""
        if len(low_df) < 50:
            return True  # Allow if not enough data

        # Find recent swing high and low
        recent_data = low_df.tail(self.config["fibonacci_retracement_lookback"])
        swing_high = recent_data["high"].max()
        swing_low = recent_data["low"].min()

        # Calculate Fibonacci levels
        fib_range = swing_high - swing_low

        if direction == "long":
            # For longs, look for retracements to 61.8% or 78.6%
            fib_618 = swing_high - (fib_range * 0.618)
            fib_786 = swing_high - (fib_range * 0.786)

            # Allow entries in Fibonacci retracement zones
            return fib_786 <= current_price <= fib_618

        else:  # short
            # For shorts, look for retracements to 61.8% or 78.6%
            fib_618 = swing_low + (fib_range * 0.618)
            fib_786 = swing_low + (fib_range * 0.786)

            # Allow entries in Fibonacci retracement zones
            return fib_618 <= current_price <= fib_786

    def _get_fibonacci_level(self, low_df: pd.DataFrame, current_price: float) -> Optional[str]:
        """Get the Fibonacci level closest to current price."""
        if len(low_df) < 50:
            return None

        recent_data = low_df.tail(self.config["fibonacci_retracement_lookback"])
        swing_high = recent_data["high"].max()
        swing_low = recent_data["low"].min()
        fib_range = swing_high - swing_low

        # Calculate Fibonacci levels
        fib_levels = {
            "23.6%": swing_high - (fib_range * 0.236),
            "38.2%": swing_high - (fib_range * 0.382),
            "50.0%": swing_high - (fib_range * 0.5),
            "61.8%": swing_high - (fib_range * 0.618),
            "78.6%": swing_high - (fib_range * 0.786),
        }

        # Find closest level
        closest_level = None
        min_distance = float("inf")

        for level, price in fib_levels.items():
            distance = abs(current_price - price)
            if distance < min_distance:
                min_distance = distance
                closest_level = level

        # Only return if within 1% of the level
        if min_distance < current_price * 0.01:
            return closest_level

        return None

    def _enhanced_signal_filter(self, signal: Dict, low_df: pd.DataFrame, high_df: pd.DataFrame) -> bool:
        """Улучшенная фильтрация сигналов с исправленными фильтрами LONG.

        Args:
            signal: Signal data dictionary
            low_df: Low timeframe data (15m)
            high_df: High timeframe data (4h)

        Returns:
            True if signal passed all filters
        """
        current_price = low_df["close"].iloc[-1]

        # 1. Ослабленный RSI фильтр для LONG
        rsi = self._calculate_rsi(low_df)
        if signal["direction"] == "LONG" and rsi > 75:  # Was 65, now 75
            return False
        if signal["direction"] == "SHORT" and rsi < 25:  # Was 55, now 25
            return False

        # 2. Усиленная проверка тренда
        if not self._is_strong_trend_aligned(signal["direction"], high_df, low_df):
            return False

        # 3. Требовать объемную конфирмацию
        if not self._has_strong_volume_confirmation(low_df):
            return False

        # 4. Фильтр времени (избегать азиатской сессии)
        if not self._is_good_trading_time():
            return False

        # 5. Фильтр волатильности
        if not self._is_optimal_volatility(low_df, high_df):
            return False

        # 6. Фильтр качества сигнала
        if signal["confidence"] < 0.4:  # Increased from 0.3 to 0.4
            return False

        # 7. Фильтр тренда на младшем ТФ
        if not self._is_aligned_with_lower_tf_trend(signal["direction"], low_df):
            return False

        return True

    def _is_strong_trend_aligned(self, direction: str, high_df: pd.DataFrame, low_df: pd.DataFrame) -> bool:
        """Усиленная проверка совпадения с трендом на обоих ТФ.

        Args:
            direction: Направление сигнала ('LONG' или 'SHORT')
            high_df: High timeframe data (4h)
            low_df: Low timeframe data (15m)

        Returns:
            True если сигнал соответствует тренду на обоих ТФ
        """
        ema_20_4h = self._calculate_ema(high_df, 20)
        ema_50_4h = self._calculate_ema(high_df, 50)
        ema_20_15m = self._calculate_ema(low_df, 20)

        current_price_4h = high_df["close"].iloc[-1]
        current_price_15m = low_df["close"].iloc[-1]

        if direction == "LONG":
            # Price above EMA20 and EMA50 on both timeframes
            return current_price_4h > ema_20_4h and current_price_4h > ema_50_4h and current_price_15m > ema_20_15m
        else:
            return current_price_4h < ema_20_4h and current_price_4h < ema_50_4h and current_price_15m < ema_20_15m

    def _is_optimal_volatility(self, low_df: pd.DataFrame, high_df: pd.DataFrame) -> bool:
        """Проверка оптимальной волатильности для торговли.

        Args:
            low_df: Low timeframe data (15m)
            high_df: High timeframe data (4h)

        Returns:
            True если волатильность оптимальна
        """
        # Check volatility on both timeframes
        atr_15m = self._calculate_atr(low_df)
        atr_4h = self._calculate_atr(high_df)

        # Get average ATR values for last 50 bars
        if len(low_df) >= 50:
            avg_atr_15m = low_df["high"].rolling(self.config["volatility_percentile_calc_period"]).apply(lambda x: self._calculate_atr(low_df.iloc[-self.config["volatility_percentile_lookback"]:])).iloc[-1]
        else:
            avg_atr_15m = atr_15m

        if len(high_df) >= 50:
            avg_atr_4h = high_df["high"].rolling(self.config["volatility_percentile_calc_period"]).apply(lambda x: self._calculate_atr(high_df.iloc[-self.config["volatility_percentile_lookback"]:])).iloc[-1]
        else:
            avg_atr_4h = atr_4h

        # Check that current volatility is not too low or high
        volatility_ratio_15m = atr_15m / avg_atr_15m if avg_atr_15m > 0 else 1.0
        volatility_ratio_4h = atr_4h / avg_atr_4h if avg_atr_4h > 0 else 1.0

        # Optimal volatility: 0.7 - 1.5 of average
        return 0.7 <= volatility_ratio_15m <= 1.5 and 0.7 <= volatility_ratio_4h <= 1.5

    def _is_good_trading_time(self) -> bool:
        """Check trading time (avoid low liquidity periods).

        Returns:
            True if it's good time to trade
        """
        from datetime import datetime, time

        current_time = datetime.now().time()

        # Avoid trading during low liquidity periods
        # Asian session (22:00 - 06:00 UTC) - low liquidity
        low_liquidity_start = time(22, 0)
        low_liquidity_end = time(6, 0)

        if low_liquidity_start <= current_time or current_time <= low_liquidity_end:
            return False

        return True

    def _has_strong_volume_confirmation(self, low_df: pd.DataFrame) -> bool:
        """Проверка сильной объемной конфирмации.

        Args:
            low_df: Low timeframe data (15m)

        Returns:
            True если объем достаточно сильный
        """
        if "volume" not in low_df.columns or len(low_df) < 20:
            return True  # Skip volume check if no data

        current_volume = low_df["volume"].iloc[-1]
        avg_volume = low_df["volume"].rolling(self.config["volume_lookback_bars"]).mean().iloc[-1]

        # Require volume above average
        return current_volume > avg_volume * 1.2

    def _is_aligned_with_lower_tf_trend(self, direction: str, low_df: pd.DataFrame) -> bool:
        """Проверка совпадения с трендом на младшем ТФ.

        Args:
            direction: Направление сигнала
            low_df: Low timeframe data (15m)

        Returns:
            True если сигнал соответствует тренду на младшем ТФ
        """
        if len(low_df) < 10:
            return True

        # Simple trend check on lower timeframe
        recent_closes = low_df["close"].tail(self.config["price_action_lookback"])

        if direction == "LONG":
            # Check that price is rising
            return recent_closes.iloc[-1] > recent_closes.iloc[-3]
        else:
            # Check that price is falling
            return recent_closes.iloc[-1] < recent_closes.iloc[-3]

    def _has_increasing_volume(self, low_df: pd.DataFrame) -> bool:
        """Проверка растущего объема.

        Args:
            low_df: Low timeframe data (15m)

        Returns:
            True если объем растет
        """
        if "volume" not in low_df.columns or len(low_df) < 5:
            return True

        recent_volumes = low_df["volume"].tail(5)
        return recent_volumes.iloc[-1] > recent_volumes.iloc[-2]

    def _has_bullish_structure_break(self, low_df: pd.DataFrame) -> bool:
        """Check for bullish market structure break."""
        if len(low_df) < 20:
            return False

        # Look for recent higher high and higher low pattern
        recent_data = low_df.tail(self.config["structure_analysis_lookback"])

        # Find recent swing points
        highs = recent_data["high"].rolling(self.config["swing_point_lookback_bars"], center=True).max()
        lows = recent_data["low"].rolling(self.config["swing_point_lookback_bars"], center=True).min()

        # Check for higher high
        recent_highs = highs.dropna().tail(self.config["swing_point_lookback_bars"])
        if len(recent_highs) >= 2:
            if recent_highs.iloc[-1] > recent_highs.iloc[-2]:
                return True

        return False

    def _has_bearish_structure_break(self, low_df: pd.DataFrame) -> bool:
        """Check for bearish market structure break."""
        if len(low_df) < 20:
            return False

        # Look for recent lower high and lower low pattern
        recent_data = low_df.tail(self.config["structure_analysis_lookback"])

        # Find recent swing points
        highs = recent_data["high"].rolling(self.config["swing_point_lookback_bars"], center=True).max()
        lows = recent_data["low"].rolling(self.config["swing_point_lookback_bars"], center=True).min()

        # Check for lower low
        recent_lows = lows.dropna().tail(self.config["swing_point_lookback_bars"])
        if len(recent_lows) >= 2:
            if recent_lows.iloc[-1] < recent_lows.iloc[-2]:
                return True

        return False

    def _create_long_signal(
        self, low_df: pd.DataFrame, high_df: pd.DataFrame, current_price: float, confluence_factors: List[str], atr: float
    ) -> Dict[str, Any]:
        """Create LONG signal optimized for spot trading with partial TPs."""
        # Use adaptive stop loss if enabled
        if self.config.get("use_adaptive_sl", False):
            stop_loss = self._calculate_adaptive_stop_loss(low_df, high_df, current_price, "LONG")
            stop_distance = current_price - stop_loss
        else:
            # Calculate minimum stop distance
            min_stop_distance = self._calculate_minimum_stop_distance(low_df, high_df)

            # Smart stop placement (ATR-based with minimum distance)
            if atr > 0:
                atr_stop_distance = atr * self.config["atr_multiplier"]
                stop_distance = max(atr_stop_distance, min_stop_distance)
            else:
                # Fallback: use recent swing low with minimum distance
                recent_lows = low_df["low"].tail(self.config["support_level_lookback_bars"])
                swing_stop_distance = current_price - recent_lows.min() * 0.998
                stop_distance = max(swing_stop_distance, min_stop_distance)

            stop_loss = current_price - stop_distance

        # Enhanced position size calculation
        confidence = len(confluence_factors) / 9.0  # Normalize confidence
        volatility = atr / current_price if current_price > 0 else 0.01

        # Base risk
        base_risk = self.cash_usdt * (self.config["risk_per_trade_pct"] / 100)

        # Volatility adjustment
        atr_ratio = atr / current_price
        if atr_ratio > 0.03:  # High volatility
            volatility_factor = 0.7
        elif atr_ratio < 0.01:  # Low volatility
            volatility_factor = 1.3
        else:
            volatility_factor = 1.0

        # Confidence adjustment
        confidence_factor = 0.5 + confidence  # 0.5-1.5

        # Loss adjustment
        loss_factor = 1.0
        if hasattr(self, "consecutive_losses") and self.consecutive_losses > 0:
            loss_factor = self.config["risk_reduction_after_loss"] ** self.consecutive_losses

        adjusted_risk = base_risk * volatility_factor * confidence_factor * loss_factor

        # Position size calculation
        risk_distance = abs(current_price - stop_loss)
        if risk_distance > 0:
            position_size = adjusted_risk / risk_distance
        else:
            position_size = 0

        # Ensure we don't exceed available cash
        max_position_value = self.cash_usdt * 0.95  # Leave 5% buffer for fees
        max_position_size = max_position_value / current_price
        position_size = min(position_size, max_position_size)

        # Partial take profit levels based on provided R-multiples
        risk_distance = stop_distance
        tp1 = current_price + (risk_distance * self.config.get("tp1_r", 1.0))
        tp2 = current_price + (risk_distance * self.config.get("tp2_r", 2.0))
        runner_target = None  # runner managed by trailing stop

        return {
            "direction": "LONG",
            "entry_price": float(current_price),
            "stop_loss": float(stop_loss),
            "take_profit": float(tp2),
            "position_size": float(position_size),
            "reason": f"SMC Spot Long - {', '.join(confluence_factors)}",
            "confidence": float(len(confluence_factors) / 9.0),
            "strategy": "SMC_SPOT",
            "atr": float(atr),
            "risk_distance": float(risk_distance),
            "take_profit_levels": [
                {"price": float(tp1), "percentage": float(self.config.get("tp1_pct", 0.5)), "reason": "TP1"},
                {"price": float(tp2), "percentage": float(self.config.get("tp2_pct", 0.3)), "reason": "TP2"},
                # runner_pct handled by engine with trailing stop
            ],
            "trailing_stop_enabled": self.config["trailing_stop_enabled"],
            "breakeven_move_enabled": self.config["breakeven_move_enabled"],
            "move_to_be_at": float(tp1),
            "trail_after": float(tp2),
        }

    def _create_short_signal(
        self, low_df: pd.DataFrame, high_df: pd.DataFrame, current_price: float, confluence_factors: List[str], atr: float
    ) -> Dict[str, Any]:
        """Create SHORT signal optimized for spot trading (sell BTC, buy back cheaper)."""
        # Calculate minimum stop distance
        min_stop_distance = self._calculate_minimum_stop_distance(low_df, high_df)

        # Smart stop placement (ATR-based with minimum distance)
        if atr > 0:
            atr_stop_distance = atr * self.config.get("sl_atr_multiplier", 2.0)
            stop_distance = max(atr_stop_distance, min_stop_distance)
        else:
            # Fallback: use recent swing high with minimum distance
            recent_highs = low_df["high"].tail(self.config["support_level_lookback_bars"])
            swing_stop_distance = recent_highs.max() * 1.002 - current_price
            stop_distance = max(swing_stop_distance, min_stop_distance)

        stop_loss = current_price + stop_distance

        # Calculate position size based on available BTC
        risk_amount = self.asset_qty * current_price * (self.config["risk_per_trade_pct"] / 100)
        position_size = risk_amount / stop_distance

        # Ensure we don't exceed available BTC
        max_position_size = self.asset_qty * 0.95  # Leave 5% buffer for fees
        position_size = min(position_size, max_position_size)

        # Partial take profit levels
        risk_distance = stop_distance
        tp1 = current_price - (risk_distance * self.config.get("tp1_r", 1.0))
        tp2 = current_price - (risk_distance * self.config.get("tp2_r", 2.0))

        return {
            "direction": "SHORT",
            "entry_price": float(current_price),
            "stop_loss": float(stop_loss),
            "take_profit": float(tp2),
            "position_size": float(position_size),
            "reason": f"SMC Spot Short - {', '.join(confluence_factors)}",
            "confidence": float(len(confluence_factors) / 9.0),
            "strategy": "SMC_SPOT",
            "atr": float(atr),
            "risk_distance": float(risk_distance),
            "take_profit_levels": [
                {"price": float(tp1), "percentage": float(self.config.get("tp1_pct", 0.5)), "reason": "TP1"},
                {"price": float(tp2), "percentage": float(self.config.get("tp2_pct", 0.3)), "reason": "TP2"},
            ],
            "trailing_stop_enabled": self.config["trailing_stop_enabled"],
            "breakeven_move_enabled": self.config["breakeven_move_enabled"],
            "move_to_be_at": float(tp1),  # Move to breakeven after TP1
            "trail_after": float(tp2),  # Start trailing after TP2
        }

    def on_trade_exit(self, position):
        """Улучшенная обработка выхода из сделки с управлением зонами."""
        self.signals_executed += 1

        # Update loss counter for dynamic risk management
        if hasattr(position, "pnl") and position.pnl < 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0

        # Invalidate all zones used in this trade to prevent re-entry
        entry_price = position.entry_price

        # Mark order blocks as used
        for ob in self.active_order_blocks:
            if ob.low <= entry_price <= ob.high:
                ob.used = True

        # Mark FVGs as filled if they were used
        for fvg in self.active_fvgs:
            if fvg.low <= entry_price <= fvg.high:
                fvg.filled = True
                fvg.used = True

    def get_strategy_config(self) -> Dict[str, Any]:
        """Get strategy configuration for web interface."""
        return {
            "name": "SMC Spot Strategy",
            "description": "Smart Money Concepts strategy optimized for spot crypto trading",
            "mode": "spot",
            "allow_short": self.config.get("allow_short", False),
            "parameters": {
                "timeframes": {
                    "high_timeframe": {"type": "string", "value": self.config["high_timeframe"]},
                    "low_timeframe": {"type": "string", "value": self.config["low_timeframe"]},
                },
                "risk_management": {
                    "risk_per_trade_pct": {
                        "type": "number",
                        "value": self.config["risk_per_trade_pct"],
                        "min": 0.1,
                        "max": 2.0,
                        "step": 0.1,
                        "description": "Risk per trade percentage",
                    },
                    "max_concurrent_positions": {
                        "type": "number",
                        "value": self.config["max_concurrent_positions"],
                        "min": 1,
                        "max": 3,
                        "step": 1,
                        "description": "Maximum concurrent positions",
                    },
                    "min_required_rr": {
                        "type": "number",
                        "value": self.config["min_required_rr"],
                        "min": 1.0,
                        "max": 5.0,
                        "step": 0.1,
                        "description": "Minimum acceptable risk-reward",
                    },
                    "max_stop_distance_pct": {
                        "type": "number",
                        "value": self.config["max_stop_distance_pct"],
                        "min": 0.01,
                        "max": 0.10,
                        "step": 0.01,
                        "description": "Max 4% stop loss distance",
                    },
                },
                "partial_take_profits": {
                    "use_partial_tp": {"type": "boolean", "value": self.config["use_partial_tp"], "description": "Enable partial take profits"},
                    "tp1_r": {
                        "type": "number",
                        "value": self.config["tp1_r"],
                        "min": 0.5,
                        "max": 2.0,
                        "step": 0.1,
                        "description": "TP1 risk-reward ratio",
                    },
                    "tp1_pct": {
                        "type": "number",
                        "value": self.config["tp1_pct"],
                        "min": 0.1,
                        "max": 0.8,
                        "step": 0.1,
                        "description": "Percentage to close at TP1",
                    },
                    "tp2_r": {
                        "type": "number",
                        "value": self.config["tp2_r"],
                        "min": 1.0,
                        "max": 3.0,
                        "step": 0.1,
                        "description": "TP2 risk-reward ratio",
                    },
                    "tp2_pct": {
                        "type": "number",
                        "value": self.config["tp2_pct"],
                        "min": 0.1,
                        "max": 0.5,
                        "step": 0.1,
                        "description": "Percentage to close at TP2",
                    },
                    "runner_pct": {
                        "type": "number",
                        "value": self.config["runner_pct"],
                        "min": 0.1,
                        "max": 0.5,
                        "step": 0.1,
                        "description": "Percentage to keep as runner",
                    },
                },
                "stop_loss": {
                    "breakeven_move_enabled": {
                        "type": "boolean",
                        "value": self.config["breakeven_move_enabled"],
                        "description": "Move stop to breakeven after TP1",
                    },
                    "trailing_stop_enabled": {
                        "type": "boolean",
                        "value": self.config["trailing_stop_enabled"],
                        "description": "Enable trailing stop for runner",
                    },
                    "sl_atr_multiplier": {
                        "type": "number",
                        "value": self.config["sl_atr_multiplier"],
                        "min": 0.5,
                        "max": 5.0,
                        "step": 0.1,
                        "description": "ATR multiplier for SL",
                    },
                    "trail_start": {
                        "type": "number",
                        "value": self.config["trail_start"],
                        "min": 0.5,
                        "max": 3.0,
                        "step": 0.1,
                        "description": "Start trailing after R multiple",
                    },
                    "trail_step": {
                        "type": "number",
                        "value": self.config["trail_step"],
                        "min": 0.1,
                        "max": 1.0,
                        "step": 0.1,
                        "description": "Trailing step in R",
                    },
                },
                "market_bias": {
                    "neutral_bias_allowed": {
                        "type": "boolean",
                        "value": self.config["neutral_bias_allowed"],
                        "description": "Allow trading in neutral market bias",
                    },
                    "cooldown_after_stop_bars_15m": {
                        "type": "number",
                        "value": self.config["cooldown_after_loss_bars"], # Changed from "cooldown_after_stop_bars_15m" to "cooldown_after_loss_bars"
                        "min": 4,
                        "max": 48,
                        "step": 4,
                        "description": "Cooldown period after stop loss (15m bars)",
                    },
                    "reduce_risk_after_loss": {
                        "type": "boolean",
                        "value": self.config["reduce_risk_after_loss"],
                        "description": "Reduce risk after a loss",
                    },
                    "risk_reduction_after_loss": {
                        "type": "number",
                        "value": self.config["risk_reduction_after_loss"],
                        "min": 0.1,
                        "max": 1.0,
                        "step": 0.1,
                        "description": "Risk multiplier after a loss",
                    },
                },
                "technical_entry_filters": {
                    "ema_filter_period": {"type": "number", "value": self.config["ema_filter_period"]},
                    "rsi_period": {"type": "number", "value": self.config["rsi_period"]},
                    "min_rsi_long": {"type": "number", "value": self.config["min_rsi_long"]},
                    "max_rsi_long": {"type": "number", "value": self.config["max_rsi_long"]},
                    "volume_threshold": {"type": "number", "value": self.config["volume_threshold"]},
                },
                "filters": {
                    "volatility_filter_enabled": {"type": "boolean", "value": self.config["volatility_filter_enabled"]},
                    "atr_period": {"type": "number", "value": self.config["atr_period"]},
                    "atr_percentile_min": {"type": "number", "value": self.config["atr_percentile_min"]},
                    "atr_percentile_max": {"type": "number", "value": self.config["atr_percentile_max"]},
                    "require_structure_confirmation": {"type": "boolean", "value": self.config["require_structure_confirmation"]},
                },
                "exchange": {
                    "min_notional": {"type": "number", "value": self.config["min_notional"]},
                    "taker_fee": {"type": "number", "value": self.config["taker_fee"]},
                    "slippage_bp": {"type": "number", "value": self.config["slippage_bp"]},
                },
            },
        }
        """Get SMC spot strategy information."""
        base_info = super().get_strategy_info()
        base_info.update(
            {
                "mode": "spot",
                "market_bias": self.market_bias,
                "cash_usdt": self.cash_usdt,
                "asset_qty": self.asset_qty,
                "equity": self.equity,
                "active_order_blocks": len(self.active_order_blocks),
                "active_fvgs": len(self.active_fvgs),
                "liquidity_levels": len(self.liquidity_levels),
                "signals_generated": self.signals_generated,
                "signals_executed": self.signals_executed,
                "premium_discount_zones": self.premium_discount_zones,
                "allow_short": self.config.get("allow_short", False),
                "max_concurrent_positions": self.config.get("max_concurrent_positions", 1),
            }
        )
        return base_info

    def manage_open_positions(self, current_price: float, current_time: datetime):
        """Manage open positions with trailing stops.

        Args:
            current_price: Current BTC price
            current_time: Current time
        """
        # This method will be called from engine for position management
        # Here we can add trailing stop and partial close logic
        pass

    def _manage_long_position(self, position, current_price: float, current_time: datetime):
        """Manage long position with trailing stop.

        Args:
            position: Position object
            current_price: Current price
            current_time: Current time
        """
        unrealized_pnl = (current_price - position.entry_price) * position.size

        # Calculate achieved R-levels
        risk_per_unit = position.entry_price - position.stop_loss
        current_r = (current_price - position.entry_price) / risk_per_unit if risk_per_unit > 0 else 0

        # Trailing stop activates after 1.5R
        if current_r >= self.config.get("trail_start", 1.5) and not getattr(position, "trailing_activated", False):
            position.trailing_activated = True
            position.trailing_start_price = current_price

        if getattr(position, "trailing_activated", False):
            # Update trailing stop
            trail_step = self.config.get("trail_step", 0.5)
            new_stop = current_price - (risk_per_unit * trail_step)
            position.stop_loss = max(position.stop_loss, new_stop)

        # Move to breakeven after 1R
        if current_r >= 1.0 and position.stop_loss < position.entry_price:
            position.stop_loss = position.entry_price * 1.001  # Slightly above entry

        # Partial close
        if not getattr(position, "partial_tp_taken", False) and current_r >= 1.0:
            # Close 50% of position
            close_qty = position.size * 0.5
            # Partial close logic will be in engine
            position.partial_tp_taken = True


# Example usage
if __name__ == "__main__":
    # Test SMC strategy
    config = {"high_timeframe": "4h", "low_timeframe": "15m", "confluence_required": True, "risk_reward_ratio": 3.0}

    strategy = SMCStrategy(config)

    # Mock market data
    dates = pd.date_range("2023-01-01", periods=100, freq="15min")
    np.random.seed(42)
    prices = 50000 + np.cumsum(np.random.randn(100) * 10)

    mock_data = {
        "4h": pd.DataFrame(
            {
                "open": prices[::16],
                "high": prices[::16] + np.random.rand(len(prices[::16])) * 50,
                "low": prices[::16] - np.random.rand(len(prices[::16])) * 50,
                "close": prices[::16] + np.random.randn(len(prices[::16])) * 20,
                "volume": np.random.randint(1000, 10000, len(prices[::16])),
            },
            index=dates[::16],
        ),
        "15m": pd.DataFrame(
            {
                "open": prices,
                "high": prices + np.random.rand(100) * 20,
                "low": prices - np.random.rand(100) * 20,
                "close": prices + np.random.randn(100) * 10,
                "volume": np.random.randint(1000, 10000, 100),
            },
            index=dates,
        ),
    }

    # Generate signals
    signals = strategy.generate_signals(mock_data)
    print(f"Generated {len(signals)} signals")

    for signal in signals:
        print(f"Signal: {signal}")

    # Get strategy info
    info = strategy.get_strategy_info()
    print(f"Strategy info: {info}")
