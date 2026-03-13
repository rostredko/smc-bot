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
from typing import Optional, Union

# ── Root logger name for the whole project ──────────────────────────────────
PROJECT_ROOT_LOGGER = "backtrade"
WS_LOG_QUEUE_MAXSIZE = 10000

# ── A single shared queue used by the WebSocket broadcaster ─────────────────
# The server imports and uses this queue directly.
ws_log_queue: queue.Queue = queue.Queue(maxsize=WS_LOG_QUEUE_MAXSIZE)


def clear_ws_log_queue() -> int:
    """
    Drain queued WebSocket log lines.
    Returns number of removed messages.
    """
    removed = 0
    while True:
        try:
            ws_log_queue.get_nowait()
            removed += 1
        except queue.Empty:
            break
    return removed


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
            try:
                self._queue.put_nowait(msg)
            except queue.Full:
                # Bounded queue: drop oldest line to avoid unbounded memory growth.
                try:
                    self._queue.get_nowait()
                    self._queue.put_nowait(msg)
                except queue.Empty:
                    pass
        except Exception:
            self.handleError(record)


class WsFormatter(logging.Formatter):
    """Formatter for dashboard/live-output messages with optional per-record prefix overrides."""

    def __init__(self, prefix: str = ""):
        super().__init__("%(message)s")
        self._prefix = prefix

    def format(self, record: logging.LogRecord) -> str:
        message = super().format(record)
        prefix = getattr(record, "ws_prefix_override", self._prefix)
        return f"{prefix}{message}" if prefix else message


def coerce_log_level(level: Union[int, str, None], default: int = logging.INFO) -> int:
    """Normalize string/int log levels to a valid logging module constant."""
    if isinstance(level, int):
        return level
    if isinstance(level, str):
        normalized = level.strip().upper()
        if not normalized:
            return default
        resolved = logging.getLevelName(normalized)
        if isinstance(resolved, int):
            return resolved
    return default


def setup_logging(
    level: int = logging.INFO,
    console_level: Optional[Union[int, str]] = None,
    run_id: Optional[str] = None,
    ws_level: Optional[Union[int, str]] = None,
    enable_ws: bool = True,
) -> None:
    """
    Configure the project root logger.

    Called once by the server at startup (enable_ws=True) and optionally
    once more per backtest run to propagate the run_id prefix.

    Args:
        level: Logging level (logging.DEBUG / logging.INFO / …)
        console_level: Optional console handler level override.
        run_id: Optional run identifier prepended to every WS message.
        ws_level: Optional WebSocket handler level override.
        enable_ws: If True, attach the QueueHandler for WebSocket delivery.
    """
    level = coerce_log_level(level, default=logging.INFO)
    console_level = coerce_log_level(console_level, default=level)
    ws_level = coerce_log_level(ws_level, default=level)
    root_level = min(level, console_level, ws_level)
    root = logging.getLogger(PROJECT_ROOT_LOGGER)
    root.setLevel(root_level)
    root.propagate = False  # Don't bubble up to the global root logger

    # Remove stale handlers to avoid duplicate messages on re-setup
    root.handlers.clear()

    # ── Console / terminal handler ───────────────────────────────────────────
    console_handler = logging.StreamHandler()
    console_handler.setLevel(console_level)
    console_fmt = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
    console_handler.setFormatter(logging.Formatter(console_fmt, datefmt="%H:%M:%S"))
    root.addHandler(console_handler)

    # ── WebSocket queue handler ──────────────────────────────────────────────
    if enable_ws:
        prefix = f"[{run_id}] " if run_id else ""
        ws_handler = QueueHandler(ws_log_queue)
        ws_handler.setLevel(ws_level)
        # Format mirrors the current print() style so the UI looks the same
        ws_handler.setFormatter(WsFormatter(prefix=prefix))
        root.addHandler(ws_handler)


def get_logger(name: str) -> logging.Logger:
    """
    Return a child logger under the project root namespace.

    Example:
        # in engine/data_loader.py
        logger = get_logger(__name__)   # → 'backtrade.engine.data_loader'
    """
    return logging.getLogger(f"{PROJECT_ROOT_LOGGER}.{name}")
