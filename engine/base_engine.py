from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import backtrader as bt

class BaseEngine(ABC):
    """
    Abstract base class for Backtrader-based engines.
    Handles common comprehensive setup for Cerebro.
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.cerebro = bt.Cerebro()
        self.strategy = None
        self.should_cancel = False
        
        # Compatibility logger
        class MockLogger:
            def __init__(self): self.logs = []
            def log(self, *args, **kwargs): pass
            
        self.logger = MockLogger()
        
        # Set up base configuration
        self._setup_broker()
        self._setup_sizers()

    def _setup_broker(self):
        """Configure the broker (cash, commission)."""
        initial_capital = self.config.get("initial_capital", 10000.0)
        self.cerebro.broker.setcash(initial_capital)

        commission = self.config.get("commission", 0.0004) # Default 0.04% for crypto
        self.cerebro.broker.setcommission(commission=commission)
        
        # Allow fractional sizing for crypto
        self.cerebro.broker.set_coo(True) 

    def _setup_sizers(self):
        """Configure position sizing."""
        # Default to a simple sizer, strategies can override or we can make this configurable
        risk_per_trade = self.config.get("risk_per_trade", 2.0)
        # We might want a custom sizer that takes risk into account, 
        # but for now let's stick to a PercentSizer or similar if applicable, 
        # or handle sizing in the strategy itself.
        # Let's use a fixed sizer for now and let strategy manage size dynamically if needed.
        # Use PercentSizer to trade 10% of portfolio by default
        self.cerebro.addsizer(bt.sizers.PercentSizer, percents=10)

    @abstractmethod
    def add_data(self):
        """Add data feeds to Cerebro."""
        pass

    def add_strategy(self, strategy_class, **kwargs):
        """Add a strategy to Cerebro."""
        self.cerebro.addstrategy(strategy_class, **kwargs)

    def run(self):
        """Run the engine."""
        return self.cerebro.run()
