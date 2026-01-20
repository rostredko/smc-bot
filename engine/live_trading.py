"""
Live Trading module for real-time trading and paper trading.
Handles order placement, position management, and account monitoring.
"""

import os
import json
import ccxt
from typing import Dict, List, Any


@dataclass
class LiveTradingConfig:
    """Configuration for live trading."""

    # Exchange settings
    exchange_name: str = "binance"
    api_key: str = ""
    secret: str = ""
    sandbox: bool = True  # Use testnet by default

    # Trading settings
    symbol: str = "BTC/USDT"
    timeframes: List[str] = None
    initial_capital: float = 1000.0
    risk_per_trade: float = 2.0
    max_drawdown: float = 15.0
    max_positions: int = 3  # Legacy parameter - positions now managed by risk/reward ratio
    leverage: float = 10.0

    # Strategy settings
    strategy_name: str = "smc_strategy"
    strategy_config: Dict[str, Any] = None

    # Execution settings
    poll_interval: int = 60  # seconds
    slippage: float = 0.0001
    commission: float = 0.0004

    def __post_init__(self):
        if self.timeframes is None:
            self.timeframes = ["4h", "15m"]
        if self.strategy_config is None:
            self.strategy_config = {}  # Empty default


class LiveTradingEngine:
    """
    Live trading engine that executes trades in real-time using a loaded strategy.
    """

    def __init__(self, config: LiveTradingConfig):
        """
        Initialize live trading engine.

        Args:
            config: Live trading configuration
        """
        self.config = config
        self.logger = TradingLogger("live_trading")

        # Initialize exchange
        self._init_exchange()

        # Initialize components
        self.risk_manager = RiskManager(
            initial_capital=config.initial_capital,
            risk_per_trade=config.risk_per_trade,
            max_drawdown=config.max_drawdown,
            max_positions=config.max_positions,
            leverage=config.leverage,
        )

        # Dynamic Strategy Loading
        try:
            strategy_module = __import__(f"strategies.{config.strategy_name}", fromlist=["Strategy"])
            strategy_class = None
            for class_name in ["Strategy", "SMCStrategy", "SimpleTestStrategy", config.strategy_name.title() + "Strategy", "PriceActionStrategy"]:
                if hasattr(strategy_module, class_name):
                    strategy_class = getattr(strategy_module, class_name)
                    break
            
            if strategy_class is None:
                 raise ValueError(f"Could not find strategy class in {config.strategy_name}")
                 
            self.strategy = strategy_class(config.strategy_config)
        except Exception as e:
            self.logger.error(f"Failed to load strategy {config.strategy_name}: {e}")
            raise

        # Trading state
        self.is_running = False
        self.positions: Dict[int, Position] = {}
        self.position_counter = 0
        self.last_update_time = None

        # Performance tracking
        self.total_trades = 0
        self.winning_trades = 0
        self.total_pnl = 0.0

        self.logger.info("Live trading engine initialized")

    def _init_exchange(self):
        """Initialize exchange connection."""
        try:
            exchange_class = getattr(ccxt, self.config.exchange_name)

            exchange_config = {
                "apiKey": self.config.api_key,
                "secret": self.config.secret,
                "enableRateLimit": True,
                "options": {"defaultType": "future"},  # Use futures for leverage
            }

            if self.config.sandbox:
                exchange_config["sandbox"] = True

            self.exchange = exchange_class(exchange_config)

            # Test connection
            self.exchange.load_markets()
            self.logger.info(f"Connected to {self.config.exchange_name} exchange")

        except Exception as e:
            self.logger.error(f"Failed to initialize exchange: {e}")
            raise

    def start_trading(self):
        """Start live trading loop."""
        self.logger.info("Starting live trading...")
        self.is_running = True

        try:
            while self.is_running:
                self._trading_cycle()
                time.sleep(self.config.poll_interval)

        except KeyboardInterrupt:
            self.logger.info("Trading stopped by user")
        except Exception as e:
            self.logger.error(f"Trading error: {e}")
        finally:
            self.stop_trading()

    def stop_trading(self):
        """Stop live trading and close all positions."""
        self.logger.info("Stopping live trading...")
        self.is_running = False

        # Close all open positions
        for position in list(self.positions.values()):
            self._close_position(position, "Engine stopped")

        self.logger.info("Live trading stopped")

    def _trading_cycle(self):
        """Execute one trading cycle."""
        try:
            # Update market data
            market_data = self._fetch_market_data()
            if not market_data:
                return

            # Update positions
            self._update_positions(market_data)

            # Generate signals
            signals = self.strategy.generate_signals(market_data)

            # Execute new trades
            for signal in signals:
                if self._can_open_position():
                    self._execute_signal(signal, market_data)

            # Log status
            self._log_status()

        except Exception as e:
            self.logger.error(f"Trading cycle error: {e}")

    def _fetch_market_data(self) -> Optional[Dict[str, pd.DataFrame]]:
        """Fetch market data for all timeframes."""
        market_data = {}

        try:
            for timeframe in self.config.timeframes:
                # Fetch OHLCV data
                ohlcv = self.exchange.fetch_ohlcv(self.config.symbol, timeframe, limit=500)

                # Convert to DataFrame
                df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
                df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
                df.set_index("timestamp", inplace=True)

                market_data[timeframe] = df

            self.last_update_time = datetime.now()
            return market_data

        except Exception as e:
            self.logger.error(f"Failed to fetch market data: {e}")
            return None

    def _update_positions(self, market_data: Dict[str, pd.DataFrame]):
        """Update all open positions."""
        current_price = market_data[self.config.timeframes[-1]]["close"].iloc[-1]

        positions_to_close = []

        for position in self.positions.values():
            # Update unrealized PnL
            position.update_price(current_price)

            # Check stop loss and take profit
            if self._should_close_position(position, current_price):
                positions_to_close.append(position)

        # Close positions that hit SL/TP
        for position in positions_to_close:
            self._close_position(position, "SL/TP hit")

    def _should_close_position(self, position: Position, current_price: float) -> bool:
        """Check if position should be closed."""
        if position.direction == "LONG":
            return current_price <= position.stop_loss or current_price >= position.take_profit
        else:  # SHORT
            return current_price >= position.stop_loss or current_price <= position.take_profit

    def _can_open_position(self) -> bool:
        """Check if we can open a new position."""
        can_open, reason = self.risk_manager.can_open_position()
        return can_open

    def _execute_signal(self, signal: Dict[str, Any], market_data: Dict[str, pd.DataFrame]):
        """Execute a trading signal."""
        try:
            current_price = market_data[self.config.timeframes[-1]]["close"].iloc[-1]

            # Calculate position size
            position_size = self.risk_manager.calculate_position_size(current_price, signal["stop_loss"], signal["direction"])

            if position_size <= 0:
                self.logger.warning("Position size too small, skipping signal")
                return

            # Create position
            position = Position(
                id=self.position_counter,
                entry_price=current_price,
                size=position_size,
                stop_loss=signal["stop_loss"],
                take_profit=signal["take_profit"],
                reason=signal["reason"],
                direction=signal["direction"],
            )

            # Execute trade (paper trading for now)
            self._execute_trade(position)

            # Add to positions
            self.positions[self.position_counter] = position
            self.position_counter += 1
            self.total_trades += 1

            self.logger.info(f"Opened {signal['direction']} position: {position}")

        except Exception as e:
            self.logger.error(f"Failed to execute signal: {e}")

    def _execute_trade(self, position: Position):
        """Execute actual trade on exchange (currently paper trading)."""
        # TODO: Implement actual trade execution
        # For now, just log the trade
        self.logger.info(f"PAPER TRADE: {position.direction} {position.size} @ {position.entry_price}")

    def _close_position(self, position: Position, reason: str):
        """Close a position."""
        try:
            # Calculate final PnL
            current_price = self._get_current_price()
            final_pnl = position.get_unrealized_pnl(current_price)

            # Update statistics
            self.total_pnl += final_pnl
            if final_pnl > 0:
                self.winning_trades += 1

            # Execute close trade (paper trading for now)
            self.logger.info(f"PAPER TRADE CLOSE: {position.direction} @ {current_price}, PnL: {final_pnl:.2f}")

            # Remove from positions
            del self.positions[position.id]

            # Update strategy
            self.strategy.on_trade_exit(position)

            self.logger.info(f"Closed position {position.id}: {reason}, PnL: {final_pnl:.2f}")

        except Exception as e:
            self.logger.error(f"Failed to close position: {e}")

    def _get_current_price(self) -> float:
        """Get current market price."""
        try:
            ticker = self.exchange.fetch_ticker(self.config.symbol)
            return ticker["last"]
        except Exception as e:
            self.logger.error(f"Failed to get current price: {e}")
            return 0.0

    def _log_status(self):
        """Log current trading status."""
        if not self.last_update_time:
            return

        win_rate = (self.winning_trades / self.total_trades * 100) if self.total_trades > 0 else 0

        status = {
            "timestamp": self.last_update_time.isoformat(),
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "win_rate": win_rate,
            "total_pnl": self.total_pnl,
            "open_positions": len(self.positions),
            "balance": self.risk_manager.get_account_balance(),
        }

        self.logger.info(f"Status: {status}")

    def get_performance_stats(self) -> Dict[str, Any]:
        """Get performance statistics."""
        win_rate = (self.winning_trades / self.total_trades * 100) if self.total_trades > 0 else 0

        return {
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "win_rate": win_rate,
            "total_pnl": self.total_pnl,
            "open_positions": len(self.positions),
            "account_balance": self.risk_manager.get_account_balance(),
            "max_drawdown": self.risk_manager.get_max_drawdown(),
            "is_running": self.is_running,
        }


