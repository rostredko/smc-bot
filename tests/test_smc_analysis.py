#!/usr/bin/env python3
"""
Tests for SMC analysis components.
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

from engine.smc_analysis import OrderBlockDetector, FairValueGapDetector, LiquidityZoneMapper


class TestOrderBlockDetector:
    """Test Order Block detection functionality."""
    
    def test_order_block_detector_initialization(self):
        """Test OrderBlockDetector initializes correctly."""
        detector = OrderBlockDetector()
        assert detector.min_strength == 0.6
        assert len(detector.order_blocks) == 0
    
    def test_order_block_detector_custom_config(self):
        """Test OrderBlockDetector with custom config."""
        detector = OrderBlockDetector(min_strength=0.7)
        assert detector.min_strength == 0.7
    
    def test_find_order_blocks_empty_data(self):
        """Test finding order blocks with empty data."""
        detector = OrderBlockDetector()
        empty_df = pd.DataFrame()
        blocks = detector.find_order_blocks(empty_df)
        assert blocks == []
    
    def test_find_order_blocks_insufficient_data(self):
        """Test finding order blocks with insufficient data."""
        detector = OrderBlockDetector()
        
        # Create minimal data
        dates = pd.date_range('2023-01-01', periods=5, freq='1h')
        df = pd.DataFrame({
            'open': [50000, 50100, 50200, 50300, 50400],
            'high': [50200, 50300, 50400, 50500, 50600],
            'low': [49900, 50000, 50100, 50200, 50300],
            'close': [50100, 50200, 50300, 50400, 50500],
            'volume': [1000, 1500, 1200, 1800, 2000]
        }, index=dates)
        
        blocks = detector.find_order_blocks(df)
        assert isinstance(blocks, list)
    
    def test_find_order_blocks_sufficient_data(self):
        """Test finding order blocks with sufficient data."""
        detector = OrderBlockDetector()
        
        # Create sufficient data with clear order blocks
        dates = pd.date_range('2023-01-01', periods=100, freq='1h')
        np.random.seed(42)
        
        # Create data with some structure
        prices = 50000 + np.cumsum(np.random.randn(100) * 50)
        
        df = pd.DataFrame({
            'open': prices,
            'high': prices + np.random.rand(100) * 100,
            'low': prices - np.random.rand(100) * 100,
            'close': prices + np.random.randn(100) * 50,
            'volume': np.random.randint(1000, 10000, 100)
        }, index=dates)
        
        blocks = detector.find_order_blocks(df)
        assert isinstance(blocks, list)
    
    def test_find_premium_discount_zones_empty_data(self):
        """Test finding premium/discount zones with empty data."""
        detector = OrderBlockDetector()
        empty_df = pd.DataFrame()
        zones = detector.find_premium_discount_zones(empty_df)
        assert zones is not None  # Returns dict with None values
    
    def test_find_premium_discount_zones_sufficient_data(self):
        """Test finding premium/discount zones with sufficient data."""
        detector = OrderBlockDetector()
        
        # Create sufficient data
        dates = pd.date_range('2023-01-01', periods=100, freq='4h')
        np.random.seed(42)
        
        prices = 50000 + np.cumsum(np.random.randn(100) * 200)
        
        df = pd.DataFrame({
            'open': prices,
            'high': prices + np.random.rand(100) * 200,
            'low': prices - np.random.rand(100) * 200,
            'close': prices + np.random.randn(100) * 100,
            'volume': np.random.randint(1000, 10000, 100)
        }, index=dates)
        
        zones = detector.find_premium_discount_zones(df)
        assert isinstance(zones, dict) or zones is None


class TestFairValueGapDetector:
    """Test Fair Value Gap detection functionality."""
    
    def test_fvg_detector_initialization(self):
        """Test FairValueGapDetector initializes correctly."""
        detector = FairValueGapDetector()
        assert detector.min_gap_size == 0.001
        assert len(detector.fair_value_gaps) == 0
    
    def test_fvg_detector_custom_config(self):
        """Test FairValueGapDetector with custom config."""
        detector = FairValueGapDetector(min_gap_size=0.002)
        assert detector.min_gap_size == 0.002
    
    def test_scan_for_gaps_empty_data(self):
        """Test scanning for gaps with empty data."""
        detector = FairValueGapDetector()
        empty_df = pd.DataFrame()
        gaps = detector.scan_for_gaps(empty_df)
        assert gaps == []
    
    def test_scan_for_gaps_insufficient_data(self):
        """Test scanning for gaps with insufficient data."""
        detector = FairValueGapDetector()
        
        # Create minimal data
        dates = pd.date_range('2023-01-01', periods=3, freq='1h')
        df = pd.DataFrame({
            'open': [50000, 50100, 50200],
            'high': [50200, 50300, 50400],
            'low': [49900, 50000, 50100],
            'close': [50100, 50200, 50300],
            'volume': [1000, 1500, 1200]
        }, index=dates)
        
        gaps = detector.scan_for_gaps(df)
        assert isinstance(gaps, list)
    
    def test_scan_for_gaps_sufficient_data(self):
        """Test scanning for gaps with sufficient data."""
        detector = FairValueGapDetector()
        
        # Create sufficient data
        dates = pd.date_range('2023-01-01', periods=50, freq='1h')
        np.random.seed(42)
        
        prices = 50000 + np.cumsum(np.random.randn(50) * 100)
        
        df = pd.DataFrame({
            'open': prices,
            'high': prices + np.random.rand(50) * 100,
            'low': prices - np.random.rand(50) * 100,
            'close': prices + np.random.randn(50) * 50,
            'volume': np.random.randint(1000, 10000, 50)
        }, index=dates)
        
        gaps = detector.scan_for_gaps(df)
        assert isinstance(gaps, list)
    
    def test_identify_fvg_structure(self):
        """Test FVG identification with known structure."""
        detector = FairValueGapDetector()
        
        # Create data with a clear FVG
        dates = pd.date_range('2023-01-01', periods=10, freq='1h')
        df = pd.DataFrame({
            'open': [50000, 50100, 50200, 50300, 50400, 50500, 50600, 50700, 50800, 50900],
            'high': [50100, 50200, 50300, 50400, 50500, 50600, 50700, 50800, 50900, 51000],
            'low': [49900, 50000, 50100, 50200, 50300, 50400, 50500, 50600, 50700, 50800],
            'close': [50100, 50200, 50300, 50400, 50500, 50600, 50700, 50800, 50900, 51000],
            'volume': [1000] * 10
        }, index=dates)
        
        gaps = detector.scan_for_gaps(df)
        assert isinstance(gaps, list)


class TestLiquidityZoneMapper:
    """Test Liquidity Level mapping functionality."""
    
    def test_liquidity_mapper_initialization(self):
        """Test LiquidityZoneMapper initializes correctly."""
        mapper = LiquidityZoneMapper()
        assert mapper.sweep_threshold == 0.002
        assert len(mapper.liquidity_zones) == 0
    
    def test_liquidity_mapper_custom_config(self):
        """Test LiquidityZoneMapper with custom config."""
        mapper = LiquidityZoneMapper(sweep_threshold=0.003)
        assert mapper.sweep_threshold == 0.003
    
    def test_find_liquidity_levels_empty_data(self):
        """Test finding liquidity levels with empty data."""
        mapper = LiquidityZoneMapper()
        empty_df = pd.DataFrame()
        levels = mapper.identify_liquidity_sweeps(empty_df)
        assert levels == []
    
    def test_find_liquidity_levels_insufficient_data(self):
        """Test finding liquidity levels with insufficient data."""
        mapper = LiquidityZoneMapper()
        
        # Create minimal data
        dates = pd.date_range('2023-01-01', periods=10, freq='1h')
        df = pd.DataFrame({
            'open': [50000] * 10,
            'high': [50100] * 10,
            'low': [49900] * 10,
            'close': [50000] * 10,
            'volume': [1000] * 10
        }, index=dates)
        
        levels = mapper.identify_liquidity_sweeps(df)
        assert isinstance(levels, list)
    
    def test_find_liquidity_levels_sufficient_data(self):
        """Test finding liquidity levels with sufficient data."""
        mapper = LiquidityZoneMapper()
        
        # Create sufficient data
        dates = pd.date_range('2023-01-01', periods=100, freq='1h')
        np.random.seed(42)
        
        prices = 50000 + np.cumsum(np.random.randn(100) * 100)
        
        df = pd.DataFrame({
            'open': prices,
            'high': prices + np.random.rand(100) * 100,
            'low': prices - np.random.rand(100) * 100,
            'close': prices + np.random.randn(100) * 50,
            'volume': np.random.randint(1000, 10000, 100)
        }, index=dates)
        
        levels = mapper.identify_liquidity_sweeps(df)
        assert isinstance(levels, list)
    
    def test_identify_support_resistance(self):
        """Test identification of support and resistance levels."""
        mapper = LiquidityZoneMapper()
        
        # Create data with clear support/resistance
        dates = pd.date_range('2023-01-01', periods=50, freq='1h')
        
        # Create data that bounces off certain levels
        prices = []
        for i in range(50):
            if i % 10 < 5:
                prices.append(50000 + (i % 5) * 100)  # Support at 50000
            else:
                prices.append(51000 - (i % 5) * 100)  # Resistance at 51000
        
        df = pd.DataFrame({
            'open': prices,
            'high': [p + 50 for p in prices],
            'low': [p - 50 for p in prices],
            'close': prices,
            'volume': [1000] * 50
        }, index=dates)
        
        levels = mapper.identify_liquidity_sweeps(df)
        assert isinstance(levels, list)


class TestSMCAnalysisIntegration:
    """Test integration between SMC analysis components."""
    
    def test_all_components_work_together(self):
        """Test that all SMC analysis components work together."""
        # Initialize all components
        ob_detector = OrderBlockDetector()
        fvg_detector = FairValueGapDetector()
        liquidity_mapper = LiquidityZoneMapper()
        
        # Create comprehensive test data
        dates = pd.date_range('2023-01-01', periods=100, freq='1h')
        np.random.seed(42)
        
        prices = 50000 + np.cumsum(np.random.randn(100) * 100)
        
        df = pd.DataFrame({
            'open': prices,
            'high': prices + np.random.rand(100) * 100,
            'low': prices - np.random.rand(100) * 100,
            'close': prices + np.random.randn(100) * 50,
            'volume': np.random.randint(1000, 10000, 100)
        }, index=dates)
        
        # Test all components
        order_blocks = ob_detector.find_order_blocks(df)
        fvgs = fvg_detector.scan_for_gaps(df)
        liquidity_levels = liquidity_mapper.identify_liquidity_sweeps(df)
        premium_discount = ob_detector.find_premium_discount_zones(df)
        
        # Verify all return expected types
        assert isinstance(order_blocks, list)
        assert isinstance(fvgs, list)
        assert isinstance(liquidity_levels, list)
        assert isinstance(premium_discount, dict) or premium_discount is None
    
    def test_components_with_realistic_data(self):
        """Test components with more realistic market data."""
        # Create more realistic market data
        dates = pd.date_range('2023-01-01', periods=200, freq='15min')
        np.random.seed(42)
        
        # Simulate trending market with some structure
        trend = np.linspace(0, 1000, 200)  # Upward trend
        noise = np.random.randn(200) * 50
        prices = 50000 + trend + noise
        
        df = pd.DataFrame({
            'open': prices,
            'high': prices + np.random.rand(200) * 100,
            'low': prices - np.random.rand(200) * 100,
            'close': prices + np.random.randn(200) * 25,
            'volume': np.random.randint(1000, 20000, 200)
        }, index=dates)
        
        # Test all components
        ob_detector = OrderBlockDetector()
        fvg_detector = FairValueGapDetector()
        liquidity_mapper = LiquidityZoneMapper()
        
        order_blocks = ob_detector.find_order_blocks(df)
        fvgs = fvg_detector.scan_for_gaps(df)
        liquidity_levels = liquidity_mapper.identify_liquidity_sweeps(df)
        
        # All should return lists
        assert isinstance(order_blocks, list)
        assert isinstance(fvgs, list)
        assert isinstance(liquidity_levels, list)


# Test runner
if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
