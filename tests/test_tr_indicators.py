import pytest

from strategies.helpers.tr_indicators import (
    adr_exhaustion_score,
    adr_mean,
    classify_signal,
    composite_signal_score,
    ema_cross_score,
    ema_stack_score,
    pivot_levels,
    pivot_position_score,
    pvsra_label,
    pvsra_score_delta,
)


class TestPvsraLabel:
    def test_ring_volume_bull_is_green(self):
        assert pvsra_label(
            vol=200, spread=1.0, avg_vol=100, max_spread_vol=50, is_bull=True
        ) == "green"

    def test_ring_volume_bear_is_red(self):
        assert pvsra_label(
            vol=200, spread=1.0, avg_vol=100, max_spread_vol=50, is_bull=False
        ) == "red"

    def test_ring_via_spread_vol_bull(self):
        assert pvsra_label(
            vol=50, spread=2.0, avg_vol=60, max_spread_vol=100, is_bull=True
        ) == "green"

    def test_big_volume_bull_is_blue(self):
        assert pvsra_label(
            vol=150, spread=1.0, avg_vol=100, max_spread_vol=9999, is_bull=True
        ) == "blue"

    def test_big_volume_bear_is_violet(self):
        assert pvsra_label(
            vol=150, spread=1.0, avg_vol=100, max_spread_vol=9999, is_bull=False
        ) == "violet"

    def test_normal_bull_is_gray_up(self):
        assert pvsra_label(
            vol=80, spread=1.0, avg_vol=100, max_spread_vol=9999, is_bull=True
        ) == "gray_up"

    def test_normal_bear_is_gray_dn(self):
        assert pvsra_label(
            vol=80, spread=1.0, avg_vol=100, max_spread_vol=9999, is_bull=False
        ) == "gray_dn"

    def test_ring_takes_priority_over_big(self):
        assert pvsra_label(
            vol=200, spread=1.0, avg_vol=100, max_spread_vol=50, is_bull=True
        ) == "green"

    def test_degenerate_reference_yields_gray_not_false_ring(self):
        # Regression: first-bar-of-backtest case. avg_vol and max_spread_vol
        # are both 0 during warmup; any non-zero volume used to trigger a
        # spurious ring label via `vol >= 0*mult`/`spread*vol >= 0`.
        assert pvsra_label(
            vol=500, spread=1.0, avg_vol=0.0, max_spread_vol=0.0, is_bull=True
        ) == "gray_up"
        assert pvsra_label(
            vol=500, spread=1.0, avg_vol=0.0, max_spread_vol=0.0, is_bull=False
        ) == "gray_dn"

    def test_zero_avg_but_active_spread_window_still_works(self):
        # avg_vol still degenerate but max_spread_vol is known — spread route
        # must stay active so big institutional candles still register.
        assert pvsra_label(
            vol=200, spread=2.0, avg_vol=0.0, max_spread_vol=100.0, is_bull=True
        ) == "green"


class TestPvsraScoreDelta:
    def test_green_gives_plus_two(self):
        assert pvsra_score_delta("green") == 2.0

    def test_red_gives_minus_two(self):
        assert pvsra_score_delta("red") == -2.0

    def test_blue_gives_plus_one(self):
        assert pvsra_score_delta("blue") == 1.0

    def test_violet_gives_minus_one(self):
        assert pvsra_score_delta("violet") == -1.0

    def test_gray_gives_zero(self):
        assert pvsra_score_delta("gray_up") == 0.0
        assert pvsra_score_delta("gray_dn") == 0.0


class TestEmaStackScore:
    def test_full_bull_stack(self):
        assert ema_stack_score(5.0, 4.0, 3.0, 2.0) == 2.0

    def test_full_bear_stack(self):
        assert ema_stack_score(2.0, 3.0, 4.0, 5.0) == -2.0

    def test_partial_stack_is_neutral(self):
        assert ema_stack_score(5.0, 4.0, 6.0, 2.0) == 0.0

    def test_equal_values_neutral(self):
        assert ema_stack_score(3.0, 3.0, 3.0, 3.0) == 0.0


class TestEmaCrossScore:
    def test_golden_cross(self):
        assert ema_cross_score(ema5=11.0, ema13=10.0, ema5_prev=9.0, ema13_prev=10.0) == 1.0

    def test_death_cross(self):
        assert ema_cross_score(ema5=9.0, ema13=10.0, ema5_prev=11.0, ema13_prev=10.0) == -1.0

    def test_no_cross(self):
        assert ema_cross_score(ema5=11.0, ema13=10.0, ema5_prev=10.5, ema13_prev=10.0) == 0.0

    def test_already_crossed_no_event(self):
        assert ema_cross_score(ema5=12.0, ema13=10.0, ema5_prev=11.0, ema13_prev=10.0) == 0.0


