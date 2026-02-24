"""
MongoDB connection for Backtrade Machine.
Uses MONGODB_URI and MONGODB_DB from environment.
"""

import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
MONGODB_DB = os.getenv("MONGODB_DB", "backtrade")
USE_DATABASE = os.getenv("USE_DATABASE", "true").lower() in ("true", "1", "yes")

_client = None
_db = None
_available = None


def get_database():
    """Return MongoDB database instance. Raises if connection fails."""
    global _client, _db
    if _db is not None:
        return _db
    if os.getenv("USE_MONGOMOCK", "").lower() in ("true", "1", "yes"):
        import mongomock
        _client = mongomock.MongoClient()
        _db = _client[MONGODB_DB]
    else:
        from pymongo import MongoClient
        _client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=3000)
        _db = _client[MONGODB_DB]
        _client.admin.command("ping")
    return _db


def is_database_available() -> bool:
    """Check if MongoDB is reachable and USE_DATABASE is enabled."""
    global _available
    if _available is not None:
        return _available
    use_mock = os.getenv("USE_MONGOMOCK", "").lower() in ("true", "1", "yes")
    if not use_mock and not USE_DATABASE:
        _available = False
        return False
    try:
        get_database()
        _available = True
        return True
    except Exception:
        _available = False
        return False


def init_db():
    """Create indexes for collections."""
    if not is_database_available():
        return
    db = get_database()

    backtests = db["backtests"]
    backtests.create_index("created_at", name="ix_created_at")
    backtests.create_index("configuration.symbol", name="ix_symbol")
    backtests.create_index("configuration.strategy", name="ix_strategy")
    backtests.create_index("total_pnl", name="ix_total_pnl")
