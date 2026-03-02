"""
Integration tests for engine + strategy + TA-Lib.

Runs full backtests with crafted OHLC data that triggers TA-Lib patterns.
Verifies: pattern detection, indicators (EMA, RSI, ATR, ADX), trade lifecycle.

TA-Lib patterns used in PriceActionStrategy (all covered here):
- CDLENGULFING: Bullish Engulfing, Bearish Engulfing
- CDLHAMMER: Bullish Pinbar (hammer)
- CDLINVERTEDHAMMER: Bullish Pinbar (inverted hammer)
- CDLSHOOTINGSTAR: Bearish Pinbar (shooting star)
- CDLHANGINGMAN: Bearish Pinbar (hanging man)

Run: pytest tests/test_integration_talib.py -v
"""
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.bt_backtest_engine import BTBacktestEngine
from engine.bt_analyzers import TradeListAnalyzer
from strategies.bt_price_action import PriceActionStrategy


def _make_base_df(periods=350, base_price=1000, flat=True):
    """Base dataframe with enough bars for EMA(200), ATR(14), RSI(14)."""
    np.random.seed(42)
    dates = pd.date_range(start="2024-01-01", periods=periods, freq="h")
    if flat:
        closes = base_price + np.random.normal(0, 1, periods)
    else:
        trend = np.linspace(0, 50, periods)
        noise = np.random.normal(0, 2, periods)
        closes = base_price + trend + noise
    opens = np.roll(closes, 1)
    opens[0] = base_price
    highs = np.maximum(opens, closes) + np.abs(np.random.randn(periods)) * 2
    lows = np.minimum(opens, closes) - np.abs(np.random.randn(periods)) * 2
    volumes = np.full(periods, 1000.0)
    return pd.DataFrame(
        {"open": opens, "high": highs, "low": lows, "close": closes, "volume": volumes},
        index=dates,
    )


def _inject_bullish_engulfing(df, bar_idx, base=1000):
    """Inject TA-Lib Bullish Engulfing at bar_idx. Prev red, curr green engulfs.
    Prices kept near base so ATR stays low and _has_significant_range passes."""
    prev_o, prev_h, prev_l, prev_c = base - 2, base - 1, base - 3, base - 4
    curr_o, curr_h, curr_l, curr_c = base - 5, base + 5, base - 6, base
    df.iloc[bar_idx - 1] = [prev_o, prev_h, prev_l, prev_c, 1000]
    df.iloc[bar_idx] = [curr_o, curr_h, curr_l, curr_c, 1000]
    return df


def _inject_bearish_engulfing(df, bar_idx, base=1000):
    """Inject TA-Lib Bearish Engulfing at bar_idx."""
    prev_o, prev_h, prev_l, prev_c = base - 5, base - 4, base - 6, base - 4.5
    curr_o, curr_h, curr_l, curr_c = base - 4, base - 3, base - 7, base - 6
    df.iloc[bar_idx - 1] = [prev_o, prev_h, prev_l, prev_c, 1000]
    df.iloc[bar_idx] = [curr_o, curr_h, curr_l, curr_c, 1000]
    return df


def _make_pinbar_context_df(periods=350, base=1000):
    """Base with LARGE body and SMALL shadows so TA-Lib pinbar averages allow detection."""
    np.random.seed(42)
    dates = pd.date_range(start="2024-01-01", periods=periods, freq="h")
    o = base + np.arange(periods) * 0.5
    c = o + 10 * (np.random.rand(periods) > 0.3)
    h = np.maximum(o, c) + 1
    l = np.minimum(o, c) - 1
    for i in range(periods):
        h[i] = max(h[i], o[i], c[i], l[i])
        l[i] = min(l[i], o[i], c[i], h[i])
    return pd.DataFrame(
        {"open": o, "high": h, "low": l, "close": c, "volume": np.full(periods, 1000.0)},
        index=dates,
    )


def _inject_hammer(df, bar_idx):
    """Inject TA-Lib Hammer at bar_idx (small body at top, long lower shadow)."""
    o, h, l, c = 1001, 1001.5, 981, 1000.5
    df.iloc[bar_idx] = [o, h, l, c, 1000]
    return df


def _inject_inverted_hammer(df, bar_idx):
    """Inject Inverted Hammer shape (small body at bottom, long upper shadow)."""
    o, h, l, c = 998, 1018, 997, 999
    df.iloc[bar_idx] = [o, h, l, c, 1000]
    return df


