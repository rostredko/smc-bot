"""
DataLoader module for fetching historical market data via ccxt.
Handles multi-timeframe data retrieval, caching, and preprocessing.
"""

import os
import pandas as pd
import ccxt
import time
from typing import Dict, List

from engine.logger import get_logger
logger = get_logger(__name__)


class DataLoader:
    """
    Responsible for connecting to exchanges via ccxt and retrieving historical market data.
    Handles OHLCV data fetching, multi-timeframe support, and caching.
    """

    def _get_project_root(self) -> str:
        """Get the absolute path to the project root directory."""
        # Find the root based on this file's location (engine/data_loader.py -> project_root)
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(current_dir)
        return project_root

    def __init__(self, exchange_name: str = "binance", exchange_type: str = "future", cache_dir: str = "data_cache", max_cache_age_days: float = 7.0):
        """
        Initialize the data loader.

        Args:
            exchange_name: Name of the exchange (e.g., 'binance', 'bybit')
            exchange_type: Type of market ('spot', 'future', 'swap'). Default 'future'.
            cache_dir: Directory to store cached data relative to project root
            max_cache_age_days: Maximum age of a cache file in days before it is invalidated
        """
        self.exchange_name = exchange_name
        self.exchange_type = exchange_type
        self.max_cache_age_days = max_cache_age_days
        
        project_root = self._get_project_root()
        self.cache_dir = os.path.join(project_root, cache_dir)
        self.exchange = self._initialize_exchange()

        # Create cache directory if it doesn't exist
        os.makedirs(self.cache_dir, exist_ok=True)

        # Rate limiting
        self.last_request_time = 0
        self.min_request_interval = 0.1  # 100ms between requests

    def _initialize_exchange(self) -> ccxt.Exchange:
        """Initialize the ccxt exchange client."""
        logger.info(f"🔌 Initializing {self.exchange_name} ({self.exchange_type}) exchange connection...")
        try:
            # Use binanceusdm for futures to avoid hitting Spot API (which might be blocked)
            if self.exchange_name == 'binance' and self.exchange_type == 'future':
                exchange_class = getattr(ccxt, 'binanceusdm')
            else:
                exchange_class = getattr(ccxt, self.exchange_name)
                
            exchange = exchange_class(
                {
                    "rateLimit": 1200,  # Respect rate limits
                    "enableRateLimit": True,
                    "options": {
                        "defaultType": self.exchange_type, 
                    }
                }
            )

            # Test connection and get exchange info
            logger.info(f"✅ Connected to {exchange.name}")
            logger.debug("📊 Exchange info:")
            logger.debug(f"   - Rate limit: {exchange.rateLimit}ms")
            logger.debug(f"   - Mode (defaultType): {exchange.options.get('defaultType', 'spot')}")
            logger.debug(f"   - Has swap: {exchange.has.get('swap', False)}")
            logger.debug(f"   - Has future: {exchange.has.get('future', False)}")
            logger.debug(f"   - Has spot: {exchange.has.get('spot', False)}")

            # Test market loading
            logger.info("📈 Loading markets...")
            markets = exchange.load_markets()
            logger.info(f"✅ Loaded {len(markets)} markets")

            # Show some popular symbols
            popular_symbols = [s for s in markets.keys() if "BTC" in s or "ETH" in s][:5]
            logger.debug(f"🎯 Popular symbols: {', '.join(popular_symbols)}")

            return exchange
        except Exception as e:
            logger.error(f"❌ Failed to initialize {self.exchange_name} exchange: {e}")
            raise RuntimeError(f"Failed to initialize {self.exchange_name} exchange: {e}")

    def fetch_ohlcv(self, symbol: str, timeframe: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        Fetch raw candlestick data from the exchange between given dates.

        Args:
            symbol: Trading pair (e.g., 'BTC/USDT')
            timeframe: Timeframe (e.g., '1h', '4h', '1d')
            start_date: Start date in 'YYYY-MM-DD' format
            end_date: End date in 'YYYY-MM-DD' format

        Returns:
            DataFrame with OHLCV data
        """
        if not start_date or not end_date:
            raise ValueError("start_date and end_date are required for fetch_ohlcv")
        if start_date > end_date:
            raise ValueError(f"start_date ({start_date}) must be <= end_date ({end_date})")
        cache_file = self._get_cache_file(symbol, timeframe, start_date, end_date)
        if os.path.exists(cache_file):
            file_age_days = (time.time() - os.path.getmtime(cache_file)) / (24 * 3600)
            if file_age_days > self.max_cache_age_days:
                logger.info(f"♻️ Cache file {cache_file} is {file_age_days:.1f} days old (older than {self.max_cache_age_days} limit). Removing it.")
                try:
                    os.remove(cache_file)
                except OSError as e:
                    logger.warning(f"Failed to remove old cache file {cache_file}: {e}")
            else:
                logger.info(f"Loading cached data from {cache_file} (Age: {file_age_days:.1f} days)")
                return pd.read_csv(cache_file, index_col=0, parse_dates=True)

        # Convert dates to timestamps
        start_ts = int(pd.Timestamp(start_date).timestamp() * 1000)
        end_ts = int(pd.Timestamp(end_date).timestamp() * 1000)

        logger.info(f"Fetching {symbol} {timeframe} data from {start_date} to {end_date}")

        all_data = []
        current_ts = start_ts

        while current_ts < end_ts:
            # Rate limiting
            self._rate_limit()

            try:
                # Fetch data in chunks (exchanges limit per request)
                ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, since=current_ts, limit=1000)

                if not ohlcv:
                    break

                all_data.extend(ohlcv)

                # Update current timestamp to next chunk
                current_ts = ohlcv[-1][0] + 1

                logger.debug(f"Fetched {len(ohlcv)} bars, total: {len(all_data)}")

            except Exception as e:
                logger.error(f"Error fetching data: {e}")
                time.sleep(1)  # Wait before retry
                continue

        if not all_data:
            raise RuntimeError(f"No data fetched for {symbol} {timeframe}")

        # Convert to DataFrame
        df = self._ohlcv_to_dataframe(all_data)

        # Filter to requested date range
        df = df[(df.index >= start_date) & (df.index <= end_date)]

        # Cache the data
        df.to_csv(cache_file)
        logger.info(f"Cached data to {cache_file}")

        return df

    def get_data(self, symbol: str, timeframe: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        High-level method to get formatted data.

        Args:
            symbol: Trading pair
            timeframe: Timeframe
            start_date: Start date
            end_date: End date

        Returns:
            Cleaned DataFrame with OHLCV data
        """
        df = self.fetch_ohlcv(symbol, timeframe, start_date, end_date)
        return df

    def get_data_multi(self, symbol: str, timeframes: List[str], start_date: str, end_date: str) -> Dict[str, pd.DataFrame]:
        """
        Fetch data for multiple timeframes.

        Args:
            symbol: Trading pair
            timeframes: List of timeframes
            start_date: Start date
            end_date: End date

        Returns:
            Dictionary mapping timeframe to DataFrame
        """
        data = {}

        for tf in timeframes:
            logger.info(f"Fetching {tf} data...")
            data[tf] = self.get_data(symbol, tf, start_date, end_date)

        return data

    def _ohlcv_to_dataframe(self, ohlcv: List[List]) -> pd.DataFrame:
        """Convert OHLCV list to pandas DataFrame."""
        df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])

        # Convert timestamp to datetime
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df.set_index("timestamp", inplace=True)

        # Ensure numeric types
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        # Remove any rows with NaN values
        df.dropna(inplace=True)

        return df

    def _rate_limit(self):
        """Implement rate limiting between requests."""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time

        if time_since_last < self.min_request_interval:
            time.sleep(self.min_request_interval - time_since_last)

        self.last_request_time = time.time()

    def _get_cache_file(self, symbol: str, timeframe: str, start_date: str, end_date: str) -> str:
        """Generate cache file path."""
        symbol_clean = symbol.replace("/", "_")
        filename = f"{symbol_clean}_{timeframe}_{start_date}_{end_date}.csv"
        return os.path.join(self.cache_dir, filename)

    def clear_cache(self):
        """Clear all cached data."""
        import shutil

        if os.path.exists(self.cache_dir):
            shutil.rmtree(self.cache_dir)
        os.makedirs(self.cache_dir, exist_ok=True)
        logger.info("Cache cleared")

    def get_available_symbols(self) -> List[str]:
        """Get list of available trading symbols."""
        try:
            markets = self.exchange.load_markets()
            return list(markets.keys())
        except Exception as e:
            logger.error(f"Error fetching symbols: {e}")
            return []

    def get_exchange_info(self) -> Dict:
        """Get exchange information."""
        try:
            return {
                "name": self.exchange.name,
                "countries": self.exchange.countries,
                "rateLimit": self.exchange.rateLimit,
                "has": self.exchange.has,
            }
        except Exception as e:
            logger.error(f"Error fetching exchange info: {e}")
            return {}


# Example usage
if __name__ == "__main__":
    loader = DataLoader("binance")

    # Test data fetching
    df = loader.get_data("BTC/USDT", "1h", "2023-01-01", "2023-01-31")
    logger.info(f"Fetched {len(df)} bars")
    logger.debug(df.head())
    logger.debug(df.columns.tolist())
