"""Run log capture and persistence for backtest/live runs."""

import logging
import threading
from collections import deque
from pathlib import Path
from typing import Dict, List, Optional, Any

from engine.logger import coerce_log_level

RUN_LOG_CAPTURE_MAX_LINES = 12000
RUN_LOG_DB_TAIL_LINES = 400


class RunLogCollector(logging.Handler):
    """Collects tail logs for persistence in run result payloads."""

    def __init__(self, max_lines: int = RUN_LOG_CAPTURE_MAX_LINES):
        super().__init__(level=logging.INFO)
        self._lines = deque(maxlen=max_lines)
        self._lock = threading.Lock()
        self.total_count = 0

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record).rstrip("\n")
        except Exception:
            self.handleError(record)
            return
        with self._lock:
            self._lines.append(msg)
            self.total_count += 1

    def get_tail(self, max_lines: int = RUN_LOG_DB_TAIL_LINES) -> List[str]:
        with self._lock:
            if max_lines <= 0:
                return []
            lines = list(self._lines)
        return lines[-max_lines:]


def attach_run_log_handlers(
    run_id: str,
    level: int = logging.INFO,
    logs_dir: Optional[Path] = None,
) -> tuple["RunLogCollector", logging.FileHandler, str]:
    """Attach per-run file and in-memory log handlers to the project root logger."""
    if logs_dir is None:
        logs_dir = Path(__file__).parent.parent.parent / "logs" / "runs"
    logs_dir = Path(logs_dir)
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file_path = logs_dir / f"{run_id}.log"
    level = coerce_log_level(level, default=logging.INFO)
    fmt = logging.Formatter(
        "%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.FileHandler(log_file_path, encoding="utf-8")
    file_handler.setLevel(level)
    file_handler.setFormatter(fmt)

    collector = RunLogCollector(max_lines=RUN_LOG_CAPTURE_MAX_LINES)
    collector.setLevel(level)
    collector.setFormatter(fmt)

    root_logger = logging.getLogger("backtrade")
    root_logger.addHandler(file_handler)
    root_logger.addHandler(collector)
    return collector, file_handler, str(log_file_path)


def detach_run_log_handlers(*handlers: Optional[logging.Handler]) -> None:
    """Detach and close run-specific handlers safely."""
    root_logger = logging.getLogger("backtrade")
    for handler in handlers:
        if handler is None:
            continue
        if handler in root_logger.handlers:
            root_logger.removeHandler(handler)
        try:
            handler.flush()
        except Exception:
            pass
        try:
            handler.close()
        except Exception:
            pass


def attach_run_log_metadata(
    payload: Dict[str, Any],
    collector: Optional[RunLogCollector],
    log_file_path: Optional[str],
) -> None:
    """Embed log metadata into saved run payload."""
    if collector is None:
        payload["logs"] = []
        payload["log_lines_total"] = 0
        return
    payload["logs"] = collector.get_tail(RUN_LOG_DB_TAIL_LINES)
    payload["log_lines_total"] = collector.total_count
    if log_file_path:
        payload["log_file"] = log_file_path


def resolve_run_log_levels(config: Optional[Dict[str, Any]] = None) -> tuple[int, int]:
    cfg = config or {}
    app_level = coerce_log_level(cfg.get("log_level"), default=logging.INFO)
    ws_level = coerce_log_level(cfg.get("live_output_log_level"), default=logging.INFO)
    return app_level, ws_level
