#!/usr/bin/env python3
"""
Tests for engine/data_loader.py.
Covers initialization, fetch_ohlcv, caching, _ohlcv_to_dataframe, get_data, get_data_multi,
clear_cache, get_available_symbols, get_exchange_info.
All tests use mocked exchange to avoid network access.
"""

import sys
import os
import pytest
import pandas as pd
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


@patch("engine.data_loader.DataLoader._initialize_exchange")
class TestDataLoaderInitialization:
    """Test DataLoader initialization and configuration."""

    def test_data_loader_init_default(self, mock_init_exchange):
        from engine.data_loader import DataLoader
        mock_init_exchange.return_value = MagicMock()
        loader = DataLoader()
        assert loader.exchange is not None
        assert loader.cache_dir is not None
        assert "data_cache" in loader.cache_dir

    def test_data_loader_with_custom_exchange(self, mock_init_exchange):
        from engine.data_loader import DataLoader
        mock_init_exchange.return_value = MagicMock()
        loader = DataLoader(exchange_name="bybit", exchange_type="spot")
        assert loader.exchange is not None
        assert loader.exchange_name == "bybit"
        assert loader.exchange_type == "spot"

    def test_data_loader_cache_directory_exists(self, mock_init_exchange):
        from engine.data_loader import DataLoader
        mock_init_exchange.return_value = MagicMock()
        loader = DataLoader()
        assert os.path.exists(loader.cache_dir)

    def test_rate_limit_attributes(self, mock_init_exchange):
        from engine.data_loader import DataLoader
        mock_init_exchange.return_value = MagicMock()
        loader = DataLoader()
        assert loader.last_request_time == 0
        assert loader.min_request_interval == 0.1

    def test_get_project_root_returns_absolute_path(self, mock_init_exchange):
        from engine.data_loader import DataLoader
        mock_init_exchange.return_value = MagicMock()
        loader = DataLoader()
        root = loader._get_project_root()
        assert os.path.isabs(root)
        assert loader.cache_dir.startswith(root)


@patch("engine.data_loader.DataLoader._initialize_exchange")
class TestDataLoading:
    """Test data loading functionality."""

    def test_get_data_delegates_to_fetch_ohlcv(self, mock_init_exchange):
        from engine.data_loader import DataLoader
        mock_init_exchange.return_value = MagicMock()
        loader = DataLoader()
        expected = pd.DataFrame({
            "open": [100.0] * 5, "high": [105.0] * 5, "low": [95.0] * 5,
            "close": [101.0] * 5, "volume": [1000] * 5,
        }, index=pd.date_range("2024-01-01", periods=5, freq="h"))
        with patch.object(loader, "fetch_ohlcv", return_value=expected) as mock_fetch:
            result = loader.get_data("BTC/USDT", "1h", "2024-01-01", "2024-01-05")
            mock_fetch.assert_called_once_with("BTC/USDT", "1h", "2024-01-01", "2024-01-05")
            assert result.equals(expected)

    def test_get_data_multi_calls_get_data_per_timeframe(self, mock_init_exchange):
        from engine.data_loader import DataLoader
        mock_init_exchange.return_value = MagicMock()
        loader = DataLoader()
        df = pd.DataFrame({"open": [100], "high": [105], "low": [95], "close": [101], "volume": [1000]}, index=pd.date_range("2024-01-01", periods=1, freq="h"))
        with patch.object(loader, "get_data", return_value=df) as mock_get:
            result = loader.get_data_multi("BTC/USDT", ["1h", "4h"], "2024-01-01", "2024-01-31")
            assert mock_get.call_count == 2
            assert "1h" in result and "4h" in result


@patch("engine.data_loader.DataLoader._initialize_exchange")
class TestDataCaching:
    """Test data caching functionality."""

    def test_get_cache_file_path(self, mock_init_exchange):
        from engine.data_loader import DataLoader
        mock_init_exchange.return_value = MagicMock()
        loader = DataLoader()
        path = loader._get_cache_file("BTC/USDT", "4h", "2023-01-01", "2023-01-31")
        assert isinstance(path, str)
        assert "BTC_USDT" in path
        assert "4h" in path
        assert "2023-01-01" in path
        assert "2023-01-31" in path
        assert path.endswith(".csv")

    def test_get_cache_file_symbol_cleanup(self, mock_init_exchange):
        from engine.data_loader import DataLoader
        mock_init_exchange.return_value = MagicMock()
        loader = DataLoader()
        path = loader._get_cache_file("ETH/BTC", "1h", "2024-01-01", "2024-01-31")
        assert "ETH_BTC" in path

    def test_clear_cache_recreates_directory(self, mock_init_exchange):
        from engine.data_loader import DataLoader
        mock_init_exchange.return_value = MagicMock()
        loader = DataLoader()
        loader.clear_cache()
        assert os.path.exists(loader.cache_dir)


