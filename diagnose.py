import sys
import logging
from backtrade.engine.bt_backtest_engine import BacktestEngine

logging.basicConfig(level=logging.INFO)

def run_test(filters_to_disable):
    config = {
        "strategy": "bt_price_action",
        "symbol": "BTC/USDT",
        "timeframes": ["4h", "15m"],
        "exchange": "binance",
        "exchange_type": "future",
        "execution_mode": "paper",
        "start_date": "2023-01-01",
        "end_date": "2023-01-31",
        "strategy_config": {
            "use_trend_filter": False,
            "use_rsi_filter": False,
            "use_adx_filter": False,
            "use_pinbar_quality_filter": False,
            "use_engulfing_quality_filter": False,
            
            "use_opposing_level_tp": True,
            "use_premium_discount_filter": True,
            "use_structure_filter": True,
            "use_space_to_target_filter": True,
            "use_choch_displacement_filter": True,
            "use_ltf_choch_trigger": True,
            "ltf_choch_entry_window_bars": 6,
            "risk_reward_ratio": 1.5,
            "space_to_target_min_rr": 1.2
        }
    }
    
    for f in filters_to_disable:
        config["strategy_config"][f] = False
        
    engine = BacktestEngine(config)
    results = engine.run_backtest()
    trades = results.get("total_trades", 0)
    print(f"Disabled: {filters_to_disable} => Trades: {trades}")

if __name__ == "__main__":
    print("Testing base config (all requested filters ON)...")
    run_test([])
    
    filters = [
        "use_ltf_choch_trigger",
        "use_space_to_target_filter",
        "use_premium_discount_filter",
        "use_structure_filter",
    ]
    
    for f in filters:
        run_test([f])
        
    print("Testing ALL OFF...")
    run_test(filters)
