"""`sup-1` — the proposed supplier model, same engine, re-weighted groups.

The supplier model is the reason the engine is generic rather than a transcription of
``scoreSubcontractor``: it moves weight into Product & technical (25), Logistics (15,
including the inverse lead-time curve) and Commercial (15), and it moves the ISO 9001
criterion from group C to group F. Nothing about the arithmetic changes.
"""

from __future__ import annotations

import pytest
from vendoriq_scoring import load_model, score

SUPPLIER_GROUP_MAX = {"A": 15, "B": 15, "C": 25, "D": 15, "E": 15, "F": 10, "G": 5}


def test_group_maxima_sum_to_one_hundred() -> None:
    model = load_model("sup-1")
    declared = {group["group"]: group["max"] for group in model.groups}
    assert declared == SUPPLIER_GROUP_MAX
    assert sum(declared.values()) == 100

    # And the criteria actually add up to the group maxima they claim.
    from_criteria: dict[str, float] = dict.fromkeys(declared, 0.0)
    for criterion in model.criteria:
        from_criteria[criterion["group"]] += criterion["max"]
    assert from_criteria == pytest.approx(declared)


def test_a_perfect_supplier_scores_one_hundred() -> None:
    """Every rubric at 3, every threshold above its top cut, lead time at 1 day."""
    model = load_model("sup-1")
    raw = {
        "A.1": 3, "A.2": 20, "A.3": 3, "A.4": 3,
        "B.1": 40_000_000, "B.2": 5_000_000, "B.3": 3, "B.4": 3,
        "C.1": 3, "C.2": 3, "C.3": 3, "C.4": 3,
        "D.1": 3, "D.2": 3, "D.3": 1,
        "E.1": 3, "E.2": 3, "E.3": 3,
        "F.1": 3, "F.2": 3, "F.3": 3,
        "G.1": 10, "G.2": 3,
    }  # fmt: skip
    result = score(model, raw)
    assert result.total == 100.0
    assert result.cls == "A"
    assert result.ko is True


def test_the_lead_time_curve_is_the_only_inverse_criterion() -> None:
    """D.3 is worth 6; every step down the curve is a quarter of it (README §2)."""
    model = load_model("sup-1")
    lead_time = next(c for c in model.criteria if c["code"] == "D.3")
    assert lead_time["kind"] == "leadtime"
    assert lead_time["max"] == 6
    assert [c["kind"] for c in model.criteria].count("leadtime") == 1

    base = {"A.1": 3, "A.4": 3, "C.3": 3}
    points = {
        days: score(model, {**base, "D.3": days}).per["D.3"] for days in (0, 3, 7, 14, 30, 31)
    }
    assert points == {0: 0.0, 3: 6.0, 7: 4.5, 14: 3.0, 30: 1.5, 31: 0.0}


def test_a_faster_supplier_never_scores_lower() -> None:
    """Monotonic between 1 and 30 days — a shorter lead time is never punished."""
    model = load_model("sup-1")
    base = {"A.1": 3, "A.4": 3, "C.3": 3}
    curve = [score(model, {**base, "D.3": days}).per["D.3"] for days in range(1, 31)]
    assert curve == sorted(curve, reverse=True)


def test_supplier_knock_outs_are_registration_tax_and_authorisation() -> None:
    """Spec §10.2: a supplier with no manufacturer authorisation is not a supplier."""
    model = load_model("sup-1")
    assert [c["code"] for c in model.criteria if c["ko"]] == ["A.1", "A.4", "C.3"]

    passing = {"A.1": 3, "A.4": 3, "C.3": 3}
    assert score(model, passing).ko is True
    for code in passing:
        assert score(model, {**passing, code: 0}).cls == "KO", code


def test_iso_9001_sits_in_group_f_for_suppliers() -> None:
    """The one criterion that changes group between the models — the matching code
    depends on it (``_certificate_held`` accepts C.4 *or* F.1)."""
    sub = {c["code"]: c["name_en"] for c in load_model("sub-4").criteria}
    sup = {c["code"]: c["name_en"] for c in load_model("sup-1").criteria}
    assert sub["C.4"] == "ISO 9001"
    assert sup["F.1"] == "ISO 9001"


def test_the_supplier_model_is_still_a_proposal() -> None:
    assert load_model("sup-1").status == "proposed"
