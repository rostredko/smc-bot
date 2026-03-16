"""Engine utility functions."""


def safe_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
