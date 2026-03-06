"""
FastAPI Web Server for Backtrade Machine.
Provides REST API endpoints for web dashboard integration.
"""

import os
import asyncio
import sys
import threading
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from pathlib import Path
from uuid import uuid4
from collections import deque

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT_DIR = os.path.dirname(CURRENT_DIR)
if CURRENT_DIR not in sys.path:
    sys.path.append(CURRENT_DIR)
if PROJECT_ROOT_DIR not in sys.path:
    sys.path.append(PROJECT_ROOT_DIR)

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, BackgroundTasks, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict

from engine.bt_backtest_engine import BTBacktestEngine
from engine.bt_live_engine import BTLiveEngine
from engine.data_loader import DataLoader
from engine.logger import (
    get_logger,
    setup_logging,
    ws_log_queue,
    suppress_ws_logging,
    clear_ws_log_queue,
)
from services.strategy_runtime import resolve_strategy_class, build_runtime_strategy_config
from services.result_mapper import (
    map_backtest_trades,
    map_live_trades,
    build_backtest_metrics_doc,
    build_live_metrics_doc,
    build_equity_series,
)

from db import get_database, is_database_available, init_db
from db.repositories import BacktestRepository, UserConfigRepository, AppConfigRepository

setup_logging(enable_ws=False)
logger = get_logger("server")

BASE_DIR = Path(__file__).parent.parent.absolute()
DATA_DIR = str(BASE_DIR / "data_cache")
VERSION_FILE = BASE_DIR / "VERSION"


def _read_version() -> str:
    """Read semantic version from VERSION file."""
    if VERSION_FILE.exists():
        return VERSION_FILE.read_text().strip()
    return "1.0.0"


APP_VERSION = _read_version()
WS_CLEAR_CONSOLE_SIGNAL = "__BTM_CLEAR_CONSOLE__"
RUN_LOGS_DIR = BASE_DIR / "logs" / "runs"
RUN_LOG_CAPTURE_MAX_LINES = 12000
RUN_LOG_DB_TAIL_LINES = 400

os.makedirs(DATA_DIR, exist_ok=True)

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    if not is_database_available():
        logger.error("MongoDB not available. Set MONGODB_URI and ensure MongoDB is running.")
        raise RuntimeError("Database required. MongoDB not available.")
    logger.info("Database storage enabled")
    broadcast_task = asyncio.create_task(broadcast_from_queue())
    yield
    _broadcast_shutdown.set()
    try:
        await asyncio.wait_for(broadcast_task, timeout=2.0)
    except (asyncio.CancelledError, asyncio.TimeoutError):
        broadcast_task.cancel()
        try:
            await broadcast_task
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title="Backtrade Machine API",
    description="REST API for Backtrade Machine",
    version=APP_VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if os.path.exists("dist"):
    app.mount("/static", StaticFiles(directory="dist"), name="static")


class BacktestConfig(BaseModel):
    initial_capital: float = 10000
    risk_per_trade: float = 1.5
    max_drawdown: float = 20.0
    leverage: float = 10.0
    symbol: str = "BTC/USDT"
    timeframes: List[str] = ["4h", "15m"]
    start_date: str = "2025-01-01"
    end_date: str = "2025-12-31"
    confluence_required: str = "false"
    strategy: str = "smc_strategy"
    strategy_config: Dict[str, Any] = {}
    trailing_stop_distance: float = 0.04
    breakeven_trigger_r: float = 1.5
    dynamic_position_sizing: bool = True
    taker_fee: float = 0.04  # Default 0.04%
    exchange: str = "binance"
    exchange_type: str = "future"
    loaded_template_name: Optional[str] = None
    position_cap_adverse: float = 0.5  # Worst-case gap for position cap (0.5=50%). Lower = larger positions.


class BacktestRequest(BaseModel):
    config: BacktestConfig
    run_id: Optional[str] = None


class BacktestStatus(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    run_id: str
    status: str  # "running", "completed", "failed", "cancelled"
    progress: float = 0.0
    message: str = ""
    results: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    should_cancel: bool = False  # Flag to signal cancellation
    engine: Optional[Any] = None  # Reference to BacktestEngine for cancellation


running_backtests: Dict[str, BacktestStatus] = {}
active_connections: List[WebSocket] = []
connection_lock = threading.Lock()

live_trading_state: Dict[str, Any] = {
    "is_running": False,
    "engine": None,
    "start_time": None,
    "stop_requested": False,
}

strategy_schema_cache: Dict[str, Dict[str, Any]] = {}
_broadcast_shutdown: asyncio.Event = asyncio.Event()


def _latest_running_backtest_run_id() -> Optional[str]:
    """Return the newest run_id still in running state."""
    for rid, status in reversed(list(running_backtests.items())):
        if status.status == "running":
            return rid
    return None


class _RunLogCollector(logging.Handler):
    """Collects tail logs for persistence in run result payloads."""

    def __init__(self, max_lines: int = RUN_LOG_CAPTURE_MAX_LINES):
        super().__init__(level=logging.INFO)
        self._lines = deque(maxlen=max_lines)
        self._lock = threading.Lock()
        self.total_count = 0

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record).rstrip("\n")
        except Exception:
            self.handleError(record)
            return
        with self._lock:
            self._lines.append(msg)
            self.total_count += 1

    def get_tail(self, max_lines: int = RUN_LOG_DB_TAIL_LINES) -> List[str]:
        with self._lock:
            if max_lines <= 0:
                return []
            lines = list(self._lines)
        return lines[-max_lines:]


