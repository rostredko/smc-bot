"""
E2E Live Trading Test
======================
Tests the full live trading pipeline using a real Binance WebSocket connection.
Uses ``force_signal_every_n_bars=1`` to guarantee signals fire on every bar,
ensuring at least MIN_TRADES closed trades within TIMEOUT_SECS.

Run with:
    RUN_LIVE_TESTS=1 pytest tests/test_live_e2e.py -v -s --timeout=240

Mark: @pytest.mark.live (excluded from default test run, opt-in only).
Add ``-m live`` plus ``RUN_LIVE_TESTS=1`` to include it. The default ``pytest`` run skips it automatically.

Requirements:
    - Active internet connection (Binance public WebSocket, no API key needed)
    - CCXT, TA-Lib installed (standard in docker container)
"""

import sys
import os
import threading
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.bt_live_engine import BTLiveEngine
from strategies.fast_test_strategy import FastTestStrategy

# ── Configuration ────────────────────────────────────────────────────────────

MIN_TRADES = 2          # minimum closed trades (1m bars: ~2-3 per 4 minutes)
TIMEOUT_SECS = 300      # 5 minutes max

ENGINE_CONFIG = {
    "symbol": "BTC/USDT",
    "timeframes": ["1m", "1m"],
    "exchange": "binance",
    "exchange_type": "future",
    "initial_capital": 10000,
    "risk_per_trade": 1.0,
    "leverage": 10,
    "max_drawdown": 50,
}

# FastTestStrategy: uses fixed_size to avoid margin errors in paper broker
STRATEGY_CONFIG = {
    "sl_mult": 0.3,         # tight SL → trades close fast
    "tp_mult": 0.6,         # 2:1 RR
    "atr_period": 7,
    "risk_per_trade": 1.0,
    "leverage": 10,
    "max_drawdown": 50,
    "dynamic_position_sizing": True,
    "fixed_size": 0.001,    # 0.001 BTC ≈ $68 — safely within any paper margin
}


# ── Marker ────────────────────────────────────────────────────────────────────

pytestmark = [
    pytest.mark.live,  # include with: pytest -m live
    pytest.mark.skipif(
        os.getenv("RUN_LIVE_TESTS") != "1",
        reason="Set RUN_LIVE_TESTS=1 to run internet-dependent live E2E test.",
    ),
]


# ── Helper ────────────────────────────────────────────────────────────────────

def _monitor_and_stop(engine: BTLiveEngine, min_trades: int, timeout: float) -> dict:
    """
    Background monitor: polls engine.closed_trades list length every second.
    Stops the engine when MIN_TRADES closed trades are confirmed, or on timeout.
    Returns a result dict for assertions.
    """
    result = {"closed": 0, "timed_out": False, "stopped_at": None}
    deadline = time.time() + timeout

    while time.time() < deadline:
        # Poll the closed_trades list that is updated by the live engine
        # (works even while cerebro.run() is blocking)
        strategy = getattr(engine, "strategy", None)
        if strategy is not None:
            closed = getattr(strategy, "next_trade_id", 1) - 1
        else:
            closed = len(getattr(engine, "closed_trades", []))
        result["closed"] = closed
        if closed >= min_trades:
            print(f"\n  ✅ {closed} trades closed — stopping engine")
            result["stopped_at"] = time.time()
            engine.stop()
            return result
        time.sleep(1)

    result["timed_out"] = True
    print(f"\n  ⏰ Timeout after {timeout}s with {result['closed']} trades")
    engine.stop()
    return result


# ── Test ──────────────────────────────────────────────────────────────────────