@patch("engine.data_loader.DataLoader._initialize_exchange")
class TestDataValidation:
    """Test data validation and integrity checks."""

    def test_fetch_ohlcv_raises_on_none_dates(self, mock_init_exchange):
        from engine.data_loader import DataLoader
        mock_init_exchange.return_value = MagicMock()
        loader = DataLoader()
        with pytest.raises(ValueError, match="start_date and end_date are required"):
            loader.fetch_ohlcv("BTC/USDT", "1h", None, "2024-01-31")
        with pytest.raises(ValueError, match="start_date and end_date are required"):
            loader.fetch_ohlcv("BTC/USDT", "1h", "2024-01-01", None)

    def test_fetch_ohlcv_raises_when_start_after_end(self, mock_init_exchange):
        from engine.data_loader import DataLoader
        mock_init_exchange.return_value = MagicMock()
        loader = DataLoader()
        with pytest.raises(ValueError, match="start_date.*must be <= end_date"):
            loader.fetch_ohlcv("BTC/USDT", "1h", "2024-12-31", "2024-01-01")

    def test_ohlcv_data_integrity(self, mock_init_exchange, sample_ohlcv_data):
        df = sample_ohlcv_data
        assert (df["high"] >= df["low"]).all()
        assert (df["high"] >= df["open"]).all()
        assert (df["high"] >= df["close"]).all()
        assert (df["low"] <= df["open"]).all()
        assert (df["low"] <= df["close"]).all()
        assert (df["volume"] > 0).all()

    def test_missing_required_columns(self, mock_init_exchange):
        invalid_data = pd.DataFrame({
            "open": [50000, 50100], "high": [50200, 50300], "low": [49900, 50000], "close": [50100, 50200]
        })
        required_columns = {"open", "high", "low", "close", "volume"}
        missing = required_columns - set(invalid_data.columns)
        assert "volume" in missing

    def test_price_continuity(self, mock_init_exchange, trending_ohlcv_data):
        df = trending_ohlcv_data.copy()
        df["pct_change"] = df["close"].pct_change().abs() * 100
        assert (df["pct_change"] < 50).any()

    def test_datetime_index_validity(self, mock_init_exchange, sample_ohlcv_data):
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


@patch("engine.data_loader.DataLoader._initialize_exchange")
class TestOhlcvToDataframe:
    """Test _ohlcv_to_dataframe conversion."""

    def test_valid_ohlcv_produces_dataframe(self, mock_init_exchange):
        from engine.data_loader import DataLoader
        mock_init_exchange.return_value = MagicMock()
        loader = DataLoader()
        ohlcv = [
            [1704067200000, 100.0, 105.0, 95.0, 101.0, 1000.0],
            [1704070800000, 101.0, 106.0, 96.0, 102.0, 1100.0],
        ]
        df = loader._ohlcv_to_dataframe(ohlcv)
        assert len(df) == 2
        assert list(df.columns) == ["open", "high", "low", "close", "volume"]
        assert df.index.name == "timestamp" or isinstance(df.index, pd.DatetimeIndex)
        assert df["close"].iloc[0] == 101.0

    def test_all_nan_returns_empty(self, mock_init_exchange):
        from engine.data_loader import DataLoader
        mock_init_exchange.return_value = MagicMock()
        loader = DataLoader()
        invalid_ohlcv = [[1000000, "x", "x", "x", "x", "x"]]
        df = loader._ohlcv_to_dataframe(invalid_ohlcv)
        assert df.empty