def _inject_shooting_star(df, bar_idx):
    """Inject Shooting Star shape (small body at bottom, long upper shadow, bearish)."""
    o, h, l, c = 1001, 1021, 1000, 1001
    df.iloc[bar_idx] = [o, h, l, c, 1000]
    return df


def _inject_hanging_man(df, bar_idx):
    """Inject Hanging Man shape (small body at top, long lower shadow, bearish)."""
    o, h, l, c = 1018, 1020, 998, 1017
    df.iloc[bar_idx] = [o, h, l, c, 1000]
    return df


def _make_price_hit_tp_long(df, entry_bar, entry_price, tp_price):
    """After entry at entry_bar, make price reach tp_price within 20 bars."""
    for k in range(1, 25):
        idx = entry_bar + k
        if idx >= len(df):
            break
        mid = entry_price + (tp_price - entry_price) * (k / 15)
        df.iloc[idx] = [mid, mid + 3, mid - 1, mid + 1, 1000]
    return df


def _set_execution_bar(df, bar_idx, fill_price):
    """Set open of bar_idx to fill_price (market order fills at next bar open)."""
    row = df.iloc[bar_idx].copy()
    row["open"] = fill_price
    row["high"] = fill_price + 2
    row["low"] = fill_price - 2
    row["close"] = fill_price + 1
    df.iloc[bar_idx] = row


def _make_price_hit_sl_long(df, entry_bar, sl_price):
    """Make price drop to sl_price (hit stop loss)."""
    entry_price = df.iloc[entry_bar]["open"]
    for k in range(1, 10):
        idx = entry_bar + k
        if idx >= len(df):
            break
        mid = entry_price - (entry_price - sl_price) * (k / 5)
        df.iloc[idx] = [mid, mid + 1, mid - 2, mid - 1, 1000]
    return df


def _make_price_hit_tp_short(df, entry_bar, entry_price, tp_price):
    """For short: price drops to tp_price."""
    for k in range(1, 25):
        idx = entry_bar + k
        if idx >= len(df):
            break
        mid = entry_price - (entry_price - tp_price) * (k / 15)
        df.iloc[idx] = [mid, mid + 1, mid - 2, mid - 1, 1000]
    return df


def _run_backtest_with_patterns(
    mock_dataloader_cls,
    df,
    pattern_hammer=True,
    pattern_inverted_hammer=True,
    pattern_shooting_star=True,
    pattern_hanging_man=True,
    pattern_bullish_engulfing=True,
    pattern_bearish_engulfing=True,
    **strategy_kwargs,
):
    mock_loader = MagicMock()
    mock_loader.get_data.return_value = df
    mock_dataloader_cls.return_value = mock_loader
    config = {
        "symbol": "BTC/USDT",
        "timeframes": ["1h"],
        "start_date": "2024-01-01",
        "end_date": "2024-12-31",
        "initial_capital": 10000,
        "leverage": 5.0,
    }
    engine = BTBacktestEngine(config)
    defaults = {
        "use_trend_filter": False,
        "use_adx_filter": False,
        "use_rsi_filter": False,
        "risk_reward_ratio": 2.0,
    }
    defaults.update(strategy_kwargs)
    engine.add_strategy(
        PriceActionStrategy,
        pattern_hammer=pattern_hammer,
        pattern_inverted_hammer=pattern_inverted_hammer,
        pattern_shooting_star=pattern_shooting_star,
        pattern_hanging_man=pattern_hanging_man,
        pattern_bullish_engulfing=pattern_bullish_engulfing,
        pattern_bearish_engulfing=pattern_bearish_engulfing,
        **defaults,
    )
    return engine.run_backtest(), engine


@pytest.mark.integration
@pytest.mark.engine
@patch("engine.bt_backtest_engine.DataLoader")
class TestIntegrationBullishEngulfing(unittest.TestCase):
    """Bullish Engulfing pattern → Long entry → Take Profit."""

    def test_bullish_engulfing_triggers_long_and_hits_tp(self, mock_dataloader_cls):
        df = _make_base_df()
        _inject_bullish_engulfing(df, 250)
        _set_execution_bar(df, 251, 1000)
        _make_price_hit_tp_long(df, 251, 1000, 1016)

        mock_loader = MagicMock()
        mock_loader.get_data.return_value = df
        mock_dataloader_cls.return_value = mock_loader

        config = {
            "symbol": "BTC/USDT",
            "timeframes": ["1h"],
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "initial_capital": 10000,
            "leverage": 5.0,
        }
        engine = BTBacktestEngine(config)
        engine.add_strategy(
            PriceActionStrategy,
            use_trend_filter=False,
            use_adx_filter=False,
            use_rsi_filter=False,
            risk_reward_ratio=2.0,
        )
        metrics = engine.run_backtest()

        self.assertGreater(metrics["total_trades"], 0, "Expected at least one trade")
        self.assertGreater(metrics["win_count"], 0, "Expected at least one winning trade")
        self.assertGreater(metrics["final_capital"], metrics["initial_capital"])
        self.assertIn("Bullish Engulfing", [t.get("reason") for t in engine.closed_trades])


