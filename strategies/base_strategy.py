"""
Strategy Base Interface and Example SMC Strategy Implementation.
Defines the standard interface for trading strategies and provides an example SMC-based strategy.
"""

import pandas as pd
from typing import Dict, List, Optional, Any
from abc import ABC, abstractmethod

from engine.smc_analysis import MarketStructureAnalyzer, OrderBlockDetector, FairValueGapDetector, LiquidityZoneMapper


class StrategyBase(ABC):
    """
    Abstract base class for trading strategies.
    All strategies must implement the generate_signals method.
    """

    def __init__(self, config: Optional[Dict] = None):
        """
        Initialize strategy with optional configuration.

        Args:
            config: Strategy configuration dictionary
        """
        self.config = config or {}
        self.name = self.__class__.__name__

        # Strategy state
        self.current_bias = None
        self.active_zones = []
        self.last_signal_time = None

        # Initialize SMC analyzers
        self.structure_analyzer = MarketStructureAnalyzer()
        self.order_block_detector = OrderBlockDetector()
        self.fvg_detector = FairValueGapDetector()
        self.liquidity_mapper = LiquidityZoneMapper()

    @abstractmethod
    def generate_signals(self, market_data: Dict[str, pd.DataFrame]) -> List[Dict[str, Any]]:
        """
        Generate trading signals based on market data.

        Args:
            market_data: Dictionary mapping timeframe to DataFrame

        Returns:
            List of signal dictionaries or empty list if no signals
        """
        pass

    def on_trade_exit(self, position) -> None:
        """
        Callback when a trade is closed.
        Can be overridden by strategies to update internal state.

        Args:
            position: Closed Position object
        """
        pass

    def get_strategy_info(self) -> Dict[str, Any]:
        """Get strategy information and parameters."""
        return {"name": self.name, "config": self.config, "current_bias": self.current_bias, "active_zones": len(self.active_zones)}

    def reset_state(self):
        """Reset strategy state (useful for new backtest runs)."""
        self.current_bias = None
        self.active_zones = []
        self.last_signal_time = None


# Example usage
if __name__ == "__main__":
    # Test strategy interface
    class TestStrategy(StrategyBase):
        def generate_signals(self, market_data):
            return []

    strategy = TestStrategy()
    print(f"Strategy created: {strategy.name}")
    print(f"Strategy info: {strategy.get_strategy_info()}")
