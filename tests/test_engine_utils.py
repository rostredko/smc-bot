"""Unit tests for engine/utils.py."""

import pytest

from engine.utils import safe_float


class TestSafeFloat:
    """Tests for safe_float."""

    def test_safe_float_valid_number(self):
        assert safe_float(42.5) == 42.5

    def test_safe_float_string_number(self):
        assert safe_float("3.14") == 3.14

    def test_safe_float_none_returns_zero(self):
        assert safe_float(None) == 0.0

    def test_safe_float_invalid_returns_zero(self):
        assert safe_float("not a number") == 0.0
