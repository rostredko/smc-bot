"""
FastAPI Web Server for SMC Trading Engine.
Provides REST API endpoints for web dashboard integration.
"""

import os
import json
import asyncio
import sys
import threading
from datetime import datetime
from typing import Dict, List, Optional, Any
from pathlib import Path

# Add parent directory to path to import engine modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, HTTPException, BackgroundTasks, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from engine.backtest_engine import BacktestEngine
from strategies.smc_strategy import SMCStrategy
from strategies.simple_test_strategy import SimpleTestStrategy


# Store original stdout/stderr at module level for use in broadcast functions
original_stdout = sys.stdout
original_stderr = sys.stderr

# Configuration - Use absolute paths for cross-platform compatibility
BASE_DIR = Path(__file__).parent.parent.absolute()
DATA_DIR = str(BASE_DIR / "data_cache")
RESULTS_DIR = str(BASE_DIR / "results")

# Ensure directories exist
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(RESULTS_DIR, exist_ok=True)

# FastAPI app
app = FastAPI(
    title="SMC Trading Engine API",
    description="REST API for SMC Trading Engine",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
if os.path.exists("dist"):
    app.mount("/static", StaticFiles(directory="dist"), name="static")


# Pydantic models
class BacktestConfig(BaseModel):
    initial_capital: float = 10000
    risk_per_trade: float = 2.0
    max_drawdown: float = 15.0
    max_positions: int = 3
    leverage: float = 10.0
    symbol: str = "BTC/USDT"
    timeframes: List[str] = ["4h", "15m"]
    start_date: str = "2023-01-01"
    end_date: str = "2023-12-31"
    confluence_required: str = "false"
    strategy: str = "smc_strategy"
    strategy_config: Dict[str, Any] = {}
    min_risk_reward: float = 2.0
    trailing_stop_distance: float = 0.02
    max_total_risk_percent: float = 15.0
    dynamic_position_sizing: bool = True


class BacktestRequest(BaseModel):
    config: BacktestConfig
    run_id: Optional[str] = None


class BacktestStatus(BaseModel):
    run_id: str
    status: str  # "running", "completed", "failed", "cancelled"
    progress: float = 0.0
    message: str = ""
    results: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    should_cancel: bool = False  # Flag to signal cancellation
    engine: Optional[Any] = None  # Reference to BacktestEngine for cancellation
    
    class Config:
        arbitrary_types_allowed = True


# Global state for running backtests
running_backtests: Dict[str, BacktestStatus] = {}

# WebSocket connections - for real-time message broadcasting
active_connections: List[WebSocket] = []
connection_lock = threading.Lock()

# Cache for strategy schemas to avoid re-importing
strategy_schema_cache: Dict[str, Dict[str, Any]] = {}

# Queue for log messages from background tasks
import queue
log_queue = queue.Queue()


async def broadcast_from_queue():
    """Periodically broadcast queued messages to WebSocket clients."""
    iteration = 0
    while True:
        iteration += 1
        try:
            # Try to get a message from the queue (non-blocking)
            messages_sent = 0
            while True:
                try:
                    message = log_queue.get_nowait()
                    # Broadcast to all connected clients
                    with connection_lock:
                        connections_copy = active_connections.copy()
                    
                    if not connections_copy:
                        continue  # No clients connected, skip
                    
                    for connection in connections_copy:
                        try:
                            await connection.send_text(message)
                            messages_sent += 1
                        except Exception as e:
                            # Silently remove dead connections
                            with connection_lock:
                                if connection in active_connections:
                                    active_connections.remove(connection)
                except queue.Empty:
                    break
            
        except Exception as e:
            pass  # Silently ignore errors
        
        # Wait before checking again
        await asyncio.sleep(0.05)


def load_available_strategies():
    """Load available strategies from strategies directory."""
    strategies = []
    strategies_dir = BASE_DIR / "strategies"
    
    if strategies_dir.exists():
        for file in strategies_dir.glob("*.py"):
            if file.name != "__init__.py" and file.name != "base_strategy.py":
                strategy_name = file.stem
                # Get schema (will be cached after first call)
                config_schema = get_strategy_config_schema(strategy_name)
                strategies.append({
                    "name": strategy_name,
                    "display_name": strategy_name.replace("_", " ").title(),
                    "description": f"{strategy_name} strategy",
                    "config_schema": config_schema
                })
    
    return strategies


def get_strategy_config_schema(strategy_name: str):
    """Get configuration schema for a strategy - returns hardcoded schemas."""
    if strategy_name in strategy_schema_cache:
        return strategy_schema_cache[strategy_name]
    
    # Return hardcoded schemas for known strategies without importing
    default_schemas = {
        "smc_strategy": {
            # Core
            "mode": {"type": "string", "default": "spot"},
            "allow_short": {"type": "boolean", "default": False},
            # Timeframes
            "high_timeframe": {"type": "string", "default": "4h"},
            "low_timeframe": {"type": "string", "default": "15m"},
            # Risk
            "risk_per_trade_pct": {"type": "number", "default": 0.3},
            "max_concurrent_positions": {"type": "number", "default": 3},
            "min_required_rr": {"type": "number", "default": 2.0},
            "max_stop_distance_pct": {"type": "number", "default": 0.04},
            # Volatility
            "volatility_filter_enabled": {"type": "boolean", "default": True},
            "atr_period": {"type": "number", "default": 14},
            "atr_percentile_min": {"type": "number", "default": 30},
            "atr_percentile_max": {"type": "number", "default": 70},
            "sl_atr_multiplier": {"type": "number", "default": 2.0},
            "min_signal_confidence": {"type": "number", "default": 0.4},
            # Technical
            "ema_filter_period": {"type": "number", "default": 50},
            "rsi_period": {"type": "number", "default": 14},
            "min_rsi_long": {"type": "number", "default": 35},
            "max_rsi_long": {"type": "number", "default": 70},
            "volume_threshold": {"type": "number", "default": 1.3},
            # Partial TPs
            "use_partial_tp": {"type": "boolean", "default": True},
            "tp1_r": {"type": "number", "default": 1.0},
            "tp1_pct": {"type": "number", "default": 0.5},
            "tp2_r": {"type": "number", "default": 2.0},
            "tp2_pct": {"type": "number", "default": 0.3},
            "runner_pct": {"type": "number", "default": 0.2},
            # Exit Management
            "trailing_stop_enabled": {"type": "boolean", "default": True},
            "trail_start": {"type": "number", "default": 1.5},
            "trail_step": {"type": "number", "default": 0.3},
            "breakeven_move_enabled": {"type": "boolean", "default": True},
            # Market Structure
            "require_structure_confirmation": {"type": "boolean", "default": True},
            "support_level_lookback_bars": {"type": "number", "default": 20},
            # Cooldown & Psychology
            "cooldown_after_loss_bars": {"type": "number", "default": 10},
            "reduce_risk_after_loss": {"type": "boolean", "default": True},
            "risk_reduction_after_loss": {"type": "number", "default": 0.6},
            # Exchange
            "min_notional": {"type": "number", "default": 10.0},
            "taker_fee": {"type": "number", "default": 0.0004},
            "slippage_bp": {"type": "number", "default": 2},
        },
        "simple_test_strategy": {
            "threshold": {"type": "number", "default": 0.5},
            "use_volume": {"type": "boolean", "default": False},
            "ema_period": {"type": "number", "default": 20},
            "rsi_period": {"type": "number", "default": 14},
            "rsi_threshold": {"type": "number", "default": 30}
        },
        "price_action_strategy": {
            "primary_timeframe": {"type": "string", "default": "4h"},
            "min_range_factor": {"type": "number", "default": 0.8},
            "use_trend_filter": {"type": "boolean", "default": True},
            "trend_ema_period": {"type": "number", "default": 50},
            
            "use_rsi_filter": {"type": "boolean", "default": True},
            "rsi_period": {"type": "number", "default": 14},
            "rsi_overbought": {"type": "number", "default": 70},
            "rsi_oversold": {"type": "number", "default": 30},

            "risk_reward_ratio": {"type": "number", "default": 2.5},
            "sl_buffer_atr": {"type": "number", "default": 0.5},
            "min_wick_to_range": {"type": "number", "default": 0.6},
            "max_body_to_range": {"type": "number", "default": 0.3}
        }
    }
    
    schema = default_schemas.get(strategy_name, {})
    strategy_schema_cache[strategy_name] = schema
    return schema


@app.on_event("startup")
async def startup_event():
    """Start background task to broadcast queued messages."""
    asyncio.create_task(broadcast_from_queue())


@app.get("/")
async def root():
    """Serve the main dashboard page."""
    if os.path.exists("dist/index.html"):
        return FileResponse("dist/index.html")
    else:
        return {"message": "SMC Trading Engine API", "version": "1.0.0", "error": "Frontend not built. Run 'npm run build' first."}


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


@app.get("/strategies")
async def get_strategies():
    """Get available strategies."""
    import time
    start = time.time()
    print(f"[BACKEND] Getting strategies list...", flush=True)
    strategies = load_available_strategies()
    elapsed = time.time() - start
    print(f"[BACKEND] Strategies loaded in {elapsed:.3f}s: {[s['name'] for s in strategies]}", flush=True)
    return {"strategies": strategies}


@app.get("/config")
async def get_config():
    """Get current configuration in flat format for frontend."""
    config_path = BASE_DIR / "config" / "backtest_config.json"
    if config_path.exists():
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        # Flatten the config structure for frontend
        flat_config = {
            "initial_capital": config.get("account", {}).get("initial_capital", 10000),
            "risk_per_trade": config.get("account", {}).get("risk_per_trade", 2.0),
            "max_drawdown": config.get("account", {}).get("max_drawdown", 15.0),
            "max_positions": config.get("account", {}).get("max_positions", 3),
            "leverage": config.get("account", {}).get("leverage", 10.0),
            "symbol": config.get("trading", {}).get("symbol", "BTC/USDT"),
            "timeframes": config.get("trading", {}).get("timeframes", ["4h", "15m"]),
            "start_date": config.get("period", {}).get("start_date", "2023-01-01"),
            "end_date": config.get("period", {}).get("end_date", "2023-12-31"),
            "strategy": config.get("strategy", {}).get("name", "smc_strategy")
        }
        return flat_config
    return {}


@app.post("/config")
async def update_config(config: Dict[str, Any]):
    """Update configuration."""
    config_path = BASE_DIR / "config" / "backtest_config.json"
    
    # Load existing config to preserve structure
    existing_config = {}
    if config_path.exists():
        with open(config_path, 'r') as f:
            existing_config = json.load(f)
    
    # Update the config with new values while preserving structure
    if "account" not in existing_config:
        existing_config["account"] = {}
    if "trading" not in existing_config:
        existing_config["trading"] = {}
    if "period" not in existing_config:
        existing_config["period"] = {}
    if "strategy" not in existing_config:
        existing_config["strategy"] = {}
    
    # Update account settings
    if "initial_capital" in config:
        existing_config["account"]["initial_capital"] = config["initial_capital"]
    if "risk_per_trade" in config:
        existing_config["account"]["risk_per_trade"] = config["risk_per_trade"]
    if "max_drawdown" in config:
        existing_config["account"]["max_drawdown"] = config["max_drawdown"]
    if "max_positions" in config:
        existing_config["account"]["max_positions"] = config["max_positions"]
    if "leverage" in config:
        existing_config["account"]["leverage"] = config["leverage"]
    
    # Update trading settings
    if "symbol" in config:
        existing_config["trading"]["symbol"] = config["symbol"]
    if "timeframes" in config:
        existing_config["trading"]["timeframes"] = config["timeframes"]
    
    # Update period settings
    if "start_date" in config:
        existing_config["period"]["start_date"] = config["start_date"]
    if "end_date" in config:
        existing_config["period"]["end_date"] = config["end_date"]
    
    # Update strategy settings
    if "strategy" in config:
        existing_config["strategy"]["name"] = config["strategy"]
    
    # Save updated config
    with open(config_path, 'w') as f:
        json.dump(existing_config, f, indent=2)
    
    return {"message": "Configuration updated"}


@app.post("/backtest/start")
async def start_backtest(request: BacktestRequest, background_tasks: BackgroundTasks):
    """Start a new backtest."""
    run_id = request.run_id or f"backtest_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    # Check if already running
    if run_id in running_backtests:
        raise HTTPException(status_code=400, detail=f"Backtest {run_id} is already running")
    
    # Initialize status
    running_backtests[run_id] = BacktestStatus(
        run_id=run_id,
        status="running",
        progress=0.0,
        message="Starting backtest..."
    )
    
    # Start background task
    background_tasks.add_task(run_backtest_task, run_id, request.config.dict())
    
    return {"run_id": run_id, "status": "started"}


@app.get("/backtest/status/{run_id}")
async def get_backtest_status(run_id: str):
    """Get backtest status."""
    if run_id not in running_backtests:
        raise HTTPException(status_code=404, detail="Backtest not found")
    
    status = running_backtests[run_id]
    # Return status without engine field (which is not serializable)
    return {
        "run_id": status.run_id,
        "status": status.status,
        "progress": status.progress,
        "message": status.message,
        "results": status.results,
        "error": status.error,
        "should_cancel": status.should_cancel
    }


@app.get("/backtest/results/{run_id}")
async def get_backtest_results(run_id: str):
    """Get backtest results."""
    if run_id not in running_backtests:
        raise HTTPException(status_code=404, detail="Backtest not found")
    
    status = running_backtests[run_id]
    if status.status != "completed":
        raise HTTPException(status_code=400, detail="Backtest not completed")
    
    return status.results


@app.get("/results")
async def get_results():
    """Get all backtest results."""
    results = []
    
    if os.path.exists(RESULTS_DIR):
        for name in os.listdir(RESULTS_DIR):
            if name.endswith(".json"):
                results.append(name)
    
    return {"results": sorted(results)}


@app.get("/results/{filename}")
async def get_result_file(filename: str):
    """Get specific result file."""
    file_path = os.path.join(RESULTS_DIR, filename)
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Result file not found")
    
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading file: {str(e)}")


@app.delete("/backtest/{run_id}")
async def cancel_backtest(run_id: str):
    """Cancel a running backtest."""
    if run_id not in running_backtests:
        raise HTTPException(status_code=404, detail="Backtest not found")
    
    status = running_backtests[run_id]
    if status.status == "running":
        status.should_cancel = True  # Set flag to signal cancellation
        # Also set the flag on the engine itself for graceful shutdown
        if status.engine:
            status.engine.should_cancel = True
        status.message = "Cancellation requested..."
    
    return {"message": "Backtest cancellation requested"}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time console output."""
    await websocket.accept()
    
    with connection_lock:
        active_connections.append(websocket)
    
    try:
        # Keep the connection open
        while True:
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        with connection_lock:
            if websocket in active_connections:
                active_connections.remove(websocket)


async def broadcast_message(message: str):
    """Broadcast message to all connected WebSocket clients."""
    # Make a copy of connections to avoid iteration issues
    with connection_lock:
        connections_copy = active_connections.copy()
    
    for connection in connections_copy:
        try:
            await connection.send_text(message)
        except Exception as e:
            # Silently remove dead connections
            with connection_lock:
                if connection in active_connections:
                    active_connections.remove(connection)


async def run_backtest_task(run_id: str, config: Dict[str, Any]):
    """Background task to run backtest."""
    import io
    import contextlib
    
    try:
        # Update status
        running_backtests[run_id].message = "Initializing engine..."
        running_backtests[run_id].progress = 10.0
        await broadcast_message(f"[{run_id}] Initializing engine...\n")
        
        # Convert config to engine format
        engine_config = {
            'initial_capital': config.get('initial_capital', 10000),
            'risk_per_trade': config.get('risk_per_trade', 2.0),
            'max_drawdown': config.get('max_drawdown', 15.0),
            'max_positions': config.get('max_positions', 3),
            'leverage': config.get('leverage', 10.0),
            'symbol': config.get('symbol', 'BTC/USDT'),
            'timeframes': config.get('timeframes', ['4h', '15m']),
            'start_date': config.get('start_date', '2023-01-01'),
            'end_date': config.get('end_date', '2023-12-31'),
            'strategy': config.get('strategy', 'smc_strategy'),
            'strategy_config': config.get('strategy_config', {}),
            'min_risk_reward': config.get('min_risk_reward', 2.0),
            'trailing_stop_distance': config.get('trailing_stop_distance', 0.02),
            'max_total_risk_percent': config.get('max_total_risk_percent', 15.0),
            'dynamic_position_sizing': config.get('dynamic_position_sizing', True),
            'log_level': 'INFO',
            'export_logs': True,
            'log_file': 'results/backtest_logs.json',
            'detailed_signals': True,
            'detailed_trades': True,
            'market_analysis': True,
            'save_results': True,
            'results_file': 'results/backtest_results.json',
            'export_trades': True,
            'trades_file': 'results/trades_history.json'
        }
        
        # Log configuration details
        await broadcast_message(f"[{run_id}] ============================================================\n")
        await broadcast_message(f"[{run_id}] BACKTEST CONFIGURATION\n")
        await broadcast_message(f"[{run_id}] ============================================================\n")
        await broadcast_message(f"[{run_id}] Strategy: {engine_config['strategy']}\n")
        await broadcast_message(f"[{run_id}] Symbol: {engine_config['symbol']}\n")
        await broadcast_message(f"[{run_id}] Timeframes: {', '.join(engine_config['timeframes'])}\n")
        await broadcast_message(f"[{run_id}] Period: {engine_config['start_date']} to {engine_config['end_date']}\n")
        await broadcast_message(f"[{run_id}] Initial Capital: ${engine_config['initial_capital']:,.2f}\n")
        await broadcast_message(f"[{run_id}] Risk Per Trade: {engine_config['risk_per_trade']}%\n")
        await broadcast_message(f"[{run_id}] Max Drawdown: {engine_config['max_drawdown']}%\n")
        await broadcast_message(f"[{run_id}] Max Positions: {engine_config['max_positions']}\n")
        await broadcast_message(f"[{run_id}] Leverage: {engine_config['leverage']}x\n")
        await broadcast_message(f"[{run_id}] Min Risk/Reward: {engine_config['min_risk_reward']}\n")
        await broadcast_message(f"[{run_id}] Trailing Stop Distance: {engine_config['trailing_stop_distance']}\n")
        await broadcast_message(f"[{run_id}] Max Total Risk: {engine_config['max_total_risk_percent']}%\n")
        await broadcast_message(f"[{run_id}] Dynamic Position Sizing: {engine_config['dynamic_position_sizing']}\n")
        if engine_config['strategy_config']:
            await broadcast_message(f"[{run_id}] Strategy Config: {engine_config['strategy_config']}\n")
        await broadcast_message(f"[{run_id}] ============================================================\n")
        
        # Create custom stdout to capture print statements
        class WebSocketStdout:
            """Custom stdout wrapper to capture print() output and put it in a queue."""
            def __init__(self, run_id: str):
                self.run_id = run_id
                self.signals_count = 0
            
            def write(self, text: str):
                if text.strip():  # Only send non-empty lines
                    # Count signals from log messages
                    if "SIGNAL GENERATED:" in text:
                        self.signals_count += 1
                    # Put message in thread-safe queue
                    msg = f"[{self.run_id}] {text.strip()}\n"
                    log_queue.put(msg)
            
            def flush(self):
                pass
        
        # Redirect stdout to capture print statements
        websocket_stdout = WebSocketStdout(run_id)
        sys.stdout = websocket_stdout
        
        try:
            # Create engine
            await broadcast_message(f"[{run_id}] Creating engine instance...\n")
            engine = BacktestEngine(engine_config)
            
            # Clear any previous logs to start fresh
            engine.logger.logs = []
            
            # Store engine reference for cancellation support
            running_backtests[run_id].engine = engine
            
            await broadcast_message(f"[{run_id}] ✅ Engine created\n")
            
            # Update status
            running_backtests[run_id].message = "Loading data..."
            running_backtests[run_id].progress = 30.0
            await broadcast_message(f"[{run_id}] Loading data...\n")
            
            # Check if cancellation was requested
            if running_backtests[run_id].should_cancel:
                running_backtests[run_id].status = "cancelled"
                running_backtests[run_id].message = "Backtest cancelled"
                await broadcast_message(f"[{run_id}] Backtest cancelled by user\n")
                return
            
            # Load data
            await broadcast_message(f"[{run_id}] Starting data load...\n")
            engine.load_data()
            await broadcast_message(f"[{run_id}] ✅ Data loaded\n")
            
            # Check if cancellation was requested
            if running_backtests[run_id].should_cancel:
                running_backtests[run_id].status = "cancelled"
                running_backtests[run_id].message = "Backtest cancelled"
                await broadcast_message(f"[{run_id}] Backtest cancelled by user\n")
                return
            
            # Update status
            running_backtests[run_id].message = "Running backtest..."
            running_backtests[run_id].progress = 50.0
            await broadcast_message(f"[{run_id}] Running backtest...\n")
            
            # Run backtest
            await broadcast_message(f"[{run_id}] Starting engine.run_backtest()...\n")
            
            # Check for cancellation before running
            if running_backtests[run_id].should_cancel:
                running_backtests[run_id].status = "cancelled"
                running_backtests[run_id].message = "Backtest cancelled"
                await broadcast_message(f"[{run_id}] ❌ Backtest cancelled before execution\n")
                return
            
            # Run backtest in a separate thread to prevent blocking the async loop
            loop = asyncio.get_event_loop()
            metrics = await loop.run_in_executor(None, engine.run_backtest)
            
            # Check if backtest was cancelled
            if engine.should_cancel:
                await broadcast_message(f"[{run_id}] ⏹️ Backtest cancelled by user\n")
                await broadcast_message(f"[{run_id}] 📊 Intermediate metrics calculated\n")
                # Use intermediate metrics up to cancellation point
            else:
                await broadcast_message(f"[{run_id}] ✅ engine.run_backtest() completed\n")
            
            # Add signals count to metrics
            metrics['signals_generated'] = websocket_stdout.signals_count # Use the counter from the custom stdout
            
            # Convert Position objects to dictionaries for JSON serialization
            trades_data = []
            for trade in engine.closed_trades:
                # Calculate PnL percentage
                pnl_percent = 0
                if trade.entry_price and trade.original_size:
                    pnl_percent = (trade.realized_pnl / (trade.entry_price * trade.original_size)) * 100
                
                trade_dict = {
                    'id': trade.id,
                    'direction': trade.direction,
                    'entry_price': trade.entry_price,
                    'exit_price': trade.exit_price,
                    'size': trade.size,
                    'pnl': trade.realized_pnl,  # Add pnl field for frontend
                    'pnl_percent': pnl_percent,  # Add pnl_percent field for frontend
                    'entry_time': trade.entry_time.isoformat() if trade.entry_time else None,
                    'exit_time': trade.exit_time.isoformat() if trade.exit_time else None,
                    'duration': str(trade.exit_time - trade.entry_time) if trade.exit_time and trade.entry_time else None,
                    'status': 'CLOSED' if trade.is_closed else 'OPEN',
                    'stop_loss': trade.stop_loss,
                    'take_profit': trade.take_profit,
                    'realized_pnl': trade.realized_pnl,
                    'exit_reason': trade.exit_reason,
                    'reason': trade.reason
                }
                trades_data.append(trade_dict)
            
            # Convert equity curve to serializable format
            equity_data = []
            for point in engine.equity_curve:
                equity_dict = {
                    'date': point['timestamp'].isoformat() if hasattr(point['timestamp'], 'isoformat') else str(point['timestamp']),
                    'equity': point['equity']
                }
                equity_data.append(equity_dict)
            
            # Map metrics from PerformanceReporter to frontend format
            # PerformanceReporter uses: win_count, loss_count, total_pnl
            # Frontend expects: winning_trades, losing_trades, total_pnl
            mapped_metrics = {
                'total_pnl': metrics.get('total_pnl', 0),
                'winning_trades': metrics.get('win_count', 0),
                'losing_trades': metrics.get('loss_count', 0),
                'total_trades': metrics.get('total_trades', 0),
                'win_rate': metrics.get('win_rate', 0) / 100 if metrics.get('win_rate', 0) > 1 else metrics.get('win_rate', 0),
                'profit_factor': metrics.get('profit_factor', 0),
                'max_drawdown': metrics.get('max_drawdown', 0),
                'sharpe_ratio': metrics.get('sharpe_ratio', 0),
                'avg_win': metrics.get('avg_win', 0),
                'avg_loss': metrics.get('avg_loss', 0),
                'initial_capital': engine_config.get('initial_capital', 10000),
                'signals_generated': websocket_stdout.signals_count, # Use the counter from the custom stdout
                'equity_curve': equity_data,
                'trades': trades_data
            }
            
            # Update metrics with mapped values
            metrics.update(mapped_metrics)
            
            # Add logs to metrics for complete data preservation
            metrics['logs'] = engine.logger.logs
            
            # Store results in running_backtests IMMEDIATELY so frontend can access them
            running_backtests[run_id].results = metrics
            running_backtests[run_id].progress = 100.0
            
            # Update status AFTER results are set
            if engine.should_cancel:
                running_backtests[run_id].status = "cancelled"
                running_backtests[run_id].message = "Backtest cancelled"
            else:
                running_backtests[run_id].status = "completed"
                running_backtests[run_id].message = "Backtest completed successfully"
            
            # Update status
            running_backtests[run_id].message = "Generating report..."
            await broadcast_message(f"[{run_id}] Generating report...\n")
            
            # Save results
            result_file = os.path.join(RESULTS_DIR, f"{run_id}.json")
            with open(result_file, 'w') as f:
                json.dump(metrics, f, indent=2, default=str)
            await broadcast_message(f"[{run_id}] ✅ Results saved to {result_file}\n")
            
            # All data (metrics, trades, logs) is already contained in the results file
            # No need for separate smc_spot_*.json files
        
        finally:
            # Restore original stdout
            sys.stdout = original_stdout
            sys.stderr = original_stderr # Also restore stderr
        
    except Exception as e:
        # Update status with error
        running_backtests[run_id].status = "failed"
        running_backtests[run_id].message = f"Backtest failed: {str(e)}"
        running_backtests[run_id].error = str(e)
        await broadcast_message(f"[{run_id}] ERROR: {str(e)}\n")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
