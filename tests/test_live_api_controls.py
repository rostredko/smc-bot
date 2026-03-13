import os
import sys
import asyncio
import logging
import threading
import time
import math
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest
from fastapi.testclient import TestClient

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "web-dashboard"))
sys.path.insert(0, PROJECT_ROOT)

from server import (
    app,
    live_trading_state,
    run_live_trading_task,
    run_backtest_task,
    running_backtests,
    BacktestStatus,
    active_connections,
    _build_ohlcv_indicator_key,
    get_strategy_config_schema,
    WS_CLEAR_CONSOLE_SIGNAL,
    broadcast_from_queue,
    _broadcast_shutdown,
    connection_lock,
    ws_log_queue,
    _build_chart_data_for_trades,
    _emit_live_output_message,
)
from engine.logger import PROJECT_ROOT_LOGGER, clear_ws_log_queue, setup_logging
from db.connection import get_database
from db.repositories import UserConfigRepository


client = TestClient(app)


def _reset_live_state():
    live_trading_state["is_running"] = False
    live_trading_state["engine"] = None
    live_trading_state["start_time"] = None
    live_trading_state["stop_requested"] = False


def _reset_backtest_state(run_id: str):
    running_backtests.pop(run_id, None)


def _clear_project_log_handlers():
    logging.getLogger(PROJECT_ROOT_LOGGER).handlers.clear()


def _mock_chart_df(rows: int = 300) -> pd.DataFrame:
    idx = pd.date_range("2025-01-01", periods=rows, freq="h")
    close = [10000 + i * 2 for i in range(rows)]
    return pd.DataFrame(
        {
            "open": close,
            "high": [c + 5 for c in close],
            "low": [c - 5 for c in close],
            "close": [c + 1 for c in close],
            "volume": [1000.0] * rows,
        },
        index=idx,
    )


def _mock_chart_df_wave(rows: int = 300) -> pd.DataFrame:
    idx = pd.date_range("2025-01-01", periods=rows, freq="h")
    closes = [10000 + 320 * math.sin(i / 6.0) for i in range(rows)]
    opens = [closes[i - 1] if i > 0 else closes[0] for i in range(rows)]
    highs = [max(o, c) + 25 for o, c in zip(opens, closes)]
    lows = [min(o, c) - 25 for o, c in zip(opens, closes)]
    return pd.DataFrame(
        {
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": [1000.0] * rows,
        },
        index=idx,
    )


def test_stop_live_accepts_request_before_engine_is_attached():
    _reset_live_state()
    live_trading_state["is_running"] = True

    resp = client.post("/api/live/stop")
    assert resp.status_code == 200
    assert live_trading_state["stop_requested"] is True

    _reset_live_state()


def test_emit_live_output_message_uses_logger_when_ws_handler_is_active():
    clear_ws_log_queue()
    setup_logging(level="debug", ws_level="info", run_id="run_test", enable_ws=True)

    try:
        asyncio.run(_emit_live_output_message("hello", level=logging.INFO))
        assert ws_log_queue.get_nowait() == "[run_test] hello"
    finally:
        clear_ws_log_queue()
        _clear_project_log_handlers()


def test_emit_live_output_message_preserves_prefix_override():
    clear_ws_log_queue()
    setup_logging(level="debug", ws_level="info", run_id="run_test", enable_ws=True)

    try:
        asyncio.run(_emit_live_output_message("[LIVE] Starting live trading engine...", level=logging.INFO, ws_prefix_override=""))
        assert ws_log_queue.get_nowait() == "[LIVE] Starting live trading engine..."
    finally:
        clear_ws_log_queue()
        _clear_project_log_handlers()


def test_emit_live_output_message_falls_back_to_direct_broadcast_without_ws_handler():
    _clear_project_log_handlers()

    with patch("server.broadcast_message", new=AsyncMock()) as mock_broadcast:
        asyncio.run(_emit_live_output_message("[LIVE] Starting live trading engine...", level=logging.INFO))
        mock_broadcast.assert_awaited_once_with("[LIVE] Starting live trading engine...")


