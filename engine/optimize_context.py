"""
Context for optimization progress logging.
When run_backtest_optimize sets this, BaseStrategy logs each combo in __init__ and stop().
"""

import threading

_log_opt_progress = False
_opt_total_combos = 0
_opt_combo_counter = 0
_current_combo: int | None = None
_combo_lock = threading.Lock()


def set_opt_progress_logging(enabled: bool, total_combos: int = 0) -> None:
    global _log_opt_progress, _opt_total_combos, _opt_combo_counter, _current_combo
    _log_opt_progress = enabled
    _opt_total_combos = total_combos
    _opt_combo_counter = 0
    _current_combo = None


def should_log_opt_progress() -> bool:
    return _log_opt_progress


def next_opt_combo() -> int:
    global _opt_combo_counter
    with _combo_lock:
        _opt_combo_counter += 1
        return _opt_combo_counter


def get_opt_total() -> int:
    return _opt_total_combos


def set_current_combo(n: int) -> None:
    global _current_combo
    with _combo_lock:
        _current_combo = n


def get_current_combo() -> int | None:
    with _combo_lock:
        return _current_combo


def clear_current_combo() -> None:
    global _current_combo
    with _combo_lock:
        _current_combo = None


class OptComboLogFilter:
    """Logging filter that prepends [combo N/M] to messages when a combo is running."""

    def filter(self, record):
        n = get_current_combo()
        if n is not None and get_opt_total() > 0:
            msg = record.getMessage()
            if msg.startswith("Opt combo ") or ("Combo " in msg and " done:" in msg):
                return True  # already identifies combo
            prefix = f"[combo {n}/{get_opt_total()}] "
            record.msg = prefix + msg
            record.args = ()  # already formatted
        return True
