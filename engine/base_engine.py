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
        """Add a strategy to Cerebro, filtering out invalid params."""
        filtered_kwargs = self._filter_strategy_params(strategy_class, kwargs)
        self.cerebro.addstrategy(strategy_class, **filtered_kwargs)

    def add_opt_strategy(self, strategy_class, **kwargs):
        """Add a strategy for parameter optimization, filtering out invalid params."""
        filtered_kwargs = self._filter_strategy_params(strategy_class, kwargs)
        self.cerebro.optstrategy(strategy_class, **filtered_kwargs)

    def _filter_strategy_params(self, strategy_class, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Filter kwargs to only include keys present in strategy_class.params."""
        if not hasattr(strategy_class, 'params'):
            return kwargs
        
        valid_keys = set()
        params = strategy_class.params
        
        # Case 1: Params is a tuple of tuples/lists (standard Backtrader strategy definition)
        if isinstance(params, (list, tuple)):
            for item in params:
                if isinstance(item, (list, tuple)) and len(item) >= 1:
                    valid_keys.add(item[0])
        # Case 2: Params is already an instantiated Params object (less common for class-level check)
        elif hasattr(params, '_getitems'):
            for k, _ in params._getitems():
                valid_keys.add(k)
        # Case 3: Simple attribute access (fallback)
        else:
            valid_keys = {attr for attr in dir(params) if not attr.startswith('_')}

        # Always allow some standard Backtrader internal params if they happen to be passed
        # though usually they aren't part of st_config.
        
        filtered = {k: v for k, v in kwargs.items() if k in valid_keys}
        
        # Log if we filtered anything out for debugging
        filtered_out = set(kwargs.keys()) - set(filtered.keys())
        if filtered_out:
            # We use a late import or just rely on self.config['log_level'] if we had a real logger
            # For now, we'll just let it be silent or use the engine logger if available
            pass
            
        return filtered

    def run(self):
        """Run the engine. runonce=True enables vectorized indicators (~2-3x faster)."""
        return self.cerebro.run(runonce=True)
