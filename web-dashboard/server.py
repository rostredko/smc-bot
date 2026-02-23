"""
FastAPI Web Server for Backtrade Machine.
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

from engine.bt_backtest_engine import BTBacktestEngine
from strategies.bt_price_action import PriceActionStrategy
# Central logging — must import AFTER sys.path is set up
from engine.logger import get_logger, setup_logging, ws_log_queue

# Bootstrap project logging (console only at startup; WS handler added per-run)
setup_logging(enable_ws=False)
logger = get_logger("server")

# Configuration - Use absolute paths for cross-platform compatibility
BASE_DIR = Path(__file__).parent.parent.absolute()
DATA_DIR = str(BASE_DIR / "data_cache")
RESULTS_DIR = str(BASE_DIR / "results")
USER_CONFIGS_DIR = str(BASE_DIR / "user_configs")

# Ensure directories exist
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(RESULTS_DIR, exist_ok=True)
os.makedirs(USER_CONFIGS_DIR, exist_ok=True)

# FastAPI app
app = FastAPI(
    title="Backtrade Machine API",
    description="REST API for Backtrade Machine",
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
    risk_per_trade: float = 1.5
    max_drawdown: float = 20.0
    max_positions: int = 3
    leverage: float = 10.0
    symbol: str = "BTC/USDT"
    timeframes: List[str] = ["4h", "15m"]
    start_date: str = "2025-01-01"
    end_date: str = "2025-12-31"
    confluence_required: str = "false"
    strategy: str = "smc_strategy"
    strategy_config: Dict[str, Any] = {}
    min_risk_reward: float = 2.5
    trailing_stop_distance: float = 0.04
    breakeven_trigger_r: float = 1.5
    max_total_risk_percent: float = 15.0
    dynamic_position_sizing: bool = True
    taker_fee: float = 0.04  # Default 0.04%
    slippage_bp: float = 0.0 # Default 0 basis points
    exchange: str = "binance"
    exchange_type: str = "future"


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


async def broadcast_from_queue():
    """Periodically drain ws_log_queue and broadcast messages to WebSocket clients."""
    while True:
        try:
            while True:
                try:
                    message = ws_log_queue.get_nowait()
                    with connection_lock:
                        connections_copy = active_connections.copy()

                    if not connections_copy:
                        continue  # No clients connected, skip

                    for connection in connections_copy:
                        try:
                            await connection.send_text(message)
                        except Exception:
                            with connection_lock:
                                if connection in active_connections:
                                    active_connections.remove(connection)
                except Exception:  # queue.Empty or other
                    break
        except Exception as e:
            logger.debug(f"Broadcaster loop error: {e}")

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
        "bt_price_action": {
            # Pattern Settingsical Entry Filters
            "use_trend_filter": {"type": "boolean", "default": True},
            "trend_ema_period": {"type": "number", "default": 200},
            
            "use_rsi_filter": {"type": "boolean", "default": True},
            "rsi_period": {"type": "number", "default": 14},
            "rsi_overbought": {"type": "number", "default": 70},
            "rsi_oversold": {"type": "number", "default": 30},
            
            "use_rsi_momentum": {"type": "boolean", "default": False},
            "rsi_momentum_threshold": {"type": "number", "default": 60},
            
            "use_adx_filter": {"type": "boolean", "default": False},
            "adx_period": {"type": "number", "default": 14},
            "adx_threshold": {"type": "number", "default": 25},
            
            # Pattern Settings
            "min_range_factor": {"type": "number", "default": 0.8},
            "min_wick_to_range": {"type": "number", "default": 0.6},
            "max_body_to_range": {"type": "number", "default": 0.3},

            "risk_reward_ratio": {"type": "number", "default": 2.5},
            "sl_buffer_atr": {"type": "number", "default": 1.0}
        }
    }
    
    # Backward compatibility for legacy config name
    default_schemas["price_action_strategy"] = default_schemas["bt_price_action"]
    
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
    strategies = load_available_strategies()
    elapsed = time.time() - start
    logger.debug(f"Strategies loaded in {elapsed:.3f}s: {[s['name'] for s in strategies]}")
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
            "max_positions": config.get("account", {}).get("max_positions", 1),
            "leverage": config.get("account", {}).get("leverage", 10.0),
            "symbol": config.get("trading", {}).get("symbol", "BTC/USDT"),
            "timeframes": config.get("trading", {}).get("timeframes", ["4h", "15m"]),
            "start_date": config.get("period", {}).get("start_date", "2023-01-01"),
            "end_date": config.get("period", {}).get("end_date", "2023-12-31"),
            "strategy": config.get("strategy", {}).get("name", "smc_strategy"),
            "strategy_config": config.get("strategy", {}).get("config", {}),
            "min_risk_reward": config.get("min_risk_reward", 2.5),
            "trailing_stop_distance": config.get("trailing_stop_distance", 0.04),
            "breakeven_trigger_r": config.get("breakeven_trigger_r", 1.5),
            "max_total_risk_percent": config.get("max_total_risk_percent", 15.0),
            "dynamic_position_sizing": config.get("dynamic_position_sizing", True)
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
        
    # Update root level settings
    if "min_risk_reward" in config:
        existing_config["min_risk_reward"] = config["min_risk_reward"]
    if "trailing_stop_distance" in config:
        existing_config["trailing_stop_distance"] = config["trailing_stop_distance"]
    if "breakeven_trigger_r" in config:
        existing_config["breakeven_trigger_r"] = config["breakeven_trigger_r"]
    if "max_total_risk_percent" in config:
        existing_config["max_total_risk_percent"] = config["max_total_risk_percent"]
    if "dynamic_position_sizing" in config:
        existing_config["dynamic_position_sizing"] = config["dynamic_position_sizing"]
    
    # Save updated config
    with open(config_path, 'w') as f:
        json.dump(existing_config, f, indent=2)
    
    return {"message": "Configuration updated"}


@app.get("/api/user-configs")
async def list_user_configs():
    """List all saved user configurations."""
    configs = []
    if os.path.exists(USER_CONFIGS_DIR):
        for name in os.listdir(USER_CONFIGS_DIR):
            if name.endswith(".json"):
                configs.append(name[:-5])  # Remove .json extension
    return {"configs": sorted(configs)}


@app.get("/api/user-configs/{name}")
async def get_user_config(name: str):
    """Get a specific user configuration."""
    # Basic path traversal protection
    if "/" in name or "\\" in name or ".." in name:
        raise HTTPException(status_code=400, detail="Invalid configuration name")
    
    file_path = os.path.join(USER_CONFIGS_DIR, f"{name}.json")
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Configuration not found")
        
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading configuration: {str(e)}")


@app.post("/api/user-configs/{name}")
async def save_user_config(name: str, config: Dict[str, Any]):
    """Save a user configuration."""
    if "/" in name or "\\" in name or ".." in name:
        raise HTTPException(status_code=400, detail="Invalid configuration name")
        
    file_path = os.path.join(USER_CONFIGS_DIR, f"{name}.json")
    try:
        with open(file_path, 'w') as f:
            json.dump(config, f, indent=2)
        return {"message": f"Configuration '{name}' saved successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error saving configuration: {str(e)}")


@app.delete("/api/user-configs/{name}")
async def delete_user_config(name: str):
    """Delete a user configuration."""
    if "/" in name or "\\" in name or ".." in name:
        raise HTTPException(status_code=400, detail="Invalid configuration name")
        
    file_path = os.path.join(USER_CONFIGS_DIR, f"{name}.json")
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Configuration not found")
        
    try:
        os.remove(file_path)
        return {"message": f"Configuration '{name}' deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting configuration: {str(e)}")

@app.post("/backtest/start")
async def start_backtest(request: BacktestRequest, background_tasks: BackgroundTasks):
    """Start a new backtest."""
    run_id = request.run_id or f"backtest_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    # Check if already running
    if run_id in running_backtests:
        raise HTTPException(status_code=400, detail=f"Backtest {run_id} is already running")
    
    # Memory Cleanup: Limit running_backtests to last 20 items to prevent leaks
    if len(running_backtests) > 20:
        keys_to_remove = list(running_backtests.keys())[:-20]
        for k in keys_to_remove:
            if k in running_backtests:
                del running_backtests[k]

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


def _default_configuration_for_legacy_backtest() -> Dict[str, Any]:
    """Default configuration for old backtests that lack configuration. Matches PriceActionStrategy defaults."""
    return {
        "symbol": "BTC/USDT",
        "timeframes": ["1h"],
        "strategy": "bt_price_action",
        "_legacy_default": True,  # Marks that real config was not saved; these are assumed defaults
        "strategy_config": {
            "use_trend_filter": True,
            "trend_ema_period": 200,
            "use_rsi_filter": True,
            "rsi_period": 14,
            "rsi_overbought": 70,
            "rsi_oversold": 30,
            "use_adx_filter": True,
            "adx_period": 14,
            "adx_threshold": 25,
        },
    }


@app.get("/results/{filename}")
async def get_result_file(filename: str):
    """Get specific result file. Backfills configuration for legacy files and persists it."""
    file_path = os.path.join(RESULTS_DIR, filename)
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Result file not found")
    
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)
        
        # Backfill configuration for legacy backtests (no configuration saved)
        if not data.get("configuration"):
            default_cfg = _default_configuration_for_legacy_backtest()
            data["configuration"] = default_cfg
            try:
                with open(file_path, 'w') as f:
                    json.dump(data, f, indent=2, default=str)
                logger.info(f"Backfilled configuration for legacy result: {filename}")
            except Exception as e:
                logger.warning(f"Could not persist backfilled config to {filename}: {e}")
        
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading file: {str(e)}")



@app.get("/api/backtest/history")
async def get_backtest_history(page: int = 1, page_size: int = 10):
    """Get paginated history of backtests with summary metrics."""
    history = []
    
    if os.path.exists(RESULTS_DIR):
        # Get list of JSON files with their modification times
        files = []
        for name in os.listdir(RESULTS_DIR):
            if name.endswith(".json") and name.startswith("backtest_"):
                # Skip log files and generic result files
                if "_logs" in name or name == "backtest_results.json":
                    continue
                    
                file_path = os.path.join(RESULTS_DIR, name)
                try:
                    mtime = os.path.getmtime(file_path)
                    files.append((name, mtime))
                except OSError:
                    continue
        
        # Sort by modification time (descending)
        files.sort(key=lambda x: x[1], reverse=True)
        
        # Calculate pagination
        total_count = len(files)
        total_pages = (total_count + page_size - 1) // page_size  # Ceiling division
        
        # Validate page number
        if page < 1:
            page = 1
        if page > total_pages and total_pages > 0:
            page = total_pages
            
        # Calculate offset
        offset = (page - 1) * page_size
        
        # Get files for current page
        page_files = files[offset:offset + page_size]
        
        # Process files for current page
        for filename, mtime in page_files:
            try:
                file_path = os.path.join(RESULTS_DIR, filename)
                with open(file_path, 'r') as f:
                    data = json.load(f)
                
                # Extract simplified summary stats
                summary = {
                    "filename": filename,
                    "timestamp": datetime.fromtimestamp(mtime).isoformat(),
                    "total_pnl": data.get("total_pnl", 0),
                    "initial_capital": data.get("initial_capital", data.get("configuration", {}).get("initial_capital", 10000)),
                    "win_rate": data.get("win_rate", 0),
                    "max_drawdown": data.get("max_drawdown", 0),
                    "total_trades": data.get("total_trades", 0),
                    "profit_factor": data.get("profit_factor", 0),
                    "sharpe_ratio": data.get("sharpe_ratio", 0),
                    "expected_value": data.get("expected_value", 0), # Expectancy if available
                    "avg_win": data.get("avg_win", 0),
                    "avg_loss": data.get("avg_loss", 0),
                    "winning_trades": data.get("winning_trades", 0),
                    "losing_trades": data.get("losing_trades", 0),
                    "strategy": data.get("configuration", {}).get("strategy", "Unknown"),
                    # Pass full configuration for detailed view
                    "configuration": data.get("configuration", {})
                }
                history.append(summary)
            except Exception as e:
                logger.warning(f"Error reading history file {filename}: {e}")
                continue
    else:
        total_count = 0
        total_pages = 0
                
    return {
        "history": history,
        "pagination": {
            "total_count": total_count,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages
        }
    }


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


@app.delete("/api/backtest/history/{filename}")
async def delete_backtest_result(filename: str):
    """Delete a specific backtest result file."""
    # Security check: ensure filename contains only safe characters
    if not filename.endswith(".json") or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
        
    file_path = os.path.join(RESULTS_DIR, filename)
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
        
    try:
        os.remove(file_path)
        
        # Also try to remove the corresponding trades file if it exists
        # Pattern: backtest_TIMESTAMP_results.json -> backtest_TIMESTAMP_trades.json
        if "_results.json" in filename:
            trades_file = filename.replace("_results.json", "_trades.json")
            trades_path = os.path.join(RESULTS_DIR, trades_file)
            if os.path.exists(trades_path):
                os.remove(trades_path)
                
        # Also try to remove logs file
        # Pattern: backtest_TIMESTAMP_results.json -> backtest_TIMESTAMP_logs.json (sometimes)
        # But commonly logs are just backtest_logs.json (overwritten) or separate. 
        # For now, we just delete the main result file and trades file.
        
        return {"message": f"Successfully deleted {filename}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting file: {str(e)}")


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
        except Exception:
            # Silently remove dead connections
            with connection_lock:
                if connection in active_connections:
                    active_connections.remove(connection)


async def run_backtest_task(run_id: str, config: Dict[str, Any]):
    """Background task to run backtest."""
    
    try:
        # Update status
        running_backtests[run_id].message = "Initializing engine..."
        running_backtests[run_id].progress = 10.0
        await broadcast_message(f"[{run_id}] Initializing engine...\n")
        
        # Calculate commission from taker_fee (e.g. 0.04 -> 0.0004)
        taker_fee_pct = config.get('taker_fee', 0.04)
        commission = taker_fee_pct / 100.0
        
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
            'min_risk_reward': config.get('min_risk_reward', 2.5),
            'trailing_stop_distance': config.get('trailing_stop_distance', 0.04),
            'breakeven_trigger_r': config.get('breakeven_trigger_r', 1.5),
            'max_total_risk_percent': config.get('max_total_risk_percent', 15.0),
            'dynamic_position_sizing': config.get('dynamic_position_sizing', True),
            'commission': commission,
            'taker_fee': taker_fee_pct,
            'slippage_bp': config.get('slippage_bp', 0.0),
            'log_level': 'INFO',
            'export_logs': True,
            'log_file': os.path.join(RESULTS_DIR, 'backtest_logs.json'),
            'detailed_signals': True,
            'detailed_trades': True,
            'market_analysis': True,
            'save_results': True,
            'results_file': 'results/backtest_results.json',
            'export_trades': True,
            'trades_file': 'results/trades_history.json'
        }
        
        # CRITICAL: Sync dashboard timeframes with strategy config
        # The strategy uses 'high_timeframe' and 'low_timeframe' keys, while engine uses 'timeframes' list
        if len(engine_config['timeframes']) >= 1:
             # Just ensure the engine has timeframes set (already done via 'timeframes' key)
             pass
        
        
        # Log configuration details
        await broadcast_message(f"[{run_id}] ============================================================\n")
        await broadcast_message(f"[{run_id}] BACKTEST CONFIGURATION\n")
        await broadcast_message(f"[{run_id}] ============================================================\n")
        await broadcast_message(f"[{run_id}] Strategy: {engine_config['strategy']}\n")
        await broadcast_message(f"[{run_id}] Symbol: {engine_config['symbol']}\n")
        await broadcast_message(f"[{run_id}] Commission (Taker): {engine_config['taker_fee']}% ({engine_config['commission']})\n")
        await broadcast_message(f"[{run_id}] Slippage: {engine_config['slippage_bp']} bp\n")
        await broadcast_message(f"[{run_id}] Timeframes: {', '.join(engine_config['timeframes'])}\n")
        await broadcast_message(f"[{run_id}] Period: {engine_config['start_date']} to {engine_config['end_date']}\n")
        await broadcast_message(f"[{run_id}] Initial Capital: ${engine_config['initial_capital']:,.2f}\n")
        await broadcast_message(f"[{run_id}] Risk Per Trade: {engine_config['risk_per_trade']}%\n")
        await broadcast_message(f"[{run_id}] Max Drawdown: {engine_config['max_drawdown']}%\n")
        await broadcast_message(f"[{run_id}] Leverage: {engine_config['leverage']}x\n")
        await broadcast_message(f"[{run_id}] Trailing Stop Distance: {engine_config['trailing_stop_distance']}\n")
        await broadcast_message(f"[{run_id}] Breakeven Trigger (R): {engine_config['breakeven_trigger_r']}\n")
        await broadcast_message(f"[{run_id}] Dynamic Position Sizing: {engine_config['dynamic_position_sizing']}\n")
        if engine_config['strategy_config']:
            await broadcast_message(f"[{run_id}] Strategy Config: {engine_config['strategy_config']}\n")
        await broadcast_message(f"[{run_id}] ============================================================\n")
        
        # Activate WebSocket log delivery for this run.
        # setup_logging adds a QueueHandler that formats every log record with
        # the run_id prefix and puts it into ws_log_queue, which broadcast_from_queue()
        # drains every 50 ms and sends to all connected WebSocket clients.
        import logging as _logging
        setup_logging(level=_logging.INFO, run_id=run_id, enable_ws=True)

        # Track signals count via a lightweight log handler
        class _SignalCounter(_logging.Handler):
            def __init__(self):
                super().__init__()
                self.count = 0
            def emit(self, record):
                if "SIGNAL GENERATED:" in record.getMessage():
                    self.count += 1

        signal_counter = _SignalCounter()
        import logging as _logging_root
        _root_logger = _logging_root.getLogger("backtrade")
        _root_logger.addHandler(signal_counter)

        try:
            # Create engine
            await broadcast_message(f"[{run_id}] Creating engine instance...\n")
            engine = BTBacktestEngine(engine_config)
            
            # Add Strategy
            # Use 'price_action' or default to PriceActionStrategy class
            # We only have one strategy for now in BT migration
            st_config = engine_config.get('strategy_config', {})
            
            # Inject general settings that are actually strategy parameters
            # These are defined at the top level in the UI but needed by the strategy
            st_config['trailing_stop_distance'] = engine_config.get('trailing_stop_distance', 0.0)
            st_config['breakeven_trigger_r'] = engine_config.get('breakeven_trigger_r', 0.0)
            st_config['risk_per_trade'] = engine_config.get('risk_per_trade', 1.0)
            st_config['leverage'] = engine_config.get('leverage', 1.0)
            st_config['dynamic_position_sizing'] = engine_config.get('dynamic_position_sizing', True)
            st_config['max_drawdown'] = engine_config.get('max_drawdown', 50.0)
            
            engine.add_strategy(PriceActionStrategy, **st_config)
            

            
            # Store engine reference for cancellation support
            running_backtests[run_id].engine = engine
            
            await broadcast_message(f"[{run_id}] ✅ Engine created\n")
            
            # Update status
            running_backtests[run_id].message = "Loading data..."
            running_backtests[run_id].progress = 30.0
            
            # Check if cancellation was requested
            if running_backtests[run_id].should_cancel:
                running_backtests[run_id].status = "cancelled"
                running_backtests[run_id].message = "Backtest cancelled"
                await broadcast_message(f"[{run_id}] Backtest cancelled by user\n")
                return
            
            # Run backtest
            await broadcast_message(f"[{run_id}] Starting engine.run_backtest()...\n")
            
            # Run backtest in a separate thread
            loop = asyncio.get_event_loop()
            metrics = await loop.run_in_executor(None, engine.run_backtest)
            
            await broadcast_message(f"[{run_id}] ✅ engine.run_backtest() completed\n")
            
            # Initialize mapped_metrics to ensure scope visibility
            mapped_metrics = None
            
            try:
                # Count signals generated during this run
                metrics['signals_generated'] = signal_counter.count
                
                # Convert Dictionary trades to expected format
                trades_data = []
                for i, trade in enumerate(engine.closed_trades):
                    entry_time = datetime.fromisoformat(trade['entry_time']) if trade['entry_time'] else None
                    exit_time = datetime.fromisoformat(trade['exit_time']) if trade['exit_time'] else None
                    
                    # Format duration string (remove '0 days ' artifact)
                    duration_str = None
                    if exit_time and entry_time:
                        diff = exit_time - entry_time
                        duration_str = str(diff).replace("0 days ", "")

                    trade_dict = {
                        'id': i + 1,
                        'direction': trade['direction'],
                        'entry_price': trade['entry_price'],
                        'exit_price': trade['exit_price'],
                        'size': trade['size'],
                        'pnl': trade['realized_pnl'],
                        'pnl_percent': (trade['realized_pnl'] / (trade['entry_price'] * trade['size'])) * 100 if trade['entry_price'] and trade['size'] else 0,
                        'entry_time': trade['entry_time'],
                        'exit_time': trade['exit_time'],
                        'duration': duration_str,
                        'status': 'CLOSED',
                        'stop_loss': trade['stop_loss'],
                        'take_profit': trade['take_profit'],
                        'realized_pnl': trade['realized_pnl'],
                        'exit_reason': trade.get('exit_reason', 'Unknown'),
                        'commission': trade.get('commission', 0),
                        'reason': trade.get('reason', 'Unknown'), # Use .get() for safety
                        'narrative': trade.get('narrative', None), # Add Narrative field
                        'sl_calculation': trade.get('sl_calculation', None), # Add SL Calc
                        'tp_calculation': trade.get('tp_calculation', None), # Add TP Calc
                        'sl_history': trade.get('sl_history', []), # Add SL History
                        'metadata': {}
                    }
                    trades_data.append(trade_dict)
                
                # Convert equity curve to serializable format with downsampling
                equity_data = []
                
                # Downsample to max 100 points
                total_points = len(engine.equity_curve)
                step = max(1, int(total_points / 100))
                
                for i, point in enumerate(engine.equity_curve):
                    if i % step == 0 or i == total_points - 1:
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
                    'final_capital': metrics.get('final_capital', 0),
                    'signals_generated': signal_counter.count,  # signals counted by _SignalCounter handler
                    'equity_curve': equity_data,
                    'trades': trades_data,
                    'strategy': engine_config.get('strategy', 'Unknown'),
                    'configuration': engine_config
                }
                
                # Update metrics with mapped values
                metrics.update(mapped_metrics)
                
                # logs field: reserved for future structured log export
                metrics['logs'] = []
                
                # Store results in running_backtests IMMEDIATELY so frontend can access them
                running_backtests[run_id].results = metrics
                running_backtests[run_id].progress = 100.0
                
            except Exception as e:
                import traceback
                error_trace = traceback.format_exc()
                logger.error(f"Error processing backtest data: {e}\n{error_trace}")
                await broadcast_message(f"[{run_id}] ⚠️ Error processing backtest data: {str(e)}\n")
                # Don't raise, try to continue if possible, but mapped_metrics might be None
            
            # Update status
            running_backtests[run_id].message = "Generating report..."
            await broadcast_message(f"[{run_id}] Generating report...\n")
            
            # Save results first to get the path
            result_file = os.path.join(RESULTS_DIR, f"{run_id}.json")
            try:
                with open(result_file, 'w') as f:
                    json.dump(metrics, f, indent=2, default=str)
                await broadcast_message(f"[{run_id}] ✅ Results saved to {result_file}\n")
                await asyncio.sleep(0.5) # Increased sleep to ensure flush
            except Exception as e:
                import traceback
                logger.error(f"Error saving results: {e}\n{traceback.format_exc()}")
                await broadcast_message(f"[{run_id}] ⚠️ Error saving results: {str(e)}\n")
            
            # Restore WS logging to console-only (no more per-run prefix needed)
            setup_logging(enable_ws=False)
            
            # Broadcast results summary to logs
            # Broadcast results summary to logs

            try:
                if mapped_metrics is None:
                    await broadcast_message(f"[{run_id}] ⚠️ Skipping report generation (metrics missing)\n")
                else:
                    await broadcast_message(f"[{run_id}] Generating detailed report...\n")
                    
                    # Safe calculations for summary
                    init_cap = mapped_metrics.get('initial_capital', 1)
                    if init_cap == 0: init_cap = 1 # Avoid division by zero
                    
                    total_pnl = mapped_metrics.get('total_pnl', 0)
                    final_cap = mapped_metrics.get('final_capital', 0)
                    
                    return_pct = (total_pnl / init_cap) * 100
                    
                    # Construct summary lines
                    summary_lines = [
                        "============================================================",
                        "BACKTEST RESULTS SUMMARY",
                        "============================================================",
                        f"Final Balance:    ${final_cap:,.2f}",
                        f"Total PnL:        ${total_pnl:,.2f}",
                        f"Return:           {return_pct:.2f}%",
                        f"Max Drawdown:     {mapped_metrics.get('max_drawdown', 0):.2f}%",
                        f"Win Rate:         {mapped_metrics.get('win_rate', 0) * 100:.2f}%",
                        f"Profit Factor:    {mapped_metrics.get('profit_factor', 0):.2f}",
                        f"Total Trades:     {mapped_metrics.get('total_trades', 0)}",
                        f"  - Winning:      {metrics.get('win_count', 0)}",
                        f"  - Losing:       {metrics.get('loss_count', 0)}",
                        f"Sharpe Ratio:     {mapped_metrics.get('sharpe_ratio', 0):.2f}",
                        "============================================================"
                    ]
                    
                    # Broadcast line by line to ensure reliability with explicit delay
                    await broadcast_message(f"[{run_id}] Backtest Summary:\n")
                    await asyncio.sleep(0.1)
                    
                    for line in summary_lines:
                         await broadcast_message(f"[{run_id}] {line}\n")
                         # Explicit delay to prevent flooding/race conditions
                         await asyncio.sleep(0.2)
                    
                    # Also log to file for debugging
                    logger.info(f"[{run_id}] Backtest Summary Generated")

                    # Allow extended time for logs to flush to WebSocket BEFORE marking as completed
                    await broadcast_message(f"[{run_id}] Report generated. Finalizing...\n")
                    await asyncio.sleep(1.0)
                
                # Update status to completed FINAL step
                if not engine.should_cancel:
                     running_backtests[run_id].status = "completed"
                     running_backtests[run_id].message = "Backtest completed successfully"
                     
            except Exception as e:
                import traceback
                error_trace = traceback.format_exc()
                logger.error(f"Error generating report summary: {e}\n{error_trace}")
                await broadcast_message(f"[{run_id}] Error generating report summary: {str(e)}\n")
                
                running_backtests[run_id].status = "failed"
                running_backtests[run_id].message = f"Report generation failed: {str(e)}"
        
        finally:
            # Clean up signal counter handler to avoid accumulation across runs
            _root_logger.removeHandler(signal_counter)
            # Restore WS logging to console-only after cleanup
            setup_logging(enable_ws=False)
        
    except Exception as e:
        # Update status with error
        running_backtests[run_id].status = "failed"
        running_backtests[run_id].message = f"Backtest failed: {str(e)}"
        running_backtests[run_id].error = str(e)
        await broadcast_message(f"[{run_id}] ERROR: {str(e)}\n")



import ccxt

# Global cache for symbols
# structure: { "data": ["BTC/USDT", ...], "timestamp": 1234567890.0 }
SYMBOLS_CACHE = {
    "data": [],
    "timestamp": 0.0
}
CACHE_DURATION_SECONDS = 300 # 5 minutes

@app.get("/api/symbols/top")
async def get_top_symbols(limit: int = 10):
    """
    Fetch top symbols by 24h quote volume from Binance.
    Cached for 5 minutes.
    """
    global SYMBOLS_CACHE
    now = datetime.now().timestamp()
    
    # Check cache
    if SYMBOLS_CACHE["data"] and (now - SYMBOLS_CACHE["timestamp"] < CACHE_DURATION_SECONDS):
        return {"symbols": SYMBOLS_CACHE["data"][:limit]}

    try:
        # Run synchronous ccxt code in a thread to avoid blocking loop
        def fetch_from_exchange():
            exchange = ccxt.binance({'enableRateLimit': True})
            tickers = exchange.fetch_tickers()
            
            # Filter and sort
            valid_pairs = []
            # Filter and sort
            valid_pairs = []
            
            # Symbols to exclude (Stablecoins, Fiat pairs, Special tokens)
            EXCLUDED_PATTERNS = ['UP/', 'DOWN/', 'BEAR/', 'BULL/']
            EXCLUDED_EXACT = [
                'USDC/USDT', 'FDUSD/USDT', 'TUSD/USDT', 'USDP/USDT', 'BUSD/USDT', 
                'DAI/USDT', 'EUR/USDT', 'GBP/USDT', 'PAXG/USDT', 'WBTC/USDT',
                'USTC/USDT', 'USD1/USDT', 'ZAMA/USDT', 'USDE/USDT'
            ]
            
            for symbol, ticker in tickers.items():
                if not symbol.endswith('/USDT'):
                    continue
                    
                # Check exclusions
                if symbol in EXCLUDED_EXACT:
                    continue
                    
                is_excluded = False
                for pattern in EXCLUDED_PATTERNS:
                    if pattern in symbol:
                        is_excluded = True
                        break
                if is_excluded:
                    continue

                quote_vol = ticker.get('quoteVolume', 0)
                if quote_vol:
                     valid_pairs.append((symbol, quote_vol))
            
            # Sort by volume desc
            valid_pairs.sort(key=lambda x: x[1], reverse=True)
            
            return [p[0] for p in valid_pairs[:50]] # Keep top 50 in cache

        # Execute in threadpool
        loop = asyncio.get_event_loop()
        top_symbols = await loop.run_in_executor(None, fetch_from_exchange)
        
        # Update cache
        SYMBOLS_CACHE = {
            "data": top_symbols,
            "timestamp": now
        }
        
        return {"symbols": top_symbols[:limit]}
        
    except Exception as e:
        logger.error(f"Error fetching top symbols: {e}")
        # Return fallback if cache empty, or old cache if available
        if SYMBOLS_CACHE["data"]:
             return {"symbols": SYMBOLS_CACHE["data"][:limit]}
        return {"symbols": ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT"]}


# ---------------------------------------------------------------------------
# OHLCV endpoint — fetches candlestick data for trade chart visualisation
# ---------------------------------------------------------------------------

from collections import OrderedDict
from datetime import timezone

# Simple LRU cache: max 30 entries, each key = "symbol|timeframe|start|end"
_OHLCV_CACHE: OrderedDict = OrderedDict()
_OHLCV_CACHE_MAX = 30


def _ohlcv_cache_key(symbol: str, timeframe: str, since_ms: int, until_ms: int) -> str:
    return f"{symbol}|{timeframe}|{since_ms}|{until_ms}"


def _ohlcv_cache_get(key: str):
    if key in _OHLCV_CACHE:
        _OHLCV_CACHE.move_to_end(key)
        return _OHLCV_CACHE[key]
    return None


def _ohlcv_cache_set(key: str, value: list):
    if key in _OHLCV_CACHE:
        _OHLCV_CACHE.move_to_end(key)
    _OHLCV_CACHE[key] = value
    if len(_OHLCV_CACHE) > _OHLCV_CACHE_MAX:
        _OHLCV_CACHE.popitem(last=False)


# Map friendly timeframe strings to millisecond durations for window expansion
_TF_MS: dict = {
    "1m": 60_000,
    "3m": 180_000,
    "5m": 300_000,
    "15m": 900_000,
    "30m": 1_800_000,
    "1h": 3_600_000,
    "2h": 7_200_000,
    "4h": 14_400_000,
    "6h": 21_600_000,
    "8h": 28_800_000,
    "12h": 43_200_000,
    "1d": 86_400_000,
    "3d": 259_200_000,
    "1w": 604_800_000,
}


@app.get("/api/ohlcv")
async def get_ohlcv(
    symbol: str = "BTC/USDT",
    timeframe: str = "1h",
    start: str = "",
    end: str = "",
    context_bars: int = 25,
    # ── Indicator knobs (0 = disabled) ──────────────────────────────────────
    ema_period: int = 0,        # EMA overlay on price (e.g. 200)
    ema_timeframe: str = "",    # Timeframe for EMA computation (defaults to main timeframe)
    rsi_period: int = 0,        # RSI subplot (e.g. 14)
    rsi_overbought: float = 70,
    rsi_oversold: float = 30,
    adx_period: int = 0,        # ADX subplot (e.g. 14)
    adx_threshold: float = 25,
):
    """
    Fetch OHLCV candlestick data + optional TA-Lib indicators.

    Indicator params (pass 0 to skip):
      ema_period       - EMA on price panel (trend filter line)
      rsi_period       - RSI subplot
      rsi_overbought   - upper reference line (default 70)
      rsi_oversold     - lower reference line (default 30)
      adx_period       - ADX subplot
      adx_threshold    - reference line (default 25)

    Returns:
      {
        candles: [{time, open, high, low, close, volume}],
        indicators: {
          ema?:  [{time, value}],
          rsi?:  [{time, value}], rsi_ob, rsi_os,
          adx?:  [{time, value}], adx_threshold
        }
      }
    """
    try:
        def to_ms(iso_str: str) -> int:
            dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return int(dt.timestamp() * 1000)

        bar_ms = _TF_MS.get(timeframe, 3_600_000)
        pad_ms = bar_ms * max(1, context_bars)

        if start:
            since_ms = to_ms(start) - pad_ms
        else:
            since_ms = int(datetime.now(timezone.utc).timestamp() * 1000) - 200 * bar_ms

        if end:
            until_ms = to_ms(end) + pad_ms
        else:
            until_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

        # TA-Lib needs a warmup window so it has enough data for the first valid value.
        # Fetch an extra 300 bars before the visible window for warmup, then trim.
        warmup_bars = 300
        fetch_since_ms = since_ms - bar_ms * warmup_bars

        # Cache key includes indicator config so different param combos are cached separately
        ind_key = f"ema{ema_period}_rsi{rsi_period}-{rsi_overbought}-{rsi_oversold}_adx{adx_period}-{adx_threshold}"
        cache_key = _ohlcv_cache_key(symbol, timeframe, since_ms, until_ms) + "|" + ind_key

        cached = _ohlcv_cache_get(cache_key)
        if cached is not None:
            logger.debug(f"OHLCV+indicators cache hit: {cache_key}")
            return cached

        num_bars = max(1, int((until_ms - fetch_since_ms) / bar_ms)) + 2

        def fetch_and_compute():
            import numpy as np

            # ── 1. Fetch raw OHLCV ──────────────────────────────────────────
            exchange = ccxt.binance({"enableRateLimit": True})
            raw = exchange.fetch_ohlcv(symbol, timeframe, since=fetch_since_ms, limit=min(num_bars, 1500))

            if not raw:
                return {"candles": [], "indicators": {}}

            timestamps = [bar[0] for bar in raw]
            opens      = np.array([bar[1] for bar in raw], dtype=float)
            highs      = np.array([bar[2] for bar in raw], dtype=float)
            lows       = np.array([bar[3] for bar in raw], dtype=float)
            closes     = np.array([bar[4] for bar in raw], dtype=float)
            volumes    = np.array([bar[5] for bar in raw], dtype=float)

            # ── 2. Compute indicators (full array, then trim) ───────────────
            indicators_raw: dict = {}
            indicators_out: dict = {}   # ← must be defined before HTF EMA block writes into it

            try:
                import talib  # TA-Lib is installed in deps/requirements.txt
                has_talib = True
            except ImportError:
                try:
                    import TA_Lib as talib
                    has_talib = True
                except ImportError:
                    has_talib = False
                    logger.warning("TA-Lib not available — indicators skipped")

            if has_talib:
                # ── EMA: optionally on a different (higher) timeframe ─────────
                if ema_period > 0:
                    effective_ema_tf = ema_timeframe if ema_timeframe else timeframe
                    if effective_ema_tf != timeframe:
                        # Fetch HTF OHLCV for EMA — needs its own warmup window
                        htf_bar_ms    = _TF_MS.get(effective_ema_tf, bar_ms)
                        htf_fetch_ms  = since_ms - htf_bar_ms * (ema_period + 100)
                        htf_limit     = max(1, int((until_ms - htf_fetch_ms) / htf_bar_ms)) + 5
                        raw_htf = exchange.fetch_ohlcv(
                            symbol, effective_ema_tf,
                            since=htf_fetch_ms,
                            limit=min(htf_limit, 1000)
                        )
                        htf_closes    = np.array([b[4] for b in raw_htf], dtype=float)
                        htf_timestamps = [b[0] for b in raw_htf]
                        htf_ema_arr   = talib.EMA(htf_closes, timeperiod=ema_period)

                        # Build EMA series for the visible window (HTF timestamps)
                        ema_series: list = []
                        for j, ts_ms_htf in enumerate(htf_timestamps):
                            if ts_ms_htf < since_ms or ts_ms_htf > until_ms:
                                continue
                            val = float(htf_ema_arr[j]) if (j < len(htf_ema_arr) and not np.isnan(htf_ema_arr[j])) else None
                            if val is not None:
                                ema_series.append({
                                    "time": datetime.fromtimestamp(ts_ms_htf / 1000, tz=timezone.utc).isoformat(),
                                    "value": val,
                                })
                        indicators_out["ema"] = {
                            "values":    ema_series,
                            "period":    ema_period,
                            "timeframe": effective_ema_tf,
                        }
                    else:
                        # Same timeframe — compute EMA on the main LTF closes array
                        indicators_raw["ema"] = talib.EMA(closes, timeperiod=ema_period)

                if rsi_period > 0:
                    indicators_raw["rsi"] = talib.RSI(closes, timeperiod=rsi_period)

                if adx_period > 0:
                    indicators_raw["adx"] = talib.ADX(highs, lows, closes, timeperiod=adx_period)

            # ── 3. Build visible candles (trim warmup) ──────────────────────
            candles = []
            indicator_series: dict = {k: [] for k in indicators_raw}

            for i, ts_ms in enumerate(timestamps):
                if ts_ms > until_ms:
                    break
                dt_iso = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).isoformat()

                # Only include candles in the visible window (after warmup)
                if ts_ms >= since_ms:
                    candles.append({
                        "time":   dt_iso,
                        "open":   opens[i],
                        "high":   highs[i],
                        "low":    lows[i],
                        "close":  closes[i],
                        "volume": volumes[i],
                    })

                    # Include indicator values for visible range (LTF indicators only)
                    for key, arr in indicators_raw.items():
                        val = float(arr[i]) if (i < len(arr) and not np.isnan(arr[i])) else None
                        if val is not None:
                            indicator_series[key].append({"time": dt_iso, "value": val})

            # ── 4. Build response ────────────────────────────────────────────
            # EMA may already be in indicators_out (HTF case); only add LTF EMA if not yet set
            if "ema" not in indicators_out and "ema" in indicator_series and indicator_series["ema"]:
                indicators_out["ema"] = {
                    "values":    indicator_series["ema"],
                    "period":    ema_period,
                    "timeframe": timeframe,
                }

            if "rsi" in indicator_series and indicator_series["rsi"]:
                indicators_out["rsi"] = {
                    "values":       indicator_series["rsi"],
                    "period":       rsi_period,
                    "overbought":   rsi_overbought,
                    "oversold":     rsi_oversold,
                }

            if "adx" in indicator_series and indicator_series["adx"]:
                indicators_out["adx"] = {
                    "values":    indicator_series["adx"],
                    "period":    adx_period,
                    "threshold": adx_threshold,
                }

            return {"candles": candles, "indicators": indicators_out}


        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, fetch_and_compute)

        _ohlcv_cache_set(cache_key, result)
        logger.info(
            f"OHLCV fetched: {symbol} {timeframe} → {len(result['candles'])} candles, "
            f"indicators: {list(result['indicators'].keys())}"
        )
        return result

    except Exception as e:
        logger.error(f"Error fetching OHLCV for {symbol} {timeframe}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch OHLCV data: {str(e)}")



if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)




