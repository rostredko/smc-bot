from datetime import datetime
from typing import Any, Dict

from db.connection import get_database

BACKTEST_CONFIG_ID = "default"
LIVE_CONFIG_ID = "live"


class AppConfigRepository:
    def __init__(self):
        self._coll = None

    def _collection(self):
        if self._coll is None:
            self._coll = get_database()["app_config"]
        return self._coll

    def get(self, config_id: str = BACKTEST_CONFIG_ID) -> Dict[str, Any]:
        doc = self._collection().find_one({"_id": config_id})
        if doc is None:
            return {}
        return doc.get("config", {})

    def save(self, config: Dict[str, Any], config_id: str = BACKTEST_CONFIG_ID) -> None:
        self._collection().update_one(
            {"_id": config_id},
            {
                "$set": {
                    "config": config,
                    "updated_at": datetime.utcnow().isoformat() + "Z",
                }
            },
            upsert=True,
        )

    def get_backtest_config(self) -> Dict[str, Any]:
        return self.get(BACKTEST_CONFIG_ID)

    def get_live_config(self) -> Dict[str, Any]:
        return self.get(LIVE_CONFIG_ID)

    def save_live_config(self, config: Dict[str, Any]) -> None:
        self.save(config, LIVE_CONFIG_ID)
