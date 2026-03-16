"""Shared state for web-dashboard API (connections, backtests, live trading, console)."""

import asyncio
import threading
from collections import deque
from typing import Dict, List, Optional, Any

from fastapi import WebSocket

from api.models import BacktestStatus

ACTIVE_CONSOLE_BUFFER_MAX_LINES = 5000

running_backtests: Dict[str, BacktestStatus] = {}
active_connections: List[WebSocket] = []
connection_lock = threading.Lock()

live_trading_state: Dict[str, Any] = {
    "is_running": False,
    "engine": None,
    "run_id": None,
    "config": None,
    "start_time": None,
    "stop_requested": False,
}

active_console_state: Dict[str, Any] = {
    "run_id": None,
    "run_type": None,
    "lines": deque(maxlen=ACTIVE_CONSOLE_BUFFER_MAX_LINES),
}
active_console_lock = threading.Lock()

strategy_schema_cache: Dict[str, Dict[str, Any]] = {}
_broadcast_shutdown: asyncio.Event = asyncio.Event()


def _latest_running_backtest_run_id() -> Optional[str]:
    """Return the newest run_id still in running state."""
    for rid, status in reversed(list(running_backtests.items())):
        if status.status == "running":
            return rid
    return None


def _has_active_runtime() -> bool:
    return bool(live_trading_state.get("is_running")) or _latest_running_backtest_run_id() is not None
