
import sys
import os
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient

# Add web-dashboard to path to import server.py
# We need to go up one level from tests, then into web-dashboard
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'web-dashboard'))
sys.path.insert(0, PROJECT_ROOT)

try:
    from server import app
except ImportError:
    print("Failed to import server from web-dashboard")
    app = None

from db.repositories import AppConfigRepository

class TestAPI(unittest.TestCase):
    def setUp(self):
        if app:
            self.client = TestClient(app)
        else:
            self.skipTest("Could not import app from server")

    def test_health_check(self):
        # We don't have a root endpoint defined in the snippet I saw, 
        # but we have /results
        response = self.client.get("/results")
        self.assertEqual(response.status_code, 200)
        self.assertIn("results", response.json())

    def test_get_config(self):
        response = self.client.get("/config")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        # Empty config returns {}; populated config has initial_capital, strategy
        self.assertIsInstance(data, dict)

    def test_history_endpoint(self):
        response = self.client.get("/api/backtest/history")
        self.assertEqual(response.status_code, 200)
        self.assertIn("history", response.json())

    def test_strategies_endpoint_returns_only_public_strategies(self):
        response = self.client.get("/strategies")
        self.assertEqual(response.status_code, 200)

        strategies = response.json()["strategies"]
        names = [strategy["name"] for strategy in strategies]

        self.assertEqual(names, ["bt_price_action", "fast_test_strategy"])
        self.assertNotIn("market_structure", names)

    def test_live_config_endpoints(self):
        response = self.client.get("/config/live")
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.json(), dict)
        response = self.client.post("/config/live", json={"symbol": "ETH/USDT", "exchange": "binance"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("message", response.json())

        live_config = self.client.get("/config/live").json()
        self.assertEqual(live_config.get("execution_mode"), "paper")
        self.assertEqual(live_config.get("maker_fee_bps"), 2.0)
        self.assertEqual(live_config.get("taker_fee_bps"), 4.0)
        self.assertEqual(live_config.get("commission"), 0.0004)

    def test_live_config_endpoint_ignores_legacy_auth_fields(self):
        response = self.client.post(
            "/config/live",
            json={
                "symbol": "BTC/USDT",
                "exchange": "binance",
                "apiKey": "legacy-key",
                "secret": "legacy-secret",
                "sandbox": True,
            },
        )
        self.assertEqual(response.status_code, 200)

        config = AppConfigRepository().get_live_config()
        self.assertEqual(config.get("exchange"), "binance")
        self.assertNotIn("apiKey", config)
        self.assertNotIn("secret", config)
        self.assertNotIn("sandbox", config)

    def test_live_config_get_masks_legacy_auth_fields_from_existing_storage(self):
        with patch.object(
            AppConfigRepository,
            "get_live_config",
            return_value={"exchange": "binance", "apiKey": "ABCD1234", "secret": "supersecret"},
        ):
            response = self.client.get("/config/live")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get("exchange"), "binance")
        self.assertNotIn("apiKey", data)
        self.assertNotIn("secret", data)

if __name__ == '__main__':
    unittest.main()
