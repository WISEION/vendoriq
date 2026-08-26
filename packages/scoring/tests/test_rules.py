"""One case per rule kind, at the boundary where a mis-port would show.

The two asymmetries this file exists to pin down (README §2):

* ``thresh`` compares with strict ``<``; ``bands`` / ``ongoing`` / ``leadtime`` use ``<=``.
  A value exactly on a ``thresh`` cut therefore falls to the *next* band, while a value
  exactly on a ``bands`` limit stays in the current one.
* ``ongoing`` scores 25 % of the weight for *zero* ongoing projects — idle capacity is
  available capacity — while ``leadtime`` scores 0 for an unknown (zero-day) lead time.
"""

from __future__ import annotations

from typing import Any, cast

import pytest
from vendoriq_scoring import Criterion, classify, load_model, r1, score, score_criterion


def criterion(
    kind: str, maximum: float, spec: object = None, *, code: str = "X.1", ko: bool = False
) -> Criterion:
    """A criterion literal, so a rule can be tested without a whole model."""
    row: dict[str, Any] = {
        "code": code,
        "group": "X",
        "max": maximum,
        "kind": kind,
        "spec": spec,
        "ko": ko,
        "name_az": "test",
        "name_en": "test",
        "unit": None,
        "evidence_doc": None,
    }
    return cast(Criterion, row)


# --------------------------------------------------------------------------- rubric


@pytest.mark.parametrize(
    ("value", "expected"),
    [(0, 0.0), (1, 1.7), (2, 3.3), (3, 5.0), (None, 0.0), ("", 0.0)],
)
def test_rubric_is_value_over_three_times_max(value: object, expected: float) -> None:
    """5-point criterion: 1/3 → 1.666… → 1.7, 2/3 → 3.333… → 3.3. R1, not truncation."""
    assert score_criterion(criterion("rubric", 5), value) == pytest.approx(expected)


def test_rubric_above_three_is_not_clamped() -> None:
    """The reference does not clamp; a 4 in a 0–3 cell is a data-entry bug, not a score."""
    assert score_criterion(criterion("rubric", 5), 6) == pytest.approx(10.0)


# ---------------------------------------------------------------------------- bands

BANDS = {"zero": 0, "bands": [[3, 1], [7, 2]], "top": 3}


@pytest.mark.parametrize(
    ("years", "expected"),
    [(0, 0), (1, 1), (3, 1), (3.5, 2), (7, 2), (7.1, 3), (30, 3)],
)
def test_bands_uses_less_than_or_equal_and_literal_points(years: float, expected: float) -> None:
    """3 and 7 stay in their band (``<=``), and the points are literal — never × max."""
    assert score_criterion(criterion("bands", 3, BANDS), years) == expected


def test_bands_points_are_not_scaled_by_max() -> None:
    """A 3-point and a 30-point bands criterion award the same literal points."""
    assert score_criterion(criterion("bands", 30, BANDS), 5) == 2


def test_bands_zero_comes_from_the_spec() -> None:
    assert score_criterion(criterion("bands", 3, {**BANDS, "zero": 0}), 0) == 0


# --------------------------------------------------------------------------- thresh

CUTS = {"cuts": [[500000, 0], [1000000, 0.25], [5000000, 0.5], [10000000, 0.75]], "top": 1}


@pytest.mark.parametrize(
    ("turnover", "expected"),
    [
        (0, 0.0),
        (499_999, 0.0),
        (500_000, 2.0),  # exactly on the cut → strict < fails → the NEXT band, 25 % of 8
        (999_999, 2.0),
        (1_000_000, 4.0),  # 50 % of 8
        (5_000_000, 6.0),  # 75 % of 8
        (9_999_999, 6.0),
        (10_000_000, 8.0),  # above every cut → the full max, unrounded
        (99_000_000, 8.0),
    ],
)
def test_thresh_uses_strict_less_than(turnover: float, expected: float) -> None:
    assert score_criterion(criterion("thresh", 8, CUTS), turnover) == pytest.approx(expected)


def test_thresh_ignores_spec_top() -> None:
    """``top`` is carried in the JSON for comparability; the thresh branch never reads it."""
    with_top = criterion("thresh", 8, {**CUTS, "top": 0.1})
    assert score_criterion(with_top, 20_000_000) == pytest.approx(8.0)


def test_thresh_rounds_each_fraction() -> None:
    """9 × 0.3 = 2.7 exactly; 9 × 0.7 = 6.3 — both through R1, never truncated."""
    cuts = {"cuts": [[2, 0], [5, 0.3], [10, 0.7]], "top": 1}
    assert score_criterion(criterion("thresh", 9, cuts), 4) == pytest.approx(2.7)
    assert score_criterion(criterion("thresh", 9, cuts), 9) == pytest.approx(6.3)


# -------------------------------------------------------------------------- ongoing


@pytest.mark.parametrize(
    ("ongoing", "expected"),
    [
        (0, 1.0),  # 25 % of 4 — no ongoing work means free capacity, not zero merit
        (1, 2.0),
        (3, 2.0),  # <= 3
        (4, 4.0),
        (6, 4.0),  # <= 6 → the full weight: busy, but not overcommitted
        (7, 3.0),  # > 6 → 75 %, the overload penalty
        (40, 3.0),
    ],
)
def test_ongoing_curve(ongoing: float, expected: float) -> None:
    assert score_criterion(criterion("ongoing", 4), ongoing) == pytest.approx(expected)


