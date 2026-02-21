from fastapi.testclient import TestClient
from web_dashboard.server import app

client = TestClient(app)

config = {
  "initial_capital": 10000.0,
  "risk_per_trade": 1.5,
  "max_drawdown": 30.0,
  "max_positions": 1,
  "leverage": 10.0,
  "symbol": "BTC/USDT",
  "timeframes": ["4h", "1h"],
  "start_date": "2025-01-01",
  "end_date": "2025-12-31",
  "strategy": "bt_price_action",
  "strategy_config": {},
  "min_risk_reward": 2.5,
  "trailing_stop_distance": 0.04,
  "breakeven_trigger_r": 1.5,
  "dynamic_position_sizing": True
}

resp = client.post("/backtest/start", json={"config": config})
print("Response:", resp.json())
