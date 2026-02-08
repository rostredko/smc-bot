#!/usr/bin/env python3
"""
SMC Trading Engine - Main Entry Point
This script provides easy access to all main functionality including backtesting, live trading, and testing.
"""

import json
import os
import sys
import argparse
from pathlib import Path
from typing import Dict, Any, Optional

# Add engine directory to path
engine_dir = Path(__file__).parent / "engine"
sys.path.insert(0, str(engine_dir))

from engine.bt_backtest_engine import BTBacktestEngine
from engine.bt_live_engine import BTLiveEngine
from strategies.bt_price_action import PriceActionStrategy


def create_default_config() -> Dict[str, Any]:
    """Create a default configuration for backtesting."""
    return {
        # Account settings
        "initial_capital": 10000,
        "risk_per_trade": 2.0,  # 2% risk per trade
        "max_drawdown": 15.0,  # 15% max drawdown
        "max_positions": 3,  # Legacy parameter - now managed by risk/reward ratio
        "leverage": 10.0,  # 10x leverage
        # Trading pair and timeframes
        "symbol": "BTC/USDT",
        "timeframes": ["4h"], # Backtrader works best with single timeframe or properly aligned ones. Start with 1.
        "exchange": "binance",
        # Backtest period
        "start_date": "2023-01-01",
        "end_date": "2023-12-31",
        # Strategy settings
        "strategy": "price_action",
        "strategy_config": {
            "trend_ema_period": 50,
            "rsi_period": 14,
            "risk_reward_ratio": 2.5,
        },
        # Risk management
        "min_risk_reward": 3.0,  # Minimum 1:3 R:R
        # Logging
        "log_level": "INFO",
        "export_logs": True,
        "log_file": "results/backtest_logs.json",
    }


def load_config_from_json(config_file: str) -> Dict[str, Any]:
    """
    Load configuration from JSON file.

    Args:
        config_file: Path to JSON configuration file

    Returns:
        Configuration dictionary
    """
    try:
        with open(config_file, "r") as f:
            json_config = json.load(f)

        # Convert JSON structure to engine format
        # Support both flat and nested structures

        # Check strategy first
        strategy_conf = json_config.get("strategy", {})
        if isinstance(strategy_conf, str):
            strategy_name = strategy_conf
        else:
            strategy_name = strategy_conf.get("name", "")
        
        # Default to Price Action if not specified/legacy
        if not strategy_name:
             strategy_name = "price_action"

        config = {
            # Account settings (try nested first, then flat)
            "initial_capital": json_config.get("account", {}).get("initial_capital", json_config.get("initial_capital", 10000)),
            "risk_per_trade": json_config.get("account", {}).get("risk_per_trade", json_config.get("risk_per_trade", 2.0)),
            "commission": json_config.get("trading", {}).get("commission", json_config.get("commission", 0.0004)),
            
            # Trading settings (try nested first, then flat)
            "symbol": json_config.get("trading", {}).get("symbol", json_config.get("symbol", "BTC/USDT")),
            "timeframes": json_config.get("trading", {}).get("timeframes", json_config.get("timeframes", ["4h", "15m"])),
            "exchange": json_config.get("trading", {}).get("exchange", json_config.get("exchange", "binance")),
            
            # Period settings (try nested first, then flat)
            "start_date": json_config.get("period", {}).get("start_date", json_config.get("start_date", "2023-01-01")),
            "end_date": json_config.get("period", {}).get("end_date", json_config.get("end_date", "2023-12-31")),
            
            # Strategy settings
            "strategy": strategy_name,
            "strategy_config": (json_config.get("strategy", {}) if isinstance(json_config.get("strategy"), dict) else {}).get("config", json_config.get("strategy_config", {})),
            
            # Output settings
            "save_results": json_config.get("output", {}).get("save_results", True),
            "results_file": json_config.get("output", {}).get("results_file", "results/backtest_results.json"),
            "export_trades": json_config.get("output", {}).get("export_trades", True),
            "trades_file": json_config.get("output", {}).get("trades_file", "results/trades_history.json"),
        }

        return config

    except FileNotFoundError:
        print(f"❌ Configuration file not found: {config_file}")
        return None
    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON in configuration file: {e}")
        return None
    except Exception as e:
        print(f"❌ Error loading configuration: {e}")
        return None


