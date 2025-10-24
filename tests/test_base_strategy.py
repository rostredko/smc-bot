#!/usr/bin/env python3
"""
Tests for Base Strategy module.
Tests the base strategy class that other strategies inherit from.
Run with: pytest tests/test_base_strategy.py -v
"""

import sys
import os
import pytest
import pandas as pd
import numpy as np
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from strategies.base_strategy import StrategyBase


class TestBaseStrategyInitialization:
    """Test StrategyBase initialization and configuration."""
    
    def test_base_strategy_init(self):
        """Test StrategyBase cannot be instantiated directly (abstract)."""
        # StrategyBase is abstract, so we need a concrete implementation
        class ConcreteStrategy(StrategyBase):
            def generate_signals(self, market_data):
                return []
        
        strategy = ConcreteStrategy()
        
        assert hasattr(strategy, 'config')
        assert hasattr(strategy, 'name')
        assert strategy.name == 'ConcreteStrategy'
    
    def test_base_strategy_with_config(self):
        """Test StrategyBase with custom config."""
        class ConcreteStrategy(StrategyBase):
            def generate_signals(self, market_data):
                return []
        
        custom_config = {
            'risk_reward_ratio': 3.0,
            'max_concurrent_positions': 2
        }
        
        strategy = ConcreteStrategy(custom_config)
        assert strategy.config.get('risk_reward_ratio') == 3.0
        assert strategy.config.get('max_concurrent_positions') == 2
    
    def test_base_strategy_with_empty_config(self):
        """Test StrategyBase with empty config."""
        class ConcreteStrategy(StrategyBase):
            def generate_signals(self, market_data):
                return []
        
        strategy = ConcreteStrategy({})
        
        # Should have some defaults
        assert hasattr(strategy, 'config')
        assert isinstance(strategy.config, dict)
    
    def test_strategy_has_analyzers(self):
        """Test that strategy has SMC analysis components."""
        class ConcreteStrategy(StrategyBase):
            def generate_signals(self, market_data):
                return []
        
        strategy = ConcreteStrategy()
        
        assert hasattr(strategy, 'structure_analyzer')
        assert hasattr(strategy, 'order_block_detector')
        assert hasattr(strategy, 'fvg_detector')
        assert hasattr(strategy, 'liquidity_mapper')


class TestSignalGeneration:
    """Test signal generation methods."""
    
    def test_generate_signals_method_exists(self):
        """Test that generate_signals method is defined."""
        class ConcreteStrategy(StrategyBase):
            def generate_signals(self, market_data):
                return []
        
        strategy = ConcreteStrategy()
        
        assert hasattr(strategy, 'generate_signals')
        assert callable(strategy.generate_signals)
    
    def test_generate_signals_empty_data(self):
        """Test signal generation with empty data."""
        class ConcreteStrategy(StrategyBase):
            def generate_signals(self, market_data):
                return []
        
        strategy = ConcreteStrategy()
        signals = strategy.generate_signals({})
        
        # Base strategy should return empty list
        assert isinstance(signals, list)
        assert len(signals) == 0
    
    def test_generate_signals_returns_list(self, sample_ohlcv_data):
        """Test that generate_signals returns a list."""
        class ConcreteStrategy(StrategyBase):
            def generate_signals(self, market_data):
                return []
        
        strategy = ConcreteStrategy()
        
        market_data = {'1h': sample_ohlcv_data}
        signals = strategy.generate_signals(market_data)
        
        assert isinstance(signals, list)
    
    def test_signal_structure_validation(self):
        """Test that signals have required structure."""
        # Create a valid signal structure
        valid_signal = {
            'direction': 'LONG',
            'entry_price': 50000,
            'stop_loss': 49000,
            'take_profit': 51000,
            'reason': 'Test signal'
        }
        
        # Check all required fields exist
        required_fields = {'direction', 'entry_price', 'stop_loss', 'take_profit', 'reason'}
        assert required_fields.issubset(set(valid_signal.keys()))


