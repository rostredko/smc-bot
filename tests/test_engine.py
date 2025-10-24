#!/usr/bin/env python3
"""
Automated tests for SMC Trading Engine.
Run with: pytest tests/test_engine.py -v
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

from engine.backtest_engine import BacktestEngine
from engine.risk_manager import SpotRiskManager
from engine.position import Position
from engine.logger import Logger
from engine.metrics import PerformanceReporter
from strategies.simple_test_strategy import SimpleTestStrategy


class TestRiskManager:
    """Test risk management functionality."""
    
    def test_risk_manager_initialization(self, risk_manager):
        """Test risk manager initializes correctly."""
        assert risk_manager.initial_capital == 10000
        assert risk_manager.risk_per_trade == 2.0
        assert risk_manager.max_drawdown == 15.0
        assert risk_manager.max_positions == 3
        assert len(risk_manager.open_positions) == 0
    
    def test_can_open_position(self, risk_manager):
        """Test position opening limits."""
        # Should be able to open first position
        can_open, reason = risk_manager.can_open_position(50000, 49000)
        assert can_open == True
        
        # Add positions to reach limit
        pos1 = Position(1, 50000, 0.1, 49000, 51000, direction='LONG')
        pos2 = Position(2, 50000, 0.1, 49000, 51000, direction='LONG')
        pos3 = Position(3, 50000, 0.1, 49000, 51000, direction='LONG')
        risk_manager.add_position(pos1)
        risk_manager.add_position(pos2)
        risk_manager.add_position(pos3)
        
        # Should not be able to open more (max 3)
        can_open, reason = risk_manager.can_open_position(50000, 49000)
        assert can_open == False
    
    def test_position_sizing(self, risk_manager):
        """Test position size calculation."""
        entry_price = 50000
        stop_loss = 49000
        size = risk_manager.calculate_position_size(entry_price, stop_loss)
        
        # Risk amount should be 2% of 10000 = 200
        # Stop distance = 1000
        # Size should be approximately 200 / 1000 = 0.2
        assert size > 0
        assert size < 1  # Should be reasonable size
    
    def test_drawdown_limit(self):
        """Test drawdown limit enforcement."""
        rm = SpotRiskManager(10000, 2.0, 10.0, 3)
        
        # Simulate 15% drawdown (exceeds 10% limit)
        rm.cash_usdt = 8500  # Simulate loss
        rm.asset_qty = 0  # No assets
        can_open, reason = rm.can_open_position(50000, 49000)
        assert can_open == False


class TestPosition:
    """Test position/trade functionality."""
    
    def test_position_creation(self, mock_position):
        """Test position object creation."""
        assert mock_position.id == 1
        assert mock_position.direction == 'LONG'
        assert mock_position.entry_price == 50000
        assert mock_position.size == 0.1
        assert mock_position.stop_loss == 49000
        assert mock_position.take_profit == 52000
    
    def test_unrealized_pnl_long(self):
        """Test unrealized PnL calculation for LONG position."""
        pos = Position(1, 50000, 0.1, 49000, 52000, direction='LONG')
        
        # Price goes up to 51000
        pnl = pos.get_unrealized_pnl(51000)
        expected_pnl = (51000 - 50000) * 0.1
        assert pnl == expected_pnl
        
        # Price goes down to 49500
        pnl = pos.get_unrealized_pnl(49500)
        expected_pnl = (49500 - 50000) * 0.1
        assert pnl == expected_pnl
    
    def test_unrealized_pnl_short(self):
        """Test unrealized PnL calculation for SHORT position."""
        pos = Position(1, 50000, 0.1, 51000, 48000, direction='SHORT')
        
        # Price goes down to 49000 (profit)
        pnl = pos.get_unrealized_pnl(49000)
        expected_pnl = (50000 - 49000) * 0.1
        assert pnl == expected_pnl
        
        # Price goes up to 51000 (loss)
        pnl = pos.get_unrealized_pnl(51000)
        expected_pnl = (50000 - 51000) * 0.1
        assert pnl == expected_pnl


class TestLogger:
    """Test logging functionality."""
    
    def test_logger_initialization(self, logger):
        """Test logger initializes correctly."""
        assert logger.log_level == "INFO"
        assert len(logger.logs) == 0
        assert logger.trade_count == 0
    
    def test_log_message(self, logger):
        """Test basic log message."""
        logger.log("INFO", "Test message")
        
        assert len(logger.logs) == 1
        assert logger.logs[0]['level'] == "INFO"
        assert logger.logs[0]['message'] == "Test message"
    
    def test_log_levels(self):
        """Test log level filtering."""
        logger = Logger("WARNING")
        
        # INFO should not be logged
        logger.log("INFO", "Info message")
        assert len(logger.logs) == 0
        
        # WARNING should be logged
        logger.log("WARNING", "Warning message")
        assert len(logger.logs) == 1


class TestPerformanceReporter:
    """Test performance metrics calculation."""
    
    def test_empty_metrics(self, performance_reporter):
        """Test metrics with no trades."""
        metrics = performance_reporter.compute_metrics([], [])
        
        assert metrics['total_trades'] == 0
        assert metrics['win_rate'] == 0
        assert metrics['total_pnl'] == 0
    
    def test_simple_metrics(self, performance_reporter, create_sample_trades):
        """Test metrics with simple trade data."""
        trades = create_sample_trades(count=4)
        
        equity_curve = [
            {'timestamp': pd.Timestamp('2023-01-01'), 'equity': 10000},
            {'timestamp': pd.Timestamp('2023-01-02'), 'equity': 10100},
            {'timestamp': pd.Timestamp('2023-01-03'), 'equity': 10050},
            {'timestamp': pd.Timestamp('2023-01-04'), 'equity': 10200},
        ]
        
        metrics = performance_reporter.compute_metrics(trades, equity_curve)
        
        assert metrics['total_trades'] == 4
        assert metrics['win_count'] == 2
        assert metrics['loss_count'] == 2
        assert metrics['win_rate'] == 50.0
        assert metrics['total_pnl'] == 150.0


class TestBacktestEngine:
    """Test backtest engine integration."""
    
    @patch('engine.data_loader.ccxt')
    def test_engine_initialization(self, mock_ccxt, backtest_config, mock_exchange):
        """Test engine initializes with config."""
        mock_ccxt.binance.return_value = mock_exchange
        
        engine = BacktestEngine(backtest_config)
        
        assert engine.initial_capital == 10000
        assert engine.strategy is not None
        assert engine.risk_manager is not None
        assert engine.logger is not None
        
        # Verify exchange was initialized
        mock_ccxt.binance.assert_called_once()
        mock_exchange.load_markets.assert_called_once()
    
    @patch('engine.backtest_engine.DataLoader')
    def test_data_loading_with_mock(self, mock_data_loader_class, backtest_config, sample_ohlcv_data):
        """Test data loading with mocked DataLoader."""
        # Mock DataLoader instance
        mock_data_loader_instance = MagicMock()
        mock_data_loader_instance.fetch_ohlcv.return_value = sample_ohlcv_data
        mock_data_loader_class.return_value = mock_data_loader_instance
        
        engine = BacktestEngine(backtest_config)
        
        # Test data loading
        data = engine.data_loader.fetch_ohlcv('BTC/USDT', '1h', '2023-01-01', '2023-01-02')
        
        assert isinstance(data, pd.DataFrame)
        assert len(data) == 100
        assert 'open' in data.columns
        assert 'high' in data.columns
        assert 'low' in data.columns
        assert 'close' in data.columns
        assert 'volume' in data.columns


class TestDataIntegrity:
    """Test data validation and integrity."""
    
    def test_price_data_validation(self, sample_ohlcv_data):
        """Test that price data is valid."""
        df = sample_ohlcv_data
        
        # Validate high >= low
        assert (df['high'] >= df['low']).all()
        
        # Validate high >= open and high >= close
        assert (df['high'] >= df['open']).all()
        assert (df['high'] >= df['close']).all()
        
        # Validate low <= open and low <= close
        assert (df['low'] <= df['open']).all()
        assert (df['low'] <= df['close']).all()
        
        # Validate volume > 0
        assert (df['volume'] > 0).all()
    
    def test_minimal_data_edge_cases(self, minimal_ohlcv_data):
        """Test data with minimal records."""
        df = minimal_ohlcv_data
        
        assert len(df) == 5
        assert df.index[0] == pd.Timestamp('2023-01-01 00:00:00')
        assert (df['high'] >= df['low']).all()


# Test runner
if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])

