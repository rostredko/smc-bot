#!/usr/bin/env python3
"""
Pytest configuration and shared fixtures for all tests.
This file provides reusable test data and mocks to reduce duplication.
"""

import sys
import os

# Use mongomock for API tests (no real MongoDB required)
os.environ["USE_MONGOMOCK"] = "true"
os.environ["USE_DATABASE"] = "true"
import pytest
import pandas as pd
import numpy as np
from datetime import timedelta
from unittest.mock import MagicMock

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


# ============================================================================
# MARKET DATA FIXTURES
# ============================================================================

@pytest.fixture
def sample_ohlcv_data():
    """Create sample OHLCV data for testing."""
    dates = pd.date_range('2023-01-01', periods=100, freq='1h')
    np.random.seed(42)
    
    close_prices = 50000 + np.cumsum(np.random.randn(100) * 100)
    
    df = pd.DataFrame({
        'close': close_prices,
        'open': close_prices + np.random.randn(100) * 50,
        'volume': np.random.randint(1000, 10000, 100)
    }, index=dates)
    
    # Calculate high and low based on open and close
    df['high'] = df[['open', 'close']].max(axis=1) + np.random.rand(100) * 100
    df['low'] = df[['open', 'close']].min(axis=1) - np.random.rand(100) * 100
    
    # Ensure high >= low
    df = df[['open', 'high', 'low', 'close', 'volume']]
    
    return df


@pytest.fixture
def multi_timeframe_data():
    """Create multi-timeframe market data."""
    dates_4h = pd.date_range('2023-01-01', periods=50, freq='4h')
    dates_15m = pd.date_range('2023-01-01', periods=100, freq='15min')
    
    np.random.seed(42)
    close_4h = 50000 + np.cumsum(np.random.randn(50) * 100)
    close_15m = 50000 + np.cumsum(np.random.randn(100) * 50)
    
    # 4h data
    df_4h = pd.DataFrame({
        'close': close_4h,
        'open': close_4h + np.random.randn(50) * 50,
        'volume': np.random.randint(1000, 10000, 50)
    }, index=dates_4h)
    df_4h['high'] = df_4h[['open', 'close']].max(axis=1) + np.random.rand(50) * 100
    df_4h['low'] = df_4h[['open', 'close']].min(axis=1) - np.random.rand(50) * 100
    
    # 15m data
    df_15m = pd.DataFrame({
        'close': close_15m,
        'open': close_15m + np.random.randn(100) * 25,
        'volume': np.random.randint(1000, 10000, 100)
    }, index=dates_15m)
    df_15m['high'] = df_15m[['open', 'close']].max(axis=1) + np.random.rand(100) * 50
    df_15m['low'] = df_15m[['open', 'close']].min(axis=1) - np.random.rand(100) * 50
    
    return {
        '4h': df_4h[['open', 'high', 'low', 'close', 'volume']],
        '15m': df_15m[['open', 'high', 'low', 'close', 'volume']]
    }


@pytest.fixture
def minimal_ohlcv_data():
    """Create minimal OHLCV data for edge case testing."""
    dates = pd.date_range('2023-01-01', periods=5, freq='1h')
    return pd.DataFrame({
        'open': [50000, 50100, 50200, 50300, 50400],
        'high': [50200, 50300, 50400, 50500, 50600],
        'low': [49900, 50000, 50100, 50200, 50300],
        'close': [50100, 50200, 50300, 50400, 50500],
        'volume': [1000, 1500, 1200, 1800, 2000]
    }, index=dates)


@pytest.fixture
def trending_ohlcv_data():
    """Create trending market data with clear structure."""
    dates = pd.date_range('2023-01-01', periods=200, freq='15min')
    np.random.seed(42)
    
    # Upward trend
    trend = np.linspace(0, 1000, 200)
    noise = np.random.randn(200) * 50
    close = 50000 + trend + noise
    
    df = pd.DataFrame({
        'close': close,
        'open': close + np.random.randn(200) * 25,
        'volume': np.random.randint(1000, 20000, 200)
    }, index=dates)
    
    df['high'] = df[['open', 'close']].max(axis=1) + np.random.rand(200) * 100
    df['low'] = df[['open', 'close']].min(axis=1) - np.random.rand(200) * 100
    
    return df[['open', 'high', 'low', 'close', 'volume']]


# ============================================================================
# ENGINE COMPONENT FIXTURES
# ============================================================================

@pytest.fixture
def risk_manager():
    """Create a RiskManager instance for testing."""
    from engine.risk_manager import RiskManager
    return RiskManager(
        initial_capital=10000,
        leverage=1.0,
        risk_per_trade=2.0,
        max_drawdown=15.0,
        max_positions=3
    )


@pytest.fixture
def logger():
    """Create a Logger instance for testing."""
    from engine.logger import Logger
    return Logger("INFO")


@pytest.fixture
def performance_reporter():
    """Create a PerformanceReporter instance for testing."""
    from engine.metrics import PerformanceReporter
    return PerformanceReporter()


@pytest.fixture
def mock_position():
    """Create a mock Position for testing."""
    from engine.position import Position
    return Position(
        id=1,
        entry_price=50000,
        size=0.1,
        stop_loss=49000,
        take_profit=52000,
        direction='LONG'
    )