def test_cancel_backtest_calls_engine_cancel():
    run_id = f"bt_cancel_{uuid4().hex[:8]}"
    status = BacktestStatus(run_id=run_id, status="running", progress=0.0, message="")
    status.engine = MagicMock()
    running_backtests[run_id] = status

    try:
        resp = client.delete(f"/backtest/{run_id}")
        assert resp.status_code == 200
        assert status.should_cancel is True
        status.engine.cancel.assert_called_once()
    finally:
        _reset_backtest_state(run_id)


def test_cancel_active_backtest_uses_latest_running_run_id():
    old_run = f"bt_old_{uuid4().hex[:6]}"
    new_run = f"bt_new_{uuid4().hex[:6]}"
    old_status = BacktestStatus(run_id=old_run, status="running", progress=10.0, message="")
    new_status = BacktestStatus(run_id=new_run, status="running", progress=20.0, message="")
    old_status.engine = MagicMock()
    new_status.engine = MagicMock()
    running_backtests[old_run] = old_status
    running_backtests[new_run] = new_status

    try:
        resp = client.post("/backtest/active/stop")
        assert resp.status_code == 200
        new_status.engine.cancel.assert_called_once()
        old_status.engine.cancel.assert_not_called()
        assert new_status.should_cancel is True
    finally:
        _reset_backtest_state(old_run)
        _reset_backtest_state(new_run)


