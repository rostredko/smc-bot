"""
Integration test: optimize run → save best variant as template → single backtest from template.
Asserts that single backtest results match the best variant from the optimize run.
"""
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

import pandas as pd

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "web-dashboard"))

from engine.bt_backtest_engine import BTBacktestEngine
from strategies.bt_price_action import PriceActionStrategy
from services.strategy_runtime import build_opt_strategy_config, build_runtime_strategy_config


def _mock_ohlcv_df(rows=120):
    """Minimal OHLCV data for backtest."""
    return pd.DataFrame({
        "open": [100.0] * rows,
        "high": [105.0] * rows,
        "low": [95.0] * rows,
        "close": [101.0] * rows,
        "volume": [1000] * rows,
    }, index=pd.date_range("2024-01-01", periods=rows, freq="h"))


def _build_config_from_variant(base_config: dict, variant: dict) -> dict:
    """
    Simulate frontend buildConfigFromVariant: merge variant params into base,
    strip optimize fields, set run_mode=single.
    """
    cfg = dict(base_config)
    base_st = dict(cfg.get("strategy_config") or {})
    params = variant.get("params") or {}

    clean_base = {}
    for k, v in base_st.items():
        clean_base[k] = params[k] if (isinstance(v, (list, tuple)) and k in params) else v

    strategy_config = {**clean_base, **params}
    out = {**cfg, "strategy_config": strategy_config}

    out.pop("run_mode", None)
    out.pop("opt_params", None)
    out.pop("opt_target_metric", None)
    out.pop("opt_timeframes", None)
    out["run_mode"] = "single"

    if isinstance(params.get("trailing_stop_distance"), (int, float)):
        out["trailing_stop_distance"] = params["trailing_stop_distance"]

    return out


@patch("engine.bt_backtest_engine.DataLoader")
class TestOptimizeSaveSingleParity(unittest.TestCase):
    """Optimize → save best as template → single backtest must match best variant."""

    def test_single_from_saved_variant_matches_best_optimize_run(self, mock_dataloader_cls):
        mock_loader = MagicMock()
        mock_loader.get_data.return_value = _mock_ohlcv_df(150)
        mock_dataloader_cls.return_value = mock_loader

        # 1. Base config (template-like) with opt_params
        base_config = {
            "symbol": "BTC/USDT",
            "timeframes": ["1h"],
            "start_date": "2024-01-01",
            "end_date": "2024-01-31",
            "initial_capital": 10000,
            "risk_per_trade": 2.0,
            "leverage": 10.0,
            "run_mode": "optimize",
            "opt_params": {
                "risk_reward_ratio": [1.5, 2.0],
                "sl_buffer_atr": [1.0, 1.3],
                "trailing_stop_distance": [0, 0.01],
            },
            "opt_target_metric": "sharpe_ratio",
            "strategy_config": {
                "use_trend_filter": False,
                "use_structure_filter": False,
                "use_adx_filter": False,
                "use_rsi_filter": False,
            },
        }

        # 2. Run optimize
        engine = BTBacktestEngine(base_config)
        opt_kwargs = build_opt_strategy_config(base_config)
        opt_result = engine.run_backtest_optimize(PriceActionStrategy, opt_kwargs, "sharpe_ratio")

        self.assertEqual(opt_result["run_mode"], "optimize")
        variants = opt_result.get("variants", [])
        self.assertGreater(len(variants), 0, "Optimize must produce variants")

        best = variants[0]

        # 3. Build single-run config from best variant (simulate Save from variant)
        single_config = _build_config_from_variant(base_config, best)
        self.assertEqual(single_config["run_mode"], "single")
        self.assertNotIn("opt_params", single_config)

        # 4. Run single backtest with that config
        single_engine = BTBacktestEngine(single_config)
        st_config = build_runtime_strategy_config(single_config)
        single_engine.add_strategy(PriceActionStrategy, **st_config)
        single_metrics = single_engine.run_backtest()

        self.assertNotEqual(single_metrics.get("cancelled"), True, "Single run must complete")

        # 5. Assert single results match best variant
        self.assertAlmostEqual(
            single_metrics["total_pnl"],
            best["total_pnl"],
            places=2,
            msg="Single total_pnl must match best variant",
        )
        self.assertAlmostEqual(
            single_metrics["total_trades"],
            best["total_trades"],
            msg="Single total_trades must match best variant",
        )
        self.assertAlmostEqual(
            single_metrics["win_rate"],
            best["win_rate"],
            places=4,
            msg="Single win_rate must match best variant",
        )
        self.assertAlmostEqual(
            single_metrics["profit_factor"],
            best["profit_factor"],
            places=2,
            msg="Single profit_factor must match best variant",
        )
        self.assertAlmostEqual(
            single_metrics["max_drawdown"],
            best["max_drawdown"],
            places=2,
            msg="Single max_drawdown must match best variant",
        )


if __name__ == "__main__":
    unittest.main()
