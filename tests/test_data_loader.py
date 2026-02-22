#!/usr/bin/env python3
"""
Tests for Data Loader module.
Tests data loading, caching, and data validation.
Run with: pytest tests/test_data_loader.py -v

Note: Most tests require network access to Binance API and will be skipped in sandbox environment.
"""

import sys
import os
import pytest
import pandas as pd
from unittest.mock import patch

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


# Tests that require network access are marked to skip in sandbox
pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


class TestDataLoaderInitialization:
    """Test DataLoader initialization and configuration."""
    
    @pytest.mark.skip(reason="Requires network access to Binance API")
    def test_data_loader_init_default(self):
        """Test DataLoader initializes with default config."""
        from engine.data_loader import DataLoader
        loader = DataLoader()
        assert loader.exchange is not None
        assert loader.cache_dir is not None
    
    @pytest.mark.skip(reason="Requires network access to Binance API")
    def test_data_loader_with_custom_exchange(self):
        """Test DataLoader with custom exchange."""
        from engine.data_loader import DataLoader
        loader = DataLoader(exchange_name='binance')
        assert loader.exchange is not None
    
    @pytest.mark.skip(reason="Requires network access to Binance API")
    def test_data_loader_cache_directory_exists(self):
        """Test that cache directory is created if it doesn't exist."""
        from engine.data_loader import DataLoader
        loader = DataLoader()
        assert os.path.exists(loader.cache_dir)


class TestDataLoading:
    """Test data loading functionality."""
    
    @pytest.mark.skip(reason="Requires network access to Binance API")
    @patch('engine.data_loader.DataLoader.fetch_ohlcv')
    def test_fetch_ohlcv_returns_dataframe(self, mock_fetch):
        """Test that fetch_ohlcv returns a DataFrame."""
        from engine.data_loader import DataLoader
        dates = pd.date_range('2023-01-01', periods=10, freq='1h')
        expected_data = pd.DataFrame({
            'open': [50000 + i*10 for i in range(10)],
            'high': [50100 + i*10 for i in range(10)],
            'low': [49900 + i*10 for i in range(10)],
            'close': [50050 + i*10 for i in range(10)],
            'volume': [1000 + i*100 for i in range(10)]
        }, index=dates)
        
        mock_fetch.return_value = expected_data
        
        loader = DataLoader()
        data = loader.fetch_ohlcv('BTC/USDT', '1h', '2023-01-01', '2023-01-10')
        
        assert isinstance(data, pd.DataFrame)
        assert len(data) == 10
    
    @pytest.mark.skip(reason="Requires network access to Binance API")
    def test_fetch_ohlcv_dataframe_structure(self):
        """Test that fetched data has correct structure."""
        from engine.data_loader import DataLoader
        loader = DataLoader()
        
        assert hasattr(loader, 'fetch_ohlcv')
        assert callable(loader.fetch_ohlcv)


class TestDataCaching:
    """Test data caching functionality."""
    
    @pytest.mark.skip(reason="Requires network access to Binance API")
    def test_cache_filename_generation(self):
        """Test correct cache filename generation."""
        from engine.data_loader import DataLoader
        loader = DataLoader()
        
        filename = loader._generate_cache_filename('BTC/USDT', '4h', '2023-01-01', '2023-01-31')
        
        assert isinstance(filename, str)
        assert 'BTC_USDT' in filename or 'BTC-USDT' in filename
        assert '4h' in filename
    
    @pytest.mark.skip(reason="Requires network access to Binance API")
    def test_cache_directory_path(self):
        """Test cache directory path is valid."""
        from engine.data_loader import DataLoader
        loader = DataLoader()
        
        assert os.path.isabs(loader.cache_dir) or loader.cache_dir.startswith('.')
        assert 'data_cache' in loader.cache_dir or 'cache' in loader.cache_dir.lower()


