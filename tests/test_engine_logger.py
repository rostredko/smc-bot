"""
Tests for engine/logger.py — setup_logging, get_logger, QueueHandler.
"""
import logging
import os
import queue
import sys
import unittest

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.logger import (
    coerce_log_level,
    get_logger,
    setup_logging,
    QueueHandler,
    WsFormatter,
    PROJECT_ROOT_LOGGER,
    ws_log_queue,
    clear_ws_log_queue,
)


class TestGetLogger(unittest.TestCase):
    def test_get_logger_returns_logger(self):
        logger = get_logger("test.module")
        self.assertIsInstance(logger, logging.Logger)

    def test_get_logger_uses_project_namespace(self):
        logger = get_logger("engine.data_loader")
        self.assertEqual(logger.name, f"{PROJECT_ROOT_LOGGER}.engine.data_loader")


class TestSetupLogging(unittest.TestCase):
    def tearDown(self):
        root = logging.getLogger(PROJECT_ROOT_LOGGER)
        root.handlers.clear()

    def test_setup_logging_no_crash(self):
        setup_logging(level=logging.INFO, enable_ws=False)
        root = logging.getLogger(PROJECT_ROOT_LOGGER)
        self.assertEqual(root.level, logging.INFO)
        self.assertFalse(root.propagate)

    def test_setup_logging_with_ws_adds_queue_handler(self):
        setup_logging(level=logging.DEBUG, enable_ws=True)
        root = logging.getLogger(PROJECT_ROOT_LOGGER)
        queue_handlers = [h for h in root.handlers if isinstance(h, QueueHandler)]
        self.assertEqual(len(queue_handlers), 1)

    def test_setup_logging_with_run_id(self):
        setup_logging(level=logging.INFO, run_id="run-123", enable_ws=True)
        root = logging.getLogger(PROJECT_ROOT_LOGGER)
        self.assertEqual(root.level, logging.INFO)

    def test_setup_logging_accepts_string_level(self):
        setup_logging(level="debug", enable_ws=False)
        root = logging.getLogger(PROJECT_ROOT_LOGGER)
        self.assertEqual(root.level, logging.DEBUG)

    def test_setup_logging_allows_ws_level_override(self):
        setup_logging(level="debug", ws_level="info", enable_ws=True)
        root = logging.getLogger(PROJECT_ROOT_LOGGER)
        queue_handler = next(h for h in root.handlers if isinstance(h, QueueHandler))
        self.assertEqual(root.level, logging.DEBUG)
        self.assertEqual(queue_handler.level, logging.INFO)


class TestCoerceLogLevel(unittest.TestCase):
    def test_coerce_log_level_from_string(self):
        self.assertEqual(coerce_log_level("warning"), logging.WARNING)

    def test_coerce_log_level_falls_back_for_unknown_value(self):
        self.assertEqual(coerce_log_level("not-a-level", default=logging.ERROR), logging.ERROR)


class TestQueueHandler(unittest.TestCase):
    def test_queue_handler_puts_formatted_message_to_queue(self):
        q = queue.Queue()
        handler = QueueHandler(q)
        handler.setFormatter(logging.Formatter("%(message)s"))

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="hello",
            args=(),
            exc_info=None,
        )
        handler.emit(record)

        self.assertFalse(q.empty())
        msg = q.get_nowait()
        self.assertEqual(msg, "hello")

    def test_queue_handler_drops_oldest_when_queue_is_full(self):
        q = queue.Queue(maxsize=1)
        handler = QueueHandler(q)
        handler.setFormatter(logging.Formatter("%(message)s"))

        first = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="first",
            args=(),
            exc_info=None,
        )
        second = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="second",
            args=(),
            exc_info=None,
        )
        handler.emit(first)
        handler.emit(second)

        self.assertFalse(q.empty())
        msg = q.get_nowait()
        self.assertEqual(msg, "second")

    def test_queue_handler_does_not_suppress_messages_by_substring(self):
        q = queue.Queue()
        handler = QueueHandler(q)
        handler.setFormatter(logging.Formatter("%(message)s"))

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="OHLCV fetched: BTC/USDT 1m -> 52 candles",
            args=(),
            exc_info=None,
        )
        handler.emit(record)

        self.assertFalse(q.empty())
        self.assertEqual(q.get_nowait(), "OHLCV fetched: BTC/USDT 1m -> 52 candles")

    def test_clear_ws_log_queue_drains_messages(self):
        clear_ws_log_queue()
        ws_log_queue.put_nowait("line-1")
        ws_log_queue.put_nowait("line-2")
        removed = clear_ws_log_queue()
        self.assertEqual(removed, 2)
        self.assertTrue(ws_log_queue.empty())


class TestWsFormatter(unittest.TestCase):
    def test_ws_formatter_uses_prefix_by_default(self):
        formatter = WsFormatter(prefix="[run-1] ")
        record = logging.LogRecord("test", logging.INFO, "", 0, "hello", (), None)
        self.assertEqual(formatter.format(record), "[run-1] hello")

    def test_ws_formatter_allows_per_record_prefix_override(self):
        formatter = WsFormatter(prefix="[run-1] ")
        record = logging.LogRecord("test", logging.INFO, "", 0, "[LIVE] Starting...", (), None)
        record.ws_prefix_override = ""
        self.assertEqual(formatter.format(record), "[LIVE] Starting...")