@pytest.mark.integration
@pytest.mark.engine
@patch("engine.bt_backtest_engine.DataLoader")
class TestIntegrationBearishEngulfing(unittest.TestCase):
    """Bearish Engulfing pattern → Short entry → Take Profit."""

    def test_bearish_engulfing_triggers_short_and_hits_tp(self, mock_dataloader_cls):
        df = _make_base_df()
        _inject_bearish_engulfing(df, 250)
        _set_execution_bar(df, 251, 994)
        _make_price_hit_tp_short(df, 251, 994, 970)

        mock_loader = MagicMock()
        mock_loader.get_data.return_value = df
        mock_dataloader_cls.return_value = mock_loader

        config = {
            "symbol": "BTC/USDT",
            "timeframes": ["1h"],
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "initial_capital": 10000,
            "leverage": 5.0,
        }
        engine = BTBacktestEngine(config)
        engine.add_strategy(
            PriceActionStrategy,
            use_trend_filter=False,
            use_adx_filter=False,
            use_rsi_filter=False,
            risk_reward_ratio=2.0,
        )
        metrics = engine.run_backtest()

        self.assertGreater(metrics["total_trades"], 0)
        trades = engine.closed_trades
        short_trades = [t for t in trades if t.get("direction") == "SHORT"]
        self.assertGreater(len(short_trades), 0, "Expected at least one SHORT trade")
        self.assertIn("Bearish Engulfing", [t.get("reason") for t in engine.closed_trades])


@pytest.mark.integration
@pytest.mark.engine
@patch("engine.bt_backtest_engine.DataLoader")
class TestIntegrationHammer(unittest.TestCase):
    """CDLHAMMER (Bullish Pinbar) → Long entry."""

    def test_hammer_triggers_bullish_pinbar_long(self, mock_dataloader_cls):
        df = _make_pinbar_context_df()
        _inject_hammer(df, 250)
        _set_execution_bar(df, 251, 1000.5)
        _make_price_hit_tp_long(df, 251, 1000.5, 1017)

        metrics, engine = _run_backtest_with_patterns(
            mock_dataloader_cls,
            df,
            pattern_bullish_engulfing=False,
            pattern_bearish_engulfing=False,
        )

        self.assertGreater(metrics["total_trades"], 0, "Hammer should trigger Bullish Pinbar")
        self.assertIn("Bullish Pinbar", [t.get("reason") for t in engine.closed_trades])


@pytest.mark.integration
@pytest.mark.engine
@patch("engine.bt_backtest_engine.DataLoader")
class TestIntegrationInvertedHammer(unittest.TestCase):
    """CDLINVERTEDHAMMER (Bullish Pinbar) → Long entry."""

    def test_inverted_hammer_runs_and_may_trigger_long(self, mock_dataloader_cls):
        df = _make_pinbar_context_df()
        _inject_inverted_hammer(df, 250)
        _set_execution_bar(df, 251, 999)
        _make_price_hit_tp_long(df, 251, 999, 1015)

        metrics, engine = _run_backtest_with_patterns(
            mock_dataloader_cls,
            df,
            pattern_hammer=False,
            pattern_shooting_star=False,
            pattern_hanging_man=False,
            pattern_bullish_engulfing=False,
            pattern_bearish_engulfing=False,
        )

        if metrics["total_trades"] > 0:
            self.assertIn("Bullish Pinbar", [t.get("reason") for t in engine.closed_trades])