def test_nested_user_config_flatten_includes_position_cap_adverse():
    repo = UserConfigRepository()
    name = f"tmp_cfg_{uuid4().hex[:8]}"
    nested = {
        "account": {
            "initial_capital": 15000,
            "risk_per_trade": 1.2,
            "max_drawdown": 25,
            "leverage": 5,
        },
        "trading": {"symbol": "ETH/USDT", "timeframes": ["4h", "1h"]},
        "period": {"start_date": "2025-01-01", "end_date": "2025-03-01"},
        "strategy": {"name": "bt_price_action", "config": {"use_trend_filter": True}},
        "position_cap_adverse": 0.7,
    }
    repo.save(name, nested)

    try:
        resp = client.get(f"/api/user-configs/{name}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["position_cap_adverse"] == 0.7
        assert data["symbol"] == "ETH/USDT"
        assert data["strategy"] == "bt_price_action"
    finally:
        repo.delete(name)


def test_ohlcv_indicator_key_includes_ema_timeframe():
    key_1h = _build_ohlcv_indicator_key(
        timeframe="1h",
        ema_period=200,
        ema_timeframe="1h",
        rsi_period=14,
        rsi_overbought=70,
        rsi_oversold=30,
        adx_period=14,
        adx_threshold=21,
        atr_period=14,
        fractal_period=2,
    )
    key_4h = _build_ohlcv_indicator_key(
        timeframe="1h",
        ema_period=200,
        ema_timeframe="4h",
        rsi_period=14,
        rsi_overbought=70,
        rsi_oversold=30,
        adx_period=14,
        adx_threshold=21,
        atr_period=14,
        fractal_period=2,
    )
    assert key_1h != key_4h
    assert "@4h" in key_4h


def test_bt_price_action_schema_defaults_match_runtime_defaults():
    schema = get_strategy_config_schema("bt_price_action")
    assert schema["use_rsi_filter"]["default"] is True
    assert schema["use_adx_filter"]["default"] is True
    assert schema["adx_threshold"]["default"] == 30
    assert schema["min_range_factor"]["default"] == 1.2
    assert schema["risk_reward_ratio"]["default"] == 2.0
    assert schema["sl_buffer_atr"]["default"] == 1.5
    assert schema["use_premium_discount_filter"]["default"] is False
    assert schema["use_space_to_target_filter"]["default"] is False
    assert schema["space_to_target_min_rr"]["default"] == 2.0
    assert schema["use_choch_displacement_filter"]["default"] is False
    assert schema["choch_displacement_atr_mult"]["default"] == 1.5
    assert schema["require_choch_fvg"]["default"] is False


def test_clear_ohlcv_cache_endpoint_clears_mongo_cache():
    db = get_database()
    col = db["ohlcv_cache"]
    col.insert_one(
        {
            "exchange": "binance",
            "exchange_type": "future",
            "symbol": "BTC/USDT",
            "timeframe": "1h",
            "timestamp": int(time.time() * 1000),
            "open": 1.0,
            "high": 1.0,
            "low": 1.0,
            "close": 1.0,
            "volume": 1.0,
            "cached_at": "2026-03-06T00:00:00Z",
        }
    )
    assert col.count_documents({}) >= 1

    resp = client.post("/api/ohlcv/cache/clear")
    assert resp.status_code == 200
    assert col.count_documents({}) == 0


def test_chart_data_builder_omits_rsi_adx_when_filters_disabled():
    df = _mock_chart_df()
    loader = MagicMock()
    loader.get_data.return_value = df
    trade = {
        "entry_time": "2025-01-05T00:00:00Z",
        "exit_time": "2025-01-06T00:00:00Z",
    }
    config = {
        "symbol": "BTC/USDT",
        "timeframes": ["1h"],
        "start_date": "2025-01-01",
        "end_date": "2025-02-01",
        "exchange_type": "future",
        "strategy_config": {
            "use_trend_filter": True,
            "use_rsi_filter": False,
            "use_rsi_momentum": False,
            "use_adx_filter": False,
            "rsi_period": 14,
            "adx_period": 14,
        },
    }

    _build_chart_data_for_trades([trade], config, data_loader=loader, context_bars=10)

    indicators = trade.get("chart_data", {}).get("indicators", {})
    assert "rsi" not in indicators
    assert "adx" not in indicators


def test_chart_data_builder_uses_strategy_thresholds_for_rsi_adx():
    df = _mock_chart_df()
    loader = MagicMock()
    loader.get_data.return_value = df
    trade = {
        "entry_time": "2025-01-05T00:00:00Z",
        "exit_time": "2025-01-06T00:00:00Z",
    }
    config = {
        "symbol": "BTC/USDT",
        "timeframes": ["1h"],
        "start_date": "2025-01-01",
        "end_date": "2025-02-01",
        "exchange_type": "future",
        "strategy_config": {
            "use_trend_filter": True,
            "use_rsi_filter": True,
            "use_rsi_momentum": False,
            "use_adx_filter": True,
            "rsi_period": 14,
            "rsi_overbought": 80,
            "rsi_oversold": 20,
            "adx_period": 14,
            "adx_threshold": 37,
        },
    }

    _build_chart_data_for_trades([trade], config, data_loader=loader, context_bars=10)

    indicators = trade.get("chart_data", {}).get("indicators", {})
    assert indicators["rsi"]["overbought"] == 80
    assert indicators["rsi"]["oversold"] == 20
    assert indicators["adx"]["threshold"] == 37


def test_chart_data_builder_includes_structure_levels():
    df_1h = _mock_chart_df_wave()
    df_4h = (
        df_1h.resample("4h")
        .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
        .dropna()
    )
    loader = MagicMock()

    def _get_data(symbol, timeframe, start, end):
        return df_4h if timeframe == "4h" else df_1h

    loader.get_data.side_effect = _get_data
    trade = {
        "entry_time": "2025-01-05T00:00:00Z",
        "exit_time": "2025-01-06T12:00:00Z",
    }
    config = {
        "symbol": "BTC/USDT",
        "timeframes": ["4h", "1h"],
        "start_date": "2025-01-01",
        "end_date": "2025-02-01",
        "exchange_type": "future",
        "strategy_config": {
            "use_trend_filter": False,
            "use_rsi_filter": False,
            "use_rsi_momentum": False,
            "use_adx_filter": False,
            "market_structure_pivot_span": 2,
        },
    }

    _build_chart_data_for_trades([trade], config, data_loader=loader, context_bars=20)

    indicators = trade.get("chart_data", {}).get("indicators", {})
    assert "sh_level" in indicators
    assert "sl_level" in indicators
    assert len(indicators["sh_level"]["values"]) > 0
    assert len(indicators["sl_level"]["values"]) > 0


def test_chart_data_builder_includes_fractal_markers():
    rows = 240
    idx = pd.date_range("2025-01-01", periods=rows, freq="h")
    # Smooth wave with slight drift to guarantee strict local maxima/minima.
    centers = [10000.0 + 180.0 * math.sin(i / 6.0) + 0.02 * i for i in range(rows)]
    amplitudes = [18.0 + 2.0 * math.sin(i / 17.0) for i in range(rows)]
    closes = [centers[i] + 3.0 * math.sin(i / 2.0) for i in range(rows)]
    opens = [closes[i - 1] if i > 0 else closes[0] for i in range(rows)]
    highs = [centers[i] + amplitudes[i] for i in range(rows)]
    lows = [centers[i] - amplitudes[i] for i in range(rows)]
    df = pd.DataFrame(
        {
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": [1000.0] * rows,
        },
        index=idx,
    )
    loader = MagicMock()
    loader.get_data.return_value = df
    trade = {
        "entry_time": "2025-01-02T00:00:00Z",
        "exit_time": "2025-01-08T00:00:00Z",
    }
    config = {
        "symbol": "BTC/USDT",
        "timeframes": ["1h"],
        "start_date": "2025-01-01",
        "end_date": "2025-02-01",
        "exchange_type": "future",
        "strategy_config": {
            "use_trend_filter": False,
            "use_rsi_filter": False,
            "use_rsi_momentum": False,
            "use_adx_filter": False,
            "market_structure_pivot_span": 2,
        },
    }

    _build_chart_data_for_trades([trade], config, data_loader=loader, context_bars=20)

    indicators = trade.get("chart_data", {}).get("indicators", {})
    assert "fractal_high" in indicators
    assert "fractal_low" in indicators
    assert len(indicators["fractal_high"]["values"]) > 0
    assert len(indicators["fractal_low"]["values"]) > 0


def test_websocket_disconnect_cleans_active_connections():
    before = len(active_connections)

    with client.websocket_connect("/ws"):
        assert len(active_connections) >= before + 1

    for _ in range(20):
        if len(active_connections) <= before:
            break
        time.sleep(0.05)

    assert len(active_connections) <= before


def test_start_backtest_clears_live_output_before_launch():
    with patch("server.run_backtest_task", new=AsyncMock()), \
         patch("server.clear_ws_log_queue", return_value=7) as clear_queue, \
         patch("server.broadcast_message", new=AsyncMock()) as broadcast:
        resp = client.post(
            "/backtest/start",
            json={"config": {"strategy": "bt_price_action", "symbol": "BTC/USDT", "timeframes": ["1h"]}},
        )

    assert resp.status_code == 200
    clear_queue.assert_called_once()
    assert any(
        call.args and call.args[0] == WS_CLEAR_CONSOLE_SIGNAL
        for call in broadcast.await_args_list
    )
    run_id = resp.json().get("run_id")
    if run_id:
        _reset_backtest_state(run_id)


def test_start_live_clears_live_output_before_launch():
    _reset_live_state()
    with patch("server.run_live_trading_task", new=AsyncMock()), \
         patch("server.clear_ws_log_queue", return_value=3) as clear_queue, \
         patch("server.broadcast_message", new=AsyncMock()) as broadcast:
        resp = client.post(
            "/api/live/start",
            json={"config": {"strategy": "fast_test_strategy", "symbol": "BTC/USDT", "timeframes": ["1m"]}},
        )

    assert resp.status_code == 200
    clear_queue.assert_called_once()
    assert any(
        call.args and call.args[0] == WS_CLEAR_CONSOLE_SIGNAL
        for call in broadcast.await_args_list
    )
    _reset_live_state()


@pytest.mark.asyncio
@patch("server.setup_logging")
@patch("server.DataLoader")
@patch("server.BacktestRepository")
@patch("server.BTLiveEngine")
async def test_live_task_saves_history_even_with_empty_metrics(
    engine_cls,
    repo_cls,
    loader_cls,
    _setup_logging,
):
    _reset_live_state()

    engine = MagicMock()
    engine.closed_trades = []
    engine.equity_curve = []
    engine.run_live.return_value = {}
    engine_cls.return_value = engine

    repo = MagicMock()
    repo_cls.return_value = repo

    with patch("server.broadcast_message", new=AsyncMock()):
        await run_live_trading_task(
            {
                "symbol": "BTC/USDT",
                "timeframes": ["1m"],
                "strategy": "fast_test_strategy",
                "initial_capital": 10000,
            }
        )

    assert repo.save.called
    assert repo.save.call_args.kwargs.get("is_live") is True
    saved_doc = repo.save.call_args.args[1]
    assert saved_doc.get("total_trades") == 0
    assert saved_doc.get("trades") == []
    assert saved_doc.get("signals_generated") == 0
    assert saved_doc.get("log_file", "").endswith(".log")
    assert isinstance(saved_doc.get("logs"), list)
    assert isinstance(saved_doc.get("log_lines_total"), int)
    if saved_doc.get("log_file"):
        try:
            os.remove(saved_doc["log_file"])
        except OSError:
            pass
    loader_cls.assert_not_called()


@pytest.mark.asyncio
@patch("server.setup_logging")
@patch("server.BacktestRepository")
@patch("server.resolve_strategy_class")
@patch("server.build_runtime_strategy_config")
@patch("server.BTBacktestEngine")
async def test_backtest_task_sets_cancelled_status_when_engine_returns_cancelled(
    engine_cls,
    runtime_cfg_builder,
    strategy_resolver,
    repo_cls,
    _setup_logging,
):
    run_id = f"bt_cancelled_{uuid4().hex[:8]}"
    running_backtests[run_id] = BacktestStatus(
        run_id=run_id,
        status="running",
        progress=0.0,
        message="Starting backtest...",
    )

    class _DummyStrategy:
        pass

    engine = MagicMock()
    engine.run_backtest.return_value = {"cancelled": True}
    engine.should_cancel = True
    engine.closed_trades = []
    engine.equity_curve = []
    engine_cls.return_value = engine
    runtime_cfg_builder.return_value = {}
    strategy_resolver.return_value = _DummyStrategy
    repo = MagicMock()
    repo_cls.return_value = repo

    with patch("server.broadcast_message", new=AsyncMock()):
        await run_backtest_task(
            run_id,
            {
                "strategy": "bt_price_action",
                "symbol": "BTC/USDT",
                "timeframes": ["1h"],
                "initial_capital": 10000,
            },
        )

    try:
        status = running_backtests[run_id]
        assert status.status == "cancelled"
        assert status.message == "Backtest cancelled. Partial results saved."
        assert status.progress == 100.0
        assert status.results is not None
        assert status.results.get("cancelled") is True
        assert repo.save.called
    finally:
        try:
            os.remove(os.path.join(PROJECT_ROOT, "logs", "runs", f"{run_id}.log"))
        except OSError:
            pass
        _reset_backtest_state(run_id)


@pytest.mark.asyncio
@patch("server.setup_logging")
@patch("server._build_chart_data_for_trades")
@patch("server.BacktestRepository")
@patch("server.resolve_strategy_class")
@patch("server.build_runtime_strategy_config")
@patch("server.BTBacktestEngine")
async def test_backtest_task_persists_run_log_metadata(
    engine_cls,
    runtime_cfg_builder,
    strategy_resolver,
    repo_cls,
    _chart_builder,
    _setup_logging,
):
    run_id = f"bt_logs_{uuid4().hex[:8]}"
    running_backtests[run_id] = BacktestStatus(
        run_id=run_id,
        status="running",
        progress=0.0,
        message="Starting backtest...",
    )

    class _DummyStrategy:
        pass

    def _fake_run_backtest():
        import logging
        logging.getLogger("backtrade.test").warning("TEST RUN LOG LINE")
        return {
            "initial_capital": 10000.0,
            "final_capital": 10010.0,
            "total_pnl": 10.0,
            "max_drawdown": 1.5,
            "win_rate": 50.0,
            "profit_factor": 1.1,
            "total_trades": 2,
            "win_count": 1,
            "loss_count": 1,
            "avg_win": 20.0,
            "avg_loss": -10.0,
            "sharpe_ratio": 0.2,
        }

    engine = MagicMock()
    engine.run_backtest.side_effect = _fake_run_backtest
    engine.should_cancel = False
    engine.closed_trades = []
    engine.equity_curve = []
    engine.data_loader = MagicMock()
    engine_cls.return_value = engine
    runtime_cfg_builder.return_value = {}
    strategy_resolver.return_value = _DummyStrategy
    repo = MagicMock()
    repo_cls.return_value = repo

    with patch("server.broadcast_message", new=AsyncMock()):
        await run_backtest_task(
            run_id,
            {
                "strategy": "bt_price_action",
                "symbol": "BTC/USDT",
                "timeframes": ["1h"],
                "initial_capital": 10000,
                "start_date": "2025-01-01",
                "end_date": "2025-01-31",
            },
        )

    try:
        assert repo.save.called
        saved_doc = repo.save.call_args.args[1]
        assert saved_doc.get("log_file", "").endswith(f"{run_id}.log")
        assert isinstance(saved_doc.get("logs"), list)
        assert any("TEST RUN LOG LINE" in line for line in saved_doc.get("logs", []))
        assert saved_doc.get("log_lines_total", 0) >= len(saved_doc.get("logs", []))
        if saved_doc.get("log_file"):
            try:
                os.remove(saved_doc["log_file"])
            except OSError:
                pass
    finally:
        _reset_backtest_state(run_id)


@pytest.mark.asyncio
@patch("server.setup_logging")
@patch("server.BacktestRepository")
@patch("server.resolve_strategy_class")
@patch("server.build_runtime_strategy_config")
@patch("server.BTBacktestEngine")
async def test_backtest_task_respects_cancel_requested_before_engine_attach(
    engine_cls,
    runtime_cfg_builder,
    strategy_resolver,
    repo_cls,
    _setup_logging,
):
    run_id = f"bt_pre_cancel_{uuid4().hex[:8]}"
    status = BacktestStatus(
        run_id=run_id,
        status="running",
        progress=0.0,
        message="Starting backtest...",
    )
    status.should_cancel = True
    running_backtests[run_id] = status

    class _DummyStrategy:
        pass

    engine = MagicMock()
    engine.run_backtest.return_value = {"cancelled": True}
    engine.should_cancel = False
    engine.closed_trades = []
    engine.equity_curve = []
    engine_cls.return_value = engine
    runtime_cfg_builder.return_value = {}
    strategy_resolver.return_value = _DummyStrategy
    repo = MagicMock()
    repo_cls.return_value = repo

    with patch("server.broadcast_message", new=AsyncMock()):
        await run_backtest_task(
            run_id,
            {
                "strategy": "bt_price_action",
                "symbol": "BTC/USDT",
                "timeframes": ["1h"],
                "initial_capital": 10000,
            },
        )

    try:
        engine.cancel.assert_called()
        assert running_backtests[run_id].status == "cancelled"
        assert running_backtests[run_id].results is not None
        assert running_backtests[run_id].results.get("cancelled") is True
    finally:
        try:
            os.remove(os.path.join(PROJECT_ROOT, "logs", "runs", f"{run_id}.log"))
        except OSError:
            pass
        _reset_backtest_state(run_id)


@pytest.mark.asyncio
async def test_broadcast_from_queue_yields_under_log_burst_without_connections():
    with connection_lock:
        active_connections.clear()

    while True:
        try:
            ws_log_queue.get_nowait()
        except Exception:
            break

    _broadcast_shutdown.clear()
    stop_event = threading.Event()

    def _producer():
        i = 0
        while not stop_event.is_set():
            try:
                ws_log_queue.put_nowait(f"burst-{i}")
                i += 1
            except Exception:
                pass

    producer = threading.Thread(target=_producer, daemon=True)
    producer.start()
    task = asyncio.create_task(broadcast_from_queue())

    try:
        await asyncio.sleep(0.2)
        _broadcast_shutdown.set()
        stop_event.set()
        producer.join(timeout=1.0)
        await asyncio.wait_for(task, timeout=1.0)
    finally:
        stop_event.set()
        _broadcast_shutdown.set()
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        _broadcast_shutdown.clear()
        while True:
            try:
                ws_log_queue.get_nowait()
            except Exception:
                break