def _attach_run_log_handlers(run_id: str) -> tuple[_RunLogCollector, logging.FileHandler, str]:
    """Attach per-run file and in-memory log handlers to the project root logger."""
    RUN_LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_file_path = RUN_LOGS_DIR / f"{run_id}.log"
    fmt = logging.Formatter(
        "%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.FileHandler(log_file_path, encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(fmt)

    collector = _RunLogCollector(max_lines=RUN_LOG_CAPTURE_MAX_LINES)
    collector.setFormatter(fmt)

    root_logger = logging.getLogger("backtrade")
    root_logger.addHandler(file_handler)
    root_logger.addHandler(collector)
    return collector, file_handler, str(log_file_path)


def _detach_run_log_handlers(*handlers: Optional[logging.Handler]) -> None:
    """Detach and close run-specific handlers safely."""
    root_logger = logging.getLogger("backtrade")
    for handler in handlers:
        if handler is None:
            continue
        if handler in root_logger.handlers:
            root_logger.removeHandler(handler)
        try:
            handler.flush()
        except Exception:
            pass
        try:
            handler.close()
        except Exception:
            pass


def _attach_run_log_metadata(
    payload: Dict[str, Any],
    collector: Optional[_RunLogCollector],
    log_file_path: Optional[str],
) -> None:
    """Embed log metadata into saved run payload."""
    if collector is None:
        payload["logs"] = []
        payload["log_lines_total"] = 0
        return
    payload["logs"] = collector.get_tail(RUN_LOG_DB_TAIL_LINES)
    payload["log_lines_total"] = collector.total_count
    if log_file_path:
        payload["log_file"] = log_file_path


async def _prepare_live_output_for_new_run() -> None:
    """
    Clear buffered WS logs and notify connected clients to reset Live Output.
    """
    dropped = clear_ws_log_queue()
    if dropped > 0:
        logger.debug(f"Cleared {dropped} queued WS log messages before new run")
    await broadcast_message(WS_CLEAR_CONSOLE_SIGNAL)


async def broadcast_from_queue():
    """Periodically drain ws_log_queue and broadcast messages to WebSocket clients."""
    while not _broadcast_shutdown.is_set():
        try:
            processed = 0
            max_batch = 300
            while processed < max_batch:
                try:
                    message = ws_log_queue.get_nowait()
                except Exception:
                    break

                processed += 1
                with connection_lock:
                    connections_copy = active_connections.copy()

                if not connections_copy:
                    # No subscribers: drop queued line and continue.
                    continue

                for connection in connections_copy:
                    try:
                        await connection.send_text(message)
                    except Exception:
                        with connection_lock:
                            if connection in active_connections:
                                active_connections.remove(connection)

                # Yield periodically to keep HTTP API responsive during log bursts.
                if processed % 50 == 0:
                    await asyncio.sleep(0)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.debug(f"Broadcaster loop error: {e}")

        await asyncio.sleep(0.02)


_EXCLUDED_STRATEGY_FILES = frozenset({"__init__.py", "base_strategy.py"})


def load_available_strategies():
    """Load available strategies from strategies directory."""
    strategies_dir = BASE_DIR / "strategies"
    if not strategies_dir.exists():
        return []
    return [
        {
            "name": f.stem,
            "display_name": f.stem.replace("_", " ").title(),
            "description": f"{f.stem} strategy",
            "config_schema": get_strategy_config_schema(f.stem),
        }
        for f in strategies_dir.glob("*.py")
        if f.name not in _EXCLUDED_STRATEGY_FILES
    ]


def get_strategy_config_schema(strategy_name: str):
    """Get configuration schema for a strategy - returns hardcoded schemas."""
    if strategy_name in strategy_schema_cache:
        return strategy_schema_cache[strategy_name]
    
    default_schemas = {
        "smc_strategy": {
            "mode": {"type": "string", "default": "spot"},
            "allow_short": {"type": "boolean", "default": False},
            "high_timeframe": {"type": "string", "default": "4h"},
            "low_timeframe": {"type": "string", "default": "15m"},
            "risk_per_trade_pct": {"type": "number", "default": 0.3},
            "max_concurrent_positions": {"type": "number", "default": 3},
            "min_required_rr": {"type": "number", "default": 2.0},
            "max_stop_distance_pct": {"type": "number", "default": 0.04},
            "volatility_filter_enabled": {"type": "boolean", "default": True},
            "atr_period": {"type": "number", "default": 14},
            "atr_percentile_min": {"type": "number", "default": 30},
            "atr_percentile_max": {"type": "number", "default": 70},
            "sl_atr_multiplier": {"type": "number", "default": 2.0},
            "min_signal_confidence": {"type": "number", "default": 0.4},
            "ema_filter_period": {"type": "number", "default": 50},
            "rsi_period": {"type": "number", "default": 14},
            "min_rsi_long": {"type": "number", "default": 35},
            "max_rsi_long": {"type": "number", "default": 70},
            "volume_threshold": {"type": "number", "default": 1.3},
            "use_partial_tp": {"type": "boolean", "default": True},
            "tp1_r": {"type": "number", "default": 1.0},
            "tp1_pct": {"type": "number", "default": 0.5},
            "tp2_r": {"type": "number", "default": 2.0},
            "tp2_pct": {"type": "number", "default": 0.3},
            "runner_pct": {"type": "number", "default": 0.2},
            "trailing_stop_enabled": {"type": "boolean", "default": True},
            "trail_start": {"type": "number", "default": 1.5},
            "trail_step": {"type": "number", "default": 0.3},
            "breakeven_move_enabled": {"type": "boolean", "default": True},
            "require_structure_confirmation": {"type": "boolean", "default": True},
            "support_level_lookback_bars": {"type": "number", "default": 20},
            "cooldown_after_loss_bars": {"type": "number", "default": 10},
            "reduce_risk_after_loss": {"type": "boolean", "default": True},
            "risk_reduction_after_loss": {"type": "number", "default": 0.6},
            "min_notional": {"type": "number", "default": 10.0},
            "taker_fee": {"type": "number", "default": 0.0004},
        },
        "simple_test_strategy": {
            "threshold": {"type": "number", "default": 0.5},
            "use_volume": {"type": "boolean", "default": False},
            "ema_period": {"type": "number", "default": 20},
            "rsi_period": {"type": "number", "default": 14},
            "rsi_threshold": {"type": "number", "default": 30}
        },
        "bt_price_action": {
            "use_trend_filter": {"type": "boolean", "default": True},
            "trend_ema_period": {"type": "number", "default": 200},
            
            "use_rsi_filter": {"type": "boolean", "default": True},
            "rsi_period": {"type": "number", "default": 14},
            "rsi_overbought": {"type": "number", "default": 70},
            "rsi_oversold": {"type": "number", "default": 30},
            
            "use_rsi_momentum": {"type": "boolean", "default": False},
            "rsi_momentum_threshold": {"type": "number", "default": 60},
            
            "use_adx_filter": {"type": "boolean", "default": True},
            "adx_period": {"type": "number", "default": 14},
            "adx_threshold": {"type": "number", "default": 30},
            "min_range_factor": {"type": "number", "default": 1.2},
            "min_wick_to_range": {"type": "number", "default": 0.6},
            "max_body_to_range": {"type": "number", "default": 0.3},

            "risk_reward_ratio": {"type": "number", "default": 2.0},
            "sl_buffer_atr": {"type": "number", "default": 1.5},

            "pattern_hammer": {"type": "boolean", "default": True},
            "pattern_inverted_hammer": {"type": "boolean", "default": True},
            "pattern_shooting_star": {"type": "boolean", "default": True},
            "pattern_hanging_man": {"type": "boolean", "default": True},
            "pattern_bullish_engulfing": {"type": "boolean", "default": True},
            "pattern_bearish_engulfing": {"type": "boolean", "default": True}
        },
        "fast_test_strategy": {
            "sl_mult": {"type": "number", "default": 0.35},
            "tp_mult": {"type": "number", "default": 0.55},
            "atr_period": {"type": "number", "default": 7},
            "fixed_size": {"type": "number", "default": 0.001},
            "min_fallback_size": {"type": "number", "default": 0.001},
            "force_signal_every_n_bars": {"type": "number", "default": 1},
            "max_hold_bars": {"type": "number", "default": 1},
            "stop_after_n_trades": {"type": "number", "default": 0},
        }
    }
    
    default_schemas["price_action_strategy"] = default_schemas["bt_price_action"]
    
    schema = default_schemas.get(strategy_name, {})
    strategy_schema_cache[strategy_name] = schema
    return schema


@app.get("/")
async def root():
    """Serve the main dashboard page."""
    if os.path.exists("dist/index.html"):
        return FileResponse("dist/index.html")
    else:
        return {"message": "SMC Trading Engine API", "version": APP_VERSION, "error": "Frontend not built. Run 'npm run build' first."}


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


def _config_to_flat(config: Dict[str, Any]) -> Dict[str, Any]:
    account = config.get("account", {})
    trading = config.get("trading", {})
    period = config.get("period", {})
    strategy_section = config.get("strategy", {})
    return {
        "initial_capital": account.get("initial_capital", 10000),
        "risk_per_trade": account.get("risk_per_trade", 2.0),
        "max_drawdown": account.get("max_drawdown", 15.0),
        "leverage": account.get("leverage", 10.0),
        "symbol": trading.get("symbol", "BTC/USDT"),
        "timeframes": trading.get("timeframes", ["4h", "15m"]),
        "start_date": period.get("start_date", "2023-01-01"),
        "end_date": period.get("end_date", "2023-12-31"),
        "strategy": strategy_section.get("name", "smc_strategy"),
        "strategy_config": strategy_section.get("config", {}),
        "trailing_stop_distance": config.get("trailing_stop_distance", 0.04),
        "breakeven_trigger_r": config.get("breakeven_trigger_r", 1.5),
        "dynamic_position_sizing": config.get("dynamic_position_sizing", True),
        "position_cap_adverse": config.get("position_cap_adverse", 0.5),
    }


@app.get("/config")
async def get_config():
    """Get current configuration in flat format for frontend."""
    config = AppConfigRepository().get()
    if config:
        return _config_to_flat(config)
    return {}


@app.post("/config")
async def update_config(config: Dict[str, Any]):
    """Update configuration."""
    existing_config = AppConfigRepository().get()

    for section in ("account", "trading", "period", "strategy"):
        if section not in existing_config:
            existing_config[section] = {}

    for key in ("initial_capital", "risk_per_trade", "max_drawdown", "leverage"):
        if key in config:
            existing_config["account"][key] = config[key]
    for key in ("symbol", "timeframes"):
        if key in config:
            existing_config["trading"][key] = config[key]
    for key in ("start_date", "end_date"):
        if key in config:
            existing_config["period"][key] = config[key]
    if "strategy" in config:
        existing_config["strategy"]["name"] = config["strategy"]
    if "strategy_config" in config:
        existing_config["strategy"]["config"] = config["strategy_config"]
    for key in ("trailing_stop_distance", "breakeven_trigger_r", "dynamic_position_sizing"):
        if key in config:
            existing_config[key] = config[key]
    if "position_cap_adverse" in config:
        existing_config["position_cap_adverse"] = config["position_cap_adverse"]

    AppConfigRepository().save(existing_config)
    return {"message": "Configuration updated"}


@app.get("/config/live")
async def get_live_config():
    """Get live trading configuration from DB."""
    config = AppConfigRepository().get_live_config()
    if not config:
        return {}
    masked = dict(config)
    if masked.get("secret"):
        masked["secret"] = "***"
    if masked.get("apiKey"):
        masked["apiKey"] = masked["apiKey"][:4] + "***" if len(masked["apiKey"]) > 4 else "***"
    return masked


def _is_masked(value: Any) -> bool:
    return value in (None, "", "***") or (isinstance(value, str) and value.endswith("***") and len(value) <= 7)


@app.post("/config/live")
async def update_live_config(config: Dict[str, Any]):
    """Save live trading configuration to DB."""
    existing = AppConfigRepository().get_live_config()
    for key in ("exchange", "apiKey", "secret", "sandbox", "symbol", "timeframes",
                "initial_capital", "risk_per_trade", "max_drawdown",
                "leverage", "poll_interval", "strategy_config"):
        if key in config and not (key in ("apiKey", "secret") and _is_masked(config[key])):
            existing[key] = config[key]
    if "account" in config:
        existing.setdefault("account", {}).update(config["account"])
    if "trading" in config:
        existing.setdefault("trading", {}).update(config["trading"])
    AppConfigRepository().save_live_config(existing)
    return {"message": "Live config updated"}


@app.get("/api/user-configs")
async def list_user_configs():
    """List all saved user configurations (by priority if set, else newest first)."""
    return {"configs": UserConfigRepository().list_names_sorted_by_priority()}


@app.get("/api/user-configs/{name}")
async def get_user_config(name: str):
    """Get a specific user configuration."""
    if "/" in name or "\\" in name or ".." in name:
        raise HTTPException(status_code=400, detail="Invalid configuration name")
    data = UserConfigRepository().get(name)
    if data is None:
        raise HTTPException(status_code=404, detail="Configuration not found")
    
    # Flatten it if it's in the nested format
    if "trading" in data or "account" in data or "period" in data:
        return _config_to_flat(data)
    return data


@app.post("/api/user-configs/{name}")
async def save_user_config(name: str, config: Dict[str, Any]):
    """Save a user configuration."""
    if "/" in name or "\\" in name or ".." in name:
        raise HTTPException(status_code=400, detail="Invalid configuration name")
    UserConfigRepository().save(name, config)
    return {"message": f"Configuration '{name}' saved successfully"}


@app.delete("/api/user-configs/{name}")
async def delete_user_config(name: str):
    """Delete a user configuration."""
    if "/" in name or "\\" in name or ".." in name:
        raise HTTPException(status_code=400, detail="Invalid configuration name")
    if not UserConfigRepository().delete(name):
        raise HTTPException(status_code=404, detail="Configuration not found")
    return {"message": f"Configuration '{name}' deleted successfully"}


class ReorderConfigsRequest(BaseModel):
    order: List[str]


@app.put("/api/user-configs/reorder")
async def reorder_user_configs(req: ReorderConfigsRequest):
    """Save template priority order (first in list = highest priority)."""
    for name in req.order:
        if "/" in name or "\\" in name or ".." in name:
            raise HTTPException(status_code=400, detail=f"Invalid configuration name: {name}")
    UserConfigRepository().save_template_order(req.order)
    return {"message": "Order saved", "configs": UserConfigRepository().list_names_sorted_by_priority()}


@app.post("/backtest/start")
async def start_backtest(request: BacktestRequest, background_tasks: BackgroundTasks):
    """Start a new backtest."""
    if request.run_id:
        run_id = request.run_id
    else:
        run_id = f"backtest_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}"
    
    if run_id in running_backtests:
        raise HTTPException(status_code=400, detail=f"Backtest {run_id} is already running")
    
    if len(running_backtests) > 20:
        for k in list(running_backtests.keys())[:-20]:
            del running_backtests[k]

    await _prepare_live_output_for_new_run()

    running_backtests[run_id] = BacktestStatus(
        run_id=run_id,
        status="running",
        progress=0.0,
        message="Starting backtest..."
    )
    
    background_tasks.add_task(run_backtest_task, run_id, request.config.dict())
    
    return {"run_id": run_id, "status": "started"}


@app.get("/backtest/status/{run_id}")
async def get_backtest_status(run_id: str):
    """Get backtest status."""
    if run_id not in running_backtests:
        raise HTTPException(status_code=404, detail="Backtest not found")
    
    status = running_backtests[run_id]
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
    ids = BacktestRepository().list_ids()
    return {"results": [f"{rid}.json" for rid in ids]}


def _default_configuration_for_legacy_backtest() -> Dict[str, Any]:
    """Default configuration for old backtests that lack configuration. Matches PriceActionStrategy defaults."""
    return {
        "symbol": "BTC/USDT",
        "timeframes": ["1h"],
        "exchange": "binance",
        "exchange_type": "future",
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
            "adx_threshold": 30,
            "min_range_factor": 1.2,
            "risk_reward_ratio": 2.0,
            "sl_buffer_atr": 1.5,
        },
    }


