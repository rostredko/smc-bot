from types import SimpleNamespace
from unittest.mock import patch

from strategies.base_strategy import BaseStrategy


def _make_strategy() -> BaseStrategy:
    strategy = BaseStrategy.__new__(BaseStrategy)
    strategy.params = SimpleNamespace()
    return strategy


def test_log_signal_thesis_emits_trigger_filters_context_and_risk_plan():
    strategy = _make_strategy()
    entry_context = {
        "why_entry": [
            "Pattern: Bearish Engulfing",
            "Structure: Bearish (state=-1), POI [67000.00, 68000.00]",
            "EMA filter: HTF close below EMA200 ($69,100.00)",
            "ADX: 27.5 ≥ 21 (trend strength)",
        ],
        "indicators_at_entry": {
            "ATR": 512.4,
            "Structure": -1,
            "RSI": 47.1,
            "ADX": 27.5,
        },
    }

    with patch("strategies.base_strategy.logger.info") as info_mock:
        BaseStrategy._log_signal_thesis(
            strategy,
            "2026-03-01 04:00:00",
            entry_context=entry_context,
            sl_price_ref=70125.45,
            tp_price_ref=66462.00,
            sl_calc_expr="SH_Level_1D (69720.12) + (ATR_1D * 0.5)",
            tp_calc_expr="max(Entry - (Risk * RR), SL_Level_1D 66462.00)",
        )

    logged_lines = [call.args[0] for call in info_mock.call_args_list]

    assert len(logged_lines) == 4
    assert "SIGNAL THESIS: Trigger: Bearish Engulfing" in logged_lines[0]
    assert "SIGNAL THESIS: Filters: Structure: Bearish" in logged_lines[1]
    assert "Structure=bearish" in logged_lines[2]
    assert "SIGNAL THESIS: Risk plan: SL 70125.45 via SH_Level_1D" in logged_lines[3]
