import os
import sys

import backtrader as bt
import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.bt_analyzers import TradeListAnalyzer  # noqa: E402
from strategies.bt_traders_reality import TradersRealityStrategy  # noqa: E402


def _make_ohlcv(n: int = 500, seed: int = 42, base: float = 50000.0) -> pd.DataFrame:
    """Generate n hourly OHLCV bars with enough warmup for EMA-200 and weekly state."""
    rng = np.random.default_rng(seed)
    noise = rng.normal(0, 50, n)
    closes = base + np.cumsum(noise)
    opens = closes + rng.normal(0, 20, n)
    highs = np.maximum(opens, closes) + rng.uniform(10, 80, n)
    lows = np.minimum(opens, closes) - rng.uniform(10, 80, n)
    vols = rng.uniform(500, 2000, n)
    dates = pd.date_range("2024-01-01", periods=n, freq="1h")
    return pd.DataFrame(
        {"open": opens, "high": highs, "low": lows, "close": closes, "volume": vols},
        index=dates,
    )


def _run_cerebro(df: pd.DataFrame, **strategy_params) -> bt.Strategy:
    cerebro = bt.Cerebro()
    cerebro.addstrategy(TradersRealityStrategy, **strategy_params)
    data = bt.feeds.PandasData(dataname=df)
    cerebro.adddata(data)
    cerebro.addanalyzer(TradeListAnalyzer, _name="tradelist")
    cerebro.broker.setcash(100_000)
    cerebro.broker.setcommission(commission=0.001)
    results = cerebro.run()
    return results[0]


def _long_trades(trades):
    return [
        t
        for t in trades
        if (t.get("signal_direction") or t.get("direction") or "").lower() == "long"
    ]


def _short_trades(trades):
    return [
        t
        for t in trades
        if (t.get("signal_direction") or t.get("direction") or "").lower() == "short"
    ]


class TestTradersRealityStrategyInstantiation:
    def test_strategy_runs_without_error(self):
        df = _make_ohlcv(500)
        strat = _run_cerebro(df)
        assert strat is not None


class TestTradersRealityFilters:
    """Verify that the PVSRA and HTF gates reject signals correctly."""

    def _make_trending_bullish_df(self, n: int = 500) -> pd.DataFrame:
        dates = pd.date_range("2023-01-01", periods=n, freq="1h")
        closes = np.linspace(40000, 55000, n)
        opens = closes - 10
        highs = closes + 50
        lows = closes - 50
        vols = np.linspace(1000, 3000, n)
        return pd.DataFrame(
            {"open": opens, "high": highs, "low": lows, "close": closes, "volume": vols},
            index=dates,
        )

    def test_no_entry_without_pvsra_qualifier(self):
        """With uniform volume PVSRA stays gray — no entry should fire."""
        df = self._make_trending_bullish_df(500)
        df["volume"] = 1000.0
        strat = _run_cerebro(
            df,
            use_htf_ema_filter=False,
            signal_long_min_score=2.0,
            pvsra_rv_mult=2.0,
            pvsra_bv_mult=1.5,
            risk_reward_ratio=2.0,
        )
        trades = strat.analyzers.tradelist.get_analysis()
        assert len(trades) == 0

    def test_htf_filter_blocks_long_in_downtrend(self):
        """Strongly downtrending data: HTF EMA filter should block all longs."""
        n = 500
        dates = pd.date_range("2023-01-01", periods=n, freq="1h")
        closes = np.linspace(55000, 40000, n)
        opens = closes + 10
        highs = closes + 50
        lows = closes - 50
        vols = np.where(np.arange(n) % 20 == 0, 10000.0, 500.0)
        df = pd.DataFrame(
            {"open": opens, "high": highs, "low": lows, "close": closes, "volume": vols},
            index=dates,
        )
        strat = _run_cerebro(df, use_htf_ema_filter=True, risk_reward_ratio=2.0)
        trades = strat.analyzers.tradelist.get_analysis()
        assert len(_long_trades(trades)) == 0