def run_backtest_from_config(config_file: str, config_name: Optional[str] = None):
    """
    Run backtest from JSON configuration file.

    Args:
        config_file: Path to JSON configuration file
        config_name: Optional name for the configuration (defaults to filename)

    Returns:
        Tuple of (engine, metrics) or (None, None) if failed
    """
    if config_name is None:
        config_name = os.path.basename(config_file).replace(".json", "")

    print(f"\n{'='*60}")
    print(f"RUNNING BACKTEST: {config_name}")
    print(f"Configuration: {config_file}")
    print(f"{'='*60}")

    # Load configuration
    config = load_config_from_json(config_file)
    if config is None:
        return None, None

    # Display configuration summary
    print(f"📊 Configuration Summary:")
    print(f"   Strategy: {config['strategy']}")
    print(f"   Symbol: {config['symbol']}")
    print(f"   Period: {config['start_date']} to {config['end_date']}")
    print(f"   Capital: ${config['initial_capital']:,}")

    try:
        # Create and run the backtest engine
        engine = BTBacktestEngine(config)
        
        # Add Strategy (Currently only supports PriceAction)
        engine.add_strategy(PriceActionStrategy, **config.get('strategy_config', {}))
        
        metrics = engine.run_backtest()

        # Save results if requested
        if config.get("save_results", False):
            results_file = config.get("results_file", f"{config_name}_results.json")
            save_results(metrics, results_file)
            print(f"📊 Results saved to: {results_file}")

        # Export trades if requested
        if config.get("export_trades", False):
            trades_file = config.get("trades_file", f"{config_name}_trades.json")
            export_trades(engine.closed_trades, trades_file)
            print(f"💼 Trades exported to: {trades_file}")

        return engine, metrics

    except Exception as e:
        print(f"❌ Error running backtest: {e}")
        import traceback

        traceback.print_exc()
        return None, None


def save_results(metrics: Dict[str, Any], filename: str):
    """Save backtest results to JSON file."""
    try:
        with open(filename, "w") as f:
            json.dump(metrics, f, indent=2, default=str)
    except Exception as e:
        print(f"❌ Error saving results: {e}")


def export_trades(trades: list, filename: str):
    """Export trade history to JSON file."""
    try:
        # Trades are already a list of dicts from our Analyzer
        with open(filename, "w") as f:
            json.dump(trades, f, indent=2, default=str)
    except Exception as e:
        print(f"❌ Error exporting trades: {e}")


def run_backtest(config_file: str = "config/config.json"):
    """
    Run backtest from JSON configuration file.
    This is the main function for running backtests.

    Args:
        config_file: Path to JSON configuration file
    """
    print("🚀 SMC Trading Engine - Backtest")
    print("=" * 50)

    # Check if config file exists
    if not os.path.exists(config_file):
        print(f"❌ Configuration file not found: {config_file}")
        print("💡 Creating default configuration file...")

        # Ensure config directory exists
        config_dir = os.path.dirname(config_file)
        if config_dir and not os.path.exists(config_dir):
            os.makedirs(config_dir)

        # Create default config
        default_config = {
            "name": "Default SMC Test",
            "description": "Default configuration for SMC strategy testing",
            "account": {"initial_capital": 10000, "risk_per_trade": 2.0, "max_drawdown": 15.0, "max_positions": 3, "leverage": 10.0},
            "trading": {"symbol": "BTC/USDT", "timeframes": ["4h", "15m"], "exchange": "binance", "slippage": 0.0001, "commission": 0.0004},
            "period": {"start_date": "2025-09-01", "end_date": "2025-10-20"},
            "strategy": {
                "name": "simplified_smc_strategy",
                "config": {
                    "high_timeframe": "4h",
                    "low_timeframe": "15m",
                    "min_zone_strength": 0.3,
                    "volume_threshold": 1.0,
                    "max_zones": 10,
                    "confluence_required": False,
                    "risk_reward_ratio": 2.0,
                },
            },
            "risk_management": {"min_risk_reward": 2.0, "trailing_stop_distance": 0.02},
            "logging": {
                "level": "INFO",
                "export_logs": True,
                "log_file": "results/backtest_logs.json",
                "detailed_signals": True,
                "detailed_trades": True,
                "market_analysis": True,
            },
            "output": {"save_results": True, "results_file": "results/backtest_results.json", "export_trades": True, "trades_file": "results/trades_history.json"},
        }

        with open(config_file, "w") as f:
            json.dump(default_config, f, indent=2)

        print(f"✅ Created default configuration: {config_file}")
        print("💡 You can edit this file to customize your backtest parameters")

    # Run the backtest
    engine, metrics = run_backtest_from_config(config_file, "Backtest")

    if engine and metrics:
        signals_generated = getattr(engine.strategy, "signals_generated", 0)
        signals_executed = getattr(engine.strategy, "signals_executed", 0)

        print(f"\n🎯 Backtest Results:")
        print(f"   Signals Generated: {signals_generated}")
        print(f"   Signals Executed: {signals_executed}")
        print(f"   Total Trades: {metrics.get('total_trades', 0)}")
        print(f"   Win Rate: {metrics.get('win_rate', 0):.1f}%")
        print(f"   Total PnL: ${metrics.get('total_pnl', 0):,.2f}")
        print(f"   Max Drawdown: {metrics.get('max_drawdown', 0):.1f}%")
        print(f"   Sharpe Ratio: {metrics.get('sharpe_ratio', 0):.2f}")

        if signals_generated > 0:
            print(f"✅ SUCCESS: Strategy generated {signals_generated} signals!")
        else:
            print(f"❌ ISSUE: No signals were generated")
            print("💡 Try adjusting strategy parameters in the configuration file")

    return engine, metrics


