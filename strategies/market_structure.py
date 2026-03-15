from __future__ import annotations

from typing import Any, Sequence


def is_confirmed_swing_high(
    candidate_high: float,
    left_highs: Sequence[Any],
    right_highs: Sequence[Any],
) -> bool:
    candidate = float(candidate_high)
    for value in left_highs:
        if candidate <= float(value):
            return False
    for value in right_highs:
        if candidate <= float(value):
            return False
    return True


def is_confirmed_swing_low(
    candidate_low: float,
    left_lows: Sequence[Any],
    right_lows: Sequence[Any],
) -> bool:
    candidate = float(candidate_low)
    for value in left_lows:
        if candidate >= float(value):
            return False
    for value in right_lows:
        if candidate >= float(value):
            return False
    return True


def advance_structure_state(
    close_value: float,
    last_swing_high: float | None,
    last_swing_low: float | None,
    current_structure: int | float = 0,
) -> int:
    if last_swing_high is not None and float(close_value) > float(last_swing_high):
        return 1
    if last_swing_low is not None and float(close_value) < float(last_swing_low):
        return -1
    if current_structure > 0:
        return 1
    if current_structure < 0:
        return -1
    return 0


def compute_market_structure_levels(
    highs: Sequence[Any],
    lows: Sequence[Any],
    closes: Sequence[Any],
    pivot_span: int = 2,
) -> tuple[list[float], list[float], list[float]]:
    """
    Compute BOS-only market structure from confirmed swing highs/lows.

    The returned arrays are aligned with the input bars:
    - sh_level: last confirmed swing high carried forward
    - sl_level: last confirmed swing low carried forward
    - structure: 1 / -1 only after BOS, otherwise carries prior state or stays 0
    """
    span = max(1, int(pivot_span))
    count = min(len(highs), len(lows), len(closes))
    nan = float("nan")

    sh_out = [nan] * count
    sl_out = [nan] * count
    st_out = [0.0] * count

    last_sh: float | None = None
    last_sl: float | None = None
    structure = 0

    for i in range(count):
        if i >= span * 2:
            c_idx = i - span
            cand_high = float(highs[c_idx])
            cand_low = float(lows[c_idx])
            if is_confirmed_swing_high(
                cand_high,
                highs[c_idx - span:c_idx],
                highs[c_idx + 1:c_idx + span + 1],
            ):
                last_sh = cand_high
            if is_confirmed_swing_low(
                cand_low,
                lows[c_idx - span:c_idx],
                lows[c_idx + 1:c_idx + span + 1],
            ):
                last_sl = cand_low

        structure = advance_structure_state(
            close_value=float(closes[i]),
            last_swing_high=last_sh,
            last_swing_low=last_sl,
            current_structure=structure,
        )
        sh_out[i] = last_sh if last_sh is not None else nan
        sl_out[i] = last_sl if last_sl is not None else nan
        st_out[i] = float(structure)

    return sh_out, sl_out, st_out


def compute_fractal_markers(
    highs: Sequence[Any],
    lows: Sequence[Any],
    pivot_span: int = 2,
) -> tuple[list[float], list[float]]:
    """
    Compute strict fractal markers aligned to pivot bars.
    """
    span = max(1, int(pivot_span))
    count = min(len(highs), len(lows))
    nan = float("nan")
    fr_high = [nan] * count
    fr_low = [nan] * count

    for c_idx in range(span, count - span):
        cand_high = float(highs[c_idx])
        cand_low = float(lows[c_idx])
        if is_confirmed_swing_high(
            cand_high,
            highs[c_idx - span:c_idx],
            highs[c_idx + 1:c_idx + span + 1],
        ):
            fr_high[c_idx] = cand_high
        if is_confirmed_swing_low(
            cand_low,
            lows[c_idx - span:c_idx],
            lows[c_idx + 1:c_idx + span + 1],
        ):
            fr_low[c_idx] = cand_low

    return fr_high, fr_low
