
"""
Core BacktestEngine class refactored to use the `backtesting.py` library.
This maintains the original interface for compatibility but delegates execution.
"""

import json
import pandas as pd
from typing import Any, Dict, List
from backtesting import Backtest
from backtesting.lib import FractionalBacktest

from .data_loader import DataLoader
from .logger import Logger
from .adapters import BacktestingAdapter

class BacktestEngine:
    """
    Coordinator using backtesting.py for simulation.
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.initial_capital = config.get("initial_capital", 10000)
        
        self.logger = Logger(config.get("log_level", "INFO"))
        self.data_loader = DataLoader(config.get("exchange", "binance"))
        
        self.strategy_class = None
        self._load_strategy()
        
        self.data = pd.DataFrame()
        self.bt_instance = None # Will hold the Backtest instance

    def _load_strategy(self):
        """Load the specified strategy class."""
        strategy_name = self.config.get("strategy", "price_action_strategy")
        try:
            strategy_module = __import__(f"strategies.{strategy_name}", fromlist=["Strategy"])
            
            # Simple heuristic to find the class
            pascal_name = "".join(x.title() for x in strategy_name.split("_"))
            candidates = [pascal_name, f"{pascal_name}Strategy", "Strategy", "PriceActionStrategy"]
            
            for name in candidates:
                if hasattr(strategy_module, name):
                    self.strategy_class = getattr(strategy_module, name)
                    break
                    
            if not self.strategy_class:
                raise AttributeError(f"Could not find strategy class in {strategy_name}")

            self.logger.log("INFO", f"Loaded strategy class: {self.strategy_class.__name__}")
            
        except Exception as e:
            self.logger.log("ERROR", f"Failed to load strategy: {e}")
            raise e

    def load_data(self):
        """Fetch historical data."""
        symbol = self.config["symbol"]
        timeframe = self.config.get("timeframes", ["1h"])[0] # Use primary
        start = self.config["start_date"]
        end = self.config["end_date"]
        
        self.logger.log("INFO", f"Loading data for {symbol} ({start} - {end})...")
        df = self.data_loader.get_data(symbol, timeframe, start, end)
        
        # Rename columns to match backtesting.py requirements (Title Case)
        df = df.rename(columns={
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume"
        })
        
        # Ensure proper Index
        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index)
            
        self.data = df
        self.logger.log("INFO", f"Loaded {len(df)} bars.")

    def run_backtest(self) -> Dict[str, Any]:
        """Execute backtest using backtesting.py."""
        self.logger.log("INFO", "Starting backtest (backtesting.py engine)...")
        
        # Configure Adapter
        BacktestingAdapter.target_strategy_class = self.strategy_class
        
        # Merge strategy-specific config with main config so Adapter has access to everything
        # (risk_per_trade, initial_capital, etc.)
        strategy_conf = self.config.get("strategy_config", {}).copy()
        full_conf = self.config.copy()
        full_conf.update(strategy_conf) # Strategy config overrides main config if key conflict (unlikely)
        
        BacktestingAdapter.target_strategy_config = full_conf
        
        # Ensure config has timeframe for consistency
        BacktestingAdapter.target_strategy_config['primary_timeframe'] = self.config.get("timeframes", ["1h"])[0]
        
        # Pass reference price for scaling detection
        if not self.data.empty:
            BacktestingAdapter.target_strategy_config['reference_price'] = float(self.data['Close'].iloc[0])

        if not self.data.empty:
            BacktestingAdapter.target_strategy_config['reference_price'] = float(self.data['Close'].iloc[0])

        # Initialize detailed trades collection
        BacktestingAdapter.detailed_trades = []

        # Initialize Backtest with Fractional support
        self.bt_instance = FractionalBacktest(
            self.data,
            BacktestingAdapter,
            cash=self.initial_capital,
            commission=self.config.get("commission", 0.0004), # DEFAULT TAKER FEE
            exclusive_orders=True # Simplified mode
        )
        
        # Run
        stats = self.bt_instance.run()
        
        # Map Results
        metrics = self._map_results(stats)
        
        
        self.logger.log("INFO", "Backtest completed.")
        
        # Prepare metrics for logging (Logger expects 0-100 for win_rate)
        log_metrics = metrics.copy()
        log_metrics['win_rate'] = metrics['win_rate'] * 100
        self.logger.print_summary(log_metrics)
        
        return metrics

    def _map_results(self, stats: pd.Series) -> Dict[str, Any]:
        """Convert backtesting.py stats Series to our standard metrics dictionary."""
        # Extract trade history
        # backtesting.py stores trades in stats['_trades']
        trades_df = stats['_trades']
        closed_trades = []
        
        winning_trades = 0
        losing_trades = 0
        total_win_pnl = 0.0
        total_loss_pnl = 0.0
        
        if not trades_df.empty:
            for _, t in trades_df.iterrows():
                pnl = t.get("PnL")
                if pnl > 0:
                    winning_trades += 1
                    total_win_pnl += pnl
                elif pnl < 0:
                    losing_trades += 1
                    total_loss_pnl += pnl
                    
                # Attempt to find detailed info
                detailed_info = {}
                if hasattr(BacktestingAdapter, 'detailed_trades'):
                     # Match by Entry Time (approximate or exact)
                     # stats EntryTime is pd.Timestamp
                     entry_time = t.get("EntryTime")
                     
                     # Normalize comparison to string to avoid Timestamp type issues
                     entry_time_str = str(entry_time)
                     
                     for dt in BacktestingAdapter.detailed_trades:
                         # dt['entry_time'] comes from backtesting Trade object (Timestamp)
                         dt_time_str = str(dt.get('entry_time'))
                         
                         if dt_time_str == entry_time_str:
                             detailed_info = dt
                             break
                
                # Format Duration
                duration = t.get("Duration")
                duration_str = "N/A"
                if pd.notna(duration):
                    # duration is a Timedelta
                    total_seconds = int(duration.total_seconds())
                    days = total_seconds // 86400
                    hours = (total_seconds % 86400) // 3600
                    minutes = (total_seconds % 3600) // 60
                    
                    parts = []
                    if days > 0: parts.append(f"{days}d")
                    if hours > 0: parts.append(f"{hours}h")
                    parts.append(f"{minutes}m")
                    duration_str = " ".join(parts)

                closed_trades.append({
                    "entry_time": t.get("EntryTime").isoformat() if pd.notna(t.get("EntryTime")) else None,
                    "exit_time": t.get("ExitTime").isoformat() if pd.notna(t.get("ExitTime")) else None,
                    "entry_price": t.get("EntryPrice"),
                    "exit_price": t.get("ExitPrice"),
                    "direction": "LONG" if t.get("Size") > 0 else "SHORT",
                    "size": abs(t.get("Size", 0)), # Absolute size
                    "pnl": pnl,
                    "return_pct": t.get("ReturnPct") * 100,
                    "reason": detailed_info.get("reason", "Signal"),
                    "stop_loss": detailed_info.get("stop_loss"),
                    "take_profit": detailed_info.get("take_profit"),
                    "exit_reason": detailed_info.get("exit_reason", "Signal/Manual"),
                    "duration": duration_str,
                    "metadata": detailed_info.get("metadata", {})
                })

        # Calculate PnL manually if needed, or derived from Equity
        equity_final = stats.get("Equity Final [$]", 0.0)
        total_pnl = equity_final - self.initial_capital

        # Map Metrics
        metrics = {
            # Frontend likely expects 0.0-1.0 for Win Rate (formatting as %), but backtesting.py gives 0-100
            "win_rate": stats.get("Win Rate [%]", 0.0) / 100.0, 
            "total_return_pct": stats.get("Return [%]", 0.0),
            "total_trades": int(stats.get("# Trades", 0)),
            "total_pnl": total_pnl,
            "sharpe_ratio": stats.get("Sharpe Ratio", 0.0),
            
            # Map robustly
            "profit_factor": stats.get("Profit Factor", 0.0),
            "max_drawdown": abs(stats.get("Max. Drawdown [%]", 0.0)), # Ensure positive or match format
            "signals_generated": int(stats.get("# Trades", 0)), # Approximation: executed trades = signals
            
            "max_drawdown_pct": stats.get("Max. Drawdown [%]", 0.0), 
            "avg_trade_pct": stats.get("Avg. Trade [%]", 0.0),
            
            "equity_final": equity_final,
            "equity_peak": stats.get("Equity Peak [$]", 0.0),
            
            "winning_trades": winning_trades,
            "losing_trades": losing_trades,
            "avg_win": total_win_pnl / winning_trades if winning_trades > 0 else 0.0,
            "avg_loss": total_loss_pnl / losing_trades if losing_trades > 0 else 0.0,
            
            # Detailed lists expected by frontend
            "closed_trades": closed_trades,
            "equity_curve": [],
            "configuration": self.config
        }
        
        # Parse equity curve for chart
        if '_equity_curve' in stats:
            eq_df = stats['_equity_curve']
            # Format: timestamp, equity, drawdown?
            curve = []
            for ts, row in eq_df.iterrows():
                curve.append({
                    "date": ts.isoformat() if hasattr(ts, 'isoformat') else str(ts), # Rename timestamp -> date
                    "equity": row['Equity'],
                    "drawdown": row.get('DrawdownPct', 0) * 100 if 'DrawdownPct' in row else 0
                })
            metrics['equity_curve'] = curve

        return metrics

def run_backtest(config_file: str):
    """Entry point."""
    with open(config_file, "r") as f:
        config = json.load(f)

    engine = BacktestEngine(config)
    engine.load_data()
    metrics = engine.run_backtest()

    return engine, metrics