@pytest.fixture
def mock_closed_trade():
    """Create a mock closed trade for metrics testing."""
    class MockTrade:
        def __init__(self):
            self.realized_pnl = 100
            self.risk_amount = 100
            self.risk_reward_ratio = 2.0
            self.entry_time = pd.Timestamp('2023-01-01 10:00:00')
            self.exit_time = pd.Timestamp('2023-01-01 12:00:00')
    
    return MockTrade()


# ============================================================================
# STRATEGY FIXTURES
# ============================================================================

@pytest.fixture
def simple_test_strategy():
    """Create a SimpleTestStrategy instance."""
    from strategies.simple_test_strategy import SimpleTestStrategy
    return SimpleTestStrategy({
        'signal_frequency': 5,
        'risk_reward_ratio': 2.0
    })


@pytest.fixture
def smc_strategy():
    """Create an SMCStrategy instance."""
    from strategies.smc_strategy import SMCStrategy
    return SMCStrategy({
        'high_timeframe': '4h',
        'low_timeframe': '15m',
        'min_zone_strength': 0.6,
        'confluence_required': True
    })


# ============================================================================
# SMC ANALYSIS COMPONENT FIXTURES
# ============================================================================

@pytest.fixture
def order_block_detector():
    """Create an OrderBlockDetector instance."""
    from engine.smc_analysis import OrderBlockDetector
    return OrderBlockDetector(min_strength=0.6)


@pytest.fixture
def fvg_detector():
    """Create a FairValueGapDetector instance."""
    from engine.smc_analysis import FairValueGapDetector
    return FairValueGapDetector(min_gap_size=0.001)


@pytest.fixture
def liquidity_mapper():
    """Create a LiquidityZoneMapper instance."""
    from engine.smc_analysis import LiquidityZoneMapper
    return LiquidityZoneMapper(sweep_threshold=0.002)


# ============================================================================
# MOCK FIXTURES
# ============================================================================

@pytest.fixture
def mock_exchange():
    """Create a mocked exchange object."""
    mock = MagicMock()
    mock.name = 'Binance'
    mock.countries = ['US']
    mock.rateLimit = 1200
    mock.has = {'futures': True, 'spot': True}
    mock.load_markets.return_value = {
        'BTC/USDT': {'id': 'BTCUSDT', 'symbol': 'BTC/USDT', 'base': 'BTC', 'quote': 'USDT'},
        'ETH/USDT': {'id': 'ETHUSDT', 'symbol': 'ETH/USDT', 'base': 'ETH', 'quote': 'USDT'}
    }
    return mock


@pytest.fixture
def mock_data_loader():
    """Create a mocked DataLoader."""
    mock = MagicMock()
    mock.fetch_ohlcv = MagicMock()
    return mock


# ============================================================================
# CONFIGURATION FIXTURES
# ============================================================================

@pytest.fixture
def backtest_config():
    """Create a standard backtest configuration."""
    return {
        'initial_capital': 10000,
        'risk_per_trade': 2.0,
        'max_drawdown': 15.0,
        'max_positions': 3,
        'leverage': 10.0,
        'symbol': 'BTC/USDT',
        'timeframes': ['4h', '15m'],
        'start_date': '2023-01-01',
        'end_date': '2023-01-31',
        'strategy': 'simple_test_strategy',
        'exchange': 'binance',
        'log_level': 'INFO'
    }


@pytest.fixture
def spot_config():
    """Create a spot trading configuration."""
    return {
        'initial_capital': 10000,
        'risk_per_trade': 0.5,
        'max_drawdown': 15.0,
        'max_positions': 1,
        'leverage': 1.0,
        'symbol': 'BTC/USDT',
        'timeframes': ['4h', '15m'],
        'strategy': 'smc_strategy',
        'exchange': 'binance',
        'log_level': 'INFO'
    }


# ============================================================================
# TEST UTILITIES
# ============================================================================

@pytest.fixture
def create_sample_trades():
    """Factory fixture to create sample trades."""
    def _create_trades(count=4, pnl_values=None):
        """Create mock trades with specified PnL values."""
        if pnl_values is None:
            pnl_values = [100, -50, 150, -50]
        
        trades = []
        for i, pnl in enumerate(pnl_values[:count]):
            class MockTrade:
                def __init__(self, trade_id, realized_pnl):
                    self.id = trade_id
                    self.realized_pnl = realized_pnl
                    self.risk_amount = 100
                    self.risk_reward_ratio = 2.0
                    self.entry_time = pd.Timestamp('2023-01-01') + timedelta(hours=i)
                    self.exit_time = pd.Timestamp('2023-01-01') + timedelta(hours=i+1)
            
            trades.append(MockTrade(i+1, pnl))
        
        return trades
    
    return _create_trades


# ============================================================================
# PYTEST HOOKS
# ============================================================================

def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests"
    )
    config.addinivalue_line(
        "markers", "unit: marks tests as unit tests"
    )
    config.addinivalue_line(
        "markers", "strategy: marks tests as strategy tests"
    )
    config.addinivalue_line(
        "markers", "data_loader: marks tests for data loader"
    )