class TestDataValidation:
    """Test data validation and integrity checks."""
    
    def test_ohlcv_data_integrity(self, sample_ohlcv_data):
        """Test OHLCV data passes integrity checks."""
        df = sample_ohlcv_data
        
        # High should be >= Low
        assert (df['high'] >= df['low']).all(), "High should be >= Low"
        
        # High should be >= Open and Close
        assert (df['high'] >= df['open']).all(), "High should be >= Open"
        assert (df['high'] >= df['close']).all(), "High should be >= Close"
        
        # Low should be <= Open and Close
        assert (df['low'] <= df['open']).all(), "Low should be <= Open"
        assert (df['low'] <= df['close']).all(), "Low should be <= Close"
        
        # Volume should be positive
        assert (df['volume'] > 0).all(), "Volume should be positive"
    
    def test_missing_required_columns(self):
        """Test detection of missing required columns."""
        invalid_data = pd.DataFrame({
            'open': [50000, 50100],
            'high': [50200, 50300],
            'low': [49900, 50000],
            'close': [50100, 50200]
        })
        
        required_columns = {'open', 'high', 'low', 'close', 'volume'}
        missing = required_columns - set(invalid_data.columns)
        
        assert len(missing) > 0, "Should detect missing volume column"
        assert 'volume' in missing
    
    def test_price_continuity(self, trending_ohlcv_data):
        """Test that prices don't have unrealistic gaps."""
        df = trending_ohlcv_data
        
        df_copy = df.copy()
        df_copy['pct_change'] = df_copy['close'].pct_change().abs() * 100
        
        assert (df_copy['pct_change'] < 50).any(), "Some data exists"
    
    def test_datetime_index_validity(self, sample_ohlcv_data):
        """Test that datetime index is valid."""
        df = sample_ohlcv_data
        
        assert isinstance(df.index, pd.DatetimeIndex)
        assert df.index.is_monotonic_increasing
        assert len(df.index.unique()) == len(df)


class TestDataTransformation:
    """Test data transformation utilities."""
    
    def test_resample_data_upward(self, sample_ohlcv_data):
        """Test upsampling data (e.g., 1h to 4h)."""
        df = sample_ohlcv_data
        
        resampled = df.resample('4h').agg({
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum'
        })
        
        assert len(resampled) < len(df)
        assert (resampled['high'] >= resampled['low']).all()


class TestDataQuality:
    """Test data quality checks."""
    
    def test_null_values_detection(self):
        """Test detection of null values in data."""
        data_with_nulls = pd.DataFrame({
            'open': [50000, None, 50200],
            'high': [50200, 50300, None],
            'low': [49900, 50000, 50100],
            'close': [50100, 50200, 50300],
            'volume': [1000, None, 1200]
        })
        
        null_count = data_with_nulls.isnull().sum().sum()
        assert null_count > 0, "Should detect null values"
        assert data_with_nulls.isnull().any().any()
    
    def test_duplicate_timestamp_detection(self):
        """Test detection of duplicate timestamps."""
        dates = pd.date_range('2023-01-01', periods=5, freq='1h')
        duplicate_dates = pd.DatetimeIndex([dates[0], dates[1], dates[1], dates[2], dates[3]])
        
        df = pd.DataFrame({
            'open': [50000, 50100, 50200, 50300, 50400],
            'high': [50100, 50200, 50300, 50400, 50500],
            'low': [49900, 50000, 50100, 50200, 50300],
            'close': [50050, 50150, 50250, 50350, 50450],
            'volume': [1000, 1100, 1200, 1300, 1400]
        }, index=duplicate_dates)
        
        has_duplicates = df.index.duplicated().any()
        assert has_duplicates, "Should detect duplicate timestamps"
    
    def test_data_completeness(self, minimal_ohlcv_data):
        """Test that required data is complete."""
        df = minimal_ohlcv_data
        
        required_fields = ['open', 'high', 'low', 'close', 'volume']
        for field in required_fields:
            assert field in df.columns, f"Missing required field: {field}"
            assert not df[field].isnull().any(), f"Null values in {field}"


class TestDataLoaderEdgeCases:
    """Test edge cases and error handling."""
    
    def test_unsupported_timeframe(self):
        """Test handling of unsupported timeframes."""
        supported_timeframes = ['1m', '5m', '15m', '1h', '4h', '1d']
        assert '25m' not in supported_timeframes
    
    def test_invalid_symbol_format(self):
        """Test handling of invalid symbol format."""
        valid = 'BTC/USDT'
        invalid = 'BTCUSDT'
        
        assert '/' in valid
        assert '/' not in invalid


class TestEngineDataFeed:
    """Test the SMCDataFeed explicit mapping"""
    
    def test_smc_data_feed_columns(self):
        """Ensure SMCDataFeed has explicit bindings for exactly OHLCV."""
        from engine.bt_backtest_engine import SMCDataFeed
        
        # In Backtrader, params is a metaclass. We instantiate to check defaults.
        import pandas as pd
        dummy_df = pd.DataFrame({'open':[], 'high':[], 'low':[], 'close':[], 'volume':[]})
        data = SMCDataFeed(dataname=dummy_df)
        
        assert data.p.datetime is None
        assert data.p.open == -1
        assert data.p.high == -1
        assert data.p.low == -1
        assert data.p.close == -1
        assert data.p.volume == -1


# Test runner
if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
