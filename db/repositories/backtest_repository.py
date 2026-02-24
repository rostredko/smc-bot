from datetime import datetime
from typing import Any, Dict, List, Optional

from db.connection import get_database


def _sanitize_for_mongo(obj: Any) -> Any:
    if hasattr(obj, "item"):
        return obj.item()
    if isinstance(obj, dict):
        return {k: _sanitize_for_mongo(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_for_mongo(v) for v in obj]
    if isinstance(obj, datetime):
        return obj
    return obj


def _run_id_from_filename(filename: str) -> str:
    if filename.endswith(".json"):
        return filename[:-5]
    return filename


def _filename_from_run_id(run_id: str) -> str:
    return f"{run_id}.json"


class BacktestRepository:
    def __init__(self):
        self._coll = None

    def _collection(self):
        if self._coll is None:
            self._coll = get_database()["backtests"]
        return self._coll

    def save(self, run_id: str, data: Dict[str, Any]) -> None:
        doc = _sanitize_for_mongo(dict(data))
        doc["_id"] = run_id
        doc["created_at"] = datetime.utcnow().isoformat() + "Z"
        self._collection().replace_one({"_id": run_id}, doc, upsert=True)

    def get_by_id(self, run_id: str) -> Optional[Dict[str, Any]]:
        doc = self._collection().find_one({"_id": run_id})
        if doc is None:
            return None
        doc = dict(doc)
        doc.pop("_id", None)
        return doc

    def get_by_filename(self, filename: str) -> Optional[Dict[str, Any]]:
        return self.get_by_id(_run_id_from_filename(filename))

    def list_ids(self) -> List[str]:
        cursor = self._collection().find({}, {"_id": 1}).sort("created_at", -1)
        return [d["_id"] for d in cursor]

    def list_paginated(
        self, page: int = 1, page_size: int = 10
    ) -> tuple[List[Dict[str, Any]], int]:
        coll = self._collection()
        total = coll.count_documents({})
        total_pages = (total + page_size - 1) // page_size if total > 0 else 0
        if page < 1:
            page = 1
        if page > total_pages and total_pages > 0:
            page = total_pages
        offset = (page - 1) * page_size
        cursor = coll.find({}).sort("created_at", -1).skip(offset).limit(page_size)
        history = []
        for doc in cursor:
            run_id = doc["_id"]
            cfg = doc.get("configuration", {})
            history.append(
                {
                    "filename": _filename_from_run_id(run_id),
                    "timestamp": doc.get("created_at", ""),
                    "total_pnl": doc.get("total_pnl", 0),
                    "initial_capital": doc.get("initial_capital", cfg.get("initial_capital", 10000)),
                    "win_rate": doc.get("win_rate", 0),
                    "max_drawdown": doc.get("max_drawdown", 0),
                    "total_trades": doc.get("total_trades", 0),
                    "profit_factor": doc.get("profit_factor", 0),
                    "sharpe_ratio": doc.get("sharpe_ratio", 0),
                    "expected_value": doc.get("expected_value", 0),
                    "avg_win": doc.get("avg_win", 0),
                    "avg_loss": doc.get("avg_loss", 0),
                    "winning_trades": doc.get("winning_trades", 0),
                    "losing_trades": doc.get("losing_trades", 0),
                    "strategy": cfg.get("strategy", "Unknown"),
                    "configuration": cfg,
                }
            )
        return history, total

    def delete(self, run_id: str) -> bool:
        result = self._collection().delete_one({"_id": run_id})
        return result.deleted_count > 0

    def delete_by_filename(self, filename: str) -> bool:
        return self.delete(_run_id_from_filename(filename))