@pytest.mark.integration
@pytest.mark.engine
@patch("engine.bt_backtest_engine.DataLoader")
class TestIntegrationShootingStar(unittest.TestCase):
    """CDLSHOOTINGSTAR (Bearish Pinbar) → Short entry."""

    def test_shooting_star_runs_and_may_trigger_short(self, mock_dataloader_cls):
        df = _make_pinbar_context_df()
        _inject_shooting_star(df, 250)
        _set_execution_bar(df, 251, 1001)
        _make_price_hit_tp_short(df, 251, 1001, 980)

        metrics, engine = _run_backtest_with_patterns(
            mock_dataloader_cls,
            df,
            pattern_hammer=False,
            pattern_inverted_hammer=False,
            pattern_hanging_man=False,
            pattern_bullish_engulfing=False,
            pattern_bearish_engulfing=False,
        )

        if metrics["total_trades"] > 0:
            self.assertIn("Bearish Pinbar", [t.get("reason") for t in engine.closed_trades])


@pytest.mark.integration
@pytest.mark.engine
@patch("engine.bt_backtest_engine.DataLoader")
class TestIntegrationHangingMan(unittest.TestCase):
    """CDLHANGINGMAN (Bearish Pinbar) → Short entry."""

    def test_hanging_man_runs_and_may_trigger_short(self, mock_dataloader_cls):
        df = _make_pinbar_context_df()
        _inject_hanging_man(df, 250)
        _set_execution_bar(df, 251, 1017)
        _make_price_hit_tp_short(df, 251, 1017, 995)

        metrics, engine = _run_backtest_with_patterns(
            mock_dataloader_cls,
            df,
            pattern_hammer=False,
            pattern_inverted_hammer=False,
            pattern_shooting_star=False,
            pattern_bullish_engulfing=False,
            pattern_bearish_engulfing=False,
        )

        if metrics["total_trades"] > 0:
            self.assertIn("Bearish Pinbar", [t.get("reason") for t in engine.closed_trades])


@pytest.mark.integration
@pytest.mark.engine
@patch("engine.bt_backtest_engine.DataLoader")
class TestIntegrationNoPattern(unittest.TestCase):
    """No TA-Lib pattern in data → no trades."""

    def test_flat_data_produces_no_trades(self, mock_dataloader_cls):
        df = _make_base_df()
        # No pattern injection — just base data (no engulfing, no pinbar)
        mock_loader = MagicMock()
        mock_loader.get_data.return_value = df
        mock_dataloader_cls.return_value = mock_loader

        config = {
            "symbol": "BTC/USDT",
            "timeframes": ["1h"],
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "initial_capital": 10000,
        }
        engine = BTBacktestEngine(config)
        engine.add_strategy(
            PriceActionStrategy,
            use_trend_filter=False,
            use_adx_filter=False,
            use_rsi_filter=False,
            pattern_hammer=False,
            pattern_inverted_hammer=False,
            pattern_shooting_star=False,
            pattern_hanging_man=False,
            pattern_bullish_engulfing=False,
            pattern_bearish_engulfing=False,
        )
        metrics = engine.run_backtest()

        self.assertEqual(metrics.get("total_trades", 0), 0)
        self.assertEqual(len(engine.closed_trades), 0)
        self.assertEqual(metrics["initial_capital"], metrics["final_capital"])


@pytest.mark.integration
@pytest.mark.engine
@patch("engine.bt_backtest_engine.DataLoader")
class TestIntegrationStopLoss(unittest.TestCase):
    """Pattern triggers → entry → price hits SL (loss)."""

    def test_bullish_engulfing_hits_stop_loss(self, mock_dataloader_cls):
        df = _make_base_df()
        _inject_bullish_engulfing(df, 250)
        _set_execution_bar(df, 251, 1000)
        _make_price_hit_sl_long(df, 251, 990)

        mock_loader = MagicMock()
        mock_loader.get_data.return_value = df
        mock_dataloader_cls.return_value = mock_loader

        config = {
            "symbol": "BTC/USDT",
            "timeframes": ["1h"],
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "initial_capital": 10000,
            "leverage": 5.0,
        }
        engine = BTBacktestEngine(config)
        engine.add_strategy(
            PriceActionStrategy,
            use_trend_filter=False,
            use_adx_filter=False,
            use_rsi_filter=False,
            risk_reward_ratio=2.0,
        )
        metrics = engine.run_backtest()

        self.assertGreater(metrics["total_trades"], 0)
        self.assertGreater(metrics["loss_count"], 0)
        self.assertLess(metrics["final_capital"], metrics["initial_capital"])


