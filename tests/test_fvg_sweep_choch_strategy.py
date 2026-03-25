from types import SimpleNamespace

from strategies.fvg_sweep_choch_strategy import FvgSweepChochStrategy


class _Line:
    def __init__(self, value):
        self.value = value

    def __getitem__(self, idx):
        return self.value


def _build_strategy(
    *,
    use_ote_filter=True,
    ote_min_retracement=0.62,
    use_min_pullback_filter=True,
    min_pullback_atr_mult=1.0,
    htf_atr=5.0,
):
    strategy = FvgSweepChochStrategy.__new__(FvgSweepChochStrategy)
    strategy.params = SimpleNamespace(
        use_ote_filter=use_ote_filter,
        ote_min_retracement=ote_min_retracement,
        use_min_pullback_filter=use_min_pullback_filter,
        min_pullback_atr_mult=min_pullback_atr_mult,
    )
    strategy._bool_param = lambda name, default=False: bool(getattr(strategy.params, name, default))
    strategy._float_param = lambda name, default, min_value=None: max(
        min_value if min_value is not None else float("-inf"),
        float(getattr(strategy.params, name, default)),
    )
    strategy._to_valid_float = lambda value: None if value is None else float(value)
    strategy._htf_swing_highs = [{"bar": 10, "price": 120.0}]
    strategy._htf_swing_lows = [{"bar": 9, "price": 100.0}]
    strategy.atr_htf = _Line(htf_atr)
    return strategy


def test_ote_filter_allows_long_only_in_discount_zone():
    strategy = _build_strategy()
    assert strategy._passes_ote_filter("long", 107.5) is True
    assert strategy._passes_ote_filter("long", 108.0) is False


def test_ote_filter_allows_short_only_in_premium_zone():
    strategy = _build_strategy()
    assert strategy._passes_ote_filter("short", 112.5) is True
    assert strategy._passes_ote_filter("short", 112.0) is False


def test_ote_filter_is_bypassed_when_disabled():
    strategy = _build_strategy(use_ote_filter=False)
    assert strategy._passes_ote_filter("long", 119.0) is True
    assert strategy._passes_ote_filter("short", 101.0) is True


def test_min_pullback_filter_blocks_longs_too_close_to_htf_high():
    strategy = _build_strategy()
    assert strategy._passes_min_pullback_filter("long", 114.0) is True
    assert strategy._passes_min_pullback_filter("long", 116.0) is False


def test_min_pullback_filter_blocks_shorts_too_close_to_htf_low():
    strategy = _build_strategy()
    assert strategy._passes_min_pullback_filter("short", 106.0) is True
    assert strategy._passes_min_pullback_filter("short", 104.0) is False


def test_min_pullback_filter_is_bypassed_when_disabled():
    strategy = _build_strategy(use_min_pullback_filter=False)
    assert strategy._passes_min_pullback_filter("long", 119.0) is True
    assert strategy._passes_min_pullback_filter("short", 101.0) is True


def test_choch_mode_confirmed_changes_setup_phase():
    strategy = FvgSweepChochStrategy.__new__(FvgSweepChochStrategy)
    strategy.params = SimpleNamespace(
        enable_sweep=True,
        enable_structure_filter=True,
        choch_mode="confirmed",
        sweep_min_atr_mult=0.15,
    )
    strategy._bool_param = lambda name, default=False: bool(getattr(strategy.params, name, default))
    strategy._float_param = lambda name, default, min_value=None: max(
        min_value if min_value is not None else float("-inf"),
        float(getattr(strategy.params, name, default)),
    )
    strategy._to_valid_float = lambda value: None if value is None else float(value)
    strategy.order = None
    strategy.position = None
    strategy._allows_direction = lambda direction: direction == "long"
    strategy._get_active_fvg = lambda direction: {"top": 110.0, "bottom": 100.0, "midpoint": 105.0} if direction == "long" else None
    strategy._is_price_in_zone = lambda zone: True
    strategy._last_internal_swing_low = {"price": 102.0}
    strategy._last_internal_swing_high = {"price": 108.0}
    strategy.low_line = _Line(100.0)
    strategy.close_line = _Line(103.0)
    strategy.high_line = _Line(104.0)
    strategy.atr = _Line(5.0)
    strategy.data_ltf = [None] * 10
    strategy._active_setup = None

    strategy._try_capture_sweep()

    assert strategy._active_setup is not None
    assert strategy._active_setup["phase"] == "await_confirmed_swing"
    assert strategy._active_setup["choch_level"] is None


def test_entry_type_limit_uses_limit_branch():
    strategy = FvgSweepChochStrategy.__new__(FvgSweepChochStrategy)
    strategy.params = SimpleNamespace(entry_type="limit")
    strategy._active_setup = {"direction": "long", "phase": "ready_to_enter", "zone": {"top": 110.0, "bottom": 100.0}}
    strategy.position = None
    strategy.order = None
    strategy._is_price_in_zone = lambda zone: True
    called = {"limit": 0, "market": 0}
    strategy._place_limit_entry = lambda direction: called.__setitem__("limit", called["limit"] + 1)
    strategy._place_market_entry = lambda direction, entry_price: called.__setitem__("market", called["market"] + 1)
    strategy.close_line = _Line(105.0)

    strategy._try_place_entry()

    assert called["limit"] == 1
    assert called["market"] == 0


def test_limit_mode_fvg_midpoint_changes_limit_entry_price():
    strategy = FvgSweepChochStrategy.__new__(FvgSweepChochStrategy)
    strategy.params = SimpleNamespace(limit_mode="fvg_midpoint", use_midpoint=True)
    strategy._active_setup = {
        "zone": {"midpoint": 105.0},
        "choch_level": 108.0,
    }
    captured = {}
    strategy._place_entry_order = lambda direction, entry_price, exectype: captured.update(
        {"direction": direction, "entry_price": entry_price, "exectype": exectype}
    )

    strategy._place_limit_entry("long")

    assert captured["direction"] == "long"
    assert captured["entry_price"] == 105.0


def test_tp_mode_rr_changes_take_profit_math():
    strategy = FvgSweepChochStrategy.__new__(FvgSweepChochStrategy)
    strategy.params = SimpleNamespace(tp_mode="rr", risk_reward_ratio=2.0)
    strategy._float_param = lambda name, default, min_value=None: max(
        min_value if min_value is not None else float("-inf"),
        float(getattr(strategy.params, name, default)),
    )
    strategy._htf_swing_highs = [{"price": 111.0}]
    strategy._htf_swing_lows = [{"price": 90.0}]

    target, reason = strategy._resolve_take_profit("long", 100.0, 95.0)

    assert target == 110.0
    assert reason == "Entry + (Risk * RR)"
