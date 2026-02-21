"""
Centralized logging configuration for Backtrade Machine.

Usage in any module:
    from engine.logger import get_logger
    logger = get_logger(__name__)

WebSocket live-log delivery:
    The server sets up a QueueHandler at startup so all logging
    records from any module are forwarded to the WebSocket broadcast queue.
"""

import logging
import queue
from typing import Optional

# ── Root logger name for the whole project ──────────────────────────────────
PROJECT_ROOT_LOGGER = "backtrade"

# ── A single shared queue used by the WebSocket broadcaster ─────────────────
# The server imports and uses this queue directly.
ws_log_queue: queue.Queue = queue.Queue()


# ── Custom handler that pushes formatted records into ws_log_queue ───────────
class QueueHandler(logging.Handler):
    """
    Logging handler that puts formatted log records into `ws_log_queue`.
    The server's broadcast_from_queue() task drains this queue and sends
    messages to all connected WebSocket clients.
    """

    def __init__(self, q: queue.Queue):
        super().__init__()
        self._queue = q

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            self._queue.put(msg)
        except Exception:
            self.handleError(record)


def setup_logging(
    level: int = logging.INFO,
    run_id: Optional[str] = None,
    enable_ws: bool = True,
) -> None:
    """
    Configure the project root logger.

    Called once by the server at startup (enable_ws=True) and optionally
    once more per backtest run to propagate the run_id prefix.

    Args:
        level: Logging level (logging.DEBUG / logging.INFO / …)
        run_id: Optional run identifier prepended to every WS message.
        enable_ws: If True, attach the QueueHandler for WebSocket delivery.
    """
    root = logging.getLogger(PROJECT_ROOT_LOGGER)
    root.setLevel(level)
    root.propagate = False  # Don't bubble up to the global root logger

    # Remove stale handlers to avoid duplicate messages on re-setup
    root.handlers.clear()

    # ── Console / terminal handler ───────────────────────────────────────────
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_fmt = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
    console_handler.setFormatter(logging.Formatter(console_fmt, datefmt="%H:%M:%S"))
    root.addHandler(console_handler)

    # ── WebSocket queue handler ──────────────────────────────────────────────
    if enable_ws:
        prefix = f"[{run_id}] " if run_id else ""
        ws_handler = QueueHandler(ws_log_queue)
        ws_handler.setLevel(level)
        # Format mirrors the current print() style so the UI looks the same
        ws_handler.setFormatter(logging.Formatter(f"{prefix}%(message)s"))
        root.addHandler(ws_handler)


def get_logger(name: str) -> logging.Logger:
    """
    Return a child logger under the project root namespace.

    Example:
        # in engine/data_loader.py
        logger = get_logger(__name__)   # → 'backtrade.engine.data_loader'
    """
    return logging.getLogger(f"{PROJECT_ROOT_LOGGER}.{name}")
