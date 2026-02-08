"""
DataLoader module for fetching historical market data via ccxt.
Handles multi-timeframe data retrieval, caching, and preprocessing.
"""

import os
import pandas as pd
import ccxt
import time
from typing import Dict, List


class DataLoader:
    """
    Responsible for connecting to exchanges via ccxt and retrieving historical market data.
    Handles OHLCV data fetching, multi-timeframe support, and caching.
    """

    def __init__(self, exchange_name: str = "binance", exchange_type: str = "future", cache_dir: str = "data_cache"):
        """
        Initialize the data loader.

        Args:
            exchange_name: Name of the exchange (e.g., 'binance', 'bybit')
            exchange_type: Type of market ('spot', 'future', 'swap'). Default 'future'.
            cache_dir: Directory to store cached data
        """
        self.exchange_name = exchange_name
        self.exchange_type = exchange_type
        self.cache_dir = cache_dir
        self.exchange = self._initialize_exchange()

        # Create cache directory if it doesn't exist
        os.makedirs(cache_dir, exist_ok=True)

        # Rate limiting
        self.last_request_time = 0
        self.min_request_interval = 0.1  # 100ms between requests

    def _initialize_exchange(self) -> ccxt.Exchange:
        """Initialize the ccxt exchange client."""
        print(f"🔌 Initializing {self.exchange_name} ({self.exchange_type}) exchange connection...")
        try:
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
            print(f"✅ Connected to {exchange.name}")
            print(f"📊 Exchange info:")
            print(f"   - Rate limit: {exchange.rateLimit}ms")
            print(f"   - Mode (defaultType): {exchange.options.get('defaultType', 'spot')}")
            print(f"   - Has swap: {exchange.has.get('swap', False)}")
            print(f"   - Has future: {exchange.has.get('future', False)}")
            print(f"   - Has spot: {exchange.has.get('spot', False)}")

            # Test market loading
            print(f"📈 Loading markets...")
            markets = exchange.load_markets()
            print(f"✅ Loaded {len(markets)} markets")

            # Show some popular symbols
            popular_symbols = [s for s in markets.keys() if "BTC" in s or "ETH" in s][:5]
            print(f"🎯 Popular symbols: {', '.join(popular_symbols)}")

            return exchange
        except Exception as e:
            print(f"❌ Failed to initialize {self.exchange_name} exchange: {e}")
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
        # Check cache first
        cache_file = self._get_cache_file(symbol, timeframe, start_date, end_date)
        if os.path.exists(cache_file):
            print(f"Loading cached data from {cache_file}")
            return pd.read_csv(cache_file, index_col=0, parse_dates=True)

        # Convert dates to timestamps
        start_ts = int(pd.Timestamp(start_date).timestamp() * 1000)
        end_ts = int(pd.Timestamp(end_date).timestamp() * 1000)

        print(f"Fetching {symbol} {timeframe} data from {start_date} to {end_date}")

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

                print(f"Fetched {len(ohlcv)} bars, total: {len(all_data)}")

            except Exception as e:
                print(f"Error fetching data: {e}")
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
        print(f"Cached data to {cache_file}")

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

        # Add common technical indicators
        df = self._add_technical_indicators(df)

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
            print(f"Fetching {tf} data...")
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

    def _add_technical_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add common technical indicators to the DataFrame."""
        # ATR (Average True Range)
        df["atr"] = self._calculate_atr(df, period=14)

        # Simple Moving Averages
        df["sma_20"] = df["close"].rolling(window=20).mean()
        df["sma_50"] = df["close"].rolling(window=50).mean()

        # Exponential Moving Averages
        df["ema_12"] = df["close"].ewm(span=12).mean()
        df["ema_26"] = df["close"].ewm(span=26).mean()

        # MACD
        df["macd"] = df["ema_12"] - df["ema_26"]
        df["macd_signal"] = df["macd"].ewm(span=9).mean()
        df["macd_histogram"] = df["macd"] - df["macd_signal"]

        # RSI
        df["rsi"] = self._calculate_rsi(df["close"], period=14)

        # Volume indicators
        df["volume_sma"] = df["volume"].rolling(window=20).mean()
        df["volume_ratio"] = df["volume"] / df["volume_sma"]

        return df

    def _calculate_atr(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        """Calculate Average True Range."""
        high_low = df["high"] - df["low"]
        high_close = abs(df["high"] - df["close"].shift())
        low_close = abs(df["low"] - df["close"].shift())

        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        atr = true_range.rolling(window=period).mean()

        return atr

    def _calculate_rsi(self, prices: pd.Series, period: int = 14) -> pd.Series:
        """Calculate Relative Strength Index."""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))

        return rsi

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
        print("Cache cleared")

    def get_available_symbols(self) -> List[str]:
        """Get list of available trading symbols."""
        try:
            markets = self.exchange.load_markets()
            return list(markets.keys())
        except Exception as e:
            print(f"Error fetching symbols: {e}")
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
            print(f"Error fetching exchange info: {e}")
            return {}


# Example usage
if __name__ == "__main__":
    loader = DataLoader("binance")

    # Test data fetching
    df = loader.get_data("BTC/USDT", "1h", "2023-01-01", "2023-01-31")
    print(f"Fetched {len(df)} bars")
    print(df.head())
    print(df.columns.tolist())