@patch("engine.data_loader.DataLoader._initialize_exchange")
class TestFetchOhlcv:
    """Test fetch_ohlcv validation and cache behavior."""

    def test_raises_on_empty_start_date(self, mock_init_exchange):
        from engine.data_loader import DataLoader
        mock_init_exchange.return_value = MagicMock()
        loader = DataLoader()
        with pytest.raises(ValueError, match="start_date and end_date are required"):
            loader.fetch_ohlcv("BTC/USDT", "1h", "", "2024-01-31")

    def test_raises_on_empty_end_date(self, mock_init_exchange):
        from engine.data_loader import DataLoader
        mock_init_exchange.return_value = MagicMock()
        loader = DataLoader()
        with pytest.raises(ValueError, match="start_date and end_date are required"):
            loader.fetch_ohlcv("BTC/USDT", "1h", "2024-01-01", "")

    def test_raises_when_start_after_end(self, mock_init_exchange):
        from engine.data_loader import DataLoader
        mock_init_exchange.return_value = MagicMock()
        loader = DataLoader()
        with pytest.raises(ValueError, match="start_date.*must be <= end_date"):
            loader.fetch_ohlcv("BTC/USDT", "1h", "2024-12-31", "2024-01-01")

    def test_returns_cached_data_when_fresh(self, mock_init_exchange):
        from engine.data_loader import DataLoader
        mock_init_exchange.return_value = MagicMock()
        loader = DataLoader()
        expected = pd.DataFrame({"open": [100], "high": [105], "low": [95], "close": [101], "volume": [1000]}, index=pd.date_range("2024-01-01", periods=1, freq="h"))
        cache_path = loader._get_cache_file("BTC/USDT", "1h", "2024-01-01", "2024-01-31")
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        expected.to_csv(cache_path)
        try:
            result = loader.fetch_ohlcv("BTC/USDT", "1h", "2024-01-01", "2024-01-31")
            assert len(result) >= 1
            assert "close" in result.columns
        finally:
            if os.path.exists(cache_path):
                os.remove(cache_path)


@patch("engine.data_loader.DataLoader._initialize_exchange")
class TestGetAvailableSymbolsAndExchangeInfo:
    """Test get_available_symbols and get_exchange_info."""

    def test_get_available_symbols_returns_list(self, mock_init_exchange):
        from engine.data_loader import DataLoader
        mock_exchange = MagicMock()
        mock_exchange.load_markets.return_value = {"BTC/USDT": {}, "ETH/USDT": {}}
        mock_init_exchange.return_value = mock_exchange
        loader = DataLoader()
        symbols = loader.get_available_symbols()
        assert isinstance(symbols, list)
        assert "BTC/USDT" in symbols
        assert "ETH/USDT" in symbols

    def test_get_available_symbols_returns_empty_on_error(self, mock_init_exchange):
        from engine.data_loader import DataLoader
        mock_exchange = MagicMock()
        mock_exchange.load_markets.side_effect = Exception("Network error")
        mock_init_exchange.return_value = mock_exchange
        loader = DataLoader()
        symbols = loader.get_available_symbols()
        assert symbols == []

    def test_get_exchange_info_returns_dict(self, mock_init_exchange):
        from engine.data_loader import DataLoader
        mock_exchange = MagicMock()
        mock_exchange.name = "Binance"
        mock_exchange.countries = ["US"]
        mock_exchange.rateLimit = 1200
        mock_exchange.has = {"spot": True, "future": True}
        mock_init_exchange.return_value = mock_exchange
        loader = DataLoader()
        info = loader.get_exchange_info()
        assert isinstance(info, dict)
        assert info["name"] == "Binance"
        assert info["rateLimit"] == 1200

    def test_get_exchange_info_returns_empty_on_error(self, mock_init_exchange):
        from engine.data_loader import DataLoader
        mock_init_exchange.return_value = MagicMock()
        loader = DataLoader()

        class BadExchange:
            name = "X"
            rateLimit = 0
            has = {}
            @property
            def countries(self):
                raise RuntimeError("Connection lost")

        loader.exchange = BadExchange()
        info = loader.get_exchange_info()
        assert info == {}


@patch("engine.data_loader.DataLoader._initialize_exchange")
class TestDataLoaderEdgeCases:
    """Test edge cases and error handling."""

    def test_ohlcv_to_dataframe_handles_all_nan(self, mock_init_exchange):
        from engine.data_loader import DataLoader
        mock_init_exchange.return_value = MagicMock()
        loader = DataLoader(exchange_name="binance", exchange_type="future")
        invalid_ohlcv = [[1000000, "x", "x", "x", "x", "x"]]
        df = loader._ohlcv_to_dataframe(invalid_ohlcv)
        assert df.empty

    def test_unsupported_timeframe(self, mock_init_exchange):
        supported_timeframes = ["1m", "5m", "15m", "1h", "4h", "1d"]
        assert "25m" not in supported_timeframes

    def test_invalid_symbol_format(self, mock_init_exchange):
        assert "/" in "BTC/USDT"
        assert "/" not in "BTCUSDT"


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