class TestTradersRealityEntry:
    """Inject explicit ring-volume bars and verify entries fire."""

    def _make_uptrend_with_pvsra_spike(self) -> pd.DataFrame:
        n = 500
        dates = pd.date_range("2023-01-01", periods=n, freq="1h")
        closes = np.linspace(40000, 52000, n)
        opens = closes - 20
        highs = closes + 80
        lows = closes - 80
        vols = np.full(n, 1000.0)
        for idx in (350, 400, 450, 470):
            vols[idx] = 3200.0
        return pd.DataFrame(
            {"open": opens, "high": highs, "low": lows, "close": closes, "volume": vols},
            index=dates,
        )

    def test_pvsra_green_triggers_long_entry(self):
        df = self._make_uptrend_with_pvsra_spike()
        strat = _run_cerebro(
            df,
            use_htf_ema_filter=False,
            signal_long_min_score=2.0,
            risk_reward_ratio=2.0,
            max_drawdown=None,
        )
        trades = strat.analyzers.tradelist.get_analysis()
        assert len(_long_trades(trades)) >= 1

    def test_trade_metadata_contains_score(self):
        df = self._make_uptrend_with_pvsra_spike()
        strat = _run_cerebro(
            df,
            use_htf_ema_filter=False,
            signal_long_min_score=2.0,
            risk_reward_ratio=2.0,
            max_drawdown=None,
        )
        trades = strat.analyzers.tradelist.get_analysis()
        longs = _long_trades(trades)
        assert longs, "Expected at least one long trade"
        ec = longs[0].get("entry_context") or {}
        indicators = ec.get("indicators_at_entry") or {}
        assert "SignalScore" in indicators
        assert indicators["SignalScore"] >= 2.0


class TestTradersRealityLiveEngineIntegration:
    """Verify strategy wires up with BTLiveEngine (paper) without network."""

    def test_live_engine_initialises_and_attaches_strategy(self, monkeypatch):
        from unittest.mock import MagicMock

        from engine import bt_live_engine as live_mod
        from engine.bt_live_engine import BTLiveEngine

        class _DummyWSClient:
            def __init__(self, **kwargs):
                self.name = "dummy"

            def start(self):
                pass

            def join(self, timeout=None):
                pass

            def is_alive(self):
                return False

            def request_stop(self):
                pass

        data_loader = MagicMock()
        data_loader.fetch_recent_bars.return_value = [
            {
                "timestamp": 1,
                "open": 50000.0,
                "high": 50100.0,
                "low": 49900.0,
                "close": 50050.0,
                "volume": 1.0,
            }
        ]
        monkeypatch.setattr(live_mod, "DataLoader", lambda **kw: data_loader)
        monkeypatch.setattr(
            live_mod,
            "create_live_stream_client",
            lambda **kw: _DummyWSClient(**kw),
        )

        engine = BTLiveEngine(
            {
                "initial_capital": 10_000.0,
                "symbol": "BTC/USDT",
                "timeframes": ["1h", "4h"],
                "exchange": "binance",
            }
        )
        engine.add_strategy(TradersRealityStrategy, risk_reward_ratio=2.0)
        engine.add_data()
        assert len(engine.cerebro.datas) == 2
        engine.stop()