@app.get("/results/{filename}")
async def get_result_file(filename: str):
    """Get specific backtest result. Backfills configuration for legacy records."""
    repo = BacktestRepository()
    data = repo.get_by_filename(filename)
    if data is None:
        raise HTTPException(status_code=404, detail="Result not found")
    if not data.get("configuration"):
        data["configuration"] = _default_configuration_for_legacy_backtest()
        run_id = filename[:-5] if filename.endswith(".json") else filename
        repo.save(run_id, data)
    return data



@app.get("/api/backtest/history")
async def get_backtest_history(
    page: int = 1, 
    page_size: int = 10,
    sort_field: Optional[str] = None,
    sort_direction: Optional[str] = None
):
    """Get paginated history of backtests with summary metrics."""
    history, total_count = BacktestRepository().list_paginated(
        page=page, 
        page_size=page_size,
        sort_field=sort_field,
        sort_direction=sort_direction
    )
    total_pages = (total_count + page_size - 1) // page_size if total_count > 0 else 0
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
        if status.engine:
            try:
                status.engine.cancel()
            except Exception:
                status.engine.should_cancel = True
        status.message = "Cancellation requested..."
    
    return {"message": "Backtest cancellation requested"}


@app.post("/backtest/active/stop")
async def cancel_active_backtest():
    """Cancel the most recent running backtest when run_id is unknown on the client."""
    run_id = _latest_running_backtest_run_id()
    if run_id is None:
        raise HTTPException(status_code=404, detail="No running backtest found")
    return await cancel_backtest(run_id)


