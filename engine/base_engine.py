from abc import ABC, abstractmethod
from typing import Dict, Any

# Apply OCO guard before any Cerebro/broker creation (fixes ghost-trade same-bar double fill)
from engine.bt_oco_patch import apply_oco_guard
from engine.timeframe_utils import ordered_timeframes
from engine.execution_settings import apply_execution_settings
apply_oco_guard()

import backtrader as bt


class BaseEngine(ABC):
    """
    Abstract base class for Backtrader-based engines.
    Handles common comprehensive setup for Cerebro.
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = apply_execution_settings(config)
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

        commission = self.config.get("commission", 0.0004)
        leverage = self.config.get("leverage", 1.0)
        self.cerebro.broker.setcommission(commission=commission, leverage=leverage)

        slip_perc = self.config.get("slippage_perc", 0.0)
        if not slip_perc:
            try:
                slip_perc = float(self.config.get("slippage_bps", 0.0)) / 10000.0
            except (TypeError, ValueError):
                slip_perc = 0.0
        try:
            slip_perc = float(slip_perc)
        except (TypeError, ValueError):
            slip_perc = 0.0
        if slip_perc > 0:
            # Apply slippage to market/stop-style fills but not to passive take-profit limits.
            self.cerebro.broker.set_slippage_perc(
                slip_perc,
                slip_open=True,
                slip_limit=False,
                slip_match=True,
                slip_out=False,
            )
        
        # Allow fractional sizing for crypto
        self.cerebro.broker.set_coo(True) 

    def _setup_sizers(self):
        """Position sizing is handled dynamically inside the strategy itself."""
        pass

    def _ordered_timeframes(self, timeframes):
        """
        Always add lower timeframe first so multi-timeframe strategies receive:
        data0 = LTF, data1 = HTF, regardless of config array order.
        """
        return ordered_timeframes(timeframes)


    @abstractmethod
    def add_data(self):
        """Add data feeds to Cerebro."""
        pass

    def add_strategy(self, strategy_class, **kwargs):
        """Add a strategy to Cerebro."""
        self.cerebro.addstrategy(strategy_class, **kwargs)

    def run(self):
        """Run the engine."""
        return self.cerebro.run(runonce=False)