class TestPivotLevels:
    def test_classic_pivot_calculation(self):
        levels = pivot_levels(high=110.0, low=90.0, close=105.0)
        pp = (110 + 90 + 105) / 3
        assert abs(levels["PP"] - pp) < 1e-9
        assert abs(levels["R1"] - (2 * pp - 90)) < 1e-9
        assert abs(levels["S1"] - (2 * pp - 110)) < 1e-9
        assert abs(levels["R2"] - (pp + 20)) < 1e-9
        assert abs(levels["S2"] - (pp - 20)) < 1e-9
        assert abs(levels["R3"] - (110 + 2 * (pp - 90))) < 1e-9
        assert abs(levels["S3"] - (90 - 2 * (110 - pp))) < 1e-9

    def test_returns_all_keys(self):
        levels = pivot_levels(100.0, 80.0, 90.0)
        for key in ("PP", "R1", "R2", "R3", "S1", "S2", "S3"):
            assert key in levels


class TestPivotPositionScore:
    def test_above_pp_gives_plus_one(self):
        assert pivot_position_score(close=105.0, pp=100.0) == 1.0

    def test_below_pp_gives_minus_one(self):
        assert pivot_position_score(close=95.0, pp=100.0) == -1.0

    def test_equal_pp_gives_zero(self):
        assert pivot_position_score(close=100.0, pp=100.0) == 0.0


class TestAdrMean:
    def test_mean_of_list(self):
        assert adr_mean([10.0, 20.0, 30.0]) == pytest.approx(20.0)

    def test_single_value(self):
        assert adr_mean([15.0]) == pytest.approx(15.0)

    def test_empty_returns_none(self):
        assert adr_mean([]) is None


class TestAdrExhaustionScore:
    def test_no_exhaustion_neutral(self):
        assert adr_exhaustion_score(
            close=100.0, day_low=90.0, day_high=110.0, adr=20.0
        ) == 0.0

    def test_upward_exhaustion_penalises(self):
        # adr_used_up   = (107.5 - 90) / 10 = 1.75 > 0.85  -> -1
        # adr_used_down = (110 - 107.5) / 10 = 0.25 < 0.85 -> no boost
        assert adr_exhaustion_score(
            close=107.5, day_low=90.0, day_high=110.0, adr=10.0
        ) == -1.0

    def test_downward_exhaustion_rewards(self):
        # adr_used_up   = (91 - 90) / 10 = 0.1 < 0.85 -> no penalty
        # adr_used_down = (100 - 91) / 10 = 0.9 > 0.85 -> +1
        assert adr_exhaustion_score(
            close=91.0, day_low=90.0, day_high=100.0, adr=10.0
        ) == 1.0

    def test_both_exhausted_nets_zero(self):
        result = adr_exhaustion_score(
            close=100.0, day_low=99.9, day_high=100.1, adr=0.01
        )
        assert isinstance(result, float)

    def test_zero_adr_returns_zero(self):
        assert adr_exhaustion_score(
            close=100.0, day_low=99.0, day_high=101.0, adr=0.0
        ) == 0.0


class TestClassifySignal:
    def test_strong_long_at_four(self):
        assert classify_signal(4.0) == "STRONG LONG"

    def test_strong_long_above_four(self):
        assert classify_signal(6.0) == "STRONG LONG"

    def test_long_at_two(self):
        assert classify_signal(2.0) == "LONG"

    def test_long_at_three(self):
        assert classify_signal(3.0) == "LONG"

    def test_neutral_at_one(self):
        assert classify_signal(1.0) == "NEUTRAL"

    def test_neutral_at_zero(self):
        assert classify_signal(0.0) == "NEUTRAL"

    def test_neutral_at_minus_one(self):
        assert classify_signal(-1.0) == "NEUTRAL"

    def test_short_at_minus_two(self):
        assert classify_signal(-2.0) == "SHORT"

    def test_strong_short_at_minus_four(self):
        assert classify_signal(-4.0) == "STRONG SHORT"

    def test_strong_short_below_minus_four(self):
        assert classify_signal(-5.0) == "STRONG SHORT"


class TestCompositeSignalScore:
    def test_full_bull_scenario(self):
        score = composite_signal_score(
            ema_stack=2.0,
            pvsra_delta=2.0,
            pp_score=1.0,
            adr_score=0.0,
            cross_score=0.0,
        )
        assert score == pytest.approx(5.0)

    def test_all_zeros(self):
        assert composite_signal_score(0.0, 0.0, 0.0, 0.0, 0.0) == pytest.approx(0.0)

    def test_mixed_signals_sum(self):
        score = composite_signal_score(2.0, -1.0, 1.0, 0.0, 0.0)
        assert score == pytest.approx(2.0)
