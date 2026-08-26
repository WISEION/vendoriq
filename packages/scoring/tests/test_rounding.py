"""``R1`` must be ``Math.round(x * 10) / 10``, not Python's ``round``.

Python rounds halves to even: ``round(0.05, 1)`` is ``0.0`` and ``round(0.25, 1)`` is
``0.2``. The workbook — and therefore the reference JS — rounds halves up. On a 24-row
model the difference compounds into whole points, which is why this has its own test file.
"""

from __future__ import annotations

import math
from fractions import Fraction

import pytest
from vendoriq_scoring import r0, r1, to_number


def js_math_round(x: float) -> float:
    """ECMA-262 ``Math.round``: ``floor(x + 0.5)``. The oracle for the property test."""
    return math.floor(x + 0.5)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0.0, 0.0),
        (0.04, 0.0),
        (0.05, 0.1),  # Python's round() says 0.0 here
        (0.15, 0.2),  # and 0.1 here
        (0.25, 0.3),  # and 0.2 here
        (0.35, 0.4),
        (2.25, 2.3),
        (2.35, 2.4),
        (1.0, 1.0),
        (99.94999, 99.9),
        (99.95, 100.0),
    ],
)
def test_r1_rounds_halves_up(value: float, expected: float) -> None:
    assert r1(value) == pytest.approx(expected, abs=1e-9)


def test_r1_disagrees_with_python_round_on_the_boundaries() -> None:
    """The test that would fail if someone "simplified" R1 to round(x, 1)."""
    disagreements = [x / 100 for x in range(0, 1000) if r1(x / 100) != round(x / 100, 1)]
    assert disagreements, "R1 must not be Python's banker's rounding"


def test_r1_matches_math_round_over_a_wide_range() -> None:
    """Property: for every tenth-boundary in [0, 100], R1(x) == Math.round(x*10)/10."""
    for hundredths in range(0, 10_001):
        x = hundredths / 100
        assert r1(x) == js_math_round(x * 10) / 10, x


def test_r1_matches_math_round_on_exact_half_boundaries() -> None:
    """Exact halves via Fraction, so the assertion is about the rule, not float noise."""
    for tenth in range(0, 200):
        exact = float(Fraction(2 * tenth + 1, 20))  # 0.05, 0.15, 0.25, …
        assert r1(exact) == pytest.approx((tenth + 1) / 10, abs=1e-9), exact


def test_r1_is_defined_for_negative_values_too() -> None:
    """No score is negative, but R1 must not silently do something else if one ever is."""
    assert r1(-0.05) == pytest.approx(0.0, abs=1e-9)  # Math.round(-0.5) is -0
    assert r1(-0.15) == pytest.approx(-0.1, abs=1e-9)
    assert r1(-2.25) == pytest.approx(-2.2, abs=1e-9)


def test_r0_is_math_round() -> None:
    assert r0(95.918) == 96
    assert r0(0.5) == 1
    assert r0(1.5) == 2  # Python's round(1.5) is 2 but round(2.5) is 2 — r0 says 3
    assert r0(2.5) == 3
    assert r0(-0.5) == 0


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, 0.0),
        ("", 0.0),
        ("   ", 0.0),
        ("abc", 0.0),
        (float("nan"), 0.0),
        (True, 1.0),
        (False, 0.0),
        (3, 3.0),
        (2.5, 2.5),
        ("12", 12.0),
        (" 12 ", 12.0),
        ("1400915571 / 7200482051", 1400915571.0),  # multi-value cell, brief §1.11
        ("85%", 0.85),  # percentage written as text
        ("1 234 567", 1234567.0),  # space as a thousands separator
        ("1,234,567.89", 1234567.89),
        ("1234,56", 1234.56),  # comma as the decimal separator
        ("385937 AZN", 385937.0),
        ("Müddətsiz", 0.0),  # "no expiry" is not a number
        ([], 0.0),
        ({"a": 1}, 0.0),
    ],
)
def test_to_number_is_number_v_or_zero(value: object, expected: float) -> None:
    assert to_number(value) == pytest.approx(expected, abs=1e-9)
