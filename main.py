#!/usr/bin/env python3
"""
Backtrade Machine - Main Entry Point
This script provides easy access to all main functionality including backtesting, live trading, and testing.
"""

import json
import sys
import argparse
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from engine.logger import get_logger, setup_logging
from engine.bt_backtest_engine import BTBacktestEngine
from engine.bt_live_engine import BTLiveEngine
from strategies.bt_price_action import PriceActionStrategy

# Bootstrap logging for CLI usage
setup_logging(enable_ws=False)
logger = get_logger("main")


def create_default_config() -> Dict[str, Any]:
    """Create a default configuration for backtesting."""
    return {
        # Account settings
        "initial_capital": 10000,
        "risk_per_trade": 2.0,  # 2% risk per trade
        "max_drawdown": 15.0,   # 15% max drawdown
        "max_positions": 3,
        "leverage": 10.0,
        # Trading pair and timeframes
        "symbol": "BTC/USDT",
        "timeframes": ["4h"],
        "exchange": "binance",
        # Backtest period
        "start_date": "2023-01-01",
        "end_date": "2023-12-31",
        # Strategy settings
        "strategy": "bt_price_action",
        "strategy_config": {
            "trend_ema_period": 50,
            "rsi_period": 14,
            "risk_reward_ratio": 2.5,
        },
        # Risk management
        "min_risk_reward": 3.0,
        "log_level": "INFO",
    }


def _normalize_json_config(json_config: Dict[str, Any]) -> Dict[str, Any]:
    """Convert JSON config (nested or flat) to flat engine format."""
    strategy_conf = json_config.get("strategy", {})
    if isinstance(strategy_conf, str):
        strategy_name = strategy_conf
    else:
        strategy_name = strategy_conf.get("name", "") if strategy_conf else ""

    if not strategy_name:
        strategy_name = "bt_price_action"

    account = json_config.get("account", {})
    trading = json_config.get("trading", {})
    period = json_config.get("period", {})

    return {
        "initial_capital": account.get("initial_capital", json_config.get("initial_capital", 10000)),
        "commission": trading.get("commission", json_config.get("commission", 0.0004)),
        "symbol": trading.get("symbol", json_config.get("symbol", "BTC/USDT")),
        "timeframes": trading.get("timeframes", json_config.get("timeframes", ["4h", "15m"])),
        "exchange": trading.get("exchange", json_config.get("exchange", "binance")),
        "leverage": json_config.get("leverage", account.get("leverage", 10.0)),
        "start_date": period.get("start_date", json_config.get("start_date", "2023-01-01")),
        "end_date": period.get("end_date", json_config.get("end_date", "2023-12-31")),
        "strategy": strategy_name,
        "strategy_config": (
            strategy_conf.get("config", {}) if isinstance(strategy_conf, dict) else
            json_config.get("strategy_config", {})
        ),
    }


def load_config_from_db(config_type: str = "backtest") -> Dict[str, Any] | None:
    """Load configuration from MongoDB. Returns None if DB unavailable or config empty."""
    try:
        from db import is_database_available
        from db.repositories import AppConfigRepository
        if not is_database_available():
            return None
        repo = AppConfigRepository()
        if config_type == "backtest":
            raw = repo.get_backtest_config()
        else:
            raw = repo.get_live_config()
        if not raw:
            return None
        if config_type == "backtest":
            return _normalize_json_config(raw)
        return _normalize_live_config(raw)
    except Exception as e:
        logger.debug(f"Could not load config from DB: {e}")
        return None


