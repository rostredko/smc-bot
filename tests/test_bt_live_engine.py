"""
Tests for engine/bt_live_engine.py — BTLiveEngine placeholder.
"""
import unittest
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.bt_live_engine import BTLiveEngine


class TestBTLiveEngine(unittest.TestCase):
    def test_init_no_crash(self):
        config = {"initial_capital": 10000, "exchange": "binance"}
        engine = BTLiveEngine(config)
        self.assertIsNotNone(engine.cerebro)
        self.assertIsNone(engine.strategy)

    def test_add_data_logs_warning(self):
        config = {"initial_capital": 10000}
        engine = BTLiveEngine(config)
        engine.add_data()
        self.assertEqual(len(engine.cerebro.datas), 0)

    def test_run_live_logs_info(self):
        config = {"initial_capital": 10000}
        engine = BTLiveEngine(config)
        engine.run_live()
