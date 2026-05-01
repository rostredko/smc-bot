"""Pure-Python indicator helpers for TradersRealityStrategy.

No backtrader or pandas dependency. All inputs are plain Python scalars/lists,
so every function is trivially unit-testable. Logic mirrors the signal math in
``scripts/market_analyzer.py`` (Python port of the Traders Reality PineScript).
"""
from __future__ import annotations

from typing import Optional


def pvsra_label(
    vol: float,
    spread: float,
    avg_vol: float,
    max_spread_vol: float,
    is_bull: bool,
    rv_mult: float = 2.0,
    bv_mult: float = 1.5,
) -> str:
    """Classify a bar as a PVSRA vector.

    Ring Volume (rv): ``vol >= avg_vol*rv_mult`` OR ``spread*vol >= max_spread_vol``.
    Big Volume   (bv): ``vol >= avg_vol*bv_mult`` AND NOT ring.
    Colors: green/red (ring), blue/violet (big), gray_up/gray_dn (normal).

    When the reference window has degenerate stats (``avg_vol <= 0`` AND
    ``max_spread_vol <= 0``) labeling falls back to gray — this protects the
    very first bars of a backtest from being misclassified as ring-volume.
    """
    if avg_vol <= 0 and max_spread_vol <= 0:
        return "gray_up" if is_bull else "gray_dn"

    cond_rv = (
        (avg_vol > 0 and vol >= avg_vol * rv_mult)
        or (max_spread_vol > 0 and spread * vol >= max_spread_vol)
    )
    cond_bv = (avg_vol > 0 and vol >= avg_vol * bv_mult) and not cond_rv
    if cond_rv:
        return "green" if is_bull else "red"
    if cond_bv:
        return "blue" if is_bull else "violet"
    return "gray_up" if is_bull else "gray_dn"


def pvsra_score_delta(label: str) -> float:
    """Signal score contribution for a PVSRA label (±2 for ring, ±1 for big)."""
    return {
        "green": 2.0,
        "red": -2.0,
        "blue": 1.0,
        "violet": -1.0,
        "gray_up": 0.0,
        "gray_dn": 0.0,
    }.get(label, 0.0)


def ema_stack_score(ema5: float, ema13: float, ema50: float, ema200: float) -> float:
    """Return +2 for full bull stack (5>13>50>200), -2 for full bear, 0 otherwise."""
    if ema5 > ema13 > ema50 > ema200:
        return 2.0
    if ema5 < ema13 < ema50 < ema200:
        return -2.0
    return 0.0


def ema_cross_score(
    ema5: float, ema13: float, ema5_prev: float, ema13_prev: float
) -> float:
    """Return +1 on golden cross (5 over 13), -1 on death cross, 0 otherwise."""
    if ema5 > ema13 and ema5_prev <= ema13_prev:
        return 1.0
    if ema5 < ema13 and ema5_prev >= ema13_prev:
        return -1.0
    return 0.0


def pivot_levels(high: float, low: float, close: float) -> dict:
    """Classic floor pivot levels computed from previous day's High/Low/Close."""
    pp = (high + low + close) / 3.0
    r1 = 2 * pp - low
    s1 = 2 * pp - high
    r2 = pp + (high - low)
    s2 = pp - (high - low)
    r3 = high + 2 * (pp - low)
    s3 = low - 2 * (high - pp)
    return {"PP": pp, "R1": r1, "R2": r2, "R3": r3, "S1": s1, "S2": s2, "S3": s3}


def pivot_position_score(close: float, pp: float) -> float:
    """Close strictly above PP: +1. Strictly below: -1. Equal: 0."""
    if close > pp:
        return 1.0
    if close < pp:
        return -1.0
    return 0.0


def adr_mean(daily_ranges: list) -> Optional[float]:
    """Mean of a list of daily High-Low ranges. Returns None if list is empty."""
    if not daily_ranges:
        return None
    return sum(daily_ranges) / len(daily_ranges)


def adr_exhaustion_score(
    close: float,
    day_low: float,
    day_high: float,
    adr: float,
    threshold: float = 0.85,
) -> float:
    """Penalise entry when price is near the extreme of the day's range.

    Price near day HIGH (``adr_used_up > threshold``): -1 (long exhausted).
    Price near day LOW  (``adr_used_down > threshold``): +1 (short exhausted).
    """
    if adr <= 0:
        return 0.0
    adr_used_up = (close - day_low) / adr
    adr_used_down = (day_high - close) / adr
    score = 0.0
    if adr_used_up > threshold:
        score -= 1.0
    if adr_used_down > threshold:
        score += 1.0
    return score


def classify_signal(score: float) -> str:
    """Map composite score to human-readable signal label."""
    if score >= 4:
        return "STRONG LONG"
    if score >= 2:
        return "LONG"
    if score <= -4:
        return "STRONG SHORT"
    if score <= -2:
        return "SHORT"
    return "NEUTRAL"


def composite_signal_score(
    ema_stack: float,
    pvsra_delta: float,
    pp_score: float,
    adr_score: float,
    cross_score: float,
) -> float:
    """Sum all component scores into the composite signal score."""
    return ema_stack + pvsra_delta + pp_score + adr_score + cross_score