def _normalize_live_config(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize live config from DB (nested or flat) to engine format."""
    account = raw.get("account", {})
    trading = raw.get("trading", {})
    base = _normalize_json_config(raw)
    base["sandbox"] = raw.get("sandbox", trading.get("sandbox", True))
    base["apiKey"] = raw.get("apiKey", trading.get("apiKey", ""))
    base["secret"] = raw.get("secret", trading.get("secret", ""))
    base["poll_interval"] = raw.get("poll_interval", 60)
    return base


def run_backtest_from_config(config: Dict[str, Any], config_name: str = "Backtest"):
    """
    Run backtest from configuration dict.

    Returns:
        Tuple of (engine, metrics) or (None, None) if failed
    """
    logger.info(f"\n{'='*60}")
    logger.info(f"RUNNING BACKTEST: {config_name}")
    logger.info(f"{'='*60}")

    logger.info("📊 Configuration Summary:")
    logger.info(f"   Strategy: {config['strategy']}")
    logger.info(f"   Symbol: {config['symbol']}")
    logger.info(f"   Period: {config['start_date']} to {config['end_date']}")
    logger.info(f"   Capital: ${config['initial_capital']:,}")

    try:
        engine = BTBacktestEngine(config)
        engine.add_strategy(PriceActionStrategy, **config.get('strategy_config', {}))
        metrics = engine.run_backtest()

        if config.get("save_results", False) or config.get("export_trades", False):
            run_id = f"backtest_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            full_metrics = _build_full_metrics(metrics, engine, config)
            _save_backtest(run_id, full_metrics)
            logger.info(f"📊 Results saved (run_id: {run_id})")

        return engine, metrics

    except Exception as e:
        logger.error(f"❌ Error running backtest: {e}", exc_info=True)
        return None, None


def _build_full_metrics(
    metrics: Dict[str, Any], engine: Any, config: Dict[str, Any]
) -> Dict[str, Any]:
    """Build full metrics dict with trades and equity curve for DB storage."""
    from datetime import datetime as dt

    trades_data = []
    for i, trade in enumerate(engine.closed_trades):
        entry_time = trade.get("entry_time")
        exit_time = trade.get("exit_time")
        duration_str = None
        if exit_time and entry_time:
            try:
                et = dt.fromisoformat(entry_time) if isinstance(entry_time, str) else entry_time
                xt = dt.fromisoformat(exit_time) if isinstance(exit_time, str) else exit_time
                duration_str = str(xt - et).replace("0 days ", "")
            except (ValueError, TypeError):
                pass
        trades_data.append({
            "id": i + 1,
            "direction": trade.get("direction"),
            "entry_price": trade.get("entry_price"),
            "exit_price": trade.get("exit_price"),
            "size": trade.get("size"),
            "pnl": trade.get("realized_pnl"),
            "entry_time": entry_time,
            "exit_time": exit_time,
            "duration": duration_str,
            "realized_pnl": trade.get("realized_pnl"),
            "exit_reason": trade.get("exit_reason", "Unknown"),
            "reason": trade.get("reason", "Unknown"),
            "narrative": trade.get("narrative"),
            "sl_calculation": trade.get("sl_calculation"),
            "tp_calculation": trade.get("tp_calculation"),
            "sl_history": trade.get("sl_history", []),
            "entry_context": trade.get("entry_context"),
            "exit_context": trade.get("exit_context"),
        })
    equity_data = []
    for point in getattr(engine, "equity_curve", []):
        ts = point.get("timestamp")
        equity_data.append({
            "date": ts.isoformat() if hasattr(ts, "isoformat") else str(ts),
            "equity": point.get("equity", 0),
        })
    engine_config = {
        "initial_capital": config.get("initial_capital", 10000),
        "risk_per_trade": config.get("risk_per_trade", 2.0),
        "max_drawdown": config.get("max_drawdown", 15.0),
        "max_positions": config.get("max_positions", 3),
        "leverage": config.get("leverage", 10.0),
        "symbol": config.get("symbol", "BTC/USDT"),
        "timeframes": config.get("timeframes", ["4h", "15m"]),
        "exchange": config.get("exchange", "binance"),
        "exchange_type": config.get("exchange_type", "future"),
        "start_date": config.get("start_date", "2023-01-01"),
        "end_date": config.get("end_date", "2023-12-31"),
        "strategy": config.get("strategy", "bt_price_action"),
        "strategy_config": config.get("strategy_config", {}),
    }
    return {
        **metrics,
        "equity_curve": equity_data,
        "trades": trades_data,
        "configuration": engine_config,
        "strategy": engine_config.get("strategy", "Unknown"),
        "logs": [],
    }


def _save_backtest(run_id: str, metrics: Dict[str, Any]) -> None:
    """Save backtest results to database."""
    from db import is_database_available
    from db.repositories import BacktestRepository
    if not is_database_available():
        raise RuntimeError("MongoDB required. Set MONGODB_URI and ensure MongoDB is running.")
    BacktestRepository().save(run_id, metrics)


def run_backtest():
    """Run backtest. Config from MongoDB only."""
    logger.info("🚀 Backtrade Machine - Backtest")
    logger.info("=" * 50)

    config = load_config_from_db("backtest")
    if config is None:
        config = _normalize_json_config(create_default_config())
        logger.info("📋 Using default config (DB empty)")
    else:
        logger.info("📋 Config loaded from database")

    engine, metrics = run_backtest_from_config(config, "Backtest")

    if engine and metrics:
        signals_generated = getattr(engine.strategy, "signals_generated", 0)
        signals_executed = getattr(engine.strategy, "signals_executed", 0)

        logger.info("\n🎯 Backtest Results:")
        logger.info(f"   Signals Generated: {signals_generated}")
        logger.info(f"   Signals Executed: {signals_executed}")
        logger.info(f"   Total Trades: {metrics.get('total_trades', 0)}")
        logger.info(f"   Win Rate: {metrics.get('win_rate', 0):.1f}%")
        logger.info(f"   Total PnL: ${metrics.get('total_pnl', 0):,.2f}")
        logger.info(f"   Max Drawdown: {metrics.get('max_drawdown', 0):.1f}%")
        logger.info(f"   Sharpe Ratio: {metrics.get('sharpe_ratio', 0):.2f}")

        if signals_generated > 0:
            logger.info(f"✅ SUCCESS: Strategy generated {signals_generated} signals!")
        else:
            logger.warning("❌ ISSUE: No signals were generated")
            logger.info("💡 Try adjusting strategy parameters in the dashboard (MongoDB config)")

    return engine, metrics


def run_live_trading():
    """Run live trading. Config from MongoDB only."""
    try:
        logger.info("Backtrade Machine - Live Trading")
        logger.info("=" * 50)

        config = load_config_from_db("live")

        if config is None:
            config = _normalize_live_config({
                "account": {"initial_capital": 1000.0, "risk_per_trade": 2.0},
                "trading": {"symbol": "BTC/USDT", "exchange": "binance", "sandbox": True},
            })
            logger.warning("⚠️  Config not found, using default.")

        engine = BTLiveEngine(config)
        logger.info("Starting live trading engine...")
        engine.run_live()

    except KeyboardInterrupt:
        logger.info("\nTrading stopped by user")
    except Exception as e:
        logger.error(f"❌ Error starting live trading: {e}", exc_info=True)


def run_tests():
    """Run test suite."""
    import subprocess

    logger.info("🧪 Running Backtrade Machine Tests...")
    logger.info("=" * 50)

    cmd = [sys.executable, "-m", "pytest", "tests/", "-v", "--tb=short", "--color=yes"]
    logger.info(f"Running: {' '.join(cmd)}")

    try:
        subprocess.run(cmd, check=True)
        logger.info("\n✅ All tests passed!")
        return 0
    except subprocess.CalledProcessError as e:
        logger.error(f"\n❌ Tests failed with exit code {e.returncode}")
        return e.returncode
    except Exception as e:
        logger.error(f"\n❌ Error running tests: {e}")
        return 1


def show_help():
    """Show detailed help information."""
    # Help text is intentionally printed to stdout for CLI readability
    print("📚 Backtrade Machine Help")
    print("=" * 50)
    print()
    print("🔧 Backtest Commands:")
    print("  python main.py backtest                    # Config from MongoDB")
    print()
    print("📈 Live Trading Commands:")
    print("  python main.py live                        # Config from MongoDB")
    print()
    print("🧪 Testing Commands:")
    print("  python main.py test                        # Run all tests")
    print()
    print("📁 Project Structure:")
    print("  engine/     - Core trading engine")
    print("  strategies/ - Trading strategies")
    print("  tests/      - Automated tests")
    print("  scripts/    - Additional utility scripts")


def main():
    """Main entry point with argument parsing."""
    parser = argparse.ArgumentParser(
        description="Backtrade Machine - Main Entry Point",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py backtest    # Config from MongoDB
  python main.py live       # Config from MongoDB
  python main.py test       # Run tests
  python main.py help       # Show detailed help
        """,
    )

    parser.add_argument("command", choices=["backtest", "live", "test", "help"], help="Command to execute")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose output")

    args = parser.parse_args()

    if args.command == "backtest":
        run_backtest()

    elif args.command == "live":
        run_live_trading()

    elif args.command == "test":
        run_tests()

    elif args.command == "help":
        show_help()

    else:
        parser.print_help()


if __name__ == "__main__":
    if len(sys.argv) == 1:
        # Intentionally print to stdout for clean CLI banner
        print("🚀 Backtrade Machine")
        print("=" * 40)
        print("Available commands:")
        print("  backtest     - Run backtest")
        print("  live         - Start live trading")
        print("  test         - Run tests")
        print("  help         - Show detailed help")
        print()
        print("Examples:")
        print("  python main.py backtest")
        print("  python main.py live")
        print("  python main.py test")
    else:
        main()
