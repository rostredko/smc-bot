
"""
Automated tests for SMC Trading Engine (Updated for backtesting.py integration).
Run with: pytest tests/test_engine.py -v
"""

import sys
import os
import pytest
import pandas as pd
from unittest.mock import MagicMock, patch

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from engine.backtest_engine import BacktestEngine
from strategies.price_action_strategy import PriceActionStrategy # Direct import for testing

class TestBacktestEngineIntegration:
    """Test BacktestEngine wrapper around backtesting.py."""
    
    @pytest.fixture
    def mock_data_loader(self):
        with patch('engine.backtest_engine.DataLoader') as MockLoader:
            instance = MockLoader.return_value
            # Create sample dataframe with standard columns required by backtesting.py
            dates = pd.date_range(start='2023-01-01', periods=100, freq='1h')
            df = pd.DataFrame({
                "open": [100 + i for i in range(100)],
                "high": [105 + i for i in range(100)],
                "low": [95 + i for i in range(100)],
                "close": [102 + i for i in range(100)],
                "volume": [1000 for _ in range(100)]
            }, index=dates)
            instance.get_data.return_value = df
            yield instance

    def test_initialization(self, mock_data_loader):
        """Test engine initializes correctly with config."""
        config = {
            "initial_capital": 10000,
            "symbol": "BTC/USDT",
            "start_date": "2023-01-01",
            "end_date": "2023-02-01",
            "strategy": "price_action_strategy"
        }
        
        engine = BacktestEngine(config)
        assert engine.initial_capital == 10000
        assert engine.strategy_class is not None
        # Should detect PriceActionStrategy from name
        assert engine.strategy_class.__name__ == 'PriceActionStrategy'

    def test_data_loading(self, mock_data_loader):
        """Test data loading isolates and renames columns."""
        config = {
            "initial_capital": 10000,
            "symbol": "BTC/USDT",
            "start_date": "2023-01-01",
            "end_date": "2023-02-01"
        }
        engine = BacktestEngine(config)
        engine.load_data()
        
        # Check normalization (Title Case for backtesting.py)
        assert 'Open' in engine.data.columns
        assert 'Close' in engine.data.columns
        assert len(engine.data) == 100

    def test_run_backtest_execution(self, mock_data_loader):
        """Test full execution flow (mocked data)."""
        config = {
            "initial_capital": 10000,
            "symbol": "BTC/USDT",
            "start_date": "2023-01-01",
            "end_date": "2023-02-01",
            "strategy": "price_action_strategy",
            # Relax filters to ensure at least some activity or valid run
            "strategy_config": {
                "use_trend_filter": False,
                "use_rsi_filter": False
            }
        }
        engine = BacktestEngine(config)
        engine.load_data()
        
        # Run backtest
        metrics = engine.run_backtest()
        
        # Check metrics structure
        assert "total_return_pct" in metrics
        assert "win_rate" in metrics
        assert "total_trades" in metrics
        assert "equity_final" in metrics
        assert isinstance(metrics["closed_trades"], list)
        
        # Since date is monotonic up, PriceActionStrategy might trigger some signals
        # depending on patterns. We just verify it ran without error and returned dict.
        assert engine.bt_instance is not None

if __name__ == '__main__':
    pytest.main([__file__, '-v'])
