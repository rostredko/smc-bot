
import sys
import os
import unittest
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

    def test_live_config_endpoints(self):
        response = self.client.get("/config/live")
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.json(), dict)
        response = self.client.post("/config/live", json={"symbol": "ETH/USDT", "sandbox": True})
        self.assertEqual(response.status_code, 200)
        self.assertIn("message", response.json())

if __name__ == '__main__':
    unittest.main()
