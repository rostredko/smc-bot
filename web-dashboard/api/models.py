"""Pydantic models for API request/response and internal state."""

from typing import Dict, List, Optional, Any

from pydantic import BaseModel, ConfigDict

from engine.execution_settings import DEFAULT_EXECUTION_MODE


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
    strategy: str = "bt_price_action"
    strategy_config: Dict[str, Any] = {}
    trailing_stop_distance: float = 0.04
    breakeven_trigger_r: float = 1.5
    dynamic_position_sizing: bool = True
    taker_fee: Optional[float] = None  # Legacy percent input; prefer *_fee_bps fields.
    maker_fee_bps: Optional[float] = None
    taker_fee_bps: Optional[float] = None
    exchange: str = "binance"
    exchange_type: str = "future"
    execution_mode: str = DEFAULT_EXECUTION_MODE
    fee_source: Optional[str] = None
    loaded_template_name: Optional[str] = None
    position_cap_adverse: float = 0.5  # Worst-case gap for position cap (0.5=50%). Lower = larger positions.
    slippage_bps: float = 0.0
    funding_rate_per_8h: float = 0.0
    funding_interval_hours: int = 8
    log_level: str = "INFO"
    live_output_log_level: str = "INFO"


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
    config: Optional[Dict[str, Any]] = None
    should_cancel: bool = False  # Flag to signal cancellation
    engine: Optional[Any] = None  # Reference to BacktestEngine for cancellation
