#!/usr/bin/env python3
"""
Tests for SMC trading strategies.
Focused on strategy-specific functionality that changes frequently.
Run with: pytest tests/test_strategies.py -v
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

from strategies.simple_test_strategy import SimpleTestStrategy
from strategies.smc_strategy import SMCStrategy


class TestSimpleTestStrategySignals:
    """Test SimpleTestStrategy signal generation (strategy-specific tests)."""
    
    @pytest.mark.strategy
    def test_signal_generation_sufficient_data(self, simple_test_strategy, trending_ohlcv_data):
        """Test signal generation with sufficient data."""
        market_data = {'1h': trending_ohlcv_data}
        signals = simple_test_strategy.generate_signals(market_data)
        
        assert isinstance(signals, list)
        assert len(signals) > 0
    
    @pytest.mark.strategy
    def test_signal_structure(self, simple_test_strategy, sample_ohlcv_data):
        """Test that generated signals have correct structure."""
        market_data = {'1h': sample_ohlcv_data}
        signals = simple_test_strategy.generate_signals(market_data)
        
        if signals:
            signal = signals[0]
            required_fields = ['direction', 'entry_price', 'stop_loss', 'take_profit', 'reason']
            for field in required_fields:
                assert field in signal, f"Missing field: {field}"
            assert signal['direction'] in ['LONG', 'SHORT']
            assert isinstance(signal['entry_price'], (int, float))


class TestSMCStrategyCore:
    """Test core SMC strategy functionality."""
    
    @pytest.mark.strategy
    def test_smc_strategy_multi_timeframe(self, smc_strategy, multi_timeframe_data):
        """Test SMC strategy with multi-timeframe data."""
        signals = smc_strategy.generate_signals(multi_timeframe_data)
        
        assert isinstance(signals, list)
    
    @pytest.mark.strategy
    def test_adaptive_stop_loss_calculation(self, smc_strategy, multi_timeframe_data):
        """Test adaptive stop loss calculation."""
        # Extract data
        low_df = multi_timeframe_data.get('15m')
        high_df = multi_timeframe_data.get('4h')
        
        if low_df is not None and high_df is not None:
            current_price = low_df['close'].iloc[-1]
            
            # Test for both directions
            for direction in ['LONG', 'SHORT']:
                stop_loss = smc_strategy._calculate_adaptive_stop_loss(
                    low_df, high_df, current_price, direction
                )
                
                assert isinstance(stop_loss, (int, float))
                assert stop_loss > 0
                
                if direction == 'LONG':
                    assert stop_loss < current_price, "LONG stop should be below entry"
                else:
                    assert stop_loss > current_price, "SHORT stop should be above entry"
    
    @pytest.mark.strategy
    def test_enhanced_signal_filter(self, smc_strategy, multi_timeframe_data):
        """Test enhanced signal filtering."""
        low_df = multi_timeframe_data.get('15m')
        high_df = multi_timeframe_data.get('4h')
        
        if low_df is not None and high_df is not None:
            signal = {
                'direction': 'LONG',
                'confidence': 0.8,
                'timestamp': datetime.now()
            }
            
            result = smc_strategy._enhanced_signal_filter(signal, low_df, high_df)
            assert isinstance(result, bool)
    
    @pytest.mark.strategy
    def test_macd_calculation(self, smc_strategy, sample_ohlcv_data):
        """Test MACD calculation."""
        macd_line, signal_line, histogram = smc_strategy._calculate_macd(sample_ohlcv_data)
        
        assert isinstance(macd_line, (int, float))
        assert isinstance(signal_line, (int, float))
        assert isinstance(histogram, (int, float))
    
    @pytest.mark.strategy
    def test_volatility_optimal_check(self, smc_strategy, multi_timeframe_data):
        """Test volatility optimal check."""
        low_df = multi_timeframe_data.get('15m')
        high_df = multi_timeframe_data.get('4h')
        
        if low_df is not None and high_df is not None:
            result = smc_strategy._is_optimal_volatility(low_df, high_df)
            assert isinstance(result, (bool, np.bool_))
    
    @pytest.mark.strategy
    def test_volume_confirmation(self, smc_strategy, sample_ohlcv_data):
        """Test volume confirmation check."""
        result = smc_strategy._has_strong_volume_confirmation(sample_ohlcv_data)
        assert isinstance(result, (bool, np.bool_))


class TestSMCStrategySignals:
    """Test SMC strategy signal generation."""
    
    @pytest.mark.strategy
    def test_signal_generation_with_mocks(self, smc_strategy, multi_timeframe_data):
        """Test SMC signal generation with mocked components."""
        # Mock the analysis components
        smc_strategy.order_block_detector = Mock()
        smc_strategy.order_block_detector.find_premium_discount_zones.return_value = {
            'premium': {'low': 52000, 'high': 53000},
            'discount': {'low': 47000, 'high': 48000}
        }
        smc_strategy.order_block_detector.find_order_blocks.return_value = []
        
        smc_strategy.fvg_detector = Mock()
        smc_strategy.fvg_detector.scan_for_gaps.return_value = []
        
        smc_strategy.liquidity_mapper = Mock()
        smc_strategy.liquidity_mapper.identify_liquidity_sweeps.return_value = []
        
        smc_strategy.structure_analyzer = Mock()
        smc_strategy.structure_analyzer.detect_structure_breaks.return_value = {}
        smc_strategy.structure_analyzer.detect_choch.return_value = {}
        
        signals = smc_strategy.generate_signals(multi_timeframe_data)
        assert isinstance(signals, list)
    
    @pytest.mark.strategy
    def test_signal_confidence_levels(self, smc_strategy, multi_timeframe_data):
        """Test that signals have confidence levels."""
        # Mock components for consistent signals
        smc_strategy.order_block_detector = Mock()
        smc_strategy.order_block_detector.find_premium_discount_zones.return_value = {
            'discount': {'low': 47000, 'high': 48000}
        }
        smc_strategy.order_block_detector.find_order_blocks.return_value = []
        smc_strategy.fvg_detector = Mock()
        smc_strategy.fvg_detector.scan_for_gaps.return_value = []
        smc_strategy.liquidity_mapper = Mock()
        smc_strategy.liquidity_mapper.identify_liquidity_sweeps.return_value = []
        smc_strategy.structure_analyzer = Mock()
        smc_strategy.structure_analyzer.detect_structure_breaks.return_value = {}
        smc_strategy.structure_analyzer.detect_choch.return_value = {}
        
        signals = smc_strategy.generate_signals(multi_timeframe_data)
        
        # If signals are generated, check confidence
        if signals:
            for signal in signals:
                if 'confidence' in signal:
                    assert 0 <= signal['confidence'] <= 1


class TestStrategyIntegrationWithEngine:
    """Test strategy integration with engine components."""
    
    @pytest.mark.integration
    @pytest.mark.strategy
    def test_strategy_with_risk_manager(self, smc_strategy, risk_manager, sample_ohlcv_data):
        """Test strategy integration with risk manager."""
        market_data = {'1h': sample_ohlcv_data}
        signals = smc_strategy.generate_signals(market_data)
        
        # Verify risk manager can validate signals
        for signal in signals:
            can_open, _ = risk_manager.can_open_position(
                signal['entry_price'],
                signal['stop_loss']
            )
            assert isinstance(can_open, bool)
    
    @pytest.mark.integration
    @pytest.mark.strategy
    def test_strategy_with_logger(self, smc_strategy, logger, multi_timeframe_data):
        """Test strategy with logger."""
        signals = smc_strategy.generate_signals(multi_timeframe_data)
        
        for signal in signals:
            logger.log("INFO", f"Signal: {signal['direction']} at {signal['entry_price']}")
        
        assert logger.trade_count >= 0


class TestStrategyPerformance:
    """Test strategy performance characteristics."""
    
    @pytest.mark.strategy
    def test_signal_generation_performance(self, smc_strategy, multi_timeframe_data):
        """Test that signal generation completes in reasonable time."""
        import time
        
        start = time.time()
        signals = smc_strategy.generate_signals(multi_timeframe_data)
        elapsed = time.time() - start
        
        # Should complete quickly (< 5 seconds for normal data)
        assert elapsed < 5.0
        assert isinstance(signals, list)
    
    @pytest.mark.strategy
    def test_multiple_signal_generations(self, smc_strategy, multi_timeframe_data):
        """Test multiple signal generations don't interfere."""
        signals1 = smc_strategy.generate_signals(multi_timeframe_data)
        signals2 = smc_strategy.generate_signals(multi_timeframe_data)
        
        # Both should be valid
        assert isinstance(signals1, list)
        assert isinstance(signals2, list)


# Test runner
if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
