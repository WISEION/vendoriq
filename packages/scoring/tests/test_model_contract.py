"""Contract tests for the shipped scoring models.

These assert the *data*, not the engine — the engine lands in phase 1A. If one of these
fails, a model JSON drifted away from spec §10 and the drift must be a new version.
"""

from __future__ import annotations

import pytest
from vendoriq_scoring import BUILTIN_MODEL_VERSIONS, ScoringModel, load_model

SUB_GROUP_MAX = {"A": 15, "B": 20, "C": 25, "D": 10, "E": 15, "F": 10, "G": 5}
SUP_GROUP_MAX = {"A": 15, "B": 15, "C": 25, "D": 15, "E": 15, "F": 10, "G": 5}


@pytest.fixture(params=BUILTIN_MODEL_VERSIONS)
def model(request: pytest.FixtureRequest) -> ScoringModel:
    return load_model(request.param)


def test_every_builtin_version_loads(model: ScoringModel) -> None:
    assert model.version in BUILTIN_MODEL_VERSIONS
    assert model.currency == "AZN"  # spec §16: data is AZN even where the sheet says USD
    assert model.pass_mark == 70
    assert model.validity_months == 12


def test_criteria_sum_to_one_hundred(model: ScoringModel) -> None:
    assert sum(c["max"] for c in model.criteria) == 100
    assert model.total_max == 100


def test_group_maxima_match_the_spec() -> None:
    sub = {g["group"]: g["max"] for g in load_model("sub-4").groups}
    sup = {g["group"]: g["max"] for g in load_model("sup-1").groups}
    assert sub == SUB_GROUP_MAX
    assert sup == SUP_GROUP_MAX


def test_knock_out_criteria() -> None:
    sub_ko = [c["code"] for c in load_model("sub-4").criteria if c["ko"]]
    sup_ko = [c["code"] for c in load_model("sup-1").criteria if c["ko"]]
    assert sub_ko == ["A.1", "A.4", "F.1"]  # licence, tax clearance, HSE policy
    assert sup_ko == ["A.1", "A.4", "C.3"]  # registration, tax clearance, authorisation


def test_criteria_are_well_formed(model: ScoringModel) -> None:
    codes = [c["code"] for c in model.criteria]
    assert len(codes) == len(set(codes)), "criterion codes must be unique within a version"
    for criterion in model.criteria:
        assert criterion["group"] in {g["group"] for g in model.groups}
        assert criterion["name_az"] and criterion["name_en"], criterion["code"]
        if criterion["kind"] in {"thresh", "bands"}:
            assert criterion["spec"] is not None, criterion["code"]
        else:
            assert criterion["spec"] is None, criterion["code"]


def test_class_bands_are_descending_and_cover_zero(model: ScoringModel) -> None:
    mins = [band["min"] for band in model.classes]
    assert mins == sorted(mins, reverse=True)
    assert [band["cls"] for band in model.classes] == ["A", "B", "C", "D", "F"]
    assert mins == [90, 80, 70, 60, 0]


def test_supplier_model_is_still_a_proposal() -> None:
    """Spec §10.2 / §16: sup-1 stays 'proposed' until the commission freezes it."""
    assert load_model("sup-1").status == "proposed"
    assert load_model("sub-4").status == "active"
