"""
Unit tests for RiskManager position sizing.
"""
import unittest
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strategies.helpers.risk_manager import RiskManager


class TestRiskManager(unittest.TestCase):
    def test_zero_entry_price_returns_zero(self):
        self.assertEqual(
            RiskManager.calculate_position_size(10000, 1.0, 0, 95, 10),
            0.0
        )

    def test_negative_entry_price_returns_zero(self):
        self.assertEqual(
            RiskManager.calculate_position_size(10000, 1.0, -100, 95, 10),
            0.0
        )

    def test_zero_account_value_returns_zero(self):
        self.assertEqual(
            RiskManager.calculate_position_size(0, 1.0, 100, 95, 10),
            0.0
        )

    def test_none_account_value_returns_zero(self):
        self.assertEqual(
            RiskManager.calculate_position_size(None, 1.0, 100, 95, 10),
            0.0
        )

    def test_entry_equals_stop_loss_returns_zero(self):
        size = RiskManager.calculate_position_size(10000, 1.0, 100, 100, 10)
        self.assertEqual(size, 0.0)

    def test_dynamic_sizing_correct_risk(self):
        size = RiskManager.calculate_position_size(
            account_value=10000,
            risk_per_trade_pct=1.0,
            entry_price=100,
            stop_loss=95,
            leverage=10,
            dynamic_sizing=True
        )
        self.assertAlmostEqual(size, 20.0, places=2)

    def test_leverage_cap_applied(self):
        size = RiskManager.calculate_position_size(
            account_value=10000,
            risk_per_trade_pct=10.0,
            entry_price=100,
            stop_loss=99,
            leverage=2,
            dynamic_sizing=True
        )
        self.assertAlmostEqual(size, 200.0, places=2)


if __name__ == "__main__":
    unittest.main()