@app.delete("/api/backtest/history/{filename}")
async def delete_backtest_result(filename: str):
    """Delete a specific backtest result. Accepts run_id with or without .json suffix."""
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    if not BacktestRepository().delete_by_filename(filename):
        raise HTTPException(status_code=404, detail="Not found")
    return {"message": f"Successfully deleted {filename}"}


class LiveStartRequest(BaseModel):
    model_config = ConfigDict(extra='allow')
    config: Dict[str, Any]

@app.post("/api/live/start")
async def start_live_trading(request: LiveStartRequest, background_tasks: BackgroundTasks):
    """Start the live (paper) trading engine."""
    global live_trading_state
    if live_trading_state["is_running"]:
        raise HTTPException(status_code=400, detail="Live trading is already running")
    
    config = request.config
    if not config:
        raise HTTPException(status_code=400, detail="Live configuration not found")

    await _prepare_live_output_for_new_run()

    live_trading_state["is_running"] = True
    live_trading_state["start_time"] = datetime.now().isoformat()
    live_trading_state["stop_requested"] = False
    await broadcast_message("[LIVE] Starting live trading engine...\n")
    
    background_tasks.add_task(run_live_trading_task, config)
    return {"message": "Live trading started"}


@app.post("/api/live/stop")
async def stop_live_trading():
    """Stop the live (paper) trading engine."""
    global live_trading_state
    if not live_trading_state["is_running"]:
        raise HTTPException(status_code=400, detail="Live trading is not running")
    live_trading_state["stop_requested"] = True

    engine = live_trading_state["engine"]
    await broadcast_message("[LIVE] Stopping live trading engine...\n")
    if engine:
        engine.stop()  # Signals the stop_event
    return {"message": "Live trading stop signal sent"}