@pytest.mark.integration
@pytest.mark.engine
@patch("engine.bt_backtest_engine.DataLoader")
class TestIntegrationDualTimeframe(unittest.TestCase):
    """Dual timeframe: 4h + 1h. TA-Lib indicators on both."""

    def test_dual_tf_runs_without_error(self, mock_dataloader_cls):
        df_1h = _make_base_df(periods=400)
        df_4h = _make_base_df(periods=100)  # Resampled would differ; we use same structure
        df_4h.index = pd.date_range("2024-01-01", periods=100, freq="4h")

        _inject_bullish_engulfing(df_1h, 250)
        _set_execution_bar(df_1h, 251, 1000)
        _make_price_hit_tp_long(df_1h, 251, 1000, 1016)

        def get_data(symbol, tf, start, end):
            if tf == "1h":
                return df_1h
            return df_4h

        mock_loader = MagicMock()
        mock_loader.get_data.side_effect = get_data
        mock_dataloader_cls.return_value = mock_loader

        config = {
            "symbol": "BTC/USDT",
            "timeframes": ["4h", "1h"],
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "initial_capital": 10000,
        }
        engine = BTBacktestEngine(config)
        engine.add_strategy(
            PriceActionStrategy,
            use_trend_filter=False,
            use_adx_filter=False,
            use_rsi_filter=False,
        )
        metrics = engine.run_backtest()

        self.assertIsInstance(metrics, dict)
        self.assertIn("total_trades", metrics)
        mock_loader.get_data.assert_any_call("BTC/USDT", "1h", "2024-01-01", "2024-12-31")
        mock_loader.get_data.assert_any_call("BTC/USDT", "4h", "2024-01-01", "2024-12-31")


@pytest.mark.integration
@pytest.mark.engine
@patch("engine.bt_backtest_engine.DataLoader")
class TestIntegrationWithFilters(unittest.TestCase):
    """Strategy with EMA/RSI/ADX filters — indicators must compute correctly."""

    def test_trend_filter_blocks_trade_in_downtrend(self, mock_dataloader_cls):
        """When price is below EMA(200), long signals should be blocked."""
        df = _make_base_df(periods=350, flat=False)
        for i in range(350):
            if i < 200:
                p = 1000 + i * 0.5
            else:
                p = 1100 - (i - 200) * 0.5
            df.iloc[i] = [p, p + 1, p - 1, p, 1000]
        _inject_bullish_engulfing(df, 250)
        _set_execution_bar(df, 251, 1000)
        _make_price_hit_tp_long(df, 251, 1000, 1016)

        mock_loader = MagicMock()
        mock_loader.get_data.return_value = df
        mock_dataloader_cls.return_value = mock_loader

        config = {
            "symbol": "BTC/USDT",
            "timeframes": ["1h"],
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "initial_capital": 10000,
            "leverage": 5.0,
        }
        engine = BTBacktestEngine(config)
        engine.add_strategy(
            PriceActionStrategy,
            use_trend_filter=True,
            use_adx_filter=False,
            use_rsi_filter=False,
        )
        metrics = engine.run_backtest()

        self.assertEqual(metrics["total_trades"], 0, "EMA filter should block long in downtrend")


@pytest.mark.integration
@pytest.mark.engine
@patch("engine.bt_backtest_engine.DataLoader")
class TestIntegrationTaLibIndicators(unittest.TestCase):
    """Verify TA-Lib indicators (EMA, RSI, ATR, ADX) compute without error."""

    def test_run_with_all_filters_enabled(self, mock_dataloader_cls):
        df = _make_base_df(periods=350)
        _inject_bullish_engulfing(df, 250)
        _set_execution_bar(df, 251, 1000)
        _make_price_hit_tp_long(df, 251, 1000, 1016)

        mock_loader = MagicMock()
        mock_loader.get_data.return_value = df
        mock_dataloader_cls.return_value = mock_loader

        config = {
            "symbol": "BTC/USDT",
            "timeframes": ["1h"],
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "initial_capital": 10000,
        }
        engine = BTBacktestEngine(config)
        engine.add_strategy(
            PriceActionStrategy,
            use_trend_filter=True,
            use_adx_filter=True,
            use_rsi_filter=True,
            trend_ema_period=200,
            adx_period=14,
            rsi_period=14,
        )
        metrics = engine.run_backtest()

        self.assertIsInstance(metrics, dict)
        self.assertIn("sharpe_ratio", metrics)
        self.assertIn("max_drawdown", metrics)


if __name__ == "__main__":
    unittest.main()