def create_live_trading_config_from_file(config_file: str) -> LiveTradingConfig:
    """Create live trading config from JSON file."""
    with open(config_file, "r") as f:
        config_data = json.load(f)

    return LiveTradingConfig(
        exchange_name=config_data.get("exchange", "binance"),
        api_key=config_data.get("apiKey", ""),
        secret=config_data.get("secret", ""),
        sandbox=config_data.get("sandbox", True),
        symbol=config_data.get("symbol", "BTC/USDT"),
        timeframes=config_data.get("timeframes", ["4h", "15m"]),
        initial_capital=config_data.get("initial_capital", 1000.0),
        risk_per_trade=config_data.get("risk_per_trade", 2.0),
        max_drawdown=config_data.get("max_drawdown", 15.0),
        max_positions=config_data.get("max_positions", 3),
        leverage=config_data.get("leverage", 10.0),
        poll_interval=config_data.get("poll_interval", 60),
        strategy_config=config_data.get("strategy_config", {}),
    )


# Example usage
if __name__ == "__main__":
    # Create configuration
    config = LiveTradingConfig(
        api_key="YOUR_API_KEY",
        secret="YOUR_SECRET",
        sandbox=True,  # Use testnet
        symbol="BTC/USDT",
        initial_capital=1000.0,
        risk_per_trade=2.0,
        poll_interval=60,
        strategy_name="smc_strategy"
    )

    # Create and start trading engine
    engine = LiveTradingEngine(config)

    try:
        engine.start_trading()
    except KeyboardInterrupt:
        print("Trading stopped by user")
    finally:
        stats = engine.get_performance_stats()
        print(f"Final stats: {stats}")
