from datetime import datetime
from typing import Any, Dict, List

from db.connection import get_database


_ORDER_DOC_ID = "__template_order__"


class UserConfigRepository:
    def __init__(self):
        self._coll = None

    def _collection(self):
        if self._coll is None:
            self._coll = get_database()["user_configs"]
        return self._coll

    def list_names(self) -> List[str]:
        cursor = self._collection().find({"_id": {"$ne": _ORDER_DOC_ID}}, {"_id": 1})
        return sorted(d["_id"] for d in cursor)

    def _list_names_by_updated(self) -> List[str]:
        """Config names sorted by updated_at descending (newest first), excluding order doc."""
        cursor = self._collection().find(
            {"_id": {"$ne": _ORDER_DOC_ID}},
            {"_id": 1, "updated_at": 1}
        ).sort([("updated_at", -1), ("_id", 1)])
        return [d["_id"] for d in cursor]

    def get_template_order(self) -> List[str] | None:
        """Return saved template order, or None if not set."""
        doc = self._collection().find_one({"_id": _ORDER_DOC_ID})
        if doc and isinstance(doc.get("order"), list):
            return doc["order"]
        return None

    def save_template_order(self, order: List[str]) -> None:
        """Persist template priority order (higher index = lower priority)."""
        self._collection().update_one(
            {"_id": _ORDER_DOC_ID},
            {"$set": {"order": order, "updated_at": datetime.utcnow().isoformat() + "Z"}},
            upsert=True,
        )

    def list_names_sorted_by_priority(self) -> List[str]:
        """Return config names: by saved priority if set, else by updated_at (newest first)."""
        saved_order = self.get_template_order()
        by_updated = self._list_names_by_updated()
        if not saved_order:
            return by_updated
        by_updated_set = set(by_updated)
        known = [n for n in saved_order if n in by_updated_set]
        known_set = set(known)
        new_ones = [n for n in by_updated if n not in known_set]
        return known + new_ones

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
