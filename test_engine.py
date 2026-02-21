from engine.bt_backtest_engine import BTBacktestEngine
import sys

engine_config = {
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

class Tracer:
    def __init__(self, original):
        self.original = original
    def get_data(self, symbol, tf, start_date, end_date):
        print(f"TRACER: get_data called with tf={tf}")
        # Abort to prevent waiting
        sys.exit(0)

engine = BTBacktestEngine(engine_config)
engine.data_loader.get_data = Tracer(engine.data_loader).get_data
print(f"engine.config['timeframes'] = {engine.config['timeframes']}")
engine.add_data()