def test_ongoing_is_not_zero_at_zero_but_leadtime_is() -> None:
    """The deliberate asymmetry, in one assertion."""
    assert score_criterion(criterion("ongoing", 4), 0) > 0
    assert score_criterion(criterion("leadtime", 6), 0) == 0


# ------------------------------------------------------------------------- leadtime


@pytest.mark.parametrize(
    ("days", "expected"),
    [
        (0, 0.0),  # unknown lead time earns nothing
        (1, 6.0),
        (3, 6.0),  # <= 3 days → the full weight
        (4, 4.5),  # 75 % of 6
        (7, 4.5),
        (8, 3.0),  # 50 %
        (14, 3.0),
        (15, 1.5),  # 25 %
        (30, 1.5),
        (31, 0.0),  # beyond a month the supplier is no use for a live site
        (365, 0.0),
    ],
)
def test_leadtime_is_an_inverse_curve(days: float, expected: float) -> None:
    assert score_criterion(criterion("leadtime", 6), days) == pytest.approx(expected)


# ------------------------------------------------------------------------ the engine


def test_unknown_kind_is_an_error_not_a_zero() -> None:
    """A typo in a model version must fail loudly, not silently score 0."""
    with pytest.raises(ValueError, match="unknown criterion kind"):
        score_criterion(criterion("quadratic", 5), 3)


def test_missing_criteria_are_zero_never_an_error() -> None:
    """An empty map scores, it does not raise. The only point is C.3's ongoing zero-case."""
    model = load_model("sub-4")
    result = score(model, {})
    assert result.per["A.1"] == 0.0
    assert result.per["C.3"] == 1.0  # ongoing: 25 % of 4 for no ongoing work
    assert result.total == 1.0
    assert result.ko is False
    assert result.cls == "KO"


def test_every_group_is_present_even_when_it_scores_zero() -> None:
    model = load_model("sub-4")
    result = score(model, {})
    assert set(result.groups) == {"A", "B", "C", "D", "E", "F", "G"}
    assert result.groups == {"A": 0.0, "B": 0.0, "C": 1.0, "D": 0.0, "E": 0.0, "F": 0.0, "G": 0.0}


def test_group_totals_round_after_every_addition() -> None:
    """The rule that makes the 13 totals match, isolated.

    Three rubric criteria in group D of ``sub-4`` (max 3, 4, 3) scored 1/3 each give
    1.0 + 1.3 + 1.0 = 3.3 with per-criterion rounding. Summing the *unrounded* 1.0,
    1.333…, 1.0 and rounding once gives 3.3 too — so the difference is asserted directly
    on the accumulator instead, where a half-tenth is created and then re-rounded.
    """
    accumulated = 0.0
    for step in (0.05, 0.05, 0.05):
        accumulated = r1(accumulated + step)
    assert accumulated == pytest.approx(0.3)  # round-after-each: 0.1 + 0.1 + 0.1
    assert r1(0.05 + 0.05 + 0.05) == pytest.approx(0.2)  # round-once would say 0.2


# ------------------------------------------------------------------- KO and classes


def test_knock_out_is_decided_on_the_raw_value() -> None:
    model = load_model("sub-4")
    full = dict.fromkeys([c["code"] for c in model.criteria], 3)
    assert score(model, full).ko is True

    for ko_code in ("A.1", "A.4", "F.1"):
        failed = {**full, ko_code: 0}
        result = score(model, failed)
        assert result.ko is False, ko_code
        assert result.cls == "KO", ko_code
        # The total is still computed — the evaluation screen shows both (spec §10).
        assert result.total > 0


def test_knock_out_survives_a_high_total() -> None:
    """A vendor can be excellent on paper and still be rejected for a missing licence."""
    model = load_model("sub-4")
    raw = {
        "A.1": 0,  # no construction licence
        "A.2": 20,
        "A.3": 3,
        "A.4": 3,
        "B.1": 20_000_000,
        "B.2": 5_000_000,
        "B.3": 3,
        "B.4": 3,
        "C.1": 20,
        "C.2": 9_000_000,
        "C.3": 5,
        "C.4": 3,
        "D.1": 3,
        "D.2": 3,
        "D.3": 3,
        "E.1": 200,
        "E.2": 30,
        "E.3": 3,
        "E.4": 3,
        "F.1": 3,
        "F.2": 3,
        "F.3": 3,
        "G.1": 3,
        "G.2": 10,
    }
    result = score(model, raw)
    assert result.total >= 90
    assert result.cls == "KO"


@pytest.mark.parametrize(
    ("total", "expected"),
    [(100, "A"), (90, "A"), (89.9, "B"), (80, "B"), (79.9, "C"), (70, "C"), (69.9, "D"),
     (60, "D"), (59.9, "F"), (0, "F")],
)  # fmt: skip
def test_class_bands(total: float, expected: str) -> None:
    model = load_model("sub-4")
    assert classify(model, total, ko_passed=True) == expected


def test_class_is_ko_whatever_the_total() -> None:
    model = load_model("sub-4")
    assert classify(model, 99.0, ko_passed=False) == "KO"
    assert classify(model, 0.0, ko_passed=False) == "KO"


def test_pass_mark_is_the_c_band() -> None:
    """Spec §10: pass is 70, which is exactly where class C starts."""
    model = load_model("sub-4")
    assert model.pass_mark == 70
    assert classify(model, model.pass_mark, ko_passed=True) == "C"
    assert classify(model, model.pass_mark - 0.1, ko_passed=True) == "D"
