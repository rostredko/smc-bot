from datetime import datetime
from typing import Any, Dict, List

from db.connection import get_database


class UserConfigRepository:
    def __init__(self):
        self._coll = None

    def _collection(self):
        if self._coll is None:
            self._coll = get_database()["user_configs"]
        return self._coll

    def list_names(self) -> List[str]:
        cursor = self._collection().find({}, {"_id": 1})
        return sorted(d["_id"] for d in cursor)

    def get(self, name: str) -> Dict[str, Any] | None:
        doc = self._collection().find_one({"_id": name})
        if doc is None:
            return None
        return doc.get("config", doc)

    def save(self, name: str, config: Dict[str, Any]) -> None:
        self._collection().update_one(
            {"_id": name},
            {
                "$set": {
                    "config": config,
                    "updated_at": datetime.utcnow().isoformat() + "Z",
                }
            },
            upsert=True,
        )

    def delete(self, name: str) -> bool:
        result = self._collection().delete_one({"_id": name})
        return result.deleted_count > 0
