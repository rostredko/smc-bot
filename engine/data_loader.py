"""
DataLoader module for fetching historical market data via ccxt.
Handles multi-timeframe data retrieval, caching, and preprocessing.
"""

import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Tuple, Callable, Optional

import ccxt
import pandas as pd

from engine.logger import coerce_log_level, get_logger

try:
    from db.connection import get_database, is_database_available
except Exception:  # pragma: no cover - optional DB dependency in some runtimes
    get_database = None  # type: ignore[assignment]
    is_database_available = None  # type: ignore[assignment]

logger = get_logger(__name__)


class DataLoader:
    """
    Responsible for connecting to exchanges via ccxt and retrieving historical market data.
    Supports partial DB cache (Mongo) with selective range backfill and CSV fallback cache.
    """

    def _get_project_root(self) -> str:
        """Get the absolute path to the project root directory."""
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(current_dir)
        return project_root

    def __init__(
        self,
        exchange_name: str = "binance",
        exchange_type: str = "future",
        cache_dir: str = "data_cache",
        max_cache_age_days: float = 7.0,
        enable_db_cache: bool = True,
        log_level: int = logging.INFO,
    ):
        """
        Initialize the data loader.

        Args:
            exchange_name: Name of the exchange (e.g., "binance", "bybit")
            exchange_type: Type of market ("spot", "future", "swap")
            cache_dir: Directory to store CSV cached data relative to project root
            max_cache_age_days: Freshness window for recently cached bars
            enable_db_cache: If True, use MongoDB OHLCV cache when available
            log_level: Operational log level for routine loader messages
        """
        self.exchange_name = exchange_name
        self.exchange_type = exchange_type
        self.max_cache_age_days = float(max_cache_age_days)
        self.enable_db_cache = bool(enable_db_cache)
        self.log_level = coerce_log_level(log_level, default=logging.INFO)

        project_root = self._get_project_root()
        self.cache_dir = os.path.join(project_root, cache_dir)
        self.exchange = self._initialize_exchange()

        os.makedirs(self.cache_dir, exist_ok=True)

        self.last_request_time = 0.0
        self.min_request_interval = 0.1  # 100ms between requests
        self.cancel_check: Optional[Callable[[], bool]] = None

        self._cache_collection = self._init_db_cache_collection() if self.enable_db_cache else None

    def _is_cancel_requested(self) -> bool:
        check = self.cancel_check
        if check is None:
            return False
        try:
            return bool(check())
        except Exception:
            return False

    def _log_operational(self, message: str) -> None:
        logger.log(self.log_level, message)

    def _initialize_exchange(self) -> ccxt.Exchange:
        """Initialize the ccxt exchange client."""
        self._log_operational(f"Initializing {self.exchange_name} ({self.exchange_type}) exchange connection...")
        try:
            if self.exchange_name == "binance" and self.exchange_type == "future":
                exchange_class = getattr(ccxt, "binanceusdm")
            else:
                exchange_class = getattr(ccxt, self.exchange_name)

            exchange = exchange_class(
                {
                    "rateLimit": 1200,
                    "enableRateLimit": True,
                    "options": {
                        "defaultType": self.exchange_type,
                    },
                }
            )

            self._log_operational(f"Connected to {exchange.name}")
            self._log_operational("Loading markets...")
            markets = exchange.load_markets()
            self._log_operational(f"Loaded {len(markets)} markets")

            return exchange
        except Exception as e:
            logger.error(f"Failed to initialize {self.exchange_name} exchange: {e}")
            raise RuntimeError(f"Failed to initialize {self.exchange_name} exchange: {e}")

    def _init_db_cache_collection(self):
        """Initialize MongoDB OHLCV cache collection if DB is available."""
        if get_database is None or is_database_available is None:
            return None

        try:
            if not is_database_available():
                return None
            db = get_database()
            collection = db["ohlcv_cache"]
            collection.create_index(
                [
                    ("exchange", 1),
                    ("exchange_type", 1),
                    ("symbol", 1),
                    ("timeframe", 1),
                    ("timestamp", 1),
                ],
                unique=True,
                name="uq_ohlcv_cache_key",
            )
            collection.create_index(
                [
                    ("exchange", 1),
                    ("exchange_type", 1),
                    ("symbol", 1),
                    ("timeframe", 1),
                    ("timestamp", 1),
                ],
                name="ix_ohlcv_cache_lookup",
            )
            collection.create_index("cached_at", name="ix_ohlcv_cached_at")
            return collection
        except Exception as e:
            logger.warning(f"DB cache disabled: failed to initialize ohlcv_cache collection: {e}")
            return None

    def _timeframe_to_ms(self, timeframe: str) -> int:
        """Convert timeframe string to milliseconds."""
        if hasattr(self.exchange, "parse_timeframe"):
            seconds = int(self.exchange.parse_timeframe(timeframe))
            return max(seconds * 1000, 1)

        unit = timeframe[-1]
        value = int(timeframe[:-1])
        multipliers = {
            "m": 60_000,
            "h": 3_600_000,
            "d": 86_400_000,
            "w": 604_800_000,
        }
        if unit not in multipliers:
            raise ValueError(f"Unsupported timeframe: {timeframe}")
        return value * multipliers[unit]

    @staticmethod
    def _to_utc_timestamp(value: str) -> pd.Timestamp:
        """Parse date/time and normalize to UTC."""
        ts = pd.Timestamp(value)
        if ts.tzinfo is None:
            return ts.tz_localize("UTC")
        return ts.tz_convert("UTC")

    @classmethod
    def _to_utc_naive(cls, value: str) -> pd.Timestamp:
        """Return UTC-normalized timestamp without timezone for dataframe index comparisons."""
        return cls._to_utc_timestamp(value).tz_localize(None)

    def _date_range_to_timestamps(self, start_date: str, end_date: str) -> Tuple[int, int, pd.Timestamp]:
        """Convert YYYY-MM-DD date range to millisecond timestamps (inclusive end)."""
        start_dt_utc = self._to_utc_timestamp(start_date)
        end_dt_utc_inclusive = self._to_utc_timestamp(end_date) + pd.Timedelta(days=1) - pd.Timedelta(milliseconds=1)
        start_ts = int(start_dt_utc.timestamp() * 1000)
        end_ts = int(end_dt_utc_inclusive.timestamp() * 1000)
        return start_ts, end_ts, end_dt_utc_inclusive.tz_localize(None)

    def _cache_identity(self, symbol: str, timeframe: str) -> Dict[str, str]:
        return {
            "exchange": self.exchange_name,
            "exchange_type": self.exchange_type,
            "symbol": symbol,
            "timeframe": timeframe,
        }

    def _load_cached_docs(self, symbol: str, timeframe: str, start_ts: int, end_ts: int) -> List[Dict[str, Any]]:
        """Load cached bars for a range from DB with freshness policy for recent bars."""
        if self._cache_collection is None:
            return []

        identity = self._cache_identity(symbol, timeframe)
        recent_cutoff_dt = datetime.now(timezone.utc) - timedelta(days=self.max_cache_age_days)
        recent_cutoff_ts = int(recent_cutoff_dt.timestamp() * 1000)

        query: Dict[str, Any] = {
            **identity,
            "timestamp": {"$gte": start_ts, "$lte": end_ts},
            "$or": [
                {"timestamp": {"$lt": recent_cutoff_ts}},
                {
                    "$and": [
                        {"timestamp": {"$gte": recent_cutoff_ts}},
                        {"cached_at": {"$gte": recent_cutoff_dt}},
                    ]
                },
            ],
        }

        docs = list(
            self._cache_collection.find(
                query,
                {
                    "_id": 0,
                    "timestamp": 1,
                    "open": 1,
                    "high": 1,
                    "low": 1,
                    "close": 1,
                    "volume": 1,
                },
            ).sort("timestamp", 1)
        )
        return docs

    def _find_missing_ranges(
        self,
        cached_timestamps: List[int],
        start_ts: int,
        end_ts: int,
        timeframe_ms: int,
    ) -> List[Tuple[int, int]]:
        """Find gaps in cached timeline and return missing [start, end] ranges."""
        if not cached_timestamps:
            return [(start_ts, end_ts)]

        missing: List[Tuple[int, int]] = []
        current = start_ts

        for ts in sorted(set(int(v) for v in cached_timestamps if start_ts <= int(v) <= end_ts)):
            if ts < current:
                continue
            if ts > current:
                gap_end = min(end_ts, ts - timeframe_ms)
                if gap_end >= current:
                    missing.append((current, gap_end))
            next_expected = ts + timeframe_ms
            if next_expected > current:
                current = next_expected

        if current <= end_ts:
            missing.append((current, end_ts))

        return missing

    def _fetch_ohlcv_range(
        self,
        symbol: str,
        timeframe: str,
        range_start_ts: int,
        range_end_ts: int,
    ) -> List[List[Any]]:
        """Fetch OHLCV bars from exchange only for a concrete timestamp range."""
        timeframe_ms = self._timeframe_to_ms(timeframe)
        all_data: List[List[Any]] = []
        current_ts = range_start_ts

        max_retries_per_chunk = 5
        retries = 0

        while current_ts <= range_end_ts:
            if self._is_cancel_requested():
                self._log_operational(f"Data fetch cancelled for {symbol} {timeframe}")
                break
            self._rate_limit()
            try:
                ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, since=current_ts, limit=1000)
                if not ohlcv:
                    break

                for bar in ohlcv:
                    ts = int(bar[0])
                    if ts < range_start_ts:
                        continue
                    if ts > range_end_ts:
                        break
                    all_data.append(bar)

                last_ts = int(ohlcv[-1][0])
                if last_ts > range_end_ts:
                    break

                next_ts = last_ts + timeframe_ms
                if next_ts <= current_ts:
                    next_ts = current_ts + timeframe_ms
                current_ts = next_ts
                retries = 0
            except Exception as e:
                if self._is_cancel_requested():
                    self._log_operational(f"Data fetch cancelled during retry for {symbol} {timeframe}")
                    break
                logger.error(f"Error fetching data chunk for {symbol} {timeframe}: {e}")
                retries += 1
                if retries >= max_retries_per_chunk:
                    raise RuntimeError(f"Failed to fetch data after {max_retries_per_chunk} retries: {e}")
                time.sleep(1)
                current_ts += timeframe_ms

        return all_data

    def _upsert_bars_to_db(self, symbol: str, timeframe: str, bars: List[List[Any]]) -> None:
        """Store fetched OHLCV bars in DB cache via bulk_write (faster than per-bar update_one)."""
        if self._cache_collection is None or not bars:
            return

        from pymongo import UpdateOne

        identity = self._cache_identity(symbol, timeframe)
        cached_at = datetime.now(timezone.utc)

        def _do_bulk(chunk: List[List[Any]]) -> bool:
            operations = [
                UpdateOne(
                    {**identity, "timestamp": int(bar[0])},
                    {
                        "$set": {
                            "open": float(bar[1]),
                            "high": float(bar[2]),
                            "low": float(bar[3]),
                            "close": float(bar[4]),
                            "volume": float(bar[5]),
                            "cached_at": cached_at,
                        }
                    },
                    upsert=True,
                )
                for bar in chunk
            ]
            try:
                self._cache_collection.bulk_write(operations, ordered=False)
                return True
            except TypeError as e:
                if "sort" in str(e) or "unexpected keyword" in str(e).lower():
                    return False
                raise

        chunk_size = 1000
        for i in range(0, len(bars), chunk_size):
            chunk = bars[i : i + chunk_size]
            if not _do_bulk(chunk):
                for bar in chunk:
                    ts = int(bar[0])
                    self._cache_collection.update_one(
                        {**identity, "timestamp": ts},
                        {
                            "$set": {
                                "open": float(bar[1]),
                                "high": float(bar[2]),
                                "low": float(bar[3]),
                                "close": float(bar[4]),
                                "volume": float(bar[5]),
                                "cached_at": cached_at,
                            }
                        },
                        upsert=True,
                    )

    def _docs_to_dataframe(self, docs: List[Dict[str, Any]]) -> pd.DataFrame:
        """Convert cached DB docs into an OHLCV dataframe."""
        if not docs:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

        df = pd.DataFrame(docs)
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True).dt.tz_convert(None)
        df.set_index("timestamp", inplace=True)
        ohlc_cols = ["open", "high", "low", "close", "volume"]
        df[ohlc_cols] = df[ohlc_cols].apply(pd.to_numeric, errors="coerce")
        df.dropna(inplace=True)
        df = df[~df.index.duplicated(keep="last")].sort_index()
        return df

    def _fetch_ohlcv_with_db_cache(self, symbol: str, timeframe: str, start_date: str, end_date: str) -> pd.DataFrame:
        """Fetch OHLCV using DB-backed partial cache and fetch only missing ranges."""
        start_ts, end_ts, _ = self._date_range_to_timestamps(start_date, end_date)
        timeframe_ms = self._timeframe_to_ms(timeframe)

        cached_docs = self._load_cached_docs(symbol, timeframe, start_ts, end_ts)
        cached_timestamps = [int(doc["timestamp"]) for doc in cached_docs if "timestamp" in doc]
        missing_ranges = self._find_missing_ranges(cached_timestamps, start_ts, end_ts, timeframe_ms)

        if cached_docs:
            self._log_operational(
                f"{symbol} {timeframe}: {len(cached_docs)} bars from DB cache, {len(missing_ranges)} gap(s) to fetch"
            )
        elif missing_ranges:
            self._log_operational(
                f"{symbol} {timeframe}: cache empty, fetching {len(missing_ranges)} range(s)"
            )

        fetched_total = 0
        for gap_start, gap_end in missing_ranges:
            if self._is_cancel_requested():
                self._log_operational(f"Stopping gap fetch due to cancellation: {symbol} {timeframe}")
                break
            self._log_operational(
                f"Fetching {symbol} {timeframe} gap from "
                f"{pd.to_datetime(gap_start, unit='ms').strftime('%Y-%m-%d %H:%M:%S')} to "
                f"{pd.to_datetime(gap_end, unit='ms').strftime('%Y-%m-%d %H:%M:%S')}"
            )
            bars = self._fetch_ohlcv_range(symbol, timeframe, gap_start, gap_end)
            fetched_total += len(bars)
            self._upsert_bars_to_db(symbol, timeframe, bars)

        if missing_ranges:
            cached_docs = self._load_cached_docs(symbol, timeframe, start_ts, end_ts)

        if not cached_docs:
            if self._is_cancel_requested():
                raise RuntimeError(f"Data fetch cancelled for {symbol} {timeframe}")
            raise RuntimeError(f"No data fetched for {symbol} {timeframe}")

        df = self._docs_to_dataframe(cached_docs)
        start_dt = self._to_utc_naive(start_date)
        end_dt = self._to_utc_naive(end_date) + pd.Timedelta(days=1) - pd.Timedelta(milliseconds=1)
        df = df[(df.index >= start_dt) & (df.index <= end_dt)]

        if df.empty:
            raise RuntimeError(f"No data fetched for {symbol} {timeframe}")

        if fetched_total > 0:
            self._log_operational(f"Loaded {len(df)} bars ({fetched_total} fetched, {len(df) - fetched_total} from DB cache)")
        else:
            self._log_operational(f"Loaded {len(df)} bars from DB cache")

        return df

    def _fetch_ohlcv_with_file_cache(self, symbol: str, timeframe: str, start_date: str, end_date: str) -> pd.DataFrame:
        """Legacy exact-range CSV cache fallback when DB cache is unavailable."""
        self._log_operational(f"Using file cache (MongoDB OHLCV cache unavailable)")
        cache_file = self._get_cache_file(symbol, timeframe, start_date, end_date)
        if os.path.exists(cache_file):
            file_age_days = (time.time() - os.path.getmtime(cache_file)) / (24 * 3600)
            end_dt = self._to_utc_naive(end_date)
            recent_cutoff_naive = (datetime.now(timezone.utc) - timedelta(days=self.max_cache_age_days)).replace(tzinfo=None)
            is_historical_only = end_dt < recent_cutoff_naive
            if is_historical_only:
                self._log_operational(f"Loading cached data from {cache_file} (historical range, age: {file_age_days:.1f} days)")
                return pd.read_csv(cache_file, index_col=0, parse_dates=True)
            if file_age_days > self.max_cache_age_days:
                self._log_operational(
                    f"Cache file {cache_file} is {file_age_days:.1f} days old "
                    f"(older than {self.max_cache_age_days} limit). Removing it."
                )
                try:
                    os.remove(cache_file)
                except OSError as e:
                    logger.warning(f"Failed to remove old cache file {cache_file}: {e}")
            else:
                self._log_operational(f"Loading cached data from {cache_file} (Age: {file_age_days:.1f} days)")
                return pd.read_csv(cache_file, index_col=0, parse_dates=True)

        start_ts, end_ts, end_dt_inclusive = self._date_range_to_timestamps(start_date, end_date)
        self._log_operational(f"Fetching {symbol} {timeframe} data from {start_date} to {end_date}")

        all_data = self._fetch_ohlcv_range(symbol, timeframe, start_ts, end_ts)
        if not all_data:
            if self._is_cancel_requested():
                raise RuntimeError(f"Data fetch cancelled for {symbol} {timeframe}")
            raise RuntimeError(f"No data fetched for {symbol} {timeframe}")

        df = self._ohlcv_to_dataframe(all_data)
        start_dt = self._to_utc_naive(start_date)
        df = df[(df.index >= start_dt) & (df.index <= end_dt_inclusive)]

        df.to_csv(cache_file)
        self._log_operational(f"Loaded {len(df)} bars, cached to {cache_file}")
        return df

    def fetch_ohlcv(self, symbol: str, timeframe: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        Fetch raw candlestick data from the exchange between given dates.

        Args:
            symbol: Trading pair (e.g., "BTC/USDT")
            timeframe: Timeframe (e.g., "1h", "4h", "1d")
            start_date: Start date in "YYYY-MM-DD" format
            end_date: End date in "YYYY-MM-DD" format

        Returns:
            DataFrame with OHLCV data
        """
        if not start_date or not end_date:
            raise ValueError("start_date and end_date are required for fetch_ohlcv")
        if start_date > end_date:
            raise ValueError(f"start_date ({start_date}) must be <= end_date ({end_date})")

        if self._cache_collection is not None:
            return self._fetch_ohlcv_with_db_cache(symbol, timeframe, start_date, end_date)

        return self._fetch_ohlcv_with_file_cache(symbol, timeframe, start_date, end_date)

    def fetch_recent_bars(self, symbol: str, timeframe: str, limit: int = 150) -> List[Dict[str, float]]:
        """
        Fetch most recent closed bars using REST API for live-engine warm-up.
        Returns a list of dictionaries with standard OHLCV keys.
        """
        if self._is_cancel_requested():
            return []
        self._rate_limit()
        self._log_operational(f"Fetching {limit} recent historical bars for {symbol} {timeframe}...")
        try:
            ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit + 1)

            if not ohlcv or len(ohlcv) < 2:
                logger.warning(f"Could not fetch enough recent bars for {symbol} {timeframe}")
                return []

            closed_bars = ohlcv[:-1]
            result: List[Dict[str, float]] = []
            for bar in closed_bars:
                result.append(
                    {
                        "timestamp": int(bar[0]),
                        "open": float(bar[1]),
                        "high": float(bar[2]),
                        "low": float(bar[3]),
                        "close": float(bar[4]),
                        "volume": float(bar[5]),
                    }
                )

            self._log_operational(f"Successfully loaded {len(result)} historical closed bars for {symbol} {timeframe}.")
            return result

        except Exception as e:
            logger.error(f"Error fetching recent bars for {symbol} {timeframe}: {e}")
            return []

    def get_data(self, symbol: str, timeframe: str, start_date: str, end_date: str) -> pd.DataFrame:
        """High-level method to get formatted data."""
        return self.fetch_ohlcv(symbol, timeframe, start_date, end_date)

    def get_data_multi(
        self,
        symbol: str,
        timeframes: List[str],
        start_date: str,
        end_date: str,
    ) -> Dict[str, pd.DataFrame]:
        """Fetch data for multiple timeframes."""
        data: Dict[str, pd.DataFrame] = {}
        for tf in timeframes:
            self._log_operational(f"Fetching {tf} data...")
            data[tf] = self.get_data(symbol, tf, start_date, end_date)
        return data

    def _ohlcv_to_dataframe(self, ohlcv: List[List[Any]]) -> pd.DataFrame:
        """Convert OHLCV list to pandas DataFrame."""
        df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True).dt.tz_convert(None)
        df.set_index("timestamp", inplace=True)

        ohlc_cols = ["open", "high", "low", "close", "volume"]
        df[ohlc_cols] = df[ohlc_cols].apply(pd.to_numeric, errors="coerce")
        df.dropna(inplace=True)

        if df.empty:
            logger.warning("OHLCV data contained only NaN values after cleaning")

        return df

    def _rate_limit(self) -> None:
        """Implement rate limiting between requests."""
        if self._is_cancel_requested():
            return
        current_time = time.time()
        time_since_last = current_time - self.last_request_time

        if time_since_last < self.min_request_interval:
            time.sleep(self.min_request_interval - time_since_last)

        self.last_request_time = time.time()

    def _get_cache_file(self, symbol: str, timeframe: str, start_date: str, end_date: str) -> str:
        """Generate CSV cache file path (legacy fallback cache)."""
        symbol_clean = symbol.replace("/", "_")
        filename = f"{symbol_clean}_{timeframe}_{start_date}_{end_date}.csv"
        return os.path.join(self.cache_dir, filename)

    def clear_cache(self) -> None:
        """Clear all cached data (CSV and DB cache for this exchange/type)."""
        import shutil

        if os.path.exists(self.cache_dir):
            shutil.rmtree(self.cache_dir)
        os.makedirs(self.cache_dir, exist_ok=True)

        if self._cache_collection is not None:
            self._cache_collection.delete_many(
                {
                    "exchange": self.exchange_name,
                    "exchange_type": self.exchange_type,
                }
            )

        self._log_operational("Cache cleared")

    def get_available_symbols(self) -> List[str]:
        """Get list of available trading symbols."""
        try:
            markets = self.exchange.load_markets()
            return list(markets.keys())
        except Exception as e:
            logger.error(f"Error fetching symbols: {e}")
            return []

    def get_exchange_info(self) -> Dict[str, Any]:
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


if __name__ == "__main__":
    loader = DataLoader("binance")
    df = loader.get_data("BTC/USDT", "1h", "2023-01-01", "2023-01-31")
    logger.info(f"Fetched {len(df)} bars")
    logger.debug(df.head())
    logger.debug(df.columns.tolist())
