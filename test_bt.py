import requests
import json
import time

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
  "strategy_config": {
    "use_trend_filter": True,
    "trend_ema_period": 200,
    "use_rsi_filter": True,
    "rsi_period": 14,
    "rsi_overbought": 70,
    "rsi_oversold": 30,
    "use_rsi_momentum": False,
    "rsi_momentum_threshold": 60,
    "use_adx_filter": True,
    "adx_period": 14,
    "adx_threshold": 30,
    "min_range_factor": 1.2,
    "min_wick_to_range": 0.6,
    "max_body_to_range": 0.3,
    "risk_reward_ratio": 2,
    "sl_buffer_atr": 1.5,
    "trailing_stop_distance": 0.04,
    "breakeven_trigger_r": 1.5,
    "risk_per_trade": 1.5,
    "leverage": 10.0,
    "dynamic_position_sizing": True,
    "max_drawdown": 30.0
  },
  "min_risk_reward": 2.5,
  "trailing_stop_distance": 0.04,
  "breakeven_trigger_r": 1.5,
  "max_total_risk_percent": 15.0,
  "dynamic_position_sizing": True,
  "commission": 0.0004,
  "taker_fee": 0.04,
  "slippage_bp": 0.0,
  "log_level": "INFO",
  "export_logs": True,
  "log_file": "/Users/rostislav/Projects/smc-bot/results/backtest_logs.json",
  "detailed_signals": True,
  "detailed_trades": True,
  "market_analysis": True,
  "save_results": True,
  "results_file": "results/backtest_results.json",
  "export_trades": True,
  "trades_file": "results/trades_history.json"
}

resp = requests.post("http://localhost:8000/backtest/start", json={"config": config})
run_id = resp.json()["run_id"]
print("Started:", run_id)

while True:
    st = requests.get(f"http://localhost:8000/backtest/status/{run_id}").json()
    print(st["status"], st.get("message", ""))
    if st["status"] in ["completed", "failed", "cancelled"]:
        print("Done. PNL:", st.get("results", {}).get("total_pnl"))
        break
    time.sleep(1)
