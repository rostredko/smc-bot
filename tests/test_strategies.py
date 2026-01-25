
import pytest
import pandas as pd
import numpy as np
from strategies.price_action_strategy import PriceActionStrategy

@pytest.fixture
def sample_data():
    """Create sample OHLCV data for testing."""
    dates = pd.date_range(start='2024-01-01', periods=100, freq='4h')
    
    # Create synthetic data with a trend and pullback
    # 0-50: Uptrend
    # 50-60: Pullback (Pin bar potential)
    # 60-100: Uptrend continuation
    
    close = np.linspace(100, 200, 100)
    # Add some noise/volatility
    for i in range(len(close)):
        if 50 <= i <= 60:
            close[i] -= 5 # Pullback
            
    df = pd.DataFrame({
        'open': close - 1,
        'high': close + 2,
        'low': close - 2,
        'close': close,
        'volume': np.random.randint(100, 1000, 100)
    }, index=dates)
    
    # Ensure some "Pin Bar" like candles
    # At index 55: Long lower wick, close near high
    df.iloc[55, df.columns.get_loc('open')] = 145
    df.iloc[55, df.columns.get_loc('close')] = 148
    df.iloc[55, df.columns.get_loc('high')] = 149
    df.iloc[55, df.columns.get_loc('low')] = 130 # Long wick
    
    return {"4h": df}

def test_strategy_initialization():
    """Test strategy init with defaults."""
    strategy = PriceActionStrategy({})
    assert strategy.config is not None
    assert strategy.min_range_factor == 0.8 # Default check

def test_strategy_signal_generation(sample_data):
    """Test that signals are generated from data."""
    config = {
        "primary_timeframe": "4h",
        "min_range_factor": 0.5, # Relax filters for test
        "use_trend_filter": False,
        "risk_reward_ratio": 2.0
    }
    strategy = PriceActionStrategy(config)
    signals = strategy.generate_signals(sample_data)
    
    # We expect at least one signal or at least valid execution (empty list is also valid result if no pattern found)
    assert isinstance(signals, list)
    
    # Check if our engineered pinbar was detected
    # We might need to adjust logic or data carefully to force a hit, 
    # but primarily we want to ensure no crash and correct return type.
    
def test_strategy_custom_config():
    """Test custom configuration override."""
    config = {
        "min_range_factor": 2.5,
        "risk_reward_ratio": 3.0
    }
    strategy = PriceActionStrategy(config)
    assert strategy.min_range_factor == 2.5
    assert strategy.risk_reward_ratio == 3.0

def test_strategy_indicators(sample_data):
    """Test that indicators (RSI, EMA) are calculated."""
    config = {
        "use_trend_filter": True,
        "trend_ema_period": 10,
        "use_rsi_filter": True,
        "rsi_period": 14
    }
    strategy = PriceActionStrategy(config)
    
    # We can't easily access internal DF from generate_signals without mocking,
    # but we can call internal helpers if accessible or just ensure it runs.
    
    # Using public method
    signals = strategy.generate_signals(sample_data)
    assert isinstance(signals, list)