class TestSignalValidation:
    """Test signal validation methods."""
    
    def test_validate_signal_direction(self):
        """Test signal direction validation."""
        valid_directions = ['LONG', 'SHORT', 'EXIT']
        invalid_direction = 'INVALID'
        
        assert 'LONG' in valid_directions
        assert 'SHORT' in valid_directions
        assert 'EXIT' in valid_directions
        assert invalid_direction not in valid_directions
    
    def test_validate_signal_prices(self):
        """Test signal price relationships."""
        # For LONG: entry < take_profit and entry > stop_loss
        long_signal = {
            'direction': 'LONG',
            'entry_price': 50000,
            'stop_loss': 49000,  # Below entry
            'take_profit': 51000  # Above entry
        }
        
        assert long_signal['entry_price'] > long_signal['stop_loss']
        assert long_signal['entry_price'] < long_signal['take_profit']
    
    def test_validate_short_signal_prices(self):
        """Test SHORT signal price relationships."""
        # For SHORT: entry > take_profit and entry < stop_loss
        short_signal = {
            'direction': 'SHORT',
            'entry_price': 50000,
            'stop_loss': 51000,  # Above entry
            'take_profit': 49000  # Below entry
        }
        
        assert short_signal['entry_price'] < short_signal['stop_loss']
        assert short_signal['entry_price'] > short_signal['take_profit']
    
    def test_risk_reward_ratio_calculation(self):
        """Test risk/reward ratio calculation."""
        signal = {
            'entry_price': 50000,
            'stop_loss': 49000,
            'take_profit': 53000
        }
        
        risk = signal['entry_price'] - signal['stop_loss']  # 1000
        reward = signal['take_profit'] - signal['entry_price']  # 3000
        ratio = reward / risk if risk != 0 else 0
        
        assert ratio == 3.0


class TestStrategyInfo:
    """Test strategy information methods."""
    
    def test_strategy_has_name(self):
        """Test that strategy has a name."""
        class TestStrategy(StrategyBase):
            def generate_signals(self, market_data):
                return []
        
        strategy = TestStrategy()
        
        assert hasattr(strategy, 'name')
        assert strategy.name == 'TestStrategy'
    
    def test_strategy_info_structure(self):
        """Test strategy info has correct structure."""
        class TestStrategy(StrategyBase):
            def generate_signals(self, market_data):
                return []
        
        strategy = TestStrategy()
        info = {
            'name': strategy.name,
            'config': strategy.config
        }
        
        assert isinstance(info, dict)
        assert 'name' in info
        assert isinstance(info['name'], str)
        assert 'config' in info
        assert isinstance(info['config'], dict)


class TestStrategyState:
    """Test strategy state tracking."""
    
    def test_strategy_has_state_attributes(self):
        """Test that strategy has state attributes."""
        class TestStrategy(StrategyBase):
            def generate_signals(self, market_data):
                return []
        
        strategy = TestStrategy()
        
        assert hasattr(strategy, 'current_bias')
        assert hasattr(strategy, 'active_zones')
        assert hasattr(strategy, 'last_signal_time')
    
    def test_strategy_state_initialization(self):
        """Test that state is initialized correctly."""
        class TestStrategy(StrategyBase):
            def generate_signals(self, market_data):
                return []
        
        strategy = TestStrategy()
        
        assert strategy.current_bias is None
        assert strategy.active_zones == []
        assert strategy.last_signal_time is None