@app.get("/api/live/status")
async def get_live_status():
    """Get status of the live trading engine."""
    global live_trading_state
    status = {
        "is_running": live_trading_state["is_running"],
        "start_time": live_trading_state["start_time"],
        "stop_requested": live_trading_state.get("stop_requested", False),
        "current_equity": None,
        "initial_capital": None,
        "open_trades": 0
    }
    
    engine = live_trading_state.get("engine")
    if status["is_running"] and engine and hasattr(engine, "cerebro") and engine.cerebro:
        try:
            status["current_equity"] = engine.cerebro.broker.getvalue()
            status["initial_capital"] = engine.cerebro.broker.startingcash
        except Exception:
            pass
            
    return status


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time console output."""
    await websocket.accept()
    
    with connection_lock:
        active_connections.append(websocket)
    
    try:
        while True:
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
            except asyncio.TimeoutError:
                # Keep connection alive and periodically check for disconnects.
                continue
    except WebSocketDisconnect:
        with connection_lock:
            if websocket in active_connections:
                active_connections.remove(websocket)


async def broadcast_message(message: str):
    """Broadcast message to all connected WebSocket clients."""
    with connection_lock:
        connections_copy = active_connections.copy()
    
    for connection in connections_copy:
        try:
            await connection.send_text(message)
        except Exception:
            with connection_lock:
                if connection in active_connections:
                    active_connections.remove(connection)

async def run_live_trading_task(config: Dict[str, Any]):
    """Background task to run the live trading engine and save results upon stopping."""
    global live_trading_state
    
    run_id = f"live_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}"
    session_start = datetime.now()
    signal_counter = None
    _root_logger = None
    run_log_collector: Optional[_RunLogCollector] = None
    run_log_file_handler: Optional[logging.FileHandler] = None
    run_log_path: Optional[str] = None

    try:
        import logging as _logging
        setup_logging(level=_logging.INFO, run_id=run_id, enable_ws=True)
        run_log_collector, run_log_file_handler, run_log_path = _attach_run_log_handlers(run_id)

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
        
        engine = BTLiveEngine(config)
        st_config = build_runtime_strategy_config(config)
        strategy_name = config.get('strategy', 'bt_price_action')
        strategy_class = resolve_strategy_class(strategy_name)
        engine.add_strategy(strategy_class, **st_config)
        
        live_trading_state["engine"] = engine
        if live_trading_state.get("stop_requested"):
            await broadcast_message(f"[{run_id}] Stop requested before engine start; stopping now.\n")
            engine.stop()
        
        await broadcast_message(f"[{run_id}] Live engine loop starting...\n")
        
        loop = asyncio.get_event_loop()
        # run_live will block until engine.stop() is called
        metrics = await loop.run_in_executor(None, engine.run_live)
        session_end = datetime.now()

        await broadcast_message(f"[{run_id}] Live trading stopped. Saving results...\n")
        
        safe_metrics = metrics if isinstance(metrics, dict) else {}
        if signal_counter is not None:
            safe_metrics["signals_generated"] = int(signal_counter.count)
        trades_data = map_live_trades(engine.closed_trades)

        # For fast stop/save flow in live mode, chart_data prebuild is OFF by default.
        # UI can lazy-load chart candles/indicators on trade details open via /api/ohlcv.
        if bool(config.get("live_attach_chart_data", False)) and trades_data:
            chart_start = (session_start - timedelta(days=1)).strftime("%Y-%m-%d")
            chart_end = (session_end + timedelta(hours=1)).strftime("%Y-%m-%d")
            live_engine_config = {**config, "start_date": chart_start, "end_date": chart_end}
            try:
                chart_limit = int(config.get("live_chart_trades_limit", 20))
                chart_limit = max(0, chart_limit)
                trades_for_chart = trades_data[:chart_limit] if chart_limit > 0 else []
                if trades_for_chart:
                    # Keep Live Output clean: suppress WS logs for post-stop chart prebuild.
                    with suppress_ws_logging():
                        loader = DataLoader(
                            exchange_name=config.get("exchange", "binance"),
                            exchange_type=config.get("exchange_type", "future"),
                        )
                        _build_chart_data_for_trades(
                            trades_for_chart,
                            live_engine_config,
                            data_loader=loader,
                            context_bars=25,
                        )
                if len(trades_data) > chart_limit > 0:
                    logger.debug(f"chart_data added to first {chart_limit} live trades (total {len(trades_data)} — MongoDB size limit)")
                elif chart_limit > 0:
                    logger.debug(f"chart_data added to {len(trades_for_chart)} live trades")
            except Exception as chart_err:
                logger.warning(f"Live chart_data build failed: {chart_err}")
        
        equity_data = build_equity_series(engine.equity_curve, max_points=None)
        mapped_metrics = build_live_metrics_doc(
            config=config,
            metrics=safe_metrics,
            trades_data=trades_data,
            equity_data=equity_data,
            session_start=session_start,
            session_end=session_end,
        )
        _attach_run_log_metadata(mapped_metrics, run_log_collector, run_log_path)
        
        # Save into repository as live
        BacktestRepository().save(run_id, mapped_metrics, is_live=True)
        await broadcast_message(f"[{run_id}] Live run saved to history.\n")
            
    except Exception as e:
        logger.error(f"Error in live trading task: {e}")
        await broadcast_message(f"[LIVE ERROR] {e}\n")
    finally:
        if _root_logger is not None and signal_counter is not None:
            try:
                _root_logger.removeHandler(signal_counter)
            except Exception:
                pass
        _detach_run_log_handlers(run_log_collector, run_log_file_handler)
        live_trading_state["is_running"] = False
        live_trading_state["engine"] = None
        live_trading_state["start_time"] = None
        live_trading_state["stop_requested"] = False
        await broadcast_message(f"[{run_id}] Live engine fully stopped. All processes terminated.\n")
        setup_logging(enable_ws=False)



async def run_backtest_task(run_id: str, config: Dict[str, Any]):
    """Background task to run backtest."""
    signal_counter = None
    _root_logger = None
    run_log_collector: Optional[_RunLogCollector] = None
    run_log_file_handler: Optional[logging.FileHandler] = None
    run_log_path: Optional[str] = None

    try:
        running_backtests[run_id].message = "Initializing engine..."
        running_backtests[run_id].progress = 10.0
        await broadcast_message(f"[{run_id}] Initializing engine...\n")
        
        taker_fee_pct = config.get('taker_fee', 0.04)
        commission = taker_fee_pct / 100.0
        
        engine_config = {
            'initial_capital': config.get('initial_capital', 10000),
            'risk_per_trade': config.get('risk_per_trade', 2.0),
            'max_drawdown': config.get('max_drawdown', 15.0),
            'leverage': config.get('leverage', 10.0),
            'symbol': config.get('symbol', 'BTC/USDT'),
            'timeframes': config.get('timeframes', ['4h', '15m']),
            'exchange': config.get('exchange', 'binance'),
            'exchange_type': config.get('exchange_type', 'future'),
            'start_date': config.get('start_date', '2023-01-01'),
            'end_date': config.get('end_date', '2023-12-31'),
            'strategy': config.get('strategy', 'smc_strategy'),
            'strategy_config': config.get('strategy_config', {}),
            'trailing_stop_distance': config.get('trailing_stop_distance', 0.04),
            'breakeven_trigger_r': config.get('breakeven_trigger_r', 1.5),
            'dynamic_position_sizing': config.get('dynamic_position_sizing', True),
            'position_cap_adverse': config.get('position_cap_adverse', 0.5),
            'commission': commission,
            'taker_fee': taker_fee_pct,
            'log_level': 'INFO',
            'detailed_signals': True,
            'detailed_trades': True,
            'market_analysis': True,
            'save_results': True,
        }
        if config.get('loaded_template_name'):
            engine_config['loaded_template_name'] = config['loaded_template_name']
        
        await broadcast_message(f"[{run_id}] ============================================================\n")
        await broadcast_message(f"[{run_id}] BACKTEST CONFIGURATION\n")
        await broadcast_message(f"[{run_id}] ============================================================\n")
        await broadcast_message(f"[{run_id}] Strategy: {engine_config['strategy']}\n")
        await broadcast_message(f"[{run_id}] Symbol: {engine_config['symbol']}\n")
        await broadcast_message(f"[{run_id}] Commission (Taker): {engine_config['taker_fee']}% ({engine_config['commission']})\n")
        await broadcast_message(f"[{run_id}] Timeframes: {', '.join(engine_config['timeframes'])}\n")
        await broadcast_message(f"[{run_id}] Period: {engine_config['start_date']} to {engine_config['end_date']}\n")
        await broadcast_message(f"[{run_id}] Initial Capital: ${engine_config['initial_capital']:,.2f}\n")
        await broadcast_message(f"[{run_id}] Risk Per Trade: {engine_config['risk_per_trade']}%\n")
        await broadcast_message(f"[{run_id}] Max Drawdown: {engine_config['max_drawdown']}%\n")
        await broadcast_message(f"[{run_id}] Leverage: {engine_config['leverage']}x\n")
        await broadcast_message(f"[{run_id}] Trailing Stop Distance: {engine_config['trailing_stop_distance']}\n")
        await broadcast_message(f"[{run_id}] Breakeven Trigger (R): {engine_config['breakeven_trigger_r']}\n")
        await broadcast_message(f"[{run_id}] Dynamic Position Sizing: {engine_config['dynamic_position_sizing']}\n")
        await broadcast_message(f"[{run_id}] Position Cap Adverse: {engine_config.get('position_cap_adverse', 0.5)} (worst-case gap)\n")
        if engine_config['strategy_config']:
            await broadcast_message(f"[{run_id}] Strategy Config: {engine_config['strategy_config']}\n")
        await broadcast_message(f"[{run_id}] ============================================================\n")
        
        import logging as _logging
        setup_logging(level=_logging.INFO, run_id=run_id, enable_ws=True)
        run_log_collector, run_log_file_handler, run_log_path = _attach_run_log_handlers(run_id)

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
            await broadcast_message(f"[{run_id}] Creating engine instance...\n")
            engine = BTBacktestEngine(engine_config)
            running_backtests[run_id].engine = engine

            if running_backtests[run_id].should_cancel:
                engine.cancel()
                running_backtests[run_id].message = "Cancellation acknowledged before run start. Finalizing partial results..."
                await broadcast_message(f"[{run_id}] Cancellation requested before execution. Preparing partial results...\n")
            
            st_config = build_runtime_strategy_config(engine_config)
            strategy_name = engine_config.get('strategy', 'bt_price_action')
            strategy_class = resolve_strategy_class(strategy_name)
            engine.add_strategy(strategy_class, **st_config)

            if running_backtests[run_id].should_cancel and not engine.should_cancel:
                engine.cancel()
            
            await broadcast_message(f"[{run_id}] ✅ Engine created\n")
            
            running_backtests[run_id].message = "Loading data..."
            running_backtests[run_id].progress = 30.0

            await broadcast_message(f"[{run_id}] Starting engine.run_backtest()...\n")
            
            loop = asyncio.get_event_loop()
            metrics = await loop.run_in_executor(None, engine.run_backtest)
            if not isinstance(metrics, dict):
                metrics = {}

            cancel_requested = bool(
                running_backtests[run_id].should_cancel
                or engine.should_cancel
                or bool(metrics.get("cancelled"))
            )
            if cancel_requested:
                running_backtests[run_id].message = "Cancellation acknowledged. Finalizing partial results..."
                running_backtests[run_id].progress = 75.0
                await broadcast_message(f"[{run_id}] Cancellation acknowledged. Finalizing partial results...\n")
            
            await broadcast_message(f"[{run_id}] ✅ engine.run_backtest() completed\n")
            
            mapped_metrics = None
            
            try:
                metrics['signals_generated'] = signal_counter.count
                
                trades_data = map_backtest_trades(engine.closed_trades)

                # MongoDB 16MB limit: chart_data only for first 75 trades to avoid "document too large"
                chart_limit = 75
                trades_for_chart = trades_data[:chart_limit] if len(trades_data) > chart_limit else trades_data
                try:
                    _build_chart_data_for_trades(trades_for_chart, engine_config, data_loader=engine.data_loader, context_bars=25)
                    if len(trades_data) > chart_limit:
                        logger.info(f"chart_data added to first {chart_limit} trades only (total {len(trades_data)} — MongoDB size limit)")
                except Exception as chart_err:
                    logger.warning(f"chart_data build failed: {chart_err}")
                
                equity_data = build_equity_series(engine.equity_curve, max_points=100)
                mapped_metrics = build_backtest_metrics_doc(
                    engine_config=engine_config,
                    metrics=metrics,
                    trades_data=trades_data,
                    equity_data=equity_data,
                    signals_generated=signal_counter.count,
                )
                mapped_metrics["cancelled"] = cancel_requested
                _attach_run_log_metadata(mapped_metrics, run_log_collector, run_log_path)
                
                metrics.update(mapped_metrics)
                metrics["cancelled"] = cancel_requested
                _attach_run_log_metadata(metrics, run_log_collector, run_log_path)
                
                running_backtests[run_id].results = metrics
                running_backtests[run_id].progress = 100.0
                
            except Exception as e:
                import traceback
                error_trace = traceback.format_exc()
                logger.error(f"Error processing backtest data: {e}\n{error_trace}")
                await broadcast_message(f"[{run_id}] ⚠️ Error processing backtest data: {str(e)}\n")
            
            running_backtests[run_id].message = "Generating report..."
            await broadcast_message(f"[{run_id}] Generating report...\n")
            
            try:
                BacktestRepository().save(run_id, metrics)
                await broadcast_message(f"[{run_id}] ✅ Results saved to database\n")
                await asyncio.sleep(0.5)
            except Exception as e:
                import traceback
                logger.error(f"Error saving results: {e}\n{traceback.format_exc()}")
                await broadcast_message(f"[{run_id}] ⚠️ Error saving results: {str(e)}\n")

            try:
                if mapped_metrics is None:
                    await broadcast_message(f"[{run_id}] ⚠️ Skipping report generation (metrics missing)\n")
                else:
                    await broadcast_message(f"[{run_id}] Generating detailed report...\n")
                    
                    init_cap = mapped_metrics.get('initial_capital', 1)
                    if init_cap == 0: init_cap = 1 # Avoid division by zero
                    
                    total_pnl = mapped_metrics.get('total_pnl', 0)
                    final_cap = mapped_metrics.get('final_capital', 0)
                    
                    return_pct = (total_pnl / init_cap) * 100
                    
                    summary_title = "BACKTEST PARTIAL RESULTS (CANCELLED)" if cancel_requested else "BACKTEST RESULTS SUMMARY"
                    summary_lines = [
                        "============================================================",
                        summary_title,
                        "============================================================",
                        f"Status:           {'CANCELLED (partial run)' if cancel_requested else 'COMPLETED'}",
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
                    
                    await broadcast_message(f"[{run_id}] Backtest Summary:\n")
                    await asyncio.sleep(0.1)
                    
                    for line in summary_lines:
                         await broadcast_message(f"[{run_id}] {line}\n")
                         await asyncio.sleep(0.2)
                    await broadcast_message(f"[{run_id}] Report generated. Finalizing...\n")
                    await asyncio.sleep(1.0)

                if cancel_requested:
                    running_backtests[run_id].status = "cancelled"
                    running_backtests[run_id].message = "Backtest cancelled. Partial results saved."
                    await broadcast_message(f"[{run_id}] Backtest cancelled. Partial results saved to history.\n")
                else:
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
            if _root_logger is not None and signal_counter is not None:
                _root_logger.removeHandler(signal_counter)
            _detach_run_log_handlers(run_log_collector, run_log_file_handler)
            setup_logging(enable_ws=False)
        
    except Exception as e:
        running_backtests[run_id].status = "failed"
        running_backtests[run_id].message = f"Backtest failed: {str(e)}"
        running_backtests[run_id].error = str(e)
        await broadcast_message(f"[{run_id}] ERROR: {str(e)}\n")



import ccxt

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
    
    if SYMBOLS_CACHE["data"] and (now - SYMBOLS_CACHE["timestamp"] < CACHE_DURATION_SECONDS):
        return {"symbols": SYMBOLS_CACHE["data"][:limit]}

    try:
        def fetch_from_exchange():
            exchange = ccxt.binance({'enableRateLimit': True})
            tickers = exchange.fetch_tickers()
            
            valid_pairs = []
            EXCLUDED_PATTERNS = ('UP/', 'DOWN/', 'BEAR/', 'BULL/')
            EXCLUDED_EXACT = frozenset([
                'USDC/USDT', 'FDUSD/USDT', 'TUSD/USDT', 'USDP/USDT', 'BUSD/USDT',
                'DAI/USDT', 'EUR/USDT', 'GBP/USDT', 'PAXG/USDT', 'WBTC/USDT',
                'USTC/USDT', 'USD1/USDT', 'ZAMA/USDT', 'USDE/USDT'
            ])
            
            for symbol, ticker in tickers.items():
                if not symbol.endswith('/USDT'):
                    continue
                if symbol in EXCLUDED_EXACT:
                    continue
                if any(p in symbol for p in EXCLUDED_PATTERNS):
                    continue

                quote_vol = ticker.get('quoteVolume', 0)
                if quote_vol:
                    valid_pairs.append((symbol, quote_vol))
            
            valid_pairs.sort(key=lambda x: x[1], reverse=True)
            
            return [p[0] for p in valid_pairs[:50]]  # Keep top 50 in cache

        loop = asyncio.get_event_loop()
        top_symbols = await loop.run_in_executor(None, fetch_from_exchange)
        
        SYMBOLS_CACHE = {
            "data": top_symbols,
            "timestamp": now
        }
        
        return {"symbols": top_symbols[:limit]}
        
    except Exception as e:
        logger.error(f"Error fetching top symbols: {e}")
        if SYMBOLS_CACHE["data"]:
             return {"symbols": SYMBOLS_CACHE["data"][:limit]}
        return {"symbols": ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT"]}


from collections import OrderedDict
from datetime import timezone

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


def _build_ohlcv_indicator_key(
    timeframe: str,
    ema_period: int,
    ema_timeframe: str,
    rsi_period: int,
    rsi_overbought: float,
    rsi_oversold: float,
    adx_period: int,
    adx_threshold: float,
    atr_period: int,
) -> str:
    effective_ema_tf = ema_timeframe if ema_timeframe else timeframe
    return (
        f"ema{ema_period}@{effective_ema_tf}"
        f"_rsi{rsi_period}-{rsi_overbought}-{rsi_oversold}"
        f"_adx{adx_period}-{adx_threshold}"
        f"_atr{atr_period}"
    )


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


def _build_chart_data_for_trades(
    trades: List[Dict],
    config: Dict[str, Any],
    data_loader: Optional[Any] = None,
    context_bars: int = 25,
) -> None:
    """
    Enrich each trade with chart_data (candles + indicators) from the SAME DataLoader
    used by the backtest. Single source of truth — chart shows exactly what the strategy saw.
    Modifies trades in place.
    Pass data_loader from engine to avoid re-initializing exchange and re-loading data.
    """
    if not trades:
        return
    import numpy as np
    try:
        import talib
    except ImportError:
        try:
            import TA_Lib as talib
        except ImportError:
            logger.warning("TA-Lib not available — chart_data skipped")
            return

    symbol = config.get("symbol", "BTC/USDT")
    timeframes = config.get("timeframes", ["1h"])
    start_date = config.get("start_date", "")[:10]
    end_date = config.get("end_date", "")[:10]
    strat_cfg = config.get("strategy_config", {})
    exchange_type = config.get("exchange_type", "future")

    chart_tf = min(timeframes, key=lambda t: _TF_MS.get(t, 3600000)) if timeframes else "1h"
    ema_tf = max(timeframes, key=lambda t: _TF_MS.get(t, 0)) if len(timeframes) > 1 else chart_tf
    ema_period = 200 if strat_cfg.get("use_trend_filter", True) else 0
    rsi_period = strat_cfg.get("rsi_period", 14) or 14
    adx_period = strat_cfg.get("adx_period", 14) or 14
    atr_period = strat_cfg.get("atr_period", 14) or 14

    if not start_date or not end_date:
        return

    loader = data_loader if data_loader is not None else DataLoader(exchange_name="binance", exchange_type=exchange_type)
    df_full = loader.get_data(symbol, chart_tf, start_date, end_date)
    if df_full is None or df_full.empty:
        return

    bar_ms = _TF_MS.get(chart_tf, 3_600_000)
    timestamps = [int(ts.timestamp() * 1000) for ts in df_full.index]
    opens = df_full["open"].values.astype(float)
    highs = df_full["high"].values.astype(float)
    lows = df_full["low"].values.astype(float)
    closes = df_full["close"].values.astype(float)
    volumes = df_full["volume"].values.astype(float)

    indicators_raw = {}
    if ema_period > 0:
        if ema_tf != chart_tf:
            df_htf = loader.get_data(symbol, ema_tf, start_date, end_date)
            if df_htf is not None and not df_htf.empty:
                htf_closes = df_htf["close"].values.astype(float)
                htf_ema = talib.EMA(htf_closes, timeperiod=ema_period)
                htf_ts = [int(ts.timestamp() * 1000) for ts in df_htf.index]
                indicators_raw["_ema_htf"] = (htf_ts, htf_ema)
        else:
            indicators_raw["ema"] = talib.EMA(closes, timeperiod=ema_period)
    if rsi_period > 0:
        indicators_raw["rsi"] = talib.RSI(closes, timeperiod=rsi_period)
    if adx_period > 0:
        indicators_raw["adx"] = talib.ADX(highs, lows, closes, timeperiod=adx_period)
    if atr_period > 0:
        indicators_raw["atr"] = talib.ATR(highs, lows, closes, timeperiod=atr_period)

    def to_ms(iso: str) -> int:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1000)

    pad_ms = bar_ms * max(1, context_bars)

    for trade in trades:
        entry_iso = trade.get("entry_time") or ""
        exit_iso = trade.get("exit_time") or ""
        if not entry_iso or not exit_iso:
            continue
        since_ms = to_ms(entry_iso) - pad_ms
        until_ms = to_ms(exit_iso) + pad_ms

        out_candles = []
        out_indicators = {"ema": [], "rsi": [], "adx": [], "atr": []}

        for i, ts_ms in enumerate(timestamps):
            if ts_ms < since_ms:
                continue
            if ts_ms > until_ms:
                break
            dt_iso = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).isoformat()
            out_candles.append({
                "time": dt_iso,
                "open": float(opens[i]),
                "high": float(highs[i]),
                "low": float(lows[i]),
                "close": float(closes[i]),
                "volume": float(volumes[i]),
            })
            for key in ["rsi", "adx", "atr"]:
                if key in indicators_raw:
                    arr = indicators_raw[key]
                    val = float(arr[i]) if i < len(arr) and not np.isnan(arr[i]) else None
                    if val is not None:
                        out_indicators[key].append({"time": dt_iso, "value": val})
            if "ema" in indicators_raw:
                arr = indicators_raw["ema"]
                val = float(arr[i]) if i < len(arr) and not np.isnan(arr[i]) else None
                if val is not None:
                    out_indicators["ema"].append({"time": dt_iso, "value": val})
            elif "_ema_htf" in indicators_raw:
                htf_ts, htf_ema = indicators_raw["_ema_htf"]
                candidates = [idx for idx in range(len(htf_ts)) if htf_ts[idx] <= ts_ms]
                j = candidates[-1] if candidates else 0
                if j < len(htf_ema) and not np.isnan(htf_ema[j]):
                    out_indicators["ema"].append({"time": dt_iso, "value": float(htf_ema[j])})

        indicators_out = {}
        if out_indicators["ema"]:
            indicators_out["ema"] = {"values": out_indicators["ema"], "period": ema_period, "timeframe": ema_tf}
        if out_indicators["rsi"]:
            indicators_out["rsi"] = {"values": out_indicators["rsi"], "period": rsi_period, "overbought": 70, "oversold": 30}
        if out_indicators["adx"]:
            indicators_out["adx"] = {"values": out_indicators["adx"], "period": adx_period, "threshold": 25}
        if out_indicators["atr"]:
            indicators_out["atr"] = {"values": out_indicators["atr"], "period": atr_period}

        trade["chart_data"] = {"candles": out_candles, "indicators": indicators_out}

    logger.info(f"chart_data added to {len(trades)} trades (single source: DataLoader)")


@app.post("/api/ohlcv/cache/clear")
async def clear_ohlcv_cache(disk: bool = False):
    """Clear OHLCV caches. disk=True also removes data_cache/*.csv (forces re-fetch from exchange)."""
    _OHLCV_CACHE.clear()
    logger.info("OHLCV in-memory cache cleared")
    msg = "In-memory cache cleared"
    db_removed = 0
    try:
        if is_database_available():
            db = get_database()
            db_removed = db["ohlcv_cache"].delete_many({}).deleted_count
            logger.info(f"OHLCV Mongo cache cleared: {db_removed} documents removed")
            msg += f"; Mongo cache cleared ({db_removed} docs)"
    except Exception as e:
        logger.warning(f"Failed to clear Mongo OHLCV cache: {e}")
    if disk and os.path.isdir(DATA_DIR):
        removed = 0
        for f in os.listdir(DATA_DIR):
            if f.endswith(".csv"):
                try:
                    os.remove(os.path.join(DATA_DIR, f))
                    removed += 1
                except OSError:
                    pass
        logger.info(f"Removed {removed} files from data_cache")
        msg += f"; {removed} data_cache files removed"
    return {"message": msg}


@app.get("/api/ohlcv")
async def get_ohlcv(
    symbol: str = "BTC/USDT",
    timeframe: str = "1h",
    start: str = "",
    end: str = "",
    context_bars: int = 25,
    exchange_type: str = "future",
    backtest_start: str = "",
    backtest_end: str = "",
    ema_period: int = 0,
    ema_timeframe: str = "",
    rsi_period: int = 0,
    rsi_overbought: float = 70,
    rsi_oversold: float = 30,
    adx_period: int = 0,
    adx_threshold: float = 25,
    atr_period: int = 0,
):
    """
    Fetch OHLCV candlestick data + optional TA-Lib indicators.
    Indicator params (pass 0 to skip): ema_period, rsi_period, adx_period, atr_period.
    Returns candles and indicators (ema, rsi, adx, atr) with values per bar.
    """
    with suppress_ws_logging():
        return await _get_ohlcv_impl(
            symbol=symbol, timeframe=timeframe, start=start, end=end,
            context_bars=context_bars, exchange_type=exchange_type,
            backtest_start=backtest_start, backtest_end=backtest_end,
            ema_period=ema_period, ema_timeframe=ema_timeframe,
            rsi_period=rsi_period, rsi_overbought=rsi_overbought, rsi_oversold=rsi_oversold,
            adx_period=adx_period, adx_threshold=adx_threshold, atr_period=atr_period,
        )


async def _get_ohlcv_impl(
    symbol: str, timeframe: str, start: str, end: str,
    context_bars: int, exchange_type: str,
    backtest_start: str, backtest_end: str,
    ema_period: int, ema_timeframe: str,
    rsi_period: int, rsi_overbought: float, rsi_oversold: float,
    adx_period: int, adx_threshold: float, atr_period: int,
):
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

        warmup_bars = 300
        fetch_since_ms = since_ms - bar_ms * warmup_bars

        ind_key = _build_ohlcv_indicator_key(
            timeframe=timeframe,
            ema_period=ema_period,
            ema_timeframe=ema_timeframe,
            rsi_period=rsi_period,
            rsi_overbought=rsi_overbought,
            rsi_oversold=rsi_oversold,
            adx_period=adx_period,
            adx_threshold=adx_threshold,
            atr_period=atr_period,
        )
        use_cache = not (backtest_start and backtest_end)  # Never cache backtest requests — always use fresh DataLoader data
        cache_key = _ohlcv_cache_key(symbol, timeframe, since_ms, until_ms) + f"|{exchange_type}|" + ind_key
        if backtest_start and backtest_end:
            cache_key += f"|bt_{backtest_start}_{backtest_end}"

        if use_cache:
            cached = _ohlcv_cache_get(cache_key)
            if cached is not None:
                logger.debug(f"OHLCV+indicators cache hit: {cache_key}")
                return cached

        num_bars = max(1, int((until_ms - fetch_since_ms) / bar_ms)) + 2

        def fetch_and_compute():
            import numpy as np

            use_loader = bool(backtest_start and backtest_end)
            if use_loader:
                try:
                    loader = DataLoader(exchange_name="binance", exchange_type=exchange_type)
                    df_full = loader.get_data(symbol, timeframe, backtest_start[:10], backtest_end[:10])
                    if df_full is None or df_full.empty:
                        use_loader = False
                    else:
                        logger.info(f"OHLCV using DataLoader (backtest range {backtest_start[:10]}–{backtest_end[:10]}): {len(df_full)} bars")
                        timestamps = [int(ts.timestamp() * 1000) for ts in df_full.index]
                        opens   = df_full["open"].values.astype(float)
                        highs   = df_full["high"].values.astype(float)
                        lows    = df_full["low"].values.astype(float)
                        closes  = df_full["close"].values.astype(float)
                        volumes = df_full["volume"].values.astype(float)
                        exchange = None
                        fetch_symbol = symbol
                except Exception as e:
                    logger.warning(f"DataLoader fallback failed ({e}), using exchange fetch")
                    use_loader = False
            if not use_loader:
                if exchange_type == "future":
                    exchange = ccxt.binanceusdm({"enableRateLimit": True})
                    exchange.load_markets()
                    fetch_symbol = symbol if symbol in exchange.markets else f"{symbol}:USDT"
                else:
                    exchange = ccxt.binance({"enableRateLimit": True})
                    fetch_symbol = symbol
                raw = exchange.fetch_ohlcv(fetch_symbol, timeframe, since=fetch_since_ms, limit=min(num_bars, 1500))
                if not raw:
                    return {"candles": [], "indicators": {}}
                raw_arr = np.array(raw, dtype=float)
                timestamps = raw_arr[:, 0].astype(int).tolist()
                opens   = raw_arr[:, 1]
                highs   = raw_arr[:, 2]
                lows    = raw_arr[:, 3]
                closes  = raw_arr[:, 4]
                volumes = raw_arr[:, 5]

            indicators_raw: dict = {}
            indicators_out: dict = {}

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
                if ema_period > 0:
                    effective_ema_tf = ema_timeframe if ema_timeframe else timeframe
                    if effective_ema_tf != timeframe:
                        htf_bar_ms    = _TF_MS.get(effective_ema_tf, bar_ms)
                        htf_fetch_ms  = since_ms - htf_bar_ms * (ema_period + 100)
                        htf_limit     = max(1, int((until_ms - htf_fetch_ms) / htf_bar_ms)) + 5
                        if use_loader and backtest_start and backtest_end:
                            df_htf = loader.get_data(symbol, effective_ema_tf, backtest_start[:10], backtest_end[:10])
                            if df_htf is not None and not df_htf.empty:
                                htf_closes = df_htf["close"].values.astype(float)
                                htf_timestamps = [int(ts.timestamp() * 1000) for ts in df_htf.index]
                            else:
                                htf_closes = np.array([])
                                htf_timestamps = []
                        else:
                            raw_htf = exchange.fetch_ohlcv(
                                fetch_symbol, effective_ema_tf,
                                since=htf_fetch_ms,
                                limit=min(htf_limit, 1000)
                            )
                            raw_htf_arr   = np.array(raw_htf, dtype=float)
                            htf_closes    = raw_htf_arr[:, 4]
                            htf_timestamps = raw_htf_arr[:, 0].astype(int).tolist()
                        htf_ema_arr   = talib.EMA(htf_closes, timeperiod=ema_period) if len(htf_closes) > 0 else np.array([])

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
                        indicators_raw["ema"] = talib.EMA(closes, timeperiod=ema_period)

                if rsi_period > 0:
                    indicators_raw["rsi"] = talib.RSI(closes, timeperiod=rsi_period)

                if adx_period > 0:
                    indicators_raw["adx"] = talib.ADX(highs, lows, closes, timeperiod=adx_period)

                if atr_period > 0:
                    indicators_raw["atr"] = talib.ATR(highs, lows, closes, timeperiod=atr_period)

            candles = []
            indicator_series: dict = {k: [] for k in indicators_raw}

            for i, ts_ms in enumerate(timestamps):
                if ts_ms < since_ms:
                    continue
                if ts_ms > until_ms:
                    break
                dt_iso = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).isoformat()

                candles.append({
                    "time":   dt_iso,
                    "open":   opens[i],
                    "high":   highs[i],
                    "low":    lows[i],
                    "close":  closes[i],
                    "volume": volumes[i],
                })

                for key, arr in indicators_raw.items():
                    val = float(arr[i]) if (i < len(arr) and not np.isnan(arr[i])) else None
                    if val is not None:
                        indicator_series[key].append({"time": dt_iso, "value": val})

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

            if "atr" in indicator_series and indicator_series["atr"]:
                indicators_out["atr"] = {
                    "values": indicator_series["atr"],
                    "period": atr_period,
                }

            return {"candles": candles, "indicators": indicators_out}


        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, fetch_and_compute)

        if use_cache:
            _ohlcv_cache_set(cache_key, result)
        logger.debug(
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