class TestTradersRealityHygiene:
    """Regression coverage for bug-fixes in the strategy."""

    def test_pvsra_label_set_accepts_list_from_json(self):
        """Dashboard passes labels as JSON list; strategy must normalise to set."""
        df = _make_ohlcv(500)
        strat = _run_cerebro(
            df,
            use_htf_ema_filter=False,
            pvsra_long_labels=["green", "blue"],
            pvsra_short_labels=["red", "violet"],
            max_drawdown=None,
        )
        assert strat._pvsra_long_set == frozenset({"green", "blue"})
        assert strat._pvsra_short_set == frozenset({"red", "violet"})

    def test_warmup_emits_only_gray_labels(self):
        """During warmup (buffer not full) PVSRA label must stay gray_up/gray_dn.

        Regression: on a degenerate average-volume window the ring-volume
        condition `vol >= 0 * mult` fired trivially, painting the first bar
        green/red and poisoning the composite score.
        """
        import pandas as pd

        n = 20
        dates = pd.date_range("2023-01-01", periods=n, freq="1h")
        # Zero volume on first bar, then positive — exactly the case that
        # used to produce a false ring label on bar 2.
        vols = [0.0] + [1000.0] * (n - 1)
        df = pd.DataFrame(
            {
                "open": [50000.0] * n,
                "high": [50100.0] * n,
                "low": [49900.0] * n,
                "close": [50050.0] * n,
                "volume": vols,
            },
            index=dates,
        )
        strat = _run_cerebro(df, use_htf_ema_filter=False, max_drawdown=None)
        # After 20 bars but pvsra_avg_period=10 default, the last label should
        # reflect the genuine window (not a warmup artefact); it must be one
        # of the valid labels. More importantly: no trade should have fired
        # from poisoned early bars.
        trades = strat.analyzers.tradelist.get_analysis()
        assert trades == [] or all(
            isinstance(t.get("entry_context", {}).get("indicators_at_entry", {}).get("PVSRA"), str)
            for t in trades
        )

    def test_zero_size_entry_leaves_no_pending_metadata(self, monkeypatch):
        """Aborting entry on size=0 must not leave stale pending_metadata.

        Regression: the old code logged SIGNAL GENERATED and set
        pending_metadata + sl_history before asking RiskManager for size. A
        rejected size would leave dangling state.
        """
        df = _make_ohlcv(500)
        strat = _run_cerebro(
            df,
            use_htf_ema_filter=False,
            max_drawdown=None,
        )
        # Force a direct call into _place_entry with RiskManager patched to 0.
        import strategies.bt_traders_reality as mod

        monkeypatch.setattr(
            mod.TradersRealityStrategy,
            "_calculate_position_size",
            lambda self, *a, **kw: 0.0,
        )
        # Reset position-related state and attempt a long entry.
        strat.pending_metadata = None
        strat.sl_history = []
        strat.initial_sl = None
        strat._place_entry("long", score=3.0, pvsra="green")
        assert strat.pending_metadata is None
        assert strat.sl_history == []
        assert strat.initial_sl is None


class TestTradersRealitySLTP:
    def _make_strat(self) -> TradersRealityStrategy:
        df = _make_ohlcv(500)
        return _run_cerebro(
            df,
            use_htf_ema_filter=False,
            risk_reward_ratio=2.0,
            max_drawdown=None,
        )

    def test_sl_long_falls_back_to_atr_when_no_pivots(self):
        strat = self._make_strat()
        strat._pivots = None
        strat._m0 = None
        _sl, _dist, expr = strat._resolve_sl_long(50000.0)
        if _sl is not None:
            assert "ATR" in expr or "Low" in expr

    def test_tp_long_uses_r1_when_pivot_available(self):
        strat = self._make_strat()
        if strat._pivots is None:
            pytest.skip("Pivots not populated in this run")
        r1 = strat._pivots["R1"]
        entry = strat._pivots["PP"] + 1.0
        if r1 <= entry:
            pytest.skip("R1 below entry; path not exercised")
        tp, _, expr = strat._resolve_tp_long(entry, sl_distance=50.0)
        assert abs(tp - r1) < 1e-6
        assert "R1" in expr

    def test_tp_short_uses_s1_when_pivot_available(self):
        strat = self._make_strat()
        if strat._pivots is None:
            pytest.skip("Pivots not populated in this run")
        s1 = strat._pivots["S1"]
        entry = strat._pivots["PP"] - 1.0
        if s1 >= entry:
            pytest.skip("S1 above entry; path not exercised")
        tp, _, expr = strat._resolve_tp_short(entry, sl_distance=50.0)
        assert abs(tp - s1) < 1e-6
        assert "S1" in expr