def run_live_trading(config_file_path: str = "config/live_config.json"):
    """Run live trading mode."""
    try:
        print("SMC Live Trading Bot (Backtrader)")
        print("=" * 50)
        
        # Load configuration
        config = load_config_from_json(config_file_path)
        if config is None:
            # Create default if not exists
             config = {
                "account": {"initial_capital": 1000.0, "risk_per_trade": 2.0},
                "trading": {"symbol": "BTC/USDT", "exchange": "binance", "sandbox": True}
             }
             print("⚠️  Config not found, using default.")

        # Create and start trading engine
        engine = BTLiveEngine(config)

        print("Starting live trading engine...")
        engine.run_live()

    except KeyboardInterrupt:
        print("\nTrading stopped by user")
    except Exception as e:
        print(f"❌ Error starting live trading: {e}")
        import traceback
        traceback.print_exc()


def run_tests():
    """Run test suite."""
    import subprocess

    print("🧪 Running SMC Trading Engine Tests...")
    print("=" * 50)

    # Run pytest with verbose output
    cmd = [sys.executable, "-m", "pytest", "tests/", "-v", "--tb=short", "--color=yes"]

    print(f"Running: {' '.join(cmd)}")
    print()

    try:
        result = subprocess.run(cmd, check=True)
        print("\n✅ All tests passed!")
        return 0
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Tests failed with exit code {e.returncode}")
        return e.returncode
    except Exception as e:
        print(f"\n❌ Error running tests: {e}")
        return 1


def show_help():
    """Show detailed help information."""
    print("📚 SMC Trading Engine Help")
    print("=" * 50)
    print()
    print("🔧 Backtest Commands:")
    print("  python main.py backtest                    # Run with default config")
    print("  python main.py backtest config/config.json  # Run with custom config")
    print()
    print("📈 Live Trading Commands:")
    print("  python main.py live                        # Start live trading")
    print("  python main.py live --config config/live_trading_config.json")
    print("  python main.py live --sandbox --symbol ETH/USDT")
    print()
    print("🧪 Testing Commands:")
    print("  python main.py test                        # Run all tests")
    print()
    print("📁 Project Structure:")
    print("  config/     - Configuration files")
    print("  engine/     - Core trading engine (includes SMC analysis)")
    print("  strategies/ - Trading strategies")
    print("  tests/      - Automated tests")
    print("  scripts/    - Additional utility scripts")


def main():
    """Main entry point with argument parsing."""
    parser = argparse.ArgumentParser(
        description="SMC Trading Engine - Main Entry Point",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py backtest                           # Run backtest with default config
  python main.py backtest config/my_config.json    # Run backtest with custom config
  python main.py live                              # Start live trading
  python main.py test                              # Run tests
  python main.py help                              # Show detailed help
        """,
    )

    parser.add_argument("command", choices=["backtest", "live", "test", "help"], help="Command to execute")

    parser.add_argument("config_file", nargs="?", default=None, help="Configuration file path")

    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose output")

    # Parse arguments
    args = parser.parse_args()

    if args.command == "backtest":
        print("🚀 SMC Trading Engine - Backtest")
        print("=" * 50)
        config_path = args.config_file or "config/backtest_config.json"
        run_backtest(config_path)

    elif args.command == "live":
        print("🚀 SMC Trading Engine - Live Trading")
        print("=" * 50)
        config_path = args.config_file or "config/live_config.json"
        run_live_trading(config_path)

    elif args.command == "test":
        print("🚀 SMC Trading Engine - Tests")
        print("=" * 50)
        run_tests()

    elif args.command == "help":
        show_help()

    else:
        parser.print_help()


if __name__ == "__main__":
    # If no arguments provided, show basic help
    if len(sys.argv) == 1:
        print("🚀 SMC Trading Engine")
        print("=" * 40)
        print("Available commands:")
        print("  backtest     - Run backtest")
        print("  live         - Start live trading")
        print("  test         - Run tests")
        print("  help         - Show detailed help")
        print()
        print("Examples:")
        print("  python main.py backtest")
        print("  python main.py backtest config/backtest_config.json")
        print("  python main.py live")
        print("  python main.py live config/live_config.json")
        print("  python main.py test")
        print("  python main.py help")
    else:
        main()