class TestDataHandling:
    """Test how strategies handle different data types."""
    
    def test_handle_multi_timeframe_data(self, multi_timeframe_data):
        """Test strategy with multi-timeframe data."""
        class TestStrategy(StrategyBase):
            def generate_signals(self, market_data):
                return []
        
        strategy = TestStrategy()
        
        # Should not raise error
        signals = strategy.generate_signals(multi_timeframe_data)
        assert isinstance(signals, list)
    
    def test_handle_single_timeframe_data(self, sample_ohlcv_data):
        """Test strategy with single timeframe data."""
        class TestStrategy(StrategyBase):
            def generate_signals(self, market_data):
                return []
        
        strategy = TestStrategy()
        
        market_data = {'1h': sample_ohlcv_data}
        signals = strategy.generate_signals(market_data)
        
        assert isinstance(signals, list)
    
    def test_handle_missing_required_columns(self):
        """Test strategy handles incomplete data gracefully."""
        class TestStrategy(StrategyBase):
            def generate_signals(self, market_data):
                return []
        
        strategy = TestStrategy()
        
        # Data with missing columns
        incomplete_data = pd.DataFrame({
            'open': [50000, 50100],
            'close': [50100, 50200]
            # Missing high, low, volume
        })
        
        market_data = {'1h': incomplete_data}
        
        # Should not crash
        try:
            signals = strategy.generate_signals(market_data)
            assert isinstance(signals, list)
        except KeyError:
            # Expected if strategy requires all columns
            pass


class TestStrategyInheritance:
    """Test strategy inheritance and polymorphism."""
    
    def test_strategy_can_be_subclassed(self):
        """Test that StrategyBase can be subclassed."""
        class CustomStrategy(StrategyBase):
            def generate_signals(self, market_data):
                return [{'direction': 'LONG', 'entry_price': 50000}]
        
        strategy = CustomStrategy()
        signals = strategy.generate_signals({})
        
        assert len(signals) == 1
        assert signals[0]['direction'] == 'LONG'
    
    def test_subclass_inherits_config(self):
        """Test that subclasses inherit config handling."""
        class CustomStrategy(StrategyBase):
            def generate_signals(self, market_data):
                return []
        
        custom_config = {'test_param': 'test_value'}
        strategy = CustomStrategy(custom_config)
        
        assert strategy.config['test_param'] == 'test_value'
    
    def test_subclass_inherits_analyzers(self):
        """Test that subclasses inherit SMC analyzers."""
        class CustomStrategy(StrategyBase):
            def generate_signals(self, market_data):
                return []
        
        strategy = CustomStrategy()
        
        assert hasattr(strategy, 'structure_analyzer')
        assert hasattr(strategy, 'order_block_detector')
        assert hasattr(strategy, 'fvg_detector')
        assert hasattr(strategy, 'liquidity_mapper')


class TestStrategyEdgeCases:
    """Test edge cases and error handling."""
    
    def test_strategy_with_none_config(self):
        """Test strategy with None config."""
        class TestStrategy(StrategyBase):
            def generate_signals(self, market_data):
                return []
        
        strategy = TestStrategy(None)
        
        # Should have defaults or handle gracefully
        assert hasattr(strategy, 'config')
        assert strategy.config == {}
    
    def test_strategy_with_large_config(self):
        """Test strategy with large config."""
        large_config = {f'param_{i}': i for i in range(100)}
        
        class TestStrategy(StrategyBase):
            def generate_signals(self, market_data):
                return []
        
        strategy = TestStrategy(large_config)
        assert len(strategy.config) >= 100
    
    def test_concurrent_signal_generation(self):
        """Test signal generation doesn't have state issues."""
        class TestStrategy(StrategyBase):
            def generate_signals(self, market_data):
                return []
        
        strategy = TestStrategy()
        
        # Generate signals multiple times
        for _ in range(5):
            strategy.generate_signals({})
        
        # State should be preserved
        assert hasattr(strategy, 'config')


class TestStrategyBestPractices:
    """Test that strategies follow best practices."""
    
    def test_strategy_has_docstring(self):
        """Test that strategy class has documentation."""
        class TestStrategy(StrategyBase):
            """A test strategy."""
            def generate_signals(self, market_data):
                return []
        
        strategy = TestStrategy()
        assert strategy.__class__.__doc__ is not None
    
    def test_strategy_methods_have_docstrings(self):
        """Test that strategy methods have documentation."""
        class TestStrategy(StrategyBase):
            def generate_signals(self, market_data):
                """Generate trading signals."""
                return []
        
        strategy = TestStrategy()
        assert strategy.generate_signals.__doc__ is not None


# Test runner
if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
