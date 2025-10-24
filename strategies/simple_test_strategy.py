"""
Simple test strategy for basic engine validation.
Generates simple MA crossover signals.
"""

import pandas as pd
from typing import Dict, List, Optional, Any
from strategies.base_strategy import StrategyBase


class SimpleTestStrategy(StrategyBase):
    """
    Simple strategy that generates signals based on basic price patterns.
    Used for testing the engine with guaranteed signals.
    """

    def __init__(self, config: Optional[Dict] = None):
        """Initialize simple test strategy."""
        default_config = {"signal_frequency": 10, "risk_reward_ratio": 2.0}  # Generate signal every N bars

        super().__init__(config)
        self.config = {**default_config, **self.config}

        # Strategy state
        self.bar_count = 0
        self.last_signal_bar = 0

        # Performance tracking
        self.signals_generated = 0
        self.signals_executed = 0

    def generate_signals(self, market_data: Dict[str, pd.DataFrame]) -> List[Dict[str, Any]]:
        """
        Generate simple test signals.

        Args:
            market_data: Dictionary with timeframe data

        Returns:
            List of signal dictionaries
        """
        signals = []

        # Use the lowest timeframe available
        timeframes = list(market_data.keys())
        if not timeframes:
            return signals

        # Get the most granular timeframe
        tf = min(timeframes, key=lambda x: self._get_timeframe_minutes(x))
        df = market_data[tf]

        if len(df) < 20:
            return signals

        # Generate signals every N bars
        current_bar = len(df) - 1

        if (current_bar - self.last_signal_bar) >= self.config["signal_frequency"]:
            current_price = df["close"].iloc[-1]

            # Simple alternating signal pattern
            if self.bar_count % 2 == 0:
                signal = self._create_long_signal(df, current_price)
            else:
                signal = self._create_short_signal(df, current_price)

            if signal:
                signals.append(signal)
                self.last_signal_bar = current_bar
                self.bar_count += 1

        # Update signals generated counter
        self.signals_generated += len(signals)

        return signals

    def _get_timeframe_minutes(self, timeframe: str) -> int:
        """Convert timeframe string to minutes."""
        if timeframe.endswith("m"):
            return int(timeframe[:-1])
        elif timeframe.endswith("h"):
            return int(timeframe[:-1]) * 60
        elif timeframe.endswith("d"):
            return int(timeframe[:-1]) * 24 * 60
        else:
            return 60  # Default to 1 hour

    def _create_long_signal(self, df: pd.DataFrame, current_price: float) -> Dict[str, Any]:
        """Create a long signal."""
        # Simple stop loss and take profit
        stop_loss = current_price * 0.98  # 2% stop loss
        take_profit = current_price * (1 + (current_price - stop_loss) * self.config["risk_reward_ratio"] / current_price)

        return {
            "direction": "LONG",
            "entry_price": current_price,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "reason": f"Simple test LONG signal #{self.bar_count}",
            "confidence": 0.8,
            "strategy": "SimpleTest",
        }

    def _create_short_signal(self, df: pd.DataFrame, current_price: float) -> Dict[str, Any]:
        """Create a short signal."""
        # Simple stop loss and take profit
        stop_loss = current_price * 1.02  # 2% stop loss
        take_profit = current_price * (1 - (stop_loss - current_price) * self.config["risk_reward_ratio"] / current_price)

        return {
            "direction": "SHORT",
            "entry_price": current_price,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "reason": f"Simple test SHORT signal #{self.bar_count}",
            "confidence": 0.8,
            "strategy": "SimpleTest",
        }

    def get_strategy_info(self) -> Dict[str, Any]:
        """Get strategy information."""
        base_info = super().get_strategy_info()
        base_info.update({"bar_count": self.bar_count, "last_signal_bar": self.last_signal_bar, "signal_frequency": self.config["signal_frequency"]})
        return base_info