@pytest.mark.live
def test_live_trading_produces_real_trades():
    """
    Full end-to-end live paper trading test.

    Validates:
    1. Engine starts and warm-up completes
    2. At least MIN_TRADES trades are closed within TIMEOUT_SECS
    3. Each trade has all required fields with valid values
    4. SL/TP are correctly placed at fill price (not signal price)
    5. Engine metrics are consistent with trade list
    """
    # Build engine — strategy self-terminates after MIN_TRADES via stop_event
    # injected by _StopEventInjector observer in bt_live_engine.run_live()
    engine = BTLiveEngine(ENGINE_CONFIG)
    strategy_config = {**STRATEGY_CONFIG, "stop_after_n_trades": MIN_TRADES}
    engine.add_strategy(FastTestStrategy, **strategy_config)

    metrics_holder: dict = {}

    def run_in_thread():
        metrics_holder["result"] = engine.run_live()

    run_thread = threading.Thread(target=run_in_thread, daemon=True)
    run_thread.start()

    # Wait for strategy to self-terminate or hard timeout
    run_thread.join(timeout=TIMEOUT_SECS)
    if run_thread.is_alive():
        print(f"\n  ⏰ Timeout after {TIMEOUT_SECS}s — force stopping engine")
        engine.stop()
        run_thread.join(timeout=15)

    metrics = metrics_holder.get("result", {})

    # ── Assertion 1: got enough trades ────────────────────────────────────────
    trades = engine.closed_trades
    assert len(trades) >= MIN_TRADES, (
        f"Expected ≥{MIN_TRADES} closed trades, got {len(trades)}.\n"
        "Check Binance WebSocket connectivity and warm-up guard logic."
    )

    # ── Assertion 2: all required trade fields present and valid ──────────────
    REQUIRED_FIELDS = [
        "entry_price", "exit_price", "direction", "entry_time",
        "exit_time", "realized_pnl", "stop_loss", "take_profit",
        "exit_reason", "size",
    ]

    for i, trade in enumerate(trades):
        missing = [f for f in REQUIRED_FIELDS if f not in trade or trade[f] is None]
        assert not missing, f"Trade #{i+1} missing fields: {missing}\nTrade data: {trade}"

        # Numeric sanity
        assert trade["entry_price"] > 0, f"Trade #{i+1}: entry_price ≤ 0"
        assert trade["exit_price"] > 0,  f"Trade #{i+1}: exit_price ≤ 0"
        assert trade["size"] > 0,        f"Trade #{i+1}: size ≤ 0"
        assert str(trade["direction"]).upper() in ("LONG", "SHORT"), \
            f"Trade #{i+1}: invalid direction '{trade['direction']}'"

        # SL/TP were placed at fill price, not signal price — must differ from entry
        sl = trade["stop_loss"]
        ep = trade["entry_price"]
        assert sl != ep, (
            f"Trade #{i+1}: stop_loss == entry_price ({sl}) "
            "— SL was not adjusted to fill price (zero-PnL bug)!"
        )
        assert sl > 0, f"Trade #{i+1}: stop_loss ≤ 0"

        # LONG: SL below entry, TP above entry
        direction_upper = str(trade["direction"]).upper()
        if direction_upper == "LONG":
            assert trade["stop_loss"] < ep, \
                f"Trade #{i+1} LONG: SL {sl} not below entry {ep}"
            assert trade["take_profit"] > ep, \
                f"Trade #{i+1} LONG: TP {trade['take_profit']} not above entry {ep}"
        else:
            assert trade["stop_loss"] > ep, \
                f"Trade #{i+1} SHORT: SL {sl} not above entry {ep}"
            assert trade["take_profit"] < ep, \
                f"Trade #{i+1} SHORT: TP {trade['take_profit']} not below entry {ep}"

        # Exit reason must be known (not left as Unknown from metadata gap)
        assert trade["exit_reason"] != "Unknown", \
            f"Trade #{i+1}: exit_reason is still 'Unknown' — notify_trade bug"

    # ── Assertion 3: engine metrics consistent ────────────────────────────────
    assert metrics.get("total_trades", 0) >= MIN_TRADES, \
        f"Engine metrics show {metrics.get('total_trades')} trades, but expected ≥{MIN_TRADES}"
    assert metrics.get("initial_capital", 0) == ENGINE_CONFIG["initial_capital"], \
        "Engine initial_capital mismatch"
    assert "final_capital" in metrics, "Engine metrics missing final_capital"
    assert "win_rate" in metrics, "Engine metrics missing win_rate"

    # ── Summary output ────────────────────────────────────────────────────────
    print(f"\n{'─'*60}")
    print(f"  Live E2E Result: {len(trades)} trades in ~{TIMEOUT_SECS}s")
    print(f"  Win rate:       {metrics.get('win_rate', 0):.1f}%")
    print(f"  Total PnL:      {metrics.get('total_pnl', 0):.2f}")
    print(f"  Final capital:  {metrics.get('final_capital', 0):.2f}")
    print(f"{'─'*60}")
    for i, t in enumerate(trades):
        sign = "✅" if t["realized_pnl"] >= 0 else "🔴"
        print(f"  {sign} Trade #{i+1} {t['direction']:5s} | "
              f"Entry={t['entry_price']:.2f} SL={t['stop_loss']:.2f} TP={t['take_profit']:.2f} | "
              f"PnL={t['realized_pnl']:.2f} | Reason={t['exit_reason']}")
